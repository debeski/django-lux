# Updater Consolidation Status

**Completed in v1.8.0:** Composer is the external executor for generated inline updates. DjangoLux owns update policy, locking, backup admission, intent, and durable application state; Composer owns network fetch/verification, staging, activation, health-gating, and rollback.

The retired `dlux-updater` Compose service is no longer emitted by the scaffold:

- runtime reconciliation and migrations run as `celery` Compose `pre_start` steps;
- `web` waits on `migrate --check` for restart/reboot safety; and
- Celery Beat performs DjangoLux's small state/intent tick.

Existing generated projects use `./start.sh check` to inspect the migration and `./start.sh check --fix` to apply recognized repairs after review. Compose 5.3.0+ is required for the init-container hooks.

The legacy in-container executor remains only through the v1.8 compatibility window and is removed in v1.9.0. See [Verified Inline Updates](inline-updater.md) for the supported runtime contract.
