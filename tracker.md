# Project Tracker (django-microsys)

## Part 1: Project Related
### Current Verified Snapshot:
- Verified on `2026-05-15`.
- Package/version state:
  - `microsys/VERSION` is `2.1.5`.
  - `CHANGELOG.md` now contains the stable `v2.1.5` patch release entry with the major asset and template cleanup history.
  - Root URL hijacking simplified: removed `_is_root_mounted_microsys` introspection; now uses 404-based detection — if `/` returns 404, redirect to `home_url`; if dev has a view at `/`, stay out of the way.
  - Built distributions now exclude `microsys.tests`, `__pycache__`, and compiled Python cache artifacts from both `wheel` and `sdist`.
  - Current verified implementation state:
  - Pre-setup middleware now guards all non-allowlisted host-app URLs, including a host project's own `/`, and its allowlist follows both root-mounted and prefix-mounted Microsys routes: anonymous users are redirected to `login`, authenticated superusers to `system_setup`, and authenticated non-superusers are logged out then redirected to `login`.
  - Login 2FA uses one challenge input for authenticator codes, requested email OTPs, and backup codes; TOTP secrets are encrypted at rest and OTP actions are throttled.
  - Profile TOTP setup now uses the stable `pyotp.TOTP(...)` path, falls back to username if email is blank, persists TOTP state through `set_profile_totp_state(...)` instead of the full `Profile.save()` path, and returns sanitized JSON on provisioning/QR generation or secret-persistence failures instead of raw 500 HTML errors.
  - Destructive profile security actions require current password in both UI and backend via `require_current_password(request)`.
  - System Settings/setup file fields use the Microsys custom archive widget through `build_archive_file_field(...)`.
  - System Settings/setup boolean cards use the shared toggle renderer `build_settings_toggle_field(form, field_name, ...)` across steps `2` to `5`.
  - Step 2 `allow_user_language_override` is full-width and separated from the translation matrix filters.
  - `registration_activation_mode` and `registration_throttle_enabled` are hidden/disabled until `public_registration_enabled` is enabled.
  - Step 3 and Step 4 boolean-card rows now use explicit row gutters/margins so stacked toggle rows have vertical separation instead of only horizontal spacing.
  - Step 3 `public_registration_enabled` now takes a full row; its dependent controls render on the following row as the hidden/gated pair.
  - Step 3 owns root/home access controls: `home_url` moved from Step 4, `public_root_split_enabled` + `public_root_url` split anonymous `/` from authenticated Home only when public root access is enabled, and split-off behavior still matches previous redirects.
  - Step 3 public-root/modal JS is state-scoped per form action/surface; the public-root split visibility is now controlled by one form-scoped handler using `name=` fields, with no duplicate document-level listener.
  - Step 3 split toggle is reset/disabled when public root is off, anonymous public-root fields are disabled while hidden, and `SystemSettingsForm` preserves existing Home/Public Root values when conditional destination fields are omitted from POST.
  - Step 3 Access & Security/public-root labels/help use Microsys translation keys, and the Options modal security entrypoint no longer falls back to hardcoded English.
  - Setup editor accessibility controls use ids/labels without extra `ms_*` POST names.
  - Step 2 default-language preview now reloads through the normal language switch path after persisting setup state, so previously entered non-file values survive while setup labels/help text refresh in the selected preview language, but setup no longer auto-reopens the prior wizard step after reload; `system_setup.js` is bumped to `20260514c`.
  - Dynamic modal form submits request JSON and now handles non-JSON HTTP errors without throwing a JSON parse exception.
  - AJAX requests that hit Django `SuspiciousOperation`/400 request parsing failures now receive a JSON error with the exception class instead of an HTML bad-request page.
  - Step 5 titlebar toggle-card row now uses the same `g-3 mb-3` row spacing pattern as the neighboring setup rows, so the gap before the first selection-widget row matches the gap between the selection-widget rows.
  - Step 5 titlebar settings now include `hide_on_public_unauthenticated_index`; when enabled, the shared base template hides the titlebar for anonymous requests on the public root/home path only.
  - Shared dynamic-modal loader script now carries the request CSP nonce, keeping the Options -> System Settings modal asset chain aligned with the no-inline/CSP-safe asset policy.
  - Shared setup/settings toggle cards now have dedicated content/control sub-elements and container-query reflow rules in `microsys/static/microsys/main/css/system_setup.css`.
    - Narrow toggle cards stack the switch below the label/help instead of pushing the switch outside the card boundary.
    - Step 3 `Provider STARTTLS` and `Provider SSL` no longer use the shared toggle-card renderer; they now use a dedicated compact email-toggle wrapper because the user reported repeated narrow-card rendering failures there.
    - Label/help wrapping now uses `overflow-wrap: break-word` with normal word breaking so narrow toggle cards do not collapse short labels into vertical character stacks.
    - The shared toggle control wrapper no longer uses Bootstrap `form-check` padding/negative-margin switch layout inside the custom card, so narrow Step 3 email toggles stay fully inside card bounds.
  - Step 3 email TLS/SSL switches now render through dedicated `build_email_toggle_field(...)` markup instead of `build_settings_toggle_field(...)`.
  - First-launch setup wizard step navigation now unhides server-rendered later steps by removing `d-none` in the shared wizard helper instead of only flipping inline `display`, so Step 2 to Step 5 no longer render as empty after `Next`.
  - Shared modal wizard button navigation now removes/applies Bootstrap `d-none` plus inline `display`/`aria-hidden` on Prev/Next/Submit controls, so the user-create modal keeps its action row working on step 2 after the helper-wide button-state regression.
  - Legacy full-page user create/edit/detail views were removed; routed user management is modal-only, and the obsolete `microsys/templates/microsys/users/user_form.html` fallback template is gone.
  - Shared selector toggle-card grids now have vertical padding in `microsys/static/microsys/main/css/selectors.css`, and the selectors asset version was bumped for browser pickup.
  - Shared Bootstrap-style primary badges now get explicit white foreground text from `microsys/static/microsys/main/css/main.css`, and the shared `main.css` include in `base.html` is versioned as `20260515a` so light-theme badge contrast fixes propagate instead of sticking behind browser cache.
  - Options use shared external assets in `microsys/static/microsys/main/css/options.css` and `microsys/static/microsys/main/js/options.js`; cards are draggable, order persists, System Info keeps double-card placement, related switches have explicit ids/names/labels, and drag handles use in-flow grip controls to avoid title/icon overlap.
  - Options drag placement uses RTL-aware inline start/end gap indicators rendered from `.ms-options-card`, avoiding clipped markers inside `.ms-options-panel`.
  - Setup/editor template accessibility pass:
    - language catalog, system names, translation matrix, and sidebar-builder JS-driven controls now expose stable `id`/`name` attributes and the previously unlabeled editable controls now carry labels or `aria-label`s.
    - Remaining template scan misses are outside the setup/options path and currently limited to file widgets plus a few user/profile management controls.
  - User hub mobile toolbar now wraps within one toolbar row when there is enough width, instead of being forced into separate stacked rows by mobile CSS.
  - The unauthenticated titlebar login trigger now shares the same base shape/hover treatment as `ms-titlebar-home`, and the `dark` / `gothic` / `retro` / `neon` theme overrides now target the live `.ms-login-round` selector instead of only the authenticated home button path.
  - Template/rendered-HTML asset policy cleanup is enforced in code: no inline `<style>`, executable inline `<script>`, or inline `style=` remains in the verified template/form/widget paths, and theme preview swatches use slug-based CSS classes.
  - User permission assignment UI now excludes scaffold infra app labels such as `db` / `health_check`, skips orphaned permissions whose `ContentType.model_class()` no longer resolves, groups `manage_scopes` with `manage_staff` plus the synthetic `is_staff` toggle under the dedicated staff-access card, and labels any remaining `Profile`-backed permission group with `model_user` (`Users`) instead of `model_profile` (`User Profile`).
  - The three-tier staff-management UI is restored from stash in a targeted way only:
    - `microsys.utils` now exposes presentation-only helpers `get_user_management_tier_state(...)` and `get_user_management_tier_state_for_user(...)`.
    - permissions create/edit forms render a live staff-tier preview with scope-aware warnings and `data-codename` hooks for `manage_scopes` / `manage_staff`.
    - profile, user hub, user detail modal, and the manage-users table now show consistent derived tier badges/descriptions, including the delegation badge for `manage_staff`.
    - the manage-users tutorial points at the live modal add-user trigger (`button[data-dynamic-modal]`) instead of the removed full-page create-user link.
  - Permission-step staff-tier preview styling is now self-contained for theme contrast:
    - the preview card uses explicit dark-surface overrides for `dark` / `gothic` / `neon` / `retro` even when those modes do not rely on `data-bs-theme="dark"`,
    - the tier badges inside the preview no longer rely on ambient theme `bg-primary` contrast, so `Global Staff` stays readable in the light-based themes.
  - Manage-users table staff-tier badges now use dedicated table-scoped badge classes in `tables.css` instead of raw Bootstrap `bg-*` tier classes, so Global Staff stays readable in the light-based themes there too.
  - Sidebar/titlebar runtime controls, split-step Options System Settings modals, scope-aware generated CRUD scaffolds, and MSRP-1 authorization hardening are implemented in code.

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


### Current Project's Unsolved Known Bugs:
- First-launch System Setup still has an unresolved runtime issue where the sidebar-toolbar removal warning does not match the Options modal behavior.
- Live Options -> System Settings Step 3 modal save still returns HTTP 400 in the user's mounted app; local full modal POST reproductions return 200, so the next check must use the new AJAX JSON error/class or server logs from the live app.
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
    - [ ] signed-in devices card
    - [ ] 2FA enable button in profile
    - [ ] general setup/options labels and descriptions
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
  - [x] Fixed the shared Bootstrap-style primary badge contrast path by adding an explicit readable foreground to primary badges in `main.css` and versioning the shared stylesheet include in `base.html`.
  - [x] Fixed manage-users table staff-tier badge contrast by replacing the table renderer’s raw Bootstrap tier badges with dedicated table-scoped staff-tier badge classes.
  - [x] Fixed permission-step staff-tier preview contrast so Global Staff badges stay readable in light/blue/red/gold/green/mono and the preview panel no longer stays light in dark/gothic/neon/retro.
  - [x] Restored the stashed three-tier staff-management UI without reviving the unrelated auth/config refactor: shared tier helper, live permissions preview, tier badges in profile/user hub/user detail/table, and the modal add-user tutorial selector fix.
  - [x] Removed setup preview step-index restoration so a reload no longer auto-jumps back to the translations step; non-file wizard values still rehydrate after the reload.
  - [x] Fixed the Step 2 default-language setup preview regression by restoring reload-based language switching after persisting wizard state, so labels/help text change with the selected preview language without wiping previously entered non-file values.
  - [x] Fixed the first-launch setup guard so non-Microsys app URLs, including host-project `/` routes, are blocked before configuration is complete, and added middleware/default-route regressions for anonymous, superuser, and non-superuser redirects.
  - [x] Fixed the unauthenticated titlebar login trigger styling path so `.ms-login-round` now inherits the shared titlebar shape rules and the dark/gothic/retro/neon theme overrides that previously only hit `.ms-titlebar-home`.
  - [x] Added a Step 5 titlebar toggle for hiding the titlebar on the anonymous public root/home page and wired the shared base render path to suppress only that case.
  - [x] Split public root from authenticated home when needed: Step 3 now exposes the main Home URL, a public-root split toggle, and a separate anonymous public-root URL, with middleware/logout redirects honoring the split only when public access is enabled.
  - [x] Fixed Step 3 public-root/home setup state collisions by scoping saved wizard state to the specific form action and bumped the setup JS/CSS asset versions so browsers fetch the latest Step 3 visibility logic.
  - [x] Reworked Step 3 public-root visibility logic to remove the duplicate document-level listener, use one form-scoped controller, reset/disable the split toggle when public root is off, and bump `system_setup.js` to `20260513c`.
  - [x] Fixed Step 3 side effects from hidden/conditional destination fields by preserving omitted Home/Public Root values server-side.
  - [x] Removed `name=` from JS-only setup editor controls and added active split-save and field-count regressions; local modal POST reproduction still returns 200, but the user's live 400 remains pending diagnosis.
  - [x] Restored Options card drag handles to the previous `bi-grip-vertical` icon and moved the handle out of absolute overlay positioning so it no longer overlaps the card title icon.
  - [x] Added translation-backed Step 3 Access & Security/public-root labels, removed the remaining hardcoded Options security-label fallback, and nonce-protected the shared dynamic-modal loader for stricter CSP deployments.
  - [x] Reduced setup/options accessibility audit noise by adding missing ids/names/labels to Options switches and JS-driven setup editor controls, and added regressions for those template surfaces.
  - [x] Fixed shared wizard button visibility handling so Bootstrap `d-none` is removed/restored for Prev/Next/Submit, preventing the user-create modal step-2 action-row regression.
  - [x] Removed obsolete unrouted full-page user create/edit/detail views, their stale exports, the dead `user_form.html` template.

### One-line info about last verified Tests:
- `2026-05-15`: After the shared primary-badge contrast fix and `main.css` cache-bust update, Django `DiscoverRunner` reran `test_defaults_and_urls` (`68` tests) and passed; earlier same-day reruns also passed for `test_tables` (`20` tests), `test_permissions_ui` (`6` tests), `test_utils` + `test_context_processors` + `test_tables` (`99` tests), and `test_views` (`85` tests).

### One-line info about last time edited Docs:
- `2026-05-13`: `CHANGELOG.md` gained a new `v2.1.6` entry, and `docs/README.md`, `docs/FEATURES.md`, `docs/admin-guide.md`, and `docs/security-msrp-1.md` were updated for the Step 3 home/public-root split, focused System Settings modal entrypoints, and CSP-safe dynamic-modal asset loading.

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


TODO by DeBeski (DO NOT TOUCH)
- re-build the three tier user staff visual ui that was lost in the last incident, for permissions, profile, and user management views.
- the per page options are not reflecting visually which option is selected even tho the get works and the url is updated with such option. tested on manage_users and activitylog.
