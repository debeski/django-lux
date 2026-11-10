"""Worker tuning for ``dlux_worker`` (``DLUX_TASK_RUNNER``)."""

from django.conf import settings

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


def runner_config():
    config = dict(RUNNER_DEFAULTS)
    overrides = getattr(settings, "DLUX_TASK_RUNNER", None)
    if isinstance(overrides, dict):
        config.update({key: value for key, value in overrides.items() if key in RUNNER_DEFAULTS})
    config["queues"] = [str(queue) for queue in (config["queues"] or ["default"])]
    return config
