"""DjangoLux's background tasks, run by ``dlux_worker``.

Their names stay ``dlux.tasks.*`` (``dlux.tasks`` also exposes them under their
historical attribute names). Callers send by name through
``dlux.taskrunner.enqueue`` and never import this module, which is what keeps it
out of the backup/reports/updater import knot.
"""

import logging

from .ocr import RETRY_DELAYS as OCR_RETRY_DELAYS
from .taskrunner import Retry, task, worker_started

logger = logging.getLogger("dlux")


@task(name="dlux.tasks.build_report_backup")
def build_report_backup(backup_pk):
    from .reports import run_report_backup

    run_report_backup(backup_pk)


def system_backup_lost(backup_pk, passphrase=""):
    """``on_lost`` for a backup run: fail its row now instead of after the stall timeout."""
    from .backup import fail_lost_system_backup

    fail_lost_system_backup(backup_pk)


def system_restore_lost(restore_pk, passphrase=""):
    """``on_lost`` for a restore run: a restore has no stall reaper, so this is its only guard."""
    from .backup import fail_lost_system_restore

    fail_lost_system_restore(restore_pk)


@task(name="dlux.tasks.build_system_backup", sensitive=True, on_lost=system_backup_lost)
def build_system_backup(backup_pk, passphrase=""):
    from .backup import retry_countdown_for, run_system_backup

    run_system_backup(backup_pk, passphrase=passphrase, allow_passphrase_retry=True)
    # Re-queue ourselves rather than blocking the worker for the retry delay.
    # Carrying the original arguments is also the only way a passphrase-
    # protected backup can be retried at all — the passphrase is never stored
    # (the dlux queue keeps it encrypted until the run ends).
    countdown = retry_countdown_for(backup_pk)
    if countdown is not None:
        build_system_backup.using(countdown=countdown).enqueue(backup_pk, passphrase)


@task(name="dlux.tasks.restore_system_backup", sensitive=True, on_lost=system_restore_lost)
def restore_system_backup(restore_pk, passphrase=""):
    from .backup import run_system_restore

    run_system_restore(restore_pk, passphrase=passphrase)


@task(name="dlux.tasks.run_scheduled_system_backup")
def run_scheduled_system_backup():
    from .backup import run_scheduled_system_backup as run

    run()


# Weather: web has no route to the internet in a generated stack, the worker
# does. Both write their answer to the shared cache for web to read.
@task(name="dlux.tasks.weather_refresh")
def weather_refresh(location, units, language, encrypted_api_key):
    from .weather import WeatherUnavailable, refresh_reading

    try:
        refresh_reading(location, units, language, encrypted_api_key)
    except WeatherUnavailable:
        pass  # recorded in the cache for web to report


@task(name="dlux.tasks.weather_search")
def weather_search(token, query, encrypted_api_key):
    from .weather import run_search

    run_search(token, query, encrypted_api_key)


@task(name="dlux.tasks.dlux_update_check")
def dlux_update_check():
    # Reliable, persistent trigger for the daily DjangoLux update check. The
    # isolated updater worker still *processes* the queued check; this only
    # enqueues one when due, so the schedule survives updater-worker restarts
    # instead of living solely in that worker's in-memory countdown.
    from .updater.service import queue_daily_check_if_due

    queue_daily_check_if_due()


@task(name="dlux.tasks.dlux_state_tick")
def dlux_state_tick():
    """One iteration of the DjangoLux write-side loop.

    This is what the `dlux-updater` service's worker loop used to do. It
    moved into the task worker once Composer took over executing updates: the
    only writes left are small JSON files in the runtime volume's `state/`
    directory — update intents, the agent bridge, control-link pairing and the
    snapshot — so a dedicated always-on container is no longer warranted. The
    worker is already resident, already runs under the release supervisor, and
    is not network-facing.

    Guarded by a short cache lock so two concurrent ticks never race over the
    same files. (``dlux_worker`` never overlaps a schedule entry with itself;
    the lock also covers an operator running the task by hand.) `process_next()` is
    separately safe (it claims rows with `select_for_update`), but the bridge
    writes are not.
    """
    from django.core.cache import cache

    # add() is atomic; the timeout bounds a tick that dies mid-flight.
    if not cache.add("dlux.state_tick.lock", "1", 120):
        return
    try:
        from .updater import UpdaterError
        from .updater.agent_bridge import (
            consume_agent_requests, publish_agent_results, publish_agent_snapshot,
        )
        from .updater.service import (
            UpdateService, reconcile_channel_policy, reconcile_check_policy,
            reconcile_state_if_due, record_worker_volume_report, tick_ops_run,
        )

        try:
            service = UpdateService()
        except UpdaterError as exc:
            # The worker owns the runtime volume, so it is the only process
            # whose writability verdict means anything. Record it and stop:
            # web reads it from the state row instead of probing a mount it
            # is deliberately given read-only.
            record_worker_volume_report(str(exc))
            return
        record_worker_volume_report()
        # Before any intent is processed: the versions the Options card shows
        # (and the rollback target it offers) come from the state row, and
        # nothing else refreshes it against the installed package.
        reconcile_state_if_due(service)
        # The worker is the only writer of the channel policy. Applying a
        # pending request before any intent is processed means a check
        # queued in the same tick already resolves against the new channel.
        try:
            reconcile_channel_policy(service)
        except UpdaterError:
            pass
        try:
            reconcile_check_policy(service)
        except (UpdaterError, OSError):
            pass
        consume_agent_requests(service)
        service.process_next()
        # A manual check waits for Composer's fresh report; this finishes it.
        service.tick_check_request()
        # Operations card: hand a queued operation to Composer, or finish one.
        tick_ops_run(service)
        # Composer executes an inline package update; this reads back its ack
        # and finishes the run. Without it a handed-off run never ends.
        service.tick_package_update()
        service.tick_image_update()
        service.tick_control_link()
        publish_agent_results(service.store)
        publish_agent_snapshot(service.store)
    finally:
        cache.delete("dlux.state_tick.lock")


@task(name="dlux.tasks.ocr_background")
def ocr_background():
    from .ocr.background import tick

    return tick()


@task(name="dlux.tasks.ocr_file", takes_context=True, requeue_lost=True, max_retries=len(OCR_RETRY_DELAYS))
def ocr_file(context, result_id):
    """Read one ``FileText`` row's file; waits out a busy or unavailable service with growing delays."""
    from .ocr.client import OCRUnavailable
    from .ocr.service import give_up, run

    try:
        run(result_id)
    except OCRUnavailable as exc:
        if context.retries >= len(OCR_RETRY_DELAYS):
            give_up(result_id, f"{exc} (gave up after {context.retries} retries)")
            return
        raise Retry(OCR_RETRY_DELAYS[context.retries]) from exc


@task(name="dlux.tasks.reap_stalled_system_backups")
def reap_stalled_system_backups():
    from .backup import reap_stalled_system_backups as reap

    reap()


def reap_backups_on_worker_start(**_kwargs):
    """Clear backups abandoned by the worker instance we are replacing.

    A worker that is OOM-killed or restarted mid-build never runs the
    failure path, so its row stays 'running' with no error and no file —
    the ghost that blocks later scheduled backups. Its heartbeat stopped
    when the process died, so the reaper can retire it safely; a backup
    genuinely running in a sibling worker heartbeats every few seconds and
    is never inside the stall window.
    """
    try:
        from .backup import reap_stalled_system_backups as reap

        reaped, requeued = reap()
        if reaped or requeued:
            logger.warning(
                "Worker startup retired %s stalled system backup(s) and restarted %s.",
                reaped, requeued,
            )
    except Exception:
        logger.warning("Could not reap stalled system backups on worker startup", exc_info=True)


worker_started.connect(reap_backups_on_worker_start, dispatch_uid="dlux.jobs.reap_backups_on_worker_start")
