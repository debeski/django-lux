"""Writing and running a system backup."""

import json
import tempfile
import zipfile
from contextlib import contextmanager
from datetime import timedelta
from django.apps import apps
from django.core.files import File
from django.core.files.storage import default_storage
from django.db import connection, models, transaction
from django.template.defaultfilters import filesizeformat
from django.utils import timezone
from ..utils.archive import build_relation_schema, stream_model_into_zip

from ._shared import _SUPERUSER_PASSWORD_OMITTED, _dlux_version, _log_system_action, get_current_migration_state, logger
from .chain import (
    INDEX_MEMBER, delete_backup_files, index_root, migration_digest, new_index, read_index_sidecar, row_digest, write_index_sidecar,
)
from .config import _backup_config, _is_user_model, _system_model_queryset, get_system_backup_models, get_system_backup_storage_prefix
from .crypto import BACKUP_KIND, INCREMENT_KIND, DlbPayloadWriter, _clean_passphrase
from .reporters import BackupCancelled, _BackupReporter, _CallbackReporter, _NullReporter, _ThreadedReporter, _format_count
from .retry import fail_system_backup


CONSISTENCY_SNAPSHOT = "snapshot"
CONSISTENCY_LIVE = "live"


def _scrub_superuser_password(obj):
    """Serialize superuser accounts without their password hash."""
    if _is_user_model(obj.__class__) and getattr(obj, "is_superuser", False):
        obj.password = _SUPERUSER_PASSWORD_OMITTED
    return obj


def snapshot_supported():
    """Whether reads can be frozen into one consistent snapshot here.

    PostgreSQL only: a read-only REPEATABLE READ transaction sees the database
    as of its first query, with no locks taken, so writers carry on while the
    backup reads a frozen copy. Not inside an outer transaction, whose
    isolation level is already fixed.
    """
    return connection.vendor == "postgresql" and not connection.in_atomic_block


@contextmanager
def consistent_snapshot():
    """Hold the database at one point in time for the duration of the block.

    Yields ``"snapshot"`` when frozen, ``"live"`` when the engine cannot freeze
    (rows are then read model by model as the backup proceeds).
    """
    if not snapshot_supported():
        yield CONSISTENCY_LIVE
        return
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        yield CONSISTENCY_SNAPSHOT


def write_system_backup(
    dest,
    *,
    passphrase=None,
    progress_callback=None,
    reporter=None,
    include_media=True,
    include_system_data=True,
    encrypt=True,
    consistency=CONSISTENCY_LIVE,
    previous_index=None,
    chain=None,
    index_out=None,
):
    """Build the complete system backup into ``dest``. Returns ``(metadata, manifest)``.

    ``include_media=False`` writes a data-only backup (database rows + migration
    state, no media blobs) — much faster, used for the inline updater's pre-update
    safety snapshot since an inline code/schema update never alters media on disk.

    ``include_system_data=False`` leaves Dlux's own bookkeeping out (see
    ``SYSTEM_DATA_MODELS``): a portable project-data snapshot. ``encrypt=False``
    stores the archive unencrypted.

    Every backup digests each row and writes the resulting index (see
    ``dlux.backup.chain``) into ``index.json`` and, when given, ``index_out``.
    With ``previous_index`` the backup is an increment: only rows whose digest
    differs, media whose storage name is new, and ``deleted/<app>/<model>.json``
    lists of primary keys gone since are written. ``chain`` is the member's
    chain identity, completed here with its index ``root``.

    The archive is encrypted while it is written (``DlbPayloadWriter``), so there
    is no separate encryption pass. ``reporter`` receives coarse ``checkpoint()``
    milestones and frequent ``tick()`` sub-progress; ``progress_callback`` is the
    older two-argument milestone-only form. A reporter may raise
    ``BackupCancelled`` to stop the run.
    """
    if reporter is None:
        reporter = _CallbackReporter(progress_callback) if progress_callback else _NullReporter()
    manifest = {
        "kind": "dlux-system-backup",
        "generated_at": timezone.now().isoformat(),
        "dlux_version": _dlux_version(),
        "migration_state": get_current_migration_state(),
        "media_included": bool(include_media),
        "system_data_included": bool(include_system_data),
        "consistency": consistency,
        "superuser_policy": {
            "users": "included",
            "password_hashes": "omitted",
            "restore": "target_password_preserved_when_username_matches",
        },
        "models": [],
        "files": [],
        "missing_files": [],
    }
    models_to_export = get_system_backup_models(include_system_data=include_system_data)
    # Bake relation/label schema into the manifest so the standalone .dlb viewer
    # can resolve FK/M2M/O2O references to readable names without this project.
    manifest["schema"] = build_relation_schema(models_to_export)
    from ..translations import get_strings
    strings = get_strings()
    STAGE_MODELS = "models"
    STAGE_ENCRYPTING = "encrypting"
    BAND_START, BAND_END = 5, 90

    # Progress is weighted by rows, not by model count, so the bar (and the ETA
    # derived from it) moves at the rate work is actually done: a 20k-row
    # activity log is most of a backup, an empty settings table is nothing.
    querysets = [(model, _system_model_queryset(model)) for model in models_to_export]
    weights = []
    for model, qs in querysets:
        has_files = include_media and any(
            isinstance(field, models.FileField) for field in model._meta.get_fields()
        )
        # A model with uploads is walked twice (records, then files).
        weights.append(((qs.count() + 1) * (2 if has_files else 1), has_files))
    total_weight = max(sum(weight for weight, _has_files in weights), 1)

    def band(position):
        return BAND_START + int((position / total_weight) * (BAND_END - BAND_START))

    natural_key_cache = {}
    index = new_index()
    parent_models = (previous_index or {}).get("models") or {}
    parent_files = set((previous_index or {}).get("files") or [])
    incremental = previous_index is not None
    current_files = set()

    def file_filter(name):
        current_files.add(name)
        return not incremental or name not in parent_files
    writer = DlbPayloadWriter(passphrase=passphrase, encrypt=encrypt)
    try:
        done_weight = 0
        with zipfile.ZipFile(writer, "w", zipfile.ZIP_DEFLATED) as zf:
            for (model, qs), (weight, has_files) in zip(querysets, weights):
                model_label = str(model._meta.verbose_name)
                reporter.checkpoint(
                    band(done_weight),
                    strings.get("backup_progress_model", "Backing up {model}...").format(model=model_label),
                    stage=STAGE_MODELS,
                )

                def report_step(step_stage, done, total, _base=done_weight, _weight=weight,
                                _halves=has_files, _label=model_label):
                    share = (done / total) if total else 1.0
                    if _halves:
                        share = 0.5 + share * 0.5 if step_stage == "files" else share * 0.5
                    template = (
                        "backup_progress_model_files" if step_stage == "files" else "backup_progress_model_rows"
                    )
                    fallback = (
                        "Backing up {model} - files {done}/{total}..."
                        if step_stage == "files"
                        else "Backing up {model} - records {done}/{total}..."
                    )
                    reporter.tick(
                        band(_base + int(_weight * share)),
                        strings.get(template, fallback).format(
                            model=_label,
                            done=_format_count(done),
                            total=_format_count(total),
                        ),
                        stage=STAGE_MODELS,
                    )

                label = model._meta.label_lower
                model_index = {}
                previous_rows = parent_models.get(label) or {}

                def observe(pk, text, _rows=model_index, _previous=previous_rows):
                    key = str(pk)
                    digest = row_digest(text)
                    _rows[key] = digest
                    return not incremental or _previous.get(key) != digest

                stream_model_into_zip(
                    zf, model, qs, manifest,
                    serialize_kwargs={"use_natural_foreign_keys": True},
                    object_transform=_scrub_superuser_password,
                    include_files=include_media,
                    step_callback=report_step,
                    natural_key_cache=natural_key_cache,
                    row_observer=observe,
                    file_filter=file_filter,
                )
                index["models"][label] = model_index
                if incremental:
                    deleted = sorted(set(previous_rows) - set(model_index))
                    manifest["models"][-1]["deleted"] = len(deleted)
                    if deleted:
                        zf.writestr(
                            f"deleted/{model._meta.app_label}/{model._meta.model_name}.json",
                            json.dumps(deleted),
                        )
                done_weight += weight
                reporter.checkpoint(
                    band(done_weight),
                    strings.get("backup_progress_model_done", "Backed up {model}.").format(model=model_label),
                    stage=STAGE_MODELS,
                )
            index["files"] = sorted(current_files)
            chain = dict(chain or {})
            chain["root"] = index_root(index)
            manifest["chain"] = chain
            manifest["migration_digest"] = migration_digest(manifest["migration_state"])
            zf.writestr(INDEX_MEMBER, json.dumps(index, separators=(",", ":")))
            zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        reporter.checkpoint(
            92,
            strings.get(
                "backup_progress_sealing" if encrypt else "backup_progress_sealing_plain",
                "Finishing encryption ({size})..." if encrypt else "Writing the backup file ({size})...",
            ).format(size=filesizeformat(writer.size)),
            stage=STAGE_ENCRYPTING,
        )
        metadata = writer.finish(dest, {
            "created_at": manifest["generated_at"],
            "dlux_version": manifest["dlux_version"],
            "models": len(manifest["models"]),
            "rows": sum(item["count"] for item in manifest["models"]),
            "files": len(manifest["files"]),
            "media_included": bool(include_media),
            "system_data_included": bool(include_system_data),
            "consistency": consistency,
            "chain": chain,
            "migration_digest": manifest["migration_digest"],
            "kind": INCREMENT_KIND if incremental else BACKUP_KIND,
        })
    except BaseException:
        writer.abort()
        raise
    if index_out is not None:
        index_out.update(index)
    return metadata, manifest


def _encryption_mode(backup):
    SystemBackup = type(backup)
    mode = getattr(backup, "encryption", "") or SystemBackup.ENCRYPTION_SERVER_KEY
    if backup.passphrase_required:
        return SystemBackup.ENCRYPTION_PASSPHRASE
    return mode


def _discard(paths, backup_pk):
    for path in paths:
        try:
            default_storage.delete(path)
        except Exception:
            logger.warning("Could not remove a file of backup pk=%s", backup_pk, exc_info=True)


def _chain_start(backup, passphrase):
    """``(previous_index, chain)`` for the member this row will become.

    A full backup starts its own chain. An incremental continues ``parent``,
    whose index sidecar must open with this run's key (so a passphrase chain
    keeps one passphrase) and whose schema must still be the current one.
    """
    SystemBackup = type(backup)
    if not backup.is_incremental:
        return None, {
            "id": backup.token, "sequence": 0, "token": backup.token,
            "parent": "", "parent_root": "", "kind": SystemBackup.KIND_FULL,
        }
    parent = backup.parent
    if parent is None or parent.status != SystemBackup.STATUS_COMPLETED or not parent.index_root:
        raise ValueError("The backup this increment continues is no longer available; take a full backup.")
    if parent.migration_digest != migration_digest():
        raise ValueError("The database schema changed since this backup chain began; take a full backup.")
    if not parent.index_path or not default_storage.exists(parent.index_path):
        raise ValueError("The index of the previous backup is missing; take a full backup.")
    previous_index = read_index_sidecar(parent.index_path, passphrase=passphrase)
    if index_root(previous_index) != parent.index_root:
        raise ValueError("The index of the previous backup does not match it; take a full backup.")
    return previous_index, {
        "id": parent.chain_id, "sequence": parent.sequence + 1, "token": backup.token,
        "parent": parent.token, "parent_root": parent.index_root, "kind": SystemBackup.KIND_INCREMENTAL,
    }


def run_system_backup(backup_pk, passphrase=None, *, allow_passphrase_retry=False):
    """Celery-or-inline runner that builds the .dlb for a SystemBackup row.

    Scope and encryption are read off the row (``media_included``,
    ``system_data_included``, ``encryption``), set by the caller when the row is
    created, so the choice survives a Celery handoff — the task only receives
    the pk (and the passphrase, which is stored nowhere).

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
        progress_log=[],
    )
    if not claimed:
        backup.refresh_from_db()
        return backup
    backup.refresh_from_db()
    mode = _encryption_mode(backup)
    if mode == SystemBackup.ENCRYPTION_PASSPHRASE and not _clean_passphrase(passphrase):
        fail_system_backup(backup, "This backup is passphrase-protected; the passphrase is required to build it.")
        return backup
    from ..utils.backup_progress import cancel_backup_progress, finish_backup_progress, start_backup_progress
    from ..translations import get_strings
    strings = get_strings()
    start_backup_progress(backup)
    reporter = _BackupReporter(backup)
    saved_paths = []
    sealed_passphrase = passphrase if mode == SystemBackup.ENCRYPTION_PASSPHRASE else None
    encrypt = mode != SystemBackup.ENCRYPTION_NONE
    try:
        reporter.checkpoint(
            2,
            strings.get("backup_progress_preparing", "Preparing backup..."),
            stage=SystemBackup.STAGE_PREPARING,
        )
        previous_index, chain = _chain_start(backup, sealed_passphrase)
        index = {}
        with tempfile.TemporaryFile() as tmp:
            with consistent_snapshot() as consistency:
                run_reporter = _ThreadedReporter(reporter) if consistency == CONSISTENCY_SNAPSHOT else reporter
                try:
                    metadata, manifest = write_system_backup(
                        tmp,
                        passphrase=sealed_passphrase,
                        reporter=run_reporter,
                        include_media=bool(backup.media_included),
                        include_system_data=bool(backup.system_data_included),
                        encrypt=encrypt,
                        consistency=consistency,
                        previous_index=previous_index,
                        chain=chain,
                        index_out=index,
                    )
                finally:
                    if run_reporter is not reporter:
                        run_reporter.close()
            size = tmp.tell()
            tmp.seek(0)
            reporter.checkpoint(
                95,
                strings.get("backup_progress_storing", "Storing backup artifact..."),
                stage=SystemBackup.STAGE_STORING,
            )
            prefix = get_system_backup_storage_prefix()
            saved_path = default_storage.save(f"{prefix}/system-{backup.token}.dlb", File(tmp))
            saved_paths.append(saved_path)
        chain = manifest["chain"]
        sidecar = saved_path[:-4] + ".idx" if saved_path.endswith(".dlb") else f"{saved_path}.idx"
        saved_paths.append(write_index_sidecar(
            sidecar, index, passphrase=sealed_passphrase, encrypt=encrypt, chain=chain,
        ))
        completed_at = timezone.now()
        values = {
            "file_path": saved_path,
            "chain_id": chain["id"],
            "sequence": chain["sequence"],
            "index_root": chain["root"],
            "migration_digest": manifest["migration_digest"],
            "file_size": size,
            "model_count": metadata["models"],
            "row_count": metadata["rows"],
            "file_count": metadata["files"],
            "missing_file_count": len(manifest["missing_files"]),
            "passphrase_required": bool(metadata.get("passphrase_required")),
            "status": SystemBackup.STATUS_COMPLETED,
            "completed_at": completed_at,
            "heartbeat_at": completed_at,
            "stage": "",
            "next_attempt_at": None,
            "error": "",
        }
        # Conditional, like every progress write: a cancel that lands while the
        # file is being stored must win, and the stored file must not linger.
        if not SystemBackup.objects.filter(pk=backup.pk, status=SystemBackup.STATUS_RUNNING).update(**values):
            raise BackupCancelled()
        for name, value in values.items():
            setattr(backup, name, value)
        finish_backup_progress(backup, success=True)
        _log_system_action(backup.requested_by_username, "EXPORT", {
            "kind": "system_backup",
            "trigger": backup.trigger,
            "models": backup.model_count,
            "rows": backup.row_count,
            "files": backup.file_count,
            "attempts": backup.attempt_count,
            "encryption": mode,
            "system_data": bool(backup.system_data_included),
            "consistency": metadata.get("consistency", ""),
            "seconds": backup.duration_seconds,
            "backup_kind": backup.kind,
            "chain_sequence": backup.sequence,
        })
        apply_backup_retention(protected_pk=backup.pk)
    except BackupCancelled:
        _discard(saved_paths, backup_pk)
        backup.refresh_from_db()
        if backup.status == SystemBackup.STATUS_CANCELLED:
            cancel_backup_progress(backup, strings.get("sysbackup_cancelled_note", "Backup cancelled."))
    except Exception as exc:
        logger.exception("System backup pk=%s failed", backup_pk)
        _discard(saved_paths, backup_pk)
        fail_system_backup(
            backup,
            str(exc)[:1000],
            passphrase_in_hand=bool(allow_passphrase_retry and _clean_passphrase(passphrase)),
        )
    return backup


def apply_backup_retention(*, protected_pk=None, now=None):
    """Apply configured age/count rotation to completed system backups.

    Rotation works on whole chains (a full backup and its increments): an
    increment is useless without the members before it, so a chain is kept or
    removed as one. Age is the age of a chain's newest member and the count is
    a count of chains. A backup outside any chain is a chain of one.

    File removal and row removal are deliberately best-effort per item; a
    storage outage must not turn an otherwise valid new backup into a failure.
    """
    SystemBackup = apps.get_model("dlux", "SystemBackup")
    config = _backup_config()
    retention_days = config["retention_days"]
    max_to_keep = config["max_backups_to_keep"]
    now = now or timezone.now()
    chains = {}
    for backup in SystemBackup.objects.filter(status=SystemBackup.STATUS_COMPLETED).order_by("created_at"):
        chains.setdefault(backup.chain_id or backup.token, []).append(backup)
    ordered = sorted(chains.items(), key=lambda item: item[1][-1].created_at, reverse=True)
    protected = {
        key for key, members in chains.items()
        if protected_pk is not None and any(member.pk == protected_pk for member in members)
    }
    doomed = set()
    if retention_days:
        cutoff = now - timedelta(days=retention_days)
        doomed.update(key for key, members in ordered if members[-1].created_at < cutoff)
    if max_to_keep:
        doomed.update(key for key, _members in ordered[max_to_keep:])
    doomed -= protected

    removed = 0
    for key in doomed:
        members = chains[key]
        # Every row in the chain, not only completed ones: a failed retry of an
        # increment still points at the base being removed.
        extra = list(SystemBackup.objects.filter(chain_id=key).exclude(pk__in=[m.pk for m in members]))
        for old_backup in sorted(members + extra, key=lambda item: item.sequence, reverse=True):
            try:
                delete_backup_files(old_backup)
                old_backup.delete()
                removed += 1
            except Exception:
                logger.exception("Could not rotate system backup pk=%s", old_backup.pk)
    return removed
