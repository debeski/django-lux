"""SMTP timeout pairing between the app and the scaffolded internal relay.

Relay delivery is two hops (app -> relay -> provider) and only the relay can see
why the provider hop failed. If the app's client timeout fires first, the operator
gets a bare "Connection unexpectedly closed: timed out" while the real reason lands
in the relay log ~20s later. These tests pin the ordering that keeps the reason
reachable.
"""

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from unittest.mock import patch

from django.test import TestCase, override_settings

from dlux.utils.mail import (
    DLUX_SMTP_DIRECT_TIMEOUT,
    DLUX_SMTP_RELAY_CLIENT_TIMEOUT,
    DLUX_SMTP_RELAY_UPSTREAM_TIMEOUT,
    send_dlux_mail,
)

class SmtpTimeoutOrderingTests(TestCase):
    def test_relay_upstream_timeout_stays_below_the_client_timeout(self):
        """The relay must lose the race so its 451 carries the real cause."""
        self.assertLess(DLUX_SMTP_RELAY_UPSTREAM_TIMEOUT, DLUX_SMTP_RELAY_CLIENT_TIMEOUT)
        # Enough headroom for the relay's own connect/TLS/auth round trips to be
        # reported rather than cut off by the client.
        self.assertGreaterEqual(
            DLUX_SMTP_RELAY_CLIENT_TIMEOUT - DLUX_SMTP_RELAY_UPSTREAM_TIMEOUT, 5,
        )

    def test_direct_transport_is_bounded_but_tolerates_a_slow_server(self):
        """Two failure modes pull in opposite directions; stay between them.

        Too low and a slow-but-working server (in-line scanning, legacy relays)
        fails every send while looking identical to an outage. Too high and a dead
        host hangs interactive auth, since OTP mail is sent during login. Django
        itself defaults to no timeout at all, so anything bounded beats the stock
        behaviour — but keep it comfortably under a minute.
        """
        self.assertGreaterEqual(DLUX_SMTP_DIRECT_TIMEOUT, 15)
        self.assertLessEqual(DLUX_SMTP_DIRECT_TIMEOUT, 30)
        self.assertLess(DLUX_SMTP_DIRECT_TIMEOUT, DLUX_SMTP_RELAY_CLIENT_TIMEOUT)

    def test_relay_defaults_tolerate_a_server_that_is_slow_on_data(self):
        """Connect/EHLO/AUTH can be instant while DATA takes 30-60s — size for DATA."""
        self.assertGreaterEqual(DLUX_SMTP_RELAY_UPSTREAM_TIMEOUT, 60)

    def test_the_packaged_relay_ships_the_same_default(self):
        """The constant and the relay must not drift apart."""
        from dlux import smtp_relay

        self.assertEqual(smtp_relay.DEFAULT_UPSTREAM_TIMEOUT, DLUX_SMTP_RELAY_UPSTREAM_TIMEOUT)


class SendMailTimeoutSelectionTests(TestCase):
    def _captured_timeout(self, transport):
        config = {
            'backend': 'django.core.mail.backends.smtp.EmailBackend',
            'transport': transport,
            'host': 'smtp-relay' if transport == 'relay' else 'smtp.example.com',
            'port': 1025 if transport == 'relay' else 587,
            'username': '',
            'password': '',
            'use_tls': False,
            'use_ssl': False,
            'from_email': 'noreply@example.com',
        }
        with patch('dlux.utils.mail.get_dlux_email_config', return_value=config), \
                patch('dlux.utils.mail.get_connection') as get_connection:
            get_connection.return_value.send_messages.return_value = 1
            send_dlux_mail('subject', 'body', ['someone@example.com'], alert_on_failure=False)
        return get_connection.call_args.kwargs['timeout']

    def test_relay_transport_waits_long_enough_for_the_relays_own_verdict(self):
        self.assertEqual(self._captured_timeout('relay'), DLUX_SMTP_RELAY_CLIENT_TIMEOUT)

    def test_direct_transport_uses_the_short_timeout(self):
        self.assertEqual(self._captured_timeout('direct'), DLUX_SMTP_DIRECT_TIMEOUT)


class UiConfiguredTimeoutTests(TestCase):
    """The timeout is settable from the Email step, not just SMTP_RELAY_* env vars."""

    def test_relay_transport_derives_the_client_budget_from_the_ui_value(self):
        from dlux.utils.mail import (
            DLUX_SMTP_RELAY_CLIENT_HEADROOM,
            resolve_smtp_timeouts,
        )

        upstream, client = resolve_smtp_timeouts({'transport': 'relay', 'timeout': 120})

        self.assertEqual(upstream, 120)
        self.assertEqual(client, 120 + DLUX_SMTP_RELAY_CLIENT_HEADROOM)
        # Raising it in the UI can never invert the ordering the 451 reason needs.
        self.assertLess(upstream, client)

    def test_direct_transport_uses_the_ui_value_as_the_client_timeout(self):
        from dlux.utils.mail import resolve_smtp_timeouts

        self.assertEqual(resolve_smtp_timeouts({'transport': 'direct', 'timeout': 45}), (45, 45))

    def test_blank_or_junk_falls_back_to_the_shipped_defaults(self):
        from dlux.utils.mail import resolve_smtp_timeouts

        for value in (0, None, '', 'abc'):
            with self.subTest(value=value):
                upstream, client = resolve_smtp_timeouts({'transport': 'relay', 'timeout': value})
                self.assertEqual(upstream, DLUX_SMTP_RELAY_UPSTREAM_TIMEOUT)
                self.assertEqual(client, DLUX_SMTP_RELAY_CLIENT_TIMEOUT)

    def test_normalizer_clamps_the_stored_value(self):
        from dlux.system.normalizers import normalize_email_config

        self.assertEqual(normalize_email_config({'timeout': 2})['timeout'], 5)
        self.assertEqual(normalize_email_config({'timeout': 5000})['timeout'], 300)
        self.assertEqual(normalize_email_config({'timeout': 'abc'})['timeout'], 0)
        self.assertEqual(normalize_email_config({'timeout': 90})['timeout'], 90)

    def test_the_relay_prefers_the_ui_timeout_over_the_environment(self):
        from unittest.mock import patch

        import smtplib

        from dlux import smtp_relay

        captured = {}

        class _FakeSMTP:
            def __init__(self, host, port, timeout=None):
                captured['timeout'] = timeout

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def ehlo(self):
                pass

            def sendmail(self, *args):
                pass

        upstream = {'host': 'mail.example.com', 'port': 465, 'use_ssl': True, 'timeout': 111}
        with patch.object(smtp_relay, 'upstream_config', return_value=upstream), \
                patch.object(smtplib, 'SMTP_SSL', _FakeSMTP), \
                patch.dict('os.environ', {'SMTP_RELAY_UPSTREAM_TIMEOUT': '30'}, clear=False):
            smtp_relay.deliver('a@b.com', ['c@d.com'], b'hi')

        self.assertEqual(captured['timeout'], 111)
