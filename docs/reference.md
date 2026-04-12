# Reference

This page is the fast lookup sheet for common microSYS commands, routes, template tags, and helper utilities.

## Management Commands

| Command | Purpose |
| --- | --- |
| `python manage.py microsys_setup` | Create migrations, apply migrations, and run the config check. |
| `python manage.py microsys_setup --skip-check` | Skip the validation pass after setup. |
| `python manage.py microsys_setup --no-migrate` | Skip `makemigrations` and `migrate`. |
| `python manage.py microsys_check` | Validate apps, middleware, context processors, URLs, and Crispy settings. |

## Core Routes

| Route | Purpose |
| --- | --- |
| `/accounts/login/` | Login screen |
| `/accounts/logout/` | Logout |
| `/accounts/profile/` | User profile |
| `/sys/setup/` | First-launch system setup |
| `/sys/options/` | Options view |
| `/sys/users/` | User management |
| `/sys/logs/` | Activity log |
| `/sys/logs/<int:pk>/details/` | Activity log detail modal |
| `/sys/scopes/manage/` | Scope management |
| `/sys/sections/` | Section management |

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

## API Endpoints

### Autofill

| Route | Method | Purpose |
| --- | --- | --- |
| `/sys/api/last-entry/<app>/<model>/` | `GET` | Return the most recent record for sticky-form cloning |
| `/sys/api/details/<app>/<model>/empty_schema/` | `GET` | Return an empty field structure for clearing autofill targets |
| `/sys/api/details/<app>/<model>/<pk>/` | `GET` | Return serialized model details for autofill |

### Preferences

| Route | Method | Purpose |
| --- | --- | --- |
| `/sys/api/preferences/update/` | `POST` | Merge updated preference values into `Profile.preferences` |
| `/sys/api/preferences/reset/` | `POST` | Clear saved preferences and related session keys |

Common preference keys:

- `theme`
- `lang`
- `sidebar_collapsed`
- `sidebar_accordions`
- `sidebar_order`
- `autofill_enabled`

Common runtime sidebar config keys in `get_system_config()["sidebar"]`:

- `home_url_name`
- `entries`
- `enable_reorder`
- `show_toolbar`

Theme/runtime UI notes:

- official theme ordering comes from `microsys/themes.py`
- the options page uses `.theme-preview` selectors
- the sidebar toolbar picker uses `.theme-option-circle` selectors
- runtime theme changes dispatch the `microsys:theme-changed` event so secondary UI such as the sidebar indicator can sync without a refresh

## Context Menu Events

| Event | Purpose |
| --- | --- |
| `micro:record:view` | View a record from a context-enabled element |
| `micro:record:edit` | Open or route into an edit flow |
| `micro:record:delete` | Trigger a delete flow |

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

## Template Tags and Filters

### `microsys_tags`

| Name | Type | Purpose |
| --- | --- | --- |
| `ms_timesince` | simple tag | Translated relative timestamp output |
| `include_if_exists` | simple tag | Render a template only if it exists |

### `microsys_translation`

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
| `microsys_settings()` | Apply the default MicroSys settings requirements from a project `settings.py` via `microsys_settings(globals())`, including app stack, middleware, context processor, Crispy defaults, and core language/format defaults |
| `get_model_classes()` | Resolve model, form, table, and filter classes via conventions or overrides |
| `get_user_linked_models()` | Find all models with a OneToOneField to the User model |
| `resolve_model_by_name()` | Find a model class dynamically by name |
| `filter_context_actions()` | Hide context-menu actions the current user should not see |
| `collect_related_objects()` | Inspect reverse and related objects for reporting or delete warnings |
| `has_related_records()` | Fast relation check before destructive actions |
| `setup_filter_helper()` | Normalize filter UI and clear-button behavior |
| `advanced_filter_helper()` | Build a primary filter row plus collapsible advanced rows, optional action buttons, and separate hidden/clear preserve behavior |
| `set_field_attrs()` | Apply microSYS-friendly widget classes and affordances to a form, including the shared datepicker hook (`.ms-datepicker` with legacy `.flatpickr` compatibility) |
| `translate_choices()` | Translate choice lists using the system translation engine |
| `log_user_action()` | Create consistent audit log entries |
| `fetch_file()` | Download one file, many files, or ZIP bundles from model instances |
| `fetch_excel()` | Export queryset data to Excel with hidden system/file columns |

## Codebase Entry Points

When you need to trace behavior in the code, these files are the usual first stops:

- `microsys/models.py` for `SystemSettings`, `ScopedModel`, `Profile`, and scope-related models
- `microsys/forms.py` for the setup wizard form, user wizard, and runtime configuration form logic
- `microsys/views/sections.py` for sections and dynamic modal flows
- `microsys/translations.py` for built-in translation keys and language-resolution logic
- `microsys/utils.py` for discovery helpers, configuration merging, filtering helpers, and UI utilities
