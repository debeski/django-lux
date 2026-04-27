# Project Tracker

## Part 1: Project
### Current Verified Snapshot and current project overview:
- Verified on: `2026-04-27`
- Project: `django-microsys`
- Current package version from codebase: `1.20.4b0` in `microsys/VERSION`
- Current verified state:
  - ScopedManager now enforces isolation between Central (NULL scope) and Private (Scoped) records:
    - Scoped users see only their own scope.
    - Non-scoped users see only NULL-scope records (the Centralized pool).
    - Superusers see everything.
  - MSRP hardening is in place for dynamic modal CRUD, section management, user/profile modals, activity-log access, reset-password flow, diagnostics exposure, and 2FA mutators.
  - Theme/sidebar/titlebar governance is live through `SystemSettings`, setup, runtime context, and preferences enforcement.
  - System setup has been reorganized into five steps: Identity, Localization, Access & Security, Navigation, and Appearance & Personalization.
  - `SystemSettings` now uses language-keyed `system_names`; the old `name` / `name_en` system-name fields are intentionally removed by migration `0007`.
  - Localization setup now uses an explicit language catalog plus a translation matrix. Discovered app translations can suggest/prefill languages, but do not auto-enable languages for users.
  - User-reported setup UI regressions from `2026-04-26` have code-level fixes: system names render in Identity, the old visual default-language picker is removed, Enter advances the multi-step setup wizard before final submit, and custom-language add/remove now keeps catalog, system-name rows, default language, and translation matrix columns synchronized.
  - Translation matrix UI now has source tabs for Microsys, installed app translation layers, project translations, and settings-only override keys.
  - System Settings can now be exported as a portable JSON setup file from Options and imported from step 1 of setup/System Settings. The export covers DB-backed operational setup fields; logo/favicon are stored as file names only, not embedded media content.
  - `get_system_config()` now exposes nested public groups: `identity`, `localization`, `security`, `navigation`, `appearance`, and `personalization`, while retaining flat non-name keys for existing internal behavior.
  - Runtime sidebar save->render is repaired and stale user sidebar trees now fall back to system sidebar.
  - Selector-widget, setup split-step flow, and Options split System Settings entrypoints are implemented.
  - Table platform is framework-owned through `microsys/tables/table.html`, `MicrosysTable`, and the `django_tables2` patch layer.
  - Full Django test suite is currently green: `253` tests passing.

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

### Standards' rules and policies:
- Keep Microsys defaults framework-neutral unless the default is explicitly part of the framework contract.
- Prefer additive helpers, templates, and extension points over project-rewriting commands.
- Do not use `settings.configure()` as a host-project installation path.
- Keep host-project-specific behavior out of Microsys defaults unless broadly reusable.
- Document supported integration surfaces in `README.md` plus `docs/reference.md` or `docs/customization-guide.md`.

### Cross-Cutting Audits if any:
- Security/MSRP audit:
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
- **Fixed**: Context menu in section manager was redirecting to `/${app}/${id}/` instead of showing the smart view modal. Added `isSectionManagerActive()` check to main.js fallback handlers to prevent navigation when on section manager pages.
- **Fixed**: Staff users not seeing manage users icon or getting 403 on `/sys/users/` because `user_can_view_user_directory()` required `auth.view_user` permission. Now it accepts either `auth.view_user` OR `microsys.manage_staff` permission. Forms still auto-grant `auth.view_user` for backward compatibility.
- **Fixed**: `view_activitylog` and `manage_scopes` permissions not appearing in permission widget. The queryset filter in `CustomUserCreationForm` and `CustomUserPermissionsForm` was only allowing `manage_staff` and section-related microsys permissions.
- **Fixed**: Sidebar permission inference for function-based views. Added URL pattern-based permission inference that extracts app label from namespace and model name from URL name (e.g., `documents:outgoing_list` → `documents.view_outgoing`). Simplified `_user_has_sidebar_permission` to strictly check permissions without staff fallback - users must have the actual permission to see the item. Added `__ms_options_view__` permission to `options_view` system route. Updated `_infer_permissions` to return `(permissions, permissions_explicit)` tuple. Updated `_resolve_sidebar_item` to preserve `permissions_explicit` from catalog. Updated tests to verify the new behavior.
- **Implemented**: New permission tier system separating Global Staff from Central Staff:
  - **Global Staff**: `is_staff=True, scope=NULL, manage_scopes permission` — Can create/manage scopes, assign users to any scope, view/edit ALL users. Only superusers can create Global Staff.
  - **Central Staff**: `is_staff=True, scope=NULL, NO manage_scopes permission` — Can only create/manage scopeless (NULL scope) users. Cannot view scoped users, manage scopes, or assign scopes. Can be created by Global Staff or other Central Staff with `manage_staff` permission.
  - **Server-side Enforcement**: Added view-level and form-level protection to prevent Central Staff from:
    - Seeing Global Staff users in the user list (`UserListView.get_queryset()` now excludes users with `manage_scopes` permission)
    - Editing Global Staff users (`edit_user` view blocks with error message)
    - Creating Global Staff users (`create_user` view strips `manage_scopes` from submission)
    - Assigning `manage_scopes` via permissions form (`CustomUserPermissionsForm.save()` strips the permission)
  - **Permission Assignment Principle**: Users can only assign permissions they themselves have. Non-superusers see only their own permissions in the widget.
  - **CRITICAL FIX**: Widget was using cached class-level queryset instead of filtered queryset. Fixed by storing `_filtered_queryset` on the widget and prioritizing it in `get_context()`. This prevents users from seeing/assigning permissions they don't have.
  - **CRITICAL FIX**: `_get_form_kwargs()` was passing `request` via `**kwargs` detection, causing `TypeError` in forms that don't accept `request`. The fallback then stripped ALL kwargs including `user`, breaking permission filtering completely. Fixed by only passing `request` when explicitly named as a parameter.
  - **CRITICAL SECURITY FIX**: Sidebar items with no permissions were visible to ALL users due to `user_has_any_permission_tokens` returning `True` for empty permissions. Fixed by adding `default_visible_to_all=False` parameter - now items MUST have explicit permissions to appear in sidebar. Superusers can see all sidebar items regardless of permissions.
  - **UI Fix**: Scope field now completely hidden from Central Staff (using `HiddenInput` widget) instead of showing disabled field with message. Cleaner UX and prevents any confusion.
- No currently verified critical authz/2FA/backdoor issue remains from the `2026-04-24` MSRP audit slice.
- Browser/manual validation is still pending for several UI-heavy flows:
  - setup and Options appearance/localization controls
  - language catalog add/remove behavior and translation-matrix filtering/editing after the latest code-level fix
  - live sidebar/titlebar behavior across light/dark themes
  - sidebar collapsed icon-only mode: density control and sections manager should vanish (code fix applied, needs browser verification)
  - sidebar expanded mode: toolbar icon accommodation when few sidebar items (code fix applied, needs browser verification)
  - POST-only 2FA flows in the browser
- Host projects that override `extra_head` without `{{ block.super }}` can still drop base asset includes.
- Crispy file-field override precedence still depends on host `INSTALLED_APPS` / template lookup order.
- SSO is not present in the live package; only an older sibling reference tree exists and should not be treated as live state.

### Tasks:
- Priority 1:
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
  - `python -m compileall microsys/models.py microsys/utils.py microsys/translations.py microsys/forms.py microsys/context_processors.py microsys/api.py`
  - focused Django slice for setup/config/localization/runtime context:
    - `UtilsTests`
    - `ContextProcessorsTests`
    - `MicrosysDefaultRouteTests`
    - result: `83` tests passed
  - full suite:
    - `./.venv/bin/python ... runner.run_tests(['microsys.tests'])`
    - result: `253` tests passed
  - focused setup/config/views slice after translation tabs and setup import/export:
    - `UtilsTests`
    - `MicrosysDefaultRouteTests`
    - `GeneralViewsTests`
    - result: `74` tests passed
  - focused regression slice for source tabs, import override, modal step 4, and export:
    - result: `6` tests passed
  - `python -m compileall microsys/translations.py microsys/forms.py microsys/utils.py microsys/views/general.py microsys/views/__init__.py microsys/views/sections.py microsys/urls.py microsys/tests/test_defaults_and_urls.py microsys/tests/test_utils.py microsys/tests/test_views.py`
  - `git diff --check -- README.md docs/admin-guide.md docs/customization-guide.md microsys/translations.py microsys/forms.py microsys/utils.py microsys/views/general.py microsys/views/__init__.py microsys/views/sections.py microsys/urls.py microsys/templates/microsys/base.html microsys/templates/microsys/includes/system_setup.html microsys/templates/microsys/includes/options.html microsys/templates/microsys/includes/translation_matrix_editor.html microsys/static/microsys/main/js/system_setup.js microsys/static/microsys/main/css/system_setup.css microsys/tests/test_defaults_and_urls.py microsys/tests/test_utils.py microsys/tests/test_views.py tracker.md`
    - passed with Git warning that `microsys/utils.py` CRLF will be replaced by LF when touched
  - `python -m compileall microsys/forms.py microsys/tests/test_defaults_and_urls.py`
  - focused Django setup/default-route slice after setup UI fix:
    - `MicrosysDefaultRouteTests`
    - result: `19` tests passed
  - final post-asset-bump checks:
    - `python -m compileall microsys/forms.py microsys/tests/test_defaults_and_urls.py`
    - `MicrosysDefaultRouteTests.test_setup_identity_step_renders_language_keyed_system_names`: `1` test passed
    - `git diff --check -- microsys/forms.py microsys/templates/microsys/base.html microsys/templates/microsys/includes/system_setup.html microsys/templates/microsys/includes/language_catalog_editor.html microsys/templates/microsys/includes/system_names_editor.html microsys/static/microsys/main/js/system_setup.js microsys/static/microsys/main/css/system_setup.css microsys/tests/test_defaults_and_urls.py tracker.md`
  - attempted JS parser check:
    - `node --check microsys/static/microsys/main/js/system_setup.js` could not run because `node` is not installed
    - Python `esprima` parser check could not run because `esprima` is not installed
  - `python -m compileall microsys/utils.py microsys/middleware.py microsys/views/profile.py microsys/context_processors.py microsys/discovery.py microsys/views/scopes.py microsys/tests/test_utils.py microsys/tests/test_context_processors.py microsys/tests/test_middleware.py microsys/tests/test_defaults_and_urls.py microsys/tests/test_sidebar_discovery.py microsys/tests/test_views.py microsys/tests/test_m2m.py`
  - `python -m compileall microsys/patches.py microsys/tests/test_utils_discovery.py microsys/tests/test_models.py microsys/tests/test_tables.py`
  - focused Django slice over stale utility/config/middleware/default-route fixes: `7` tests passed
  - focused Django slice over remaining table/model/discovery regressions: `9` tests passed
  - focused Django slice over generic auto-table + activity-log views after the table patch correction: `5` tests passed
  - broader stale-code + MSRP-adjacent slice:
    - `UtilsTests`
    - `ContextProcessorsTests`
    - `ActivityLogMiddlewareTests`
    - `MicrosysDefaultRouteTests`
    - `ScopeViewsTests`
    - `SecurityHardeningViewTests`
    - `ActivityLogViewsTests`
    - `SidebarDiscoveryTests`
    - result: `144` tests passed
- Recommended next validation:
  - browser validation for the UI-heavy setup, Options, language matrix, sidebar/titlebar, and 2FA flows
  - one live generated-project boot and one generated-app registration pass

### Docs:
- Primary live docs:
  - `README.md`
  - `docs/reference.md`
  - `docs/customization-guide.md`
  - `docs/admin-guide.md`
  - `CHANGELOG.md`
- Key contracts to keep documented:
  - MSRP authorization and 2FA contracts
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
