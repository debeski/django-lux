"""Email setup through the environment: encryption from the port, the read-only
Email step, the relay timeout, and failures that name their hop and step."""

from dlux.tests.harness import setup_test_environment

setup_test_environment()

import asyncio
import contextlib
import io
import os
import re
import smtplib
import socket
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.template import Context, Template
from django.test import Client, SimpleTestCase, override_settings
from django.urls import reverse

from dlux import smtp_relay
from dlux.forms import SystemSettingsForm
from dlux.models import SystemSettings
from dlux.system.constants import EMAIL_CONFIG_PROVIDER_PRESETS, SETUP_STEP_EMAIL
from dlux.system.normalizers import email_config_fingerprint, normalize_email_config
from dlux.tests.smtp_mock import MockSMTPServer
from dlux.tests.test_email_step import _IsolatedSettingsTestCase
from dlux.translations import get_strings
from dlux.utils import (
    describe_mail_failure,
    effective_email_settings,
    encrypt_email_secret,
    get_email_service_status,
)
from dlux.utils.mail import DluxSMTPBackend

RELAY_ENV = {
    'SMTP_RELAY_HOST': 'smtp.provider.example',
    'SMTP_RELAY_PORT': '465',
    'SMTP_RELAY_USE_TLS': 'True',
    'SMTP_RELAY_USE_SSL': '',
    'SMTP_RELAY_USER': 'mailer@provider.example',
    'SMTP_RELAY_PASSWORD_SET': 'yes',
}


def _without(*names):
    return {name: value for name, value in os.environ.items() if name not in names}


def _store(**config):
    instance = SystemSettings.load()
    instance.email_config = normalize_email_config(config)
    instance.save(update_fields=['email_config'])
    return instance.email_config


class EncryptionFromPortTests(SimpleTestCase):
    def test_port_465_defaults_to_ssl_and_any_other_port_to_starttls(self):
        self.assertEqual(smtp_relay.resolve_encryption(465), (False, True, True))
        self.assertEqual(smtp_relay.resolve_encryption(587), (True, False, True))
        self.assertEqual(smtp_relay.resolve_encryption(25), (True, False, True))

    def test_a_set_flag_wins_over_the_port(self):
        self.assertEqual(smtp_relay.resolve_encryption(465, use_ssl=False), (True, False, False))
        self.assertEqual(smtp_relay.resolve_encryption(587, use_ssl=True), (False, True, False))
        self.assertEqual(smtp_relay.resolve_encryption(587, use_tls=False), (False, False, True))

    def test_the_env_route_reads_use_ssl_and_derives_it_when_empty(self):
        with patch.dict('os.environ', {**RELAY_ENV, 'SMTP_RELAY_PASSWORD': 'p'}, clear=False):
            config = smtp_relay.env_upstream_config()
        self.assertTrue(config['use_ssl'])
        self.assertFalse(config['use_tls'])
        self.assertTrue(config['encryption_derived'])

    def test_an_older_compose_that_forces_starttls_still_gets_ssl_on_465(self):
        """compose.yml before 1.16.2 passes SMTP_RELAY_USE_TLS=True and no SSL flag."""
        env = _without('SMTP_RELAY_USE_SSL')
        env.update({'SMTP_RELAY_HOST': 'h', 'SMTP_RELAY_PORT': '465', 'SMTP_RELAY_USE_TLS': 'True'})
        with patch.dict('os.environ', env, clear=True):
            config = smtp_relay.env_upstream_config()
        self.assertTrue(config['use_ssl'])

    def test_explicit_ssl_off_on_465_is_respected(self):
        with patch.dict('os.environ', {**RELAY_ENV, 'SMTP_RELAY_USE_SSL': 'False'}, clear=False):
            config = smtp_relay.env_upstream_config()
        self.assertFalse(config['use_ssl'])
        self.assertTrue(config['use_tls'])


class RelayTimeoutTests(_IsolatedSettingsTestCase):
    def test_the_ui_timeout_reaches_the_environment_route(self):
        _store(transport='relay', secret_storage='env', timeout=120)
        with patch.dict('os.environ', {**RELAY_ENV, 'SMTP_RELAY_PASSWORD': 'p'}, clear=False):
            config = smtp_relay.upstream_config()
        self.assertEqual(config['timeout'], 120)
        self.assertEqual(config['host'], 'smtp.provider.example')
        self.assertEqual(config['source'], 'environment')

    def test_direct_transport_leaves_the_relay_on_its_own_default(self):
        _store(transport='direct', secret_storage='env', timeout=120)
        with patch.dict('os.environ', RELAY_ENV, clear=False):
            self.assertNotIn('timeout', smtp_relay.upstream_config())


@override_settings(DEFAULT_FROM_EMAIL='noreply@provider.example')
class RelayDeliveryStepTests(_IsolatedSettingsTestCase):
    """Real sockets against a local server; short timeouts keep them fast."""

    def _deliver(self, server_port, ca_file='', **env):
        settings_env = {
            'SMTP_RELAY_HOST': '127.0.0.1',
            'SMTP_RELAY_PORT': str(server_port),
            'SMTP_RELAY_UPSTREAM_TIMEOUT': '2',
            'SMTP_RELAY_USER': '',
            'SMTP_RELAY_PASSWORD': '',
            'SMTP_RELAY_USE_TLS': 'True',
            'SMTP_RELAY_USE_SSL': '',
            'SMTP_RELAY_TLS_VERIFY': 'True',
            'SMTP_RELAY_CA_FILE': ca_file,
            **env,
        }
        _store(transport='relay', secret_storage='env')
        with patch.dict('os.environ', settings_env, clear=False):
            smtp_relay.deliver('noreply@provider.example', ['ops@example.com'], b'Subject: t\r\n\r\nbody\r\n')

    def test_implicit_tls_delivers_with_credentials(self):
        with MockSMTPServer(implicit_tls=True, username='u', password='p') as server:
            self._deliver(
                server.port, server.ca_file, SMTP_RELAY_USE_SSL='True', SMTP_RELAY_USER='u', SMTP_RELAY_PASSWORD='p',
            )
        self.assertEqual(len(server.messages), 1)
        self.assertTrue(server.messages[0]['tls'])

    def test_starttls_delivers_with_credentials(self):
        with MockSMTPServer(starttls=True, username='u', password='p') as server:
            self._deliver(server.port, server.ca_file, SMTP_RELAY_USER='u', SMTP_RELAY_PASSWORD='p')
        self.assertTrue(server.messages[0]['tls'])

    def test_a_closed_port_fails_at_connect(self):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        with self.assertRaises(smtp_relay.SMTPStepError) as caught:
            self._deliver(port)
        self.assertEqual((caught.exception.step, caught.exception.reason), ('connect', 'refused'))

    def test_a_server_that_never_greets_fails_at_the_greeting(self):
        with MockSMTPServer(silent=True) as server:
            with self.assertRaises(smtp_relay.SMTPStepError) as caught:
                self._deliver(server.port)
        self.assertEqual((caught.exception.step, caught.exception.reason), ('greeting', 'timeout'))
        self.assertIn('seconds=2', str(caught.exception))

    def test_ssl_against_a_starttls_server_fails_at_tls(self):
        with MockSMTPServer(starttls=True) as server:
            with self.assertRaises(smtp_relay.SMTPStepError) as caught:
                self._deliver(server.port, SMTP_RELAY_USE_SSL='True')
        self.assertEqual(caught.exception.step, 'tls')
        self.assertEqual(caught.exception.hint, 'starttls_port')

    def test_wrong_credentials_fail_at_auth(self):
        with MockSMTPServer(starttls=True, username='u', password='p') as server:
            with self.assertRaises(smtp_relay.SMTPStepError) as caught:
                self._deliver(server.port, server.ca_file, SMTP_RELAY_USER='u', SMTP_RELAY_PASSWORD='wrong')
        self.assertEqual((caught.exception.step, caught.exception.reason), ('auth', 'rejected'))
        self.assertIn('535', str(caught.exception))
        self.assertNotIn('wrong', str(caught.exception))

    def test_hints_name_the_likely_fix(self):
        self.assertEqual(smtp_relay.failure_hint('greeting', 'timeout', 465, True, False), 'implicit_tls')
        self.assertEqual(smtp_relay.failure_hint('tls', 'tls', 587, False, True), 'starttls_port')
        self.assertEqual(smtp_relay.failure_hint('connect', 'timeout', 587, True, False), 'firewall')
        self.assertEqual(smtp_relay.failure_hint('auth', 'rejected', 587, True, False), 'credentials')
        self.assertEqual(smtp_relay.failure_hint('send', 'rejected', 587, True, False), '')


class _BrokenReader:
    def at_eof(self):
        return False

    async def readline(self):
        raise ConnectionResetError(54, 'Connection reset by peer')


class _ClosingWriter:
    def __init__(self):
        self.lines = []

    def write(self, payload):
        self.lines.append(payload.decode().rstrip('\r\n'))

    async def drain(self):
        return None

    def get_extra_info(self, _name):
        return ('127.0.0.1', 1)

    def close(self):
        return None

    async def wait_closed(self):
        raise ConnectionResetError(54, 'Connection reset by peer')


class RelayListenerTests(SimpleTestCase):
    def test_a_probe_that_hangs_up_is_not_an_error(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            asyncio.run(smtp_relay.handle_client(_BrokenReader(), _ClosingWriter()))
        self.assertEqual(stderr.getvalue(), '')

    def test_a_step_failure_reaches_the_app_as_tokens_in_the_451(self):
        failure = smtp_relay.SMTPStepError(
            'connect', 'timeout', host='smtp.provider.example', port=465,
            use_tls=False, use_ssl=True, timeout=60, detail='timed out',
        )
        script = [
            b'EHLO app\r\n', b'MAIL FROM:<a@b.c>\r\n', b'RCPT TO:<d@e.f>\r\n', b'DATA\r\n',
            b'body\r\n', b'.\r\n', b'QUIT\r\n',
        ]

        class _Reader:
            def __init__(self):
                self.lines = list(script)

            def at_eof(self):
                return not self.lines

            async def readline(self):
                return self.lines.pop(0) if self.lines else b''

        writer = _ClosingWriter()
        with patch.object(smtp_relay, 'deliver', side_effect=failure), \
                contextlib.redirect_stderr(io.StringIO()):
            asyncio.run(smtp_relay.handle_client(_Reader(), writer))
        reply = next(line for line in writer.lines if line.startswith('451'))
        self.assertTrue(reply.startswith(
            '451 Relay delivery failed: step=connect reason=timeout hint=firewall seconds=60 '
        ), reply)
        self.assertEqual(
            smtp_relay.parse_failure_reply(reply),
            {'step': 'connect', 'reason': 'timeout', 'hint': 'firewall', 'seconds': '60'},
        )

    def test_an_oversized_body_is_read_to_its_end_before_the_refusal(self):
        script = [
            b'MAIL FROM:<a@b.c>\r\n', b'RCPT TO:<d@e.f>\r\n', b'DATA\r\n',
            b'x' * 80 + b'\r\n', b'NOOP\r\n', b'.\r\n', b'QUIT\r\n',
        ]

        class _Reader:
            def __init__(self):
                self.lines = list(script)

            def at_eof(self):
                return not self.lines

            async def readline(self):
                return self.lines.pop(0) if self.lines else b''

        writer = _ClosingWriter()
        with patch.object(smtp_relay, 'max_message_bytes', return_value=50), \
                patch.object(smtp_relay, 'deliver') as deliver:
            asyncio.run(smtp_relay.handle_client(_Reader(), writer))
        deliver.assert_not_called()
        self.assertIn('552 Message exceeds configured size limit', writer.lines)
        # The NOOP inside the body is body text, not a command.
        self.assertEqual(writer.lines.count('250 OK'), 2)
        self.assertEqual(writer.lines[-1], '221 Bye')


@override_settings(DEFAULT_FROM_EMAIL='noreply@provider.example')
class EffectiveSettingsTests(_IsolatedSettingsTestCase):
    def test_the_relay_route_shows_the_relays_values_and_only_a_password_flag(self):
        with patch.dict('os.environ', RELAY_ENV, clear=False):
            effective = effective_email_settings({'transport': 'relay', 'secret_storage': 'env'})
        self.assertEqual(effective['source'], 'relay_env')
        self.assertTrue(effective['visible'])
        self.assertEqual((effective['host'], effective['port']), ('smtp.provider.example', 465))
        self.assertEqual(effective['encryption'], 'ssl')
        self.assertTrue(effective['encryption_derived'])
        self.assertIs(effective['password_set'], True)
        self.assertNotIn('password', effective)

    def test_an_empty_password_flag_reads_not_set(self):
        with patch.dict('os.environ', {**RELAY_ENV, 'SMTP_RELAY_PASSWORD_SET': ''}, clear=False):
            effective = effective_email_settings({'transport': 'relay', 'secret_storage': 'env'})
        self.assertIs(effective['password_set'], False)

    def test_the_relay_route_is_ready_without_anything_typed_on_the_step(self):
        with patch.dict('os.environ', RELAY_ENV, clear=False):
            status = get_email_service_status(email_config={'transport': 'relay', 'secret_storage': 'env'})
        self.assertTrue(status['available'])
        self.assertEqual(status['reason'], 'relay_configured')
        self.assertEqual(status['detail'], 'smtp.provider.example:465')

    def test_a_username_without_a_password_is_not_ready(self):
        with patch.dict('os.environ', {**RELAY_ENV, 'SMTP_RELAY_PASSWORD_SET': ''}, clear=False):
            status = get_email_service_status(email_config={'transport': 'relay', 'secret_storage': 'env'})
        self.assertEqual(status['reason'], 'relay_missing_password')

    def test_an_older_compose_does_not_block_a_test_send(self):
        """Web cannot see the relay's variables; the test send is what decides."""
        env = _without(*[name for name in os.environ if name.startswith('SMTP_RELAY_')])
        with patch.dict('os.environ', env, clear=True):
            status = get_email_service_status(email_config={'transport': 'relay', 'secret_storage': 'env'})
            effective = effective_email_settings({'transport': 'relay', 'secret_storage': 'env'})
        self.assertTrue(status['available'])
        self.assertEqual(status['reason'], 'relay_env_not_visible')
        self.assertFalse(effective['visible'])
        self.assertIsNone(effective['password_set'])

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
        EMAIL_HOST='direct.provider.example', EMAIL_PORT=587, EMAIL_USE_TLS=True,
        EMAIL_HOST_USER='direct-user', EMAIL_HOST_PASSWORD='direct-secret',
    )
    def test_the_direct_route_shows_the_web_services_email_settings(self):
        _store(transport='direct', secret_storage='env', host='typed.example', port=2525)
        effective = effective_email_settings()
        self.assertEqual(effective['source'], 'django')
        self.assertEqual((effective['host'], effective['port']), ('direct.provider.example', 587))
        self.assertEqual(effective['encryption'], 'starttls')
        self.assertIs(effective['password_set'], True)
        self.assertIs(effective['internal_relay'], False)

    @override_settings(EMAIL_HOST='smtp-relay', EMAIL_PORT=1025)
    def test_a_generated_stacks_direct_route_is_marked_as_the_internal_relay(self):
        effective = effective_email_settings({'transport': 'direct', 'secret_storage': 'env'})
        self.assertIs(effective['internal_relay'], True)
        with patch.dict('os.environ', RELAY_ENV, clear=False):
            relay = effective_email_settings({'transport': 'relay', 'secret_storage': 'env'})
        self.assertIs(relay['internal_relay'], False)


@override_settings(DEFAULT_FROM_EMAIL='noreply@provider.example')
class EnvStorageStepTests(_IsolatedSettingsTestCase):
    def _render(self, **config):
        form = SystemSettingsForm(
            instance=SystemSettings(is_configured=False, email_config=normalize_email_config(config)),
            mode='setup',
        )
        return Template('{% load crispy_forms_tags %}{% crispy form %}').render(Context({'form': form}))

    def _email_step(self, html):
        start = html.index('data-email-config-section')
        return html[start:html.index('data-email-send-test-result', start)]

    def test_the_relay_route_shows_effective_values_read_only(self):
        env = {**RELAY_ENV, 'SMTP_RELAY_PASSWORD': 'hunter2-never-shown'}
        with patch.dict('os.environ', env, clear=False):
            html = self._render(transport='relay', secret_storage='env')
        step = self._email_step(html)
        self.assertIn("<code dir='ltr'>smtp.provider.example</code>", step)
        self.assertIn("<code dir='ltr'>465</code>", step)
        self.assertIn('SSL (implicit TLS) · chosen from the port', step)
        self.assertIn("<code dir='ltr'>mailer@provider.example</code>", step)
        self.assertNotIn('hunter2-never-shown', html)
        self.assertIn("class='dlux-email-provider-fields d-none'", step)

    def test_the_step_never_shows_the_relays_own_port(self):
        with patch.dict('os.environ', RELAY_ENV, clear=False):
            for config in (
                {'transport': 'relay', 'secret_storage': 'env'},
                {'transport': 'relay', 'secret_storage': 'encrypted_db', 'host': 'smtp.provider.example'},
                {'transport': 'relay', 'secret_storage': 'env', 'provider_preset': 'relay', 'port': 1025},
            ):
                self.assertNotIn('1025', self._email_step(self._render(**config)), config)

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend', EMAIL_HOST='smtp-relay', EMAIL_PORT=1025,
    )
    def test_a_generated_stacks_direct_route_names_the_relay_not_its_port(self):
        """Generated stacks point EMAIL_* at smtp-relay:1025; neither panel may show that port."""
        with patch.dict('os.environ', RELAY_ENV, clear=False):
            for transport in ('direct', 'relay'):
                step = self._email_step(self._render(transport=transport, secret_storage='env'))
                self.assertNotIn('1025', step, transport)
                self.assertIn('data-email-direct-internal-relay', step, transport)
                self.assertIn('point at the internal relay', step, transport)

    def test_relay_is_no_longer_a_provider_preset(self):
        self.assertNotIn('relay', EMAIL_CONFIG_PROVIDER_PRESETS)
        form = SystemSettingsForm(instance=SystemSettings(is_configured=False), mode='setup')
        self.assertNotIn('relay', dict(form.fields['email_config_provider_preset'].choices))

    def test_an_older_compose_says_how_to_get_the_values(self):
        env = _without(*[name for name in os.environ if name.startswith('SMTP_RELAY_')])
        with patch.dict('os.environ', env, clear=True):
            step = self._email_step(self._render(transport='relay', secret_storage='env'))
        self.assertIn('./start.sh check --fix', step)

    def test_the_test_recipient_is_not_a_setting(self):
        form = SystemSettingsForm(instance=SystemSettings(is_configured=False), mode='setup')
        self.assertNotIn('email_config_test_recipient', form.fields)
        step = self._email_step(self._render(transport='relay', secret_storage='env'))
        recipient = re.search(r'<input[^>]*data-email-test-recipient[^>]*>', step).group(0)
        self.assertNotIn('name=', recipient)
        self.assertIn('data-dlux-unsaved-ignore', recipient)
        self.assertIn("autocomplete='off'", recipient)


@override_settings(DEFAULT_FROM_EMAIL='noreply@provider.example')
class EnvStorageApplyTests(_IsolatedSettingsTestCase):
    def setUp(self):
        super().setUp()
        instance = SystemSettings.load()
        instance.is_configured = True
        instance.save(update_fields=['is_configured'])
        get_user_model().objects.create_superuser(username='mail-admin', email='m@e.com', password='adminpass123')
        self.client = Client()
        self.client.login(username='mail-admin', password='adminpass123')

    def _apply(self, data):
        return self.client.post(f"{reverse('email_config_apply')}?step={SETUP_STEP_EMAIL}", data)

    def test_environment_storage_asks_for_nothing_and_keeps_the_typed_provider(self):
        _store(
            transport='relay', secret_storage='encrypted_db', host='typed.example', port=587,
            username='typed-user', encrypted_password=encrypt_email_secret('typed-secret'), enabled=True,
        )
        with patch.dict('os.environ', RELAY_ENV, clear=False):
            response = self._apply({
                'email_config_enabled': 'on',
                'email_config_transport': 'relay',
                'email_config_secret_storage': 'env',
                'email_config_timeout': '120',
            })
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()['available'])
        stored = SystemSettings.load().email_config
        self.assertEqual(stored['secret_storage'], 'env')
        self.assertEqual(stored['timeout'], 120)
        self.assertEqual((stored['host'], stored['username']), ('typed.example', 'typed-user'))
        self.assertTrue(stored['encrypted_password'])

        # Switching back restores the typed provider, password included.
        response = self._apply({
            'email_config_enabled': 'on',
            'email_config_transport': 'relay',
            'email_config_secret_storage': 'encrypted_db',
            'email_config_host': 'typed.example',
            'email_config_port': '587',
            'email_config_use_tls': 'on',
            'email_config_username': 'typed-user',
        })
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(SystemSettings.load().email_config['encrypted_password'])

    def test_registration_can_be_enabled_on_the_environment_route(self):
        with patch.dict('os.environ', RELAY_ENV, clear=False):
            form = SystemSettingsForm(
                data={
                    'email_config_enabled': 'on',
                    'email_config_transport': 'relay',
                    'email_config_secret_storage': 'env',
                    'public_registration_enabled': 'on',
                },
                instance=SystemSettings.load(),
            )
            form.is_valid()
        self.assertNotIn('email_config', form.errors)


class LegacyRelayPresetTests(SimpleTestCase):
    def test_the_vm_config_is_cleaned_and_stays_verified(self):
        raw = {
            'transport': 'relay', 'secret_storage': 'env', 'provider_preset': 'relay',
            'host': '', 'port': 1025, 'use_ssl': True, 'default_from_email': 'a@b.c',
        }
        legacy = normalize_email_config(raw)
        # What 1.16.1 stored: port 1025 and SSL on, STARTTLS off.
        legacy_fingerprint = email_config_fingerprint({**legacy, 'port': 1025, 'use_tls': False, 'use_ssl': True})
        cleaned = normalize_email_config({**raw, 'verified': True, 'verified_fingerprint': legacy_fingerprint})
        self.assertEqual(cleaned['provider_preset'], 'custom')
        self.assertEqual(cleaned['port'], 587)
        # 587 is STARTTLS: the SSL flag the VM row carried is reset with the port.
        self.assertEqual((cleaned['use_tls'], cleaned['use_ssl']), (True, False))
        self.assertTrue(cleaned['verified'])
        self.assertEqual(cleaned['verified_fingerprint'], email_config_fingerprint(cleaned))
        self.assertEqual(normalize_email_config(cleaned), cleaned)

    def test_a_real_provider_on_1025_is_left_alone(self):
        self.assertEqual(normalize_email_config({'transport': 'relay', 'host': 'mailpit', 'port': 1025})['port'], 1025)
        self.assertEqual(normalize_email_config({'transport': 'direct', 'port': 1025})['port'], 1025)


@override_settings(DEFAULT_FROM_EMAIL='noreply@provider.example')
class FailureMessageTests(_IsolatedSettingsTestCase):
    RELAY = {'transport': 'relay', 'secret_storage': 'env'}

    def test_a_provider_timeout_behind_the_relay_names_hop_step_and_fix(self):
        reply = (
            'Relay delivery failed: step=connect reason=timeout hint=firewall seconds=60 '
            'connect smtp.provider.example:465 ssl: timed out'
        )
        exc = smtplib.SMTPDataError(451, reply.encode())
        with patch.dict('os.environ', RELAY_ENV, clear=False):
            failure = describe_mail_failure(exc, get_strings('en'), email_config=self.RELAY)
        self.assertEqual((failure['hop'], failure['step'], failure['reason']), ('provider_relay', 'connect', 'timeout'))
        self.assertEqual(
            failure['message'],
            'Provider server, through the internal relay: connecting to smtp.provider.example:465 failed — '
            'no answer within 60 seconds. Outbound connections to port 465 may be blocked by a firewall on '
            'this server or its network.',
        )

    def test_a_relay_that_predates_step_tokens_still_says_which_hop(self):
        exc = smtplib.SMTPDataError(451, b'Relay delivery failed: timed out')
        with patch.dict('os.environ', RELAY_ENV, clear=False):
            failure = describe_mail_failure(exc, get_strings('en'), email_config=self.RELAY)
        self.assertEqual((failure['hop'], failure['step'], failure['reason']), ('provider_relay', 'unknown', 'timeout'))
        self.assertTrue(failure['message'].startswith('Provider server, through the internal relay: delivery to'))

    def test_an_unreachable_relay_is_the_first_hop_and_never_shows_its_port(self):
        exc = ConnectionRefusedError(61, 'Connection refused')
        exc.dlux_step = 'connect'
        failure = describe_mail_failure(exc, get_strings('en'), email_config=self.RELAY)
        self.assertEqual(failure['hop'], 'relay')
        self.assertEqual(
            failure['message'],
            'Internal relay: connecting to the relay service failed — the connection was refused.',
        )
        self.assertNotIn('1025', failure['message'])

    @override_settings(EMAIL_HOST='smtp-relay', EMAIL_PORT=1025)
    def test_a_direct_send_to_the_internal_relay_takes_the_relays_hops(self):
        direct = {'transport': 'direct', 'secret_storage': 'env'}
        refused = ConnectionRefusedError(61, 'Connection refused')
        refused.dlux_step = 'connect'
        failure = describe_mail_failure(refused, get_strings('en'), email_config=direct)
        self.assertEqual(failure['hop'], 'relay')
        self.assertNotIn('1025', failure['message'])

        reply = (
            'Relay delivery failed: step=auth reason=rejected hint=credentials '
            'auth smtp.provider.example:587 starttls: 535 bad'
        )
        with patch.dict('os.environ', RELAY_ENV, clear=False):
            failure = describe_mail_failure(
                smtplib.SMTPDataError(451, reply.encode()), get_strings('en'), email_config=direct,
            )
        self.assertEqual((failure['hop'], failure['step']), ('provider_relay', 'auth'))
        self.assertIn('smtp.provider.example:587', failure['message'])
        self.assertIn('SMTP_RELAY_USER and SMTP_RELAY_PASSWORD', failure['message'])

    def test_the_message_is_translated(self):
        exc = smtplib.SMTPDataError(
            451, b'Relay delivery failed: step=auth reason=rejected hint=credentials auth smtp.p.example:587 starttls: 535 bad',
        )
        with patch.dict('os.environ', RELAY_ENV, clear=False):
            failure = describe_mail_failure(exc, get_strings('ar'), email_config=self.RELAY)
        self.assertIn('خادم المزود، عبر المرحّل الداخلي', failure['message'])
        self.assertIn('تسجيل الدخول إلى smtp.p.example:587', failure['message'])
        self.assertIn('SMTP_RELAY_USER', failure['message'])

    def test_a_direct_send_records_its_step(self):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        backend = DluxSMTPBackend(host='127.0.0.1', port=port, timeout=2, use_tls=False)
        from django.core.mail import EmailMessage

        with self.assertRaises(ConnectionRefusedError) as caught:
            backend.send_messages([EmailMessage('s', 'b', 'a@b.c', ['d@e.f'])])
        self.assertEqual(caught.exception.dlux_step, 'connect')

    def test_a_direct_send_refuses_an_untrusted_certificate_at_tls(self):
        """Django's backend verifies certificates; the mock's CA is private."""
        import ssl

        from django.core.mail import EmailMessage

        with MockSMTPServer(starttls=True, username='u', password='p') as server:
            backend = DluxSMTPBackend(
                host='127.0.0.1', port=server.port, timeout=3, use_tls=True, username='u', password='p',
            )
            with self.assertRaises(ssl.SSLError) as caught:
                backend.send_messages([EmailMessage('s', 'b', 'a@b.c', ['d@e.f'])])
        self.assertEqual(caught.exception.dlux_step, 'tls')
        failure = describe_mail_failure(
            caught.exception, get_strings('en'),
            email_config={'transport': 'direct', 'secret_storage': 'encrypted_db', 'host': '127.0.0.1', 'port': server.port},
        )
        self.assertEqual((failure['step'], failure['reason']), ('tls', 'certificate'))


@override_settings(DEFAULT_FROM_EMAIL='noreply@provider.example')
class SendTestViewTests(_IsolatedSettingsTestCase):
    def setUp(self):
        super().setUp()
        settings_row = SystemSettings.load()
        settings_row.is_configured = True
        settings_row.save()
        get_user_model().objects.create_superuser(username='test-admin', email='t@e.com', password='adminpass123')
        self.client = Client()
        self.client.login(username='test-admin', password='adminpass123')

    def test_a_failed_test_names_the_step(self):
        _store(transport='relay', secret_storage='env', enabled=True)
        exc = smtplib.SMTPDataError(
            451, b'Relay delivery failed: step=greeting reason=timeout hint=implicit_tls seconds=60 '
                 b'greeting smtp.provider.example:465 starttls: timed out',
        )
        with patch.dict('os.environ', RELAY_ENV, clear=False), \
                patch('dlux.views.options.send_dlux_mail', side_effect=exc):
            response = self.client.post(reverse('email_send_test'), {'recipient': 'ops@example.com'})
        self.assertEqual(response.status_code, 502)
        payload = response.json()
        self.assertEqual((payload['hop'], payload['step'], payload['reason']), ('provider_relay', 'greeting', 'timeout'))
        self.assertIn('waiting for the greeting from smtp.provider.example:465', payload['message'])
        self.assertIn('SMTP_RELAY_USE_SSL=True', payload['message'])


class ScaffoldRelayEnvironmentTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from dlux.cli import main

        cls._tmp = tempfile.TemporaryDirectory()
        target = Path(cls._tmp.name) / 'mail_demo'
        main(['startproject', 'mail_demo', str(target)])
        cls.compose = (target / 'compose.yml').read_text(encoding='utf-8')
        cls.env = (target / '.secrets' / '.env').read_text(encoding='utf-8')

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()
        super().tearDownClass()

    def _block(self, header):
        start = self.compose.index(header)
        rest = self.compose[start + len(header):]
        end = re.search(r'^\S|^  [a-z][\w-]*:$', rest, re.MULTILINE)
        return rest[:end.start()] if end else rest

    def test_web_and_worker_share_the_non_secret_relay_values(self):
        shared = self._block('x-environment:')
        for line in (
            'SMTP_RELAY_HOST: "${SMTP_RELAY_HOST:-smtp.gmail.com}"',
            'SMTP_RELAY_PORT: "${SMTP_RELAY_PORT:-587}"',
            'SMTP_RELAY_USE_TLS: "${SMTP_RELAY_USE_TLS:-True}"',
            'SMTP_RELAY_USE_SSL: "${SMTP_RELAY_USE_SSL:-}"',
            'SMTP_RELAY_USER: "${SMTP_RELAY_USER:-}"',
            'SMTP_RELAY_PASSWORD_SET: "${SMTP_RELAY_PASSWORD:+yes}"',
        ):
            self.assertIn(line, shared)
        self.assertNotIn('SMTP_RELAY_PASSWORD: ', shared)

    def test_only_the_relay_gets_the_password(self):
        self.assertEqual(self.compose.count('SMTP_RELAY_PASSWORD: "${SMTP_RELAY_PASSWORD:-}"'), 1)
        self.assertIn('SMTP_RELAY_PASSWORD: "${SMTP_RELAY_PASSWORD:-}"', self._block('  smtp-relay:'))

    def test_the_env_template_offers_use_ssl(self):
        self.assertIn('\nSMTP_RELAY_USE_SSL=\n', self.env)
