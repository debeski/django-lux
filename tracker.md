# MicroSys Tracker

## Part 1: Project

### Current Verified Snapshot and current project overview:

- Verified on: `2026-04-11`
- Project: `django-microsys` framework package
- Current framework state:
  - `microsys_settings(globals())` in `microsys.utils` is now the supported low-friction settings integration path
  - `microsys_setup` now appends that helper block to the active project `settings.py`
  - `microsys_check` now validates both the resulting configuration state and the presence of the recommended helper wiring
  - `microsys/form_base.html` is the supported form-page entrypoint
  - `microsys/list_base.html` is the supported list/filter-page entrypoint
  - `microsys/forms/assets_head.html` and `microsys/forms/assets_scripts.html` remain the supported embedded-form asset includes
  - `microsys/forms/filter_assets_head.html` is the lightweight filter/list asset include for pages that cannot extend `microsys/list_base.html`
  - `setup_filter_helper()` and `advanced_filter_helper()` now emit Microsys filter classes so the shared modern field/button surface applies automatically on pages using the list base or filter asset include
  - the shared datepicker standard is now `vanillajs-datepicker`, with legacy `.flatpickr` compatibility preserved
  - the shared modern form surface lives under `microsys/static/microsys/forms/`
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

### Tasks:

- Priority 1:
  - [ ] Decide whether host projects should be encouraged to remove redundant manual Microsys settings once `microsys_settings(globals())` is adopted
  - [ ] Add explicit tests for `microsys_settings()` defaulting of `LANGUAGE_CODE`, `TIME_ZONE`, `USE_I18N`, `USE_TZ`, `FORMAT_MODULE_PATH`, and `DEFAULT_CHARSET`
  - [ ] Add explicit tests for `setup_filter_helper()` / `advanced_filter_helper()` class output so the new filter surface does not regress silently
  - [ ] Add explicit tests for `microsys/list_base.html` and `microsys/forms/filter_assets_head.html`
- Priority 2:
  - [ ] Decide whether a dedicated mixed `form_list_base.html` is worth adding for pages like `manage_sections`
  - [ ] Revisit the global Crispy file-field override story and either harden it or document its host-project dependency more prominently
  - [ ] Extend the docs with a migration example showing a host project moving from manual Microsys settings to `microsys_settings(globals())`
- Completed Recently:
  - [x] Add `microsys_settings(globals())` to `microsys.utils`
  - [x] Upgrade `microsys_setup` to append the helper block to the active project settings file
  - [x] Upgrade `microsys_check` to validate the helper wiring explicitly
  - [x] Add `microsys/list_base.html`
  - [x] Add `microsys/forms/filter_assets_head.html`
  - [x] Move shared filter/list styling onto the modern Microsys form surface
  - [x] Add dark-theme support for the shared modern form/filter surface

### Tests:

- Verified recently:
  - `docker compose exec -T web python manage.py check`
  - `docker compose exec -T web python manage.py microsys_check`
  - `docker compose exec -T web python manage.py microsys_setup --skip-configure --no-migrate --skip-check`
  - `docker compose exec -T web python manage.py shell -c "from microsys.utils import microsys_settings; scope={...}; microsys_settings(scope); print(...)"` to verify settings mutation behavior
  - `docker compose exec -T web python manage.py shell -c "import py_compile; py_compile.compile('/app/microsys/utils.py', cfile='/tmp/...', doraise=True); ...; print('compile-ok')"`
- Recommended next validation:
  - add package tests for the new helper and list base
  - visually confirm the modern filter surface in both light and dark modes on a real list page

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
