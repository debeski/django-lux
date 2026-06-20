"""Full system backup & restore (.dlb files).

This is deliberately separate from the reports backup (``dlux.reports``):
the reports backup is the supervisor's scoped, window-filtered monitoring
export, while this module produces a complete, encrypted, all-time snapshot of
every model (users, scopes, password hashes, settings, activity history) plus
all referenced storage files — built so a restore can fully replace a system.

Container format (``.dlb`` — "dlux backup"):

    DLB1 | u32 metadata length | metadata JSON (cleartext, non-sensitive)
         | repeated frames: u64 token length | Fernet token (32MB plaintext chunks)

The payload is a regular backup zip (same layout the reports backup uses, via
``reports.stream_model_into_zip``) encrypted chunk-by-chunk with Fernet, so
arbitrarily large backups encrypt/decrypt with flat memory. By default the key
is derived from Django's ``SECRET_KEY`` plus a per-file random salt. A
superuser may instead provide a one-off passphrase when creating the backup;
that passphrase is then required for restore.
"""

import base64
import hashlib
import io
import json
import logging
import secrets
import struct
import tempfile
import zipfile

from django.apps import apps
from django.conf import settings
from django.core import serializers
from django.core.files import File
from django.core.files.storage import default_storage
from django.core.management.color import no_style
from django.db import connection, transaction
from django.db.migrations.recorder import MigrationRecorder
from django.utils import timezone

from .reports import get_backup_storage_prefix, stream_model_into_zip

logger = logging.getLogger("dlux")

DLB_MAGIC = b"DLB1"
DLB_FORMAT_VERSION = 1
_CHUNK_SIZE = 32 * 1024 * 1024
_PASSWORD_KDF_ITERATIONS = 390_000

# Environment-owned or run-bookkeeping models that must never be dumped:
# sessions are ephemeral, contenttypes/permissions are recreated by migrate
# (rows are referenced via natural keys instead), and the backup/restore
# bookkeeping itself can't be part of the payload it describes.
_SYSTEM_BACKUP_EXCLUDED = {
    "sessions.session",
    "contenttypes.contenttype",
    "auth.permission",
    "admin.logentry",
    "dlux.reportbackup",
    "dlux.systembackup",
    "dlux.systemrestore",
}

_SUPERUSER_PASSWORD_OMITTED = "!dlux-superuser-password-omitted"


def _backup_config():
    config = getattr(settings, "DLUX_CONFIG", {}).get("backup", {})
    return config if isinstance(config, dict) else {}


def _config_excluded_keys():
    values = _backup_config().get("exclude_models", [])
    if isinstance(values, str):
        values = [values]
    return {str(v or "").strip().lower() for v in values or [] if str(v or "").strip()}


def _dependency_sorted(models_list):
    """Order models so FK/M2M targets come before their referrers.

    Natural-key references (e.g. Profile.user → User by username) are resolved
    against the database at deserialize time; if the target rows aren't loaded
    yet the deserializer defers the field as NULL, which NOT NULL columns
    reject immediately. INSTALLED_APPS order gives no such guarantee (host
    projects often list dlux before django.contrib.auth), so restores must
    load in dependency order. Cycles are broken at the back-edge — deferrable
    FK constraints cover those at commit.
    """
    included = set(models_list)
    deps = {}
    for model in models_list:
        targets = set()
        for field in model._meta.concrete_fields:
            related = getattr(field, "related_model", None)
            if field.is_relation and related in included and related is not model:
                targets.add(related)
        for field in model._meta.many_to_many:
            related = field.related_model
            if related in included and related is not model:
                targets.add(related)
        deps[model] = targets
    ordered, visiting, visited = [], set(), set()

    def visit(model):
        if model in visited or model in visiting:
            return
        visiting.add(model)
        for target in sorted(deps[model], key=lambda m: m._meta.label_lower):
            visit(target)
        visiting.discard(model)
        visited.add(model)
        ordered.append(model)

    for model in models_list:
        visit(model)
    return ordered


def get_system_backup_models():
    """Every concrete managed model that belongs in a full snapshot, dependency-ordered."""
    excluded = _SYSTEM_BACKUP_EXCLUDED | _config_excluded_keys()
    result = []
    for model in apps.get_models():
        meta = model._meta
        if meta.abstract or meta.proxy or not meta.managed or meta.auto_created:
            continue
        if meta.label_lower in excluded:
            continue
        result.append(model)
    return _dependency_sorted(result)


def _system_model_queryset(model):
    manager = getattr(model, "all_objects", model._base_manager)
    return manager.all()


def _is_user_model(model):
    return model is apps.get_model(settings.AUTH_USER_MODEL)


def _scrub_superuser_password(obj):
    """Serialize superuser accounts without their password hash."""
    if _is_user_model(obj.__class__) and getattr(obj, "is_superuser", False):
        obj.password = _SUPERUSER_PASSWORD_OMITTED
    return obj


def get_current_migration_state():
    applied = MigrationRecorder(connection).applied_migrations()
    return sorted(f"{app}.{name}" for app, name in applied)


def _dlux_version():
    try:
        import dlux
        return str(getattr(dlux, "__version__", "")) or "unknown"
    except Exception:
        return "unknown"


# ── Encryption ───────────────────────────────────────────────────────────────


def _clean_passphrase(passphrase):
    value = "" if passphrase is None else str(passphrase)
    return value.strip()


def _django_secret_key_seed():
    return str(getattr(settings, "SECRET_KEY", "") or "dlux-backup-secret-dev-key")


def _derive_backup_key(salt_hex, *, encryption=None, passphrase=None):
    salt = bytes.fromhex(salt_hex)
    encryption = encryption or {}
    kdf = encryption.get("kdf")
    key_source = encryption.get("key_source")

    # Backward-compatible reader for early unreleased DLB1 files. Only Django
    # SECRET_KEY is used for this legacy key source.
    if kdf == "sha256-salt-seed":
        return hashlib.sha256(salt + _django_secret_key_seed().encode("utf-8")).digest()

    if key_source == "passphrase":
        seed = _clean_passphrase(passphrase)
        if not seed:
            raise ValueError("Backup passphrase is required")
    else:
        seed = _django_secret_key_seed()

    iterations = int(encryption.get("iterations") or _PASSWORD_KDF_ITERATIONS)
    return hashlib.pbkdf2_hmac("sha256", seed.encode("utf-8"), salt, iterations, dklen=32)


def _backup_fernet(salt_hex, *, encryption=None, passphrase=None):
    from cryptography.fernet import Fernet

    digest = _derive_backup_key(salt_hex, encryption=encryption, passphrase=passphrase)
    return Fernet(base64.urlsafe_b64encode(digest))


# ── .dlb container ───────────────────────────────────────────────────────────


def _encrypt_stream(src, dest, salt_hex, *, encryption, passphrase=None):
    fernet = _backup_fernet(salt_hex, encryption=encryption, passphrase=passphrase)
    while True:
        chunk = src.read(_CHUNK_SIZE)
        if not chunk:
            break
        token = fernet.encrypt(chunk)
        dest.write(struct.pack(">Q", len(token)))
        dest.write(token)


def _decrypt_stream(src, dest, salt_hex, *, encryption, passphrase=None):
    fernet = _backup_fernet(salt_hex, encryption=encryption, passphrase=passphrase)
    while True:
        header = src.read(8)
        if not header:
            break
        if len(header) != 8:
            raise ValueError("Truncated backup container")
        (length,) = struct.unpack(">Q", header)
        token = src.read(length)
        if len(token) != length:
            raise ValueError("Truncated backup container")
        dest.write(fernet.decrypt(token))


def write_dlb_container(zip_fileobj, dest, metadata, *, passphrase=None):
    """Wrap an already-built backup zip stream into an encrypted .dlb container."""
    salt_hex = secrets.token_bytes(16).hex()
    has_passphrase = bool(_clean_passphrase(passphrase))
    encryption = {
        "scheme": "fernet-chunked",
        "kdf": "pbkdf2-sha256",
        "salt": salt_hex,
        "iterations": _PASSWORD_KDF_ITERATIONS,
        "key_source": "passphrase" if has_passphrase else "django-secret-key",
        "passphrase_required": has_passphrase,
    }
    metadata = dict(metadata or {})
    metadata.setdefault("format", DLB_FORMAT_VERSION)
    metadata.setdefault("kind", "dlux-system-backup")
    metadata["encryption"] = encryption
    payload = json.dumps(metadata, ensure_ascii=False).encode("utf-8")
    dest.write(DLB_MAGIC)
    dest.write(struct.pack(">I", len(payload)))
    dest.write(payload)
    _encrypt_stream(zip_fileobj, dest, salt_hex, encryption=encryption, passphrase=passphrase)
    return metadata


def read_dlb_metadata(fileobj):
    """Read and return the cleartext metadata header; leaves the stream at the payload."""
    magic = fileobj.read(len(DLB_MAGIC))
    if magic != DLB_MAGIC:
        raise ValueError("Not a Dlux backup (.dlb) file")
    (length,) = struct.unpack(">I", fileobj.read(4))
    if length <= 0 or length > 10 * 1024 * 1024:
        raise ValueError("Corrupt backup metadata header")
    metadata = json.loads(fileobj.read(length).decode("utf-8"))
    if metadata.get("kind") != "dlux-system-backup":
        raise ValueError("Unsupported backup kind")
    return metadata


def decrypt_dlb_to_tempfile(fileobj, *, passphrase=None):
    """Decrypt an .dlb stream (positioned anywhere) into a temp zip file.

    Returns ``(metadata, tempfile)`` with the temp file positioned at 0.
    The caller owns closing the temp file.
    """
    fileobj.seek(0)
    metadata = read_dlb_metadata(fileobj)
    encryption = metadata.get("encryption") or {}
    salt_hex = str(encryption.get("salt") or "")
    if not salt_hex:
        raise ValueError("Backup metadata is missing encryption parameters")
    tmp = tempfile.TemporaryFile()
    try:
        _decrypt_stream(fileobj, tmp, salt_hex, encryption=encryption, passphrase=passphrase)
    except Exception:
        tmp.close()
        raise
    tmp.seek(0)
    return metadata, tmp


# ── Full backup build ────────────────────────────────────────────────────────


def write_system_backup(dest, *, passphrase=None):
    """Build the complete encrypted system backup into ``dest``. Returns metadata."""
    manifest = {
        "kind": "dlux-system-backup",
        "generated_at": timezone.now().isoformat(),
        "dlux_version": _dlux_version(),
        "migration_state": get_current_migration_state(),
        "superuser_policy": {
            "users": "included",
            "password_hashes": "omitted",
            "restore": "target_password_preserved_when_username_matches",
        },
        "models": [],
        "files": [],
        "missing_files": [],
    }
    with tempfile.TemporaryFile() as zip_tmp:
        with zipfile.ZipFile(zip_tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            for model in get_system_backup_models():
                qs = _system_model_queryset(model)
                stream_model_into_zip(
                    zf, model, qs, manifest,
                    serialize_kwargs={"use_natural_foreign_keys": True},
                    object_transform=_scrub_superuser_password,
                )
            zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        zip_tmp.seek(0)
        metadata = write_dlb_container(zip_tmp, dest, {
            "created_at": manifest["generated_at"],
            "dlux_version": manifest["dlux_version"],
            "models": len(manifest["models"]),
            "rows": sum(item["count"] for item in manifest["models"]),
            "files": len(manifest["files"]),
            "passphrase_required": bool(_clean_passphrase(passphrase)),
        }, passphrase=passphrase)
    return metadata, manifest


def run_system_backup(backup_pk, passphrase=None):
    """Celery-or-inline runner that builds the .dlb for a SystemBackup row."""
    SystemBackup = apps.get_model("dlux", "SystemBackup")
    backup = SystemBackup.objects.filter(pk=backup_pk).first()
    if backup is None or backup.status != SystemBackup.STATUS_PENDING:
        return backup
    backup.status = SystemBackup.STATUS_RUNNING
    backup.started_at = timezone.now()
    backup.save(update_fields=["status", "started_at"])
    try:
        with tempfile.TemporaryFile() as tmp:
            metadata, manifest = write_system_backup(tmp, passphrase=passphrase)
            size = tmp.tell()
            tmp.seek(0)
            saved_path = default_storage.save(
                f"{get_backup_storage_prefix()}/system-{backup.token}.dlb",
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
        backup.error = ""
        backup.save()
        _log_system_action(backup.requested_by_username, "EXPORT", {
            "kind": "system_backup",
            "models": backup.model_count,
            "rows": backup.row_count,
            "files": backup.file_count,
        })
    except Exception as exc:
        logger.exception("System backup pk=%s failed", backup_pk)
        backup.status = SystemBackup.STATUS_FAILED
        backup.completed_at = timezone.now()
        backup.error = str(exc)[:1000]
        backup.save(update_fields=["status", "completed_at", "error"])
    return backup


def _log_system_action(username, action, details):
    try:
        UserActivityLog = apps.get_model("dlux", "ActivityLog")
        User = apps.get_model(settings.AUTH_USER_MODEL)
        user = User._default_manager.filter(username=username).first()
        UserActivityLog.safe_log(
            user=user,
            action=action,
            model_name="Dlux System Backup",
            details=details,
        )
    except Exception:
        pass


# ── Restore ──────────────────────────────────────────────────────────────────


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


def _wipe_and_load(zf, models_to_restore):
    """Replace every restorable model's rows with the backup contents.

    Runs inside one transaction with FK checks deferred/disabled, so neither
    the wipe nor the load order matters; integrity is verified before commit.
    """
    from .signals import suspend_dlux_signals

    counts = {}
    current_superuser_passwords = _current_superuser_passwords()
    with suspend_dlux_signals():
        with transaction.atomic():
            with connection.constraint_checks_disabled():
                with connection.cursor() as cursor:
                    # ReportBackup rows FK to users (which are being replaced) but are
                    # excluded from the payload — clear them so no dangling refs remain.
                    ReportBackup = apps.get_model("dlux", "ReportBackup")
                    cursor.execute(f"DELETE FROM {connection.ops.quote_name(ReportBackup._meta.db_table)}")
                    _delete_auto_m2m_rows(cursor, models_to_restore)
                    for model in reversed(models_to_restore):
                        cursor.execute(_delete_model_rows_sql(model))
                deferred = []
                for model in models_to_restore:
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
                    counts[model._meta.label_lower] = loaded
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


def _restore_files(zf, manifest):
    restored, failed = 0, 0
    for entry in manifest.get("files") or []:
        archive_path = entry.get("path")
        storage_name = entry.get("name")
        if not archive_path or not storage_name:
            continue
        try:
            if default_storage.exists(storage_name):
                default_storage.delete(storage_name)
            with zf.open(archive_path) as fh:
                default_storage.save(storage_name, File(fh))
            restored += 1
        except Exception:
            logger.exception("Failed to restore backup file %s", storage_name)
            failed += 1
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
    try:
        if not restore.backup_file_path or not default_storage.exists(restore.backup_file_path):
            raise ValueError("Backup file not found in storage")
        with default_storage.open(restore.backup_file_path, "rb") as fh:
            metadata, zip_tmp = decrypt_dlb_to_tempfile(fh, passphrase=passphrase)
        try:
            with zipfile.ZipFile(zip_tmp) as zf:
                manifest = json.loads(zf.read("manifest.json"))
                migration_report = build_migration_report(manifest)
                report = {"metadata": metadata, "migrations": migration_report}
                if not migration_report["match"] and not restore.ignore_version_mismatch:
                    restore.report = report
                    restore.status = SystemRestore.STATUS_FAILED
                    restore.completed_at = timezone.now()
                    restore.error = "Migration state mismatch between backup and this system"
                    restore.save(update_fields=["report", "status", "completed_at", "error"])
                    return restore
                models_to_restore = get_system_backup_models()
                counts = _wipe_and_load(zf, models_to_restore)
                files_restored, files_failed = _restore_files(zf, manifest)
                report["restored_rows"] = sum(counts.values())
                report["restored_models"] = len(counts)
                report["restored_files"] = files_restored
                report["failed_files"] = files_failed
        finally:
            zip_tmp.close()
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
    except Exception as exc:
        logger.exception("System restore pk=%s failed", restore_pk)
        restore.status = SystemRestore.STATUS_FAILED
        restore.completed_at = timezone.now()
        restore.error = str(exc)[:1000]
        restore.save(update_fields=["status", "completed_at", "error"])
    return restore


# ── Dispatch (Celery when available) ─────────────────────────────────────────


def system_backup_celery_available():
    if not _backup_config().get("use_celery", True):
        return False
    try:
        from .tasks import build_system_backup_task
    except Exception:
        return False
    if build_system_backup_task is None:
        return False
    try:
        app = build_system_backup_task.app
        with app.connection_for_write() as conn:
            conn.ensure_connection(max_retries=0, timeout=2)
        return bool(app.control.ping(timeout=1.0))
    except Exception:
        return False


def dispatch_system_backup(backup, *, passphrase=None):
    if not system_backup_celery_available():
        return False
    from .tasks import build_system_backup_task
    try:
        build_system_backup_task.apply_async(args=[backup.pk, _clean_passphrase(passphrase)], retry=False)
        return True
    except Exception:
        logger.exception("Failed to queue system backup pk=%s", backup.pk)
        return False


def dispatch_system_restore(restore, *, passphrase=None):
    if not system_backup_celery_available():
        return False
    from .tasks import restore_system_backup_task
    try:
        restore_system_backup_task.apply_async(args=[restore.pk, _clean_passphrase(passphrase)], retry=False)
        return True
    except Exception:
        logger.exception("Failed to queue system restore pk=%s", restore.pk)
        return False
