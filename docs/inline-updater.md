# Verified Inline Updates

Generated DjangoLux Compose projects use Composer for inline package updates. DjangoLux decides whether an update is allowed and records intent; Composer fetches, verifies, stages, activates, health-gates, and rolls back from outside the application container. The project image is always the fallback runtime.

## Requirements

This architecture applies only to generated Compose stacks. It requires:

- Docker Compose 5.3.0+ for `pre_start` init containers;
- a running Composer service topology (`composer-agent`, `composer-executor`, and `docker-socket-proxy`), at Composer 1.3.10 or newer; and
- a writable `dlux_runtime` volume for the state owner.

Composer 1.3.10 is the first version that can activate a schema-2 release: earlier ones read `inline_safe` straight off the wheel's manifest, which schema 2 derives and never publishes, so the install failed after the release had been fetched, verified and staged. It is also the version in which the agent stages the wheel and the executor swaps it — the executor sits on an internal network and can never fetch one itself. Release manifests from v1.8.8 declare that floor, so an older Composer reports the requirement instead of attempting an install that cannot finish. Update it with `./start.sh update-self`, then `./start.sh agent-update`.

Ordinary Django installations and non-Compose deployments run without this update path. They remain fully usable; they simply do not receive Composer-driven inline updates. For an existing generated stack, run `./start.sh check` and then review `./start.sh check --fix` if Composer reports missing infrastructure.

## Boot and ownership

The v1.8.0 scaffold does not run `dlux-updater`. Instead, Compose runs two `celery` `pre_start` steps:

1. `dlux_reconcile` selects a safe runtime release; and
2. `migrator` applies migrations and collects static assets under the active runtime release.

They live on `celery` because the steps inherit its writable runtime mount. They set `DLUX_BOOT_GATE=off` because the inherited entrypoint otherwise waits for the very migrations the step is about to apply. `web` independently waits on `migrate --check`, which also protects restart-policy and host-reboot paths where Compose skips `pre_start`.

Celery Beat writes DjangoLux's small state/intent tick. Composer performs all network and container operations. This separation means a failed candidate can be rolled back by a process that is not being replaced.

### What finishes a handed-off run

`_handoff_to_composer` writes `package-update-request.json` and moves the run to
`applying`. That is the end of DjangoLux's part: nothing in the web or worker
process can observe what Composer does next. The Celery tick's
`tick_package_update()` reads the answer back from
`package-update-request.json.ack` — the token and the exit code — reconciles the
versions the Options card reports, and finishes the run: completed, rolled back
(taken from Composer's own result in `deploy-status.json`), or failed with a
"needs an operator" message for Composer's exit 3, which means the rollback was
not healthy either.

A hand-off Composer never acknowledges is failed after 30 minutes. Composer's own
work is bounded — download, swap, restart, health wait — so past that nothing is
coming, and a run left active would block every later update: `queue_run()`
refuses to queue one while another is active. The release may still be active in
that case; the Options card reports what is actually installed.

Before 1.8.9 none of this ran. The hand-off raised `AttributeError` before the
request file was written, so an apply ended at "Started apply request." and
Composer was never told anything.

### What refreshes the reported versions

`dlux_reconcile` runs before migrations and only repairs the runtime pointer on the volume — it never writes the database. The database side is `UpdateService.reconcile()`, and since 1.8.6 the Celery state tick runs it once per worker process (so, after `migrator`) and again whenever the recorded baked version stops matching the installed package.

Between 1.8.0 and 1.8.5 nothing called it, because the `dlux-updater` startup that used to was retired without carrying the call over. On a stack upgraded in that window the Options card reports the versions recorded before the upgrade, and its rollback button offers a release that is no longer installed — do not press it. Upgrading to 1.8.6 corrects the row on the first tick after the worker starts.

### Who decides the runtime volume is usable

Only the process that writes the volume. `web` may mount `dlux_runtime` read-only — that is the intended arrangement — so a writability probe in `web` describes the web mount, not the mount an update runs against.

Celery records its own verdict on the update state row each tick (`worker_seen_at`, `worker_volume_problem`). The update panel, the queue guard and `updater.runtime_volume` in Deployment Doctor all read that recorded verdict; `web` never probes for itself. Until a writer has reported at all — a fresh install, a single-process deployment, a management command on a laptop — the calling process's own probe still stands in, because it is the only evidence available.

A writer that reported and then went quiet for more than ten minutes is treated as gone: queueing is refused with that reason rather than accepting a run nothing would drain, and the state exposes `worker_stale`.

Before 1.8.6 the guard probed locally in every process, so a read-only `web` mount disabled the update card and refused manual checks on a healthy stack. Granting `web` write access worked around that; it is no longer needed.

## Update handoff

After superuser approval, DjangoLux writes an update request on `dlux_runtime`. Composer publishes its acknowledgement and the latest installable release metadata. An absent availability document is **unknown**, never "up to date".

Release eligibility remains strict. Composer honors the release manifest's schema, migration effect, rollback compatibility, service requirements, baked image floor, and `install.inline` permission. An inline-forbidden release requires a normal project-image rebuild; Composer execution does not make a database-destructive migration safe to apply from a volume.

Update admission serializes through the DjangoLux state row. An image update and an inline update cannot be admitted concurrently. When a pre-update backup is requested, DjangoLux must finish it before the update intent is written.

## Recovery and rollback

Rollback selects the prior code/static release; it does not reverse migrations or restore database data. Reconcile falls back to the baked package when an active runtime release is missing, corrupt, or not newer than the image. Keep the runtime volume: it holds the active pointer, release installations, maintenance state, and Composer/DjangoLux handoff records.

Use [Deployment Doctor](doctor.md) for diagnostics and [Composer Agent Integration](composer-agent.md) for the service/network boundary.

## Compatibility window

`DLUX_UPDATE_EXECUTOR="inline"` and `python -m dlux enable-updater` are deprecated migration aids, scheduled for removal in v1.9.0. They are not a supported way to avoid Composer. New deployments should use the Composer topology and no longer declare `dlux-updater`.
