"""Image-level (full container) update path.

Deliberately separate from the inline wheel updater (``service.py`` /
``DluxUpdateRun``): image updates are executed by the external composer-updater
container, which recreates the app containers — including this one. Routing that
through the inline worker's durable-run recovery would false-fail every update
(the worker is killed mid-run), so this keeps its own lightweight record and is
finalized by reading composer's ``deploy-status.json``.

Reused from the inline path: ``_create_backup`` (backup modes), maintenance
mode, and the ``DLUX_UPDATE_CHECK_INTERVAL`` check that already records the
latest release + its manifest.
"""

import json
import os
from pathlib import Path

from packaging.version import InvalidVersion, Version

from django.apps import apps
from django.utils import timezone

from . import UpdaterError
from .service import _state_model, runtime_store, updates_enabled

# How long to wait for composer to finish after hand-off before giving up and
# clearing maintenance. Generous: a full pull + recreate + migrate can be slow.
HANDOFF_TIMEOUT_SECONDS = 3600

TRIGGER_FILENAME = "image-update-request.json"
STATUS_FILENAME = "deploy-status.json"


def _image_model():
    return apps.get_model("dlux", "DluxImageUpdate")


def _run_model():
    return apps.get_model("dlux", "DluxUpdateRun")


def trigger_path(store):
    return store.state_dir / TRIGGER_FILENAME


def status_path(store):
    return store.state_dir / STATUS_FILENAME


def read_deploy_status(store=None):
    store = store or runtime_store()
    try:
        data = json.loads(status_path(store).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def image_update_available(state):
    """(available, target_version, reason).

    True when the latest known release is newer than the active runtime but is
    NOT inline-safe because it needs a project image rebuild — exactly the case
    the inline wheel updater detects and refuses (``latest_compatible`` False
    with an image-rebuild reason). Inline-safe releases are left to the wheel
    updater and never surface here.
    """
    latest = str(getattr(state, "latest_version", "") or "").strip()
    active = str(getattr(state, "active_version", "") or getattr(state, "baked_version", "") or "").strip()
    if not latest:
        return False, "", ""
    try:
        if active and Version(latest) <= Version(active):
            return False, "", ""
    except InvalidVersion:
        return False, "", ""
    if getattr(state, "latest_compatible", False):
        return False, "", ""
    manifest = getattr(state, "latest_manifest", None) or {}
    reason = str(getattr(state, "latest_reason", "") or "")
    needs_image = (
        manifest.get("migration_policy") == "image_rebuild"
        or manifest.get("inline_safe") is False
        or "image rebuild" in reason.lower()
    )
    if not needs_image:
        return False, "", ""
    return True, latest, reason


def active_image_update():
    return _image_model().objects.filter(is_active=True).order_by("created_at").first()


def serialize_image_update(row, *, store=None, include_log=False):
    if row is None:
        return None
    result = {
        "token": row.token,
        "status": row.status,
        "active": row.is_active,
        "source_version": row.source_version,
        "target_version": row.target_version,
        "error": row.error,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "handoff_at": row.handoff_at.isoformat() if row.handoff_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }
    if row.is_active:
        # Surface composer's live deploy status while an update is in flight.
        result["deploy_status"] = read_deploy_status(store)
    if include_log:
        result["progress_log"] = row.progress_log
    return result


def queue_image_update(username="", backup_mode=None):
    if not updates_enabled():
        raise UpdaterError("Inline DjangoLux updates are disabled for this project.")
    Image = _image_model()
    Run = _run_model()
    backup_mode = backup_mode if backup_mode in dict(Run.BACKUP_MODE_CHOICES) else Run.BACKUP_DATA
    state = _state_model().load()
    available, target, _reason = image_update_available(state)
    if not available:
        raise UpdaterError("No image-level DjangoLux update is available.")
    if state.active_run_token:
        raise UpdaterError("An inline DjangoLux update is already running.")
    from django.db import transaction

    with transaction.atomic():
        if Image.objects.select_for_update(skip_locked=True).filter(is_active=True).exists():
            raise UpdaterError("An image update is already in progress.")
        row = Image.objects.create(
            source_version=state.active_version or state.baked_version,
            target_version=target,
            requested_by_username=str(username or "")[:150],
            backup_mode=backup_mode,
        )
    return row


def write_composer_trigger(store, row):
    """Atomically write the composer-updater trigger request onto the shared
    runtime volume. composer's `watch` picks up the changed token and runs a
    full `-uo` update."""
    path = trigger_path(store)
    payload = {
        "token": row.token,
        "target": row.target_version,
        "requested_at": timezone.now().isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    os.replace(tmp, path)
