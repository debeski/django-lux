# Project Tracker (django-lux)

## Part 1: Project Related
### Current Verified Snapshot:
- Package version source: `dlux/VERSION` = `1.2.1`; `dist/` is absent in this checkout.
- DjangoLux is a Django UX/application framework: `dlux_settings()`, `SystemSettings`, setup wizard, scoped models, user/security, navigation, reports, backup, scaffolding, optional SSO.
- Core resolver flow: `dlux.system` defaults/schema/registry -> `DLUX_CONFIG` -> DB `SystemSettings` -> normalized request/user/runtime context -> backend-enforced views/helpers.
- Active release standard: tag-driven GitHub Actions per `docs/RELEASING.md`; post-v1.2.0 work is now tracked under unreleased `v1.2.1` with matching `dlux/VERSION`.

### Current Project Adopted Standards:
- Settings integration: `from dlux.utils import dlux_settings`; `dlux_settings(globals())`; mount `dlux.urls` at root for `/accounts/` and `/sys/`.
- Settings source of truth: use `dlux.system` for constants/defaults/normalizers/schema/registry; only `dlux.models.default_*_config` wrappers remain as migration-history shims.
- DSRP-1 (`docs/security-dsrp-1.md`): backend authorization must match UI visibility; POST-only security mutators.
- Runtime UI uses one `dlux` prefix for authored CSS/data/events/JS globals; avoid inline runtime JS/CSS except approved JSON/dynamic-font bridges.
- User-facing copy routes through Dlux translations (`DLUX_STRINGS`) and must stay language/direction/theme aware.

### Adopted Standards' rules and policies:
- Maintain `tracker.md` as the brief live source of state, <=100 lines total, and update it after state/docs/tests changes.
- Changelog uses newest `## vX.Y.Z` sections and flat bold-title bullets; released/tagged sections are immutable.
- Preserve user changes and avoid destructive git commands unless explicitly requested.

### Cross-Cutting Audits if any:
- 2026-06-13: Conceptual survey covered docs, `dlux/`, split utils, views/forms/templates/static, backup/reports, tests, scaffolding, SSO, and viewer.

### Current Project's Unsolved Known Bugs:
- Fallback file/download redirects should remain reviewed in high-risk deployments; current `_safe_referer()` uses allowed-host checks.
- Mounted `test` compose stores sessions in Redis default cache; do not run live `cache.clear()` probes because that deletes browser sessions.

### Incomplete Tasks:
- **Priority 1:**
  - [ ] Browser-validate setup Step 10 (Logging) grid hydrate/serialize + audit tab + prune after collectstatic.
- **Priority 2 (deferred from ActivityLog plan):**
  - [ ] Optional: full request-scoped `transaction.on_commit` aggregator with nested-by-relation details + dev-satellite folding (deferred — `on_commit` doesn't fire under the TestCase suite; satellite scan was order-fragile and over-broad. Rolling-window fix shipped instead).
- **Completed Recently:**
  - [x] Mirrored first-launch setup headers on the language gate and wizard: title/description now occupy logical start and logo sits opposite (LTR text-left/logo-right; RTL text-right/logo-left); `system_setup.css` `?v=20260621a`; changelog/tests updated.
  - [x] Fixed English first-launch setup gate no-op: global `prevent_double_submit.js` disabled the first named submitter during serialization and stripped `setup_language=en`; helper now uses `event.submitter`, form-state repeat blocking, deferred disabling, and `?v=20260621a`; EN/AR tests/docs/changelog updated.
  - [x] Added localized descriptions for Dlux-owned assignable permissions without help text (reports, backup downloads, sections, activity log) in grouped user/staff permission cards; widget now uses a Dlux codename-to-translation map; docs/changelog/tests updated.
  - [x] Corrected setup language gate semantics: `/sys/setup/` language choice now controls setup UI language/direction only; `default_language` remains editable/save-only in Localization, bound POST rerenders preserve the chosen default radio, and `system_setup.js` is `?v=20260620l`; docs/changelog/tests updated.
  - [x] Fixed titlebar surface selector no-op: theme CSS `.titlebar { background: ... !important; }` rules overrode `titlebar.css` muted/glass styles; added post-theme `titlebar_surfaces.css` with higher-specificity `muted`/`glass` overrides, loaded after the theme loop (`?v=20260620a`); Chrome computed-style probe verified distinct default/muted/glass backgrounds for light/dark/neon; changelog/tests updated.
  - [x] Fixed setup option-change jumps for specific card selectors: `DluxChoiceSelectorWidget` hidden radios were absolutely positioned without a positioned option ancestor, so browser focus-scroll could move `.dlux-setup-scroll`/window when clicking lower titlebar/login/table-density cards; `selectors.css` now anchors hidden inputs to each `.dlux-choice-option` card and `selectors.js` keeps pointer scroll-restore fallback; Chrome probe verified input/card rect equality and unchanged scrollTop after click; cache-busters selectors css `?v=20260620c`, js `?v=20260620b`; changelog/tests updated.
  - [x] Fixed setup-shell measured-titlebar jump: removed `--dlux-setup-titlebar-offset` measurement, made `.dlux-setup-viewport` plain flow `height: calc(100vh - var(--header-height))` with no fixed `top`; css `?v=20260620i`, js `?v=20260620f`; 560 green earlier.
  - [x] Restored `dlux.constants` public surface (star re-export of `dlux.system.constants`, `__all__`-complete) after the registry refactor deleted it and broke downstream `from dlux.constants import ...` with `ModuleNotFoundError`; also dropped the redundant `paginate_by = DEFAULT_TABLE_PAGE_SIZE` + constant import from the app scaffold template and the `charlie` sample (dlux `patches.py`/`DluxTable` own per-page + rows-per-page selector); 560 green; changelog updated.
  - [x] Settled constants under `dlux.system.constants`: redirected internal imports/tests/templates; root `dlux.constants` remains as a thin re-export shim, while old default-module shims were removed per user direction; docs/changelog/tests updated.
  - [x] Added Phase B schema-driven form slice: `SystemSettingsForm` now hydrates/packs auth, registration, public-root, layout, and client-IP scalar groups from `dlux.system` schema; complex builders remain custom; `enforce_strong_passwords` flat auth export/import/save/runtime merge path completed; migration-wrapper invariant documented.
  - [x] Added Phase A `dlux.system` settings registry source of truth: canonical constants/defaults/normalizers/schema/registry now drive config defaults, flat legacy maps, runtime aliases, export/import field coverage, and model default maps; old defaults modules and published `dlux.models.default_*_config` callables remain importable; docs/changelog/version/tests updated.
  - [x] Fixed profile activity caps and single-session eviction: Recent Activity + System Interactions now show latest five each; `UserPresenceSession.session_key` folded into unreleased `0002` + `SessionStore.delete()` eviction supports cache/Redis-backed sessions; docs/changelog/tests updated.
  - [x] Fixed persisted notification language switching: serializers infer `DLUX_STRINGS` keys for legacy exact-match stored text, new fixed file/user/section notices emit `message_key`, and free-form/interpolated messages intentionally remain stored text; docs/changelog/tests updated.
  - [x] Fixed notification drawer bulk clear semantics: `/sys/api/notifications/clear-all/` and `clear_all_notifications()` now dismiss read visible states only, leaving unread drawer items untouched; labels/docs/changelog/tests updated.
  - [x] Fixed invalid profile password modal and keyed notification localization: invalid password-change POSTs reopen `#resetPasswordModal` without generic flash; `notify(..., message_key/title_key)` localizes flash/drawer/API payloads per request; docs/changelog/tests updated.
  - [x] Added no-op password-change rejection: shared `DluxPasswordMustChangeMixin` on profile password change + staff reset password rejects `new_password2` matching current hash, preserves stored hash and forced-change flag; EN/AR error string, docs/changelog/tests updated.
  - [x] Coordinated first-login forced password change with Initial User Setup: `DLUX_SHOW_INITIAL_USER_SETUP` is suppressed while `Profile.preferences["force_password_change"]` is active; `/accounts/welcome/` remains middleware-blocked until password change clears the flag; profile warning is persistent via `data-autoclose="false"`; docs/changelog/tests updated.
  - [x] Fixed shared `DluxChoiceSelectorWidget` toggle-card surfaces for dark-based themes: `selectors.css` now uses `--dlux-choice-toggle-surface*` variables backed by theme setup tokens; `base.html` selector CSS cache-buster bumped; focused regression added; changelog updated.
  - [x] ActivityLog redesign COMPLETE (plan `.claude/plans/set-up-the-robust-plan-twinkling-kettle.md`): Phases 1/2/5 (rename+category+`log_config`+gating) plus Phase 4 audit hooks (`log_audit_event` for login/lockout/2FA/password/session/trusted-device/permission, gated by `audit.events`), Phase 6 audit append-only `save()/delete()` + `dlux_prune_activity_log` (skips audit), Phase 5b `dlux.log_activity` dev helper, consumers (log-view user/system/audit tabs `?category=` gated to superuser/global-staff + admin `category`), and Phase 3 rolling-window User/Profile merge (fixes second-boundary double-log). 525 green.

### One-line info about last verified Tests:
- 2026-06-21: Mirrored setup header passed focused wizard/language-gate template and render tests (5), `django check`, `makemigrations --check --dry-run`, and `git diff --check`.
- 2026-06-21: English setup-language submit fix passed focused gate/helper tests (5), full `test_all.py` (567), `django check`, `makemigrations --check --dry-run`, and `git diff --check`; live Browser verification unavailable because the in-app browser connection failed before opening the page.
- 2026-06-21: Dlux permission descriptions passed focused `dlux.tests.test_permissions_ui` (7), `django check`, `makemigrations --check --dry-run`, and `git diff --check`.
- 2026-06-20: Titlebar surface fix passed Chrome computed-style probe (light/dark/neon default/muted/glass all distinct), focused titlebar/base-template tests (2), `django check`, and `git diff --check`.
- 2026-06-20: Choice selector focus-scroll fix passed headless Chrome selector probe, focused selector/template tests (2), setup view+JS/CSS tests (3), `django check`, and `git diff --check`.

### One-line info about last time edited Docs:
- 2026-06-22: Created unreleased `CHANGELOG.md` v1.2.1, moved post-tag setup fixes into it, and restored tagged v1.2.0 text.
- 2026-06-21: Updated `CHANGELOG.md`, `docs/FEATURES.md`, and `docs/admin-guide.md` for working English/Arabic first-launch setup language selection and named-submitter preservation.

## Part 2: Global
### Global Standard Helpers, Shortcuts, Info, etc.:
- Prefer `rg`/`rg --files` for repository discovery.

### Global Rulesets:
- Keep tracker brief/grounded; changelog/docs updates happen in the same turn as meaningful changes.

### Agent Handoff Rules:
- Read `tracker.md` every turn; preserve user changes; use tag-driven release docs plus version metadata for changelog decisions.

### References and Links:
- Security: `docs/security-dsrp-1.md`; Release: `docs/RELEASING.md`; Concept report: `docs/conceptual-codebase-report.md`.
