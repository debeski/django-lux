
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
        ]
        return any(request.path.startswith(prefix) for prefix in allowed_prefixes)

    def _should_redirect_to_setup(self, request):
        if self._setup_guard_allowed(request):
            return False

        # Direct DB check to bypass any caching/merging bugs in get_system_config
        try:
            from microsys.models import SystemSettings
            # We use load() which we modified to check DB existence, but let's be even more direct here
            # to be absolutely sure we don't return False if it's truly not configured.
            s = SystemSettings.objects.filter(pk=1).first()
            if s and s.is_configured:
                return False
        except Exception:
            # If DB is not ready, we can't redirect yet (prevents infinite loops during migrations)
            return False

        user = getattr(request, 'user', None)
        if not user or not getattr(user, 'is_authenticated', False):
            # Not logged in: go to setup (which redirects to login if @login_required)
            return True

        return bool(user.is_superuser)

    def _is_root_mounted_microsys(self):
        """Check if Microsys is mounted at the root URL."""
        from django.urls import resolve, Resolver404
        try:
            match = resolve('/')
            return (match.func.__module__.startswith('microsys.') or 
                    getattr(match.func, '__module__', '').startswith('microsys.'))
        except Resolver404:
            return True 

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
        
        # Anonymous users always go to login
        if not getattr(user, 'is_authenticated', False):
            return redirect('login')
        
        try:
            config = get_system_config()
        except Exception:
            config = {}

        # Direct check again for safety
        try:
            from microsys.models import SystemSettings
            s = SystemSettings.objects.filter(pk=1).first()
            is_configured = s.is_configured if s else False
        except Exception:
            is_configured = False

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
