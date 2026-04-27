from django import forms
from django.apps import apps
from django.conf import settings

if not settings.configured:
    settings.configure(
        SECRET_KEY='microsys-test-key',
        ALLOWED_HOSTS=['testserver', 'localhost'],
        INSTALLED_APPS=[
            'django.contrib.auth',
            'django.contrib.contenttypes',
            'django.contrib.sessions',
            'django.contrib.messages',
            'django.contrib.staticfiles',
            'crispy_forms',
            'crispy_bootstrap5',
            'django_filters',
            'django_tables2',
            'microsys',
        ],
        MIDDLEWARE=[
            'django.contrib.sessions.middleware.SessionMiddleware',
            'django.contrib.auth.middleware.AuthenticationMiddleware',
            'microsys.middleware.ActivityLogMiddleware',
        ],
        ROOT_URLCONF='microsys.urls',
        TEMPLATES=[
            {
                'BACKEND': 'django.template.backends.django.DjangoTemplates',
                'APP_DIRS': True,
                'OPTIONS': {
                    'context_processors': [
                        'django.template.context_processors.request',
                        'django.contrib.auth.context_processors.auth',
                        'django.contrib.messages.context_processors.messages',
                        'microsys.context_processors.microsys_context',
                    ],
                },
            }
        ],
        DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}},
        STATIC_URL='/static/',
        DEFAULT_AUTO_FIELD='django.db.models.BigAutoField',
        USE_TZ=True,
        CRISPY_ALLOWED_TEMPLATE_PACKS='bootstrap5',
        CRISPY_TEMPLATE_PACK='bootstrap5',
    )

    import django
    django.setup()

from django.test import TestCase, Client, RequestFactory
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.core.cache import cache
from django.contrib.auth.hashers import identify_hasher
import json
from unittest.mock import patch

from microsys.models import Scope, Section, SystemSettings

User = get_user_model()


class GeneralViewsTests(TestCase):
    def setUp(self):
        cache.clear()
        from microsys.models import SystemSettings

        self.user = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='adminpass123'
        )
        self.client = Client()
        self.client.login(username='admin', password='adminpass123')
        settings = SystemSettings.load()
        settings.is_configured = True
        settings.save()

    def test_options_view_requires_login(self):
        """Test that options_view requires authentication."""
        self.client.logout()
        response = self.client.get(reverse('options_view'))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_options_view_accessible_to_authenticated_user(self):
        """Test that options_view is accessible to authenticated users."""
        response = self.client.get(reverse('options_view'))
        self.assertEqual(response.status_code, 200)

    def test_options_view_context_data(self):
        """Test that options_view includes required context data."""
        response = self.client.get(reverse('options_view'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('version', response.context)
        self.assertIn('django_version', response.context)
        self.assertIn('python_version', response.context)

    def test_options_view_hides_runtime_diagnostics_for_non_staff_users(self):
        regular_user = User.objects.create_user(
            username='viewer',
            email='viewer@example.com',
            password='viewerpass123'
        )
        self.client.logout()
        self.client.login(username='viewer', password='viewerpass123')

        response = self.client.get(reverse('options_view'))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['show_system_diagnostics'])
        self.assertNotContains(response, 'bi-info-circle')
        self.assertNotContains(response, '?step=0')

    def test_options_view_reads_decrypter_version_from_env(self):
        with patch.dict('os.environ', {'DECRYPTER_VERSION': '2.4.1'}, clear=False):
            response = self.client.get(reverse('options_view'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['decrypter_version'], '2.4.1')

    def test_options_view_exposes_split_system_settings_entrypoints(self):
        response = self.client.get(reverse('options_view'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '?step=0')
        self.assertContains(response, '?step=1')
        self.assertContains(response, '?step=2')
        self.assertContains(response, '?step=3')
        self.assertContains(response, '?step=4')
        self.assertContains(response, reverse('system_settings_export'))

    def test_system_settings_modal_honors_requested_wizard_step(self):
        response = self.client.get(
            reverse('modal_manager', args=['microsys', 'SystemSettings', 1]) + '?step=4',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertIn('data-ms-wizard-initial-step="4"', payload['html'])
        self.assertIn('?step=4', payload['html'])

    def test_system_settings_export_downloads_setup_payload_for_superuser(self):
        settings_obj = SystemSettings.load()
        settings_obj.system_names = {'en': 'Exported System'}
        settings_obj.languages = {'fr': {'name': 'Francais', 'dir': 'ltr', 'flag': 'FR'}}
        settings_obj.default_language = 'fr'
        settings_obj.save()

        response = self.client.get(reverse('system_settings_export'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json; charset=utf-8')
        payload = json.loads(response.content)
        self.assertEqual(payload['format'], 'django-microsys.system-settings')
        self.assertEqual(payload['settings']['system_names']['en'], 'Exported System')
        self.assertIn('fr', payload['settings']['languages'])

    def test_system_settings_modal_uses_setup_form_class_for_live_behavior(self):
        response = self.client.get(
            reverse('modal_manager', args=['microsys', 'SystemSettings', 1]) + '?step=1',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertIn('class="microsys-form ms-system-setup-form"', payload['html'])

    def test_system_setup_view_requires_superuser(self):
        """Test that system_setup_view requires superuser status."""
        regular_user = User.objects.create_user(
            username='user',
            email='user@example.com',
            password='userpass123'
        )
        self.client.logout()
        self.client.login(username='user', password='userpass123')
        response = self.client.get(reverse('system_setup'))
        self.assertEqual(response.status_code, 403)  # Permission denied

    def test_system_setup_view_accessible_to_superuser(self):
        """Test that system_setup_view is accessible to superusers."""
        from microsys.models import SystemSettings
        settings = SystemSettings.load()
        settings.is_configured = False
        settings.save()
        
        response = self.client.get(reverse('system_setup'))
        self.assertEqual(response.status_code, 200)

    def test_system_setup_redirects_if_configured(self):
        """Test that system_setup redirects if system is already configured."""
        from microsys.models import SystemSettings
        settings = SystemSettings.load()
        settings.is_configured = True
        settings.save()
        
        response = self.client.get(reverse('system_setup'))
        self.assertEqual(response.status_code, 302)  # Redirect


class ProfileViewsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            first_name='John',
            last_name='Doe'
        )
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')

    def test_user_profile_requires_login(self):
        """Test that user_profile requires authentication."""
        self.client.logout()
        response = self.client.get(reverse('user_profile'))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_user_profile_accessible_to_authenticated_user(self):
        """Test that user_profile is accessible to authenticated users."""
        response = self.client.get(reverse('user_profile'))
        self.assertEqual(response.status_code, 200)

    def test_user_profile_context_data(self):
        """Test that user_profile includes required context data."""
        response = self.client.get(reverse('user_profile'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('user', response.context)
        self.assertIn('profile', response.context)
        self.assertIn('stats', response.context)
        self.assertIn('password_form', response.context)

    def test_user_profile_password_change(self):
        """Test password change functionality in profile."""
        response = self.client.post(reverse('user_profile'), {
            'old_password': 'testpass123',
            'new_password1': 'newpass123',
            'new_password2': 'newpass123',
        })
        self.assertEqual(response.status_code, 302)  # Redirect on success

    def test_user_profile_stats_calculation(self):
        """Test that profile stats are calculated correctly."""
        from microsys.models import UserActivityLog
        UserActivityLog.objects.create(
            created_by=self.user,
            action='CREATE',
            model_name='TestModel'
        )
        
        response = self.client.get(reverse('user_profile'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['stats']['total_actions'], 1)
        self.assertEqual(response.context['stats']['docs_created'], 1)


class ScopeViewsTests(TestCase):
    def setUp(self):
        cache.clear()
        settings_obj = SystemSettings.load()
        settings_obj.is_configured = True
        settings_obj.save()
        self.user = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='adminpass123'
        )
        self.client = Client()
        self.client.login(username='admin', password='adminpass123')

    def test_manage_scopes_requires_superuser(self):
        """Test that manage_scopes requires superuser status."""
        regular_user = User.objects.create_user(
            username='user',
            email='user@example.com',
            password='userpass123'
        )
        self.client.logout()
        self.client.login(username='user', password='userpass123')
        response = self.client.get(reverse('manage_scopes'))
        self.assertEqual(response.status_code, 403)  # Permission denied

    def test_manage_scopes_accessible_to_superuser(self):
        """Test that manage_scopes is accessible to superusers."""
        response = self.client.get(reverse('manage_scopes'))
        self.assertEqual(response.status_code, 200)

    def test_toggle_scopes_requires_superuser(self):
        """Test that toggle_scopes requires superuser status."""
        regular_user = User.objects.create_user(
            username='user',
            email='user@example.com',
            password='userpass123'
        )
        self.client.logout()
        self.client.login(username='user', password='userpass123')
        response = self.client.post(reverse('toggle_scopes'), json.dumps({}), content_type='application/json')
        self.assertEqual(response.status_code, 403)  # Permission denied

    def test_toggle_scopes_works(self):
        """Test that toggle_scopes toggles the scope system."""
        from microsys.models import ScopeSettings
        response = self.client.post(
            reverse('toggle_scopes'),
            json.dumps({'target_enabled': True}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertTrue(ScopeSettings.load().is_enabled)


class ActivityLogViewsTests(TestCase):
    def setUp(self):
        cache.clear()
        settings_obj = SystemSettings.load()
        settings_obj.is_configured = True
        settings_obj.save()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            is_staff=True
        )
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')
        content_type = ContentType.objects.get_for_model(
            apps.get_model('microsys', 'UserActivityLog'),
            for_concrete_model=False,
        )
        self.view_activitylog_permission = Permission.objects.get(
            codename='view_activitylog',
            content_type=content_type,
        )
        self.user.user_permissions.add(self.view_activitylog_permission)

    def test_activity_log_view_requires_staff(self):
        """Test that activity log view requires explicit permission."""
        regular_user = User.objects.create_user(
            username='user',
            email='user@example.com',
            password='userpass123'
        )
        self.client.logout()
        self.client.login(username='user', password='userpass123')
        response = self.client.get(reverse('user_activity_log'))
        self.assertEqual(response.status_code, 403)

    def test_activity_log_view_allows_non_staff_user_with_explicit_permission(self):
        regular_user = User.objects.create_user(
            username='logviewer',
            email='logviewer@example.com',
            password='viewerpass123',
        )
        regular_user.user_permissions.add(self.view_activitylog_permission)

        self.client.logout()
        self.client.login(username='logviewer', password='viewerpass123')
        response = self.client.get(reverse('user_activity_log'))

        self.assertEqual(response.status_code, 200)

    def test_activity_log_view_accessible_to_staff(self):
        """Test that activity log view is accessible to staff."""
        response = self.client.get(reverse('user_activity_log'))
        self.assertEqual(response.status_code, 200)

    def test_activity_log_view_context_data(self):
        """Test that activity log view includes required context data."""
        from microsys.models import UserActivityLog
        UserActivityLog.objects.create(
            created_by=self.user,
            action='CREATE',
            model_name='TestModel'
        )
        
        response = self.client.get(reverse('user_activity_log'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('filter', response.context)
        self.assertIn('table', response.context)
        self.assertEqual(response.context['filter'].form.fields['keyword'].label, '')

    def test_activity_log_view_keeps_inline_filter_labels_on_bound_get_requests(self):
        from microsys.models import UserActivityLog

        UserActivityLog.objects.create(
            created_by=self.user,
            action='CREATE',
            model_name='Keyword Match',
        )

        response = self.client.get(reverse('user_activity_log'), {'keyword': 'match', 'page': 1})

        self.assertEqual(response.status_code, 200)
        self.assertIn('filter', response.context)
        self.assertEqual(response.context['filter'].form.fields['keyword'].label, '')
        self.assertTrue(response.context['filter'].form.fields['keyword'].widget.attrs.get('placeholder'))

    def test_activity_log_detail_view_renders_structured_changes_and_masks_totp_secret(self):
        from microsys.models import UserActivityLog

        self.user.is_superuser = True
        self.user.save(update_fields=['is_superuser'])

        log = UserActivityLog.objects.create(
            created_by=self.user,
            action='UPDATE',
            model_name='User Profile',
            object_id=self.user.pk,
            details={
                'first_name': {'old': 'Old', 'new': 'New'},
                'totp_secret': {'old': 'RAWOLDSECRET', 'new': 'RAWNEWSECRET'},
            },
        )

        response = self.client.get(reverse('user_activity_log_detail', args=[log.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ms-log-detail-panel')
        self.assertContains(response, 'ms-log-detail-item')
        self.assertContains(response, 'ms-log-detail-status is-changed')
        self.assertContains(response, '********')
        self.assertNotContains(response, 'RAWOLDSECRET')
        self.assertNotContains(response, 'RAWNEWSECRET')

    def test_activity_log_detail_view_hides_superuser_logs_from_non_superuser_staff(self):
        from microsys.models import UserActivityLog

        superuser = User.objects.create_superuser(
            username='rootlog',
            email='rootlog@example.com',
            password='rootlogpass123'
        )
        log = UserActivityLog.objects.create(
            created_by=superuser,
            action='UPDATE',
            model_name='System Settings',
        )

        response = self.client.get(reverse('user_activity_log_detail', args=[log.pk]))

        self.assertEqual(response.status_code, 404)

    def test_activity_log_detail_requires_explicit_permission(self):
        from microsys.models import UserActivityLog

        self.user.user_permissions.remove(self.view_activitylog_permission)
        log = UserActivityLog.objects.create(
            created_by=self.user,
            action='UPDATE',
            model_name='System Settings',
        )

        response = self.client.get(reverse('user_activity_log_detail', args=[log.pk]))

        self.assertEqual(response.status_code, 403)


class SecurityHardeningViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        settings_obj = SystemSettings.load()
        settings_obj.is_configured = True
        settings_obj.save()
        self.superuser = User.objects.create_superuser(
            username='root',
            email='root@example.com',
            password='rootpass123'
        )
        self.regular_user = User.objects.create_user(
            username='regular',
            email='regular@example.com',
            password='regularpass123'
        )
        self.other_user = User.objects.create_user(
            username='other',
            email='other@example.com',
            password='otherpass123'
        )
        self.staff_user = User.objects.create_user(
            username='staffer',
            email='staff@example.com',
            password='staffpass123',
            is_staff=True,
        )
        self.scope_a = Scope.objects.create(name='Scope A')
        self.scope_b = Scope.objects.create(name='Scope B')
        self.staff_user.profile.scope = self.scope_a
        self.staff_user.profile.save(update_fields=['scope'])
        self.other_user.profile.scope = self.scope_b
        self.other_user.profile.save(update_fields=['scope'])

    def _grant_section_permission(self, user, codename):
        content_type = ContentType.objects.get_for_model(Section, for_concrete_model=False)
        permission, _ = Permission.objects.get_or_create(
            codename=codename,
            content_type=content_type,
            defaults={'name': codename.replace('_', ' ').title()},
        )
        user.user_permissions.add(permission)
        return permission

    def _grant_user_permission(self, user, codename):
        content_type = ContentType.objects.get_for_model(User)
        permission = Permission.objects.get(codename=codename, content_type=content_type)
        user.user_permissions.add(permission)
        return permission

    def test_generic_modal_manager_requires_model_permissions(self):
        self.client.login(username='regular', password='regularpass123')

        response = self.client.get(
            reverse('modal_manager', args=['auth', 'User', 'new']),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 403)

    def test_generic_modal_delete_requires_model_permissions(self):
        self.client.login(username='regular', password='regularpass123')

        response = self.client.post(
            reverse('modal_delete', args=['auth', 'User', self.other_user.pk]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 403)

    def test_profile_edit_modal_is_self_only(self):
        self.client.login(username='regular', password='regularpass123')

        forbidden = self.client.get(
            reverse('modal_profile_edit', args=[self.other_user.pk]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        allowed = self.client.get(
            reverse('modal_profile_edit', args=[self.regular_user.pk]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(allowed.status_code, 200)

    def test_user_management_modals_require_staff(self):
        self.client.login(username='regular', password='regularpass123')

        create_response = self.client.get(
            reverse('modal_user'),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        edit_response = self.client.get(
            reverse('modal_user_edit', args=[self.other_user.pk]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(create_response.status_code, 403)
        self.assertEqual(edit_response.status_code, 403)

    def test_manage_users_requires_view_user_permission_for_staff(self):
        self.client.login(username='staffer', password='staffpass123')

        response = self.client.get(reverse('manage_users'))

        self.assertEqual(response.status_code, 403)

    def test_manage_users_allows_staff_with_view_user_permission(self):
        self._grant_user_permission(self.staff_user, 'view_user')
        self.client.login(username='staffer', password='staffpass123')

        response = self.client.get(reverse('manage_users'))

        self.assertEqual(response.status_code, 200)

    def test_user_management_modal_enforces_scope_rules(self):
        self.client.login(username='staffer', password='staffpass123')

        response = self.client.get(
            reverse('modal_user_edit', args=[self.other_user.pk]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 403)

    def test_user_detail_modal_enforces_scope_rules(self):
        self._grant_user_permission(self.staff_user, 'view_user')
        self.client.login(username='staffer', password='staffpass123')

        response = self.client.get(reverse('user_detail_modal', args=[self.other_user.pk]))

        self.assertEqual(response.status_code, 403)

    def test_user_detail_modal_blocks_superuser_targets_for_non_superuser_staff(self):
        self._grant_user_permission(self.staff_user, 'view_user')
        self.client.login(username='staffer', password='staffpass123')

        response = self.client.get(reverse('user_detail_modal', args=[self.superuser.pk]))

        self.assertEqual(response.status_code, 403)

    def test_user_detail_modal_requires_view_user_permission(self):
        self.client.login(username='staffer', password='staffpass123')

        response = self.client.get(reverse('user_detail_modal', args=[self.staff_user.pk]))

        self.assertEqual(response.status_code, 403)

    def test_user_detail_modal_hides_recent_logs_without_activity_log_permission(self):
        from microsys.models import UserActivityLog

        self._grant_user_permission(self.staff_user, 'view_user')
        UserActivityLog.objects.create(
            created_by=self.staff_user,
            action='CREATE',
            model_name='User',
        )
        self.client.login(username='staffer', password='staffpass123')

        response = self.client.get(reverse('user_detail_modal', args=[self.staff_user.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['recent_logs']), [])

    def test_reset_password_requires_change_user_permission(self):
        self.client.login(username='staffer', password='staffpass123')

        response = self.client.post(
            reverse('reset_password', args=[self.regular_user.pk]),
            {
                'reset_password-new_password1': 'ResetPass456!',
                'reset_password-new_password2': 'ResetPass456!',
            },
        )

        self.assertEqual(response.status_code, 403)

    def test_reset_password_enforces_scope_rules_even_with_change_permission(self):
        self._grant_user_permission(self.staff_user, 'change_user')
        self.client.login(username='staffer', password='staffpass123')

        response = self.client.post(
            reverse('reset_password', args=[self.other_user.pk]),
            {
                'reset_password-new_password1': 'ResetPass456!',
                'reset_password-new_password2': 'ResetPass456!',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('manage_users'))
        self.other_user.refresh_from_db()
        self.assertFalse(self.other_user.check_password('ResetPass456!'))

    def test_manage_sections_requires_sections_view_permission(self):
        self.client.login(username='regular', password='regularpass123')

        response = self.client.get(reverse('manage_sections'))

        self.assertEqual(response.status_code, 403)

    def test_manage_sections_allows_view_only_permission_for_get(self):
        self._grant_section_permission(self.regular_user, 'view_sections')
        self.client.login(username='regular', password='regularpass123')

        response = self.client.get(reverse('manage_sections'))

        self.assertEqual(response.status_code, 200)

    def test_manage_sections_post_requires_manage_sections_permission(self):
        self._grant_section_permission(self.regular_user, 'view_sections')
        self.client.login(username='regular', password='regularpass123')

        response = self.client.post(reverse('manage_sections'))

        self.assertEqual(response.status_code, 403)

    def test_add_subsection_requires_manage_sections_permission(self):
        self._grant_section_permission(self.regular_user, 'view_sections')
        self.client.login(username='regular', password='regularpass123')

        response = self.client.post(reverse('add_subsection'))

        self.assertEqual(response.status_code, 403)

    def test_get_section_details_requires_sections_view_permission(self):
        self.client.login(username='regular', password='regularpass123')

        response = self.client.get(reverse('get_section_details'))

        self.assertEqual(response.status_code, 403)

    def test_get_section_details_rejects_non_section_models_even_with_sections_permission(self):
        self._grant_section_permission(self.regular_user, 'view_sections')
        self.client.login(username='regular', password='regularpass123')

        response = self.client.get(
            reverse('get_section_details'),
            {'model': 'user', 'pk': self.other_user.pk},
        )

        self.assertEqual(response.status_code, 404)

    def test_delete_section_rejects_non_section_models_even_with_manage_permission(self):
        self._grant_section_permission(self.regular_user, 'manage_sections')
        self.client.login(username='regular', password='regularpass123')

        response = self.client.post(
            reverse('delete_section'),
            json.dumps({'model': 'user', 'pk': self.other_user.pk}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 404)

    def test_add_subsection_rejects_non_subsection_models_even_with_manage_permission(self):
        self._grant_section_permission(self.regular_user, 'manage_sections')
        self.client.login(username='regular', password='regularpass123')

        response = self.client.post(
            reverse('add_subsection') + '?model=user',
            {'username': 'should-not-work'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 404)
        payload = json.loads(response.content)
        self.assertFalse(payload['success'])

    def test_invalid_subsection_post_does_not_create_record_when_form_fails(self):
        class RejectingScopeForm(forms.ModelForm):
            class Meta:
                model = Scope
                fields = ['name']

            def clean(self):
                cleaned = super().clean()
                raise forms.ValidationError('Blocked by validation')

        self._grant_section_permission(self.superuser, 'manage_sections')
        self.client.login(username='root', password='rootpass123')

        allowed_subsection = {'model': Scope, 'model_name': 'scope'}

        with patch('microsys.views.sections._resolve_allowed_subsection_definition', return_value=allowed_subsection), \
             patch('microsys.views.sections.resolve_form_class_for_model', return_value=RejectingScopeForm), \
             patch('microsys.views.sections._create_minimal_instance_from_post', side_effect=AssertionError('fallback should not run')):
            response = self.client.post(
                reverse('add_subsection') + '?model=scope',
                {'name': 'ShouldNotCreate'},
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertFalse(payload['success'])
        self.assertFalse(Scope.objects.filter(name='ShouldNotCreate').exists())

    def test_get_section_details_returns_sanitized_error_payload(self):
        self._grant_section_permission(self.regular_user, 'view_sections')
        self.client.login(username='regular', password='regularpass123')
        scope = Scope.objects.create(name='Visible Scope')
        allowed_section = {'model': Scope, 'model_name': 'scope'}

        with patch('microsys.views.sections._resolve_allowed_section_definition', return_value=allowed_section), \
             patch('microsys.views.sections.collect_related_objects', side_effect=RuntimeError('sensitive traceback marker')):
            response = self.client.get(reverse('get_section_details'), {'model': 'scope', 'pk': scope.pk})

        self.assertEqual(response.status_code, 500)
        payload = json.loads(response.content)
        self.assertFalse(payload['success'])
        self.assertNotIn('sensitive traceback marker', payload['error'])
        self.assertNotIn('traceback', payload)


class TwoFactorSecurityViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username='twofa',
            email='twofa@example.com',
            password='twofapass123',
        )
        self.user.profile.is_email_2fa_enabled = True
        self.user.profile.save(update_fields=['is_email_2fa_enabled'])
        self.client = Client()
        self.client.login(username='twofa', password='twofapass123')

    def _prime_pre_2fa_session(self):
        session = self.client.session
        session['pre_2fa_user_id'] = self.user.pk
        session.save()

    def test_two_factor_mutation_endpoints_reject_get_requests(self):
        before_secret = self.user.profile.totp_secret
        before_codes = list(self.user.profile.backup_codes or [])

        endpoints = [
            reverse('enable_2fa'),
            reverse('setup_totp'),
            reverse('disable_2fa'),
            reverse('generate_backup_codes'),
            reverse('resend_otp_login'),
        ]

        for url in endpoints:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 405)

        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.totp_secret, before_secret)
        self.assertEqual(self.user.profile.backup_codes, before_codes)

    def test_send_otp_no_longer_prints_live_codes(self):
        with patch('microsys.views.twofa.send_mail', return_value=1), \
             patch('builtins.print') as mocked_print:
            from microsys.views.twofa import send_otp

            self.assertTrue(send_otp(None, self.user, intent='login'))

        mocked_print.assert_not_called()

    def test_generated_backup_codes_are_hashed_at_rest(self):
        response = self.client.post(
            reverse('generate_backup_codes'),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        plain_codes = payload['codes']

        self.user.profile.refresh_from_db()
        stored_codes = self.user.profile.backup_codes
        self.assertEqual(len(stored_codes), len(plain_codes))

        for raw_code, stored_code in zip(plain_codes, stored_codes):
            self.assertNotEqual(raw_code, stored_code)
            identify_hasher(stored_code)

    def test_backup_code_verification_consumes_hashed_code(self):
        generate_response = self.client.post(
            reverse('generate_backup_codes'),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        plain_codes = json.loads(generate_response.content)['codes']
        self._prime_pre_2fa_session()

        response = self.client.post(
            reverse('verify_otp_login'),
            {'otp_code': plain_codes[0], 'method': 'backup_code'},
        )

        self.assertEqual(response.status_code, 302)
        self.user.profile.refresh_from_db()
        self.assertEqual(len(self.user.profile.backup_codes), len(plain_codes) - 1)

    def test_verify_otp_rejects_unsafe_next_redirects(self):
        from microsys.models import SystemSettings

        cache.set(f'otp_{self.user.pk}_login', {'code': '123456', 'attempts': 0}, timeout=300)
        self._prime_pre_2fa_session()
        settings_obj = SystemSettings.load()
        settings_obj.home_url = reverse('user_profile')
        settings_obj.save()

        response = self.client.post(
            reverse('verify_otp_login'),
            {'otp_code': '123456', 'method': 'email', 'next': 'https://evil.example/phish'},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('user_profile'))
