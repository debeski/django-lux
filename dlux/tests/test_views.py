from django import forms
from django.apps import apps

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.test import TestCase, Client, RequestFactory, override_settings
from django.test.utils import CaptureQueriesContext
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.contrib.sessions.models import Session
from django.urls import reverse
from django.core.cache import cache
from django.db import connection
from django.contrib.auth.hashers import check_password, identify_hasher, make_password
from django.utils import timezone
from datetime import timedelta
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from dlux.models import Scope, Section, SystemSettings
from dlux.utils import get_user_management_tier_state_for_user

User = get_user_model()


class GeneralViewsTests(TestCase):
    def setUp(self):
        cache.clear()
        from dlux.models import SystemSettings

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
        self.assertContains(response, 'data-dlux-navbar')
        settings_obj.navbar_config['allow_user_mode_override'] = False
        settings_obj.save(update_fields=['navbar_config'])
        response = self.client.get(reverse('options_view'))
        self.assertNotContains(response, 'data-options-card="navbar-mode"')

    def test_options_view_hides_sidebar_density_card_when_sidebar_disabled(self):
        settings_obj = SystemSettings.load()
        settings_obj.sidebar_config = {
            'enabled': False,
            'home_url_name': None,
            'entries': [],
            'enable_reorder': True,
            'show_toolbar': True,
            'show_icons': True,
            'density': 'balanced',
            'allow_user_density': True,
            'collapse_mode': 'icons',
        }
        settings_obj.save(update_fields=['sidebar_config'])

        response = self.client.get(reverse('options_view'))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['sidebar_enabled'])
        self.assertFalse(response.context['sidebar_density_picker_enabled'])
        self.assertNotContains(response, 'data-options-card="sidebar-density"')

    def test_options_email_diagnostics_only_render_when_email_features_enabled(self):
        settings_obj = SystemSettings.load()
        settings_obj.auth_config = {**(settings_obj.auth_config or {}), "email_2fa": False}
        settings_obj.public_registration_enabled = False
        settings_obj.save()

        response = self.client.get(reverse('options_view'))

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context.get('email_service'))
        self.assertNotContains(response, '<th>Email:</th>', html=True)

        settings_obj.auth_config = {**(settings_obj.auth_config or {}), "email_2fa": True}
        settings_obj.save()
        response = self.client.get(reverse('options_view'))

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context.get('email_service'))
        self.assertContains(response, '<th>Email:</th>', html=True)

    def test_email_send_test_requires_superuser_and_post(self):
        # GET is rejected (POST-only).
        self.assertEqual(self.client.get(reverse('email_send_test')).status_code, 405)

        # Non-superuser is forbidden.
        User.objects.create_user(username='staffer', email='s@example.com', password='pw12345678')
        self.client.logout()
        self.client.login(username='staffer', password='pw12345678')
        response = self.client.post(reverse('email_send_test'), {'recipient': 'to@example.com'})
        self.assertEqual(response.status_code, 403)

    def test_email_send_test_validates_recipient_and_configuration(self):
        # Invalid recipient is rejected before any send attempt.
        response = self.client.post(reverse('email_send_test'), {'recipient': 'not-an-email'})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['ok'])

        # Valid recipient but email service not configured -> 409, no send.
        with patch('dlux.views.general.get_email_service_status', return_value={'available': False}):
            with patch('dlux.views.general.send_dlux_mail') as mocked:
                response = self.client.post(reverse('email_send_test'), {'recipient': 'to@example.com'})
        self.assertEqual(response.status_code, 409)
        mocked.assert_not_called()

    def test_email_send_test_sends_when_configured(self):
        with patch('dlux.views.general.get_email_service_status', return_value={'available': True}):
            with patch('dlux.views.general.send_dlux_mail', return_value=1) as mocked:
                response = self.client.post(reverse('email_send_test'), {'recipient': 'to@example.com'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        mocked.assert_called_once()
        # Test sends must not re-enter the failure-alert path.
        self.assertFalse(mocked.call_args.kwargs.get('alert_on_failure', True))

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
        self.assertNotContains(response, 'data-options-card="system-backup"')

    def test_options_view_shows_system_backup_card_for_superuser_only(self):
        SystemBackup = apps.get_model('dlux', 'SystemBackup')
        SystemRestore = apps.get_model('dlux', 'SystemRestore')
        SystemBackup.objects.create(
            requested_by_username='admin',
            status=SystemBackup.STATUS_COMPLETED,
            completed_at=timezone.now(),
            passphrase_required=True,
        )
        SystemRestore.objects.create(
            requested_by_username='admin',
            backup_file_path='dlux_backups/system-example.dlb',
            status=SystemRestore.STATUS_COMPLETED,
            completed_at=timezone.now(),
        )

        response = self.client.get(reverse('options_view'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-options-card="system-backup"')
        self.assertContains(response, reverse('system_backup_page'))
        self.assertEqual(response.context['system_backup_summary']['completed_count'], 1)
        self.assertEqual(response.context['system_backup_summary']['protected_count'], 1)
        self.assertContains(response, 'Last backup')
        self.assertContains(response, 'Passphrase protected')
        self.assertContains(response, 'Last restore')

        regular_user = User.objects.create_user(
            username='backupviewer',
            email='backupviewer@example.com',
            password='viewerpass123'
        )
        self.client.logout()
        self.client.login(username=regular_user.username, password='viewerpass123')
        response = self.client.get(reverse('options_view'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'data-options-card="system-backup"')
        self.assertNotContains(response, reverse('system_backup_page'))

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
        content_type = ContentType.objects.get(app_label='dlux', model='profile')
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
        Profile = apps.get_model('dlux', 'Profile')
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
        self.assertContains(response, 'dlux-system-settings-grid')
        self.assertContains(response, 'dlux-system-settings-tile')
        self.assertContains(response, 'data-dlux-tooltip="System names, logo, favicon, and home route."')

    def test_options_view_uses_shared_selector_markup_for_font_picker(self):
        response = self.client.get(reverse('options_view'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'dlux-font-picker')
        self.assertContains(response, 'dlux-density-options')
        self.assertContains(response, 'data-font="cairo"')
        self.assertContains(response, 'data-font="alexandria"')
        self.assertContains(response, 'dlux/main/js/options.js?v=')
        self.assertNotContains(response, 'dlux-font-preview-card')

    def test_options_view_uses_real_font_family_for_underscore_slug(self):
        settings_obj = SystemSettings.load()
        settings_obj.allowed_fonts = ['cairo', 'readex_pro']
        settings_obj.save(update_fields=['allowed_fonts'])
        cache.clear()
        profile = self.user.profile
        profile.preferences = {'font': 'readex_pro'}
        profile.save(update_fields=['preferences'])

        response = self.client.get(reverse('options_view'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['font_families']['readex_pro'], 'Readex Pro')
        self.assertContains(response, '"readex_pro": "Readex Pro"', html=False)

    def test_system_settings_modal_honors_requested_wizard_step(self):
        response = self.client.get(
            reverse('modal_manager', args=['dlux', 'SystemSettings', 1]) + '?step=4',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertIn('data-dlux-wizard-initial-step="4"', payload['html'])
        self.assertIn('?step=4', payload['html'])
        self.assertIn('dlux-btn-submit', payload['html'])
        self.assertNotIn('dlux-form-action-primary', payload['html'])
        self.assertNotIn('dlux-form-action-neutral', payload['html'])
        self.assertNotIn('dlux-btn-next', payload['html'])
        self.assertNotIn('dlux-btn-prev', payload['html'])

    def test_system_settings_modal_honors_requested_wizard_step_five(self):
        response = self.client.get(
            reverse('modal_manager', args=['dlux', 'SystemSettings', 1]) + '?step=5',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertIn('data-dlux-wizard-initial-step="5"', payload['html'])
        self.assertIn('?step=5', payload['html'])
        self.assertIn('dlux-btn-submit', payload['html'])

    def test_system_settings_modal_honors_requested_wizard_step_six(self):
        response = self.client.get(
            reverse('modal_manager', args=['dlux', 'SystemSettings', 1]) + '?step=6',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertIn('data-dlux-wizard-initial-step="6"', payload['html'])
        self.assertIn('?step=6', payload['html'])
        self.assertIn('dlux-btn-submit', payload['html'])

    def test_system_settings_export_downloads_setup_payload_for_superuser(self):
        settings_obj = SystemSettings.load()
        settings_obj.system_names = {'en': 'Exported System'}
        settings_obj.languages = {'fr': {'name': 'Francais', 'dir': 'ltr', 'flag': 'FR'}}
        settings_obj.default_language = 'fr'
        settings_obj.save()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / 'Client Portal'
            project_root.mkdir()
            with override_settings(BASE_DIR=project_root):
                response = self.client.get(reverse('system_settings_export'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json; charset=utf-8')
        today = timezone.localdate().isoformat()
        self.assertEqual(
            response['Content-Disposition'],
            f'attachment; filename="dlux-client-portal-{today}.json"',
        )
        self.assertNotIn('exported-system', response['Content-Disposition'])
        payload = json.loads(response.content)
        self.assertEqual(payload['format'], 'django-lux.system-settings')
        self.assertEqual(payload['settings']['system_names']['en'], 'Exported System')
        self.assertIn('fr', payload['settings']['languages'])

    def test_export_slug_falls_back_to_english_system_name_then_project(self):
        from dlux.views.general import _resolve_project_export_slug

        settings_obj = SystemSettings.load()
        settings_obj.system_names = {'en': 'My Portal', 'ar': 'بوابتي'}
        settings_obj.save()
        # With no usable BASE_DIR, the configured English system name is used.
        with override_settings(BASE_DIR=''):
            self.assertEqual(_resolve_project_export_slug(settings_obj), 'my-portal')

        # With no name set anywhere, the final 'project' fallback applies.
        settings_obj.system_names = {}
        settings_obj.save()
        with override_settings(BASE_DIR=''):
            self.assertEqual(_resolve_project_export_slug(settings_obj), 'project')

        # DLUX_PROJECT_NAME is no longer consulted.
        with override_settings(BASE_DIR='', DLUX_PROJECT_NAME='Should Be Ignored'):
            self.assertEqual(_resolve_project_export_slug(settings_obj), 'project')

    def test_export_slug_skips_generic_container_dir_names(self):
        from dlux.views.general import _resolve_project_export_slug

        settings_obj = SystemSettings.load()
        settings_obj.system_names = {'en': 'Archive System'}
        settings_obj.save()
        with tempfile.TemporaryDirectory() as tmpdir:
            # A generic Docker WORKDIR-style name (e.g. /app) is skipped so the
            # configured system name is used instead.
            generic_root = Path(tmpdir) / 'app'
            generic_root.mkdir()
            with override_settings(BASE_DIR=generic_root):
                self.assertEqual(_resolve_project_export_slug(settings_obj), 'archive-system')

            # A meaningful directory name still wins over the system name.
            named_root = Path(tmpdir) / 'Archive Portal'
            named_root.mkdir()
            with override_settings(BASE_DIR=named_root):
                self.assertEqual(_resolve_project_export_slug(settings_obj), 'archive-portal')

    def test_system_settings_modal_uses_setup_form_class_for_live_behavior(self):
        response = self.client.get(
            reverse('modal_manager', args=['dlux', 'SystemSettings', 1]) + '?step=1',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertIn('class="dlux-form dlux-system-setup-form"', payload['html'])

    def test_system_settings_modal_post_preserves_step_six_values_when_omitted(self):
        settings_obj = SystemSettings.load()
        settings_obj.allowed_themes = ['dark', 'neon']
        settings_obj.default_theme = 'dark'
        settings_obj.allowed_fonts = ['cairo']
        settings_obj.default_fonts = {'en': 'cairo', 'ar': 'cairo'}
        settings_obj.default_table_density = 'roomy'
        settings_obj.save()

        response = self.client.post(
            reverse('modal_manager', args=['dlux', 'SystemSettings', 1]) + '?step=0',
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
        with patch('dlux.models.UserActivityLog.safe_log') as safe_log, \
             patch('dlux.signals.get_current_user', return_value=self.user), \
             patch('dlux.signals.get_current_request', return_value=fake_request), \
             patch('dlux.session_history.remember_request_presence'):
            response = self.client.post(
                reverse('modal_manager', args=['dlux', 'Scope', 'new']),
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
        with patch('dlux.models.UserActivityLog.safe_log') as safe_log, \
             patch('dlux.signals.get_current_user', return_value=self.user), \
             patch('dlux.signals.get_current_request', return_value=fake_request), \
             patch('dlux.session_history.remember_request_presence'):
            response = self.client.post(
                reverse('modal_delete', args=['dlux', 'Scope', scope.pk]),
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
        """Test that system_setup_view starts with the setup language gate."""
        from dlux.models import SystemSettings
        settings = SystemSettings.load()
        settings.is_configured = False
        settings.save()
        
        response = self.client.get(reverse('system_setup'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="setup_language"')
        self.assertContains(response, 'data-setup-language-start="en"')
        self.assertContains(response, 'data-setup-language-start="ar"')
        self.assertNotContains(response, 'data-dlux-wizard-step-nav')

    def test_system_setup_language_choice_unlocks_localized_wizard(self):
        from dlux.models import SystemSettings
        settings = SystemSettings.load()
        settings.is_configured = False
        settings.save()

        response = self.client.post(reverse('system_setup'), {'setup_language': 'ar'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('system_setup'))

        session = self.client.session
        self.assertEqual(session['dlux_initial_setup_language'], 'ar')
        self.assertEqual(session['lang'], 'ar')

        response = self.client.get(reverse('system_setup'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-dlux-wizard-step-nav')
        self.assertContains(response, 'data-dlux-wizard-step-target="0"')
        self.assertContains(response, 'data-dlux-wizard-step-target="6"')
        self.assertContains(response, 'aria-label="التنقل بين خطوات التهيئة"')
        self.assertContains(response, 'dlux-setup-step-nav__bullet')
        self.assertContains(response, 'data-language-default value="en" checked')
        self.assertContains(response, 'data-language-default value="ar"')
        self.assertNotContains(response, 'data-default-language-locked')
        self.assertNotContains(response, 'disabled aria-disabled="true"')

    def test_system_setup_english_language_choice_unlocks_wizard(self):
        from dlux.models import SystemSettings
        settings = SystemSettings.load()
        settings.is_configured = False
        settings.save()

        response = self.client.post(reverse('system_setup'), {'setup_language': 'en'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('system_setup'))

        session = self.client.session
        self.assertEqual(session['dlux_initial_setup_language'], 'en')
        self.assertEqual(session['lang'], 'en')

        response = self.client.get(reverse('system_setup'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-dlux-wizard-step-nav')
        self.assertNotContains(response, 'name="setup_language"')

    def test_system_setup_redirects_if_configured(self):
        """Test that system_setup redirects if system is already configured."""
        from dlux.models import SystemSettings
        settings = SystemSettings.load()
        settings.is_configured = True
        settings.save()
        
        response = self.client.get(reverse('system_setup'))
        self.assertEqual(response.status_code, 302)  # Redirect

    def test_system_setup_auto_loads_base_dir_config_json_when_unconfigured(self):
        settings_obj = SystemSettings.load()
        settings_obj.is_configured = False
        settings_obj.save()
        with tempfile.TemporaryDirectory() as tmpdir, override_settings(BASE_DIR=Path(tmpdir)):
            config_path = Path(tmpdir) / 'config.json'
            config_path.write_text(json.dumps({
                'format': 'django-lux.system-settings',
                'version': 1,
                'settings': {
                    'system_names': {'en': 'Imported System'},
                    'home_url': '/sys/profile/',
                    'default_language': 'en',
                    'default_theme': 'light',
                    'allowed_themes': ['light'],
                    'allowed_fonts': ['cairo'],
                    'default_fonts': {'en': 'cairo'},
                    'allow_user_font_override': False,
                    'languages': {'en': {'name': 'English', 'dir': 'ltr', 'flag': 'EN'}},
                    'translations_override': {'en': {'custom_key': 'Custom'}},
                    'sidebar_config': {'enabled': False, 'entries': []},
                    'navbar_config': {'enabled': True, 'default_mode': 'history', 'hierarchy': {'nodes': []}},
                    'titlebar_config': {'show_title': False},
                },
            }), encoding='utf-8')

            response = self.client.get(reverse('system_setup'))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/sys/profile/')
        settings_obj.refresh_from_db()
        self.assertTrue(settings_obj.is_configured)
        self.assertEqual(settings_obj.system_names['en'], 'Imported System')
        self.assertEqual(settings_obj.allowed_fonts, ['cairo'])
        self.assertEqual(settings_obj.default_fonts, {'en': 'cairo'})
        self.assertFalse(settings_obj.allow_user_font_override)
        self.assertTrue(settings_obj.navbar_config['enabled'])
        self.assertFalse(settings_obj.titlebar_config['show_title'])

    def test_system_setup_ignores_invalid_config_json_and_renders_language_gate(self):
        settings_obj = SystemSettings.load()
        settings_obj.is_configured = False
        settings_obj.save()
        with tempfile.TemporaryDirectory() as tmpdir, override_settings(BASE_DIR=Path(tmpdir)):
            (Path(tmpdir) / 'config.json').write_text('{not valid json', encoding='utf-8')

            response = self.client.get(reverse('system_setup'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="setup_language"')
        settings_obj.refresh_from_db()
        self.assertFalse(settings_obj.is_configured)

    def test_system_setup_ignores_config_json_after_system_is_configured(self):
        settings_obj = SystemSettings.load()
        settings_obj.is_configured = True
        settings_obj.system_names = {'en': 'Existing'}
        settings_obj.save()
        with tempfile.TemporaryDirectory() as tmpdir, override_settings(BASE_DIR=Path(tmpdir)):
            (Path(tmpdir) / 'config.json').write_text(json.dumps({
                'system_names': {'en': 'Imported'},
                'home_url': '/sys/profile/',
            }), encoding='utf-8')

            response = self.client.get(reverse('system_setup'))

        self.assertEqual(response.status_code, 302)
        settings_obj.refresh_from_db()
        self.assertEqual(settings_obj.system_names['en'], 'Existing')


class ProfileViewsTests(TestCase):
    def setUp(self):
        cache.clear()
        settings_obj = SystemSettings.load()
        settings_obj.is_configured = True
        settings_obj.auth_config = {**(settings_obj.auth_config or {}), "email_2fa": True}
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

    def test_user_profile_rejects_password_change_to_current_password(self):
        original_password_hash = self.user.password
        response = self.client.post(reverse('user_profile'), {
            'old_password': 'testpass123',
            'new_password1': 'testpass123',
            'new_password2': 'testpass123',
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['password_form'].errors.as_data()['new_password2'][0].code, 'password_unchanged')
        self.assertContains(response, 'id="resetPasswordModal"')
        self.assertContains(response, 'data-dlux-open-on-load="true"')
        self.assertEqual(response.context.get('dlux_flash_notifications'), [])
        self.user.refresh_from_db()
        self.assertEqual(self.user.password, original_password_hash)
        self.assertTrue(self.user.check_password('testpass123'))

    def test_user_profile_stats_calculation(self):
        """Test that profile stats are calculated correctly."""
        from dlux.models import UserActivityLog
        # Use a model_name that does not collide with any registered model. Report
        # eligibility (filter_report_eligible_activity) falls through to "include"
        # only when the name resolves to no real model; the bare `TestModel`
        # registered by test_signals would otherwise resolve to an ineligible
        # dlux-app model and drop this row to 0 once that module is imported
        # (full-suite ordering), even though the test passes in isolation.
        UserActivityLog.objects.create(
            created_by=self.user,
            action='CREATE',
            model_name='ProfileStatsFixtureModel'
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
        from dlux.models import UserActivityLog

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

    def test_user_profile_routes_operational_labels_to_system_interactions(self):
        from dlux.models import UserActivityLog

        # Operational tracking noise (presence/device churn) must not appear in
        # either feed — it is excluded entirely (see reports.exclude_log_noise).
        presence_log = UserActivityLog.objects.create(
            created_by=self.user,
            action='UPDATE',
            model_name='Presence Session',
        )
        # A kept operational event (login) still routes to System Interactions.
        auth_log = UserActivityLog.objects.create(
            created_by=self.user,
            action='LOGIN',
            model_name='Mounted App Entry',
        )
        project_log = UserActivityLog.objects.create(
            created_by=self.user,
            action='CREATE',
            model_name='Mounted App Entry',
        )

        response = self.client.get(reverse('user_profile'))

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(presence_log, response.context['system_interactions'])
        self.assertNotIn(presence_log, response.context['recent_activity'])
        self.assertIn(auth_log, response.context['system_interactions'])
        self.assertNotIn(auth_log, response.context['recent_activity'])
        self.assertIn(project_log, response.context['recent_activity'])

    def test_user_profile_keeps_report_eligible_dlux_activity_recent(self):
        from dlux.models import UserActivityLog

        section_log = UserActivityLog.objects.create(
            created_by=self.user,
            action='CREATE',
            model_name='Dlux Section Entry',
        )
        system_log = UserActivityLog.objects.create(
            created_by=self.user,
            action='UPDATE',
            model_name='System Settings',
        )

        def eligible_model_names(model_name):
            return model_name == 'Dlux Section Entry'

        with patch('dlux.views.profile.is_report_eligible_activity_model_name', side_effect=eligible_model_names):
            response = self.client.get(reverse('user_profile'))

        self.assertEqual(response.status_code, 200)
        self.assertIn(section_log, response.context['recent_activity'])
        self.assertNotIn(section_log, response.context['system_interactions'])
        self.assertIn(system_log, response.context['system_interactions'])

    def test_user_profile_limits_activity_feeds_to_latest_five_each(self):
        from dlux.models import UserActivityLog

        base_time = timezone.now() - timedelta(hours=1)
        recent_logs = []
        system_logs = []
        for index in range(8):
            recent_log = UserActivityLog.objects.create(
                created_by=self.user,
                action='CREATE',
                model_name='Mounted App Entry',
            )
            system_log = UserActivityLog.objects.create(
                created_by=self.user,
                action='LOGIN',
                model_name='Mounted App Entry',
            )
            UserActivityLog.objects.filter(pk=recent_log.pk).update(created_at=base_time + timedelta(minutes=index))
            UserActivityLog.objects.filter(pk=system_log.pk).update(created_at=base_time + timedelta(minutes=index, seconds=30))
            recent_logs.append(recent_log.pk)
            system_logs.append(system_log.pk)

        response = self.client.get(reverse('user_profile'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual([log.pk for log in response.context['recent_activity']], list(reversed(recent_logs[-5:])))
        self.assertEqual([log.pk for log in response.context['system_interactions']], list(reversed(system_logs[-5:])))


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
        from dlux.models import ScopeSettings
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
            apps.get_model('dlux', 'ActivityLog'),
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
        from dlux.models import UserActivityLog
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
        from dlux.models import UserActivityLog

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
        from dlux.models import UserActivityLog

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
        from dlux.models import UserActivityLog

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
        total = response.context['table'].paginator.count
        self.assertEqual(len(response.context['table'].page.object_list), total - 10)

    def test_activity_log_queryset_prefetches_table_accessor_relations(self):
        from dlux.models import UserActivityLog
        from dlux.views.activitylog import UserActivityLogView

        scope = Scope.objects.create(name='Log Scope')
        self.user.profile.scope = scope
        self.user.profile.save(update_fields=['scope'])
        for index in range(8):
            UserActivityLog.objects.create(
                created_by=self.user,
                action='CREATE',
                model_name=f'Entry {index}',
            )

        request = RequestFactory().get(reverse('user_activity_log'))
        request.user = self.user
        view = UserActivityLogView()
        view.request = request
        view.args = ()
        view.kwargs = {}

        with CaptureQueriesContext(connection) as captured:
            logs = list(view.get_queryset())
            for log in logs:
                if log.created_by and getattr(log.created_by, 'profile', None):
                    scope = getattr(log.created_by.profile, 'scope', None)
                    if scope:
                        _ = scope.name

        self.assertLessEqual(len(captured), 6)

    def test_activity_log_detail_view_renders_structured_changes_and_masks_totp_secret(self):
        from dlux.models import UserActivityLog

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
        self.assertContains(response, 'dlux-log-detail-panel')
        self.assertContains(response, 'dlux-log-detail-item')
        self.assertContains(response, 'dlux-log-detail-status is-changed')
        self.assertContains(response, '********')
        self.assertNotContains(response, 'RAWOLDSECRET')
        self.assertNotContains(response, 'RAWNEWSECRET')

    def test_activity_log_detail_view_hides_superuser_logs_from_non_superuser_staff(self):
        from dlux.models import UserActivityLog

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
        from dlux.models import UserActivityLog

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
        self.assertIn('dlux-btn-prev d-none', payload['html'])
        self.assertIn('dlux-btn-next', payload['html'])
        self.assertIn('dlux-btn-submit d-none', payload['html'])
        self.assertIn('name="force_password_change"', payload['html'])

    def test_user_create_modal_can_require_first_login_password_change(self):
        self.client.login(username='root', password='rootpass123')

        response = self.client.post(
            reverse('modal_user'),
            {
                'username': 'mustchange',
                'password1': 'Initialpass123!',
                'password2': 'Initialpass123!',
                'first_name': 'Must',
                'last_name': 'Change',
                'email': 'mustchange@example.com',
                'is_active': 'on',
                'force_password_change': 'on',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(json.loads(response.content)['success'])
        user = User.objects.get(username='mustchange')
        self.assertTrue(user.profile.preferences.get('force_password_change'))

    def test_forced_password_change_redirects_until_profile_password_update(self):
        forced_user = User.objects.create_user(
            username='forceduser',
            email='forced@example.com',
            password='Initialpass123!',
        )
        forced_user.profile.preferences = {'force_password_change': True}
        forced_user.profile.save(update_fields=['preferences'])
        self.client.login(username='forceduser', password='Initialpass123!')

        blocked = self.client.get(reverse('manage_users'))
        self.assertEqual(blocked.status_code, 302)
        self.assertTrue(blocked['Location'].endswith(f"{reverse('user_profile')}?force_password_change=1"))

        profile_response = self.client.get(reverse('user_profile'))
        self.assertEqual(profile_response.status_code, 200)
        self.assertTrue(profile_response.context['force_password_change_required'])

        changed = self.client.post(
            reverse('user_profile'),
            {
                'old_password': 'Initialpass123!',
                'new_password1': 'Changedpass123!',
                'new_password2': 'Changedpass123!',
            },
        )

        self.assertEqual(changed.status_code, 302)
        forced_user.profile.refresh_from_db()
        self.assertNotIn('force_password_change', forced_user.profile.preferences)

        after_change = self.client.get(reverse('manage_users'))
        self.assertFalse(
            after_change.status_code == 302
            and after_change['Location'].endswith(f"{reverse('user_profile')}?force_password_change=1")
        )

    def test_forced_password_change_rejects_current_password_reuse(self):
        forced_user = User.objects.create_user(
            username='forcedsame',
            email='forcedsame@example.com',
            password='Initialpass123!',
        )
        original_password_hash = forced_user.password
        forced_user.profile.preferences = {'force_password_change': True}
        forced_user.profile.save(update_fields=['preferences'])
        self.client.login(username='forcedsame', password='Initialpass123!')

        response = self.client.post(
            reverse('user_profile'),
            {
                'old_password': 'Initialpass123!',
                'new_password1': 'Initialpass123!',
                'new_password2': 'Initialpass123!',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['password_form'].errors.as_data()['new_password2'][0].code, 'password_unchanged')
        forced_user.refresh_from_db()
        self.assertEqual(forced_user.password, original_password_hash)
        forced_user.profile.refresh_from_db()
        self.assertTrue(forced_user.profile.preferences.get('force_password_change'))

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

    def test_manage_users_queryset_prefetches_table_accessor_relations(self):
        from dlux.models import PublicRegistration
        from dlux.views.users import UserListView

        self._grant_user_permission(self.staff_user, 'view_user')
        manage_staff = Permission.objects.get(
            content_type=ContentType.objects.get(app_label='dlux', model='profile'),
            codename='manage_staff',
        )
        group = Group.objects.create(name='Scoped Delegators')
        group.permissions.add(manage_staff)

        for index in range(8):
            user = User.objects.create_user(
                username=f'perf-scope-{index}',
                email=f'perf-scope-{index}@example.com',
                password='scopepass123',
                is_staff=index % 2 == 0,
            )
            user.profile.scope = self.scope_a
            user.profile.phone = f'555-010{index}'
            user.profile.save(update_fields=['scope', 'phone'])
            if index % 2 == 0:
                user.groups.add(group)
            if index == 0:
                PublicRegistration.objects.create(
                    user=user,
                    email=user.email,
                    expires_at=timezone.now() + timedelta(days=1),
                )

        request = RequestFactory().get(reverse('manage_users'))
        request.user = self.staff_user
        view = UserListView()
        view.request = request
        view.args = ()
        view.kwargs = {}

        users = list(view.get_queryset())
        with CaptureQueriesContext(connection) as captured:
            for user in users:
                _ = user.profile.phone
                if user.profile.scope:
                    _ = user.profile.scope.name
                try:
                    _ = user.public_registration
                except PublicRegistration.DoesNotExist:
                    pass
                get_user_management_tier_state_for_user(user, strings={'_': '_'})

        self.assertEqual(len(captured), 0)

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
        content_type = ContentType.objects.get(app_label='dlux', model='profile')
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
        from dlux.models import UserActivityLog

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
        profile_type = ContentType.objects.get(app_label='dlux', model='profile')
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
        self.assertContains(response, 'dlux-staff-tier-badge--global_staff')

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

    def test_reset_password_rejects_current_password_reuse(self):
        self.client.login(username='root', password='rootpass123')
        original_password_hash = self.regular_user.password

        response = self.client.post(
            reverse('reset_password', args=[self.regular_user.pk]),
            {
                'reset_password-new_password1': 'regularpass123',
                'reset_password-new_password2': 'regularpass123',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.regular_user.refresh_from_db()
        self.assertEqual(self.regular_user.password, original_password_hash)
        self.assertTrue(self.regular_user.check_password('regularpass123'))

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

        with patch('dlux.views.sections._resolve_allowed_subsection_definition', return_value=allowed_subsection), \
             patch('dlux.views.sections.resolve_form_class_for_model', return_value=RejectingScopeForm), \
             patch('dlux.views.sections._create_minimal_instance_from_post', side_effect=AssertionError('fallback should not run')):
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

        with patch('dlux.views.sections._resolve_allowed_section_definition', return_value=allowed_section), \
             patch('dlux.views.sections.collect_related_objects', side_effect=RuntimeError('sensitive traceback marker')):
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

        with patch('dlux.views.twofa.pyotp', fake_pyotp), \
             patch('dlux.views.twofa.qrcode', fake_qrcode), \
             patch('dlux.views.twofa.get_system_config', return_value={
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

        from dlux.utils import decrypt_totp_secret, is_encrypted_totp_secret
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

        with patch('dlux.views.twofa.pyotp', fake_pyotp), \
             patch('dlux.views.twofa.qrcode'), \
             patch('dlux.views.twofa.set_profile_totp_state', side_effect=DatabaseError('too long')):
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

        with patch('dlux.views.twofa.pyotp', fake_pyotp), \
             patch('dlux.views.twofa.qrcode'), \
             patch('dlux.views.twofa.set_profile_totp_state', side_effect=RuntimeError('missing crypto backend')):
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

        with patch('dlux.views.twofa.pyotp', fake_pyotp), \
             patch('dlux.views.twofa.qrcode', SimpleNamespace(make=lambda uri: None)):
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
        with patch('dlux.views.twofa.pyotp', fake_pyotp):
            response = self.client.post(
                reverse('verify_otp_login'),
                {'otp_code': '654321', 'method': 'totp'},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(captured['secret'], 'JBSWY3DPEHPK3PXP')

    def test_two_factor_verify_is_ip_rate_limited(self):
        self._prime_pre_2fa_session()
        cache.set('dlux:2fa:verify:ip:127.0.0.1:login', 20, timeout=600)

        response = self.client.post(
            reverse('verify_otp_login'),
            {'otp_code': '000000'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 429)
        payload = json.loads(response.content)
        self.assertEqual(payload['status'], 'error')

    def test_two_factor_email_send_is_ip_rate_limited(self):
        cache.set('dlux:2fa:send:ip:127.0.0.1:login', 10, timeout=3600)
        self._prime_pre_2fa_session()

        with patch('dlux.views.twofa.send_dlux_mail', return_value=1) as mocked_mail:
            response = self.client.post(
                reverse('resend_otp_login'),
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            )

        self.assertEqual(response.status_code, 400)
        mocked_mail.assert_not_called()

    def test_send_otp_no_longer_prints_live_codes(self):
        with patch('dlux.views.twofa.send_dlux_mail', return_value=1), \
             patch('builtins.print') as mocked_print:
            from dlux.views.twofa import send_otp

            self.assertTrue(send_otp(None, self.user, intent='login'))

        mocked_print.assert_not_called()

    def test_email_otp_is_stored_hashed_in_cache(self):
        captured = {}

        def fake_send_dlux_mail(subject, body, recipients, fail_silently=False):
            captured['body'] = body
            return 1

        with patch('dlux.views.twofa.send_dlux_mail', side_effect=fake_send_dlux_mail), \
             patch('dlux.views.twofa._generate_email_otp_code', return_value='123456'):
            from dlux.views.twofa import send_otp

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

        def fake_send_dlux_mail(subject, body, recipients, fail_silently=False):
            captured['recipients'] = recipients
            return 1

        with patch('dlux.views.twofa.send_dlux_mail', side_effect=fake_send_dlux_mail), \
             patch('dlux.views.twofa._generate_email_otp_code', return_value='123456'):
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

        with patch('dlux.views.twofa.send_dlux_mail', return_value=1) as mocked_mail:
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

        with patch('dlux.views.twofa.send_dlux_mail', return_value=1) as mocked_mail, \
             patch('dlux.views.twofa._generate_email_otp_code', return_value='123456'):
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
        from dlux.models import SystemSettings

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

        with patch('dlux.views.twofa.send_dlux_mail', return_value=1) as mocked_mail:
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

        with patch('dlux.views.twofa.send_dlux_mail', return_value=1) as mocked_mail:
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

        with patch('dlux.views.twofa._generate_email_otp_code', return_value='123456'), \
             patch('dlux.views.twofa.send_dlux_mail', return_value=1):
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
        with patch('dlux.views.twofa.send_dlux_mail', return_value=1) as mocked_mail:
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
        trusted_device_model = apps.get_model('dlux', 'TrustedDevice')
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

        trusted_cookie = verify_response.cookies.get('dlux_trusted_device')
        bypass_client = Client(HTTP_USER_AGENT='Mozilla/5.0 Chrome/122.0 Linux')
        bypass_client.cookies['dlux_trusted_device'] = trusted_cookie.value

        with patch('dlux.views.twofa.send_dlux_mail', return_value=1) as mocked_mail:
            response = bypass_client.post(reverse('login'), {
                'username': 'twofa',
                'password': 'twofapass123',
            })

        self.assertEqual(response.status_code, 302)
        self.assertNotEqual(response.url, reverse('verify_otp_login'))
        mocked_mail.assert_not_called()
        trusted_device = trusted_device_model.objects.get(user=self.user)
        self.assertTrue(trusted_device.session_key)

    def test_trusted_two_factor_login_evicts_other_sessions_when_enabled(self):
        settings_obj = SystemSettings.load()
        settings_obj.auth_config = {**(settings_obj.auth_config or {}), "prevent_multiple_active_sessions": True}
        settings_obj.is_configured = True
        settings_obj.save()
        other_client = Client(HTTP_USER_AGENT='Mozilla/5.0 Firefox/123.0 Windows')
        other_client.login(username='twofa', password='twofapass123')
        other_session_key = other_client.session.session_key
        cache.set(
            f'otp_{self.user.pk}_login',
            {'code_hash': make_password('123456'), 'attempts': 0},
            timeout=300,
        )
        self._prime_pre_2fa_session()

        response = self.client.post(
            reverse('verify_otp_login'),
            {'otp_code': '123456', 'method': 'email', 'trust_device': '1'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Session.objects.filter(session_key=other_session_key).exists())


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

    def _mark_session_trusted(self, client, token_hash):
        trusted_device_model = apps.get_model('dlux', 'TrustedDevice')
        session = client.session
        trusted_device = trusted_device_model.objects.create(
            user=self.user,
            token_hash=token_hash,
            session_key=session.session_key,
            trusted_until=timezone.now() + timedelta(days=30),
        )
        session['dlux_device'] = {
            'user_agent': client.defaults.get('HTTP_USER_AGENT', ''),
            'ip_address': '127.0.0.1',
            'first_seen': timezone.now().isoformat(),
            'last_seen': timezone.now().isoformat(),
            'trusted_device_id': trusted_device.pk,
            'trusted_until': trusted_device.trusted_until.isoformat(),
        }
        session.save()
        return trusted_device

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
        from dlux.views.profile import _profile_sessions_for_user

        sessions = _profile_sessions_for_user(
            self.user,
            current_session_key='missing-session-row',
            current_session_data={
                'dlux_device': {
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
        trusted_device_model = apps.get_model('dlux', 'TrustedDevice')
        client = Client(HTTP_USER_AGENT='Mozilla/5.0 Chrome/122.0 Linux')
        client.login(username='devices', password='devicespass123')
        session = client.session
        trusted_device = trusted_device_model.objects.create(
            user=self.user,
            token_hash='test-trusted-device',
            session_key=session.session_key,
            trusted_until=timezone.now() + timedelta(days=30),
        )
        session['dlux_device'] = {
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
        trusted_device_model = apps.get_model('dlux', 'TrustedDevice')
        first_client = Client(HTTP_USER_AGENT='Mozilla/5.0 Chrome/122.0 Linux')
        second_client = Client(HTTP_USER_AGENT='Mozilla/5.0 Firefox/123.0 Windows')
        first_client.login(username='devices', password='devicespass123')
        second_client.login(username='devices', password='devicespass123')
        first_client.get(reverse('user_profile'))
        second_client.get(reverse('user_profile'))
        self._mark_session_trusted(first_client, 'trusted-revoke-actor')
        second_session = second_client.session
        trusted_device = trusted_device_model.objects.create(
            user=self.user,
            token_hash='trusted-revoke-test',
            session_key=second_session.session_key,
            trusted_until=timezone.now() + timedelta(days=30),
        )
        second_session['dlux_device'] = {
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

    def test_profile_trust_current_device_creates_trusted_device(self):
        client = Client(HTTP_USER_AGENT='Mozilla/5.0 Chrome/122.0 Linux')
        client.login(username='devices', password='devicespass123')

        response = client.post(
            reverse('trust_current_device'),
            {'current_password': 'devicespass123'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('dlux_trusted_device', response.cookies)
        trusted_device_model = apps.get_model('dlux', 'TrustedDevice')
        trusted_device = trusted_device_model.objects.get(user=self.user, revoked_at__isnull=True)
        self.assertEqual(trusted_device.session_key, client.session.session_key)

    def test_profile_trust_current_device_evicts_other_sessions_when_enabled(self):
        settings_obj = SystemSettings.load()
        settings_obj.auth_config = {**(settings_obj.auth_config or {}), "prevent_multiple_active_sessions": True}
        settings_obj.save()
        first_client = Client(HTTP_USER_AGENT='Mozilla/5.0 Chrome/122.0 Linux')
        second_client = Client(HTTP_USER_AGENT='Mozilla/5.0 Firefox/123.0 Windows')
        first_client.login(username='devices', password='devicespass123')
        second_client.login(username='devices', password='devicespass123')
        second_session_key = second_client.session.session_key

        response = first_client.post(
            reverse('trust_current_device'),
            {'current_password': 'devicespass123'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Session.objects.filter(session_key=second_session_key).exists())

    def test_untrusted_session_cannot_revoke_trusted_session(self):
        first_client = Client(HTTP_USER_AGENT='Mozilla/5.0 Chrome/122.0 Linux')
        second_client = Client(HTTP_USER_AGENT='Mozilla/5.0 Firefox/123.0 Windows')
        first_client.login(username='devices', password='devicespass123')
        second_client.login(username='devices', password='devicespass123')
        trusted_device = self._mark_session_trusted(second_client, 'trusted-protected-target')
        target_session_key = second_client.session.session_key

        response = first_client.post(
            reverse('revoke_profile_session', args=[target_session_key]),
            {'current_password': 'devicespass123'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Session.objects.filter(session_key=target_session_key).exists())
        trusted_device.refresh_from_db()
        self.assertIsNone(trusted_device.revoked_at)

    def test_trusted_session_can_revoke_trusted_session(self):
        first_client = Client(HTTP_USER_AGENT='Mozilla/5.0 Chrome/122.0 Linux')
        second_client = Client(HTTP_USER_AGENT='Mozilla/5.0 Firefox/123.0 Windows')
        first_client.login(username='devices', password='devicespass123')
        second_client.login(username='devices', password='devicespass123')
        self._mark_session_trusted(first_client, 'trusted-current-session')
        trusted_device = self._mark_session_trusted(second_client, 'trusted-target-session')
        target_session_key = second_client.session.session_key

        response = first_client.post(
            reverse('revoke_profile_session', args=[target_session_key]),
            {'current_password': 'devicespass123'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Session.objects.filter(session_key=target_session_key).exists())
        trusted_device.refresh_from_db()
        self.assertIsNotNone(trusted_device.revoked_at)

    def test_standard_login_evicts_other_sessions_when_single_session_enabled(self):
        settings_obj = SystemSettings.load()
        settings_obj.auth_config = {**(settings_obj.auth_config or {}), "prevent_multiple_active_sessions": True}
        settings_obj.save()
        first_client = Client(HTTP_USER_AGENT='Mozilla/5.0 Chrome/122.0 Linux')
        second_client = Client(HTTP_USER_AGENT='Mozilla/5.0 Firefox/123.0 Windows')
        first_client.login(username='devices', password='devicespass123')
        first_session_key = first_client.session.session_key
        trusted_device = self._mark_session_trusted(first_client, 'trusted-session-evicted-on-new-login')

        response = second_client.post(reverse('login'), {
            'username': 'devices',
            'password': 'devicespass123',
        })

        self.assertEqual(response.status_code, 302)
        # The newest login becomes the only active session; the older one is evicted...
        self.assertFalse(Session.objects.filter(session_key=first_session_key).exists())
        self.assertTrue(Session.objects.filter(session_key=second_client.session.session_key).exists())
        # ...but the evicted device keeps its trusted-device record (trust != session).
        trusted_device.refresh_from_db()
        self.assertIsNone(trusted_device.revoked_at)

    @override_settings(SESSION_ENGINE='django.contrib.sessions.backends.cache')
    def test_standard_login_evicts_cache_backed_sessions_when_single_session_enabled(self):
        from django.conf import settings

        cache.clear()
        settings_obj = SystemSettings.load()
        settings_obj.auth_config = {**(settings_obj.auth_config or {}), "prevent_multiple_active_sessions": True}
        settings_obj.is_configured = True
        settings_obj.save()
        first_client = Client(HTTP_USER_AGENT='Mozilla/5.0 Chrome/122.0 Linux')
        second_client = Client(HTTP_USER_AGENT='Mozilla/5.0 Firefox/123.0 Windows')

        first_response = first_client.post(reverse('login'), {
            'username': 'devices',
            'password': 'devicespass123',
        })
        self.assertEqual(first_response.status_code, 302)
        first_session_key = first_client.cookies[settings.SESSION_COOKIE_NAME].value
        PresenceSession = apps.get_model('dlux', 'UserPresenceSession')
        self.assertTrue(PresenceSession.objects.filter(user=self.user, session_key=first_session_key).exists())

        second_response = second_client.post(reverse('login'), {
            'username': 'devices',
            'password': 'devicespass123',
        })
        self.assertEqual(second_response.status_code, 302)

        bounced = first_client.get(reverse('user_profile'))
        self.assertEqual(bounced.status_code, 302)
        self.assertIn(reverse('session_ended'), bounced.url)

    def test_standard_login_keeps_other_sessions_when_single_session_disabled(self):
        settings_obj = SystemSettings.load()
        settings_obj.auth_config = {**(settings_obj.auth_config or {}), "prevent_multiple_active_sessions": False}
        settings_obj.save()
        first_client = Client(HTTP_USER_AGENT='Mozilla/5.0 Chrome/122.0 Linux')
        second_client = Client(HTTP_USER_AGENT='Mozilla/5.0 Firefox/123.0 Windows')
        first_client.login(username='devices', password='devicespass123')
        first_session_key = first_client.session.session_key

        response = second_client.post(reverse('login'), {
            'username': 'devices',
            'password': 'devicespass123',
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Session.objects.filter(session_key=first_session_key).exists())

    def test_single_session_enforcement_no_op_without_current_session_key(self):
        from types import SimpleNamespace
        from dlux.trust import enforce_single_active_session
        settings_obj = SystemSettings.load()
        settings_obj.auth_config = {**(settings_obj.auth_config or {}), "prevent_multiple_active_sessions": True}
        settings_obj.save()
        other = Client(HTTP_USER_AGENT='Mozilla/5.0 Chrome/122.0 Linux')
        other.login(username='devices', password='devicespass123')
        other_key = other.session.session_key
        # A request with no resolvable current session key must evict nothing — otherwise
        # it would delete every session for the user, including the live one.
        fake_request = SimpleNamespace(session=SimpleNamespace(session_key=None))
        self.assertEqual(enforce_single_active_session(fake_request, self.user), 0)
        self.assertTrue(Session.objects.filter(session_key=other_key).exists())

    def test_evicted_device_is_redirected_to_signed_out_interstitial(self):
        from django.core.cache import cache
        cache.clear()
        settings_obj = SystemSettings.load()
        settings_obj.auth_config = {**(settings_obj.auth_config or {}), "prevent_multiple_active_sessions": True}
        settings_obj.is_configured = True
        settings_obj.save()
        first_client = Client(HTTP_USER_AGENT='Mozilla/5.0 Chrome/122.0 Linux')
        second_client = Client(HTTP_USER_AGENT='Mozilla/5.0 Firefox/123.0 Windows')
        first_client.login(username='devices', password='devicespass123')
        first_session_key = first_client.session.session_key

        second_client.post(reverse('login'), {'username': 'devices', 'password': 'devicespass123'})
        self.assertFalse(Session.objects.filter(session_key=first_session_key).exists())

        # The evicted device's next page load is intercepted and pointed at the interstitial.
        from dlux.session_history import get_session_revoked_reason
        bounced = first_client.get(reverse('user_profile'))
        self.assertEqual(bounced.status_code, 302)
        self.assertIn(reverse('session_ended'), bounced.url)
        # Detection is one-shot — the flag is consumed so the interstitial can't recur.
        self.assertIsNone(get_session_revoked_reason(first_session_key))

        # The interstitial itself renders for the (now anonymous) browser.
        ended = self.client.get(reverse('session_ended'), {'reason': 'signed_in_elsewhere'})
        self.assertEqual(ended.status_code, 200)
        self.assertContains(ended, 'Signed out')

    def test_presence_history_uses_device_cookie_across_ip_changes(self):
        client = Client(HTTP_USER_AGENT='Mozilla/5.0 Chrome/122.0 Linux')
        client.login(username='devices', password='devicespass123')

        response = client.get(
            reverse('user_profile'),
            HTTP_X_FORWARDED_FOR='203.0.113.5, 127.0.0.1',
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('dlux_device_id', response.cookies)
        KnownDevice = apps.get_model('dlux', 'UserKnownDevice')
        PresenceSession = apps.get_model('dlux', 'UserPresenceSession')
        known_device = KnownDevice.objects.get(user=self.user)
        self.assertIn('203.0.113.5', known_device.ip_addresses)

        session = client.session
        metadata = session.get('dlux_device')
        metadata['last_seen'] = (timezone.now() - timedelta(minutes=2)).isoformat()
        session['dlux_device'] = metadata
        session.save()
        presence = PresenceSession.objects.get(user=self.user)
        presence.last_seen_at = timezone.now() - timedelta(minutes=2)
        presence.save(update_fields=['last_seen_at'])

        response = client.get(
            reverse('user_profile'),
            HTTP_X_FORWARDED_FOR='198.51.100.9, 127.0.0.1',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(KnownDevice.objects.filter(user=self.user).count(), 1)
        known_device.refresh_from_db()
        self.assertIn('198.51.100.9', known_device.ip_addresses)
        presence.refresh_from_db()
        self.assertGreater(presence.estimated_seconds, 0)

    def test_revoke_session_marks_presence_session_revoked(self):
        first_client = Client(HTTP_USER_AGENT='Mozilla/5.0 Chrome/122.0 Linux')
        second_client = Client(HTTP_USER_AGENT='Mozilla/5.0 Firefox/123.0 Windows')
        first_client.login(username='devices', password='devicespass123')
        second_client.login(username='devices', password='devicespass123')
        first_client.get(reverse('user_profile'))
        second_client.get(reverse('user_profile'))
        second_session_key = second_client.session.session_key
        PresenceSession = apps.get_model('dlux', 'UserPresenceSession')
        presence = PresenceSession.objects.get(user=self.user, session_key_hash__isnull=False, device_label__contains='Firefox')

        response = first_client.post(
            reverse('revoke_profile_session', args=[second_session_key]),
            {'current_password': 'devicespass123'},
        )

        self.assertRedirects(response, reverse('user_profile'))
        presence.refresh_from_db()
        self.assertIsNotNone(presence.ended_at)
        self.assertIsNotNone(presence.revoked_at)

    def test_user_report_modal_and_xlsx_require_report_permission(self):
        ActivityLog = apps.get_model('dlux', 'ActivityLog')
        ActivityLog.objects.create(
            created_by=self.user,
            action='VIEW',
            model_name='session',
            ip_address='203.0.113.10',
            user_agent='Mozilla/5.0 Chrome/122.0 Linux',
        )
        for index in range(10):
            ActivityLog.objects.create(
                created_by=self.user,
                action='UPDATE',
                model_name=f'report-model-{index}',
                ip_address='203.0.113.10',
                user_agent='Mozilla/5.0 Chrome/122.0 Linux',
            )
        other_user = User.objects.create_user(
            username='report-denied',
            email='report-denied@example.com',
            password='deniedpass123',
        )
        denied_client = Client()
        denied_client.login(username='report-denied', password='deniedpass123')

        denied = denied_client.get(reverse('user_report_modal', args=[self.user.pk]))
        self.assertEqual(denied.status_code, 403)

        admin = User.objects.create_superuser(
            username='report-admin',
            email='report-admin@example.com',
            password='reportpass123',
        )
        admin_client = Client()
        admin_client.login(username='report-admin', password='reportpass123')
        response = admin_client.get(
            reverse('user_report_modal', args=[self.user.pk]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertIn('User Report', payload['html'])
        self.assertIn('data-dlux-user-report-activity', payload['html'])
        self.assertIn('data-dlux-user-report-activity-item', payload['html'])
        self.assertIn('data-dlux-user-report-activity-pagination', payload['html'])
        self.assertIn('dlux-user-report-badge', payload['html'])
        self.assertNotIn('bg-secondary-subtle text-secondary', payload['html'])
        self.assertNotIn('session_key_hash', payload['html'])

        xlsx = admin_client.get(reverse('user_report_xlsx', args=[self.user.pk]))
        self.assertEqual(xlsx.status_code, 200)
        self.assertEqual(
            xlsx['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        self.assertGreater(len(xlsx.content), 1000)

    def test_user_report_filters_operational_activity_and_exports_selected_window(self):
        from dlux.user_reports import build_user_report

        ActivityLog = apps.get_model('dlux', 'ActivityLog')
        project_log = ActivityLog.objects.create(
            created_by=self.user,
            action='CREATE',
            model_name='Project Entry',
        )
        old_project_log = ActivityLog.objects.create(
            created_by=self.user,
            action='CREATE',
            model_name='Project Entry',
        )
        ActivityLog.all_objects.filter(pk=old_project_log.pk).update(
            created_at=timezone.now() - timedelta(days=40)
        )
        ActivityLog.objects.create(
            created_by=self.user,
            action='LOGIN',
            model_name='auth',
        )
        ActivityLog.objects.create(
            created_by=self.user,
            action='UPDATE',
            model_name='System Settings',
        )

        admin = User.objects.create_superuser(
            username='report-filter-admin',
            email='report-filter-admin@example.com',
            password='reportpass123',
        )
        admin_client = Client()
        admin_client.login(username='report-filter-admin', password='reportpass123')

        response = admin_client.get(
            reverse('user_report_modal', args=[self.user.pk]),
            {'window': 'all'},
        )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertIn('Project Entry', payload['html'])
        self.assertNotIn('System Settings', payload['html'])
        self.assertNotIn('auth', payload['html'])
        self.assertIn('data-dlux-user-report-window="all"', payload['html'])
        self.assertIn('data-dlux-user-report-total-actions>2</strong>', payload['html'])

        week_report = build_user_report(self.user, actor=admin, window='week')
        all_report = build_user_report(self.user, actor=admin, window='all')
        self.assertEqual(week_report['summary']['activity_count'], 1)
        self.assertEqual(all_report['summary']['activity_count'], 2)
        self.assertEqual([item.pk for item in week_report['recent_activity']], [project_log.pk])
        self.assertEqual(
            {item.pk for item in all_report['recent_activity']},
            {project_log.pk, old_project_log.pk},
        )

        week_xlsx = admin_client.get(reverse('user_report_xlsx', args=[self.user.pk]), {'window': 'week'})
        all_xlsx = admin_client.get(reverse('user_report_xlsx', args=[self.user.pk]), {'window': 'all'})

        self.assertEqual(week_xlsx.status_code, 200)
        self.assertEqual(all_xlsx.status_code, 200)
        self.assertIn(b'PK', week_xlsx.content[:4])
        self.assertIn(b'PK', all_xlsx.content[:4])
        self.assertTrue(project_log.pk)

    def test_reports_overview_requires_permission_and_renders_staff_entry_data(self):
        ActivityLog = apps.get_model('dlux', 'ActivityLog')
        ActivityLog.objects.create(
            created_by=self.user,
            action='CREATE',
            model_name='Project Entry',
        )
        ActivityLog.objects.create(
            created_by=self.user,
            action='UPDATE',
            model_name='Known Device',
        )
        staff = User.objects.create_user(
            username='reports-staff',
            email='reports-staff@example.com',
            password='reportspass123',
            is_staff=True,
        )
        staff_client = Client()
        staff_client.login(username='reports-staff', password='reportspass123')

        denied = staff_client.get(reverse('reports_overview'))
        self.assertEqual(denied.status_code, 403)

        view_reports = Permission.objects.get(codename='view_reports')
        staff.user_permissions.add(view_reports)

        response = staff_client.get(reverse('reports_overview'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Reports')
        self.assertContains(response, 'Project Entry')
        overview_model_labels = {item['label'] for item in response.context['overview']['models']}
        self.assertNotIn('Known Device', overview_model_labels)

        xlsx = staff_client.get(reverse('reports_overview_xlsx'), {'window': 'week'})
        self.assertEqual(xlsx.status_code, 200)
        self.assertEqual(
            xlsx['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    def test_reports_backup_requires_separate_permission(self):
        staff = User.objects.create_user(
            username='backup-staff',
            email='backup-staff@example.com',
            password='backuppass123',
            is_staff=True,
        )
        staff.user_permissions.add(Permission.objects.get(codename='view_reports'))
        staff_client = Client()
        staff_client.login(username='backup-staff', password='backuppass123')

        denied = staff_client.get(reverse('reports_backup_zip'))
        self.assertEqual(denied.status_code, 403)

        staff.user_permissions.add(Permission.objects.get(codename='download_backup'))
        allowed = staff_client.get(reverse('reports_backup_zip'))

        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed['Content-Type'], 'application/zip')
        content = b''.join(allowed.streaming_content)
        self.assertIn(b'PK', content[:4])

    def test_reports_count_non_ascii_model_labels(self):
        """Translated (non-ASCII) verbose names are stored as the activity log
        model_name. They normalize to an empty key, so the eligibility filter must
        not reject them outright — otherwise every operation in a non-Latin locale
        (e.g. Arabic) drops out and reports always show 0. Regression for that bug."""
        from dlux.reports import (
            is_report_eligible_activity_model_name,
            build_reports_overview,
        )
        from dlux.user_reports import build_user_report

        ActivityLog = apps.get_model('dlux', 'ActivityLog')
        arabic_label = 'قرار'  # "decree" — a host-model verbose name in Arabic

        # The label normalizes to '' yet must remain eligible (it is not a known
        # operational internal, so it falls through to the default-include path).
        self.assertTrue(is_report_eligible_activity_model_name(arabic_label))
        # Operational internals stay excluded regardless.
        self.assertFalse(is_report_eligible_activity_model_name('System Settings'))

        ActivityLog.objects.create(created_by=self.user, action='CREATE', model_name=arabic_label)
        ActivityLog.objects.create(created_by=self.user, action='UPDATE', model_name=arabic_label)
        ActivityLog.objects.create(created_by=self.user, action='UPDATE', model_name='System Settings')

        overview = build_reports_overview(self.user, window='all')
        self.assertEqual(overview['all_total'], 2)
        overview_labels = {item['label'] for item in overview['models']}
        self.assertIn(arabic_label, overview_labels)

        report = build_user_report(self.user, actor=self.user, window='all')
        self.assertEqual(report['summary']['activity_count'], 2)

    def test_reports_group_by_stable_model_key_regardless_of_locale(self):
        """The stable model_key drives grouping/eligibility. The same model logged
        under different UI languages collapses into one row, and operational internals
        stay excluded via their key even when the displayed label differs."""
        from dlux.reports import build_reports_overview

        ActivityLog = apps.get_model('dlux', 'ActivityLog')
        # Same logical host model, logged under two languages → identical stable key.
        ActivityLog.objects.create(
            created_by=self.user, action='CREATE',
            model_key='documents.decree', model_name='قرار',
        )
        ActivityLog.objects.create(
            created_by=self.user, action='UPDATE',
            model_key='documents.decree', model_name='Decree',
        )
        # A dlux-internal model stays excluded via its stable key.
        ActivityLog.objects.create(
            created_by=self.user, action='UPDATE',
            model_key='dlux.systemsettings', model_name='System Settings',
        )

        overview = build_reports_overview(self.user, window='all')
        self.assertEqual(overview['all_total'], 2)
        decree_rows = [m for m in overview['models'] if m['key'] == 'documents.decree']
        self.assertEqual(len(decree_rows), 1)
        self.assertEqual(decree_rows[0]['count'], 2)
        self.assertNotIn(
            'dlux.systemsettings',
            {m['key'] for m in overview['models']},
        )


class ProfileConfigAndOnboardingTests(TestCase):
    """profile_config normalization, the Initial User Setup modal, and the first-login flag."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        from dlux.models import SystemSettings
        s = SystemSettings.load()
        s.is_configured = True
        s.save()
        self.User = get_user_model()

    def test_normalize_profile_config(self):
        from dlux.utils.config import normalize_profile_config, default_profile_config
        d = default_profile_config()
        self.assertEqual(normalize_profile_config(d), normalize_profile_config(normalize_profile_config(d)))
        p = normalize_profile_config({'security_nudges': 'bogus', 'show_activity_feed': False,
                                      'onboarding_options': {'fonts': False}})
        self.assertEqual(p['security_nudges'], 'subtle')  # invalid falls back
        self.assertFalse(p['show_activity_feed'])
        self.assertFalse(p['onboarding_options']['fonts'])

    def test_onboarding_save_sets_prefs_and_flag(self):
        from dlux.models import Profile
        u = self.User.objects.create_user('onbsave', 'os@e.com', 'pw12345678')
        c = Client(); c.force_login(u)
        g = c.get(reverse('initial_user_setup'))
        self.assertEqual(g.status_code, 200)
        self.assertIn(b'dlux-initial-user-setup-form', g.content)
        r = c.post(reverse('initial_user_setup'), {'theme': 'dark', 'language': 'en'})
        self.assertTrue(r.json()['success'])
        prof = Profile.all_objects.get(user=u)
        self.assertTrue(prof.is_configured)
        self.assertEqual(prof.preferences.get('theme'), 'dark')
        # Onboarding is the user's own choice — no notification or activity-log entry.
        from dlux.models import DluxNotification, UserActivityLog
        self.assertEqual(DluxNotification.objects.count(), 0)
        self.assertEqual(UserActivityLog.objects.filter(created_by=u).count(), 0)

    def test_onboarding_skip_sets_flag_without_prefs(self):
        from dlux.models import Profile
        u = self.User.objects.create_user('onbskip', 'ok@e.com', 'pw12345678')
        c = Client(); c.force_login(u)
        r = c.post(reverse('initial_user_setup'), {'skip': '1'})
        self.assertTrue(r.json()['success'])
        prof = Profile.all_objects.get(user=u)
        self.assertTrue(prof.is_configured)
        self.assertFalse(prof.preferences)

    def test_form_density_and_modal_size_preferences_validate_and_persist(self):
        from dlux.models import Profile
        u = self.User.objects.create_user('fduser', 'fd@e.com', 'pw12345678')
        c = Client(); c.force_login(u)
        # Valid values persist.
        c.post(reverse('update_preferences'), {'form_density': 'dense'})
        c.post(reverse('update_preferences'), {'modal_size': 'wide'})
        prefs = Profile.all_objects.get(user=u).preferences
        self.assertEqual(prefs.get('form_density'), 'dense')
        self.assertEqual(prefs.get('modal_size'), 'wide')
        # Invalid values are rejected (and cleared).
        c.post(reverse('update_preferences'), {'form_density': 'bogus'})
        c.post(reverse('update_preferences'), {'modal_size': 'huge'})
        prefs = Profile.all_objects.get(user=u).preferences
        self.assertIsNone(prefs.get('form_density'))
        self.assertIsNone(prefs.get('modal_size'))

    def test_options_renders_form_density_and_modal_size_cards(self):
        u = self.User.objects.create_user('optcards', 'oc@e.com', 'pw12345678')
        c = Client(); c.force_login(u)
        html = c.get(reverse('options_view')).content
        self.assertIn(b'data-options-card="form-density"', html)
        self.assertIn(b'data-options-card="modal-size"', html)
        self.assertIn(b'data-form-density="dense"', html)
        self.assertIn(b'data-modal-size="wide"', html)

    def test_landing_page_options_are_discovered_and_permission_filtered(self):
        from dlux.discovery import build_user_home_url_options
        su = self.User.objects.create_superuser('suopt', 'so@e.com', 'pw12345678')
        reg = self.User.objects.create_user('regopt', 'ro@e.com', 'pw12345678')
        su_values = {o['value'] for o in build_user_home_url_options(su)}
        reg_values = {o['value'] for o in build_user_home_url_options(reg)}
        # Superuser sees at least as many pages as a permission-limited regular user.
        self.assertTrue(reg_values.issubset(su_values))
        self.assertGreater(len(su_values), len(reg_values))

    def test_landing_page_rejects_unauthorized_url(self):
        from dlux.models import SystemSettings, Profile
        from dlux.utils.config import normalize_profile_config
        from django.core.cache import cache
        s = SystemSettings.load()
        s.profile_config = normalize_profile_config({'allow_user_home_url': True}); s.save(); cache.delete('SystemSettings')
        u = self.User.objects.create_user('rejuser', 'rj@e.com', 'pw12345678')
        c = Client(); c.force_login(u)
        c.post(reverse('update_preferences'), {'user_home_url': '/evil/path/'})
        self.assertIsNone(Profile.all_objects.get(user=u).preferences.get('user_home_url'))

    def test_options_landing_page_save_is_gated(self):
        from dlux.models import SystemSettings, Profile
        from dlux.utils.config import normalize_profile_config
        from django.core.cache import cache
        s = SystemSettings.load()
        s.profile_config = normalize_profile_config({'allow_user_home_url': True}); s.save(); cache.delete('SystemSettings')
        u = self.User.objects.create_user('lpuser', 'lp@e.com', 'pw12345678')
        c = Client(); c.force_login(u)
        # Options renders the landing-page control when allowed.
        self.assertIn(b'data-user-home-url', c.get(reverse('options_view')).content)
        c.post(reverse('update_preferences'), {'user_home_url': '/sys/options/'})
        self.assertEqual(Profile.all_objects.get(user=u).preferences.get('user_home_url'), '/sys/options/')
        # When the admin disallows it, the API refuses (and clears) the value.
        s.profile_config = normalize_profile_config({'allow_user_home_url': False}); s.save(); cache.delete('SystemSettings')
        self.assertNotIn(b'data-user-home-url', c.get(reverse('options_view')).content)
        c.post(reverse('update_preferences'), {'user_home_url': '/elsewhere/'})
        self.assertIsNone(Profile.all_objects.get(user=u).preferences.get('user_home_url'))

    def test_superuser_excluded_from_initial_user_setup(self):
        reg = self.User.objects.create_user('reguser', 'rg@e.com', 'pw12345678')
        c = Client(); c.force_login(reg)
        self.assertTrue(c.get(reverse('user_profile')).context['DLUX_SHOW_INITIAL_USER_SETUP'])
        su = self.User.objects.create_superuser('suuser', 'su@e.com', 'pw12345678')
        c2 = Client(); c2.force_login(su)
        self.assertFalse(c2.get(reverse('user_profile')).context['DLUX_SHOW_INITIAL_USER_SETUP'])

    def test_onboarding_modal_ajax_returns_json_html(self):
        u = self.User.objects.create_user('ajaxu', 'aj@e.com', 'pw12345678')
        c = Client(); c.force_login(u)
        g = c.get(reverse('initial_user_setup'), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(g['Content-Type'], 'application/json')
        self.assertIn('dlux-initial-user-setup-form', g.json()['html'])

    def test_login_redirect_honors_user_home_url(self):
        from dlux.models import SystemSettings
        from dlux.utils.config import normalize_profile_config
        from django.core.cache import cache
        s = SystemSettings.load(); s.home_url = '/accounts/profile/'
        s.profile_config = normalize_profile_config({'allow_user_home_url': True}); s.save(); cache.delete('SystemSettings')
        u = self.User.objects.create_user('homeuser', 'hu@e.com', 'pw12345678')
        u.profile.is_configured = True
        u.profile.preferences = {'user_home_url': '/sys/options/'}
        u.profile.save()
        c = Client()
        resp = c.post(reverse('login'), {'username': 'homeuser', 'password': 'pw12345678'})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], '/sys/options/')
        # When the admin disallows it, fall back to the system home.
        s.profile_config = normalize_profile_config({'allow_user_home_url': False}); s.save(); cache.delete('SystemSettings')
        c2 = Client()
        resp2 = c2.post(reverse('login'), {'username': 'homeuser', 'password': 'pw12345678'})
        self.assertEqual(resp2['Location'], '/accounts/profile/')

    def test_context_flag_shows_only_until_configured(self):
        u = self.User.objects.create_user('onbflag', 'of@e.com', 'pw12345678')
        c = Client(); c.force_login(u)
        page = c.get(reverse('user_profile'))
        self.assertTrue(page.context['DLUX_SHOW_INITIAL_USER_SETUP'])
        u.profile.is_configured = True
        u.profile.save()
        page2 = c.get(reverse('user_profile'))
        self.assertFalse(page2.context['DLUX_SHOW_INITIAL_USER_SETUP'])

    def test_onboarding_is_deferred_until_forced_password_change_is_cleared(self):
        u = self.User.objects.create_user('forceonb', 'fo@e.com', 'pw12345678')
        u.profile.preferences = {'force_password_change': True}
        u.profile.save(update_fields=['preferences'])
        c = Client(); c.force_login(u)

        page = c.get(reverse('user_profile'))
        self.assertEqual(page.status_code, 200)
        self.assertTrue(page.context['force_password_change_required'])
        self.assertFalse(page.context['DLUX_SHOW_INITIAL_USER_SETUP'])

        welcome = c.get(reverse('initial_user_setup'), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(welcome.status_code, 403)
        payload = welcome.json()
        self.assertFalse(payload['success'])
        self.assertEqual(payload['redirect_url'], f"{reverse('user_profile')}?force_password_change=1")

        u.profile.preferences = {}
        u.profile.save(update_fields=['preferences'])
        page_after_clear = c.get(reverse('user_profile'))
        self.assertTrue(page_after_clear.context['DLUX_SHOW_INITIAL_USER_SETUP'])
