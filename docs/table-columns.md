# Configurable table columns — 1.14 beta

The published 1.14.0b3 beta provides the Tables settings step, canonical storage, column discovery, runtime overlays and interactive builder. Canonical audit/deletion sets and symmetric audit visibility remain in place. It integrates the 1.13.2 setup, search and tour fixes and paginated backup/restore tables. The table inspector and ribbon ordering use additive migration `0028_tables_config`.

## Sparse column configuration

### Personal column organization (1.14.1)

Authenticated viewers can open **Arrange columns** above a Dlux table. Hide columns, drag them into order, or use the up/down buttons. **Restore** removes only that table's personal override and follows the current administrator defaults. Labels, icons and administrator sorting remain system settings. At least one configurable data column stays visible; dedicated action, scope and record-visibility controls remain outside personal configuration.

Personal settings are applied after the developer baseline and `SystemSettings.tables_config`. They never reveal a developer-excluded or administrator-hidden column. Changed administrator restrictions take effect on the next render and are checked again when saving an already-open organizer. New columns follow the current administrator order unless the viewer arranges them. Tables without a model and anonymous viewers have no organizer. A developer can opt a table out with `Meta.dlux_user_columns = False`.

The GET/POST endpoint is `/sys/api/preferences/tables/columns/` (`user_table_columns`). GET returns Dlux modal HTML. POST accepts a signed `token` and `preferences` JSON (`order`, `hidden`, or `reset: true`); success reloads the current page, preserving its query string. A short-lived, user-bound signed catalog comes from the actual authorized table render, rather than accepting arbitrary model/table discovery from the caller. It contains column names/labels only and never reads rows. Saving requires login and CSRF, rechecks current administrator restrictions, locks the caller's profile, preserves unrelated preferences and enforces the profile JSON size cap. Expired or foreign tokens are refused. Preferences live in `Profile.preferences['table_columns'][table_key]`, using a stable key derived from the table class, model and prefix. Added/removed columns and audit toggles do not reset personal choices; separately prefixed variants do not overwrite each other. No migration is required.

`SystemSettings.tables_config` is an additive JSON field with database default `{}`. It is registered with the settings registry, runtime configuration and settings import/export. The **Tables** step sits between Ribbon and Components and owns table density, accent edges, sticky headers, resizing, zebra stripes, row actions and audit/soft-deleted visibility. Components retains forms, modals and Options-page layout. Table/card corner shapes stay with Themes and Fonts. Existing permission gates for audit/deleted records are unchanged.

The flat settings keys remain public and unchanged. `tables_config` is canonical storage; `layout_config` retains synchronized legacy mirrors. `SystemSettings.load()` reads legacy values through without writing, preserving existing column overlays and explicit canonical values. The next ordinary settings save persists the canonical group and its mirrors. This uses additive migration `0028_tables_config`, depending on published `0027_opsrun_params`; there is no inline-unsafe data migration. ORM saves through either group, including `update_fields`, synchronize both groups; explicit canonical writes win when both groups are supplied. Loaded-value snapshots distinguish a legacy edit from unchanged cached canonical data. Cache entries from before this contract are refreshed from the database. Old project configuration/imports using `layout_config` remain accepted. Direct SQL or `QuerySet.update()` bypasses model synchronization and cache invalidation.

The defensive normalizer validates table preferences, drops malformed model entries and malformed column lists, removes duplicate names, and retains unknown column names for later runtime resolution. Missing table preferences use existing defaults. An explicit empty `hidden` or `order` list clears that preference in a partial import. Unrelated section saves preserve table settings and column overlays.

The Tables form owns a hidden `tables_config` JSON transport, including during first-launch file imports. Inactive sections preserve its native JSON initial value; a missing transport does not discard an existing overlay. The column builder uses this same transport.

```json
{
  "columns": {
    "documents.record": {
      "hidden": ["description"],
      "order": ["number", "title", "date"],
      "headers": {"title": {"labels": {"en": "Document", "ar": "المستند"}, "icon": "bi-file-text"}},
      "sorting": ["-date", "number"]
    }
  }
}
```

Keys are lower-case Django model labels (`app_label.model_name`); column names are table column identifiers. Store only changed preferences, never a snapshot of all columns. Optional `headers` entries hold language-keyed plain-text labels (up to 200 characters) and one validated `bi-*` icon class. `sorting` contains at most two distinct column aliases; prefix an alias with `-` for descending order. Explicit empty values can clear preferences in partial imports.

## Column discovery and runtime behavior

`dlux.discovery.tables.table_column_catalog(request=None, urlconf=None)` walks named routes, inspecting declared table classes and `get_table_class()` results. It also resolves model-backed dynamic managers through the same model-class resolver as their runtime and includes section tables. It constructs tables with empty data rather than querying their rows or rendering pages. Configuration/scope helpers and project constructors may still read settings. Columns shared by table variants are merged under the model key; display labels use model-qualified table translations and the request language. Audit/deletion columns (including project extensions), scope, row actions and code-hidden/excluded columns are omitted.

`SystemSettingsForm.table_columns_catalog` supplies this catalog lazily and caches it for that form instance. The builder renders it only in Tables or the full setup wizard. Discovery suppresses only the saved presentation overlay, so hidden columns remain available to re-enable. Intentionally blank headers get builder-only labels from `table_columns_<column_name>` translations, falling back to a readable column name; their runtime headers remain unchanged. A failed constructor, URL walk or request-dependent table-class resolver logs a diagnostic and degrades safely. Function views other than the built-in section manager, tables created only inside page execution, and columns added after the common initialization hook cannot be fully inferred. Those columns remain usable at runtime but may not appear in the catalog.

The shared table initialization hook applies each model's overlay to both generated and handwritten Dlux-managed tables. Unknown or removed names are ignored; newly introduced columns retain their default visibility and follow explicitly ordered columns. The overlay never reveals a column hidden/excluded by code and leaves tables with no matching configuration unchanged. If configuration would hide every data column, the first baseline data column remains visible. Audit, deletion, scope and row-action columns retain their existing gates and positions; this overlay cannot hide, reveal or reorder them. Tables using an explicit custom template or opting out of Dlux rendering ignore the overlay.

Installing the table hook is idempotent. Rebuilding Django's app registry cannot wrap it again and rerun authorization without the original request, or apply the presentation overlay twice.

Column preferences control presentation. They do not change queryset filtering, permissions or export authorization. Keep sensitive data protection in the backend.

Header labels use the current Dlux language and fall back to code labels when no override exists for it. Icons and labels render through the shared table template with escaping. Default sorting applies only to visible, orderable, configurable columns; stale, protected and excluded names are ignored. Unsupported computed sorts log a warning and retain the table's code ordering. A request's explicit sort takes precedence through the normal django-tables2 request configuration.

## Using the builder

Open **Options → Tables**. Each discovered model uses the ribbon builder's existing card shell and the shared element inspector. Select a header to edit its labels in the configured languages, choose an optional icon with the shared picker, show/remove it, reset it or assign primary/secondary default sorting and direction. There is no separate selection grid. Removed developer columns remain muted, selectable placeholders in the header strip so they can be restored. The last shown column cannot be removed. Audit/deletion, scope, row actions and code-hidden columns retain their dedicated controls and are absent from the inspector. Admin-created columns are outside this iteration's scope.

Like Ribbon, Sidebar and Navbar, the builder starts with **Show system items** off. Users, activity logs and other framework tables appear only when it is enabled. Catalog entries carry `is_system`: framework/Django infrastructure models, the configured user model and tables supplied by a `dlux` module are system items. If a model has several table variants, any supplied system variant makes that model a system item. Project tables generated through Dlux's shared manager/section views remain project items; inheriting `DluxTable` alone does not make a table a system item. A translated empty state explains the filter when an installation has only system tables.

This switch filters the builder only. It is not persisted in `tables_config`, does not dirty the form, resets to off when the builder reopens, and neither drops hidden system-table overlays nor disables their runtime application. Existing backend permissions continue to control access.

Drag shown headers within their own strip to reorder. The focused header also accepts Left/Right arrow keys in the current reading direction; the adjacent earlier/later buttons provide tap controls on phones. The strip scrolls horizontally within its card. Select the table title to access **Use table defaults**, with the ribbon's rewind icon; this removes only that model's overlay. The per-column **Restore** rewind restores its labels/icon/visibility and removes its sort assignment, while preserving other columns and header order. Restore is disabled when the selected column has no header, visibility or sort override, and updates immediately while editing. Dismiss the inspector with its clear-selection action before selecting a covered header. Save the normal settings form to apply changes to actual tables; closing without saving follows the existing discard guard.

Opening the builder or inspecting a header does not rewrite JSON or dirty the form. Edits retain unrelated table preferences, other models' overlays and stale column names. First-launch file imports refresh the header strip and inspector immediately. Only an explicit model reset removes that model's stale preferences. Labels, status announcements and controls use the dlux translation framework; assets are external, CSP compliant and theme/RTL aware.

Hiding and showing a column retains its position. Reverting labels, icons, sorting or ordering to the form's opening configuration restores the original JSON carrier, including its formatting; closing then skips the unsaved-changes prompt. A remaining change still prompts normally. This also works when an existing saved overlay is edited and reverted.

## Pagination

Since 1.14.0b3, URL page sizes cannot override the validated table size when django-tables2 configures the paginator. Invalid or oversized values fall back to allowed saved/default values; fixed metadata sizes, table prefixes and custom page-size fields remain supported. Shared request objects are unchanged.

## Personal column layouts

Personal layouts use the same header-strip renderer as the system builder, but
no inspector: since 1.15.2 each header carries an eye. An open eye means the
column is shown for you; a struck eye means it is hidden, and the header is
dimmed. Click the eye to switch. The last shown column's eye is disabled with a
"keep at least one column" hint. The ribbon gets an icon-only Arrange columns
action with a Dlux tooltip; without a ribbon the icon joins the existing table
footer or header controls. No separate button row is added. The standard modal
supports the eyes, drag, logical arrow keys, Restore, Save and Cancel. Restoring
or reverting edits compares the resulting layout with the original state.

Select a table title in the administrator builder to change **Allow personal
column layouts**. This is enabled by default. Its sparse setting is
`tables_config.columns["app.model"].user_columns`; `false` hides the action,
ignores stored personal layouts, and denies both GET and POST from existing
signed dialogs. Stored preferences are retained for re-enabling. Developer
exclusions, administrator-hidden columns and protected controls remain outside
personal customization. Header labels, icons and default sorting stay with the
administrator.
