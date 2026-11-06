# Configurable table columns

Administrators choose, per model, which table columns show, in what order, with
which header label and icon, and how a table sorts by default. They do this in the
**Tables** step of System Settings. Viewers can then arrange their own columns
within those limits (see [Personal column layouts](#personal-column-layouts)).

The configuration lives in `SystemSettings.tables_config`, added by the additive
migration `0028_tables_config`.

## Sparse column configuration

`SystemSettings.tables_config` is a JSON field with database default `{}`. It is
registered with the settings registry, runtime configuration and settings
import/export.

The **Tables** step sits between Ribbon and Components. It owns:

- table density, accent edges, sticky headers, resizing and zebra stripes;
- row actions and audit/soft-deleted visibility;
- the column builder.

Components keeps forms, modals and the Options-page layout; table and card corner
shapes stay with Themes and Fonts. The permission gates for audit and deleted
records are independent of these settings.

### Canonical storage and legacy mirrors

The flat settings keys stay public. `tables_config` is the canonical storage and
`layout_config` keeps synchronized legacy mirrors of the table keys:

- `SystemSettings.load()` reads legacy values through without writing,
  preserving existing column overlays and explicit canonical values. The next
  ordinary settings save persists the canonical group and its mirrors.
- ORM saves through either group, including `update_fields`, synchronize both
  groups. When both are supplied, explicit canonical writes win.
- Loaded-value snapshots tell a legacy edit apart from unchanged cached
  canonical data. A cached settings instance without that snapshot is reloaded
  from the database and re-cached.
- Project configuration and imports that use `layout_config` are accepted.
- Direct SQL or `QuerySet.update()` bypasses model synchronization and cache
  invalidation.

Migration `0028_tables_config` follows `0027_opsrun_params` and only adds the
field; it has no data migration, so it is safe for inline updates.

### Normalization and transport

The defensive normalizer validates table preferences:

- It drops malformed model entries and malformed column lists, and removes
  duplicate names.
- It keeps unknown column names for later runtime resolution.
- Missing table preferences use the defaults. An explicit empty `hidden` or
  `order` list clears that preference in a partial import.
- Saving an unrelated settings section preserves table settings and column
  overlays.

The Tables form owns a hidden `tables_config` JSON transport, also during
first-launch file imports, and the column builder writes through it. Inactive
sections keep its native JSON initial value, and a missing transport does not
discard an existing overlay.

### Overlay format

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

Store only changed preferences, never a snapshot of all columns.

| Key | Holds |
| --- | --- |
| model key | Lower-case Django model label (`app_label.model_name`). |
| `hidden`, `order` | Lists of table column identifiers. |
| `headers` | Per column: language-keyed plain-text `labels` (up to 200 characters each) and one validated `bi-*` `icon` class. |
| `sorting` | At most two distinct column aliases; prefix an alias with `-` for descending order. |
| `user_columns` | Boolean, default `true`: whether viewers may arrange this model's columns (see [Personal column layouts](#personal-column-layouts)). |

Explicit empty values clear preferences in partial imports.

## Column discovery and runtime behavior

`dlux.discovery.tables.table_column_catalog(request=None, urlconf=None)` builds
the builder's catalog:

- It walks named routes, inspecting declared table classes and
  `get_table_class()` results.
- It resolves model-backed dynamic managers through the same model-class
  resolver as their runtime, and includes section tables.
- It constructs tables with empty data rather than querying rows or rendering
  pages. Configuration and scope helpers and project constructors may still read
  settings.
- Columns shared by table variants merge under the model key. Display labels use
  model-qualified table translations and the request language.
- It omits audit/deletion columns (including project extensions), scope, row
  actions and code-hidden or excluded columns.
- Each entry carries model keys, translated labels, column names, labels and
  orderability, route names and an `is_system` classification.

`SystemSettingsForm.table_columns_catalog` supplies this catalog lazily and caches
it for that form instance. The builder renders it only in Tables or the full setup
wizard. Discovery suppresses only the saved presentation overlay, so hidden columns
remain available to re-enable.

Intentionally blank headers get builder-only labels from
`table_columns_<column_name>` translations, falling back to a readable column
name; their runtime headers stay blank.

A failed constructor, URL walk or request-dependent table-class resolver logs a
diagnostic and degrades safely. Discovery cannot fully infer:

- function views other than the built-in section manager;
- tables created only inside page execution;
- columns added after the common initialization hook.

Those columns still work at runtime but may be missing from the catalog.

### Applying the overlay

The shared table initialization hook applies each model's overlay to both
generated and handwritten Dlux-managed tables:

- Unknown or removed names are ignored. Newly introduced columns keep their
  default visibility and follow the explicitly ordered columns.
- The overlay never reveals a column hidden or excluded by code, and leaves
  tables with no matching configuration unchanged.
- If the configuration would hide every data column, the first baseline data
  column stays visible.
- Audit, deletion, scope and row-action columns keep their own gates and
  positions; the overlay cannot hide, reveal or reorder them.
- Tables using an explicit custom template or opting out of Dlux rendering
  ignore the overlay.

Installing the hook is idempotent. Rebuilding Django's app registry cannot wrap it
again, rerun authorization without the original request, or apply the overlay
twice.

Column preferences control presentation only. They do not change queryset
filtering, permissions or export authorization, so keep sensitive-data protection
in the backend.

### Headers and sorting

Header labels use the current Dlux language and fall back to the code labels when
no override exists for it. Icons and labels render through the shared table
template with escaping.

Default sorting applies only to visible, orderable, configurable columns; stale,
protected and excluded names are ignored. An unsupported computed sort logs a
warning and keeps the table's code ordering. A request's explicit sort takes
precedence through the normal django-tables2 request configuration.

## Using the builder

Open **Options → Tables**. Each discovered model uses the ribbon builder's card
shell and the shared element inspector; there is no separate selection grid.
Select a header to:

- edit its labels in the configured languages;
- choose an optional icon with the shared picker;
- show or remove it, or reset it;
- assign it primary or secondary default sorting and a direction.

Removed developer columns stay in the header strip as muted, selectable
placeholders so they can be restored. The last shown column cannot be removed.
Audit/deletion, scope, row actions and code-hidden columns keep their dedicated
controls and are absent from the inspector. The builder configures the columns
tables declare; it cannot create new ones.

Select a table title to reach the model-level controls: **Use table defaults**
(the ribbon's rewind icon), which removes only that model's overlay, and **Allow
personal column layouts** (see [Personal column layouts](#personal-column-layouts)).

The Mono theme's column-builder and disclosure styling lives in
`dlux/static/dlux/themes/css/mono.css`.

### System items

Like Ribbon, Sidebar and Navbar, the builder starts with **Show system items**
off. Users, activity logs and other framework tables appear only when it is on.

Catalog entries carry `is_system`. Framework and Django infrastructure models, the
configured user model and tables supplied by a `dlux` module are system items. If
any table variant of a model is a system variant, the model is a system item.
Project tables generated through Dlux's shared manager or section views stay
project items; inheriting `DluxTable` alone does not make a table a system item. A
translated empty state explains the filter when an installation has only system
tables.

The switch filters the builder only. It is not stored in `tables_config`, does not
dirty the form and resets to off when the builder reopens. It neither drops hidden
system-table overlays nor stops them applying at runtime, and backend permissions
still control access.

### Ordering, restoring and saving

- **Reorder**: drag shown headers within their strip. The focused header also
  takes Left/Right arrow keys in the current reading direction, and the adjacent
  earlier/later buttons give tap controls on phones. The strip scrolls
  horizontally within its card.
- **Restore** (per column, rewind icon): restores the column's labels, icon and
  visibility and removes its sort assignment, keeping other columns and the
  header order. It is disabled while the selected column has no header,
  visibility or sort override, and follows pending edits immediately.
- Dismiss the inspector with its clear-selection action before selecting a header
  it covers.
- Save the normal settings form to apply changes to actual tables. Closing
  without saving follows the usual discard guard.

Opening the builder or inspecting a header does not rewrite the JSON or dirty the
form. Edits keep unrelated table preferences, other models' overlays and stale
column names; only an explicit model reset removes that model's stale preferences.
First-launch file imports refresh the header strip and inspector immediately.

Hiding and showing a column keeps its position. Reverting labels, icons, sorting or
ordering to the form's opening configuration restores the original JSON carrier,
formatting included, so closing skips the unsaved-changes prompt. This holds when
an existing saved overlay is edited and reverted; any remaining change still
prompts.

Labels, status announcements and controls use the dlux translation framework. The
assets are external, CSP compliant and theme- and RTL-aware.

## Pagination

URL page sizes cannot override the validated table size when django-tables2
configures the paginator. Invalid or oversized values fall back to allowed saved or
default sizes. Fixed metadata sizes, table prefixes and custom page-size fields
work, and the request shared with other tables and views is left unchanged. The
full page-size precedence is in the [Developer Guide](developer-guide.md).

The backup and restore history tables are `DluxTable`s on the shared table
template, so builder header overrides apply to them. Their page size is fixed by
`Meta.dlux_per_page`, whatever the URL asks for.

## Personal column layouts

Signed-in viewers can open **Arrange columns** for a Dlux table and change, for
themselves, which columns show and in what order.

- The ribbon carries an icon-only Arrange columns action with a Dlux tooltip.
  Without a ribbon, the icon joins the table's footer or header controls; no
  separate button row is added.
- The dialog uses the same header strip as the administrator builder, without
  an inspector. Each header carries an eye: open means the column shows for you;
  struck means it is hidden, and the header is dimmed. Click the eye to switch.
- Reorder by dragging or with the arrow keys and earlier/later buttons, in the
  reading direction.
- At least one configurable data column stays visible: the last shown column's
  eye is disabled with a "keep at least one column" hint.
- **Restore** removes only that table's personal layout and follows the current
  administrator defaults. Restoring or reverting edits compares the result with
  the original state. **Save** and **Close** finish the dialog.

Header labels, icons and default sorting stay with the administrator. Action,
scope and record-visibility controls are outside personal configuration.

### Limits and precedence

Personal layouts apply after the developer baseline and
`SystemSettings.tables_config`:

- They never reveal a developer-excluded or administrator-hidden column.
- Changed administrator restrictions take effect on the next render and are
  checked again when an already-open dialog saves.
- Columns the saved layout does not name follow the named ones, in administrator
  order.
- Tables without a model and anonymous viewers have no Arrange columns action.

Two switches turn personal layouts off:

- **Allow personal column layouts**, on the table title in the administrator
  builder (on by default), stored as
  `tables_config.columns["app.model"].user_columns`. `false` hides the action,
  ignores stored personal layouts, and makes the endpoint refuse both GET and
  POST, including signed dialogs issued before the change. Stored layouts are kept
  for re-enabling.
- `Meta.dlux_user_columns = False` on a table class opts that table out in code.

### Endpoint and storage

The GET/POST endpoint is `/sys/api/preferences/tables/columns/`
(`user_table_columns`):

- GET returns the Dlux modal HTML.
- POST takes a signed `token` and `preferences` JSON (`order`, `hidden`, or
  `reset: true`). Success reloads the current page, keeping its query string.
- The signed catalog comes from the actual authorized table render. It is bound
  to the user, expires after an hour, and holds column names and labels only, so
  callers cannot name arbitrary models or tables and the endpoint never reads
  rows. Expired or foreign tokens are refused.
- Saving requires login and CSRF, rechecks the current administrator
  restrictions, locks the caller's profile, keeps unrelated preferences and
  enforces the profile JSON size cap.

Layouts live in `Profile.preferences['table_columns'][table_key]`; no migration
is needed. The key is derived from the table class, model and prefix, so
separately prefixed variants do not overwrite each other. Added or removed columns
and audit toggles do not reset a viewer's choices.

### Header strip API

Both builders draw headers with `DluxColumnStrip.header()` from
`dlux/static/dlux/helpers/column_strip/js/main.js`, which supplies the drag
handles and earlier/later arrows.

- `header({..., visibility: {show, hide, keepOne}})` adds the per-header eye
  button (`.dlux-table-columns__eye`, `aria-pressed` when hidden). The personal
  dialog uses it instead of an inspector.
- `DluxColumnStrip.setVisibility(eye, shown, labels, columnLabel, locked)`
  updates an eye; `locked` keeps the last shown column on and shows the
  `keepOne` hint.
