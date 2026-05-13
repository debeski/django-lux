
import threading
from django.conf import settings
from django.contrib.auth import logout
from django.core.exceptions import SuspiciousOperation
from django.http import JsonResponse
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

    @staticmethod
    def _path_directory(path):
        if not path:
            return ''
        trimmed = path[:-1] if path.endswith('/') else path
        if '/' not in trimmed:
            return path
        return trimmed.rsplit('/', 1)[0] + '/'

    def _setup_guard_allowed(self, request):
        allowed_exact_paths = set()
        allowed_prefixes = [
            getattr(settings, 'STATIC_URL', '/static/') or '/static/',
            getattr(settings, 'MEDIA_URL', '/media/') or '/media/',
        ]

        try:
            allowed_exact_paths.update({
                reverse('login'),
                reverse('logout'),
            })
            allowed_prefixes.extend([
                reverse('system_setup'),
                self._path_directory(reverse('update_preferences')),
                self._path_directory(reverse('verify_otp_generic')),
            ])
        except Exception:
            allowed_exact_paths.update({
                '/accounts/login/',
                '/accounts/logout/',
            })
            allowed_prefixes.extend([
                '/sys/setup/',
                '/sys/api/preferences/',
                '/sys/2fa/',
            ])

        if request.path in allowed_exact_paths:
            return True
        return any(prefix and request.path.startswith(prefix) for prefix in allowed_prefixes)

    @staticmethod
    def _load_system_config():
        try:
            from microsys.utils import get_system_config
            config = get_system_config()
            if isinstance(config, dict):
                return config
        except Exception:
            pass

        fallback = getattr(settings, 'MICROSYS_CONFIG', {})
        return fallback if isinstance(fallback, dict) else {}

    def _should_redirect_to_setup(self, request):
        return self._setup_redirect_response(request) is not None

    def _setup_redirect_response(self, request):
        if self._setup_guard_allowed(request):
            return None

        config = self._load_system_config()
        if config.get('is_configured', False):
            return None

        user = getattr(request, 'user', None)
        if user and getattr(user, 'is_authenticated', False):
            if bool(getattr(user, 'is_superuser', False)):
                return redirect('system_setup')
            if hasattr(request, 'session'):
                logout(request)
            return redirect('login')

        return redirect('login')

    def _root_redirect(self, request, response):
        """
        Handle root URL hijacking.

        If the dev has no view at '/' (response is 404), redirect to
        the configured root destination during system setup. If the system
        is not yet configured, redirect to the setup wizard instead.

        When public_root is disabled, anonymous users are sent to the
        login page instead of the public destination.

        If the dev DOES have a view at '/' (response is not 404),
        this method returns None and the middleware stays out of the way.
        """
        if response.status_code != 404 or request.path != '/':
            return None

        config = self._load_system_config()

        if not config.get('is_configured', False):
            return redirect('system_setup')

        targets = self._resolve_root_targets(config)
        home_url = targets['home_url']

        # When public_root is off, anonymous users must log in first
        user = getattr(request, 'user', None)
        is_authenticated = bool(user and getattr(user, 'is_authenticated', False))
        if not config.get('public_root', False):
            if not is_authenticated:
                return redirect('login')
            if home_url and home_url != '/':
                return redirect(home_url)
            return None

        target_url = home_url if is_authenticated else targets['anonymous_public_target']
        if target_url and target_url != '/':
            return redirect(target_url)

        return None

    @staticmethod
    def _resolve_root_targets(config):
        home_url = str(config.get('home_url') or DEFAULT_HOME_URL).strip() or DEFAULT_HOME_URL
        public_root_split_enabled = bool(config.get('public_root_split_enabled', False))
        public_root_url = str(config.get('public_root_url') or '').strip() or home_url
        anonymous_public_target = public_root_url if public_root_split_enabled else home_url
        return {
            'home_url': home_url,
            'anonymous_public_target': anonymous_public_target,
        }

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
        - LOGOUT_REDIRECT_URL → anonymous public destination when
                                 public_root is on, login page when
                                 public_root is off
        """
        try:
            from microsys.utils import get_system_config
            config = get_system_config()
            if not config.get('is_configured', False):
                return

            targets = self._resolve_root_targets(config)
            settings.LOGIN_REDIRECT_URL = targets['home_url']

            if config.get('public_root', False):
                settings.LOGOUT_REDIRECT_URL = targets['anonymous_public_target']
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

            setup_redirect = self._setup_redirect_response(request)
            if setup_redirect is not None:
                return setup_redirect

            try:
                response = self.get_response(request)
            except SuspiciousOperation as exc:
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'error': f'Bad request: {exc.__class__.__name__}',
                    }, status=400)
                raise

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
