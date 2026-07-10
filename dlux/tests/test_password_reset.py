from dlux.tests.harness import setup_test_environment

setup_test_environment()

import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from dlux.models import SystemSettings
from dlux import password_reset as pr
from dlux.system.normalizers import normalize_auth_config

User = get_user_model()


@override_settings(
    DEBUG=True,
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    DEFAULT_FROM_EMAIL='security@example.com',
)
class ForgotPasswordFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        mail.outbox = []
        self.client = Client()
        ss = SystemSettings.load()
        ss.is_configured = True
        ss.save(update_fields=['is_configured'])
        self.user = User.objects.create_user('joe', 'joe@example.com', 'pw12345!')

    def _enable(self, value=True):
        ss = SystemSettings.load()
        auth = dict(ss.auth_config or {})
        auth['forgot_password_enabled'] = value
        ss.auth_config = auth
        ss.save()
        cache.clear()

    # --- gating -----------------------------------------------------------
    def test_disabled_returns_404(self):
        self._enable(False)
        self.assertEqual(self.client.get(reverse('password_reset')).status_code, 404)

    def test_enabled_renders_login_style_form(self):
        self._enable(True)
        r = self.client.get(reverse('password_reset'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'dlux-login--')          # inherits configured login style
        self.assertContains(r, 'name="email"')

    # --- request + delivery ----------------------------------------------
    def test_request_sends_reset_email_via_dlux_mail(self):
        self._enable(True)
        r = self.client.post(reverse('password_reset'), {'email': 'joe@example.com'})
        self.assertRedirects(r, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        self.assertRegex(body, r'/accounts/reset/[^/\s]+/[^/\s]+/')

    def test_full_reset_cycle_changes_password(self):
        self._enable(True)
        self.client.post(reverse('password_reset'), {'email': 'joe@example.com'})
        link = re.search(r'(/accounts/reset/[^/\s]+/[^/\s]+/)', mail.outbox[0].body).group(1)
        # First GET redirects to the set-password URL (token moved into session).
        r1 = self.client.get(link)
        self.assertEqual(r1.status_code, 302)
        r2 = self.client.get(r1.url)
        self.assertEqual(r2.status_code, 200)
        self.assertContains(r2, 'name="new_password1"')
        r3 = self.client.post(r1.url, {'new_password1': 'BrandNew-pass-99', 'new_password2': 'BrandNew-pass-99'})
        self.assertRedirects(r3, reverse('password_reset_complete'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('BrandNew-pass-99'))

    def test_confirm_view_404_when_disabled(self):
        self._enable(False)
        self.assertEqual(
            self.client.get(reverse('password_reset_confirm', kwargs={'uidb64': 'x', 'token': 'y'})).status_code,
            404,
        )

    # --- login-page link --------------------------------------------------
    def test_login_page_shows_forgot_link_only_when_available(self):
        self._enable(False)
        self.assertNotContains(self.client.get(reverse('login')), reverse('password_reset'))
        self._enable(True)
        self.assertContains(self.client.get(reverse('login')), reverse('password_reset'))

    # --- settings pattern -------------------------------------------------
    def test_normalizer_default_off_and_roundtrips(self):
        self.assertFalse(normalize_auth_config({})['forgot_password_enabled'])
        self.assertTrue(normalize_auth_config({'forgot_password_enabled': True})['forgot_password_enabled'])

    def test_availability_requires_email_ready(self):
        from unittest.mock import patch
        self._enable(True)
        self.assertTrue(pr.forgot_password_available())
        # Enabled but mail delivery not ready -> the flow self-gates off.
        with patch.object(pr, 'get_email_service_status', return_value={'available': False}):
            self.assertFalse(pr.forgot_password_available())


@override_settings(DEBUG=True)
class LockoutCountdownTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        ss = SystemSettings.load()
        ss.is_configured = True
        ss.save(update_fields=['is_configured'])
        User.objects.create_user('joe', 'joe@example.com', 'pw12345!')

    def test_lockout_exposes_remaining_seconds_for_countdown(self):
        # Default threshold is 5 failed attempts.
        for _ in range(5):
            self.client.post(reverse('login'), {'username': 'joe', 'password': 'wrong'})
        r = self.client.post(reverse('login'), {'username': 'joe', 'password': 'wrong'})
        self.assertEqual(r.status_code, 429)
        self.assertGreater(r.context['lockout_remaining'], 0)
        self.assertContains(r, 'data-dlux-lockout-remaining', status_code=429)
        # Message is rendered server-side (progressive enhancement) so the
        # notice is never blank even if login.js is cached/stale.
        self.assertContains(r, 'Too many failed attempts', status_code=429)
