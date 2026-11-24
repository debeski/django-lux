"""Worker tuning for ``dlux_worker`` (``DLUX_TASK_RUNNER``)."""

from django.conf import settings

# The queue DjangoLux's outbound mail runs on (``dlux.utils.mail.queue_dlux_mail``).
MAIL_QUEUE = "dlux-mail"
# Mail is claimed before any other due run (OCR is 0 to -9, unprioritised work 0).
MAIL_PRIORITY = 50

RUNNER_DEFAULTS = {
    "threads": 4,
    "queues": ["default"],
    # Queues every worker serves on top of ``queues``, with one thread kept for
    # them alone, so short urgent work (DjangoLux's mail) never waits for a
    # thread behind backups or OCR. An empty list gives that thread back.
    "express_queues": [MAIL_QUEUE],
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
    config["express_queues"] = [str(queue) for queue in (config["express_queues"] or []) if str(queue)]
    return config
