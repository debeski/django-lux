"""Writing and running a system backup."""

import json
import tempfile
import zipfile
from datetime import timedelta
from django.apps import apps
from django.core.files import File
from django.core.files.storage import default_storage
from django.db import models
from django.template.defaultfilters import filesizeformat
from django.utils import timezone
from ..utils.archive import build_relation_schema, stream_model_into_zip

from ._shared import _SUPERUSER_PASSWORD_OMITTED, _dlux_version, _log_system_action, get_current_migration_state, logger
from .config import _backup_config, _is_user_model, _system_model_queryset, get_system_backup_models, get_system_backup_storage_prefix
from .crypto import _clean_passphrase, write_dlb_container
from .reporters import _BackupReporter, _CallbackReporter, _NullReporter, _format_count
from .retry import fail_system_backup


def _scrub_superuser_password(obj):
    """Serialize superuser accounts without their password hash."""
    if _is_user_model(obj.__class__) and getattr(obj, "is_superuser", False):
        obj.password = _SUPERUSER_PASSWORD_OMITTED
    return obj


def write_system_backup(dest, *, passphrase=None, progress_callback=None, reporter=None, include_media=True):
    """Build the complete encrypted system backup into ``dest``. Returns metadata.

    ``include_media=False`` writes a data-only backup (database rows + migration
    state, no media blobs) — much faster, used for the inline updater's pre-update
    safety snapshot since an inline code/schema update never alters media on disk.

    ``reporter`` receives coarse ``checkpoint()`` milestones and frequent
    ``tick()`` sub-progress; ``progress_callback`` is the older two-argument
    milestone-only form.
    """
    if reporter is None:
        reporter = _CallbackReporter(progress_callback) if progress_callback else _NullReporter()
    manifest = {
        "kind": "dlux-system-backup",
        "generated_at": timezone.now().isoformat(),
        "dlux_version": _dlux_version(),
        "migration_state": get_current_migration_state(),
        "media_included": bool(include_media),
        "superuser_policy": {
            "users": "included",
            "password_hashes": "omitted",
            "restore": "target_password_preserved_when_username_matches",
        },
        "models": [],
        "files": [],
        "missing_files": [],
    }
    models_to_export = get_system_backup_models()
    # Bake relation/label schema into the manifest so the standalone .dlb viewer
    # can resolve FK/M2M/O2O references to readable names without this project.
    manifest["schema"] = build_relation_schema(models_to_export)
    total_models = max(len(models_to_export), 1)
    from ..translations import get_strings
    strings = get_strings()
    STAGE_MODELS = "models"
    STAGE_ENCRYPTING = "encrypting"
    with tempfile.TemporaryFile() as zip_tmp:
        with zipfile.ZipFile(zip_tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            for index, model in enumerate(models_to_export):
                model_label = str(model._meta.verbose_name)
                span_start = 5 + int((index / total_models) * 70)
                span_end = 5 + int(((index + 1) / total_models) * 70)
                reporter.checkpoint(
                    span_start,
                    strings.get("backup_progress_model", "Backing up {model}...").format(model=model_label),
                    stage=STAGE_MODELS,
                )

                def report_step(step_stage, done, total, _start=span_start, _end=span_end, _label=model_label):
                    # Sub-progress is confined to this model's slice of the 5–75
                    # band, so the bar keeps creeping instead of freezing on a
                    # model that owns thousands of uploads.
                    share = (done / total) if total else 1.0
                    if step_stage == "files":
                        share = 0.5 + (share * 0.5)
                    else:
                        share = share * 0.5
                    template = (
                        "backup_progress_model_files" if step_stage == "files" else "backup_progress_model_rows"
                    )
                    fallback = (
                        "Backing up {model} - files {done}/{total}..."
                        if step_stage == "files"
                        else "Backing up {model} - records {done}/{total}..."
                    )
                    reporter.tick(
                        _start + int((_end - _start) * share),
                        strings.get(template, fallback).format(
                            model=_label,
                            done=_format_count(done),
                            total=_format_count(total),
                        ),
                        stage=STAGE_MODELS,
                    )

                qs = _system_model_queryset(model)
                stream_model_into_zip(
                    zf, model, qs, manifest,
                    serialize_kwargs={"use_natural_foreign_keys": True},
                    object_transform=_scrub_superuser_password,
                    include_files=include_media,
                    step_callback=report_step,
                )
                reporter.checkpoint(
                    span_end,
                    strings.get("backup_progress_model_done", "Backed up {model}.").format(model=model_label),
                    stage=STAGE_MODELS,
                )
            zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        payload_size = zip_tmp.tell()
        zip_tmp.seek(0)
        reporter.checkpoint(
            82,
            strings.get("backup_progress_encrypting", "Encrypting backup artifact..."),
            stage=STAGE_ENCRYPTING,
        )

        def report_encryption(written):
            share = (written / payload_size) if payload_size else 1.0
            reporter.tick(
                82 + int(min(1.0, share) * 12),
                strings.get(
                    "backup_progress_encrypting_bytes",
                    "Encrypting backup artifact ({done} of {total})...",
                ).format(done=filesizeformat(written), total=filesizeformat(payload_size)),
                stage=STAGE_ENCRYPTING,
            )

        metadata = write_dlb_container(zip_tmp, dest, {
            "created_at": manifest["generated_at"],
            "dlux_version": manifest["dlux_version"],
            "models": len(manifest["models"]),
            "rows": sum(item["count"] for item in manifest["models"]),
            "files": len(manifest["files"]),
            "media_included": bool(include_media),
            "passphrase_required": bool(_clean_passphrase(passphrase)),
        }, passphrase=passphrase, on_chunk=report_encryption)
    return metadata, manifest


def run_system_backup(backup_pk, passphrase=None, *, allow_passphrase_retry=False):
    """Celery-or-inline runner that builds the .dlb for a SystemBackup row.

    Whether media blobs are included is read from ``backup.media_included`` (set by
    the caller when the row is created), so the choice survives a Celery handoff —
    the task only receives the pk. ``media_included=False`` yields a faster data-only
    snapshot (database + migration state), used by the inline updater's pre-update
    backup and by manual "quick" backups.

    ``allow_passphrase_retry`` is set only by the Celery task, which can arm an
    automatic retry for a passphrase-protected backup because it re-queues itself
    with the same arguments; no other caller can reproduce that passphrase.
    """
    SystemBackup = apps.get_model("dlux", "SystemBackup")
    backup = SystemBackup.objects.filter(pk=backup_pk).first()
    if backup is None or backup.status != SystemBackup.STATUS_PENDING:
        return backup
    now = timezone.now()
    # The pending → running transition is the claim, and it is the only one:
    # a queued retry, a due-retry sweep, and an operator's Resume can all aim at
    # the same row, and exactly one of them must build it.
    claimed = SystemBackup.objects.filter(
        pk=backup.pk,
        status=SystemBackup.STATUS_PENDING,
    ).filter(
        models.Q(next_attempt_at__isnull=True) | models.Q(next_attempt_at__lte=now),
    ).update(
        status=SystemBackup.STATUS_RUNNING,
        started_at=now,
        heartbeat_at=now,
        stage=SystemBackup.STAGE_PREPARING,
        attempt_count=models.F("attempt_count") + 1,
        next_attempt_at=None,
    )
    if not claimed:
        backup.refresh_from_db()
        return backup
    backup.refresh_from_db()
    include_media = bool(backup.media_included)
    from ..utils.backup_progress import finish_backup_progress, start_backup_progress
    from ..translations import get_strings
    start_backup_progress(backup)
    reporter = _BackupReporter(backup)
    reporter.checkpoint(
        2,
        get_strings().get("backup_progress_preparing", "Preparing backup..."),
        stage=SystemBackup.STAGE_PREPARING,
    )
    try:
        with tempfile.TemporaryFile() as tmp:
            metadata, manifest = write_system_backup(
                tmp,
                passphrase=passphrase,
                reporter=reporter,
                include_media=include_media,
            )
            size = tmp.tell()
            tmp.seek(0)
            reporter.checkpoint(
                95,
                get_strings().get("backup_progress_storing", "Storing backup artifact..."),
                stage=SystemBackup.STAGE_STORING,
            )
            saved_path = default_storage.save(
                f"{get_system_backup_storage_prefix()}/system-{backup.token}.dlb",
                File(tmp),
            )
        backup.file_path = saved_path
        backup.file_size = size
        backup.model_count = metadata["models"]
        backup.row_count = metadata["rows"]
        backup.file_count = metadata["files"]
        backup.missing_file_count = len(manifest["missing_files"])
        backup.passphrase_required = bool(metadata.get("passphrase_required"))
        backup.status = SystemBackup.STATUS_COMPLETED
        backup.completed_at = timezone.now()
        backup.heartbeat_at = backup.completed_at
        backup.stage = ""
        backup.next_attempt_at = None
        backup.error = ""
        backup.save()
        finish_backup_progress(backup, success=True)
        _log_system_action(backup.requested_by_username, "EXPORT", {
            "kind": "system_backup",
            "trigger": backup.trigger,
            "models": backup.model_count,
            "rows": backup.row_count,
            "files": backup.file_count,
            "attempts": backup.attempt_count,
        })
        apply_backup_retention(protected_pk=backup.pk)
    except Exception as exc:
        logger.exception("System backup pk=%s failed", backup_pk)
        fail_system_backup(
            backup,
            str(exc)[:1000],
            passphrase_in_hand=bool(allow_passphrase_retry and _clean_passphrase(passphrase)),
        )
    return backup


def apply_backup_retention(*, protected_pk=None, now=None):
    """Apply configured age/count rotation to completed system backups.

    File removal and row removal are deliberately best-effort per item; a
    storage outage must not turn an otherwise valid new backup into a failure.
    """
    SystemBackup = apps.get_model("dlux", "SystemBackup")
    config = _backup_config()
    retention_days = config["retention_days"]
    max_to_keep = config["max_backups_to_keep"]
    now = now or timezone.now()
    candidates = SystemBackup.objects.filter(status=SystemBackup.STATUS_COMPLETED).order_by("-created_at")
    delete_pks = set()
    if retention_days:
        cutoff = now - timedelta(days=retention_days)
        delete_pks.update(candidates.filter(created_at__lt=cutoff).values_list("pk", flat=True))
    if max_to_keep:
        delete_pks.update(candidates.values_list("pk", flat=True)[max_to_keep:])
    if protected_pk is not None:
        delete_pks.discard(protected_pk)

    removed = 0
    for old_backup in SystemBackup.objects.filter(pk__in=delete_pks):
        try:
            if old_backup.file_path:
                default_storage.delete(old_backup.file_path)
            old_backup.delete()
            removed += 1
        except Exception:
            logger.exception("Could not rotate system backup pk=%s", old_backup.pk)
    return removed
