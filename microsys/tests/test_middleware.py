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
        MEDIA_URL='/media/',
        DEFAULT_AUTO_FIELD='django.db.models.BigAutoField',
        USE_TZ=True,
        CRISPY_ALLOWED_TEMPLATE_PACKS='bootstrap5',
        CRISPY_TEMPLATE_PACK='bootstrap5',
    )

    import django
    django.setup()

from django.test import TestCase, RequestFactory, override_settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.http import HttpResponse
from django.core.cache import cache
from microsys.middleware import ActivityLogMiddleware, get_current_user, get_current_request

User = get_user_model()


class ActivityLogMiddlewareTests(TestCase):
    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()
        self.middleware = ActivityLogMiddleware(lambda r: HttpResponse())
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

    def test_get_current_user_returns_none_when_not_set(self):
        """Test that get_current_user returns None when not set."""
        self.assertIsNone(get_current_user())

    def test_get_current_request_returns_none_when_not_set(self):
        """Test that get_current_request returns None when not set."""
        self.assertIsNone(get_current_request())

    def test_middleware_sets_thread_local_user(self):
        """Test that middleware sets thread-local user."""
        request = self.factory.get('/')
        request.user = self.user
        self.middleware(request)
        self.assertEqual(get_current_user(), self.user)

    def test_middleware_sets_thread_local_request(self):
        """Test that middleware sets thread-local request."""
        request = self.factory.get('/')
        request.user = self.user
        self.middleware(request)
        self.assertEqual(get_current_request(), request)

    def test_middleware_cleans_up_thread_locals(self):
        """Test that middleware cleans up thread-local variables."""
        request = self.factory.get('/')
        request.user = self.user
        self.middleware(request)
        
        # After response, thread locals should be cleaned up
        # Note: This happens in the finally block, so we need to call it again
        # to verify cleanup
        from microsys.middleware import _thread_locals
        self.assertFalse(hasattr(_thread_locals, 'user'))

    def test_setup_guard_allowed_paths(self):
        """Test that setup guard allows specific paths."""
        allowed_paths = [
            '/accounts/login/',
            '/accounts/logout/',
            '/sys/setup/',
            '/sys/api/preferences/',
            '/sys/2fa/',
            '/static/test.css',
            '/media/test.jpg',
        ]
        
        for path in allowed_paths:
            request = self.factory.get(path)
            request.user = self.user
            self.assertFalse(self.middleware._should_redirect_to_setup(request))

    def test_should_redirect_to_setup_for_unconfigured_system(self):
        """Test redirect to setup for unconfigured system."""
        request = self.factory.get('/some-page')
        request.user = self.user
        request.path = '/some-page'
        
        # Make user a superuser
        self.user.is_superuser = True
        self.user.save()
        
        with override_settings(MICROSYS_CONFIG={'is_configured': False}):
            self.assertTrue(self.middleware._should_redirect_to_setup(request))

    def test_should_not_redirect_to_setup_for_configured_system(self):
        """Test no redirect to setup for configured system."""
        request = self.factory.get('/some-page')
        request.user = self.user
        request.path = '/some-page'
        
        with override_settings(MICROSYS_CONFIG={'is_configured': True}):
            self.assertFalse(self.middleware._should_redirect_to_setup(request))

    def test_should_not_redirect_to_setup_for_anonymous_user(self):
        """Test no redirect to setup for anonymous user."""
        request = self.factory.get('/some-page')
        request.user = type('AnonymousUser', (), {'is_authenticated': False})()
        request.path = '/some-page'
        
        with override_settings(MICROSYS_CONFIG={'is_configured': False}):
            self.assertFalse(self.middleware._should_redirect_to_setup(request))

    def test_is_root_mounted_microsys(self):
        """Test detection of root-mounted microsys."""
        self.assertTrue(self.middleware._is_root_mounted_microsys())

    def test_should_redirect_missing_root(self):
        """Test redirect for missing root."""
        request = self.factory.get('/')
        request.user = self.user
        request.path = '/'
        request.method = 'GET'
        request.resolver_match = None
        
        response = HttpResponse(status=404)
        self.assertTrue(self.middleware._should_redirect_missing_root(request, response))

    def test_should_not_redirect_missing_root_for_non_root(self):
        """Test no redirect for non-root paths."""
        request = self.factory.get('/some-path')
        request.user = self.user
        request.path = '/some-path'
        request.method = 'GET'
        request.resolver_match = None
        
        response = HttpResponse(status=404)
        self.assertFalse(self.middleware._should_redirect_missing_root(request, response))

    def test_missing_root_redirect_for_anonymous(self):
        """Test missing root redirect for anonymous user."""
        request = self.factory.get('/')
        request.user = type('AnonymousUser', (), {'is_authenticated': False})()
        
        response = self.middleware._missing_root_redirect(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/accounts/login/')

    def test_missing_root_redirect_for_superuser_unconfigured(self):
        """Test missing root redirect for superuser on unconfigured system."""
        request = self.factory.get('/')
        self.user.is_superuser = True
        self.user.save()
        request.user = self.user
        
        with override_settings(MICROSYS_CONFIG={'is_configured': False}):
            response = self.middleware._missing_root_redirect(request)
            self.assertEqual(response.status_code, 302)
            self.assertIn('sys/setup', response.url)

    def test_missing_root_redirect_for_configured_system(self):
        """Test missing root redirect for configured system."""
        request = self.factory.get('/')
        self.user.is_superuser = True
        self.user.save()
        request.user = self.user
        
        with override_settings(MICROSYS_CONFIG={'is_configured': True, 'home_url': '/profile/'}):
            response = self.middleware._missing_root_redirect(request)
            self.assertEqual(response.status_code, 302)
            self.assertIn('/profile/', response.url)

    def test_middleware_full_flow_with_redirect_to_setup(self):
        """Test full middleware flow with redirect to setup."""
        request = self.factory.get('/some-page')
        self.user.is_superuser = True
        self.user.save()
        request.user = self.user
        request.path = '/some-page'
        
        with override_settings(MICROSYS_CONFIG={'is_configured': False}):
            response = self.middleware(request)
            self.assertEqual(response.status_code, 302)
            self.assertIn('sys/setup', response.url)

    def test_middleware_full_flow_without_redirect(self):
        """Test full middleware flow without redirect."""
        request = self.factory.get('/some-page')
        request.user = self.user
        request.path = '/some-page'
        
        with override_settings(MICROSYS_CONFIG={'is_configured': True}):
            response = self.middleware(request)
            self.assertEqual(response.status_code, 200)
