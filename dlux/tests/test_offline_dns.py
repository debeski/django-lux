"""The package suite never waits on DNS.

The System Settings form probes the SMTP relay by its stack name each time it is
built, and the suite builds that form hundreds of times. Once a runner's resolver
stopped answering, each probe waited ten seconds for the lookup and one
PostgreSQL job ran for most of an hour without finishing. `dlux.tests.offline_dns`
answers every hostname but localhost at once; these tests keep it installed and
keep the probe on it.
"""

import socket
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from dlux.forms import SystemSettingsForm
from dlux.models import SystemSettings
from dlux.tests import offline_dns
from dlux.utils import internal_smtp_relay_available

_needs_dns = offline_dns.needs_dns
_machine_resolver = offline_dns._real_getaddrinfo


def _literals_only(host, *args, **kwargs):
    if _needs_dns(host):
        raise AssertionError(f'the machine resolver was asked about {host!r}')
    return _machine_resolver(host, *args, **kwargs)


class OfflineResolverTests(SimpleTestCase):
    def test_the_suite_runs_with_the_offline_resolver(self):
        self.assertIs(socket.getaddrinfo, offline_dns.getaddrinfo)

    def test_hostnames_fail_at_once_without_asking_the_resolver(self):
        with patch.object(offline_dns, '_real_getaddrinfo', side_effect=_literals_only):
            for host in ('smtp-relay', 'ocr', 'no-such-relay-host.invalid', 'smtp.example.com', b'composer-agent'):
                with self.subTest(host=host), self.assertRaises(socket.gaierror) as caught:
                    socket.getaddrinfo(host, 25)
                self.assertEqual(caught.exception.errno, socket.EAI_NONAME)

    def test_localhost_and_address_literals_still_resolve(self):
        for host in ('localhost', 'LOCALHOST.', '127.0.0.1', None):
            with self.subTest(host=host):
                self.assertTrue(socket.getaddrinfo(host, 80, type=socket.SOCK_STREAM))


class RelayProbeStaysOffTheResolverTests(TestCase):
    def test_building_the_settings_form_never_asks_the_resolver(self):
        with patch.object(offline_dns, '_real_getaddrinfo', side_effect=_literals_only), \
                patch.object(offline_dns, 'needs_dns', wraps=_needs_dns) as checked:
            SystemSettingsForm(instance=SystemSettings.load(), mode='modal')
            self.assertFalse(internal_smtp_relay_available())
        self.assertIn('smtp-relay', [call.args[0] for call in checked.call_args_list])
