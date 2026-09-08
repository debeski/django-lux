# Deprecation Countdown

This page records live compatibility contracts and their concrete removal targets. Historical detail from the pre-v1.8 documentation reorganization is retained in `.xclude/docs/deprecation-countdown.md`.

## Active through v1.x

### `AUDIT_FIELD_NAMES`

`dlux.system.constants` is canonical: `audit_column_names()` for the columns gated by
`show_audit_fields`, `deletion_column_names()` for the soft-delete pair, and
`record_visibility_column_names()` for both. Each is extensible by a host project through
`DLUX_AUDIT_COLUMNS` / `DLUX_DELETION_COLUMNS`.

`dlux.utils.AUDIT_FIELD_NAMES` remains a published alias of `DEFAULT_AUDIT_COLUMNS` and is
**removed in v1.10**. It is a plain tuple, so it never carries a project's additions — move to
`audit_column_names()`. Note also that `deleted_by` is no longer treated as an audit column:
a deletion is not a change history, so it answers to `show_soft_deleted` and the superuser
gate along with `deleted_at`.


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
template. All three shims are removed in v1.9.0.

**No callers remain as of v1.8.14 (2026-09-08).** The only thing still using them
was a set of `archive_file_*` string overrides in `project-decrees`,
`project-archive` and `project-dhub`; those are now `file_field_*`, so nothing
depends on the fallback and the shims can go on schedule. Note that
`apply_archive_file_widgets` / `build_archive_file_fields_row` in archive and dhub
are those projects' own helpers built on `DluxFileInput`, not these shims.

Projects styling or scripting against `.archive-file-*` or
`data-archive-file-*` must move now — those markup names are gone in v1.8.3,
with no shim.
## Scheduled for v1.10.0

### `advanced_filter_helper`

`dlux.utils.advanced_filter_helper` is superseded by the ribbon (`dlux.ribbon`),
which derives a list page's filter band from the FilterSet instead of a
per-view `advanced_config` dict, and whose layout is an administrator setting
rather than fixed markup. See [Ribbon](ribbon.md).

**Moved from v1.9.0 to v1.10.0 (2026-09-08).** As of v1.8.14 the remaining
callers are `project-archive` (6 sites), `project-dhub` (6) and
`project-trademarks` (7) — and none of the three uses `RibbonMixin` at all, so
this is adopting the ribbon rather than swapping a helper. Each call site
carries per-field placeholders and column classes that the ribbon replaces with
an administrator-chosen layout, which makes it a product decision per project
and one that wants visual sign-off. Doing that during the release that also
introduces the beta channel was too many moving parts at once.

`project-decrees` and both `project-sales-crm` editions have already moved to
the ribbon. The helper is unchanged and keeps working through v1.9.x. Migrate
those three before v1.10.0; pilot one filter against a running deployment before
converting the rest.
