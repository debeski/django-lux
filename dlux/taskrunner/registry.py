"""Backend-neutral task definitions.

``@task(name=...)`` declares a function once. Enqueueing goes through
``dispatch.enqueue``, which sends it to Celery or to the DjangoLux queue
according to ``DLUX_TASK_BACKEND``. While Celery is importable the same function
is also registered as a Celery task under the same name, so a Celery worker can
run it and messages already in a broker keep resolving during a migration.

The API mirrors ``django.tasks`` (``enqueue``, ``using``, ``call``,
``takes_context``, priority -100..100 with higher first) so tasks move to plain
``django.tasks`` later without call-site changes. It does not depend on
``django.tasks`` itself, so it works on every Django that DjangoLux supports and
regardless of a project's ``TASKS`` setting.
"""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from django.utils import timezone

_REGISTRY = {}

PRIORITY_MIN = -100
PRIORITY_MAX = 100


class Retry(Exception):
    """Raise inside a task to run it again after ``delay`` seconds.

    Under the dlux backend the same queue row goes back to READY, keeping its
    priority. Under Celery it becomes ``self.retry(countdown=delay)`` with the
    message's delivery priority, exactly as before.
    """

    def __init__(self, delay=0, message=""):
        super().__init__(message or f"retry in {delay}s")
        self.delay = max(0, int(delay or 0))


@dataclass(frozen=True)
class TaskContext:
    """What a ``takes_context`` task receives as its first argument."""

    task_name: str
    attempt: int = 1
    priority: object = None
    run_id: str = ""
    backend: str = ""

    @property
    def retries(self):
        return max(0, self.attempt - 1)


@dataclass(frozen=True)
class DluxTask:
    func: object
    name: str
    priority: int | None = None
    queue_name: str = "default"
    run_after: datetime | None = None
    takes_context: bool = False
    # Upper bound on Retry under the dlux backend (and Celery's max_retries).
    max_retries: int | None = None
    # At-least-once: a run whose worker died is put back instead of failed.
    requeue_lost: bool = False
    # Arguments are encrypted at rest and cleared when the run finishes.
    sensitive: bool = False

    def using(self, *, priority=None, queue_name=None, run_after=None, countdown=None):
        changes = {}
        if priority is not None:
            changes["priority"] = _checked_priority(priority)
        if queue_name is not None:
            changes["queue_name"] = str(queue_name)
        if countdown is not None:
            run_after = timezone.now() + timedelta(seconds=max(0, float(countdown)))
        if run_after is not None:
            changes["run_after"] = run_after
        return replace(self, **changes)

    def enqueue(self, *args, **kwargs):
        """Queue the task. Returns the dlux run id, or Celery's ``AsyncResult``."""
        from .dispatch import enqueue_task

        return enqueue_task(self, args, kwargs)

    def call(self, *args, **kwargs):
        """Run the function in this process, now."""
        if self.takes_context:
            return self.func(TaskContext(task_name=self.name, backend="inline"), *args, **kwargs)
        return self.func(*args, **kwargs)

    def invoke(self, context, args, kwargs):
        if self.takes_context:
            return self.func(context, *args, **kwargs)
        return self.func(*args, **kwargs)

    @property
    def module_path(self):
        return f"{self.func.__module__}.{self.func.__qualname__}"

    @property
    def celery(self):
        """The Celery task registered under ``name``, or None without Celery."""
        return _CELERY_TWINS.get(self.name)


_CELERY_TWINS = {}


def _checked_priority(priority):
    value = int(priority)
    if value != priority or not PRIORITY_MIN <= value <= PRIORITY_MAX:
        raise ValueError(f"priority must be a whole number between {PRIORITY_MIN} and {PRIORITY_MAX}.")
    return value


def task(function=None, *, name=None, priority=None, queue_name="default", takes_context=False,
         max_retries=None, requeue_lost=False, sensitive=False):
    """Declare a task. ``name`` defaults to the function's import path."""

    def wrapper(func):
        definition = DluxTask(
            func=func,
            name=name or f"{func.__module__}.{func.__qualname__}",
            priority=None if priority is None else _checked_priority(priority),
            queue_name=queue_name,
            takes_context=takes_context,
            max_retries=max_retries,
            requeue_lost=requeue_lost,
            sensitive=sensitive,
        )
        _REGISTRY[definition.name] = definition
        twin = _celery_twin(definition)
        if twin is not None:
            _CELERY_TWINS[definition.name] = twin
        return definition

    if function is not None:
        return wrapper(function)
    return wrapper


def _celery_twin(definition):
    try:
        from celery import shared_task
    except Exception:
        return None

    def run(self, *args, **kwargs):
        priority = (getattr(self.request, "delivery_info", None) or {}).get("priority")
        context = TaskContext(
            task_name=definition.name,
            attempt=int(getattr(self.request, "retries", 0) or 0) + 1,
            priority=priority,
            run_id=str(getattr(self.request, "id", "") or ""),
            backend="celery",
        )
        try:
            return definition.invoke(context, args, kwargs)
        except Retry as exc:
            raise self.retry(exc=exc.__cause__ or exc, countdown=exc.delay, priority=priority)

    run.__name__ = definition.func.__name__
    run.__qualname__ = definition.func.__qualname__
    run.__module__ = definition.func.__module__
    run.__doc__ = definition.func.__doc__
    options = {"name": definition.name, "bind": True, "ignore_result": True}
    if definition.requeue_lost:
        options["acks_late"] = True
    if definition.max_retries is not None:
        options["max_retries"] = definition.max_retries
    return shared_task(**options)(run)


def get_task(name):
    """The registered ``DluxTask`` called ``name``, or None.

    Only tasks whose module this process imported are known; ``dlux_worker``
    imports ``dlux.jobs`` and every app's ``tasks`` module at startup.
    """
    return _REGISTRY.get(name)


def registered_tasks():
    return dict(_REGISTRY)


def resolve_task(name):
    """What a worker runs for ``name``: a ``DluxTask``, a ``django.tasks.Task``, or None.

    Only those two kinds are accepted, so a queue row can never make the worker
    call an arbitrary importable function.
    """
    found = get_task(name)
    if found is not None:
        return found
    if not name or "." not in name:
        return None
    try:
        from django.utils.module_loading import import_string

        target = import_string(name)
    except Exception:
        return None
    if isinstance(target, DluxTask):
        return target
    try:
        from django.tasks import Task
    except ImportError:
        return None
    return target if isinstance(target, Task) else None
