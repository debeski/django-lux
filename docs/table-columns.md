# Configurable table columns — development status

The 1.14 table-builder work follows the owner-approved “Table Column Builder” plan. Phase 1 (canonical audit/deletion sets and symmetric audit visibility) already shipped. The current branch begins Phase 2 with configuration storage; the Tables step, control relocation, discovery, runtime overlay and builder UI are pending.

## Sparse column configuration

`SystemSettings.tables_config` is an additive JSON field with database default `{}`. It is registered with the settings registry, runtime configuration and settings import/export. Empty configuration preserves existing table behavior. The defensive normalizer drops malformed model entries and malformed column lists, removes duplicate names, and retains unknown column names for later runtime resolution.

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

1. Complete Phase 2: Tables step between Ribbon and Components; relocate table settings with legacy compatibility and section-save preservation tests.
2. Discover model/table columns, excluding audit/deletion fields and logging skipped tables.
3. Apply the overlay at the common table-adjustment seam, ignoring missing columns and preventing empty tables.
4. Add horizontal reorderable header previews and wrapping checkbox chips using the ribbon builder shell. No inspector.
5. Complete EN/AR, RTL/mobile, permission, migration and release validation.

Release metadata is intentionally inherited from the branch base until release integration. The migration gate currently refuses publication because that manifest declares `migrations.effect: none`; 1.14 integration must declare the additive migration and verify rollback compatibility before any beta is tagged. This branch is not release-ready.

## Isolated branch testbed

The branch testbed lives at `.xclude/testbed/` in the `table_builder` checkout. Compose project `dlux-table-builder` uses port `8094`, separate named database/runtime/static/Redis/Composer volumes, separate media/log directories and fresh private credentials in `.secrets/.env`. It does not share the official testbed's database or runtime volume. It uses a branch wheel baked into uniquely tagged `dlux-table-builder:dev`; it does not retag Composer or the official app image.

Run its copied `./start.sh` wrapper from that directory. Rebuild the wheel and branch image after source changes, then restart through the wrapper. Never publish this development image or represent its inherited package version as a released 1.14 beta.
