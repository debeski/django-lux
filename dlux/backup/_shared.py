"""Values and helpers used by both the create and restore halves."""

import logging
from django.apps import apps
from django.conf import settings
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder

from .config import _backup_config


logger = logging.getLogger("dlux")


_SUPERUSER_PASSWORD_OMITTED = "!dlux-superuser-password-omitted"


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
