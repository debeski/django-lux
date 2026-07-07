"""Cache-based failed-login lockout for the password step.

Dependency-free brute-force protection that mirrors the existing throttle style
used by registration (``registration.py``) and the 2FA per-IP limiter
(``views/twofa.py``): plain Django cache counters, no third-party packages.

A failed password attempt increments two rolling counters — one keyed on the
client IP, one on the attempted username — each with a TTL equal to the lockout
window. Once either counter reaches the configured threshold the key is "locked"
until ``locked_until``. A successful login clears both counters.

Config (SystemSettings ``auth_config``, resolved via get_system_config):
- ``login_lockout_enabled``          -> on/off toggle
- ``login_lockout_threshold``        -> failed attempts before the lock arms (default 5)
- ``login_lockout_window_minutes``   -> rolling window counting failures (default 15)
- ``login_lockout_duration_minutes`` -> how long the lock lasts once armed (default 15)

The legacy Django-settings knobs (``DLUX_LOGIN_LOCKOUT_MAX_ATTEMPTS`` /
``DLUX_LOGIN_LOCKOUT_SECONDS``) remain only as a fallback when the system config
cannot be resolved at all — the admin-configurable values supersede them.
"""

import time

from django.conf import settings
from django.core.cache import cache

CACHE_PREFIX = 'dlux:login:fail:'
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_LOCKOUT_SECONDS = 15 * 60


def _settings_fallback_attempts():
    try:
        return max(int(getattr(settings, 'DLUX_LOGIN_LOCKOUT_MAX_ATTEMPTS', DEFAULT_MAX_ATTEMPTS)), 1)
    except (TypeError, ValueError):
        return DEFAULT_MAX_ATTEMPTS


def _settings_fallback_seconds():
    try:
        return max(int(getattr(settings, 'DLUX_LOGIN_LOCKOUT_SECONDS', DEFAULT_LOCKOUT_SECONDS)), 1)
    except (TypeError, ValueError):
        return DEFAULT_LOCKOUT_SECONDS


def _max_attempts():
    try:
        from dlux.utils import get_system_config
        return max(int(get_system_config().get('login_lockout_threshold', 5)), 1)
    except Exception:
        return _settings_fallback_attempts()


def _window_seconds():
    """Rolling window (seconds) during which failed attempts accumulate."""
    try:
        from dlux.utils import get_system_config
        return max(int(get_system_config().get('login_lockout_window_minutes', 15)), 1) * 60
    except Exception:
        return _settings_fallback_seconds()


def _lockout_seconds():
    """How long (seconds) the lock lasts once the threshold is reached."""
    try:
        from dlux.utils import get_system_config
        return max(int(get_system_config().get('login_lockout_duration_minutes', 15)), 1) * 60
    except Exception:
        return _settings_fallback_seconds()


def _enabled():
    """Resolve the SystemSettings/DLUX_CONFIG toggle, defaulting to on."""
    try:
        from dlux.utils import get_system_config
        return bool(get_system_config().get('login_lockout_enabled', True))
    except Exception:
        return True


def _client_ip(request):
    try:
        from dlux.utils import get_client_ip
        return get_client_ip(request) or 'unknown'
    except Exception:
        return 'unknown'


def _keys(request, username):
    keys = [f'{CACHE_PREFIX}ip:{_client_ip(request)}']
    uname = str(username or '').strip().lower()
    if uname:
        keys.append(f'{CACHE_PREFIX}user:{uname}')
    return keys


def login_lockout_remaining(request, username):
    """Return seconds remaining if the IP or username is currently locked, else 0."""
    if not _enabled():
        return 0
    now = time.time()
    threshold = _max_attempts()
    remaining = 0
    for key in _keys(request, username):
        data = cache.get(key)
        if not data:
            continue
        if int(data.get('count', 0)) >= threshold:
            locked_for = int(float(data.get('locked_until', 0)) - now)
            if locked_for > 0:
                remaining = max(remaining, locked_for)
    return remaining


def _log_failed_login(request, username, locked):
    """Record a failed-login (and, on threshold, a lockout) audit event."""
    try:
        from dlux.utils import log_audit_event
        uname = str(username or '').strip()[:50] or None
        log_audit_event(request, 'login_failed', 'LOGIN_FAILED', model_name='auth', number=uname)
        if locked:
            log_audit_event(request, 'lockout', 'LOCKOUT', model_name='auth', number=uname)
    except Exception:
        pass


def register_failed_login(request, username):
    """Increment failure counters; arm the lockout when the threshold is reached."""
    if not _enabled():
        return
    now = time.time()
    threshold = _max_attempts()
    window = _window_seconds()
    duration = _lockout_seconds()
    newly_locked = False
    for key in _keys(request, username):
        data = cache.get(key) or {'count': 0, 'locked_until': 0}
        data['count'] = int(data.get('count', 0)) + 1
        if data['count'] >= threshold:
            if not data.get('locked_until'):
                newly_locked = True
            data['locked_until'] = now + duration
            # The key must outlive the lock even when the lock lasts longer
            # than the counting window.
            cache.set(key, data, timeout=max(window, duration))
        else:
            cache.set(key, data, timeout=window)
    _log_failed_login(request, username, locked=newly_locked)


def clear_failed_logins(request, username):
    """Reset counters after a successful authentication."""
    for key in _keys(request, username):
        cache.delete(key)
