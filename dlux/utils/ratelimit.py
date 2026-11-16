"""Per-address and global limits for public form POSTs.

Public pages (reviews, complaints, contact forms) accept anonymous writes. Each
limited form is a *bucket* with two fixed-window cache counters: one per client
network and one for the whole bucket. A POST is counted against the address
first; only a POST still inside its address limit counts toward the global
limit, so one sender cannot spend the budget every other sender shares.

The address comes from ``get_client_ip()``, so the limiter follows the deployment's
Client IP policy. IPv6 addresses count per /64 network. Cache keys carry a keyed
HMAC of the network (``SECRET_KEY``-derived), never the address itself, and every
key expires when its window ends.

``DLUX_PUBLIC_FORM_LIMITS`` overrides a bucket's code values per deployment:
``{'complaint': {'per_address': 3, 'total': 150, 'window': 3600}}``. ``None``
turns that limit off.
"""

import functools
import ipaddress
import logging
import math
import re
import time
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import DEFAULT_CACHE_ALIAS, caches
from django.core.cache.backends.base import BaseCache
from django.http import HttpResponse, JsonResponse
from django.utils.cache import add_never_cache_headers
from django.utils.crypto import salted_hmac

from ..translations import get_current_language_code, get_strings
from .config import get_client_ip

logger = logging.getLogger('dlux')

CACHE_PREFIX = 'dlux:formlimit:'
SETTINGS_NAME = 'DLUX_PUBLIC_FORM_LIMITS'
DEFAULT_PER_ADDRESS = 5
DEFAULT_TOTAL = 300
DEFAULT_WINDOW = 3600
IPV6_PREFIX_LENGTH = 64
LIMIT_ADDRESS = 'address'
LIMIT_TOTAL = 'total'
MESSAGE_KEY = 'msg_public_form_rate_limited'

_BUCKET_PATTERN = re.compile(r'^[a-z0-9][a-z0-9_.-]{0,63}$')
_ADDRESS_HMAC_SALT = 'dlux.utils.ratelimit.address'
_warned_overrides = set()


@dataclass(frozen=True)
class PublicFormLimitResult:
    """Outcome of counting one public form POST.

    ``limit`` names the limit that refused it (``'address'`` or ``'total'``), or
    is ``None`` when the POST was allowed. ``retry_after`` is the number of
    seconds until the current window ends.
    """

    allowed: bool
    limit: str | None
    retry_after: int


def _check_bucket(bucket):
    if not isinstance(bucket, str) or not _BUCKET_PATTERN.match(bucket):
        raise ValueError(
            f'Public form bucket {bucket!r} must be 1-64 characters of a-z, 0-9, "_", "." or "-".'
        )
    return bucket


def _check_count(name, value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f'{name} must be a positive integer or None, not {value!r}.')
    return value


def _check_window(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f'window must be a positive number of seconds, not {value!r}.')
    return value


def _resolve_limits(bucket, per_address, total, window):
    """Apply the bucket's ``DLUX_PUBLIC_FORM_LIMITS`` override to the code values."""
    resolved = {'per_address': per_address, 'total': total, 'window': window}
    overrides = getattr(settings, SETTINGS_NAME, None) or {}
    override = overrides.get(bucket) if isinstance(overrides, dict) else None
    if not isinstance(override, dict):
        return resolved
    checks = {
        'per_address': lambda value: _check_count('per_address', value),
        'total': lambda value: _check_count('total', value),
        'window': _check_window,
    }
    for name, check in checks.items():
        if name not in override:
            continue
        try:
            resolved[name] = check(override[name])
        except ValueError as exc:
            if (bucket, name) not in _warned_overrides:
                _warned_overrides.add((bucket, name))
                logger.warning('%s[%r] ignored: %s', SETTINGS_NAME, bucket, exc)
    return resolved


def _network(address):
    """Return the network one sender controls: the IPv4 address or the IPv6 /64."""
    text = str(address or '').strip()
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        return text or 'unknown'
    if ip.version == 6:
        if ip.ipv4_mapped:
            return str(ip.ipv4_mapped)
        return str(ipaddress.IPv6Network((int(ip), IPV6_PREFIX_LENGTH), strict=False))
    return str(ip)


def _address_digest(address):
    return salted_hmac(_ADDRESS_HMAC_SALT, _network(address), algorithm='sha256').hexdigest()[:32]


def _increment(cache, key, ttl):
    """Count one hit on ``key``, which expires ``ttl`` seconds from its first hit."""
    if cache.add(key, 1, timeout=ttl):
        return 1
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=ttl)
        return 1
    if type(cache).incr is BaseCache.incr:
        # The generic incr() re-sets the key with the default timeout.
        cache.touch(key, ttl)
    return count


def count_public_form_post(
    request,
    bucket,
    *,
    per_address=DEFAULT_PER_ADDRESS,
    total=DEFAULT_TOTAL,
    window=DEFAULT_WINDOW,
):
    """Count one POST to ``bucket`` and say whether it stays inside the limits.

    Call it once per submission, before validating the form. A cache that cannot
    be reached lets the POST through and logs the error.
    """
    _check_bucket(bucket)
    limits = _resolve_limits(
        bucket,
        _check_count('per_address', per_address),
        _check_count('total', total),
        _check_window(window),
    )
    window = limits['window']
    now = time.time()
    index = int(now // window)
    retry_after = max(1, math.ceil((index + 1) * window - now))
    cache = caches[DEFAULT_CACHE_ALIAS]
    try:
        if limits['per_address'] is not None:
            key = f'{CACHE_PREFIX}{bucket}:a:{_address_digest(get_client_ip(request))}:{index}'
            count = _increment(cache, key, retry_after)
            if count > limits['per_address']:
                if count == limits['per_address'] + 1:
                    logger.warning('Public form %r: one sender reached its limit for this window.', bucket)
                return PublicFormLimitResult(False, LIMIT_ADDRESS, retry_after)
        if limits['total'] is not None:
            count = _increment(cache, f'{CACHE_PREFIX}{bucket}:t:{index}', retry_after)
            if count > limits['total']:
                if count == limits['total'] + 1:
                    logger.warning('Public form %r: the global limit is reached for this window.', bucket)
                return PublicFormLimitResult(False, LIMIT_TOTAL, retry_after)
    except Exception:
        logger.exception('Public form %r: the limit cache failed; the POST is allowed.', bucket)
    return PublicFormLimitResult(True, None, retry_after)


def _wants_json(request):
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return True
    accept = request.headers.get('accept', '')
    return 'application/json' in accept and 'text/html' not in accept


def rate_limited_response(request, result):
    """The default 429: the translated message as text, or JSON for script requests."""
    strings = get_strings(get_current_language_code(request))
    message = strings.get(MESSAGE_KEY, 'Too many submissions. Please try again later.')
    if _wants_json(request):
        response = JsonResponse({'status': 'error', 'message': message}, status=429)
    else:
        response = HttpResponse(message, status=429, content_type='text/plain; charset=utf-8')
    response['Retry-After'] = str(result.retry_after)
    add_never_cache_headers(response)
    return response


def public_form_limit(
    bucket,
    *,
    per_address=DEFAULT_PER_ADDRESS,
    total=DEFAULT_TOTAL,
    window=DEFAULT_WINDOW,
    methods=('POST',),
    on_limited=None,
):
    """Limit a view's POSTs per client address and in total.

    A refused request gets ``on_limited(request, result, *args, **kwargs)`` when
    given (to re-render the form with a notice; it should answer 429), else
    ``rate_limited_response()``. Other methods pass through uncounted.
    """
    _check_bucket(bucket)
    _check_count('per_address', per_address)
    _check_count('total', total)
    _check_window(window)
    limited_methods = frozenset(str(method).upper() for method in methods)

    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if request.method in limited_methods:
                result = count_public_form_post(
                    request, bucket, per_address=per_address, total=total, window=window,
                )
                if not result.allowed:
                    if on_limited is not None:
                        return on_limited(request, result, *args, **kwargs)
                    return rate_limited_response(request, result)
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


__all__ = [
    'DEFAULT_PER_ADDRESS',
    'DEFAULT_TOTAL',
    'DEFAULT_WINDOW',
    'LIMIT_ADDRESS',
    'LIMIT_TOTAL',
    'PublicFormLimitResult',
    'count_public_form_post',
    'public_form_limit',
    'rate_limited_response',
]
