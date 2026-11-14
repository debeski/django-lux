"""``dlux_worker``: runs queued tasks in a thread pool and keeps the schedule rows armed.

There is no separate scheduler process and no leader election. A schedule
entry is one queue row; it becomes due by its ``run_after`` and is claimed like
any other run, so two workers cannot both run the same tick, and the worker
that finishes a tick re-arms it in the same fenced ``UPDATE``.
"""

import logging
import os
import socket
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings
from django.db import connections
from django.utils import timezone

from . import queue
from .config import runner_config
from .registry import DluxTask, Retry, TaskContext, resolve_task
from .schedules import parse_schedule
from .signals import worker_started, worker_stopping

logger = logging.getLogger("dlux")

PRUNE_EVERY = 3600


def close_old_connections():
    """Django's ``close_old_connections``, minus connections inside an atomic block.

    Between tasks a pool thread is never inside one; the exception is
    ``run_burst`` called from a transaction (a test, a caller's ``atomic``),
    whose connection must not be closed under it.
    """
    for conn in connections.all(initialized_only=True):
        if not conn.in_atomic_block:
            conn.close_if_unusable_or_obsolete()


def load_task_modules():
    """Import DjangoLux's tasks and every installed app's ``tasks`` module, as Celery's autodiscovery does."""
    from django.utils.module_loading import autodiscover_modules

    import dlux.jobs  # noqa: F401

    autodiscover_modules("tasks")


class Worker:
    def __init__(self, *, threads=None, queues=None, schedule=True, poll_interval=None):
        config = runner_config()
        self.config = config
        self.threads = max(1, int(threads or config["threads"]))
        self.queues = list(queues or config["queues"])
        self.poll_interval = float(poll_interval if poll_interval is not None else config["poll_interval"])
        # True: DLUX_TASK_SCHEDULE; a dict: that schedule; False: run no schedule.
        self.use_schedule = schedule
        self.id = f"{socket.gethostname()[:40]}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        self.stop_event = threading.Event()
        self._maintenance_stop = threading.Event()
        self._slot_freed = threading.Event()
        self._inflight = set()
        self._lock = threading.Lock()
        self.schedule = {}

    # -- lifecycle -------------------------------------------------------------------

    def setup(self):
        load_task_modules()
        if self.use_schedule is not False:
            raw = self.use_schedule if isinstance(self.use_schedule, dict) else getattr(settings, "DLUX_TASK_SCHEDULE", {})
            self.schedule = {entry.name: entry for entry in parse_schedule(raw)}
        self._register()
        worker_started.send(sender=Worker, worker=self)
        self.maintain(force_prune=True)
        if self.use_schedule is not False:
            removed = queue.sync_schedule(self.schedule.values())
            for entry in self.schedule.values():
                if resolve_task(entry.task_name) is None:
                    logger.error("Schedule entry %r names unknown task %r; its runs will fail.", entry.name, entry.task_name)
            if removed:
                logger.info("Removed %s schedule row(s) no longer in DLUX_TASK_SCHEDULE.", removed)

    def _register(self):
        from dlux import __version__
        from dlux.models import DluxTaskWorker

        now = timezone.now()
        hostname, pid = socket.gethostname()[:255], os.getpid()
        # Same host and pid as a live-looking row: that row is this process's
        # previous incarnation (a restarted container keeps its hostname and
        # pid 1), so its runs are lost now rather than after the stale window.
        DluxTaskWorker.objects.filter(hostname=hostname, pid=pid, stopped_at__isnull=True).exclude(
            id=self.id).update(stopped_at=now)
        DluxTaskWorker.objects.update_or_create(id=self.id, defaults={
            "hostname": hostname,
            "pid": pid,
            "version": str(__version__)[:32],
            "threads": self.threads,
            "queues": self.queues,
            "started_at": now,
            "heartbeat_at": now,
            "stopped_at": None,
        })

    def heartbeat(self):
        from dlux.models import DluxTaskWorker

        if not DluxTaskWorker.objects.filter(id=self.id).update(heartbeat_at=timezone.now(), stopped_at=None):
            self._register()

    def maintain(self, *, force_prune=False):
        """Heartbeat, settle runs lost with dead workers, and prune now and then."""
        self.heartbeat()
        queue.recover_lost_runs(resolve=resolve_task, exclude_worker=self.id)
        now = time.monotonic()
        if force_prune or now - getattr(self, "_last_prune", 0) >= PRUNE_EVERY:
            self._last_prune = now
            pruned = queue.prune()
            if pruned:
                logger.info("Pruned %s finished task run(s).", pruned)

    def _maintenance_loop(self):
        interval = max(1.0, float(self.config["heartbeat_interval"]))
        while not self._maintenance_stop.wait(interval):
            try:
                self.maintain()
            except Exception:
                logger.warning("Task worker maintenance failed; retrying next beat.", exc_info=True)
            finally:
                close_old_connections()

    def stop(self, *_args):
        """Stop claiming. Running tasks finish; the heartbeat goes on until they have."""
        self.stop_event.set()
        self._slot_freed.set()

    def run(self):
        """Block until ``stop()``: claim due runs whenever a thread is free."""
        self.setup()
        maintenance = threading.Thread(target=self._maintenance_loop, name="dlux-worker-maintenance", daemon=True)
        maintenance.start()
        logger.info("dlux_worker %s started: %s thread(s), queues %s.", self.id, self.threads, ",".join(self.queues))
        pool = ThreadPoolExecutor(max_workers=self.threads, thread_name_prefix="dlux-task")
        try:
            while not self.stop_event.is_set():
                claimed = False
                while self._free_slots() and not self.stop_event.is_set():
                    run = self._claim()
                    if run is None:
                        break
                    claimed = True
                    future = pool.submit(self.execute, run)
                    with self._lock:
                        self._inflight.add(future)
                    future.add_done_callback(self._done)
                if not claimed:
                    self._slot_freed.clear()
                    self._slot_freed.wait(self.poll_interval if self._free_slots() else None)
        finally:
            worker_stopping.send(sender=Worker, worker=self)
            pool.shutdown(wait=False, cancel_futures=True)
            self._finish(maintenance)

    def _finish(self, maintenance):
        from dlux.models import DluxTaskWorker

        deadline = time.monotonic() + float(self.config["shutdown_grace"])
        while self._inflight and time.monotonic() < deadline:
            time.sleep(0.2)
        if self._inflight:
            # Keep heartbeating: the process exits once these threads end (or
            # is killed, and then the heartbeat stops and they are recovered).
            logger.warning("dlux_worker %s is stopping with %s task(s) still running.", self.id, len(self._inflight))
            return
        self._maintenance_stop.set()
        maintenance.join(timeout=5)
        DluxTaskWorker.objects.filter(id=self.id).update(stopped_at=timezone.now())
        close_old_connections()

    def run_burst(self, *, limit=None):
        """Run due work in this thread until none is left (tests, one-shot cron use). Returns the count."""
        self.setup()
        done = 0
        try:
            while limit is None or done < limit:
                run = self._claim()
                if run is None:
                    break
                self.execute(run)
                done += 1
        finally:
            from dlux.models import DluxTaskWorker

            DluxTaskWorker.objects.filter(id=self.id).update(stopped_at=timezone.now())
        return done

    # -- execution -------------------------------------------------------------------

    def _free_slots(self):
        with self._lock:
            return len(self._inflight) < self.threads

    def _done(self, future):
        with self._lock:
            self._inflight.discard(future)
        self._slot_freed.set()

    def _claim(self):
        try:
            return queue.claim_next(self.id, self.queues, schedules=list(self.schedule))
        except Exception:
            logger.warning("Could not claim a task run; retrying.", exc_info=True)
            close_old_connections()
            self.stop_event.wait(self.poll_interval)
            return None

    def execute(self, run):
        """Run one claimed row and record what happened. Never raises."""
        close_old_connections()
        try:
            self._execute(run)
        except Exception:
            logger.exception("Task run %s (%s) could not be recorded.", run.pk, run.task_name)
        finally:
            close_old_connections()

    def _execute(self, run):
        # Claims are limited to this worker's own entries, so a schedule row has one.
        entry = self.schedule.get(run.schedule_name) if run.schedule_name else None
        definition = resolve_task(run.task_name)
        if definition is None:
            self._record(run, entry, error=queue.error_entry(
                exception_class_path="dlux.taskrunner.UnknownTask",
                message=f"No task called {run.task_name!r} is registered in this worker.",
            ))
            return
        try:
            args, kwargs = queue.run_arguments(run)
        except ValueError as exc:
            self._record(run, entry, error=queue.error_entry(exc))
            return
        try:
            value = self._invoke(definition, run, args, kwargs)
        except Retry as exc:
            limit = getattr(definition, "max_retries", None)
            if exc.counts and limit is not None and run.attempts > limit:
                self._record(run, entry, error=queue.error_entry(exc))
            else:
                queue.retry_run(run, exc.delay, error=queue.error_entry(exc.__cause__ or exc),
                                counted=exc.counts)
            return
        except Exception as exc:
            logger.exception("Task %s (run %s) failed.", run.task_name, run.pk)
            self._record(run, entry, error=queue.error_entry(exc))
            return
        self._record(run, entry, return_value=value)

    def _record(self, run, entry, *, return_value=None, error=None):
        next_due = None
        if entry is not None:
            next_due = entry.next_due(timezone.now(), previous_due=run.run_after)
        if not queue.complete_run(run, return_value=return_value, error=error, next_due=next_due):
            logger.warning("Task run %s finished after it was recovered elsewhere; outcome dropped.", run.pk)

    def _invoke(self, definition, run, args, kwargs):
        if isinstance(definition, DluxTask):
            context = TaskContext(
                task_name=definition.name,
                attempt=run.attempts,
                priority=run.priority,
                run_id=run.pk,
                backend="dlux",
            )
            return definition.invoke(context, args, kwargs)
        from .backend import call_django_task

        return call_django_task(definition, run, args, kwargs)
