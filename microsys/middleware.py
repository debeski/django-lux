
import threading
from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse

from .constants import DEFAULT_HOME_URL

_thread_locals = threading.local()

def get_current_user():
    return getattr(_thread_locals, 'user', None)

def get_current_request():
    return getattr(_thread_locals, 'request', None)

class ActivityLogMiddleware:
    """
    Middleware to capture the current request and user in a thread-local variable.
    This allows access to the user in signals where request is not available.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def _setup_guard_allowed(self, request):
        allowed_prefixes = [
            '/accounts/login/',
            '/accounts/logout/',
            '/sys/setup/',
            '/sys/api/preferences/',
            '/sys/2fa/',
            '/static/',
            '/media/',
        ]
        return any(request.path.startswith(prefix) for prefix in allowed_prefixes)

    def _should_redirect_to_setup(self, request):
        if self._setup_guard_allowed(request):
            return False

        try:
            from microsys.utils import get_system_config
            config = get_system_config()
            if config.get('is_configured', False):
                return False
        except Exception:
            return False

        if request.path == '/' and self._is_root_mounted_microsys():
            return True

        user = getattr(request, 'user', None)
        if not user or not getattr(user, 'is_authenticated', False):
            return False

        return bool(user.is_superuser)

    def _is_root_mounted_microsys(self):
        """Check if Microsys is mounted at the root URL."""
        from django.urls import URLPattern, URLResolver, get_resolver

        resolver = get_resolver()
        urlconf_name = getattr(resolver, 'urlconf_name', '')
        if isinstance(urlconf_name, str) and urlconf_name == 'microsys.urls':
            return True

        for pattern in resolver.url_patterns:
            route = getattr(pattern.pattern, '_route', str(pattern.pattern))
            if isinstance(pattern, URLResolver):
                nested = getattr(pattern, 'urlconf_name', None)
                nested_name = nested if isinstance(nested, str) else getattr(nested, '__name__', '')
                if route == '' and nested_name == 'microsys.urls':
                    return True
            elif isinstance(pattern, URLPattern):
                callback = getattr(pattern, 'callback', None)
                if route == '' and getattr(callback, '__module__', '').startswith('microsys.'):
                    return True
        return False

    def _should_redirect_missing_root(self, request, response):
        """Helper to check if we should redirect from / to dashboard/setup."""
        if response.status_code != 404:
            return False
        
        return (
            request.path == '/' and
            self._is_root_mounted_microsys()
        )

    def _missing_root_redirect(self, request):
        from microsys.utils import get_system_config
        user = request.user
        
        config = get_system_config()
        is_configured = bool(config.get('is_configured', False))
        
        # Anonymous users: check if public root is allowed
        if not getattr(user, 'is_authenticated', False):
            if not is_configured:
                return redirect('system_setup')
            # If host set explicit LOGIN_REDIRECT_URL, respect their routing intent
            has_custom_login_redirect = hasattr(settings, 'LOGIN_REDIRECT_URL') and settings.LOGIN_REDIRECT_URL != DEFAULT_HOME_URL
            # Or if public_root is explicitly enabled in config
            public_root_enabled = config.get('public_root', False)
            
            if has_custom_login_redirect or public_root_enabled:
                # Let the request proceed (will likely 404, letting host handle it)
                return None
            # Otherwise, redirect to login
            return redirect('login')

        if user.is_superuser and not is_configured:
            return redirect('system_setup')

        return redirect(
            config.get('home_url') or
            getattr(settings, 'LOGIN_REDIRECT_URL', DEFAULT_HOME_URL)
        )

    def __call__(self, request):
        _thread_locals.user = getattr(request, 'user', None)
        _thread_locals.request = request

        try:
            if self._should_redirect_to_setup(request):
                return redirect('system_setup')
            
            response = self.get_response(request)
            
            if self._should_redirect_missing_root(request, response):
                return self._missing_root_redirect(request)
            
            return response
        finally:
            if hasattr(_thread_locals, 'user'):
                del _thread_locals.user
            if hasattr(_thread_locals, 'request'):
                del _thread_locals.request
