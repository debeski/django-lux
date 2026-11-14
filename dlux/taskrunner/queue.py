"""The queue table's state transitions.

Every transition after the claim is a conditional ``UPDATE`` fenced on the
claim token, so a worker that lost its run (its heartbeat went stale and the
run was recovered elsewhere) can never overwrite the newer outcome.

    READY --claim--> RUNNING --success--> SUCCESSFUL   (schedule row: back to READY, next run_after)
                             --Retry----> READY (run_after = now + delay, same row, same priority)
                             --error----> FAILED       (schedule row: back to READY, last_status FAILED)
    RUNNING, worker heartbeat stale --recover--> READY (schedule rows, requeue_lost tasks) or FAILED
"""

import base64
import hashlib
import json
import logging
import traceback
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, connections, router, transaction
from django.db.models import F, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from .config import runner_config

logger = logging.getLogger("dlux")

READY = "READY"
RUNNING = "RUNNING"
SUCCESSFUL = "SUCCESSFUL"
FAILED = "FAILED"

MAX_ERRORS = 10
MAX_TRACEBACK = 8000
WORKER_LOST = "dlux.taskrunner.WorkerLost"


def _models():
    from django.apps import apps

    return apps.get_model("dlux", "DluxTaskRun"), apps.get_model("dlux", "DluxTaskWorker")


def _fernet():
    from cryptography.fernet import Fernet

    digest = hashlib.sha256(("dlux-taskrunner:" + settings.SECRET_KEY).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def seal_arguments(args, kwargs):
    payload = json.dumps({"args": list(args), "kwargs": dict(kwargs)}, cls=DjangoJSONEncoder)
    return _fernet().encrypt(payload.encode()).decode()


def unseal_arguments(token):
    """``(args, kwargs)``; ``ValueError`` when the token cannot be read (SECRET_KEY changed)."""
    from cryptography.fernet import InvalidToken

    try:
        data = json.loads(_fernet().decrypt(str(token).encode()).decode())
    except (InvalidToken, ValueError, UnicodeError) as exc:
        raise ValueError("The task's sealed arguments cannot be decrypted with this SECRET_KEY.") from exc
    return list(data.get("args") or []), dict(data.get("kwargs") or {})


def _jsonable(value):
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))


def error_entry(exc=None, *, exception_class_path=None, message=""):
    if exc is not None:
        kind = type(exc)
        exception_class_path = f"{kind.__module__}.{kind.__qualname__}"
        message = "".join(traceback.format_exception(exc))
    return {"exception_class_path": exception_class_path or "", "traceback": str(message)[-MAX_TRACEBACK:]}


def _with_error(errors, entry):
    return (list(errors or []) + [entry])[-MAX_ERRORS:]


def insert_run(task_name, args=(), kwargs=None, *, priority=0, run_after=None, queue_name="default", sensitive=False):
    DluxTaskRun, _ = _models()
    now = timezone.now()
    run = DluxTaskRun(
        task_name=task_name,
        queue_name=queue_name or "default",
        priority=int(priority or 0),
        run_after=run_after or now,
        enqueued_at=now,
    )
    if sensitive:
        run.sealed_arguments = seal_arguments(args or (), kwargs or {})
    else:
        run.args = _jsonable(list(args or ()))
        run.kwargs = _jsonable(dict(kwargs or {}))
    run.save(force_insert=True)
    return run


def run_arguments(run):
    if run.sealed_arguments:
        return unseal_arguments(run.sealed_arguments)
    return list(run.args or []), dict(run.kwargs or {})


def _ready(queues, now, schedules=None):
    from django.db.models import Q

    DluxTaskRun, _ = _models()
    ready = DluxTaskRun.objects.filter(status=READY, run_after__lte=now, queue_name__in=list(queues))
    if schedules is not None:
        ready = ready.filter(Q(schedule_name__isnull=True) | Q(schedule_name__in=list(schedules)))
    return ready.order_by("-priority", "run_after", "enqueued_at")


def claim_next(worker_id, queues=("default",), *, now=None, schedules=None):
    """Take the next due run for ``worker_id`` (highest priority, then oldest ``run_after``).

    ``schedules`` limits schedule rows to the entries this worker knows (None:
    any), so a worker never runs, or re-arms, an entry it has no spec for.

    PostgreSQL (and any backend with ``SKIP LOCKED``) locks one row and skips
    rows other workers hold, so concurrent workers never wait on each other.
    Elsewhere (SQLite) a compare-and-set ``UPDATE ... WHERE status='READY'``
    makes the claim atomic: two claimers can pick the same candidate, only one
    update matches.
    """
    DluxTaskRun, _ = _models()
    now = now or timezone.now()
    token = uuid.uuid4().hex
    claimed = {
        "status": RUNNING,
        "claim_token": token,
        "worker_id": worker_id,
        "last_attempted_at": now,
    }
    db = router.db_for_write(DluxTaskRun)
    if connections[db].features.has_select_for_update_skip_locked:
        with transaction.atomic(using=db):
            run = _ready(queues, now, schedules).using(db).select_for_update(skip_locked=True).first()
            if run is None:
                return None
            for field, value in claimed.items():
                setattr(run, field, value)
            run.attempts += 1
            run.started_at = run.started_at or now
            run.worker_ids = (list(run.worker_ids or []) + [worker_id])[-MAX_ERRORS:]
            run.save(update_fields=[*claimed, "attempts", "started_at", "worker_ids"])
            return run
    for pk in list(_ready(queues, now, schedules).using(db).values_list("pk", flat=True)[:5]):
        updated = DluxTaskRun.objects.using(db).filter(pk=pk, status=READY).update(
            attempts=F("attempts") + 1,
            started_at=Coalesce(F("started_at"), Value(now)),
            **claimed,
        )
        if updated:
            run = DluxTaskRun.objects.using(db).get(pk=pk)
            run.worker_ids = (list(run.worker_ids or []) + [worker_id])[-MAX_ERRORS:]
            DluxTaskRun.objects.using(db).filter(pk=pk, claim_token=token).update(worker_ids=run.worker_ids)
            return run
    return None


def _fenced(run):
    DluxTaskRun, _ = _models()
    return DluxTaskRun.objects.filter(pk=run.pk, status=RUNNING, claim_token=run.claim_token)


def complete_run(run, *, return_value=None, error=None, next_due=None, now=None):
    """Record the outcome of a claimed run. ``next_due`` re-arms a schedule row instead of finishing it.

    Returns False when the run was no longer ours (recovered by another worker).
    """
    now = now or timezone.now()
    status = FAILED if error is not None else SUCCESSFUL
    updates = {"finished_at": now, "claim_token": "", "last_status": status}
    if error is not None:
        updates["errors"] = _with_error(run.errors, error)
    else:
        try:
            updates["return_value"] = _jsonable(return_value)
        except (TypeError, ValueError):
            updates["return_value"] = None
    if run.schedule_name and next_due is not None:
        updates.update(status=READY, run_after=next_due, attempts=0)
    else:
        updates.update(status=status, sealed_arguments="")
    return _fenced(run).update(**updates) == 1


def retry_run(run, delay, *, error=None, now=None, counted=True):
    """Put a run back to READY after ``delay``; an uncounted retry gives back the claim's attempt."""
    now = now or timezone.now()
    updates = {
        "status": READY,
        "claim_token": "",
        "run_after": now + timedelta(seconds=max(0, int(delay))),
        "last_status": FAILED,
    }
    if not counted:
        updates["attempts"] = F("attempts") - 1
    if error is not None:
        updates["errors"] = _with_error(run.errors, error)
    return _fenced(run).update(**updates) == 1


def live_dlux_workers(now=None):
    _, DluxTaskWorker = _models()
    now = now or timezone.now()
    cutoff = now - timedelta(seconds=runner_config()["stale_after"])
    return DluxTaskWorker.objects.filter(heartbeat_at__gte=cutoff, stopped_at__isnull=True)


def recover_lost_runs(*, resolve, now=None, exclude_worker=None):
    """Settle RUNNING rows whose worker is gone. Returns ``(requeued, failed)``.

    Schedule rows always go back to READY (due now). A run of a task declared
    ``requeue_lost`` goes back to READY up to ``max_recoveries`` times: Celery's
    ``acks_late``. Anything else is FAILED, the way an acknowledged Celery
    message is simply gone when its worker dies.
    """
    DluxTaskRun, _ = _models()
    config = runner_config()
    now = now or timezone.now()
    alive = set(live_dlux_workers(now).values_list("id", flat=True))
    if exclude_worker:
        alive.add(exclude_worker)
    requeued = failed = 0
    for run in DluxTaskRun.objects.filter(status=RUNNING).exclude(worker_id__in=alive):
        entry = error_entry(
            exception_class_path=WORKER_LOST,
            message=f"Worker {run.worker_id or '?'} stopped sending heartbeats while this task was running.",
        )
        errors = _with_error(run.errors, entry)
        definition = resolve(run.task_name)
        if run.schedule_name:
            updates = {"status": READY, "run_after": now, "attempts": 0, "last_status": FAILED, "finished_at": now}
        elif getattr(definition, "requeue_lost", False) and run.recoveries < config["max_recoveries"]:
            updates = {"status": READY, "run_after": now, "recoveries": F("recoveries") + 1}
        else:
            updates = {"status": FAILED, "last_status": FAILED, "finished_at": now, "sealed_arguments": ""}
        if _fenced(run).update(claim_token="", errors=errors, **updates):
            if updates["status"] == READY:
                requeued += 1
            else:
                failed += 1
            logger.warning("Task run %s (%s) was lost with worker %s: %s.", run.pk, run.task_name,
                           run.worker_id, "requeued" if updates["status"] == READY else "failed")
    return requeued, failed


def sync_schedule(entries, *, now=None):
    """Make the schedule rows match ``entries``: one row per entry, never one per tick."""
    DluxTaskRun, _ = _models()
    now = now or timezone.now()
    names = []
    for entry in entries:
        names.append(entry.name)
        fields = {
            "task_name": entry.task_name,
            "args": _jsonable(list(entry.args)),
            "kwargs": _jsonable(dict(entry.kwargs)),
            "priority": entry.priority,
            "queue_name": entry.queue_name,
            "schedule_signature": entry.signature,
        }
        existing = DluxTaskRun.objects.filter(schedule_name=entry.name).first()
        if existing is None:
            try:
                with transaction.atomic():
                    DluxTaskRun.objects.create(schedule_name=entry.name, run_after=entry.first_due(now), **fields)
            except IntegrityError:
                pass  # another worker created it first
            continue
        stale = DluxTaskRun.objects.filter(pk=existing.pk).exclude(schedule_signature=entry.signature)
        stale.exclude(status=RUNNING).update(status=READY, run_after=entry.first_due(now), attempts=0, **fields)
        stale.filter(status=RUNNING).update(**fields)
        # A finished schedule row means a re-arm was lost: arm it again.
        DluxTaskRun.objects.filter(pk=existing.pk, status__in=[SUCCESSFUL, FAILED]).update(
            status=READY, run_after=entry.next_due(now, previous_due=existing.run_after), attempts=0,
        )
    removed, _ = DluxTaskRun.objects.filter(schedule_name__isnull=False).exclude(
        schedule_name__in=names).exclude(status=RUNNING).delete()
    return removed


def prune(*, now=None):
    """Delete finished one-off runs past their retention and long-gone worker rows."""
    DluxTaskRun, DluxTaskWorker = _models()
    config = runner_config()
    now = now or timezone.now()
    one_off = DluxTaskRun.objects.filter(schedule_name__isnull=True)
    deleted = one_off.filter(status=SUCCESSFUL, finished_at__lt=now - timedelta(seconds=config["keep_successful"])).delete()[0]
    deleted += one_off.filter(status=FAILED, finished_at__lt=now - timedelta(seconds=config["keep_failed"])).delete()[0]
    gone = now - timedelta(seconds=max(86400, config["stale_after"] * 10))
    DluxTaskWorker.objects.filter(heartbeat_at__lt=gone).delete()
    return deleted


def queue_summary(now=None):
    """Counts for the Options page and the doctor."""
    from django.db.models import Count, Q

    DluxTaskRun, _ = _models()
    now = now or timezone.now()
    one_off = DluxTaskRun.objects.filter(schedule_name__isnull=True)
    return one_off.aggregate(
        ready=Count("pk", filter=Q(status=READY, run_after__lte=now)),
        waiting=Count("pk", filter=Q(status=READY, run_after__gt=now)),
        running=Count("pk", filter=Q(status=RUNNING)),
        failed=Count("pk", filter=Q(status=FAILED)),
    ) | {
        "schedules_failing": DluxTaskRun.objects.filter(schedule_name__isnull=False, last_status=FAILED).count(),
    }
