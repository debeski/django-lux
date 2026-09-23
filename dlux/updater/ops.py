"""Named deployment operations Dlux asks Composer to perform.

The Operations card lets an administrator run the things that otherwise need a
shell on the host — starting with `composer check`, the doctor for the *outside*
of the stack. Dlux gains no Docker authority by it: it writes a typed request
naming one operation from ``OPERATIONS`` below, and the resident Composer
performs it and writes back a result. An operation that is not in that table
cannot be requested at all, which is the whole security model — see
``operations_center_plan.md`` §2-§4.

The file shape mirrors the package-update and channel handoffs: one request at a
time, carrying the run's token, acknowledged under the same token. Composer
publishes the result beside it, so a stale result can never be read as this
run's (the token has to match).

Read-only operations live here first. Anything that changes the deployment
(applying `check --fix`, restarting a service, updating Composer itself) is a
later phase and is deliberately absent, not merely unimplemented.
"""

from __future__ import annotations

from django.utils import timezone

from . import UpdaterError
from .channel import _atomic_json, _read_json
from .runtime import state_dir

SCHEMA_VERSION = 1
REQUEST_FILENAME = "ops-request.json"
ACK_FILENAME = f"{REQUEST_FILENAME}.ack"
RESULT_FILENAME = "ops-result.json"

#: What an administrator may ask Composer to do, and the Composer that can do it.
#: ``min_composer`` is reported when an older resident never answers, so the UI
#: says "your Composer is too old" instead of "it timed out".
OPERATIONS = {
    "check": {
        "min_composer": "1.5.0",
        "changes_deployment": False,
        "needs_preview": False,
        "label": "Run deployment check",
    },
    "check-fix-preview": {
        "min_composer": "1.6.0",
        "changes_deployment": False,
        "needs_preview": False,
        "label": "Preview repairs",
    },
    "check-fix-apply": {
        # Writes to the deployment files. Superuser + current password in the
        # view, and it may only apply the repair a preview showed: the digest
        # comes from that preview's result, never from the request.
        "min_composer": "1.6.0",
        "changes_deployment": True,
        "needs_preview": True,
        "label": "Apply repairs",
    },
}

#: The only value a request may carry besides the operation name, and it is
#: read from the preview's own result — never from the browser.
DIGEST_FIELD = "compose_digest"

#: How long a request waits for its acknowledgement before the run gives up. The
#: agent answers within one loop tick (2s) plus the check itself, which shells
#: out to Docker and Compose a handful of times.
REQUEST_TIMEOUT_SECONDS = 120


def normalize_operation(value):
    """A supported operation name, or raise ``UpdaterError``."""
    name = str(value or "").strip().lower()
    if name not in OPERATIONS:
        raise UpdaterError(f"Unknown deployment operation: {value!r}.")
    return name


def request_path(store=None):
    return state_dir(store) / REQUEST_FILENAME


def ack_path(store=None):
    return state_dir(store) / ACK_FILENAME


def result_path(store=None):
    return state_dir(store) / RESULT_FILENAME


def normalize_digest(value):
    """A compose digest as Composer publishes it, or raise ``UpdaterError``."""
    digest = str(value or "").strip().lower()
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise UpdaterError("The repair preview is missing or unusable; preview it again.")
    return digest


def write_request(store, token, operation, *, compose_digest=""):
    """Ask Composer to perform ``operation``. Celery only — ``store`` required."""
    if store is None:
        raise UpdaterError("Requesting a deployment operation requires the runtime store.")
    operation = normalize_operation(operation)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "token": str(token)[:64],
        "operation": operation,
        "requested_at": timezone.now().isoformat(),
    }
    if OPERATIONS[operation]["needs_preview"]:
        payload[DIGEST_FIELD] = normalize_digest(compose_digest)
    _atomic_json(request_path(store), payload)


def read_ack(store=None, *, token=""):
    """Composer's acknowledgement for ``token``, or ``{}`` when it has not answered."""
    ack = _read_json(ack_path(store))
    if token and str(ack.get("token") or "") != str(token):
        return {}
    return ack


def read_result(store=None, *, token=""):
    """The result document Composer published for ``token``, or ``{}``.

    Token-matched on purpose: the previous operation's result is still on the
    volume, and showing it as this one's would be a lie the UI cannot detect.
    """
    result = _read_json(result_path(store))
    if token and str(result.get("token") or "") != str(token):
        return {}
    return result


def repairs(result):
    """The repairs a preview or apply reported, bounded for the card."""
    return [r for r in (result or {}).get("repairs") or [] if isinstance(r, dict)]


def summarize(result):
    """Counts the card leads with: how many findings, and how bad."""
    findings = [f for f in (result or {}).get("findings") or [] if isinstance(f, dict)]
    levels = [str(f.get("level") or "").lower() for f in findings]
    return {
        "total": len(findings),
        "ok": levels.count("ok"),
        "warn": levels.count("warn"),
        "fail": levels.count("fail"),
    }
