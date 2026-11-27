# Deployment Configuration

This is the canonical list of project-facing `DLUX_*` Django settings and
environment variables that DjangoLux reads. It does not list ordinary Django,
database, proxy, or scaffold variables such as `SECRET_KEY`, `BASE_URL`,
`POSTGRES_PASSWORD`, or `TIME_ZONE` unless a `DLUX_*` setting explicitly falls
back to one of them.

## Configuration Layers

DjangoLux configuration has three distinct layers:

1. `DLUX_CONFIG` supplies project-owned runtime defaults from `settings.py`.
2. The database-backed `SystemSettings` singleton overlays UI-managed runtime
   settings such as authentication policy, themes, fonts, layout, and backups.
3. The top-level settings below control deployment behavior, registries, limits,
   secrets, diagnostics, and updater infrastructure. They are not exported in a
   System Settings JSON export.

Call `dlux_settings(globals())` after declaring project overrides. The helper
uses `setdefault`, so explicitly declared Django settings win.

## Core and Registry Settings

| Setting | Source | Type / default | Purpose |
|---|---|---|---|
| `DLUX_CONFIG` | Django setting | `dict`, `{}` | Code-owned defaults layered beneath database System Settings. See [Project Configuration](project-configuration.md#dlux_config). |
| `DLUX_SKIP_CONFIG_IMPORT` | Environment | boolean, unset/false | Skip automatic first-launch `config.json` import in migrator and setup-page requests. Accepts `1`, `true`, `yes`, or `on` (case-insensitive). Keeps manual setup/import available; does not reset configured systems. Composer 1.5.3+ injects it with `--skip-config`; requires DjangoLux 1.9.4+. |
| `ADMIN_PASS` | Environment, read by `migrator` | string, `admin` | Password of the `admin` superuser `migrator` creates when no user of that name exists. |
| `ADMIN_EMAIL` | Environment, read by `migrator` | string, empty | That superuser's email address. Empty leaves the account without one, so no password-reset link goes anywhere until an address is set. |
| `DLUX_MIGRATOR_LOCK_TIMEOUT` | Environment, read by `migrator` | seconds, `900` | How long a `migrator` waits for another one on the same PostgreSQL database. Each run holds a session advisory lock from its first migration to its last setup step, so a second run (two workers' `pre_start` at once) waits, then finds nothing left to do, instead of failing on a table the first created. |
| `DLUX_CUSTOM_FONTS` | Django setting | `list` or `tuple`, empty | Registers project-owned WOFF2 families. See [Project Configuration](project-configuration.md#themes-and-fonts). |
| `DLUX_CUSTOM_THEMES` | Django setting | `list` or `tuple`, empty | Registers project-owned scoped theme CSS. See [Project Configuration](project-configuration.md#themes-and-fonts). |
| `DLUX_MIDDLEWARE` | Django setting | dotted path, `dlux.middleware.DluxMiddleware` | Selects the middleware inserted by `dlux_settings()`. A compatible replacement must preserve the setup guard and session/security behavior the project needs. |
| `DLUX_SETUP_GUARD_ALLOWED_PREFIXES` | Django setting | iterable of URL prefixes, empty | Allows explicit machine/API paths through the pre-setup guard. It does not bypass authentication on those endpoints. |
| `DLUX_VERSIONED_STATIC` | Django setting, read by `dlux_settings()` | boolean, `True` | Swaps Django's default `StaticFilesStorage` for `dlux.static_storage.VersionedStaticFilesStorage`, so `{% static %}` URLs carry `?v=<DjangoLux version>-<project version>` and change with every release (the generated proxy caches `/static/` for a year). Another `staticfiles` backend is kept. Set `False` before `dlux_settings(globals())` to keep Django's storage. See [Project Configuration](project-configuration.md#settings-integration). |
| `DLUX_ISOLATE_TEST_CACHE` | Django setting | boolean, `True` | Replaces the default cache with process-local memory during test processes. Set `False` only when a dedicated test cache is already isolated from live sessions and settings. |
| `DLUX_BASE_URL` | Django setting, then `BASE_URL` environment fallback | string, empty | Public URL used by `dlux_doctor` deployment checks. It does not change Django host/origin settings. |

## Cache outages

| Setting | Source | Type / default | Purpose |
|---|---|---|---|
| `DLUX_CACHE_FAIL_FAST` | Django setting, read by `dlux_settings()` | boolean, `True` | Points every `django_redis.cache.RedisCache` cache at `dlux.resilient_cache.FailFastRedisCache`, caps its timeouts and puts `dlux.cache_outage.CacheOutageMiddleware` just before `SessionMiddleware` in `MIDDLEWARE`. A `SESSION_ENGINE` of `django.contrib.sessions.backends.cache` whose `SESSION_CACHE_ALIAS` names one of those caches becomes `dlux.cache_sessions`. `False` keeps `CACHES`, `MIDDLEWARE` and `SESSION_ENGINE` as the settings file wrote them. Other cache backends are never changed. |
| `DLUX_CACHE_SOCKET_TIMEOUT` | Django setting, read by `dlux_settings()` | seconds, `2` | The highest `SOCKET_CONNECT_TIMEOUT` and `SOCKET_TIMEOUT` a `django_redis` cache keeps. A larger, missing or invalid value becomes this one; a smaller one is kept. It overrides the settings file, which generated projects never regenerate (a generated settings file may still say 5 and 20 seconds). |

Generated stacks run Redis with RDB snapshots (`--appendonly no --save 60 1`), not
an append-only file.
- **Why:** a snapshot is written to a temporary file and renamed into place only when
  complete. A hard power-off or a killed Docker Desktop therefore leaves the last
  good snapshot, and Redis starts again. A half-written append-only file makes Redis
  refuse to start until it is repaired.
- **The cost:** a crash can lose up to about a minute of cache and sessions, so some
  users sign in again. Application data lives in Postgres.
- **Existing stacks:** Composer's `check` reports a stack that still runs Redis with
  an append-only file (`redis-persistence`), and `check --fix` switches it to
  snapshots. It also recovers a Redis that refuses to start on a damaged
  append-only file (`redis-aof-corrupt`). Both need Composer 1.11.0 or later.

Generated stacks keep sessions in the Redis cache, so a Redis that stops answering
takes sign-in with it. What happens then:

- The first cache operation waits at most `DLUX_CACHE_SOCKET_TIMEOUT`. Its failure
  opens a breaker for that cache server in the process, and for the next 10 seconds
  every cache operation fails at once with `dlux.resilient_cache.CacheUnavailable`
  instead of waiting again. One warning on the `dlux.cache` logger names the
  server (without its password) and the error; another says when it answers again.
- Reads that only save work treat the outage as a miss: the System Settings
  singleton, the sidebar and route catalog, the search index and notification
  de-duplication. Pages that need nothing else keep working, from the database.
- Everything else fails: sessions, the login lockout, two-factor codes and their
  cooldowns. Pretending those work would sign people in without a session or
  skip a lockout. `CacheOutageMiddleware` answers such a request with a 503 page
  (JSON for `XMLHttpRequest` and `Accept: application/json`) saying the
  sign-in service is not responding, with `Retry-After: 10`, instead of a 500.
- A request that carries a session cookie is one of them, a page or a panel's
  poll alike. Django's cache session engine would read the outage as a missing
  session and delete the cookie, signing the user out for good;
  `dlux.cache_sessions`, the scaffold's `SESSION_ENGINE` and what `dlux_settings()`
  puts in place of Django's, raises the outage instead. The 503 leaves the cookie
  alone, and the user is still signed in when Redis answers again. Any other
  error reading a session, such as a key the cache refuses, still starts an empty
  session, as Django's engine does.
- `dlux.resilient_cache.safe_get(key, default)`, `safe_set(key, value, timeout)`,
  `safe_add(key, value, timeout)` and `safe_delete(key)` give project code the
  same miss-on-outage behaviour for its own non-critical caching.
- The public-form limiter (`@public_form_limit`) lets a POST through when the
  cache is down, by design; see
  [DSRP-1](security-dsrp-1.md#rate-limiting--session-controls).

Singleton models such as `SystemSettings` are cached as their field values, never
as a pickled model instance, so DjangoLux never unpickles a model another Django
version wrote. Each DjangoLux and Django version keeps its own entry
(`dlux:singleton:SystemSettings:<djangolux>|<django>`), so two versions sharing a
cache do not overwrite each other: the worker health check runs the image's baked
DjangoLux, which can differ from the runtime release beside it. All versions share
the class-name key. Deleting it (`cache.delete("SystemSettings")`) makes every
version's entry a miss, rebuilt from the database, and every save replaces it.
DjangoLux 1.16 and older keep their pickled instance under that key; it is left
in place for them, until a save or its expiry, and never read as the row. When an
image update also changed Django, each process may log Django's "Pickled model
instance" warning once while that instance is there. An entry missing a field a migration
added is a miss with no log line; only an unreadable or malformed entry under the
version's own key logs a warning. Session keys are not versioned: users stay
signed in across an update.

Every save gives the row a new `cache_revision`, in the same statement as its
fields, and the cached entry carries the revision it was written with. Once per
request (on every call outside one) the cached row is checked against the
class-name key and the database, and an entry whose revision no longer matches is
a miss. While DjangoLux 1.16 or older holds the class-name key, its saves set no
revision, so that check compares the row's field values instead, in the same one
query. A save the
cache never saw, because the cache was down, the transaction rolled back or a
racing save wrote its entry last, is therefore served from the next request after
the cache answers again, not when the old entry expires. Code that updates a
singleton row with `QuerySet.update()` instead of `save()` sets a new
`cache_revision` (`uuid.uuid4().hex`) in the same update, or deletes the cached
row afterwards (`cache.delete("SystemSettings")`).

## Database outages

| Setting | Source | Type / default | Purpose |
|---|---|---|---|
| `DLUX_DB_FAIL_FAST` | Django setting, read by `dlux_settings()` | boolean, `True` | Gives every PostgreSQL connection in `DATABASES` a `connect_timeout` and TCP keepalives (`keepalives_idle` 10, `keepalives_interval` 5, `keepalives_count` 3) in `OPTIONS`, keeping any value the settings file sets, and puts `dlux.db_outage.DatabaseOutageMiddleware` just outside the session middleware. `False` keeps `DATABASES` and `MIDDLEWARE` as written. |
| `DLUX_DB_CONNECT_TIMEOUT` | Django setting, read by `dlux_settings()` | seconds, `5` | The `connect_timeout` given to a PostgreSQL connection that sets none. |
| `DLUX_DB_BREAKER_SECONDS` | Django setting, read at connect time | seconds, `5` | After a connection attempt fails in a web process, further attempts in that process fail at once for this long (`dlux.db_outage.DatabaseUnavailable`). `0` turns it off. |

Generated stacks open a database connection per request, so the connect timeout
bounds how long a request waits on a database that does not answer. After one
attempt fails, the web process refuses further attempts for
`DLUX_DB_BREAKER_SECONDS` without waiting, so a page whose reads each tolerate a
missing database pays the timeout once, not once per read. The task worker and
management commands have no breaker and try every time.

`DatabaseOutageMiddleware` answers a request that failed because the database could
not serve it with a 503 page "Database not responding" (JSON for `XMLHttpRequest`
and `Accept: application/json`) and `Retry-After: 15`, instead of a 500. It covers
errors raised in a view and in inner middleware such as the session and
authentication middleware. It counts as an outage: a connection that failed or
closed, SQLSTATE classes `08` (connection), `53` (insufficient resources, such as
"too many clients") and `57` (operator intervention: shutdown, cannot connect now,
statement timeout), and `25006` (read-only transaction). Any other database error,
such as a missing table, stays a 500. The page is built without the database, the
session or System Settings, in the language of `LANGUAGE_CODE`.

The same middleware answers 503 "Restore in progress" while a
[system restore](backups.md#restore) replaces the data.

## Limits and Data Discovery

| Setting | Source | Type / default | Purpose |
|---|---|---|---|
| `DLUX_MAX_PREFERENCES_BYTES` | Django setting | integer bytes, `65536`, minimum `1024` | Maximum serialized size of a user's complete `Profile.preferences` payload. |
| `DLUX_MAX_SYSTEM_APP_CONFIG_BYTES` | Django setting | integer bytes, `65536`, minimum `1024` | Maximum serialized size accepted for one app-owned System Settings namespace write. |
| `DLUX_DLB_UPLOAD_MAX_MB` | Django setting | integer MB, `512`, minimum `1` | Largest `.dlb` the Backup & Restore upload form accepts. The reverse-proxy body limit (`CADDY_MAX_SIZE` / `NGINX_MAX_SIZE`, both `10M` by default) applies first, so raising this alone does not admit a larger file. |
| `DLUX_SEARCH_DATA_MODELS` | Django setting | iterable of `app_label.model`, unset | Restricts global data search to the listed models. Unset uses DjangoLux discovery. |
| `DLUX_SEARCH_DATA_URL_RESOLVER` | Django setting | dotted callable path, unset | Resolves a searched object to its click-through URL. The callable receives the object and returns a URL. |

## Session, Registration, and Two-Factor Controls

| Setting | Source | Type / default | Purpose |
|---|---|---|---|
| `DLUX_SESSION_IDLE_TIMEOUT_SECONDS` | Django setting | integer seconds, `0` | Static sliding-idle timeout. `0` disables it. An enabled database `inactivity_timeout_*` policy takes precedence. |
| `DLUX_SESSION_ABSOLUTE_TIMEOUT_SECONDS` | Django setting | integer seconds, `0` | Hard authenticated-session lifetime. `0` disables it. |
| `DLUX_LOGIN_LOCKOUT_MAX_ATTEMPTS` | Django setting | integer, `5` | Legacy fallback used only if resolved System Settings cannot be read. Normal policy uses `login_lockout_threshold`. |
| `DLUX_LOGIN_LOCKOUT_SECONDS` | Django setting | integer seconds, `900` | Legacy fallback for both counting and lock duration only if resolved System Settings cannot be read. Normal policy uses `login_lockout_window_minutes` and `login_lockout_duration_minutes`. |
| `DLUX_REGISTRATION_TOKEN_TTL_SECONDS` | Django setting | integer seconds, `86400` | Lifetime of a public-registration email-verification token. |
| `DLUX_2FA_CHALLENGE_WINDOW_SECONDS` | Django setting | integer seconds, `300` | Maximum time to finish 2FA after the password step. `0` disables this window. |
| `DLUX_2FA_IP_VERIFY_LIMIT` | Django setting | integer, `20` | Maximum OTP verification attempts per client IP during the verification window. |
| `DLUX_2FA_IP_VERIFY_WINDOW` | Django setting | integer seconds, `600` | Cache window for the per-IP OTP verification limit. |
| `DLUX_2FA_IP_SEND_LIMIT` | Django setting | integer, `10` | Maximum OTP sends per client IP during the send window. |
| `DLUX_2FA_IP_SEND_WINDOW` | Django setting | integer seconds, `3600` | Cache window for the per-IP OTP send limit. |
| `DLUX_PUBLIC_FORM_LIMITS` | Django setting | dict of form bucket to `{'per_address', 'total', 'window'}`, unset | Overrides the limits a `@public_form_limit` view declares, per bucket. `None` turns that limit off; an invalid value is logged and the view's own value applies. See [DSRP-1](security-dsrp-1.md#rate-limiting--session-controls). |

The challenge window and four per-IP 2FA values are read when the two-factor
view module loads. Configure them before Django starts; changing them at runtime
requires a process restart.

## Secret and Email Settings

| Setting | Source | Type / default | Purpose |
|---|---|---|---|
| `DLUX_TOTP_SECRET_KEY` | Environment, then Django setting | secret string | Dedicated encryption seed for stored TOTP secrets. Falls back to environment `DLUX_SECRET_KEY`, then Django `SECRET_KEY`. |
| `DLUX_EMAIL_SECRET_KEY` | Environment, then Django setting | secret string | Dedicated encryption seed for database-stored SMTP passwords. Falls back to environment `DLUX_SECRET_KEY`, then Django `SECRET_KEY`. |
| `DLUX_SECRET_KEY` | Environment only | secret string | Optional shared fallback encryption seed for TOTP and stored email secrets. Prefer the two dedicated keys when independent rotation is required. |
| `DLUX_SMTP_RELAY_HOST` | Django setting | string, `smtp-relay` | Internal SMTP relay host used by DjangoLux when relay transport is selected. |
| `DLUX_SMTP_RELAY_PORT` | Django setting | integer, `1025` | Internal SMTP relay port used by DjangoLux when relay transport is selected. |

Changing an encryption seed makes values encrypted with the previous seed
unreadable. Treat these keys as durable secrets and rotate them only with an
explicit data migration or credential re-entry plan.

The `DLUX_SMTP_RELAY_*` settings identify the application's internal relay.
Generated Compose deployments configure that relay's provider in `.secrets/.env`:

| Variable | Default | Purpose |
|---|---|---|
| `SMTP_RELAY_HOST` | `smtp.gmail.com` | Provider SMTP host. |
| `SMTP_RELAY_PORT` | `587` | Provider SMTP port. |
| `SMTP_RELAY_USE_SSL` | empty | `True` for implicit TLS, `False` for none. Empty follows the port: SSL on 465, otherwise plaintext upgraded by STARTTLS. |
| `SMTP_RELAY_USE_TLS` | `True` | STARTTLS on a non-SSL connection. Ignored when SSL is on. |
| `SMTP_RELAY_USER` | empty | Provider user name. |
| `SMTP_RELAY_PASSWORD` | empty | Provider password. Reaches the `smtp-relay` service only. |
| `SMTP_RELAY_TLS_VERIFY` | `True` | Check the provider's certificate and host name before signing in. `False` accepts any certificate. Environment route only; the Email step has its own switch. |
| `SMTP_RELAY_CA_FILE` | empty | Path, inside `smtp-relay`, of a PEM bundle of CA certificates the relay trusts besides the system CAs. Applies to both routes. |
| `SMTP_RELAY_UPSTREAM_TIMEOUT` | `60` | Seconds one delivery to the provider may take in total, connect to the end of the message, when the Email step sets no timeout. |
| `SMTP_RELAY_MAX_MESSAGE_BYTES` | `10485760` | Largest message accepted (`552` above it). |
| `SMTP_RELAY_MAX_LINE_BYTES` | `1048576` | Longest line accepted. A longer command line gets `500 Line too long` and the connection closes; a longer message line refuses the message with `552` and keeps the session. |
| `SMTP_RELAY_IDLE_TIMEOUT` | `300` | Seconds the relay waits for the next line before it answers `421` and closes the connection. |
| `SMTP_RELAY_MAX_CONNECTIONS` | `100` | Open connections the relay serves at once; one more gets `421 Too many connections`. |

The relay reads the Email step from the database for every delivery, on a fresh
connection, so a database restart costs at most the one delivery in flight.

The relay uses these when the Email step's provider settings are **Environment**,
or when it cannot read the step at all; the step's timeout applies on both routes.
`compose.yml` shares the non-secret values with `web` and `worker` through the
`x-environment` block, so the Email step can show them, and gives them
`SMTP_RELAY_PASSWORD_SET` (`yes` or empty) instead of the password:

```yaml
x-environment:
  SMTP_RELAY_HOST: "${SMTP_RELAY_HOST:-smtp.gmail.com}"
  SMTP_RELAY_PORT: "${SMTP_RELAY_PORT:-587}"
  SMTP_RELAY_USE_TLS: "${SMTP_RELAY_USE_TLS:-True}"
  SMTP_RELAY_USE_SSL: "${SMTP_RELAY_USE_SSL:-}"
  SMTP_RELAY_USER: "${SMTP_RELAY_USER:-}"
  SMTP_RELAY_PASSWORD_SET: "${SMTP_RELAY_PASSWORD:+yes}"
  SMTP_RELAY_TLS_VERIFY: "${SMTP_RELAY_TLS_VERIFY:-True}"
  SMTP_RELAY_CA_FILE: "${SMTP_RELAY_CA_FILE:-}"
services:
  smtp-relay:
    environment:
      SMTP_RELAY_PASSWORD: "${SMTP_RELAY_PASSWORD:-}"
```

Composer's `./start.sh check --fix` brings an existing stack's `compose.yml` to
this shape. The relay process runs the DjangoLux baked into the project image, so
choosing SSL from the port and honouring the Email step's timeout on the
environment route need an image built on DjangoLux 1.16.2 or later; on an older
image, set `SMTP_RELAY_USE_SSL=True` for port 465. A relay delivery failure answers the app
with the failing step (`step=`, `reason=`, `hint=` tokens in its `451` reply) and
logs the same line; a probe or health check that hangs up is not logged.

### Provider certificate

The relay signs in only to a provider whose certificate chains to a trusted CA and
names the host it dialled (`SMTP_RELAY_HOST`, or the host entered on the Email
step), over SSL and STARTTLS alike. Trusted means the image's system CA store, plus
`SMTP_RELAY_CA_FILE` when set. A certificate that fails the check stops the delivery
before any credential is sent; the app reports step `tls`, reason `certificate`,
with a hint naming the CA file and the switch for the route in use.

For a provider whose certificate comes from a private CA, give the relay that CA
instead of switching the check off. The scaffold's `compose.yml` carries the mount,
commented out, under `smtp-relay`:

```yaml
  smtp-relay:
    volumes:
      - ./.secrets/smtp-relay-ca.pem:/etc/dlux/smtp-relay-ca.pem:ro
```

Save the bundle as `.secrets/smtp-relay-ca.pem`, uncomment the two lines, set
`SMTP_RELAY_CA_FILE=/etc/dlux/smtp-relay-ca.pem` in `.secrets/.env` and run
`./start.sh`. A CA file that cannot be read fails every delivery at step `config`,
reason `ca_file`, before the relay connects.

`SMTP_RELAY_TLS_VERIFY=False` (environment route) or clearing **Verify the
provider's certificate** on the Email step (Entered here route) accepts any
certificate, which hands the provider password to whoever answers on that address.
The relay then logs a warning on every delivery, and the CA file is not read. The
check runs in the DjangoLux baked into the project image: it needs an image built on
DjangoLux 1.16.2 or later. `smtp-relay` mounts no runtime volume, so an inline
DjangoLux update reaches web and the worker but not the relay. The relay's greeting
(`220 dlux smtp relay ready cert-check`) names the check; when the greeting lacks
`cert-check`, the Email step says the certificate is not checked and asks for a
project image built on 1.16.2 or later, and Composer's `check` warns
(`relay-version`).

## API Diagnostics

| Setting | Source | Type / default | Purpose |
|---|---|---|---|
| `DLUX_API_STATUS_URL` | Django setting | URL string, empty | Preferred URL for the optional API service health row. |
| `DLUX_API_URL` | Django setting | URL string, empty | Legacy fallback when `DLUX_API_STATUS_URL` is unset. |

Resolution order is `DLUX_API_STATUS_URL`, `DLUX_API_URL`,
`DLUX_CONFIG["api_status_url"]`, then `DLUX_CONFIG["api_url"]`. Optional
`X_API_KEY` and `X_SECRET_KEY` Django settings are sent by the health probe when
configured; they are ordinary project settings, not part of the `DLUX_*`
namespace.

The task worker runs the probe (`dlux.tasks.api_status_probe`, 3-second timeout)
and keeps the answer in the shared cache for ten minutes; web never opens the
connection. Options shows the last answer and queues a new probe when it is a
minute old, so the row lags the endpoint by up to a minute. Before the first
answer the row is `unknown` ("Waiting for the task worker's check", or "No task
worker is running" without a worker; a `DEBUG` development server without a
worker probes from web instead). The URL must be reachable from the `worker`
service, which in a generated stack has no route to public hosts.

## Application Version and Inline Updater

| Setting | Source | Type / default | Purpose |
|---|---|---|---|
| `DLUX_LOGOUT_REDIRECT_URL` | Django setting | URL or `reverse_lazy(...)`, unset | Where logging out lands. Unset, dlux decides: the public page when public root access is on, otherwise the login page — both resolved through the URLconf, so a project mounting `dlux.urls` under a prefix such as `/staff/` gets the prefixed path. Set this to override that choice. It exists because dlux rewrites Django's own `LOGOUT_REDIRECT_URL` on every request, so a value a project puts there is replaced before it is ever used; this key is the project's and dlux only reads it. |
| `DLUX_APP_VERSION` | Django setting | version string, discovered | Deployed host application's version, distinct from the DjangoLux package version. Falls back to `VERSION`, then the project release manifest. |
| `DLUX_INLINE_UPDATES_ENABLED` | Django setting or environment through `dlux_settings()` | boolean, `False` | Enables verified inline DjangoLux update checks and operator-approved apply/rollback. Generated Compose projects set it to `True` in `compose.yml`; `compose.dev.yml` overrides it back to `False` on `web` and `celery`, because development runs a bind-mounted source checkout rather than an installed release. |
| `DLUX_UPDATE_EXECUTOR` | — | **Removed in 1.10.0; ignored** | Composer performs every approved inline DjangoLux update: DjangoLux writes a `package-update-request.json` intent that Composer's executor stages, activates and health-gates from outside the container, so it can roll back a release that failed to start. **This requires Composer running as a service in the deployment** (latest stable image), not only as the deployer; `composer check --fix` installs it. The `inline` value that restored the in-container executor was removed together with that executor. |
| `DLUX_UPDATE_POLICY` | `.secrets/.env`, passed by `compose.yml` to `web`, `worker`, `composer-agent` and `composer-executor`; read through `dlux_settings()` | `all`, `inline` or `none`; default `all`, unknown counts as `none` | Which update paths the deployment allows. Both DjangoLux and Composer 1.11.0+ refuse the others ([Which updates a deployment allows](inline-updater.md#which-updates-a-deployment-allows)). |
| `DLUX_UPDATE_CHECK_INTERVAL` | Django setting or environment through `dlux_settings()` | integer seconds, `86400`, minimum `300` | Minimum time between persisted update checks. |
| `DLUX_UPDATE_RUNTIME_ROOT` | Django setting or environment | filesystem path, `/opt/dlux-runtime` | Durable runtime release, state, maintenance, and progress root. |
| `DLUX_UPDATE_WEB_URL` | Django setting, then environment | URL, `http://web:8000` on a generated stack (`DLUX_STACK_SCHEMA` set), otherwise unset | Where the worker asks `web` which DjangoLux it runs before it reports an inline update complete. The probe is signed with `SECRET_KEY` and bypasses any HTTP proxy. Unset outside a generated stack, so the run log notes that web was not checked. See [What finishes a handed-off run](inline-updater.md#what-finishes-a-handed-off-run). |
| `DLUX_BAKED_VERSION` | Environment only | version string, package version fallback | Records the DjangoLux version baked into the application image. Generated runtime wrappers populate it. |
| `DLUX_ALLOW_INSECURE_SECRET_KEY` | Django setting through `dlux_settings()` | boolean, `False` | Allows a non-DEBUG deployment to boot on an empty or placeholder `SECRET_KEY`. Off by default: both scaffold layers fall back silently (`local_secret` in compose, a dev key in `settings.py`), and a restart that resolves a different key invalidates every session cookie, signing all users out with nothing logged. Set it only for CI or throwaway stacks. |
| `DLUX_STACK_SCHEMA` | Environment, set in `compose.yml`'s `x-environment` | integer, unset on stacks generated before stamping | The stack contract schema the generated stack files were written for. Read only by the `stack.schema` doctor check; changing it changes no behaviour. See [Stack Schema Stamps](stack-schema.md). |
| `DLUX_ENVIRONMENT` | Environment only | string, `production` | Environment label included in Composer-agent status snapshots. It does not enable Django debug mode or change security policy. |

Set `DLUX_UPDATE_RUNTIME_ROOT` in the environment for generated deployments.
The Django updater reads the resolved setting, while its standalone container
health probe reads the environment directly; using the same environment value
keeps both pointed at one runtime volume.

See the [Verified Inline Updater](inline-updater.md) for volume ownership,
release verification, maintenance, recovery, and rollback behavior.

## Background Tasks

| Setting | Source | Type / default | Purpose |
|---|---|---|---|
| `DLUX_TASK_SCHEDULE` | Django setting, merged by `dlux_settings()` | dict of beat-style entries | What `dlux_worker` runs on a schedule: DjangoLux adds its five entries (state tick, stalled-backup reaper, scheduled-backup check, update check, OCR background scan) next to the project's. Entry shape matches `CELERY_BEAT_SCHEDULE` (`task`, `schedule` as seconds, `timedelta` or `crontab`, `args`, `kwargs`, `options.priority`); `dlux.taskrunner.crontab` replaces `celery.schedules.crontab`. |
| `DLUX_TASK_RUNNER` | Django setting | dict, see defaults | Worker tuning: `threads` (4), `queues` (`["default"]`), `express_queues` (`["dlux-mail"]`: served by every worker on one extra thread kept for them, see [Task Runner](task-runner.md#priorities)), `poll_interval` (1 s), `heartbeat_interval` (10 s), `stale_after` (60 s, when a silent worker's runs count as lost), `keep_successful` (1 day) and `keep_failed` (7 days) retention, `max_recoveries` (3), `shutdown_grace` (25 s). |

DjangoLux's own background work always runs on `dlux_worker` (the `worker`
service of a generated stack). See [Task Runner](task-runner.md) for the queue,
retries, recovery and the public task API.

## Names That Are Not Deployment Settings

The following names may appear in templates, JavaScript, tests, or historical
documentation, but they are not accepted deployment settings:

- `DLUX_FONTS`, `DLUX_THEMES`, `DLUX_THEME_NAMES`, `DLUX_ACTIVE_THEME`, `DLUX_TABLE_DENSITIES`,
  `DLUX_MODAL_SIZES`, `DLUX_STRINGS`, `DLUX_STRINGS_URL`, `DLUX_URL_PREFIX`, `DLUX_URLS`,
  `DLUX_VERSION`, and `DLUX_SHOW_INITIAL_USER_SETUP` are generated runtime
  context values.
- `DLUX_PROJECT_NAME` is ignored.
- `DLUX_CELERY_HEALTH_TTL` is ignored: Celery health is checked on demand from
  Options.

## Deployment Safety

- Never commit secret values to source control or a generated `.env` template.
- Keep `DLUX_UPDATE_RUNTIME_ROOT` on the generated durable volume with the
  documented read/write split.
- Do not use `DLUX_SETUP_GUARD_ALLOWED_PREFIXES` as an authorization mechanism.
- Prefer database System Settings for operator-editable policy and reserve
  top-level deployment settings for infrastructure, secrets, hard limits, and
  code-owned registries.
- The generated `Dockerfile` runs `apt-get -y upgrade` before it installs the
  system packages, and removes pip once `requirements.txt` is installed, so the
  image carries Debian's current security fixes and no pip. Nothing in a running
  stack calls pip (Composer unpacks inline releases itself), and image scanners
  flag the packages pip vendors. A project keeps its own copy of the
  `Dockerfile`: matching the scaffold takes those two lines. An image built
  `FROM` the project image that needs pip runs `python -m ensurepip` first.
  Rebuild the project image to pick up fixes published after its last build.

## File permissions

A DjangoLux image can run as a fixed non-root user: uid `10001` with primary
group `0` (`USER 10001:0` in the Dockerfile). Data a root image wrote is
`root:root`, with directories at `0755` and files at `0644`. That user can read
it but cannot create, delete or rename anything in it, so it reaches the data
through group `0`. Only modes change: owners stay root, and a root image keeps
working on the same data.

What the app needs on each mount:

| Mount | Directories | Files |
| --- | --- | --- |
| `media`, `static`, a project's own read-write mounts | read, write, search | read |
| `logs` | read, write, search | read, write (a log handler appends and rotates) |
| Runtime volume (`/opt/dlux-runtime`) | read, write, search on the volume root, its top-level directories and everything under `state/`; read and search below them | read (a file is replaced by renaming a new one over it, never written in place) |
| A read-only mount (`imports`) | read, search | read |

The app and composer-agent share the runtime volume. composer-agent runs as uid
`0` without capabilities, so both sides create directories at `0775` and files
at `0664` there and reach each other's entries through group `0`. The generated
entrypoint sets `umask 0002`.

**Preparing the image.** A project that sets `USER 10001:0` in its own
`Dockerfile` creates every mount point the app containers use, group `0` and
group-writable, before that line. The generated `Dockerfile` carries the same
`RUN`, which changes nothing for a root image:

```dockerfile
RUN mkdir -p /app/imports /app/logs /app/media /app/staticfiles /opt/dlux-runtime \
    && chgrp 0 /app/imports /app/logs /app/media /app/staticfiles /opt/dlux-runtime \
    && chmod g+rwX /app/imports /app/logs /app/media /app/staticfiles /opt/dlux-runtime
USER 10001:0
```

A named volume Docker creates on the first start copies its mount point's owner
and mode from the image, so without this line `static` and the runtime volume
start as `root` `0755` and the worker's gate stops the first start of an empty
deployment.

**The entrypoint gate.** Before it waits for the database, the generated
`entrypoint.sh` runs `python -m dlux.mount_access gate`. Under a non-root uid it
checks the top two levels of every mount under `/app` and of the runtime volume.
If anything the app needs is missing, it stops the container with exit code 78
and names each path; a root process skips the check. `python -m
dlux.mount_access report` prints the whole-tree result as JSON. The doctor's
`storage.mount_access` check reports the same: an error under a non-root uid, and
as root an informational line counting what uid `10001` would still need.

**Granting access.** Composer's `app-permissions` check reports what the app
cannot use, and `./start.sh check --fix` grants it. The grant changes only modes
(the group only on an entry owned by neither group `0` nor the app). It never
follows a link, never leaves the mount's filesystem, and never changes a file
with more than one hard link. Composer runs the same grant before every `up` and
every recreate of an image that runs as a non-root uid, pulling the image first
when it is not on the host yet, and recreates nothing when the image cannot be
read or the grant fails.
Every change is listed in
`.xclude/composer-check/<UTC>/app-permissions/app-permissions.tsv.gz`, and
`./start.sh app-permissions revert <that file>` restores the previous modes of the
entries that still have the granted ones. A deployment without Composer grants
the same bits as root before the first start of a non-root image: `chmod g+rwx`
on the directories in the table, `chmod g+rw` on log files and `chmod g+r` on
any other file the group cannot read.

## Stored files (`/media/`)

Stored files are private by default (stack schema 4). The generated proxy, Caddy or the nginx fallback, serves `/media/` with its own file server. Before it sends anything outside the public folders, it asks DjangoLux at `/sys/files/media-access/` (Caddy `forward_auth`, nginx `auth_request`). DjangoLux answers that URI wherever the project mounts `dlux.urls`, so a project that mounts it under a prefix (`path('staff/', include('dlux.urls'))`) uses the generated proxy blocks unchanged and needs no root alias. The rules (`dlux.files.media`), in order:

| Request | Result |
| --- | --- |
| `dlux_backups/`, `dlux/assets/private/`, `dlux/file_history/`, plus `DLUX_APP_ONLY_MEDIA` and (1.15.5+) any `.dlb` file | Refused to everyone. The app's own views serve these after their checks (backups, installer downloads, file history). |
| `public/`, `dlux/branding/`, `dlux/assets/image/`, `dlux/assets/font/`, plus `DLUX_PUBLIC_MEDIA` | Served to anyone (branding on the login page, managed images and fonts). |
| A registered document file (`register_document_file`) | Served to anyone when its registration's `public(document)` rule returns `True` (a soft-deleted document is never public). Otherwise served only to a signed-in user who reaches the document in its scoped queryset and passes its `view` access check (`can_access`, else `view_<model>`). A case variant of its name is refused. |
| Any other file in the same folder as a registered document file, or a file a history row names exactly (`FileVersion.active_name_before` or `archived_file`, in any folder) | Refused to everyone. A replaced original, a project's own history copy kept beside the documents, or an orphan has no document left to check; history copies are served by the history views. The exact current file of another file field on a document model, such as an attachment, is the exception: it needs a signed-in user. Subfolders are judged by their own contents. |
| Any other stored file | Served to any signed-in user. |

Whatever a rule above would serve is refused when it is a backup (1.15.5+): a file in the folder system backups are written to now (System Settings, Backup, *Automatic export target*, `backup_config.auto_export_target`) or the reports backup folder (`DLUX_CONFIG['reports']['backup_storage_prefix']`), read on each request, or a file a backup record still names after its folder was changed. From 1.15.5 a custom backup folder needs no `DLUX_APP_ONLY_MEDIA` entry; on 1.15.3 and 1.15.4, list it there. The backup folder can't be a public folder, because the proxy serves those without asking: System Settings refuses one, and a stored value that is one falls back to `dlux_backups`. Move any backups already kept in a public folder out of it.

A refusal is a 403 from the proxy. Allowed private files carry `Cache-Control: private, no-cache`, so a browser revalidates each time.

| Setting | Default | Effect |
| --- | --- | --- |
| `DLUX_PUBLIC_MEDIA` | `()` | Extra folders under `MEDIA_ROOT` served to anyone, such as `['products/']` for storefront images. With the default proxy, files there still go through the check, which allows them. |
| `DLUX_APP_ONLY_MEDIA` | `()` | Extra folders never served from `/media/`. Serve them from your own view with `dlux.files.serving.serve_file` after your permission check. |

An entry with a wildcard (`*`, `?` or `[…]`) is a file pattern instead of a folder: `'publication/*.png'` matches the PNG files directly in `publication/`, not those in its subfolders, because each `*` stays within one folder level. Folders and patterns are matched without regard to case. To make a record's file public only while the record is published, use the `public` rule of [`register_document_file`](document-files.md) instead of a pattern.

**Existing stacks (schema 3 or unstamped)** serve every `/media/` file to anyone. The image update doesn't change this, because the proxy file lives in the project:

1. Update DjangoLux to 1.15.3 or later.
2. Run `./start.sh check --fix` with Composer 1.9.2 or later. `composer check` reports the exposure as a `stored-files` failure. The fix rewrites an unmodified generated proxy file to these blocks, validates it, restamps it to 4, archives the original under `.xclude/composer-check/`, and recreates the proxy. It refuses while the running DjangoLux is older than 1.15.3.
3. If the proxy file was edited by hand, Composer reports it and leaves it alone. Copy the `/media/` blocks from the 1.15.3 scaffold's `.proxy/Caddyfile` (or `.proxy/default.conf.template`) into it, restamp it and `compose.yml`'s `DLUX_STACK_SCHEMA` to `4`, then restart the proxy with `./start.sh restart caddy` (or `nginx`). `./start.sh` and `./start.sh update` don't recreate the proxy when only its mounted file changed, so the old rules keep serving until it restarts. Afterwards, check that a private file's `/media/` URL returns 403 when signed out.

Before switching, list any folder your site shows to signed-out visitors (product photos, for example) in `DLUX_PUBLIC_MEDIA`, or move those files under `media/public/`.

Projects that already deny their own folders in the proxy can keep those rules; they don't conflict.

## Cross-site requests (Fetch Metadata)

The generated proxy refuses, with a 403 before the request reaches the app, what another site's page makes a visitor's browser send in the background: images, scripts, `fetch()` calls, form posts and `<object>`/`<embed>` loads. It reads the browser's `Sec-Fetch-*` headers and applies the [resource isolation policy](https://web.dev/articles/fetch-metadata). CSRF tokens, `SameSite=Lax` cookies, `X-Frame-Options`/`frame-ancestors`, `nosniff` and the absence of CORS headers already stop forged changes, framing and cross-origin reads. This policy is the layer that keeps those requests away from the app at all, which also closes cross-site timing and error probes (XS-Leaks).

| Request | Result |
| --- | --- |
| No `Sec-Fetch-Site` header: crawlers, health checks, ScanLink, server-to-server calls, older browsers | Passes |
| `Sec-Fetch-Site` is `same-origin`, `same-site` or `none` (typed in, a bookmark) | Passes |
| A link from another site: `cross-site`, a `GET` or `HEAD` navigation (`Sec-Fetch-Mode: navigate`) to anything but `<object>`/`<embed>` | Passes. An `<iframe>` is a navigation too; `X-Frame-Options` refuses it. |
| Anything else from another site: `no-cors` images and scripts, `cors` fetches, cross-site form posts (`POST` navigations), `<object>`/`<embed>` | 403 from the proxy |

It covers private `/media/` files, `/health` and every route proxied to the app. The routes above it stay open to other sites on purpose, because they are public and served by the proxy itself: `/static/`, the public `/media/` folders, `/_update/status.json` and `/_update/log.txt`, the maintenance page assets under `/_dlux/maintenance/` and `/_edge-alive`. A health check sends no `Sec-Fetch-*` headers, so `/health` keeps working.

Nothing in DjangoLux needs an exemption. SSO redirects back to a client are `GET` navigations. ScanLink's callbacks and its tray app's update checks come from Python, not a browser. The staff page's calls to ScanLink go to the operator's own computer, not to this site. Add one only for a route another site calls from a browser by design, such as an API you open with CORS or, on a DjangoLux SSO provider with browser-based clients, the OIDC token and userinfo endpoints. In the Caddyfile, add the paths to the expression; in the nginx template, give the route its own `location` without the `if ($cross_site_request)` line:

```caddyfile
@cross_site_request expression <<CEL
	{header.Sec-Fetch-Site} == "cross-site"
	&& !(method("GET", "HEAD")
		&& {header.Sec-Fetch-Mode} == "navigate"
		&& !({header.Sec-Fetch-Dest} in ["object", "embed"]))
	&& !path("/o/token/", "/o/userinfo/")
	CEL
```

Two stricter rules that security scanners suggest would break things. Requiring `Sec-Fetch-User` blocks crawlers, health checks and links a script follows. Allowing only navigations to reach HTML pages breaks the app's own same-origin `fetch()` calls, such as search as you type.

**The block.** New projects get it from `python -m dlux startproject` (stack schema unchanged). In `.proxy/Caddyfile` it sits inside the site's `route`, after the public media handler and before the private `/media/*` handler:

```caddyfile
		@cross_site_request expression <<CEL
			{header.Sec-Fetch-Site} == "cross-site"
			&& !(method("GET", "HEAD")
				&& {header.Sec-Fetch-Mode} == "navigate"
				&& !({header.Sec-Fetch-Dest} in ["object", "embed"]))
			CEL
		respond @cross_site_request 403
```

The nginx fallback (`.proxy/default.conf.template`) maps the same rule next to its other `map`, then refuses it first thing in the `location /media/`, `location /` and `location /health` blocks:

```nginx
map "$http_sec_fetch_site:$request_method:$http_sec_fetch_mode:$http_sec_fetch_dest" $cross_site_request {
    default                                             0;
    "~^cross-site:(GET|HEAD):navigate:(object|embed)$"  1;
    "~^cross-site:(GET|HEAD):navigate:"                 0;
    "~^cross-site:"                                     1;
}

    location / {
        if ($cross_site_request) { return 403; }
        ...
```

**Existing stacks.** `composer check` reports a `fetch-metadata` warning for each proxy file in `.proxy/` without the policy. It looks for the name `cross_site_request`: in the Caddyfile, a `@cross_site_request` matcher and `respond @cross_site_request 403`; in the nginx template, the `$cross_site_request` map and `if ($cross_site_request) { return 403; }`. Comments and the expression's formatting don't matter, but keep the name. Copy the block above into the file, then run `./start.sh restart caddy` (or `nginx`). `./start.sh` alone doesn't reload a changed proxy file. To check it afterwards:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -H 'Sec-Fetch-Site: cross-site' -H 'Sec-Fetch-Mode: no-cors' -H 'Sec-Fetch-Dest: image' https://your-site/
```

That prints `403`. The same request with `-H 'Sec-Fetch-Mode: navigate' -H 'Sec-Fetch-Dest: document'` instead, or with no `Sec-Fetch-*` headers, reaches the app.

## Managed asset upload limits

`DLUX_ASSET_MAX_IMAGE_MB` controls the validated image limit and defaults to `10`. `DLUX_ASSET_MAX_FONT_MB` controls WOFF2 uploads and defaults to `20`. `DLUX_ASSET_MAX_INSTALLER_MB` controls protected installer uploads and defaults to `200`. Managed files use Django's configured default storage; production deployments must persist or externally host that storage. See [Managed assets](managed-assets.md).
