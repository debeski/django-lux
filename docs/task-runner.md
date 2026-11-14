# Task Runner

DjangoLux runs its background work on its own task manager: a queue table in
the project database and `python manage.py dlux_worker`. Backups and restores,
the update check and the state tick, OCR, weather and the scheduled jobs all run
there, with no Celery, Celery Beat or broker. In a generated stack the `worker`
service runs it. A single-PC Windows desktop build runs it the same way, since
nothing in it needs a broker.

The same API is public for projects: declare a task with `@task`, queue it with
`.enqueue()` (or `.delay()`), schedule it in `DLUX_TASK_SCHEDULE`.

## API

Everything a project needs is importable from `dlux.taskrunner`: `task`,
`enqueue`, `Retry`, `TaskContext`, `crontab`, `worker_alive`, `worker_started`,
`worker_stopping`, `registered_tasks`, `runner_config` and the `DluxTask` type.

### Declaring a task

Put tasks in an app's `tasks.py`; `dlux_worker` imports every installed app's
`tasks` module at start. DjangoLux's own tasks live in `dlux/jobs.py`:

```python
from dlux.taskrunner import Retry, task

@task(name="dlux.tasks.ocr_file", takes_context=True, requeue_lost=True, max_retries=8)
def ocr_file(context, result_id):
    try:
        run(result_id)
    except OCRBusy as exc:            # busy, not broken: wait without using a retry
        raise Retry(exc.retry_after, counts=False) from exc
    except OCRUnavailable as exc:
        if context.retries >= 8:
            give_up(result_id, ...)
            return
        raise Retry(OCR_RETRY_DELAYS[context.retries]) from exc
```

| Option | Meaning |
|---|---|
| `name` | Stable task name, stored in the queue; defaults to the import path. Give tasks an explicit name so moving the function does not strand queued runs. DjangoLux's are `dlux.tasks.*`. |
| `priority` | Default priority, django.tasks semantics (below). |
| `queue_name` | Queue (default `"default"`); a worker takes the queues in `DLUX_TASK_RUNNER["queues"]` or `--queue`. |
| `takes_context` | First argument is a `TaskContext` (`attempt` from 1, `retries`, `priority`, `run_id`, `backend`). |
| `max_retries` | Upper bound on `Retry`; one more `Retry` fails the run. |
| `requeue_lost` | At-least-once: a run whose worker died goes back to the queue. |
| `sensitive` | Arguments are encrypted at rest and cleared when the run ends (backup passphrases). |

The API deliberately mirrors `django.tasks`: `enqueue(*args, **kwargs)`,
`using(priority=, run_after=, queue_name=)` (plus `countdown=`), `call()` to run
inline, `takes_context`. It does not use `django.tasks` itself, so it works on
every Django DjangoLux supports and regardless of a project's `TASKS` setting.
`delay()` is `enqueue()` under Celery's name, so call sites moved from Celery,
and the mocks in their tests, keep working.

`dlux.tasks` exposes DjangoLux's tasks under their historical attribute names
(`build_system_backup_task`, `ocr_file`, ...); they are the same `DluxTask`
objects.

### Sending a task

```python
from dlux.taskrunner import enqueue

refresh_rates.enqueue()
refresh_rates.delay()
build_system_backup.using(countdown=600).enqueue(pk, passphrase)
enqueue("dlux.tasks.ocr_file", args=(row.pk,), priority=-6)
enqueue("dlux.tasks.build_system_backup", args=[pk, passphrase], sensitive=True)
```

Every form inserts a queue row inside the caller's transaction and returns its
run id, so a job is visible to the worker only if the work that queued it
commits. Sending by name keeps the caller from importing the task module (which
keeps DjangoLux's backups and reports out of the updater's import cycle). It
never seals arguments on its own: a sensitive task's caller passes
`sensitive=True` (its `DluxTask.enqueue` does).

### Priorities

Priorities follow `django.tasks`: whole numbers from -100 to 100, **higher runs
first**, default 0.

| Work | Priority |
|---|---|
| Run OCR (manual), unprioritised tasks | 0 |
| Automatic OCR on save | -6 |
| OCR backfill, background scan | -9 |

`dlux.ocr.service.PRIORITY` holds these numbers.

### Is anything running the work?

`dlux.taskrunner.worker_alive()` answers for every place that needs a running
worker (system backups, report backups, weather, the Options Tasks row). It is
one indexed query: a `DluxTaskWorker` row whose heartbeat is inside `stale_after`
and that has not stopped. No broker round trip, so web can ask it freely.

### Worker hooks

`dlux.taskrunner.worker_started` is sent once after the worker's heartbeat row
exists and before it claims anything; `worker_stopping` when it stops claiming.
Receivers get `worker=` (the `Worker`). DjangoLux connects its stalled-backup
reaper to `worker_started`.

### `django.tasks` (Django 6.0+)

`dlux.taskrunner.backend.DatabaseBackend` is a `django.tasks` backend over the
same queue (`supports_defer`, `supports_priority`, `supports_get_result`). On
Django 6.0+, `dlux_settings()` sets
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
month **and** day of week to match. `options.priority` (or `priority`),
`options.queue`, `args` and `kwargs` are honoured. `dlux_settings()` adds
DjangoLux's four entries (`dlux-state-tick` 5 s,
`dlux-scheduled-system-backup-check` 900 s, `dlux-update-check` 3600 s,
`dlux-ocr-background` 60 s at priority -9) next to the project's. A bad entry
fails system check `dlux.E102`.

`task` names either a registered `@task` name or the import path of a
`django.tasks.Task`.

## Moving project tasks from Celery

Celery for project tasks is deprecated: the doctor check `tasks.celery_deprecated`
warns while a project still uses it, and generated stacks stop installing Celery
(see [Deprecation Countdown](deprecation-countdown.md)). New projects get no
Celery. A stack migrated by Composer keeps a project-only `celery` service until
the project has moved:

| Celery | DjangoLux task manager |
|---|---|
| `@shared_task(name="crm.refresh")` / `@app.task` | `@task(name="crm.refresh")` from `dlux.taskrunner` |
| `refresh.delay(1)` | `refresh.delay(1)` or `refresh.enqueue(1)` |
| `refresh.apply_async(args=[1], countdown=60)` | `refresh.using(countdown=60).enqueue(1)` |
| `apply_async(priority=9)` (Redis: lower first) | `using(priority=-9)` (higher first) |
| `send_task("crm.refresh", args=[1])` | `enqueue("crm.refresh", args=[1])` |
| `@shared_task(bind=True)` + `self.retry(countdown=30)` | `@task(takes_context=True)` + `raise Retry(30)`; `context.retries` counts them |
| `acks_late=True` | `requeue_lost=True` |
| `CELERY_BEAT_SCHEDULE` entry | the same entry in `DLUX_TASK_SCHEDULE` |
| `celery.schedules.crontab` | `dlux.taskrunner.crontab` (same arguments) |
| `worker_ready.connect(...)` | `worker_started.connect(...)` |

Then remove the project's `celery.py` and its import in the package
`__init__.py`, the `CELERY_*` settings, `celery` and `django-celery-beat` from
the requirements, and the `celery` service (with its name in
`COMPOSER_AGENT_RESTART_SERVICES`) from `compose.yml`. Results are not kept
the way a Celery result backend keeps them; a task that must report back writes
to a model, or the project uses `django.tasks` and `get_result()`.

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
release a worker runs.

## Worker lifecycle

```
python manage.py dlux_worker [--threads N] [--queue NAME ...] [--no-schedule] [--burst] [--check]
```

1. **Start**: import `dlux.jobs` and every installed app's `tasks` module;
   parse `DLUX_TASK_SCHEDULE`; register the
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
`close_old_connections()` runs before and after every task.

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
| Task raises `Retry(delay, counts=False)` | Same as `Retry(delay)`, but the attempt is given back: it never uses `max_retries` (a busy resource, not a failure) | same, within the tick |
| `Retry` past `max_retries` | `FAILED` | `READY` at the next slot, `last_status = FAILED` |
| Task raises anything else | `FAILED` with traceback (no automatic retries) | `READY` at the next slot, `last_status = FAILED` |
| Unknown task name | `FAILED` (`dlux.taskrunner.UnknownTask`) | same, re-armed |
| Sealed arguments unreadable (changed `SECRET_KEY`) | `FAILED` | n/a |
| Worker dies mid-run, task `requeue_lost` | Back to `READY` (due now), up to `max_recoveries` (3), then `FAILED` | `READY`, due now |
| Worker dies mid-run, other tasks | `FAILED` (`dlux.taskrunner.WorkerLost`) | `READY`, due now |

A worker is dead when its heartbeat is older than `stale_after` (60 s) or its
row is marked stopped. Delivery is **at-least-once** for `requeue_lost` tasks
(OCR files) and **at-most-once** otherwise. A worker that cannot reach the
database for longer than `stale_after` while its task keeps running can have
that task recovered elsewhere; `ocr_file` is safe to run twice (it locks its
`FileText` row and skips work that is done or fresh), and the backup tasks have
their own row guards and reaper. There are no per-task time limits; a hung task
holds its thread until the worker restarts.

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
  going (the row is RUNNING). The cache lock in `dlux_state_tick` also covers
  an operator running it by hand.
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

- **Arguments at rest.** A database queue would keep backup and restore
  passphrases on disk. Tasks declared
  `sensitive=True` (`build_system_backup`, `restore_system_backup`) store their
  arguments only as a Fernet token derived from `SECRET_KEY` and clear it when
  the run ends, including on failure. The queue tables are never in a system
  backup.
- **What a row can run.** A worker resolves a task name only to a registered
  `@task` or an imported `django.tasks.Task`. A row naming any other importable
  callable (`os.system`) fails as an unknown task.
- **Where it runs.** In a generated stack `dlux_worker` is the `worker` service:
  internal network only, and the one DjangoLux service that writes the runtime
  volume. It opens no outbound connections; tasks that need the internet go
  through the Composer relay.
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

DjangoLux still allows `Django>=5.1`. On 5.x the task manager works for
DjangoLux's and the project's `@task` functions: `@dlux.taskrunner.task`, the queue, the worker and the
scheduler do not use `django.tasks`. Only `dlux.taskrunner.backend` (the
`django.tasks` adapter) needs Django 6.0; `dlux_settings()` sets `TASKS` only on
6.0+, and project code written with `django.tasks` needs 6.0 anyway. The test
suite runs on Django 6.x only.

## Operating it

- **Generated stack**: the `worker` service runs
  `python -m dlux.updater.supervisor -- python manage.py dlux_worker`, carries
  the init containers (`dlux_reconcile`, then `migrator`), applies migrations on
  a restart (`DLUX_BOOT_GATE: apply`), and has the healthcheck
  `python manage.py dlux_worker --check` and `stop_grace_period: 30s`. A stack
  generated before stack schema 5 has no `worker`. With the project image on
  DjangoLux 1.16 (pulled, or rebuilt after bumping the pin), `./start.sh check
  --fix` (Composer 1.10 or later) adds it, and the next deploy starts it; a
  development stack runs `./start.sh -d check --fix`, then `./start.sh -d -b`.
  Without `worker`, queued DjangoLux tasks wait in the queue. See
  [Stack Schema Stamps](stack-schema.md).
- **Options page, Tasks row**: shows `dlux_worker`, online with the worker count
  and the due and failed counts, degraded when runs or schedule entries failed,
  offline when no heartbeat is fresh. It is a database read, so it is always
  current; the recheck button (`POST sys/api/task-worker-health/`, staff only)
  reads it again.
- **Doctor**: `tasks.worker` warns when no worker heartbeat is fresh (naming
  `check --fix` for an older stack) and when runs failed; it fails when the queue
  tables cannot be read. `tasks.celery_deprecated` warns while the project still
  has a Celery app, beat entries or `CELERY_BROKER_URL`.
- **Inspecting the queue**: `DluxTaskRun.objects.filter(status="FAILED")` holds
  the traceback in `errors`; a failed one-off run can be retried by setting it
  back to `READY` with `run_after` now.
