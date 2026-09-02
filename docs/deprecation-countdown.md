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
template. All three shims are removed in v1.9.0 — `project-decrees`,
`project-archive` and `project-dhub` still reference them as of v1.8.4. Projects styling or scripting
against `.archive-file-*` or `data-archive-file-*` must move now — those markup
names are gone in v1.8.3, with no shim.

### `advanced_filter_helper`

`dlux.utils.advanced_filter_helper` is superseded by the ribbon (`dlux.ribbon`),
which derives a list page's filter band from the FilterSet instead of a
per-view `advanced_config` dict, and whose layout is an administrator setting
rather than fixed markup. See [Ribbon](ribbon.md).

The helper is unchanged and keeps working through v1.8.x. Verified callers as
of v1.8.4: `project-archive`, `project-dhub`, `project-trademarks`.
`project-decrees` and both `project-sales-crm` editions have moved to the
ribbon. It is removed in v1.9.0; migrate those three before then.

The in-container inline update executor, `DLUX_UPDATE_EXECUTOR="inline"`, and `python -m dlux enable-updater` are migration-only compatibility paths. Composer remains the required executor for generated inline updates. See [Verified Inline Updates](inline-updater.md).
