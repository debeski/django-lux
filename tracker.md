# Project Tracker (django-lux)

## Part 1: Project Related
### Current Verified Snapshot:
- v1.2.12 is TAGGED + PUBLISHED on PyPI; manifest now bumped to unreleased v1.2.13 (new appearance/anti-bot config toggles; NO migrations; inline-safe). All v1.2.13 work is uncommitted working-tree on top of the v1.2.12 tag — do NOT file it under v1.2.12.
- `dlux/release-manifest.json` is the version source (now v1.2.13, inline-safe: no new deps/migrations). Migration baseline: `0006` (v1.2.10) adds `SystemBackup.media_included` + `DluxUpdateRun.backup_mode`; no new migrations since (new keys are legacy_flat on existing JSONFields).
- v1.2.7 remains the mandatory rebuilt baseline before later manifest-approved inline releases.
- DjangoLux supplies settings/setup, scoped models, auth/security, navigation, reports, backup, scaffolding, SSO hooks, and the Compose updater.
- Updater state uses `DluxUpdateState`/`DluxUpdateRun` plus `dlux_runtime` releases, atomic pointer, generation, maintenance, heartbeat, and degraded markers.
- `switch_pos` is rolled back to active/baked v1.2.4 but degraded with maintenance retained after candidate and rollback Celery probes raced normal startup. v1.2.13 reconcile now SELF-HEALS this class: once back on baked it clears the stuck degraded flag (needs one reconcile post-upgrade, or a one-time flag clear / `down -v` since the current row predates the fix).

### Current Project Adopted Standards:
- Integrate settings with `from dlux.utils import dlux_settings`; call `dlux_settings(globals())`; mount `dlux.urls` at root.
- `dlux.system` owns settings defaults/schema/normalizers/registry; migration-history wrappers remain in `dlux.models`.
- DSRP-1 requires backend authorization to match UI visibility and security mutations to be POST-only.
- Authored runtime CSS/data/events/JS use the `dlux` prefix and external assets; user copy uses `DLUX_STRINGS`.
- Releases are tag-driven; package/version/release validation all read `dlux/release-manifest.json`.

### Adopted Standards' rules and policies:
- Maintain this tracker as verified project state, <=100 lines total; Part 1 <=55 lines.
- Root changelog sections are newest-first `## vX.Y.Z` with flat bold-title bullets; tagged sections are immutable.
- Never delete repository files; relocate obsolete/replaced material under `.xpose/` with relative-path preservation.
- Preserve unrelated user changes and use `apply_patch` for source/doc edits.
- NEVER put raw HTML tags in i18n strings or form label/help_text (en+ar+fallbacks): crispy renders help_text UNescaped, and an injected tag (e.g. `<title>`) silently truncates innerHTML-loaded dynamic-modal forms — swallowing every node after it with NO Python/JS error. Use plain words or HTML entities.
- ALWAYS reuse dlux-provided components, never roll your own: settings-form choice fields MUST bind `DluxChoiceSelectorWidget` via `_bind_choice_selector_widget` (variant `toggle` for few options, `card`+searchable for many) — never plain `forms.Select`; toggles use `build_settings_toggle_field`; modals use the dynamic modal; spinners use `DluxLoadingButton`; strings via `DLUX_STRINGS`/`s.get`. New settings keys follow the existing field's full pattern (decl→schema→normalizer→default→form widget→initial→clean preservation→payload→APP_CONFIG→export/import→en+ar). All of this is DSRP-1 (CSP-safe data-*/external-asset controls) + form-consistency; match an existing field end-to-end before adding one.
- Feature/config/schema/API/security/deployment changes require same-turn technical documentation.

### Cross-Cutting Audits if any:
- 2026-06-23: Updater audit covered artifacts, attestation, dependency/migration gates, supervisor/runtime state, recovery, UI/API, scaffold, nginx, and Compose.
- 2026-06-24: ScanLink has no PDF byte/page cap; generated-project nginx imposes an effective `5M` form-upload ceiling.
- 2026-06-24: Reports audit covered activity-window propagation, Celery backup lifecycle, durable polling/download handoff, media sharing, and nginx response/security behavior.

### Current Project's Unsolved Known Bugs:
- Fallback file/download redirects remain a high-risk-deployment review point; `_safe_referer()` currently enforces allowed hosts.
- Mounted test Compose uses Redis sessions; never use live `cache.clear()` probes because they delete browser sessions.

### Incomplete Tasks:
- **Priority 1:**
  - [ ] Browser-validate setup Step 10 logging grid hydrate/serialize, audit tab, and prune after collectstatic.
  - [ ] Browser-validate v1.2.13: anon public root with show_sidebar_on_public on — confirm `sidebar_items.html` degrades gracefully (public/empty entries) for AnonymousUser.
- **Priority 2:**
  - [ ] Optional request-scoped `transaction.on_commit` activity aggregator; deferred due TestCase/order fragility.
- **Completed Recently:**
  - [x] v1.2.13 updater recovery hardening (`dlux/updater`): (1) reconcile reverts an unreconstructable active release (active_version != baked, no staged volume release on disk, no wheel url/sha — image/mount activation, backward image move, or wiped volume) to the BAKED image instead of hard-failing on a wheel that never existed (new branch + shared `_reset_to_baked_image()` helper consolidating the two prior baked-reset blocks); (2) once converged on baked (`active==baked`, source image) reconcile CLEARS a stuck `degraded` flag so transient degrades self-heal — volume-release degrades (e.g. failed-rollback target present on disk) stay sticky (proven by existing `test_manual_rollback_recovery_failure`); (3) scaffold supervisor template derives `DLUX_BAKED_VERSION` from `dlux.__version__` (manifest, stdlib-only import) not `importlib.metadata`, so bind-mount dev works (metadata fallback retained). Supervisor lives in project `tools/` → existing deployments need rebuild/`enable-updater` re-copy for #3; reconcile #1/#2 ship in the dlux package (inline). 3 new tests (demote-to-baked, degraded self-heal, supervisor source guard). No migration; inline-safe.
  - [x] v1.2.13 FIXED blank System Settings steps 3-11: `public_root_title` help string contained a literal `<title>` tag; crispy renders help_text as RAW HTML, so when the dynamic-modal AJAX form was injected via innerHTML the browser parsed `<title>` as a real element and swallowed every wizard step after Security (the field's step) — steps 3-11 vanished from the DOM with NO Python/JS error. Removed the literal tag from help (en+ar+form fallback). VERIFIED in a real headless browser (playwright): pre-fix modal had 3 wizard-steps, post-fix 12 with the correct one visible. Reverted my earlier wrong-hypothesis changes (dynamic_modal/main.js script-skip, sections.py wizard cap). Lesson: NEVER embed raw HTML tags in i18n help/label strings — crispy outputs them unescaped and they silently truncate innerHTML-injected forms.
  - [x] v1.2.13 layout polish: (1) form density made genuinely distinct — density vars now also drive inter-row margin (overrides crispy `mb-3`) + input padding (verified 37/49/58px input heights, 6.4/16/24px gaps); (2) Form Density + Modal Size are now PER-USER (Options cards mirroring Table Density: `form_density_previews.html`/`modal_size_previews.html` + `options.js` `initBodyAttrPicker` → `/sys/api/preferences/update/` validates → `dlux_context` resolves user→default → `body[data-dlux-form-density]`/`[data-dlux-modal-size]`); modal width now body-attr CSS (compact 800/standard 1140/wide min(96vw,1480px)) not a Bootstrap class; (3) body-affecting settings (footer show/text, sticky, zebra, form-density, modal-size) LIVE-PREVIEW via `applyImmediateSystemSettingsPreview` (public-root settings excluded like language); (4) sticky headers FIXED — `overflow:hidden`/`overflow-x:auto` table wrappers trapped `position:sticky`; sticky-on now sets them `overflow:visible` so the header pins to `#mainContent` top (page-level, per user choice; wide tables lose contained h-scroll). 2 new prefs tests; 652 green; browser-verified (playwright). DECREES container seeded 40-50 rows for sticky testing.
  - [x] v1.2.13 appearance/anti-bot config toggles (NO migration; all legacy_flat on existing JSONFields). layout_config: `sticky_table_headers`/`zebra_striping` (default on; gate prior unconditional tables.css via `body[data-dlux-sticky-header/zebra]` from base.html), `default_form_density` (new `--dlux-form-*` vars in form_fields.css via `body[data-dlux-form-density]`), `default_modal_size` (→`APP_CONFIG.appearance.modal_size_class`, applied in dynamic_modal.html; `.dlux-modal-wide` in main.css). registration_config: `honeypot_enabled` gates existing `website` trap in views/registration.py. public_root_config: `public_root_theme` (context_processors forces theme + emits its CSS), `public_root_title`/`public_root_meta_description` (base.html `<title>`/`<meta>` for anon index), `show_titlebar_on_public`+`show_sidebar_on_public` (default OFF) supersede titlebar `hide_on_public_unauthenticated_index` (form field removed; legacy migrates inverted in expand+DB+import layers) and replace base.html hardcoded anon-sidebar gate via new `_is_public_index()`/`dlux_show_sidebar`/`dlux_is_public_index`. `SystemSettings.load()` first-run seeding mirrors all new keys (prevents expand-fold clobber of DLUX_CONFIG). All gated by `_should_apply_db_override`, single-step preservation, export/import (SYSTEM_SETTINGS_EXPORT_FIELDS). Strings en+ar. Suite RAN in throwaway venv: 647 tests, only 2 fail (pre-existing env: test_supervisor importlib.metadata baked-version; test_user_profile_stats full-suite ordering — both pass/clean in isolation).
  - [x] Older released items (v1.2.4–v1.2.12: dlux_setup AST detect, footer disable/link + z-index/theme colors, allow_user_home_url move, loading-button helper + migrations, updater UX, scaffold nginx envsubst, delete-perm re-enable, global footer, dlb-viewer, backup scope `0006`, updater hardening, etc.) — see CHANGELOG.

### One-line info about last verified Tests:
- 2026-06-27: v1.2.13 full suite GREEN in throwaway venv (+playwright): 652 tests, all pass (config + updater-recovery + 2 new form/modal-density prefs tests). Browser-verified Options cards apply/persist/roundtrip + settings-modal live preview. Fixed two PRE-EXISTING failures (baseline v1.2.12 failed both): (1) `test_supervisor` now pins `DLUX_BAKED_VERSION='9.9.9-supervisor-test'` in the subprocess env + asserts the sentinel (dropped importlib.metadata derivation); (2) `test_user_profile_stats` full-suite ordering — `model_name='TestModel'` collided with `test_signals.TestModel` (registered process-wide → resolves to an ineligible dlux model → count 0); switched to unique `ProfileStatsFixtureModel` so report eligibility falls through to include. New tests: 6 in test_system_registry + 3 in test_defaults_and_urls; fixed titlebar-field assertions.
- 2026-06-26: CI #3 (637 tests, test_dlux_setup ran) failed only on `test_get_system_config_with_settings_override` — `db_config['footer_enabled']` was set UNCONDITIONALLY, so `expand_system_config_groups` materialized a full `layout_config` (default density) that clobbered a settings-level `default_table_density='roomy'` override on unconfigured systems. Fixed: gate footer_enabled behind `_should_apply_db_override` like the other layout keys. Traced all 6 `default_table_density` asserts in test_utils — pass. Earlier CI #2 fixed test_updater 606 (stale `setRootStatus(message,5000)` assertion). Not run locally (no Django).
- 2026-06-26: CI #1 — `test_startproject_creates_expected_files` `.env` line count 12→15 (NGINX_* vars). Fixed.
- 2026-06-24: v1.2.11 baseline — full suite 631 OK (supervisor test derives baked version from `importlib.metadata`).

### One-line info about last time edited Docs:
- 2026-06-27: v1.2.13 docs — reference.md (new layout/public_root/honeypot keys), customization-guide.md ("Appearance Toggles" + "Public Root Appearance and SEO"), admin-guide.md (Step 3 public-root controls, Step 7 titlebar note), registration.md (honeypot toggle).

## Part 2: Global
### Global Standard Helpers, Shortcuts, Info, etc.:
- Prefer `rg`/`rg --files` for discovery; inspect durable updater runs through the database, not web access logs alone.

### Global Rulesets:
- Keep tracker/changelog/docs synchronized with verified code and executed checks.

### Agent Handoff Rules:
- Read `tracker.md` every turn; preserve user work; use tag state plus release manifest before changelog/version edits.

### References and Links:
- Security: `docs/security-dsrp-1.md`; updater: `docs/inline-updater.md`; release: `docs/RELEASING.md`.
