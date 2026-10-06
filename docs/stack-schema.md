# Stack Schema Stamps

Every non-Python file `dlux startproject` generates for the deployment stack
records the **stack contract schema** it was written for. It is one number: the
`schema_version` of `dlux/contracts/stack.json`, which defines the services,
networks, mounts, invariants and `.env` keys of the generated stack.

The stamp is the contract schema, not the DjangoLux version. These files change
only when the contract does, so a version stamp would only say when a file was
generated. The schema number says whether it still matches the contract the
running DjangoLux expects. Generated Python files already name the DjangoLux
version that wrote them (`Generated with django-lux X.Y.Z.`).

## Where the stamp lives

| File | Stamp |
| --- | --- |
| `compose.yml` | `DLUX_STACK_SCHEMA: "N"` in the shared `x-environment` block, so it also reaches `web`, `celery`, `db` and `smtp-relay` |
| `Dockerfile` | `LABEL org.dlux.stack-schema="N"` (readable with `docker image inspect`) |
| `compose.dev.yml`, `entrypoint.sh`, `gunicorn.py`, `.secrets/.env`, `.proxy/Caddyfile`, `.proxy/default.conf.template` | `# dlux stack schema N` header comment |
| `.proxy/maintenance.html` | `<!-- dlux stack schema N -->` |

Not stamped: `start.sh` / `start.ps1`, which Composer owns and versions with its
own `# composer-wrapper: N` marker, and `.gitignore`, `.dockerignore` and
`.gitattributes`, which nothing depends on.

`dlux.contracts.stack.read_stamp(text)` parses all three spellings and returns
the number or `None`; `stack_schema()` returns the running contract's number.
Both are dependency-free so Composer can read host-side files with the same rule.
`STACK_SCHEMA_ENV` and `STACK_SCHEMA_LABEL` name the environment key and label.

## What reports it

`dlux_doctor` check `stack.schema` (group `services`) reads `DLUX_STACK_SCHEMA`
from the app container's environment, which comes from `compose.yml`:

| Situation | Status |
| --- | --- |
| No `DLUX_STACK_SCHEMA` (stack generated before stamping) | `skipped`, informational |
| Matches the running contract | `ok` |
| Older or newer than the running contract, or not a number | `warning`, pointing here |

It never reports `error`. A mismatch means the stack files need the changes
below, not that the site is down. The doctor cannot read the other stamped files
because `.dockerignore` keeps them out of the image. Checking those belongs to
Composer's host-side `composer check`, which does not read stamps yet.

## Bumping the schema

Bump `schema_version` in `dlux/contracts/stack.json` when a change renames a
contract field or changes what an invariant means, or when existing generated
files need editing to match the contract. Adding a service or key that old files
can simply lack does not need a bump. The scaffold test
`test_every_stack_file_is_stamped_with_the_contract_schema` keeps every template
on the current number, and each bump adds a row below.

## Changes by schema

| Schema | Since | Change to existing stacks |
| --- | --- | --- |
| 2 | 1.7.0 | Each DjangoLux-owned service's command module is part of the contract; the retired `tools.smtp_relay` and `tools.dlux_runtime_supervisor` entrypoints must be replaced (`composer check --fix` does this). |
| 1 | — | Initial contract: services, networks, single ingress, Docker socket rule, `dlux_runtime` read/write split. |

Stacks generated before stamping carry no number. Their `compose.yml` is still
compared with the contract by `composer check`. To stamp one by hand, add
`DLUX_STACK_SCHEMA: "2"` to its `x-environment` block once it passes that check.
