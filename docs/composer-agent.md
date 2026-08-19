# Composer Agent Integration

Composer is the deployment companion for generated DjangoLux Compose projects. DjangoLux owns application policy, permissions, backups, maintenance state, and update admission. Composer owns external image/package work, container lifecycle, health verification, and the optional outbound control-plane relay.

## Generated topology

The v1.8.0 scaffold runs these Composer services:

| Service | Authority | Network access |
| --- | --- | --- |
| `composer-agent` | outbound registry/control-plane communication and typed local relay | `egress`, `docker_proxy` |
| `composer-executor` | the sole Docker-write authority | `docker_proxy` only |
| `docker-socket-proxy` | read-only Docker API for the agent | `docker_proxy` only |

The agent has no raw Docker socket. It reads through the proxy, which disables `POST` and `EXEC`; typed write requests go through the private `composer_exec_sock` to the isolated executor. Both Composer services run with all capabilities dropped and `no-new-privileges`.

`egress` is deliberately separate from published `frontend`. The public proxy does not share a bridge with services that need outbound access. The internal application network remains isolated for `db`, `redis`, `web`, and `celery`.

`dlux-updater` is not part of the v1.8.0 scaffold. Runtime reconciliation and migrations run as `celery` `pre_start` steps, and Celery Beat handles the small state/intent tick. Do not add the retired service back to a new stack.

## Local bridge and enrollment

The shared `dlux_runtime` volume carries bounded, atomic, schema-versioned JSON documents. DjangoLux writes approved intent and durable state; Composer publishes availability, acknowledgements, deployment status, and agent snapshots. The bridge excludes secrets, environment dumps, unrestricted logs, backup artifacts, and restore commands.

Pair from the superuser Control Panel after first boot. Headless deployments may set:

- `COMPOSER_CONTROL_URL` — public HTTPS control-panel base URL.
- `COMPOSER_ENROLLMENT_TOKEN` — one-use bootstrap token.

Credentials are retained in the private `composer_agent_state` volume after enrollment. The agent has no inbound listener, and local DjangoLux operations continue if the control plane is unavailable or revokes the connection.

## Existing stacks

Run Composer through the generated wrapper:

```bash
./start.sh check
./start.sh check --fix
```

`check` reports missing Composer services, obsolete `dlux-updater` wiring, or runtime-volume drift. Review the proposed change before `--fix`; Composer preserves modified project files under `.xpose/` and validates the resulting Compose configuration. Compose 5.3.0 or newer is required because DjangoLux uses `pre_start` hooks.

For update behavior and recovery, see [Verified Inline Updates](inline-updater.md).
