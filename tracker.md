# Project Tracker

## Part 1: Project

### Current Verified Snapshot and current project overview:

- Verified on: `2026-04-16`
- Project: `django-microsys` framework package
- Current framework state:
  - `microsys_settings(globals())` in `microsys.utils` is the supported low-friction settings integration path
  - `python -m microsys startproject` is the preferred greenfield MicroSys project scaffold entrypoint
  - `python -m microsys startapp` is the preferred MicroSys app scaffold entrypoint, with optional `--register` project patching
  - the `ms` console script still exists as a short alias, but docs should prefer `python -m microsys ...`
  - `python -m microsys startproject` generates the inner Django config package as `config/` instead of reusing the outer project name
  - generated project Python files now start with a triple-quoted header showing `django-microsys` version, project name, and generation date, excluding `__init__.py`
  - generated README files now prefer the module-form scaffold commands: `python -m microsys startproject` and `python -m microsys startapp`
  - generated projects now include root-level `.gitattributes`, `.gitignore`, `start.sh`, and `start.ps1`, with `start.sh` marked executable
  - generated `start.ps1` now maps Windows project paths into `/host_mnt/<drive>/...` inside the decrypter container so Docker Desktop can both accept the in-container working directory and resolve relative Compose bind mounts from a daemon-visible Linux path
  - scaffold file generation now forces LF newlines, fixing Windows-generated `entrypoint.sh` and `start.sh` files that previously broke Linux container startup with misleading `/app/entrypoint.sh: no such file or directory` errors
  - generated projects now also include a root Docker baseline: `.dockerignore`, `Dockerfile`, `compose.yml`, `compose.dev.yml`, `.nginx/nginx.conf`, `entrypoint.sh`, `gunicorn.py`, and `req.txt`
  - generated projects now include `.secrets/.env` with only the bootstrap secret values used by the decrypter/startup flow: `DJANGO_SECRET_KEY`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `PGADMIN_DEFAULT_EMAIL`, `PGADMIN_DEFAULT_PASSWORD`, and `ADMIN_PASS`
  - generated projects now include `config/celery.py`, export `celery_app` from `config/__init__.py`, enable `django-health-check`, and wire a `/health/` route plus a `celery` compose service
  - generated projects now also include `django-cors-headers` and `django-csp` in the scaffold baseline, with `corsheaders` / `csp` apps, their middleware, baseline `CORS_*` settings, and a default `CONTENT_SECURITY_POLICY`
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
- Preferred scaffolding:
  - `python -m microsys startproject <project_name> [destination]`
  - `python -m microsys startapp <app_name> [--register]`
  - console-script alias still exists: `ms startproject <project_name> [destination]`
  - console-script alias still exists: `ms startapp <app_name> [--register]`
  - generated project layout: outer project folder plus inner `config/` package for `settings.py`, `urls.py`, `asgi.py`, and `wsgi.py`
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
  - canonical helper now owns `LocaleMiddleware`, `MESSAGE_TAGS`, i18n/tz, format-module, charset, and activity middleware defaults
- Form/filter surface audit:
  - form base exists
  - list base now exists
  - dark-mode support for the shared modern surface is now partially framework-owned
- Scaffold surface audit:
  - project and app scaffolds now exist under `python -m microsys ...`, with `ms` kept only as a short alias
  - app registration patching is marker-based and idempotent on rerun
  - generated projects now standardize on `config.settings` in `manage.py` and the ASGI/WSGI modules
  - generated project-file headers are data-driven from package version and current date, not hardcoded text
  - generated root shell assets now include the decrypter launcher pattern used by `../min_survey/start.sh`; no source `start.ps1` existed there, so the PowerShell file is an equivalent companion implementation
  - generated PowerShell launcher now translates `C:\...` host paths into `/host_mnt/<drive>/...` for `docker run -w`, because helper-container-only paths such as `/workspace` break downstream Compose bind mounts on Windows
  - generated scaffold files must use LF on all platforms because `.gitattributes` does not help files created directly by the scaffold before they are committed or checked out through git
  - generated Docker assets are based on `../min_survey` but normalized to the scaffolded project name and `config.wsgi`
  - generated Docker assets now follow the `../min_survey` two-file compose pattern more closely: `compose.yml` plus `compose.dev.yml`, official `nginx:latest` with mounted `./.nginx/nginx.conf`, and a non-account-specific default web image tag via `WEB_IMAGE`
  - generated project settings now seed `health_check` / `health_check.db` and default Celery Redis settings, with task autodiscovery driven by generated `config/celery.py`
  - generated project settings use env-driven Postgres, Redis cache, and Django secret loading via `get_secret()`
  - user corrected the scaffold rule: `.secrets/.env` must stay a six-key bootstrap secret file only, and `compose.yml` must keep the existing inline `environment:` pattern instead of importing `.secrets/.env` directly
  - generated project settings template no longer includes inert CORS settings without `django-cors-headers`, and production HSTS now sets `SECURE_HSTS_SECONDS` alongside `SECURE_HSTS_INCLUDE_SUBDOMAINS`
  - generated project settings now parse `BASE_URL` hostname for `SESSION_COOKIE_DOMAIN` / `CSRF_COOKIE_DOMAIN` instead of string-stripping the full URL
  - scaffold `req.txt` now includes `django-cors-headers` so projects that re-enable `CORS_*` settings have the dependency available
  - scaffold `req.txt` now includes `django-csp`, and the project settings use the django-csp 4.x dictionary-based `CONTENT_SECURITY_POLICY` format
- Template override audit:
  - Crispy precedence still depends on host project app order and should not be assumed blindly

### Current Project's Known Bugs:

- `microsys_check` can only validate the helper block if it can read the active `settings.py`; exotic settings-loading patterns may reduce that signal
- the new `microsys startproject` / `microsys startapp` scaffolds are verified by file-generation tests and syntax checks, but still need a full end-to-end run inside a Django environment with dependencies installed
- generated Docker dev flow is now structurally aligned with `../min_survey`, but still needs one end-to-end validation with the decrypter wrapper using `./start.sh -d`
- generated Celery and health-check scaffold wiring is verified by file-generation tests, but still needs one live compose boot to confirm worker startup and `/health/` readiness behavior
- generated `.secrets/.env` plus restored compose pattern is verified by scaffold tests, but still needs one live run through the decrypter/startup flow
- ~~Root URL always redirects anonymous users to login~~ — **Fixed** (added `public_root` config flag and `LOGIN_REDIRECT_URL` detection to allow host projects to have public root pages)
- host projects that override `extra_head` without `{{ block.super }}` can accidentally drop base-provided asset includes
- automatic framework takeover of Crispy file fields is still not guaranteed unless template resolution order favors Microsys over `crispy_bootstrap5`
- the latest theme/surface/sidebar CSS refinements are verified statically and through Django checks, but still need manual browser confirmation across the newer dark themes and the updated sidebar picker/runtime combinations
- ~~Email 2FA option not appearing in deployments~~ — **Fixed in v1.19.4** (`get_2fa_config()` now reads explicit `email_2fa` flag from system config)
- ~~Anonymous users receiving 404 on root URL instead of redirect to login~~ — **Fixed in v1.19.4b4** (removed `is_authenticated` check from `_should_redirect_missing_root()` in `middleware.py`)

### Tasks:

- Priority 1:
  - [ ] Run an end-to-end validation of `python -m microsys startproject` inside a real Django environment and confirm the generated project boots cleanly
  - [ ] Run an end-to-end validation of `python -m microsys startapp --register` inside a generated project and confirm the generated app imports, migrates, and loads its starter routes
  - [ ] Add explicit tests for `setup_filter_helper()` / `advanced_filter_helper()` class output so the new filter surface does not regress silently
  - [ ] Add explicit tests for `microsys/list_base.html` and `microsys/forms/filter_assets_head.html`
  - [ ] Add explicit tests for the shared theme registry helpers and the official discovered theme ordering
  - [ ] Add explicit tests for setup/runtime handling of `sidebar.enable_reorder` and `sidebar.show_toolbar`
- Priority 2:
  - [ ] Decide whether a dedicated mixed `form_list_base.html` is worth adding for pages like `manage_sections`
  - [ ] Revisit the global Crispy file-field override story and either harden it or document its host-project dependency more prominently
  - [ ] Extend the docs with a migration example showing a host project moving from manual Microsys settings to `microsys_settings(globals())`
  - [ ] Consider whether `python -m microsys startapp` should also generate starter templates for dynamic modal or sections-first flows
  - [ ] Manually verify `mono`, `gothic`, `retro`, and `neon` across sidebar rail states, options selectors, toolbar controls, and framework-owned cards/popovers
- Completed Recently:
  - [x] Add generated Docker baseline files `.dockerignore`, `Dockerfile`, `compose.yml`, `entrypoint.sh`, `gunicorn.py`, and `req.txt` to `python -m microsys startproject`
  - [x] Remove generated `micro.txt`; scaffolded projects now pin `django-microsys==<generated version>` directly in `req.txt` and rely on package dependency resolution for framework extras
  - [x] Add generated `.secrets/.env` with only the six bootstrap secret values and keep compose on the pre-existing inline env pattern
  - [x] Add generated `compose.dev.yml` and `.nginx/nginx.conf`, switch nginx to official image + mounted config, and remove the Debeski-owned default web image requirement from the project scaffold
  - [x] Add scaffolded Celery baseline: `config/celery.py`, `celery` compose service, Celery settings defaults, and `django-health-check` `/health/` routing
  - [x] Add generated root `.gitattributes`, updated `.gitignore`, and decrypter launcher scripts `start.sh` / `start.ps1` to `python -m microsys startproject`
  - [x] Update generated scaffold README files to prefer `python -m microsys ...` commands instead of `ms ...`
  - [x] Add generation headers to scaffolded project Python files with package version, project name, and date
  - [x] Change `python -m microsys startproject` to generate `config/` as the inner Django package instead of duplicating the outer project name
  - [x] Add `microsys.__main__` so `python -m microsys ...` works as a fallback CLI entrypoint
  - [x] Fix duplicate trailing `microsys_settings()` override so the richer helper is the only live implementation
  - [x] Add helper defaults for `LocaleMiddleware` ordering and `MESSAGE_TAGS[messages.ERROR] = "danger"`
  - [x] Add `get_secret(secret_name, env_var)` helper
  - [x] Add `ms` CLI entrypoint as a short alias to the module command
  - [x] Add `python -m microsys startproject` MicroSys-ready project scaffold
  - [x] Add `python -m microsys startapp` MicroSys-native app scaffold with starter model/forms/filters/tables/views/templates/tests
  - [x] Add optional `python -m microsys startapp --register` settings and URL patching
  - [x] Add repo-side scaffold tests and helper tests for the new defaults
  - [x] Update docs for `python -m microsys startproject`, `python -m microsys startapp`, `--register`, and the finalized helper defaults
  - [x] Add `public_root` config flag to allow anonymous access to root URL
  - [x] Add `public_root` BooleanField to SystemSettings model + migration `0002`
  - [x] Add `public_root` checkbox to SystemSettingsForm
  - [x] Update middleware to respect `public_root` and detect host `LOGIN_REDIRECT_URL` override
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
  - added a new `v1.20.2` changelog entry documenting the Windows Docker Desktop path-translation fix, Compose bind-mount compatibility fix, and LF newline safeguard for generated shell files
  - corrected `CHANGELOG.md` so `v1.20.1` is a separate patch entry for the Windows scaffold fixes, with the larger scaffold/settings release restored under `v1.20.0`
  - `python -m microsys.tests.test_scaffold` after forcing LF newlines in generated scaffold files and asserting `entrypoint.sh` / `start.sh` contain no CRLF bytes
  - `python -m py_compile /home/debeski/depy/projects/microsys-pkg/microsys/scaffold.py` after the Windows newline fix
  - `python -m microsys.tests.test_scaffold` after updating `start.ps1` to translate Windows project paths into `/host_mnt/<drive>/...` for Docker Desktop compatibility
  - bumped package version from `1.20.0` to `1.20.1` in `microsys/VERSION` and aligned the top changelog release heading
  - updated `CHANGELOG.md` release heading from `Unreleased` to `v1.20.0` and replaced stale `ms startproject` / `ms startapp` wording there with `microsys startproject` / `microsys startapp`
  - reverted the temporary scaffold-local `get_secret()` workaround after deciding to publish the package update instead of carrying the compatibility shim in generated settings
  - updated `README.md`, `docs/getting-started.md`, `docs/reference.md`, and `CHANGELOG.md` to reflect the current scaffold baseline: `.secrets/.env`, `config/celery.py`, `/health/`, and bundled `django-cors-headers` / `django-csp`
  - `python -m microsys.tests.test_scaffold` after adding `corsheaders` / `csp` apps, middleware, dependencies, and baseline CORS/CSP settings to the scaffold
  - `python -m py_compile /home/debeski/depy/projects/microsys-pkg/microsys/scaffold_templates/project/package/settings.py.tmpl` after adding baseline CORS/CSP support
  - reviewed CORS setting names against `django-cors-headers` project docs and updated scaffold `req.txt` accordingly
  - `python -m py_compile /home/debeski/depy/projects/microsys-pkg/microsys/scaffold_templates/project/package/settings.py.tmpl` after switching cookie-domain handling to parsed hostname
  - `python -m py_compile /home/debeski/depy/projects/microsys-pkg/microsys/scaffold_templates/project/package/settings.py.tmpl` after removing inert CORS settings and adding `SECURE_HSTS_SECONDS`
  - `python -m microsys.tests.test_scaffold` after restoring the compose pattern and shrinking generated `.secrets/.env` back to the six bootstrap keys
  - `python -m compileall /home/debeski/depy/projects/microsys-pkg/microsys/scaffold.py /home/debeski/depy/projects/microsys-pkg/microsys/tests/test_scaffold.py`
  - `python -m microsys.tests.test_scaffold` after adding scaffolded Celery and health-check defaults
  - `python -m compileall /home/debeski/depy/projects/microsys-pkg/microsys/scaffold.py /home/debeski/depy/projects/microsys-pkg/microsys/tests/test_scaffold.py`
  - `python -m microsys.tests.test_scaffold` after aligning generated compose files with the `min_survey` dev override pattern and mounted nginx config
  - `python -m compileall /home/debeski/depy/projects/microsys-pkg/microsys/scaffold.py /home/debeski/depy/projects/microsys-pkg/microsys/tests/test_scaffold.py`
  - `python -m microsys.tests.test_scaffold` after adding generated Docker baseline files
  - `python -m microsys.tests.test_scaffold` after adding generated root dotfiles and start scripts
  - `python -m microsys.tests.test_scaffold` after adding generated project-file headers
  - `python -m compileall /home/debeski/depy/projects/microsys-pkg/microsys/scaffold.py /home/debeski/depy/projects/microsys-pkg/microsys/tests/test_scaffold.py`
  - `python -m microsys.tests.test_scaffold` after switching generated projects to `config/`
  - `python -m compileall /home/debeski/depy/projects/microsys-pkg/microsys/cli.py /home/debeski/depy/projects/microsys-pkg/microsys/scaffold.py /home/debeski/depy/projects/microsys-pkg/microsys/tests/test_scaffold.py /home/debeski/depy/projects/microsys-pkg/microsys/utils.py`
  - `python -m microsys.tests.test_scaffold`
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
  - run `python -m microsys startproject` in a fresh directory inside a real Django environment and boot the generated project
  - run `docker compose -f compose.yml -f compose.dev.yml up` in a generated scaffold and confirm `web`, `celery`, and `/health/` all become healthy
  - confirm the generated `.secrets/.env` works correctly with the decrypter/startup flow without importing it directly in compose
  - run `python -m microsys startapp --register` in that generated project and confirm the app imports, migrates, and its starter URLs render
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
  - `python -m microsys startproject`
  - `python -m microsys startapp`
  - `python -m microsys startapp --register`
  - generated `config/celery.py`
  - generated `/health/` route via `django-health-check`
  - generated `.secrets/.env`
  - scaffolded `corsheaders` / `csp` baseline and `CONTENT_SECURITY_POLICY`
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
  - `public_root` config flag (via `MICROSYS_CONFIG` or System Settings UI) to allow anonymous root access

## Part 2: Global

### Global Standard Helpers, Shortcuts, Info, etc.:

- `microsys_settings(globals())`
- `get_secret(secret_name, env_var)`
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
- Prefer the `python -m microsys` scaffold flow over starting from raw Django defaults when building new MicroSys projects or apps; treat `ms` as a convenience alias only
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
