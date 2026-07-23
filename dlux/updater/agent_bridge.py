import json
import os
import time
import uuid
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.db import connection
from django.utils import timezone

from dlux import __version__

from . import UpdaterError
from .image_update import app_version, image_update_metadata, queue_image_update


SCHEMA_VERSION = 1
MAX_DOCUMENT_BYTES = 65536
SNAPSHOT_INTERVAL_SECONDS = 60
_next_snapshot_at = 0.0


def bridge_root(store):
    return store.state_dir / "agent"


def requests_dir(store):
    return bridge_root(store) / "requests"


def results_dir(store):
    return bridge_root(store) / "results"


def processed_dir(store):
    return bridge_root(store) / "processed"


def snapshot_path(store):
    return bridge_root(store) / "snapshot.json"


def _atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _read_request(path):
    raw = Path(path).read_bytes()
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise UpdaterError("Agent request exceeds the 64 KiB limit.")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise UpdaterError("Agent request is not valid JSON.") from exc
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise UpdaterError("Agent request schema is unsupported.")
    try:
        operation_id = str(uuid.UUID(str(value.get("operation_id") or "")))
    except ValueError as exc:
        raise UpdaterError("Agent operation ID is invalid.") from exc
    if Path(path).stem != operation_id:
        raise UpdaterError("Agent operation ID does not match its spool filename.")
    action = str(value.get("action") or "")
    if action not in {"dlux.image_update", "dlux.backup.create"}:
        raise UpdaterError("Agent action is not supported by the DLUX bridge.")
    payload = value.get("payload") or {}
    if not isinstance(payload, dict):
        raise UpdaterError("Agent request payload is invalid.")
    backup_mode = str(payload.get("backup_mode") or "data").strip().lower()
    allowed_modes = {"data", "full", "skip"} if action == "dlux.image_update" else {"data", "full"}
    if backup_mode not in allowed_modes:
        raise UpdaterError("Agent backup mode is invalid.")
    actor = value.get("actor") or {}
    username = str(actor.get("display") or actor.get("id") or "control-plane")[:150]
    return operation_id, action, backup_mode, username


def _row_result(row):
    message = ""
    if row.progress_log:
        message = row.progress_log.splitlines()[-1][:1000]
    return {
        "schema_version": SCHEMA_VERSION,
        "operation_id": str(row.control_operation_id),
        "status": row.status,
        "message": message,
        "error": str(row.error or "")[:4000],
        "image_token": row.token,
        "target_version": row.target_version,
        "backup_token": row.backup_token,
        "updated_at": (row.completed_at or row.handoff_at or row.created_at).isoformat(),
    }


def _backup_result(backup):
    return {
        "schema_version": SCHEMA_VERSION,
        "operation_id": backup.token,
        "status": backup.status,
        "message": str(backup.progress_message or "")[:1000],
        "error": str(backup.error or "")[:4000],
        "backup_token": backup.token,
        "backup_mode": "full" if backup.media_included else "data",
        "file_size": backup.file_size,
        "updated_at": (backup.completed_at or backup.started_at or backup.created_at).isoformat(),
    }


def _archive_request(store, path):
    destination_root = processed_dir(store)
    destination_root.mkdir(parents=True, exist_ok=True)
    destination = destination_root / path.name
    if destination.exists():
        destination = destination.with_name(
            f"{destination.stem}.duplicate-{time.time_ns()}{destination.suffix}"
        )
    path.replace(destination)


def publish_agent_results(store):
    Image = apps.get_model("dlux", "DluxImageUpdate")
    rows = Image.objects.exclude(control_operation_id=None).order_by("-created_at")[:100]
    for row in rows:
        _atomic_json(results_dir(store) / f"{row.control_operation_id}.json", _row_result(row))


def consume_agent_requests(service, limit=10):
    root = requests_dir(service.store)
    root.mkdir(parents=True, exist_ok=True)
    Image = apps.get_model("dlux", "DluxImageUpdate")
    processed = 0
    for path in sorted(root.glob("*.json")):
        if processed >= limit:
            break
        processed += 1
        operation_id = path.stem
        try:
            operation_id, action, backup_mode, username = _read_request(path)
            if action == "dlux.image_update":
                existing = Image.objects.filter(control_operation_id=operation_id).first()
                if existing is not None:
                    result = _row_result(existing)
                else:
                    row = queue_image_update(
                        username,
                        backup_mode=backup_mode,
                        control_operation_id=operation_id,
                        request_source="control",
                    )
                    result = _row_result(row)
            else:
                Backup = apps.get_model("dlux", "SystemBackup")
                backup, _created = Backup.objects.get_or_create(
                    token=operation_id,
                    defaults={
                        "requested_by_username": username,
                        "trigger": Backup.TRIGGER_MANUAL,
                        "media_included": backup_mode == "full",
                    },
                )
                if backup.status == Backup.STATUS_PENDING:
                    from dlux.backup import run_system_backup

                    run_system_backup(backup.pk)
                    backup.refresh_from_db()
                result = _backup_result(backup)
        except Exception as exc:
            result = {
                "schema_version": SCHEMA_VERSION,
                "operation_id": operation_id,
                "status": "rejected",
                "error": str(exc).replace("\x00", "")[:4000],
                "updated_at": timezone.now().isoformat(),
            }
        _atomic_json(results_dir(service.store) / f"{operation_id}.json", result)
        _archive_request(service.store, path)
    return processed


def _project_name():
    try:
        SystemSettings = apps.get_model("dlux", "SystemSettings")
        names = SystemSettings.load().system_names or {}
        if isinstance(names, dict) and names.get("en"):
            return str(names["en"])[:160]
    except Exception:
        pass
    return Path(getattr(settings, "BASE_DIR", "/app")).name[:160] or "project"


def _resource_summary():
    try:
        import psutil
    except ImportError:
        return {}
    try:
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage(str(getattr(settings, "BASE_DIR", "/")))
        return {
            "cpu_percent": round(float(psutil.cpu_percent(interval=None)), 1),
            "memory_percent": round(float(memory.percent), 1),
            "disk_percent": round(float(disk.percent), 1),
        }
    except Exception:
        return {}


def build_agent_snapshot(store):
    Backup = apps.get_model("dlux", "SystemBackup")
    Image = apps.get_model("dlux", "DluxImageUpdate")
    recent_backups = list(Backup.objects.order_by("-created_at")[:10])
    latest_backup = recent_backups[0] if recent_backups else None
    active_image = Image.objects.filter(is_active=True).order_by("created_at").first()
    image_meta = image_update_metadata(store)
    try:
        connection.ensure_connection()
        database = "online"
    except Exception:
        database = "offline"
    backup = {}
    if latest_backup is not None:
        backup = {
            "status": latest_backup.status,
            "trigger": latest_backup.trigger,
            "file_size": latest_backup.file_size,
            "media_included": latest_backup.media_included,
            "created_at": latest_backup.created_at.isoformat(),
            "completed_at": latest_backup.completed_at.isoformat() if latest_backup.completed_at else None,
            "recent": [
                {
                    "token": item.token,
                    "status": item.status,
                    "trigger": item.trigger,
                    "file_size": item.file_size,
                    "media_included": item.media_included,
                    "created_at": item.created_at.isoformat(),
                    "completed_at": item.completed_at.isoformat() if item.completed_at else None,
                }
                for item in recent_backups
            ],
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "observed_at": timezone.now().isoformat(),
        "project": {
            "name": _project_name(),
            "environment": str(os.environ.get("DLUX_ENVIRONMENT") or "production")[:64],
        },
        "versions": {
            "application": app_version(),
            "dlux": __version__,
            "composer": str(os.environ.get("COMPOSER_VERSION") or "")[:64],
        },
        "health": {
            "database": database,
            "maintenance": store.maintenance_file.exists(),
            "degraded": store.degraded_file.exists(),
        },
        "resources": _resource_summary(),
        "backup": backup,
        "updates": {
            "image_available": bool(image_meta.get("available")),
            "image_target": str(image_meta.get("target") or "")[:128],
            "active_status": active_image.status if active_image else "",
        },
    }


def publish_agent_snapshot(store, force=False):
    global _next_snapshot_at
    now = time.monotonic()
    if not force and now < _next_snapshot_at:
        return False
    _atomic_json(snapshot_path(store), build_agent_snapshot(store))
    _next_snapshot_at = now + SNAPSHOT_INTERVAL_SECONDS
    return True
