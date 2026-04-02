
import threading
from django.conf import settings
from django.shortcuts import redirect

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

    def __call__(self, request):
        _thread_locals.user = getattr(request, 'user', None)
        _thread_locals.request = request

        try:
            if self._should_redirect_to_setup(request):
                return redirect('system_setup')
            return self.get_response(request)
        finally:
            # Clean up to prevent memory leaks or data pollution in reused threads
            if hasattr(_thread_locals, 'user'):
                del _thread_locals.user
            if hasattr(_thread_locals, 'request'):
                del _thread_locals.request
