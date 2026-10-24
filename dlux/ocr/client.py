"""HTTP client for the stack's ``ocr`` service (``docker/ocr/server.py``).

The service is on the internal Compose network only; this never reaches a
public host, and ignores proxy environment variables on purpose.
"""

import json
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener

from django.core.cache import cache

from . import config

HEALTH_CACHE_KEY = 'dlux:ocr:health'
_opener = build_opener(ProxyHandler({}))


class OCRUnavailable(Exception):
    """The service is off, unreachable or busy; the same request may succeed later."""


class OCRRejected(Exception):
    """The service read the request and refused the file; retrying the same file will not help."""


def _json(raw):
    try:
        value = json.loads(raw.decode('utf-8') or '{}')
    except (ValueError, UnicodeDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def service_health(refresh=False):
    """Cached ``GET /health`` of the service, or ``None`` when OCR is off or it does not answer."""
    options = config()
    if not options['enabled']:
        return None
    key = f"{HEALTH_CACHE_KEY}:{options['service_url']}"
    if not refresh:
        cached = cache.get(key)
        if cached is not None:
            return cached or None
    try:
        with _opener.open(f"{options['service_url']}/health", timeout=3) as response:
            health = _json(response.read())
    except (OSError, ValueError):
        health = {}
    cache.set(key, health, 30)
    return health or None


def call_service(content, mode=None):
    """Send file bytes to ``POST /v1/ocr``; the provider call every OCR read goes through."""
    options = config()
    query = urlencode({'mode': mode or options['mode'], 'threads': options['threads']})
    request = Request(
        f"{options['service_url']}/v1/ocr?{query}", data=content, method='POST',
        headers={'Content-Type': 'application/octet-stream'},
    )
    try:
        with _opener.open(request, timeout=options['timeout']) as response:
            return _json(response.read())
    except HTTPError as exc:
        payload = _json(exc.read())
        message = payload.get('error') or f'OCR service returned {exc.code}'
        if exc.code in (429, 502, 503, 504):
            raise OCRUnavailable(message) from exc
        raise OCRRejected(message) from exc
    except (URLError, socket.timeout, ConnectionError) as exc:
        reason = getattr(exc, 'reason', exc)
        raise OCRUnavailable(f'OCR service unreachable: {reason.__class__.__name__}') from exc
