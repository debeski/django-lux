"""How often Composer looks for updates, and asking it to look right now.

Composer's resident agent checks PyPI (DjangoLux releases) and the registry
(project images) on an interval. The administrator chooses that interval in
Options; it is recorded on ``DluxUpdateState.check_interval_minutes`` and the
Celery worker mirrors it to ``state/check-policy.json``, which the agent reads on
every loop tick — the same split as the release channel (see ``channel``): web
mounts the runtime volume read-only, Celery owns the write side, Composer never
touches the database.

A manual check is a request, not a read: the worker writes
``state/check-request.json`` carrying the check run's token, the agent re-checks
immediately and acknowledges in ``check-request.json.ack``, and only then does
the run read the refreshed availability report. A Composer that predates this
never acknowledges; the run then falls back to the last report it published.
"""

from __future__ import annotations

from django.utils import timezone

from . import UpdaterError
from .channel import _atomic_json, _read_json
from .runtime import state_dir

POLICY_SCHEMA_VERSION = 1
POLICY_FILENAME = "check-policy.json"
REQUEST_FILENAME = "check-request.json"
ACK_FILENAME = f"{REQUEST_FILENAME}.ack"

INTERVAL_CHOICES_MINUTES = (5, 15, 30, 60, 180, 360, 720, 1440)
DEFAULT_INTERVAL_MINUTES = 15

# How long a manual check waits for Composer's acknowledgement before it falls
# back to the last published report (an older Composer never acknowledges).
REQUEST_TIMEOUT_SECONDS = 20


def normalize_interval(value):
    """A supported interval in minutes, or raise ``UpdaterError``."""
    try:
        minutes = int(str(value).strip())
    except (TypeError, ValueError):
        raise UpdaterError("The update check interval must be a whole number of minutes.")
    if minutes not in INTERVAL_CHOICES_MINUTES:
        choices = ", ".join(str(choice) for choice in INTERVAL_CHOICES_MINUTES)
        raise UpdaterError(f"Unsupported update check interval; choose one of {choices} minutes.")
    return minutes


def policy_path(store=None):
    return state_dir(store) / POLICY_FILENAME


def request_path(store=None):
    return state_dir(store) / REQUEST_FILENAME


def ack_path(store=None):
    return state_dir(store) / ACK_FILENAME


def read_policy(store=None):
    """The published interval in minutes, or ``None`` when absent or unusable."""
    data = _read_json(policy_path(store))
    seconds = data.get("interval_seconds")
    if type(seconds) is not int or seconds <= 0:
        return None
    return seconds // 60


def publish_policy(store, minutes):
    """Write the policy file atomically. Celery only — ``store`` is required."""
    if store is None:
        raise UpdaterError("Publishing the update check policy requires the runtime store.")
    minutes = normalize_interval(minutes)
    _atomic_json(policy_path(store), {
        "schema_version": POLICY_SCHEMA_VERSION,
        "interval_seconds": minutes * 60,
        "published_at": timezone.now().isoformat(),
    })
    return minutes


def write_request(store, token):
    """Ask Composer to check now. Celery only — ``store`` is required."""
    if store is None:
        raise UpdaterError("Requesting an update check requires the runtime store.")
    _atomic_json(request_path(store), {
        "schema_version": POLICY_SCHEMA_VERSION,
        "token": str(token)[:64],
        "requested_at": timezone.now().isoformat(),
    })


def acknowledged(store, token):
    """Has Composer finished the check requested under ``token``?"""
    return bool(token) and str(_read_json(ack_path(store)).get("token") or "") == str(token)
