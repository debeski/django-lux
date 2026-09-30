# Outbound Requests: the network rule and the relay

A DjangoLux stack has **one** service with internet access: `composer-agent`.
Everything a project needs from the outside world goes through it, over a small,
typed, audited channel. This page states the rule, the topology it produces, and
how a project developer asks for an outbound call.

> **Status.** The topology and the rule below describe what the scaffold already
> does. The relay itself (the channel, `dlux.relay`, declared operations) is
> **designed and agreed but not implemented**: until it lands, the only supported
> route out for project code is the interim in "Until the relay ships". Do not
> build against the API sketched here yet.

## The topology

```
   internet
      ^
      |  egress
 composer-agent  <--- runtime volume (files) --->  celery  (writes requests)
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
| `celery` | no | requests only |
| `web` | no | never (read-only mount) |
| `db`, `redis`, `caddy` | no (`caddy` faces users on `frontend`) | no |

`smtp-relay` keeps its own `egress` for outgoing mail and is outside this page.

## The rule

**Project code must not open a network connection to the outside world from `web`
or `celery`.** No `requests`, `urllib`, `httpx` or `socket` call to a public host in
a view, a signal, a task or a management command that runs in those containers.
Under `runserver` it will appear to work, which is exactly how it ships broken:
in a generated stack the DNS lookup fails.

If your feature needs something from the internet, it asks the agent through the
relay. The agent makes the call, checks it against a fixed operation, and returns
only the fields the operation defines.

## How a developer asks (planned)

1. **Use a built-in operation** when Dlux or Composer ships one (weather is the
   first: `weather.geocode`, `weather.current`).
2. **Declare your own** in `relay/operations.json`, deployed with the project and
   mounted read-only into `composer-agent` alone, so application code can never
   widen its own network access. Each operation pins one https host and port, a
   method, typed parameters, an optional sealed secret, a timeout and size limit,
   the response fields it returns, and a rate limit. Run `composer relay approve`
   to record the declaration's digest in a committed `relay/operations.lock`; the
   agent refuses anything not locked, and a reviewer sees each new host in the diff.
3. **Call it** with `dlux.relay.fetch(op, params, secret=None, wait=...)`. In a
   Celery task it writes the request; in a web request it queues a task by name, so
   `web` never writes. Read the result from the cache the way weather does.

Secrets (API keys, tokens) are never placed on the volume in the clear. Dlux seals
them to a public key only the agent holds; see the design notes.

## What the agent enforces

Whatever an operation says, the agent applies: https only, verified TLS, exact host
match, no redirects, no IP literals, refusal of loopback, private, link-local
(including the cloud metadata address) and IPv6 equivalents after resolving once and
connecting to that address, parameter patterns, a response size cap, a projection of
the reply, per-operation rate limits, request expiry and a bounded backlog. It
records call counts, status, bytes and duration per operation, never parameters or
secrets.

## Until the relay ships

Weather is the only feature that needs the internet today, and it makes its calls
in the Celery worker, so a stack that uses it must put `celery` on the network the
scaffold already declares. That is a deliberate exception to the topology above,
and it is why the relay exists. See [Weather](weather.md). Do not use the same
workaround for new features; wait for the relay or ask for an operation.
