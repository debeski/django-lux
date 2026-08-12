from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

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


class SessionPolicyConfigTests(TestCase):
    def test_defaults_include_session_lifecycle_knobs(self):
        cfg = normalize_auth_config({})
        self.assertFalse(cfg['purge_session_on_exit'])
        self.assertFalse(cfg['inactivity_timeout_enabled'])
        self.assertEqual(cfg['inactivity_timeout_minutes'], 10)

    def test_purge_on_exit_copy_describes_browser_not_tab_expiry(self):
        from dlux.translations import get_strings

        help_text = get_strings('en')['help_sys_purge_session_on_exit']
        self.assertIn('browser is fully closed', help_text)
        self.assertIn('Closing one tab does not end', help_text)

    def test_inactivity_minutes_clamped(self):
        self.assertEqual(normalize_auth_config({'inactivity_timeout_minutes': 0})['inactivity_timeout_minutes'], 1)
        self.assertEqual(normalize_auth_config({'inactivity_timeout_minutes': 99999})['inactivity_timeout_minutes'], 1440)
        self.assertEqual(normalize_auth_config({'inactivity_timeout_minutes': 'nope'})['inactivity_timeout_minutes'], 10)

    def test_session_keys_flatten_into_system_config(self):
        from dlux.utils import get_system_config

        _fresh_config_state()
        with override_settings(DLUX_CONFIG={
            'auth_config': {
                'purge_session_on_exit': True,
                'inactivity_timeout_enabled': True,
                'inactivity_timeout_minutes': 25,
            },
        }):
            config = get_system_config()
            self.assertTrue(config['purge_session_on_exit'])
            self.assertTrue(config['inactivity_timeout_enabled'])
            self.assertEqual(config['inactivity_timeout_minutes'], 25)

    def test_security_group_exposes_session_knobs(self):
        from dlux.utils.config import build_config_groups

        groups = build_config_groups({
            'inactivity_timeout_enabled': True,
            'inactivity_timeout_minutes': 20,
            'purge_session_on_exit': True,
        })
        self.assertTrue(groups['security']['purge_session_on_exit'])
        self.assertTrue(groups['security']['inactivity_timeout_enabled'])
        self.assertEqual(groups['security']['inactivity_timeout_minutes'], 20)


class SessionTimeoutMiddlewareTests(TestCase):
    def setUp(self):
        _fresh_config_state()
        self.factory = RequestFactory()

    def _authed_request(self):
        from django.contrib.auth import get_user_model
        from importlib import import_module
        from django.conf import settings as dj_settings

        user = get_user_model().objects.create_user(username='idle', password='x')
        request = self.factory.get('/dashboard/')
        engine = import_module(dj_settings.SESSION_ENGINE)
        request.session = engine.SessionStore()
        request.user = user
        return request

    def test_idle_timeout_from_config_signs_out(self):
        import time as _time
        from dlux.middleware import DluxMiddleware

        mw = DluxMiddleware(lambda r: None)
        with override_settings(DLUX_CONFIG={
            'auth_config': {'inactivity_timeout_enabled': True, 'inactivity_timeout_minutes': 1},
        }):
            request = self._authed_request()
            # First authed request anchors the idle clock.
            self.assertIsNone(mw._session_timeout_response(request))
            # Backdate activity beyond the 1-minute window.
            request.session['dlux_last_activity'] = _time.time() - 120
            response = mw._session_timeout_response(request)
            self.assertIsNotNone(response)
            self.assertIn('idle_timeout', response.url)

    def test_purge_on_exit_sets_browser_close_expiry(self):
        from dlux.middleware import DluxMiddleware

        mw = DluxMiddleware(lambda r: None)
        with override_settings(DLUX_CONFIG={
            'auth_config': {'purge_session_on_exit': True},
        }):
            request = self._authed_request()
            mw._apply_session_cookie_policy(request)
            self.assertTrue(request.session.get_expire_at_browser_close())
            self.assertTrue(request.session.get('dlux_expire_on_close'))


class LoginLockoutConfigTests(TestCase):
    def setUp(self):
        _fresh_config_state()
        self.factory = RequestFactory()

    def _request(self):
        return self.factory.post('/accounts/login/', REMOTE_ADDR='10.9.8.7')

    def test_threshold_and_duration_come_from_config(self):
        from dlux.auth import login_throttle

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
        from dlux.auth import login_throttle

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
        from dlux.auth.password_validation import strong_password_failures, strong_password_min_length

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
        from dlux.auth.password_validation import strong_password_min_length
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


class LegacyValidatorPathTests(SimpleTestCase):
    """The validator module moved and the old path was not kept as an alias.

    So a project that hardcoded `dlux.password_validation...` in its own
    AUTH_PASSWORD_VALIDATORS depends entirely on `dlux_settings()` rewriting it.
    Without that rewrite the project fails at startup on an unresolvable
    validator — which is why this is a test and not a comment.
    """

    NEW = "dlux.auth.password_validation.DluxStrongPasswordValidator"
    OLD = "dlux.password_validation.DluxStrongPasswordValidator"

    def _settings(self, validators=None):
        from dlux.utils.settings import dlux_settings

        scope = {"BASE_DIR": "/tmp", "INSTALLED_APPS": [], "MIDDLEWARE": [], "TEMPLATES": []}
        if validators is not None:
            scope["AUTH_PASSWORD_VALIDATORS"] = validators
        return [v["NAME"] for v in dlux_settings(scope)["AUTH_PASSWORD_VALIDATORS"]]

    def test_the_old_module_path_no_longer_exists(self):
        import importlib

        with self.assertRaises(ImportError):
            importlib.import_module("dlux.password_validation")

    def test_a_fresh_project_gets_the_new_path(self):
        self.assertEqual(self._settings(), [self.NEW])

    def test_a_pinned_legacy_path_is_rewritten_not_duplicated(self):
        names = self._settings([{"NAME": self.OLD}])

        self.assertEqual(names, [self.NEW])
        self.assertNotIn(self.OLD, names)

    def test_the_rewrite_preserves_other_validators_and_their_options(self):
        django_validator = "django.contrib.auth.password_validation.MinimumLengthValidator"
        names = self._settings([
            {"NAME": django_validator, "OPTIONS": {"min_length": 12}},
            {"NAME": self.OLD},
        ])

        self.assertEqual(names, [django_validator, self.NEW])

    def test_an_already_current_project_is_untouched(self):
        self.assertEqual(self._settings([{"NAME": self.NEW}]), [self.NEW])
