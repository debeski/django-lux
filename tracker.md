# MicroSys Tracker

## Part 1: Project

### Current Verified Snapshot and current project overview:

- Verified on: `2026-04-16`
- Project: `django-microsys` framework package
- Current framework state:
  - `microsys_settings(globals())` in `microsys.utils` is the supported low-friction settings integration path
  - `microsys_setup` appends that helper block to the active project `settings.py`
  - `microsys_check` validates both the resulting configuration state and the presence of the recommended helper wiring
  - `microsys/form_base.html` is the supported form-page entrypoint
  - `microsys/list_base.html` is the supported list/filter-page entrypoint
  - `microsys/forms/assets_head.html` and `microsys/forms/assets_scripts.html` remain the supported embedded-form asset includes
  - `microsys/forms/filter_assets_head.html` is the lightweight filter/list asset include for pages that cannot extend `microsys/list_base.html`
  - `setup_filter_helper()` and `advanced_filter_helper()` emit Microsys filter classes so the shared modern field/button surface applies automatically on pages using the list base or filter asset include
  - the shared datepicker standard is `vanillajs-datepicker`, with legacy `.flatpickr` compatibility preserved
  - the shared modern form surface lives under `microsys/static/microsys/forms/`
  - theme handling now runs through `microsys/themes.py`, with the official discovered order `light`, `blue`, `gold`, `green`, `red`, `mono`, `dark`, `gothic`, `retro`, `neon`
  - setup, options, base template CSS inclusion, runtime validation, and the sidebar toolbar picker all read from that shared theme registry path
  - setup step 3 persists sidebar runtime flags for `enable_reorder` and `show_toolbar`, and disabling the toolbar shows the Dynamic Sections Manager access warning
  - the shared sidebar now uses a flat edge-to-edge rail layout with unified geometry, a non-arrow folder marker, explicit root/child active treatments, collapsed-mode icon centering, and a flush sidebar-width theme picker popup
  - the sidebar theme indicator updates when theme changes come from Options via the shared `microsys:theme-changed` event
  - `mono`, `gothic`, `retro`, and `neon` now carry framework-level conformance overrides for shared surfaces such as user hub, profile, activity log, tutorial popovers, dashboard/module cards, toolbar controls, options pickers, and system-settings badges
- Important framework caveat:
  - the framework `templates/bootstrap5/layout/field_file.html` override exists, but whether it beats `crispy_bootstrap5` still depends on template lookup / `INSTALLED_APPS` order in the host project

### Current Project Official Standards:

- Preferred settings integration:
  - `from microsys.utils import microsys_settings`
  - `microsys_settings(globals())`
- Preferred page entrypoints:
  - full-page forms: `microsys/form_base.html`
  - list/filter pages: `microsys/list_base.html`
  - mixed pages: extend one base and include the other asset include explicitly when needed
- Preferred datepicker:
  - `vanillajs-datepicker` via `.ms-datepicker`
- Preferred filter surface:
  - `setup_filter_helper()` for basic list filters
  - `advanced_filter_helper()` for multi-row advanced filters and action rows
- Preferred extension hooks:
  - `microsys/includes/custom_head.html`
  - `microsys/includes/custom_scripts.html`

### Standards' rules and policies:

- Keep Microsys defaults framework-neutral unless the default is intentionally part of the framework standard
- Prefer additive helpers and template entrypoints over management commands that rewrite arbitrary project structure
- Do not use `settings.configure()` as a host-project installation mechanism
- Prefer supported base templates and asset includes over telling host projects to manually duplicate CSS/JS imports
- Keep host-project-specific behavior out of Microsys helper defaults unless it is broadly reusable
- Document every new supported integration surface in README plus docs/reference or docs/customization

### Cross-Cutting Audits if any:

- Settings integration audit:
  - helper path now exists and is the preferred pattern
  - command layer now points at the helper path instead of pretending to be a full installer
- Form/filter surface audit:
  - form base exists
  - list base now exists
  - dark-mode support for the shared modern surface is now partially framework-owned
- Template override audit:
  - Crispy precedence still depends on host project app order and should not be assumed blindly

### Current Project's Known Bugs:

- `microsys_check` can only validate the helper block if it can read the active `settings.py`; exotic settings-loading patterns may reduce that signal
- host projects that override `extra_head` without `{{ block.super }}` can accidentally drop base-provided asset includes
- automatic framework takeover of Crispy file fields is still not guaranteed unless template resolution order favors Microsys over `crispy_bootstrap5`
- the latest theme/surface/sidebar CSS refinements are verified statically and through Django checks, but still need manual browser confirmation across the newer dark themes and the updated sidebar picker/runtime combinations
- ~~Email 2FA option not appearing in deployments~~ — **Fixed in v1.19.4** (`get_2fa_config()` now reads explicit `email_2fa` flag from system config)
- ~~Anonymous users receiving 404 on root URL instead of redirect to login~~ — **Fixed in v1.19.4b4** (removed `is_authenticated` check from `_should_redirect_missing_root()` in `middleware.py`)

### Tasks:

- Priority 1:
  - [ ] Decide whether host projects should be encouraged to remove redundant manual Microsys settings once `microsys_settings(globals())` is adopted
  - [ ] Add explicit tests for `microsys_settings()` defaulting of `LANGUAGE_CODE`, `TIME_ZONE`, `USE_I18N`, `USE_TZ`, `FORMAT_MODULE_PATH`, and `DEFAULT_CHARSET`
  - [ ] Add explicit tests for `setup_filter_helper()` / `advanced_filter_helper()` class output so the new filter surface does not regress silently
  - [ ] Add explicit tests for `microsys/list_base.html` and `microsys/forms/filter_assets_head.html`
  - [ ] Add explicit tests for the shared theme registry helpers and the official discovered theme ordering
  - [ ] Add explicit tests for setup/runtime handling of `sidebar.enable_reorder` and `sidebar.show_toolbar`
- Priority 2:
  - [ ] Decide whether a dedicated mixed `form_list_base.html` is worth adding for pages like `manage_sections`
  - [ ] Revisit the global Crispy file-field override story and either harden it or document its host-project dependency more prominently
  - [ ] Extend the docs with a migration example showing a host project moving from manual Microsys settings to `microsys_settings(globals())`
  - [ ] Manually verify `mono`, `gothic`, `retro`, and `neon` across sidebar rail states, options selectors, toolbar controls, and framework-owned cards/popovers
- Completed Recently:
  - [x] Add `microsys_settings(globals())` to `microsys.utils`
  - [x] Upgrade `microsys_setup` to append the helper block to the active project settings file
  - [x] Upgrade `microsys_check` to validate the helper wiring explicitly
  - [x] Add `microsys/list_base.html`
  - [x] Add `microsys/forms/filter_assets_head.html`
  - [x] Move shared filter/list styling onto the modern Microsys form surface
  - [x] Add dark-theme support for the shared modern form/filter surface
  - [x] Unify theme registration, preview metadata, and CSS inclusion through `microsys/themes.py`
  - [x] Add `mono`, `gothic`, `retro`, and `neon` runtime/theme-picker support to the official framework theme flow
  - [x] Add sidebar runtime controls for reorder and toolbar visibility in setup and runtime config handling
  - [x] Rework the shared sidebar into a flatter rail with better active states, compact picker docking, collapsed icon handling, and live theme-indicator sync
  - [x] Document the `1.19.1` theme/sidebar/runtime polish batch across changelog and docs
  - [x] Fix email 2FA: replace `os.getenv('EMAIL_HOST')` with explicit `email_2fa` config flag (v1.19.4b0)
  - [x] Add `email_2fa` BooleanField to SystemSettings model + migration `0002`
  - [x] Add `email_2fa` toggle to SystemSettingsForm (Step 1)
  - [x] Wire `email_2fa` through `get_system_config()` default + DB read + MICROSYS_CONFIG seed
  - [x] Add `auto_create_user_scope` toggle to ScopeSettings for per-user automatic scope creation (v1.19.4b1)
  - [x] Fix transaction handling and error reporting for auto_create_user_scope (v1.19.4b2)
  - [x] Restore missing users views module lost due to gitignore `users/` folder pattern (v1.19.4b3)
  - [x] Fix anonymous root redirect (removed `is_authenticated` check from middleware) (v1.19.4b4)

- SSO / OIDC:
  - [x] Phase 1: Core OIDC Provider via `django-oauth-toolkit` — `microsys/sso/` sub-package
  - [x] Phase 2: SSO Admin Card + Modal for client app management
  - [x] Phase 3: Connected Devices UI in Profile for Token Revocation
  - [x] Phase 4: Separate `django-microsys-sso-client` package

### Tests:

- Verified recently:
  - `docker compose exec -T web python manage.py check`
  - `docker compose exec -T web python manage.py microsys_check`
  - `docker compose exec -T web python manage.py microsys_setup --skip-configure --no-migrate --skip-check`
  - `docker compose exec -T web python manage.py shell -c "from microsys.utils import microsys_settings; scope={...}; microsys_settings(scope); print(...)"` to verify settings mutation behavior
  - `docker compose exec -T web python manage.py shell -c "import py_compile; py_compile.compile('/app/microsys/utils.py', cfile='/tmp/...', doraise=True); ...; print('compile-ok')"`
  - `python -m compileall /home/debeski/depy/projects/microsys-pkg/microsys/themes.py /home/debeski/depy/projects/microsys-pkg/microsys/forms.py /home/debeski/depy/projects/microsys-pkg/microsys/context_processors.py /home/debeski/depy/projects/microsys-pkg/microsys/utils.py`
  - `docker compose exec -T web python manage.py shell -c "from microsys.themes import get_theme_names; print(get_theme_names())"`
  - `docker compose exec -T web python manage.py test microsys.tests.test_context_processors.ContextProcessorsTests.test_microsys_context_theme_options microsys.tests.test_defaults_and_urls.MicrosysDefaultRouteTests.test_setup_form_surfaces_neon_and_sidebar_behavior_flags microsys.tests.test_utils.UtilsTests.test_get_system_config_rejects_unknown_default_theme`
  - `python -m py_compile` passed for `models.py`, `views/twofa.py`, `utils.py`, `forms.py`, `migrations/0002_systemsettings_email_2fa.py` (email 2FA fix)
- Recommended next validation:
  - Deploy updated microsys to finestor compose and confirm email 2FA toggle appears in system settings
  - Enable email_2fa toggle, verify email 2FA option appears in profile page
  - Send test OTP email to confirm email delivery works
  - add package tests for the new helper and list base
  - visually confirm the modern filter surface in both light and dark modes on a real list page
  - visually confirm the latest dark-theme and sidebar-runtime refinements in the browser

### Docs:

- Primary references:
  - `README.md`
  - `docs/README.md`
  - `docs/customization-guide.md`
  - `docs/reference.md`
  - `CHANGELOG.md`
- Current key integration surfaces to keep documented:
  - `microsys_settings(globals())`
  - `microsys/form_base.html`
  - `microsys/list_base.html`
  - `microsys/forms/assets_head.html`
  - `microsys/forms/assets_scripts.html`
  - `microsys/forms/filter_assets_head.html`
  - `microsys/themes.py`
  - sidebar config keys `enable_reorder` and `show_toolbar`
  - options-page `.theme-preview` and sidebar `.theme-option-circle` theme-picking surfaces
  - `email_2fa` config flag (via `MICROSYS_CONFIG` or System Settings UI)

## Part 2: Global

### Global Standard Helpers, Shortcuts, Info, etc.:

- `microsys_settings(globals())`
- `get_system_config()`
- `get_strings()`
- `get_current_language_code()`
- `lazy_translator()`
- `get_model_classes()`
- `resolve_form_class_for_model()`
- `discover_section_models()`
- `setup_filter_helper()`
- `advanced_filter_helper()`
- `set_field_attrs()`
- `translate_choices()`
- `log_user_action()`
- `fetch_file()`
- `fetch_excel()`

### Global Ruleset:

- Prefer framework-owned entrypoints over project-specific copy-paste integrations
- Prefer documented helper paths over clever but implicit runtime magic
- Keep defaults safe and additive
- Keep docs and changelog in sync with new supported surfaces

### Agent Handoff Rules:

- Read this tracker before changing Microsys integration behavior
- Re-validate the live command behavior after changing `microsys_setup` or `microsys_check`
- Re-check host-project implications when changing shared templates, helper defaults, or template override precedence
- Update README, customization docs, reference docs, and changelog for any new supported integration surface

### Links To Possibly Helpful Tools and Projects if any:

- Archive host project: `/home/debeski/depy/projects/archive`
- DNgine tracker reference: `/home/debeski/depy/tools/DNgine/tracker.md`

### References:

- `README.md`
- `docs/getting-started.md`
- `docs/customization-guide.md`
- `docs/reference.md`
- `CHANGELOG.md`
