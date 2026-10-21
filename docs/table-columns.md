# Configurable table columns — development status

The 1.14 table-builder work follows the owner-approved “Table Column Builder” plan. Phase 1 (canonical audit/deletion sets and symmetric audit visibility) already shipped. The branch implements the Tables step, canonical storage, column discovery and runtime visibility/ordering overlay (Phases 2–4). The interactive builder remains pending.

## Sparse column configuration

`SystemSettings.tables_config` is an additive JSON field with database default `{}`. It is registered with the settings registry, runtime configuration and settings import/export. The **Tables** step sits between Ribbon and Components and owns table density, accent edges, sticky headers, resizing, zebra stripes, row actions and audit/soft-deleted visibility. Components retains forms, modals and Options-page layout. Table/card corner shapes stay with Themes and Fonts. Existing permission gates for audit/deleted records are unchanged.

The flat settings keys remain public and unchanged. `tables_config` is canonical storage; `layout_config` retains synchronized legacy mirrors. `SystemSettings.load()` reads legacy values through without writing, preserving existing column overlays and explicit canonical values. The next ordinary settings save persists the canonical group and its mirrors. This needs only the additive `0027` field migration; there is no inline-unsafe data migration. ORM saves through either group, including `update_fields`, synchronize both groups; explicit canonical writes win when both groups are supplied. Loaded-value snapshots distinguish a legacy edit from unchanged cached canonical data. Cache entries from before this contract are refreshed from the database. Old project configuration/imports using `layout_config` remain accepted. Direct SQL or `QuerySet.update()` bypasses model synchronization and cache invalidation.

The defensive normalizer validates table preferences, drops malformed model entries and malformed column lists, removes duplicate names, and retains unknown column names for later runtime resolution. Missing table preferences use existing defaults. An explicit empty `hidden` or `order` list clears that preference in a partial import. Unrelated section saves preserve table settings and column overlays.

The Tables form owns a hidden `tables_config` JSON transport, including during first-launch file imports. Inactive sections preserve its native JSON initial value; a missing transport does not discard an existing overlay. The visible column builder will use this same transport in Phase 5.

```json
{
  "columns": {
    "documents.record": {
      "hidden": ["description"],
      "order": ["number", "title", "date"]
    }
  }
}
```

Keys are lower-case Django model labels (`app_label.model_name`); column names are table column identifiers. Store only changed visibility and explicit ordering, never a snapshot of all columns.

## Column discovery and runtime behavior

`dlux.discovery.tables.table_column_catalog(request=None, urlconf=None)` walks named routes, inspecting declared table classes and `get_table_class()` results. It also resolves model-backed dynamic managers through the same model-class resolver as their runtime and includes section tables. It constructs tables with empty data rather than querying their rows or rendering pages. Configuration/scope helpers and project constructors may still read settings. Columns shared by table variants are merged under the model key; display labels use model-qualified table translations and the request language. Audit/deletion columns (including project extensions), scope, row actions and code-hidden/excluded columns are omitted.

`SystemSettingsForm.table_columns_catalog` supplies this catalog lazily and caches it for that form instance. Discovery suppresses only the saved presentation overlay, so hidden columns remain available to re-enable. A failed constructor, URL walk or request-dependent table-class resolver logs a diagnostic and degrades safely. Function views other than the built-in section manager, tables created only inside page execution, and columns added after the common initialization hook cannot be fully inferred. Those columns remain usable at runtime but may not appear in the catalog.

The shared table initialization hook applies each model's overlay to both generated and handwritten Dlux-managed tables. Unknown or removed names are ignored; newly introduced columns retain their default visibility and follow explicitly ordered columns. The overlay never reveals a column hidden/excluded by code and leaves tables with no matching configuration unchanged. If configuration would hide every data column, the first baseline data column remains visible. Audit, deletion, scope and row-action columns retain their existing gates and positions; this overlay cannot hide, reveal or reorder them. Tables using an explicit custom template or opting out of Dlux rendering ignore the overlay.

Installing the table hook is idempotent. Rebuilding Django's app registry cannot wrap it again and rerun authorization without the original request, or apply the presentation overlay twice.

Column preferences control presentation. They do not change queryset filtering, permissions or export authorization. Keep sensitive data protection in the backend.

## Remaining implementation

1. Add horizontal reorderable header previews and wrapping checkbox chips using the ribbon builder shell. No inspector.
2. Complete interactive builder and release validation.

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

Release metadata is intentionally inherited from the branch base until release integration. The migration gate currently refuses publication because that manifest declares `migrations.effect: none`; 1.14 integration must declare the additive migration and verify rollback compatibility before any beta is tagged. This branch is not release-ready.

## Isolated branch testbed

The branch testbed lives at `.xclude/testbed/` in the `table_builder` checkout. Compose project `dlux-table-builder` uses port `8094`, separate named database/runtime/static/Redis/Composer volumes, separate media/log directories and fresh private credentials in `.secrets/.env`. It does not share the official testbed's database or runtime volume. It uses a branch wheel baked into uniquely tagged `dlux-table-builder:dev` and pins its deployer/resident Composer pair to `dlux-table-builder-composer:baseline`; it does not retag shared Composer or official app images.

Use `./run.sh` in that directory: it exports the local Composer image pin and delegates to the unchanged, integrity-checked `start.sh` wrapper. Rebuild the wheel and branch image after source changes, then restart through `./run.sh`. Never publish this development image or represent its inherited package version as a released 1.14 beta.
