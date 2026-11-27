"""Break-it round 2 sign-in and user-management findings (R2-007 … R2-101).

Each test names the finding it guards. They fail on the code the findings were
written against and pass with the fixes.
"""
import json
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from dlux.models import Scope, SystemSettings

User = get_user_model()

LOCKOUT_CONFIG = {
    'auth_config': {
        'login_lockout_enabled': True,
        'login_lockout_threshold': 5,
        'login_lockout_window_minutes': 15,
        'login_lockout_duration_minutes': 15,
    },
}


def _activity_log():
    from django.apps import apps
    return apps.get_model('dlux', 'ActivityLog')


def _grant(user, *tokens):
    for token in tokens:
        app_label, codename = token.split('.', 1)
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label=app_label, codename=codename)
        )


def _fresh():
    cache.clear()
    settings_row = SystemSettings.load()
    settings_row.is_configured = True
    settings_row.save()
    cache.clear()


class TwoFactorFailureTests(TestCase):
    """R2-007 / R2-033: a wrong code is counted, audited, and never a 500."""

    def setUp(self):
        _fresh()
        self.user = User.objects.create_user('totpuser', 'totp@example.com', 'totppass12345')
        self.client = Client(raise_request_exception=True)

    def _prime(self, client=None):
        client = client or self.client
        session = client.session
        session['pre_2fa_user_id'] = self.user.pk
        session['pre_2fa_method'] = 'totp'
        session['pre_2fa_started_at'] = time.time()
        session.save()

    def _enable_totp(self):
        import pyotp
        from dlux.utils import set_profile_totp_state
        secret = pyotp.random_base32()
        set_profile_totp_state(self.user.profile, raw_secret=secret, enabled=True)
        self.user.profile.refresh_from_db()
        return pyotp.TOTP(secret)

    def test_wrong_code_is_counted_and_audited_for_an_anonymous_challenge(self):
        self._enable_totp()
        self._prime()
        response = self.client.post(
            reverse('verify_otp_login'), {'otp_code': '000000', 'method': 'totp'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)['status'], 'error')
        self.assertEqual(cache.get('dlux:2fa:verify:ip:127.0.0.1:login'), 1)
        self.assertEqual(cache.get(f'dlux:2fa:verify:user:{self.user.pk}'), 1)
        row = _activity_log().objects.get(action='2FA_FAILED')
        self.assertIsNone(row.created_by)
        self.assertEqual(row.details.get('user_id'), self.user.pk)

    def test_challenge_ends_after_five_wrong_codes(self):
        totp = self._enable_totp()
        self._prime()
        for _ in range(4):
            response = self.client.post(reverse('verify_otp_login'), {'otp_code': '000000', 'method': 'totp'})
            self.assertEqual(response.status_code, 200)
        response = self.client.post(reverse('verify_otp_login'), {'otp_code': '000000', 'method': 'totp'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('login'))
        # The challenge is gone: even the right code no longer signs in.
        response = self.client.post(reverse('verify_otp_login'), {'otp_code': totp.now(), 'method': 'totp'})
        self.assertEqual(response.url, reverse('login'))
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_account_cap_holds_across_fresh_challenges(self):
        totp = self._enable_totp()
        for _ in range(3):
            client = Client()
            self._prime(client)
            for _ in range(4):
                client.post(reverse('verify_otp_login'), {'otp_code': '000000', 'method': 'totp'})
        client = Client()
        self._prime(client)
        response = client.post(
            reverse('verify_otp_login'), {'otp_code': totp.now(), 'method': 'totp'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 429)
        self.assertNotIn('_auth_user_id', client.session)

    def test_posted_intent_cannot_open_a_fresh_ip_counter(self):
        self._enable_totp()
        self._prime()
        cache.set('dlux:2fa:verify:ip:127.0.0.1:login', 20, timeout=600)
        response = self.client.post(
            reverse('verify_otp_login'),
            {'otp_code': '000000', 'method': 'totp', 'intent': 'login-rotated-1'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 429)

    def test_wrong_email_code_is_counted(self):
        self.user.profile.is_email_2fa_enabled = True
        self.user.profile.save(update_fields=['is_email_2fa_enabled'])
        self._prime()
        session = self.client.session
        session['pre_2fa_method'] = 'email'
        session.save()
        from django.contrib.auth.hashers import make_password
        cache.set(f'otp_{self.user.pk}_login', {'code_hash': make_password('123456'), 'attempts': 0}, timeout=300)
        response = self.client.post(reverse('verify_otp_login'), {'otp_code': '000000', 'method': 'email'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(cache.get('dlux:2fa:verify:ip:127.0.0.1:login'), 1)
        self.assertTrue(_activity_log().objects.filter(action='2FA_FAILED').exists())

    def test_email_code_attempts_are_reserved_before_comparing(self):
        from django.contrib.auth.hashers import make_password
        from dlux.views.twofa import verify_otp_logic
        cache.set(f'otp_{self.user.pk}_login', {'code_hash': make_password('123456'), 'attempts': 0}, timeout=300)
        # Three attempts already reserved by parallel requests: the code is spent.
        cache.set(f'otp_attempts_{self.user.pk}_login', 3, timeout=300)
        self.assertEqual(verify_otp_logic(self.user, '123456', 'login'), (False, '2fa_invalid_code'))


class TotpSeedAndReplayTests(TestCase):
    """R2-035: the live seed is not handed out again and a code works once."""

    def setUp(self):
        _fresh()
        import pyotp
        from dlux.utils import set_profile_totp_state
        self.user = User.objects.create_user('seeduser', 'seed@example.com', 'seedpass12345')
        self.secret = pyotp.random_base32()
        set_profile_totp_state(self.user.profile, raw_secret=self.secret, enabled=True)
        self.totp = pyotp.TOTP(self.secret)

    def test_setup_refuses_when_totp_is_enabled(self):
        client = Client()
        client.force_login(self.user)
        response = client.post(reverse('setup_totp'), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 409)
        self.assertNotIn(self.secret, response.content.decode())

    def test_a_code_signs_in_only_once(self):
        code = self.totp.now()
        results = []
        for _ in range(2):
            client = Client()
            session = client.session
            session['pre_2fa_user_id'] = self.user.pk
            session['pre_2fa_method'] = 'totp'
            session['pre_2fa_started_at'] = time.time()
            session.save()
            client.post(reverse('verify_otp_login'), {'otp_code': code, 'method': 'totp'})
            results.append('_auth_user_id' in client.session)
        self.assertEqual(results, [True, False])


@override_settings(DLUX_CONFIG=LOCKOUT_CONFIG)
class LoginLockoutTests(TestCase):
    """R2-008 / R2-088 / R2-033."""

    def setUp(self):
        _fresh()
        self.user = User.objects.create_user('u_noperm', 'noperm@example.com', 'rightpass12345')

    def _post(self, username, password, ip='10.0.0.1'):
        return Client().post(reverse('login'), {'username': username, 'password': password}, REMOTE_ADDR=ip)

    def _lock(self):
        for n in range(5):
            # A new address each time, so only the username counter can lock.
            self._post('u_noperm', 'wrong', ip=f'10.1.0.{n + 1}')

    def test_nfkc_spellings_share_the_lock(self):
        self._lock()
        for spelling in ('u_noperm', 'ｕ_noperm', 'ｕ＿ｎｏｐｅｒｍ', 'U_NOPERM'):
            with self.subTest(spelling=spelling):
                response = self._post(spelling, 'rightpass12345', ip='10.2.0.1')
                self.assertEqual(response.status_code, 429)

    def test_email_spelling_shares_the_lock_when_email_sign_in_is_on(self):
        self._lock()
        with patch('dlux.auth.registration.public_registration_config', return_value={'enabled': True}):
            response = self._post('NoPerm@example.com', 'rightpass12345', ip='10.2.0.2')
        self.assertEqual(response.status_code, 429)

    def test_reservations_count_before_the_password_check(self):
        from dlux.auth.login_throttle import reserve_login_attempt
        factory = RequestFactory()
        # Six requests in flight, none finished: the sixth is refused up front.
        results = [reserve_login_attempt(factory.post('/accounts/login/', REMOTE_ADDR=f'10.3.0.{n}'), 'u_noperm')
                   for n in range(6)]
        self.assertEqual(results[:5], [0] * 5)
        self.assertGreater(results[5], 0)

    def test_parallel_burst_gets_at_most_threshold_password_checks(self):
        from dlux.auth import login_throttle
        factory = RequestFactory()
        allowed = []
        barrier = threading.Barrier(20)

        def attempt(n):
            barrier.wait()
            request = factory.post('/accounts/login/', REMOTE_ADDR=f'10.4.0.{n}')
            if login_throttle.reserve_login_attempt(request, 'u_noperm') == 0:
                allowed.append(n)

        threads = [threading.Thread(target=attempt, args=(n,)) for n in range(20)]
        # Threads cannot share the test database; the policy values are fixed here.
        with patch.object(login_throttle, '_enabled', return_value=True), \
             patch.object(login_throttle, '_max_attempts', return_value=5), \
             patch.object(login_throttle, '_window_seconds', return_value=900), \
             patch.object(login_throttle, '_lockout_seconds', return_value=900), \
             patch.object(login_throttle, '_client_ip', side_effect=lambda request: request.META['REMOTE_ADDR']):
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        self.assertEqual(len(allowed), 5)

    def test_failed_sign_in_writes_an_audit_row(self):
        self._post('u_noperm', 'wrong')
        row = _activity_log().objects.get(action='LOGIN_FAILED')
        self.assertIsNone(row.created_by)
        self.assertEqual(row.number, 'u_noperm')

    def test_anonymous_failures_are_not_merged_across_accounts_or_senders(self):
        self._post('u_noperm', 'wrong', ip='10.7.0.1')
        self._post('someone_else', 'wrong', ip='10.7.0.1')
        self._post('u_noperm', 'wrong', ip='10.7.0.2')
        self._post('u_noperm', 'wrong', ip='10.7.0.2')
        self.assertEqual(_activity_log().objects.filter(action='LOGIN_FAILED').count(), 3)

    def test_lockout_writes_an_audit_row(self):
        self._lock()
        self.assertEqual(_activity_log().objects.filter(action='LOCKOUT').count(), 1)

    def test_right_password_after_four_failures_signs_in(self):
        for n in range(4):
            self._post('u_noperm', 'wrong', ip=f'10.5.0.{n}')
        response = self._post('u_noperm', 'rightpass12345', ip='10.5.0.9')
        self.assertEqual(response.status_code, 302)
