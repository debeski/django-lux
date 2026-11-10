# Composer Agent Integration

Composer is the deployment companion for generated DjangoLux Compose projects.
DjangoLux owns application policy, permissions, backups, maintenance state, and
update admission. Composer owns external image and package work, container
lifecycle, health verification, and the optional outbound control-plane relay.

## Generated topology

The scaffold runs these Composer services:

| Service | Authority | Network access |
| --- | --- | --- |
| `composer-agent` | outbound registry/control-plane communication and typed local relay | `egress`, `docker_proxy` |
| `composer-executor` | the sole Docker-write authority | `docker_proxy` only |
| `docker-socket-proxy` | read-only Docker API for the agent | `docker_proxy` only |

The agent has no raw Docker socket. It reads through the proxy, which disables
`POST` and `EXEC`; typed write requests go through the private
`composer_exec_sock` to the isolated executor, which holds the Docker socket. Both
Composer services drop all capabilities and run with `no-new-privileges`. The
executor adds back only `DAC_OVERRIDE`, so it can read the project's `0600`
`.secrets/.env` to deploy; the project directory is mounted read-only in both.

`egress` is deliberately separate from published `frontend`. The public proxy
does not share a bridge with services that need outbound access. The internal
application network remains isolated for `db`, `redis`, `web`, and `worker`.

The rule this topology enforces is stated in
[Outbound Requests](outbound-requests.md): the agent is the only service with
internet access, `worker` is the only DjangoLux service that writes the local
bridge (a project-only `celery` kept on a stack migrated from schema 4 may write
relay requests too), and `web` reads it but never writes. Project code asks the
agent for outbound calls instead of opening connections itself.

The scaffold has no `dlux-updater` service. Runtime reconciliation and migrations
run as `worker` `pre_start` steps, and the task worker's schedule runs the small
state and intent tick (see
[Verified Inline Updates](inline-updater.md#deployment-architecture)). Do not add
the service back to a stack; `./start.sh check` reports one left in an older
stack's `compose.yml`.

## Local bridge and enrollment

The shared `dlux_runtime` volume carries bounded, atomic, schema-versioned JSON
documents. DjangoLux writes approved intent, durable state and a status snapshot
for the agent; Composer publishes availability, acknowledgements, deployment
status and its own agent status. The bridge excludes secrets in the clear,
environment dumps, unrestricted logs, backup artifacts, and restore commands. The
one secret that passes through it is a one-use pairing token on its way to the
agent (see [Pairing with a control panel](#pairing-with-a-control-panel)).

### The agent bridge

The control-plane side of the bridge lives in `state/agent/` on the runtime
volume:

| File | Written by | Carries |
| --- | --- | --- |
| `snapshot.json` | DjangoLux, at most once a minute | project name and environment; application, DjangoLux and Composer versions; database, maintenance and degraded health; CPU, memory and disk use; the ten latest backups; image-update availability |
| `requests/<operation_id>.json` | the agent, on the control plane's behalf | one action: `dlux.image_update` (backup mode `data`, `full` or `skip`) or `dlux.backup.create` (`data` or `full`) |
| `results/<operation_id>.json` | DjangoLux | the outcome of each request, rejections included |
| `enroll-request.json` | DjangoLux | a pairing request: control URL, one-use pairing code, operation id |
| `agent-status.json` | the agent | enrollment and connection status, and the resident Composer version |

DjangoLux accepts a request only when it is at most 64 KiB, has schema version 1,
names one of those two actions, and its file name is its UUID `operation_id`;
anything else gets a `rejected` result. Handled requests move to `processed/`.
Package updates never travel through this bridge: an inline package run is always
local.

### Pairing with a control panel

Pair from the superuser **Control Panel** page (`/sys/control-panel/`, linked from
the admin panel's actions rail) after first boot:

1. Enter the control panel's base URL and the one-use pairing token it issued.
   The URL must be `https://`; `http://` is accepted only for `localhost`,
   `127.0.0.1` and `::1`.
2. `web` cannot write the bridge, so it records the request in the database
   (`DluxControlLinkRequest`). The worker publishes it as `enroll-request.json` on
   its next tick and deletes the row, so the token is at rest in the database for
   at most one tick. A request the worker cannot publish keeps its row, with the
   token cleared and the error shown on the page.
3. The agent redeems the token with the control plane once per request, keeps the
   credentials it receives, and records the outcome in `agent-status.json`
   (`last_enroll`: operation id, state, error, time). An agent that is already
   enrolled, and not revoked, adopts the URL and reports success without
   redeeming anything.
4. On success the worker removes the published request. A failed attempt stays on
   the page until the operator retries or cancels; **Cancel**
   (`/sys/control-panel/cancel/`) clears a pending request.

The page shows one of four states: *unconfigured*, *pending*, *connected*, or
*disconnected* (a control URL is on record but the agent is not enrolled, or the
control plane revoked it). When a connection the worker has seen drops, every
active superuser gets one notification linking to the page. The superuser-only
`/sys/api/control-panel/status/` returns the same state as JSON.

Headless deployments may enroll from the environment instead; the scaffold passes
both to `composer-agent`:

- `COMPOSER_CONTROL_URL`: public HTTPS control-panel base URL.
- `COMPOSER_ENROLLMENT_TOKEN`: one-use bootstrap token.

Credentials are retained in the private `composer_agent_state` volume after
enrollment. The agent has no inbound listener, and local DjangoLux operations
continue if the control plane is unavailable or revokes the connection.

## Existing stacks

Run Composer through the generated wrapper:

```bash
./start.sh check
./start.sh check --fix
```

`check` reports missing Composer services, obsolete `dlux-updater` wiring, or
runtime-volume drift. Review the proposed change before `--fix`; Composer
preserves modified project files under `.xclude/` and validates the resulting
Compose configuration. Compose 5.3.0 or newer is required because DjangoLux uses
`pre_start` hooks.

For update behavior and recovery, see [Verified Inline Updates](inline-updater.md).

### Deployment checks and the secrets file

With Composer 1.9.0 or later, the Operations panel's deployment check runs in the
deployment executor's identity, and `./start.sh check` verifies that the executor
can open the configured secrets file, not only the user who ran the command. A
file the host user can read may still be unreadable after UID mapping; the finding
names the executor's mapped host UID and shows a Linux VM recovery command for it.
The network-facing agent needs no access to the secrets file. Update both resident
services with `./start.sh agent update`.
