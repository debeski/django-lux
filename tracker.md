# Project Tracker (django-lux)

## Part 1: Project Related
### Current Verified Snapshot:
- Package version source: `dlux/VERSION` = `1.1.0`; `dist/` is absent in this checkout.
- DjangoLux is a Django UX/application framework: `dlux_settings()`, `SystemSettings`, setup wizard, scoped models, user/security, navigation, reports, backup, scaffolding, optional SSO.
- Core resolver flow: defaults -> `DLUX_CONFIG` -> DB `SystemSettings` -> normalized request/user/runtime context -> backend-enforced views/helpers.
- Active release standard: tag-driven GitHub Actions per `docs/RELEASING.md`; current unreleased work is logged under `CHANGELOG.md` `## v1.1.0`.

### Current Project Adopted Standards:
- Settings integration: `from dlux.utils import dlux_settings`; `dlux_settings(globals())`; mount `dlux.urls` at root for `/accounts/` and `/sys/`.
- DSRP-1 (`docs/security-dsrp-1.md`): backend authorization must match UI visibility; POST-only security mutators.
- Runtime UI uses one `dlux` prefix for authored CSS/data/events/JS globals; avoid inline runtime JS/CSS except approved JSON/dynamic-font bridges.
- User-facing copy routes through Dlux translations (`DLUX_STRINGS`) and must stay language/direction/theme aware.

### Adopted Standards' rules and policies:
- Maintain `tracker.md` as the brief live source of state, <=100 lines total, and update it after state/docs/tests changes.
- Changelog uses newest `## vX.Y.Z` sections and flat bold-title bullets; for this checkout, append to `## v1.1.0`.
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
  - [x] Fixed profile activity caps and single-session eviction: Recent Activity + System Interactions now show latest five each; `UserPresenceSession.session_key` folded into unreleased `0002` + `SessionStore.delete()` eviction supports cache/Redis-backed sessions; docs/changelog/tests updated.
  - [x] Fixed persisted notification language switching: serializers infer `DLUX_STRINGS` keys for legacy exact-match stored text, new fixed file/user/section notices emit `message_key`, and free-form/interpolated messages intentionally remain stored text; docs/changelog/tests updated.
  - [x] Fixed notification drawer bulk clear semantics: `/sys/api/notifications/clear-all/` and `clear_all_notifications()` now dismiss read visible states only, leaving unread drawer items untouched; labels/docs/changelog/tests updated.
  - [x] Fixed invalid profile password modal and keyed notification localization: invalid password-change POSTs reopen `#resetPasswordModal` without generic flash; `notify(..., message_key/title_key)` localizes flash/drawer/API payloads per request; docs/changelog/tests updated.
  - [x] Added no-op password-change rejection: shared `DluxPasswordMustChangeMixin` on profile password change + staff reset password rejects `new_password2` matching current hash, preserves stored hash and forced-change flag; EN/AR error string, docs/changelog/tests updated.
  - [x] Coordinated first-login forced password change with Initial User Setup: `DLUX_SHOW_INITIAL_USER_SETUP` is suppressed while `Profile.preferences["force_password_change"]` is active; `/accounts/welcome/` remains middleware-blocked until password change clears the flag; profile warning is persistent via `data-autoclose="false"`; docs/changelog/tests updated.
  - [x] Fixed shared `DluxChoiceSelectorWidget` toggle-card surfaces for dark-based themes: `selectors.css` now uses `--dlux-choice-toggle-surface*` variables backed by theme setup tokens; `base.html` selector CSS cache-buster bumped; focused regression added; changelog updated.
  - [x] ActivityLog redesign COMPLETE (plan `.claude/plans/set-up-the-robust-plan-twinkling-kettle.md`): Phases 1/2/5 (rename+category+`log_config`+gating) plus Phase 4 audit hooks (`log_audit_event` for login/lockout/2FA/password/session/trusted-device/permission, gated by `audit.events`), Phase 6 audit append-only `save()/delete()` + `dlux_prune_activity_log` (skips audit), Phase 5b `dlux.log_activity` dev helper, consumers (log-view user/system/audit tabs `?category=` gated to superuser/global-staff + admin `category`), and Phase 3 rolling-window User/Profile merge (fixes second-boundary double-log). 525 green.

### One-line info about last verified Tests:
- 2026-06-20: Migration cleanup folded `UserPresenceSession.session_key` into unreleased `0002_system_settings_configs_and_notifications.py`, removed `0003_user_presence_session_key.py`; `makemigrations --check --dry-run` and cache-backed session regression passed.
- 2026-06-19: Profile five-entry cap + cache-backed single-session eviction passed focused tests `ProfileViewsTests.test_user_profile_limits_activity_feeds_to_latest_five_each`, `ProfileSessionDeviceTests.test_standard_login_evicts_cache_backed_sessions_when_single_session_enabled`, full `ProfileViewsTests` + `ProfileSessionDeviceTests`, `makemigrations --check --dry-run`, and `django check`.
- 2026-06-19: Persisted notification language-switch fix passed `DJANGO_SETTINGS_MODULE=dlux.tests.settings ../dlux-test/.venv/bin/python -m django test dlux.tests.test_notifications --verbosity=1`, `python -m django check`, and scoped `git diff --check`.
- 2026-06-19: Notification clear-read semantics passed `DJANGO_SETTINGS_MODULE=dlux.tests.settings ../dlux-test/.venv/bin/python -m django test dlux.tests.test_notifications --verbosity=1`; scoped `git diff --check` passed.
- 2026-06-19: Password modal + keyed notification localization passed focused Django tests `ProfileViewsTests.test_user_profile_rejects_password_change_to_current_password`, `NotificationPipelineTests.test_keyed_notifications_render_in_request_language`, `DluxDefaultRouteTests.test_profile_confirmation_script_submits_password_modal_on_enter`, then widened `dlux.tests.test_notifications` + password/security focused tests; scoped `git diff --check` passed.
- 2026-06-19: No-op password rejection passed focused Django tests `ProfileViewsTests.test_user_profile_rejects_password_change_to_current_password`, `SecurityHardeningViewTests.test_forced_password_change_rejects_current_password_reuse`, and `SecurityHardeningViewTests.test_reset_password_rejects_current_password_reuse`; scoped `git diff --check` passed.
- 2026-06-19: Forced-password/onboarding coordination passed focused Django tests `ProfileConfigAndOnboardingTests.test_onboarding_is_deferred_until_forced_password_change_is_cleared` and `DluxDefaultRouteTests.test_profile_confirmation_script_submits_password_modal_on_enter`; scoped `git diff --check` passed.
- 2026-06-19: Selector dark-surface fix passed focused `DJANGO_SETTINGS_MODULE=dlux.tests.settings ../dlux-test/.venv/bin/python -m django test dlux.tests.test_defaults_and_urls.DluxDefaultRouteTests.test_selector_css_adds_vertical_padding_for_toggle_card_grids --verbosity=1` and scoped `git diff --check`; `pytest` unavailable in the venv.
- 2026-06-18: profile_config + Initial User Setup + `user_home_url` login wiring passed full `python dlux/tests/test_all.py` (532, +5: normalize/onboarding-save/skip/context-flag/login-redirect), `django check`, `makemigrations --check` (folded into `0002`), temp-`STATIC_ROOT` `collectstatic`, profile.html parse + conditional render smoke, settings step render (step=10), and `git diff --check`.

### One-line info about last time edited Docs:
- 2026-06-19: Updated `CHANGELOG.md` (v1.1.0), `docs/reference.md`, `docs/FEATURES.md`, and `docs/admin-guide.md` for profile feed cap and cache-backed single active-session eviction semantics.
- 2026-06-19: Updated `CHANGELOG.md` (v1.1.0), `docs/reference.md`, and `docs/FEATURES.md` for persisted notification language-switch behavior and exact-match legacy fallback.
- 2026-06-19: Updated `CHANGELOG.md` (v1.1.0), `docs/reference.md`, and `docs/FEATURES.md` for notification drawer clear-read semantics.
- 2026-06-19: Updated `CHANGELOG.md` (v1.1.0), `docs/reference.md`, and `docs/FEATURES.md` for password modal validation behavior and keyed notification localization.
- 2026-06-19: Updated `CHANGELOG.md` (v1.0.4), `docs/reference.md`, `docs/admin-guide.md`, and `docs/FEATURES.md` for password reuse rejection.
- 2026-06-19: Updated `CHANGELOG.md` (v1.0.4), `docs/reference.md`, and `docs/admin-guide.md` for forced-password/Initial User Setup ordering and persistent warning behavior.
- 2026-06-19: Updated `CHANGELOG.md` (v1.0.4) for the shared choice selector dark-theme surface fix; no feature/API docs changed.
- 2026-06-18: Updated `CHANGELOG.md` (v1.0.4) and `docs/reference.md` (new `profile_config` + Initial User Setup section, config-groups list) for the profile_config feature; `tracker.md` refreshed.

## Part 2: Global
### Global Standard Helpers, Shortcuts, Info, etc.:
- Prefer `rg`/`rg --files` for repository discovery.

### Global Rulesets:
- Keep tracker brief/grounded; changelog/docs updates happen in the same turn as meaningful changes.

### Agent Handoff Rules:
- Read `tracker.md` every turn; preserve user changes; use tag-driven release docs plus version metadata for changelog decisions.

### References and Links:
- Security: `docs/security-dsrp-1.md`; Release: `docs/RELEASING.md`; Concept report: `docs/conceptual-codebase-report.md`.
