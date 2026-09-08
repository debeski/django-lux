# Project Tracker (django-lux) [Max 100 lines total]

## Part 1: Project Related
### Current Verified Snapshot:
- Dlux v1.8.13 is tagged/published; the tree is **v1.8.14b1 (UNTAGGED)** — the beta-channel rehearsal, paired with Composer 1.3.14b1. Carries the 1.8.14 work (boot-gate `apply`, cumulative migration baseline, one canonical audit/deletion column set, step-anchor guard) plus the channel implementation itself.
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
- Never delete files; move superseded material into `.xclude/` with its relative path.

### Cross-Cutting Audits if any:
- 2026-09-04 live-stack guard: adding an unapplied field to `SystemSettings` makes singleton reads fail and surfaces defaults across bind-mounted dev stacks; new runtime state must use an isolated model/table or migrate every live stack atomically.
- Import-cycle and template/render-cost guards remain active; do not replace function-scope imports blindly.
- Generated deployment docs must reflect Compose 5.3+ `pre_start`, Composer external execution, and the retired updater service.
- 2026-08-31 scoped-model audit: Dlux tenant/user-visible records using row isolation are scoped (`Profile`, `ActivityLog`, notifications/rules/watches); remaining non-scoped concrete tables are global/system/owner-filtered infrastructure, with `GroupProfile.scope` managed manually by preset gates.

### Current Project's Unsolved Known Bugs:
- Release notes have cited tests that were not running: 3 modules were never in `test_all.TEST_LABELS` (61 tests). Registered, and `test_suite_registration` now guards it — but treat any "N new tests" claim in an older entry as unverified.
- The whole inline-update hand-off shipped untested end to end (1.8.0-1.8.8): unit tests pinned `write_request` while the caller could not reach it, and one updater test passed only because the crash produced the status it asserted. Drive the run, not the helper.
- Inline updates require a runtime volume writable *by Celery*; web's mount may be read-only and its local probe no longer decides (1.8.6). No fallback path is valid.

### Incomplete Tasks:
- **Priority 1:**
  - [ ] TAG THE REHEARSAL: Composer `v1.3.14b1` first (Dlux's manifest requires `>=1.3.14b1`), then Dlux `v1.8.14b1`. Nothing is pushed yet. Then exercise the flow on a real deployment: opt in, receive the beta, opt out, confirm no downgrade.
  - [ ] `release_channels_plan.md` remaining after the rehearsal: the reference-stack acceptance harness (§7), published-artifact acceptance as a dependent job (§3.8), promotion serialization (§3.6), and the Composer 1.4.0 retirement inventory (§9). 1.9.0b1/1.4.0b1 stay the first feature betas.
  - [ ] v1.8.8 shipped the titlebar feature unreviewed because `git add -A` swept the tree; `docs/RELEASING.md` now says stage explicit paths. Deployed stacks need `collectstatic` under `dlux.updater.supervisor` or they serve baked-image static against runtime templates.
  - [ ] Before v1.10.0 (removal moved there 2026-09-08, so it no longer gates 1.9.0): project-archive/dhub/trademarks must adopt the ribbon — 19 `advanced_filter_helper` call sites, and none of the three uses `RibbonMixin` yet. Each site carries per-field placeholders/col_class the ribbon replaces with an administrator-chosen layout, so it is a product decision per project. Pilot one filter against a running stack before converting the rest; none of the three is currently deployed locally. If that cannot land in time, move the removal to v1.10 instead of shipping 1.9.0 that breaks their list pages.
  - [ ] v1.9.0 remaining: an asset-manager view grouped by namespace; then adopt in the projects — switch_pos `Product.image`/`Service.image`/`PublicCatalogListing.image_override` and gov_edition `storage.Asset.image`, each with a migration and a backfill command.
  - [ ] Review live Docker staging acceptance for Composer migration and `dlux_check --apply`.
- **Priority 2:**
  - [ ] System Settings > Login Page > Full-page split: EN/AR hero-message textareas reuse the active UI language's empty Markdown placeholder, so both show Arabic under an Arabic UI (and both English under an English UI). Cosmetic only; resolve per field and preserve configured language order.
  - [ ] Postponed 2026-08-28: keep stale-route pruning import-only; revisit builder-save pruning only if an actual stale-entry problem appears.
  - [ ] Finish `forms/system_settings.py` group extraction behind existing contracts.
- **Completed Recently:**
  - [x] Channels implemented across both repos (2026-09-08). Dlux: `updater/channel.py` policy + token handoff, `DluxUpdateState.update_channel` (migration 0021), `allow_prereleases` selection, Options switch + `POST /sys/api/dlux-update/channel/`, tag classification in `release_check --classify`, PEP 440 tag ordering with migrations diffed against the last **stable** tag, `validate_declared_migration_effect` (caught this release's own manifest declaring `none` while adding 0021). Composer: `versions.py`/`dlux_channel.py`/`channel_config.py`/`release_tag.py`, `dlux channel`, `check --beta|--stable`, wrappers at marker 3.
  - [x] BLOCKER found and fixed: Composer's `KNOWN_REQUIREMENT_KEYS` lacked `migration_baseline` and fails closed, so **every published Composer would have refused the 1.8.14 manifest outright**. Dlux 1.8.14 was uninstallable as written. Fixed in Composer 1.3.14b1; that is why the manifest requires `>=1.3.14b1` and not `>=1.3.14` — a beta does not satisfy the floor of the release it precedes (2026-09-08).
  - [x] `archive_file` deprecation cleared: the only remaining callers were `archive_file_*` string overrides — renamed to `file_field_*` in archive (18), dhub (18) and decrees (2). Nothing depends on the widget's fallback shim now; the `apply_archive_file_widgets` names left in archive/dhub are those projects' own helpers, not dlux's contract (2026-09-08).
  - [x] `dlux_prune_assets`: dry-run by default, `--apply` to delete, `--namespace`/`--kind` scoping. References come from the `ManagedAssetField` registry (no reverse accessors exist — `related_name='+'`), the `dlux.shared` pool is skipped unless `--include-shared`, and a declaration it cannot read makes the run refuse rather than treat that model's assets as orphans. 9 tests (2026-09-08).
  - [x] v1.8.14: boot gate gained `apply` (celery migrates when Compose skips `pre_start`, instead of every service waiting); `requires.migration_baseline` makes a multi-release update's migration span knowable and `release_check` now actually enforces both floors (`validate_image_baseline` had never been called); audit/deletion sets centralised in `dlux.system.constants`, extensible, with the `AUDIT_FIELD_NAMES` shim due for removal in v1.10; audit columns now hide even when a table declares them; `test_settings_step_anchors` guards step anchors and immediately caught `ribbon_title`; backup restore test pinned to the inline path (2026-09-07).
  - [x] v1.8.13: Record Visibility switches anchored to `SETUP_STEP_SECURITY` (were `SETUP_STEP_LAYOUT` after the move) — the audit toggle could be turned on and never off; `_should_add_more_after_save()` now reads the value of `save_add_more`, not its presence, so a plain Save stops reopening the modal. Both reproduced on the live decrees dev stack before/after (2026-09-07).
  - [x] v1.8.12 context-menu regression: `dlux:dynamic_modal:open` bound in capture phase, so a host dispatching a non-bubbling CustomEvent on `document.body` (decrees view/edit) reaches the modal again. Latent since 1.8.0, masked by stale static; browser-verified across all three dispatch shapes (2026-09-06).
  - [x] v1.8.12 suite registration: `test_modal_content_init`, `test_titlebar_action_rail`, `test_inspector_shell` added to `TEST_LABELS` (2366 -> 2430) plus a guard that fails on any unregistered `test_*.py` (2026-09-06).
  - [x] v1.8.12 updater trio: reconcile also triggers on a runtime-generation change (a version update no longer leaves `active_version` frozen); `queue_image_update()` reports the live release via `active_runtime_version()`; `dlux_settings()` refuses a non-DEBUG boot on an empty/placeholder `SECRET_KEY` (opt out with `DLUX_ALLOW_INSECURE_SECRET_KEY`) (2026-09-06).
  - [x] v1.8.12 `dlux_image_gate`: adopt/keep/abort verdict so an image baking an older dlux keeps the newer active release instead of being refused outright, decided by the release's own `requires.baked_image` floor. Composer must adopt the command for the gate to relax (2026-09-06).
  - [x] Tooltip positioning feedback loop fixed (v1.8.12): `positionTooltip()` clears `left`/`top` before measuring, so the fixed, auto-width box is no longer shrink-to-fit-capped by its own stale offset (2026-09-05).
  - [x] v1.8.4 managed assets public API: `ManagedAssetField(kind, namespace, reads)` + registry, namespace column (0018, backfilled by kind), namespace-scoped dedup and storage paths, field-identity-authorized instant upload for every kind, public `resolve_asset_selection`/`apply_asset_pickers`/`apply_asset_selections`/`build_asset_field`/`ManagedAssetFormMixin`, `capture` support, System Settings switched onto the same public helper (2026-09-02).
  - [x] Data reset (shipping in v1.8.4): permanent mode (hard-deletes scoped rows + empties their recycle bin) behind a typed confirmation word, line models excluded via `cascade_parent()`, `trashed` counts in the catalog, and a `data_reset_finished` signal for projects to rebuild derived figures (2026-09-02).
  - [x] File widget renamed off `project-archive`'s `archive_file` names to `build_file_field` / `file_field_*` / `.dlux-file-*`, with v1.x shims for the two helpers, the old string keys and the `archive-file-input` opt-in class (2026-09-01).

### One-line info about last verified Tests:
- 2026-09-08: channels — full `dlux.tests` 2502 OK (33 new in `test_channels`), `node --test tests-js` 63 OK, composer 599 OK (43 new in `tests/test_channels.py`); key tests confirmed failing against pre-fix code (the `migration_baseline` refusal, `channel=` selection, the prerelease-satisfies-floor bug); `release_check` exit 0 for `v1.8.14b1` after the new effect check forced the manifest to declare `additive`.
- 2026-09-07: v1.8.14 — the new step-anchor guard found a second live instance of the audit-toggle bug (`ribbon_title` rendered in Ribbon, anchored to Components) and it is fixed; `expected_migration_baseline()` derives 1.8.9 from published history, which is the release decrees crossed.
- 2026-09-07: v1.8.13 — both fixes proven against the running decrees stack: audit toggle stored True->False from Access & Security; save response went `add_more:true` -> `add_more:false` with the modal staying closed. New tests fail on the pre-fix code.
- 2026-09-06: full `dlux.tests` 2430 OK (was 2366 — 3 unregistered modules + the new guard + 2 modal-listener tests); the capture-phase test fails against the pre-fix listener; event phases verified in a real browser (non-bubbling body dispatch reaches capture only).
- 2026-09-06: v1.8.12 updater work — full `dlux.tests` 2366 OK (17 new across `ReconcileTriggerTests`, `ActiveRuntimeVersionTests`, `ImageCandidateGateTests`, `PlaceholderSecretKeyTests`), `makemigrations --check` clean, `release_check --base-tag v1.8.11` exit 0, `dlux_image_gate` driven for real (1.8.6 vs active -> keep).
- 2026-09-05: tooltip drift — full `dlux.tests` 2349 OK and `node --test 'tests-js/*.test.mjs'` 63 OK (2 new in `tests-js/tooltip_position.test.mjs`; the stale-offset one fails on pre-fix code, 841px vs 762px). Browser-verified in a real repro: pre-fix walked 8px/hover after a resize, post-fix lands correct on the first hover.
- 2026-09-05: `test_package_handoff.HandoffCollectsStaticTests` no longer pins `1.8.11` — it derives a version above the baked floor, since `reconcile()` resets any volume release below `get_baked_version()` and the bump to 1.8.12 broke it.

### One-line info about last time edited Docs:
- 2026-09-08: `docs/RELEASING.md` "Channels: stable and beta" (tag table, refused tags, tested-minimum rule, stable-baseline migration rule); `docs/inline-updater.md` "Which releases are eligible" (ownership table, failure modes); `docs/reference.md` + `docs/FEATURES.md` entries; Composer `README.md` + `docs/RELEASING.md` mirrors, including the `:beta` alias advance rule.
- 2026-09-06: `release_channels_plan.md` records both projects' mandatory beta-first milestones, implementation paths, channel semantics, staging gates and retirement checklist; gitignored planning artifact.
- 2026-09-06: `docs/inline-updater.md` gained "Moving to an image that bakes an older DjangoLux" (adopt/keep/abort); `docs/deployment-configuration.md` documents `DLUX_ALLOW_INSECURE_SECRET_KEY`.

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
