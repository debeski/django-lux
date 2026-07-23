# Design Spec — UI-Driven Control-Panel Pairing (no `.env`, no redeploy)

> Status: **Phase 1 implemented** (`dlux` 1.5.1, `app-composer` 1.2.1,
> `project-dlux-control` 0.1.1). Phase 2 (agent-generated claim code) remains a
> proposal. Cross-repo feature spanning `django-lux` (`dlux`), `app-composer`
> (the agent), and `project-dlux-control` (the control panel).
>
> **Two deviations from the original draft, decided during implementation:**
> 1. **Bridge direction.** The existing agent bridge is agent-initiated
>    (agent writes `requests/`, DLUX writes `results/` + `snapshot.json`), so
>    pairing uses two dedicated sibling files instead: `enroll-request.json`
>    (DLUX→agent) and `agent-status.json` (agent→DLUX).
> 2. **No DB storage of the token.** The pairing token is written straight to
>    the `enroll-request.json` in the private `dlux_runtime` volume (already the
>    DLUX↔agent trust domain) and auto-cleared on success — so no encrypted
>    settings field, model, or migration was needed.

## Problem

Today a project enrolls its `composer-agent` with the central control panel by
seeding two env vars **before first boot**:

```
COMPOSER_CONTROL_URL=...
COMPOSER_ENROLLMENT_TOKEN=...   # one-use
```

The agent reads them in `composer/agent.py::ensure_enrolled()`, calls the panel
once, and persists durable credentials in its private `composer_agent_state`
volume (`agent_store.py`). After that first enrollment the token is dead weight.

The operator experience is therefore: open the panel → generate a token → paste
URL+token into `.env` → deploy → (agent enrolls) → go back and delete the token →
redeploy. That "edit config, redeploy, clean up" cycle is the friction this spec
removes. The goal is a **UI-first pairing** that mirrors how DjangoLux already
stores the SMTP relay password (encrypted DB secret entered in System Settings),
with **zero enrollment vars in `.env`** and **no redeploy**.

## What already exists (and gets reused)

- **The agent is outbound-only.** It dials the panel; the panel never dials in.
  This is the security boundary and does **not** change.
- **Durable credential store** — `composer/agent_store.py` (sqlite, mode `0600`,
  in `composer_agent_state`). Credentials already survive recreation; the token
  is already single-use. Rotation already exists (`agent.rotate_credentials`).
- **A typed DLUX↔agent bridge already carries operations both ways** —
  `dlux/updater/agent_bridge.py` writes request docs to
  `<state>/agent/requests/<operation_id>.json` (envelope
  `{schema_version: 1, operation_id: <uuid>, …}`, atomic write, 64 KiB cap,
  filename stem == `operation_id`), the agent processes them and writes to
  `results/`, and the agent publishes status to `<state>/agent/snapshot.json`
  (`build_agent_snapshot` / `publish_agent_snapshot`), which DLUX already reads.
- **The enroll HTTP contract** — `composer/control_client.py::enroll()` does
  `POST {control_url}/api/agent/v1/enroll/` with body
  `{schema_version: 1, enrollment_token, **capabilities}` and expects
  `{agent_id, agent_secret}`. Subsequent calls authenticate with
  `Authorization: Bearer <secret>` + `X-Composer-Agent-ID`.
- **DjangoLux encrypted-secret + System Settings tile pattern** — the same
  mechanism used for the SMTP relay password (Fernet, see `dlux/backup.py`
  helpers and the System Settings secret-storage UI).

The key realization: **enrollment is just a new request kind on a bridge that
already works, and a pairing code is just the `enrollment_token` the agent
already knows how to redeem.** So Phase 1 is small.

## Phase 1 — Panel-issued pairing code, entered in DLUX (recommended first build)

The closest analogue to the SMTP-secret UX and the smallest lift, because it
reuses the agent's existing `enroll(token, …)` path verbatim.

### Flow

1. **Panel:** operator opens `project-dlux-control` → *Add application* → the
   panel mints a **short-lived, single-use pairing code** (e.g. `ABCD-1234`,
   TTL ~10 min) bound to a pending application slot, and shows it plus the
   control-plane base URL.
2. **DLUX UI:** in *System Settings → Control Panel* tile, the superuser enters
   the **control URL** (not a secret) and the **pairing code**. On save DLUX:
   - stores the pairing code **Fernet-encrypted** and marks it `pending` (it is
     transient, not a long-lived secret),
   - writes an `agent.enroll` request into the bridge `requests/` dir:
     ```json
     {
       "schema_version": 1,
       "operation_id": "<uuid4>",
       "kind": "agent.enroll",
       "control_url": "https://panel.example.org",
       "pairing_code": "ABCD-1234",
       "requested_at": "<iso8601>"
     }
     ```
3. **Agent:** its bridge loop (`process_bridge_results` / request handling in
   `composer/agent.py`) gains an `agent.enroll` handler that:
   - constructs a `ControlPlaneClient(control_url)`,
   - calls `client.enroll(pairing_code, self.capabilities())` — **the pairing
     code is passed as `enrollment_token`; no HTTP contract change**,
   - persists `{agent_id, agent_secret}` via `AgentStore.save_credentials`,
   - writes a `result` doc (`ok`/`error`) and forces
     `publish_agent_snapshot(force=True)` with `enrolled: true`,
     `control_url`, `enrolled_at`, `agent_id` (never the secret).
4. **DLUX:** reads `snapshot.json`, flips the tile to **Connected**, and
   **deletes the encrypted pairing code** (it has served its purpose). On
   `error`, the tile shows the failure and keeps the code for one retry until
   TTL expiry.

### Result

No `.env` enrollment vars, no redeploy, self-clearing secret, live status in the
UI, and disconnect/rotate/re-pair from the same tile. `COMPOSER_CONTROL_URL` /
`COMPOSER_ENROLLMENT_TOKEN` remain honored as a **headless fallback** for
CI/GitOps deploys (env path unchanged).

## Phase 2 — Agent-generated claim code (optional, stronger)

Zero secret ever leaves the panel or transits a clipboard into a config field.

1. On an unclaimed first boot (no credentials, no token), the agent generates a
   **claim code** and publishes it in `snapshot.json`
   (`claim_code`, `claim_expires_at`).
2. DLUX surfaces it in the tile: *"Pair this app — enter `ABCD-1234` in your
   control panel."*
3. Operator approves it in `project-dlux-control`; the panel marks the claim
   approved and mints credentials.
4. The agent, polling a new unauthenticated
   `POST /api/agent/v1/claim/poll/` with its claim code, receives
   `{agent_id, agent_secret}` once approved and persists them.

This needs a new panel claim endpoint + an agent pre-enroll poll loop, so it is
deferred. It still needs the control URL known to the agent (one non-secret UI
field, or a build/discovery default).

## Repo responsibilities

| Repo | Phase 1 work |
|------|--------------|
| `pkg-django-lux` (`dlux`) | New *Control Panel* System-Settings tile (control URL field + pairing-code field, Fernet-encrypted transient store); write `agent.enroll` bridge request via `updater/agent_bridge.py`; read `snapshot.json` for status; auto-clear code on success. |
| `app-composer` (agent) | Add `agent.enroll` bridge request handler in `composer/agent.py` that calls the existing `control_client.enroll()`; extend `snapshot` with `enrolled`/`control_url`/`enrolled_at`; keep env bootstrap as fallback. |
| `project-dlux-control` (panel) | *Add application* UI that mints a short-lived single-use pairing code bound to a pending app; existing `/api/agent/v1/enroll/` accepts it as `enrollment_token`. |

## Schemas (Phase 1, additive)

**Bridge request** (DLUX → agent), `requests/<operation_id>.json`:
```json
{ "schema_version": 1, "operation_id": "<uuid4>", "kind": "agent.enroll",
  "control_url": "https://panel.example.org", "pairing_code": "ABCD-1234",
  "requested_at": "<iso8601>" }
```

**Bridge result** (agent → DLUX), `results/<operation_id>.json`:
```json
{ "schema_version": 1, "operation_id": "<uuid4>", "kind": "agent.enroll",
  "state": "ok", "agent_id": "<id>", "enrolled_at": "<iso8601>" }
```
(`state: "error"` carries a sanitized `error` string; never the secret.)

**Snapshot additions** (`snapshot.json`):
```json
{ "enrolled": true, "control_url": "https://panel.example.org",
  "agent_id": "<id>", "enrolled_at": "<iso8601>" }
```

**Enroll HTTP** — unchanged: `POST /api/agent/v1/enroll/`,
body `{schema_version:1, enrollment_token:"ABCD-1234", **capabilities}` →
`{agent_id, agent_secret}`.

## Security model

- Outbound-only boundary preserved; agent still dials the panel.
- Pairing code is short-lived, single-use, and TTL-bound; it only ever grants one
  enrollment for one pending app slot in the panel.
- The code lives transiently: Fernet-encrypted in DLUX until the agent redeems
  it, then deleted. It never lands in `.env`, image layers, or git.
- Durable `{agent_id, agent_secret}` stay only in the `0600` agent store, exactly
  as today. Rotation path unchanged.
- The bridge request file is inside the private `dlux_runtime` volume shared only
  by DLUX web and the agent (same trust domain that already exchanges update
  operations); 64 KiB cap and schema/UUID validation already enforced in
  `agent_bridge.py`.
- Require `https://` control URLs except an explicit `--allow-http-localhost`
  (the flag already exists in `composer/cli.py`).

## Fallback / migration

- Env bootstrap (`COMPOSER_CONTROL_URL` / `COMPOSER_ENROLLMENT_TOKEN`) keeps
  working unchanged — headless/GitOps deploys are unaffected.
- Already-enrolled agents are inert to this feature (durable credentials win in
  `ensure_enrolled()`); the tile just shows **Connected**.
- No DB migration beyond one nullable encrypted settings field for the transient
  pairing code + control URL.

## Open questions

1. Is the control URL ever fleet-wide default/discoverable, or always operator-entered per app?
2. Should the DLUX tile also expose **disconnect** (revoke credentials + tell the panel), and **re-pair**? (Recommended: yes, both.)
3. Phase 2 claim-poll endpoint: unauthenticated-but-rate-limited by claim code, or a coarse pre-shared fleet key?

## Suggested build order

1. Agent `agent.enroll` bridge handler + snapshot fields (`app-composer`) — unblocks everything, testable against a stub panel.
2. Panel *Add application* + pairing-code minting (`project-dlux-control`).
3. DLUX *Control Panel* tile + bridge writer + status/auto-clear (`pkg-django-lux`).
4. Phase 2 claim-code, if desired.
