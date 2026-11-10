"""Queueing a task by name, and asking whether anything will run it."""

import logging
from datetime import timedelta

from django.utils import timezone

from .queue import insert_run, live_dlux_workers

logger = logging.getLogger("dlux")


def enqueue_task(definition, args=(), kwargs=None, **options):
    options.setdefault("priority", definition.priority)
    options.setdefault("run_after", definition.run_after)
    options.setdefault("queue_name", definition.queue_name)
    options.setdefault("sensitive", definition.sensitive)
    return enqueue(definition.name, args=args, kwargs=kwargs, **options)


def enqueue(name, args=(), kwargs=None, *, priority=None, run_after=None, countdown=None,
            queue_name="default", sensitive=False):
    """Queue task ``name`` and return its run id.

    The row is inserted in the caller's transaction, so the worker sees it only
    once the work that queued it commits. Raises when the queue cannot accept it
    (table missing); DjangoLux's callers treat that as "run it here instead" or
    "try later".

    Sending by name keeps the caller from importing the task module. A
    ``sensitive`` task must say so here (its ``DluxTask.enqueue`` does).
    """
    if countdown is not None:
        run_after = timezone.now() + timedelta(seconds=max(0, float(countdown)))
    return insert_run(
        name, list(args or ()), dict(kwargs or {}),
        priority=priority or 0,
        run_after=run_after,
        queue_name=queue_name,
        sensitive=sensitive,
    ).pk


def worker_alive():
    """A ``dlux_worker`` heartbeat inside the stale window: one indexed query."""
    try:
        return live_dlux_workers().exists()
    except Exception:
        logger.debug("Could not read the task worker heartbeats", exc_info=True)
        return False
