# Verified Inline Updater

The DjangoLux inline updater is available only to scaffold-generated Docker Compose projects. DjangoLux remains an in-process Django app; the updater changes where an approved newer wheel is loaded from. The project image remains the fallback runtime.

## Deployment Architecture

Generated projects define a persistent `dlux_runtime` volume:

- `releases/<version>/` contains retained `pip --target` wheel installations.
- `state/active.json` atomically selects either the image package or one volume release.
- `state/generation` tells the generated supervisor to gracefully restart Gunicorn and Celery.
- `state/maintenance` tells nginx to serve the generated static HTTP 503 page.
- `state/updater-heartbeat` is the updater service health signal.

The `dlux-updater` service uses the same `WEB_IMAGE` as `web` and `celery`. It mounts `dlux_runtime`, static files, media-backed system backups, and logs read/write. It joins the internal database/Redis network and the dedicated `dlux_update_egress` bridge, publishes no ports, and never mounts the Docker socket. `web`, `celery`, and nginx mount the runtime volume read-only. Web and Celery wait for the updater health check so the worker can reconstruct a missing volume from `DluxUpdateState` before application processes start.

The project-owned `tools/dlux_runtime_supervisor.py` uses only the Python
standard library. Before prepending a selected release directory to the child
`PYTHONPATH`, it records the image (baked) version as `DLUX_BAKED_VERSION`; this
keeps the immutable rollback target distinct from the active imported package
after container recreation. The baked version is derived from `dlux.__version__`
(the running code's release manifest — a stdlib-only import that triggers no
Django setup), falling back to the installed distribution metadata only when
`dlux` cannot be imported. Reading it from the manifest means a bind-mounted
source checkout (where installed-package metadata is absent or stale) bakes the
correct version, and unifies the source of truth with `get_baked_version()`. It
reads `active.json`, falls back to the baked package for missing/corrupt state,
forwards termination signals, and bounds graceful shutdown before restarting on a
generation change. (The supervisor lives in the generated project's `tools/`, so
existing deployments adopt this on the next image rebuild / `enable-updater`
re-copy.)

If an empty/corrupt volume cannot be reconstructed from the database's verified active-release metadata, the updater writes `state/degraded`, preserves that metadata for retry, and fails its bootstrap health check. Web and Celery therefore do not start against a silently downgraded package. A successful reconstruction (or the updater container's baked migrator repairing an already-restored pointer/static tree) clears and archives the degraded marker.

Reconcile also has two self-healing fallbacks so a runtime never wedges
permanently. (1) When the recorded active release cannot be served **and cannot
be rebuilt** — there is no staged volume release on disk *and* no downloadable
wheel URL/digest (an image- or mount-activated release, a backward image move, or
a wiped runtime volume) — reconcile reverts to the baked image (re-activating it,
clearing stale active/previous/latest metadata, bumping the generation, and
restarting the worker) instead of hard-failing while chasing a wheel that never
existed. (2) Once the runtime has converged back onto the baked image
(`active == baked`), a lingering degraded flag from a transient failure is
cleared, so a one-off degrade self-heals on the next reconcile. A degrade tied to
a **present volume release** (for example a failed-rollback target that is still
staged) deliberately stays sticky for operator review.

When an operator deliberately rebuilds the project image with a newer Dlux pin
for an unsafe, dependency-changing, or bootstrap-changing release, the updater
detects that the baked image version is newer than the persistent volume
selection. It atomically activates the image, clears stale inline-candidate and
pointer-rollback metadata, and restarts once so the new image's migration
bootstrap runs. Retained volume releases are not deleted.

Generated Compose projects set:

```text
DLUX_INLINE_UPDATES_ENABLED=True
DLUX_UPDATE_CHECK_INTERVAL=86400
DLUX_UPDATE_RUNTIME_ROOT=/opt/dlux-runtime
```

Non-generated deployments remain disabled by default. The update source is fixed in code to the official stable `django-lux` project on PyPI; custom indexes, SSO companion packages, bare-metal installs, and blue/green orchestration are not supported in v1.
Generated requirements use `django-lux[updater]` so PyPI attestation tooling is installed only where this deployment feature is enabled.

## Existing Generated Projects

Version `1.2.2` introduced the updater infrastructure, but its wheel-download
cache prefixed the SHA-256 digest to the wheel basename. Pip rejects that renamed
file before staging, so neither v1.2.3 nor another candidate can repair a
v1.2.2/v1.2.3 image inline. Version `1.2.4` repaired wheel staging, but its
post-generation health verifier probes Celery only once and can race a normal
worker restart. That false failure can also race automatic rollback and leave
maintenance/degraded state behind. Version `1.2.7` is the current repaired
bootstrap baseline and deliberately declares `inline_safe=false`. Existing
deployments must update their exact requirement pin and perform one normal
rebuild/redeploy:

```text
django-lux[updater]==1.2.7
```

```sh
# Production/default Compose image
docker build -t "${WEB_IMAGE:-your-project:latest}" .
docker compose up -d --force-recreate dlux-updater web celery smtp-relay nginx

# Or, when running the generated development override
docker compose -f compose.yml -f compose.dev.yml build
docker compose -f compose.yml -f compose.dev.yml up -d --force-recreate dlux-updater web celery smtp-relay nginx
```

Projects that have not enabled the Compose infrastructure yet should install the
repaired baseline through that rebuild, then run the bootstrap from the generated
project root:

```sh
python -m dlux enable-updater          # dry run
python -m dlux enable-updater --apply  # guarded apply
```

The command accepts only recognized generated layouts. It refuses ambiguous/custom Compose structures, makes timestamped copies of every modified file under `.xpose/dlux-updater-bootstrap/`, applies idempotent marked changes, updates the exact `django-lux` requirements pin to the repaired bootstrap version, and runs `docker compose config`. It prints the single image rebuild/redeploy command required to activate the infrastructure. Re-running the command is safe.

The repaired bootstrap itself is installed by that rebuild. Version v1.2.5 is
the first manifest-approved release that can be applied inline through the
corrected staging path.

## Admin Operation

System Info at `/sys/options/` shows the installed version, latest verified stable version, last check, compatibility result, and any durable run status. Global Staff can read this data. Only superusers can check, apply, or roll back.

The worker checks daily after startup jitter. Nothing is installed automatically. A superuser can:

1. Select **Check for updates**.
2. Select **Review and update** only when the release passes every safety gate.
3. Review the escaped release summary, compatibility result, target version, and maintenance notice.
4. Confirm with the current password.

Apply and rollback are CSRF-protected POST operations and create audit events.
After password confirmation, the review modal remains open as a progress view
with the current phase, percentage meter, and bounded durable run log. It
disables dismissal while the run is active and keeps terminal failure details
visible. Run progress is stored in `DluxUpdateRun`, so closing the browser or
losing the connection during a restart does not lose the result; reopening the
page reconnects to an active apply/rollback run. A successful update exposes
**Roll back to previous version**. Successful completion is a transient status;
an idle card does not repeat the latest historical check as an active/completed
operation, while actionable failure details remain visible.

## Release Verification Contract

Every wheel must contain `dlux/release-manifest.json` with schema version 1, the exact wheel version, `inline_safe`, minimum updater schema, migration policy, summary, and the official GitHub release URL. Discovery uses PyPI's Simple JSON API and excludes prereleases, development releases, yanked files, non-wheel files, and anything other than `py3-none-any`.

Before an Update button is allowed, the worker verifies:

- the official PyPI URL/redirect allowlist and SHA-256 digest;
- the PyPI Trusted Publisher attestation for repository `debeski/django-lux`
  and configured workflow `.github/workflows/release.yml` (serialized by
  PyPI's integrity API as the canonical basename `release.yml`);
- manifest schema/version and `inline_safe=true`;
- updater-schema and Python-version compatibility;
- an unchanged DjangoLux dependency contract, with every requirement already installed and satisfied;
- candidate `check`, `dlux_check`, and migration-plan subprocesses with the staged release first on `PYTHONPATH`.

Any failed gate displays **Project image rebuild required** and does not expose the inline Update action. Release CI permits `inline_safe=true` only when Dlux migration changes contain `CreateModel`, `AddIndex`, or nullable/defaulted `AddField` operations.

## Apply and Rollback

Apply re-fetches and re-verifies the wheel, installs it to isolated staging with `pip --target --no-deps`, completes and verifies a **data-only** Dlux system backup tagged with the `update` trigger, enables maintenance, runs candidate migrations and `collectstatic`, atomically switches the pointer, increments the generation, and verifies `/health/`, the active Dlux version in web, and the version reported by a live Celery worker. Web and Celery readiness/version probes retry within one bounded 120-second handshake so supervisor startup latency is not treated as failure. The review modal states this blocking backup guarantee; backup failure aborts before maintenance rather than merely warning the operator to create one manually.

The pre-update backup excludes media blobs (`include_media=False`): it captures the database rows and migration state but not uploaded files, because an inline code/schema update never alters media on disk. This keeps the backup fast even on media-heavy deployments (a full media copy could take many minutes, defeating the point of a quick inline update). Restoring a data-only `.dlb` replaces the database and leaves existing media untouched, since the restore only rewrites the files its manifest lists. Manual and scheduled backups remain full (media + data).

Before the pointer switch, failure leaves the existing release active and clears maintenance. After the switch, failure restores the previous code pointer, recollects its static assets, increments the generation again, and verifies health. If the updater container or host stops after claiming a run, the next worker terminalizes that interrupted run: it recollects current static assets before clearing pre-switch maintenance, or restores the recorded source pointer/static assets and increments generation after a post-switch apply interruption. Failed interruption recovery persists degraded state and leaves nginx maintenance enabled. Old downloads, releases, failed staging trees, backups, and bounded run logs are retained.

Rollback uses the same password, backup, preflight, maintenance, static, pointer, restart, and health pipeline. It does not reverse migrations and the updater never automatically restores the database. Inline-safe migrations must remain compatible with the immediately previous release; the pre-operation `.dlb` backup remains available for manual disaster recovery under the configured `backup_config` retention policy. Rotation runs only after the new backup completes and explicitly protects that new row/file during the pass.

Updater pointer/run rows are deployment bookkeeping and are excluded from `.dlb` payloads. Restoring application data into another environment therefore starts from that environment's baked Dlux release instead of importing a stale runtime-volume pointer.

When a failed pre-v1.2.7 health race already left a deployment degraded with a
maintenance marker, rebuilding on v1.2.7 is the recovery path: newer-image
reconciliation selects the baked release and clears both markers before the
worker becomes ready. No manual database or runtime-volume edit is required.
