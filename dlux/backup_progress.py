"""Shared progress persistence and drawer notifications for Dlux backups."""

import logging

from django.apps import apps
from django.contrib.auth import get_user_model
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from .translations import get_strings


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
        from .notifications import notify

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
        from .notifications import notify

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
