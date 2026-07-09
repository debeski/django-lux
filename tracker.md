# Project Tracker (django-lux)

## Part 1: Project Related
### Current Verified Snapshot:
- v1.3.0-v1.4.0 all tagged/released; v1.4.0 tagged 2026-07-09 07:40 for titlebar global search, session lifecycle, app-wide language activation, and microsys branding-media repair.
- Working tree = unreleased v1.4.1: Options layout styles, settings-modal speed/grouping, inactivity scroll throttle, Nav fallback, Admin bulk forced password command, and public-registration Scope/Group defaults; manifest v1.4.1, inline_safe true.
- `dlux/release-manifest.json` is version source; migration baseline `0009` adds `Scope.description` + public-registration default markers; groups use native `auth.Group`; v1.2.7 remains mandatory rebuilt baseline.
- DjangoLux supplies settings/setup, auth/security, navigation, reports, backup, scaffolding, SSO hooks, and updater; updater state uses `DluxUpdateState`/`DluxUpdateRun` plus `dlux_runtime`.
- `switch_pos` legacy note: active/baked v1.2.4 may stay degraded until v1.2.13+ reconcile clears it or a one-time flag clear / `down -v` is done.

### Current Project Adopted Standards:
- Integrate settings with `from dlux.utils import dlux_settings`; call `dlux_settings(globals())`; mount `dlux.urls` at root.
- `dlux.system` owns settings defaults/schema/normalizers/registry; migration-history wrappers remain in `dlux.models`.
- DSRP-1 requires backend authorization to match UI visibility and security mutations to be POST-only.
- Authored runtime CSS/data/events/JS use the `dlux` prefix and external assets; user copy uses `DLUX_STRINGS`.
- Releases are tag-driven; package/version/release validation read `dlux/release-manifest.json`.

### Adopted Standards' rules and policies:
- LANGUAGE: `LocaleMiddleware` is auth-blind; after auth use `get_current_language_code(request)` or `request.LANGUAGE_CODE` only inside/after `DluxMiddleware._activate_display_language`.
- Tracker/changelog/git policy: keep tracker <=100 lines; newest-first changelog; tagged releases immutable; never remove repo files; preserve unrelated user work; use `apply_patch`.
- No raw HTML in i18n strings or form label/help_text; crispy help_text is unescaped and can break dynamic modal DOM.
- Reuse Dlux components: choice selectors, toggles, dynamic modal, loading buttons, strings, and full schema->form->config import/export patterns.
- Feature/config/schema/API/security/deployment changes require same-turn technical docs.

### Cross-Cutting Audits if any:
- 2026-06-23: Updater audit covered artifacts, attestation, dependency/migration gates, supervisor/runtime state, recovery, UI/API, scaffold, nginx, and Compose.
- 2026-06-24: ScanLink no PDF byte/page cap; gen-project nginx effective `5M` upload ceiling; reports audit covered backup/download/media/nginx.
- 2026-07-04: Scaffold-vs-`../project-decrees` audit; fixed stray committed `.pyc`; open user call on back-porting compose `post_start migrator` + smtp relay depends_on.

### Current Project's Unsolved Known Bugs:
- Fallback file/download redirects remain a high-risk-deployment review point; `_safe_referer()` currently enforces allowed hosts.
- Mounted test Compose uses Redis sessions; never use live `cache.clear()` probes because they delete browser sessions.

### Incomplete Tasks:
- **Priority 1:**
  - [ ] Browser-validate setup Step 10 logging grid hydrate/serialize, audit tab, and prune after collectstatic.
  - [ ] Browser-validate v1.2.13: anon public root with show_sidebar_on_public on; confirm `sidebar_items.html` degrades for AnonymousUser.
- **Priority 2:**
  - [ ] Optional request-scoped `transaction.on_commit` activity aggregator; deferred due TestCase/order fragility.
- **Completed Recently:**
  - [x] v1.4.1 Nav titles + confirm-password unify/redesign + dlb-viewer check (735 green): (1) NAV: current-page title = last crumb; `_node_to_crumb` resolved label from node-labels→catalog→`_humanize`, but reports/profile aren't catalog candidates → English. FIX: `_node_to_crumb` now also resolves `SYSTEM_ROUTE_META[leaf].label_key` via get_strings(lang,overrides) before humanize; added `reports_overview` to META (+`__dlux_reports__` marker). (NOTE: first attempt only fixed `build_navbar_route_label_map` = the history-trail map, NOT the current-title path — wrong place.) (2) CONFIRM: global `window.dluxConfirmPassword` (partial `confirm_password_modal.html` in base.html + `confirm_password.js`) REDESIGNED to admin-modal style (header+title/close, warning/danger alert body, labeled password, footer cancel+confirm) — NOT the small profile popup I first reused; dynamic title/desc/confirmLabel/danger; profile `showConfirmation`=thin wrapper; admin Force-passwords chip drives it via data-* (bespoke modal removed). (3) `tools/dlb-viewer` (Go) IN-LINE — DLB1/PBKDF2/Fernet/schema match backup.py; go build+test pass; parsed a fresh dlux .dlb. +2 wiring tests. README +global-search. NOT browser-verified (running instance must be on current build).
  - [x] v1.4.1 public-registration Scope/Group defaults: context-menu markers on Scopes/Group presets, `Scope.description`, scope detail modal, activation applies scope + live `auth.Group` memberships; migration `0009`, +6 tests, docs/changelog/manifest.
  - [x] v1.4.1 Admin panel bulk forced password-change command: circular heading-row command launcher; `/sys/admin/force-password-change-all/` POST superuser+current-password gated; marks non-superuser `Profile.preferences.force_password_change`; +4 tests, docs/changelog/manifest.
  - [x] v1.4.1 Nav Bar Dlux link-parent fallback: `system_backup_page` declares `breadcrumb_parent='options_view'`; unplaced route shows `Root/System/Application Options/Backup & Restore`; builder exposes system routes and explicit hierarchy wins; +2 tests, docs/changelog/manifest.
  - [x] v1.4.1 settings modal speed/lighter grouping: `_step_render(step_idx, template, ctx)` gates heavy step fragments; footer moved to Identity; no step renumber.
  - [x] v1.4.1 Options layout styles: JSON-only `layout_config.options_style` cards/tabs/compact; fail-safe tabs CSS; +7 `test_options_layout.py`; no migration.

### One-line info about last verified Tests:
- 2026-07-09: v1.4.1 full suite GREEN via `.venv/bin/python dlux/tests/test_all.py --verbosity=1`: 735 tests; `DJANGO_SETTINGS_MODULE=dlux.tests.settings .venv/bin/python -m django makemigrations --check --dry-run` clean; manifest JSON valid.
- 2026-07-09: targeted green after public-registration defaults: registration/groups/scope tests = 21; scope-detail single test green after adding group-preset list.
- 2026-07-09 earlier: v1.4.1 721 tests after options_layout; v1.4.0 714 tests after search.
- Older baselines: v1.3.7 692; v1.3.6 683; v1.3.0 667; v1.2.13 652.

### One-line info about last time edited Docs:
- 2026-07-09: docs updated for `options_style`, Nav Bar `breadcrumb_parent`, Admin bulk forced password change, and Scope/Group public-registration defaults; `.xpose/plan.md` completed that workstream.
- 2026-07-08/07: session-lifecycle and privacy/consent docs, including `docs/data-privacy.md`.

## Part 2: Global
### Global Standard Helpers, Shortcuts, Info, etc.:
- Prefer `rg`/`rg --files` for discovery; inspect durable updater runs through the database, not web access logs alone.

### Global Rulesets:
- Keep tracker/changelog/docs synchronized with verified code and executed checks.
- Static cache-busting: use `{% dlux_static %}` for versioned dlux assets; it appends `?v=dlux.__version__` and works in render contexts without `DLUX_VERSION`.

### Agent Handoff Rules:
- Read `tracker.md` every turn; preserve user work; use tag state plus release manifest before changelog/version edits.

### References and Links:
- Security: `docs/security-dsrp-1.md`; updater: `docs/inline-updater.md`; release: `docs/RELEASING.md`.
