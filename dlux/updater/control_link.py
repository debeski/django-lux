"""UI-driven Control Panel pairing (DjangoLux side of the agent bridge).

The superuser enters the control-panel URL and a one-use pairing token in the
*Control Panel* tile. DjangoLux drops an ``enroll-request.json`` into the shared
agent bridge (the private ``dlux_runtime`` volume); the resident ``composer-agent``
redeems the token through the control plane and reports back in
``agent-status.json``. No ``.env`` editing and no redeploy are involved, and the
pairing token only ever lives transiently in the private runtime volume.
"""

import json
import uuid

from django.utils import timezone

from . import agent_bridge

ENROLL_REQUEST_FILENAME = "enroll-request.json"
AGENT_STATUS_FILENAME = "agent-status.json"

_TERMINAL_ENROLL_STATES = ("ok", "error")


def _enroll_request_path(store):
    return agent_bridge.bridge_root(store) / ENROLL_REQUEST_FILENAME


def _agent_status_path(store):
    return agent_bridge.bridge_root(store) / AGENT_STATUS_FILENAME


def write_enroll_request(store, control_url, pairing_token, operation_id=None):
    """Atomically publish an enroll request for the agent; returns the operation id.

    Only the update worker may call this — the web tier's runtime mount is
    read-only. Web-tier callers queue a ``DluxControlLinkRequest`` instead.
    """
    operation_id = str(operation_id or uuid.uuid4())
    agent_bridge.bridge_root(store).mkdir(parents=True, exist_ok=True)
    agent_bridge._atomic_json(
        _enroll_request_path(store),
        {
            "schema_version": 1,
            "operation_id": operation_id,
            "control_url": str(control_url or "").strip(),
            "pairing_code": str(pairing_token or "").strip(),
            "requested_at": timezone.now().isoformat(),
        },
    )
    return operation_id


def read_enroll_request(store):
    try:
        value = json.loads(_enroll_request_path(store).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def clear_enroll_request(store):
    try:
        _enroll_request_path(store).unlink()
    except OSError:
        pass


def _request_model():
    from django.apps import apps

    return apps.get_model("dlux", "DluxControlLinkRequest")


def queue_enroll_request(control_url, pairing_token):
    """Record a pairing intent for the worker to publish; returns the operation id.

    Called from the web tier, which cannot write the agent bridge itself. Any
    earlier unapplied request is dropped so the newest submission wins.
    """
    model = _request_model()
    model.objects.all().delete()
    row = model.objects.create(
        action=model.ACTION_ENROLL,
        control_url=str(control_url or "").strip(),
        pairing_token=str(pairing_token or "").strip(),
    )
    return str(row.operation_id)


def queue_cancel_request():
    """Drop any unapplied request and ask the worker to clear a published one."""
    model = _request_model()
    model.objects.all().delete()
    model.objects.create(action=model.ACTION_CANCEL)


def queued_request():
    """The pending web-tier request the worker has not applied yet, or None."""
    try:
        return _request_model().objects.order_by("created_at").first()
    except Exception:
        return None


def read_agent_status(store):
    try:
        value = json.loads(_agent_status_path(store).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def control_link_state(store):
    """Combine the agent status file, the published request, and any queued
    web-tier request into one view model.

    Pure read: served by the web tier, which has no write access to the runtime
    volume. A published request is treated as settled once the agent reports a
    successful terminal result for the same ``operation_id`` (a failed result is
    kept so the tile can surface the error until the operator retries or
    cancels); the worker does the actual file cleanup in ``tick_control_link``.
    """
    status = read_agent_status(store) or {}
    published = read_enroll_request(store)
    last = status.get("last_enroll") if isinstance(status.get("last_enroll"), dict) else {}

    if (
        published
        and last.get("operation_id") == published.get("operation_id")
        and last.get("state") == "ok"
    ):
        published = None

    queued = queued_request()
    queued_enroll = None
    if queued is not None and queued.action == _request_model().ACTION_ENROLL:
        queued_enroll = queued
    pending = published or queued_enroll
    pending_operation_id = ""
    pending_control_url = ""
    if published:
        pending_operation_id = published.get("operation_id", "")
        pending_control_url = published.get("control_url", "")
    elif queued_enroll is not None:
        pending_operation_id = str(queued_enroll.operation_id)
        pending_control_url = queued_enroll.control_url

    return {
        "bridge_available": True,
        "queued": queued is not None,
        "queue_error": getattr(queued, "error", "") or "",
        "agent_status_present": bool(status),
        "enrolled": bool(status.get("enrolled")),
        "control_url": status.get("control_url") or pending_control_url or "",
        "agent_id": status.get("agent_id") or "",
        "agent_version": status.get("agent_version") or "",
        "enrolled_at": status.get("enrolled_at") or "",
        "last_contact_at": status.get("last_contact_at") or "",
        "revoked": bool(status.get("revoked")),
        "pending": bool(pending),
        "pending_operation_id": pending_operation_id,
        "last_enroll": {
            "operation_id": last.get("operation_id", ""),
            "state": last.get("state", ""),
            "error": last.get("error", ""),
            "at": last.get("at", ""),
        },
    }
