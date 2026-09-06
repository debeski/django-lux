# Project Tracker (django-lux) [Max 100 lines total]

## Part 1: Project Related
### Current Verified Snapshot:
- v1.8.11 is tagged/published. The tree is v1.8.12 (UNTAGGED): `dlux:dynamic_modal:open` is bound in the capture phase again (a host project's non-bubbling dispatch on `document.body` had reached nothing since 1.8.0), plus the updater/SECRET_KEY fixes and the tooltip drift fix.
- Generated Compose stacks use Composer agent/executor/proxy services; `dlux-updater` is retired. Celery `pre_start` runs reconcile/migrator and Celery Beat writes the state tick.
- Canonical runtime settings are `homepage_config` and `search_config`; legacy keys remain v1.x mirrors.
- Inline installs need Composer 1.3.10+ AND dlux 1.8.9+: a deployment on 1.8.0-1.8.8 cannot hand off at all, so it must reach 1.8.9 by image rebuild or by `./start.sh dlux-update apply` from the project root.

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
- Release notes have cited tests that were not running: 3 modules were never in `test_all.TEST_LABELS` (61 tests). Registered, and `test_suite_registration` now guards it — but treat any "N new tests" claim in an older entry as unverified.
- 2026-09-06 PROD (decrees, 1.8.6 -> 1.8.11, Composer 1.3.12): boot-gate deadlock. `entrypoint.sh` makes BOTH `web` and `celery` wait on `migrate --check`, but only celery's `pre_start` applies — and Compose skips `pre_start` on a restart-policy restart, which is what Composer's "Restart Services" does. Pending migration 0020 (shipped 1.8.9, crossed by this multi-release jump) left both looping forever. Recovered by applying the migration by hand. `DLUX_BOOT_GATE=off` is set only on the pre_start steps, never on celery's own container, so the documented "net" cannot apply anything.
- 2026-09-06: a release manifest's `migrations.effect` describes only the hop from its base tag, so a multi-release update (1.8.6 -> 1.8.11) reported `none` while actually crossing 0020. Nothing warned the update carried a migration.
- The whole inline-update hand-off shipped untested end to end (1.8.0-1.8.8): unit tests pinned `write_request` while the caller could not reach it, and one updater test passed only because the crash produced the status it asserted. Drive the run, not the helper.
- Inline updates require a runtime volume writable *by Celery*; web's mount may be read-only and its local probe no longer decides (1.8.6). No fallback path is valid.
- 2026-08-31: `SystemBackupViewTests.test_restore_requires_password_and_confirmation` leaves restore status `pending` in the gov container; isolated from Backup page layout changes.

### Incomplete Tasks:
- **Priority 1:**
  - [ ] Implement `release_channels_plan.md` BEFORE Dlux 1.9.0 / Composer 1.4.0: first beta releases MUST be 1.9.0b1 / 1.4.0b1; stable gated on acceptance. Includes channel UI/CLI, publication, bootstrap and deprecation audit.
  - [ ] v1.8.8 shipped the titlebar feature unreviewed because `git add -A` swept the tree; `docs/RELEASING.md` now says stage explicit paths. Deployed stacks need `collectstatic` under `dlux.updater.supervisor` or they serve baked-image static against runtime templates.
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
  - [x] v1.8.12 context-menu regression: `dlux:dynamic_modal:open` bound in capture phase, so a host dispatching a non-bubbling CustomEvent on `document.body` (decrees view/edit) reaches the modal again. Latent since 1.8.0, masked by stale static; browser-verified across all three dispatch shapes (2026-09-06).
  - [x] v1.8.12 suite registration: `test_modal_content_init`, `test_titlebar_action_rail`, `test_inspector_shell` added to `TEST_LABELS` (2366 -> 2430) plus a guard that fails on any unregistered `test_*.py` (2026-09-06).
  - [x] v1.8.12 updater trio: reconcile also triggers on a runtime-generation change (a version update no longer leaves `active_version` frozen); `queue_image_update()` reports the live release via `active_runtime_version()`; `dlux_settings()` refuses a non-DEBUG boot on an empty/placeholder `SECRET_KEY` (opt out with `DLUX_ALLOW_INSECURE_SECRET_KEY`) (2026-09-06).
  - [x] v1.8.12 `dlux_image_gate`: adopt/keep/abort verdict so an image baking an older dlux keeps the newer active release instead of being refused outright, decided by the release's own `requires.baked_image` floor. Composer must adopt the command for the gate to relax (2026-09-06).
  - [x] Tooltip positioning feedback loop fixed (v1.8.12): `positionTooltip()` clears `left`/`top` before measuring, so the fixed, auto-width box is no longer shrink-to-fit-capped by its own stale offset (2026-09-05).
  - [x] v1.8.4 managed assets public API: `ManagedAssetField(kind, namespace, reads)` + registry, namespace column (0018, backfilled by kind), namespace-scoped dedup and storage paths, field-identity-authorized instant upload for every kind, public `resolve_asset_selection`/`apply_asset_pickers`/`apply_asset_selections`/`build_asset_field`/`ManagedAssetFormMixin`, `capture` support, System Settings switched onto the same public helper (2026-09-02).
  - [x] Data reset (shipping in v1.8.4): permanent mode (hard-deletes scoped rows + empties their recycle bin) behind a typed confirmation word, line models excluded via `cascade_parent()`, `trashed` counts in the catalog, and a `data_reset_finished` signal for projects to rebuild derived figures (2026-09-02).
  - [x] File widget renamed off `project-archive`'s `archive_file` names to `build_file_field` / `file_field_*` / `.dlux-file-*`, with v1.x shims for the two helpers, the old string keys and the `archive-file-input` opt-in class (2026-09-01).
  - [x] `activity_log` is the first screen on `dlux/list_page.html` — 42 template lines to 27, detail modal moved into `list_modals`, table card dropped (2026-09-01).
  - [x] `dlux/list_page.html` promoted from the reference project: Ribbon over table, no card, blocks `list_before_table` / `list_body` / `list_after_table` / `list_modals` / `list_page_attrs`, plus `extra_styles` / `extra_scripts` (2026-09-01).
  - [x] Standalone `manage_sections` now uses a manage-only expandable form above the table: default collapsed, ribbon Add opens create, row Edit opens edit, Cancel returns to table state, invalid POST stays open (2026-09-01).

### One-line info about last verified Tests:
- 2026-09-06: full `dlux.tests` 2430 OK (was 2366 — 3 unregistered modules + the new guard + 2 modal-listener tests); the capture-phase test fails against the pre-fix listener; event phases verified in a real browser (non-bubbling body dispatch reaches capture only).
- 2026-09-06: v1.8.12 updater work — full `dlux.tests` 2366 OK (17 new across `ReconcileTriggerTests`, `ActiveRuntimeVersionTests`, `ImageCandidateGateTests`, `PlaceholderSecretKeyTests`), `makemigrations --check` clean, `release_check --base-tag v1.8.11` exit 0, `dlux_image_gate` driven for real (1.8.6 vs active -> keep).
- 2026-09-05: tooltip drift — full `dlux.tests` 2349 OK and `node --test 'tests-js/*.test.mjs'` 63 OK (2 new in `tests-js/tooltip_position.test.mjs`; the stale-offset one fails on pre-fix code, 841px vs 762px). Browser-verified in a real repro: pre-fix walked 8px/hover after a resize, post-fix lands correct on the first hover.
- 2026-09-05: `test_package_handoff.HandoffCollectsStaticTests` no longer pins `1.8.11` — it derives a version above the baked floor, since `reconcile()` resets any volume release below `get_baked_version()` and the bump to 1.8.12 broke it.
- 2026-09-05: static-after-handoff — full `dlux.tests` 2407 OK (6 new in `test_package_handoff`, driving `tick_package_update()` with a stub runner: applied/rollback/rolled-back all collect, the release path is on `PYTHONPATH`, a failed collect completes the run but is logged and reported).
- 2026-09-05: Titlebar Phase 2 — full `dlux.tests` 2384 OK; one `.titlebar__actions` in both layouts (12 ordered actions under Titlebar Actions, 5 under Dropdown, one bell not two), grouping verified in a browser: Home stays on the bar, the other 11 enter the rail in configured order and it scrolls.
- 2026-09-05: v1.8.10 — `release_check --base-tag v1.8.9` exit 0, `makemigrations --check` clean, +6 reconcile tests (offer stand-down, rollback target from the volume, baked floor, image fallback).
- 2026-09-05: v1.8.9 — full `dlux.tests` 2378 OK (11 new in `test_package_handoff`); `release_check --base-tag v1.8.8` exit 0 (effect `state_only`); `sqlmigrate dlux 0020` prints `-- (no-op)`.
- 2026-09-04: v1.8.8 — full `dlux.tests` 2367 OK; `release_check --base-tag v1.8.7` exit 0 (inline_safe true, effect `none`, image_baseline 1.2.7, `composer >=1.3.10`).
- 2026-09-04: v1.8.7 — full `dlux.tests` 2367 OK (7 new in `test_modal_content_init`, 4 in `test_ribbon`); `release_check --base-tag v1.8.6` exit 0, effect `none`.
- 2026-09-04 incident recovery — gov, decrees, and sales-crm containers report v1.8.6, original configured settings rows, and no applied lock migration; fresh requests no longer log unavailable `SystemSettings`.
- 2026-09-04: Guard + reconcile — full `dlux.tests` 2328 OK (7 new in `test_package_handoff`, 4 in `test_updater`), `makemigrations --check` clean, `release_check --base-tag v1.8.5` exit 0 on the 1.8.6 manifest.
- 2026-09-02: v1.9.0 green — full `dlux.tests` 2294 run, 2292 OK (25 new in `test_asset_fields`); the only 2 errors are `test_manifest_schema_v2` shelling out to `git tag`, which the sandbox now denies (`.git/config: Operation not permitted`) — environmental, re-run outside it before release.
- 2026-09-01: `list_page.html` consumed downstream — gov's 3 generic lists render through it with no semantic diff (only the wrapper class changed); `list_page_attrs` carries a host project's own data hooks, which is what kept its `scoped_list.html` from being retired outright.
- 2026-09-01: Gov stack after the file-widget rename — `collectstatic` copied 13 files; Caddy now serves `dlux-file` CSS/JS (23/23, 0 legacy) and every JS `[data-dlux-file-*]` hook is present in the rendered widget (library/scan absent only in their unguarded-off branches).
- 2026-09-01: File-widget rename — 3 new compat tests (shim removed → the template one fails, restored → passes); full `dlux.tests` 2264 run, 1 pre-existing unrelated failure; `node --check` x3 OK.

### One-line info about last time edited Docs:
- 2026-09-06: `release_channels_plan.md` records both projects' mandatory beta-first milestones, implementation paths, channel semantics, staging gates and retirement checklist; gitignored planning artifact.
- 2026-09-06: `docs/inline-updater.md` gained "Moving to an image that bakes an older DjangoLux" (adopt/keep/abort); `docs/deployment-configuration.md` documents `DLUX_ALLOW_INSECURE_SECRET_KEY`.
- 2026-09-05: `docs/inline-updater.md` — the hand-off's ack step also collects static, and what a failed collect does (run completes, `static_collected: false`).
- 2026-09-05: `system-settings-preview-plan.md` now includes Preview-button UX: popup previews for off-page targets and glass mode for visible behind-modal chrome.
- 2026-09-05: `docs/inline-updater.md` gained "What finishes a handed-off run" and "What the card offers after an update" (offer stand-down, rollback target, the baked floor).
- 2026-09-04: `docs/inline-updater.md` gained "What refreshes the reported versions" and "Who decides the runtime volume is usable" (1.8.0-1.8.5 stale-version warning included).

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
