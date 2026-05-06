# Project Tracker (django-microsys)

## Part 1: Project Related
### Current Verified Snapshot:
- Verified on `2026-05-07`.
- Package/version state:
  - `microsys/VERSION` is `2.1.1`.
  - `CHANGELOG.md` now contains the stable `v2.1.1` patch release entry above the `v2.1.0` release and beta history.
  - Built distributions now exclude `microsys.tests`, `__pycache__`, and compiled Python cache artifacts from both `wheel` and `sdist`.
- Current verified implementation state:
  - Public registration playground exists in core, is disabled by default, and uses email-first inactive users plus hashed verification tokens.
  - Generated Docker projects use the internal `smtp-relay` sidecar path for UI-managed relay delivery when `SystemSettings.email_config.transport == "relay"`.
  - Login 2FA uses one challenge input for authenticator codes, requested email OTPs, and backup codes; TOTP secrets are encrypted at rest and OTP actions are throttled.
  - Profile TOTP setup now uses the stable `pyotp.TOTP(...)` path, falls back to username if email is blank, persists TOTP state through `set_profile_totp_state(...)` instead of the full `Profile.save()` path, and returns sanitized JSON on provisioning/QR generation or secret-persistence failures instead of raw 500 HTML errors.
  - Destructive profile security actions require current password in both UI and backend via `require_current_password(request)`.
  - System Settings/setup file fields use the Microsys custom archive widget through `build_archive_file_field(...)`.
  - System Settings/setup boolean cards use the shared toggle renderer `build_settings_toggle_field(form, field_name, ...)` across steps `2` to `5`.
  - Step 2 `allow_user_language_override` is full-width and separated from the translation matrix filters.
  - `registration_activation_mode` and `registration_throttle_enabled` are hidden/disabled until `public_registration_enabled` is enabled.
  - Step 3 and Step 4 boolean-card rows now use explicit row gutters/margins so stacked toggle rows have vertical separation instead of only horizontal spacing.
  - Step 3 `public_registration_enabled` now takes a full row; its dependent controls render on the following row as the hidden/gated pair.
  - Step 5 titlebar toggle-card row now uses the same `g-3 mb-3` row spacing pattern as the neighboring setup rows, so the gap before the first selection-widget row matches the gap between the selection-widget rows.
  - Shared setup/settings toggle cards now have dedicated content/control sub-elements and container-query reflow rules in `microsys/static/microsys/main/css/system_setup.css`.
    - Narrow toggle cards stack the switch below the label/help instead of pushing the switch outside the card boundary.
    - This directly covers tight cards such as `Provider STARTTLS` and `Provider SSL`.
  - Shared selector toggle-card grids now have vertical padding in `microsys/static/microsys/main/css/selectors.css`, and the selectors asset version was bumped for browser pickup.
  - Options now use shared external assets in `microsys/static/microsys/main/css/options.css` and `microsys/static/microsys/main/js/options.js`.
    - Autofill and reset-defaults are standalone cards again, using the shared Options card surface instead of nested cards inside one wrapper.
    - All Options cards now expose drag handles and persist user-defined card order in local storage.
    - System Info keeps the double-card span while sharing the same card language.
  - User hub mobile toolbar now wraps within one toolbar row when there is enough width, instead of being forced into separate stacked rows by mobile CSS.
  - Template/rendered-HTML asset policy cleanup is now enforced in code:
    - no inline `<style>` blocks remain under `microsys/templates/`
    - no executable inline `<script>` blocks remain under `microsys/templates/`
    - no inline `style=` attributes remain in templates, `microsys/forms.py`, or `microsys/widgets.py`
    - theme preview swatches now use shared slug-based CSS classes instead of inline background styles
  - Sidebar/titlebar runtime controls, split-step Options System Settings modals, scope-aware generated CRUD scaffolds, and MSRP-1 authorization hardening are implemented in code.
- Current verified caveats:
- Browser/manual validation is still pending for several UI-heavy flows.
  - First-launch System Setup still has an unresolved runtime mismatch for the sidebar-toolbar warning, while the Options modal path works.

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
- Preferred helper APIs already adopted in current code:
  - Current-password protection: `require_current_password(request)`
  - Shared crispy file field: `build_archive_file_field('<field_name>')`
  - Shared setup/settings toggle card: `build_settings_toggle_field(form, '<field_name>', css_class='...')`
  - Direct TOTP persistence helper: `set_profile_totp_state(profile, raw_secret=..., enabled=...)`
- Active framework standards:
  - MSRP-1 is the active runtime authorization standard.
  - Standard source: `docs/security-msrp-1.md`
  - Optional SSO is additive-only and lives under `optional_packages/`.
  - Public registration is core, additive, and email-gated.

### Adopted Standards' rules and policies:
- Backend authorization must always match any protected UI visibility; hiding links/buttons is never the only control.
- Keep Microsys defaults framework-neutral unless the behavior is an explicit framework contract.
- Prefer additive helpers, templates, and extension points over project-rewriting behavior.
- Do not use `settings.configure()` as a host-project installation path.
- Do not rely on app-order template shadowing for critical behavior when an explicit helper or explicit template path can be used.
- For System Settings/setup:
  - use `build_archive_file_field(...)` for Microsys custom file widgets,
  - use `build_settings_toggle_field(...)` for shared toggle-card booleans,
  - keep UI gating mirrored in backend validation/normalization.
- No HTML should carry inline CSS or executable inline JS unless there is a real unavoidable runtime requirement:
  - do not use inline `<style>` blocks in templates,
  - do not use executable inline `<script>` blocks in templates,
  - do not emit inline `style=` attributes from templates or Python HTML helpers when a class, static asset, `json_script`, or `data-*` bridge can be used instead.
- Generated/scaffolded URL entrypoints must enforce login plus the relevant permission on the backend.
- Packaged PyPI distributions should exclude repository test packages and Python cache artifacts unless a release explicitly needs them.

### Cross-Cutting Audits if any:
- Security/MSRP-1 audit:
  - backend permission enforcement exists for modal CRUD, sections, diagnostics, activity log, reset-password flow, and 2FA mutators.
  - profile destructive security actions now share the reusable current-password backend guard.
  - no inline CSS/JS in HTML unless there is a real unavoidable runtime reason. always CSP complied.
- Public registration/mail audit:
  - registration is disabled by default and 404s while disabled.
  - email readiness gates public registration and email 2FA.
  - exports redact SMTP secrets; encrypted DB storage is supported for UI-managed secrets.
- Setup/Options audit:
  - setup and split-step Options modals share the same main System Settings helpers for boolean toggle cards and custom file widgets.
  - public-registration-dependent controls and email-delivery controls are visibility-gated in setup JS and preserved across imported payloads.
- Optional SSO audit:
  - provider/client code remains isolated in `optional_packages/`; no core runtime coupling is intended.

### Current Project's Unsolved Known Bugs:
- First-launch System Setup still has an unresolved runtime issue where the sidebar-toolbar removal warning does not match the Options modal behavior.
- Browser/manual validation is still pending for:
  - setup/System Settings wizard behavior,
  - sidebar/titlebar runtime behavior,
  - Options selector widgets and theme persistence,
  - POST-only 2FA flows,
  - profile security/session UX.

### Incomplete Tasks:
- Priority 1:
  - [ ] Reproduce and fix the first-launch System Setup sidebar-toolbar warning mismatch against the working Options modal path.
  - [ ] Browser-check the refreshed Options page behavior:
    - [ ] card drag ordering and persistence
    - [ ] System Info double-width placement after card reordering
    - [ ] autofill toggle and reset-defaults card behavior after the external JS move
  - [ ] Browser-check the externalized template asset cleanup across affected pages:
    - [ ] login theme bootstrap
    - [ ] dashboard chart render
    - [ ] tutorial string bootstrap
    - [ ] profile image widget preview
    - [ ] activity log detail modal loader
    - [ ] manage users detail/reset/delete modal actions
    - [ ] sidebar preload and theme preview swatches
  - [ ] Browser-check the user hub mobile toolbar wrap behavior on smaller screens.
  - [ ] Browser-check POST-only 2FA flows:
    - [ ] setup
    - [ ] verify
    - [ ] resend
    - [ ] disable
    - [ ] backup-code usage
  - [ ] Browser-check setup/System Settings appearance and shell behavior:
    - [ ] language catalog add/remove and default-language behavior
    - [ ] translation matrix search/filter/edit behavior
    - [ ] allowed themes matrix
    - [ ] language lock behavior
    - [ ] sidebar density/collapse/icon controls
    - [ ] sidebar enabled/disabled runtime layout
    - [ ] titlebar visibility/alignment/shape/surface controls
    - [ ] email delivery UI gating and readiness alerts
  - [ ] Browser-check account/security UI modernization:
    - [ ] public signup provenance badge
    - [ ] unified login 2FA challenge UX
    - [ ] profile 2FA loading/email confirmation flow
    - [ ] signed-in device list and revocation UX
    - [ ] light/dark/mono/neon/gothic/retro contrast for secondary buttons
  - [ ] Review translation coverage for UI labels/messages that were called out by the user and are not yet re-verified in browser/runtime:
    - [ ] signed-in devices card
    - [ ] 2FA enable button in profile
    - [ ] general setup/options labels and descriptions
- Priority 2:
  - [ ] Run one end-to-end generated-project validation for `python -m microsys startproject`.
  - [ ] Run one end-to-end generated-app validation for `python -m microsys startapp --register`.
  - [ ] Validate generated Docker/Celery/health-check baseline in a live boot.
  - [ ] Run full provider OIDC validation after installing `django-oauth-toolkit[oidc]`.
  - [ ] Run full client OIDC validation after installing `mozilla-django-oidc`.
- Completed Recently:
  - [x] Aligned setup boolean cards across steps `2` to `5` with `build_settings_toggle_field(...)`.
  - [x] Made Step 2 language override full-width and added gap before translation filters.
  - [x] Gated `registration_activation_mode` and `registration_throttle_enabled` behind `public_registration_enabled`.
  - [x] Added explicit Step 3/4 row spacing for stacked toggle-card rows.
  - [x] Moved `public_registration_enabled` to its own full-width row and placed its dependent controls on the following gated row.
  - [x] Fixed System Settings file widgets to use the Microsys custom archive widget path explicitly.
  - [x] Added reusable current-password confirmation gating for destructive profile security actions.
  - [x] Added vertical padding to shared toggle-card selector grids and bumped the selectors asset version.
  - [x] Added permanent responsive reflow behavior to shared setup/settings toggle cards.
  - [x] Bumped the `system_setup.css` asset version for browser pickup after the toggle-card reflow fix.
  - [x] Aligned the Step 5 titlebar toggle row spacing with the selection-widget row spacing.
  - [x] Replaced inline Options styling/behavior with shared external `options.css` and `options.js` assets.
  - [x] Restored Autofill and Reset Defaults as standalone Options cards while reusing the new shared card surface across the page.
  - [x] Added draggable/persisted Options card ordering while preserving the double-width System Info card span.
  - [x] Changed the user hub mobile toolbar from forced stacked rows to wrap layout so it can stay on one row when space allows.
  - [x] Externalized inline template CSS/JS into shared static assets and removed inline `style=` usage from templates plus the main Python HTML emitters.
  - [x] Converted theme preview swatches from inline background styles to shared slug-based CSS classes.
  - [x] Added regression tests that fail on inline template `<style>`, executable inline `<script>`, and inline `style=` markup.
  - [x] Fixed profile TOTP setup to avoid the fragile `pyotp.totp.TOTP(...)` path, bypass unrelated `Profile.save()` side effects via `set_profile_totp_state(...)`, and return JSON instead of raw 500 responses when provisioning/QR generation or secret persistence fails.
  - [x] Added the stable `v2.1.0` changelog entry and refreshed dependency docs to include `cryptography`.
  - [x] Updated the reference/admin/customization/registration/scaffold docs for reusable guards/helpers, draggable Options cards, scaffold baseline details, and current 2FA/public-registration behavior.
  - [x] Added the stable `v2.1.1` changelog entry for packaging hygiene, MSRP-1 no-inline policy clarification, and release/docs organization.
  - [x] Refreshed `docs/FEATURES.md` and `docs/README.md` to match the `2.1.1` setup flow, Options/runtime behavior, reusable helper APIs, 2FA routes, and no-inline MSRP-1 policy references.

### One-line info about last verified Tests:
- `2026-05-07`: Django `DiscoverRunner` passed `microsys.tests.test_utils.UtilsTests` plus `microsys.tests.test_views.TwoFactorSecurityViewTests` with `65` tests after adding `set_profile_totp_state(...)`, tightening TOTP persistence, and updating release/docs metadata.

### One-line info about last time edited Docs:
- `2026-05-07`: `docs/FEATURES.md` and `docs/README.md` were refreshed to match `2.1.1` runtime behavior, reusable helper APIs, current 2FA routes, and the no-inline MSRP-1 policy; earlier the same day `CHANGELOG.md` was updated with the stable `v2.1.1` patch release entry, `docs/security-msrp-1.md` was updated to add the no-inline HTML/CSS/JS policy to the MSRP-1 core rules, and `README.md`, `docs/getting-started.md`, `docs/reference.md`, `docs/admin-guide.md`, `docs/customization-guide.md`, `docs/registration.md`, `microsys/scaffold_templates/project/README.md.tmpl`, and `tracker.md` were updated for `v2.1.0`, reusable helper coverage, scaffold/runtime docs, and the explicit `cryptography` dependency.

## Part 2: Global
### Global Standard Helpers, Shortcuts, Info, etc.:
- Reusable helper APIs:
  - `require_current_password(request)`
  - `build_archive_file_field('<field_name>')`
  - `build_settings_toggle_field(form, '<field_name>', css_class='...')`
  - `set_profile_totp_state(profile, raw_secret=..., enabled=...)`
- Common validation commands:
  - Focused defaults/render suite:
    - `./.venv/bin/python -m unittest microsys.tests.test_defaults_and_urls`
  - Focused 2FA view suite:
    - `./.venv/bin/python - <<'PY' ... DiscoverRunner(...).run_tests(['microsys.tests.test_views.TwoFactorSecurityViewTests']) ... PY`
  - Legacy focused defaults/render suite reference:
    - `./.venv/bin/python - <<'PY' ... runner.run_tests(['microsys.tests.test_defaults_and_urls']) ... PY`
  - Full compile check without repo `__pycache__` ownership issues:
    - `PYTHONPYCACHEPREFIX=/tmp/microsys-pycache ./.venv/bin/python -m compileall microsys`
  - Packaging verification:
    - `rm -rf dist build *.egg-info && ./.venv/bin/python -m build --wheel --sdist`
    - `unzip -l dist/*.whl | rg 'microsys/tests|__pycache__|\\.pyc|\\.pyo'`
    - `tar -tf dist/*.tar.gz | rg 'microsys/tests|__pycache__|\\.pyc|\\.pyo'`
- Known local environment note:
  - `node` is not available in the current environment, so JS syntax checks via `node --check` are not currently usable.

### Global Rulesets:
- Prefer explicit reusable helpers over template shadowing or duplicated inline HTML.
- When a UI issue differs between modal/runtime/setup surfaces, verify the actual load/bind/runtime path before adding sync code.
- Keep tracker entries grounded in verified code, verified runtime behavior, or explicit user instruction.
- Do not convert user complaints into “fixed” tracker notes until the real runtime path is verified.
- Leave unrelated worktree changes untouched.
- No inline CSS/JS in HTML unless there is a real unavoidable runtime reason:
  - prefer dedicated static CSS/JS files,
  - use `json_script` and `data-*` for server-to-client data handoff,
  - if a future exception is truly required, record why in the tracker instead of normalizing it silently.
- Packaging should stay lean by default:
  - exclude `microsys.tests` from published distributions,
  - exclude `__pycache__`, `.pyc`, and `.pyo` artifacts from published distributions.

### Agent Handoff Rules:
- Re-read this tracker at the start of every turn and update it after meaningful project-state changes.
- The user explicitly corrected earlier assumptions about local testing: they mount this repo over the target app, so do not assume they are running only the packaged PyPI release when they say the local checkout is active.
- The unresolved first-launch sidebar warning issue should be treated as a real runtime problem, not something to “paper over” with speculative event handlers unless the runtime path has been reproduced.
- Preserve user corrections explicitly in future tracker updates so the same wrong assumptions are not repeated.

### References and Links:
- Key project files:
  - `microsys/forms.py`
  - `microsys/widgets.py`
  - `microsys/guards.py`
  - `microsys/utils.py`
  - `microsys/views/twofa.py`
  - `microsys/views/profile.py`
  - `microsys/views/sections.py`
  - `microsys/static/microsys/main/js/system_setup.js`
  - `microsys/static/microsys/main/css/selectors.css`
  - `microsys/static/microsys/users/css/user_hub.css`
  - `microsys/templates/microsys/base.html`
  - `microsys/tests/test_defaults_and_urls.py`
- Optional SSO references:
  - `optional_packages/django-microsys-sso/microsys_sso`
  - `optional_packages/django-microsys-sso-client/microsys_sso_client`
- External standards/docs already relevant to the project:
  - OAuth 2.0 Security BCP / RFC 9700: `https://www.rfc-editor.org/rfc/rfc9700.html`
  - Django OAuth Toolkit OIDC docs: `https://django-oauth-toolkit.readthedocs.io/en/stable/oidc.html`
  - mozilla-django-oidc settings docs: `https://mozilla-django-oidc.readthedocs.io/en/stable/settings.html`
