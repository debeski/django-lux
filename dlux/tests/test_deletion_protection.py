"""History-preserving deletion: soft bulk delete on ScopedModel querysets, and
users that history points at being soft-deleted instead of erased."""
from dlux.tests.harness import setup_test_environment

setup_test_environment()

from unittest import mock

from django.apps import apps
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, modify_settings

from dlux.admin_actions import data_reset as dr
from dlux.middleware import _thread_locals
from dlux.utils import delete_user_preserving_history, is_soft_deleted_user, user_has_history

User = get_user_model()


def _act_as(test, user):
    _thread_locals.user = user
    test.addCleanup(_thread_locals.__dict__.pop, 'user', None)


class ScopedQuerySetTests(TestCase):
    def setUp(self):
        self.su = User.objects.create_superuser('root', 'r@x.com', 'pw')
        _act_as(self, self.su)
        self.AL = apps.get_model('dlux.ActivityLog')
        self.AL.all_objects.all().hard_delete()
        self.rows = [self.AL.all_objects.create(action='T', model_name='x', category='user')
                     for _ in range(3)]

    def test_bulk_delete_is_soft_and_records_who(self):
        count, per_model = self.AL.objects.filter(action='T').delete()
        self.assertEqual(count, 3)
        self.assertEqual(per_model, {'dlux.ActivityLog': 3})
        self.assertEqual(self.AL.objects.count(), 0)
        self.assertEqual(self.AL.all_objects.count(), 3)
        for row in self.AL.all_objects.all():
            self.assertIsNotNone(row.deleted_at)
            self.assertEqual(row.deleted_by_id, self.su.pk)

    def test_bulk_delete_leaves_already_deleted_rows_alone(self):
        self.AL.all_objects.filter(pk=self.rows[0].pk).delete()
        first = self.AL.all_objects.get(pk=self.rows[0].pk).deleted_at
        count, _ = self.AL.all_objects.all().delete()
        self.assertEqual(count, 2)
        self.assertEqual(self.AL.all_objects.get(pk=self.rows[0].pk).deleted_at, first)

    def test_bulk_delete_without_a_user_leaves_deleted_by_empty(self):
        _thread_locals.__dict__.pop('user', None)
        self.AL.all_objects.all().delete()
        self.assertFalse(self.AL.all_objects.filter(deleted_by__isnull=False).exists())
        self.assertEqual(self.AL.all_objects.filter(deleted_at__isnull=False).count(), 3)

    def test_hard_delete_erases_rows(self):
        self.AL.all_objects.filter(pk=self.rows[0].pk).delete()
        self.AL.all_objects.all().hard_delete()
        self.assertEqual(self.AL.all_objects.count(), 0)

    def test_restore_brings_rows_back(self):
        self.AL.objects.all().delete()
        restored = self.AL.all_objects.all().restore()
        self.assertEqual(restored, 3)
        self.assertEqual(self.AL.objects.count(), 3)
        self.assertFalse(self.AL.all_objects.filter(deleted_by__isnull=False).exists())


class _HistoryHelpers:
    def setUp(self):
        self.AL = apps.get_model('dlux.ActivityLog')

    def _user_without_history(self, name):
        user = User.objects.create_user(name, f'{name}@x.com', 'pw')
        # Account-owned rows (profile, signal logs about the account) are not
        # what this test is about; clear any log row that names the user.
        self.AL.all_objects.filter(created_by=user).hard_delete()
        self.AL.all_objects.filter(updated_by=user).hard_delete()
        return user

    def _give_history(self, user):
        _thread_locals.user = user
        try:
            self.AL.all_objects.create(action='T', model_name='x', category='user')
        finally:
            _thread_locals.__dict__.pop('user', None)


class UserHistoryTests(_HistoryHelpers, TestCase):
    def test_history_detection(self):
        joe = self._user_without_history('joe')
        self.assertFalse(user_has_history(joe))
        self._give_history(joe)
        self.assertTrue(user_has_history(joe))

    def test_soft_deleted_history_still_counts(self):
        joe = self._user_without_history('joe')
        self._give_history(joe)
        self.AL.all_objects.filter(created_by=joe).delete()
        self.assertTrue(user_has_history(joe))

    def test_unsaved_user_has_no_history(self):
        self.assertFalse(user_has_history(User(username='ghost')))
        self.assertFalse(user_has_history(None))

    def test_user_with_history_is_soft_deleted_once(self):
        joe = self._user_without_history('joe')
        self._give_history(joe)
        self.assertEqual(delete_user_preserving_history(joe), 'soft')
        joe.refresh_from_db()
        self.assertFalse(joe.is_active)
        self.assertEqual(joe.username, 'joe_del')
        self.assertTrue(is_soft_deleted_user(joe))
        self.assertTrue(self.AL.all_objects.filter(created_by=joe).exists())
        self.assertEqual(delete_user_preserving_history(joe), 'kept')
        joe.refresh_from_db()
        self.assertEqual(joe.username, 'joe_del')

    def test_user_without_history_is_hard_deleted(self):
        joe = self._user_without_history('joe')
        pk = joe.pk
        self.assertEqual(delete_user_preserving_history(joe), 'hard')
        self.assertFalse(User.objects.filter(pk=pk).exists())


@modify_settings(INSTALLED_APPS={'append': 'django.contrib.admin'})
class AdminUserDeleteTests(_HistoryHelpers, TestCase):
    def setUp(self):
        super().setUp()
        from dlux.admin import CustomUserAdmin  # needs django.contrib.admin installed
        self.admin = CustomUserAdmin(User, AdminSite())
        self.request = RequestFactory().post('/')
        self.request.user = User.objects.create_superuser('root', 'r@x.com', 'pw')

    def test_single_delete_keeps_a_user_with_history(self):
        joe = self._user_without_history('joe')
        self._give_history(joe)
        self.admin.delete_model(self.request, joe)
        self.assertTrue(User.objects.filter(pk=joe.pk, is_active=False).exists())

    def test_admin_log_entries_count_as_history(self):
        from dlux.utils.users import _user_history_relations
        User._meta._expire_cache()     # pick up admin's reverse relation
        self.addCleanup(User._meta._expire_cache)
        found = {(rel.related_model._meta.label_lower, rel.field.name)
                 for rel in _user_history_relations(User)}
        self.assertIn(('admin.logentry', 'user'), found)
        self.assertNotIn(('dlux.profile', 'user'), found)   # CASCADE: part of the account

    def test_bulk_delete_routes_every_user_through_the_same_rule(self):
        # The test settings run without django.contrib.admin's tables, so a real
        # hard delete here would trip over django_admin_log; the rule itself is
        # covered in UserHistoryTests.
        joe = self._user_without_history('joe')
        ann = self._user_without_history('ann')
        with mock.patch('dlux.utils.delete_user_preserving_history') as rule:
            self.admin.delete_queryset(self.request, User.objects.filter(pk__in=[joe.pk, ann.pk]))
        self.assertEqual({call.args[0].pk for call in rule.call_args_list}, {joe.pk, ann.pk})


class ResetUsersTests(_HistoryHelpers, TestCase):
    def setUp(self):
        super().setUp()
        self.su = User.objects.create_superuser('root', 'r@x.com', 'pw')

    def _check_both_modes(self, mode):
        joe = self._user_without_history('joe')
        ann = self._user_without_history('ann')
        self._give_history(joe)
        entry = dr.execute_reset(self.su, ['auth.user'], mode=mode)[0]
        self.assertEqual(entry['status'], 'deleted')
        self.assertEqual((entry['deleted'], entry['soft_count'], entry['kept']), (2, 1, 0))
        self.assertTrue(User.objects.filter(pk=joe.pk, is_active=False).exists())
        self.assertFalse(User.objects.filter(pk=ann.pk).exists())
        self.assertTrue(self.AL.all_objects.filter(created_by=joe).exists())

        again = dr.execute_reset(self.su, ['auth.user'], mode=mode)[0]
        self.assertEqual((again['status'], again['deleted'], again['kept']), ('empty', 0, 1))

    def test_soft_mode(self):
        self._check_both_modes(dr.RESET_MODE_SOFT)

    def test_permanent_mode(self):
        self._check_both_modes(dr.RESET_MODE_PERMANENT)


class ResetOptOutTests(TestCase):
    def test_dlux_reset_false_hides_a_model(self):
        AL = apps.get_model('dlux.ActivityLog')
        self.assertTrue(dr.is_reset_eligible(AL))
        with mock.patch.object(AL, 'dlux_reset', False, create=True):
            self.assertFalse(dr.is_reset_eligible(AL))
            su = User.objects.create_superuser('root', 'r@x.com', 'pw')
            self.assertNotIn('dlux.activitylog', [m['key'] for m in dr.build_reset_catalog(su)])
