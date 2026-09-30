# Deprecation Countdown

This page records live compatibility contracts and their concrete removal targets. Historical detail from the pre-v1.8 documentation reorganization is retained in `.xclude/docs/deprecation-countdown.md`.

## Active through v1.x

### Homepage settings aliases

`SystemSettings.homepage_config` is canonical. The legacy `home_url`, `public_root_config`, and profile landing-page permission paths are mirrored on save, accepted by runtime configuration/import, and scheduled for removal in v2.0. Move host code to `homepage_config` now; user-facing copy should call the anonymous destination the public page.

### Global-search titlebar aliases

`SystemSettings.search_config` is canonical. `titlebar_config.global_search_mode` and `titlebar_config.global_search_include_data` remain accepted/mirrored through v1.x and are removed in v2.0. Move host code to `search_config` now.

### Static/template compatibility paths

The `dlux/main/css/{main,buttons,index_cards}.css` compatibility stylesheets and `dlux/includes/messages.html` template shim remain until the next major release. New project code should use `dlux/base/css/...` and `dlux/notifications/messages.html`.

### Public package facades

The `dlux.forms`, `dlux.models`, `dlux.reports`, `dlux.discovery`, `dlux.backup`, and `dlux.translations` package facades are public API and remain permanently. Their internal module splits do not require host-project import changes.

### Raw `ImageField` for project images

As of v1.8.4 a model image or font belongs in the asset library through
`ManagedAssetField`, not a plain `ImageField`/`FileField`. See
[Managed assets](managed-assets.md).

Nothing is removed — Django's own fields are not dlux's to deprecate — but a
project adding a new raw image field is going against the standard, and the
namespaced picker, the permission-checked instant upload and the clean-up action
do not apply to it. Existing fields migrate by adding the asset field beside the
old one and adopting the stored file on first save; `SystemSettings.logo` and
`favicon` are dlux's own example of that pairing and stay readable indefinitely.

`Profile.profile_picture` is a deliberate exception and stays an `ImageField`.
An avatar is one person's, not a reusable library file, and nothing else should
be able to pick it — putting it in a shared, de-duplicating library would be the
wrong shape even before the permission question of a user editing their own row.

## Removed in v1.8.0

- `dlux.constants` — import from `dlux.system.constants`.
- Cookie-based assisted-entry preference (`enable_prefill`) — use `sticky_forms_enabled()` and `sticky_form_initial()`.
- The generated `dlux-updater` Compose service — reconciliation/migrations moved to `celery` `pre_start`; the state tick moved to Celery Beat. Existing generated stacks migrate through `./start.sh check --fix`.

## Removed in v1.10.0

Four compatibility contracts reached their removal date. Nothing below is importable, selectable
or accepted any more; each entry says what to use instead.

### `AUDIT_FIELD_NAMES`

`dlux.utils.AUDIT_FIELD_NAMES` was a plain alias of `DEFAULT_AUDIT_COLUMNS` and never carried a
project's additions. Use `dlux.system.constants`: `audit_column_names()` for the columns gated by
`show_audit_fields`, `deletion_column_names()` for the soft-delete pair, and
`record_visibility_column_names()` for both. Each is extensible by a host project through
`DLUX_AUDIT_COLUMNS` / `DLUX_DELETION_COLUMNS`. Note also that `deleted_by` is no longer treated
as an audit column: a deletion is not a change history, so it answers to `show_soft_deleted` and
the superuser gate along with `deleted_at`.

### In-container update executor

Removed: `DLUX_UPDATE_EXECUTOR = "inline"`, the executor behind it (the in-container check,
apply and rollback paths of `dlux.updater.service`, and the release-selection helpers
`fetch_simple_index` / `select_latest_candidate` that only it used), and the
`python -m dlux enable-updater` / `enable-agent` Compose migrations (`dlux.scaffold.legacy`).
Composer has performed every inline update since v1.8.0; `DLUX_UPDATE_EXECUTOR` is now ignored.
Existing generated stacks migrate with `./start.sh check --fix`. See
[Updater Consolidation](updater-consolidation.md) and [Verified Inline Updates](inline-updater.md).

### `archive_file` names on the file widget

The file-upload widget kept the names it had in `project-archive`'s document forms. They were
replaced in v1.8.3 and the shims are gone:

| Removed | Use |
| --- | --- |
| `build_archive_file_field(...)` | `build_file_field(...)` |
| `_build_archive_file_widget(...)` | `_build_file_widget(...)` |
| `archive_file_*` translation keys (read as a fallback) | `file_field_*` |
| `class="archive-file-input"` selecting the file-card template | `dlux-file-input` |
| `.archive-file-*` classes, `data-archive-file-*` attributes | `.dlux-file-*`, `data-dlux-file-*` |

`apply_archive_file_widgets` / `build_archive_file_fields_row` in archive and dhub are those
projects' own helpers built on `DluxFileInput`, not these shims. A project whose own widget
still carries `archive-file-input` (project-dhub) must move to `dlux-file-input`.

### `advanced_filter_helper`

`dlux.utils.advanced_filter_helper` is removed. It is superseded by the ribbon (`dlux.ribbon`),
which derives a list page's filter band from the FilterSet instead of a per-view
`advanced_config` dict, and whose layout is an administrator setting rather than fixed markup. See
[Ribbon](ribbon.md). `setup_filter_helper()` remains for a plain filter bar. `project-archive`,
`project-decrees`, `project-trademarks` and both `project-sales-crm` editions had moved to the
ribbon; `project-dhub` still calls the helper (6 sites in `documents/filters.py`) and must adopt the
ribbon before it upgrades past v1.9.x.
