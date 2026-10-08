"""Progress reporters used while a backup runs."""

import threading
import time


class BackupCancelled(Exception):
    """Raised inside a running backup once its row has been cancelled."""


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
        self._running = type(backup).STATUS_RUNNING
        self._last_notify = 0.0
        self._last_touch = 0.0

    def checkpoint(self, percent, message, stage=None):
        # Every write is conditional on the row still running: the write that
        # matches nothing is the cancellation signal.
        if not self._set(self._backup, percent, message, stage=stage, require_status=self._running):
            raise BackupCancelled()
        self._last_notify = self._last_touch = time.monotonic()

    def tick(self, percent, message, stage=None):
        now = time.monotonic()
        if now - self._last_notify >= self.NOTIFY_INTERVAL_SECONDS:
            self.checkpoint(percent, message, stage=stage)
        elif now - self._last_touch >= self.HEARTBEAT_INTERVAL_SECONDS:
            if not self._touch(
                self._backup, percent=percent, message=message, stage=stage,
                require_status=self._running,
            ):
                raise BackupCancelled()
            self._last_touch = now


class _ThreadedReporter:
    """Runs a reporter on its own thread, and so on its own database connection.

    A snapshot backup reads inside one read-only REPEATABLE READ transaction;
    progress written from that connection would be rejected, and would stay
    invisible to the page until commit anyway. Django connections are
    per-thread, so the inner reporter writes through a connection of its own.
    Updates are latest-wins: a slow write never stalls the backup, it only
    skips intermediate ticks. Cancellation seen by the thread is re-raised on
    the backup's thread at its next report.
    """

    def __init__(self, inner):
        self._inner = inner
        self._lock = threading.Condition()
        self._pending = None
        self._stopping = False
        self._cancelled = False
        self._error = None
        self._thread = threading.Thread(target=self._run, name="dlb-progress", daemon=True)
        self._thread.start()

    def _run(self):
        from django.db import connection

        try:
            while True:
                with self._lock:
                    while self._pending is None and not self._stopping:
                        self._lock.wait()
                    item, self._pending = self._pending, None
                    if item is None:
                        return
                method, args = item
                try:
                    getattr(self._inner, method)(*args)
                except BackupCancelled:
                    self._cancelled = True
                except Exception as exc:
                    self._error = exc
                with self._lock:
                    self._lock.notify_all()
        finally:
            connection.close()

    def _post(self, method, percent, message, stage):
        if self._cancelled:
            raise BackupCancelled()
        with self._lock:
            if self._pending is None or method == "checkpoint" or self._pending[0] != "checkpoint":
                self._pending = (method, (percent, message, stage))
            self._lock.notify_all()
        if self._cancelled:
            raise BackupCancelled()

    def checkpoint(self, percent, message, stage=None):
        self._post("checkpoint", percent, message, stage)

    def tick(self, percent, message, stage=None):
        self._post("tick", percent, message, stage)

    def close(self):
        with self._lock:
            self._stopping = True
            self._lock.notify_all()
        self._thread.join()
        if self._cancelled:
            raise BackupCancelled()


class _CallbackReporter(_NullReporter):
    """Adapter for the legacy ``progress_callback(percent, message)`` argument."""

    def __init__(self, callback):
        self._callback = callback

    def checkpoint(self, percent, message, stage=None):
        self._callback(percent, message)


def _format_count(value):
    return f"{int(value or 0):,}"
