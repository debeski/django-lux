# Composer Agent Integration

DjangoLux remains the authority for backups, maintenance, monitoring, inline updates, permissions, and durable application state. One outbound `composer-agent` per generated Compose project executes Docker operations and relays only typed local documents. It never receives the raw Docker socket and does not reproduce DLUX behavior.

## Generated topology

New scaffolds include `dlux-updater`, `composer-agent`, and `docker-socket-proxy`. The agent mounts the project at the identical host path read-only, `dlux_runtime` read/write, and `composer_agent_state` read/write. It runs with all capabilities dropped and `no-new-privileges`, joins only the `egress` and isolated `docker_proxy` networks, and reaches Docker through the restricted proxy.

Generated Compose files declare four networks (Compose prefixes each with the
project name, so they never collide across projects):

| Network | Type | Members | Purpose |
| --- | --- | --- | --- |
| `frontend` | bridge | `caddy` | Published ingress and ACME. Only service with `ports:`. |
| `egress` | bridge | `smtp-relay`, `dlux-updater`, `composer-agent` | Outbound internet for the services that need it. |
| `internal` | `internal: true` | `db`, `redis`, `web`, `celery` | Inter-service traffic with no internet route. |
| `docker_proxy` | `internal: true` | `composer-agent`, `docker-socket-proxy` | Sole path to the Docker API. |

`frontend` and `egress` are deliberately separate bridges: Docker blocks
forwarding between them, so a compromised public edge has no L2 route to the
updater or the agent. Attaching one service to both collapses that boundary —
`ComposeNetworkTopologyTests` enforces it.

The normal enrollment path is **Options → Admin panel → Admin commands → Control
Panel**. The dedicated page shows bridge availability and live pairing state,
and uses the native DjangoLux form and notification system. Headless deployments
may instead configure these optional bootstrap values manually:

- `COMPOSER_CONTROL_URL`: public HTTPS base URL of the DLUX control panel; leave empty for local-only operation.
- `COMPOSER_ENROLLMENT_TOKEN`: one-use token created by the panel and valid for 15 minutes.

The UI rejects non-local `http://` control-panel URLs because enrollment returns
long-lived agent credentials. Validation and pairing status use native DjangoLux
flash notifications and do not depend on the optional legacy Django-message
bridge.
- `COMPOSER_AGENT_STATE_DIR`: `/var/lib/composer-agent` in generated deployments.

The enrollment secret is persisted in the dedicated state volume. Local DLUX-triggered updates keep working during control-plane outages and after remote revocation.

## Local typed bridge

The shared spool lives under `/opt/dlux-runtime/state/agent/`:

- `requests/<operation-id>.json`: validated central image-update or backup-create request.
- `results/<operation-id>.json`: durable phase/final result.
- `processed/<operation-id>.json`: handled request archive so the bounded consumer queue keeps advancing.
- `snapshot.json`: current approved versions, image-update state, backup summary/history, database/maintenance health, and resource facts.
- `agent-status.json`: enrollment state plus the resident agent's own `composer_version` (composer >= 1.2.5; legacy `agent_version` is the fallback). DLUX shows this as **Composer (agent)** on the System Diagnostics card and the Control Panel pairing page, distinct from **Composer (deployer)** — the `COMPOSER_VERSION` of the image `./start.sh` runs. The two images pull independently, so they can differ.

Documents are atomic, schema-versioned, and capped at 64 KiB. They exclude credentials, environment dumps, application secrets, unrestricted logs, backup artifacts, and restore instructions.

Central `dlux.image_update` calls the same `queue_image_update()` path as a local request. Inline and image admission serialize on the locked `DluxUpdateState` row, so a container recreate cannot be admitted during an inline migration and only one image update can become active. DLUX must complete the chosen backup before it writes the Composer trigger. Composer success alone is not terminal: the recreated DLUX worker must finalize `DluxImageUpdate`, clear maintenance, and publish the result. Backup failure or DLUX rejection produces no deployment trigger.

Central `dlux.backup.create` accepts only `data` or `full`, uses the operation UUID as the idempotent DLUX backup token, and publishes approved backup status/history. Restore remains project-local.

## Migrating an existing generated project

Pull Composer 1.2.0, then use its guarded, dry-run-first migration:

```bash
./start.sh --update
./start.sh enable-agent
./start.sh enable-agent --apply
```

The dry run prints the exact diff. Apply preserves the original `compose.yml`
under `.xpose/dlux-agent-bootstrap/<timestamp>/`, replaces the recognized
resident updater block, adds `composer_agent_state`, and requires a successful
pre-write `docker compose config`. Review the printed one-time recreate command,
set the control URL/enrollment token, and retain the preserved Compose file until
the project is verified. `python -m dlux enable-agent` remains a deprecated
forwarder for one migration cycle; it does not maintain a second transformer.

`composer watch` remains compatible for one migration cycle. New scaffolds emit only `composer-agent`.
