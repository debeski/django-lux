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

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.cache import cache
import json

User = get_user_model()


class APIEndpointsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')

    def test_get_last_entry_requires_login(self):
        """Test that get_last_entry requires authentication."""
        self.client.logout()
        response = self.client.get(
            reverse('get_last_entry', args=['microsys', 'SystemSettings'])
        )
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_get_last_entry_requires_permission(self):
        """Test that get_last_entry requires view permission."""
        # Create a user without permissions
        regular_user = User.objects.create_user(
            username='user2',
            email='user2@example.com',
            password='userpass123'
        )
        self.client.logout()
        self.client.login(username='user2', password='userpass123')
        
        response = self.client.get(
            reverse('get_last_entry', args=['microsys', 'SystemSettings'])
        )
        self.assertEqual(response.status_code, 403)  # Permission denied

    def test_get_last_entry_with_permission(self):
        """Test get_last_entry with proper permissions."""
        # Give the user permission
        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(User)
        perm = Permission.objects.create(
            codename='view_user',
            name='Can view user',
            content_type=ct,
        )
        self.user.user_permissions.add(perm)
        
        response = self.client.get(
            reverse('get_last_entry', args=['auth', 'User'])
        )
        self.assertIn(response.status_code, [200, 404])  # 200 if exists, 404 if no entries

    def test_get_model_details_requires_login(self):
        """Test that get_model_details requires authentication."""
        self.client.logout()
        response = self.client.get(
            reverse('get_model_details', args=['microsys', 'SystemSettings', 'empty_schema'])
        )
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_get_model_details_empty_schema(self):
        """Test get_model_details with empty_schema."""
        response = self.client.get(
            reverse('get_model_details', args=['microsys', 'SystemSettings', 'empty_schema'])
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('_pk', data)

    def test_get_model_details_invalid_model(self):
        """Test get_model_details with invalid model."""
        response = self.client.get(
            reverse('get_model_details', args=['invalid', 'InvalidModel', '1'])
        )
        self.assertEqual(response.status_code, 404)

    def test_update_preferences_requires_login(self):
        """Test that update_preferences requires authentication."""
        self.client.logout()
        response = self.client.post(
            reverse('update_preferences'),
            {'theme': 'dark'},
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_update_preferences_post(self):
        """Test update_preferences with POST."""
        response = self.client.post(
            reverse('update_preferences'),
            json.dumps({'theme': 'dark', 'language': 'en'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')
        
        # Verify preference was saved
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.preferences.get('theme'), 'dark')

    def test_update_preferences_with_form_data(self):
        """Test update_preferences with form data (not JSON)."""
        response = self.client.post(
            reverse('update_preferences'),
            {'theme': 'light', 'sidebar_collapsed': 'true'}
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')

    def test_update_preferences_invalid_method(self):
        """Test update_preferences with invalid method."""
        response = self.client.get(reverse('update_preferences'))
        self.assertEqual(response.status_code, 405)  # Method not allowed

    def test_reset_preferences_requires_login(self):
        """Test that reset_preferences requires authentication."""
        self.client.logout()
        response = self.client.post(reverse('reset_preferences'))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_reset_preferences_post(self):
        """Test reset_preferences with POST."""
        # Set some preferences first
        self.user.profile.preferences = {'theme': 'dark', 'language': 'en'}
        self.user.profile.save()
        
        response = self.client.post(reverse('reset_preferences'))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        
        # Verify preferences were cleared
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.preferences, {})

    def test_reset_preferences_clears_session(self):
        """Test that reset_preferences clears session keys."""
        # Set session keys
        session = self.client.session
        session['django_language'] = 'ar'
        session['sidebarCollapsed'] = True
        session.save()
        
        response = self.client.post(reverse('reset_preferences'))
        self.assertEqual(response.status_code, 200)
        
        # Verify session keys were cleared
        session = self.client.session
        self.assertNotIn('django_language', session)
        self.assertNotIn('sidebarCollapsed', session)

    def test_reset_preferences_invalid_method(self):
        """Test reset_preferences with invalid method."""
        response = self.client.get(reverse('reset_preferences'))
        self.assertEqual(response.status_code, 400)  # Bad request
