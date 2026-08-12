"""Ask Composer to apply or roll back an inline DjangoLux release.

DjangoLux states intent; Composer executes. This is the same shape as the
image-update trigger in ``image_update.py`` — an atomically written request file
on the shared runtime volume, picked up by Composer's executor, acknowledged by
token — but for the *package* rather than the project image.

Why the executor moved out of this package at all: Composer stages and verifies a
release before activating it, and health-gates the restart from outside the
container being swapped. An in-container updater cannot roll back a release that
prevented it from starting. See ``docs/updater-consolidation.md``.

Removal schedule: DjangoLux 1.8.0 deprecates the in-container executor and 1.9.0
deletes it. Nothing here deletes anything a deployed ``compose.yml`` names — that
file is project-owned, and its ``dlux-updater`` service is ``restart: always``
and ``org.dlux.restart: protected``.
"""
import json
import os
import uuid

from django.utils import timezone

from . import UpdaterError
from .image_update import _state_dir, read_deploy_status

TRIGGER_FILENAME = "package-update-request.json"
ACK_FILENAME = f"{TRIGGER_FILENAME}.ack"

APPLY = "apply"
ROLLBACK = "rollback"
MODES = frozenset({APPLY, ROLLBACK})


def trigger_path(store=None):
    return _state_dir(store) / TRIGGER_FILENAME


def ack_path(store=None):
    return _state_dir(store) / ACK_FILENAME


def read_ack(store=None):
    """Composer's terminal acknowledgement for the last package request, or {}."""
    try:
        data = json.loads(ack_path(store).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def pending_token(store=None):
    """The token of a request Composer has not acknowledged yet, or ''.

    Used to refuse queueing a second package operation while one is in flight —
    two concurrent swaps of the same volume would race over ``active.json``.
    """
    try:
        request = json.loads(trigger_path(store).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    token = str(request.get("token") or "").strip()
    if not token:
        return ""
    return "" if str(read_ack(store).get("token") or "").strip() == token else token


def write_request(
    store=None,
    *,
    mode=APPLY,
    target_version="",
    backup_mode="data",
    token="",
    operation_id="",
):
    """Atomically write the request Composer's executor watches for.

    The payload mirrors the ``dlux.package_update`` agent action so the local
    file path and the control-panel path carry identical fields.
    """
    if mode not in MODES:
        raise UpdaterError("The requested package-update mode is invalid.")
    token = str(token or uuid.uuid4())
    payload = {
        "token": token,
        "requested_at": timezone.now().isoformat(),
        "payload": {
            "mode": mode,
            "target_version": str(target_version or ""),
            "backup_mode": str(backup_mode or "data"),
        },
    }
    if operation_id:
        payload["operation_id"] = str(operation_id)

    path = trigger_path(store)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return payload


AVAILABILITY_FILENAME = "package-available.json"


def availability_path(store=None):
    return _state_dir(store) / AVAILABILITY_FILENAME


def read_availability(store=None):
    """What Composer last reported as available, or {}.

    Composer publishes this from `composer dlux-update --check`, which resolves,
    downloads and verifies the wheel — the manifest inside it is the only
    authority on `inline_safe`. DjangoLux never reaches PyPI itself.

    An empty dict means "Composer has not reported yet", which the UI must show
    as *unknown* rather than as "up to date".
    """
    try:
        data = json.loads(availability_path(store).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def composer_progress(store=None):
    """Composer's progress for a package operation, or {}.

    Composer reuses ``deploy-status.json`` for both operation kinds; entries for
    a package update carry ``kind == "package"``.
    """
    status = read_deploy_status(store)
    if not status:
        return {}
    if status.get("kind") and status.get("kind") != "package":
        return {}
    return status
