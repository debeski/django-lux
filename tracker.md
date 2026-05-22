# Project Tracker (django-microsys)

## Part 1: Project Related
### Current Verified Snapshot:
- Verified through `2026-05-22`: local package version markers are on `v2.2.3` and current edits remain focused on runtime bug-fix batches.
- System setup/System Settings uses a six-step wizard. Step 2 owns language catalog, system names, default language, language override policy, and the translation matrix. Step 6 owns themes, fonts, and table density.
- Dynamic Font Management is active:
  - font registry lives in `microsys/fonts.py`,
  - `SystemSettings` stores `allowed_fonts`, language-keyed `default_fonts`, and `allow_user_font_override`,
  - Options uses the shared selector markup and `--ms-main-font`.
- Runtime theme allowlisting remains enforced by context and the preferences API. `2026-05-22` setup preview work adds a setup-only path that can load a disabled theme stylesheet for preview without widening runtime preference acceptance.
- Explicit `setTheme(...)` changes now run through a short veil fade around the class swap; reduced-motion and Microsys `no-animations` skip the fade, and sidebar item/icon transitions pause under that veil so they resolve with the same swap.
- System Settings single-step modal POSTs preserve omitted Step 6 values server-side. Step resolver accepts modal wizard steps `0..5`.
- Current translation contract from code, docs, and `dhub` runtime inspection:
  - app-local sources are installed app `translations.py` modules exposing `MS_TRANSLATIONS`,
  - Step 2 matrix is meant to group Microsys, installed app, project-config, and settings-only override keys,
  - `dhub-web-1` currently pins installed `django-microsys==2.2.2`; it discovers `portfolio` and `documents` app translation sources but reproduces a Microsys-only matrix because merged app keys mutate the core source layer before grouping.

### Current Project Adopted Standards:
- Preferred settings integration:
  - `from microsys.utils import microsys_settings`
  - `microsys_settings(globals())`
- Preferred scaffolding:
  - `python -m microsys startproject <project_name> [destination]`
  - `python -m microsys startapp <app_name> [--register]`
- Preferred page entrypoints:
  - `microsys/form_base.html`
  - `microsys/list_base.html`
- Preferred helper APIs:
  - `require_current_password(request)`
  - `build_archive_file_field('<field_name>')`
  - `build_settings_toggle_field(form, '<field_name>', css_class='...')`
  - `set_profile_totp_state(profile, raw_secret=..., enabled=...)`
- Active standards:
  - MSRP-1 is the runtime authorization standard; source is `docs/security-msrp-1.md`.
  - Optional SSO is additive-only under `optional_packages/`.
  - Public registration is core, additive, and email-gated.

### Adopted Standards' rules and policies:
- Backend authorization must match protected UI visibility; hidden controls are not authorization.
- Keep Microsys defaults framework-neutral unless behavior is an explicit framework contract.
- Prefer additive helpers, templates, and extension points over project-rewriting behavior.
- Do not use `settings.configure()` as a host-project installation path.
- Do not rely on app-order template shadowing for critical behavior when an explicit helper or template path exists.
- For setup/System Settings:
  - use `build_archive_file_field(...)` for Microsys archive/file widgets,
  - use `build_settings_toggle_field(...)` for shared toggle-card booleans,
  - mirror UI gating in backend validation/normalization.
- Do not add inline CSS or executable inline JS to templates unless unavoidable; prefer static assets, `json_script`, and `data-*`.
- All new or revised user-facing copy must use Microsys translations, not local English/Arabic literals or new template `|default:"..."` fallbacks.
- Generated/scaffolded URL entrypoints must enforce login and the relevant permission on the backend.
- Published distributions should exclude `microsys.tests`, Python caches, and compiled Python artifacts unless a release explicitly needs them.

### Cross-Cutting Audits if any:
- Prior verified audits cover CSP-oriented template cleanup, setup toggle consistency, permissions UI filtering, modal JSON error tolerance, staff-tier surface restoration, and packaged-distribution exclusions.
- Browser/manual audit coverage is still incomplete for mounted-app setup flows, Options selector behavior, sidebar/titlebar runtime behavior, and POST-only 2FA flows.

### Current Project's Unsolved Known Bugs:
- Live confirmation is pending after the `2026-05-22` Step 2 matrix source fix. The `dhub` container reproduced a Microsys-only matrix with discovered `portfolio` and `documents` sources under installed Microsys `2.2.2`; local merge isolation now keeps app keys out of the core source claim path.
- Live confirmation is pending after the `2026-05-22` Options font asset cache-bust. Local `options.js` already marks a clicked `[data-font]` selector `is-active` immediately; the reported missing highlight is production-only.
- Live confirmation is pending after the `2026-05-22` setup-only disabled-theme preview path for Step 6.
- Live confirmation is pending for the `2026-05-22` sidebar-item theme-switch follow-up; the veil fade was accepted, but sidebar item transitions still looked choppy until they were paused under the veil.
- First-launch System Setup has a runtime mismatch between the sidebar-toolbar removal warning and Options modal behavior.
- Live Options -> System Settings Step 3 modal save has returned HTTP 400 in the user's mounted app while local full modal POST reproductions return 200; use AJAX JSON error/class or live server logs next.
- Browser/runtime confirmation remains pending in the mounted app after the Step 2 relay/env readiness fix.
- `microsys/fetcher.py` fallback download/export redirects still trust raw `HTTP_REFERER`.
- User-reported runtime backlog not handled in the current batch:
  - Options System Info server time shows only date, hour, and minutes,
  - Options cards cannot be reordered in neon theme,
  - Step 4 collapsed Icons Only sidebar pushes parent/folder accordion icons out of bounds,
  - re-enabling a previously disabled sidebar drops child toggle state and can force Hide Completely collapse mode,
  - shared toggle cursor should be pointer,
  - Options card reorder handle should use drag cursor,
  - Profile confirm-password modal should submit on Enter,
  - some session/2FA activity entries still render under Recent Activity instead of System Interactions.

### Incomplete Tasks:
- Tasks:
  - Priority 1:
    - [ ] Re-check Step 2 app source tabs after the fixed local code/package reaches `dhub`.
    - [ ] Browser-check the `2026-05-22` Options font highlight and Step 6 disabled-theme preview fixes in production/mounted app.
    - [ ] Browser-check sidebar item repaint after pausing sidebar transitions under the accepted theme-switch fade.
    - [ ] Browser-check reduced-motion/no-animation bypass for the theme switch fade.
    - [ ] Harden `microsys/fetcher.py` fallback redirects for missing, local, and forged external referers.
    - [ ] Capture the live Step 3 System Settings modal HTTP 400 JSON/log details if it still reproduces.
  - Priority 1 browser validation:
    - [ ] Setup/System Settings wizard navigation, language catalog, translation matrix, allowed themes/fonts, sidebar, titlebar, and email readiness.
    - [ ] Options card order persistence, System Info placement, autofill/reset, selector widgets, and theme persistence.
    - [ ] Pre-setup mounted-project guard for anonymous, superuser, and non-superuser requests.
    - [ ] POST-only 2FA setup, verify, resend, disable, backup-code, and trusted-device/session UX.
    - [ ] Staff-tier create/edit/profile/detail/manage-table surfaces and user-hub mobile toolbar wrap.
  - Priority 2:
    - [ ] Run generated-project validation for `python -m microsys startproject`.
    - [ ] Run generated-app validation for `python -m microsys startapp --register`.
    - [ ] Validate generated Docker/Celery/health-check baseline in a live boot.
    - [ ] Validate optional provider/client OIDC after installing their dependencies.
    - [ ] Keep unrelated nested settings/import-export/password/force-2FA refactor as a separate planned batch.
  - Completed Recently:
    - [x] Added setup-only preview support for a Step 6 theme that was disabled when the page loaded.
    - [x] Smoothed explicit theme changes with a short switch veil fade instead of broad element transitions.
    - [x] Paused sidebar item/icon transition repaint while the theme-switch veil is active after the user isolated remaining choppiness to sidebar items.
    - [x] Bumped the production `options.js` asset key for the existing immediate Options font `is-active` update path.
    - [x] Reproduced the Step 2 matrix source collapse in `dhub` and isolated app translation merges from `MICROSYS_STRINGS` so app source tabs remain claimable.
    - [x] Fixed Step 2 relay/env email readiness detection for scaffolded `SMTP_RELAY_*` plus `DEFAULT_FROM_EMAIL`.
    - [x] Preserved omitted Step 6 values on single-step System Settings modal saves and fixed modal step `5` resolution.

### One-line info about last verified Tests:
- `2026-05-22`: focused `DiscoverRunner` checks passed for theme-switch fade/reduced-motion/sidebar-transition coverage, setup theme preview/cache-bust coverage, and translation matrix layer/source-group tests; focused compileall passed for edited Python test/form/translation files. Initial focused runner invocation without importing test settings failed before Django setup and was rerun correctly.

### One-line info about last time edited Docs:
- `2026-05-16`: main README/docs batch covered Trusted Devices, Client IP Resolution, advanced 2FA UX, Dynamic Font Management, and the Step 5/6 wizard split; no docs changed on `2026-05-22`.

## Part 2: Global
### Global Standard Helpers, Shortcuts, Info, etc.:
- Reusable helper APIs:
  - `require_current_password(request)`
  - `build_archive_file_field('<field_name>')`
  - `build_settings_toggle_field(form, '<field_name>', css_class='...')`
  - `set_profile_totp_state(profile, raw_secret=..., enabled=...)`
- Common validation commands:
  - Focused defaults/render suite: `./.venv/bin/python -c "import microsys.tests.test_defaults_and_urls; import django; from django.test.runner import DiscoverRunner; django.setup(); raise SystemExit(bool(DiscoverRunner(verbosity=1).run_tests(['microsys.tests.test_defaults_and_urls'])))"`
  - Focused modal/view suites: import target test modules before `django.setup()`, then run targeted labels through `DiscoverRunner`.
  - Full compile check without repo pycache churn: `PYTHONPYCACHEPREFIX=/tmp/microsys-pycache ./.venv/bin/python -m compileall microsys`
  - Packaging check: build wheel/sdist, then inspect for `microsys/tests`, `__pycache__`, `.pyc`, and `.pyo`.
- Known environment note: `node` is not available locally, so `node --check` is not a current JS validation path.

### Global Rulesets:
- Prefer explicit reusable helpers over template shadowing or duplicated inline HTML.
- When a UI issue differs between modal/runtime/setup surfaces, verify the actual load/bind/runtime path before adding sync code.
- Keep tracker entries grounded in verified code, verified runtime behavior, or explicit user instruction.
- Do not convert user complaints into fixed tracker notes until the real runtime path is verified.
- Leave unrelated worktree changes untouched.
- For translation bugs, check the app-local `translations.py` contract and translation discovery layer before adding hardcoded copy.
- When implementing a big change, identify three real-life break scenarios and provide fixes/workarounds.

### Agent Handoff Rules:
- Re-read this tracker at the start of every turn and update it after meaningful state, task, bug, test, docs, or handoff changes.
- User correction: their target app mounts this repo, so do not assume they are running only the packaged PyPI release when local checkout is active.
- `dhub-web-1` inspected on `2026-05-22` uses the image-installed package, not a repo bind mount; `/app/req.txt` pins `django-microsys==2.2.2` even though this checkout version markers are `2.2.3`.
- User correction for current runtime bug batch: stay on the bug-fix path, keep impact minimal, and ask or research when evidence is insufficient.
- User correction for theme animation: the veil fade is desired; remaining theme-switch choppiness was observed only in sidebar items.
- If setup default-language preview refreshes direction but not server-rendered text, inspect `microsys/static/microsys/main/js/system_setup.js` and `microsys/static/microsys/language/js/main.js`; reload preview must persist form state without restoring stale wizard step.
- If first-launch later steps look empty, inspect shared wizard `d-none` handling before changing form markup.
- If shared setup toggle layout regresses, inspect `build_settings_toggle_field(...)` plus `system_setup.css` before replacing the renderer.
- Keep Step 3 email TLS/SSL on the dedicated email-toggle path unless intentionally retired and browser-verified.
- If permission group noise returns, inspect `get_assignable_permissions_queryset()` and `GroupedPermissionWidget.get_context()` before changing templates.
- Preserve explicit user corrections in future tracker updates.

### References and Links:
- Key project files:
  - `microsys/forms.py`
  - `microsys/translations.py`
  - `microsys/utils.py`
  - `microsys/context_processors.py`
  - `microsys/static/microsys/main/js/system_setup.js`
  - `microsys/static/microsys/themes/js/main.js`
  - `microsys/templates/microsys/base.html`
  - `microsys/tests/test_defaults_and_urls.py`
- Translation docs currently state the app-source matrix contract:
  - `docs/admin-guide.md`
  - `docs/customization-guide.md`
- Optional SSO references:
  - `optional_packages/django-microsys-sso/microsys_sso`
  - `optional_packages/django-microsys-sso-client/microsys_sso_client`
