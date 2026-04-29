# Project Tracker

## Part 1: Project
### Current Verified Snapshot and current project overview:
- Verified on: `2026-04-29`
- Project: `django-microsys`
- Current package version from codebase: `2.0.3` in `microsys/VERSION`
- last migration file: `0001_initial.py`
- Current verified state:
  - Core framework areas: scoped data isolation, MSRP authorization hardening, managed table rendering, setup/System Settings, runtime sidebar/titlebar controls, and Options entrypoints are implemented in code.
  - `SystemSettings` uses language-keyed `system_names`; `get_system_config()` exposes nested public groups (`identity`, `localization`, `security`, `navigation`, `appearance`, `personalization`) plus compatibility keys.
  - Options sidebar visibility now matches direct `/sys/options/` access through `__ms_authenticated__`.
  - TOTP provisioning uses configured system identity display name / neutral fallback, not the old project-specific `FineStor` issuer.
  - Last known full-suite status before later focused fixes: `253` tests passing. More recent broad run is blocked by the tracked `view_activitylog` permission test drift.
  - Browser/manual validation remains pending for UI-heavy setup, Options, sidebar/titlebar, and 2FA flows.

### Current Project Official Standards:
- Preferred settings integration:
  - `from microsys.utils import microsys_settings`
  - `microsys_settings(globals())`
- Preferred scaffolding:
  - `python -m microsys startproject <project_name> [destination]`
  - `python -m microsys startapp <app_name> [--register]`
- Preferred page entrypoints:
  - `microsys/form_base.html`
  - `microsys/list_base.html`
- Preferred filter helpers:
  - `setup_filter_helper()`
  - `advanced_filter_helper()`
- Preferred table base:
  - `microsys.tables.MicrosysTable`
- Preferred extension hooks:
  - `microsys/includes/custom_head.html`
  - `microsys/includes/custom_scripts.html`
- Preferred system-name config:
  - `MICROSYS_CONFIG["system_names"] = {"en": "...", "ar": "..."}`
- Preferred runtime config groups for new code:
  - `APP_CONFIG.identity`
  - `APP_CONFIG.localization`
  - `APP_CONFIG.security`
  - `APP_CONFIG.navigation`
  - `APP_CONFIG.appearance`
  - `APP_CONFIG.personalization`
- Security:
  - MSRP-1 "Microsys Secure Runtime Policy":
    - The project authorization standard for runtime-exposed surfaces.
    - Covers direct URL access, sidebar discovery/rendering, dashboard/user-hub shortcuts, modal CRUD, context actions, diagnostics, and state-changing security flows.
    - UI visibility is never the only control; every protected behavior must have matching backend authorization.

### Standards' rules and policies:
- Keep Microsys defaults framework-neutral unless the default is explicitly part of the framework contract.
- Prefer additive helpers, templates, and extension points over project-rewriting commands.
- Do not use `settings.configure()` as a host-project installation path.
- Keep host-project-specific behavior out of Microsys defaults unless broadly reusable.
- Document supported integration surfaces in `README.md` plus `docs/reference.md` or `docs/customization-guide.md`.
- MSRP-1 is the active authorization policy: direct routes, sidebar/catalog visibility, dashboard/user-hub links, modal/context actions, diagnostics, and 2FA mutators must agree on who can access the behavior.
- Prefer helper-backed permission checks and internal tokens resolved by `user_matches_permission_token()`; do not add ad hoc `is_staff` gates unless staff-only access is the explicit contract.
- Any generated or scaffolded entrypoint exposed by URL registration must enforce login plus the relevant model/system permission on the backend, not only through sidebar hiding.

### Cross-Cutting Audits if any:
- Security/MSRP-1 audit:
  - backend permission enforcement now exists for modal CRUD, sections, user detail/modals, activity log, and reset-password flow
  - 2FA state mutators are POST-only and backup codes are hashed at rest
  - Options diagnostics are privileged-only
- Table platform audit:
  - Microsys-managed tables now respect `Meta.microsys_table`, `Meta.microsys_density`, `Meta.microsys_per_page`, `Meta.microsys_per_page_options`, and `Meta.microsys_actions`
  - stock/no-template host tables are auto-captured into the Microsys renderer
- Setup/Options audit:
  - theme allowlist, language lock, sidebar runtime controls, and titlebar controls are wired through setup and split Options modals
  - setup/System Settings localization now has an explicit add-language catalog and translation matrix; custom languages remain unavailable until explicitly added

### Current Project's Known Bugs:
- **Verified bug/test drift**: Proper Django test runner currently fails `8` activity-log view tests because `ActivityLogViewsTests.setUp()` looks for `view_activitylog` on the `UserActivityLog` content type, while the live model/migration define that permission on `Profile`.
- **Verified bug**: Scaffolded app CRUD views in `microsys/scaffold_templates/app/views.py.tmpl` do not use login or model-permission mixins, while `startapp --register` exposes the generated app URLs.
- **Verified code smell**: `microsys/context_processors.py` still has a private `_user_has_sidebar_permission()` helper that runtime sidebar rendering does not use.
- **Manual validation pending**: UI-heavy setup, Options, language matrix, sidebar/titlebar, and POST-only 2FA flows still need browser checks.
- **Integration caveats**: host templates overriding `extra_head` without `{{ block.super }}` can drop base assets; crispy file-field override precedence depends on host app/template ordering.

### Tasks:
- Priority 1:
  - [ ] Resolve `view_activitylog` permission ownership/test drift:
    - Decide whether the permission belongs to `UserActivityLog`, `Profile`, or a dedicated proxy/dummy permission model.
    - Align model metadata/migrations/tests/forms with that decision.
    - Re-run the proper Django test runner.
  - [ ] Harden scaffolded app CRUD templates:
    - Add login and model-permission enforcement to generated list/detail/create/update/delete views.
    - Ensure generated tests cover direct URL access, not only sidebar visibility.
  - [ ] Remove or reconcile the stale `_user_has_sidebar_permission()` helper in `microsys/context_processors.py`.
  - [ ] Browser-check POST-only 2FA flows: setup, verify, resend, disable, and backup-code usage.
  - [ ] Browser-check setup/System Settings appearance governance:
    - language catalog add/remove and default-language behavior after the `2026-04-26` UI wiring fix
    - translation matrix search/filter/edit behavior
    - allowed themes matrix
    - language lock behavior
    - sidebar density/collapse/icon controls
    - titlebar visibility/alignment/shape/surface controls
  - [ ] Browser-check live runtime shell behavior:
    - sidebar save -> runtime render
    - sidebar toolbar auto-hide/disable logic
    - desktop collapse modes `icons`, `hidden`, `locked_expanded`
    - titlebar `show_title` / `show_logo` / `show_home_button`
  - [ ] Browser-check Options layout and selector widgets after the latest cleanup.
- Priority 2:
  - [ ] Run one end-to-end generated-project validation for `python -m microsys startproject`.
  - [ ] Run one end-to-end generated-app validation for `python -m microsys startapp --register`.
  - [ ] Validate generated Docker/Celery/health-check baseline in a live boot.
  - [ ] Revisit SSO only as a fresh implementation against the current package, not the older sibling branch.
- Completed Recently:
  - [x] Fixed Options sidebar authorization contract with `__ms_authenticated__` and removed live fake Options-token references from code/docs/tests
  - [x] Added sidebar discovery coverage proving `options_view` uses `__ms_authenticated__` and renders for a normal authenticated stub user
  - [x] Normalized `docs/FEATURES.md` version header/footer to current package version `2.0.3`
  - [x] Replaced hard-coded TOTP issuer `FineStor` with configured system identity display name / neutral fallback in `microsys/views/twofa.py`
  - [x] Added regression coverage that `/sys/2fa/setup/totp/` passes the configured display name as the TOTP issuer
  - [x] Implemented Global Staff vs Central Staff tier system with `manage_scopes` permission
  - [x] Fixed section manager context menu view/edit/delete handlers by adding `isSectionManagerActive()` check to main.js fallbacks
  - [x] Fixed staff users getting 403 on `/sys/users/` — `user_can_view_user_directory()` now accepts `manage_staff` permission
  - [x] Updated CHANGELOG.md with v1.87.0b4 release notes
  - [x] Updated docs/admin-guide.md with staff tier documentation
  - [x] Updated docs/reference.md with new helper functions and authorization contracts
  - [x] Updated README.md to mention three-tier staff authorization
  - [x] Enhanced `filter_context_actions()` to properly support `manage_sections` permission for all section-related actions
  - [x] Sidebar toolbar popovers now mutually exclusive: opening density popup closes theme popup, opening theme popup closes density popup.
  - [x] Sidebar collapsed icon-only: density control and sections manager link now hide (like reorder), only theme selector remains.
  - [x] Sidebar expanded: toolbar uses `width: 100%; min-width: max-content; flex-shrink: 0` so sidebar accommodates toolbar icon width instead of squishing them; added `gap: 6px` to toolbar for breathing room.
  - [x] Reorganized setup/System Settings into five conceptual steps.
  - [x] Replaced `SystemSettings.name` / `name_en` with `SystemSettings.system_names` and added migration `0007_systemsettings_system_names`.
  - [x] Added explicit language-catalog editing and translation-matrix editing backed by `languages` and `translations_override`.
  - [x] Added nested public config groups and moved title/base rendering to `identity.display_name`.
  - [x] Fixed setup UI regressions found by user testing:
    - Identity step now shows language-keyed system-name inputs.
    - Localization no longer renders both the old default-language picker and the new default radios.
    - Enter advances the full setup wizard instead of submitting before the last step.
    - Adding/removing a custom language updates the catalog, hidden JSON fields, Identity system-name rows, and translation matrix columns.
    - Setup static asset versions were bumped so browsers fetch the corrected setup JS/CSS.
  - [x] Added source tabs to the translation matrix so keys are grouped by Microsys, app, project, or settings-only override source.
  - [x] Added System Settings setup export/import:
    - Export link in the Options System Settings card.
    - Superuser-only `system_settings_export` endpoint.
    - Import file control in setup/System Settings step 1.
    - Server-side import handling plus browser-side prefill wiring.
  - [x] Finished MSRP backend hardening for modal CRUD, sections, activity log, user detail/modals, reset-password flow, diagnostics exposure, and 2FA mutators.
  - [x] Repaired stale-code drift in config/middleware/test paths around uploaded branding URLs, root/setup redirects, lazy model-class aliases, and thread-local middleware expectations.
  - [x] Fixed table patch drift so host tables again honor `Meta`-level Microsys controls for opt-out, density, page size, and row-action wiring.
  - [x] Removed the remaining full-suite failures in `test_utils_discovery`, `test_models`, and `test_tables`.
  - [x] Verified the full Django suite at `253` passing tests.

### Tests:
- Verified checks actually run:
  - `git diff --check -- tracker.md`
    - result: passed after tracker trimming
  - `./.venv/bin/python -m unittest microsys.tests.test_sidebar_discovery`
    - result: `13` tests passed after the Options `__ms_authenticated__` fix
  - `./.venv/bin/python -c "from microsys.tests import test_views; from django.test.runner import DiscoverRunner; runner = DiscoverRunner(verbosity=1); failures = runner.run_tests(['microsys.tests.test_views.GeneralViewsTests']); raise SystemExit(bool(failures))"`
    - result: `12` tests passed after the Options sidebar/direct-access contract fix
  - `./.venv/bin/python -c "import pathlib; files=['microsys/discovery.py','microsys/utils.py','microsys/tests/test_sidebar_discovery.py']; [compile(pathlib.Path(f).read_text(encoding='utf-8'), f, 'exec') for f in files]; print('syntax ok')"`
    - result: syntax ok
  - `rg -n "__ms_authenticated__" microsys docs README.md CHANGELOG.md tracker.md`
    - result: `__ms_authenticated__` is used for Options route docs/tests/runtime
  - search for the old fake Options-token literal across `microsys`, `docs`, `README.md`, and `CHANGELOG.md`
    - result: no matches
  - `rg -n "1\.20\.4b0|2\.0\.0|2\.0\.1|2\.0\.3|Version:|reflects package version" docs/FEATURES.md docs README.md tracker.md microsys/VERSION CHANGELOG.md`
    - result: `docs/FEATURES.md` now has header/footer `2.0.3`; remaining `2.0.0`/`2.0.1` hits are changelog headings only
  - `./.venv/bin/python -c "from microsys.tests import test_views; from django.test.runner import DiscoverRunner; runner = DiscoverRunner(verbosity=1); failures = runner.run_tests(['microsys.tests.test_views.TwoFactorSecurityViewTests']); raise SystemExit(bool(failures))"`
    - result: `6` tests passed
  - `./.venv/bin/python -c "import pathlib; files=['microsys/views/twofa.py','microsys/tests/test_views.py']; [compile(pathlib.Path(f).read_text(encoding='utf-8'), f, 'exec') for f in files]; print('syntax ok')"`
    - result: syntax ok
  - `./.venv/bin/python -c "from microsys.tests import test_views; from django.test.runner import DiscoverRunner; runner = DiscoverRunner(verbosity=1); failures = runner.run_tests(['microsys.tests']); raise SystemExit(bool(failures))"`
    - result: `255` tests run, `8` errors
    - all errors are `Permission.DoesNotExist` for `view_activitylog` on `UserActivityLog` content type in `ActivityLogViewsTests.setUp()`
  - full suite:
    - `./.venv/bin/python ... runner.run_tests(['microsys.tests'])`
    - result: `253` tests passed
    - historical result before later activity-log test drift was introduced/observed
- Recommended next validation:
  - fix `view_activitylog` ownership/test drift, then rerun the proper Django full suite
  - browser validation for the UI-heavy setup, Options, language matrix, sidebar/titlebar, and 2FA flows
  - one live generated-project boot and one generated-app registration pass

### Docs:
- Primary live docs:
  - `README.md`
  - `CHANGELOG.md`
  - `docs/README.md`
  - `docs/FEATURES.md`
  - `docs/reference.md`
  - `docs/getting-started.md`
  - `docs/admin-guide.md`
  - `docs/customization-guide.md`
  - `docs/developer-guide.md`
- Key contracts to keep documented:
  - MSRP-1 authorization and 2FA contracts
  - `SystemSettings.allowed_themes`
  - `SystemSettings.allow_user_theme_override`
  - `SystemSettings.allow_user_language_override`
  - `SystemSettings.system_names`
  - `SystemSettings.languages` explicit language catalog behavior
  - `SystemSettings.translations_override` as the matrix-backed runtime override layer
  - System Settings export/import JSON format: `django-microsys.system-settings`
  - `SystemSettings.titlebar_config`
  - sidebar runtime config keys: `show_icons`, `density`, `allow_user_density`, `collapse_mode`
  - `microsys.widgets.MicrosysChoiceSelectorWidget`
  - `microsys.widgets.MicrosysMultipleChoiceSelectorWidget`
  - `microsys.tables.MicrosysTable`
  - `microsys_settings(globals())`

## Part 2: Global
### Global Standard Helpers, Shortcuts, Info, etc.:
- Fast file search:
  - `rg`
  - `rg --files`
- Preferred verification order:
  - focused failing slice first
  - broader slice second
  - full suite last
- In this workspace, `tracker.md` is required working memory and must be reread each turn.

### Global Ruleset:
- Keep tracker entries grounded in verified code, verified runtime behavior, or explicit user instruction.
- Use `apply_patch` for manual file edits.
- Do not revert unrelated dirty worktree changes.
- Prefer updating stale tests when framework contracts have intentionally moved, but fix product code first when behavior is actually wrong.

### Agent Handoff Rules:
- Re-read `tracker.md` at the start of every turn.
- Update tracker after meaningful code, verification, or contract changes.
- Keep the tracker short and current; remove stale historical detail instead of appending endlessly.
- When browser/manual validation is still pending, state that explicitly instead of implying full runtime verification.

### Links To Possibly Helpful Tools and Projects if any:
- Cross-reference trackers:
  - `/home/debeski/depy/tools/DNgine/tracker.md`
  - `/home/debeski/depy/projects/archive/tracker.md`
- Older SSO reference only:
  - `/home/debeski/depy/projects/microsys-pkg(SSO)/microsys`

### References:
- Key project files:
  - `microsys/utils.py`
  - `microsys/patches.py`
  - `microsys/models.py`
  - `microsys/context_processors.py`
  - `microsys/views/sections.py`
  - `microsys/views/users.py`
  - `microsys/views/twofa.py`
  - `microsys/templates/microsys/tables/table.html`



TODO by DeBeski: "DO NOT TOUCH"

the sidebar-toolbar removal warning only works in modal view "from options view", doesnt work in initial setup view tho.

generated table of scaffolded app's context menu doesnt work for some mysterious reason even tho microsys table should be handling it automatically.
