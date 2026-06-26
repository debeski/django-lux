from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.template import Context, Template
from django.test import TestCase

from dlux.forms import CustomUserCreationForm, CustomUserPermissionsForm
from dlux.models import Profile
from dlux.models import SystemSettings

User = get_user_model()


class PermissionsUiTests(TestCase):
    def setUp(self):
        SystemSettings.load()
        self.user = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='adminpass123',
        )

    def test_permissions_form_excludes_scaffold_infra_db_permissions(self):
        content_type = ContentType.objects.create(app_label='db', model='testmodel')
        permission = Permission.objects.create(
            name='Can view test model',
            codename='view_testmodel',
            content_type=content_type,
        )

        form = CustomUserPermissionsForm(instance=self.user, user=self.user)

        self.assertNotIn(permission.pk, form.fields['permissions'].queryset.values_list('pk', flat=True))

    def test_assignable_permissions_reenable_model_delete_but_keep_sensitive_excluded(self):
        from dlux.forms import get_assignable_permissions_queryset

        content_type = ContentType.objects.create(app_label='inventory', model='widget')
        Permission.objects.create(
            name='Can delete widget',
            codename='delete_widget',
            content_type=content_type,
        )

        assignable = set(
            get_assignable_permissions_queryset().values_list('codename', flat=True)
        )

        # Re-enabled: a business-model delete permission can be granted to users.
        self.assertIn('delete_widget', assignable)
        # Sensitive auth deletes stay excluded.
        self.assertNotIn('delete_user', assignable)
        self.assertNotIn('delete_group', assignable)
        self.assertNotIn('delete_permission', assignable)

    def test_context_menu_delete_requires_delete_permission(self):
        from dlux.utils import filter_context_actions

        staff = User.objects.create_user(
            username='editor', password='editorpass123', is_staff=True,
        )
        content_type = ContentType.objects.create(app_label='inventory', model='widget')
        delete_widget = Permission.objects.create(
            name='Can delete widget',
            codename='delete_widget',
            content_type=content_type,
        )
        actions = [
            {'label': 'view', 'permissions': []},
            {'label': 'delete', 'permissions': ['inventory.delete_widget']},
        ]

        def labels_for(user):
            fresh = User.objects.get(pk=user.pk)  # drop cached permissions
            return {a['label'] for a in filter_context_actions(fresh, actions)}

        # No delete permission → Delete entry is hidden, View remains.
        self.assertEqual(labels_for(staff), {'view'})

        # manage_sections must NOT bypass a generic per-model delete.
        manage_sections = Permission.objects.get(codename='manage_sections')
        staff.user_permissions.add(manage_sections)
        self.assertEqual(labels_for(staff), {'view'})

        # Explicit delete grant reveals the Delete entry.
        staff.user_permissions.add(delete_widget)
        self.assertEqual(labels_for(staff), {'view', 'delete'})

    def test_permissions_widget_skips_orphaned_content_type_permissions(self):
        content_type = ContentType.objects.create(app_label='orphaned_app', model='ghostmodel')
        permission = Permission.objects.create(
            name='Can view ghost model',
            codename='view_ghostmodel',
            content_type=content_type,
        )

        form = CustomUserPermissionsForm(instance=self.user, user=self.user)
        form.fields['permissions'].queryset = Permission.objects.filter(pk=permission.pk)
        form.fields['permissions'].widget._filtered_queryset = form.fields['permissions'].queryset

        html = Template('{% load crispy_forms_tags %}{% crispy form %}').render(Context({'form': form}))

        self.assertNotIn('Ghost Model', html)
        self.assertNotIn('orphaned_app', html)

    def test_manage_scopes_groups_with_staff_access_permissions(self):
        profile_type = ContentType.objects.get_for_model(Profile)
        manage_staff = Permission.objects.get(
            content_type=profile_type,
            codename='manage_staff',
        )
        manage_scopes = Permission.objects.get(
            content_type=profile_type,
            codename='manage_scopes',
        )

        form = CustomUserPermissionsForm(instance=self.user, user=self.user)
        widget = form.fields['permissions'].widget
        context = widget.get_context('permissions', [], {'id': 'id_permissions'})
        dlux_groups = context['widget']['grouped_perms']['dlux']['models']

        self.assertIn('staff_access', dlux_groups)
        profile_codenames = {
            option.get('codename')
            for option in dlux_groups.get('profile', {}).get('permissions', [])
        }
        self.assertNotIn(manage_scopes.codename, profile_codenames)

        staff_access_codenames = {
            option.get('codename')
            for option in dlux_groups['staff_access']['permissions']
        }
        self.assertIn(manage_staff.codename, staff_access_codenames)
        self.assertIn(manage_scopes.codename, staff_access_codenames)

    def test_profile_permissions_use_model_user_group_label(self):
        profile_type = ContentType.objects.get_for_model(Profile)
        permission = Permission.objects.create(
            name='Can view profile',
            codename='view_profile',
            content_type=profile_type,
        )

        form = CustomUserPermissionsForm(instance=self.user, user=self.user)
        form.fields['permissions'].queryset = Permission.objects.filter(pk=permission.pk)
        form.fields['permissions'].widget._filtered_queryset = form.fields['permissions'].queryset

        context = form.fields['permissions'].widget.get_context('permissions', [], {'id': 'id_permissions'})
        dlux_groups = context['widget']['grouped_perms']['dlux']['models']

        self.assertEqual(dlux_groups['profile']['name'], 'Users')

    def test_dlux_owned_permissions_include_descriptions(self):
        form = CustomUserPermissionsForm(instance=self.user, user=self.user)
        context = form.fields['permissions'].widget.get_context('permissions', [], {'id': 'id_permissions'})
        dlux_groups = context['widget']['grouped_perms']['dlux']['models']
        help_by_codename = {
            option['codename']: option.get('help_text')
            for model_group in dlux_groups.values()
            for option in model_group.get('permissions', [])
            if option.get('codename')
        }

        self.assertEqual(
            help_by_codename.get('view_reports'),
            'Allows viewing the reports overview and exporting report summaries.',
        )
        self.assertEqual(
            help_by_codename.get('download_backup'),
            'Allows building and downloading report backup ZIP archives.',
        )
        self.assertEqual(
            help_by_codename.get('view_sections'),
            'Allows opening the Sections screen and viewing the section hierarchy.',
        )
        self.assertEqual(
            help_by_codename.get('manage_sections'),
            'Allows creating, editing, reordering, and deleting sections and subsections.',
        )
        self.assertEqual(
            help_by_codename.get('view_activitylog'),
            'Allows viewing activity-log pages and activity detail modals.',
        )

    def test_creation_form_renders_staff_tier_preview(self):
        form = CustomUserCreationForm(user=self.user)

        html = Template('{% load crispy_forms_tags %}{% crispy form %}').render(Context({'form': form}))

        self.assertIn('dlux-staff-tier-preview', html)
        self.assertIn('Staff Tier Preview', html)
        self.assertIn('data-codename="manage_scopes"', html)
        self.assertIn('data-codename="manage_staff"', html)
        self.assertIn('Staff Tier &amp; Access', html)

    def test_permissions_form_preview_uses_target_tier_state(self):
        profile_type = ContentType.objects.get_for_model(Profile)
        manage_scopes = Permission.objects.get(content_type=profile_type, codename='manage_scopes')
        manage_staff = Permission.objects.get(content_type=profile_type, codename='manage_staff')
        target = User.objects.create_user(
            username='globalstaff',
            email='globalstaff@example.com',
            password='globalstaffpass123',
            is_staff=True,
        )
        target.user_permissions.add(manage_scopes, manage_staff)

        form = CustomUserPermissionsForm(instance=target, user=self.user)
        html = Template('{% load crispy_forms_tags %}{% crispy form %}').render(Context({'form': form}))

        self.assertIn('dlux-staff-tier-preview', html)
        self.assertIn('Global Staff', html)
        self.assertIn('Can Assign Staff Roles', html)
