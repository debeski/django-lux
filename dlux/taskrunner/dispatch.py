"""The one place that decides where a task goes and whether anything will run it."""

import logging
from datetime import timedelta

from django.utils import timezone

from .config import task_backend, uses_dlux_backend
from .queue import insert_run, live_dlux_workers

logger = logging.getLogger("dlux")

CELERY_PRIORITY_LOWEST = 9


def celery_priority(priority):
    """django.tasks priority (higher first, default 0) -> Redis-transport priority (0 first, 9 last).

    0 maps to 0, the priority Celery gives a message sent without one, and
    -6 / -9 map to 6 / 9: the numbers DjangoLux sent before the runner existed.
    """
    return min(CELERY_PRIORITY_LOWEST, max(0, -int(priority)))


def enqueue_task(definition, args=(), kwargs=None):
    return enqueue(
        definition.name,
        args=args,
        kwargs=kwargs,
        priority=definition.priority,
        run_after=definition.run_after,
        queue_name=definition.queue_name,
        sensitive=definition.sensitive,
    )


def enqueue(name, args=(), kwargs=None, *, priority=None, run_after=None, countdown=None,
            queue_name="default", sensitive=False):
    """Queue task ``name`` on the configured backend.

    Returns the dlux run id or Celery's ``AsyncResult``. Raises when the
    backend cannot accept it (broker down, table missing); every DjangoLux
    caller already treats that as "run it here instead" or "try later".

    Sending by name keeps the caller from importing the task module. A
    ``sensitive`` task must say so here (its ``DluxTask.enqueue`` does).
    """
    args = list(args or ())
    kwargs = dict(kwargs or {})
    if countdown is not None:
        run_after = timezone.now() + timedelta(seconds=max(0, float(countdown)))
    if uses_dlux_backend():
        return insert_run(
            name, args, kwargs,
            priority=priority or 0,
            run_after=run_after,
            queue_name=queue_name,
            sensitive=sensitive,
        ).pk
    return _send_to_celery(name, args, kwargs, priority=priority, run_after=run_after)


def _send_to_celery(name, args, kwargs, *, priority=None, run_after=None):
    app = celery_app()
    if app is None:
        raise RuntimeError("Celery is not installed, so the task cannot be queued.")
    options = {"args": args, "retry": False}
    if kwargs:
        options["kwargs"] = kwargs
    if priority is not None:
        options["priority"] = celery_priority(priority)
    if run_after is not None:
        countdown = (run_after - timezone.now()).total_seconds()
        if countdown > 0:
            options["countdown"] = countdown
    return app.send_task(name, **options)


def celery_app():
    """The project's Celery app (``current_app`` is the one ``app.autodiscover_tasks`` set up)."""
    try:
        from celery import current_app
    except Exception:
        return None
    return current_app


def celery_worker_alive(app=None):
    """Broker reachable and at least one Celery worker answering a ping (blocks up to ~3 s)."""
    app = app if app is not None else celery_app()
    if app is None:
        return False
    try:
        with app.connection_for_write() as conn:
            conn.ensure_connection(max_retries=0, timeout=2)
        return bool(app.control.ping(timeout=1.0))
    except Exception:
        return False


def dlux_worker_alive():
    """A ``dlux_worker`` heartbeat inside the stale window: one indexed query, no broker."""
    try:
        return live_dlux_workers().exists()
    except Exception:
        logger.debug("Could not read the task worker heartbeats", exc_info=True)
        return False


def worker_alive():
    """Whether queued work will be picked up, on whichever backend is configured."""
    if task_backend() == "dlux":
        return dlux_worker_alive()
    return celery_worker_alive()
