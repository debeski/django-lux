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
            'microsys.middleware.MicrosysMiddleware',
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
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.contrib.sessions.models import Session
from django.urls import reverse
from django.core.cache import cache
from django.contrib.auth.hashers import check_password, identify_hasher, make_password
from django.utils import timezone
from datetime import timedelta
import json
from types import SimpleNamespace
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
        self.assertIn('server_time_backend_display', response.context)
        self.assertIn('version', response.context)
        self.assertIn('django_version', response.context)
        self.assertIn('python_version', response.context)

    def test_options_view_shows_navbar_mode_card_only_when_override_is_allowed(self):
        settings_obj = SystemSettings.load()
        settings_obj.navbar_config = {
            'enabled': True,
            'default_mode': 'hierarchy',
            'allow_user_mode_override': True,
            'hierarchy': {'nodes': []},
        }
        settings_obj.save()

        response = self.client.get(reverse('options_view'))

        self.assertContains(response, 'data-options-card="navbar-mode"')
        self.assertContains(response, 'data-ms-navbar')
        settings_obj.navbar_config['allow_user_mode_override'] = False
        settings_obj.save(update_fields=['navbar_config'])
        response = self.client.get(reverse('options_view'))
        self.assertNotContains(response, 'data-options-card="navbar-mode"')

    def test_options_email_diagnostics_only_render_when_email_features_enabled(self):
        settings_obj = SystemSettings.load()
        settings_obj.email_2fa = False
        settings_obj.public_registration_enabled = False
        settings_obj.save()

        response = self.client.get(reverse('options_view'))

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context.get('email_service'))
        self.assertNotContains(response, '<th>Email:</th>', html=True)

        settings_obj.email_2fa = True
        settings_obj.save()
        response = self.client.get(reverse('options_view'))

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context.get('email_service'))
        self.assertContains(response, '<th>Email:</th>', html=True)

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

    def test_options_view_hides_diagnostics_for_central_and_scoped_staff(self):
        central_staff = User.objects.create_user(
            username='central',
            email='central@example.com',
            password='centralpass123',
            is_staff=True,
        )
        scoped_staff = User.objects.create_user(
            username='scoped',
            email='scoped@example.com',
            password='scopedpass123',
            is_staff=True,
        )
        scoped_staff.profile.scope = Scope.objects.create(name='Scoped Office')
        scoped_staff.profile.save(update_fields=['scope'])

        for user, password in ((central_staff, 'centralpass123'), (scoped_staff, 'scopedpass123')):
            self.client.logout()
            self.client.login(username=user.username, password=password)
            response = self.client.get(reverse('options_view'))
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.context['show_system_diagnostics'])
            self.assertNotIn('version', response.context)
            self.assertNotIn('python_version', response.context)

    def test_options_view_shows_diagnostics_for_global_staff(self):
        global_staff = User.objects.create_user(
            username='global',
            email='global@example.com',
            password='globalpass123',
            is_staff=True,
        )
        content_type = ContentType.objects.get(app_label='microsys', model='profile')
        permission = Permission.objects.get(content_type=content_type, codename='manage_scopes')
        global_staff.user_permissions.add(permission)

        self.client.logout()
        self.client.login(username='global', password='globalpass123')
        response = self.client.get(reverse('options_view'))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['show_system_diagnostics'])
        self.assertIn('version', response.context)
        self.assertIn('python_version', response.context)
        self.assertContains(response, response.context['server_time_backend_display'])

    def test_staff_missing_profile_does_not_get_staff_tier_access(self):
        staff_without_profile = User.objects.create_user(
            username='missingprofile',
            email='missingprofile@example.com',
            password='missingpass123',
            is_staff=True,
        )
        Profile = apps.get_model('microsys', 'Profile')
        Profile.all_objects.filter(user=staff_without_profile).delete()

        self.client.logout()
        self.client.login(username='missingprofile', password='missingpass123')
        response = self.client.get(reverse('manage_users'))

        self.assertEqual(response.status_code, 403)

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
        self.assertContains(response, '?step=5')
        self.assertContains(response, '?step=6')
        self.assertContains(response, reverse('system_settings_export'))
        self.assertContains(response, 'ms-system-settings-grid')
        self.assertContains(response, 'ms-system-settings-tile')
        self.assertContains(response, 'data-ms-tooltip="System names, logo, favicon, and home route."')

    def test_options_view_uses_shared_selector_markup_for_font_picker(self):
        response = self.client.get(reverse('options_view'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ms-font-picker')
        self.assertContains(response, 'ms-density-options')
        self.assertContains(response, 'data-font="shabwa"')
        self.assertContains(response, 'microsys/main/js/options.js?v=20260522b')
        self.assertNotContains(response, 'ms-font-preview-card')

    def test_system_settings_modal_honors_requested_wizard_step(self):
        response = self.client.get(
            reverse('modal_manager', args=['microsys', 'SystemSettings', 1]) + '?step=4',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertIn('data-ms-wizard-initial-step="4"', payload['html'])
        self.assertIn('?step=4', payload['html'])
        self.assertIn('ms-btn-submit', payload['html'])
        self.assertNotIn('microsys-form-action-primary', payload['html'])
        self.assertNotIn('microsys-form-action-neutral', payload['html'])
        self.assertNotIn('ms-btn-next', payload['html'])
        self.assertNotIn('ms-btn-prev', payload['html'])

    def test_system_settings_modal_honors_requested_wizard_step_five(self):
        response = self.client.get(
            reverse('modal_manager', args=['microsys', 'SystemSettings', 1]) + '?step=5',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertIn('data-ms-wizard-initial-step="5"', payload['html'])
        self.assertIn('?step=5', payload['html'])
        self.assertIn('ms-btn-submit', payload['html'])

    def test_system_settings_modal_honors_requested_wizard_step_six(self):
        response = self.client.get(
            reverse('modal_manager', args=['microsys', 'SystemSettings', 1]) + '?step=6',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertIn('data-ms-wizard-initial-step="6"', payload['html'])
        self.assertIn('?step=6', payload['html'])
        self.assertIn('ms-btn-submit', payload['html'])

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

    def test_system_settings_modal_post_preserves_step_six_values_when_omitted(self):
        settings_obj = SystemSettings.load()
        settings_obj.allowed_themes = ['dark', 'neon']
        settings_obj.default_theme = 'dark'
        settings_obj.allowed_fonts = ['cairo']
        settings_obj.default_fonts = {'en': 'cairo', 'ar': 'cairo'}
        settings_obj.default_table_density = 'roomy'
        settings_obj.save()

        response = self.client.post(
            reverse('modal_manager', args=['microsys', 'SystemSettings', 1]) + '?step=0',
            {
                'system_names': '{"en": "System", "ar": "System"}',
                'home_url': '/dashboard/',
                'default_language': 'en',
                'allow_user_theme_override': 'on',
                'allow_user_font_override': 'on',
                'languages': '{"en": {"name": "English", "dir": "ltr", "flag": "EN"}, "ar": {"name": "Arabic", "dir": "rtl", "flag": "AR"}}',
                'translations_override': '{}',
                'sidebar_config': '{"enabled": true, "home_url_name": null, "entries": [], "enable_reorder": true, "show_toolbar": true, "show_icons": true, "density": "balanced", "allow_user_density": true, "collapse_mode": "icons"}',
                'email_config': '{"transport": "direct", "secret_storage": "env", "host": "", "port": 587, "use_tls": true, "use_ssl": false, "username": "", "default_from_email": "", "password_configured": false}',
                'client_ip_config': '{"mode": "x_forwarded_for", "trusted_proxy_hops": 1, "custom_header": ""}',
                'titlebar_title_align': 'start',
                'titlebar_title_size': 'md',
                'titlebar_home_shape': 'circle',
                'titlebar_height': 'balanced',
                'titlebar_surface': 'default',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertTrue(payload['success'])

        settings_obj.refresh_from_db()
        self.assertEqual(settings_obj.home_url, '/dashboard/')
        self.assertEqual(settings_obj.allowed_themes, ['dark', 'neon'])
        self.assertEqual(settings_obj.default_theme, 'dark')
        self.assertEqual(settings_obj.allowed_fonts, ['cairo'])
        self.assertEqual(settings_obj.default_fonts, {'en': 'cairo', 'ar': 'cairo'})
        self.assertEqual(settings_obj.default_table_density, 'roomy')

    def test_generic_modal_manager_relies_on_signal_logging_for_scope_create(self):
        fake_request = SimpleNamespace(META={})
        with patch('microsys.models.UserActivityLog.safe_log') as safe_log, \
             patch('microsys.signals.get_current_user', return_value=self.user), \
             patch('microsys.signals.get_current_request', return_value=fake_request):
            response = self.client.post(
                reverse('modal_manager', args=['microsys', 'Scope', 'new']),
                {'name': 'NoDupScope'},
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertTrue(payload['success'])
        self.assertTrue(Scope.objects.filter(name='NoDupScope').exists())
        self.assertEqual(safe_log.call_count, 1)

    def test_generic_modal_delete_relies_on_signal_logging_for_scope_delete(self):
        scope = Scope.objects.create(name='DeleteNoDupScope')
        fake_request = SimpleNamespace(META={})
        with patch('microsys.models.UserActivityLog.safe_log') as safe_log, \
             patch('microsys.signals.get_current_user', return_value=self.user), \
             patch('microsys.signals.get_current_request', return_value=fake_request):
            response = self.client.post(
                reverse('modal_delete', args=['microsys', 'Scope', scope.pk]),
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertTrue(payload['success'])
        self.assertFalse(Scope.objects.filter(pk=scope.pk).exists())
        self.assertEqual(safe_log.call_count, 1)

    def test_disabled_sidebar_hides_titlebar_toggle(self):
        settings_obj = SystemSettings.load()
        settings_obj.sidebar_config = {
            'enabled': False,
            'entries': [],
            'show_toolbar': False,
            'enable_reorder': False,
            'allow_user_density': False,
            'collapse_mode': 'hidden',
        }
        settings_obj.save()

        response = self.client.get(reverse('options_view'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="sidebarToggle"')
        self.assertContains(response, 'titlebar__side--empty')
        self.assertNotContains(response, 'titlebar__side--has-toggle')

    def test_locked_expanded_sidebar_hides_desktop_toggle_without_reserved_space(self):
        settings_obj = SystemSettings.load()
        settings_obj.sidebar_config = {
            'enabled': True,
            'entries': [],
            'show_toolbar': False,
            'enable_reorder': False,
            'allow_user_density': False,
            'collapse_mode': 'locked_expanded',
        }
        settings_obj.save()

        response = self.client.get(reverse('options_view'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="sidebarToggle"')
        self.assertContains(response, 'sidebar-toggle--desktop-disabled')
        self.assertContains(response, 'titlebar__side--mobile-toggle')
        self.assertNotContains(response, 'titlebar__side--has-toggle')

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
        settings_obj = SystemSettings.load()
        settings_obj.is_configured = True
        settings_obj.email_2fa = True
        settings_obj.save()
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

    def test_user_profile_two_factor_setup_buttons_render_enable_label(self):
        response = self.client.get(reverse('user_profile'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<span class="btn-label">Enable</span>', html=False)
        self.assertNotContains(response, '<span class="btn-label"></span>', html=False)

    def test_user_profile_routes_virtual_session_logs_to_system_interactions(self):
        from microsys.models import UserActivityLog

        session_log = UserActivityLog.objects.create(
            created_by=self.user,
            action='DELETE',
            model_name='session',
        )
        recent_log = UserActivityLog.objects.create(
            created_by=self.user,
            action='CREATE',
            model_name='Mounted App Entry',
        )

        response = self.client.get(reverse('user_profile'))

        self.assertEqual(response.status_code, 200)
        self.assertIn(session_log, response.context['system_interactions'])
        self.assertNotIn(session_log, response.context['recent_activity'])
        self.assertIn(recent_log, response.context['recent_activity'])


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

    def test_activity_log_view_translates_system_settings_model_name_in_arabic(self):
        from microsys.models import UserActivityLog

        UserActivityLog.objects.create(
            created_by=self.user,
            action='UPDATE',
            model_name='System Settings',
        )
        session = self.client.session
        session['lang'] = 'ar'
        session.save()

        response = self.client.get(reverse('user_activity_log'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'إعدادات النظام')

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

    def test_activity_log_view_uses_table_pagination_without_double_paginating_page_two(self):
        from microsys.models import UserActivityLog

        initial_count = UserActivityLog.objects.count()
        for index in range(14):
            UserActivityLog.objects.create(
                created_by=self.user,
                action='CREATE',
                model_name=f'Entry {index}',
            )

        response = self.client.get(reverse('user_activity_log'), {'per_page': 10, 'page': 2})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['table'].page.number, 2)
        self.assertEqual(response.context['table'].paginator.num_pages, 2)
        self.assertEqual(
            len(response.context['table'].page.object_list),
            (initial_count + 14) - 10,
        )

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

    def test_user_create_modal_renders_wizard_actions_for_cancel_and_step_navigation(self):
        self.client.login(username='root', password='rootpass123')

        response = self.client.get(
            reverse('modal_user'),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertIn('data-bs-dismiss="modal"', payload['html'])
        self.assertIn('ms-btn-prev d-none', payload['html'])
        self.assertIn('ms-btn-next', payload['html'])
        self.assertIn('ms-btn-submit d-none', payload['html'])

    def test_manage_users_requires_view_user_permission_for_staff(self):
        self.client.login(username='staffer', password='staffpass123')

        response = self.client.get(reverse('manage_users'))

        self.assertEqual(response.status_code, 403)

    def test_manage_users_allows_staff_with_view_user_permission(self):
        self._grant_user_permission(self.staff_user, 'view_user')
        self.client.login(username='staffer', password='staffpass123')

        response = self.client.get(reverse('manage_users'))

        self.assertEqual(response.status_code, 200)

    def test_manage_users_uses_table_pagination_without_double_paginating_page_two(self):
        self._grant_user_permission(self.staff_user, 'view_user')
        self.client.login(username='staffer', password='staffpass123')

        for index in range(12):
            user = User.objects.create_user(
                username=f'scopea{index}',
                email=f'scopea{index}@example.com',
                password='scopepass123',
            )
            user.profile.scope = self.scope_a
            user.profile.save(update_fields=['scope'])

        response = self.client.get(reverse('manage_users'), {'per_page': 10, 'page': 2})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['table'].page.number, 2)
        self.assertEqual(response.context['table'].paginator.num_pages, 2)
        self.assertEqual(len(response.context['table'].page.object_list), 3)

    def test_manage_users_central_staff_excludes_global_staff_group_members(self):
        central_staff = User.objects.create_user(
            username='centralviewer',
            email='centralviewer@example.com',
            password='centralpass123',
            is_staff=True,
        )
        global_staff = User.objects.create_user(
            username='globaltarget',
            email='globaltarget@example.com',
            password='globalpass123',
            is_staff=True,
        )
        regular_staff = User.objects.create_user(
            username='centraltarget',
            email='centraltarget@example.com',
            password='targetpass123',
            is_staff=True,
        )
        content_type = ContentType.objects.get(app_label='microsys', model='profile')
        manage_scopes = Permission.objects.get(content_type=content_type, codename='manage_scopes')
        group = Group.objects.create(name='Global Staff')
        group.permissions.add(manage_scopes)
        global_staff.groups.add(group)

        self.client.login(username='centralviewer', password='centralpass123')
        response = self.client.get(reverse('manage_users'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, regular_staff.username)
        self.assertNotContains(response, global_staff.username)

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

    def test_user_detail_modal_shows_computed_staff_tier_summary(self):
        self._grant_user_permission(self.staff_user, 'view_user')
        profile_type = ContentType.objects.get(app_label='microsys', model='profile')
        manage_scopes = Permission.objects.get(content_type=profile_type, codename='manage_scopes')
        manage_staff = Permission.objects.get(content_type=profile_type, codename='manage_staff')
        target = User.objects.create_user(
            username='targetglobal',
            email='targetglobal@example.com',
            password='targetglobalpass123',
            is_staff=True,
        )
        target.user_permissions.add(manage_scopes, manage_staff)
        self.client.login(username='root', password='rootpass123')

        response = self.client.get(reverse('user_detail_modal', args=[target.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Global Staff')
        self.assertContains(response, 'Can Assign Staff Roles')
        self.assertContains(response, 'ms-staff-tier-badge--global_staff')

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

    def test_setup_totp_uses_configured_system_name_as_issuer(self):
        captured = {}

        class FakeTOTP:
            def __init__(self, secret):
                self.secret = secret

            def provisioning_uri(self, name, issuer_name):
                captured['name'] = name
                captured['issuer_name'] = issuer_name
                return 'otpauth://totp/test'

        class FakeQr:
            def save(self, buffer, format):
                buffer.write(b'png')

        fake_pyotp = SimpleNamespace(
            random_base32=lambda: 'JBSWY3DPEHPK3PXP',
            TOTP=FakeTOTP,
        )
        fake_qrcode = SimpleNamespace(make=lambda uri: FakeQr())

        with patch('microsys.views.twofa.pyotp', fake_pyotp), \
             patch('microsys.views.twofa.qrcode', fake_qrcode), \
             patch('microsys.views.twofa.get_system_config', return_value={
                 'identity': {'display_name': 'Configured Portal'}
             }):
            response = self.client.post(
                reverse('setup_totp'),
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(captured['name'], self.user.email)
        self.assertEqual(captured['issuer_name'], 'Configured Portal')
        self.assertNotEqual(captured['issuer_name'], 'FineStor')
        self.assertEqual(payload['secret'], 'JBSWY3DPEHPK3PXP')

        from microsys.utils import decrypt_totp_secret, is_encrypted_totp_secret
        self.user.profile.refresh_from_db()
        self.assertTrue(is_encrypted_totp_secret(self.user.profile.totp_secret))
        self.assertNotEqual(self.user.profile.totp_secret, 'JBSWY3DPEHPK3PXP')
        self.assertEqual(decrypt_totp_secret(self.user.profile.totp_secret), 'JBSWY3DPEHPK3PXP')

    def test_setup_totp_database_save_error_returns_json(self):
        from django.db import DatabaseError

        class FakeTOTP:
            def __init__(self, secret):
                self.secret = secret

            def provisioning_uri(self, name, issuer_name):
                return 'otpauth://totp/test'

        fake_pyotp = SimpleNamespace(
            random_base32=lambda: 'JBSWY3DPEHPK3PXP',
            TOTP=FakeTOTP,
        )

        with patch('microsys.views.twofa.pyotp', fake_pyotp), \
             patch('microsys.views.twofa.qrcode'), \
             patch('microsys.views.twofa.set_profile_totp_state', side_effect=DatabaseError('too long')):
            response = self.client.post(
                reverse('setup_totp'),
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            )

        self.assertEqual(response.status_code, 500)
        payload = json.loads(response.content)
        self.assertEqual(payload['status'], 'error')
        self.assertIn('Run database migrations', payload['message'])

    def test_setup_totp_non_database_save_error_returns_json(self):
        class FakeTOTP:
            def __init__(self, secret):
                self.secret = secret

            def provisioning_uri(self, name, issuer_name):
                return 'otpauth://totp/test'

        fake_pyotp = SimpleNamespace(
            random_base32=lambda: 'JBSWY3DPEHPK3PXP',
            TOTP=FakeTOTP,
        )

        with patch('microsys.views.twofa.pyotp', fake_pyotp), \
             patch('microsys.views.twofa.qrcode'), \
             patch('microsys.views.twofa.set_profile_totp_state', side_effect=RuntimeError('missing crypto backend')):
            response = self.client.post(
                reverse('setup_totp'),
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            )

        self.assertEqual(response.status_code, 500)
        payload = json.loads(response.content)
        self.assertEqual(payload['status'], 'error')
        self.assertIn('Unable to prepare authenticator setup', payload['message'])

    def test_setup_totp_generation_error_returns_json(self):
        class FakeTOTP:
            def __init__(self, secret):
                self.secret = secret

            def provisioning_uri(self, name, issuer_name):
                raise RuntimeError('broken provisioning payload')

        fake_pyotp = SimpleNamespace(
            random_base32=lambda: 'JBSWY3DPEHPK3PXP',
            TOTP=FakeTOTP,
        )

        with patch('microsys.views.twofa.pyotp', fake_pyotp), \
             patch('microsys.views.twofa.qrcode', SimpleNamespace(make=lambda uri: None)):
            response = self.client.post(
                reverse('setup_totp'),
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            )

        self.assertEqual(response.status_code, 500)
        payload = json.loads(response.content)
        self.assertEqual(payload['status'], 'error')
        self.assertIn('Unable to generate authenticator setup', payload['message'])

    def test_totp_verification_reads_encrypted_secret(self):
        captured = {}

        class FakeTOTP:
            def __init__(self, secret):
                captured['secret'] = secret

            def verify(self, code, valid_window=0):
                return code == '654321'

        self.user.profile.totp_secret = 'JBSWY3DPEHPK3PXP'
        self.user.profile.is_totp_2fa_enabled = True
        self.user.profile.save(update_fields=['totp_secret', 'is_totp_2fa_enabled'])
        self.user.profile.refresh_from_db()
        self._prime_pre_2fa_session()

        fake_pyotp = SimpleNamespace(TOTP=FakeTOTP)
        with patch('microsys.views.twofa.pyotp', fake_pyotp):
            response = self.client.post(
                reverse('verify_otp_login'),
                {'otp_code': '654321', 'method': 'totp'},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(captured['secret'], 'JBSWY3DPEHPK3PXP')

    def test_two_factor_verify_is_ip_rate_limited(self):
        self._prime_pre_2fa_session()
        cache.set('microsys:2fa:verify:ip:127.0.0.1:login', 20, timeout=600)

        response = self.client.post(
            reverse('verify_otp_login'),
            {'otp_code': '000000'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 429)
        payload = json.loads(response.content)
        self.assertEqual(payload['status'], 'error')

    def test_two_factor_email_send_is_ip_rate_limited(self):
        cache.set('microsys:2fa:send:ip:127.0.0.1:login', 10, timeout=3600)
        self._prime_pre_2fa_session()

        with patch('microsys.views.twofa.send_microsys_mail', return_value=1) as mocked_mail:
            response = self.client.post(
                reverse('resend_otp_login'),
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            )

        self.assertEqual(response.status_code, 400)
        mocked_mail.assert_not_called()

    def test_send_otp_no_longer_prints_live_codes(self):
        with patch('microsys.views.twofa.send_microsys_mail', return_value=1), \
             patch('builtins.print') as mocked_print:
            from microsys.views.twofa import send_otp

            self.assertTrue(send_otp(None, self.user, intent='login'))

        mocked_print.assert_not_called()

    def test_email_otp_is_stored_hashed_in_cache(self):
        captured = {}

        def fake_send_microsys_mail(subject, body, recipients, fail_silently=False):
            captured['body'] = body
            return 1

        with patch('microsys.views.twofa.send_microsys_mail', side_effect=fake_send_microsys_mail), \
             patch('microsys.views.twofa._generate_email_otp_code', return_value='123456'):
            from microsys.views.twofa import send_otp

            self.assertTrue(send_otp(None, self.user, intent='login'))

        cached = cache.get(f'otp_{self.user.pk}_login')
        self.assertIsNone(cached.get('code'))
        self.assertTrue(cached.get('code_hash'))
        identify_hasher(cached['code_hash'])
        self.assertTrue(check_password('123456', cached['code_hash']))

    def test_enable_email_2fa_sends_to_confirmed_email_and_updates_after_verify(self):
        self.user.profile.is_email_2fa_enabled = False
        self.user.profile.email_verified_at = None
        self.user.profile.save(update_fields=['is_email_2fa_enabled', 'email_verified_at'])
        captured = {}

        def fake_send_microsys_mail(subject, body, recipients, fail_silently=False):
            captured['recipients'] = recipients
            return 1

        with patch('microsys.views.twofa.send_microsys_mail', side_effect=fake_send_microsys_mail), \
             patch('microsys.views.twofa._generate_email_otp_code', return_value='123456'):
            response = self.client.post(
                reverse('enable_2fa'),
                {'method': 'email', 'email': 'corrected@example.com'},
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured['recipients'], ['corrected@example.com'])
        cached = cache.get(f'otp_{self.user.pk}_enable_email')
        self.assertEqual(cached['email'], 'corrected@example.com')

        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'twofa@example.com')

        response = self.client.post(
            reverse('verify_otp_enable'),
            {'otp_code': '123456', 'method': 'email', 'intent': 'enable_email'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(payload['status'], 'success')
        self.user.refresh_from_db()
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.email, 'corrected@example.com')
        self.assertTrue(self.user.profile.is_email_2fa_enabled)
        self.assertIsNotNone(self.user.profile.email_verified_at)

    def test_enable_email_2fa_rejects_invalid_confirmed_email_before_send(self):
        self.user.profile.is_email_2fa_enabled = False
        self.user.profile.save(update_fields=['is_email_2fa_enabled'])

        with patch('microsys.views.twofa.send_microsys_mail', return_value=1) as mocked_mail:
            response = self.client.post(
                reverse('enable_2fa'),
                {'method': 'email', 'email': 'not-an-email'},
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            )

        self.assertEqual(response.status_code, 400)
        mocked_mail.assert_not_called()

    def test_enable_email_2fa_send_cooldown_is_per_confirmed_email(self):
        self.user.profile.is_email_2fa_enabled = False
        self.user.profile.save(update_fields=['is_email_2fa_enabled'])

        with patch('microsys.views.twofa.send_microsys_mail', return_value=1) as mocked_mail, \
             patch('microsys.views.twofa._generate_email_otp_code', return_value='123456'):
            first = self.client.post(
                reverse('enable_2fa'),
                {'method': 'email', 'email': 'wrong@example.com'},
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            )
            second = self.client.post(
                reverse('enable_2fa'),
                {'method': 'email', 'email': 'corrected@example.com'},
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(mocked_mail.call_count, 2)
        cached = cache.get(f'otp_{self.user.pk}_enable_email')
        self.assertEqual(cached['email'], 'corrected@example.com')

    def test_disable_2fa_requires_current_password(self):
        response = self.client.post(
            reverse('disable_2fa'),
            {'method': 'email'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 400)
        payload = json.loads(response.content)
        self.assertEqual(payload['status'], 'error')
        self.user.profile.refresh_from_db()
        self.assertTrue(self.user.profile.is_email_2fa_enabled)

    def test_disable_2fa_accepts_valid_current_password(self):
        response = self.client.post(
            reverse('disable_2fa'),
            {'method': 'email', 'current_password': 'twofapass123'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(payload['status'], 'success')
        self.user.profile.refresh_from_db()
        self.assertFalse(self.user.profile.is_email_2fa_enabled)

    def test_generated_backup_codes_are_hashed_at_rest(self):
        response = self.client.post(
            reverse('generate_backup_codes'),
            {'current_password': 'twofapass123'},
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

    def test_generate_backup_codes_requires_current_password(self):
        response = self.client.post(
            reverse('generate_backup_codes'),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 400)
        payload = json.loads(response.content)
        self.assertEqual(payload['status'], 'error')

    def test_backup_code_verification_consumes_hashed_code(self):
        generate_response = self.client.post(
            reverse('generate_backup_codes'),
            {'current_password': 'twofapass123'},
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

        cache.set(
            f'otp_{self.user.pk}_login',
            {'code_hash': make_password('123456'), 'attempts': 0},
            timeout=300,
        )
        self._prime_pre_2fa_session()
        settings_obj = SystemSettings.load()
        settings_obj.home_url = reverse('user_profile')
        settings_obj.save()

        response = self.client.post(
            reverse('verify_otp_login'),
            {'otp_code': '123456', 'next': 'https://evil.example/phish'},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('user_profile'))

    def test_login_two_factor_auto_sends_email_when_email_is_only_primary_method(self):
        self.client.logout()

        with patch('microsys.views.twofa.send_microsys_mail', return_value=1) as mocked_mail:
            response = self.client.post(reverse('login'), {
                'username': 'twofa',
                'password': 'twofapass123',
            })

        self.assertRedirects(response, reverse('verify_otp_login'), fetch_redirect_response=False)
        mocked_mail.assert_called_once()
        session = self.client.session
        self.assertEqual(session.get('pre_2fa_method'), 'email')
        self.assertTrue(session.get('pre_2fa_email_sent'))

    def test_login_two_factor_defaults_to_totp_without_auto_sending_email_when_multiple_methods_exist(self):
        self.client.logout()
        self.user.profile.totp_secret = 'JBSWY3DPEHPK3PXP'
        self.user.profile.is_totp_2fa_enabled = True
        self.user.profile.save(update_fields=['totp_secret', 'is_totp_2fa_enabled'])

        with patch('microsys.views.twofa.send_microsys_mail', return_value=1) as mocked_mail:
            response = self.client.post(reverse('login'), {
                'username': 'twofa',
                'password': 'twofapass123',
            })

        self.assertRedirects(response, reverse('verify_otp_login'), fetch_redirect_response=False)
        mocked_mail.assert_not_called()
        self.assertEqual(self.client.session.get('pre_2fa_method'), 'totp')

    def test_login_verify_returns_ajax_redirect_payload_for_email_code(self):
        cache.set(
            f'otp_{self.user.pk}_login',
            {'code_hash': make_password('123456'), 'attempts': 0},
            timeout=300,
        )
        self._prime_pre_2fa_session()

        response = self.client.post(
            reverse('verify_otp_login'),
            {'otp_code': '123456', 'method': 'email'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(payload['status'], 'success')
        self.assertTrue(payload['redirect_url'])

    def test_real_login_handoff_allows_email_otp_verification_and_redirects(self):
        self.client.logout()

        with patch('microsys.views.twofa._generate_email_otp_code', return_value='123456'), \
             patch('microsys.views.twofa.send_microsys_mail', return_value=1):
            login_response = self.client.post(reverse('login'), {
                'username': 'twofa',
                'password': 'twofapass123',
            })

        self.assertRedirects(login_response, reverse('verify_otp_login'), fetch_redirect_response=False)

        verify_response = self.client.post(
            reverse('verify_otp_login'),
            {'otp_code': '123456', 'method': 'email'},
        )

        self.assertEqual(verify_response.status_code, 302)
        self.assertEqual(verify_response.url, reverse('user_profile'))

    def test_login_email_resend_returns_cooldown_payload_for_two_minutes(self):
        self._prime_pre_2fa_session()
        with patch('microsys.views.twofa.send_microsys_mail', return_value=1) as mocked_mail:
            response = self.client.post(
                reverse('resend_otp_login'),
                {'method': 'email'},
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(payload['status'], 'success')
        mocked_mail.assert_called_once()
        self.assertGreaterEqual(payload['cooldown_seconds'], 119)

        second = self.client.post(
            reverse('resend_otp_login'),
            {'method': 'email'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(second.status_code, 400)
        second_payload = json.loads(second.content)
        self.assertGreaterEqual(second_payload['cooldown_seconds'], 1)

    def test_trusted_device_bypasses_login_two_factor_on_next_login(self):
        trusted_device_model = apps.get_model('microsys', 'TrustedDevice')
        cache.set(
            f'otp_{self.user.pk}_login',
            {'code_hash': make_password('123456'), 'attempts': 0},
            timeout=300,
        )
        self._prime_pre_2fa_session()

        verify_response = self.client.post(
            reverse('verify_otp_login'),
            {'otp_code': '123456', 'method': 'email', 'trust_device': '1'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(verify_response.status_code, 200)
        self.assertEqual(trusted_device_model.objects.filter(user=self.user, revoked_at__isnull=True).count(), 1)

        trusted_cookie = verify_response.cookies.get('microsys_trusted_device')
        bypass_client = Client(HTTP_USER_AGENT='Mozilla/5.0 Chrome/122.0 Linux')
        bypass_client.cookies['microsys_trusted_device'] = trusted_cookie.value

        with patch('microsys.views.twofa.send_microsys_mail', return_value=1) as mocked_mail:
            response = bypass_client.post(reverse('login'), {
                'username': 'twofa',
                'password': 'twofapass123',
            })

        self.assertEqual(response.status_code, 302)
        self.assertNotEqual(response.url, reverse('verify_otp_login'))
        mocked_mail.assert_not_called()
        trusted_device = trusted_device_model.objects.get(user=self.user)
        self.assertTrue(trusted_device.session_key)


class ProfileSessionDeviceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username='devices',
            email='devices@example.com',
            password='devicespass123',
        )
        settings_obj = SystemSettings.load()
        settings_obj.is_configured = True
        settings_obj.save()

    def test_profile_lists_current_signed_in_session(self):
        client = Client(HTTP_USER_AGENT='Mozilla/5.0 Chrome/122.0 Linux')
        client.login(username='devices', password='devicespass123')

        response = client.get(reverse('user_profile'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Signed-in Devices')
        self.assertContains(response, 'Current Session')
        self.assertContains(response, 'Chrome on Linux')

    def test_profile_falls_back_to_current_session_when_session_row_is_not_decodable(self):
        from django.utils import timezone
        from microsys.views.profile import _profile_sessions_for_user

        sessions = _profile_sessions_for_user(
            self.user,
            current_session_key='missing-session-row',
            current_session_data={
                'microsys_device': {
                    'user_agent': 'Mozilla/5.0 Chrome/122.0 Linux',
                    'ip_address': '127.0.0.1',
                    'first_seen': '2026-05-01T09:00:00+00:00',
                    'last_seen': '2026-05-01T09:01:00+00:00',
                },
            },
            current_expire_date=timezone.now(),
        )

        self.assertEqual(len(sessions), 1)
        self.assertTrue(sessions[0]['is_current'])
        self.assertEqual(sessions[0]['device_label'], 'Chrome on Linux')

    def test_profile_can_revoke_another_own_session(self):
        first_client = Client(HTTP_USER_AGENT='Mozilla/5.0 Chrome/122.0 Linux')
        second_client = Client(HTTP_USER_AGENT='Mozilla/5.0 Firefox/123.0 Windows')
        first_client.login(username='devices', password='devicespass123')
        second_client.login(username='devices', password='devicespass123')
        first_client.get(reverse('user_profile'))
        second_client.get(reverse('user_profile'))
        second_session_key = second_client.session.session_key

        response = first_client.post(
            reverse('revoke_profile_session', args=[second_session_key]),
            {'current_password': 'devicespass123'},
        )

        self.assertRedirects(response, reverse('user_profile'))
        self.assertFalse(Session.objects.filter(session_key=second_session_key).exists())
        second_response = second_client.get(reverse('user_profile'))
        self.assertEqual(second_response.status_code, 302)

    def test_profile_session_revoke_requires_current_password(self):
        first_client = Client(HTTP_USER_AGENT='Mozilla/5.0 Chrome/122.0 Linux')
        second_client = Client(HTTP_USER_AGENT='Mozilla/5.0 Firefox/123.0 Windows')
        first_client.login(username='devices', password='devicespass123')
        second_client.login(username='devices', password='devicespass123')
        first_client.get(reverse('user_profile'))
        second_client.get(reverse('user_profile'))
        second_session_key = second_client.session.session_key

        response = first_client.post(reverse('revoke_profile_session', args=[second_session_key]))

        self.assertRedirects(response, reverse('user_profile'))
        self.assertTrue(Session.objects.filter(session_key=second_session_key).exists())

    def test_profile_session_revoke_reports_password_errors_to_ajax_modal(self):
        first_client = Client(HTTP_USER_AGENT='Mozilla/5.0 Chrome/122.0 Linux')
        second_client = Client(HTTP_USER_AGENT='Mozilla/5.0 Firefox/123.0 Windows')
        first_client.login(username='devices', password='devicespass123')
        second_client.login(username='devices', password='devicespass123')
        first_client.get(reverse('user_profile'))
        second_client.get(reverse('user_profile'))
        second_session_key = second_client.session.session_key

        response = first_client.post(
            reverse('revoke_profile_session', args=[second_session_key]),
            {'current_password': 'wrong-password'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(json.loads(response.content)['status'], 'error')
        self.assertTrue(Session.objects.filter(session_key=second_session_key).exists())

    def test_profile_session_revoke_returns_ajax_redirect_after_password_confirmation(self):
        first_client = Client(HTTP_USER_AGENT='Mozilla/5.0 Chrome/122.0 Linux')
        second_client = Client(HTTP_USER_AGENT='Mozilla/5.0 Firefox/123.0 Windows')
        first_client.login(username='devices', password='devicespass123')
        second_client.login(username='devices', password='devicespass123')
        first_client.get(reverse('user_profile'))
        second_client.get(reverse('user_profile'))
        second_session_key = second_client.session.session_key

        response = first_client.post(
            reverse('revoke_profile_session', args=[second_session_key]),
            {'current_password': 'devicespass123'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(payload['status'], 'success')
        self.assertEqual(payload['redirect_url'], reverse('user_profile'))
        self.assertFalse(Session.objects.filter(session_key=second_session_key).exists())

    def test_profile_shows_trusted_device_state_in_signed_in_devices(self):
        trusted_device_model = apps.get_model('microsys', 'TrustedDevice')
        client = Client(HTTP_USER_AGENT='Mozilla/5.0 Chrome/122.0 Linux')
        client.login(username='devices', password='devicespass123')
        session = client.session
        trusted_device = trusted_device_model.objects.create(
            user=self.user,
            token_hash='test-trusted-device',
            session_key=session.session_key,
            trusted_until=timezone.now() + timedelta(days=30),
        )
        session['microsys_device'] = {
            'user_agent': 'Mozilla/5.0 Chrome/122.0 Linux',
            'ip_address': '127.0.0.1',
            'first_seen': timezone.now().isoformat(),
            'last_seen': timezone.now().isoformat(),
            'trusted_device_id': trusted_device.pk,
            'trusted_until': trusted_device.trusted_until.isoformat(),
        }
        session.save()

        response = client.get(reverse('user_profile'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Trusted Device')
        self.assertContains(response, 'Trusted Until')

    def test_profile_revoke_session_revokes_linked_trusted_device(self):
        trusted_device_model = apps.get_model('microsys', 'TrustedDevice')
        first_client = Client(HTTP_USER_AGENT='Mozilla/5.0 Chrome/122.0 Linux')
        second_client = Client(HTTP_USER_AGENT='Mozilla/5.0 Firefox/123.0 Windows')
        first_client.login(username='devices', password='devicespass123')
        second_client.login(username='devices', password='devicespass123')
        first_client.get(reverse('user_profile'))
        second_client.get(reverse('user_profile'))
        second_session = second_client.session
        trusted_device = trusted_device_model.objects.create(
            user=self.user,
            token_hash='trusted-revoke-test',
            session_key=second_session.session_key,
            trusted_until=timezone.now() + timedelta(days=30),
        )
        second_session['microsys_device'] = {
            'user_agent': 'Mozilla/5.0 Firefox/123.0 Windows',
            'ip_address': '127.0.0.1',
            'first_seen': timezone.now().isoformat(),
            'last_seen': timezone.now().isoformat(),
            'trusted_device_id': trusted_device.pk,
            'trusted_until': trusted_device.trusted_until.isoformat(),
        }
        second_session.save()

        response = first_client.post(
            reverse('revoke_profile_session', args=[second_session.session_key]),
            {'current_password': 'devicespass123'},
        )

        self.assertRedirects(response, reverse('user_profile'))
        trusted_device.refresh_from_db()
        self.assertIsNotNone(trusted_device.revoked_at)
