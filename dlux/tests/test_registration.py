from dlux.tests.harness import setup_test_environment

setup_test_environment()

import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from dlux.system.constants import REGISTRATION_ACTIVATION_PENDING_APPROVAL
from dlux.models import PublicRegistration, SystemSettings


User = get_user_model()


@override_settings(
    DEBUG=True,
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    DEFAULT_FROM_EMAIL='security@example.com',
)
class PublicRegistrationTests(TestCase):
    def setUp(self):
        cache.clear()
        mail.outbox = []
        self.client = Client()
        settings_obj = SystemSettings.load()
        settings_obj.is_configured = True
        settings_obj.save(update_fields=['is_configured'])

    def _enable_registration(self, activation_mode='auto_login_after_verify'):
        settings_obj = SystemSettings.load()
        settings_obj.is_configured = True
        settings_obj.public_registration_enabled = True
        settings_obj.registration_activation_mode = activation_mode
        settings_obj.registration_throttle_enabled = False
        settings_obj.save()

    def _registration_payload(self, email='newuser@example.com'):
        return {
            'email': email,
            'password1': 'Strong-test-pass-123',
            'password2': 'Strong-test-pass-123',
            'first_name': 'New',
            'last_name': 'User',
            'website': '',
        }

    def _posted_token(self):
        body = mail.outbox[-1].body
        match = re.search(r'/accounts/register/verify/([^/\s]+)/', body)
        self.assertIsNotNone(match, body)
        return match.group(1)

    def test_registration_disabled_returns_404(self):
        response = self.client.get(reverse('register'))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(User.objects.filter(email='newuser@example.com').exists())

    def test_register_page_uses_configured_login_shell(self):
        self._enable_registration()
        settings_obj = SystemSettings.load()
        settings_obj.login_config = {
            'style': 'centered',
            'show_logo': True,
            'logo_treatment': 'halo',
            'logo_treatment_shape': 'soft',
            'banner_color': '',
            'hero_message': {'en': '## Welcome'},
        }
        settings_obj.save()

        response = self.client.get(reverse('register'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'dlux-login--centered')
        self.assertContains(response, 'dlux-public-auth-page--register')
        self.assertContains(response, 'data-login-logo-treatment="halo"')
        self.assertContains(response, 'class="login-input')

    def test_register_page_honours_anonymous_language_switch(self):
        self._enable_registration()

        response = self.client.get(f"{reverse('register')}?lang=ar")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session.get('lang'), 'ar')
        self.assertContains(response, 'إنشاء حساب')

    def test_login_page_marks_public_registration_and_none_logo_treatment(self):
        self._enable_registration()
        settings_obj = SystemSettings.load()
        settings_obj.login_config = {
            'style': 'split',
            'show_logo': True,
            'logo_treatment': 'none',
            'logo_treatment_shape': 'soft',
            'banner_color': '',
            'hero_message': {},
        }
        settings_obj.save()

        response = self.client.get(reverse('login'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'dlux-login--split dlux-login-has-register')
        self.assertContains(response, 'data-login-logo-treatment="none"')
        self.assertContains(response, reverse('register'))

    def test_signup_creates_inactive_user_and_hashed_pending_registration(self):
        self._enable_registration()

        response = self.client.post(reverse('register'), self._registration_payload())

        self.assertRedirects(response, reverse('register_sent'))
        user = User.objects.get(email='newuser@example.com')
        self.assertFalse(user.is_active)
        registration = PublicRegistration.objects.get(user=user)
        self.assertTrue(registration.token_hash)
        self.assertNotIn(registration.token_hash, mail.outbox[0].body)
        self.assertEqual(len(mail.outbox), 1)

    def test_public_signup_source_badge_renders_on_profile(self):
        self._enable_registration()
        self.client.post(reverse('register'), self._registration_payload())
        token = self._posted_token()
        self.client.get(reverse('register_verify', args=[token]))

        response = self.client.get(reverse('user_profile'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Public signup')

    def test_internal_user_profile_does_not_render_public_signup_source(self):
        user = User.objects.create_user('internal', 'internal@example.com', 'internalpass123')
        self.client.force_login(user)

        response = self.client.get(reverse('user_profile'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Public signup')

    def test_verify_valid_token_activates_and_logs_in(self):
        self._enable_registration()
        self.client.post(reverse('register'), self._registration_payload())
        token = self._posted_token()

        response = self.client.get(reverse('register_verify', args=[token]))

        self.assertEqual(response.status_code, 200)
        user = User.objects.get(email='newuser@example.com')
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertEqual(str(self.client.session.get('_auth_user_id')), str(user.pk))
        registration = PublicRegistration.objects.get(user=user)
        self.assertEqual(registration.status, 'activated')
        self.assertFalse(registration.token_hash)

    def test_verified_pending_approval_keeps_user_inactive_until_superuser_post_approval(self):
        self._enable_registration(REGISTRATION_ACTIVATION_PENDING_APPROVAL)
        self.client.post(reverse('register'), self._registration_payload())
        token = self._posted_token()

        response = self.client.get(reverse('register_verify', args=[token]))

        self.assertEqual(response.status_code, 200)
        user = User.objects.get(email='newuser@example.com')
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        registration = PublicRegistration.objects.get(user=user)
        self.assertEqual(registration.status, 'pending_approval')

        admin = User.objects.create_superuser('admin', 'admin@example.com', 'adminpass123')
        self.client.force_login(admin)
        get_response = self.client.get(reverse('approve_registration', args=[registration.pk]))
        self.assertEqual(get_response.status_code, 405)

        post_response = self.client.post(reverse('approve_registration', args=[registration.pk]))
        self.assertRedirects(post_response, reverse('pending_registrations'))
        user.refresh_from_db()
        registration.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertEqual(registration.status, 'activated')

    def test_duplicate_email_gets_generic_success_without_second_user(self):
        self._enable_registration()
        User.objects.create_user('existing', 'newuser@example.com', 'existingpass123')

        response = self.client.post(reverse('register'), self._registration_payload())

        self.assertRedirects(response, reverse('register_sent'))
        self.assertEqual(User.objects.filter(email__iexact='newuser@example.com').count(), 1)
        self.assertEqual(PublicRegistration.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_login_accepts_email_when_registration_enabled(self):
        self._enable_registration()
        User.objects.create_user('emailuser', 'emailuser@example.com', 'emailpass123')

        response = self.client.post(reverse('login'), {
            'username': 'emailuser@example.com',
            'password': 'emailpass123',
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.client.session.get('_auth_user_id'))
