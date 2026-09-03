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
| `DLUX_CUSTOM_FONTS` | Django setting | `list` or `tuple`, empty | Registers project-owned WOFF2 families. See [Project Configuration](project-configuration.md#themes-and-fonts). |
| `DLUX_CUSTOM_THEMES` | Django setting | `list` or `tuple`, empty | Registers project-owned scoped theme CSS. See [Project Configuration](project-configuration.md#themes-and-fonts). |
| `DLUX_MIDDLEWARE` | Django setting | dotted path, `dlux.middleware.DluxMiddleware` | Selects the middleware inserted by `dlux_settings()`. A compatible replacement must preserve the setup guard and session/security behavior the project needs. |
| `DLUX_SETUP_GUARD_ALLOWED_PREFIXES` | Django setting | iterable of URL prefixes, empty | Allows explicit machine/API paths through the pre-setup guard. It does not bypass authentication on those endpoints. |
| `DLUX_ISOLATE_TEST_CACHE` | Django setting | boolean, `True` | Replaces the default cache with process-local memory during test processes. Set `False` only when a dedicated test cache is already isolated from live sessions and settings. |
| `DLUX_BASE_URL` | Django setting, then `BASE_URL` environment fallback | string, empty | Public URL used by `dlux_doctor` deployment checks. It does not change Django host/origin settings. |

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
Generated Compose deployments configure that relay's upstream provider with the
separate `SMTP_RELAY_HOST`, `SMTP_RELAY_PORT`, `SMTP_RELAY_USE_TLS`,
`SMTP_RELAY_USER`, and `SMTP_RELAY_PASSWORD` environment variables.

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

## Application Version and Inline Updater

| Setting | Source | Type / default | Purpose |
|---|---|---|---|
| `DLUX_LOGOUT_REDIRECT_URL` | Django setting | URL or `reverse_lazy(...)`, unset | Where logging out lands. Unset, dlux decides: the public page when public root access is on, otherwise the login page — both resolved through the URLconf, so a project mounting `dlux.urls` under a prefix such as `/staff/` gets the prefixed path. Set this to override that choice. It exists because dlux rewrites Django's own `LOGOUT_REDIRECT_URL` on every request, so a value a project puts there is replaced before it is ever used; this key is the project's and dlux only reads it. |
| `DLUX_APP_VERSION` | Django setting | version string, discovered | Deployed host application's version, distinct from the DjangoLux package version. Falls back to `VERSION`, then the project release manifest. |
| `DLUX_INLINE_UPDATES_ENABLED` | Django setting or environment through `dlux_settings()` | boolean, `False` | Enables verified inline DjangoLux update checks and operator-approved apply/rollback. Generated Compose projects set it to `True` in `compose.yml`; `compose.dev.yml` overrides it back to `False` on `web` and `celery`, because development runs a bind-mounted source checkout rather than an installed release. |
| `DLUX_UPDATE_EXECUTOR` | Django setting or environment through `dlux_settings()` | `composer` (default) or `inline` | Who performs an approved inline DjangoLux update. `composer` (since 1.8.0) writes a `package-update-request.json` intent that Composer's executor stages, activates and health-gates from outside the container — it can roll back a release that failed to start, which an in-container updater cannot. **This requires Composer running as a service in the deployment** (latest stable image), not only as the deployer; `composer check --fix` installs it. `inline` restores the legacy in-container executor for a deployment whose Composer predates the `dlux.package_update` action — a migration aid with a deadline, not a supported way to run without Composer. Both it and that path are removed in 1.9.0. |
| `DLUX_UPDATE_CHECK_INTERVAL` | Django setting or environment through `dlux_settings()` | integer seconds, `86400`, minimum `300` | Minimum time between persisted update checks. |
| `DLUX_UPDATE_RUNTIME_ROOT` | Django setting or environment | filesystem path, `/opt/dlux-runtime` | Durable runtime release, state, maintenance, and progress root. |
| `DLUX_BAKED_VERSION` | Environment only | version string, package version fallback | Records the DjangoLux version baked into the application image. Generated runtime wrappers populate it. |
| `DLUX_ENVIRONMENT` | Environment only | string, `production` | Environment label included in Composer-agent status snapshots. It does not enable Django debug mode or change security policy. |

Set `DLUX_UPDATE_RUNTIME_ROOT` in the environment for generated deployments.
The Django updater reads the resolved setting, while its standalone container
health probe reads the environment directly; using the same environment value
keeps both pointed at one runtime volume.

See the [Verified Inline Updater](inline-updater.md) for volume ownership,
release verification, maintenance, recovery, and rollback behavior.

## Names That Are Not Deployment Settings

The following names may appear in templates, JavaScript, tests, or historical
documentation, but they are not accepted deployment settings:

- `DLUX_FONTS`, `DLUX_THEMES`, `DLUX_THEME_NAMES`, `DLUX_TABLE_DENSITIES`,
  `DLUX_MODAL_SIZES`, `DLUX_STRINGS`, `DLUX_URL_PREFIX`, `DLUX_URLS`,
  `DLUX_VERSION`, and `DLUX_SHOW_INITIAL_USER_SETUP` are generated runtime
  context values.
- `DLUX_PROJECT_NAME` is ignored.
- `DLUX_CELERY_HEALTH_TTL` was removed when Celery health became an on-demand
  check.

## Deployment Safety

- Never commit secret values to source control or a generated `.env` template.
- Keep `DLUX_UPDATE_RUNTIME_ROOT` on the generated durable volume with the
  documented read/write split.
- Do not use `DLUX_SETUP_GUARD_ALLOWED_PREFIXES` as an authorization mechanism.
- Prefer database System Settings for operator-editable policy and reserve
  top-level deployment settings for infrastructure, secrets, hard limits, and
  code-owned registries.
## Managed asset upload limits

`DLUX_ASSET_MAX_IMAGE_MB` controls the validated image limit and defaults to `10`. `DLUX_ASSET_MAX_FONT_MB` controls WOFF2 uploads and defaults to `20`. Managed files use Django's configured default storage; production deployments must persist or externally host that storage. See [Managed assets](managed-assets.md).
