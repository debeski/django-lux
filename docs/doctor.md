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

`dlux_check` remains as a deprecated back-compat alias for `dlux_doctor` (it
warns on stderr and delegates); prefer `dlux_doctor`.

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
- Reports carry no secret values, only key names, lengths, and booleans. They are
  safe to paste into an issue.

## Stack contract

`dlux/stack_contract.json` is the machine-readable spec of the expected Compose
stack: which services exist, which networks each joins, the sole published
ingress, where the Docker socket may be mounted (`ro`, socket-proxy only), the
`dlux_runtime` read/write split, each service's restart class, and the declared
volumes and env keys.

Every service carries an `org.dlux.restart` label — `safe` (stateless / owns no
in-flight operation: web, celery, smtp-relay, caddy) or `protected` (data store,
holds state, or manages its own lifecycle: db, redis, docker-socket-proxy,
composer-agent, composer-executor). Composer classifies restart safety from
these labels instead of a hardcoded name list; the `safe` set mirrors
`COMPOSER_AGENT_RESTART_SERVICES`, and a scaffold test keeps the two from
drifting. The contract is the single source of truth for the stack's shape —
`ComposeNetworkTopologyTests` asserts the scaffold satisfies it, and Composer's
`composer check` drift-diff checks a *deployed* `compose.yml` against it.

A `removed_services` map names services DjangoLux once shipped and has since
dropped (currently `db-backup` and `pgadmin`). Because `diff_attachments()`
ignores *extra* services (a project may run its own sidecars), Composer's check
uses `removed_services_present()` to tell an operator when a deployment still
runs one of these — so they know it is now safe to delete rather than being
silently ignored.

Composer fetches the contract version-correct by execing `python manage.py
dlux_stack_contract` in the app container: generated `manage.py` resolves the
runtime-active release before Django loads, so the contract always travels with
the dlux version actually running rather than whatever was baked into the image
(baking a static copy would go stale after an inline update — the same trap the
static-collection fix avoids). `load_contract()` stamps the report with
`dlux_version`; `diff_attachments()` is the shared, dependency-free comparison
both the tests and Composer use — it flags a contract service on the wrong
networks, a missing contract service, any service on an undeclared network, and
any service (contract or project-added) that bridges `frontend` and `egress` and
so collapses the ingress/egress isolation. `schema_version` is `1`; adding
services/keys is backwards-compatible, renaming a field bumps the version.

## Check groups

| Group | Covers |
| --- | --- |
| `settings` | INSTALLED_APPS and ordering, middleware presence and ordering, context processor, Crispy pack, `dlux_settings()` helper |
| `urls` | dlux URL mounting |
| `database` | reachability, unapplied migrations, `SystemSettings` row, setup completion |
| `services` | cache round-trip, email backend, SMTP reachability, Celery broker |
| `static` | `STATIC_ROOT` configured, populated, contains dlux assets |
| `security` | `DEBUG`, placeholder `SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, proxy SSL header, secure cookies |
| `packages` | optional extras present |

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
| 1 | At least one error, or a warning under `--strict` |

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

Use `ctx.db_available` rather than probing the database again, and return
`skip()` when a precondition is absent so the result is not misread as a pass.
