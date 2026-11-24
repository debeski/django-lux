"""The external API status shown on Options, probed by the task worker.

Web never opens the connection: the probe can wait on DNS well past its
socket timeout, and a generated stack gives web no route out. Options reads the
last result from the shared cache and asks the worker for a new one when it is
older than ``FRESH_SECONDS``.
"""
import logging
import time
import urllib.error
import urllib.request

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger("dlux")

CACHE_KEY = "dlux:api-status"
REFRESH_KEY = "dlux:api-status:refresh"
FRESH_SECONDS = 60
KEEP_SECONDS = 600
PROBE_TIMEOUT = 3
TASK_NAME = "dlux.tasks.api_status_probe"


def resolve_api_status_url():
    if getattr(settings, "DLUX_API_STATUS_URL", ""):
        return settings.DLUX_API_STATUS_URL
    if getattr(settings, "DLUX_API_URL", ""):
        return settings.DLUX_API_URL
    dlux_config = getattr(settings, "DLUX_CONFIG", {})
    if isinstance(dlux_config, dict):
        return dlux_config.get("api_status_url") or dlux_config.get("api_url") or ""
    return ""


def _result(state, url, note="", note_key="", note_context=None):
    return {
        "state": state,
        "url": url,
        "note": note,
        "note_key": note_key,
        "note_context": note_context or {},
        "checked_at": time.time(),
    }


def probe_api_status(url):
    """Open ``url`` once and describe the answer. Runs in the task worker."""
    request_obj = urllib.request.Request(url)
    api_key = getattr(settings, "X_API_KEY", "")
    secret_key = getattr(settings, "X_SECRET_KEY", "")
    if api_key:
        request_obj.add_header("X-API-KEY", api_key)
    if secret_key:
        request_obj.add_header("X-SECRET-KEY", secret_key)
    try:
        with urllib.request.urlopen(request_obj, timeout=PROBE_TIMEOUT) as response:
            if 200 <= response.status < 400:
                return _result("online", url)
            return _result(
                "degraded", url,
                note=f"Endpoint responded with HTTP {response.status}.",
                note_key="service_api_http_status",
                note_context={"status": response.status},
            )
    except urllib.error.HTTPError as exc:
        return _result(
            "degraded" if exc.code < 500 else "offline", url,
            note=f"Endpoint responded with HTTP {exc.code}.",
            note_key="service_api_http_status",
            note_context={"status": exc.code},
        )
    except Exception as exc:
        return _result(
            "offline", url,
            note=f"Error: {exc}",
            note_key="service_error_detail",
            note_context={"error": str(exc)},
        )


def refresh_api_status():
    """Probe the configured URL into the cache. The worker's task body."""
    url = resolve_api_status_url()
    if not url:
        cache.delete(CACHE_KEY)
        return None
    result = probe_api_status(url)
    cache.set(CACHE_KEY, result, KEEP_SECONDS)
    return result


def _request_refresh():
    if not cache.add(REFRESH_KEY, True, FRESH_SECONDS // 2):
        return True
    from ..taskrunner import enqueue, worker_alive

    if not worker_alive():
        cache.delete(REFRESH_KEY)
        return False
    try:
        enqueue(TASK_NAME)
        return True
    except Exception:
        cache.delete(REFRESH_KEY)
        logger.exception("Could not queue the API status probe.")
        return False


def cached_api_status():
    """The last probe of the configured URL, asking the worker for a new one when due.

    Returns None when no URL is configured. Otherwise a dict with ``state``
    (``online``/``degraded``/``offline``, or ``unknown`` before the first probe
    or without a worker), ``url``, ``note``, ``note_key``, ``note_context`` and
    ``checked_at`` (epoch seconds, None before the first probe).
    """
    url = resolve_api_status_url()
    if not url:
        return None
    saved = cache.get(CACHE_KEY)
    if not isinstance(saved, dict) or saved.get("url") != url:
        saved = None
    if saved is None or time.time() - float(saved.get("checked_at") or 0) >= FRESH_SECONDS:
        queued = _request_refresh()
        if saved is None:
            if not queued and settings.DEBUG:
                # A development server without a worker: nothing else would answer.
                return refresh_api_status()
            pending = _result(
                "unknown", url,
                note="Waiting for the task worker's check." if queued else "No task worker is running to check it.",
                note_key="service_api_pending" if queued else "service_api_no_worker",
            )
            pending["checked_at"] = None
            return pending
    return saved
