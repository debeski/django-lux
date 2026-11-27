"""The 503 a request gets when the database cannot serve it.

Two cases answer 503 instead of a 500 or a hung request:

- the database is down, full or read-only: the request raised a connection,
  resource or read-only error (``is_database_outage``);
- a system restore is replacing the data: every request except the restore's own
  status polls is turned away until it ends (``restore_in_progress``), because the
  restore's single transaction holds row locks that most pages wait on.

``DatabaseOutageMiddleware`` sits just outside the session middleware, like
``CacheOutageMiddleware``. Its page is built without the database or the session,
since either may be what is down.
"""

import logging
import sys
import time

from django.conf import settings
from django.core.signals import got_request_exception
from django.db import utils as db_utils

logger = logging.getLogger("dlux.db")

DATABASE_RETRY_AFTER_SECONDS = 15
RESTORE_RETRY_AFTER_SECONDS = 30
RESTORE_FLAG_KEY = "dlux:restore:in-progress"
# A restore refreshes the flag on every progress report; a worker that died
# mid-restore stops refreshing it, so the site reopens on its own.
RESTORE_FLAG_TTL_SECONDS = 300
RESTORE_ALLOWED_URL_NAMES = frozenset({"system_restore_status", "system_restore_list_status"})

# SQLSTATE classes and codes that mean "the database cannot serve this now",
# not "this query is wrong": connection exceptions, insufficient resources,
# operator intervention (shutdown, cannot connect now, statement timeout) and a
# read-only transaction.
_OUTAGE_SQLSTATE_CLASSES = ("08", "53", "57")
_OUTAGE_SQLSTATES = frozenset({"25006"})


def _sqlstate(exc):
    for candidate in (exc, getattr(exc, "__cause__", None)):
        if candidate is None:
            continue
        code = getattr(candidate, "sqlstate", None) or getattr(candidate, "pgcode", None)
        if code:
            return str(code)
    return ""


def is_database_outage(exc):
    """Whether ``exc`` says the database is unavailable rather than the query wrong."""
    if not isinstance(exc, db_utils.Error):
        return False
    code = _sqlstate(exc)
    if code:
        return code in _OUTAGE_SQLSTATES or code[:2] in _OUTAGE_SQLSTATE_CLASSES
    # No SQLSTATE: the driver failed before the server answered (refused,
    # timed out, connection closed).
    return isinstance(exc, (db_utils.OperationalError, db_utils.InterfaceError))


# After a connection attempt fails, the web process fails further attempts at
# once for this long: a page whose reads each tolerate a missing database would
# otherwise wait out connect_timeout once per read.
CONNECT_BREAKER_SECONDS = 5.0
_connect_failed_at = {}


class DatabaseUnavailable(db_utils.OperationalError):
    """A connection refused without trying: the last attempt failed moments ago."""


def install_connect_breaker():
    """Wrap ``BaseDatabaseWrapper.connect`` with the per-alias breaker; idempotent.

    Installed by ``DatabaseOutageMiddleware``, so it applies to web processes
    only: the task worker and management commands keep retrying every time.
    """
    from django.db.backends.base.base import BaseDatabaseWrapper

    if getattr(BaseDatabaseWrapper.connect, "_dlux_breaker", False):
        return
    original = BaseDatabaseWrapper.connect

    def connect(self):
        failed_at = _connect_failed_at.get(self.alias)
        seconds = float(getattr(settings, "DLUX_DB_BREAKER_SECONDS", CONNECT_BREAKER_SECONDS) or 0)
        if failed_at is not None and time.monotonic() - failed_at < seconds:
            raise DatabaseUnavailable(
                f"The database ({self.alias}) did not answer a connection moments ago; not retrying for {seconds:g} s."
            )
        try:
            original(self)
        except Exception as exc:
            # The driver's own error: Django wraps it only after this returns.
            driver_error = getattr(getattr(self, "Database", None), "Error", ())
            if (driver_error and isinstance(exc, driver_error)) or is_database_outage(exc):
                _connect_failed_at[self.alias] = time.monotonic()
            raise
        _connect_failed_at.pop(self.alias, None)

    connect._dlux_breaker = True
    BaseDatabaseWrapper.connect = connect


def _mark_outage(sender, request=None, **kwargs):
    if request is not None and is_database_outage(sys.exc_info()[1]):
        try:
            request._dlux_database_outage = True
        except Exception:
            pass


got_request_exception.connect(_mark_outage, dispatch_uid="dlux.db_outage.mark_outage")


def _restore_cache():
    from django.core.cache import cache

    return cache


def set_restore_in_progress(token):
    """Turn the site away for the restore's database and file phases."""
    from .resilient_cache import safe_set

    safe_set(RESTORE_FLAG_KEY, {"token": str(token), "at": time.time()}, RESTORE_FLAG_TTL_SECONDS, cache=_restore_cache())


def clear_restore_in_progress():
    from .resilient_cache import safe_delete

    safe_delete(RESTORE_FLAG_KEY, cache=_restore_cache())


def restore_in_progress():
    from .resilient_cache import safe_get

    return safe_get(RESTORE_FLAG_KEY, cache=_restore_cache()) is not None


def _offline_strings():
    """The bundled catalog for the deployment's language, without a database read."""
    from .translations.strings import DLUX_STRINGS

    lang = str(getattr(settings, "LANGUAGE_CODE", "en") or "en").split("-")[0]
    return DLUX_STRINGS.get(lang) or DLUX_STRINGS["en"]


def database_outage_response(request):
    from .cache_outage import outage_response

    return outage_response(
        request,
        title_key="db_unavailable_title",
        message_key="db_unavailable_message",
        message=(
            "The database is not responding. Try again in a minute; if it keeps "
            "happening, tell your administrator."
        ),
        retry_after=DATABASE_RETRY_AFTER_SECONDS,
        strings=_offline_strings(),
    )


def restore_in_progress_response(request):
    from .cache_outage import outage_response

    return outage_response(
        request,
        title_key="restore_in_progress_title",
        title="Restore in progress",
        message_key="restore_in_progress_message",
        message=(
            "An administrator is restoring this system from a backup. It will be "
            "available again when the restore finishes, and you will need to sign in again."
        ),
        retry_after=RESTORE_RETRY_AFTER_SECONDS,
        strings=_offline_strings(),
    )


def _is_restore_poll(request):
    from django.urls import Resolver404, resolve

    try:
        match = resolve(request.path_info)
    except Resolver404:
        return False
    return match.url_name in RESTORE_ALLOWED_URL_NAMES


class DatabaseOutageMiddleware:
    """Answer 503 instead of 500 when the database cannot serve a request.

    A view's error reaches ``process_exception``; an error raised in an inner
    middleware (the session or authentication middleware reading the database)
    is already a 500 by the time it gets here, so the request is marked by a
    ``got_request_exception`` receiver and that 500 is replaced.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        install_connect_breaker()

    def __call__(self, request):
        if restore_in_progress() and not _is_restore_poll(request):
            return restore_in_progress_response(request)
        response = self.get_response(request)
        if getattr(request, "_dlux_database_outage", False) and getattr(response, "status_code", 0) == 500:
            return database_outage_response(request)
        return response

    def process_exception(self, request, exception):
        if not is_database_outage(exception):
            return None
        logger.warning(
            "%s %s failed because the database could not serve it: %s",
            request.method, request.path, exception,
        )
        return database_outage_response(request)
