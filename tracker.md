# Project Tracker

## Part 1: Project
### Current Verified Snapshot and current project overview:
- Verified on: `2026-05-01`
- Project: `django-microsys`
- Current package version from codebase: `2.0.3` in `microsys/VERSION` (CHANGELOG.md updated for `2.1.0` pending release)
- last migration file: `0002_public_registration.py`
- Current verified state:
  - Core framework areas: scoped data isolation, MSRP authorization hardening, managed table rendering, setup/System Settings, runtime sidebar/titlebar controls, and Options entrypoints are implemented in code.
  - `SystemSettings` uses language-keyed `system_names`; `get_system_config()` exposes nested public groups (`identity`, `localization`, `security`, `navigation`, `appearance`, `personalization`) plus compatibility keys.
  - Options sidebar visibility now matches direct `/sys/options/` access through `__ms_authenticated__`.
  - TOTP provisioning uses configured system identity display name / neutral fallback, not the old project-specific `FineStor` issuer.
  - Optional SSO v1 scaffolding is implemented as separate packages under `optional_packages/`, not inside core `microsys/`:
    - provider plugin: `optional_packages/django-microsys-sso`
    - client SDK: `optional_packages/django-microsys-sso-client`
    - core `pyproject.toml` now points the `sso` extra at `django-microsys-sso>=0.1.0` instead of implying embedded SSO code.
  - Optional SSO cross-platform contract is documented as first-priority: generic PHP/.NET/JS/Java/Go/mobile/desktop clients should use standard OIDC discovery and Authorization Code flow; the Django client SDK is only a convenience wrapper.
  - Public registration playground is implemented in core and disabled by default:
    - routes: `/accounts/register/`, `/accounts/register/sent/`, `/accounts/register/verify/<token>/`
    - approval routes: `/sys/registrations/`, `/sys/registrations/<pk>/approve/`, `/sys/registrations/<pk>/reject/`
    - local user creation is email-first, inactive until verified, with hashed verification tokens only
    - activation modes: `auto_login_after_verify` and `verified_pending_approval`
    - email readiness is checked through Microsys mail helpers, supporting `env` mode plus explicit `encrypted_db` mode
    - publicly registered users expose a "Public signup" provenance badge in account surfaces without adding a separate user-source field
  - System Setup/System Settings Access & Security step has Microsys-owned email delivery configuration:
    - `SystemSettings.email_config` JSON stores non-secret env-mode hints or encrypted DB-mode SMTP config
    - encrypted DB mode uses `cryptography`; exports redact SMTP secrets and imports require re-entering the secret
    - public registration and email 2FA are gated on selected Microsys mail mode readiness
  - Login 2FA now uses one challenge input:
    - authenticator app codes work directly
    - email OTP is sent only after explicit "Send email code"
    - backup codes remain available through the same input
  - Runtime sidebar can be disabled with `sidebar_config.enabled`; disabled mode hides sidebar rendering, hides the titlebar sidebar toggle, and ignores toolbar/reorder/density controls.
  - Runtime sidebar desktop collapse/expand is controlled by `sidebar_config.collapse_mode`; `locked_expanded` now hides the desktop titlebar toggle without reserving space while keeping the mobile toggle available for phone navigation.
  - Options diagnostics are now restricted to superusers and Global Staff only; unauthorized users receive no diagnostic context values.
  - Options theme persistence no longer depends on the sidebar JS being present; base theme JS provides a global `updatePreferences()` fallback.
  - Options System Settings split-step modals receive request context and render as single-step save forms instead of full wizard forms.
  - Options System Settings card now uses the same `glass-profile option-section` shell and inline `h4` icon/title pattern as the other Options cards; action buttons use scoped dark-theme styling in dark/retro/gothic/neon.
  - Options reset action has scoped dark-theme styling in dark/retro/gothic/neon so the Reset Now outline button and action shell no longer fall back to a generic Bootstrap light/gray look.
  - System Setup sidebar builder outline action buttons use scoped dark-theme styling in dark/retro/gothic/neon instead of generic gray Bootstrap outline surfaces.
  - Dark and neon titlebar sidebar toggles now use transparent at-rest backgrounds scoped to `.titlebar .sidebar-toggle`, matching the titlebar surface like retro/gothic while keeping restrained hover feedback.
  - Disabled-sidebar titlebars no longer reserve invisible start-side space after the toggle is hidden.
  - Options email diagnostics row renders only when public registration or email 2FA is enabled.
  - User profile shows signed-in devices backed by Django sessions; the current session is listed with a request/session fallback and users can revoke their own non-current sessions through a POST-only action.
  - Global Microsys table shell/card clipping was tightened with rounded clipping so themed row/header backgrounds do not protrude past corners.
  - Generated Docker projects route application email through an internal `smtp-relay` sidecar:
    - `web` and `celery` stay on the internal network
    - only `smtp-relay` joins both the public and internal Docker networks for upstream SMTP egress, without publishing an inbound relay port by default
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
- Optional SSO:
  - Provider package: `django-microsys-sso`, opt-in through `microsys_sso.settings.microsys_sso_settings(globals())`.
  - Client package: `django-microsys-sso-client`, opt-in through `microsys_sso_client.settings.configure_microsys_sso(...)`.
  - OIDC-only v1; per-client portable roles are `admin`, `staff`, and `user`.
  - Generic clients should use provider discovery at `/o/.well-known/openid-configuration/`, Authorization Code flow, `openid email profile` scopes, RS256/JWKS validation, and the flat role claim `microsys_sso_role`.
  - Do not mirror project-generated Django permissions into SSO clients.
- Public registration:
  - Core playground feature, disabled by default through `public_registration_enabled`.
  - Requires email delivery before enabling, except local `DEBUG=True` console/locmem/file backends.
  - Email delivery is configured through `SystemSettings.email_config`:
    - `env` mode stores non-secret UI hints and reads the SMTP password from environment/secrets.
    - `encrypted_db` mode stores an encrypted SMTP password and is explicit opt-in.
    - exports never include plaintext or ciphertext SMTP secrets.
  - Email verification is mandatory before activation or approval.
  - Publicly registered users are local Microsys users, not SSO client-originated identities.
  - Approval/rejection actions are superuser-only and POST-only.

### Standards' rules and policies:
- Keep Microsys defaults framework-neutral unless the default is explicitly part of the framework contract.
- Prefer additive helpers, templates, and extension points over project-rewriting commands.
- Do not use `settings.configure()` as a host-project installation path.
- Keep host-project-specific behavior out of Microsys defaults unless broadly reusable.
- Document supported integration surfaces in `README.md` plus `docs/reference.md` or `docs/customization-guide.md`.
- MSRP-1 is the active authorization policy: direct routes, sidebar/catalog visibility, dashboard/user-hub links, modal/context actions, diagnostics, and 2FA mutators must agree on who can access the behavior.
- Optional SSO must remain additive and fail closed: no core `microsys` runtime imports/URLs/middleware/login changes, exact registered redirect URIs, HTTPS outside local development callbacks, and per-client membership/role checks before authorization.
- Prefer helper-backed permission checks and internal tokens resolved by `user_matches_permission_token()`; do not add ad hoc `is_staff` gates unless staff-only access is the explicit contract.
- Any generated or scaffolded entrypoint exposed by URL registration must enforce login plus the relevant model/system permission on the backend, not only through sidebar hiding.

### Cross-Cutting Audits if any:
- Security/MSRP-1 audit:
  - backend permission enforcement now exists for modal CRUD, sections, user detail/modals, activity log, and reset-password flow
  - 2FA state mutators are POST-only and backup codes are hashed at rest
  - Options diagnostics are superuser/Global Staff only and non-privileged users get no diagnostic context values
- Optional SSO audit:
  - provider/client code lives in `optional_packages/` and is not imported by core Microsys
  - provider redirect policy helper requires exact redirect URI registration and HTTPS unless localhost dev callbacks are explicitly allowed
  - provider userinfo claims now include flat cross-platform claims `microsys_sso_role` and `microsys_sso_client_id` plus the nested `microsys_sso` object
  - client role mapping never maps provider `admin` to Django `is_superuser`; `is_staff` changes require explicit host role mapping
- Public registration audit:
  - registration is disabled by default and returns 404 while disabled
  - signup creates inactive users and `PublicRegistration` rows with hashed tokens only
  - duplicate email, honeypot, and throttle-denied submissions use generic success-style flow
  - email OTPs now use `secrets`, store hashed cache values, keep short TTL, enforce attempt limits, and do not log live codes
  - login 2FA does not send email OTP automatically; the user must request email delivery explicitly
  - pending approval list is superuser-only; approve/reject require POST and are audit logged
- Table platform audit:
  - Microsys-managed tables now respect `Meta.microsys_table`, `Meta.microsys_density`, `Meta.microsys_per_page`, `Meta.microsys_per_page_options`, and `Meta.microsys_actions`
  - stock/no-template host tables are auto-captured into the Microsys renderer
  - Setup/Options audit:
  - theme allowlist, language lock, sidebar runtime controls, and titlebar controls are wired through setup and split Options modals
  - setup/System Settings localization now has an explicit add-language catalog and translation matrix; custom languages remain unavailable until explicitly added
  - sidebar disable and Microsys email delivery mode controls are wired through setup/System Settings export/import paths
  - System Settings email-delivery fields are UI-gated behind public registration or email 2FA toggles; hidden/disabled email fields preserve existing/imported config instead of wiping it

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
    - sidebar enabled/disabled layout and titlebar sidebar-toggle hiding
    - `locked_expanded` desktop sidebar collapse mode hides the desktop titlebar toggle while mobile toggle remains available
    - titlebar visibility/alignment/shape/surface controls
    - Microsys email delivery env/encrypted DB mode UI, feature-gated visibility, and readiness alerts
  - [ ] Browser-check account/security UI modernization:
    - public signup provenance badge on profile, user table, and user detail modal
    - unified login 2FA challenge for TOTP, requested email OTP, and backup code
    - profile 2FA loading states and updated profile image file widget
    - signed-in device list and session revocation UX
    - non-primary button contrast in light, dark, mono, neon, gothic, and retro themes
    - global table rounded-corner clipping in dark, retro, gothic, and neon themes
  - [ ] Browser-check live runtime shell behavior:
    - sidebar save -> runtime render
    - sidebar toolbar auto-hide/disable logic
    - desktop collapse modes `icons`, `hidden`, `locked_expanded`
    - titlebar `show_title` / `show_logo` / `show_home_button`
  - [ ] Browser-check Options layout and selector widgets after the latest cleanup.
    - System Settings action button contrast in light, dark, retro, gothic, neon, and mono themes
  - [ ] Browser-check Options theme persistence with sidebar enabled and disabled.
- Priority 2:
  - [ ] Run one end-to-end generated-project validation for `python -m microsys startproject`.
  - [ ] Run one end-to-end generated-app validation for `python -m microsys startapp --register`.
  - [ ] Validate generated Docker/Celery/health-check baseline in a live boot.
  - [ ] Run full provider OIDC validation after installing `django-oauth-toolkit[oidc]`:
    - apply `microsys_sso` migrations in a test project
    - verify authorize/token/userinfo/JWKS/revoke endpoints
    - verify denial for inactive client, bad redirect URI, missing role, expired invitation, and revoked session
  - [ ] Run full client OIDC validation after installing `mozilla-django-oidc`:
    - mount `microsys_sso_client.urls`
    - verify `(issuer, sub)` identity linking
    - verify allowed role auto-create and denied/missing role fail-closed behavior
    - verify local group/staff mapping and no `is_superuser` elevation
- Completed Recently:
  - [x] Updated CHANGELOG.md with v2.1.0 release notes covering public registration, SSO, email delivery, 2FA, sidebar controls, signed-in devices, Docker SMTP relay, Global/Central Staff tiers, table platform, Options security/UX, security hardening, and theme polish.
  - [x] Modernized System Setup sidebar builder and Options action buttons for dark themes.
  - [x] Replaced redundant sidebar-toggle checkbox with improved `locked_expanded` collapse mode.
  - [x] Fixed sidebar/titlebar/email/options/profile cleanup (disabled sidebar, email diagnostics gating, theme persistence, System Settings modals).
  - [x] Added signed-in devices to user profile with POST-only session revocation.
  - [x] Fixed themed Microsys table card corner clipping.
  - [x] Implemented account/security UI modernization (unified 2FA login, provenance badges, loading spinners, file-field widget).
  - [x] Implemented UI-first Microsys email delivery setup with env and encrypted DB modes.
  - [x] Fixed generated Docker SMTP delivery via `smtp-relay` sidecar.
  - [x] Implemented public registration playground in core.
  - [x] Implemented optional SSO v1 package scaffolding in `optional_packages/`.
  - [x] Implemented Global Staff vs Central Staff tier system with `manage_scopes` permission.

### Tests:
- **Current status**: `255` tests run, `8` errors — all are the known `view_activitylog` permission ownership/test drift on `UserActivityLog` content type.
- **Recommended test commands**:
  - Full suite: `./.venv/bin/python -c "from django.test.runner import DiscoverRunner; runner = DiscoverRunner(verbosity=1); failures = runner.run_tests(['microsys.tests']); raise SystemExit(bool(failures))"`
  - Core views: `./.venv/bin/python -m unittest microsys.tests.test_views`
  - Registration: `./.venv/bin/python -m unittest microsys.tests.test_registration`
  - Sidebar discovery: `./.venv/bin/python -m unittest microsys.tests.test_sidebar_discovery`
  - Optional SSO packages: `python -m compileall optional_packages`
- **Recommended next validation**:
  - Fix `view_activitylog` ownership/test drift, then rerun the full Django suite
  - Browser validation for UI-heavy setup, Options, language matrix, sidebar/titlebar, and 2FA flows
  - One live generated-project boot and one generated-app registration pass
  - Install optional SSO dependencies and run provider/client OIDC integration tests

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
  - `docs/security-msrp-1.md`
  - `docs/registration.md`
    - documents env-mode UI hints, encrypted DB mode, and generated Docker `smtp-relay:1025` egress-only relay usage
  - `docs/sso.md`
- Key contracts to keep documented:
  - MSRP-1 authorization and 2FA contracts
  - Public registration playground contract: disabled by default, SMTP-gated, email-verified, hashed tokens, throttled/honeypot protected, and local-user-only
  - Microsys email delivery config contract: `SystemSettings.email_config`, `env` mode UI hints with env/secrets password, explicit `encrypted_db` mode, redacted export/import
  - Generated Docker public-registration email contract: app containers use internal `smtp-relay:1025`; only the relay sidecar has public SMTP egress through `SMTP_RELAY_*` secrets
  - `SystemSettings.allowed_themes`
  - `SystemSettings.allow_user_theme_override`
  - `SystemSettings.allow_user_language_override`
  - `SystemSettings.system_names`
  - `SystemSettings.languages` explicit language catalog behavior
  - `SystemSettings.translations_override` as the matrix-backed runtime override layer
  - System Settings export/import JSON format: `django-microsys.system-settings`
  - `SystemSettings.titlebar_config`
  - `SystemSettings.public_registration_enabled`
  - `SystemSettings.registration_activation_mode`
  - `SystemSettings.registration_throttle_enabled`
  - sidebar runtime config keys: `enabled`, `show_icons`, `density`, `allow_user_density`, `collapse_mode`
  - `microsys.widgets.MicrosysChoiceSelectorWidget`
  - `microsys.widgets.MicrosysMultipleChoiceSelectorWidget`
  - `microsys.tables.MicrosysTable`
  - `microsys_settings(globals())`
  - `microsys_sso_settings(globals())`
  - `configure_microsys_sso(...)`
  - optional SSO per-client role contract: `admin`, `staff`, `user`
  - optional SSO generic client contract: discovery URL `/o/.well-known/openid-configuration/`, scopes `openid email profile`, flat role claim `microsys_sso_role`, no Django permission mirroring

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
- Optional SSO standards/docs:
  - OAuth 2.0 Security BCP / RFC 9700: `https://www.rfc-editor.org/rfc/rfc9700.html`
  - Django OAuth Toolkit OIDC docs: `https://django-oauth-toolkit.readthedocs.io/en/stable/oidc.html`
  - mozilla-django-oidc settings docs: `https://mozilla-django-oidc.readthedocs.io/en/stable/settings.html`

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
  - `optional_packages/django-microsys-sso/microsys_sso`
  - `optional_packages/django-microsys-sso-client/microsys_sso_client`



TODO by DeBeski: "DO NOT TOUCH"

the sidebar-toolbar removal warning only works in modal view "from options view", doesnt work in initial setup view tho.

generated table of scaffolded app's context menu doesnt work for some mysterious reason even tho microsys table should be handling it automatically.
