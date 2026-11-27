"""Values and helpers used by both the create and restore halves."""

import logging
import os
import shutil
from django.apps import apps
from django.conf import settings
from django.core.files.storage import default_storage
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder

from .config import _backup_config


logger = logging.getLogger("dlux")


_SUPERUSER_PASSWORD_OMITTED = "!dlux-superuser-password-omitted"


class BackupStorageFull(OSError):
    """The backup folder has less free space than the artifact needs."""


def _storage_free_bytes(name):
    """Free bytes on the volume that would hold ``name``; ``None`` when unknown.

    Only local storages expose a path. The nearest existing parent is measured,
    since the backup folder may not exist yet.
    """
    try:
        path = default_storage.path(name)
    except (NotImplementedError, AttributeError, ValueError):
        return None
    folder = os.path.dirname(path)
    while folder and not os.path.isdir(folder):
        parent = os.path.dirname(folder)
        if parent == folder:
            return None
        folder = parent
    try:
        return shutil.disk_usage(folder).free
    except OSError:
        return None


def ensure_storage_space(name, needed):
    """Refuse to start a write of ``needed`` bytes that cannot fit."""
    free = _storage_free_bytes(name)
    if free is None or free >= needed:
        return
    from ..translations import get_strings
    from .reporters import format_size

    raise BackupStorageFull(get_strings().get(
        "sysbackup_storage_full_error",
        "Not enough free space in the backup folder: this backup needs {needed} and {free} is free. Free some space, then retry.",
    ).format(needed=format_size(needed), free=format_size(free)))


def store_artifact(name, content, *, size=None):
    """``default_storage.save`` that leaves nothing behind when it fails.

    A save that fails part-way (a full disk) keeps the partial file under the
    name the storage chose, so every retry would fail the same way and add a
    sibling. The name is chosen first, so the failure path knows what to remove.
    """
    target = default_storage.get_available_name(name)
    if size is not None:
        ensure_storage_space(target, size)
    try:
        return default_storage.save(target, content)
    except BaseException:
        try:
            if default_storage.exists(target):
                default_storage.delete(target)
        except Exception:
            logger.warning("Could not remove the partial backup file %s", target, exc_info=True)
        raise


def get_current_migration_state():
    applied = MigrationRecorder(connection).applied_migrations()
    return sorted(f"{app}.{name}" for app, name in applied)


def _dlux_version():
    try:
        import dlux
        return str(getattr(dlux, "__version__", "")) or "unknown"
    except Exception:
        return "unknown"


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


def system_backup_worker_available():
    """Background builds are on and a ``dlux_worker`` is alive.

    ``use_celery`` is the stored name of the "build in the background" switch.
    """
    if not _backup_config().get("use_celery", True):
        return False
    from ..taskrunner import worker_alive

    return worker_alive()


# Deprecated name, kept for code written against it (see the deprecation countdown).
system_backup_celery_available = system_backup_worker_available
