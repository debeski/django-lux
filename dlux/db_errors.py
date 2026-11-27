"""Whether a database error means "the database cannot serve this now".

A leaf module, so code that only needs the classification (config reads, the
outage middleware) imports it without pulling in the middleware's dependencies.
"""

import time

from django.conf import settings
from django.db import utils as db_utils

# After a failed attempt, how long further attempts are refused without trying
# (setting DLUX_DB_BREAKER_SECONDS): the web connect breaker, and config reads
# outside a request.
DEFAULT_BREAKER_SECONDS = 5.0


def breaker_seconds():
    return float(getattr(settings, "DLUX_DB_BREAKER_SECONDS", DEFAULT_BREAKER_SECONDS) or 0)

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
    if "no such table" in str(exc).lower():
        # SQLite's missing table carries no SQLSTATE; PostgreSQL's is 42P01.
        return False
    # No SQLSTATE: the driver failed before the server answered (refused,
    # timed out, connection closed).
    return isinstance(exc, (db_utils.OperationalError, db_utils.InterfaceError))


# The read breaker for code outside a request: system config, the font list and
# ScopeSettings. Nothing memoises those reads outside a request, so with the
# database down one `manage.py check` paid a connection attempt per read.
_read_failed_at = None
_read_failure = ""


def note_read_failure(exc):
    """Record ``exc`` for the read breaker if it is an outage; return whether it was."""
    global _read_failed_at, _read_failure
    if not is_database_outage(exc):
        return False
    _read_failed_at = time.monotonic()
    first_line = (str(exc).strip().splitlines() or [""])[0]
    _read_failure = f"{type(exc).__name__}: {first_line}"
    return True


def read_recently_failed():
    """Whether a read outside a request skips the database: one failed moments ago.

    Callers ask only outside a request: a request always tries, and the web
    connect breaker makes that attempt fail fast.
    """
    return _read_failed_at is not None and time.monotonic() - _read_failed_at < breaker_seconds()


def last_read_failure():
    return _read_failure


def clear_read_failure():
    global _read_failed_at
    _read_failed_at = None
