# Updater Consolidation — moving the executor to Composer

**Status:** **Step 1 complete** (Composer can perform inline DjangoLux updates
end to end). Steps 2-4 pending on the DjangoLux side. **Target: v1.8.0.**

Shipping in a minor release is only possible because the removal is staged: 1.8.0
stops *executing* updates but keeps every entry point alive as an inert shim, so a
deployed 1.7.x stack that upgrades into it does not crash. The hard deletions
(management commands, Compose service, CLI verb) happen in v1.9.0, after
`composer check --fix` has had a release to migrate stacks.

The goal is not "replace inline updates with image rebuilds". Inline updates stay
inline. The goal is to stop DjangoLux from *executing* its own update — fetching
from PyPI, verifying, staging and supervising the swap — and to let Composer,
which already performs exactly this class of work, do it on DjangoLux's behalf.

## Where things stand

`dlux/updater/` is 3,404 lines that split into three jobs:

| Part | Lines | Files |
| --- | --- | --- |
| Self-update **executor** | 989 | `runtime.py`, `supervisor.py`, `manifest.py`, `release_check.py`, `celery_control.py` |
| **Coordination** with Composer | 907 | `image_update.py`, `agent_bridge.py`, `control_link.py`, `health.py` |
| **State + UI + orchestration** | 1,508 | `service.py`, `__init__.py` |

The coordination row already works the way this proposal wants everything to
work: DjangoLux writes an intent file, Composer executes, DjangoLux observes.

```
/opt/dlux-runtime/state/
  image-update-request.json       <- dlux writes (intent)
  image-update-request.json.ack   <- composer writes (terminal token + exit code)
  deploy-status.json              <- composer writes (progress)
  image-available.json            <- composer writes (what is available)
  deploy-log.txt                  <- composer writes
```

Composer is already a first-class actor for DjangoLux operations. Its
`agent_protocol.py` validates `dlux.image_update` and `dlux.backup.create`
alongside `composer.restart` and `composer.recovery_deploy`;
`agent_installer.py` parses DjangoLux versions and enforces
`MINIMUM_DLUX_VERSION`; `watcher.py` tracks `baked_dlux_version`;
`version_gate.py` reads version labels off images; `health_monitor.py` and
`checkup.py` already decide whether a deployment came back healthy.

## Inline vs image is decided by the release, not by the executor

`release-manifest.json` carries `inline_safe`, and `assess_wheel()` refuses an
inline update only when a release declares `inline_safe: false` — "This release
requires a project image rebuild" — with an image-baseline floor so a deployment
several releases behind cannot skip an image-required release by jumping to a
later inline-safe one.

**Nothing in this proposal changes that.** The manifest keeps deciding. Moving
the executor changes *who fetches and stages*, not *what kind of update it is*.

## What moves, what stays

| Step | Today | After |
| --- | --- | --- |
| Poll PyPI for a release | dlux | **composer** |
| Download wheel, verify attestation | dlux | **composer** |
| Stage into `releases/<version>` | dlux | **composer** |
| Flip `active.json`, bump `generation` | dlux | **composer** |
| Restart app services | `dlux-updater` service | **composer** |
| Health-gate the result, roll back on failure | (not reliably possible) | **composer** |
| Supervisor picks the active release at start | baked dlux | unchanged |
| Update intent, state model, admin UI | dlux | unchanged |
| Read `active.json` for version display | dlux | unchanged |

The runtime volume and the `PYTHONPATH` swap **stay** — they are the inline
mechanism. Rollback is not lost either: it is "point `active.json` at the
previous release and restart", a property of the volume layout, not of who wrote
to it. `RuntimeStore` already carries `releases/`, `staging/`, `downloads/`,
`failed/`, `active.json` and `generation`.

### Why the guarantee gets stronger

Today DjangoLux supervises a swap of DjangoLux. When the new release fails to
start, the thing that would roll it back is the thing that did not start. That is
the shape of the known `dlux-updater` restart loop in project-archive.

Composer sits outside the container, already runs `health_monitor.py`, and can:

1. stage the release and verify it **before** touching `active.json`,
2. flip `active.json` and restart,
3. poll health, and
4. flip back to the previous release and restart again if health does not return.

That is a genuine rollback guarantee. It is not available to an in-container
updater at any amount of effort.

## What DjangoLux keeps — and why the supervisor cannot move

`python -m dlux.updater.supervisor` runs as the container entrypoint's child,
before any volume release is on `PYTHONPATH`, importing only the standard library
plus the bundled manifest. The baked dlux supervises the volume dlux. Composer
cannot replace it without owning the container entrypoint, so roughly 200 lines
stay in the package permanently. That is a bootstrap, not a leftover.

## New protocol surface

Add one action, mirroring `dlux.image_update` exactly:

```python
# composer/agent_protocol.py
elif action == "dlux.package_update":
    _require_payload_fields(payload, {"target_version", "backup_mode", "mode"})
    # mode: "apply" | "rollback"
    # target_version: PEP 440 string, or "" meaning "latest eligible"
    # backup_mode: data | full | skip   (same vocabulary as dlux.image_update)
```

and the matching file-drop pair for the local (non-panel) path:

```
package-update-request.json       <- dlux writes (intent)
package-update-request.json.ack   <- composer writes (terminal token + exit code)
deploy-status.json                <- reused, with a "kind": "package" discriminator
```

Both delivery paths that exist today are preserved: the local trigger file
watched by the agent, and control-panel commands through the agent outbox.

### The volume layout becomes a contract

Once Composer writes `releases/<version>/` and `active.json`, the layout is a
cross-repo interface and must stop being an implicit Python API.

There is already a precedent to copy exactly: `dlux/stack_contract.py` publishes
`stack-contract.json` as the machine-readable spec of the Compose stack, fetched
version-correct through the `dlux_stack_contract` management command so the
contract always travels with the dlux version actually running. Do the same:

- `dlux/runtime_contract.py` + `runtime-contract.json` — directory names,
  `active.json` schema, generation semantics, and the failed/staging rules.
- a `dlux_runtime_contract` management command,
- `schema_version`, additive changes only; a rename requires a bump,
- assertions on both sides: dlux tests the contract matches `RuntimeStore`;
  `composer check` diffs a deployed volume against the fetched contract.

## Decision: Composer is a hard requirement (2026-08-11)

Composer is a required companion to DjangoLux from v1.8.0 — a service in the
deployment on its latest stable image, in addition to being the deployer. The
project direction is to strip DjangoLux of outbound responsibilities entirely
and have Composer handle them from outside the container.

This settles the open question "does any active deployment run dlux without
Composer?" — it no longer gates anything. A deployment that runs without
Composer is expected to adopt it, and `composer check --fix` installs the
services (`install_composer_stack()` → the hardened trio, derived from the
project's own `web` service). `composer check` FAILs a DjangoLux stack that has
none, because it genuinely has no update path.

`DLUX_UPDATE_EXECUTOR="inline"` remains until 1.9.0 as a migration aid for a
deployment whose *Composer* is too old, not as a supported way to run without
Composer.

## Deletion list (v1.9.0 — NOT 1.8.0; see the upgrade hazard below)

From `dlux/`:

- `updater/release_check.py` — PyPI polling
- `updater/runtime.py` — write paths (staging, activation); the **read** side
  moves into the contract module
- `updater/celery_control.py`
- `updater/manifest.py` — remote wheel inspection and attestation; keep local
  manifest reading, which is how `dlux.__version__` is sourced
- the **inline branches** of `UpdateService._process_check` / `_process_apply` /
  `_process_rollback` / `_roll_forward` and their recovery paths, plus the
  `DLUX_UPDATE_EXECUTOR` switch that selects them. The methods themselves stay:
  they are what writes the hand-off.
- the `updater` optional dependency (`pypi-attestations`) — moves to Composer
- `dlux enable-updater` (CLI + `scaffold.enable_updater`)
- `tools/dlux_runtime_supervisor.py.tmpl` scaffold leftovers

Kept: `supervisor.py`, the state models, the admin UI, `image_update.py`,
`agent_bridge.py`, `control_link.py`, and `updates_enabled()` as the kill switch.

### The `dlux-updater` service IS retired — superseded 2026-08-11

The correction below was itself too narrow. It established that the service had
three jobs beyond executing updates, and concluded the service must therefore
stay. The right conclusion was that those jobs needed **reassigning**, not that
the service was permanent:

- runtime reconcile + migrations → Compose init containers (`pre_start`) on
  `celery`, which Compose runs and health-orders itself
- the queue drain and bridge writes → `dlux.tasks.dlux_state_tick` on Celery beat
- `web`'s gate → its entrypoint waits on `migrate --check`, so it depends on the
  migrations rather than on the service that applies them

New scaffolds no longer emit the service; `composer check --fix` retires it from
existing stacks, gated on Compose >= 5.3.0 and DjangoLux >= 1.8.0. The original
analysis is kept below because the constraints it identified are exactly what the
reassignment had to satisfy.

### Why it looked permanent — the original analysis

An earlier draft of this list had the Compose service removed at v1.9.0. That is
wrong, and `composer check --fix` must never propose it. Verified against
`compose.yml.tmpl`:

```
command: ["python", "-m", "dlux.updater.supervisor", "--no-watch", "--", "bash", "-c",
          "python manage.py dlux_reconcile; python manage.py migrator && exec python manage.py dlux_update_worker"]
```

and on `web`:

```
depends_on:
  dlux-updater:
    condition: service_healthy
```

So the service has three jobs beyond executing updates: it reconciles runtime
state, it **applies migrations**, and `web` gates its own start on its health.
`dlux_update_worker` is also the only caller of `UpdateService.process_next()`
— the queue drainer that writes the intent file Composer acts on. Removing the
service would delete the migration gate and the hand-off producer, not just the
executor.

What v1.9.0 removes lives *inside* the service. The block, its healthcheck and
its `org.dlux.restart: protected` label all stay.

### Model fields that go stale

`DluxUpdateState.active_wheel_url/sha256`, `previous_wheel_url/sha256`,
`latest_wheel_url/sha256` and `DluxUpdateRun.wheel_url/wheel_sha256` describe an
artefact DjangoLux no longer fetches. Keep the columns for run history in the
first release (a migration that drops them is not backward-compatible and would
make the release `inline_safe: false`), stop writing them, and drop them in a
later image-required release.

## Open questions — decide before implementing

1. **Composer-less deployments.** Any deployment running DjangoLux without
   Composer loses in-app updates entirely. The scaffold emits a `composer-agent`,
   so this is believed to be empty, but it should be confirmed across the six
   active projects before committing.
2. **Attestation trust boundary.** Verification moves to Composer, which becomes
   the only component that trusts PyPI. That is the intended outcome — DjangoLux
   ends up with no outbound network egress — but it concentrates the trust
   decision in one place and should be reviewed as such.
3. **Kill switch ownership.** `updates_enabled()` currently gates queueing. Does
   Composer also honour a per-project "no automatic updates" flag, and where does
   it read it from?
4. **Mid-flight deployments.** A box upgrading *into* v1.9.0 may have a staged
   release, an active run row, and a running `dlux-updater`. The upgrade path has
   to drain or fail those runs, stop the service, and hand the volume to
   Composer.

## The upgrade hazard that shapes the whole plan

A deployed 1.7.x stack updates itself **using the executor being removed**. The
last self-update it performs is the one that lands 1.8.0 — and its `compose.yml`
is project-owned, not shipped by dlux. That file contains:

```yaml
dlux-updater:
  command: ["python", "-m", "dlux.updater.supervisor", "--no-watch", "--",
            "bash", "-c", "python manage.py dlux_reconcile; python manage.py migrator && exec python manage.py dlux_update_worker"]
  restart: always
  labels:
    org.dlux.restart: "protected"
```

If 1.8.0 deletes `dlux_update_worker`, `dlux_reconcile` or the supervisor's
worker mode, that service dies on start and `restart: always` turns it into a
crash loop — on a `protected` service, which is the hardest kind to clear. That
is the same failure project-archive is already in.

**Therefore 1.8.0 deletes nothing that a deployed compose file names.** The
commands and the supervisor stay; they become inert. Deletion waits for v1.9.0,
after stacks have been migrated.

### The migration tool already exists

Composer's `check --fix` already removes obsolete Compose service definitions
while preserving named volumes (`OBSOLETE_SERVICES` in `stack_cleanup.py`,
surfaced by `_check_removed_services`), and it already carries dlux-updater
migration logic gated on the packaged-runtime floor
(`needs_updater_migration`, `DLUX_PACKAGED_RUNTIME_MIN`). Adding `dlux-updater`
to that set — once the runtime floor is 1.8.0 — is the migration.

## Sequencing

Each step is independently shippable and leaves a working system.

**Step 1 — Composer gains the ability** (composer release, dlux untouched)
- ~~`dlux.package_update` action in `agent_protocol.py`~~ **DONE** — typed and
  bounded payload (`mode` apply|rollback with no default, pattern-checked
  `target_version`, `backup_mode`), registered in `REMOTE_ACTIONS` and wired into
  the agent's bridge dispatch and result collection alongside the other dlux
  actions. 5 tests; composer suite 336 green.
- ~~Volume mechanics~~ **DONE** — `composer/dlux_runtime.py`: stage into
  `releases/<version>/`, verify against the wheel's own manifest, atomically flip
  `active.json`, bump `generation`, quarantine a bad release, restore the
  previous one (or the image copy). Verification runs before the pointer moves.
  17 tests, including an interop test asserting dlux's `RuntimeStore` reads back
  what Composer wrote. `composer-executor` already mounts the volume `rw`, so no
  Compose change is required.
- ~~The fetch half~~ **DONE** — `composer/dlux_release_source.py`: simple-index
  read, candidate selection (pinned or newest stable), Trusted Publisher
  attestation, SHA-256 against the index fragment, in-wheel manifest check,
  `inline_safe` refusal, and traversal-safe unpack. Trust decisions mirrored from
  `dlux/updater/manifest.py`; **fail-closed** — a missing verifier refuses rather
  than passes. 20 tests. End-to-end verified: index → verify → download → assess →
  unpack → stage → activate → rollback.
- ~~Health-gated apply~~ **DONE** — `composer/dlux_package_update.py`:
  fetch → stage → activate → restart → health-check, with rollback + quarantine
  on failure and a distinct `critical` outcome when the rollback is also
  unhealthy. `restart`/`health_check` are injected; the executor passes
  `composer restart` and `HealthMonitorMixin.monitor_health`. 12 tests.
- ~~Plumbing~~ **DONE** — `composer dlux-update` (apply|rollback, `--version`,
  `--dry-run`, `--status-file`, exit 3 = needs a human) plus a second trigger file
  `package-update-request.json` watched by the executor and the watcher beside the
  image trigger, acked by token. The agent observes the package ack under its own
  marker. 13 tests.
- ~~`composer check` reporting~~ **DONE** — flags a stack still running the
  in-container executor, gated on the image shipping 1.8.0+ so a stack with no
  alternative yet is not told to remove its only update path. Report-only; the
  removal is step 4.

**Step 2 — dlux publishes the runtime contract** (1.8.0) — **DONE**
- `dlux/runtime_contract.py` + `runtime_contract.json` +
  `manage.py dlux_runtime_contract`, copying `stack_contract.py` exactly
  (version stamped at load time, never stored in the file).
- Documents the directory layout, the `active.json` schema and rules, generation
  semantics, and a writer for every state file.
- Asserted against `RuntimeStore` in both directions — a directory the contract
  names must exist, and a directory the store creates must be documented — plus
  `diff_layout()` / `diff_active()` and the management command. 15 tests.
- Composer asserts its own writer against the same document (4 tests), including
  that it writes no state file the contract does not assign to it.
- **TODO** — `composer check` diffs a *deployed* volume against the fetched
  contract (the consumer side; the contract and both conformance checks exist).

**Step 3 — dlux stops executing** (1.8.0, the behavioural change) — **DONE**
- ~~apply/rollback write an intent~~ **DONE** — `_process_apply` and
  `_process_rollback` hand off through `dlux/updater/package_request.py` unless
  `DLUX_UPDATE_EXECUTOR="inline"`. Verified across both repos: dlux writes the
  request, Composer's `WatchRuntime` picks it up and runs
  `composer dlux-update apply --version …`, dlux reads the ack back.
- ~~`_process_check` reads Composer's availability document~~ **DONE** —
  `_process_check_via_composer` reads `state/package-available.json`. Composer
  publishes it from `dlux-update --check` on the existing check cadence and
  immediately after a swap. An absent report is *unknown*, never "up to date".
  This was the last network egress in the package.
- `dlux_update_worker` and `dlux_reconcile` keep existing and keep running; they
  become intent-drainers and state-reconcilers with no network access.
- The supervisor is unchanged.
- ~~`dlux enable-updater` prints a deprecation notice~~ **DONE** — it prints the
  migration path and removal release, on the command and in `--help`. It is not
  a no-op: it still works, because `inline` is still a supported executor
  until 1.9.0.
- The scaffold keeps the `dlux-updater` service (see the correction above) and
  documents its narrowed role in the generated `compose.yml`.

**Step 4 — migrate stacks** (ready at the 1.8.0 release) — **DONE**
- ~~Add `dlux-updater` to composer's obsolete-service set~~ **Dropped, and the
  reasoning was wrong** — the service is not obsolete at any planned release
  (see the correction above). `remove_obsolete_service_blocks()` did gain an
  explicit `services` argument so a *conditional* removal is expressible, but
  nothing uses it for `dlux-updater`.
- `composer check` instead verifies readiness: a composer-side loop exists
  (`composer-executor`, `composer-agent` or the legacy `composer-updater`) and
  mounts `dlux_runtime`. A loop without that mount is a FAIL — it would see no
  requests and publish no availability, silently.
- Nothing in the compose file has to change for the switch: the package trigger
  defaults to `package-update-request.json` beside the image trigger, and every
  composer loop template already mounts the volume `rw`. Running `check --fix`
  before the 1.8.0 upgrade is a safe no-op; running it after is too.
- The migrations that *do* matter are the pre-existing ones — legacy
  `composer-updater` → `composer-agent`, and `composer-agent` → executor
  topology. Both already run under `--fix`.
- **project-archive first** — its updater is already broken, so it is the
  lowest-risk migration and the clearest proof.

**Step 5 — delete** (v1.9.0)
- The deletion list above, plus `dlux_update_worker`, `dlux_reconcile`, the
  `updater` optional dependency, and the wheel columns.
- Record the removed CLI verb and service in `docs/deprecation-countdown.md`.

## What this buys

- DjangoLux becomes network-off: no PyPI polling, no wheel download, no
  attestation verification, no code fetched and executed in-process.
- One service disappears from every deployment, along with its restart loop and
  its `protected` restart semantics.
- Ownership stops being circular: Composer owns the deployment lifecycle,
  DjangoLux owns the application and states intent.
- Rollback becomes health-gated and externally supervised, which it cannot be
  while the updater lives inside the thing being updated.
