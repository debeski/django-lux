"""Celery tasks for Dlux.

Celery is an optional dependency: when it isn't installed (or no broker/worker
is reachable) the features that use these tasks fall back to synchronous
execution. Host projects that run Celery pick this module up automatically via
``app.autodiscover_tasks()``.
"""

import logging

logger = logging.getLogger('dlux')

try:
    from celery import shared_task
    from celery.signals import worker_ready
except Exception:  # pragma: no cover - celery not installed
    shared_task = None
    worker_ready = None


if shared_task is not None:
    @shared_task(name='dlux.tasks.build_report_backup', ignore_result=True)
    def build_report_backup_task(backup_pk):
        from .reports import run_report_backup
        run_report_backup(backup_pk)

    @shared_task(name='dlux.tasks.build_system_backup', ignore_result=True)
    def build_system_backup_task(backup_pk, passphrase=''):
        from .backup import retry_countdown_for, run_system_backup
        run_system_backup(backup_pk, passphrase=passphrase, allow_passphrase_retry=True)
        # Re-queue ourselves rather than blocking the worker for the retry delay.
        # Carrying the original arguments is also the only way a passphrase-
        # protected backup can be retried at all — the passphrase is never stored.
        countdown = retry_countdown_for(backup_pk)
        if countdown is not None:
            build_system_backup_task.apply_async(
                args=[backup_pk, passphrase],
                countdown=countdown,
                retry=False,
            )

    @shared_task(name='dlux.tasks.restore_system_backup', ignore_result=True)
    def restore_system_backup_task(restore_pk, passphrase=''):
        from .backup import run_system_restore
        run_system_restore(restore_pk, passphrase=passphrase)

    @shared_task(name='dlux.tasks.run_scheduled_system_backup', ignore_result=True)
    def run_scheduled_system_backup_task():
        from .backup import run_scheduled_system_backup
        run_scheduled_system_backup()

    @shared_task(name='dlux.tasks.dlux_update_check', ignore_result=True)
    def dlux_update_check_task():
        # Reliable, persistent trigger for the daily DjangoLux update check. The
        # isolated updater worker still *processes* the queued check; this only
        # enqueues one when due, so the schedule survives updater-worker restarts
        # instead of living solely in that worker's in-memory countdown.
        from .updater.service import queue_daily_check_if_due
        queue_daily_check_if_due()

    @shared_task(name='dlux.tasks.dlux_state_tick', ignore_result=True)
    def dlux_state_tick_task():
        """One iteration of the DjangoLux write-side loop, run under Celery.

        This is what the `dlux-updater` service's worker loop used to do. It
        moved here once Composer took over executing updates: the only writes
        left are small JSON files in the runtime volume's `state/` directory —
        update intents, the agent bridge, control-link pairing and the snapshot
        — so a dedicated always-on container is no longer warranted. Celery is
        already resident, already runs under the release supervisor, and is not
        network-facing.

        Guarded by a short cache lock: beat can fire the next tick before this
        one finishes, and two concurrent ticks would race over the same files.
        `process_next()` is separately safe (it claims rows with
        `select_for_update`), but the bridge writes are not.
        """
        from django.core.cache import cache

        # add() is atomic; the timeout bounds a tick that dies mid-flight.
        if not cache.add('dlux.state_tick.lock', '1', 120):
            return
        try:
            from .updater.agent_bridge import (
                consume_agent_requests, publish_agent_results, publish_agent_snapshot,
            )
            from .updater.service import UpdateService

            service = UpdateService()
            consume_agent_requests(service)
            service.process_next()
            service.tick_image_update()
            service.tick_control_link()
            publish_agent_results(service.store)
            publish_agent_snapshot(service.store)
        finally:
            cache.delete('dlux.state_tick.lock')

    @shared_task(name='dlux.tasks.reap_stalled_system_backups', ignore_result=True)
    def reap_stalled_system_backups_task():
        from .backup import reap_stalled_system_backups
        reap_stalled_system_backups()

    if worker_ready is not None:
        @worker_ready.connect
        def _reap_backups_on_worker_start(**_kwargs):
            """Clear backups abandoned by the worker instance we are replacing.

            A worker that is OOM-killed or restarted mid-build never runs the
            failure path, so its row stays 'running' with no error and no file —
            the ghost that blocks later scheduled backups. Its heartbeat stopped
            when the process died, so the reaper can retire it safely; a backup
            genuinely running in a sibling worker heartbeats every few seconds and
            is never inside the stall window.
            """
            try:
                from .backup import reap_stalled_system_backups

                reaped, requeued = reap_stalled_system_backups()
                if reaped or requeued:
                    logger.warning(
                        'Worker startup retired %s stalled system backup(s) and restarted %s.',
                        reaped, requeued,
                    )
            except Exception:
                logger.warning('Could not reap stalled system backups on worker startup', exc_info=True)
else:  # pragma: no cover - celery not installed
    build_report_backup_task = None
    build_system_backup_task = None
    restore_system_backup_task = None
    run_scheduled_system_backup_task = None
    dlux_update_check_task = None
    reap_stalled_system_backups_task = None
