"""Entry points that start work: Celery dispatch, retry runs and resumption.

Re-running a backup lives here rather than in `retry` so the policy module stays
free of a dependency back on `create` — running a backup reports failures to
`retry`, and this module is what starts a run."""

from datetime import timedelta
from django.apps import apps
from django.db import transaction
from django.utils import timezone

from ._shared import _log_system_action, logger, system_backup_celery_available
from .config import _backup_config
from .create import run_system_backup
from .crypto import _clean_passphrase
from .retry import backup_retry_policy, fail_system_backup


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
    from ..translations import get_strings
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


def dispatch_system_backup(backup, *, passphrase=None):
    if not system_backup_celery_available():
        return False
    from ..tasks import build_system_backup_task
    try:
        build_system_backup_task.apply_async(args=[backup.pk, _clean_passphrase(passphrase)], retry=False)
        return True
    except Exception:
        logger.exception("Failed to queue system backup pk=%s", backup.pk)
        return False


def dispatch_system_restore(restore, *, passphrase=None):
    if not system_backup_celery_available():
        return False
    from ..tasks import restore_system_backup_task
    try:
        restore_system_backup_task.apply_async(args=[restore.pk, _clean_passphrase(passphrase)], retry=False)
        return True
    except Exception:
        logger.exception("Failed to queue system restore pk=%s", restore.pk)
        return False
