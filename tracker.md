# Project Tracker (django-lux)

## Part 1: Project Related
### Current Verified Snapshot:
- Current source version: unreleased v1.7.2; v1.7.1 is tagged/published — append to the v1.7.2 entry, never a tagged one.
- DjangoLux includes the typed Composer bridge and state-row-serialized update admission; generated projects emit one hardened `composer-agent` while Composer owns legacy migration.
- `Scope.default_theme` supplies the runtime fallback when scopes are enabled and multiple themes are selectable; valid personal preferences still win.
- Updater state uses `DluxUpdateState`/`DluxUpdateRun` plus `dlux_runtime`; generated proxy baseline is Caddy-default `.proxy/` with updater parity.
- The migrator contract: `-mm` forces makemigrations for ALL target apps; bare only for apps with no `migrations/0001_*.py`; `-nm` skips makemigrations+migrate but STILL collects static; `-mm`/`-nm` exclusive. Composer runs it ONCE via the `org.dlux.post-start` label (never Compose's native `post_start`, which Compose runs itself unflagged).

### Current Project Adopted Standards:
- ONE switch: reuse `dlux-settings-toggle-field__control form-switch` + `form-check-input dlux-settings-toggle-field__input` + `type=checkbox`; themes/system_setup.css style those names only. Never hand-roll `form-check form-switch`. Keep host layout (e.g. `dlux-assist-bar`) separate from it.
- Integrate settings with `from dlux.utils import dlux_settings`; call `dlux_settings(globals())`; mount `dlux.urls` at root.
- `dlux.system` owns settings defaults/schema/normalizers/registry; migration-history wrappers remain in `dlux.models`.
- DSRP-1: backend authorization must match UI visibility; security mutations are POST-only.
- Releases are tag-driven; version source is `dlux/release-manifest.json`.

### Adopted Standards' rules and policies:
- Read `tracker.md` every turn; keep it under 100 lines; preserve unrelated user work; use `apply_patch` for manual edits.
- Before changelog edits, check `git tag`; tagged versions are immutable, so start a new version and bump manifest.
- Feature/config/schema/API/security/deployment changes require same-turn docs and changelog.
- No raw HTML in i18n strings/form help; crispy help_text is unescaped.
- Reuse Dlux components and full schema -> form -> config import/export patterns.

### Cross-Cutting Audits if any:
- 2026-06/07 updater/report/scaffold audits; 2026-08-03 table integration audit: Archive v1.6.2 matches package/collected assets and uses the supported unwrapped DLUX shell.
- Mounted test Compose uses Redis sessions; never use live `cache.clear()` probes because they delete browser sessions.
- 2026-08-07 structure audit: preserve root public import façades; reduce `forms.py`, `views/general.py`, `reports.py`, `discovery.py`, `backup.py`, and domain-specific `utils` incrementally behind contract tests.

### Current Project's Unsolved Known Bugs:
- Isolated `dlux.tests.test_groups` has two 302 failures because setup middleware sees default unconfigured settings; package discovery passes after earlier tests cache configured state.
- dlux has 2 module-level import cycles (32 modules); `dlux.utils` is inside a 27-module cluster with models/middleware/discovery/context_processors. A project doing module-scope `from dlux.utils import X` in a urls-reachable module can see a half-initialised package -> Django reports "URLconf has no patterns". Import inside the function. Detector: `scripts/import_cycles.py`.
- Fallback file/download redirects remain a high-risk-deployment review point; `_safe_referer()` currently enforces allowed hosts.
- Legacy `switch_pos` v1.2.4 deployments may stay degraded until v1.2.13+ reconcile clears or operator resets runtime flags.
- A stale pre-exclusion `composer-updater` can recreate its Docker socket proxy during the first 1.5.x app-image update and lose `DOCKER_HOST`; update Composer and migrate the legacy block with `enable-agent` before retrying.

### Incomplete Tasks:
- **Priority 1:**
  - [ ] project-archive: unresolved `dlux-updater` restart loop — still runs retired `tools.dlux_runtime_supervisor` (no strictly-newer gate) and `manage.py` lacks the release resolver; run `dlux enable-updater` and re-check `DluxUpdateState.active_version` vs running `dlux.__version__`.
  - [ ] Doctor P3 (composer repo): wire `composer check` drift-diff to exec `dlux_stack_contract` + mirror `diff_attachments()` AND `diff_command_modules()`/`fix_command_modules()` (contract schema 2).
  - [ ] Doctor P4: add `dlux.doctor` remote action + Control Panel surface; redact before the report leaves the host.
  - [ ] Verify `dlux_check --apply` against a live Docker stack (collectstatic + migrator paths); only unit-tested so far.
  - [ ] Browser-validate setup Step 11 logging grid hydrate/serialize, audit tab, and prune after collectstatic.
  - [ ] Run live Docker staging acceptance for central image update, backup creation, outage replay, and control-panel self-update.
  - [ ] Browser-validate General Reports/Backup & Restore plus Navigation Root, anonymous public root, and Control Panel at desktop/mobile widths (in-app browser unavailable 2026-08-03).
  - [ ] Re-export and visually verify the fixed Archive `sys/reports/print/` PDF is exactly two A4 pages (in-app browser has no attached tab).
- **Priority 2:**
  - [ ] Stage the domain-oriented package restructure after adding public-import, URL-name, migration-drift, template/static-path, and task-path contract checks.
  - [ ] Build a superuser Asset Manager from the Admin-panel action rail: `ManagedAsset`/default storage for images and WOFF2; keep executable CSS/JS code-owned.
  - [ ] Reference assets through protected relations (system/login logos, favicon, login background, font variants); one reusable picker must auto-register direct uploads, reuse existing assets, detach without deleting, and show `collect_related_objects()` usage guards.
- **Completed Recently:**
  - [x] v1.7.2 per-scope default theme: `Scope.default_theme` + inline-safe migration 0016; scope form gated by enabled scopes and >1 allowed theme; request/onboarding fallback; valid personal preference wins. +11 tests.
  - [x] v1.7.2 two-theme sidebar control switches directly to the other allowed theme; one theme hides it and 3+ retain the popup. Native buttons, focus state, live swatch/label, persistence. +4 tests.
  - [x] v1.7.2 FIXED archive startup: dlux resolved a URL while the project's ROOT_URLCONF was mid-import (gettext patch -> get_system_config -> sidebar sanitize -> reverse), so Django cached the half-built module and all URL checks failed. Guard + 3 mutation-verified regressions.
  - [x] v1.7.2 server-side sticky helpers in `dlux.utils` (`sticky_forms_enabled`/`sticky_form_initial`, read the `sticky_forms` pref). project-archive uses them (6 views + 6 templates, +6 archive tests); its helper falls back to reading the pref directly because archive pins `django-lux==1.7.1`.
  - [x] SUPERSEDED projects (archive, decrees) prefill SERVER-SIDE in views/forms and used to gate on the `enable_prefill` COOKIE (default 'true'). Dropping the cookie writer made it permanently on — fixed by `dlux.utils.sticky_forms_enabled(request)` / `sticky_form_initial(...)` reading the `sticky_forms` preference. `data-sticky-server` marks server-prefilled forms (skip client fill, reload on toggle). project-archive converted (6 sites + 6 templates); **project-decrees still reads the cookie and needs the same change**.
  - [x] v1.7.2 assisted entry split: autofill(FK)+sticky were BOTH dead since v1.5.10 (`injectToggle()` targeted a selector the titlebar restructure renamed; init `return`ed when it failed). Now two independent `Profile.preferences` keys — `autofill_from_related` (default ON) / `sticky_forms` (default OFF); Options card + hardcoded-Arabic control removed. +19 tests.
  - [x] v1.7.2 sidebar toggle: real control affordances + lazy icon picker (disclosure); directional glyph uses ONE composed `scaleX(calc(--dlux-icon-rtl * --dlux-icon-state))`.
  - [x] v1.7.2 toggle-icon picker disabled under `collapse_mode == locked_expanded` (toggle is hidden on desktop then) as well as when the sidebar is off; `syncSidebarToggleIconAvailability()` + server-rendered `disabled`. NOTE: the toggle STILL renders below 1100px in that mode, so the icon remains user-visible on mobile. +6 tests.
### One-line info about last verified Tests:
- 2026-08-08: scope default theme — package discovery 1454 GREEN (2 PG-only skips); focused 11 GREEN; migration drift none; inline-safe release check passed. NOT browser-verified.
- 2026-08-08: custom-font registry/form contract — `dlux.tests.test_custom_fonts` 5 GREEN; `DLUX_CUSTOM_FONTS` registration, WOFF2 CSS, validation, and System Settings discovery verified.
- 2026-08-08: two-theme direct toggle — package discovery 1443 GREEN (2 PG-only skips); focused context/theme/group sequence 45 GREEN; no migrations. NOT browser-verified (browser control unavailable).
- 2026-08-08: assist bar + awaitable `updatePreferences` — full suite 1439 GREEN.
- 2026-08-07: dlux-owned sticky forms — full suite 1426 GREEN (2 PG-only skips). NOT browser-verified.
### One-line info about last time edited Docs:
- 2026-08-08: `docs/FEATURES.md`, `docs/developer-guide.md`, `docs/admin-guide.md` — per-scope default-theme storage, form dependencies, and runtime fallback.
- 2026-08-08: `docs/FEATURES.md` theme/sidebar toolbar behavior for the exactly-two direct toggle and 3+ popup.

## Part 2: Global
### Global Standard Helpers, Shortcuts, Info, etc.:
- Prefer `rg`/`rg --files`; inspect durable updater runs through DB/runtime state, not web logs alone.
- Static cache-busting: `{% dlux_static %}` appends the Dlux version plus source mtime in DEBUG; Caddy caches only files that exist.

### Global Rulesets:
- Keep tracker/changelog/docs synchronized with verified code and executed checks.
- File cleanup policy: move obsolete files into `.xpose/<relative path>`; never delete repo files or directories.
- Project-side runtime helpers belong in the package (supervisor, smtp relay): scaffold copies strand fixes in whatever version a project was generated with.

### Agent Handoff Rules:
- Preserve user work; if tagged version exists, create next changelog/manifest version.
- Adding/extending a system setting: read `docs/adding-system-settings.md` first; add keys to `SYSTEM_SETTINGS_EXPORT_FIELDS`.

### References and Links:
- Security: `docs/security-dsrp-1.md`; updater: `docs/inline-updater.md`; release: `docs/RELEASING.md`.
- Add a system setting: `docs/adding-system-settings.md`. Downstream app config: `reference.md` (`extra_config['app']`).
