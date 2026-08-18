"""Email setup step: verification lifecycle and the lock it puts on mail-dependent settings."""

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from dlux.forms import EMAIL_DEPENDENT_SETTING_FIELDS, SystemSettingsForm
from dlux.models import SystemSettings
from dlux.system.constants import (
    SETUP_STEP_COUNT,
    SETUP_STEP_EMAIL,
    SETUP_STEP_HOMEPAGE,
    SETUP_STEP_LANGUAGES,
    SETUP_STEP_SECURITY,
)
from dlux.system.normalizers import email_config_fingerprint, normalize_email_config
from dlux.utils import email_features_unlocked
from dlux.middleware import _thread_locals
from dlux.utils.import_export import apply_system_settings_import

User = get_user_model()

WORKING_SMTP = {
    'host': 'smtp.example.com',
    'port': 587,
    'use_tls': True,
    'default_from_email': 'noreply@example.com',
    'enabled': True,
}


class _IsolatedSettingsTestCase(TestCase):
    """Drops the thread-local actor left behind by any earlier client login.

    SystemSettings.save() stamps audit rows with get_current_user(); a stale user
    from a previous test's transaction leaves an unresolvable FK at teardown.
    """

    def setUp(self):
        super().setUp()
        for attr in ('user', 'request'):
            if hasattr(_thread_locals, attr):
                delattr(_thread_locals, attr)
        self.addCleanup(lambda: [
            delattr(_thread_locals, a) for a in ('user', 'request') if hasattr(_thread_locals, a)
        ])


def _store_email_config(**overrides):
    instance = SystemSettings.load()
    config = normalize_email_config({**WORKING_SMTP, **overrides})
    instance.email_config = config
    instance.save(update_fields=['email_config'])
    return config


def _mark_verified():
    """Persist a verified email config the way a passed test send does."""
    instance = SystemSettings.load()
    config = normalize_email_config(getattr(instance, 'email_config', {}) or {})
    config['verified'] = True
    config['verified_at'] = '2026-08-05T10:00:00+00:00'
    config['verified_fingerprint'] = email_config_fingerprint(config)
    instance.email_config = config
    instance.save(update_fields=['email_config'])
    return config


class EmailStepPlacementTests(TestCase):
    def test_email_step_precedes_access_and_security(self):
        """Security options depend on mail, so mail is configured first."""
        self.assertLess(SETUP_STEP_EMAIL, SETUP_STEP_SECURITY)
        self.assertEqual(SETUP_STEP_EMAIL, SETUP_STEP_HOMEPAGE + 1)
        self.assertEqual(SETUP_STEP_COUNT, 17)

    def test_options_panel_exposes_one_tile_per_wizard_step(self):
        import re
        from pathlib import Path

        template = (
            Path(__file__).resolve().parents[1]
            / 'templates' / 'dlux' / 'system' / 'options.html'
        ).read_text(encoding='utf-8')
        steps = [int(value) for value in re.findall(r"SystemSettings' 1 %\}\?step=(\d+)", template)]

        self.assertEqual(steps, list(range(SETUP_STEP_COUNT)))
        self.assertIn('DLUX_STRINGS.system_settings_email', template)


class EmailVerificationLifecycleTests(_IsolatedSettingsTestCase):
    def test_verification_survives_a_reload_but_not_a_connection_edit(self):
        _store_email_config()
        self.assertFalse(SystemSettings.load().email_config.get('verified'))

        _mark_verified()
        self.assertTrue(SystemSettings.load().email_config.get('verified'))

        # Any connection change re-arms verification on every write path.
        _store_email_config(host='smtp.elsewhere.com', verified=True,
                            verified_fingerprint=SystemSettings.load().email_config['verified_fingerprint'])
        self.assertFalse(SystemSettings.load().email_config.get('verified'))

    def test_verification_cannot_be_forged_through_import(self):
        instance = SystemSettings.load()
        apply_system_settings_import(instance, {
            'email_config': {**WORKING_SMTP, 'verified': True, 'verified_fingerprint': 'not-a-real-digest'},
        })

        self.assertFalse(SystemSettings.load().email_config.get('verified'))

    def test_export_never_carries_this_hosts_verification(self):
        _store_email_config()
        verified = _mark_verified()
        self.assertTrue(verified['verified'])

        redacted = normalize_email_config(verified, redact_secret=True)
        self.assertFalse(redacted['verified'])
        self.assertEqual(redacted['verified_at'], '')
        self.assertNotIn('encrypted_password', redacted)


class EmailTestSendGuardTests(TestCase):
    def setUp(self):
        settings_obj = SystemSettings.load()
        settings_obj.is_configured = True
        settings_obj.save(update_fields=['is_configured'])
        self.user = User.objects.create_superuser(
            username='mail-admin', email='mail-admin@example.com', password='adminpass123',
        )
        self.client = Client()
        self.client.login(username='mail-admin', password='adminpass123')
        _store_email_config()

    def _send_test(self):
        return self.client.post(reverse('email_send_test'),
                                {'recipient': 'someone@example.com'})

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
        EMAIL_HOST='smtp.example.com',
        EMAIL_PORT=587,
        DEFAULT_FROM_EMAIL='noreply@example.com',
    )
    def test_successful_test_send_verifies_the_configuration(self):
        with patch('dlux.views.options.send_dlux_mail', return_value=True):
            response = self._send_test()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        self.assertTrue(SystemSettings.load().email_config.get('verified'))
        self.assertTrue(SystemSettings.load().email_config.get('verified_at'))

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
        EMAIL_HOST='smtp.example.com',
        EMAIL_PORT=587,
        DEFAULT_FROM_EMAIL='noreply@example.com',
    )
    def test_failed_test_send_revokes_verification(self):
        _mark_verified()
        self.assertTrue(SystemSettings.load().email_config.get('verified'))

        with patch('dlux.views.options.send_dlux_mail', side_effect=OSError('connection refused')):
            response = self._send_test()

        self.assertEqual(response.status_code, 502)
        self.assertFalse(SystemSettings.load().email_config.get('verified'))

    def test_test_send_requires_superuser(self):
        staff = User.objects.create_user(username='plain', password='plainpass123', is_staff=True)
        client = Client()
        client.login(username='plain', password='plainpass123')

        self.assertEqual(
            client.post(reverse('email_send_test'), {'recipient': 'a@b.com'}).status_code, 403,
        )


class EmailDependentLockTests(_IsolatedSettingsTestCase):
    def test_dependent_toggles_lock_until_email_is_enabled_and_verified(self):
        _store_email_config(enabled=False)
        form = SystemSettingsForm(instance=SystemSettings.load())
        for name in EMAIL_DEPENDENT_SETTING_FIELDS:
            with self.subTest(field=name, state='disabled email'):
                self.assertTrue(form.fields[name].disabled)

        _store_email_config(enabled=True)
        form = SystemSettingsForm(instance=SystemSettings.load())
        for name in EMAIL_DEPENDENT_SETTING_FIELDS:
            with self.subTest(field=name, state='enabled but unverified'):
                self.assertTrue(form.fields[name].disabled)

        _mark_verified()
        form = SystemSettingsForm(instance=SystemSettings.load())
        for name in EMAIL_DEPENDENT_SETTING_FIELDS:
            with self.subTest(field=name, state='verified'):
                self.assertFalse(form.fields[name].disabled)

    def test_locked_toggles_explain_themselves_on_hover(self):
        from django.template import Context, Template

        _store_email_config(enabled=False)
        form = SystemSettingsForm(instance=SystemSettings(is_configured=False), mode='setup')
        html = Template('{% load crispy_forms_tags %}{% crispy form %}').render(Context({'form': form}))

        self.assertIn('dlux-settings-toggle-field--locked dlux-dependent-settings is-disabled', html)
        self.assertIn("aria-disabled='true'", html)
        self.assertIn('data-dlux-tooltip=', html)
        self.assertIn('Email must be enabled and verified', html)

    def test_locking_preserves_a_stored_value_instead_of_clearing_it(self):
        """A locked toggle must never silently turn off live 2FA or password recovery."""
        instance = SystemSettings.load()
        apply_system_settings_import(instance, {'email_2fa': True, 'forgot_password_enabled': True})
        _store_email_config(enabled=False)
        self.assertTrue(SystemSettings.load().email_2fa)

        form = SystemSettingsForm(
            data={'email_2fa': '', 'forgot_password_enabled': ''},
            instance=SystemSettings.load(),
        )
        form.is_valid()

        self.assertTrue(form.cleaned_data['email_2fa'])
        self.assertTrue(form.cleaned_data['forgot_password_enabled'])

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', DEBUG=True)
    def test_local_debug_backend_unlocks_without_a_test_send(self):
        self.assertTrue(email_features_unlocked())


class EncryptedSecretVisibilityTests(_IsolatedSettingsTestCase):
    """A secret stored under a different SECRET_KEY must be reported, not silently blank."""

    def test_secret_state_distinguishes_absent_from_undecryptable(self):
        from django.test import override_settings

        from dlux.utils import (
            EMAIL_SECRET_ABSENT,
            EMAIL_SECRET_OK,
            EMAIL_SECRET_UNDECRYPTABLE,
            email_secret_state,
            encrypt_email_secret,
        )

        self.assertEqual(email_secret_state(''), EMAIL_SECRET_ABSENT)

        with override_settings(SECRET_KEY='key-that-encrypted-it'):
            token = encrypt_email_secret('hunter2')
            self.assertEqual(email_secret_state(token), EMAIL_SECRET_OK)

        # Same ciphertext, different deployment key — the old code returned '' here,
        # which read identically to "no password configured".
        with override_settings(SECRET_KEY='a-completely-different-key'):
            self.assertEqual(email_secret_state(token), EMAIL_SECRET_UNDECRYPTABLE)

    def test_lenient_decrypt_still_degrades_for_the_send_path(self):
        from django.test import override_settings

        from dlux.utils import decrypt_email_secret, encrypt_email_secret

        with override_settings(SECRET_KEY='original'):
            token = encrypt_email_secret('hunter2')
        with override_settings(SECRET_KEY='rotated'):
            self.assertEqual(decrypt_email_secret(token), '')
            with self.assertRaises(Exception):
                decrypt_email_secret(token, strict=True)

    def test_test_send_names_an_undecryptable_secret_instead_of_failing_in_smtp(self):
        from django.contrib.auth import get_user_model
        from django.test import Client, override_settings
        from django.urls import reverse

        from dlux.utils import encrypt_email_secret

        settings_obj = SystemSettings.load()
        settings_obj.is_configured = True
        settings_obj.save(update_fields=['is_configured'])
        User = get_user_model()
        User.objects.create_superuser(username='sec-admin', email='s@e.com', password='adminpass123')

        with override_settings(SECRET_KEY='key-that-encrypted-it'):
            token = encrypt_email_secret('hunter2')
        _store_email_config(
            secret_storage='encrypted_db',
            username='mailer@example.com',
            encrypted_password=token,
        )

        with override_settings(
            SECRET_KEY='a-completely-different-key',
            EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
            EMAIL_HOST='smtp.example.com',
            EMAIL_PORT=587,
            DEFAULT_FROM_EMAIL='noreply@example.com',
        ):
            # Session cookies are signed with SECRET_KEY, so authenticate under the
            # rotated key — exactly the state a real deployment is in after rotation.
            client = Client()
            client.login(username='sec-admin', password='adminpass123')
            response = client.post(reverse('email_send_test'), {'recipient': 'a@b.com'})

        self.assertEqual(response.status_code, 409)
        self.assertIn('cannot be decrypted', response.json()['message'])
        self.assertFalse(SystemSettings.load().email_config.get('verified'))


class VerificationSurvivesSaveTests(_IsolatedSettingsTestCase):
    """Saving the Email step must not revoke a verification it did not change."""

    def _save_email_step(self, **overrides):
        from dlux.forms import SystemSettingsForm

        data = {
            'email_config_transport': 'relay',
            'email_config_secret_storage': 'encrypted_db',
            'email_config_provider_preset': 'custom',
            'email_config_host': 'mail.example.com',
            'email_config_port': '465',
            'email_config_use_ssl': 'on',
            'email_config_username': 'sender@example.com',
            'email_config_default_from_email': 'sender@example.com',
            'email_config_enabled': 'on',
            'email_config_password': '',
            **overrides,
        }
        form = SystemSettingsForm(data=data, instance=SystemSettings.load())
        form.is_valid()
        return form.cleaned_data.get('email_config')

    def test_saving_without_retyping_the_password_keeps_verification(self):
        """Regression: the fingerprint was computed before the secret was attached.

        The stored fingerprint covered an empty password while the persisted config
        held the real ciphertext, so verification was revoked on the very next read
        and every mail-dependent toggle silently re-locked after a save.
        """
        from dlux.utils import encrypt_email_secret

        instance = SystemSettings.load()
        instance.email_config = normalize_email_config({
            'transport': 'relay',
            'secret_storage': 'encrypted_db',
            'host': 'mail.example.com',
            'port': 465,
            'use_ssl': True,
            'username': 'sender@example.com',
            'default_from_email': 'sender@example.com',
            'enabled': True,
            'encrypted_password': encrypt_email_secret('hunter2'),
        })
        instance.save(update_fields=['email_config'])
        verified = _mark_verified()
        self.assertTrue(verified['verified'])

        saved = self._save_email_step()

        self.assertTrue(saved['encrypted_password'], 'password must be preserved')
        self.assertTrue(saved['verified'], 'an unchanged connection must stay verified')
        # And it must survive the round trip through the DB, not just this dict.
        instance.email_config = saved
        instance.save(update_fields=['email_config'])
        self.assertTrue(SystemSettings.load().email_config['verified'])

    def test_changing_a_connection_field_still_revokes_verification(self):
        """The ordering fix must not blunt the re-arming guarantee."""
        from dlux.utils import encrypt_email_secret

        instance = SystemSettings.load()
        instance.email_config = normalize_email_config({
            'transport': 'relay',
            'secret_storage': 'encrypted_db',
            'host': 'mail.example.com',
            'port': 465,
            'use_ssl': True,
            'username': 'sender@example.com',
            'default_from_email': 'sender@example.com',
            'enabled': True,
            'encrypted_password': encrypt_email_secret('hunter2'),
        })
        instance.save(update_fields=['email_config'])
        _mark_verified()

        saved = self._save_email_step(email_config_host='mail.elsewhere.com')

        self.assertFalse(saved['verified'])

    def test_retyping_the_password_revokes_verification(self):
        from dlux.utils import encrypt_email_secret

        instance = SystemSettings.load()
        instance.email_config = normalize_email_config({
            'transport': 'relay',
            'secret_storage': 'encrypted_db',
            'host': 'mail.example.com',
            'port': 465,
            'use_ssl': True,
            'username': 'sender@example.com',
            'default_from_email': 'sender@example.com',
            'enabled': True,
            'encrypted_password': encrypt_email_secret('hunter2'),
        })
        instance.save(update_fields=['email_config'])
        _mark_verified()

        saved = self._save_email_step(email_config_password='a-new-secret')

        self.assertFalse(saved['verified'], 'a new secret is an untested connection')


class EmailApplyEndpointTests(_IsolatedSettingsTestCase):
    """In-form Apply writes only email_config so a test send can follow immediately."""

    def setUp(self):
        super().setUp()
        from django.contrib.auth import get_user_model

        instance = SystemSettings.load()
        instance.is_configured = True
        instance.save(update_fields=['is_configured'])
        User = get_user_model()
        User.objects.create_superuser(username='apply-admin', email='a@e.com', password='adminpass123')
        self.client = Client()
        self.client.login(username='apply-admin', password='adminpass123')

    def _post(self, **overrides):
        from django.urls import reverse

        data = {
            'email_config_transport': 'relay',
            'email_config_secret_storage': 'encrypted_db',
            'email_config_provider_preset': 'custom',
            'email_config_host': 'mail.example.com',
            'email_config_port': '465',
            'email_config_use_ssl': 'on',
            'email_config_username': 'sender@example.com',
            'email_config_default_from_email': 'sender@example.com',
            'email_config_enabled': 'on',
            'email_config_password': 'hunter2',
            **overrides,
        }
        return self.client.post(f"{reverse('email_config_apply')}?step={SETUP_STEP_EMAIL}", data)

    def test_apply_persists_the_email_group_without_a_full_save(self):
        response = self._post()

        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()['ok'])
        stored = SystemSettings.load().email_config
        self.assertEqual(stored['host'], 'mail.example.com')
        self.assertEqual(stored['port'], 465)
        self.assertTrue(stored['enabled'])
        self.assertTrue(stored['encrypted_password'])

    def test_apply_leaves_other_settings_groups_untouched(self):
        """Only email_config is written; every other step keeps its stored value."""
        instance = SystemSettings.load()
        instance.layout_config = {**(instance.layout_config or {}), 'show_audit_fields': True}
        instance.home_url = '/somewhere/custom/'
        instance.save(update_fields=['layout_config', 'home_url'])

        self._post()

        refreshed = SystemSettings.load()
        self.assertTrue(refreshed.layout_config.get('show_audit_fields'))
        self.assertEqual(refreshed.home_url, '/somewhere/custom/')

    def test_apply_requires_superuser(self):
        from django.contrib.auth import get_user_model
        from django.urls import reverse

        User = get_user_model()
        User.objects.create_user(username='plain-apply', password='plainpass123', is_staff=True)
        client = Client()
        client.login(username='plain-apply', password='plainpass123')

        self.assertEqual(client.post(reverse('email_config_apply'), {}).status_code, 403)

    def test_apply_is_post_only(self):
        from django.urls import reverse

        self.assertEqual(self.client.get(reverse('email_config_apply')).status_code, 405)

    def test_applied_config_is_immediately_testable(self):
        """The whole point: apply then test, without leaving the step."""
        from unittest.mock import patch
        from django.test import override_settings
        from django.urls import reverse

        self._post()
        with override_settings(
            EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
            EMAIL_HOST='smtp.example.com',
            EMAIL_PORT=587,
            DEFAULT_FROM_EMAIL='sender@example.com',
        ), patch('dlux.views.options.send_dlux_mail', return_value=True):
            response = self.client.post(reverse('email_send_test'), {'recipient': 'someone@example.com'})

        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(SystemSettings.load().email_config['verified'])


class TimeoutSettingPersistenceTests(_IsolatedSettingsTestCase):
    """The UI timeout must behave like any other first-class setting."""

    def _stored(self, **overrides):
        instance = SystemSettings.load()
        instance.email_config = normalize_email_config({
            'transport': 'relay', 'secret_storage': 'encrypted_db',
            'host': 'mail.example.com', 'port': 465, 'use_ssl': True,
            'default_from_email': 'a@b.com', 'enabled': True, 'timeout': 120,
            **overrides,
        })
        instance.save(update_fields=['email_config'])
        return instance

    def test_it_survives_saving_a_different_settings_step(self):
        """Trap 2: an absent field on another step's save must not reset it."""
        from django.contrib.auth import get_user_model
        from django.test import RequestFactory

        from dlux.forms import SystemSettingsForm
        from dlux.system.constants import SETUP_STEP_LAYOUT

        self._stored()
        admin = get_user_model().objects.create_superuser(
            username='t-admin', email='t@e.com', password='adminpass123',
        )
        req = RequestFactory().post(f'/?step={SETUP_STEP_LAYOUT}', {'zebra_striping': 'on'})
        req.user = admin
        form = SystemSettingsForm(
            data={'zebra_striping': 'on'}, instance=SystemSettings.load(),
            request=req, mode='modal',
        )
        form.is_valid()

        # Drive the real save path — asserting on the cleaner in isolation proves
        # nothing, since form construction has already run a full_clean.
        self.assertEqual(form.cleaned_data['email_config']['timeout'], 120)
        self.assertTrue(form.cleaned_data['email_config']['enabled'])

    def test_it_survives_import_and_reaches_runtime_config(self):
        from dlux.utils.import_export import apply_system_settings_import
        from dlux.utils.mail import get_dlux_email_config, resolve_smtp_timeouts

        apply_system_settings_import(SystemSettings.load(), {'email_config': {
            'transport': 'relay', 'secret_storage': 'encrypted_db',
            'host': 'mail.example.com', 'port': 465, 'use_ssl': True,
            'default_from_email': 'a@b.com', 'enabled': True, 'timeout': 120,
        }})

        self.assertEqual(SystemSettings.load().email_config['timeout'], 120)
        self.assertEqual(get_dlux_email_config().get('timeout'), 120)
        self.assertEqual(resolve_smtp_timeouts(get_dlux_email_config()), (120, 135))

    def test_changing_only_the_timeout_does_not_revoke_verification(self):
        """It is an operational knob, not part of the connection the test proved."""
        self._stored()
        verified = _mark_verified()
        self.assertTrue(verified['verified'])

        instance = SystemSettings.load()
        config = dict(instance.email_config, timeout=200)
        instance.email_config = normalize_email_config(config)
        instance.save(update_fields=['email_config'])

        self.assertTrue(SystemSettings.load().email_config['verified'])
        self.assertEqual(SystemSettings.load().email_config['timeout'], 200)
