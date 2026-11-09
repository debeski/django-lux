"""A ``django.tasks`` backend over the DjangoLux queue (Django 6.0+).

    TASKS = {"default": {"BACKEND": "dlux.taskrunner.backend.DatabaseBackend"}}

``dlux_settings()`` sets exactly that on Django 6.0+ when the
project has no ``TASKS`` of its own, so ``@django.tasks.task`` functions run on
``dlux_worker`` with priority, ``run_after`` and ``get_result``. On Django
before 6.0 this module cannot be imported; DjangoLux's own tasks do not need it.
"""

from django.tasks import TaskContext as DjangoTaskContext
from django.tasks import TaskResult, TaskResultStatus
from django.tasks.backends.base import BaseTaskBackend
from django.tasks.base import TaskError
from django.tasks.exceptions import TaskResultDoesNotExist
from django.tasks.signals import task_enqueued, task_finished, task_started
from django.utils.module_loading import import_string

from . import queue


class DatabaseBackend(BaseTaskBackend):
    supports_defer = True
    supports_get_result = True
    supports_priority = True
    supports_async_task = False

    def __init__(self, alias, params):
        super().__init__(alias, params)
        # Queues are the worker's business (DLUX_TASK_RUNNER["queues"]); accept any.
        self.queues = set(params.get("QUEUES") or ())

    def enqueue(self, task, args, kwargs):
        self.validate_task(task)
        run = queue.insert_run(
            task.module_path,
            args,
            kwargs,
            priority=task.priority,
            run_after=task.run_after,
            queue_name=task.queue_name,
        )
        result = _result(task, run, self.alias)
        task_enqueued.send(type(self), task_result=result)
        return result

    def get_result(self, result_id):
        from dlux.models import DluxTaskRun

        run = DluxTaskRun.objects.filter(pk=result_id, schedule_name__isnull=True).first()
        if run is None:
            raise TaskResultDoesNotExist(result_id)
        try:
            task = import_string(run.task_name)
        except ImportError as exc:
            raise TaskResultDoesNotExist(result_id) from exc
        return _result(task, run, self.alias)


def _result(task, run, alias):
    result = TaskResult(
        task=task,
        id=run.pk,
        status=TaskResultStatus(run.status),
        enqueued_at=run.enqueued_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        last_attempted_at=run.last_attempted_at,
        args=list(run.args or []),
        kwargs=dict(run.kwargs or {}),
        backend=alias,
        errors=[TaskError(exception_class_path=e.get("exception_class_path", ""), traceback=e.get("traceback", ""))
                for e in run.errors or []],
        worker_ids=list(run.worker_ids or []),
    )
    object.__setattr__(result, "_return_value", run.return_value)
    return result


def call_django_task(task, run, args, kwargs):
    """Run a ``django.tasks.Task`` claimed by ``dlux_worker``, with Django's task signals."""
    result = _result(task, run, task.backend)
    task_started.send(sender=DatabaseBackend, task_result=result)
    try:
        if task.takes_context:
            value = task.call(DjangoTaskContext(task_result=result), *args, **kwargs)
        else:
            value = task.call(*args, **kwargs)
    except BaseException:
        object.__setattr__(result, "status", TaskResultStatus.FAILED)
        task_finished.send(sender=DatabaseBackend, task_result=result)
        raise
    object.__setattr__(result, "status", TaskResultStatus.SUCCESSFUL)
    task_finished.send(sender=DatabaseBackend, task_result=result)
    return value
