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
from django.urls import reverse
from django.core.cache import cache
import json
from unittest.mock import patch

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

    def test_system_settings_modal_honors_requested_wizard_step(self):
        response = self.client.get(
            reverse('modal_manager', args=['microsys', 'SystemSettings', 1]) + '?step=2',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertIn('data-ms-wizard-initial-step="2"', payload['html'])
        self.assertIn('?step=2', payload['html'])

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
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            is_staff=True
        )
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')

    def test_activity_log_view_requires_staff(self):
        """Test that activity log view requires staff status."""
        regular_user = User.objects.create_user(
            username='user',
            email='user@example.com',
            password='userpass123'
        )
        self.client.logout()
        self.client.login(username='user', password='userpass123')
        response = self.client.get(reverse('user_activity_log'))
        self.assertEqual(response.status_code, 302)  # Redirect (permission denied)

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
