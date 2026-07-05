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

from django.apps import apps
from django.utils import timezone

from django.conf import settings

from . import UpdaterError
from .service import _state_model, updates_enabled

# How long to wait for composer to finish after hand-off before giving up and
# clearing maintenance. Generous: a full pull + recreate + migrate can be slow.
HANDOFF_TIMEOUT_SECONDS = 3600

TRIGGER_FILENAME = "image-update-request.json"
STATUS_FILENAME = "deploy-status.json"
# Published by composer's `watch --availability-file` (composer has registry
# egress; dlux/web is network-isolated). Drives "image update available".
AVAILABILITY_FILENAME = "image-available.json"


def _image_model():
    return apps.get_model("dlux", "DluxImageUpdate")


def _run_model():
    return apps.get_model("dlux", "DluxUpdateRun")


def _state_dir(store=None):
    """Runtime state dir WITHOUT creating it. Readers run on the web container,
    which mounts the runtime volume read-only — they must never mkdir/ensure.
    Writers (the worker) pass their own ensured ``store``."""
    if store is not None:
        return store.state_dir
    root = Path(getattr(settings, "DLUX_UPDATE_RUNTIME_ROOT", "/opt/dlux-runtime")).expanduser()
    return root / "state"


def trigger_path(store=None):
    return _state_dir(store) / TRIGGER_FILENAME


def status_path(store=None):
    return _state_dir(store) / STATUS_FILENAME


def read_deploy_status(store=None):
    try:
        data = json.loads(status_path(store).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def read_image_availability(store=None):
    """The image-availability document composer publishes, or {}."""
    try:
        data = json.loads((_state_dir(store) / AVAILABILITY_FILENAME).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def image_update_available(store=None):
    """(available, target, reason).

    Registry-driven: True when composer reports a newer application image than
    the one currently running (a changed remote tag digest). composer owns this
    check because it has registry egress; dlux/web is network-isolated and only
    reads the published file. ``target`` is a short remote digest for display.
    """
    data = read_image_availability(store)
    if not data.get("available"):
        return False, "", ""
    target = ""
    for image in data.get("images", []):
        if isinstance(image, dict) and image.get("update_available") and image.get("remote_digest"):
            target = str(image["remote_digest"])[:19]  # sha256:xxxxxxxxxx
            break
    return True, target, "A new application image is available."


def active_image_update():
    return _image_model().objects.filter(is_active=True).order_by("created_at").first()


def app_version():
    """The deployed application's own version (distinct from the DjangoLux
    framework version). Prefers the ``DLUX_APP_VERSION`` setting; otherwise
    auto-reads a ``VERSION`` file at the project root (``BASE_DIR``)."""
    configured = str(getattr(settings, "DLUX_APP_VERSION", "") or "").strip()
    if configured:
        return configured
    try:
        return (Path(settings.BASE_DIR) / "VERSION").read_text(encoding="utf-8").strip()
    except (OSError, ValueError, TypeError):
        return ""


def image_status_summary(store=None):
    """Application-image facts for the Updates card: the running vs published
    image digest (from composer's availability file) and the last image update
    (from the DluxImageUpdate history). All best-effort; missing pieces are ''."""
    data = read_image_availability(store)
    images = data.get("images") or []
    first = images[0] if images and isinstance(images[0], dict) else {}
    last = _image_model().objects.order_by("-created_at").first()
    last_summary = None
    if last is not None:
        last_summary = {
            "status": last.status,
            "target": last.target_version,
            "completed_at": last.completed_at.isoformat() if last.completed_at else None,
        }
    return {
        "app_version": app_version(),
        "image": first.get("image") or "",
        "running_digest": first.get("local_digest") or "",
        "remote_digest": first.get("remote_digest") or "",
        "update_available": bool(data.get("available")),
        "checked_at": data.get("checked_at") or "",
        "last_update": last_summary,
    }


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
    available, target, _reason = image_update_available()
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


def write_deploy_status(store, status, **extra):
    """Write an initial deploy-status so the live progress page never shows a
    stale `ready` between hand-off and composer taking over. composer overwrites
    this file with its own phases once the `-uo` run starts."""
    path = status_path(store)
    payload = {"status": status, "updated_at": timezone.now().isoformat(), **extra}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    os.replace(tmp, path)
