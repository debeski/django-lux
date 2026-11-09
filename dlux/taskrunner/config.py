"""Settings of the task runner: which backend runs DjangoLux's tasks, and worker tuning."""

from django.conf import settings

TASK_BACKENDS = ("celery", "dlux")
DEFAULT_TASK_BACKEND = "celery"

RUNNER_DEFAULTS = {
    "threads": 4,
    "queues": ["default"],
    "poll_interval": 1.0,
    "heartbeat_interval": 10,
    # A worker whose heartbeat is older than this is gone: its runs are lost.
    "stale_after": 60,
    # Seconds a finished one-off run is kept before the worker prunes it.
    "keep_successful": 24 * 3600,
    "keep_failed": 7 * 24 * 3600,
    # How often a lost run of a ``requeue_lost`` task may be put back.
    "max_recoveries": 3,
    # Seconds a stopping worker waits for its running tasks.
    "shutdown_grace": 25,
}


def configured_task_backend():
    """The raw ``DLUX_TASK_BACKEND`` value, normalised; may be invalid."""
    return str(getattr(settings, "DLUX_TASK_BACKEND", DEFAULT_TASK_BACKEND) or DEFAULT_TASK_BACKEND).strip().lower()


def task_backend():
    """``"celery"`` or ``"dlux"``. An invalid value counts as Celery (and fails the system check)."""
    value = configured_task_backend()
    return value if value in TASK_BACKENDS else DEFAULT_TASK_BACKEND


def uses_dlux_backend():
    return task_backend() == "dlux"


def runner_config():
    config = dict(RUNNER_DEFAULTS)
    overrides = getattr(settings, "DLUX_TASK_RUNNER", None)
    if isinstance(overrides, dict):
        config.update({key: value for key, value in overrides.items() if key in RUNNER_DEFAULTS})
    config["queues"] = [str(queue) for queue in (config["queues"] or ["default"])]
    return config
