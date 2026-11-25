# Deployment Doctor

The doctor diagnoses a DjangoLux deployment across two layers that cannot see
each other:

| Layer | Runs as | Sees |
| --- | --- | --- |
| Project directory | Composer, on the host | `compose.yml`, `.secrets/.env`, `.proxy/*`, image labels, container/network state |
| Application | `manage.py dlux_doctor`, inside the app container | settings, database, migrations, cache, SMTP, static files, `SystemSettings` |

The app container has no access to `compose.yml` (it is in `.dockerignore` and
the project root is not mounted into `web`), and Composer cannot import Django.
So Composer orchestrates: `composer check --deep` runs its own project-directory
checks, executes `dlux_doctor --format json` in the app container (overridable
via `--deep-service` / `--deep-command`), merges both reports, and renders one
result with one exit code.

This split means app-side checks version with the dlux release that is actually
running. Composer needs no dlux knowledge beyond the report schema below.

`dlux_check` is a deprecated alias for `dlux_doctor`: it warns on stderr,
delegates, and always exits 0, so it is advisory only. Use `dlux_doctor` wherever
the exit code should gate.

## Report schema

`schema_version` is `1`. Adding checks is backwards-compatible; renaming a check
id or changing the field set requires a version bump.

```json
{
  "schema_version": 1,
  "producer": "dlux",
  "producer_version": "1.5.8",
  "generated_at": "2026-07-24T18:00:00+00:00",
  "status": "ok",
  "counts": {"ok": 18, "warning": 2, "error": 0, "skipped": 4},
  "checks": [
    {
      "id": "static.collected",
      "group": "static",
      "title": "Static files are collected",
      "status": "error",
      "detail": "STATIC_ROOT (/app/staticfiles) is empty.",
      "remedy": "Run: python manage.py collectstatic --noinput",
      "fix": {
        "kind": "management_command",
        "argv": ["collectstatic", "--noinput"],
        "label": "Collect static files",
        "safety": "safe"
      }
    }
  ]
}
```

- `status` per check is `ok`, `warning`, `error`, or `skipped`. Top-level
  `status` is the worst check; `skipped` never degrades it.
- `remedy` is human instruction and may be multi-line. `fix` is `null` unless the
  finding can be remediated automatically.
- A check that raises is reported as an `error` check, never as a crash — the
  doctor is most needed when the deployment is broken.
- A check that does not answer in time is an `error` check too, with its timing
  (see [When a dependency is down or hung](#when-a-dependency-is-down-or-hung)).
- Reports carry no secret values, only key names, lengths, and booleans. They are
  safe to paste into an issue.

## Stack contract

`dlux/contracts/stack.json` is the machine-readable spec of the expected Compose
stack: which services exist, which networks each joins, the sole published
ingress, where the Docker socket may be mounted (`rw`, `composer-executor` only), the
`dlux_runtime` read/write split, each service's restart class, and the declared
volumes and env keys.

Every service carries an `org.dlux.restart` label — `safe` (stateless / owns no
in-flight operation: web, worker, celery, smtp-relay, caddy, ocr) or `protected` (data store,
holds state, or manages its own lifecycle: db, redis, composer-agent,
composer-executor). Composer classifies restart safety from
these labels instead of a hardcoded name list; the `safe` set mirrors
`COMPOSER_AGENT_RESTART_SERVICES`, and a scaffold test keeps the two from
drifting. The contract is the single source of truth for the stack's shape:
`ComposeNetworkTopologyTests` asserts the scaffold satisfies it.

Nothing compares a *deployed* `compose.yml` with the contract. Composer's
`composer check` reads the deployed files with its own rules (topology,
runtime volume, stack schema stamps) and does not load the contract or run
`dlux_stack_contract`.

A `removed_services` map names services DjangoLux once shipped and has since
dropped (currently `db-backup` and `pgadmin`). `removed_services_present()`
names the ones a list of service names still contains; `diff_attachments()`
ignores *extra* services, because a project may run its own sidecars.

`python manage.py dlux_stack_contract` prints the contract as JSON. Run in the
app container, it prints the contract of the release actually running:
generated `manage.py` resolves the runtime-active release before Django loads,
so after an inline update it is not the copy baked into the image.
`load_contract()` stamps the result with `dlux_version`. `diff_attachments()` is
a dependency-free comparison of a stack's network attachments with the
contract. It flags a contract service on the wrong networks, a missing
contract service, any service on an undeclared network, and any service
(contract or project-added) that bridges `frontend` and `egress` and so
collapses the ingress/egress isolation. The scaffold tests use it. The
contract's `schema_version` is the stack schema: adding services/keys is
backwards-compatible, renaming a field bumps it. Generated stack files record the schema they were written for; the
`stack.schema` check compares `compose.yml`'s stamp with the running contract
(see [Stack Schema Stamps](stack-schema.md)).

## Check groups

| Group | Covers |
| --- | --- |
| `settings` | INSTALLED_APPS and ordering, middleware presence and ordering, context processor, Crispy pack, `dlux_settings()` helper, where the session cookie can be stored |
| `urls` | dlux URL mounting |
| `database` | reachability, unapplied migrations, `SystemSettings` row, setup completion |
| `services` | cache round-trip (`cache.reachable`: the probe made before the other checks; see [When a dependency is down or hung](#when-a-dependency-is-down-or-hung)), inline-update runtime volume, the image against the active release's floor (`updater.image_floor`: an error when the active inline release needs a newer project image, so the image's own DjangoLux is served; see [When the image is below the release floor](inline-updater.md#when-the-image-is-below-the-release-floor)), stack schema stamp, email delivery as the Email step sets it (`email.configured`: the route and whether its settings are complete; `email.reachable`: the internal SMTP relay answers, or on direct SMTP the provider accepts a TCP connection; both skipped while email delivery is off in System Settings > Email), DjangoLux task worker (`tasks.worker`: an error without a fresh `dlux_worker` heartbeat, because every DjangoLux task, scheduled backups included, runs there; a warning for failed runs), project Celery (`tasks.celery_deprecated`: warns while the project still has a Celery app, beat entries or `CELERY_BROKER_URL`; see [Task Runner](task-runner.md#moving-project-tasks-from-celery)), data access for the app's uid (`storage.mount_access`: an error when a non-root app cannot use part of its mounts; as root, informational, counting what uid 10001 would need; see [File permissions](deployment-configuration.md#file-permissions)) |
| `static` | `STATIC_ROOT` configured and populated, and holding every file the running DjangoLux ships in its `static/` folder (`static.collected`: an error naming the missing files, because pages that load them get 404s; `--apply` runs `collectstatic`) |
| `security` | `DEBUG`, placeholder `SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, proxy SSL header, secure cookies |
| `packages` | optional extras present |

`--group <name>` (repeatable) runs only the named groups.

`updater.runtime_volume` is skipped while inline updates are disabled. Otherwise it
reports the verdict the task worker recorded, because `web` (where the doctor
usually runs) holds the runtime volume read-only by design, and warns when the
worker has stopped reporting (see
[Who decides the runtime volume is usable](inline-updater.md#who-decides-the-runtime-volume-is-usable)).
The verdict is stored in the database, so the check is skipped while the
database is unreachable.

## When a dependency is down or hung

The doctor always returns a report, and a dead or paused service shows up once,
as its own error, rather than through every check that touches it.

- **Probes first.** Before Django's system checks and the report, the doctor
  probes the database and the cache. Each probe has `CHECK_TIMEOUT` (10 s).
- **Short socket timeouts.** For the run, the database and cache clients get a
  `PROBE_TIMEOUT` (5 s) socket timeout, whatever the project's `DATABASES` and
  `CACHES` say. It applies to `connect_timeout` on PostgreSQL and MySQL, and to
  the connect and read timeouts of `django_redis`, Django's `RedisCache` and
  `PyMemcacheCache`. Other backends keep their own.
- **A dead cache is bypassed.** When the cache probe fails, `cache.reachable` is
  an error with the probe's timing, and the rest of the run uses a dummy cache,
  so the other checks read the database directly.
- **A dead database skips what needs it.** `db.reachable` is the error; the
  other database checks, the email checks, `updater.runtime_volume` and
  `tasks.worker` are skipped and say why.
- **Every check has a deadline.** Each check runs in a worker thread with
  `CHECK_TIMEOUT`. One that does not answer is an error, "No answer within N s",
  and the report goes on. The whole pass has `RUN_TIMEOUT` (60 s); checks not
  started by then are skipped.
- **The command has a deadline.** `manage.py dlux_doctor` without `--apply`
  stops after `PROCESS_TIMEOUT` (100 s), under the 120 s `composer check --deep`
  waits. It prints a report with one `doctor.deadline` error (in the requested
  format) and exits 1; the `dlux_check` alias exits 0. `--apply` has no command
  deadline, so a migration or `collectstatic` is never cut off.
- **Config is built once.** Every translated string reads the merged system
  config, and outside a request nothing keeps it, so each read costs a database
  and a cache round-trip. During a run it is built once per pass.
- **Logs are shown once.** During a run, each distinct log record is printed
  once, and a logged exception is shortened to `Type: message` on the same line.

The limits are constants in `dlux/doctor.py`.

## Remediation safety tiers

`--apply` is deliberately not one blanket authorization:

| Tier | Meaning | Authorization |
| --- | --- | --- |
| `safe` | Idempotent, mutates no persistent data (`collectstatic`) | `--apply` |
| `stateful` | Mutates the database (`migrator`) | `--apply --allow-stateful` |
| `source` | Edits project source files | Not automated; reported as a remedy only |

`--apply` re-runs the full check pass afterwards and adds an `applied_fixes`
array to the report, so the caller sees the post-remediation state rather than
the state that triggered the fix.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | No errors (warnings allowed unless `--strict`) |
| 1 | At least one error, a warning under `--strict`, or the command deadline (`doctor.deadline`) |

## Adding a check

Register it in `dlux/doctor.py`; the command renders whatever the registry
contains.

```python
@check('services.thing', 'services', 'Thing responds')
def _check_thing(ctx):
    if not thing_ok():
        return fail('Thing did not respond.', 'Restart it.',
                    management_fix(['restart_thing'], 'Restart thing'))
    return ok('Thing responded.')
```

Use `ctx.db_available` and `ctx.cache_available` rather than probing again, and
return `skip()` when a precondition is absent so the result is not misread as a
pass. Give any network call of your own a timeout shorter than `CHECK_TIMEOUT`.
