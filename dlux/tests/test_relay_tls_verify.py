"""The relay verifies its provider's certificate before it signs in.

Real sockets against ``MockSMTPServer``, whose certificate a private CA signed:
no system store trusts it, ``SMTP_RELAY_CA_FILE`` does, and the off switch
(``SMTP_RELAY_TLS_VERIFY=False`` or the Email step's) accepts it unverified.
"""

import contextlib
import hashlib
import io
import json
import os
import smtplib
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.template import Context, Template
from django.test import SimpleTestCase, override_settings

from dlux import smtp_relay, smtp_session
from dlux.forms import SystemSettingsForm
from dlux.forms.builders import build_email_effective_panel
from dlux.forms.system_settings_groups.email import pack_email_config
from dlux.models import SystemSettings
from dlux.system.constants import EMAIL_CONFIG_VERIFIED_FIELDS
from dlux.system.normalizers import email_config_fingerprint, normalize_email_config
from dlux.tests.smtp_mock import MockSMTPServer
from dlux.tests.test_email_step import _IsolatedSettingsTestCase
from dlux.translations import get_strings
from dlux.utils import describe_mail_failure, effective_email_settings, encrypt_email_secret

MESSAGE = b'Subject: t\r\n\r\nbody\r\n'
RELAY_ENV_ROUTE = {'transport': 'relay', 'secret_storage': 'env'}


def _store(**config):
    instance = SystemSettings.load()
    instance.email_config = normalize_email_config(config)
    instance.save(update_fields=['email_config'])
    return instance.email_config


def _relay_reply(exc):
    """What the app receives from the relay for a failed delivery."""
    return smtplib.SMTPDataError(451, f'Relay delivery failed: {smtp_relay.smtp_reason(exc)}'.encode())


@override_settings(DEFAULT_FROM_EMAIL='noreply@provider.example')
class RelayCertificateTests(_IsolatedSettingsTestCase):
    def _env(self, server, **env):
        return {
            'SMTP_RELAY_HOST': '127.0.0.1',
            'SMTP_RELAY_PORT': str(server.port),
            'SMTP_RELAY_UPSTREAM_TIMEOUT': '3',
            'SMTP_RELAY_USER': 'u',
            'SMTP_RELAY_PASSWORD': 'p',
            'SMTP_RELAY_USE_TLS': 'True',
            'SMTP_RELAY_USE_SSL': '',
            'SMTP_RELAY_TLS_VERIFY': '',
            'SMTP_RELAY_CA_FILE': '',
            **env,
        }

    def _deliver(self, server, *, database_route=False, **env):
        if not database_route:
            _store(**RELAY_ENV_ROUTE)
        stderr = io.StringIO()
        with patch.dict('os.environ', self._env(server, **env), clear=False), contextlib.redirect_stderr(stderr):
            smtp_relay.deliver('noreply@provider.example', ['ops@example.com'], MESSAGE)
        return stderr.getvalue()

    def _refused(self, server, **env):
        with self.assertRaises(smtp_relay.SMTPStepError) as caught:
            self._deliver(server, **env)
        return caught.exception

    def assertRefusedBeforeSignIn(self, server, error):
        self.assertEqual((error.step, error.reason, error.hint), ('tls', 'certificate', 'tls_verify'))
        self.assertIn('step=tls reason=certificate hint=tls_verify', str(error))
        self.assertEqual(server.auth_attempts, 0)
        self.assertEqual(server.messages, [])

    def test_starttls_refuses_an_untrusted_certificate_before_signing_in(self):
        with MockSMTPServer(starttls=True, username='u', password='p') as server:
            error = self._refused(server)
        self.assertRefusedBeforeSignIn(server, error)

    def test_implicit_tls_refuses_an_untrusted_certificate_before_signing_in(self):
        with MockSMTPServer(implicit_tls=True, username='u', password='p') as server:
            error = self._refused(server, SMTP_RELAY_USE_SSL='True')
        self.assertRefusedBeforeSignIn(server, error)

    def test_a_ca_file_trusts_the_private_ca_over_starttls(self):
        with MockSMTPServer(starttls=True, username='u', password='p') as server:
            log = self._deliver(server, SMTP_RELAY_CA_FILE=server.ca_file)
        self.assertEqual(len(server.messages), 1)
        self.assertTrue(server.messages[0]['tls'])
        self.assertNotIn('verification is off', log)

    def test_a_ca_file_trusts_the_private_ca_over_implicit_tls(self):
        with MockSMTPServer(implicit_tls=True, username='u', password='p') as server:
            self._deliver(server, SMTP_RELAY_USE_SSL='True', SMTP_RELAY_CA_FILE=server.ca_file)
        self.assertEqual(len(server.messages), 1)

    def test_a_trusted_certificate_for_another_host_is_refused(self):
        with MockSMTPServer(starttls=True, username='u', password='p', cert_names=('mail.other.example',)) as server:
            error = self._refused(server, SMTP_RELAY_CA_FILE=server.ca_file)
        self.assertRefusedBeforeSignIn(server, error)
        self.assertIn('127.0.0.1', error.detail)

    def test_the_switch_accepts_an_untrusted_certificate_and_logs_every_send(self):
        with MockSMTPServer(starttls=True, username='u', password='p') as server:
            first = self._deliver(server, SMTP_RELAY_TLS_VERIFY='False')
            second = self._deliver(server, SMTP_RELAY_TLS_VERIFY='False')
        self.assertEqual(len(server.messages), 2)
        for log in (first, second):
            self.assertIn(f'certificate verification is off for 127.0.0.1:{server.port}', log)
            self.assertIn('SMTP_RELAY_TLS_VERIFY=False', log)

    def test_an_empty_or_true_switch_verifies(self):
        for value in ('', 'True', 'yes'):
            with MockSMTPServer(starttls=True, username='u', password='p') as server:
                error = self._refused(server, SMTP_RELAY_TLS_VERIFY=value)
            self.assertEqual(error.reason, 'certificate', value)

    def test_an_unreadable_ca_file_fails_before_connecting(self):
        with tempfile.TemporaryDirectory() as tmp:
            not_pem = Path(tmp) / 'not-a-ca.pem'
            not_pem.write_text('not a certificate\n')
            for path in (str(Path(tmp) / 'missing.pem'), str(not_pem)):
                with MockSMTPServer(starttls=True, username='u', password='p') as server:
                    error = self._refused(server, SMTP_RELAY_CA_FILE=path)
                self.assertEqual((error.step, error.reason), ('config', 'ca_file'), path)
                self.assertIn(f'SMTP_RELAY_CA_FILE {path}', str(error))
                self.assertEqual(server.auth_attempts, 0)

    def test_with_the_switch_off_the_ca_file_is_not_read(self):
        with MockSMTPServer(starttls=True, username='u', password='p') as server:
            self._deliver(server, SMTP_RELAY_TLS_VERIFY='False', SMTP_RELAY_CA_FILE='/nonexistent/ca.pem')
        self.assertEqual(len(server.messages), 1)

    def _store_database_route(self, server, **config):
        _store(
            transport='relay', secret_storage='encrypted_db', host='127.0.0.1', port=server.port,
            use_tls=True, use_ssl=False, username='u', encrypted_password=encrypt_email_secret('p'), timeout=5,
            **config,
        )

    def test_the_database_route_verifies_by_default(self):
        with MockSMTPServer(starttls=True, username='u', password='p') as server:
            self._store_database_route(server)
            error = self._refused(server, database_route=True, SMTP_RELAY_HOST='unused.example')
        self.assertRefusedBeforeSignIn(server, error)

    def test_the_database_route_uses_the_containers_ca_file(self):
        with MockSMTPServer(starttls=True, username='u', password='p') as server:
            self._store_database_route(server)
            self._deliver(
                server, database_route=True, SMTP_RELAY_HOST='unused.example', SMTP_RELAY_CA_FILE=server.ca_file,
            )
        self.assertEqual(len(server.messages), 1)

    def test_the_database_route_follows_the_steps_switch_not_the_environments(self):
        with MockSMTPServer(starttls=True, username='u', password='p') as server:
            self._store_database_route(server, tls_verify=False)
            log = self._deliver(
                server, database_route=True, SMTP_RELAY_HOST='unused.example', SMTP_RELAY_TLS_VERIFY='True',
            )
        self.assertEqual(len(server.messages), 1)
        self.assertIn('(the Email step)', log)
        with MockSMTPServer(starttls=True, username='u', password='p') as server:
            self._store_database_route(server)
            error = self._refused(
                server, database_route=True, SMTP_RELAY_HOST='unused.example', SMTP_RELAY_TLS_VERIFY='False',
            )
        self.assertEqual(error.reason, 'certificate')

    def test_the_app_names_the_switch_on_each_route(self):
        with MockSMTPServer(starttls=True, username='u', password='p') as server:
            error = self._refused(server)
        with patch.dict('os.environ', self._env(server), clear=False):
            env_route = describe_mail_failure(_relay_reply(error), get_strings('en'), email_config=RELAY_ENV_ROUTE)
            arabic = describe_mail_failure(_relay_reply(error), get_strings('ar'), email_config=RELAY_ENV_ROUTE)
        self.assertEqual(
            (env_route['hop'], env_route['step'], env_route['reason'], env_route['hint']),
            ('provider_relay', 'tls', 'certificate', 'tls_verify'),
        )
        self.assertIn('the server certificate was not trusted', env_route['message'])
        self.assertIn('SMTP_RELAY_CA_FILE', env_route['message'])
        self.assertIn('SMTP_RELAY_TLS_VERIFY=False', env_route['message'])
        self.assertIn('SMTP_RELAY_TLS_VERIFY=False', arabic['message'])
        self.assertIn('شهادة الخادم غير موثوقة', arabic['message'])

        database_route = describe_mail_failure(
            _relay_reply(error), get_strings('en'),
            email_config={'transport': 'relay', 'secret_storage': 'encrypted_db', 'host': '127.0.0.1', 'port': 587},
        )
        self.assertIn("turn off Verify the provider's certificate", database_route['message'])
        self.assertNotIn('SMTP_RELAY_TLS_VERIFY', database_route['message'])

    def test_a_bad_ca_file_reads_as_a_settings_problem(self):
        with MockSMTPServer(starttls=True) as server:
            error = self._refused(server, SMTP_RELAY_CA_FILE='/nonexistent/ca.pem')
        failure = describe_mail_failure(_relay_reply(error), get_strings('en'), email_config=RELAY_ENV_ROUTE)
        self.assertEqual((failure['step'], failure['reason']), ('config', 'ca_file'))
        self.assertIn('the CA file could not be loaded (SMTP_RELAY_CA_FILE /nonexistent/ca.pem', failure['message'])


class SwitchParsingTests(SimpleTestCase):
    def test_the_environment_switch_is_on_unless_set_false(self):
        for value, expected in ((None, True), ('', True), ('True', True), ('1', True), ('False', False), ('no', False)):
            env = {name: v for name, v in os.environ.items() if name != 'SMTP_RELAY_TLS_VERIFY'}
            if value is not None:
                env['SMTP_RELAY_TLS_VERIFY'] = value
            with patch.dict('os.environ', env, clear=True):
                self.assertIs(smtp_session.env_upstream_config()['tls_verify'], expected, value)

    def test_the_stored_switch_is_on_unless_set_false(self):
        for value, expected in ((None, True), ('', True), (True, True), (False, False), ('false', False), ('off', False)):
            config = {} if value is None else {'tls_verify': value}
            self.assertIs(normalize_email_config(config)['tls_verify'], expected, value)

    def test_a_direct_failure_gets_no_relay_switch(self):
        self.assertEqual(smtp_session.failure_hint('tls', 'certificate', 587, True, False), '')
        self.assertEqual(smtp_session.failure_hint('tls', 'certificate', 587, True, False, relay=True), 'tls_verify')

    def test_tls_context_verifies_unless_told_not_to(self):
        import ssl

        verifying = smtp_session.tls_context()
        self.assertEqual(verifying.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(verifying.check_hostname)
        lax = smtp_session.tls_context(False, '/nonexistent/ca.pem')
        self.assertEqual(lax.verify_mode, ssl.CERT_NONE)
        self.assertFalse(lax.check_hostname)


class StoredSwitchTests(SimpleTestCase):
    BASE = {
        'transport': 'relay', 'secret_storage': 'encrypted_db', 'host': 'smtp.provider.example', 'port': 587,
        'use_tls': True, 'username': 'u', 'encrypted_password': 'stored-secret', 'default_from_email': 'a@b.example',
    }

    def test_a_verifying_configuration_keeps_its_stored_digest(self):
        """Tests passed before the switch existed stay valid after an upgrade."""
        config = normalize_email_config(self.BASE)
        digest_without_switch = hashlib.sha256(json.dumps(
            [str(config.get(field, '')) for field in EMAIL_CONFIG_VERIFIED_FIELDS], separators=(',', ':'),
        ).encode('utf-8')).hexdigest()
        self.assertEqual(email_config_fingerprint(config), digest_without_switch)
        verified = normalize_email_config({
            **self.BASE, 'verified': True, 'verified_at': 'then', 'verified_fingerprint': digest_without_switch,
        })
        self.assertTrue(verified['verified'])
        self.assertTrue(verified['tls_verify'])

    def test_switching_checks_off_needs_a_new_test(self):
        fingerprint = email_config_fingerprint(normalize_email_config(self.BASE))
        stored = normalize_email_config({
            **self.BASE, 'tls_verify': False, 'verified': True, 'verified_fingerprint': fingerprint,
        })
        self.assertFalse(stored['verified'])

    def _values(self, transport, storage, **extra):
        return {
            'email_config_transport': transport, 'email_config_secret_storage': storage,
            'email_config_host': 'smtp.provider.example', 'email_config_port': 587,
            'email_config_use_tls': True, 'email_config_use_ssl': False, 'email_config_username': 'u',
            **extra,
        }

    def test_the_relay_step_saves_the_switch(self):
        existing = normalize_email_config(self.BASE)
        shown = {'email_config_tls_verify_shown': True}
        packed = pack_email_config(
            self._values('relay', 'encrypted_db', email_config_tls_verify=False, **shown), existing,
        )
        self.assertIs(packed['tls_verify'], False)
        packed = pack_email_config(
            self._values('relay', 'encrypted_db', email_config_tls_verify=True, **shown), packed,
        )
        self.assertIs(packed['tls_verify'], True)

    def test_a_post_that_never_showed_the_switch_cannot_turn_it_off(self):
        existing = normalize_email_config(self.BASE)
        packed = pack_email_config(self._values('relay', 'encrypted_db', email_config_tls_verify=False), existing)
        self.assertIs(packed['tls_verify'], True)

    def test_routes_without_the_switch_keep_the_stored_value(self):
        existing = normalize_email_config({**self.BASE, 'tls_verify': False})
        for transport, storage in (('direct', 'encrypted_db'), ('relay', 'env'), ('direct', 'env')):
            packed = pack_email_config(
                self._values(transport, storage, email_config_tls_verify=True, email_config_tls_verify_shown=True),
                existing,
            )
            self.assertIs(packed['tls_verify'], False, (transport, storage))


@override_settings(DEFAULT_FROM_EMAIL='noreply@provider.example')
class EmailStepSwitchTests(_IsolatedSettingsTestCase):
    def _email_step(self, **config):
        form = SystemSettingsForm(
            instance=SystemSettings(is_configured=False, email_config=normalize_email_config(config)),
            mode='setup',
        )
        html = Template('{% load crispy_forms_tags %}{% crispy form %}').render(Context({'form': form}))
        start = html.index('data-email-config-section')
        return form, html[start:html.index('data-email-send-test-result', start)]

    def _switch(self, step):
        """The switch's column classes and markup (through its marker input)."""
        at = step.index("data-dlux-email-toggle-field='email_config_tls_verify'")
        column = step.rfind('class="', 0, at) + len('class="')
        end = step.index("name='email_config_tls_verify_shown'", at)
        return step[column:step.index('"', column)], step[at:end]

    def test_the_relay_route_shows_the_switch_on_by_default(self):
        form, step = self._email_step(transport='relay', secret_storage='encrypted_db', host='smtp.provider.example')
        self.assertTrue(form.initial['email_config_tls_verify'])
        classes, markup = self._switch(step)
        self.assertNotIn('d-none', classes)
        self.assertIn("Verify the provider&#x27;s certificate", markup)
        self.assertIn('SMTP_RELAY_CA_FILE', markup)
        self.assertIn(' checked', markup)

    def test_a_stored_off_switch_renders_unchecked(self):
        form, step = self._email_step(
            transport='relay', secret_storage='encrypted_db', host='smtp.provider.example', tls_verify=False,
        )
        self.assertFalse(form.initial['email_config_tls_verify'])
        self.assertNotIn(' checked', self._switch(step)[1])

    def test_direct_smtp_hides_the_switch(self):
        _form, step = self._email_step(transport='direct', secret_storage='encrypted_db', host='smtp.provider.example')
        self.assertIn('d-none', self._switch(step)[0])

    def _save(self, **data):
        form = SystemSettingsForm(data={
            'email_config_enabled': 'on',
            'email_config_transport': 'relay',
            'email_config_secret_storage': 'encrypted_db',
            'email_config_provider_preset': 'custom',
            'email_config_host': 'smtp.provider.example',
            'email_config_port': '587',
            'email_config_use_tls': 'on',
            'email_config_username': 'u',
            'email_config_default_from_email': 'a@b.example',
            **data,
        }, instance=SystemSettings.load())
        form.is_valid()
        return form.cleaned_data['email_config']

    def test_only_a_shown_unticked_switch_turns_checks_off(self):
        self.assertIs(self._save(email_config_tls_verify_shown='1')['tls_verify'], False)
        self.assertIs(self._save()['tls_verify'], True)
        self.assertIs(
            self._save(email_config_tls_verify_shown='1', email_config_tls_verify='on')['tls_verify'], True,
        )

    def test_the_relay_panel_says_how_the_certificate_is_checked(self):
        strings = get_strings('en')
        base = {
            'SMTP_RELAY_HOST': 'smtp.provider.example', 'SMTP_RELAY_PORT': '587', 'SMTP_RELAY_USE_TLS': 'True',
            'SMTP_RELAY_USE_SSL': '', 'SMTP_RELAY_USER': 'u', 'SMTP_RELAY_PASSWORD_SET': 'yes',
            'SMTP_RELAY_TLS_VERIFY': 'True', 'SMTP_RELAY_CA_FILE': '',
        }
        cases = (
            ({}, 'checked against the system CAs</dd>'),
            ({'SMTP_RELAY_CA_FILE': '/etc/dlux/smtp-relay-ca.pem'},
             "checked against the system CAs and <code dir='ltr'>/etc/dlux/smtp-relay-ca.pem</code>"),
            ({'SMTP_RELAY_TLS_VERIFY': 'False'}, 'off: any certificate is accepted'),
        )
        for env, expected in cases:
            with patch.dict('os.environ', {**base, **env}, clear=False):
                effective = effective_email_settings(RELAY_ENV_ROUTE)
            html = build_email_effective_panel(effective, strings, panel='relay')
            self.assertIn('Certificate check', html)
            self.assertIn(expected, html)
        direct = build_email_effective_panel(
            effective_email_settings({'transport': 'direct', 'secret_storage': 'env'}), strings, panel='direct',
        )
        self.assertNotIn('Certificate check', direct)


class RelayGreetingTests(_IsolatedSettingsTestCase):
    """The relay's greeting says it checks certificates; an older relay's does not."""

    OLD_GREETING = 'dlux smtp relay ready'

    @staticmethod
    def _greeting_server(greeting):
        import socket
        import threading

        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)

        def serve():
            try:
                conn, _addr = listener.accept()
                with conn:
                    conn.sendall(f'220 {greeting}\r\n'.encode())
                    while True:
                        line = conn.recv(1024)
                        if not line or line.upper().startswith(b'QUIT'):
                            conn.sendall(b'221 Bye\r\n')
                            return
                        conn.sendall(b'250 OK\r\n')
            except OSError:
                pass

        threading.Thread(target=serve, daemon=True).start()
        return listener, listener.getsockname()[1]

    def test_only_the_current_greeting_names_the_check(self):
        self.assertTrue(smtp_session.relay_checks_certificates(smtp_session.RELAY_GREETING))
        self.assertFalse(smtp_session.relay_checks_certificates(self.OLD_GREETING))
        self.assertFalse(smtp_session.relay_checks_certificates(None))

    def test_the_probe_reads_the_greeting(self):
        from dlux.utils import internal_smtp_relay_available, internal_smtp_relay_greeting

        for greeting in (smtp_session.RELAY_GREETING, self.OLD_GREETING):
            listener, port = self._greeting_server(greeting)
            try:
                self.assertEqual(internal_smtp_relay_greeting(host='127.0.0.1', port=port), greeting)
            finally:
                listener.close()
        # A port nothing listens on. Closing a listener another thread is still
        # accepting on does not stop it accepting on Linux, so none is started.
        import socket

        unused = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        unused.bind(('127.0.0.1', 0))
        port = unused.getsockname()[1]
        unused.close()
        self.assertIsNone(internal_smtp_relay_greeting(host='127.0.0.1', port=port))
        self.assertFalse(internal_smtp_relay_available(host='127.0.0.1', port=port))

    def test_a_refusing_server_is_no_relay(self):
        from dlux.utils import internal_smtp_relay_greeting

        listener, port = self._greeting_server('busy')
        try:
            with patch('smtplib.SMTP.connect', return_value=(421, b'busy')):
                self.assertIsNone(internal_smtp_relay_greeting(host='127.0.0.1', port=port))
        finally:
            listener.close()

    def _email_step(self, greeting, **config):
        with patch('dlux.utils.internal_smtp_relay_greeting', return_value=greeting):
            form = SystemSettingsForm(
                instance=SystemSettings(is_configured=False, email_config=normalize_email_config(config)),
                mode='setup',
            )
        html = Template('{% load crispy_forms_tags %}{% crispy form %}').render(Context({'form': form}))
        start = html.index('data-email-config-section')
        return html[start:html.index('data-email-send-test-result', start)]

    def test_an_older_relay_is_flagged_on_both_routes(self):
        env = {'SMTP_RELAY_HOST': 'smtp.provider.example', 'SMTP_RELAY_TLS_VERIFY': 'True'}
        with patch.dict('os.environ', env, clear=False):
            step = self._email_step(self.OLD_GREETING, transport='relay', secret_storage='env')
        self.assertEqual(step.count('data-email-relay-outdated'), 2)
        self.assertIn('smtp-relay runs a DjangoLux older than 1.16.2', step)
        self.assertNotIn('checked against the system CAs</dd>', step)

    def test_a_current_or_missing_relay_is_not_flagged(self):
        for greeting in (smtp_session.RELAY_GREETING, None):
            step = self._email_step(greeting, transport='relay', secret_storage='encrypted_db',
                                    host='smtp.provider.example')
            self.assertNotIn('data-email-relay-outdated', step, greeting)

    def test_the_panel_flags_an_older_relay_whatever_the_settings_say(self):
        strings = get_strings('ar')
        with patch.dict('os.environ', {'SMTP_RELAY_HOST': 'h', 'SMTP_RELAY_TLS_VERIFY': 'False'}, clear=False):
            effective = effective_email_settings(RELAY_ENV_ROUTE)
        html = build_email_effective_panel(effective, strings, panel='relay', relay_checks_certificates=False)
        self.assertIn(strings['email_relay_skips_certificate_check'], html)
        self.assertNotIn(strings['email_effective_tls_verify_off'], html)


class ScaffoldCertificateTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from dlux.cli import main

        cls._tmp = tempfile.TemporaryDirectory()
        target = Path(cls._tmp.name) / 'tls_demo'
        main(['startproject', 'tls_demo', str(target)])
        cls.compose = (target / 'compose.yml').read_text(encoding='utf-8')
        cls.env = (target / '.secrets' / '.env').read_text(encoding='utf-8')
        cls.readme = (target / 'README.md').read_text(encoding='utf-8')

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()
        super().tearDownClass()

    def test_the_shared_environment_carries_both_settings(self):
        shared = self.compose[self.compose.index('x-environment:'):self.compose.index('\nservices:')]
        self.assertIn('SMTP_RELAY_TLS_VERIFY: "${SMTP_RELAY_TLS_VERIFY:-True}"', shared)
        self.assertIn('SMTP_RELAY_CA_FILE: "${SMTP_RELAY_CA_FILE:-}"', shared)

    def test_the_relay_offers_a_commented_ca_mount(self):
        relay = self.compose[self.compose.index('  smtp-relay:'):]
        relay = relay[:relay.index('    healthcheck:')]
        self.assertIn('#   - ./.secrets/smtp-relay-ca.pem:/etc/dlux/smtp-relay-ca.pem:ro', relay)
        self.assertNotIn('\n    volumes:', relay)

    def test_env_and_readme_name_the_settings(self):
        self.assertIn('\nSMTP_RELAY_TLS_VERIFY=True\n', self.env)
        self.assertTrue(self.env.rstrip('\n').endswith('SMTP_RELAY_CA_FILE='))
        self.assertIn('SMTP_RELAY_CA_FILE=/etc/dlux/smtp-relay-ca.pem', self.readme)
