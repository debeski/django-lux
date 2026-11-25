"""Keep a hung or unreachable Redis cache from hanging requests.

``dlux_settings()`` points every ``django_redis`` cache at
:class:`FailFastRedisCache`, caps its socket timeouts, and puts
``dlux.cache_outage.CacheOutageMiddleware`` just before the session middleware. ``DLUX_CACHE_FAIL_FAST =
False`` keeps the project's cache configuration exactly as written.

The policy while the cache does not answer:

* the first operation waits at most ``DLUX_CACHE_SOCKET_TIMEOUT`` seconds; the
  failure then opens a per-server breaker, and for ``RETRY_AFTER_SECONDS`` every
  operation raises :class:`CacheUnavailable` at once instead of waiting again;
* reads that only speed a page up go through :func:`safe_get`, :func:`safe_set`
  and :func:`safe_delete`, which treat an outage as a miss;
* everything else raises. Sessions live in this cache on generated stacks, and
  the login lockout, the 2FA codes and their cooldowns are security state, so
  none of them may quietly pretend to work. ``dlux.cache_outage`` turns that error into
  a 503 page that says the sign-in service is unavailable, instead of a 500
  after the old 20-second socket timeout had been paid several times over.
"""

import logging
import threading
import time

from django.core.cache import cache as default_cache
from django.core.cache.backends.base import DEFAULT_TIMEOUT

logger = logging.getLogger("dlux.cache")

RETRY_AFTER_SECONDS = 10.0

try:
    from django_redis.cache import RedisCache as _RedisCache
    from django_redis.exceptions import ConnectionInterrupted
    from redis.exceptions import ConnectionError as _RedisConnectionError
    from redis.exceptions import TimeoutError as _RedisTimeoutError
except ImportError:  # pragma: no cover - django_redis is optional
    _RedisCache = None
    ConnectionInterrupted = None
    _RedisConnectionError = OSError
    _RedisTimeoutError = TimeoutError


class CacheUnavailable(_RedisConnectionError):
    """The cache server did not answer, or did not answer recently."""


_OUTAGE_ERRORS = tuple(
    error for error in (
        CacheUnavailable, _RedisConnectionError, _RedisTimeoutError, ConnectionInterrupted,
        TimeoutError, ConnectionError,
    ) if error is not None
)

_breaker_lock = threading.Lock()
_open_until = {}


def _now():
    return time.monotonic()


def breaker_open(server):
    """Seconds left before ``server`` is tried again, or 0 when it is tried now."""
    remaining = _open_until.get(server, 0.0) - _now()
    return remaining if remaining > 0 else 0.0


def _trip(server, exc):
    with _breaker_lock:
        first = server not in _open_until
        _open_until[server] = _now() + RETRY_AFTER_SECONDS
    if first:
        logger.warning(
            "The cache at %s did not answer (%s: %s); cache operations fail at once "
            "for the next %d seconds.",
            server, type(exc).__name__, exc, RETRY_AFTER_SECONDS,
        )


def _recover(server):
    if server not in _open_until:
        return
    with _breaker_lock:
        if _open_until.pop(server, None) is None:
            return
    logger.warning("The cache at %s answers again.", server)


def reset_breakers():
    with _breaker_lock:
        _open_until.clear()


def is_cache_outage(exc):
    """True when ``exc``, or an exception it was raised from, is a cache outage."""
    seen = set()
    while exc is not None and id(exc) not in seen:
        if isinstance(exc, CacheUnavailable):
            return True
        if isinstance(exc, _OUTAGE_ERRORS) and _raised_by_cache(exc):
            return True
        seen.add(id(exc))
        exc = exc.__cause__ or exc.__context__
    return False


def _raised_by_cache(exc):
    module = type(exc).__module__ or ""
    return module.startswith(("redis", "django_redis"))


if _RedisCache is not None:
    _WRAPPED = (
        "get", "_get", "set", "add", "delete", "delete_many", "delete_pattern", "clear",
        "get_many", "set_many", "incr", "decr", "has_key", "keys", "iter_keys", "ttl",
        "pttl", "persist", "expire", "expire_at", "pexpire", "pexpire_at", "lock",
        "touch", "incr_version",
    )

    def _guard(method):
        def guarded(self, *args, **kwargs):
            server = self._server_label
            remaining = breaker_open(server)
            if remaining:
                raise CacheUnavailable(
                    f"The cache at {server} did not answer; retrying in {remaining:.0f} s."
                )
            try:
                result = method(self, *args, **kwargs)
            except CacheUnavailable:
                raise
            except _OUTAGE_ERRORS as exc:
                _trip(server, exc)
                raise CacheUnavailable(f"The cache at {server} did not answer: {exc}") from exc
            _recover(server)
            return result

        guarded.__name__ = method.__name__
        guarded.__qualname__ = method.__qualname__
        guarded.__doc__ = method.__doc__
        return guarded

    class FailFastRedisCache(_RedisCache):
        """``django_redis``'s cache with a per-server circuit breaker.

        Data, keys and serialization are exactly ``django_redis``'s, so switching
        to it keeps every session and cached value.
        """

        def __init__(self, server, params):
            super().__init__(server, params)
            servers = server if isinstance(server, (list, tuple)) else str(server).split(",")
            self._server_label = ",".join(_redact(entry) for entry in servers)

    for _name in _WRAPPED:
        if hasattr(_RedisCache, _name):
            setattr(FailFastRedisCache, _name, _guard(getattr(_RedisCache, _name)))
    del _name


def _redact(location):
    """``redis://:secret@host:6379/1`` without the password."""
    text = str(location).strip()
    if "@" in text and "://" in text:
        scheme, rest = text.split("://", 1)
        return f"{scheme}://{rest.rsplit('@', 1)[1]}"
    return text


def safe_get(key, default=None, *, cache=None):
    """``cache.get`` for a value that only saves work: an outage is a miss."""
    try:
        return (cache or default_cache).get(key, default)
    except Exception as exc:
        _log_tolerated("read", key, exc)
        return default


def safe_set(key, value, timeout=DEFAULT_TIMEOUT, *, cache=None):
    """``cache.set`` that drops the value when the cache is down."""
    try:
        (cache or default_cache).set(key, value, timeout)
        return True
    except Exception as exc:
        _log_tolerated("write", key, exc)
        return False


def safe_delete(key, *, cache=None):
    try:
        return bool((cache or default_cache).delete(key))
    except Exception as exc:
        _log_tolerated("delete", key, exc)
        return False


def _log_tolerated(action, key, exc):
    if is_cache_outage(exc):
        logger.debug("Cache %s of %r skipped: %s", action, key, exc)
    else:
        logger.warning("Cache %s of %r failed; continuing without it.", action, key, exc_info=True)
