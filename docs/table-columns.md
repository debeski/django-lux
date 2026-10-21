# Configurable table columns — development status

The 1.14 table-builder work follows the owner-approved “Table Column Builder” plan. Phase 1 (canonical audit/deletion sets and symmetric audit visibility) already shipped. Phase 2 adds the Tables step and canonical configuration storage; discovery, the column overlay and builder UI remain pending.

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

Keys are lower-case Django model labels (`app_label.model_name`); column names are table column identifiers. Store only changed visibility and explicit ordering, never a snapshot of all columns. Audit and deletion columns retain their existing dedicated gates; the future overlay must not bypass them. This configuration is currently persisted but does not yet change table rendering.

## Remaining implementation

1. Discover model/table columns, excluding audit/deletion fields and logging skipped tables.
2. Apply the overlay at the common table-adjustment seam, ignoring missing columns and preventing empty tables.
3. Add horizontal reorderable header previews and wrapping checkbox chips using the ribbon builder shell. No inspector.
4. Complete permission, UI and release validation for the remaining phases.

## Phase 2 validation — 2026-10-21

- Full Django suite: 2,915 tests, OK with 6 skips. JavaScript unit suite: 70 passed. Browser suites: 12 previews and 9 wizard tests passed, including canonical table-config file import.
- The separate PostgreSQL testbed verified legacy read-through, canonical precedence, migration-on-save and matching flat keys/legacy mirrors. The implementation retains only additive migration `0027`; an inline-unsafe backfill was not retained.
- Live Options journeys passed in English/LTR and Arabic/RTL at 1440px and 390px: Tables labels, control ownership, preview-step routing, off/on saves, reopening, unrelated Components saves, no horizontal overflow and no JavaScript page errors. Temporary preferences were restored.
- Django checks, migration consistency, import-graph guards, JavaScript syntax and whitespace checks passed. Testbed deep checks report 23 OK, zero errors and the expected local DEBUG warning.

Release metadata is intentionally inherited from the branch base until release integration. The migration gate currently refuses publication because that manifest declares `migrations.effect: none`; 1.14 integration must declare the additive migration and verify rollback compatibility before any beta is tagged. This branch is not release-ready.

## Isolated branch testbed

The branch testbed lives at `.xclude/testbed/` in the `table_builder` checkout. Compose project `dlux-table-builder` uses port `8094`, separate named database/runtime/static/Redis/Composer volumes, separate media/log directories and fresh private credentials in `.secrets/.env`. It does not share the official testbed's database or runtime volume. It uses a branch wheel baked into uniquely tagged `dlux-table-builder:dev` and pins its deployer/resident Composer pair to `dlux-table-builder-composer:baseline`; it does not retag shared Composer or official app images.

Use `./run.sh` in that directory: it exports the local Composer image pin and delegates to the unchanged, integrity-checked `start.sh` wrapper. Rebuild the wheel and branch image after source changes, then restart through `./run.sh`. Never publish this development image or represent its inherited package version as a released 1.14 beta.
