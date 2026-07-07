# Reference

This page is the fast lookup sheet for common DjangoLux commands, routes, template tags, and helper utilities.

## Scaffold Commands

| Command | Purpose |
| --- | --- |
| `python -m dlux startproject myproject` | Create a new DjangoLux-ready Django project. |
| `python -m dlux startapp billing` | Create a new DjangoLux-native app in the current project. |
| `python -m dlux startapp billing --register` | Create the app and also patch project settings and URLs. |
| `python -m dlux enable-updater` | Dry-run the guarded inline-updater bootstrap for an existing generated Compose project. |
| `python -m dlux enable-updater --apply` | Preserve changed originals under `.xpose/`, apply idempotent updater wiring, validate with `docker compose config`, and print the one-time rebuild command. |

Generated project baseline:
- `.secrets/.env` with scaffolded bootstrap secret values
- `config/settings.py` wired for env-driven Django secret, Postgres, Redis cache, and Celery
- `config/settings.py` wired with `corsheaders` / `csp`, their middleware, and starter CORS/CSP settings
- `compose.yml` and `compose.dev.yml` keeping the standard inline-env pattern
- a generated Docker baseline with `web`, `celery`, `dlux-updater`, `db`, `redis`, `nginx`, `pgadmin`, database backup, and internal `smtp-relay` services
- `requirements.txt` pinned to the generated stable `django-lux` release
- a persistent `dlux_runtime` volume, project-owned process supervisor, and static nginx maintenance page

Generated app scaffold baseline:
- discovery-friendly `models.py`, `forms.py`, `filters.py`, `tables.py`, `views.py`, `urls.py`, `translations.py`, templates, and tests
- optional `--register` patching for `INSTALLED_APPS` and root project URLs
- modal/list conventions that align with Dlux discovery, sections, and table/filter helpers

## Management Commands

| Command | Purpose |
| --- | --- |
| `python manage.py dlux_setup` | Create migrations, apply migrations, and run the config check. |
| `python manage.py dlux_setup --skip-check` | Skip the validation pass after setup. |
| `python manage.py dlux_setup --no-migrate` | Skip `makemigrations` and `migrate`. |
| `python manage.py dlux_setup --skip-configure` | Do not append the `dlux_settings(globals())` helper to the active settings module. |
| `python manage.py dlux_check` | Validate apps, middleware, context processors, URLs, and Crispy settings. |
| `python manage.py dlux_settings status` | Inspect the `SystemSettings` singleton without creating it. |
| `python manage.py dlux_settings configure` | Mark the singleton configured without replacing its values. |
| `python manage.py dlux_settings unconfigure` | Preserve settings but mark setup incomplete so `/sys/setup/` opens again. |
| `python manage.py dlux_settings delete --yes` | Delete the singleton row; the next load recreates it. |
| `python manage.py dlux_settings reset --yes` | Recreate the singleton from model defaults and mark it unconfigured. |
| `python manage.py dlux_settings export --output config.json` | Export portable System Settings JSON. |
| `python manage.py dlux_settings import --input config.json` | Import portable System Settings JSON and mark setup configured. |
| `python manage.py dlux_prune_activity_log --dry-run` | Preview log rows outside configured category retention windows. |
| `python manage.py dlux_prune_activity_log` | Delete rows outside configured category retention windows. |
| `python manage.py dlux_migrate_from_microsys` | Dry-run the supported Microsys 2.4.1 database relabel. |
| `python manage.py dlux_migrate_from_microsys --yes` | Apply the database relabel after an external backup. |
| `python manage.py dlux_update_worker` | Internal generated-Compose update worker; normally started only by `dlux-updater`. |
| `python manage.py migrator` | Internal generated-project migration/static/bootstrap command used by Compose startup. |

## Optional SSO Packages

| Package | Purpose |
| --- | --- |
| `django-lux-sso` | Optional OIDC provider plugin for a standalone Dlux SSO deployment. |
| `django-lux-sso-client` | Lightweight Django client SDK for connected projects; does not depend on `django-lux`. |

The provider is cross-platform OIDC. Non-Django projects should use their normal
OIDC library and the provider discovery document:

```text
https://sso.example.com/o/.well-known/openid-configuration/
```

Portable client role claim: `dlux_sso_role`.

Provider integration is explicit:

```python
from dlux_sso.settings import dlux_sso_settings

dlux_sso_settings(globals())
```

Client integration is explicit:

```python
from dlux_sso_client.settings import configure_dlux_sso

configure_dlux_sso(
    globals(),
    issuer_url="https://sso.example.com",
    client_id="client-id",
    client_secret="client-secret",
)
```

See [Optional SSO Packages](sso.md), [Public Registration Playground](registration.md), and [DSRP-1 Security Standard](security-dsrp-1.md).

## Core Routes

| Route | Purpose |
| --- | --- |
| `/accounts/login/` | Login screen |
| `/accounts/logout/` | Logout |
| `/accounts/register/` | Public registration form; returns 404 unless enabled |
| `/accounts/register/sent/` | Generic registration email-sent response |
| `/accounts/register/verify/<token>/` | Email verification endpoint for hashed-token registrations |
| `/accounts/profile/` | User profile |
| `/accounts/profile/sessions/<session_key>/revoke/` | POST-only revocation for one of the current user’s signed-in sessions |
| `/health/` | Django health-check endpoint for readiness checks |
| `/sys/setup/` | First-launch setup language gate and system setup wizard |
| `/sys/options/` | Options view |
| `/sys/users/` | User management |
| `/sys/registrations/` | Superuser-only pending public registration approvals |
| `/sys/registrations/<int:pk>/approve/` | POST-only public registration approval |
| `/sys/registrations/<int:pk>/reject/` | POST-only public registration rejection |
| `/sys/reset_password/<int:pk>/` | Staff password-reset endpoint for a target user |
| `/sys/logs/` | Activity log |
| `/sys/logs/<int:pk>/details/` | Activity log detail modal |
| `/sys/reports/` | Activity reports overview |
| `/sys/reports/backup.zip` | Permission-gated report backup ZIP |
| `/sys/backup/` | Superuser-only full system backup and restore page |
| `/sys/backup/create/` | Create an encrypted `.dlb` system backup |
| `/sys/backup/upload/` | Upload an encrypted `.dlb` for restore |
| `/sys/backup/restore/` | Start a system restore from an uploaded or existing `.dlb` |
| `/sys/scopes/manage/` | Scope management |
| `/sys/groups/manage/` | Permission group / preset management (requires `dlux.manage_groups`) |
| `/sys/groups/<int:pk>/members/` | Preset membership modal + who/which/when history |
| `/sys/sections/` | Section management |
| `/sys/api/dlux-update/runtime-health/` | HMAC-authenticated internal-process version health response used directly by the update worker |

Section security contract:

- `/sys/sections/`, `/sys/section/details/`, `/sys/section/delete/`, and subsection CRUD endpoints require the existing section permissions
- section detail/delete and subsection CRUD no longer accept arbitrary `model=` tokens; the target must be a discovered Dlux section or discovered section child model
- `/sys/users/` plus the user-detail page/modal require `auth.view_user` for staff users (superusers still bypass)
- `/sys/reset_password/<int:pk>/` now requires `auth.change_user` and the same staff/scope/superuser target checks as the hardened user-management modal routes. Reset submissions are rejected if the new password matches the target user's current password.
- the create-user modal can mark a new account with `profile.preferences["force_password_change"]`; `DluxMiddleware` then redirects that user to `/accounts/profile/?force_password_change=1` until the profile password-change form succeeds and clears the marker. While this marker is active, the first-login Initial User Setup auto-modal is deferred so the password-change requirement remains the only blocking first action. The forced change must set a password different from the current one.
- `/sys/logs/` and `/sys/logs/<int:pk>/details/` now require the explicit `dlux.view_activitylog` permission or superuser status rather than plain `is_staff`
- embedded activity snippets on user-detail surfaces only render when the caller also has `dlux.view_activitylog`
- sidebar-discovered system routes plus the built-in dashboard/user-hub shortcuts now mirror those same helper-backed checks instead of older template-only `is_staff` assumptions
- sidebar items are only visible to users with the required view permission; no implicit staff fallback (see Sidebar Permission Inference below)

Backup export contract:

- report ZIP and full system `.dlb` exports use primary-key pagination plus a backup-local JSON serializer, so PostgreSQL deployments do not need Django server-side named cursors for export streaming
- system backup rows, report backup rows, system restore rows, updater runtime state/run rows, sessions, content types, permissions, and admin log entries remain excluded from full `.dlb` payloads
- `.dlb` payloads are encrypted in chunked Fernet frames and include a manifest with Dlux version, migration state, model counts, file counts, and omitted-superuser-password policy
- superuser password hashes are omitted from system backups and preserved from the target database during restore

## 2FA Routes

| Route | Purpose |
| --- | --- |
| `/sys/2fa/enable/` | Start enabling a 2FA method |
| `/sys/2fa/setup/totp/` | Generate a TOTP secret and QR code |
| `/sys/2fa/verify/login/` | Verify OTP during login |
| `/sys/2fa/verify/enable/` | Verify OTP during 2FA enable flow |
| `/sys/2fa/disable/` | Disable a 2FA method |
| `/sys/2fa/backup-codes/generate/` | Generate backup codes |
| `/sys/2fa/resend/<intent>/` | Resend an OTP |

2FA security contract:

- `/sys/2fa/enable/`, `/sys/2fa/setup/totp/`, `/sys/2fa/disable/`, `/sys/2fa/backup-codes/generate/`, and resend endpoints are POST-only mutators
- backup codes are stored hashed in `Profile.backup_codes`
- login 2FA redirects validate `next` against allowed hosts before redirecting
- destructive profile-side 2FA actions such as disable, backup-code regeneration, and session revocation require the current-password guard on the backend
- Profile can trust the current browser after current-password confirmation; untrusted sessions cannot revoke trusted sessions
- when `prevent_multiple_active_sessions` is enabled, each newly authenticated session revokes every other active session for that user; the older browser is redirected to the session-ended page on its next request
- email 2FA supports auto-send on login and 120s resend cooldown to reduce authentication friction
- TOTP setup persists secret/enabled state through `set_profile_totp_state(...)` instead of the full `Profile.save()` path, so unrelated profile-save side effects do not block authenticator setup

## API Endpoints

### Autofill

| Route | Method | Purpose |
| --- | --- | --- |
| `/sys/api/last-entry/<app>/<model>/` | `GET` | Return the most recent record for sticky-form cloning |
| `/sys/api/details/<app>/<model>/empty_schema/` | `GET` | Return an empty field structure for clearing autofill targets |
| `/sys/api/details/<app>/<model>/<pk>/` | `GET` | Return serialized model details for autofill |

Autofill security contract:

- detail/autofill serialization now returns only direct fields of the requested model
- reverse OneToOne expansion such as `user.profile.*` is intentionally excluded
- reads use the model default manager so scoped query behavior is preserved

### Preferences

| Route | Method | Purpose |
| --- | --- | --- |
| `/sys/api/preferences/update/` | `POST` | Merge updated preference values into `Profile.preferences` |
| `/sys/api/preferences/reset/` | `POST` | Clear saved preferences and related session keys |

### Notifications

| Route | Method | Purpose |
| --- | --- | --- |
| `/sys/api/notifications/` | `GET` | Return the current user’s notification drawer items and unread count |
| `/sys/api/notifications/<pk>/read/` | `POST` | Mark one notification state as read for the current user |
| `/sys/api/notifications/<pk>/dismiss/` | `POST` | Mark one notification state dismissed for the current user |
| `/sys/api/notifications/read-all/` | `POST` | Mark all current-user notification states as read |
| `/sys/api/notifications/clear-all/` | `POST` | Dismiss read current-user notification states from the drawer |

### Verified Inline Updater

| Route | Method | Access/Purpose |
| --- | --- | --- |
| `/sys/api/dlux-update/state/` | `GET` | Superuser/Global Staff read-only updater state and latest run |
| `/sys/api/dlux-update/runs/<token>/` | `GET` | Superuser durable run status and bounded progress log |
| `/sys/api/dlux-update/check/` | `POST` | Superuser-only CSRF-protected official PyPI check |
| `/sys/api/dlux-update/apply/` | `POST` | Superuser + current-password verified apply request |
| `/sys/api/dlux-update/rollback/` | `POST` | Superuser + current-password verified rollback request |
| `/sys/api/dlux-update/runtime-health/` | signed `GET` | Internal updater-to-web active-version probe; unauthenticated external requests return 404 |

Generated projects set `DLUX_INLINE_UPDATES_ENABLED=True`,
`DLUX_UPDATE_CHECK_INTERVAL=86400`, and
`DLUX_UPDATE_RUNTIME_ROOT=/opt/dlux-runtime`. Other deployments default to
disabled. The update index is fixed to official PyPI and is not configurable in
v1. See [Verified Inline Updater](inline-updater.md).

Dlux Notifications replace Dlux-owned uses of Django message storage with a durable, inferred event pipeline. Public API:

```python
from dlux.notifications import notify

notify("Invoice approved.")
notify.success("Saved.")
notify.error("Could not delete record.", obj=record)
notify("Backup completed.", action="backup_complete", target_url="/sys/backup/")
notify.success(message_key="msg_password_changed")
```

Optional routing stays compact:

```python
notify(
    "Payroll batch exported.",
    obj=batch,
    action="export",
    category="reports",
    to="watchers",
    email=True,
)
```

For language-aware Dlux-owned notices, pass `message_key` and optional `title_key` values from `DLUX_STRINGS`. The stored `DluxNotification.message` remains a fallback for history/email, while flash notices, the titlebar drawer, and `/sys/api/notifications/` resolve keyed text in the active request language at render time. Legacy rows without metadata also rerender when the stored text exactly matches a known Dlux/app/project translation value; interpolated and free-form messages remain stored text.

Notification data model:

- `DluxNotification(ScopedModel)`: durable event content, level, category, source/action, source model/object metadata, target URL, request path, metadata, audience type, and expiry.
- `DluxNotificationState`: per-user read/dismiss/email state for each delivered notification.
- `DluxNotificationRule(ScopedModel)`: JSON match/delivery rules for persist/flash/badge/email/recipient routing.
- `DluxNotificationWatch(ScopedModel)`: model-level watches per user/scope; object-level watches are intentionally deferred.

Automatic behavior:

- `ScopedModel` create/update/delete events are notification-capable by default unless the model sets `dlux_notify = False`.
- Updates use the activity-log diff payload, including existing sensitive-field masking, and default to quiet persisted summaries rather than flash.
- Generic modal/context-menu CRUD attaches route/surface metadata before the signal pipeline emits the event.
- Activity logs remain the audit source; notifications are user-facing delivery records that may link to activity metadata.

Model tuning:

```python
class Invoice(ScopedModel):
    dlux_notify = {
        "watchable": True,
        "update": "summary",
        "flash": ["create", "delete"],
    }


class TempCalculation(ScopedModel):
    dlux_notify = False
```

System Settings store `notification_config` with:

- `enabled`: top-level master gate (default on), edited via the dedicated **Notifications** settings step (`?step=7`). When off, `emit_notification_event()`, `get_flash_notifications()`, and `get_notification_context()` short-circuit, suppressing flash notices, the titlebar drawer/badge, emails, automatic CRUD notifications, and `notify(...)` — the same enable/disable pattern as the sidebar and nav bar.
- `flash`: `enabled`, `position`, `size`, `text_size`, `timeout_ms`, `max_visible`
- `drawer`: `enabled`, `badge_enabled`, `preview_limit`
- `bridge.django_messages_enabled`: optional compatibility bridge for host-project Django messages
- `email.enabled/default`: `enabled` is the master gate for notification email and remains disabled/server-coerced off unless Dlux email delivery is configured; `default` emails eligible persisted notifications only after that gate is on
- `retention.default_expiry_days`
- `automatic.scoped_model_crud`: master switch for automatic `ScopedModel` CRUD notification sources
- `automatic.create/delete`: per-action gates under the automatic CRUD source
- `automatic.update`: `off`, `summary`, or `full`; summary emits quiet changed-field summaries and full keeps richer update metadata
- `automatic.actor_flash_actions/watchable`: actor flash defaults and model-watch support

DEBUG-only internal test trigger:

- `/sys/debug/notifications/` creates test notifications for the current superuser/global-staff user when `settings.DEBUG` is true; outside DEBUG it returns 404.
- Query examples: `?level=success`, `?level=all`, `?persist=0`, `?flash=0`, `?next=/sys/options/`.

### Titlebar User Hub Styles

System Settings store titlebar layout in `titlebar_config`:

- `user_hub_style`: `dropdown` (default) or `titlebar_actions`
- `actions_order`: ordered rail keys; defaults to `notifications`, `home`, `profile`, `help`, `users`, `activity`, `reports`, `settings`, `auth`

`dropdown` preserves the current notification/home/user-trigger layout and `dlux/users/user_hub.html` dropdown. `titlebar_actions` suppresses the dropdown card and renders available shortcuts as `.dlux-titlebar-action` buttons using the shared `titlebar.buttons_shape` setting. Runtime gates are unchanged for users/activity/reports; hidden home and disabled notification drawer settings omit those actions. Authenticated logout is always a POST form with CSRF.

### Activity logging (`log_config`)

`ActivityLog` (formerly `UserActivityLog`; the old name remains importable as an alias)
is the single source of truth for all logs. Every row carries a `category`:

- `user` — project work and dev-invoked logs (auto-discovered project/auxiliary models).
- `system` — dlux-internal events (`app_label == 'dlux'`, backups, etc.).
- `audit` — security events (login success/failure, logout, lockout, 2FA
  enable/disable/failure, password change, session & trusted-device revoke, permission
  denied). Audit rows are **append-only** (cannot be edited/deleted in-app) and are never
  auto-pruned by default.

`log_config` (Step 10 of the setup wizard) governs logging:

- `enabled` — master switch (does not gate audit).
- `user` / `system` — each has `enabled`, `default_actions` (`create`/`update`/`delete`),
  `retention_days` (0 = keep forever), and a sparse `models` override map keyed by
  `"app_label.model"` supporting per-action sub-toggles.
- The system list carries a synthetic **User accounts** entry (`dlux.useridentity`)
  controlling the unified User+Profile identity log — user accounts are a core dlux
  component, so identity rows are stored under the `system` category.

Only models that produce meaningful logs appear in the grid — Django framework internals
(`auth`/`sessions`/`contenttypes`/`admin`), health-check/`testmodel` models, and dlux
operational/identity/self/dummy models (devices, presence, notifications, backups, Profile,
ActivityLog, the fieldless Section placeholder) are hard-excluded.

**Custom actions:** actions beyond `create`/`update`/`delete` (e.g. `DOWNLOAD`, `EXPORT`,
`APPROVE`) are **logged by default** with no configuration. To surface a toggle for one in
the settings grid, declare it on the model:

```python
class Decree(ScopedModel):
    dlux_log_actions = ["download", "export"]   # adds per-action toggles in Step 10
```

A dev can then disable a specific action via its per-model `actions` override
(`{"download": false}`) without affecting CRUD. Security-sensitive account actions (password
reset, 2FA, lockouts) are logged under `audit`, not the per-model grid.
- `audit` — `enabled` (always on), per-event `events` flags, `immutable`, and its own
  `retention_days`.

A correctness floor (`LOG_FORCED_EXCLUDED_MODEL_KEYS`) — Session and other
non-integer-PK/bookkeeping tables — is never logged regardless of config.

Custom dev logging (zero boilerplate):

```python
from dlux import log_activity
log_activity("APPROVE", obj)                       # instance form
log_activity("EXPORT", pk, model="documents.decree")  # pk + model form
```

It resolves model/scope/actor/IP from the current request, defaults to the `user` category,
and honours `log_config` gating.

Retention is enforced by the `dlux_prune_activity_log` management command (deletes
`user`/`system` rows past their `retention_days`; skips `audit` unless its
`retention_days > 0`; supports `--dry-run`). The `/sys/logs/` view shows user/system/audit
tabs (`?category=`); the audit tab is restricted to superusers/global staff.

### Profile page + onboarding (`profile_config`)

`profile_config` (Step 11 of the setup wizard) governs the user profile page and the
first-login experience — it is **not** personalization defaults (those stay in
theme/typography/layout/language configs) and **not** per-user prefs (those live in
`Profile.preferences`):

- `show_completion_widget`, `show_session_device_cards`, `show_activity_feed` — gate the
  matching profile-page sections. The profile activity feed shows at most the latest five
  project activity entries and latest five system interaction entries.
- `security_nudges` — `off` / `subtle` / `persistent` (account-health prompt for missing 2FA).
- `allow_user_home_url` — let users pick their own landing page (stored as
  `Profile.preferences['user_home_url']`; honoured at login after an explicit `?next` and
  before the system `home_url` via `resolve_user_home_url()`).
- `onboarding_enabled` + `onboarding_options` (`theme`/`language`/`fonts`) —
  whether the first-login modal runs and which preferences it offers.
  `allow_user_home_url` independently controls whether the same modal and the
  Options page expose the permission-filtered landing-page selector.

The three landing-page values share the `*_url` family: `home_url` (system default,
public `DLUX_CONFIG` key), `public_root_url` (anonymous public landing, in
`public_root_config`), and `user_home_url` (per-user, in `Profile.preferences`).

**Initial User Setup** is the per-user first-login counterpart to the system setup wizard: a
lightweight dlux dynamic modal (`/accounts/welcome/`, `initial_user_setup`) that auto-opens
once per user when `onboarding_enabled` and the user's `Profile.is_configured` is false. It
writes the chosen theme/language/fonts (+ optional home override) into `Profile.preferences`
and sets `Profile.is_configured`; "Skip for now" just sets the flag. The auto-open trigger is
gated by the `DLUX_SHOW_INITIAL_USER_SETUP` context flag, and is suppressed while
`Profile.preferences["force_password_change"]` is active so a first-login password change
always happens before optional onboarding preferences.

### Full-system backup policy (`backup_config`)

`backup_config` (Step 12) is the DB-backed policy consumed by the full `.dlb`
backup subsystem:

- `scheduled_enabled` — opt in to Celery-beat scheduling (off by default).
- `schedule_interval_hours` — due interval, from 1 through 8760 hours; beat polls every 15 minutes.
- `retention_days` — remove completed backups older than this age; `0` keeps indefinitely.
- `max_backups_to_keep` — retain the newest completed rows/files; `0` disables the count limit.
- `auto_export_target` — validated relative folder inside Django `default_storage`.
- `use_celery` and `exclude_models` — normalized code-owned compatibility keys retained from `DLUX_CONFIG['backup']`.

Each `SystemBackup` stores a `manual`, `scheduled`, or `update` trigger. Inline
apply/rollback always creates and verifies an update-triggered backup before
maintenance, aborts if it fails, and protects the new backup while retention runs.

Common preference keys:

- `theme`
- `lang`
- `table_density`
- `table_page_size`
- `sidebar_collapsed`
- `sidebar_accordions`
- `sidebar_order`
- `autofill_enabled`
- `trusted_device` — (Internal) indicates if the current session is trusted for 30 days

Common runtime sidebar config keys in `get_system_config()["sidebar"]`:

- `enabled`
- `home_url_name`
- `entries`
- `enable_reorder`
- `show_toolbar`
- `show_icons`
- `density`
- `allow_user_density`
- `collapse_mode`

When `enabled` is `false`, Dlux does not render the runtime sidebar, ignores
sidebar toolbar/reorder/density controls, and lets the main layout expand.

`SystemSettings` storage is grouped, but the public/runtime contract is flat.
The model keeps only identity fields as standalone columns (`system_names`,
`logo`, `favicon`, `default_language`, `default_theme`, `home_url`,
`is_configured`). Mutable settings live in JSON groups in this order:
`auth_config`, `email_config`, `registration_config`, `public_root_config`,
`client_ip_config`, `notification_config`, `layout_config`,
`language_config`, `theme_config`, `typography_config`, `login_config`,
`titlebar_config`, `sidebar_config`, `navbar_config`, `log_config`,
`profile_config`, `backup_config`, and `extra_config`.

The canonical source for those grouped settings is `dlux.system`: `constants.py`
owns settings choices/constants, `defaults.py` owns `default_*_config()`
factories, `normalizers.py` owns config coercion, and `schema.py`/`registry.py`
describe groups, legacy flat keys, runtime aliases, and export/import coverage.
New Dlux internals should import from `dlux.system`. Root `dlux.constants`
exists only as a compatibility re-export, and the old defaults modules are not
canonical APIs. Important migration invariant:
published migrations `0001`, `0002`, and additive `0004` serialize default callable paths under
`dlux.models.default_*_config`, so those wrappers must remain importable
indefinitely. Keep the wrappers as thin delegates; do not move canonical
settings logic back into `dlux.models`.

`SystemSettingsForm` consumes registry schema metadata for the low-risk scalar
groups (`auth_config`, `registration_config`, `public_root_config`,
`layout_config`, and `client_ip_config`) when hydrating form initials and packing
cleaned split fields back into normalized groups. The complex builders for email
secrets, notifications, login hero copy, titlebar, sidebar, navbar, logging,
profile, language catalogs, theme, and font pickers remain custom.

Use existing flat keys in `DLUX_CONFIG`, templates, and host code unless you
are working on Dlux internals. `get_system_config()` flattens grouped DB values
back to keys such as `allowed_themes`, `public_root`,
`default_table_density`, and `translations_override`, while also exposing
normalized group aliases for internal use. `translations_override` remains
override-only data; Dlux never stores the merged translation catalog in
`language_config`.

Common runtime feature flags in `get_system_config()`:

- `email_2fa` — Enable email-based 2FA (set via `DLUX_CONFIG['email_2fa']` or the System Settings UI)
- `prevent_multiple_active_sessions` — When true, each successful login or completed 2FA login becomes the user's only active session. Dlux evicts other session keys for that user regardless of trusted-device status; trusted devices keep their trust record but must start a new session next time.
- `login_lockout_enabled` — Cache-based failed-login lockout on the password step (default on).
- `login_lockout_threshold` — Failed attempts from the same IP or username before the lock arms (1–50, default 5).
- `login_lockout_window_minutes` — Rolling window during which failed attempts keep counting (1–1440, default 15).
- `login_lockout_duration_minutes` — How long sign-in stays blocked once the lock is armed (1–1440, default 15). The legacy `DLUX_LOGIN_LOCKOUT_MAX_ATTEMPTS` / `DLUX_LOGIN_LOCKOUT_SECONDS` Django settings act only as a fallback when system config cannot be resolved.
- `enforce_strong_passwords` — Enable the strict password validator on every set-password path.
- `strong_password_min_length` — Minimum length the strict validator (and the live checklist card) requires while enforcement is on (8–64, default 12).
- `email_config` — Redacted Dlux email delivery config. Supports delivery `transport` (`direct` or `relay`) plus `secret_storage` (`env` or `encrypted_db`); exports never include SMTP secrets.
- `public_registration_enabled` — Enable disabled-by-default public signup.
- `registration_activation_mode` — `auto_login_after_verify` or `verified_pending_approval`.
- `registration_throttle_enabled` — Enable cache throttles for public signup.
- `honeypot_enabled` — Enable the hidden `website` bot-trap on the registration
  form (`registration_config.honeypot_enabled`, default on). When on, a submission
  that fills the hidden field is silently redirected to `register_sent`. Exposed as
  `APP_CONFIG.security.honeypot_enabled`.
- `privacy_policy_url` / `terms_url` — Operator-supplied policy links
  (`registration_config`). When `privacy_policy_url` is set, a privacy line/link is
  rendered on the sign-in and sign-up pages (shared `dlux/includes/auth_privacy_notice.html`,
  reading `APP_CONFIG.security`). DjangoLux ships no legal text.
- `privacy_notice_text` — Optional short notice shown with the privacy link.
- `registration_require_consent` — When true, the public registration form shows a
  **required** "I agree to the Terms & Privacy Policy" checkbox (validated in
  `PublicRegistrationForm(require_consent=...)`). See [Data & Privacy](data-privacy.md).
- `client_ip_config` — Centralized Client IP resolution configuration. Supports
  `mode` (`auto`, `x_forwarded_for`, `remote_addr`, `x_real_ip`, `cloudflare`,
  or `custom`), `trusted_proxy_hops` (0–8), and `custom_header` for custom mode.
- `public_root_theme` — Fixed theme applied to anonymous visitors on the public
  root (`public_root_config.public_root_theme`, blank = inherit the normal theme).
  Its stylesheet is emitted even if it is not in the normally-allowed theme set.
- `public_root_title` / `public_root_meta_description` — Optional `<title>` and
  `<meta name="description">` emitted only for the anonymous public index
  (`public_root_config.*`, length-bounded). Exposed as `APP_CONFIG.security.*`.
- `show_titlebar_on_public` / `show_sidebar_on_public` — Centralized public-root
  chrome toggles (`public_root_config.*`, both default **off** = hidden). They
  supersede the deprecated `titlebar_config.hide_on_public_unauthenticated_index`
  (legacy data migrates inverted) and gate `base.html`'s titlebar/sidebar for
  anonymous public-root visitors via the shared `_is_public_index()` context flag.
- `default_table_density` — System default table density (`balanced`, `dense`, or `roomy`)
- `default_form_density` — System default form field spacing (`balanced`, `dense`,
  or `roomy`), independent of table density. Drives `--dlux-form-*` CSS variables
  via `body[data-dlux-form-density]`. Exposed as `APP_CONFIG.appearance.default_form_density`.
- `default_modal_size` — Default width of the shared dynamic modal (`compact` →
  `modal-lg`, `standard` → `modal-xl`, `wide` → `modal-xl dlux-modal-wide`). The
  resolved class is `APP_CONFIG.appearance.modal_size_class`.
- `sticky_table_headers` / `zebra_striping` — Toggle (default on) the sticky table
  header row and alternating row shading; gated in `tables.css` via
  `body[data-dlux-sticky-header]` / `body[data-dlux-zebra]` emitted from `base.html`.
  Exposed as `APP_CONFIG.appearance.*`.
- `footer_text` — Optional copyright/description line for the global page footer
  (`layout_config.footer_text`, max 300 chars, blank by default). Edited from
  *System Settings → Themes & Typography → Footer* and exposed to templates as
  `APP_CONFIG.appearance.footer_text`; the `dlux/includes/footer.html` partial
  renders it, falling back to `DLUX_STRINGS.footer_text` then `© <year> <system name>`.

Theme/runtime UI notes:

- official theme ordering comes from `dlux/themes.py`
- the options page uses `.theme-preview` selectors
- the sidebar toolbar picker uses `.theme-option-circle` selectors
- runtime theme changes dispatch the `dlux:theme-changed` event so secondary UI such as the sidebar indicator can sync without a refresh

Options/runtime UI notes:

- Options cards are draggable through per-card handles and the current order is persisted in browser `localStorage`
- the wide System Info card intentionally keeps a double-column span inside the grid
- Autofill and Reset Defaults are standalone cards in the shared Options card system, not nested sub-cards

## Framework-Owned Table Surface

Dlux now owns the default table chrome for standard `django_tables2` tables.

- stock `django_tables2` templates such as `django_tables2/bootstrap5.html` are remapped at runtime to `dlux/tables/table.html`
- tables with no explicit template are also auto-captured
- explicit non-stock custom templates are left alone by default
- the system default density comes from `SystemSettings.default_table_density`
- the per-user override lives in `Profile.preferences["table_density"]`
- the per-user page-size preference lives in `Profile.preferences["table_page_size"]`
- built-in pagination and page-size controls are rendered by `dlux/tables/table.html`
- the recommended handwritten-table base class is `dlux.tables.DluxTable`

Supported table Meta overrides:

- `dlux_table = False` to opt out of the framework-owned renderer
- `dlux_density = "dense" | "balanced" | "roomy"` to force density for one table
- `dlux_per_page = 20` to force a fixed default page size for one table
- `dlux_per_page_options = (10, 20, 50, 100)` to override the built-in page-size choices
- `dlux_actions = False` to disable default Dlux row actions

Supported table extension hook:

- `get_dlux_row_actions(self, record, base_actions)` to extend or replace the default action list before permission filtering

## Context Menu Events

| Event | Purpose |
| --- | --- |
| `dlux:record:view` | View a record from a context-enabled element |
| `dlux:record:edit` | Open or route into an edit flow |
| `dlux:record:delete` | Trigger a delete flow |

Common action keys:

- `label`
- `icon`
- `url`
- `type`
- `event`
- `data`
- `dblclick`
- `textClass`
- `permission`
- `permissions`

## Common Activity Log Actions

The system records several action families out of the box, including:

- `CREATE`
- `UPDATE`
- `DELETE`
- `LOGIN`
- `LOGOUT`
- `DOWNLOAD`
- `EXPORT`

## Reusable Helpers

### View/security helpers

| Helper | Purpose |
| --- | --- |
| `require_current_password(request)` | Reusable backend guard for destructive profile/security actions. Returns a failure response or `None`. |
| `set_profile_totp_state(profile, raw_secret=..., enabled=...)` | Persist encrypted TOTP secret and/or enabled state directly without routing through the full `Profile.save()` path. |

Typical current-password guard usage:

```python
from dlux.guards import require_current_password


def my_sensitive_view(request):
    if failure_response := require_current_password(request):
        return failure_response
    # continue mutation
```

Typical TOTP state persistence usage:

```python
from dlux.utils import set_profile_totp_state


set_profile_totp_state(request.user.profile, raw_secret="BASE32SECRET", enabled=True)
```

### Form/UI helpers

| Helper | Purpose |
| --- | --- |
| `build_archive_file_field('field_name', css_class='...')` | Render the Dlux custom file widget explicitly instead of relying on template shadowing. |
| `build_settings_toggle_field(form, 'field_name', css_class='...')` | Render the shared setup/System Settings toggle-card control for boolean fields. |

### Alert Auto-Close Contract

`dlux/main/js/base_runtime.js` auto-closes every Bootstrap-style `.alert` after a short delay unless the alert explicitly opts out with `data-autoclose="false"`.

Default Django messages render through `dlux/includes/messages.html` as compact fixed flash notices rather than full-width titlebar overlays. Authenticated pages use `.dlux-flash-container`, positioned below `--header-height`; public auth pages pass `dlux_flash_mode='page'` to use `.dlux-page-alert-container` near the viewport top. Both containers are `pointer-events: none`, while visible alerts remain closeable and `.dlux-alert--closing` disables pointer events before the removal transition.

Use the opt-out for alerts that remain actionable after the first few seconds, such as validation blockers, missing-secret warnings, setup/import instructions, or status messages that explain why a field must be changed before the form can submit. Do not use it for normal Django flash messages that should behave like transient success/error notices.

Profile password-change validation is modal-scoped: invalid submissions render field errors inside `#resetPasswordModal`, reopen that modal on the response, and do not enqueue the generic form-error flash.

Server-rendered or template alerts:

```html
<div class="alert alert-info" data-autoclose="false">
    This setup notice remains visible until the user resolves it.
</div>
```

JavaScript-created alerts:

```javascript
const notice = document.createElement('div');
notice.className = 'alert alert-warning';
notice.setAttribute('data-autoclose', 'false');
```

### Lux Signature Contract

`dlux/main/js/signature.js` is the removable, client-only DjangoLux attribution layer. It reads `<html data-dlux="DjangoLux X.Y.Z ...">`, prints one quiet console credit on load, exposes non-enumerable `window.lux` / `window.dlux` console getters, and reveals a compact `.dlux-signature-pop` visual credit when a user types `dlux` on the page outside input, textarea, select, or contenteditable targets. It makes no network calls and stores no data.

## Template Tags and Filters

### `dlux_tags`

| Name | Type | Purpose |
| --- | --- | --- |
| `dlux_timesince` | simple tag | Translated relative timestamp output |
| `include_if_exists` | simple tag | Render a template only if it exists |
| `include_once` | simple tag | Render a template at most once per request (dedupes shared asset partials) |

### `dlux_translation`

| Name | Type | Purpose |
| --- | --- | --- |
| `translate_log` | filter | Translate log values with a prefix such as `action` or `model` |
| `format_log_details` | simple tag | Render structured log details as HTML badges |

### `sidebar_tags`

| Name | Type | Purpose |
| --- | --- | --- |
| `auto_sidebar` | inclusion tag | Render auto-discovered sidebar items |
| `extra_sidebar` | inclusion tag | Render additional sidebar groups |
| `sidebar_item_class` | simple tag | Return `active` when the current request matches a URL name |

## Frequently Used Helpers

| Helper | Purpose |
| --- | --- |
| `get_system_config()` | Return the merged runtime configuration |
| `get_theme_names()` | Return the active official theme-name list from the shared theme registry |
| `get_theme_choices()` | Return the active theme tuples used by settings/forms choice fields |
| `get_theme_options()` | Return the active theme metadata used by previews, labels, CSS inclusion, and runtime pickers |
| `dlux_settings()` | Apply the default DjangoLux settings requirements from a project `settings.py` via `dlux_settings(globals())`, including app stack, locale and activity middleware, context processor, Crispy defaults, `MESSAGE_TAGS`, and core language/format defaults |
| `get_secret()` | Read a Docker secret file first, then fall back to an environment variable |
| `get_model_classes()` | Resolve model, form, table, and filter classes via conventions or overrides |
| `get_user_linked_models()` | Find all models with a OneToOneField to the User model |
| `resolve_model_by_name()` | Find a model class dynamically by name |
| `filter_context_actions()` | Hide context-menu actions the current user should not see |
| `is_global_staff(user)` | Returns `True` if user is non-scoped staff with `manage_scopes` permission (can manage ALL users and scopes) |
| `is_central_staff(user)` | Returns `True` if user is non-scoped staff WITHOUT `manage_scopes` permission (can only manage scopeless users) |
| `can_manage_target_user(actor, target)` | Returns `True` if actor can manage target user, respecting superuser self-only rules, scope boundaries, and Central Staff restrictions |
| `get_visible_group_presets(user)` | Preset Groups (auth.Group + GroupProfile) a user may see/assign: global + own-scope for scoped staff, all for superuser/Global Staff |
| `can_manage_group_preset(actor, group)` | `True` if actor may CRUD/manage-membership on a preset (global presets are superuser/Global-Staff only; scoped staff manage own-scope presets) |
| `set_user_group_presets(user, groups, actor, manageable_groups=None)` | Reconcile a user's preset membership within the manageable set — syncs native `user.groups` and the `GroupMembership` audit rows |
| `set_group_members(group, users, actor, manageable_users=None)` | Group-centric inverse of the above: set one preset's members, syncing `group.user_set` and audit rows |
| `get_manageable_users_queryset(actor)` | Users an actor may add to/remove from presets, honouring the same tiers as the user directory |
| `collect_related_objects()` | Inspect reverse and related objects for reporting or delete warnings |
| `has_related_records()` | Fast relation check before destructive actions |
| `setup_filter_helper()` | Normalize filter UI and clear-button behavior |
| `advanced_filter_helper()` | Build a primary filter row plus collapsible advanced rows, optional action buttons, and separate hidden/clear preserve behavior |
| `set_field_attrs()` | Apply DjangoLux-friendly widget classes and affordances to a form, including the shared datepicker hook (`.dlux-datepicker` with legacy `.flatpickr` compatibility) |
| `translate_choices()` | Translate choice lists using the system translation engine |
| `log_user_action()` | Create consistent audit log entries |
| `fetch_file()` | Download one file, many files, or ZIP bundles from model instances |
| `fetch_excel()` | Export queryset data to Excel with hidden system/file columns |

## Authorization Contracts

- `DynamicModalManagerView` and `DynamicModalDeleteView` are backend-authorized surfaces, not login-only helpers
- `accounts/profile/edit/<pk>/modal/` is self-only
- dedicated user-management modals follow the same staff/scope/superuser rules as `dlux/views/users.py`
- `/sys/users/` and user-detail surfaces require `auth.view_user` OR `dlux.manage_staff` for staff callers (superusers still bypass)
- **Staff Tier System**: Three non-superuser staff tiers exist:
  - **Global Staff** (`is_global_staff`): Non-scoped staff with `dlux.manage_scopes` permission — can create scopes, assign any scope, and manage ALL users
  - **Central Staff** (`is_central_staff`): Non-scoped staff WITHOUT `manage_scopes` — can only create/manage scopeless users, completely blind to scoped users
  - **Scoped Staff**: Staff assigned to a specific scope — can only manage users within that scope
- Only **superusers** can create Global Staff users (assign `manage_scopes` permission)
- Global Staff and superusers can create Central Staff
- Central Staff cannot see scoped users in `/sys/users/`, cannot assign scopes, and cannot access scope management
- user-detail activity snippets require `dlux.view_activitylog`
- sidebar system items, dashboard cards, and user-hub shortcuts for Users / Sections / Activity Log follow the same helper-backed authorization rules
- section-management routes require `dlux.view_sections` or `dlux.manage_sections`
- `filter_context_actions()` now properly respects `manage_sections` permission for section-related context menu actions
- Options diagnostics are privileged-only; personal preference controls remain available to authenticated users

### Sidebar Permission Inference

Sidebar items are only visible to users who have the required view permission. The permission for each item is inferred in this order:

1. **Explicit decorator**: `sidebar_permissions` or `permission_required` on the view callback — used as-is.
2. **System route meta**: items in `SYSTEM_ROUTE_META` use their declared `__dlux_*` permission tokens:
   - `manage_users` → `__dlux_user_directory__`
   - `user_activity_log` → `__dlux_activity_log__`
   - `manage_sections` → `__dlux_sections_view__`
   - `options_view` → `__dlux_authenticated__`
3. **Model-based inference**: for class-based views with a model, the permission is `app_label.view_model_name`.
4. **URL pattern inference**: for function-based views without a model, the app label comes from the URL namespace (or callback module) and the model name from the URL name prefix (e.g., `documents:outgoing_list` → `documents.view_outgoing`).
5. **No inference**: if none of the above produce a permission, the item is hidden from non-superusers.

Internal tokens are resolved by `user_matches_permission_token()` in
`dlux/utils/authorization.py` and re-exported from `dlux.utils`.

## Codebase Entry Points

When you need to trace behavior in the code, these files are the usual first stops:

- `dlux/models.py` for `SystemSettings`, `ScopedModel`, `Profile`, notifications,
  backup/restore records, and updater state/run models
- `dlux/forms.py` for the setup wizard form, user wizard, and runtime configuration form logic
- `dlux/views/sections.py` for sections and dynamic modal flows
- `dlux/views/updater.py` and `dlux/updater/` for updater HTTP boundaries,
  verification, persistent runtime storage, and orchestration
- `dlux/translations.py` for built-in translation keys and language-resolution logic
- `dlux/utils/` for authorization, configuration merging, filtering/CRUD helpers,
  import/export, navigation, settings integration, and UI utilities
