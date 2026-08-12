"""Retry policy, failure bookkeeping and stalled-backup reaping."""

from datetime import timedelta
from django.apps import apps
from django.utils import timezone

from ._shared import system_backup_celery_available
from .config import _backup_config


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
    from ..utils.backup_progress import finish_backup_progress, mark_backup_retrying
    from ..translations import get_strings

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
