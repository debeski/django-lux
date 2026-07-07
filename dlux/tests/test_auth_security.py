from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings

from dlux.system.normalizers import normalize_auth_config


def _fresh_config_state():
    from dlux.models import SystemSettings

    SystemSettings.objects.all().delete()
    cache.clear()


class AuthConfigNormalizerTests(TestCase):
    def test_defaults_include_lockout_and_min_length_knobs(self):
        cfg = normalize_auth_config({})
        self.assertEqual(cfg['login_lockout_threshold'], 5)
        self.assertEqual(cfg['login_lockout_window_minutes'], 15)
        self.assertEqual(cfg['login_lockout_duration_minutes'], 15)
        self.assertEqual(cfg['strong_password_min_length'], 12)

    def test_out_of_range_values_are_clamped(self):
        cfg = normalize_auth_config({
            'login_lockout_threshold': 999,
            'login_lockout_window_minutes': 0,
            'login_lockout_duration_minutes': 99999,
            'strong_password_min_length': 3,
        })
        self.assertEqual(cfg['login_lockout_threshold'], 50)
        self.assertEqual(cfg['login_lockout_window_minutes'], 1)
        self.assertEqual(cfg['login_lockout_duration_minutes'], 1440)
        self.assertEqual(cfg['strong_password_min_length'], 8)

    def test_garbage_values_fall_back_to_defaults(self):
        cfg = normalize_auth_config({
            'login_lockout_threshold': 'lots',
            'strong_password_min_length': None,
        })
        self.assertEqual(cfg['login_lockout_threshold'], 5)
        self.assertEqual(cfg['strong_password_min_length'], 12)

    def test_utils_copy_delegates_to_system_normalizer(self):
        from dlux.utils.config import normalize_auth_config as utils_normalize
        self.assertEqual(utils_normalize({}), normalize_auth_config({}))


class AuthConfigFlatExposureTests(TestCase):
    def test_new_keys_flatten_into_system_config(self):
        from dlux.utils import get_system_config

        _fresh_config_state()
        with override_settings(DLUX_CONFIG={
            'auth_config': {
                'login_lockout_threshold': 3,
                'login_lockout_window_minutes': 5,
                'login_lockout_duration_minutes': 30,
                'enforce_strong_passwords': True,
                'strong_password_min_length': 16,
            },
        }):
            config = get_system_config()
            self.assertEqual(config['login_lockout_threshold'], 3)
            self.assertEqual(config['login_lockout_window_minutes'], 5)
            self.assertEqual(config['login_lockout_duration_minutes'], 30)
            self.assertEqual(config['strong_password_min_length'], 16)
            self.assertTrue(config['enforce_strong_passwords'])


class LoginLockoutConfigTests(TestCase):
    def setUp(self):
        _fresh_config_state()
        self.factory = RequestFactory()

    def _request(self):
        return self.factory.post('/accounts/login/', REMOTE_ADDR='10.9.8.7')

    def test_threshold_and_duration_come_from_config(self):
        from dlux import login_throttle

        with override_settings(DLUX_CONFIG={
            'auth_config': {
                'login_lockout_enabled': True,
                'login_lockout_threshold': 2,
                'login_lockout_window_minutes': 1,
                'login_lockout_duration_minutes': 30,
            },
        }):
            request = self._request()
            self.assertEqual(login_throttle.login_lockout_remaining(request, 'alice'), 0)
            login_throttle.register_failed_login(request, 'alice')
            self.assertEqual(login_throttle.login_lockout_remaining(request, 'alice'), 0)
            login_throttle.register_failed_login(request, 'alice')
            remaining = login_throttle.login_lockout_remaining(request, 'alice')
            # Locked after the 2nd failure, for ~30 minutes (duration, not window).
            self.assertGreater(remaining, 25 * 60)
            self.assertLessEqual(remaining, 30 * 60)

    def test_successful_login_clears_counters(self):
        from dlux import login_throttle

        with override_settings(DLUX_CONFIG={
            'auth_config': {
                'login_lockout_enabled': True,
                'login_lockout_threshold': 2,
                'login_lockout_window_minutes': 1,
                'login_lockout_duration_minutes': 30,
            },
        }):
            request = self._request()
            login_throttle.register_failed_login(request, 'bob')
            login_throttle.register_failed_login(request, 'bob')
            self.assertGreater(login_throttle.login_lockout_remaining(request, 'bob'), 0)
            login_throttle.clear_failed_logins(request, 'bob')
            self.assertEqual(login_throttle.login_lockout_remaining(request, 'bob'), 0)


class StrongPasswordMinLengthTests(TestCase):
    def setUp(self):
        _fresh_config_state()

    def test_configured_min_length_drives_failures(self):
        from dlux.password_validation import strong_password_failures, strong_password_min_length

        with override_settings(DLUX_CONFIG={
            'auth_config': {
                'enforce_strong_passwords': True,
                'strong_password_min_length': 16,
            },
        }):
            self.assertEqual(strong_password_min_length(), 16)
            # 12 chars, every character class satisfied — fails only on length.
            failures = strong_password_failures('Abcdef1!Abcd')
            self.assertEqual(len(failures), 1)
            self.assertIn('16', failures[0])
            self.assertEqual(strong_password_failures('Abcdef1!Abcdefgh'), [])

    def test_default_min_length_is_twelve(self):
        from dlux.password_validation import strong_password_min_length
        self.assertEqual(strong_password_min_length(), 12)


class AuthConfigPersistenceTests(TestCase):
    def test_load_seeds_flat_int_knobs_into_auth_config(self):
        from dlux.models import SystemSettings

        _fresh_config_state()
        with override_settings(DLUX_CONFIG={
            'login_lockout_threshold': 7,
            'login_lockout_window_minutes': 10,
            'login_lockout_duration_minutes': 45,
            'strong_password_min_length': 20,
        }):
            stored = normalize_auth_config(SystemSettings.load().auth_config)
        self.assertEqual(stored['login_lockout_threshold'], 7)
        self.assertEqual(stored['login_lockout_window_minutes'], 10)
        self.assertEqual(stored['login_lockout_duration_minutes'], 45)
        self.assertEqual(stored['strong_password_min_length'], 20)

    def test_export_import_roundtrip_preserves_flat_auth_knobs(self):
        from dlux.models import SystemSettings
        from dlux.utils.import_export import (
            apply_system_settings_import,
            export_system_settings_payload,
        )

        _fresh_config_state()
        instance = SystemSettings.load()
        instance.auth_config = {
            'login_lockout_enabled': True,
            'login_lockout_threshold': 9,
            'login_lockout_window_minutes': 20,
            'login_lockout_duration_minutes': 60,
            'enforce_strong_passwords': True,
            'strong_password_min_length': 14,
        }
        instance.save()

        payload = export_system_settings_payload(instance)
        exported = payload.get('settings', payload)
        self.assertEqual(exported['login_lockout_threshold'], 9)
        self.assertEqual(exported['strong_password_min_length'], 14)

        _fresh_config_state()
        target = SystemSettings.load()
        apply_system_settings_import(target, payload)
        stored = normalize_auth_config(SystemSettings.load().auth_config)
        self.assertEqual(stored['login_lockout_threshold'], 9)
        self.assertEqual(stored['login_lockout_window_minutes'], 20)
        self.assertEqual(stored['login_lockout_duration_minutes'], 60)
        self.assertEqual(stored['strong_password_min_length'], 14)
