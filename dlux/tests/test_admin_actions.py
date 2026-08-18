"""Direct tests for the destructive superuser-only actions.

`force_password_change_for_all_non_superusers` had none before 1.8.0: it was a
private helper inside `views/options.py`, so the only way to exercise it was an
HTTP POST through the view that called it. `data_reset` was always importable
and is covered separately in `test_data_reset.py`.
"""
from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.apps import apps
from django.contrib.auth import get_user_model
from django.test import TestCase

from dlux.admin_actions.force_password_change import (
    force_password_change_for_all_non_superusers,
)


class ForcePasswordChangeTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.Profile = apps.get_model('dlux', 'Profile')

    def _user(self, username, *, superuser=False, **prefs):
        user = self.User.objects.create_user(
            username=username, password='x', is_superuser=superuser)
        if prefs:
            profile, _ = self.Profile.all_objects.get_or_create(user=user)
            profile.preferences = dict(prefs)
            profile.save(update_fields=['preferences'])
        return user

    def _flag(self, user):
        return (self.Profile.all_objects.get(user=user).preferences or {}).get(
            'force_password_change')

    def test_every_non_superuser_is_marked(self):
        a, b = self._user('a'), self._user('b')

        updated, total = force_password_change_for_all_non_superusers()

        self.assertTrue(self._flag(a))
        self.assertTrue(self._flag(b))
        self.assertEqual((updated, total), (2, 2))

    def test_superusers_are_skipped(self):
        """The operator running this must not lock themselves out."""
        root = self._user('root', superuser=True)
        member = self._user('member')

        _updated, total = force_password_change_for_all_non_superusers()

        self.assertIsNone(self._flag(root))
        self.assertTrue(self._flag(member))
        self.assertEqual(total, 1)

    def test_an_already_marked_user_is_not_counted_again(self):
        """Re-running must be idempotent — the count reports newly marked only."""
        self._user('stale', force_password_change=True)
        self._user('fresh')

        updated, total = force_password_change_for_all_non_superusers()

        self.assertEqual(updated, 1)
        self.assertEqual(total, 2)

    def test_unrelated_preferences_survive(self):
        """It writes one key; a user's theme and layout must not be wiped."""
        user = self._user('themed', theme='dark', sidebar_collapsed=True)

        force_password_change_for_all_non_superusers()

        prefs = self.Profile.all_objects.get(user=user).preferences
        self.assertEqual(prefs['theme'], 'dark')
        self.assertTrue(prefs['sidebar_collapsed'])
        self.assertTrue(prefs['force_password_change'])

    def test_a_user_without_a_profile_gets_one(self):
        user = self._user('profileless')
        self.Profile.all_objects.filter(user=user).delete()

        force_password_change_for_all_non_superusers()

        self.assertTrue(self._flag(user))

    def test_no_users_is_a_no_op(self):
        self.User.objects.all().delete()
        self.assertEqual(force_password_change_for_all_non_superusers(), (0, 0))
