
import threading
import time
from django.conf import settings
from django.contrib.auth import logout
from django.core.exceptions import SuspiciousOperation
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse

from .system.constants import DEFAULT_HOME_URL
from .fonts import clear_font_cache

_thread_locals = threading.local()

def get_current_user():
    return getattr(_thread_locals, 'user', None)

def get_current_request():
    return getattr(_thread_locals, 'request', None)

class DluxMiddleware:
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
        configured_prefixes = getattr(settings, 'DLUX_SETUP_GUARD_ALLOWED_PREFIXES', ()) or ()
        if isinstance(configured_prefixes, str):
            configured_prefixes = (configured_prefixes,)
        allowed_prefixes.extend(
            str(prefix).strip()
            for prefix in configured_prefixes
            if str(prefix).strip().startswith('/')
        )

        try:
            allowed_exact_paths.update({
                reverse('login'),
                reverse('logout'),
                reverse('session_ended'),
                reverse('dlux_update_runtime_health'),
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
                '/sys/api/dlux-update/runtime-health/',
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
            from dlux.utils import get_system_config
            config = get_system_config()
            if isinstance(config, dict):
                return config
        except Exception:
            pass

        fallback = getattr(settings, 'DLUX_CONFIG', {})
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

        When the public page is disabled, anonymous users are sent to the
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

        # When public page access is off, anonymous users must log in first.
        user = getattr(request, 'user', None)
        is_authenticated = bool(user and getattr(user, 'is_authenticated', False))
        if not targets['public_enabled']:
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
        from .utils import normalize_homepage_config

        homepage = normalize_homepage_config(config.get('homepage_config') or config)
        public = homepage['public']
        home_url = homepage['default_url']
        public_root_url = public['url'] or home_url
        anonymous_public_target = public_root_url if public['separate_url'] else home_url
        return {
            'home_url': home_url,
            'public_enabled': public['enabled'],
            'anonymous_public_target': anonymous_public_target,
        }

    def _remember_session_device(self, request):
        from .auth.session_history import remember_request_presence

        remember_request_presence(request)

    def _signed_out_redirect(self, request):
        """If this anonymous request is carrying a session cookie whose session was
        force-revoked (single-session eviction or a remote sign-out), send the browser to
        the 'signed out' interstitial instead of silently bouncing it to the login form."""
        if request.method != 'GET':
            return None
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return None
        user = getattr(request, 'user', None)
        if user is not None and getattr(user, 'is_authenticated', False):
            return None
        cookie_name = getattr(settings, 'SESSION_COOKIE_NAME', 'sessionid')
        raw_session_key = request.COOKIES.get(cookie_name)
        if not raw_session_key:
            return None
        try:
            ended_path = reverse('session_ended')
        except Exception:
            ended_path = '/accounts/session-ended/'
        if request.path == ended_path:
            return None
        for prefix in (getattr(settings, 'STATIC_URL', None), getattr(settings, 'MEDIA_URL', None)):
            prefix = str(prefix or '').strip()
            # Ignore a bare "/" prefix (a common MEDIA_URL default) — it would match every path.
            if prefix and prefix != '/' and request.path.startswith(prefix):
                return None
        from .auth.session_history import clear_session_revoked_flag, get_session_revoked_reason
        reason = get_session_revoked_reason(raw_session_key)
        if not reason:
            return None
        # One-shot: clear it now (we still have the cookie here; by the time the browser
        # reaches the interstitial the stale session cookie has been dropped) so the
        # interstitial doesn't recur.
        clear_session_revoked_flag(raw_session_key)
        return redirect(f'{ended_path}?reason={reason}')

    def _session_timeout_response(self, request):
        """Enforce idle + absolute session timeouts beyond Django's SESSION_COOKIE_AGE.

        Both windows are opt-in via settings (0 = disabled):
        - DLUX_SESSION_IDLE_TIMEOUT_SECONDS      (sliding inactivity window)
        - DLUX_SESSION_ABSOLUTE_TIMEOUT_SECONDS  (hard cap from first authed request)

        Timestamps are middleware-managed on the session, so no login-view changes
        are needed. On expiry we log out and route to the session-ended interstitial.
        """
        user = getattr(request, 'user', None)
        if not (user and getattr(user, 'is_authenticated', False)):
            return None
        session = getattr(request, 'session', None)
        if session is None:
            return None

        # Don't trip the timeout on asset requests that happen to carry the cookie.
        for prefix in (getattr(settings, 'STATIC_URL', None), getattr(settings, 'MEDIA_URL', None)):
            prefix = str(prefix or '').strip()
            if prefix and prefix != '/' and request.path.startswith(prefix):
                return None

        try:
            idle = int(getattr(settings, 'DLUX_SESSION_IDLE_TIMEOUT_SECONDS', 0) or 0)
            absolute = int(getattr(settings, 'DLUX_SESSION_ABSOLUTE_TIMEOUT_SECONDS', 0) or 0)
        except (TypeError, ValueError):
            return None

        # The admin-configurable inactivity timeout (auth_config) overrides the
        # static idle setting when enabled: the client shows a countdown warning,
        # and this server-side check is the authoritative backstop.
        try:
            from dlux.utils import get_system_config
            config = get_system_config()
            if config.get('inactivity_timeout_enabled'):
                idle = max(0, int(config.get('inactivity_timeout_minutes', 10) or 10)) * 60
        except Exception:
            pass

        if idle <= 0 and absolute <= 0:
            return None

        now = time.time()
        started = session.get('dlux_session_started_at')
        if not started:
            # First authenticated request under an active policy — anchor the clocks.
            session['dlux_session_started_at'] = now
            session['dlux_last_activity'] = now
            return None
        last = session.get('dlux_last_activity', now)

        reason = None
        try:
            if absolute > 0 and (now - float(started)) > absolute:
                reason = 'session_timeout'
            elif idle > 0 and (now - float(last)) > idle:
                reason = 'idle_timeout'
        except (TypeError, ValueError):
            reason = None

        if reason:
            logout(request)
            try:
                ended_path = reverse('session_ended')
            except Exception:
                ended_path = '/accounts/session-ended/'
            return redirect(f'{ended_path}?reason={reason}')

        # Refresh the idle clock, throttled to ~once per 30s to avoid a write per request.
        try:
            if now - float(last or 0) > 30:
                session['dlux_last_activity'] = now
        except (TypeError, ValueError):
            session['dlux_last_activity'] = now
        return None

    def _apply_session_cookie_policy(self, request):
        """Apply ``purge_session_on_exit``: when on, make the session cookie a
        browser-session cookie (no persistent Max-Age) so the next browser session
        requires authentication. Individual tabs share that cookie and cannot expire
        it independently. A session marker keeps this to a single write and lets us
        restore the persistent lifetime if the admin turns the policy back off.
        """
        user = getattr(request, 'user', None)
        if not (user and getattr(user, 'is_authenticated', False)):
            return
        session = getattr(request, 'session', None)
        if session is None:
            return
        try:
            from dlux.utils import get_system_config
            purge = bool(get_system_config().get('purge_session_on_exit', False))
        except Exception:
            return
        applied = session.get('dlux_expire_on_close')
        if purge and not applied:
            session.set_expiry(0)  # 0 → expire at browser close
            session['dlux_expire_on_close'] = True
        elif not purge and applied:
            session.set_expiry(None)  # restore global SESSION_COOKIE_AGE
            session.pop('dlux_expire_on_close', None)

    def _force_password_change_response(self, request):
        user = getattr(request, 'user', None)
        if not (user and getattr(user, 'is_authenticated', False)):
            return None

        for prefix in (getattr(settings, 'STATIC_URL', None), getattr(settings, 'MEDIA_URL', None)):
            prefix = str(prefix or '').strip()
            if prefix and prefix != '/' and request.path.startswith(prefix):
                return None

        profile = getattr(user, 'profile', None)
        preferences = getattr(profile, 'preferences', {}) if profile is not None else {}
        if not (isinstance(preferences, dict) and preferences.get('force_password_change')):
            return None

        try:
            profile_path = reverse('user_profile')
            logout_path = reverse('logout')
            session_ended_path = reverse('session_ended')
        except Exception:
            profile_path = '/accounts/profile/'
            logout_path = '/accounts/logout/'
            session_ended_path = '/accounts/session-ended/'

        if request.path in {profile_path, logout_path, session_ended_path}:
            return None

        redirect_url = f'{profile_path}?force_password_change=1'
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            try:
                from dlux.translations import get_strings
                message = get_strings().get('force_password_change_required', 'You must change your password before continuing.')
            except Exception:
                message = 'You must change your password before continuing.'
            return JsonResponse({
                'success': False,
                'error': message,
                'redirect': redirect_url,
                'redirect_url': redirect_url,
            }, status=403)
        return redirect(redirect_url)

    def _activate_display_language(self, request):
        """Make Django's language machinery agree with the Dlux UI language.

        Django's ``LocaleMiddleware`` runs *before* ``AuthenticationMiddleware``,
        so it resolves ``request.LANGUAGE_CODE`` from the ``Accept-Language``
        header / default before the user's profile is known — an English browser
        on an Arabic account ends up with ``LANGUAGE_CODE='en'`` even though the
        Dlux UI is Arabic. ``DluxMiddleware`` runs *after* auth, so here we
        re-resolve with Dlux's own rules (session preview → profile preference →
        session → config default) and re-activate, overriding that early guess for
        the rest of the request. This keeps ``request.LANGUAGE_CODE``,
        ``translation.get_language()`` (activity-log labels, etc.), and
        ``FORMAT_MODULE_PATH`` (``dlux.formats`` date/number formats) all in sync
        with the language the user actually chose. No per-request deactivate — like
        Django's own LocaleMiddleware, every request re-activates.
        """
        try:
            from django.utils import translation
            from dlux.translations import get_current_language_code
            lang = get_current_language_code(request)
            if lang:
                translation.activate(lang)
                request.LANGUAGE_CODE = lang
        except Exception:
            pass

    @staticmethod
    def _login_url():
        """The login page's real path, wherever `dlux.urls` is mounted.

        A hardcoded '/accounts/login/' is only correct for a project that mounts
        dlux at the root. Both sales-crm editions mount it under `/staff/`, so
        logging out sent them to a URL that 404s. `reverse()` reads the
        URLconf, so the prefix comes along.
        """
        from django.urls import NoReverseMatch, reverse

        try:
            return reverse('login')
        except NoReverseMatch:
            return '/accounts/login/'

    def _sync_auth_redirects(self):
        """
        Dynamically update LOGIN_REDIRECT_URL and LOGOUT_REDIRECT_URL
        based on the live system config.

        - LOGIN_REDIRECT_URL  → always points to home_url
        - LOGOUT_REDIRECT_URL → anonymous public destination when
                                 public page access is on, login page when
                                 public page access is off
        """
        try:
            from dlux.utils import get_system_config
            config = get_system_config()
            if not config.get('is_configured', False):
                return

            targets = self._resolve_root_targets(config)
            settings.LOGIN_REDIRECT_URL = targets['home_url']

            # `LOGOUT_REDIRECT_URL` is rewritten here on every request, so a
            # project cannot express a preference through it — its value would be
            # ours by the second request. `DLUX_LOGOUT_REDIRECT_URL` is the
            # project's to set and dlux only ever reads it.
            override = getattr(settings, 'DLUX_LOGOUT_REDIRECT_URL', None)
            if override is not None:
                settings.LOGOUT_REDIRECT_URL = override
            elif config.get('public_root', False):
                settings.LOGOUT_REDIRECT_URL = targets['anonymous_public_target']
            else:
                settings.LOGOUT_REDIRECT_URL = self._login_url()
        except Exception:
            pass

    def __call__(self, request):
        _thread_locals.user = getattr(request, 'user', None)
        _thread_locals.request = request
        clear_font_cache()

        try:
            self._activate_display_language(request)
            self._sync_auth_redirects()
            self._remember_session_device(request)

            signed_out_redirect = self._signed_out_redirect(request)
            if signed_out_redirect is not None:
                return signed_out_redirect

            timeout_redirect = self._session_timeout_response(request)
            if timeout_redirect is not None:
                return timeout_redirect

            self._apply_session_cookie_policy(request)

            setup_redirect = self._setup_redirect_response(request)
            if setup_redirect is not None:
                from .auth.session_history import attach_presence_cookie

                return attach_presence_cookie(setup_redirect, request)

            force_password_redirect = self._force_password_change_response(request)
            if force_password_redirect is not None:
                from .auth.session_history import attach_presence_cookie

                return attach_presence_cookie(force_password_redirect, request)

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
                from .auth.session_history import attach_presence_cookie

                return attach_presence_cookie(root_redirect, request)

            from .auth.session_history import attach_presence_cookie

            self._remember_session_device(request)
            attach_presence_cookie(response, request)
            return response
        finally:
            if hasattr(_thread_locals, 'user'):
                del _thread_locals.user
            if hasattr(_thread_locals, 'request'):
                del _thread_locals.request

# Backward-compatibility alias so we don't break existing projects
ActivityLogMiddleware = DluxMiddleware
