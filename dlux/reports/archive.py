"""Report backup archive pipeline: zip building, streaming and dispatch.

This is backup machinery living in the reports package because it archives
report-eligible models. Whether it belongs under `dlux/backup/` instead is an
open question for Phase 1.5 — see audit_plan.md."""

import io
import json
import re
import shutil
import tempfile
import unicodedata
import zipfile
from datetime import timedelta
from io import BytesIO
from django.apps import apps
from django.core.serializers.json import Serializer as JsonSerializer
from django.core.files import File
from django.core.files.storage import default_storage
from django.db import models
from django.utils import timezone
from ..translations import get_strings
from ..utils import log_user_action
from ..utils import archive as _archive
from ..utils.archive import stream_model_into_zip


def backup_record_folder(record, *, label_field=None):
    """Report-flavoured wrapper: resolves the label field from reports config."""
    return _archive.backup_record_folder(
        record,
        label_field=label_field,
        label_field_resolver=_backup_label_field,
    )


def build_relation_schema(models_list):
    """Report-flavoured wrapper: names records by their configured label field."""
    return _archive.build_relation_schema(
        models_list,
        label_field_resolver=_backup_label_field,
    )

from ._shared import logger
from .config import _reports_config
from .export import _entry_export_queryset, _models_for_report_criteria, build_model_entries_xlsx
from .overview import build_reports_overview
from .queries import _iter_queryset_by_pk
from .windows import normalize_backup_window


_BACKUP_LABEL_FIELD_CANDIDATES = (
    "number",
    "document_number",
    "reference_number",
    "registration_number",
    "serial_number",
    "code",
    "name",
    "title",
)


def get_backup_storage_prefix():
    """Storage-relative directory where generated backup zips are kept.

    Lives under the default storage (usually MEDIA_ROOT) so web and worker
    containers can share it; deployments must block direct HTTP access to it
    (e.g. an nginx `deny all` on /media/<prefix>/) — downloads always go
    through the permission-checked Django view.
    """
    prefix = str(_reports_config().get("backup_storage_prefix") or "dlux_backups").strip("/")
    return prefix or "dlux_backups"


def _backup_label_field(model):
    configured = _reports_config().get("backup_label_fields", {})
    field_name = ""
    if isinstance(configured, dict):
        field_name = str(configured.get(model._meta.label_lower) or "").strip()
    candidates = (field_name,) if field_name else _BACKUP_LABEL_FIELD_CANDIDATES
    for candidate in candidates:
        if not candidate:
            continue
        try:
            field = model._meta.get_field(candidate)
        except Exception:
            continue
        if getattr(field, "concrete", False) and not getattr(field, "is_relation", False):
            return field.name
    return ""














REPORT_ZIP_WORKBOOK_NAME = "entries.xlsx"


def write_backup_zip(actor, fileobj, *, window="all", criteria=None, progress_callback=None):
    """Stream a scope-aware report package into ``fileobj``.

    The archive is a periodic deliverable for people, not a restore artifact
    (that is the system ``.dlb``), so it carries exactly two things: the entries
    workbook the Export Entries button produces, and the media those records
    reference, foldered by business identifier. No serialized JSON — the same
    normalized period/model/operation selection drives both parts, so the
    browser, the spreadsheet, and the ZIP always agree.
    """
    window = normalize_backup_window(window)
    requested_filters = dict(criteria or {})
    if criteria:
        requested_filters["builder"] = "1"
    overview = build_reports_overview(actor, window=window, filters=requested_filters)
    criteria = overview["criteria"]
    manifest = {
        "generated_at": timezone.now().isoformat(),
        "window": window,
        "selection": criteria,
        "models": [],
        "files": [],
        "missing_files": [],
        "report_artifacts": [REPORT_ZIP_WORKBOOK_NAME],
    }
    models_to_export = _models_for_report_criteria(criteria)
    total_models = max(len(models_to_export), 1)
    strings = get_strings()
    with zipfile.ZipFile(fileobj, "w", zipfile.ZIP_DEFLATED) as zf:
        for index, model in enumerate(models_to_export):
            if progress_callback:
                progress_callback(
                    5 + int((index / total_models) * 85),
                    strings.get("backup_progress_model", "Backing up {model}...").format(
                        model=str(model._meta.verbose_name),
                    ),
                )
            stream_model_into_zip(
                zf,
                model,
                _entry_export_queryset(model, actor, criteria, overview),
                manifest,
                human_record_folders=True,
                label_field_resolver=_backup_label_field,
                include_records=False,
            )
            if progress_callback:
                progress_callback(
                    5 + int(((index + 1) / total_models) * 85),
                    strings.get("backup_progress_model_done", "Backed up {model}.").format(
                        model=str(model._meta.verbose_name),
                    ),
                )
        if progress_callback:
            progress_callback(92, strings.get("reports_backup_building_workbook", "Building report workbook..."))
        zf.writestr(REPORT_ZIP_WORKBOOK_NAME, build_model_entries_xlsx(actor, overview))
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
    return manifest


def build_backup_zip(request, window="all", criteria=None):
    """In-memory backup build kept for backward compatibility (small datasets only)."""
    buffer = BytesIO()
    manifest = write_backup_zip(request.user, buffer, window=window, criteria=criteria)
    buffer.seek(0)
    log_user_action(
        request,
        "EXPORT",
        model_name="Dlux Reports Backup",
        details={
            "window": manifest["window"],
            "models": len(manifest["models"]),
            "files": len(manifest["files"]),
        },
    )
    return buffer.getvalue(), manifest


def _report_backup_model():
    return apps.get_model("dlux", "ReportBackup")


def report_backup_celery_available():
    """True when the backup task can actually run in the background right now:
    celery importable, broker reachable, and at least one live worker."""
    if not _reports_config().get("backup_use_celery", True):
        return False
    try:
        from ..tasks import build_report_backup_task
    except Exception:
        return False
    if build_report_backup_task is None:
        return False
    try:
        app = build_report_backup_task.app
        with app.connection_for_write() as conn:
            conn.ensure_connection(max_retries=0, timeout=2)
        return bool(app.control.ping(timeout=1.0))
    except Exception:
        return False


def dispatch_report_backup(backup):
    """Queue the backup build on Celery. Returns True when queued."""
    if not report_backup_celery_available():
        return False
    from ..tasks import build_report_backup_task
    try:
        build_report_backup_task.apply_async(args=[backup.pk], retry=False)
        return True
    except Exception:
        logger.exception("Failed to queue report backup pk=%s", backup.pk)
        return False


def _prune_report_backups(user, keep=3):
    ReportBackup = _report_backup_model()
    stale = list(
        ReportBackup.objects.filter(user=user, status=ReportBackup.STATUS_COMPLETED)
        .order_by("-created_at")[keep:]
    ) + list(
        ReportBackup.objects.filter(
            user=user,
            status=ReportBackup.STATUS_FAILED,
            created_at__lt=timezone.now() - timedelta(days=7),
        )
    )
    for old in stale:
        if old.file_path:
            try:
                default_storage.delete(old.file_path)
            except Exception:
                pass
        old.delete()


def run_report_backup(backup_pk):
    """Build the zip for a ReportBackup row and store it under the backup prefix.

    Runs inside the Celery worker (or inline as a last resort). Status/result
    are persisted on the row so the web process can poll over the shared DB.
    """
    ReportBackup = _report_backup_model()
    backup = ReportBackup.objects.filter(pk=backup_pk).first()
    if backup is None or backup.status not in (ReportBackup.STATUS_PENDING,):
        return backup
    logger.info(
        "Starting report backup pk=%s token=%s window=%s user_id=%s",
        backup.pk,
        backup.token,
        backup.window,
        backup.user_id,
    )
    backup.status = ReportBackup.STATUS_RUNNING
    backup.started_at = timezone.now()
    backup.save(update_fields=["status", "started_at"])
    from ..utils.backup_progress import finish_backup_progress, set_backup_progress, start_backup_progress
    start_backup_progress(backup)
    set_backup_progress(backup, 2, get_strings().get("backup_progress_preparing", "Preparing backup..."))
    try:
        with tempfile.TemporaryFile() as tmp:
            manifest = write_backup_zip(
                backup.user,
                tmp,
                window=backup.window,
                criteria=backup.criteria or None,
                progress_callback=lambda percent, message: set_backup_progress(backup, percent, message),
            )
            size = tmp.tell()
            tmp.seek(0)
            set_backup_progress(backup, 95, get_strings().get("backup_progress_storing", "Storing backup artifact..."))
            saved_path = default_storage.save(
                f"{get_backup_storage_prefix()}/{backup.token}.zip",
                File(tmp),
            )
        backup.file_path = saved_path
        backup.file_size = size
        backup.model_count = len(manifest["models"])
        backup.file_count = len(manifest["files"])
        backup.missing_file_count = len(manifest["missing_files"])
        backup.status = ReportBackup.STATUS_COMPLETED
        backup.completed_at = timezone.now()
        backup.error = ""
        backup.save()
        finish_backup_progress(backup, success=True)
        logger.info(
            "Completed report backup pk=%s token=%s size=%s models=%s files=%s missing=%s",
            backup.pk,
            backup.token,
            backup.file_size,
            backup.model_count,
            backup.file_count,
            backup.missing_file_count,
        )
        UserActivityLog = apps.get_model("dlux", "ActivityLog")
        UserActivityLog.safe_log(
            user=backup.user,
            action="EXPORT",
            model_name="Dlux Reports Backup",
            details={
                "window": backup.window,
                "criteria": backup.criteria,
                "models": backup.model_count,
                "files": backup.file_count,
            },
        )
        _prune_report_backups(backup.user)
    except Exception as exc:
        logger.exception("Report backup pk=%s failed", backup_pk)
        backup.status = ReportBackup.STATUS_FAILED
        backup.completed_at = timezone.now()
        backup.error = str(exc)[:1000]
        backup.save(update_fields=["status", "completed_at", "error"])
        finish_backup_progress(backup, success=False, error=backup.error)
    return backup
