# Project Tracker (django-lux) [Max 100 lines total]

## Part 1: Project Related
### Current Verified Snapshot:
- v1.8.7 is tagged/published. The tree is v1.8.8 (UNTAGGED): titlebar `actions_layout` (`scattered` default | `grouped`) with the folded action rail, a draggable action-order grip, and a manifest declaring `composer >=1.3.10`.
- Generated Compose stacks use Composer agent/executor/proxy services; `dlux-updater` is retired. Celery `pre_start` runs reconcile/migrator and Celery Beat writes the state tick.
- Canonical runtime settings are `homepage_config` and `search_config`; legacy keys remain v1.x mirrors.
- Inline installs need Composer 1.3.10+: earlier versions read `inline_safe` off the wheel (schema 2 derives it) and refused at activation. Publish Composer 1.3.10 BEFORE tagging v1.8.8.

### Current Project Adopted Standards:
- Integrate settings with `from dlux.utils import dlux_settings; dlux_settings(globals())`; mount `dlux.urls` at root.
- Use Dlux-native UI primitives and feature-first static layout; backend authorization must match UI visibility and mutations are POST-only.
- Project images and fonts go through `ManagedAssetField`, never a raw `ImageField`/`FileField`; namespace isolates each pool and the field's own permission gates upload.
- `dlux.system` owns settings defaults/schema/normalizers; migration-history wrappers remain in `dlux.models`.
- Settings steps order controls per section: toggles, then selectors, then fields, then builders; a field sits in the step its subject belongs to, not its storage group.

### Adopted Standards' rules and policies:
- Read/update this tracker each turn; retain under 100 lines. Use `apply_patch` for edits and preserve user work.
- Check tags before changelog edits; tagged versions are immutable. Change code/config/docs and their changelog together.
- Never delete files; move superseded material into `.xpose/` with its relative path.

### Cross-Cutting Audits if any:
- 2026-09-04 live-stack guard: adding an unapplied field to `SystemSettings` makes singleton reads fail and surfaces defaults across bind-mounted dev stacks; new runtime state must use an isolated model/table or migrate every live stack atomically.
- Import-cycle and template/render-cost guards remain active; do not replace function-scope imports blindly.
- Generated deployment docs must reflect Compose 5.3+ `pre_start`, Composer external execution, and the retired updater service.
- 2026-08-31 scoped-model audit: Dlux tenant/user-visible records using row isolation are scoped (`Profile`, `ActivityLog`, notifications/rules/watches); remaining non-scoped concrete tables are global/system/owner-filtered infrastructure, with `GroupProfile.scope` managed manually by preset gates.

### Current Project's Unsolved Known Bugs:
- Inline updates require a runtime volume writable *by Celery*; web's mount may be read-only and its local probe no longer decides (1.8.6). No fallback path is valid.
- 2026-08-31: `SystemBackupViewTests.test_restore_requires_password_and_confirmation` leaves restore status `pending` in the gov container; isolated from Backup page layout changes.

### Incomplete Tasks:
- **Priority 1:**
  - [ ] Before v1.9.0: migrate the remaining callers of the two deprecations — `advanced_filter_helper` in project-archive/dhub/trademarks, and the `archive_file` shims in project-decrees/archive/dhub.
  - [ ] v1.9.0 remaining: `dlux_prune_assets` (unreferenced, non-shared namespace, dry-run then `--apply`); an asset-manager view grouped by namespace; then adopt in the projects — switch_pos `Product.image`/`Service.image`/`PublicCatalogListing.image_override` and gov_edition `storage.Asset.image`, each with a migration and a backfill command.
  - [ ] Finish framework promotion from dlux-crm-gov's `common` app; only the generic list-page decision remains.
  - [ ] 4/4 Generic list page: dlux ships it, `activity_log` uses it, and gov's three generic lists now extend it through a 3-line `scoped_list.html`. Remaining — decide whether `ScopedListView` itself is promoted; `manage_users`, `manage_sections` and the scope/group fragments stay as they are until touched.
  - [ ] Review live Docker staging acceptance for Composer migration and `dlux_check --apply`.
- **Priority 2:**
  - [ ] System Settings > Login Page > Full-page split: EN/AR hero-message textareas reuse the active UI language's empty Markdown placeholder, so both show Arabic under an Arabic UI (and both English under an English UI). Cosmetic only; resolve per field and preserve configured language order.
  - [ ] Postponed 2026-08-28: keep stale-route pruning import-only; revisit builder-save pruning only if an actual stale-entry problem appears.
  - [ ] Finish `forms/system_settings.py` group extraction behind existing contracts.
- **Completed Recently:**
  - [x] v1.8.4 managed assets public API: `ManagedAssetField(kind, namespace, reads)` + registry, namespace column (0018, backfilled by kind), namespace-scoped dedup and storage paths, field-identity-authorized instant upload for every kind, public `resolve_asset_selection`/`apply_asset_pickers`/`apply_asset_selections`/`build_asset_field`/`ManagedAssetFormMixin`, `capture` support, System Settings switched onto the same public helper (2026-09-02).
  - [x] Data reset (shipping in v1.8.4): permanent mode (hard-deletes scoped rows + empties their recycle bin) behind a typed confirmation word, line models excluded via `cascade_parent()`, `trashed` counts in the catalog, and a `data_reset_finished` signal for projects to rebuild derived figures (2026-09-02).
  - [x] File widget renamed off `project-archive`'s `archive_file` names to `build_file_field` / `file_field_*` / `.dlux-file-*`, with v1.x shims for the two helpers, the old string keys and the `archive-file-input` opt-in class (2026-09-01).
  - [x] `activity_log` is the first screen on `dlux/list_page.html` — 42 template lines to 27, detail modal moved into `list_modals`, table card dropped (2026-09-01).
  - [x] `dlux/list_page.html` promoted from the reference project: Ribbon over table, no card, blocks `list_before_table` / `list_body` / `list_after_table` / `list_modals` / `list_page_attrs`, plus `extra_styles` / `extra_scripts` (2026-09-01).
  - [x] Standalone `manage_sections` now uses a manage-only expandable form above the table: default collapsed, ribbon Add opens create, row Edit opens edit, Cancel returns to table state, invalid POST stays open (2026-09-01).

### One-line info about last verified Tests:
- 2026-09-04: v1.8.8 — full `dlux.tests` 2367 run; `release_check --base-tag v1.8.7` exit 0 (inline_safe true, effect `none`, image_baseline 1.2.7, `composer >=1.3.10`).
- 2026-09-04: v1.8.7 — full `dlux.tests` 2367 OK (7 new in `test_modal_content_init`, 4 in `test_ribbon`); `release_check --base-tag v1.8.6` exit 0, effect `none`.
- 2026-09-04 incident recovery — gov, decrees, and sales-crm containers report v1.8.6, original configured settings rows, and no applied lock migration; fresh requests no longer log unavailable `SystemSettings`.
- 2026-09-04: Guard + reconcile — full `dlux.tests` 2328 OK (7 new in `test_package_handoff`, 4 in `test_updater`), `makemigrations --check` clean, `release_check --base-tag v1.8.5` exit 0 on the 1.8.6 manifest.
- 2026-09-02: v1.9.0 green — full `dlux.tests` 2294 run, 2292 OK (25 new in `test_asset_fields`); the only 2 errors are `test_manifest_schema_v2` shelling out to `git tag`, which the sandbox now denies (`.git/config: Operation not permitted`) — environmental, re-run outside it before release.
- 2026-09-01: `list_page.html` consumed downstream — gov's 3 generic lists render through it with no semantic diff (only the wrapper class changed); `list_page_attrs` carries a host project's own data hooks, which is what kept its `scoped_list.html` from being retired outright.
- 2026-09-01: Gov stack after the file-widget rename — `collectstatic` copied 13 files; Caddy now serves `dlux-file` CSS/JS (23/23, 0 legacy) and every JS `[data-dlux-file-*]` hook is present in the rendered widget (library/scan absent only in their unguarded-off branches).
- 2026-09-01: File-widget rename — 3 new compat tests (shim removed → the template one fails, restored → passes); full `dlux.tests` 2264 run, 1 pre-existing unrelated failure; `node --check` x3 OK.

### One-line info about last time edited Docs:
- 2026-09-04: `docs/reference.md` documents `titlebar_config.actions_layout` and the rail; `docs/inline-updater.md` states the Composer 1.3.10 floor and why.
- 2026-09-04: `docs/inline-updater.md` gained "What refreshes the reported versions" and "Who decides the runtime volume is usable" (1.8.0-1.8.5 stale-version warning included).
- 2026-09-02: `docs/managed-assets.md` gained the project-facing asset-field API; `docs/developer-guide.md` names `ManagedAssetField` over `ImageField`; `docs/deprecation-countdown.md` caller lists corrected (both removals stay targeted at v1.9.0).

## Part 2: Global
### Global Standard Helpers, Shortcuts, Info, etc.:
- Gov stack serves `/static/*` from the `static` volume via Caddy, so changed dlux assets need `collectstatic` in `project-sales-crm/gov_edition` before they reach the browser — and Caddy sends `Cache-Control: immutable, max-age=31536000` on unhashed filenames, so a hard reload is required too.
- Prefer `rg`; run generated Compose commands through `./start.sh`; inspect updater state through DB/runtime records, not web logs.

### Global Rulesets:
- Keep tracker, docs, and changelog grounded in verified code/runtime behavior.

### Agent Handoff Rules:
- Move/rename public paths only after downstream-usage checks; record compatibility shims in `docs/deprecation-countdown.md`.

### References and Links:
- Deployment: `docs/inline-updater.md`, `docs/composer-agent.md`, `docs/doctor.md`; settings: `docs/adding-system-settings.md`.
