"""Shared progress persistence and drawer notifications for Dlux backups."""

import logging

from django.apps import apps
from django.contrib.auth import get_user_model
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from ..translations import get_strings


logger = logging.getLogger("dlux")


def _has_field(backup, name):
    return any(field.name == name for field in type(backup)._meta.fields)


def _backup_kind(backup):
    return "report" if backup._meta.model_name == "reportbackup" else "system"


def _backup_recipients(backup):
    if _backup_kind(backup) == "report":
        user = getattr(backup, "user", None)
        return [user] if user and getattr(user, "is_active", True) else []
    username = str(getattr(backup, "requested_by_username", "") or "").strip()
    User = get_user_model()
    if username and username != "system":
        user = User._default_manager.filter(username=username, is_active=True).first()
        if user is not None:
            return [user]
    return list(User._default_manager.filter(is_active=True, is_superuser=True))


def _target_url(kind):
    try:
        return reverse("reports_overview" if kind == "report" else "system_backup_page")
    except NoReverseMatch:
        return ""


def _progress_notification(backup):
    DluxNotification = apps.get_model("dlux", "DluxNotification")
    return DluxNotification.objects.filter(
        source_model_key=backup._meta.label_lower,
        source_object_id=str(backup.pk),
        action="backup_progress",
    ).order_by("-created_at").first()


def _notification_copy(kind, state, *, message=""):
    strings = get_strings()
    title_key = f"backup_notification_{kind}_title"
    if state == "running":
        message_key = "reports_backup_preparing" if kind == "report" else "sysbackup_preparing"
        level = "info"
    elif state == "completed":
        message_key = "reports_backup_ready" if kind == "report" else "sysbackup_ready"
        level = "success"
    else:
        message_key = "reports_backup_failed" if kind == "report" else "sysbackup_failed"
        level = "error"
    return {
        "title": strings.get(title_key, "Backup"),
        "title_key": title_key,
        "message": message or strings.get(message_key, "Backup status changed."),
        "message_key": "" if message else message_key,
        "level": level,
    }


def start_backup_progress(backup):
    """Create one locked drawer item representing this active backup."""
    recipients = _backup_recipients(backup)
    if not recipients or _progress_notification(backup) is not None:
        return None
    kind = _backup_kind(backup)
    copy = _notification_copy(kind, "running")
    try:
        from ..notifications import notify

        return notify.info(
            copy["message"],
            title=copy["title"],
            title_key=copy["title_key"],
            message_key=copy["message_key"],
            obj=backup,
            user=recipients[0],
            recipients=recipients,
            to="actor",
            persist=True,
            flash=False,
            email=False,
            category="backup",
            source="backup",
            action="backup_progress",
            target_url=_target_url(kind),
            metadata={
                "backup_progress": True,
                "backup_kind": kind,
                "progress": int(getattr(backup, "progress_percent", 0) or 0),
                "progress_message": str(getattr(backup, "progress_message", "") or ""),
                "status": "running",
                "locked": True,
            },
        )
    except Exception:
        logger.warning("Could not create backup progress notification", exc_info=True)
        return None


def touch_backup_progress(backup, percent=None, message=None, stage=None):
    """Write a liveness heartbeat (and optional progress) without touching the drawer.

    The drawer notification is comparatively expensive to rewrite, so long inner
    loops call this instead: the row keeps proving the runner is alive — which is
    what the stall reaper and the "no progress for Nm" warning read — while the
    notification is refreshed only at coarse checkpoints.
    """
    values = {}
    if _has_field(backup, "heartbeat_at"):
        values["heartbeat_at"] = timezone.now()
    if percent is not None:
        percent = max(0, min(int(percent or 0), 99))
        values["progress_percent"] = percent
    if message is not None:
        message = str(message or "")[:255]
        values["progress_message"] = message
    if stage is not None and _has_field(backup, "stage"):
        values["stage"] = str(stage)[:20]
    if not values:
        return
    type(backup).objects.filter(pk=backup.pk).update(**values)
    for name, value in values.items():
        setattr(backup, name, value)


def set_backup_progress(backup, percent, message, stage=None):
    """Persist bounded progress and update the active drawer item in place."""
    percent = max(0, min(int(percent or 0), 99))
    message = str(message or "")[:255]
    touch_backup_progress(backup, percent=percent, message=message, stage=stage)
    notification = _progress_notification(backup) or start_backup_progress(backup)
    if notification is None:
        return
    metadata = dict(notification.metadata or {})
    metadata.update({
        "backup_progress": True,
        "backup_kind": _backup_kind(backup),
        "progress": percent,
        "progress_message": message,
        "status": "running",
        "locked": True,
    })
    metadata.pop("message_key", None)
    metadata.pop("translation_key", None)
    notification.message = message or notification.message
    notification.metadata = metadata
    notification.save(update_fields=["message", "metadata", "updated_at"])


def mark_backup_retrying(backup, message):
    """Keep the drawer item alive and explain the pause between two attempts.

    A run that will be retried automatically is not a terminal outcome, so it
    must not emit the unread "backup failed" notice — otherwise every transient
    hiccup pages the operator for something the system is already fixing.
    """
    message = str(message or "")[:255]
    touch_backup_progress(backup, message=message)
    notification = _progress_notification(backup)
    if notification is None:
        return
    metadata = dict(notification.metadata or {})
    metadata.update({
        "progress": int(getattr(backup, "progress_percent", 0) or 0),
        "progress_message": message,
        "status": "retrying",
        "locked": True,
    })
    metadata.pop("message_key", None)
    metadata.pop("translation_key", None)
    notification.message = message
    notification.level = "warning"
    notification.metadata = metadata
    notification.save(update_fields=["message", "level", "metadata", "updated_at"])


def finish_backup_progress(backup, *, success, error=""):
    """Unlock the progress item and emit a separate unread terminal notice."""
    kind = _backup_kind(backup)
    percent = 100 if success else int(getattr(backup, "progress_percent", 0) or 0)
    copy = _notification_copy(kind, "completed" if success else "failed")
    terminal_message = copy["message"] if success else f"{copy['message']} {str(error or '').strip()}".strip()
    type(backup).objects.filter(pk=backup.pk).update(
        progress_percent=percent,
        progress_message=terminal_message[:255],
    )
    backup.progress_percent = percent
    backup.progress_message = terminal_message[:255]
    notification = _progress_notification(backup)
    if notification is not None:
        metadata = dict(notification.metadata or {})
        metadata.update({
            "progress": percent,
            "progress_message": terminal_message,
            "status": "completed" if success else "failed",
            "locked": False,
        })
        if success:
            metadata["message_key"] = copy["message_key"]
        else:
            metadata.pop("message_key", None)
            metadata.pop("translation_key", None)
        notification.message = terminal_message
        notification.level = copy["level"]
        notification.metadata = metadata
        notification.save(update_fields=["message", "level", "metadata", "updated_at"])

    recipients = _backup_recipients(backup)
    if not recipients:
        return
    try:
        from ..notifications import notify

        helper = notify.success if success else notify.error
        helper(
            terminal_message,
            title=copy["title"],
            title_key=copy["title_key"],
            message_key=copy["message_key"] if success else "",
            obj=backup,
            user=recipients[0],
            recipients=recipients,
            to="actor",
            persist=True,
            flash=False,
            email=False,
            category="backup",
            source="backup",
            action="backup_completed" if success else "backup_failed",
            target_url=_target_url(kind),
            metadata={
                "backup_kind": kind,
                "status": "completed" if success else "failed",
                "progress": percent,
            },
        )
    except Exception:
        logger.warning("Could not create terminal backup notification", exc_info=True)


# ── Restore progress ─────────────────────────────────────────────────────────
#
# A restore's database phase runs inside one transaction (see ``_wipe_and_load``),
# so a row UPDATE written from there is invisible to the polling web process
# until the whole load commits — which is exactly the stretch an operator most
# wants to watch. Every tick is therefore mirrored into the cache, which is not
# transactional, and the status view overlays that mirror on the persisted row.
# The row stays the source of truth so progress still survives a page reload,
# a worker handoff, and a cache that is not shared between processes.

RESTORE_PROGRESS_CACHE_PREFIX = "dlux:restore-progress:"
RESTORE_PROGRESS_CACHE_TTL = 3600


def _restore_cache_key(restore):
    return f"{RESTORE_PROGRESS_CACHE_PREFIX}{restore.pk}"


def set_restore_progress(restore, percent, message, stage=None):
    """Persist bounded restore progress to the row and mirror it into the cache."""
    percent = max(0, min(int(percent or 0), 99))
    message = str(message or "")[:255]
    values = {
        "progress_percent": percent,
        "progress_message": message,
        "heartbeat_at": timezone.now(),
    }
    if stage is not None:
        values["stage"] = str(stage)[:20]
    try:
        type(restore).objects.filter(pk=restore.pk).update(**values)
    except Exception:
        logger.warning("Could not persist restore progress", exc_info=True)
    for name, value in values.items():
        setattr(restore, name, value)
    try:
        from django.core.cache import cache

        cache.set(
            _restore_cache_key(restore),
            {
                "progress_percent": percent,
                "progress_message": message,
                "stage": values.get("stage", getattr(restore, "stage", "") or ""),
                "heartbeat_at": values["heartbeat_at"].isoformat(),
            },
            RESTORE_PROGRESS_CACHE_TTL,
        )
    except Exception:
        logger.debug("Could not mirror restore progress into the cache", exc_info=True)


def read_restore_progress(restore):
    """Row progress, overlaid with a newer in-transaction tick from the cache."""
    persisted = {
        "progress_percent": int(getattr(restore, "progress_percent", 0) or 0),
        "progress_message": str(getattr(restore, "progress_message", "") or ""),
        "stage": str(getattr(restore, "stage", "") or ""),
    }
    if not restore.is_active:
        return persisted
    try:
        from django.core.cache import cache

        mirrored = cache.get(_restore_cache_key(restore))
    except Exception:
        return persisted
    if not isinstance(mirrored, dict):
        return persisted
    # Only ever move forward: a stale mirror must not drag a committed row back.
    if int(mirrored.get("progress_percent") or 0) < persisted["progress_percent"]:
        return persisted
    return {
        "progress_percent": int(mirrored.get("progress_percent") or 0),
        "progress_message": str(mirrored.get("progress_message") or ""),
        "stage": str(mirrored.get("stage") or ""),
    }


def clear_restore_progress(restore):
    try:
        from django.core.cache import cache

        cache.delete(_restore_cache_key(restore))
    except Exception:
        logger.debug("Could not clear the restore progress mirror", exc_info=True)


class RestoreReporter:
    """Throttled progress writer for one running restore.

    ``checkpoint`` marks a phase boundary and always writes. ``tick`` is called
    from per-chunk, per-model, and per-file loops and writes when *either* the
    displayed percentage advances or the interval has elapsed. Percentage is the
    important half of that rule: a purely time-based throttle silently drops
    every phase that finishes inside one interval, so a fast restore would report
    no decrypt step at all — and the bar can never skip a visible step. The time
    rule then covers the opposite case, keeping a long stretch at one percentage
    (tens of thousands of media files) from writing a row per file.
    """

    TICK_INTERVAL_SECONDS = 1.5

    def __init__(self, restore):
        self._restore = restore
        self._last_tick = 0.0
        self._last_percent = None

    def checkpoint(self, percent, message, stage=None):
        import time

        set_restore_progress(self._restore, percent, message, stage=stage)
        self._last_tick = time.monotonic()
        self._last_percent = int(percent or 0)

    def tick(self, percent, message, stage=None):
        import time

        if int(percent or 0) != self._last_percent:
            self.checkpoint(percent, message, stage=stage)
            return
        if time.monotonic() - self._last_tick >= self.TICK_INTERVAL_SECONDS:
            self.checkpoint(percent, message, stage=stage)


class NullRestoreReporter:
    def checkpoint(self, percent, message, stage=None):
        pass

    def tick(self, percent, message, stage=None):
        pass


def finish_restore_progress(restore, *, success, error=""):
    """Write the terminal percentage and emit one unread drawer notice.

    There is deliberately no "restore started" drawer item to match the backup's.
    A restore wipes and reloads every table it owns — ``DluxNotification``
    included — so an item created before the load would be deleted by the restore
    itself and replaced with whatever the snapshot held. Only this terminal
    notice, written after the transaction commits, can survive.
    """
    strings = get_strings()
    percent = 100 if success else int(getattr(restore, "progress_percent", 0) or 0)
    title = strings.get("backup_notification_restore_title", "Restore")
    message_key = "sysrestore_notify_done" if success else "sysrestore_notify_failed"
    base_message = strings.get(
        message_key,
        "System restore finished." if success else "System restore failed.",
    )
    terminal_message = base_message if success else f"{base_message} {str(error or '').strip()}".strip()
    try:
        type(restore).objects.filter(pk=restore.pk).update(
            progress_percent=percent,
            progress_message=terminal_message[:255],
        )
    except Exception:
        logger.warning("Could not persist terminal restore progress", exc_info=True)
    restore.progress_percent = percent
    restore.progress_message = terminal_message[:255]
    clear_restore_progress(restore)

    recipients = _backup_recipients(restore)
    if not recipients:
        return
    try:
        from ..notifications import notify

        helper = notify.success if success else notify.error
        helper(
            terminal_message,
            title=title,
            title_key="backup_notification_restore_title",
            message_key=message_key if success else "",
            obj=restore,
            user=recipients[0],
            recipients=recipients,
            to="actor",
            persist=True,
            flash=False,
            email=False,
            category="backup",
            source="backup",
            action="restore_completed" if success else "restore_failed",
            target_url=_target_url("system"),
            metadata={
                "backup_kind": "restore",
                "status": "completed" if success else "failed",
                "progress": percent,
            },
        )
    except Exception:
        logger.warning("Could not create terminal restore notification", exc_info=True)
