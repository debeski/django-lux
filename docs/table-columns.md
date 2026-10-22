# Configurable table columns — development status

The 1.14 table-builder work follows the owner-approved “Table Column Builder” plan. Phase 1 (canonical audit/deletion sets and symmetric audit visibility) already shipped. The branch implements the Tables step, canonical storage, discovery, runtime overlay and interactive builder (Phases 2–5). Release integration remains pending.

## Sparse column configuration

`SystemSettings.tables_config` is an additive JSON field with database default `{}`. It is registered with the settings registry, runtime configuration and settings import/export. The **Tables** step sits between Ribbon and Components and owns table density, accent edges, sticky headers, resizing, zebra stripes, row actions and audit/soft-deleted visibility. Components retains forms, modals and Options-page layout. Table/card corner shapes stay with Themes and Fonts. Existing permission gates for audit/deleted records are unchanged.

The flat settings keys remain public and unchanged. `tables_config` is canonical storage; `layout_config` retains synchronized legacy mirrors. `SystemSettings.load()` reads legacy values through without writing, preserving existing column overlays and explicit canonical values. The next ordinary settings save persists the canonical group and its mirrors. This needs only the additive `0027` field migration; there is no inline-unsafe data migration. ORM saves through either group, including `update_fields`, synchronize both groups; explicit canonical writes win when both groups are supplied. Loaded-value snapshots distinguish a legacy edit from unchanged cached canonical data. Cache entries from before this contract are refreshed from the database. Old project configuration/imports using `layout_config` remain accepted. Direct SQL or `QuerySet.update()` bypasses model synchronization and cache invalidation.

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

## Remaining release work

Integrate after 1.13, declare the additive migration in the release manifest, run release checks, and obtain owner approval before tagging or pushing a beta. Other 1.14 updater-card work remains separate from this table-builder feature.

## Phase 2 validation — 2026-10-21

- Full Django suite: 2,915 tests, OK with 6 skips. JavaScript unit suite: 70 passed. Browser suites: 12 previews and 9 wizard tests passed, including canonical table-config file import.
- The separate PostgreSQL testbed verified legacy read-through, canonical precedence, migration-on-save and matching flat keys/legacy mirrors. The implementation retains only additive migration `0027`; an inline-unsafe backfill was not retained.
- Live Options journeys passed in English/LTR and Arabic/RTL at 1440px and 390px: Tables labels, control ownership, preview-step routing, off/on saves, reopening, unrelated Components saves, no horizontal overflow and no JavaScript page errors. Temporary preferences were restored.
- Django checks, migration consistency, import-graph guards, JavaScript syntax and whitespace checks passed. Testbed deep checks report 23 OK, zero errors and the expected local DEBUG warning.

## Phases 3–4 validation — 2026-10-21

- Full Django suite: 2,936 tests, OK with six skips. Focused table/discovery/permission/import-graph checks: 111 passed, including the app-registry rebuild reproduction. Django checks, migration consistency and whitespace checks passed. The unchanged JavaScript implementation retains Phase 2's validation.
- The isolated PostgreSQL runtime catalog discovers eight models, including the handwritten user table; framework-controlled columns are absent from its configurable choices.
- Repeated hook installation retains one wrapper. Live generated-table checks confirm permitted audit/deletion columns survive a hostile presentation overlay while anonymous requests cannot reveal them; original settings were restored.
- Live settings-form saves and the real users page passed in English/LTR and Arabic/RTL at 1440px and 390px: email hiding, explicit header order, ignored removed names, all-hidden fallback and clearing the overlay back to baseline. There was no page overflow or JavaScript page error. Original table preferences, overlays and legacy mirrors were restored exactly. No screenshots were taken.
- Deep testbed checks: 23 OK, zero errors, one expected local DEBUG warning and three skipped checks. Evidence: `.xclude/testbed/column-overlay-*`.

## Phase 5 validation — 2026-10-22

- Full Django suite: 2,938 tests, OK with six skips. Focused discovery/form/translation/import-graph checks: 55 passed; partial-translation compatibility checks: 47 passed. JavaScript unit suite: 70 passed. Browser suites: four builder tests, nine wizard tests and twelve preview tests passed. They cover persistence into the real users table, drag/keyboard/tap order, sparse/stale preference preservation, first-launch import refresh, last-column protection, reset, clean opens and discarding edits. Django checks, migration consistency, JavaScript syntax and whitespace checks passed.
- The isolated PostgreSQL testbed passed the visible builder in English/LTR and Arabic/RTL at 1440px and 390px, including translated online-status labels, RTL keyboard direction, mobile tap controls, saved/reopened state, actual table rendering, reset and last-column protection. Dialog widths matched their scroll widths (1138px/388px); there were no JavaScript page errors. No screenshots were taken.
- The candidate wheel matches the builder sources/assets. Deep checks: 23 OK, zero errors, one local DEBUG warning and three skips. Temporary table preferences and legacy mirrors were restored. Evidence: `.xclude/testbed/table-builder-*` and `column-overlay-restore.log`.

System-item filter follow-up: full Django suite 2,941 tests OK/six skips; 58 focused checks, five builder browser tests and nine wizard tests passed. Classification covers users/activity, generated project managers and mixed table variants. Browser tests verify default exclusion, explicit reveal, reset on reopening, clean form state and retained pending edits. The rebuilt `8094` candidate passed English/Arabic desktop/mobile journeys, zero page errors, no dialog overflow and deep 23 OK/zero errors; original preferences were restored. Django checks, migration consistency, import-graph, translation, syntax and whitespace guards passed. Evidence: `.xclude/testbed/table-system-toggle-*`.

Inspector follow-up (2026-10-22, owner-approved scope superseding the plan's earlier no-inspector restriction): full Django suite 2,947 tests OK/six skips; focused table/tables/import-graph/translation checks 94 passed, plus 55 table checks after extending form/import/export round trips. JavaScript unit suite 70 passed; browser suites six builder, nine wizard and twelve settings-preview tests passed. Tests cover localized escaped labels, safe icons, protected columns, primary/secondary ordering with real rows, explicit request precedence, unsupported computed sorting, shared icon browsing, removal/restoration, reset, saved state and discard behavior. The isolated PostgreSQL testbed passed the inspector in English/Arabic at 1440px and 390px, including icon browsing, labels, both sort priorities, save/reopen and independent resets. Panels fit their modal bounds with no horizontal overflow or page errors; original settings and legacy mirrors were restored. Deep checks: 23 OK, one local DEBUG warning, zero errors, three skips. No screenshots were taken. Evidence: `.xclude/testbed/table-inspector-*`.

Release metadata is intentionally inherited from the branch base until release integration. The migration gate currently refuses publication because that manifest declares `migrations.effect: none`; 1.14 integration must declare the additive migration and verify rollback compatibility before any beta is tagged. This branch is not release-ready.

Final builder polish (2026-10-22): **Restore** is short, disabled at defaults and updated during edits. Hide/show retains column position; edits reverted to either defaults or an existing saved overlay close without a false unsaved prompt. Ribbon destination buttons now drag, save and render in their per-host order, including project query-only export buttons. Full Django suite: 2,952 OK/six skips; focused checks 271 and final ribbon/import-graph checks 214 passed; JavaScript 70 passed; browser suites eight builder/ribbon, nine wizard and twelve previews passed. The rebuilt PostgreSQL testbed passed English/Arabic at 1440px/390px, including Restore state, reverted changes, saved/runtime/reopened project ribbon ordering, no overflow and no page errors. Deep checks: 23 OK/zero errors, one local DEBUG warning and three skips. Original table/layout/ribbon settings were restored exactly; no screenshots were taken. Evidence: `.xclude/testbed/table-polish-*`.

## Isolated branch testbed

The branch testbed lives at `.xclude/testbed/` in the `table_builder` checkout. Compose project `dlux-table-builder` uses port `8094`, separate named database/runtime/static/Redis/Composer volumes, separate media/log directories and fresh private credentials in `.secrets/.env`. It does not share the official testbed's database or runtime volume. It uses a branch wheel baked into uniquely tagged `dlux-table-builder:dev` and pins its deployer/resident Composer pair to `dlux-table-builder-composer:baseline`; it does not retag shared Composer or official app images.

Use `./run.sh` in that directory: it exports the local Composer image pin and delegates to the unchanged, integrity-checked `start.sh` wrapper. Rebuild the wheel and branch image after source changes, then restart through `./run.sh`. Never publish this development image or represent its inherited package version as a released 1.14 beta.
