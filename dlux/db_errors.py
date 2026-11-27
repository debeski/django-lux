"""Whether a database error means "the database cannot serve this now".

A leaf module, so code that only needs the classification (config reads, the
outage middleware) imports it without pulling in the middleware's dependencies.
"""

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
    # No SQLSTATE: the driver failed before the server answered (refused,
    # timed out, connection closed).
    return isinstance(exc, (db_utils.OperationalError, db_utils.InterfaceError))
