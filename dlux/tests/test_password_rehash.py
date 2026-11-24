"""A password check that re-hashes the password must not sign the user out.

Django re-hashes a correct password whose hasher has since raised its work
factor (Django 6.1.3 moved PBKDF2 from 1.2M to 1.5M iterations) and saves it.
The session auth hash changes with it, so the session that confirmed its own
password was signed out on its next request (found upgrading Trademarks to
DjangoLux 1.16.5). Low and high iteration hashers stand in for the two Django
releases, so the re-hash happens here without slow hashing.
"""
from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import PBKDF2PasswordHasher
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from dlux.forms import ResetPasswordForm

PASSWORD = 'Rehash-pw-12345'
OLD_HASHER = 'dlux.tests.test_password_rehash.OldIterationsHasher'
NEW_HASHER = 'dlux.tests.test_password_rehash.NewIterationsHasher'


class OldIterationsHasher(PBKDF2PasswordHasher):
    iterations = 1000


class NewIterationsHasher(PBKDF2PasswordHasher):
    iterations = 2000


@override_settings(PASSWORD_HASHERS=[NEW_HASHER])
class PasswordRehashKeepsSessionTests(TestCase):
    def setUp(self):
        from dlux.models import SystemSettings

        settings_obj = SystemSettings.load()
        settings_obj.is_configured = True
        settings_obj.save()
        cache.clear()
        with self.settings(PASSWORD_HASHERS=[OLD_HASHER]):
            self.user = get_user_model().objects.create_user('rehash', 'rehash@example.com', PASSWORD)
        self.old_hash = self.user.password
        self.assertTrue(self.old_hash.startswith('pbkdf2_sha256$1000$'))
        self.client = Client()
        self.client.force_login(self.user)

    def _stored_hash(self):
        self.user.refresh_from_db()
        return self.user.password

    def _still_signed_in(self):
        response = self.client.get(reverse('user_profile'))
        return response.status_code == 200

    def test_confirming_the_current_password_keeps_the_session(self):
        response = self.client.post(
            reverse('trust_current_device'),
            {'current_password': PASSWORD},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self._stored_hash().startswith('pbkdf2_sha256$2000$'), 'the check re-hashed the password')
        self.assertTrue(self._still_signed_in())

    def test_a_wrong_password_changes_nothing(self):
        response = self.client.post(
            reverse('trust_current_device'),
            {'current_password': 'not-the-password'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._stored_hash(), self.old_hash)
        self.assertTrue(self._still_signed_in())

    def test_a_failed_password_change_keeps_the_session(self):
        response = self.client.post(reverse('user_profile'), {
            'old_password': PASSWORD,
            'new_password1': 'A-new-password-987',
            'new_password2': 'A-different-one-654',
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self._stored_hash().startswith('pbkdf2_sha256$2000$'), 'the old-password check re-hashed it')
        self.assertTrue(self._still_signed_in())

    def test_new_password_equal_to_the_current_one_does_not_rehash(self):
        form = ResetPasswordForm(user=self.user, data={'new_password1': PASSWORD, 'new_password2': PASSWORD})
        self.assertFalse(form.is_valid())
        self.assertIn('new_password2', form.errors)
        self.assertEqual(self._stored_hash(), self.old_hash)
