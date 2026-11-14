"""HTTP client for the stack's ``ocr`` service (``dlux.ocr.serve``).

The service is on the internal Compose network only; this never reaches a
public host, and ignores proxy environment variables on purpose.
"""

import json
import socket
from http.client import HTTPConnection
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPHandler, HTTPRedirectHandler, ProxyHandler, Request, build_opener

from django.core.cache import cache

from . import config

HEALTH_CACHE_KEY = 'dlux:ocr:health'
class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, file, code, message, headers, new_url):
        return None


class _EarlyAnswerConnection(HTTPConnection):
    """Reads the service's answer even when it stops reading the upload first.

    A busy service answers ``503`` and closes without reading the file, so the
    rest of the upload fails with a broken pipe or reset while the answer is
    already on the socket. Letting the send error pass hands ``getresponse`` that
    answer; a connection closed without one still fails there, as an outage.
    """

    def send(self, data):
        try:
            super().send(data)
        except (BrokenPipeError, ConnectionResetError):
            if self.sock is None:
                raise


class _EarlyAnswerHandler(HTTPHandler):
    def http_open(self, req):
        return self.do_open(_EarlyAnswerConnection, req)


_opener = build_opener(ProxyHandler({}), _NoRedirect(), _EarlyAnswerHandler())


class OCRUnavailable(Exception):
    """The service is off, unreachable or busy; the same request may succeed later."""


class OCRBusy(OCRUnavailable):
    """The engine is up but reading another file: it answered 429, or 503 with ``Retry-After``."""

    def __init__(self, message, retry_after=30):
        super().__init__(message)
        self.retry_after = retry_after


def _retry_after(headers):
    """The ``Retry-After`` seconds the service sent (1 to 300), or None when it sent none."""
    value = (headers.get('Retry-After') if headers is not None else None) or ''
    try:
        return min(max(int(str(value).strip()), 1), 300)
    except ValueError:
        return None


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
        wait = _retry_after(exc.headers)
        if exc.code == 429 or (exc.code == 503 and wait is not None):
            raise OCRBusy(message, retry_after=wait or 30) from exc
        if exc.code in (502, 503, 504):
            raise OCRUnavailable(message) from exc
        raise OCRRejected(message) from exc
    except (URLError, socket.timeout, ConnectionError) as exc:
        reason = getattr(exc, 'reason', exc)
        raise OCRUnavailable(f'OCR service unreachable: {reason.__class__.__name__}') from exc
