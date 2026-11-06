# Verified Inline Updates

Generated DjangoLux Compose projects use Composer for inline package updates.
DjangoLux decides whether an update is allowed and records intent; Composer
fetches, verifies, stages, activates, health-gates and rolls back from outside the
application container. The project image is always the fallback runtime.

## Requirements

This architecture applies only to generated Compose stacks. It requires:

- Docker Compose 5.3.0 or later, for the `pre_start` init containers (the stack
  contract records it as `minimum_compose_version`);
- the Composer service topology (`composer-agent`, `composer-executor` and
  `docker-socket-proxy`) running as services in the deployment, at or above the
  Composer version the running release declares in `requires.services.composer`;
  and
- a writable `dlux_runtime` volume for the state owner, `celery`.

Each release manifest declares the Composer it needs. A Composer below the floor
of the release it is offered reports that requirement instead of attempting an
install it cannot finish, and the Updates card names the floor when the resident
Composer is older (see [Deployment operations](#deployment-operations)). Update it
on the host with `./start.sh self update`, then `./start.sh agent update`.

Ordinary Django installations and non-Compose deployments run without this update
path. They remain fully usable; they simply receive no Composer-driven inline
updates, and `DLUX_INLINE_UPDATES_ENABLED` defaults to off for them.

For an existing generated stack, run `./start.sh check`, review what it reports,
and apply the recognized repairs with `./start.sh check --fix` when Composer
reports missing infrastructure: it installs the Composer services and migrates
obsolete `dlux-updater` wiring. There is no in-container executor:
`DLUX_UPDATE_EXECUTOR` is ignored (see
[Deprecation Countdown](deprecation-countdown.md#in-container-update-executor)),
and a deployment without Composer gets a card that reports it rather than a
fallback.

## Deployment architecture

### Who does what

| DjangoLux (`web` and `celery`) | Composer (`composer-agent` and `composer-executor`) |
| --- | --- |
| Update policy: release channel, skip list, check interval, and whether an offered release is admitted | Network fetch and verification of releases from PyPI, including whether a release is inline-safe |
| Locking: one operation at a time, serialized through the `DluxUpdateState` row | Staging: the agent downloads and stages the wheel |
| Backup admission: the pre-update backup finishes before any intent is written | Activation: the executor swaps the release on `dlux_runtime` |
| Intent: request files on the runtime volume | Restart and health-gating of the services that load DjangoLux |
| Durable application state: runs, versions, release notes, audit events | Rollback when the candidate does not come back healthy |

The executor sits on the internal `docker_proxy` network only and never fetches a
wheel itself; the agent, which has egress, stages it. Because Composer performs
all network and container operations from outside the application container, a
failed candidate is rolled back by a process that is not being replaced.

DjangoLux's side runs in Celery. Beat runs `dlux.tasks.dlux_state_tick` every five
seconds: a small write-side loop that publishes state and intent on the runtime
volume and reads Composer's answers back. `web` mounts `dlux_runtime` read-only
and records an administrator's intent in the database; `celery` mounts it
read-write and is the only project-side writer. The services, networks and
privileges are described in
[Composer Agent Integration](composer-agent.md#generated-topology).

The scaffold has no `dlux-updater` service. Do not add it back to a stack.

### Boot and ownership

Compose runs two `pre_start` steps on `celery`, each in its own ephemeral
container that must exit 0 before `celery` starts:

1. `dlux_reconcile` repairs the runtime pointer. When a volume release is not
   strictly newer than the release baked into the image, it points the runtime
   back at the image. It touches only the volume, never the database, and always
   exits 0, so it cannot block startup.
2. `migrator` applies migrations and collects static assets.

Both run under the runtime supervisor (`python -m dlux.updater.supervisor
--no-watch`), so they use the same runtime-active release gunicorn serves
templates from; run raw, `collectstatic` would collect from the baked image. They
live on `celery` because a step inherits its service's mounts, and `web`'s runtime
mount is read-only. Composer passes a deploy's migrator flags to the second step
through `DLUX_MIGRATOR_FLAGS`.

The entrypoint's boot gate, `DLUX_BOOT_GATE`, covers the paths where Compose skips
`pre_start`: a container restarting under its restart policy, which is what a host
reboot does.

| Value | Used by | Behaviour |
| --- | --- | --- |
| `off` | the `pre_start` steps | No gate. A step inherits the entrypoint and would otherwise wait for the migrations it applies. |
| `apply` | `celery` | When `migrate --check` finds unapplied migrations, runs `dlux_reconcile` and `migrate` itself, and refuses to start if they fail. |
| `on` (default) | `web` and every other service | Waits until `migrate --check` passes; never applies. |

`web` does not depend on `celery`; it waits on the migrations themselves, so a sick
worker delays nothing once they are applied.

### Who decides the runtime volume is usable

Only the process that writes the volume. `web` mounts `dlux_runtime` read-only,
which is the intended arrangement, so a writability probe in `web` describes the
web mount, not the mount an update runs against. Do not grant `web` write access.

Celery records its own verdict on the update state row each tick
(`worker_seen_at`, `worker_volume_problem`, refreshed at most once a minute while
unchanged). The update panel, the queue guard and the `updater.runtime_volume`
check in [Deployment Doctor](doctor.md) all read that recorded verdict; `web` never
probes for itself. Until a writer has reported at all (a fresh install, a
single-process deployment, a management command on a laptop) the calling
process's own probe stands in, because it is the only evidence available.

A writer that reported and then went quiet for more than ten minutes is treated as
gone: queueing an update or an operation is refused with that reason rather than
accepting a run nothing would drain, and the state exposes `worker_stale`.

### What refreshes the reported versions

`dlux_reconcile` runs before migrations and only repairs the runtime pointer on the
volume; it never writes the database. The database side is
`UpdateService.reconcile()`. The Celery state tick runs it once per worker process
(so after `migrator`), and again whenever the recorded baked version stops
matching the installed package (an image swap under a running worker) or the
runtime volume's generation advances (a release activated by Composer).

## Checking for updates

### Which releases are eligible: stable and beta

Stable is the default and admits no prerelease. Beta is a persistent, explicit
opt-in (the **Include beta releases** switch on the Options card, or
`composer dlux channel beta` on the host) and it widens *eligibility only*:
digest, attestation, manifest, migration and image-floor checks are identical on
both.

Turning it off never downgrades anything. A check only ever offers versions
strictly above the installed one, so a deployment on a beta that leaves the beta
channel waits for the next stable release above it rather than being walked back.
Going backwards is the rollback path, which has its own checks.

Three processes need the same answer and none of them can own it alone:

| | reads | writes |
| --- | --- | --- |
| Options UI (`web`) | the database column | nothing; the runtime volume is read-only there |
| Celery worker | both | the database column and `state/channel-policy.json` |
| Composer | `state/channel-policy.json` | nothing |

So the administrator's choice is recorded in `DluxUpdateState.update_channel`, and
the worker mirrors it to the policy file that Composer reads. `web` changes only
the column; the worker's next reconcile publishes it. Composer's host CLI has no
database, so it leaves a token-carrying `state/channel-request.json` beside the
policy, which the worker applies and acknowledges in `channel-request.json.ack` on
its next tick: the same hand-off shape as package and image updates. Either way
the switch reports **pending** until the published policy matches, rather than
claiming a change it has not yet made.

Every failure reads as stable: a missing policy (a deployment that never opted
in), an unreadable one, a malformed one, or one written by a newer DjangoLux whose
schema this release does not understand. A malformed policy also *reports* the
error, so corrupting a file can never be a way to turn beta on. The worker
republishes a policy that disappeared with its volume.

Both sides check the channel independently. Composer resolves the candidate from
the policy, and DjangoLux checks again before it offers or applies one. The two
can disagree for a tick after an opt-out, and the safe direction to disagree is to
offer less.

### How often Composer checks, and checking now

Composer's resident agent checks PyPI for DjangoLux releases and the registry for
project images on an interval. **Check for updates every** on the Options card
sets it with a slider (5 minutes to 24 hours, default 15 minutes; dragging updates
the label, releasing saves). The choice is stored in
`DluxUpdateState.check_interval_minutes` and published by the worker to
`state/check-policy.json` as `{"schema_version": 1, "interval_seconds": N}`. The
agent reads that file on every loop tick, so a change takes effect within seconds,
and a shorter interval pulls the next scheduled check forward. Without the file
the agent's `--check-interval` applies; the scaffold passes 900 seconds.

**Check for updates** is a request, not a read. The worker writes
`state/check-request.json` with the check run's token; the agent re-checks both
images and packages immediately and acknowledges in `check-request.json.ack`, and
the next worker tick finishes the run from the fresh report. Composer 1.4.0 or
later checks on request; an older Composer never acknowledges, so after 20 seconds
the run falls back to its last report and says so in the run log. A repeat click
within 10 seconds of a finished check returns that check's result.

DjangoLux also queues a check run of its own once `DLUX_UPDATE_CHECK_INTERVAL`
seconds (default one day) have passed since the last check; Beat looks hourly.

The card ends a check on whichever request sees the run finish: the run poll, any
state read (the 60-second background refresh, or the poll's own fallback when the
run endpoint fails), or the tab becoming visible again, which polls at once
instead of waiting for a timer a background tab may hold back for a minute.

### Release notes for the offered release

The availability report may carry the offered release's own notes. Composer reads
them from the same verified wheel that decides `inline_safe` and publishes the
manifest's `display` block (`summary`, `highlights`, `release_url`) as `display`,
or the whole manifest as `manifest`. Composer 1.9.1 or later publishes them; an
older one publishes only the version and `inline_safe`.

The check stores them as `DluxUpdateState.latest_manifest`, bounded like a
validated manifest (summary 1000 characters, 8 highlights of 160) and keeping
`release_url` only when it is that release's own GitHub page; notes naming
another version are dropped. The review dialog lists the highlights, or the
summary when there are none, above the generic "Bug fixes and improvements" line.
A report without notes clears the previous offer's, and the dialog then shows the
generic line alone. Nothing here reaches the network; the notes come off the
runtime volume like the rest of the report.

## Update handoff

After superuser approval, DjangoLux writes an update request on `dlux_runtime`.
Composer publishes its acknowledgement and the latest installable release
metadata. An absent availability document is **unknown**, never "up to date".

Release eligibility remains strict. Composer honours the release manifest's
schema, migration effect, rollback compatibility, service requirements, baked
image floor, and `install.inline` permission. An inline-forbidden release requires
a normal project-image rebuild; Composer execution does not make a
database-destructive migration safe to apply from a volume.

Update admission serializes through the DjangoLux state row. Only one inline run
is active at a time, and an image update and an inline update cannot be admitted
concurrently. When a pre-update backup is requested, DjangoLux finishes it before
the update intent is written.

An inline apply or rollback started from DjangoLux (the Options card or
`/sys/api/dlux-update/`) runs in the Celery worker:

1. **Backing up.** The worker takes the backup the run asked for: `backup_mode` is
   `data` (default), `full` or `skip`; a rollback takes a data-only one. The run
   reads *Backing up* ("Creating a data-only pre-update DjangoLux backup."), the
   backup's token is stored on the run, and a failed backup fails the run, so
   Composer is never asked to swap code. The step runs in the release being
   updated *from*.
2. **Hand-off.** The worker writes `state/package-update-request.json` (the run's
   token, mode `apply` or `rollback`, target version and backup mode) and moves
   the run to *applying*. A second request is refused while Composer has not
   acknowledged the first, because two swaps of one volume would race over
   `active.json`.
3. **Composer** stages, swaps, restarts and health-gates the release, then
   acknowledges.

`./start.sh dlux update` and `./start.sh dlux rollback` go to Composer directly
and do not pass through this step; Composer takes the snapshot itself instead,
through `manage.py dlux_backup` (see the Composer docs for `--backup`).

### What finishes a handed-off run

Writing `package-update-request.json` is the end of DjangoLux's part: nothing in
the web or worker process can observe what Composer does next. The Celery tick's
`tick_package_update()` reads the answer back from
`package-update-request.json.ack` (the token and the exit code), reconciles the
versions the Options card reports, and finishes the run:

| Composer's answer | The run |
| --- | --- |
| exit 0 | completed |
| rolled back (from Composer's own result in `deploy-status.json`) | rolled back, with Composer's message |
| exit 3 | failed: the rollback was not healthy either, and the deployment needs an operator |
| any other exit | failed, with Composer's message or the exit code |

Reading the ack is also where the now-active release's static files are collected
(`collectstatic --noinput --clear`, with the release on `PYTHONPATH`). Composer's
swap does not collect them, and without this step the deployment would serve the
previous release's CSS and JS against the new release's templates: unstyled
controls and dead scripts, with no error anywhere. It runs after any
acknowledgement, since an apply, a rollback and a rolled-back apply all change
which release is active. A collect that fails does not fail the run (Composer
swapped and health-gated the release, so it really is active), but it is named in
the run log and recorded as `static_collected: false` in the run report. Until
`manage.py collectstatic --noinput --clear` runs on the deployment, it serves the
previous release's static files.

A hand-off Composer never acknowledges is failed after 30 minutes. Composer's own
work is bounded (download, swap, restart, health wait), so past that nothing is
coming, and a run left active would block every later update. The release may
still be active in that case; check the `composer-executor` logs, and trust the
Options card for what is actually installed.

### What the card offers after an update

Neither of the fields that describe what the panel may do next is written by the
process that performs the swap: Composer is outside the container.
`reconcile()` derives them from what is actually on the volume:

- The update offer (`latest_compatible`) is stood down once the recorded latest
  release is no longer newer than the active one, so an installed release stops
  being advertised. Raising an offer stays with a check run, where the skip list
  and inline-safety are decided.
- `previous_version`, which drives the Rollback button and its admission check,
  is the newest staged release below the active one, else the release baked into
  the image: exactly how Composer picks its rollback target. A target below the
  baked version is not offered, because reconcile resets anything under that
  floor and the rollback would be undone on the next pass.
- `active_manifest` and `previous_manifest`, the installed release's notes on the
  DjangoLux row and the notes in the rollback review, come from each release's own
  `dlux/release-manifest.json`: the staged release under `releases/<version>/`,
  or the image's package for the baked version (the first copy outside the runtime
  volume, so a worker running a volume release still reads the image's). Only
  `display` (or a schema-1 manifest's top-level `summary`, `highlights`,
  `release_url`) is kept, bounded like the offered release's notes, and nothing is
  kept when the manifest names another version. They follow every apply, rollback
  and image rebuild, Composer's included.

### The end of an inline update

Once Composer acknowledges, the worker reconciles the state row (versions, the
rollback target and both releases' notes), collects the active release's static
files and finishes the run. `manage.py` output joins the run log without DEBUG log
records (lines starting `DEBUG:` or `DEBUG `), so a project that turns debug
logging on, for example with `logging.basicConfig(level=logging.DEBUG)` when
`DEBUG` is set, does not fill the update dialog with them.

Success turns the dismiss button into **Finish**, and closing the dialog reloads
the page: the card's rows were rendered by the previous release (the Backup &
Restore time only server-side) and the page still runs that release's scripts.
Closing after a failure leaves the page as it is.

## Image updates

### The end of an image update

An image update has two finish lines. Composer writes `ready` to
`state/deploy-status.json` once the containers are recreated and migrated; the new
web container's DjangoLux then marks the `DluxImageUpdate` completed (the Celery
state tick runs `_finalize_image_update`) and lowers the maintenance flag. Until
then the proxy answers 503 with the maintenance page Composer publishes on the
runtime volume (`proxy/maintenance/`).

- When the update starts, DjangoLux resets both `deploy-status.json` (to
  `preparing`) and `deploy-log.txt`, so the modal never shows the previous
  update's log while the backup runs. It then takes the pre-update backup, raises
  the maintenance flag and writes `state/image-update-request.json`.
- An update Composer does not acknowledge within two minutes fails, as does one
  that has not completed within an hour; either way the maintenance flag is
  lowered.
- The update modal is locked while the update runs, as it is for an inline update.
  On `ready` it polls the state endpoint until web answers and the update reads
  completed (from `state.image.last_update`, matched by token) or failed. Success
  turns the bar green and the dismiss button into **Finish**; closing the modal
  then reloads the page, because the page that starts an update runs the release
  it was loaded with. A failure unlocks the modal with the error.
- The maintenance page treats every end state (`ready`, `completed`,
  `rolled_back`, `failed`) as a reason to probe the URL it is shown at, and reloads
  that URL once the app answers.

From stack schema 3 (Composer 1.7.0 or later) the maintenance page is not a
project file. It ships in the Composer image; `composer-agent` publishes it on
every start to `/opt/dlux-runtime/proxy/maintenance/` and the proxy serves it from
the runtime mount it already has, with its CSS and JS under `/_dlux/maintenance/`
so they load while `web` is down. A project page goes in `.proxy/maintenance/` and
is published by `composer check --fix`. A stack stamped with an earlier schema
serves `.proxy/maintenance.html` from a bind mount until `composer check --fix`
(resident agent 1.7.0 or later) migrates it; a customised page is kept as the
override. See [Stack Schema Stamps](stack-schema.md).

### When the image moves backward

`state/active.json` with `source: image` means "whatever the image bakes".
DjangoLux reads it that way, but Composer reports its `version` field as the
installed release. When the baked package moves to an older version under an
image activation (an older application image, or a removed source mount),
reconcile rewrites the file with the baked version and the same generation. It is
a label correction, not a new runtime; without it Composer would call the
deployment up to date with a release it is not running, and offer no update.

### Moving to an image that bakes an older DjangoLux

The active release lives on the runtime volume and is what the supervisor puts on
`PYTHONPATH`, so an image baking an older DjangoLux does not by itself downgrade a
deployment. A gate that reads only the image's baked-version label would refuse
anything older than the active release, which is safe but stricter than the
deployment requires.

`manage.py dlux_image_gate --baked-dlux-version <label>` answers it properly, and
returns JSON:

- `adopt`: the image is at or ahead of the active release; reconcile resets to the
  baked release as it always does. Also returned when the label is missing or
  unparseable, so an unreadable label can never invent a verdict.
- `keep`: the image is older, but at or above the active release's
  `requires.baked_image` floor. The active release stays on the volume and keeps
  running on the new image.
- `abort`: the image predates a DjangoLux release that required an image rebuild,
  so the active release cannot run on it. Update the project image past that floor
  first.

Composer 1.3.13 or later asks this before recreating onto a new image: it
proceeds on `keep`, blocks on `abort` (quoting the reason), and blocks on its label
gate alone when the command is unavailable, the service is down, or the output is
unreadable. `COMPOSER_RUNTIME_GATE_SERVICE` selects the service it asks (default
`web`); `--force` still overrides without asking. An older Composer refuses any
image whose baked DjangoLux is older than the active release, and `--force` is
the only way through.

The floor is the rule that already governs inline installs: a release is staged
with `pip install --no-deps`, so only DjangoLux itself is on the volume and
everything it imports comes from the image. `requires.baked_image` records the
last release that needed a rebuild, which is exactly the bar an image must clear
to carry a later release.

## Deployment operations

**Updates and maintenance** has four rows: DjangoLux, the application image, the
Composer agent, and Backup & Restore, which links to that page with the date of
the last backup. Everything a row *reports* (a version, a digest, that date, what
an update would move to) sits at the row's end; the lead group holds the controls
and the name. The DjangoLux row also offers the installed release's own notes,
which reconcile reads from that release's package (see
[What the card offers after an update](#what-the-card-offers-after-an-update)); a
release without notes offers no icon. Each row's icons carry that component's own
last check in their tooltip; there is no shared "last check" line.

The Composer agent row has one icon that checks, a second that appears only when
the channel publishes a newer Composer, and a tick when it does not. Updating the
agent confirms with the current password through the shared password prompt.

The release channel and the check interval are not among the rows. They are set
once and then left alone, and a slider beside the rows is easy to nudge by
accident, so they start hidden. One chevron at the end of the card's last line
reveals them, and System info's details table with them, since the two cards
stretch to a common height.

Everything else that otherwise needs a shell on the host lives in the
**Operations** panel, opened from the admin panel's actions rail. It is offered to
superusers whether or not inline updates are enabled, and its actions work once
the resident Composer agent reports its version. Day-to-day use is described in
[Operations](operations.md#deployment-operations). It holds:

* **Deployment check**: Composer's doctor for the *outside* of the stack (a
  resident pair started with a command this Composer rejects, a missing
  `org.dlux.restart` label, an obsolete service, a legacy maintenance page). Its
  findings and the exact diff `check --fix` would apply are shown inline,
  including the maintenance-page move to stack schema 3, and **Apply repairs**
  confirms with the password and may only apply that diff. Composer refuses if
  any previewed file, the `.proxy/` files included, changed in between.
* **Services**: every Compose service with its state and health. Services the
  stack allow-lists (`COMPOSER_AGENT_RESTART_SERVICES`, never one labelled
  `org.dlux.restart: "protected"`) offer **Restart** and **Recreate**; recreating
  runs the service's `pre_start` hooks, which on `celery` applies migrations.
  Approved auxiliary services also offer **Start** and **Stop**, following the
  `can_start` and `can_stop` flags Composer reports beside `can_restart`. All of
  them are password-confirmed; every service offers **Logs**.
* **Logs**: the last lines of the chosen service, or of every service merged in
  time order, redacted by Composer and shown as plain text.

DjangoLux gains no Docker authority from any of it. The card and the panel can
request exactly the operations named in `dlux.updater.ops.OPERATIONS`, and nothing
else exists:

| Operation | Changes the deployment | Needs |
| --- | --- | --- |
| `check` | no | Composer 1.5.2 or later |
| `agent-check` | no | Composer 1.5.2 or later |
| `check-fix-apply` | **yes** | Composer 1.5.2 or later, a check that found repairs, and the current password |
| `agent-update` | **yes** | Composer 1.5.2 or later, a check that found an update, and the current password |
| `services` | no | Composer 1.7.0 or later |
| `service-restart` | **yes** | Composer 1.7.0 or later, an allow-listed `service`, and the current password |
| `service-recreate` | **yes** | Composer 1.7.0 or later, an allow-listed `service`, and the current password |
| `service-start` | **yes** | Composer 1.8.0 or later, an approved auxiliary `service`, and the current password |
| `service-stop` | **yes** | Composer 1.8.0 or later, an approved auxiliary `service`, and the current password |
| `logs-tail` | no | Composer 1.7.0 or later, `lines` (1 to 1000, default 200), and optionally a `service`; without one, every service merged in time order |

The only arguments a request can carry are a service name (letters, digits, `_`
and `-`, at most 64 characters) and a line count. DjangoLux validates them and
stores them on the run (`DluxOpsRun.params`); Composer checks the service against
the stack again, and the executor once more. The panel's operations (every row
from `services` down) only disable their buttons with the reason on an older
Composer; they do not mark the deployment as behind.

Each operation declares the Composer it needs, and DjangoLux knows the resident
version from the agent's status file, so an operation the deployment cannot
perform is disabled with its reason rather than offered and failed on a timeout.
An unknown version gates nothing, since the run's own timeout still names the
floor. In code (and in `min_composer` in the state API) each floor names the
release's first prerelease rather than the release: PEP 440 orders a prerelease
below its release, so a floor of the release itself would refuse the beta that
introduced the operation.

Updating DjangoLux before Composer is allowed, so the card also says, under the
Composer agent row, when the resident is older than it should be: older than an
operation needs, or older than the running release's own
`requires.services.composer` floor. The notice names both versions and who can fix
it. When the card's operations are blocked it gives the host commands
(`./start.sh self update`, then `./start.sh agent update`). That form is
deliberate: it is shown to stacks whose Composer is too old, and their wrappers
and Composer do not know `update self`. Composer keeps `self update` as a
deprecated alias (see
[deprecation countdown](deprecation-countdown.md#composer-self-update)). With
Composer 1.9.1 or later (wrapper 5 or later), a plain `./start.sh update`
refreshes the deployer before the stack and the resident pair. When only the
release's floor is missed, the card can still check and update the agent itself,
and the notice says so instead of sending the administrator to a shell.

Each row keeps its own last answer: checking the Composer does not blank what the
deployment check found, and vice versa.

### How an operation reaches Composer

The handoff is the update handoff's shape. A superuser POSTs
`/sys/api/dlux-ops/run/` (audited); the run is recorded in the database because
`web` mounts the runtime volume read-only; the worker writes
`state/ops-request.json` carrying the run's token; the agent performs the
operation and publishes `state/ops-result.json` and `ops-request.json.ack` under
that same token; the next worker tick finishes the run from the result. A result
whose token does not match the run is ignored: the previous operation's document
is still on the volume, and showing it would be a lie the card could not detect.

The request names an operation and, where the operation takes them, the service
and line count above; `check-fix-apply` adds the digest of the check it applies.
It carries no command, no path and no flags, so there is nothing for a compromised
database or a tampered file to smuggle into what Composer runs. One operation runs
at a time, and `check` is read-only: it never applies `--fix`.

A check that finds problems is a successful check: its exit code reports the
deployment's health. Only a refusal or a crash, which carries an error, fails the
run.

A Composer older than the operation's floor never acknowledges. After 120 seconds
the run fails with the version it needs, rather than sitting on "running" for
ever; `agent-update` and `service-recreate` get 15 minutes.

Findings are rendered as text (level, name, message and Composer's own fix hint),
and Composer redacts and bounds them before publishing (200 findings, 2000
characters each), because they are read in a browser.

### The Composer agent row

`agent-check` reads the version published on the project's Composer channel tag
and reports it beside the resident version. The row then shows one of three
things, and never guesses between them:

* a tick: checked, and the pair runs what the channel publishes;
* the update icon, with the published version beside it; or
* nothing checked yet (the plain arrow), or a check that ran but could not read
  the registry (a warning icon, with Composer's reason in a notice under the
  row). **Unknown is not "up to date"**, and it is not an update either.

**Update the Composer agent** replaces `composer-agent` and `composer-executor`
with the channel's current image. It cannot report itself, because the update
recreates both, so the executor starts a detached helper that performs it and then
writes the run's answer to the runtime volume. It is offered only after a check
found an update: nobody is asked for a password to discover that there is nothing
to install. Composer refuses it outright if the pair already runs the channel's
version. Once the pair has been replaced, the row goes back to asking rather than
claiming, because what it runs now is something only a fresh check can say.

The deployment check's icon is tri-state the same way: an arrow until checked,
then a tick, warning or cross by the worst finding. In the results modal, findings
with a repair offer **Apply repairs** in the footer (preview, then password);
findings without one say that no automatic repair is available.

### The application image row

Composer compares the running image's registry digest with the channel's. An
image built locally (a development overlay) has no registry digest, so the row
shows a neutral "Local build" icon instead of offering the registry image. When an
update is available its target is the project release manifest's version, else
the build's short digest; the DjangoLux version the image bakes is shown
separately as `baked dlux`, never as the application's version.

### Previewing and applying repairs

`composer check --fix` repairs what the check finds: an obsolete service, a
missing restart label, a resident pair started with a command this Composer
rejects. A repair rewrites the deployment's own Compose file, so it takes two
steps, but only one button each:

1. The check returns the findings *and* what `check --fix` would change: a unified
   diff per file, writing nothing, plus a SHA-256 digest of the files Composer
   read. The repair icon appears only if that found something.
2. **Apply repairs** re-verifies the administrator's current password, and the
   request carries that digest, taken from the check's own result and never from
   the browser. Composer refuses the apply when the files no longer hash to it, so
   the change that lands is the change that was shown. Applying without a check is
   refused before Composer hears of it.

A completed apply consumes the preview: what it showed is now on disk, so a second
apply needs a new check. A failed apply leaves the preview usable.

Composer's own guards still apply on top: the candidate is validated with
`docker compose config`, the originals are archived under `.xclude/`, and the write
is atomic. A transform that refuses is reported as a note on that repair rather
than failing the operation.

## Recovery and rollback

Rollback selects the prior code and static release; it does not reverse
migrations or restore database data. Reconcile falls back to the baked package
when an active runtime release is missing, corrupt, or not newer than the image's.
Once the runtime has converged on a healthy release (a successful restoration, or
the baked image) and no run or image update owns the maintenance flag, reconcile
lowers a flag left raised, so a recovered site does not stay behind the
maintenance page.

Keep the runtime volume: it holds the active pointer, release installations,
maintenance state, and the Composer/DjangoLux handoff records.

Use [Deployment Doctor](doctor.md) for diagnostics and
[Composer Agent Integration](composer-agent.md) for the service and network
boundary.

## Reference

### Routes

| Route | Method | Access and purpose |
| --- | --- | --- |
| `/sys/api/dlux-update/state/` | `GET` | Superuser or global staff. Read-only updater state, the latest run and the active image update; release notes as described below the table. |
| `/sys/api/dlux-update/runs/<token>/` | `GET` | Superuser. One run's durable status and bounded progress log. |
| `/sys/api/dlux-update/check/` | `POST` | Superuser, CSRF-protected, audited. Queues a check run; Composer re-checks PyPI. A repeat within 10 seconds returns the last result; 409 when inline updates are disabled. |
| `/sys/api/dlux-update/skip/` | `POST` | Superuser, CSRF-protected, audited. `version`, plus `unskip` to reverse it: the check never offers a skipped version. Works even when inline apply is disabled. |
| `/sys/api/dlux-update/channel/` | `POST` | Superuser, CSRF-protected, audited. `channel` (`stable` or `beta`), or the Options checkbox field `beta`. Installs nothing. |
| `/sys/api/dlux-update/interval/` | `POST` | Superuser, CSRF-protected, audited. `minutes`: 5, 15, 30, 60, 180, 360, 720 or 1440; published to Composer by the worker. |
| `/sys/api/dlux-update/apply/` | `POST` | Superuser and `current_password`, CSRF-protected, audited. `backup_mode`: `data` (default), `full` or `skip`. |
| `/sys/api/dlux-update/rollback/` | `POST` | Superuser and `current_password`, CSRF-protected, audited. |
| `/sys/api/dlux-update/image/` | `POST` | Superuser and `current_password`, CSRF-protected, audited. Queues an image update; `backup_mode` as for apply. |
| `/sys/api/dlux-update/runtime-health/` | signed `GET` | Active-version probe. Answers only a request whose `X-Dlux-Updater-Probe` header carries the HMAC of `SECRET_KEY`; any other request gets 404. |
| `/sys/api/dlux-ops/state/` | `GET` | Superuser. The deployment rows' state: available operations, the newest run, the last deployment check, the Composer agent's version against its channel, and `composer_behind`. |
| `/sys/api/dlux-ops/run/` | `POST` | Superuser, CSRF-protected, audited. One named operation (`operation`; `service` and `lines` where it takes them). The write operations also re-verify `current_password`, and `check-fix-apply` may only apply what the last check showed. |
| `/sys/operations/` | `GET` | Superuser. The Operations panel, rendered into the admin-rail dynamic modal; independent of the inline-update switch. Every action goes through `/sys/api/dlux-ops/run/`. |

In the updater state, `state.latest_manifest` holds the offered release's notes
(`version`, `summary`, `highlights`, `release_url`) when Composer's availability
report carries them, else `{}`; `state.active_manifest` and
`state.previous_manifest` hold the installed release's and the rollback target's
notes in the same shape. In the operations state, `composer_behind` (`version`,
`required`, `ops_blocked`) is present when the resident Composer is older than an
operation or this release's `requires.services.composer` floor.

### Settings

[Deployment Configuration](deployment-configuration.md#application-version-and-inline-updater)
is the canonical list of `DLUX_*` settings. The ones this page relies on:

| Name | Default | Purpose |
| --- | --- | --- |
| `DLUX_INLINE_UPDATES_ENABLED` | `False` | Enables update checks and operator-approved apply and rollback. Generated `compose.yml` sets `True`; `compose.dev.yml` sets it back to `False` on `web` and `celery`, because development runs a bind-mounted checkout rather than an installed release. |
| `DLUX_UPDATE_CHECK_INTERVAL` | `86400` (minimum `300`) | Seconds between the check runs DjangoLux queues itself. |
| `DLUX_UPDATE_RUNTIME_ROOT` | `/opt/dlux-runtime` | Where `dlux_runtime` is mounted. |
| `DLUX_BOOT_GATE` | `on` | Entrypoint migration gate: `off`, `apply` or `on` (see [Boot and ownership](#boot-and-ownership)). |
| `DLUX_MIGRATOR_FLAGS` | empty | Flags Composer passes to the `migrator` init step. |
| `COMPOSER_AGENT_RESTART_SERVICES` | `web,celery,smtp-relay,caddy,ocr` in the scaffold | Services the Operations panel may restart and recreate. |
| `COMPOSER_RUNTIME_GATE_SERVICE` | `web` | The service Composer asks for `dlux_image_gate`. |

The update index is fixed to official PyPI and is not configurable.
