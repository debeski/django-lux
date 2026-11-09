"""DjangoLux's built-in task runner: a database queue and ``manage.py dlux_worker``.

``DLUX_TASK_BACKEND`` (``"celery"`` by default, or ``"dlux"``) decides where
DjangoLux's tasks run; call sites go through ``enqueue`` / ``worker_alive`` and
never name a backend. See ``docs/task-runner.md``.
"""

from .config import TASK_BACKENDS, runner_config, task_backend, uses_dlux_backend
from .dispatch import enqueue, worker_alive
from .registry import DluxTask, Retry, TaskContext, task
from .schedules import crontab
from .signals import worker_started, worker_stopping

__all__ = [
    "TASK_BACKENDS",
    "DluxTask",
    "Retry",
    "TaskContext",
    "crontab",
    "enqueue",
    "runner_config",
    "task",
    "task_backend",
    "uses_dlux_backend",
    "worker_alive",
    "worker_started",
    "worker_stopping",
]
