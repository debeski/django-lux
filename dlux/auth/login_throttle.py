"""Cache-based failed-login lockout for the password step.

Dependency-free brute-force protection that mirrors the existing throttle style
used by registration (``registration.py``) and the 2FA per-IP limiter
(``views/twofa.py``): plain Django cache counters, no third-party packages.

Every password attempt reserves a slot in two rolling counters — one keyed on
the client IP, one on the attempted username — before the password is checked.
The reservation is an atomic ``cache.incr``, so a parallel burst cannot read the
same count: once the threshold is reached, the attempts past it are refused
without a password check. A failure that brings a counter to the threshold arms
a separate lock key for the lock duration; a successful login clears both.

The username key is the NFKC-normalised, case-folded username, the same
normalisation Django's login form applies before authenticating, so
compatibility spellings (full-width letters, ``＿``) share one counter.

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
import unicodedata

from django.conf import settings
from django.core.cache import cache

CACHE_PREFIX = 'dlux:login:count:'
LOCK_PREFIX = 'dlux:login:lock:'
RESERVATION_ATTR = '_dlux_login_reservation'
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


def normalize_login_username(username):
    """Return the lockout key form of a submitted username.

    Django's ``UsernameField`` NFKC-normalises the value before authenticating;
    case-folding on top makes ``Admin`` and ``admin`` share a counter as well.
    """
    value = unicodedata.normalize('NFKC', str(username or '')).strip()
    if '@' in value:
        value = _username_for_email(value) or value
    return unicodedata.normalize('NFKC', value.casefold())


def _username_for_email(value):
    """Resolve an email the login form would accept to the account's username."""
    try:
        from django.contrib.auth import get_user_model
        from dlux.auth.registration import public_registration_config
        if not public_registration_config().get('enabled'):
            return None
        User = get_user_model()
        match = User._default_manager.filter(email__iexact=value).first()
        return unicodedata.normalize('NFKC', match.get_username()).strip() if match else None
    except Exception:
        return None


def _keys(request, username):
    keys = [f'{CACHE_PREFIX}ip:{_client_ip(request)}']
    uname = normalize_login_username(username)
    if uname:
        keys.append(f'{CACHE_PREFIX}user:{uname}')
    return keys


def _lock_key(counter_key):
    return LOCK_PREFIX + counter_key[len(CACHE_PREFIX):]


def _lock_remaining(counter_key, now):
    locked_until = cache.get(_lock_key(counter_key))
    try:
        return max(int(float(locked_until or 0) - now), 0)
    except (TypeError, ValueError):
        return 0


def _increment(key, window):
    """Atomically add one to ``key`` and return the new count."""
    cache.add(key, 0, timeout=window)
    try:
        count = cache.incr(key)
    except ValueError:
        # Expired between add and incr.
        cache.add(key, 0, timeout=window)
        count = cache.incr(key)
    cache.touch(key, window)
    return int(count)


def login_lockout_remaining(request, username):
    """Return seconds remaining if the IP or username is currently locked, else 0."""
    if not _enabled():
        return 0
    now = time.time()
    return max((_lock_remaining(key, now) for key in _keys(request, username)), default=0)


def reserve_login_attempt(request, username):
    """Reserve one password check for this IP and username.

    Returns 0 when the attempt may go ahead, else the seconds to show the user.
    The reservation is kept on the request so ``register_failed_login`` arms the
    lock from the same counts instead of incrementing again.
    """
    if not _enabled():
        return 0
    threshold = _max_attempts()
    window = _window_seconds()
    counts = {key: _increment(key, window) for key in _keys(request, username)}
    if request is not None:
        setattr(request, RESERVATION_ATTR, counts)
    if all(count <= threshold for count in counts.values()):
        return 0
    now = time.time()
    remaining = 0
    for key, count in counts.items():
        if count > threshold:
            remaining = max(remaining, _lock_remaining(key, now) or _lockout_seconds())
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
        import logging
        logging.getLogger('dlux').warning('Could not write the failed sign-in audit event', exc_info=True)


def register_failed_login(request, username):
    """Count a failed attempt; arm the lock when a counter reaches the threshold."""
    if not _enabled():
        return
    counts = getattr(request, RESERVATION_ATTR, None) if request is not None else None
    if counts is None:
        reserve_login_attempt(request, username)
        counts = getattr(request, RESERVATION_ATTR, None) or {}
    if request is not None and hasattr(request, RESERVATION_ATTR):
        delattr(request, RESERVATION_ATTR)
    threshold = _max_attempts()
    window = _window_seconds()
    duration = _lockout_seconds()
    now = time.time()
    newly_locked = False
    for key, count in counts.items():
        if count < threshold:
            continue
        if cache.add(_lock_key(key), now + duration, timeout=duration):
            newly_locked = True
        # After the lock ends one more attempt is checked before it re-arms;
        # the counter outlives the lock so it still counts toward the next one.
        cache.set(key, threshold - 1, timeout=duration + window)
    _log_failed_login(request, username, locked=newly_locked)


def clear_failed_logins(request, username):
    """Reset counters after a successful authentication."""
    for key in _keys(request, username):
        cache.delete(key)
        cache.delete(_lock_key(key))
