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


def write_enroll_request(store, control_url, pairing_token):
    """Atomically publish an enroll request for the agent; returns the operation id."""
    operation_id = str(uuid.uuid4())
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


def read_agent_status(store):
    try:
        value = json.loads(_agent_status_path(store).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def control_link_state(store):
    """Combine the agent status file and any pending request into one view model.

    Auto-clears a pending request once the agent has reported a successful
    terminal result for that same ``operation_id`` (a failed result is kept so the
    tile can surface the error until the operator retries or cancels)."""
    status = read_agent_status(store) or {}
    pending = read_enroll_request(store)
    last = status.get("last_enroll") if isinstance(status.get("last_enroll"), dict) else {}

    if (
        pending
        and last.get("operation_id") == pending.get("operation_id")
        and last.get("state") == "ok"
    ):
        clear_enroll_request(store)
        pending = None

    return {
        "bridge_available": True,
        "agent_status_present": bool(status),
        "enrolled": bool(status.get("enrolled")),
        "control_url": status.get("control_url") or (pending or {}).get("control_url") or "",
        "agent_id": status.get("agent_id") or "",
        "agent_version": status.get("agent_version") or "",
        "enrolled_at": status.get("enrolled_at") or "",
        "last_contact_at": status.get("last_contact_at") or "",
        "revoked": bool(status.get("revoked")),
        "pending": bool(pending),
        "pending_operation_id": (pending or {}).get("operation_id", ""),
        "last_enroll": {
            "operation_id": last.get("operation_id", ""),
            "state": last.get("state", ""),
            "error": last.get("error", ""),
            "at": last.get("at", ""),
        },
    }
