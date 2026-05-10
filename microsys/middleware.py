
import threading
from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from .constants import DEFAULT_HOME_URL

_thread_locals = threading.local()

def get_current_user():
    return getattr(_thread_locals, 'user', None)

def get_current_request():
    return getattr(_thread_locals, 'request', None)

class MicrosysMiddleware:
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

        user = getattr(request, 'user', None)
        if not user or not getattr(user, 'is_authenticated', False):
            return False

        return bool(user.is_superuser)

    def _root_redirect(self, request, response):
        """
        Handle root URL hijacking.

        If the dev has no view at '/' (response is 404), redirect to
        the home_url configured during system setup.  If the system
        is not yet configured, redirect to the setup wizard instead.

        When public_root is disabled, anonymous users are sent to the
        login page instead of home_url.

        If the dev DOES have a view at '/' (response is not 404),
        this method returns None and the middleware stays out of the way.
        """
        if response.status_code != 404 or request.path != '/':
            return None

        from microsys.utils import get_system_config
        config = get_system_config()

        if not config.get('is_configured', False):
            return redirect('system_setup')

        home_url = config.get('home_url')

        # When public_root is off, anonymous users must log in first
        user = getattr(request, 'user', None)
        if not config.get('public_root', False):
            if not user or not getattr(user, 'is_authenticated', False):
                return redirect('login')

        if home_url and home_url != '/':
            return redirect(home_url)

        return None

    def _client_ip(self, request):
        forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if forwarded_for:
            return forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '')

    def _remember_session_device(self, request):
        user = getattr(request, 'user', None)
        session = getattr(request, 'session', None)
        if not user or not getattr(user, 'is_authenticated', False) or session is None:
            return

        session_key = getattr(session, 'session_key', None)
        if not session_key:
            return

        now = timezone.now()
        existing = session.get('microsys_device') if hasattr(session, 'get') else {}
        if not isinstance(existing, dict):
            existing = {}

        try:
            previous_seen = timezone.datetime.fromisoformat(str(existing.get('last_seen') or ''))
            if timezone.is_naive(previous_seen):
                previous_seen = timezone.make_aware(previous_seen, timezone.get_current_timezone())
        except (TypeError, ValueError):
            previous_seen = None

        # Keep this cheap: refresh user-agent/IP immediately, but persist last_seen at most once per minute.
        if previous_seen and (now - previous_seen).total_seconds() < 60:
            return

        user_agent = str(request.META.get('HTTP_USER_AGENT') or '').strip()
        session['microsys_device'] = {
            'first_seen': existing.get('first_seen') or now.isoformat(),
            'last_seen': now.isoformat(),
            'ip_address': self._client_ip(request),
            'user_agent': user_agent[:320],
        }

    def _sync_auth_redirects(self):
        """
        Dynamically update LOGIN_REDIRECT_URL and LOGOUT_REDIRECT_URL
        based on the live system config.

        - LOGIN_REDIRECT_URL  → always points to home_url
        - LOGOUT_REDIRECT_URL → home_url when public_root is on,
                                 login page when public_root is off
        """
        try:
            from microsys.utils import get_system_config
            config = get_system_config()
            if not config.get('is_configured', False):
                return

            home_url = config.get('home_url') or DEFAULT_HOME_URL
            settings.LOGIN_REDIRECT_URL = home_url

            if config.get('public_root', False):
                settings.LOGOUT_REDIRECT_URL = home_url
            else:
                settings.LOGOUT_REDIRECT_URL = '/accounts/login/'
        except Exception:
            pass

    def __call__(self, request):
        _thread_locals.user = getattr(request, 'user', None)
        _thread_locals.request = request

        try:
            self._sync_auth_redirects()
            self._remember_session_device(request)

            if self._should_redirect_to_setup(request):
                return redirect('system_setup')

            response = self.get_response(request)

            root_redirect = self._root_redirect(request, response)
            if root_redirect is not None:
                return root_redirect

            return response
        finally:
            if hasattr(_thread_locals, 'user'):
                del _thread_locals.user
            if hasattr(_thread_locals, 'request'):
                del _thread_locals.request

# Backward-compatibility alias so we don't break existing projects
ActivityLogMiddleware = MicrosysMiddleware
