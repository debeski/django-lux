"""register_permission_visibility_filter: hide permissions of a disabled feature, keep the grants."""

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db.models import Q
from django.test import TestCase

from dlux.access import (
    hidden_permission_ids,
    register_permission_visibility_filter,
    unregister_permission_visibility_filter,
)
from dlux.forms import CustomUserPermissionsForm, GroupPresetForm
from dlux.models import SystemSettings

User = get_user_model()


def hide_backup():
    return Q(content_type__app_label='dlux', codename='download_backup')


class PermissionVisibilityTests(TestCase):
    def setUp(self):
        SystemSettings.load()
        self.admin = User.objects.create_superuser('admin', 'admin@example.com', 'pw')
        self.view = Permission.objects.get(content_type__app_label='dlux', codename='view_reports')
        self.backup = Permission.objects.get(content_type__app_label='dlux', codename='download_backup')
        self.addCleanup(unregister_permission_visibility_filter, hide_backup)

    def group_form(self, permissions, instance=None):
        return GroupPresetForm(
            data={'name': 'Cashiers', 'description': '', 'scope': '', 'permissions': [p.pk for p in permissions]},
            instance=instance, user=self.admin,
        )

    def save_group(self, permissions, instance=None):
        form = self.group_form(permissions, instance)
        self.assertTrue(form.is_valid(), form.errors)
        return form.save()

    @staticmethod
    def offered(form):
        field = form.fields['permissions']
        queryset = getattr(field.widget, '_filtered_queryset', field.queryset)
        return set(queryset.values_list('pk', flat=True))

    def test_hidden_permissions_leave_the_group_form(self):
        register_permission_visibility_filter(hide_backup)
        form = GroupPresetForm(user=self.admin)

        self.assertNotIn(self.backup.pk, set(form.fields['permissions'].queryset.values_list('pk', flat=True)))
        self.assertNotIn(self.backup.pk, self.offered(form))
        self.assertIn(self.view.pk, self.offered(form))
        self.assertNotIn('download_backup', form.fields['permissions'].widget.render('permissions', []))

    def test_saving_while_hidden_keeps_the_grant_and_reenabling_restores_it(self):
        group = self.save_group([self.view, self.backup])
        register_permission_visibility_filter(hide_backup)

        self.save_group([self.view], instance=group)
        self.assertEqual(set(group.permissions.all()), {self.view, self.backup})
        self.save_group([], instance=group)
        self.assertEqual(set(group.permissions.all()), {self.backup})

        unregister_permission_visibility_filter(hide_backup)
        form = GroupPresetForm(instance=group, user=self.admin)
        self.assertIn(self.backup.pk, self.offered(form))
        self.assertEqual(set(form.fields['permissions'].initial), {self.backup})

    def test_visible_permissions_can_still_be_removed(self):
        group = self.save_group([self.view, self.backup])

        self.save_group([self.view], instance=group)

        self.assertEqual(set(group.permissions.all()), {self.view})

    def test_user_permission_form_keeps_hidden_grants(self):
        staff = User.objects.create_user('cashier', 'cashier@example.com', 'pw', is_staff=True)
        staff.user_permissions.set([self.view, self.backup])
        register_permission_visibility_filter(hide_backup)

        form = CustomUserPermissionsForm(
            data={'is_staff': 'on', 'permissions': []}, instance=staff, user=self.admin,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        self.assertIn(self.backup, staff.user_permissions.all())
        self.assertNotIn(self.view, staff.user_permissions.all())

    def test_filters_returning_none_or_failing_hide_nothing(self):
        def broken():
            raise RuntimeError('settings unavailable')

        def hide_nothing():
            return None

        register_permission_visibility_filter(hide_nothing)
        register_permission_visibility_filter(broken)
        self.addCleanup(unregister_permission_visibility_filter, hide_nothing)
        self.addCleanup(unregister_permission_visibility_filter, broken)

        with self.assertLogs('dlux', level='ERROR'):
            self.assertEqual(hidden_permission_ids(), set())

    def test_registering_twice_is_a_no_op(self):
        register_permission_visibility_filter(hide_backup)
        register_permission_visibility_filter(hide_backup)
        unregister_permission_visibility_filter(hide_backup)

        self.assertEqual(hidden_permission_ids(), set())

    def test_forms_package_reexports_the_registry(self):
        import dlux.access
        import dlux.forms

        self.assertIs(dlux.forms.register_permission_visibility_filter, dlux.access.register_permission_visibility_filter)
