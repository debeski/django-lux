"""The packaged internal SMTP relay (``python -m dlux.smtp_relay``).

While the relay lived in a scaffold template it could only be asserted on as text;
these exercise the real protocol loop, config resolution and failure reporting.
"""

from dlux.tests.harness import setup_test_environment

setup_test_environment()

import asyncio
from unittest.mock import patch

from django.test import TestCase, override_settings

from dlux import smtp_relay
from dlux.models import SystemSettings
from dlux.system.normalizers import normalize_email_config
from dlux.utils import encrypt_email_secret
from dlux.utils.mail import DLUX_SMTP_RELAY_CLIENT_TIMEOUT


class _FakeWriter:
    def __init__(self):
        self.lines = []
        self.closed = False

    def write(self, payload):
        self.lines.append(payload.decode('utf-8').rstrip('\r\n'))

    async def drain(self):
        return None

    def get_extra_info(self, _name):
        return ('172.19.0.6', 45660)

    def close(self):
        self.closed = True

    async def wait_closed(self):
        return None


class _FakeReader:
    """Feeds a scripted SMTP conversation to the relay's handler."""

    def __init__(self, script):
        self._lines = list(script)

    def at_eof(self):
        return not self._lines

    async def readline(self):
        return self._lines.pop(0) if self._lines else b''


def _converse(script):
    reader, writer = _FakeReader(script), _FakeWriter()
    asyncio.run(smtp_relay.handle_client(reader, writer))
    return writer.lines


SESSION = [
    b'EHLO app\r\n',
    b'MAIL FROM:<sender@example.com>\r\n',
    b'RCPT TO:<someone@example.com>\r\n',
    b'DATA\r\n',
    b'Subject: hi\r\n',
    b'\r\n',
    b'body\r\n',
    b'.\r\n',
    b'QUIT\r\n',
]


class RelayProtocolTests(TestCase):
    def test_a_complete_session_delivers_and_acknowledges(self):
        with patch.object(smtp_relay, 'deliver') as deliver:
            lines = _converse(SESSION)

        self.assertIn('220 dlux smtp relay ready', lines)
        self.assertIn('250 Message accepted', lines)
        self.assertIn('221 Bye', lines)
        mail_from, recipients, payload = deliver.call_args.args
        self.assertEqual(mail_from, 'sender@example.com')
        self.assertEqual(recipients, ['someone@example.com'])
        self.assertIn(b'body', payload)

    def test_upstream_failure_returns_451_naming_the_cause(self):
        """The operator must see the provider's error, not a bare failure."""
        with patch.object(smtp_relay, 'deliver', side_effect=OSError('mailbox unavailable')):
            lines = _converse(SESSION)

        failure = next(line for line in lines if line.startswith('451'))
        self.assertEqual(failure, '451 Relay delivery failed: mailbox unavailable')

    def test_dot_stuffing_is_undone_before_forwarding(self):
        """A body line starting with '.' arrives doubled per RFC 5321."""
        script = SESSION[:4] + [b'..leading dot\r\n', b'.\r\n', b'QUIT\r\n']
        with patch.object(smtp_relay, 'deliver') as deliver:
            _converse(script)

        self.assertEqual(deliver.call_args.args[2], b'.leading dot\r\n')

    def test_oversized_message_is_refused_and_not_delivered(self):
        script = SESSION[:4] + [b'x' * 200 + b'\r\n', b'.\r\n', b'QUIT\r\n']
        with patch.object(smtp_relay, 'max_message_bytes', return_value=50), \
                patch.object(smtp_relay, 'deliver') as deliver:
            lines = _converse(script)

        self.assertTrue(any(line.startswith('552') for line in lines))
        deliver.assert_not_called()

    def test_unknown_verbs_are_rejected_without_dropping_the_session(self):
        lines = _converse([b'WAT\r\n', b'QUIT\r\n'])

        self.assertIn('502 Command not implemented', lines)
        self.assertIn('221 Bye', lines)

    def test_addresses_parse_with_and_without_angle_brackets(self):
        self.assertEqual(smtp_relay.parse_address('MAIL FROM:<a@b.com>'), 'a@b.com')
        self.assertEqual(smtp_relay.parse_address('RCPT TO: c@d.com'), 'c@d.com')
        self.assertEqual(smtp_relay.parse_address('MAIL FROM:<a@b.com> SIZE=42'), 'a@b.com')
        self.assertEqual(smtp_relay.parse_address('MAIL FROM:'), '')


class RelayConfigResolutionTests(TestCase):
    def test_ui_config_wins_when_relay_transport_uses_an_encrypted_secret(self):
        instance = SystemSettings.load()
        instance.email_config = normalize_email_config({
            'transport': 'relay',
            'secret_storage': 'encrypted_db',
            'host': 'mail.example.com',
            'port': 465,
            'use_ssl': True,
            'username': 'sender@example.com',
            'encrypted_password': encrypt_email_secret('hunter2'),
        })
        instance.save(update_fields=['email_config'])

        config = smtp_relay.django_upstream_config()

        self.assertEqual(config['host'], 'mail.example.com')
        self.assertEqual(config['port'], 465)
        self.assertTrue(config['use_ssl'])
        self.assertEqual(config['password'], 'hunter2')

    def test_direct_transport_falls_back_to_the_environment(self):
        instance = SystemSettings.load()
        instance.email_config = normalize_email_config({
            'transport': 'direct', 'secret_storage': 'encrypted_db', 'host': 'ignored.example.com',
        })
        instance.save(update_fields=['email_config'])

        self.assertIsNone(smtp_relay.django_upstream_config())

    def test_env_fallback_reads_the_smtp_relay_variables(self):
        env = {
            'SMTP_RELAY_HOST': 'fallback.example.com',
            'SMTP_RELAY_PORT': '2525',
            'SMTP_RELAY_USE_TLS': 'false',
            'SMTP_RELAY_USER': 'u',
            'SMTP_RELAY_PASSWORD': 'p',
        }
        with patch.dict('os.environ', env, clear=False):
            config = smtp_relay.env_upstream_config()

        self.assertEqual(config['host'], 'fallback.example.com')
        self.assertEqual(config['port'], 2525)
        self.assertFalse(config['use_tls'])
        self.assertEqual(config['password'], 'p')


class RelayTimeoutTests(TestCase):
    def test_upstream_timeout_stays_under_the_apps_client_timeout(self):
        """The relay must lose the race so its 451 reason reaches the operator."""
        self.assertLess(smtp_relay.DEFAULT_UPSTREAM_TIMEOUT, DLUX_SMTP_RELAY_CLIENT_TIMEOUT)

    def test_upstream_timeout_is_overridable_without_a_code_change(self):
        with patch.dict('os.environ', {'SMTP_RELAY_UPSTREAM_TIMEOUT': '120'}, clear=False):
            self.assertEqual(smtp_relay.upstream_timeout(), 120)

    def test_a_bad_timeout_value_falls_back_to_the_default(self):
        with patch.dict('os.environ', {'SMTP_RELAY_UPSTREAM_TIMEOUT': 'not-a-number'}, clear=False):
            self.assertEqual(smtp_relay.upstream_timeout(), smtp_relay.DEFAULT_UPSTREAM_TIMEOUT)

    def test_reason_folds_to_one_capped_line(self):
        self.assertEqual(smtp_relay.smtp_reason(OSError('bad\r\nhost\n  down')), 'bad host down')
        self.assertEqual(len(smtp_relay.smtp_reason(OSError('x' * 500))), 180)
        self.assertEqual(smtp_relay.smtp_reason(OSError('')), 'OSError')


class RelayPackagingTests(TestCase):
    def test_scaffold_no_longer_emits_a_project_local_relay(self):
        from pathlib import Path

        from dlux import scaffold

        self.assertNotIn('smtp_relay', str(scaffold.__file__ and ''))
        templates = Path(scaffold.__file__).parent / 'scaffold_templates' / 'project' / 'tools'
        self.assertFalse((templates / 'smtp_relay.py.tmpl').exists())

    def test_generated_compose_runs_the_packaged_relay(self):
        from pathlib import Path

        from dlux import scaffold

        compose = (
            Path(scaffold.__file__).parent
            / 'scaffold_templates' / 'project' / 'compose.yml.tmpl'
        ).read_text(encoding='utf-8')

        self.assertIn('"python", "-m", "dlux.smtp_relay"', compose)
        self.assertNotIn('tools.smtp_relay', compose)

    def test_existing_projects_are_migrated_idempotently(self):
        from dlux.scaffold import _migrate_smtp_relay_compose

        old = '    command: ["python", "-m", "tools.smtp_relay"]\n'
        migrated = _migrate_smtp_relay_compose(old)

        self.assertIn('"python", "-m", "dlux.smtp_relay"', migrated)
        self.assertNotIn('tools.smtp_relay', migrated)
        self.assertEqual(_migrate_smtp_relay_compose(migrated), migrated)


class StackContractCommandTests(TestCase):
    """Composer owns the Compose file, so the retired entrypoint must be in the contract."""

    def test_contract_names_the_packaged_relay_entrypoint(self):
        from dlux.stack_contract import load_contract

        contract = load_contract()
        self.assertEqual(
            contract['services']['smtp-relay']['command_module'], 'dlux.smtp_relay',
        )

    def test_retired_modules_map_old_paths_to_current_ones(self):
        from dlux.stack_contract import load_contract, retired_command_modules

        retired = retired_command_modules(load_contract())
        self.assertEqual(retired['tools.smtp_relay'], 'dlux.smtp_relay')
        self.assertEqual(retired['tools.dlux_runtime_supervisor'], 'dlux.updater.supervisor')

    def test_drift_is_reported_per_service(self):
        from dlux.stack_contract import diff_command_modules, load_contract

        drift = diff_command_modules(load_contract(), {
            'smtp-relay': 'python -m tools.smtp_relay',
            'web': 'python -m dlux.updater.supervisor -- gunicorn',
        })

        self.assertEqual(drift, [('smtp-relay', 'tools.smtp_relay', 'dlux.smtp_relay')])

    def test_fix_rewrites_the_command_idempotently(self):
        from dlux.stack_contract import fix_command_modules, load_contract

        contract = load_contract()
        fixed = fix_command_modules(contract, 'command: ["python", "-m", "tools.smtp_relay"]')

        self.assertIn('dlux.smtp_relay', fixed)
        self.assertNotIn('tools.smtp_relay', fixed)
        self.assertEqual(fix_command_modules(contract, fixed), fixed)

    def test_a_compliant_stack_reports_no_drift(self):
        from dlux.stack_contract import diff_command_modules, load_contract

        self.assertEqual(diff_command_modules(load_contract(), {
            'smtp-relay': 'python -m dlux.smtp_relay',
            'dlux-updater': 'python -m dlux.updater.supervisor --no-watch',
        }), [])
