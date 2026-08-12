"""Progress reporters used while a backup runs."""

import time


class _NullReporter:
    def checkpoint(self, percent, message, stage=None):
        pass

    def tick(self, percent, message, stage=None):
        pass


class _BackupReporter:
    """Throttled progress + liveness writer for one running backup row.

    Two rates on purpose: ``checkpoint`` marks real milestones and rewrites the
    drawer notification, while ``tick`` is called from tight inner loops and
    mostly just refreshes the row's heartbeat. Without the cheap rate a large
    model would either flood the database or — as before — report nothing at all
    for many minutes, which is exactly what makes a live run indistinguishable
    from a dead one.
    """

    NOTIFY_INTERVAL_SECONDS = 10.0
    HEARTBEAT_INTERVAL_SECONDS = 3.0

    def __init__(self, backup):
        from ..utils.backup_progress import set_backup_progress, touch_backup_progress

        self._backup = backup
        self._set = set_backup_progress
        self._touch = touch_backup_progress
        self._last_notify = 0.0
        self._last_touch = 0.0

    def checkpoint(self, percent, message, stage=None):
        self._set(self._backup, percent, message, stage=stage)
        self._last_notify = self._last_touch = time.monotonic()

    def tick(self, percent, message, stage=None):
        now = time.monotonic()
        if now - self._last_notify >= self.NOTIFY_INTERVAL_SECONDS:
            self.checkpoint(percent, message, stage=stage)
        elif now - self._last_touch >= self.HEARTBEAT_INTERVAL_SECONDS:
            self._touch(self._backup, percent=percent, message=message, stage=stage)
            self._last_touch = now


class _CallbackReporter(_NullReporter):
    """Adapter for the legacy ``progress_callback(percent, message)`` argument."""

    def __init__(self, callback):
        self._callback = callback

    def checkpoint(self, percent, message, stage=None):
        self._callback(percent, message)


def _format_count(value):
    return f"{int(value or 0):,}"
