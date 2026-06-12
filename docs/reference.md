# Reference

This page is the fast lookup sheet for common DjangoLux commands, routes, template tags, and helper utilities.

## Scaffold Commands

| Command | Purpose |
| --- | --- |
| `python -m dlux startproject myproject` | Create a new DjangoLux-ready Django project. |
| `python -m dlux startapp billing` | Create a new DjangoLux-native app in the current project. |
| `python -m dlux startapp billing --register` | Create the app and also patch project settings and URLs. |

Generated project baseline:
- `.secrets/.env` with scaffolded bootstrap secret values
- `config/settings.py` wired for env-driven Django secret, Postgres, Redis cache, and Celery
- `config/settings.py` wired with `corsheaders` / `csp`, their middleware, and starter CORS/CSP settings
- `compose.yml` and `compose.dev.yml` keeping the standard inline-env pattern
- a generated Docker baseline with `web`, `celery`, `db`, `redis`, `nginx`, `pgadmin`, `migrator`, and internal `smtp-relay` services
- `req.txt` pinned to the generated stable `django-lux` release

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
| `python manage.py dlux_check` | Validate apps, middleware, context processors, URLs, and Crispy settings. |
| `python manage.py dlux_settings status` | Inspect the `SystemSettings` singleton without creating it. |
| `python manage.py dlux_settings unconfigure` | Preserve settings but mark setup incomplete so `/sys/setup/` opens again. |
| `python manage.py dlux_settings delete --yes` | Delete the singleton row; the next load recreates it. |
| `python manage.py dlux_settings reset --yes` | Recreate the singleton from model defaults and mark it unconfigured. |
| `python manage.py dlux_settings export --output config.json` | Export portable System Settings JSON. |
| `python manage.py dlux_settings import --input config.json` | Import portable System Settings JSON and mark setup configured. |

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
| `/sys/setup/` | First-launch system setup |
| `/sys/options/` | Options view |
| `/sys/users/` | User management |
| `/sys/registrations/` | Superuser-only pending public registration approvals |
| `/sys/registrations/<int:pk>/approve/` | POST-only public registration approval |
| `/sys/registrations/<int:pk>/reject/` | POST-only public registration rejection |
| `/sys/reset_password/<int:pk>/` | Staff password-reset endpoint for a target user |
| `/sys/logs/` | Activity log |
| `/sys/logs/<int:pk>/details/` | Activity log detail modal |
| `/sys/scopes/manage/` | Scope management |
| `/sys/sections/` | Section management |

Section security contract:

- `/sys/sections/`, `/sys/section/details/`, `/sys/section/delete/`, and subsection CRUD endpoints require the existing section permissions
- section detail/delete and subsection CRUD no longer accept arbitrary `model=` tokens; the target must be a discovered Dlux section or discovered section child model
- `/sys/users/` plus the user-detail page/modal require `auth.view_user` for staff users (superusers still bypass)
- `/sys/reset_password/<int:pk>/` now requires `auth.change_user` and the same staff/scope/superuser target checks as the hardened user-management modal routes
- `/sys/logs/` and `/sys/logs/<int:pk>/details/` now require the explicit `dlux.view_activitylog` permission or superuser status rather than plain `is_staff`
- embedded activity snippets on user-detail surfaces only render when the caller also has `dlux.view_activitylog`
- sidebar-discovered system routes plus the built-in dashboard/user-hub shortcuts now mirror those same helper-backed checks instead of older template-only `is_staff` assumptions
- sidebar items are only visible to users with the required view permission; no implicit staff fallback (see Sidebar Permission Inference below)

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
- when `prevent_multiple_active_sessions` is enabled, each newly trusted session revokes every other active session for that user
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

Common runtime feature flags in `get_system_config()`:

- `email_2fa` — Enable email-based 2FA (set via `DLUX_CONFIG['email_2fa']` or the System Settings UI)
- `prevent_multiple_active_sessions` — When true, a newly trusted session becomes the user's only active session; untrusted logins remain allowed and do not evict trusted sessions.
- `email_config` — Redacted Dlux email delivery config. Supports delivery `transport` (`direct` or `relay`) plus `secret_storage` (`env` or `encrypted_db`); exports never include SMTP secrets.
- `public_registration_enabled` — Enable disabled-by-default public signup.
- `registration_activation_mode` — `auto_login_after_verify` or `verified_pending_approval`.
- `registration_throttle_enabled` — Enable cache throttles for public signup.
- `client_ip_config` — Centralized Client IP resolution configuration. Supports `mode` (`direct`, `header`, `proxy`), `header_name`, and `trusted_proxies` (hop count).
- `default_table_density` — System default table density (`balanced`, `dense`, or `roomy`)

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

Use the opt-out for alerts that remain actionable after the first few seconds, such as validation blockers, missing-secret warnings, setup/import instructions, or status messages that explain why a field must be changed before the form can submit. Do not use it for normal Django flash messages that should behave like transient success/error notices.

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

## Template Tags and Filters

### `dlux_tags`

| Name | Type | Purpose |
| --- | --- | --- |
| `dlux_timesince` | simple tag | Translated relative timestamp output |
| `include_if_exists` | simple tag | Render a template only if it exists |

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

Internal tokens are resolved by `user_matches_permission_token()` in `dlux/utils.py`.

## Codebase Entry Points

When you need to trace behavior in the code, these files are the usual first stops:

- `dlux/models.py` for `SystemSettings`, `ScopedModel`, `Profile`, and scope-related models
- `dlux/forms.py` for the setup wizard form, user wizard, and runtime configuration form logic
- `dlux/views/sections.py` for sections and dynamic modal flows
- `dlux/translations.py` for built-in translation keys and language-resolution logic
- `dlux/utils.py` for discovery helpers, configuration merging, filtering helpers, and UI utilities
