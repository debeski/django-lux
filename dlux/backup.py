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
import time
import zipfile
from datetime import timedelta

from django.apps import apps
from django.conf import settings
from django.core import serializers
from django.core.files import File
from django.core.files.storage import default_storage
from django.core.management.color import no_style
from django.db import connection, models, transaction
from django.db.migrations.recorder import MigrationRecorder
from django.template.defaultfilters import filesizeformat
from django.utils import timezone

from .reports import build_relation_schema, stream_model_into_zip
from .system.defaults import default_backup_config
from .system.normalizers import normalize_backup_config

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
    "dlux.dluxupdatestate",
    "dlux.dluxupdaterun",
}

_SUPERUSER_PASSWORD_OMITTED = "!dlux-superuser-password-omitted"


def _backup_config():
    try:
        from .utils import get_system_config

        config = get_system_config().get("backup_config", {})
    except Exception:
        config = getattr(settings, "DLUX_CONFIG", {}).get("backup", {})
    return normalize_backup_config(config)


def get_system_backup_storage_prefix():
    """Return the safe folder used for full-system backups in default_storage."""
    return _backup_config().get("auto_export_target") or default_backup_config()["auto_export_target"]


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
    queryset = manager.all()
    if model._meta.label_lower == "dlux.dluxnotification":
        queryset = queryset.exclude(
            category="backup",
            source="backup",
            metadata__backup_progress=True,
        )
    elif model._meta.label_lower == "dlux.dluxnotificationstate":
        queryset = queryset.exclude(
            notification__category="backup",
            notification__source="backup",
            notification__metadata__backup_progress=True,
        )
    return queryset


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


def _encrypt_stream(src, dest, salt_hex, *, encryption, passphrase=None, on_chunk=None):
    fernet = _backup_fernet(salt_hex, encryption=encryption, passphrase=passphrase)
    written = 0
    while True:
        chunk = src.read(_CHUNK_SIZE)
        if not chunk:
            break
        token = fernet.encrypt(chunk)
        dest.write(struct.pack(">Q", len(token)))
        dest.write(token)
        written += len(chunk)
        if on_chunk:
            on_chunk(written)


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


def write_dlb_container(zip_fileobj, dest, metadata, *, passphrase=None, on_chunk=None):
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
    _encrypt_stream(
        zip_fileobj, dest, salt_hex,
        encryption=encryption,
        passphrase=passphrase,
        on_chunk=on_chunk,
    )
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


# ── Progress reporting ───────────────────────────────────────────────────────


class _NullReporter:
    def checkpoint(self, percent, message, stage=None):
        pass

    def tick(self, percent, message, stage=None):
        pass


class _BackupReporter:
    """Throttled progress + liveness writer for one running backup row.

    Two rates on purpose: ``checkpoint`` marks real milestones and rewrites the
    drawer notification, while ``tick`` is called from tight inner loops and
    mostly just refreshes the row's heartbeat. Without the cheap rate a large
    model would either flood the database or — as before — report nothing at all
    for many minutes, which is exactly what makes a live run indistinguishable
    from a dead one.
    """

    NOTIFY_INTERVAL_SECONDS = 10.0
    HEARTBEAT_INTERVAL_SECONDS = 3.0

    def __init__(self, backup):
        from .backup_progress import set_backup_progress, touch_backup_progress

        self._backup = backup
        self._set = set_backup_progress
        self._touch = touch_backup_progress
        self._last_notify = 0.0
        self._last_touch = 0.0

    def checkpoint(self, percent, message, stage=None):
        self._set(self._backup, percent, message, stage=stage)
        self._last_notify = self._last_touch = time.monotonic()

    def tick(self, percent, message, stage=None):
        now = time.monotonic()
        if now - self._last_notify >= self.NOTIFY_INTERVAL_SECONDS:
            self.checkpoint(percent, message, stage=stage)
        elif now - self._last_touch >= self.HEARTBEAT_INTERVAL_SECONDS:
            self._touch(self._backup, percent=percent, message=message, stage=stage)
            self._last_touch = now


class _CallbackReporter(_NullReporter):
    """Adapter for the legacy ``progress_callback(percent, message)`` argument."""

    def __init__(self, callback):
        self._callback = callback

    def checkpoint(self, percent, message, stage=None):
        self._callback(percent, message)


def _format_count(value):
    return f"{int(value or 0):,}"


# ── Full backup build ────────────────────────────────────────────────────────


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
    from .translations import get_strings
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
    from .backup_progress import finish_backup_progress, start_backup_progress
    from .translations import get_strings
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


# ── Failure, stall detection, and retry ──────────────────────────────────────


def backup_retry_policy():
    """Resolved recovery policy: (auto_retry_enabled, max_attempts, delay, stall timeout)."""
    config = _backup_config()
    return {
        "auto_retry_enabled": bool(config["auto_retry_enabled"]),
        "max_attempts": int(config["max_attempts"]),
        "retry_delay_minutes": int(config["retry_delay_minutes"]),
        "stall_timeout_minutes": int(config["stall_timeout_minutes"]),
    }


def _can_auto_retry(backup, policy=None, *, passphrase_in_hand=False):
    """Whether this row may be re-run without asking a human for anything.

    A passphrase-protected backup normally cannot: the passphrase is deliberately
    stored nowhere, so re-running it blind would silently produce a backup
    encrypted with the Django secret key instead of the passphrase the operator
    chose. The one exception is a retry queued from inside the Celery task that
    still holds the original passphrase in its arguments.
    """
    policy = policy or backup_retry_policy()
    if not policy["auto_retry_enabled"]:
        return False
    if backup.passphrase_required and not passphrase_in_hand:
        return False
    if int(backup.attempt_count or 0) >= policy["max_attempts"]:
        return False
    # Without a worker there is nothing that could run a delayed attempt — the
    # only executor is the web request that just failed. Promising a retry we
    # cannot start would leave the row pending until the reaper failed it again.
    return bool(passphrase_in_hand or system_backup_celery_available())


def fail_system_backup(backup, error, *, now=None, stalled=False, passphrase_in_hand=False):
    """Record a failed attempt and, when policy allows, arm the next one.

    Returns the seconds to wait before re-running, or ``None`` when this is the
    final outcome and a human has to decide what happens next.
    """
    from .backup_progress import finish_backup_progress, mark_backup_retrying
    from .translations import get_strings

    SystemBackup = type(backup)
    now = now or timezone.now()
    policy = backup_retry_policy()
    error = str(error or "")[:1000]
    strings = get_strings()

    if _can_auto_retry(backup, policy, passphrase_in_hand=passphrase_in_hand):
        delay = timedelta(minutes=policy["retry_delay_minutes"])
        backup.status = SystemBackup.STATUS_PENDING
        backup.error = error
        backup.next_attempt_at = now + delay
        backup.started_at = None
        backup.heartbeat_at = now
        backup.stage = ""
        backup.save(update_fields=[
            "status", "error", "next_attempt_at", "started_at", "heartbeat_at", "stage",
        ])
        mark_backup_retrying(backup, strings.get(
            "sysbackup_retry_scheduled",
            "Attempt {attempt} of {max} failed ({error}). Retrying in {minutes} minutes.",
        ).format(
            attempt=backup.attempt_count,
            max=policy["max_attempts"],
            error=error or ("stalled" if stalled else "unknown error"),
            minutes=policy["retry_delay_minutes"],
        ))
        return int(delay.total_seconds())

    backup.status = SystemBackup.STATUS_FAILED
    backup.completed_at = now
    backup.heartbeat_at = now
    backup.next_attempt_at = None
    backup.error = error
    backup.save(update_fields=[
        "status", "completed_at", "heartbeat_at", "next_attempt_at", "error",
    ])
    finish_backup_progress(backup, success=False, error=error)
    return None


def retry_countdown_for(backup_pk, *, now=None):
    """Seconds until this row's armed retry, or ``None`` if none is armed.

    The Celery task uses this to re-queue itself with its original arguments —
    the only path that can auto-retry a passphrase-protected backup, because the
    passphrase lives in the task arguments and nowhere else.
    """
    SystemBackup = apps.get_model("dlux", "SystemBackup")
    backup = SystemBackup.objects.filter(
        pk=backup_pk,
        status=SystemBackup.STATUS_PENDING,
        next_attempt_at__isnull=False,
    ).first()
    if backup is None:
        return None
    return max(0, int((backup.next_attempt_at - (now or timezone.now())).total_seconds()))


def reap_stalled_system_backups(*, now=None, dispatch=True, allow_inline=True):
    """Fail every backup whose runner stopped reporting, then start due retries.

    This is the guard against ghost rows. A worker that is OOM-killed, restarted,
    or disconnected mid-build never reaches ``run_system_backup``'s failure path,
    so the row would otherwise sit at ``running`` forever — showing a frozen
    percentage with no error, and (for scheduled runs) blocking every later
    backup as "already active". Any pending/running row whose heartbeat is older
    than the configured stall timeout is therefore declared dead here.

    Deliberately trigger-agnostic: the previous stale check only ever looked at
    scheduled runs, which is why an interrupted manual backup stayed a ghost.

    Returns ``(reaped, requeued)``.
    """
    SystemBackup = apps.get_model("dlux", "SystemBackup")
    now = now or timezone.now()
    policy = backup_retry_policy()
    cutoff = now - timedelta(minutes=policy["stall_timeout_minutes"])
    from .translations import get_strings
    strings = get_strings()

    reaped = 0
    active = SystemBackup.objects.filter(
        status__in=(SystemBackup.STATUS_PENDING, SystemBackup.STATUS_RUNNING),
    )
    for backup in active:
        # A pending row waiting on its own scheduled retry is not stalled.
        if backup.next_attempt_at and backup.next_attempt_at > now:
            continue
        if backup.last_signal_at and backup.last_signal_at > cutoff:
            continue
        stall_error = strings.get(
            "sysbackup_stalled_error",
            "Backup stopped reporting progress at {percent}% for over {minutes} minutes; "
            "its worker process is gone. Nothing was written.",
        ).format(percent=backup.progress_percent, minutes=policy["stall_timeout_minutes"])
        logger.warning(
            "Reaping stalled system backup pk=%s token=%s at %s%% (stage=%s)",
            backup.pk, backup.token, backup.progress_percent, backup.stage or "unknown",
        )
        fail_system_backup(backup, stall_error, now=now, stalled=True)
        reaped += 1

    requeued = dispatch_due_backup_retries(now=now, allow_inline=allow_inline) if dispatch else 0
    return reaped, requeued


def dispatch_due_backup_retries(*, now=None, allow_inline=True):
    """Start any backup whose scheduled retry time has arrived.

    ``allow_inline=False`` is what the web tier uses: a retry there must go to a
    worker or wait, never build a multi-gigabyte snapshot inside the request that
    was only polling for status.
    """
    SystemBackup = apps.get_model("dlux", "SystemBackup")
    now = now or timezone.now()
    started = 0
    # Passphrase-protected rows are excluded on purpose: only the Celery task that
    # still holds the passphrase may re-queue one, and starting it from here would
    # quietly fall back to secret-key encryption.
    due = SystemBackup.objects.filter(
        status=SystemBackup.STATUS_PENDING,
        passphrase_required=False,
        next_attempt_at__isnull=False,
        next_attempt_at__lte=now,
    )
    for backup in due:
        # Claim the row before doing anything: two pollers (a browser refresh and
        # the beat task, say) can reach this at the same moment, and a backup must
        # never run twice concurrently.
        if not allow_inline and not system_backup_celery_available():
            continue
        claimed = SystemBackup.objects.filter(
            pk=backup.pk,
            status=SystemBackup.STATUS_PENDING,
            next_attempt_at=backup.next_attempt_at,
        ).update(next_attempt_at=None)
        if not claimed:
            continue
        backup.next_attempt_at = None
        if not dispatch_system_backup(backup):
            if not allow_inline:
                continue
            run_system_backup(backup.pk)
        started += 1
    return started


def resume_system_backup(backup, *, passphrase=None, requested_by=None):
    """Re-run a failed backup on the same row as a fresh attempt.

    Resuming re-runs rather than continuing from the stall point: a ``.dlb`` is a
    single encrypted stream over a consistent snapshot, so a half-written one has
    nothing resumable in it. The row is reused so the history stays one line per
    requested backup, with ``attempt_count`` showing what it took.
    """
    SystemBackup = type(backup)
    if backup.status not in (SystemBackup.STATUS_FAILED, SystemBackup.STATUS_PENDING):
        raise ValueError("Only a failed backup can be resumed.")
    if backup.passphrase_required and not _clean_passphrase(passphrase):
        raise ValueError("This backup is passphrase-protected; the passphrase is required to resume it.")
    claimed = SystemBackup.objects.filter(pk=backup.pk, status=backup.status).update(
        status=SystemBackup.STATUS_PENDING,
        progress_percent=0,
        progress_message="",
        stage="",
        next_attempt_at=None,
        started_at=None,
        completed_at=None,
        heartbeat_at=timezone.now(),
    )
    if not claimed:
        return backup
    backup.refresh_from_db()
    if requested_by:
        _log_system_action(requested_by, "EXPORT", {
            "kind": "system_backup_resume",
            "token": backup.token,
            "attempt": int(backup.attempt_count or 0) + 1,
        })
    if not dispatch_system_backup(backup, passphrase=passphrase):
        run_system_backup(backup.pk, passphrase=passphrase)
        backup.refresh_from_db()
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


def run_scheduled_system_backup(*, now=None):
    """Create one due scheduled backup; safe for frequent Celery-beat polling."""
    config = _backup_config()
    if not config["scheduled_enabled"]:
        return None
    now = now or timezone.now()
    SystemSettings = apps.get_model("dlux", "SystemSettings")
    SystemBackup = apps.get_model("dlux", "SystemBackup")
    interval_start = now - timedelta(hours=config["schedule_interval_hours"])
    # Clear out anything the last cycle left behind (any trigger, not just this
    # one) before deciding whether a scheduled backup is still in flight.
    reap_stalled_system_backups(now=now)
    with transaction.atomic():
        SystemSettings.objects.get_or_create(pk=1)
        SystemSettings.objects.select_for_update().get(pk=1)
        active = SystemBackup.objects.filter(
            trigger=SystemBackup.TRIGGER_SCHEDULED,
            status__in=(SystemBackup.STATUS_PENDING, SystemBackup.STATUS_RUNNING),
        ).first()
        if active is not None:
            return active
        latest = SystemBackup.objects.filter(trigger=SystemBackup.TRIGGER_SCHEDULED).order_by("-created_at").first()
        if latest is not None and latest.created_at >= interval_start:
            return latest
        backup = SystemBackup.objects.create(
            requested_by_username="system",
            trigger=SystemBackup.TRIGGER_SCHEDULED,
        )
    return run_system_backup(backup.pk)


def _log_system_action(username, action, details):
    try:
        UserActivityLog = apps.get_model("dlux", "ActivityLog")
        User = apps.get_model(settings.AUTH_USER_MODEL)
        user = User._default_manager.filter(username=username).first()
        is_restore = str((details or {}).get("kind") or "") == "system_restore"
        UserActivityLog.safe_log(
            user=user,
            action=action,
            category="system",
            model_name="Dlux System Restore" if is_restore else "Dlux System Backup",
            model_key="dlux.systemrestore" if is_restore else "dlux.systembackup",
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
