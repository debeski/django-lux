"""Celery entry points for DjangoLux's tasks (``DLUX_TASK_BACKEND = "celery"``, the default).

The task bodies live in ``dlux.jobs``, defined once for both backends; this
module only exposes their Celery twins under the names projects and tests have
always used, and hooks Celery's ``worker_ready``. Host projects that run Celery
pick it up automatically via ``app.autodiscover_tasks()``. Celery is optional:
without it every attribute below is None and callers run the work inline.
"""

import logging

from . import jobs
from .ocr import RETRY_DELAYS as OCR_RETRY_DELAYS  # noqa: F401

logger = logging.getLogger('dlux')

try:
    from celery import shared_task
    from celery.signals import worker_ready
except Exception:  # pragma: no cover - celery not installed
    shared_task = None
    worker_ready = None


build_report_backup_task = jobs.build_report_backup.celery
build_system_backup_task = jobs.build_system_backup.celery
restore_system_backup_task = jobs.restore_system_backup.celery
run_scheduled_system_backup_task = jobs.run_scheduled_system_backup.celery
weather_refresh_task = jobs.weather_refresh.celery
weather_search_task = jobs.weather_search.celery
dlux_update_check_task = jobs.dlux_update_check.celery
dlux_state_tick_task = jobs.dlux_state_tick.celery
ocr_background = jobs.ocr_background.celery
ocr_file = jobs.ocr_file.celery
reap_stalled_system_backups_task = jobs.reap_stalled_system_backups.celery

if worker_ready is not None:
    worker_ready.connect(jobs.reap_backups_on_worker_start, weak=False,
                         dispatch_uid='dlux.tasks.reap_backups_on_worker_start')
