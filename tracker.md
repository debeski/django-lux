# Project Tracker (django-microsys)

## Part 1: Project Related
### Current Verified Snapshot (Verified: `2026-05-15` & `2026-05-16`)

#### 📦 Package & Distribution State
* **v2.2.1 Release:** `microsys/VERSION` and `CHANGELOG.md` updated to stable `v2.2.1`. Built distributions (`wheel`/`sdist`) explicitly exclude `microsys.tests`, `__pycache__`, and compiled artifacts.
* **Root URL Detection:** Simplified hijacking by replacing `_is_root_mounted_microsys` introspection with transparent 404 detection. If `/` yields 404, redirects to `home_url`; if host app defines `/`, hooks stay out of the way.

#### 🔒 Security, Authentication & 2FA Flow
* **Pre-Setup Middleware:** Guards non-allowlisted host-app URLs (including host `/`) for root/prefix routes. Redirects anonymous users to `login`, superusers to `system_setup`, and logs out/redirects non-superuser authenticated users to `login`.
* **Login 2FA Challenge:** Email-only auto-sends OTP with `120s` cooldown; mixed accounts default to TOTP unless email requested. Code entry auto-submits via real form once full length is hit. Fix applied: scripts use `readOnly` instead of `disabled` to prevent stripping `otp_code` from POST (Assets: `20260515d`).
* **Trusted Devices:** Stored in dedicated `TrustedDevice` model linked to `microsys_device` session metadata. Displays `Trusted until ...` for `30` days in profile; revoked alongside session termination.
* **Client IP Resolution:** Centralized into `get_client_ip(request)` governed by a JSON-backed `SystemSettings.client_ip_config` block (`mode`, `trusted_proxy_hops`, `custom_header`).
* **Profile TOTP Fixes:** Uses stable `pyotp.TOTP(...)` path (username fallback if email blank). Persists via `set_profile_totp_state(...)` instead of full `Profile.save()`. Returns sanitized JSON errors instead of raw 500 HTML.
* **Security Controls:** Requiring current password enforced for destructive actions via `require_current_password(request)`. Translations updated across all 2FA/IP modules (Assets: `20260515e`).

#### ⚙️ System Setup Wizard & Settings Engine
* **Global Architecture:** System Settings/setup uses custom archive widgets via `build_archive_file_field(...)` and shared boolean toggle card renderers `build_settings_toggle_field(...)` across Steps 2–5.
* **Step 2 (Localization):** `allow_user_language_override` is full-width, separate from matrix filters. Default-language previews reload via standard switch path to preserve unsaved form values while refreshing text in chosen language (Assets: `20260515c`).
* **Step 3 (Access & Security):** Inherits `home_url` from Step 4. Controls anonymous split routes via `public_root_split_enabled` and `public_root_url`. Managed by one form-scoped handler using `name=` fields (no duplicate document-level listeners). Registration sub-fields stay gated/disabled until `public_registration_enabled` is true. Preserves values in `SystemSettingsForm` if destination fields are missing from POST.
* **Step 5 (Titlebar Settings):** Row layout uses uniform `g-3 mb-3` gutters. Includes `hide_on_public_unauthenticated_index` to hide titlebars for anonymous requests on public root paths.
* **Step 6 (Typography & Density):** Integrated typography settings alongside centralized font handling. Single-step modal saves now preserve omitted Step 6 values (`default_theme`, `allowed_themes`, `allowed_fonts`, `default_fonts`, `default_table_density`) server-side so hidden/JS-owned controls do not block saves from other steps.
* **Wizard Step Display Fix:** Wizard step navigation removes Bootstrap `d-none` in shared helper instead of only flipping inline display, preventing Steps 2–5 from rendering empty after clicking `Next`.

#### 🎨 Layout, Accessibility & Theme Polish
* **Toggle Card Component Container Queries:** Shared cards use container queries in `system_setup.css` to stack switches below labels on narrow viewports; text uses `overflow-wrap: break-word`. Bootstrap `form-check` padding dependencies removed inside custom cards. 
  * *Exception:* Step 3 email `Provider STARTTLS`/`SSL` bypass shared renderer; uses compact `build_email_toggle_field(...)` markup to resolve rendering errors.
* **Draggable Options Panel:** Extracted to external assets (`options.css`/`options.js`). Cards are draggable and ordering persists; System Info retains double-card placement. Drag handles use in-flow grip controls to eliminate title/icon overlap. Uses RTL-aware inline start/end gap indicators on `.ms-options-card`.
* **A11y Pass:** Language catalog, system names, translation matrix, and sidebar builder JS controls enforce stable `id`/`name` attributes and explicit `aria-label` definitions. Setup editor controls strip custom `ms_*` POST namespaces.
* **Asset & CSP Policy Code Enforcement:** Zero inline `<style>`, executable inline `<script>`, or inline `style=` attributes remain in verified paths. Theme swatches use slug-based CSS classes. Dynamic-modal loaders correctly propagate the request CSP nonce.
* **UI Contrast & Micro-Fixes (2026-05-16):**
  * Primary badges get explicit white foreground text via `main.css` (cached broke at `20260515a`).
  * Profile 2FA setup buttons render `MS_TRANS.enable` accurately in English and Arabic.
  * Activity log model names are normalized (handling spaces, underscores, periods) via a shared helper before lookup.
  * User hub mobile toolbar wrapped in a single row to prevent layout splitting.
  * Unauthenticated titlebar login triggers match `ms-titlebar-home` treatments and target the live `.ms-login-round` selector across `dark`/`gothic`/`retro`/`neon` theme overrides.

#### 🛠️ Generic Modals & AJAX Framework
* **Modal Framework Navigation:** Shared modal wizard navigation manages `d-none`, inline `display`, and `aria-hidden` cleanly across steps, preserving user-create modal action buttons on Step 2.
* **System Settings Modal Step Resolution:** `DynamicModalManagerView._get_wizard_initial_step(...)` must recognize steps `0..5`; the old `0..4` limit became stale after the Step 5 -> Step 6 split and could mis-hydrate invalid Step 5 modal rerenders.
* **Modal Architecture:** Legacy full-page user forms are completely removed; routed user management is strictly modal-only. Obsolete `user_form.html` template deleted.
* **Error Tolerances:** Dynamic modal form submissions expect JSON and intercept non-JSON HTTP errors gracefully. AJAX hits returning Django `SuspiciousOperation` or 400 bad requests return structural JSON payloads with exception classes instead of raw HTML error pages. Invalid `SystemSettings` modal POSTs now log `form.errors.get_json_data()` with the requested step so container logs expose the real blocking field names.
* **Clean Logging:** Generic modal CRUD relies entirely on signal-based activity logging for `CREATE`/`UPDATE`/`DELETE` blocks, eliminating duplicate companion logs previously compiled by `DynamicModalManagerView`/`DynamicModalDeleteView`.

#### 👥 Permissions & Three-Tier Staff Architecture
* **Permission UI Sanitization:** Excludes low-level scaffold app labels (`db`, `health_check`) and skips orphaned permissions without valid `ContentType.model_class()`. Groups `manage_scopes`, `manage_staff`, and synthetic `is_staff` under a single staff-access card. Re-labels `Profile`-backed strings to `model_user` (`Users`).
* **Targeted Three-Tier UI Restoration:**
  * Exposed runtime presentation helpers `get_user_management_tier_state(...)` and `get_user_management_tier_state_for_user(...)` via `microsys.utils`.
  * Permissions forms render live staff-tier previews with scope-aware warnings and `data-codename` hooks for `manage_scopes`/`manage_staff`.
  * Target user profile, user hub, detail modals, and manage tables render consistent derived tier badges and delegation flags. Manage-users tutorial updated to track live modal trigger `button[data-dynamic-modal]`.
* **Theme & Contrast Hardening:** Staff-tier preview cards use explicit dark-surface overrides for `dark`/`gothic`/`neon`/`retro` overrides even if `data-bs-theme="dark"` is absent. Global staff badges use explicit, table-scoped classes inside `tables.css` and `ms-staff-tier-badge` inside modals to ensure readability over light theme variants.

#### 🔤 Dynamic Font Management System
* **Core Font Registry:** Centralized in `microsys/fonts.py`.
* **Model Integration:** `SystemSettings` schema extended with `allowed_fonts`, language-specific `default_fonts`, and `allow_user_font_override`.
* **Runtime Assets:** Typography configuration cards injected into User Options panel with early-load FOUC prevention in `base_head.js`. All fonts housed under `static/microsys/fonts/` driving the application global styling variable `--ms-main-font`.

#### 🔒 Active Core Hardening
* Active codebase validation checks pass for sidebar/titlebar runtime blocks, split-step options modals, auto-generated scope-aware CRUD scaffolds, and strict MSRP-1 authorization hardening.

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
- All new or revised user-facing strings must use Microsys's own translation framework:
  - do not hardcode English or Arabic UI copy in Python, templates, or JS,
  - do not add template `|default:"..."` fallbacks for new user-facing copy,
  - add the needed keys to `microsys/translations.py` and pass them through `MS_TRANS`, `get_strings(...)`, `json_script`, or `data-*` as appropriate.

### Current Project's Unsolved Known Bugs:
- First-launch System Setup still has an unresolved runtime issue where the sidebar-toolbar removal warning does not match the Options modal behavior.
- [x] Fixed persistent 500 Internal Server Error in System Settings modals caused by a missing `normalize_allowed_fonts` import and improper JSON handling in `SystemSettingsForm.__init__`.
- [x] Fixed 404 error for font files by correctly nesting them under `static/microsys/fonts/` and renaming them to lowercase to match CSS.
- [ ] Live Options -> System Settings Step 3 modal save still returns HTTP 400 in the user's mounted app; local full modal POST reproductions return 200, so the next check must use the new AJAX JSON error/class or server logs from the live app.
- [ ] Browser/runtime confirmation is still pending in the mounted deployed app after the Step 2 relay/env readiness fix; the server-side regression is now covered, but the user still needs a live retry after restarting Python workers.
- `microsys/fetcher.py` still trusts `request.META['HTTP_REFERER']` for fallback redirects in download/export error branches; this should be replaced with an allowlisted local redirect target or validated with `url_has_allowed_host_and_scheme(...)`.
- Browser/manual validation is still pending for:
  - setup/System Settings wizard behavior,
  - sidebar/titlebar runtime behavior,
  - Options selector widgets and theme persistence,
  - POST-only 2FA flows,
  - profile security/session UX.

### Incomplete Tasks:
- Priority 1:
- [ ] Harden `microsys/fetcher.py` fallback redirects so download/export error branches do not trust raw `HTTP_REFERER`.
  - [ ] Verification:
    - [ ] validate fallback redirect behavior for empty download/export cases with missing, local, and forged external referers
  - [ ] Browser-check the pre-setup host-app guard in a mounted project for anonymous, superuser, and non-superuser requests before setup completes.
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
    - [ ] manage users create modal step-2 action row (Cancel / Previous / Add)
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
    - [ ] first-launch step navigation from Step 1 through Step 5 after the shared wizard fix
    - [ ] language catalog add/remove and default-language behavior after restoring full reload-based preview text refresh without step auto-return
    - [ ] translation matrix search/filter/edit behavior
    - [ ] allowed themes matrix
    - [ ] language lock behavior
    - [ ] public-root split toggle plus anonymous/authenticated destination fields in Step 3
    - [ ] sidebar density/collapse/icon controls
    - [ ] sidebar enabled/disabled runtime layout
    - [ ] titlebar visibility/alignment/shape/surface controls, including the anonymous public home/index hide toggle
    - [ ] email delivery UI gating and readiness alerts
  - [ ] Browser-check account/security UI modernization:
    - [ ] public signup provenance badge
    - [ ] unified login 2FA challenge UX
    - [ ] profile 2FA loading/email confirmation flow
    - [ ] signed-in device list and revocation UX
    - [ ] unauthenticated titlebar login trigger in dark/gothic/retro/neon with circle/square/squircle titlebar shapes
    - [ ] light/dark/mono/neon/gothic/retro contrast for secondary buttons
  - [ ] Browser-check the restored staff-tier UI surfaces in a mounted app:
    - [ ] create-user permissions step live preview
    - [ ] edit-permissions preview for scoped, central, and global staff
    - [ ] profile badge/description rendering
    - [ ] user detail modal badge/description rendering
    - [ ] manage-users table staff-tier badge column and tutorial selector target
  - [ ] Review translation coverage for UI labels/messages that were called out by the user and are not yet re-verified in browser/runtime:
    - [ ] broader profile/user-management legacy defaults outside the recent 2FA/session/client-IP additions
    - [ ] general setup/options labels and descriptions outside the recent client-IP block
- Priority 2:
  - [ ] Run one end-to-end generated-project validation for `python -m microsys startproject`.
  - [ ] Run one end-to-end generated-app validation for `python -m microsys startapp --register`.
  - [ ] Validate generated Docker/Celery/health-check baseline in a live boot.
  - [ ] Run full provider OIDC validation after installing `django-oauth-toolkit[oidc]`.
  - [ ] Run full client OIDC validation after installing `mozilla-django-oidc`.
  - [ ] Plan the unrelated stash refactor as a separate batch before touching it:
    - [ ] strict password validation and force-2FA-first-login settings
    - [ ] nested `branding/localization/appearance/navigation/authentication/registration/email/assets` config model
    - [ ] setup import/export shape migration
    - [ ] registration branding lookup migration
- Completed Recently:
  - [x] Confirmed via live container logs that a remaining System Settings save failure was actually Step 2 email validation: `email_config` blocked save because the mounted app had `SMTP_RELAY_*` env vars set, but the validator was checking Django `EMAIL_*` or saved DB email config instead.
  - [x] Fixed the Step 2 email readiness gate for deployed internal SMTP relay + env/secrets setups: `SystemSettingsForm.clean()` and `get_email_service_status()` now accept scaffolded `SMTP_RELAY_*` plus `DEFAULT_FROM_EMAIL` as a configured relay/env path, and the focused regression plus helper probe passed.
  - [x] Fixed the System Settings modal save regression after the Step 5 -> Step 6 split: single-step modal POSTs could omit Step 6 fields and fail validation on `default_table_density` (and related theme/font values), so `SystemSettingsForm` now relaxes field-level required checks in single-step modal mode and preserves the existing Step 6 values server-side when omitted.
  - [x] Fixed the stale System Settings modal step resolver in `DynamicModalManagerView` so `?step=5` is treated as a valid wizard step after the Step 6 split, and added targeted server-side logging for invalid `SystemSettings` modal POSTs.
  - [x] Replaced the Options typography card's custom font strip with the same shared selector pattern used by the language and density cards.
  - [x] Added focused regression coverage for `?step=5`, the shared font selector markup, the single-step modal omission path for Step 6 values, and the JS guard that keeps the last allowed theme postable.
  - [x] Implemented Dynamic Font Management system: centralized registry in `fonts.py`, `SystemSettings` integration, Typography cards in setup and options, and CSS variable injection with FOUC prevention.
  - [x] Restructured System Setup wizard: split Step 5 Appearance into Step 5 (Titlebar only) and Step 6 (Themes, Typography & Table Density).
  - [x] Centralized all font assets under `static/microsys/fonts/` with lowercase normalization for consistency.
  - [x] Fixed three follow-up regressions in profile/activity-log/user-detail: missing 2FA Enable button text, untranslated `System Settings` activity-log model labels, and the user-detail modal’s weak Global Staff badge class.
  - [x] Tightened login 2FA with email-only auto-send, `120s` resend cooldown, AJAX auto-verify/redirect, trust-this-device for `30` days, signed-in-device trust display/revocation, and one JSON-backed System Settings client-IP config UI wired through `get_client_ip(request)`.
  - [x] Removed hardcoded fallback copy from the recent login-2FA/trusted-device/client-IP additions and rewired those labels/messages through Microsys translations in views, templates, JS, and the client-IP settings form.
  - [x] Removed the duplicate generic CRUD activity-log writes from the dynamic modal save/delete paths so signal-backed entries remain the only plain create/update/delete records for those models.

### One-line info about last verified Tests:
- `2026-05-18`: `DiscoverRunner` passed for `MicrosysDefaultRouteTests.test_setup_form_accepts_relay_env_mode_with_upstream_env_hints`, `PYTHONPYCACHEPREFIX=/tmp/microsys-pycache ./.venv/bin/python -m compileall microsys/forms.py microsys/utils.py microsys/tests/test_defaults_and_urls.py` passed, and a helper-level probe returned `{'available': True, 'reason': 'relay_configured'}` for internal relay + env/secrets using `SMTP_RELAY_HOST`, `SMTP_RELAY_PORT`, and `DEFAULT_FROM_EMAIL`.
- `2026-05-18`: `DiscoverRunner` reruns passed for `GeneralViewsTests.test_options_view_exposes_split_system_settings_entrypoints`, `test_options_view_uses_shared_selector_markup_for_font_picker`, `test_system_settings_modal_honors_requested_wizard_step_five`, `test_system_settings_modal_post_preserves_step_six_values_when_omitted`, and `MicrosysDefaultRouteTests.test_system_setup_js_keeps_last_allowed_theme_postable`; `PYTHONPYCACHEPREFIX=/tmp/microsys-pycache ./.venv/bin/python -m compileall microsys` had already passed in the same patch series.
- `2026-05-16`: After fixing the missing profile 2FA Enable key, System Settings activity-log translation normalization, and the user-detail modal staff-tier badge class, focused reruns passed for `test_defaults_and_urls` (`73` tests) and `ProfileViewsTests` + `ActivityLogViewsTests` + `SecurityHardeningViewTests` (`43` tests); the expected unrelated section-details log noise still appeared during the larger view batch but the batch passed.

### One-line info about last time edited Docs:
- `2026-05-16`: Overhauled `README.md`, `docs/FEATURES.md` (v2.2.0), `docs/admin-guide.md`, `docs/security-msrp-1.md`, and `docs/reference.md` to include Trusted Devices, Client IP Resolution, advanced 2FA UX, Dynamic Font Management, and the Step 5/6 wizard split.
- `2026-05-13`: `docs/README.md`, `docs/FEATURES.md`, `docs/admin-guide.md`, and `docs/security-msrp-1.md` were updated for the Step 3 home/public-root split, focused System Settings modal entrypoints, and CSP-safe dynamic-modal asset loading.

## Part 2: Global
### Global Standard Helpers, Shortcuts, Info, etc.:
- Reusable helper APIs:
  - `require_current_password(request)`
  - `build_archive_file_field('<field_name>')`
  - `build_settings_toggle_field(form, '<field_name>', css_class='...')`
  - `set_profile_totp_state(profile, raw_secret=..., enabled=...)`
- Common validation commands:
  - Focused defaults/render suite: `./.venv/bin/python -c "import microsys.tests.test_defaults_and_urls; import django; from django.test.runner import DiscoverRunner; django.setup(); raise SystemExit(bool(DiscoverRunner(verbosity=1).run_tests(['microsys.tests.test_defaults_and_urls'])))"`
  - Focused middleware suite: run `DiscoverRunner(...).run_tests(['microsys.tests.test_middleware'])`.
  - Focused user/modal/security suites: run targeted `microsys.tests.test_views`, `microsys.tests.test_permissions_ui`, or 2FA classes through `DiscoverRunner`.
  - Full compile check without repo `__pycache__` ownership issues: `PYTHONPYCACHEPREFIX=/tmp/microsys-pycache ./.venv/bin/python -m compileall microsys`
  - Packaging verification: build wheel/sdist, then inspect archives for `microsys/tests`, `__pycache__`, `.pyc`, and `.pyo`.
- Known local environment note:
  - `node` is not available in the current environment, so JS syntax checks via `node --check` are not currently usable.

### Global Rulesets:
- Prefer explicit reusable helpers over template shadowing or duplicated inline HTML.
- When a UI issue differs between modal/runtime/setup surfaces, verify the actual load/bind/runtime path before adding sync code.
- Keep tracker entries grounded in verified code, verified runtime behavior, or explicit user instruction.
- Do not convert user complaints into “fixed” tracker notes until the real runtime path is verified.
- Leave unrelated worktree changes untouched.
- The user explicitly wants a translation-first policy for UI/UX:
  - for new or revised UI copy, do not leave English/Arabic literals or `|default:"..."` user-facing fallbacks in templates, JS, or Python,
  - if a key is missing or wrong, fix `microsys/translations.py` instead of hardcoding text locally.
- No inline CSS/JS in HTML unless there is a real unavoidable runtime reason:
  - prefer dedicated static CSS/JS files,
  - use `json_script` and `data-*` for server-to-client data handoff,
  - if a future exception is truly required, record why in the tracker.
- Packaging should stay lean by default:
  - exclude `microsys.tests` from published distributions,
  - exclude `__pycache__`, `.pyc`, and `.pyo` artifacts from published distributions.
  - when following instructions and implementing a big change, always come up with 3 real-life scenarios that might break the change, inform me of those scenarios along with finding the appropriate fix/workaround.

### Agent Handoff Rules:
- Re-read this tracker at the start of every turn and update it after meaningful project-state changes.
- The user explicitly corrected earlier assumptions about local testing: they mount this repo over the target app, so do not assume they are running only the packaged PyPI release when they say the local checkout is active.
- The combined `test_views` + `test_defaults_and_urls` mega-run showed order-sensitive unrelated redirect failures on `2026-05-15`; the isolated reruns of those modules passed, so re-check them separately before attributing future failures to the staff-tier restore.
- The first-launch Step 2 to Step 5 empty-state bug was caused by the shared wizard helper leaving Bootstrap `d-none` on later steps; if setup navigation regresses again, inspect `microsys/static/microsys/helpers/wizard/js/main.js` before changing form markup.
- If an unconfigured install can still hit host-project URLs, inspect `microsys/middleware.py` first: the pre-setup gate is expected to block all non-allowlisted requests, including a host project's own `/` route, and its allowlist must stay aligned with both root-mounted and prefix-mounted Microsys URLs.
- If shared setup toggle labels start stacking vertically again, inspect `microsys/static/microsys/main/css/system_setup.css` before replacing the toggle renderer; `overflow-wrap: anywhere` was too aggressive for narrow Step 3 email cards.
- If shared setup toggles start overflowing their card bounds again, inspect `microsys/forms.py` `build_settings_toggle_field(...)` and `microsys/static/microsys/main/css/system_setup.css` before changing columns; Bootstrap `form-check` / `form-switch` wrapper padding and negative input margins conflict with the custom flex card layout.
- If modal wizard action buttons disappear while switching steps, inspect `microsys/static/microsys/helpers/wizard/js/main.js` before changing form markup; the helper must remove/apply Bootstrap `d-none` on Prev/Next/Submit, not only flip inline `display`.
- If setup default-language preview changes only `dir`/Bootstrap direction but leaves labels in the old language, inspect `microsys/static/microsys/main/js/system_setup.js` and `microsys/static/microsys/language/js/main.js`; Step 2 preview must go through a full reload after `persistSetupFormState(form)` so server-rendered strings refresh while wizard values are restored, but the reload should not restore the prior wizard step index.
- If the unauthenticated titlebar login button looks unthemed in darker themes, inspect `.ms-login-round` in `microsys/templates/microsys/includes/titlebar.html`, `microsys/static/microsys/main/css/titlebar.css`, and the per-theme CSS files before changing `.ms-titlebar-home`; the live unauthenticated selector is not `.login-title-btn`.
- Do not route Step 3 `email_config_use_tls` / `email_config_use_ssl` back through `build_settings_toggle_field(...)` unless the dedicated email-toggle path is intentionally retired and re-verified in browser; the user explicitly asked to change those toggles after repeated layout regressions.
- If unexpected permission groups like `Db -> Test Model` show up in user permissions, inspect `get_assignable_permissions_queryset()` plus `GroupedPermissionWidget.get_context()` before blaming the template; scaffold infra app labels and orphaned content types are now intentionally filtered there.
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
