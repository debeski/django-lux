# Task Runner

DjangoLux has its own task runner: a queue table in the project database and
`python manage.py dlux_worker`. It runs DjangoLux's tasks without Celery, Celery
Beat or a Redis broker. That also suits a single-PC Windows desktop build: Celery
has no supported Windows worker, and a broker is one more service to bundle.
Celery remains the runner for a project's own tasks. The planned default and the
deprecation of Celery for DjangoLux's tasks are in
[Deprecation Countdown](deprecation-countdown.md).

## Choosing the backend

| `DLUX_TASK_BACKEND` | What runs DjangoLux's tasks | Broker |
|---|---|---|
| `"celery"` (default) | The Celery worker and its embedded beat | Redis |
| `"dlux"` | `python manage.py dlux_worker` | none (the project database) |

It is a Django setting that `dlux_settings()` also reads from the environment,
so a testbed can flip it in Compose without touching project code. Any other
value fails system check `dlux.E101` and is treated as `celery`. Both web and the
worker must see the same value: web decides where a task is sent, the worker
only runs the dlux queue.

A Celery worker with beat can run beside `dlux_worker` for the project's own
tasks. Under `dlux`, `dlux_settings()` takes DjangoLux's entries out of
`CELERY_BEAT_SCHEDULE`, so Celery Beat never fires them a second time.

## API

### Declaring a task

DjangoLux's tasks live in `dlux/jobs.py`, declared once for both backends:

```python
from dlux.taskrunner import Retry, task

@task(name="dlux.tasks.ocr_file", takes_context=True, requeue_lost=True, max_retries=8)
def ocr_file(context, result_id):
    try:
        run(result_id)
    except OCRUnavailable as exc:
        if context.retries >= 8:
            give_up(result_id, ...)
            return
        raise Retry(OCR_RETRY_DELAYS[context.retries]) from exc
```

| Option | Meaning |
|---|---|
| `name` | Stable task name; defaults to the import path. DjangoLux keeps the `dlux.tasks.*` names so messages already in a broker still resolve. |
| `priority` | Default priority, django.tasks semantics (below). |
| `queue_name` | Queue (default `"default"`); a worker takes the queues in `DLUX_TASK_RUNNER["queues"]` or `--queue`. |
| `takes_context` | First argument is a `TaskContext` (`attempt` from 1, `retries`, `priority`, `run_id`, `backend`). |
| `max_retries` | Upper bound on `Retry`; one more `Retry` fails the run. Also Celery's `max_retries`. |
| `requeue_lost` | At-least-once: a run whose worker died goes back to the queue (Celery's `acks_late`). |
| `sensitive` | Arguments are encrypted at rest and cleared when the run ends (backup passphrases). |

While Celery is importable, `@task` also registers a Celery task under the same
name (`definition.celery`), with `bind=True`, `ignore_result=True`, and
`acks_late`/`max_retries` from the options. `dlux/tasks.py` keeps exposing those
Celery tasks under the attribute names projects import (`build_system_backup_task`,
`ocr_file`, ...) and keeps the `worker_ready` hook; it is what `celery
autodiscover_tasks()` imports. A `Retry` raised under Celery becomes
`self.retry(countdown=delay)` with the message's own delivery priority.

The API deliberately mirrors `django.tasks`: `enqueue(*args, **kwargs)`,
`using(priority=, run_after=, queue_name=)` (plus `countdown=`), `call()` to run
inline, `takes_context`. It does not use `django.tasks` itself, so it works on
every Django DjangoLux supports and regardless of a project's `TASKS` setting.

### Sending a task

```python
from dlux.taskrunner import enqueue

enqueue("dlux.tasks.ocr_file", args=(row.pk,), priority=-6)
enqueue("dlux.tasks.build_system_backup", args=[pk, passphrase], sensitive=True)
build_system_backup.using(countdown=600).enqueue(pk, passphrase)
```

Callers send by name and never import `dlux.jobs`, which keeps backups and
reports out of the updater's import cycle. Under `celery` `enqueue` calls
`current_app.send_task(name, args=..., retry=False)` (plus `priority`/`countdown`
when given). Under `dlux` it inserts a queue row inside the caller's transaction, so a
job is visible to the worker only if the work that queued it commits. Sending by
name never seals arguments on its own: a sensitive task's caller passes
`sensitive=True` (its `DluxTask.enqueue` does).

Every DjangoLux call site publishes to Celery with `retry=False`. An OCR file
whose message could not be published stays `pending` and is queued again once
it is stale.

### Priorities

Priorities follow `django.tasks`: whole numbers from -100 to 100, **higher runs
first**, default 0. On Celery's Redis transport (lower runs first, 0 to 9) the
facade sends `min(9, max(0, -priority))`:

| Work | dlux priority | Celery priority |
|---|---|---|
| Run OCR (manual), unprioritised tasks | 0 | 0 |
| Automatic OCR on save | -6 | 6 |
| OCR backfill, background scan | -9 | 9 |

`dlux.ocr.service.PRIORITY` holds the dlux numbers.

### Is anything running the work?

`dlux.taskrunner.worker_alive()` answers for every place that needs a running
worker (system backups, report backups, weather, the Options Tasks row). Under
`celery` it opens a broker connection, then sends a one-second ping. Under
`dlux` it is one indexed query: a `DluxTaskWorker` row whose heartbeat is inside
`stale_after` and that has not stopped. No broker round trip, so web can ask it
freely.

### Worker hooks

`dlux.taskrunner.worker_started` is sent once after the worker's heartbeat row
exists and before it claims anything; `worker_stopping` when it stops claiming.
DjangoLux connects its stalled-backup reaper to `worker_started`, the job
Celery's `worker_ready` hook does under Celery.

### `django.tasks` (Django 6.0+)

`dlux.taskrunner.backend.DatabaseBackend` is a `django.tasks` backend over the
same queue (`supports_defer`, `supports_priority`, `supports_get_result`). Under
`DLUX_TASK_BACKEND = "dlux"` on Django 6.0+, `dlux_settings()` sets
`TASKS = {"default": {"BACKEND": "dlux.taskrunner.backend.DatabaseBackend"}}`
unless the project set `TASKS` itself. A standard `@django.tasks.task` function
then runs on `dlux_worker`, with Django's task signals and `get_result()`. Raising
`dlux.taskrunner.Retry` works there too.

### Schedules

`DLUX_TASK_SCHEDULE` has the shape of `CELERY_BEAT_SCHEDULE`, so an entry moves
over by copying it:

```python
from dlux.taskrunner import crontab

DLUX_TASK_SCHEDULE = {
    "crm-refresh-rates": {"task": "crm.tasks.refresh_rates", "schedule": crontab(minute=0, hour="*/3")},
    "documents-refresh-brand-summary": {"task": "documents.tasks.refresh", "schedule": 900},
}
```

`schedule` is seconds, a `timedelta`, a `dlux.taskrunner.crontab` or a
`celery.schedules.crontab` (read through its expanded fields). `crontab` takes
Celery's arguments (`minute`, `hour`, `day_of_week`, `day_of_month`,
`month_of_year`; `*`, `*/n`, ranges, lists, `mon`-`sun`, `jan`-`dec`, Sunday as 0
or 7), evaluates in the project's `TIME_ZONE`, and, like Celery, requires day of
month **and** day of week to match. `options.priority` (or `priority`) and
`options.queue` are honoured. `dlux_settings()` adds DjangoLux's four entries
(`dlux-state-tick` 5 s, `dlux-scheduled-system-backup-check` 900 s,
`dlux-update-check` 3600 s, `dlux-ocr-background` 60 s at priority -9) next to the
project's. Under `"celery"` it keeps adding the same four to
`CELERY_BEAT_SCHEDULE`; under `"dlux"` it takes them out of it, because a Celery
worker with beat may still run next to `dlux_worker` for the project's own tasks
and must not fire DjangoLux's entries a second time. A bad entry fails system
check `dlux.E102`.

`task` names either a registered `@task` name or the import path of a
`django.tasks.Task`. Project Celery `@shared_task` functions are not run by the
dlux worker: Celery stays the runner for project-side tasks, with the project's
own `CELERY_BEAT_SCHEDULE` entries. A project that wants a task on the dlux
worker declares it with `@dlux.taskrunner.task` and schedules it in
`DLUX_TASK_SCHEDULE`.

## Schema

Migration `0030_task_runner` (additive) adds two tables. Neither has a foreign
key to project or user data.

**`dlux.DluxTaskRun`**: one queued job, or the single state row of one schedule
entry.

| Field | Purpose |
|---|---|
| `id` | 32-hex id (the `django.tasks` result id). |
| `task_name`, `queue_name` | What to run and where. |
| `args`, `kwargs` | JSON arguments; empty for a sensitive task. |
| `sealed_arguments` | Fernet token (key from `SECRET_KEY`) holding a sensitive task's arguments; cleared when the run finishes. |
| `priority`, `run_after` | Claim order and earliest start. |
| `status` | `READY`, `RUNNING`, `SUCCESSFUL`, `FAILED` (Django's `TaskResultStatus` values). |
| `last_status` | Outcome of the latest attempt or tick (a schedule row is READY between ticks). |
| `attempts`, `recoveries` | Claims of this row; times it was put back after its worker died. |
| `worker_id`, `worker_ids`, `claim_token` | Current claimer, the last ten claimers, and the fencing token of the current claim. |
| `enqueued_at`, `started_at`, `last_attempted_at`, `finished_at` | Timestamps. |
| `errors` | The last ten errors: `exception_class_path` and traceback (8 KB tail). |
| `return_value` | JSON return value (for `get_result()`); unserialisable values are stored as null. |
| `schedule_name`, `schedule_signature` | Set on schedule rows (unique), with a hash of the entry so a changed entry is noticed. |

Indexes: a partial index on `(-priority, run_after)` where `status = 'READY'`
(the claim query), `(status, finished_at)` (pruning) and a partial index on
`worker_id` where `status = 'RUNNING'` (recovery).

**`dlux.DluxTaskWorker`**: one row per worker process: `id`
(`host:pid:random`), `hostname`, `pid`, DjangoLux `version`, `threads`,
`queues`, `started_at`, `heartbeat_at`, `stopped_at`. The row says which
release a worker runs (under Celery, the `dlux_version` inspect command does).

## Worker lifecycle

```
python manage.py dlux_worker [--threads N] [--queue NAME ...] [--no-schedule] [--burst] [--check]
```

1. **Start**: import `dlux.jobs` and every installed app's `tasks` module (as
   Celery's autodiscovery does); parse `DLUX_TASK_SCHEDULE`; register the
   heartbeat row. A live-looking row with the same hostname and pid is this
   process's previous incarnation (a restarted container keeps both), so it is
   marked stopped and its runs are settled at once instead of after the stale
   window. Send `worker_started`; recover lost runs; prune; sync the schedule
   rows (create missing, update changed, delete removed ones that are not
   running).
2. **Loop**: while a thread is free, claim the next due run and hand it to the
   pool (`threads`, default 4). With nothing due, wait `poll_interval` (1 s) or
   until a thread frees up. A maintenance thread heartbeats every
   `heartbeat_interval` (10 s), settles runs lost by dead workers, and prunes
   hourly.
3. **Stop** (SIGTERM/SIGINT): stop claiming, send `worker_stopping`, and wait up
   to `shutdown_grace` (25 s) for running tasks. If they finish, the worker marks
   its row stopped and exits. If not, it keeps heartbeating until they end, so
   nothing is recovered under a live task. Docker kills the container after the
   service's `stop_grace_period` (10 s unless set); then the heartbeat stops and
   recovery takes over after `stale_after`, or at once when the restarted
   container registers.

`--burst` runs what is due in the calling thread and exits (tests, a one-shot
cron job). `--no-schedule` runs queued work only. `--check` exits 0 when a worker
on this host has a fresh heartbeat, for a container healthcheck.

Each task runs in a pool thread with its own database connection;
`close_old_connections()` runs before and after every task, as Celery's Django
fixup does.

## Claiming

PostgreSQL (and any backend with `SKIP LOCKED`) claims with one transaction:
`SELECT ... WHERE status = 'READY' AND run_after <= now ORDER BY priority DESC,
run_after, enqueued_at LIMIT 1 FOR UPDATE SKIP LOCKED`, then marks the row
RUNNING with a fresh `claim_token`. Concurrent workers skip each other's locked
rows instead of waiting.

Elsewhere (SQLite, used by the test suite and possibly a desktop build) the
claim is a compare-and-set: read up to five candidates, then
`UPDATE ... SET status = 'RUNNING' ... WHERE id = ? AND status = 'READY'`; only
one claimer's update matches. It is correct with several workers but serialises
on SQLite's write lock, so **one worker process per SQLite database** is the
supported setup. SQLite also holds its write lock for a whole restore
transaction, so the worker's heartbeat waits behind it; with a single worker
nothing else would recover the run, and the restore finishes first.

Every later transition (success, failure, retry, recovery) is an `UPDATE`
fenced on the claim token, so a worker that lost its run can never overwrite the
newer outcome; its late result is logged and dropped.

## Failure semantics

| What happens | One-off run | Schedule row |
|---|---|---|
| Task returns | `SUCCESSFUL`, return value kept | `READY` at the next slot, `last_status = SUCCESSFUL` |
| Task raises `Retry(delay)` | Same row back to `READY`, `run_after = now + delay`, priority kept, error recorded | same, within the tick |
| `Retry` past `max_retries` | `FAILED` | `READY` at the next slot, `last_status = FAILED` |
| Task raises anything else | `FAILED` with traceback (no automatic retries, as on Celery) | `READY` at the next slot, `last_status = FAILED` |
| Unknown task name | `FAILED` (`dlux.taskrunner.UnknownTask`) | same, re-armed |
| Sealed arguments unreadable (changed `SECRET_KEY`) | `FAILED` | n/a |
| Worker dies mid-run, task `requeue_lost` | Back to `READY` (due now), up to `max_recoveries` (3), then `FAILED` | `READY`, due now |
| Worker dies mid-run, other tasks | `FAILED` (`dlux.taskrunner.WorkerLost`); Celery drops an acknowledged message | `READY`, due now |

A worker is dead when its heartbeat is older than `stale_after` (60 s) or its
row is marked stopped. Delivery is **at-least-once** for `requeue_lost` tasks
(OCR files) and **at-most-once** otherwise. A worker that cannot reach the
database for longer than `stale_after` while its task keeps running can have
that task recovered elsewhere; `ocr_file` is safe to run twice (it locks its
`FileText` row and skips work that is done or fresh), and the backup tasks have
their own row guards and reaper. There are no per-task time limits (none are
configured on Celery either); a hung task holds its thread until the worker
restarts.

Retention: finished one-off runs are pruned after `keep_successful` (1 day) and
`keep_failed` (7 days); schedule rows are never pruned; worker rows silent for a
day are deleted.

## Scheduler

There is no beat process and no leader election. Each schedule entry is **one
queue row** that is claimed like any other run, which gives these guarantees
without an advisory lock:

- **No double fire.** A tick is a claim, and a row is claimed once; two workers
  cannot run the same tick.
- **No overlap.** An entry cannot start again while its previous run is still
  going (the row is RUNNING). Under Celery, beat can queue the next state tick
  behind a slow one; the cache lock in `dlux_state_tick` covers that case.
- **No row per tick.** The worker that finishes a tick re-arms the same row in
  the same fenced `UPDATE`: `READY`, `attempts = 0`, `run_after` = the next slot.
  The 5-second state tick is one row, not 17,000 a day.
- **Priority applies.** The background OCR scan (priority -9) waits behind
  manual OCR files like any other low-priority run.

Next slot: intervals stay on their grid (the first `previous_due + k × interval`
after the run ends), so a slow run or a stopped worker causes one catch-up run,
not a burst. Cron entries take their next match. A new entry runs at once if it
is an interval, at its next match if it is cron. A changed entry (task, schedule,
arguments, priority or queue) is re-armed from now; a removed one is deleted.
A worker only claims schedule rows for entries in its own `DLUX_TASK_SCHEDULE`,
so it never runs or re-arms an entry it has no spec for. All workers of one
deployment should share one schedule: two releases with different schedules
running side by side re-sync the rows each time one of them starts.

## Security

- **Arguments at rest.** Backup and restore passphrases are transient in Redis
  under Celery but would persist in a database queue. Tasks declared
  `sensitive=True` (`build_system_backup`, `restore_system_backup`) store their
  arguments only as a Fernet token derived from `SECRET_KEY` and clear it when
  the run ends, including on failure. The queue tables are never in a system
  backup.
- **What a row can run.** A worker resolves a task name only to a registered
  `@task` or an imported `django.tasks.Task`. A row naming any other importable
  callable (`os.system`) fails as an unknown task.
- **Same position as the Celery worker.** `dlux_worker` belongs where the
  Celery worker runs, in a generated stack's `celery` service: internal network
  only, the writer of the runtime volume. It opens no outbound connections; tasks that need the internet
  keep going through the Composer relay.
- **Audit and UI.** The tables are excluded from the activity log
  (`LOG_FORCED_EXCLUDED_MODEL_KEYS`), from reports (`dlux_report = False` and
  DjangoLux's own models are never report models) and from the permissions UI
  (DjangoLux models outside the whitelist). Nothing in the browser can enqueue
  an arbitrary task; web only sends DjangoLux's own tasks by name from views
  that already enforce their permissions.

## Backups and restores

`dlux.dluxtaskrun` and `dlux.dluxtaskworker` are in `_SYSTEM_BACKUP_EXCLUDED`, so
they are not written to a `.dlb` and a restore neither wipes nor reloads them. A
restore runs as one of these rows: replacing the table would erase its own job
and the worker's heartbeat mid-run. A restore run by the worker therefore ends
with its own row `SUCCESSFUL` and leaves other queued runs in place.

## Django before 6.0

DjangoLux still allows `Django>=5.1`. On 5.x the dlux backend works for
DjangoLux's own tasks: `@dlux.taskrunner.task`, the queue, the worker and the
scheduler do not use `django.tasks`. Only `dlux.taskrunner.backend` (the
`django.tasks` adapter) needs Django 6.0; `dlux_settings()` sets `TASKS` only on
6.0+, and project code written with `django.tasks` needs 6.0 anyway. The test
suite runs on Django 6.x only.

## Operating it

- **Options page, Tasks row**: under `dlux` it shows `dlux_worker`, online
  with the worker count and the due and failed counts, degraded when runs or
  schedule entries failed, offline when no heartbeat is fresh. It is a database
  read, so it is always current (the Celery row pings on demand).
- **Doctor**: `tasks.worker` warns when no worker heartbeat is fresh, when a
  project `CELERY_BEAT_SCHEDULE` entry would run nowhere (no `CELERY_BROKER_URL`
  and no `DLUX_TASK_SCHEDULE` twin), and when runs failed; it fails on an invalid
  backend value.
  `celery.configured` is skipped under `dlux`.
- **Inspecting the queue**: `DluxTaskRun.objects.filter(status="FAILED")` holds
  the traceback in `errors`; a failed one-off run can be retried by setting it
  back to `READY` with `run_after` now.
