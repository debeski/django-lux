# Project Tracker (django-lux)

## Part 1: Project Related
### Current Verified Snapshot:
- v1.2.13 is TAGGED + RELEASED (committed `98ddb52`, tag `v1.2.13`; appearance/anti-bot toggles + per-user form/modal density + sticky headers + updater hardening). NOTE: it was first mis-tagged `v1.2.13`→typo`v1.12.13` (release CI failed the tag-vs-manifest guard so NOTHING published; bad tag deleted local+remote). Manifest now bumped to unreleased v1.2.14 (frontend-only modal-size-pref fix) on top of the v1.2.13 commit.
- `dlux/release-manifest.json` is the version source (now v1.2.14, inline-safe: no new deps/migrations). Migration baseline: `0006` (v1.2.10) adds `SystemBackup.media_included` + `DluxUpdateRun.backup_mode`; no new migrations since (new keys are legacy_flat on existing JSONFields).
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
  - [x] v1.2.14 PUBLIC_ROOT_THEME reuses the theme swatch picker: bound to `DluxChoiceSelectorWidget(variant='swatch')` with per-theme `preview_class='...dlux-theme-preview--<slug>'` (same swatches as the theme picker; `--swatch` variant already in selectors.css → no new JS/CSS). Empty '' = system default (`bi-circle-half`). LIMITED to allowed themes via `get_theme_options(s, config.get('allowed_themes'))` (verified decrees: 4 allowed → 5 radios). `clean_public_root_theme` still accepts any stored slug (restricting allowed can't block save). 654 green (clean venv) + 146 referencing-module tests. NOTE: forms.py is server-side → web process must reload for the live app to show it.
  - [x] v1.2.14 RESET DEFAULTS out of the options grid → standalone footer danger zone (`.dlux-options-reset-footer`/`.dlux-options-reset-bar`, full-width strip below grid: title/desc start, Reset→Confirm/Cancel end, red `--danger` accent). NO JS change (global `.dlux-options-panel--danger[data-reset-url]` + `#btnReset*`/`#resetActions`). options.css→20260630b; test reset-card assertion → `dlux-options-reset-footer`. 654 green; rendered 200; collectstatic'd.
  - [x] v1.2.14 ADMIN PANEL: merged the 3 admin Options cards (System Info, Backup, System Settings) into ONE pinned full-width first-row `.dlux-admin-panel-card` (`grid-column:1/-1`, NO `data-options-card` so it's excluded from drag-reorder → stays first). Top zone = 3 flex tiles (status/update/backup) that wrap only when forced; status keeps storage+server-time+py+dj inline with the rest of diagnostics behind a `<details>` expander; the `.dlux-updater` widget pulled out of the old info table into its own tile. Settings tiles → horizontal auto-fill `.dlux-admin-settings-grid` bottom strip. Built via scratch script slicing original markup verbatim (no retype). Strings `admin_panel_*` en+ar; options.css→20260630a. Updated tests (test_views backup/grid markers, test_defaults_and_urls system-info→admin-panel marker). 654 green; rendered 200 in decrees container; collectstatic'd. PUBLIC-ROOT toggles (`show_titlebar/sidebar_on_public`) DO exist — Settings→Security, revealed when Public Root enabled (user thought missing). NEXT: user visual verify at localhost:82.
  - [x] v1.2.14 (other fixes, all in CHANGELOG): (a) ADMIN NOTIFICATION on successful inline update — `UpdateService._complete()` notifies active superusers for `apply`→`completed` after the atomic commit, isolated (try/except), gated on notifications enabled; `notif_app_updated_*` en+ar. (b) DISCOVERY DUP FIX — `_is_candidate` now excludes `<app>_api`/`api` namespaces + `/api/` paths (API counterparts shared the page's label → dup landing/sidebar entries; live: 11→8 opts). (c) PER-USER MODAL SIZE no longer clobbered by global default — `system_setup.js` stopped previewing `default_modal_size`/`default_form_density` (they're non-overrider DEFAULTS not a live body preview), and `dynamic_modal/main.js` re-asserts `USER_PREFS.modal_size` before `show()`. Bumped system_setup.js/dynamic_modal→20260629a, manifest→1.2.14.
  - [x] v1.2.13 RELEASED (tag `v1.2.13`, commit `98ddb52`) — see CHANGELOG for full detail. Shipped: appearance/anti-bot config toggles (layout `sticky_table_headers`/`zebra_striping`/`default_form_density`/`default_modal_size`; registration `honeypot_enabled`; public_root theme/title/meta + `show_titlebar_on_public`/`show_sidebar_on_public` superseding the legacy titlebar hide flag); per-user Form Density + Modal Size Options cards; sticky headers fixed (overflow wrappers trapped `position:sticky`; sticky-on→`overflow:visible`, `top:-1.5rem` flush under titlebar, solid `--table-row` backdrop); updater recovery hardening (reconcile reverts unreconstructable active→baked + self-heals stuck degraded; supervisor bakes from `dlux.__version__`); scan_link idempotency; and the `<title>`-in-help-text wizard-truncation fix (LESSON pinned above). All no-migration/inline-safe. Older released items v1.2.4–v1.2.12 (dlux_setup AST, footer, loading-button helper, updater UX, nginx envsubst, dlb-viewer, backup scope `0006`, etc.) — all in CHANGELOG.

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
