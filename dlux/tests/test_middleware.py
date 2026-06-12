from django.conf import settings

if not settings.configured:
    settings.configure(
        SECRET_KEY='dlux-test-key',
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
            'dlux',
        ],
        MIDDLEWARE=[
            'django.contrib.sessions.middleware.SessionMiddleware',
            'django.contrib.auth.middleware.AuthenticationMiddleware',
            'dlux.middleware.DluxMiddleware',
        ],
        ROOT_URLCONF='dlux.urls',
        TEMPLATES=[
            {
                'BACKEND': 'django.template.backends.django.DjangoTemplates',
                'APP_DIRS': True,
                'OPTIONS': {
                    'context_processors': [
                        'django.template.context_processors.request',
                        'django.contrib.auth.context_processors.auth',
                        'django.contrib.messages.context_processors.messages',
                        'dlux.context_processors.dlux_context',
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
from django.contrib.sessions.middleware import SessionMiddleware
from django.urls import reverse
from django.http import HttpResponse
from django.core.cache import cache
from unittest.mock import patch
from dlux.middleware import DluxMiddleware, get_current_user, get_current_request

User = get_user_model()


class DluxMiddlewareTests(TestCase):
    def setUp(self):
        cache.clear()
        from dlux.models import SystemSettings

        SystemSettings._default_manager.all().delete()
        self.factory = RequestFactory()
        self.middleware = DluxMiddleware(lambda r: HttpResponse())
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

    def _attach_session(self, request):
        middleware = SessionMiddleware(lambda req: HttpResponse())
        middleware.process_request(request)
        request.session.save()
        return request

    def test_get_current_user_returns_none_when_not_set(self):
        """Test that get_current_user returns None when not set."""
        self.assertIsNone(get_current_user())

    def test_get_current_request_returns_none_when_not_set(self):
        """Test that get_current_request returns None when not set."""
        self.assertIsNone(get_current_request())

    def test_middleware_sets_thread_local_user(self):
        """Test that middleware sets thread-local user."""
        seen = {}

        def capture_response(request):
            seen['user'] = get_current_user()
            return HttpResponse()

        middleware = DluxMiddleware(capture_response)
        request = self.factory.get('/some-page')
        request.user = self.user
        request.path = '/some-page'
        with override_settings(DLUX_CONFIG={'is_configured': True}):
            middleware(request)

        self.assertEqual(seen.get('user'), self.user)

    def test_middleware_sets_thread_local_request(self):
        """Test that middleware sets thread-local request."""
        seen = {}

        def capture_response(request):
            seen['request'] = get_current_request()
            return HttpResponse()

        middleware = DluxMiddleware(capture_response)
        request = self.factory.get('/some-page')
        request.user = self.user
        request.path = '/some-page'
        with override_settings(DLUX_CONFIG={'is_configured': True}):
            middleware(request)

        self.assertEqual(seen.get('request'), request)

    def test_middleware_cleans_up_thread_locals(self):
        """Test that middleware cleans up thread-local variables."""
        request = self.factory.get('/')
        request.user = self.user
        self.middleware(request)
        
        # After response, thread locals should be cleaned up
        # Note: This happens in the finally block, so we need to call it again
        # to verify cleanup
        from dlux.middleware import _thread_locals
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

    @override_settings(ROOT_URLCONF='dlux.tests.urls_with_prefix_mount')
    def test_setup_guard_allowed_paths_with_prefix_mount(self):
        """Test that setup guard allowlist follows the active Dlux mount prefix."""
        for path in [
            '/dlux/accounts/login/',
            '/dlux/accounts/logout/',
            '/dlux/sys/setup/',
            '/dlux/sys/api/preferences/update/',
            '/dlux/sys/2fa/verify/',
        ]:
            request = self.factory.get(path)
            request.user = self.user
            request.path = path
            self.assertFalse(self.middleware._should_redirect_to_setup(request))

    def test_should_redirect_to_setup_for_unconfigured_system(self):
        """Test redirect to setup for unconfigured system."""
        request = self.factory.get('/some-page')
        request.user = self.user
        request.path = '/some-page'
        
        # Make user a superuser
        self.user.is_superuser = True
        self.user.save()
        
        with patch.object(self.middleware, '_setup_guard_allowed', return_value=False), patch.object(
            self.middleware,
            '_load_system_config',
            return_value={'is_configured': False},
        ):
            self.assertTrue(self.middleware._should_redirect_to_setup(request))

    def test_should_not_redirect_to_setup_for_configured_system(self):
        """Test no redirect to setup for configured system."""
        request = self.factory.get('/some-page')
        request.user = self.user
        request.path = '/some-page'
        
        with patch.object(self.middleware, '_setup_guard_allowed', return_value=False), patch.object(
            self.middleware,
            '_load_system_config',
            return_value={'is_configured': True},
        ):
            self.assertFalse(self.middleware._should_redirect_to_setup(request))

    def test_should_not_redirect_to_setup_for_anonymous_user(self):
        """Test anonymous users are redirected to login while setup is incomplete."""
        request = self.factory.get('/some-page')
        request.user = type('AnonymousUser', (), {'is_authenticated': False})()
        request.path = '/some-page'
        
        with patch.object(self.middleware, '_setup_guard_allowed', return_value=False), patch.object(
            self.middleware,
            '_load_system_config',
            return_value={'is_configured': False},
        ):
            self.assertTrue(self.middleware._should_redirect_to_setup(request))

    def test_setup_redirect_response_sends_anonymous_users_to_login(self):
        """Test anonymous requests are blocked from host-app pages before setup completes."""
        request = self.factory.get('/external-page/')
        request.user = type('AnonymousUser', (), {'is_authenticated': False})()
        request.path = '/external-page/'

        with patch.object(self.middleware, '_setup_guard_allowed', return_value=False), patch.object(
            self.middleware,
            '_load_system_config',
            return_value={'is_configured': False},
        ):
            response = self.middleware._setup_redirect_response(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('login'))

    def test_setup_redirect_response_logs_out_non_superusers_to_login(self):
        """Test authenticated non-superusers cannot bypass the setup gate through host-app URLs."""
        request = self.factory.get('/external-page/')
        request.user = self.user
        request.path = '/external-page/'
        self._attach_session(request)
        request.session['_auth_user_id'] = str(self.user.pk)
        request.session['_auth_user_backend'] = 'django.contrib.auth.backends.ModelBackend'
        request.session['_auth_user_hash'] = self.user.get_session_auth_hash()
        request.session.save()

        with patch.object(self.middleware, '_setup_guard_allowed', return_value=False), patch.object(
            self.middleware,
            '_load_system_config',
            return_value={'is_configured': False},
        ):
            response = self.middleware._setup_redirect_response(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('login'))
        self.assertNotIn('_auth_user_id', request.session)

    def test_root_redirect_returns_none_for_non_404(self):
        """Test that _root_redirect does nothing when response is not 404."""
        request = self.factory.get('/')
        request.user = self.user
        request.path = '/'

        response = HttpResponse(status=200)
        self.assertIsNone(self.middleware._root_redirect(request, response))

    def test_root_redirect_returns_none_for_non_root_path(self):
        """Test that _root_redirect does nothing for non-root 404s."""
        request = self.factory.get('/some-path')
        request.user = self.user
        request.path = '/some-path'

        response = HttpResponse(status=404)
        self.assertIsNone(self.middleware._root_redirect(request, response))

    def test_root_redirect_to_setup_when_unconfigured(self):
        """Test _root_redirect sends to setup when system is not configured."""
        request = self.factory.get('/')
        request.user = type('AnonymousUser', (), {'is_authenticated': False})()
        request.path = '/'

        response_404 = HttpResponse(status=404)
        with override_settings(DLUX_CONFIG={'is_configured': False}):
            result = self.middleware._root_redirect(request, response_404)
            self.assertEqual(result.status_code, 302)
            self.assertIn('sys/setup', result.url)

    def test_root_redirect_to_home_url_when_configured(self):
        """Test _root_redirect sends to home_url when system is configured."""
        request = self.factory.get('/')
        request.user = self.user
        request.path = '/'

        response_404 = HttpResponse(status=404)
        with override_settings(DLUX_CONFIG={'is_configured': True, 'home_url': '/dashboard/'}):
            result = self.middleware._root_redirect(request, response_404)
            self.assertEqual(result.status_code, 302)
            self.assertIn('/dashboard/', result.url)

    def test_root_redirect_returns_none_when_home_url_is_root(self):
        """Test _root_redirect avoids infinite loop if home_url is /."""
        request = self.factory.get('/')
        request.user = self.user
        request.path = '/'

        response_404 = HttpResponse(status=404)
        with override_settings(DLUX_CONFIG={'is_configured': True, 'home_url': '/'}):
            self.assertIsNone(self.middleware._root_redirect(request, response_404))

    def test_root_redirect_anonymous_to_login_when_public_root_off(self):
        """Test _root_redirect sends anonymous users to login when public_root is disabled."""
        request = self.factory.get('/')
        request.user = type('AnonymousUser', (), {'is_authenticated': False})()
        request.path = '/'

        response_404 = HttpResponse(status=404)
        with override_settings(DLUX_CONFIG={'is_configured': True, 'home_url': '/dashboard/', 'public_root': False}):
            result = self.middleware._root_redirect(request, response_404)
            self.assertEqual(result.status_code, 302)
            self.assertIn('/accounts/login/', result.url)

    def test_root_redirect_anonymous_to_home_when_public_root_on(self):
        """Test _root_redirect sends anonymous users to home_url when public_root is enabled."""
        request = self.factory.get('/')
        request.user = type('AnonymousUser', (), {'is_authenticated': False})()
        request.path = '/'

        response_404 = HttpResponse(status=404)
        with override_settings(DLUX_CONFIG={'is_configured': True, 'home_url': '/dashboard/', 'public_root': True}):
            result = self.middleware._root_redirect(request, response_404)
            self.assertEqual(result.status_code, 302)
            self.assertIn('/dashboard/', result.url)

    def test_root_redirect_anonymous_uses_public_root_url_when_split_enabled(self):
        request = self.factory.get('/')
        request.user = type('AnonymousUser', (), {'is_authenticated': False})()
        request.path = '/'

        response_404 = HttpResponse(status=404)
        with override_settings(DLUX_CONFIG={
            'is_configured': True,
            'home_url': '/dashboard/',
            'public_root': True,
            'public_root_split_enabled': True,
            'public_root_url': '/landing/',
        }):
            result = self.middleware._root_redirect(request, response_404)
            self.assertEqual(result.status_code, 302)
            self.assertEqual(result.url, '/landing/')

    def test_root_redirect_authenticated_still_uses_home_url_when_split_enabled(self):
        request = self.factory.get('/')
        request.user = self.user
        request.path = '/'

        response_404 = HttpResponse(status=404)
        with override_settings(DLUX_CONFIG={
            'is_configured': True,
            'home_url': '/dashboard/',
            'public_root': True,
            'public_root_split_enabled': True,
            'public_root_url': '/landing/',
        }):
            result = self.middleware._root_redirect(request, response_404)
            self.assertEqual(result.status_code, 302)
            self.assertEqual(result.url, '/dashboard/')

    def test_sync_auth_redirects_uses_public_root_url_for_logout_when_split_enabled(self):
        with override_settings(DLUX_CONFIG={
            'is_configured': True,
            'home_url': '/dashboard/',
            'public_root': True,
            'public_root_split_enabled': True,
            'public_root_url': '/landing/',
        }):
            self.middleware._sync_auth_redirects()
            self.assertEqual(settings.LOGIN_REDIRECT_URL, '/dashboard/')
            self.assertEqual(settings.LOGOUT_REDIRECT_URL, '/landing/')

    def test_middleware_full_flow_with_redirect_to_setup(self):
        """Test full middleware flow with redirect to setup."""
        request = self.factory.get('/some-page')
        self.user.is_superuser = True
        self.user.save()
        request.user = self.user
        request.path = '/some-page'
        
        with patch.object(self.middleware, '_setup_guard_allowed', return_value=False), patch.object(
            self.middleware,
            '_load_system_config',
            return_value={'is_configured': False},
        ):
            response = self.middleware(request)
            self.assertEqual(response.status_code, 302)
            self.assertIn('sys/setup', response.url)

    def test_middleware_full_flow_redirects_anonymous_host_page_to_login(self):
        """Test the middleware blocks anonymous host-app pages until setup completes."""
        request = self.factory.get('/external-page/')
        request.user = type('AnonymousUser', (), {'is_authenticated': False})()
        request.path = '/external-page/'

        with patch.object(self.middleware, '_setup_guard_allowed', return_value=False), patch.object(
            self.middleware,
            '_load_system_config',
            return_value={'is_configured': False},
        ):
            response = self.middleware(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('login'))

    def test_middleware_full_flow_without_redirect(self):
        """Test full middleware flow without redirect."""
        request = self.factory.get('/some-page')
        request.user = self.user
        request.path = '/some-page'
        
        with override_settings(DLUX_CONFIG={'is_configured': True}):
            response = self.middleware(request)
            self.assertEqual(response.status_code, 200)
