# Verified Inline Updates

Generated DjangoLux Compose projects use Composer for inline package updates. DjangoLux decides whether an update is allowed and records intent; Composer fetches, verifies, stages, activates, health-gates, and rolls back from outside the application container. The project image is always the fallback runtime.

## Requirements

This architecture applies only to generated Compose stacks. It requires:

- Docker Compose 5.3.0+ for `pre_start` init containers;
- a running Composer service topology (`composer-agent`, `composer-executor`, and `docker-socket-proxy`); and
- a writable `dlux_runtime` volume for the state owner.

Ordinary Django installations and non-Compose deployments run without this update path. They remain fully usable; they simply do not receive Composer-driven inline updates. For an existing generated stack, run `./start.sh check` and then review `./start.sh check --fix` if Composer reports missing infrastructure.

## Boot and ownership

The v1.8.0 scaffold does not run `dlux-updater`. Instead, Compose runs two `celery` `pre_start` steps:

1. `dlux_reconcile` selects a safe runtime release; and
2. `migrator` applies migrations and collects static assets under the active runtime release.

They live on `celery` because the steps inherit its writable runtime mount. They set `DLUX_BOOT_GATE=off` because the inherited entrypoint otherwise waits for the very migrations the step is about to apply. `web` independently waits on `migrate --check`, which also protects restart-policy and host-reboot paths where Compose skips `pre_start`.

Celery Beat writes DjangoLux's small state/intent tick. Composer performs all network and container operations. This separation means a failed candidate can be rolled back by a process that is not being replaced.

## Update handoff

After superuser approval, DjangoLux writes an update request on `dlux_runtime`. Composer publishes its acknowledgement and the latest installable release metadata. An absent availability document is **unknown**, never "up to date".

Release eligibility remains strict. Composer honors the release manifest's schema, migration effect, rollback compatibility, service requirements, baked image floor, and `install.inline` permission. An inline-forbidden release requires a normal project-image rebuild; Composer execution does not make a database-destructive migration safe to apply from a volume.

Update admission serializes through the DjangoLux state row. An image update and an inline update cannot be admitted concurrently. When a pre-update backup is requested, DjangoLux must finish it before the update intent is written.

## Recovery and rollback

Rollback selects the prior code/static release; it does not reverse migrations or restore database data. Reconcile falls back to the baked package when an active runtime release is missing, corrupt, or not newer than the image. Keep the runtime volume: it holds the active pointer, release installations, maintenance state, and Composer/DjangoLux handoff records.

Use [Deployment Doctor](doctor.md) for diagnostics and [Composer Agent Integration](composer-agent.md) for the service/network boundary.

## Compatibility window

`DLUX_UPDATE_EXECUTOR="inline"` and `python -m dlux enable-updater` are deprecated migration aids, scheduled for removal in v1.9.0. They are not a supported way to avoid Composer. New deployments should use the Composer topology and no longer declare `dlux-updater`.
