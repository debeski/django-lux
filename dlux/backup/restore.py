"""Restoring a system backup, including the wipe-and-load path."""

import io
import json
import zipfile
from django.apps import apps
from django.conf import settings
from django.core import serializers
from django.core.files import File
from django.core.files.storage import default_storage
from django.core.management.color import no_style
from django.db import connection, transaction
from django.template.defaultfilters import filesizeformat
from django.utils import timezone

from ._shared import _dlux_version, _log_system_action, get_current_migration_state, logger
from .config import _is_user_model, get_system_backup_models
from .crypto import decrypt_dlb_to_tempfile
from .reporters import _format_count


def build_migration_report(manifest):
    """Compare the backup's migration state against this instance's."""
    backup_state = set(manifest.get("migration_state") or [])
    current_state = set(get_current_migration_state())
    return {
        "match": backup_state == current_state,
        "missing_on_target": sorted(backup_state - current_state),
        "extra_on_target": sorted(current_state - backup_state),
        "backup_dlux_version": manifest.get("dlux_version"),
        "current_dlux_version": _dlux_version(),
    }


def _zip_data_member(zf, model):
    name = f"data/{model._meta.app_label}/{model._meta.model_name}.json"
    try:
        zf.getinfo(name)
    except KeyError:
        return None
    return name


def _delete_model_rows_sql(model):
    return f"DELETE FROM {connection.ops.quote_name(model._meta.db_table)}"


def _delete_auto_m2m_rows(cursor, models_to_restore):
    """Clear implicit M2M tables so stale links cannot survive a restore."""
    seen = set()
    for model in models_to_restore:
        for field in model._meta.many_to_many:
            through = field.remote_field.through
            if not through._meta.auto_created or through._meta.db_table in seen:
                continue
            seen.add(through._meta.db_table)
            through_table = connection.ops.quote_name(through._meta.db_table)
            cursor.execute(f"DELETE FROM {through_table}")


def _current_superuser_passwords():
    User = apps.get_model(settings.AUTH_USER_MODEL)
    return dict(User._default_manager.filter(is_superuser=True).values_list(User.USERNAME_FIELD, "password"))


def _apply_superuser_password_policy(deserialized, current_passwords):
    obj = deserialized.object
    if not _is_user_model(obj.__class__) or not getattr(obj, "is_superuser", False):
        return
    username = getattr(obj, obj.USERNAME_FIELD)
    current_password = current_passwords.get(username)
    if current_password:
        obj.password = current_password
    else:
        obj.set_unusable_password()


def _wipe_and_load(zf, models_to_restore, reporter=None, *, span=(35, 70)):
    """Replace every restorable model's rows with the backup contents.

    Runs inside one transaction with FK checks deferred/disabled, so neither
    the wipe nor the load order matters; integrity is verified before commit.

    ``reporter`` progress spans ``span`` and is mirrored through the cache,
    because a row written from inside this transaction stays invisible to the
    polling web process until the whole load commits.
    """
    from ..signals import suspend_dlux_signals
    from ..utils.backup_progress import NullRestoreReporter
    from ..translations import get_strings

    if reporter is None:
        reporter = NullRestoreReporter()
    strings = get_strings()
    stage = "database"
    span_start, span_end = span
    total_models = max(len(models_to_restore), 1)
    counts = {}
    current_superuser_passwords = _current_superuser_passwords()
    with suspend_dlux_signals():
        with transaction.atomic():
            with connection.constraint_checks_disabled():
                reporter.checkpoint(
                    span_start,
                    strings.get("sysrestore_stage_wiping", "Clearing current data..."),
                    stage=stage,
                )
                with connection.cursor() as cursor:
                    # ReportBackup rows FK to users (which are being replaced) but are
                    # excluded from the payload — clear them so no dangling refs remain.
                    ReportBackup = apps.get_model("dlux", "ReportBackup")
                    cursor.execute(f"DELETE FROM {connection.ops.quote_name(ReportBackup._meta.db_table)}")
                    _delete_auto_m2m_rows(cursor, models_to_restore)
                    for model in reversed(models_to_restore):
                        cursor.execute(_delete_model_rows_sql(model))
                deferred = []
                load_start = span_start + 2
                load_span = max(span_end - load_start, 1)
                loading_label = strings.get("sysrestore_stage_loading", "Restoring")
                for index, model in enumerate(models_to_restore):
                    reporter.tick(
                        load_start + int((index / total_models) * load_span),
                        f"{loading_label} {model._meta.verbose_name} ({index + 1}/{total_models})",
                        stage=stage,
                    )
                    member = _zip_data_member(zf, model)
                    if member is None:
                        counts[model._meta.label_lower] = 0
                        continue
                    loaded = 0
                    with zf.open(member) as raw:
                        text = io.TextIOWrapper(raw, encoding="utf-8")
                        for obj in serializers.deserialize("json", text, handle_forward_references=True):
                            _apply_superuser_password_policy(obj, current_superuser_passwords)
                            obj.save()
                            if getattr(obj, "deferred_fields", None):
                                deferred.append(obj)
                            loaded += 1
                            if loaded % 500 == 0:
                                reporter.tick(
                                    load_start + int((index / total_models) * load_span),
                                    f"{loading_label} {model._meta.verbose_name} "
                                    f"({_format_count(loaded)})",
                                    stage=stage,
                                )
                    counts[model._meta.label_lower] = loaded
                reporter.checkpoint(
                    span_end - 1,
                    strings.get("sysrestore_stage_integrity", "Verifying integrity..."),
                    stage=stage,
                )
                for obj in deferred:
                    obj.save_deferred_fields()
                table_names = [model._meta.db_table for model in models_to_restore]
                connection.check_constraints(table_names=table_names)
    # Outside the transaction: bring PK sequences in line with the restored ids.
    reset_sql = connection.ops.sequence_reset_sql(no_style(), models_to_restore)
    if reset_sql:
        with connection.cursor() as cursor:
            for statement in reset_sql:
                cursor.execute(statement)
    return counts


def _restore_files(zf, manifest, reporter=None, *, span=(70, 92)):
    from ..utils.backup_progress import NullRestoreReporter
    from ..translations import get_strings

    if reporter is None:
        reporter = NullRestoreReporter()
    strings = get_strings()
    entries = [
        entry for entry in (manifest.get("files") or [])
        if entry.get("path") and entry.get("name")
    ]
    total = max(len(entries), 1)
    span_start, span_end = span
    span_width = max(span_end - span_start, 1)
    label = strings.get("sysrestore_stage_files", "Restoring files")
    reporter.checkpoint(
        span_start,
        f"{label} (0/{_format_count(len(entries))})",
        stage="files",
    )
    restored, failed = 0, 0
    for index, entry in enumerate(entries):
        archive_path = entry["path"]
        storage_name = entry["name"]
        try:
            if default_storage.exists(storage_name):
                default_storage.delete(storage_name)
            with zf.open(archive_path) as fh:
                default_storage.save(storage_name, File(fh))
            restored += 1
        except Exception:
            logger.exception("Failed to restore backup file %s", storage_name)
            failed += 1
        reporter.tick(
            span_start + int(((index + 1) / total) * span_width),
            f"{label} ({_format_count(index + 1)}/{_format_count(len(entries))})",
            stage="files",
        )
    return restored, failed


def run_system_restore(restore_pk, passphrase=None):
    """Celery-or-inline runner that fully replaces system data from an .dlb file."""
    SystemRestore = apps.get_model("dlux", "SystemRestore")
    restore = SystemRestore.objects.filter(pk=restore_pk).first()
    if restore is None or restore.status != SystemRestore.STATUS_PENDING:
        return restore
    restore.status = SystemRestore.STATUS_RUNNING
    restore.started_at = timezone.now()
    restore.save(update_fields=["status", "started_at"])
    from ..utils.backup_progress import RestoreReporter, finish_restore_progress
    from ..translations import get_strings
    strings = get_strings()
    reporter = RestoreReporter(restore)
    try:
        if not restore.backup_file_path or not default_storage.exists(restore.backup_file_path):
            raise ValueError("Backup file not found in storage")
        reporter.checkpoint(
            2,
            strings.get("sysrestore_stage_reading", "Reading the backup file..."),
            stage=SystemRestore.STAGE_READING,
        )
        try:
            container_size = default_storage.size(restore.backup_file_path)
        except Exception:
            container_size = 0
        decrypt_label = strings.get("sysrestore_stage_decrypting", "Decrypting")
        total_label = filesizeformat(container_size) if container_size else ""

        def _on_decrypt(consumed):
            if container_size:
                percent = 3 + int(min(consumed / container_size, 1.0) * 27)
                message = f"{decrypt_label} {filesizeformat(consumed)} / {total_label}"
            else:
                percent = 15
                message = f"{decrypt_label} {filesizeformat(consumed)}"
            reporter.tick(percent, message, stage=SystemRestore.STAGE_DECRYPTING)

        with default_storage.open(restore.backup_file_path, "rb") as fh:
            metadata, zip_tmp = decrypt_dlb_to_tempfile(
                fh, passphrase=passphrase, on_chunk=_on_decrypt,
            )
        try:
            with zipfile.ZipFile(zip_tmp) as zf:
                reporter.checkpoint(
                    32,
                    strings.get("sysrestore_stage_manifest", "Checking the backup contents..."),
                    stage=SystemRestore.STAGE_READING,
                )
                manifest = json.loads(zf.read("manifest.json"))
                migration_report = build_migration_report(manifest)
                report = {"metadata": metadata, "migrations": migration_report}
                if not migration_report["match"] and not restore.ignore_version_mismatch:
                    restore.report = report
                    restore.status = SystemRestore.STATUS_FAILED
                    restore.completed_at = timezone.now()
                    restore.error = "Migration state mismatch between backup and this system"
                    restore.save(update_fields=["report", "status", "completed_at", "error"])
                    finish_restore_progress(restore, success=False, error=restore.error)
                    return restore
                models_to_restore = get_system_backup_models()
                counts = _wipe_and_load(zf, models_to_restore, reporter)
                files_restored, files_failed = _restore_files(zf, manifest, reporter)
                report["restored_rows"] = sum(counts.values())
                report["restored_models"] = len(counts)
                report["restored_files"] = files_restored
                report["failed_files"] = files_failed
        finally:
            zip_tmp.close()
        reporter.checkpoint(
            95,
            strings.get("sysrestore_stage_finalizing", "Clearing caches and sessions..."),
            stage=SystemRestore.STAGE_FINALIZING,
        )
        # Restored data invalidates every cached artifact: sessions (all users
        # must sign back in with restored credentials), the SystemSettings
        # singleton, sidebar caches, and content-type caches.
        from django.contrib.contenttypes.models import ContentType
        from django.core.cache import cache
        ContentType.objects.clear_cache()
        cache.clear()
        restore.report = report
        restore.status = SystemRestore.STATUS_COMPLETED
        restore.completed_at = timezone.now()
        restore.error = ""
        restore.save()
        _log_system_action(restore.requested_by_username, "RESTORE", {
            "kind": "system_restore",
            "rows": report.get("restored_rows"),
            "files": report.get("restored_files"),
            "backup_created_at": metadata.get("created_at"),
        })
        finish_restore_progress(restore, success=True)
    except Exception as exc:
        logger.exception("System restore pk=%s failed", restore_pk)
        restore.status = SystemRestore.STATUS_FAILED
        restore.completed_at = timezone.now()
        restore.error = str(exc)[:1000]
        restore.save(update_fields=["status", "completed_at", "error"])
        finish_restore_progress(restore, success=False, error=restore.error)
    return restore
