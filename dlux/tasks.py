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
except Exception:  # pragma: no cover - celery not installed
    shared_task = None


if shared_task is not None:
    @shared_task(name='dlux.tasks.build_report_backup', ignore_result=True)
    def build_report_backup_task(backup_pk):
        from .reports import run_report_backup
        run_report_backup(backup_pk)

    @shared_task(name='dlux.tasks.build_system_backup', ignore_result=True)
    def build_system_backup_task(backup_pk, passphrase=''):
        from .backup import run_system_backup
        run_system_backup(backup_pk, passphrase=passphrase)

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
else:  # pragma: no cover - celery not installed
    build_report_backup_task = None
    build_system_backup_task = None
    restore_system_backup_task = None
    run_scheduled_system_backup_task = None
    dlux_update_check_task = None
