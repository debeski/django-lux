"""Incremental backup chains: row indexes, sidecars, and chain resolution.

A chain is one full backup (the base, sequence 0) followed by incrementals,
each holding only the rows whose digest changed since its parent plus the
primary keys deleted since. Every member carries an *index* — ``{model: {pk:
digest}}`` plus the media storage names — describing the complete state at
that point, so the next increment is computed against one file, never by
replaying the chain. The index travels inside the ``.dlb`` (``index.json``) and
in a small sidecar next to it (``.idx``) so continuing a chain does not mean
decrypting a whole parent archive.

Members are linked by fingerprints: each records the digest of its own index
(``root``) and of its parent's (``parent_root``), so a restore can tell a
complete chain from one with a swapped, missing, or foreign member before it
touches the database.
"""

import hashlib
import json
import logging
import zlib
from datetime import timedelta
from django.apps import apps
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder
from django.utils import timezone

# Leaf imports only: `_shared` sits in the backup/tasks deferred-import knot,
# and everything in that knot imports this module.
from .config import _backup_config, get_system_backup_storage_prefix
from .crypto import DlbPayloadWriter, decrypt_dlb_to_tempfile, read_dlb_metadata


INDEX_MEMBER = "index.json"

logger = logging.getLogger("dlux")


def row_digest(text):
    return hashlib.blake2b(text.encode("utf-8"), digest_size=8).hexdigest()


def migration_digest(state=None):
    if state is None:
        state = [f"{app}.{name}" for app, name in MigrationRecorder(connection).applied_migrations()]
    return hashlib.sha256("\n".join(sorted(state)).encode("utf-8")).hexdigest()


def new_index():
    return {"models": {}, "files": []}


def index_root(index):
    payload = json.dumps(index, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def write_index_sidecar(path, index, *, passphrase=None, encrypt=True, chain=None):
    """Store ``index`` as a small container beside its ``.dlb``; returns the saved path."""
    import io

    writer = DlbPayloadWriter(passphrase=passphrase, encrypt=encrypt)
    try:
        writer.write(zlib.compress(json.dumps(index, separators=(",", ":")).encode("utf-8"), 6))
        buffer = io.BytesIO()
        writer.finish(buffer, {"content": "index", "chain": chain or {}})
    except BaseException:
        writer.abort()
        raise
    if default_storage.exists(path):
        default_storage.delete(path)
    return default_storage.save(path, ContentFile(buffer.getvalue()))


def read_index_sidecar(path, *, passphrase=None):
    with default_storage.open(path, "rb") as fh:
        _meta, tmp = decrypt_dlb_to_tempfile(fh, passphrase=passphrase)
    try:
        return json.loads(zlib.decompress(tmp.read()).decode("utf-8"))
    finally:
        tmp.close()


def delete_backup_files(backup):
    """Remove a member's archive and sidecar; best effort, like rotation."""
    for path in (backup.file_path, backup.index_path):
        if not path:
            continue
        try:
            if default_storage.exists(path):
                default_storage.delete(path)
        except Exception:
            logger.warning("Could not delete backup file %s", path, exc_info=True)


def chain_members_after(backup):
    """This member and every later member of its chain (what deleting it orphans)."""
    SystemBackup = type(backup)
    if not backup.chain_id:
        return [backup]
    return list(
        SystemBackup.objects.filter(chain_id=backup.chain_id, sequence__gte=backup.sequence)
        .order_by("sequence", "created_at")
    )


def chain_policy():
    config = _backup_config()
    return {
        "incremental_enabled": bool(config.get("incremental_enabled")),
        "full_every_days": int(config.get("full_every_days") or 7),
        "max_chain_length": int(config.get("max_chain_length") or 24),
    }


def open_chain_head(*, media_included=None, system_data_included=None, encryption=None, now=None):
    """The member a new incremental would continue, or ``(None, reason)``.

    A chain is closed — the next backup must be full — when its base is gone or
    older than ``full_every_days``, it already has ``max_chain_length``
    increments, the schema changed since it began, or its head lost its index.
    Scope filters pick the chain a scheduled run continues; a manual run takes
    the newest chain of any scope.
    """
    SystemBackup = apps.get_model("dlux", "SystemBackup")
    policy = chain_policy()
    now = now or timezone.now()
    heads = SystemBackup.objects.filter(status=SystemBackup.STATUS_COMPLETED).exclude(index_root="")
    if media_included is not None:
        heads = heads.filter(media_included=media_included)
    if system_data_included is not None:
        heads = heads.filter(system_data_included=system_data_included)
    if encryption is not None:
        heads = heads.filter(encryption=encryption)
    head = heads.order_by("-completed_at", "-pk").first()
    if head is None:
        return None, "no_base"
    base = SystemBackup.objects.filter(
        token=head.chain_id, status=SystemBackup.STATUS_COMPLETED,
    ).first()
    if base is None:
        return None, "base_missing"
    if base.completed_at and base.completed_at < now - timedelta(days=policy["full_every_days"]):
        return None, "base_too_old"
    if head.sequence >= policy["max_chain_length"]:
        return None, "chain_full"
    if head.migration_digest != migration_digest():
        return None, "schema_changed"
    if not head.index_path or not default_storage.exists(head.index_path):
        return None, "index_missing"
    return head, ""


# ── Restore-side resolution, from the files themselves ──────────────────────


def _header(path):
    with default_storage.open(path, "rb") as fh:
        return read_dlb_metadata(fh)


def resolve_chain_paths(target_path, target_meta=None):
    """Ordered storage paths base → ``target_path`` for a chain member.

    Resolution reads only the cleartext headers of the ``.dlb`` files in the
    backup folder, so it works the same for rows this system made and for
    uploaded files. Raises ``ValueError`` naming what is missing or broken.
    """
    meta = target_meta or _header(target_path)
    chain = meta.get("chain") or {}
    sequence = int(chain.get("sequence") or 0)
    if sequence == 0:
        return [target_path]
    chain_id = chain.get("id")
    prefix = get_system_backup_storage_prefix()
    try:
        _dirs, files = default_storage.listdir(prefix)
    except Exception:
        files = []
    candidates = {}
    for name in files:
        if not name.lower().endswith(".dlb"):
            continue
        path = f"{prefix}/{name}"
        if path == target_path:
            continue
        try:
            info = (_header(path).get("chain") or {})
        except Exception:
            continue
        position = int(info.get("sequence") or 0)
        if info.get("id") == chain_id and position < sequence:
            candidates.setdefault(position, []).append((path, info))
    # Walk back from the target along parent_root -> root links, so a stray
    # file that merely shares a sequence number can never be picked.
    ordered = [(target_path, chain)]
    for position in range(sequence - 1, -1, -1):
        wanted = ordered[0][1].get("parent_root")
        match = next(
            (item for item in candidates.get(position, []) if item[1].get("root") == wanted),
            None,
        )
        if match is None:
            if candidates.get(position):
                raise ValueError(
                    f"Backup chain is broken at member {position + 1}: no member {position} "
                    "it was taken after is in the backup folder"
                )
            raise ValueError(
                f"Backup chain is incomplete: member {position} of {sequence} is missing "
                "from the backup folder"
            )
        ordered.insert(0, match)
    return [path for path, _info in ordered]
