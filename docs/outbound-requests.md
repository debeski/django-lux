# Outbound Requests: the network rule and the relay

A DjangoLux stack has **one** service with internet access: `composer-agent`.
Everything a project needs from the outside world goes through it, over a small,
typed, audited channel. This page states the rule, the topology it produces, and
how a project developer asks for an outbound call.

> **Requirement.** The relay (`dlux.relay` on the DjangoLux side, `composer relay`
> on Composer's) needs Composer 1.6.0 or later. A stack on an older Composer has no
> relay; see [Stacks without the relay](#stacks-without-the-relay).
> `python manage.py dlux_relay` tells you whether the agent you are running answers.

## The topology

```
   internet
      ^
      |  egress
 composer-agent  <--- runtime volume (files) --->  worker  (writes requests)
      ^                                              |
      | docker_proxy (read-only Docker API)          | Redis / DB   (internal)
 composer-executor  (Docker write authority,         |
                     no egress)                    web  (reads results, never writes)
                                                     |
                                   caddy  <-- frontend --> users
```

| Service | Internet | Writes the channel |
| --- | --- | --- |
| `composer-agent` | yes (`egress`) | results, keys, capabilities |
| `composer-executor` | no | no |
| `worker` | no | requests only |
| `celery` (project-only, on a stack migrated from schema 4) | no | requests only |
| `web` | no | never (read-only mount) |
| `db`, `redis`, `caddy` | no (`caddy` faces users on `frontend`) | no |

`smtp-relay` keeps its own `egress` for outgoing mail and is outside this page.

## The rule

**Project code must not open a network connection to the outside world from `web`
or `worker`** (or a project's own `celery` service on a stack migrated from schema
4). No `requests`, `urllib`, `httpx` or `socket` call to a public host in a view, a
signal, a task or a management command that runs in those containers.
Under `runserver` it will appear to work, which is exactly how it ships broken:
in a generated stack the DNS lookup fails.

If your feature needs something from the internet, it asks the agent through the
relay. The agent makes the call, checks it against a fixed operation, and returns
only the fields the operation defines.

## How a developer asks

1. **Use a built-in operation** when Composer ships one. Composer ships
   `weather.geocode` and `weather.current`, which [Weather](weather.md) uses.
2. **Declare your own** in `relay/operations.json` in the project directory. The
   agent already mounts that directory read-only (`${PWD}:${PWD}:ro`) and `web` and
   `worker` do not, so application code can never widen its own network access, and
   no compose change is needed. Each operation pins one https host (port 443), typed
   parameters, an optional secret, a timeout and size limit, what the response
   returns (`text`, or `json` with only the listed fields), and a rate limit; the
   full schema is in Composer's `docs/relay.md`.

   ```json
   {"schema_version": 1, "operations": [{
     "name": "finance.cbl_page",
     "url": "https://cbl.gov.ly/currency-exchange-rates/",
     "headers": {"User-Agent": "Mozilla/5.0 (my-app)"},
     "response": {"type": "text", "max_bytes": 524288},
     "rate": {"per_minute": 6}
   }]}
   ```

   Run `composer relay approve` (or `./start.sh relay approve`) to pin each
   operation's digest in `relay/operations.lock`, and commit it with the
   declarations. The agent runs only operations whose digest is locked, and a
   reviewer sees every new or changed host in the lock diff. `composer relay list`
   shows what is declared and approved.
3. **Call it from a task or a management command**: a `@dlux.taskrunner.task`
   runs in the task worker (see [Task Runner](task-runner.md)), the process that
   writes relay requests.

   ```python
   from dlux import relay

   html = relay.fetch("finance.cbl_page", timeout=20)                # text operation
   data = relay.fetch("weather.current", {"lat": 32.9, "lon": 13.2}, secret=api_key)
   ```

   `fetch()` writes the request, waits for the agent, and returns the response
   data. On failure it raises `relay.RelayError` with a stable `code`
   (`agent` no answering agent, `unsupported`, `unapproved`, `invalid`,
   `credentials`, `network`, `provider`, `response`, `blocked`, `limit`, `expired`,
   `timeout`, and `writer` for a process that cannot write the channel) and a
   message that names the fix. A `web` request cannot write to the channel: queue a
   task, cache its result, and read the cache in the request, as weather does.

Secrets (API keys, tokens) are never placed on the volume in the clear: `secret=`
is sealed to a public key only the agent holds, bound to that request and operation.

**Tests.** `dlux.relay_testing.FakeAgent(store, {"finance.cbl_page": handler})`
answers relay requests from plain callables so a project's tests never touch the
network or a Composer; it opens sealed secrets exactly as the agent does.
`python manage.py dlux_relay finance.cbl_page` checks a deployment, exiting non-zero
when the agent is not answering or an operation is missing, unapproved or invalid.

## What the agent enforces

Whatever an operation says, the agent applies: https only, verified TLS, exact host
match, no redirects, no IP literals, refusal of loopback, private, link-local
(including the cloud metadata address) and IPv6 equivalents after resolving once and
connecting to that address, parameter patterns, a response size cap, a projection of
the reply, per-operation rate limits, request expiry and a bounded backlog. It
records call counts, status, bytes and duration per operation, never parameters or
secrets.

## Stacks without the relay

On a Composer older than 1.6.0 the agent offers no operations. Update Composer
(`./start.sh self update`, then `./start.sh agent update`) rather than working
around it. Until then, [Weather](weather.md) falls back to calling OpenWeather
from the task worker, which works only if the project put `worker` on the
`egress` network the scaffold already declares. That is a deliberate exception to
the topology above and a stopgap: it lets every task reach the internet. Do not use
the same workaround for new features; ask for an operation instead.
