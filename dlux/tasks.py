"""DjangoLux's tasks under their historical attribute names.

The tasks are declared in ``dlux.jobs`` with ``@dlux.taskrunner.task`` and run
by ``dlux_worker``; their queue names stay ``dlux.tasks.<name>``. The
``*_task`` attributes below are the same ``DluxTask`` objects (``.enqueue()``,
``.delay()``), kept for code written against the old names; they are deprecated
(see ``docs/deprecation-countdown.md``). Nothing here registers with Celery: a
project's own Celery worker that autodiscovers this module finds no tasks.
"""

from . import jobs
from .ocr import RETRY_DELAYS as OCR_RETRY_DELAYS  # noqa: F401

build_report_backup_task = jobs.build_report_backup
build_system_backup_task = jobs.build_system_backup
restore_system_backup_task = jobs.restore_system_backup
run_scheduled_system_backup_task = jobs.run_scheduled_system_backup
weather_refresh_task = jobs.weather_refresh
weather_search_task = jobs.weather_search
dlux_update_check_task = jobs.dlux_update_check
dlux_state_tick_task = jobs.dlux_state_tick
ocr_background = jobs.ocr_background
ocr_file = jobs.ocr_file
reap_stalled_system_backups_task = jobs.reap_stalled_system_backups
