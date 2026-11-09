"""DjangoLux's task manager: a database queue and ``manage.py dlux_worker``.

The public API for DjangoLux and for projects:

    from dlux.taskrunner import task, enqueue, Retry, crontab

    @task(name="crm.refresh_rates", priority=-5)
    def refresh_rates(): ...

    refresh_rates.enqueue()            # or .delay(), or enqueue("crm.refresh_rates")

Schedules go in ``DLUX_TASK_SCHEDULE``; worker tuning in ``DLUX_TASK_RUNNER``.
See ``docs/task-runner.md``.
"""

from .config import runner_config
from .dispatch import enqueue, worker_alive
from .registry import DluxTask, Retry, TaskContext, registered_tasks, task
from .schedules import crontab
from .signals import worker_started, worker_stopping

__all__ = [
    "DluxTask",
    "Retry",
    "TaskContext",
    "crontab",
    "enqueue",
    "registered_tasks",
    "runner_config",
    "task",
    "worker_alive",
    "worker_started",
    "worker_stopping",
]
