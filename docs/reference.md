# Reference

A lookup sheet: management commands, routes, configuration keys, template tags and
helpers. How each feature behaves is in its own guide (see
[Feature Guides](#feature-guides)); every `DLUX_*` setting and environment variable
is in [Deployment Configuration](deployment-configuration.md).

- [Scaffold Commands](#scaffold-commands)
- [Management Commands](#management-commands)
- [Routes](#routes)
- [Configuration Keys](#configuration-keys)
- [Tables](#tables)
- [Helpers](#helpers)
- [Template Tags and Filters](#template-tags-and-filters)
- [Authorization Contracts](#authorization-contracts)
- [Optional SSO Packages](#optional-sso-packages)
- [Feature Guides](#feature-guides)
- [Codebase Entry Points](#codebase-entry-points)

## Scaffold Commands

| Command | Purpose |
| --- | --- |
| `python -m dlux startproject myproject` | Create a new DjangoLux-ready Django project (prompts for image/repo on a TTY). |
| `python -m dlux startproject myproject --image acme/app:tag --repo acme/app` | Set the Docker image (written to `.secrets/.env` as `WEB_IMAGE`) and the GitHub repo for the release URL non-interactively. |
| `python -m dlux startproject myproject --no-input` | Scaffold without prompting; use `--image`/`--repo` values or their defaults (CI). |
| `python -m dlux startapp billing` | Create a new DjangoLux-native app in the current project. |
| `python -m dlux startapp billing --register` | Create the app and also patch project settings and URLs. |
| `./start.sh update` | Update the Composer deployer, then pull and recreate the stack and resident pair (wrapper 5+). Name services to update only those. |
| `./start.sh update self` | Update only the Composer deployer. `self update` is a deprecated alias. |
| `./start.sh check` | Inspect a generated stack for Composer topology, runtime-volume, and migration drift. |
| `./start.sh check --fix` | Apply only Composer's recognized, reviewed repairs; originals are preserved under `.xclude/` and the resulting Compose configuration is validated. |


Generated project baseline:

- `.secrets/.env` with scaffolded bootstrap secret values
- `config/settings.py` wired for env-driven Django secret, Postgres, Redis cache, and Celery
- `config/settings.py` wired with `corsheaders` / `csp`, their middleware, and starter
  CORS/CSP settings
- `compose.yml` and `compose.dev.yml` keeping the standard inline-env pattern
- a generated Docker baseline with `web`, `celery`, outbound-only `composer-agent`
  (read-only Docker access via a `POST=0`/`EXEC=0` `docker-socket-proxy`), the
  isolated `composer-executor` that holds the real Docker socket and performs all
  writes, `db`, `redis`, `caddy` (active proxy; `nginx` fallback), and internal
  `smtp-relay` services. Compose 5.3.0 or later is required for the `celery`
  `pre_start` migration hooks; `./start.sh check --fix` repairs existing stacks.
- `requirements.txt` pinned to the generated stable `django-lux` release
- a persistent `dlux_runtime` volume, project-owned process supervisor, and a
  proxy-served maintenance/progress page

Generated app scaffold baseline:

- discovery-friendly `models.py`, `forms.py`, `filters.py`, `tables.py`, `views.py`,
  `urls.py`, `translations.py`, templates, and tests
- optional `--register` patching for `INSTALLED_APPS` and root project URLs
- modal/list conventions that align with Dlux discovery, sections, and table/filter helpers

## Management Commands



### Setup and settings

| Command | Purpose |
| --- | --- |
| `python manage.py dlux_setup` | Create migrations, apply migrations, and run the config check. |
| `python manage.py dlux_setup --skip-check` | Skip the validation pass after setup. |
| `python manage.py dlux_setup --no-migrate` | Skip `makemigrations` and `migrate`. |
| `python manage.py dlux_setup --skip-configure` | Do not append the `dlux_settings(globals())` helper to the active settings module. |
| `python manage.py dlux_settings status` | Inspect the `SystemSettings` singleton without creating it. |
| `python manage.py dlux_settings configure` | Mark the singleton configured without replacing its values. |
| `python manage.py dlux_settings unconfigure` | Preserve settings but mark setup incomplete so `/sys/setup/` opens again. |
| `python manage.py dlux_settings delete --yes` | Delete the singleton row; the next load recreates it. |
| `python manage.py dlux_settings reset --yes` | Recreate the singleton from model defaults and mark it unconfigured. |
| `python manage.py dlux_settings export --output config.json` | Export portable System Settings JSON. |
| `python manage.py dlux_settings import --input config.json` | Import portable System Settings JSON and mark setup configured. |

### Diagnostics and stack contract

| Command | Purpose |
| --- | --- |
| `python manage.py dlux_doctor` | Run the deployment doctor: settings wiring, URLs, database, migrations, cache, SMTP, static files, and production-safety checks. Exits 1 when any check fails. |
| `python manage.py dlux_doctor --format json` | Emit the machine-readable report Composer consumes. |
| `python manage.py dlux_doctor --group security` | Limit to one group (`settings`, `urls`, `database`, `services`, `static`, `security`, `packages`); repeatable. |
| `python manage.py dlux_doctor --strict` | Exit 1 on warnings as well as errors. |
| `python manage.py dlux_doctor --apply` | Apply the safe fixes for failing checks (for example `collectstatic`). |
| `python manage.py dlux_doctor --apply --allow-stateful` | Also run fixes that mutate the database (`migrator`). |
| `python manage.py dlux_check` | Deprecated alias for `dlux_doctor`; warns on stderr and delegates. |
| `python manage.py dlux_stack_contract` | Print the stack contract (services/networks/mounts/env) as JSON, version-stamped; Composer's drift-diff execs this. Generated stack files carry its `schema_version` as a stamp; see [Stack Schema Stamps](stack-schema.md). |
| `python manage.py dlux_runtime_contract` | Print the runtime-volume contract (layout, `active.json`, which process writes what) as JSON. |
| `python manage.py dlux_relay [OPERATION ...]` | Report whether the Composer egress relay answers and which operations it offers; exits non-zero if a named operation is not on offer. See [Outbound Requests](outbound-requests.md). |

### Backups, assets and data

| Command | Purpose |
| --- | --- |
| `python manage.py dlux_backup [--scope data\|full] [--trigger update\|manual\|scheduled] [--requested-by NAME]` | Take a system backup in the foreground (server key, system data included) and print one JSON line: `ok`, `token`, `status`, `trigger`, `scope`, `rows`, `files`, `size`, `path`, `error`. Exits non-zero unless it completed, and never leaves an automatic retry armed. Composer runs it before an operator's `dlux update`/`dlux rollback`. |
| `python manage.py dlux_prune_assets [--apply] [--namespace NS] [--kind KIND] [--include-shared]` | Report managed assets that nothing references, through any relation; `--apply` deletes them, each row before its file. Limit by namespace (repeatable) or kind; the shared pool is skipped unless asked for. See [Managed Assets](managed-assets.md). |
| `python manage.py dlux_prune_activity_log --dry-run` | Preview log rows outside configured category retention windows. |
| `python manage.py dlux_prune_activity_log` | Delete rows outside configured category retention windows. |
| `python manage.py dlux_backfill_report_activity` | Count, per report model, the records with no `CREATE` activity row (saved before activity logging), which reports therefore never count. `--apply` writes them from each record's creation time, creator, scope and number, marked `details.backfilled`; reruns skip what is already logged. `--model app.Model` (repeatable) limits the run. On a generated stack: `./start.sh run -m web dlux_backfill_report_activity`. |

### Document files and OCR

| Command | Purpose |
| --- | --- |
| `python manage.py dlux_adopt_file_history app_label.Model [--apply] [--verify]` | Copy a project's own file-history rows into `dlux.FileVersion`; archived files stay where they are. `--verify` checks every source row against its copy. See [Document Files](document-files.md). |
| `python manage.py dlux_ocr_backfill` | OCR existing registered document files in resumable batches (`--files`, `--batch-size`, `--limit`, `--enqueue`, `--retry-failed`, `--restart`, `--dry-run`). See [OCR](ocr.md). |
| `python manage.py dlux_adopt_ocr_text app_label.Model [--apply]` | Copy a project's own OCR rows into `dlux.FileText`. |

### Translations

| Command | Purpose |
| --- | --- |
| `python manage.py dlux_translations` | Audit translation strings: keys missing from a language, looked up but undefined, permission/model labels, duplicates, and values left in English. See [Translations](translation-guide.md#auditing-strings). |
| `python manage.py dlux_translations --lang ar --stub ar` | Print every Arabic gap as paste-ready entries grouped by `translations.py`. |
| `python manage.py dlux_translations --fail [--check …] [--app LABEL] [--json] [--core]` | Exit 1 on failing gaps (CI); limit checks or apps, emit JSON, or audit DjangoLux's own catalogue. |

### Seed data

| Command | Purpose |
| --- | --- |
| `python manage.py dlux_seed` | Dry-run auto-discovery and show the project models and empty canonical dependencies that would be seeded. |
| `python manage.py dlux_seed --count 25 --seed 42 --apply` | Generate 25 deterministic rows per discovered project model from field metadata. |
| `python manage.py dlux_seed --count 25 --log --apply` | Generate rows and one reportable `CREATE` activity entry per row, attributed to random active users. |
| `python manage.py dlux_seed --user-id 1 --scope-id 1 --apply` | Generate rows attributed to one user and scope; either attribution option implies `--log`. |
| `python manage.py dlux_seed app.Model --apply` | Seed only the named model; `--app`, `--exclude`, `--database`, and `--no-populate` further constrain the run. |

### Generated-stack internals

| Command | Purpose |
| --- | --- |
| `python manage.py migrator` | Internal generated-project migration/static/bootstrap command, run by Celery's Compose `pre_start` hook under the runtime supervisor. |
| `python manage.py migrator -mm` | Force makemigrations for every target app, then migrate, then collectstatic. |
| `python manage.py migrator -nm` | Skip makemigrations and migrate; still collect static. Mutually exclusive with `-mm`. |
| `python manage.py migrator -a APP` | Scope the target-app list instead of auto-discovering local apps. |
| `python manage.py dlux_reconcile` | Reset the active runtime pointer to the baked image when a volume-pinned release is not newer than it. Touches only the runtime volume and always exits 0, so it runs before migrations. |
| `python manage.py dlux_image_gate --baked-dlux-version X.Y.Z` | Print, as JSON, whether a candidate image adopts, keeps or blocks the active DjangoLux release. |
| `python manage.py dlux_update_worker` | Legacy update queue worker. Generated stacks do not run it: Celery Beat hands update intent to Composer. |

### Task worker

| Command | Purpose |
| --- | --- |
| `python manage.py dlux_worker [--threads N] [--queue NAME] [--no-schedule]` | Run the DjangoLux task worker under `DLUX_TASK_BACKEND = "dlux"`. It runs queued tasks in a thread pool plus `DLUX_TASK_SCHEDULE`, sends a heartbeat, recovers runs lost with a dead worker and prunes finished runs. On SIGTERM it exits after running tasks finish. See [Task Runner](task-runner.md). |
| `python manage.py dlux_worker --burst` | Run what is due now in this process, then exit. |
| `python manage.py dlux_worker --check` | Exit 0 when a worker on this host has a fresh heartbeat (container healthcheck). |

### Migrating from microsys

| Command | Purpose |
| --- | --- |
| `python manage.py dlux_migrate_from_microsys` | Dry-run the supported Microsys 2.4.1 database relabel. |
| `python manage.py dlux_migrate_from_microsys --yes` | Apply the database relabel after an external backup. |

### `dlux_seed` behaviour

`dlux_seed` excludes Django/Dlux internals, unmanaged/proxy/auto-created models, and
models outside the project root. Set `dlux_seed = False` on a project model that
must never receive generated rows, or `dlux_seed = True` to explicitly include a
model outside the normal project-path heuristic. It generates choices, text,
numbers, decimals, booleans, dates/times, UUIDs, JSON, IP addresses, required
files, foreign keys, one-to-one relations, and automatic many-to-many relations.
Required PDF fields receive a valid one-page PDF with a complete cross-reference
table, so downstream PDF readers can open and rewrite seeded files. Optional file
fields remain empty. Unsupported required fields or unresolved relation cycles are
reported and skipped without aborting valid models.

Activity logging is off by default. `--log` chooses a random active user for each
seeded row and writes a `user`-category `CREATE` entry in the same transaction, so
the work is included in General Reports. `--user-id` fixes the actor for every row;
`--scope-id` fixes the scope for every row; either option enables logging without a
separate `--log`. Without a fixed scope, the command uses the selected actor's scope
or the scope assigned to the generated model row. Standard Dlux `created_by`,
`updated_by`, and `scope` relations receive the same attribution.

Projects with canonical lookup data can declare ownership through their local
`populate` command:

```python
class Command(BaseCommand):
    dlux_populate_models = (
        "catalog.Category",
        "catalog.Supplier",
    )
```

If that command accepts `--models`, DjangoLux passes only empty related model
labels; otherwise it runs `populate` once. Models owned by `populate`
are reused as dependencies and never receive random rows from `dlux_seed`.
`--no-populate` preserves that ownership: empty canonical models stay empty and
dependent seed models are reported as skipped.

## Routes

### Core Routes

The routes operators and integrators reach directly. Internal JSON endpoints that
shipped pages call are left out; `dlux/urls.py` has every route.

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
| `/sys/files/media-access/` | Asked by the proxy before it serves a private `/media/` file (`X-Forwarded-Uri`); answers 204 or 403. `DluxMiddleware` also answers this root URI when the project mounts `dlux.urls` under a prefix. See [Stored files](deployment-configuration.md#stored-files-media). |
| `/sys/options/app-settings/<namespace>/` | Superuser-only modal for settings registered with `register_app_settings(...)` |
| `/sys/options/app-settings-group/<group_id>/` | Superuser-only modal for a tile registered with `register_app_settings_group(...)`: every grouped section, one Save |
| `/sys/users/` | User management |
| `/sys/registrations/` | Superuser-only pending public registration approvals |
| `/sys/registrations/<int:pk>/approve/` | POST-only public registration approval |
| `/sys/registrations/<int:pk>/reject/` | POST-only public registration rejection |
| `/sys/reset_password/<int:pk>/` | Staff password-reset endpoint for a target user |
| `/sys/logs/` | Activity log |
| `/sys/logs/<int:pk>/details/` | Activity log detail modal |
| `/sys/reports/` | Activity reports overview; its user buttons open `/sys/users/<pk>/report/` in the activity view (`user_report_access()`) for report viewers without user-directory/activity-log access |
| `/sys/reports/backup.zip` | Permission-gated report backup ZIP |
| `/sys/backup/` | Superuser-only full system backup and restore page. Its two histories paginate with `backups-page` and `restores-page` (fixed sizes 10 and 5) |
| `/sys/backup/create/` | Create a `.dlb` system backup: `backup_encryption` (`server_key` default, `passphrase` + `backup_passphrase`/`backup_passphrase_confirm`, `none`), `backup_scope` (`full`/`data`), `include_system_data` (`1` default, `0` = portable). Returns 409 while another backup is pending or running |
| `/sys/backup/<token>/status/` | Backup status JSON, including `log` (console history), `elapsed`, `eta`, `encryption`, `system_data_included` |
| `/sys/backup/<token>/download-chain/` | ZIP of every chain member from the full backup up to this increment |
| `/sys/backup/<token>/cancel/` | POST-only: cancel a pending or running backup (JSON for XHR, redirect otherwise) |
| `/sys/backup/<token>/delete/` | POST-only: delete a finished backup and its file; refused while it is active |
| `/sys/backup/upload/` | Upload an encrypted `.dlb` for restore |
| `/sys/backup/restore/` | Start a system restore from an uploaded or existing `.dlb` |
| `/sys/scopes/manage/` | Scope management |
| `/sys/scopes/delete/<int:pk>/` | POST-only scope delete; blocked with related-object details when records still reference it |
| `/sys/groups/manage/` | Permission group / preset management (requires `dlux.manage_groups`) |
| `/sys/groups/<int:pk>/delete/` | POST-only group preset delete; ignores the preset sidecar and permission M2M but blocks on assigned users/history |
| `/sys/groups/<int:pk>/members/` | Preset membership modal + who/which/when history |
| `/sys/sections/` | Section management |
| `/sys/api/dlux-update/runtime-health/` | HMAC-authenticated version health of the running processes, read by the updater |

### Route Access Contracts

- `/sys/sections/`, `/sys/section/details/`, `/sys/section/delete/` and the
  subsection CRUD endpoints require the section permissions. Section detail, delete
  and subsection CRUD accept only a discovered Dlux section or section child model,
  never an arbitrary `model=` token.
- Section Manager searches the selected model through one framework-owned `keyword`
  field, with no Advanced controls. It keeps the discovered FilterSet's unbound
  queryset restrictions and the model manager's scope; project-specific filter
  fields apply only on their own list pages.
- `/sys/users/` and the user-detail page and modal require `auth.view_user` for
  staff users; superusers bypass.
- `/sys/reset_password/<int:pk>/` requires `auth.change_user` and the same
  staff, scope and superuser target checks as the user-management modals. A new
  password equal to the target's current one is refused.
- `/accounts/profile/` offers `sign_out_other_sessions` only on the user's own
  password-change form, and only while `prevent_multiple_active_sessions` is off.
  When ticked, a successful change keeps the current browser, deletes every other
  database or cache-backed session, marks their presence rows ended and revoked, and
  lets Django rotate the kept session key. Trusted devices stay trusted. The backend
  ignores a forged toggle while single-session enforcement is on.
- Signed-in devices and session revocation resolve through the configured
  `SESSION_ENGINE`: database rows for database sessions, `UserPresenceSession` as
  the index for cache-backed ones. Missing cache entries are omitted and their stale
  presence rows closed without being marked revoked.
- The create-user modal can set `profile.preferences["force_password_change"]`.
  `DluxMiddleware` then sends that user to `/accounts/profile/?force_password_change=1`
  until a password change succeeds, which clears the marker; the new password must
  differ from the old one. Initial User Setup waits until then.
- `/sys/admin/force-password-change-all/` is a POST-only superuser endpoint behind
  the Options Admin panel. It requires the current password and sets the same marker
  on every non-superuser, keeping their other preferences.
- `/sys/logs/` and `/sys/logs/<int:pk>/details/` require `dlux.view_activitylog` or
  superuser status. Activity snippets on user-detail pages need the same permission.
- Sidebar system routes and the dashboard and user-hub shortcuts use the same
  helper-backed checks. Sidebar items need the view permission; there is no implicit
  staff fallback (see [Sidebar Permission Inference](#sidebar-permission-inference)).

Report and backup routes are described with their features in
[Operations](operations.md) and [Backups](backups.md).

### 2FA Routes

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

- `/sys/2fa/enable/`, `/sys/2fa/setup/totp/`, `/sys/2fa/disable/`,
  `/sys/2fa/backup-codes/generate/`, and resend endpoints are POST-only mutators
- backup codes are stored hashed in `Profile.backup_codes`
- login 2FA redirects validate `next` against allowed hosts before redirecting
- destructive profile-side 2FA actions such as disable, backup-code regeneration, and
  session revocation require the current-password guard on the backend
- Profile can trust the current browser after current-password confirmation; untrusted
  sessions cannot revoke trusted sessions
- when `prevent_multiple_active_sessions` is enabled, each newly authenticated session
  revokes every other active session for that user; the older browser is redirected to
  the session-ended page on its next request
- when `prevent_multiple_active_sessions` is disabled, successful logins do not revoke
  another browser's database- or cache-backed session; changing the system setting
  takes effect through normalized runtime config without a restart
- email 2FA supports auto-send on login and 120s resend cooldown to reduce authentication friction
- TOTP setup persists secret/enabled state through `set_profile_totp_state(...)`
  instead of the full `Profile.save()` path, so unrelated profile-save side effects do
  not block authenticator setup

### API Endpoints

#### Autofill

| Route | Method | Purpose |
| --- | --- | --- |
| `/sys/api/last-entry/<app>/<model>/` | `GET` | Return the most recent record for sticky-form cloning |
| `/sys/api/details/<app>/<model>/empty_schema/` | `GET` | Return an empty field structure for clearing autofill targets |
| `/sys/api/details/<app>/<model>/<pk>/` | `GET` | Return serialized model details for autofill |

Autofill security contract:

- detail and autofill serialization return only direct fields of the requested model
- reverse OneToOne expansion such as `user.profile.*` is intentionally excluded
- reads use the model default manager so scoped query behavior is preserved

#### Preferences

| Route | Method | Purpose |
| --- | --- | --- |
| `/sys/api/preferences/update/` | `POST` | Merge updated preference values into `Profile.preferences` |
| `/sys/api/preferences/reset/` | `POST` | Clear saved preferences and related session keys |
| `/sys/api/preferences/app/<namespace>/` | `POST` | Set (or clear) one app-owned preference namespace |

App-owned preference namespaces are described in
[UI Integration](ui-integration.md#per-user-app-preferences).

#### Notifications

| Route | Method | Purpose |
| --- | --- | --- |
| `/sys/api/notifications/` | `GET` | Return the current user’s notification drawer items, unread count, and unread `section_counts` keyed by source model |
| `/sys/api/notifications/<pk>/read/` | `POST` | Mark one notification state as read for the current user |
| `/sys/api/notifications/<pk>/dismiss/` | `POST` | Mark one notification state dismissed for the current user |
| `/sys/api/notifications/read-all/` | `POST` | Mark all current-user notification states as read |
| `/sys/api/notifications/clear-all/` | `POST` | Dismiss read current-user notification states from the drawer |

#### Weather

| Route | Method | Purpose |
| --- | --- | --- |
| `/sys/api/weather/` | `GET` | Current conditions for the configured locations |
| `/sys/api/weather/locations/` | `POST` | City search for superusers |

See [Weather](weather.md).

## Configuration Keys

### Profile Preferences

Common `Profile.preferences` keys:

- `theme`
- `lang`
- `table_density`
- `table_page_size`
- `sidebar_collapsed`
- `sidebar_accordions`
- `sidebar_order`
- `autofill_enabled`
- `trusted_device` (internal): whether the current session is trusted for 30 days

### Sidebar

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
- `toggle_icon`

When `enabled` is `false`, Dlux does not render the runtime sidebar, ignores
sidebar toolbar/reorder/density controls, and lets the main layout expand.

The sidebar step and `toggle_icon` are described in
[System Configuration](system-configuration.md).

### SystemSettings Storage

`SystemSettings` keeps identity and asset fields as columns (`system_names`, `logo`,
`favicon`, `default_language`, `default_theme`, `is_configured`). Everything mutable
lives in JSON groups: `auth_config`, `email_config`, `registration_config`,
`homepage_config`, `client_ip_config`, `notification_config`, `layout_config`,
`language_config`, `theme_config`, `typography_config`, `login_config`,
`titlebar_config`, `search_config`, `sidebar_config`, `ribbon_config`,
`tables_config`, `navbar_config`, `log_config`, `profile_config`, `backup_config`
and `extra_config`. Asset foreign keys stay standalone protected references and are
never embedded in JSON.

`homepage_config` is the home and public-page group:

```json
{
  "default_url": "/accounts/profile/",
  "allow_user_override": false,
  "public": {
    "enabled": false,
    "separate_url": false,
    "url": "",
    "theme": "",
    "title": "",
    "meta_description": "",
    "show_titlebar": false,
    "show_sidebar": false
  }
}
```

New code uses `homepage_config` and `search_config`, or their accepted aliases
(`homepage`/`public_homepage`, `search`/`global_search`). Until 2.0 the legacy
`home_url` column, `public_root_config`, `profile_config['allow_user_home_url']` and
the titlebar global-search keys stay synchronized mirrors, and `get_system_config()`
also flattens grouped values back to legacy keys such as `home_url`, `public_root`,
`allowed_themes`, `default_table_density` and `translations_override`; see
[Deprecation Countdown](deprecation-countdown.md). `translations_override` holds
overrides only: the merged translation catalog is never stored.

`dlux.system` is the source for the groups: `constants.py` (choices and constants),
`defaults.py` (`default_*_config()` factories), `normalizers.py` (coercion), and
`schema.py`/`registry.py` (groups, legacy flat keys, runtime aliases, import/export
coverage). Import constants from `dlux.system.constants`. How to add a setting is in
[Adding a System Setting](adding-system-settings.md).

### Runtime Flags

Common keys in `get_system_config()`:

- `email_2fa` — Enable email-based 2FA (set via `DLUX_CONFIG['email_2fa']` or the
  System Settings UI)
- `forgot_password_enabled` — Show the login-page **Forgot password?** link and enable
  the self-service email reset flow (`/accounts/password-reset/`). Default off;
  additionally self-gates on email readiness (`get_email_service_status()`), so the
  link and reset views stay hidden/404 until Dlux email delivery is configured. The
  reset email is sent through `send_dlux_mail`, and every reset page renders in the
  configured login style/direction/language.
- `prevent_multiple_active_sessions` — When true, each successful login or completed
  2FA login becomes the user's only active session. Dlux evicts other session keys for
  that user regardless of trusted-device status; trusted devices keep their trust
  record but must start a new session next time.
- `login_lockout_enabled` — Cache-based failed-login lockout on the password step (default on).
- `login_lockout_threshold` — Failed attempts from the same IP or username before the
  lock arms (1–50, default 5).
- `login_lockout_window_minutes` — Rolling window during which failed attempts keep
  counting (1–1440, default 15).
- `login_lockout_duration_minutes` — How long sign-in stays blocked once the lock is
  armed (1–1440, default 15). The `DLUX_LOGIN_LOCKOUT_MAX_ATTEMPTS` /
  `DLUX_LOGIN_LOCKOUT_SECONDS` Django settings act only as a fallback when system
  config cannot be resolved.
- `enforce_strong_passwords` — Enable the strict password validator on every set-password path.
- `strong_password_min_length` — Minimum length the strict validator (and the live
  checklist card) requires while enforcement is on (8–64, default 12).
- `purge_session_on_exit` — When true, the session cookie is a browser-session cookie
  (`session.set_expiry(0)`, no persistent `Max-Age`), so a new browser session
  requires authentication. Tabs share this cookie, so closing one tab cannot end the
  session while the browser session remains open. Enforced by `DluxMiddleware` on
  authenticated requests (default off).
- `inactivity_timeout_enabled` — Enable idle sign-out. When on, `DluxMiddleware`
  expires the session after inactivity (overriding the static
  `DLUX_SESSION_IDLE_TIMEOUT_SECONDS`), and authenticated pages load
  `session_timeout.js`, which shows a countdown modal ~30s before expiry with a "Stay
  signed in" dismiss (pings `/accounts/session-keepalive/`) and a "Sign out now"
  action (default off).
- `inactivity_timeout_minutes` — Minutes of inactivity before sign-out while
  `inactivity_timeout_enabled` is on (1–1440, default 10).
- `email_config` — Redacted Dlux email delivery config. Supports delivery `transport`
  (`direct` or `relay`) plus `secret_storage` (`env` or `encrypted_db`); exports never
  include SMTP secrets.
  The `relay` option is offered only while the internal relay answers on
  `smtp-relay:1025` (`dlux.utils.internal_smtp_relay_available`, overridable via
  `DLUX_SMTP_RELAY_HOST`/`_PORT`) — the relay starts its listener unconditionally
  and resolves its upstream per message, so reachability never depends on this
  setting. A relay already stored is left selectable even while it is down, so an
  outage cannot quietly reset a deployment to direct SMTP.
- `public_registration_enabled` — Enable disabled-by-default public signup.
- `registration_activation_mode` — `auto_login_after_verify` or `verified_pending_approval`.
- `registration_throttle_enabled` — Enable cache throttles for public signup.
- `honeypot_enabled` — Enable the hidden `website` bot-trap on the registration
  form (`registration_config.honeypot_enabled`, default on). When on, a submission
  that fills the hidden field is silently redirected to `register_sent`. Exposed as
  `APP_CONFIG.security.honeypot_enabled`.
- `privacy_policy_url` / `terms_url` — Operator-supplied policy links
  (`registration_config`). When `privacy_policy_url` is set, a privacy line/link is
  rendered on the sign-in and sign-up pages (shared `dlux/auth/privacy_notice.html`,
  reading `APP_CONFIG.security`). DjangoLux ships no legal text.
- `privacy_notice_text` — Optional short notice shown with the privacy link.
- `registration_require_consent` — When true, the public registration form shows a
  **required** "I agree to the Terms & Privacy Policy" checkbox (validated in
  `PublicRegistrationForm(require_consent=...)`). See [Data & Privacy](data-privacy.md).
- Public-registration defaults are model markers, not configuration keys:
  `Scope.is_public_registration_default` selects the one default landing scope
  while scopes are enabled, and `GroupProfile.is_public_registration_default`
  marks one or more live Group presets to assign after verification/approval.
  `Scope.description` is optional and nullable for inline-safe edits.
- `client_ip_config` — Centralized Client IP resolution configuration. Supports
  `mode` (`auto`, `x_forwarded_for`, `remote_addr`, `x_real_ip`, `cloudflare`,
  or `custom`), `trusted_proxy_hops` (0–8), and `custom_header` for custom mode.
  Resolution is only as good as the proxy chain feeding it: each proxy hop must
  append the client to `X-Forwarded-For` (the scaffold's Caddy trusts
  private-range upstreams; a front terminator needs e.g. HAProxy
  `option forwardfor`), and `trusted_proxy_hops` must equal the number of
  trusted hops that append — the scaffold default of `1` matches one front
  proxy ahead of the bundled Caddy/nginx. See
  [Getting Started → Behind a Front Proxy](getting-started.md#behind-a-front-proxy--tls-terminator).
- `public_root_theme` — Fixed theme applied to anonymous visitors on the public
  page (`public_root_config.public_root_theme`, blank = inherit the normal theme).
  Its stylesheet is emitted even if it is not in the normally-allowed theme set.
  The control appears under Themes and Typography only while public page is enabled.
- `public_root_title` / `public_root_meta_description` — Optional `<title>` and
  `<meta name="description">` emitted only for the anonymous public index
  (`public_root_config.*`, length-bounded). Exposed as `APP_CONFIG.security.*`;
  the controls appear under Identity only while public page is enabled.
- `show_titlebar_on_public` / `show_sidebar_on_public` — Centralized public page
  chrome toggles (`public_root_config.*`, both default **off** = hidden). They
  replace the deprecated `titlebar_config.hide_on_public_unauthenticated_index` and
  gate `base.html`'s titlebar/sidebar for
  anonymous public page visitors via the shared `_is_public_index()` context flag.
  Their controls appear under Titlebar and Sidebar respectively, only while public
  page is enabled.
- `default_table_density` — System default table density (`balanced`, `dense`, or `roomy`)
- `default_form_density` — System default form field spacing (`balanced`, `dense`,
  or `roomy`), independent of table density. Drives `--dlux-form-*` CSS variables
  via `body[data-dlux-form-density]`. Exposed as `APP_CONFIG.appearance.default_form_density`.
- `default_modal_size` — Default width of the shared dynamic modal (`compact` →
  `modal-lg`, `standard` → `modal-xl`, `wide` → `modal-xl dlux-modal-wide`). The
  resolved class is `APP_CONFIG.appearance.modal_size_class`.
- `table_edges` — Global Dlux table-shell corner style (`layout_config`; edited on the
  **Themes & Fonts** step, since edge shape is a
  surface decision like the palette and every builder previews in it):
  `curved` uses the shipped 1.35rem radius, `half_rounded` uses
  square top corners with 1.35rem bottom corners, and `normal` uses the standard
  Bootstrap 0.375rem radius. `base.html` emits the normalized choice as
  `body[data-dlux-table-edges]`; `tables/css/main.css` applies it through shared
  top, bottom, and shape variables to the shell, card, header cells, and footer.
- `card_edges` — Global Dlux outer-card corner style (`layout_config`; edited on the
  **Themes & Fonts** step alongside `table_edges`):
  `curved` applies the house `1.35rem` radius, `half_rounded`
  applies `0 0 1.35rem 1.35rem`, and `normal` applies the standard `0.375rem`.
  Child card sections, list-group bottoms, Ribbon surfaces, and profile panels
  consume the same shape contract. Opt an element in with
  `data-dlux-card-surface` or out with `data-dlux-card-edges-ignore`; a control
  whose proportions are the point — a progress track, say — should opt out
  rather than cohere. `base.html` emits the
  normalized choice as `body[data-dlux-card-edges]`; `base/css/card_edges.css`
  targets Bootstrap and Dlux card surfaces while excluding table cards and modal
  shells. Custom card surfaces can opt in with `data-dlux-card-surface` or opt out
  with `data-dlux-card-edges-ignore`.
- Accent edges are independent, default-off settings:
  `sidebar_config.accent_edge` is configured in Sidebar,
  `titlebar_config.accent_edge` in Titlebar, and
  `layout_config.table_accent_edges` under Layout's table controls. `base.html`
  emits one body state attribute per surface. Their rules live in each surface's
  existing stylesheet and use the active theme's `--primal` color with CSS
  logical borders, so sidebar and table edges follow RTL/LTR direction. The
  titlebar accent is declared after theme surface rules so their bottom-border
  styles cannot mask it.
- `sticky_table_headers` / `resizable_table_columns` / `zebra_striping` — Toggle
  (default on) the sticky table header row, draggable table-column resizing, and
  alternating row shading; gated in `tables.css` / `tables.js` via
  `body[data-dlux-sticky-header]`, `body[data-dlux-table-resize]`, and
  `body[data-dlux-zebra]` emitted from `base.html`. Enabled headers show subtle
  resize dividers. Dragging one divider redistributes the fixed table width across
  the other columns, keeping the table inside its parent even with sticky headers;
  proportional widths are stored per table in browser `localStorage` and can be
  reset by double-clicking a resize handle. After resizing, nowrap body-cell values
  such as dates truncate with an ellipsis rather than overlapping adjacent columns.
- `options_style` — Layout of the Options page (`/sys/options/`): `cards` (default,
  rearrangeable card grid), `tabs` (one section at a time behind a generated tab
  strip — the Admin panel is the first tab), or `compact` (a dense single-page,
  desktop-app-style list). Exposed at `APP_CONFIG.appearance.options_style` and
  emitted as `data-options-style` on `#dluxOptionsGrid`; `options.css`/`options.js`
  render the three modes from the same card DOM .
- `row_actions_style` — How table row actions are triggered (`layout_config`):
  `context` (default) keeps the right-click / long-press
  context menu; `column` adds a dedicated last three-dot column (`dlux_row_actions`)
  and turns the row's right-click marker (`data-dlux-context`) off so the button is
  the only trigger; `both` enables the column and the context menu. Distinct from a
  table's `dlux_actions` Meta flag, which gates whether row actions exist at all.
  The column is added by the patched `Table.__init__` and its three-dot button
  (`.dlux-row-actions-trigger`) reuses the row's `data-dlux-actions` payload via the
  shared context-menu JS. Exposed at `APP_CONFIG.appearance.row_actions_style`.
- `ribbon_layout` — How the list-page ribbon is arranged (`layout_config`): `default`
  (title and actions on one row, filters
  beneath), `stacked` (actions on their own row under the filters), or `compact`
  (one row: no title, actions as the last column of the filter row). Rendered by
  `{% dlux_ribbon %}` from `dlux/templates/dlux/ribbon/_<layout>.html`.
  The layout alone decides where the actions sit, so there is no separate
  setting for it. `compact` also overrides `ribbon_title`, enforced server-side
  by `Ribbon.shows_title` and mirrored in the Ribbon step by
  `ribbon/js/ribbon_settings.js`.
- `ribbon_style` — How the ribbon looks, independently of its arrangement
  (`layout_config`): `accent` (a coloured edge down the side of a
  bordered header), `panel` (a softly rounded, raised panel), or `flat` (no
  panel, just a dividing rule). Emitted as `dlux-ribbon-skin-<style>` on the
  root, which also carries `data-dlux-card-surface` so `card_edges` applies, and
  `glass-profile` on the panel skin so the themes own its surface. A new style is
  a CSS block plus a choice and an `option_meta` entry.
- `ribbon_title` — Whether the page title renders inside the ribbon (`layout_config`,
  default `True`). Off means the ribbon carries filters and actions only
  and the page supplies its own heading.
- `ribbon_advanced_trigger` — How the advanced filters are reached (`layout_config`):
  `button` (default, a toggle whose open state is remembered per list in
  `localStorage`), `always` (the panel is always open and no toggle renders), or
  `off` (the advanced fields are not rendered at all). A server-rendered open panel
  wins over a stored "collapsed" so a filter that is in effect is never hidden.
- `footer_text` — Optional copyright/description line for the global page footer
  (`layout_config.footer_text`, max 300 chars, blank by default). Edited from
  *System Settings → Identity → Footer* and exposed to templates as
  `APP_CONFIG.appearance.footer_text`; the `dlux/system/footer.html` partial
  renders it, falling back to `DLUX_STRINGS.footer_text` then `© <year> <system name>`.

### Activity Logging (`log_config`)

`ActivityLog` is the single store for all logs (`UserActivityLog` remains an importable
alias). Every row carries a `category`:

- `user` — project work and dev-invoked logs (auto-discovered project/auxiliary models).
- `system` — dlux-internal events (`app_label == 'dlux'`, backups, etc.).
- `audit` — security events (login success/failure, logout, lockout, 2FA
  enable/disable/failure, password change, session & trusted-device revoke, permission
  denied). Audit rows are **append-only** (cannot be edited/deleted in-app) and are never
  auto-pruned by default.

`log_config` (setup step 17, Logging) governs logging:

- `enabled` — master switch (does not gate audit).
- `user` / `system` — each has `enabled`, `default_actions` (`create`/`update`/`delete`),
  `retention_days` (0 = keep forever), and a sparse `models` override map keyed by
  `"app_label.model"` supporting per-action sub-toggles.
- The system list carries a synthetic **User accounts** entry (`dlux.useridentity`)
  controlling the unified User+Profile identity log — user accounts are a core dlux
  component, so identity rows are stored under the `system` category.
- `audit` — `enabled` (always on), per-event `events` flags, `immutable`, and its own
  `retention_days`.

Only models that produce meaningful logs appear in the grid — Django framework internals
(`auth`/`sessions`/`contenttypes`/`admin`), health-check/`testmodel` models, and dlux
operational/identity/self/dummy models (devices, presence, notifications, backups, Profile,
ActivityLog, the fieldless Section placeholder) are hard-excluded.

**Custom actions:** actions beyond `create`/`update`/`delete` (e.g. `DOWNLOAD`, `EXPORT`,
`APPROVE`) are **logged by default** with no configuration. To surface a toggle for one in
the settings grid, declare it on the model:

```python
class Decree(ScopedModel):
    dlux_log_actions = ["download", "export"]   # adds per-action toggles in the Logging step
```

A dev can then disable a specific action via its per-model `actions` override
(`{"download": false}`) without affecting CRUD. Security-sensitive account actions (password
reset, 2FA, lockouts) are logged under `audit`, not the per-model grid.

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

### Profile Page and Onboarding (`profile_config`)

`profile_config` (setup step 14, Profile) governs the user profile page and the
first-login experience — it is **not** personalization defaults (those stay in
theme/typography/layout/language configs) and **not** per-user prefs (those live in
`Profile.preferences`):

- `show_completion_widget`, `show_session_device_cards`, `show_activity_feed` — gate the
  matching profile-page sections. The profile activity feed shows at most the latest five
  project activity entries and latest five system interaction entries. Their System Settings
  controls share an auto-fitting row and wrap as the available width narrows.
- `security_nudges` — `off` / `subtle` / `persistent` (account-health prompt for missing 2FA).
- `homepage_config.allow_user_override` — let users pick their own landing page
  (stored as `Profile.preferences['user_home_url']`; honoured at login after an
  explicit `?next` and before `homepage_config.default_url` via
  `resolve_user_home_url()`).
  `profile_config['allow_user_home_url']` is a compatibility mirror.
  The same switch lets administrators assign landing pages (no schema change):
  **Edit User** writes `Profile.preferences['admin_home_url']`, which
  `/sys/api/preferences/update/` refuses to write and `/sys/api/preferences/reset/`
  keeps; the group preset form writes `extra_config['group_home_urls']`
  (`{group name: url}`, kept across renames and pruned on delete, via
  `get_group_home_urls()` / `set_group_home_url(name, url, previous_name=None)`).
  Both fields are hidden while the switch is off. Resolution order is the user's own
  pick, then `admin_home_url`, then the first active group preset by name with an
  entry, then `default_url`; `resolve_assigned_home_url(user, config=None)` returns
  the admin part alone and skips any page the user cannot open
  (`build_user_home_url_options`). `user_home_override_enabled(config=None)` reads
  the switch. Options and the first-login modal label the "default" choice with the
  assigned page.
- `onboarding_enabled` + `onboarding_options` (`theme`/`language`/`fonts`) —
  whether the first-login modal runs and which preferences it offers. These three choices
  render as an evenly distributed, wrapping horizontal rail in System Settings.
  `homepage_config.allow_user_override` independently controls whether the same modal and the
  Options page expose the permission-filtered landing-page selector.

System and anonymous landing behavior share `homepage_config`: `default_url`
is the authenticated/system destination and `public.url` is the optional separate
anonymous destination. Per-user `user_home_url` remains in `Profile.preferences`.
The `home_url`, `public_root_config` and flat public-page keys are synchronized
compatibility mirrors until 2.0; see [Deprecation Countdown](deprecation-countdown.md).

**Initial User Setup** is the per-user first-login counterpart to the system setup wizard: a
lightweight dlux dynamic modal (`/accounts/welcome/`, `initial_user_setup`) that auto-opens
once per user when `onboarding_enabled` and the user's `Profile.is_configured` is false. It
writes the chosen theme/language/fonts (+ optional home override) into `Profile.preferences`
and sets `Profile.is_configured`; "Skip for now" just sets the flag. The auto-open trigger is
gated by the `DLUX_SHOW_INITIAL_USER_SETUP` context flag, and is suppressed while
`Profile.preferences["force_password_change"]` is active so a first-login password change
always happens before optional onboarding preferences.

### Backups (`backup_config`)

`backup_config` (setup step 18, Backups) holds the schedule, retention, retry and
incremental-chain policy. Its keys and the backup lifecycle are in
[Backups](backups.md).

### Theme and Options Hooks

Theme runtime:

- official theme ordering comes from `dlux/themes.py`
- the options page uses `.theme-preview` selectors
- the sidebar toolbar picker uses `.theme-option-circle` selectors
- runtime theme changes dispatch the `dlux:theme-changed` event so secondary UI such
  as the sidebar indicator can sync without a refresh
- a page links only the active theme's stylesheet (`DLUX_ACTIVE_THEME`,
  `link[data-dlux-theme-css]`); the other allowed themes' links sit in the inert
  `<template id="dlux-theme-stylesheets">`
- `window.setTheme(slug)` loads the target theme's stylesheet beside the active one
  and switches once it has loaded; only the latest of several quick switches applies
- `window.dluxLoadThemeStylesheet(slug[, url])` loads a theme's stylesheet without
  switching and returns a promise of `true` once it has loaded (`false` when no URL is
  known or the request failed)

Options page:

- Options cards are draggable through per-card handles and the current order is
  persisted in browser `localStorage`
- the wide System Info card intentionally keeps a double-column span inside the grid
- Autofill and Reset Defaults are standalone cards in the shared Options card system,
  not nested sub-cards
- `tabs` style keeps Theme and Language as separate cards/tabs even when the
  card/compact layouts would merge a small number of choices into one combined card
- the authenticated Navbar groups Dlux-owned routes under an unclickable `System`
  crumb by default; unplaced Dlux system routes may also follow
  `SYSTEM_ROUTE_META[*].breadcrumb_parent` to mirror Dlux page links, so Backup &
  Restore falls under Application Options unless the hierarchy builder explicitly
  places it elsewhere; configurable Dlux system routes remain available in that
  builder for overrides

## Tables

### Framework-Owned Table Surface

Dlux owns the default table chrome for standard `django_tables2` tables.

- stock `django_tables2` templates such as `django_tables2/bootstrap5.html` are
  remapped at runtime to `dlux/tables/table.html`
- tables with no explicit template are also auto-captured
- explicit non-stock custom templates are left alone by default
- the system default density comes from `SystemSettings.default_table_density`
- the per-user override lives in `Profile.preferences["table_density"]`
- the per-user page-size preference lives in `Profile.preferences["table_page_size"]`
- built-in pagination and page-size controls are rendered by `dlux/tables/table.html`
- the paginator enforces `dlux_per_page_options` and fixed `dlux_per_page` values even
  when the URL supplies another size; invalid sizes fall back to the saved/default
  value, including prefixed and custom `Meta.per_page_field` query parameters
- the recommended handwritten-table base class is `dlux.tables.DluxTable`
- the framework list-screen arrangement is `dlux/list_page.html` (Ribbon over table,
  no card); blocks `list_before_table`, `list_body`, `list_after_table`,
  `list_modals`, `list_page_attrs`

Supported table Meta overrides:

- `dlux_table = False` to opt out of the framework-owned renderer
- `dlux_density = "dense" | "balanced" | "roomy"` to force density for one table
- `dlux_per_page = 20` to force a fixed default page size for one table
- `dlux_per_page_options = (10, 20, 50, 100)` to override the built-in page-size choices
- `dlux_actions = False` to disable default Dlux row actions
- `dlux_show_footer = False` to drop the footer toolbar (page-size, density switcher,
  record summary, pagination); such a table renders unpaginated, since nothing would
  be left to reach page two

Supported table extension hook:

- `get_dlux_row_actions(self, record, base_actions)` to extend or replace the default
  action list before permission filtering

Column layouts are described in [Table Columns](table-columns.md).

### Context Menu Events

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

### Common Activity Log Actions

The system records several action families out of the box, including:

- `CREATE`
- `UPDATE`
- `DELETE`
- `LOGIN`
- `LOGOUT`
- `DOWNLOAD`
- `EXPORT`

## Helpers

### View and Security Helpers

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

### Form and UI Helpers

| Helper | Purpose |
| --- | --- |
| `build_file_field('field_name', css_class='...')` | Render the Dlux custom file widget explicitly instead of relying on template shadowing. Field validation errors render visibly below the file card; set `field.widget.attrs['data-max-file-bytes']` for immediate client size validation while retaining server-side validation. |
| `build_settings_toggle_field(form, 'field_name', css_class='...')` | Render the shared setup/System Settings toggle-card control for boolean fields. |
| `DluxLookupField(queryset=..., create={...})` | Turn a ForeignKey into a search-and-add box: type a name, reuse an exact match, get warned about a near miss, add what is genuinely new. See [UI Integration](ui-integration.md#search-and-add-fields). |

### Frequently Used Helpers

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
| `apply_public_registration_defaults(user)` | Apply the marked public-registration default scope and matching global/scope Group presets to an activated public-registration user |
| `collect_related_objects(instance, ignore_relations=None)` | Inspect reverse and related objects for reporting or delete warnings; `ignore_relations` names internal accessors to skip |
| `has_related_records()` | Fast relation check before destructive actions |
| `setup_filter_helper()` | Normalize filter UI and clear-button behavior |
| `arabic_search_q(term, fields)` | Variant-aware Arabic `icontains`: one OR'd `Q` over `fields` matching every common spelling of `term` (alef/hamza forms, ي/ى/ئ, ة/ه, ق/غ, و/ؤ, Farsi ی/ک, Arabic-Indic digits, ignoring diacritics/tatweel/hamza) via `__iregex` — stored values need no migration |
| `arabic_search_pattern(term)` | The underlying regex builder (confusable letters become character classes); reusable for custom lookups |
| `normalize_arabic(value)` | Fold a string to one canonical Arabic spelling (for Python-side comparison, dedup keys, or a stored shadow column); `ARABIC_EQUIVALENCE_GROUPS` is the overridable default fold table (`groups=` kwarg on all three) |
| `set_field_attrs()` | Apply DjangoLux-friendly widget classes and affordances to a form, including the shared datepicker hook (`.dlux-datepicker`; `.flatpickr` is still accepted) |
| `translate_choices()` | Translate choice lists using the system translation engine |
| `log_user_action()` | Create consistent audit log entries |
| `fetch_file()` | Download one file, many files, or ZIP bundles from model instances |
| `fetch_excel()` | Export queryset data to Excel with hidden system/file columns |

### Permission Visibility

| API | Purpose |
| --- | --- |
| `dlux.access.register_permission_visibility_filter(fn)` | `fn()` returns a `Q` over `Permission` to hide from the group/user permission editors, or `None`. Evaluated per form; duplicates ignored. |
| `dlux.access.unregister_permission_visibility_filter(fn)` | Remove a filter (tests). |
| `dlux.access.hidden_permission_ids()` | Permission ids hidden right now. |
| `dlux.forms.keep_hidden_permissions(form, current, submitted)` | `submitted` plus the `current` permissions the form hid; the group and user forms save through it. |

See [Developer Guide](developer-guide.md#hiding-permissions-of-a-disabled-feature).

## Template Tags and Filters

### `dlux_tags`

| Name | Type | Purpose |
| --- | --- | --- |
| `dlux_timesince` | simple tag | Translated relative timestamp output |
| `include_if_exists` | simple tag | Render a template only if it exists |
| `include_once` | simple tag | Render a template at most once per request (dedupes shared asset partials) |
| `dlux_ribbon` | simple tag | Render a list page's ribbon — title, filters and actions — from the `ribbon` context object put there by `dlux.ribbon.RibbonMixin`; `{% dlux_ribbon %}`, or pass one explicitly. Renders nothing when there is no ribbon. See [Ribbon](ribbon.md). |
| `dlux_ribbon_field` | filter | The bound field for a name, or empty when the form lacks it — used by the ribbon templates |
| `dlux_audit_trail` | inclusion tag | Render a grouped audit block (created/edited/deleted by and at) for a model instance — `{% dlux_audit_trail object %}`. Self-gates on the `show_audit_fields` setting + `dlux.view_audit_fields` permission (deleted line is superadmin-only); renders nothing otherwise. Drop into any detail template to replace hand-rolled audit sections. |

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

## Authorization Contracts

- `DynamicModalManagerView` and `DynamicModalDeleteView` are backend-authorized
  surfaces, not login-only helpers
- `accounts/profile/edit/<pk>/modal/` is self-only
- dedicated user-management modals follow the same staff/scope/superuser rules as
  `dlux/views/users.py`
- `/sys/users/` and user-detail surfaces require `auth.view_user` OR
  `dlux.manage_staff` for staff callers (superusers still bypass)
- **Staff Tier System**: Three non-superuser staff tiers exist:
  - **Global Staff** (`is_global_staff`): Non-scoped staff with `dlux.manage_scopes`
    permission — can create scopes, assign any scope, and manage ALL users
  - **Central Staff** (`is_central_staff`): Non-scoped staff WITHOUT `manage_scopes` —
    can only create/manage scopeless users, completely blind to scoped users
  - **Scoped Staff**: Staff assigned to a specific scope — can only manage users within that scope
- Only **superusers** can create Global Staff users (assign `manage_scopes` permission)
- Global Staff and superusers can create Central Staff
- Central Staff cannot see scoped users in `/sys/users/`, cannot assign scopes, and
  cannot access scope management
- user-detail activity snippets require `dlux.view_activitylog`
- sidebar system items, dashboard cards, and user-hub shortcuts for Users / Sections /
  Activity Log follow the same helper-backed authorization rules
- section-management routes require `dlux.view_sections` or `dlux.manage_sections`
- `filter_context_actions()` lets `manage_sections` reveal only actions flagged
  `section_action: True`; it never bypasses per-model delete or change permissions
- Options diagnostics are privileged-only; personal preference controls remain
  available to authenticated users
- `SYSTEM_ROUTE_META` supplies a system route's `group_key` before model app-label
  inference, so `manage_users` stays under dlux System even though it is backed by
  `auth.User`

### Sidebar Permission Inference

Sidebar items are only visible to users who have the required view permission. The
permission for each item is inferred in this order:

1. **Explicit decorator**: `sidebar_permissions` or `permission_required` on the view
   callback — used as-is.
2. **System route meta**: items in `SYSTEM_ROUTE_META` use their declared `__dlux_*`
   permission tokens:
   - `manage_users` → `__dlux_user_directory__`
   - `user_activity_log` → `__dlux_activity_log__`
   - `manage_sections` → `__dlux_sections_view__`
   - `options_view` → `__dlux_authenticated__`
   - `system_backup_page` → `is_superuser`
3. **Model-based inference**: for class-based views with a model, the permission is
   `app_label.view_model_name`.
4. **URL pattern inference**: for function-based views without a model, the app label
   comes from the URL namespace (or callback module) and the model name from the URL
   name prefix (e.g., `documents:outgoing_list` → `documents.view_outgoing`).
5. **No inference**: if none of the above produce a permission, the item is hidden
   from non-superusers.

Internal tokens are resolved by `user_matches_permission_token()` in
`dlux/utils/authorization.py` and re-exported from `dlux.utils`.

## Naming: Management Screens

Two conventions, so the name tells you what a thing is:

- **URL names are `manage_<plural>`** — `manage_users`, `manage_scopes`,
  `manage_groups`, `manage_sections`, `manage_assets`.
- **Template names say whether it is a page or a fragment.**
  `manage_<plural>.html` is a full page that extends a base;
  `_<noun>_manager.html` is an embeddable partial rendered into a modal, and
  carries the leading underscore dlux uses for every partial.

`dlux/tests/test_ribbon.py` asserts both, so the distinction stays load-bearing
rather than coincidental.

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

See [Optional SSO Packages](sso.md), [Public Registration
Playground](registration.md), and [DSRP-1 Security Standard](security-dsrp-1.md).

## Feature Guides

These features are documented in their own guides:

| Feature | Guide |
| --- | --- |
| Backups and restore | [Backups](backups.md) |
| Inline updates, runtime volume, updater routes | [Verified Inline Updater](inline-updater.md) |
| App-owned preferences and settings | [UI Integration](ui-integration.md#app-preferences-and-app-owned-settings) |
| Options-page cards | [UI Integration](ui-integration.md#options-page-cards) |
| Global search | [UI Integration](ui-integration.md#global-search) |
| Unsaved-changes guard and dismissible dialogs | [UI Integration](ui-integration.md#unsaved-changes-guard) |
| Search-and-add (lookup) fields | [UI Integration](ui-integration.md#search-and-add-fields) |
| Alert auto-close and the Lux signature | [UI Integration](ui-integration.md#alert-auto-close) |
| Assisted entry and sticky forms | [Template Customization](template-customization.md#assisted-entry) |
| Entry clipboard | [Entry Clipboard](entry-clipboard.md) |
| Titlebar and user hub styles | [System Configuration](system-configuration.md) |
| Translation keys and coverage | [Translations](translation-guide.md) |
| Document files and stored-file serving | [Document Files](document-files.md) |
| OCR | [OCR](ocr.md) |
| PDF toolkit | [PDF Toolkit](pdf-toolkit.md) |
| ScanLink | [ScanLink](scanlink.md) |
| Table column layouts | [Table Columns](table-columns.md) |
| Ribbon | [Ribbon](ribbon.md) |
| Weather | [Weather](weather.md) |

## Codebase Entry Points

When you need to trace behavior in the code, these are the usual first stops:

- `dlux/models/` for `SystemSettings` (`settings.py`), `ScopedModel` (`base.py`),
  `Profile` (`users.py`), notifications, files, backup/restore records and updater
  state
- `dlux/system/` for settings constants, defaults, normalizers and the registry
- `dlux/forms/` for form logic: `system_settings.py` and `system_settings_groups/`
  (setup wizard), `users.py`, `auth.py`, `registration.py`, `scopes.py`,
  `permissions.py` and `builders.py` (the developer-facing field builders)
- `dlux/views/sections.py` for sections and dynamic modal flows
- `dlux/views/updater.py` and `dlux/updater/` for updater HTTP boundaries,
  verification, runtime storage and orchestration
- `dlux/translations/` for built-in strings and language resolution
- `dlux/utils/` for authorization, configuration merging, filtering and CRUD helpers,
  import/export, navigation, settings integration and UI utilities
