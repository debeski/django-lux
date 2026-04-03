
import threading
from django.conf import settings
from django.shortcuts import redirect
from django.urls import NoReverseMatch, reverse

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
        ]

        static_url = getattr(settings, 'STATIC_URL', None)
        media_url = getattr(settings, 'MEDIA_URL', None)
        if static_url:
            allowed_prefixes.append(static_url)
        if media_url:
            allowed_prefixes.append(media_url)

        return any(request.path.startswith(prefix) for prefix in allowed_prefixes)

    def _should_redirect_to_setup(self, request):
        user = getattr(request, 'user', None)
        if not user or not getattr(user, 'is_authenticated', False) or not user.is_superuser:
            return False
        if self._setup_guard_allowed(request):
            return False

        try:
            from microsys.utils import get_system_config
            config = get_system_config()
            return not bool(config.get('is_configured', False))
        except Exception:
            return False

    def _is_root_mounted_microsys(self):
        try:
            return (
                reverse('login') == '/accounts/login/' and
                reverse('system_setup') == '/sys/setup/'
            )
        except NoReverseMatch:
            return False

    def _should_redirect_missing_root(self, request, response):
        return (
            request.path == '/' and
            request.method in {'GET', 'HEAD'} and
            getattr(response, 'status_code', None) == 404 and
            getattr(request, 'resolver_match', None) is None and
            self._is_root_mounted_microsys()
        )

    def _missing_root_redirect(self, request):
        user = getattr(request, 'user', None)
        if not user or not getattr(user, 'is_authenticated', False):
            return redirect('login')

        try:
            from microsys.utils import get_system_config
            config = get_system_config()
        except Exception:
            config = {}

        if user.is_superuser and not bool(config.get('is_configured', False)):
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
            # Clean up to prevent memory leaks or data pollution in reused threads
            if hasattr(_thread_locals, 'user'):
                del _thread_locals.user
            if hasattr(_thread_locals, 'request'):
                del _thread_locals.request
