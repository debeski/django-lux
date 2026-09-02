# Deprecation Countdown

This page records live compatibility contracts and their concrete removal targets. Historical detail from the pre-v1.8 documentation reorganization is retained in `.xpose/docs/deprecation-countdown.md`.

## Active through v1.x

### Homepage settings aliases

`SystemSettings.homepage_config` is canonical. The legacy `home_url`, `public_root_config`, and profile landing-page permission paths are mirrored on save, accepted by runtime configuration/import, and scheduled for removal in v2.0. Move host code to `homepage_config` now; user-facing copy should call the anonymous destination the public page.

### Global-search titlebar aliases

`SystemSettings.search_config` is canonical. `titlebar_config.global_search_mode` and `titlebar_config.global_search_include_data` remain accepted/mirrored through v1.x and are removed in v2.0. Move host code to `search_config` now.

### Static/template compatibility paths

The `dlux/main/css/{main,buttons,index_cards}.css` compatibility stylesheets and `dlux/includes/messages.html` template shim remain until the next major release. New project code should use `dlux/base/css/...` and `dlux/notifications/messages.html`.

### Public package facades

The `dlux.forms`, `dlux.models`, `dlux.reports`, `dlux.discovery`, `dlux.backup`, and `dlux.translations` package facades are public API and remain permanently. Their internal module splits do not require host-project import changes.

## Removed in v1.8.0

- `dlux.constants` — import from `dlux.system.constants`.
- Cookie-based assisted-entry preference (`enable_prefill`) — use `sticky_forms_enabled()` and `sticky_form_initial()`.
- The generated `dlux-updater` Compose service — reconciliation/migrations moved to `celery` `pre_start`; the state tick moved to Celery Beat. Existing generated stacks migrate through `./start.sh check --fix`.

## Scheduled for v1.9.0

### `archive_file` names on the file widget

The file-upload widget kept the names it had in `project-archive`'s document
forms. As of v1.8.3 the framework name is `file_field`:

| Old | New |
| --- | --- |
| `build_archive_file_field(...)` | `build_file_field(...)` |
| `_build_archive_file_widget(...)` | `_build_file_widget(...)` |
| `archive_file_*` translation keys | `file_field_*` |
| `.archive-file-*` classes, `data-archive-file-*` attributes | `.dlux-file-*`, `data-dlux-file-*` |

The two helper names stay importable from `dlux.forms`, a project's own
`archive_file_*` string overrides are still read as a fallback, and
`class="archive-file-input"` still opts a non-Dlux widget into the file card
template. All three shims are removed in v1.9.0. Projects styling or scripting
against `.archive-file-*` or `data-archive-file-*` must move now — those markup
names are gone in v1.8.3, with no shim.

### `advanced_filter_helper`

`dlux.utils.advanced_filter_helper` is superseded by the ribbon (`dlux.ribbon`),
which derives a list page's filter band from the FilterSet instead of a
per-view `advanced_config` dict, and whose layout is an administrator setting
rather than fixed markup. See [Ribbon](ribbon.md).

The helper is unchanged and keeps working through v1.8.x — five projects still
call it (`project-archive`, `project-decrees`, `project-dhub`,
`project-trademarks`, `project-sales-crm/gov_edition`). It is removed in
v1.9.0; migrate before then.

The in-container inline update executor, `DLUX_UPDATE_EXECUTOR="inline"`, and `python -m dlux enable-updater` are migration-only compatibility paths. Composer remains the required executor for generated inline updates. See [Verified Inline Updates](inline-updater.md).
