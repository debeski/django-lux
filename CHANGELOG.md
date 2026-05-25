# Changelog

This file owns the release history for `django-microsys`.

> Only stable versions of django-microsys are available for install through pip, a list of them can be found on PyPI [here](https://pypi.org/project/django-microsys/#history).

## v2.2.7

- **Dynamic Modal Loading Fallback**: Refined `dynamic_modal/js/main.js` loading behavior to keep real previous modal content as the sizing fallback when available, ignore empty template comments, cover fallback content with a theme-aware loading overlay, and use a self-contained default skeleton only for first/empty modal loads while preserving the existing AJAX modal contract.
- **Prism And Aether Theme Surface Coverage**: Added Prism/Aether overrides for Microsys-owned `.archive-file-*` upload widgets and titlebar logo treatment surfaces, and extended `options.css` System Settings action tile overrides to Aether.
- **Aether Theme Picker Surface**: Added the missing shared `.ms-theme-preview--aether` swatch in `template_cleanup.css` and bumped the base template asset version so Aether appears with a proper surface in System Settings and sidebar theme pickers.
- **Mono Theme Picker Surface**: Updated the shared `.ms-theme-preview--mono` swatch to a clean diagonal split between white and light monochrome gray, making Mono visually distinct from the darker Prism picker surface without making it read as a dark theme.

## v2.2.6

- **User Existence Report**: Added a permission-gated User Report dynamic modal with print/PDF-friendly layout and XLSX export. The report summarizes identity/status, staff tier, activity counts, recent logs, device/network history, browser/OS observations, trusted-device context, request counts, and estimated active time.
- **Durable Device And Presence History**: Added DB-backed `UserKnownDevice` and `UserPresenceSession` history. Microsys now records forward-looking known-device and presence-session data using a signed neutral `microsys_device_id` cookie stored only as a hash, while continuing to use Django sessions for authentication and `TrustedDevice` for 2FA trust/security decisions. IP observations use the existing System Settings-aware `get_client_ip(request)` helper.
- **Report Access And Export Hardening**: Added `user_can_view_user_report(...)` so User Reports require user-directory access, target-management access, and activity-log access. XLSX export normalizes timezone-aware values for Excel compatibility and avoids exposing raw session keys, device tokens, trusted-cookie tokens, or secrets.
- **Titlebar Logo Treatments**: Added Step 6 logo treatment controls for titlebar branding, supporting unchanged, adaptive plate, halo, and contrast-assist modes with plate shape choices for better logo visibility across themes.
- **License Update**: Updated the project license to be under `MIT license`.

## v2.2.5

- **Trusted Session Precedence**: Added a Step 3 `Prevent multiple active sessions` security toggle, including DB migration, `MICROSYS_CONFIG`, setup import/export, and `microsys_settings` coverage. Trusted sessions can now be created from Profile through a current-password-confirmed `Trust This Device` action as well as from 2FA, a newly trusted session can force out all other sessions when the toggle is enabled, and untrusted sessions can no longer revoke trusted sessions from Profile.
- **Trusted Device Helper Layer**: Centralized trusted-device cookies, token hashing, session metadata sync, trust lookup, trust issuance, linked trust revocation, and single-active-session enforcement in a shared `microsys.trust` module while keeping the existing 2FA helper entrypoints compatible.

## v2.2.4

- **Optional Nav Bar**: Added a System Settings-owned authenticated Nav Bar with hierarchy and browser-session history styles, a visual hierarchy editor with translated manual nodes, an allowed Options style override, and a runtime `microsys_navbar_crumbs` hook for dynamic record or tab crumbs. Follow-up polish keeps one browser-session history trail with language-aware labels, hides Microsys system routes from the hierarchy builder, wraps system views under an unclickable `System` crumb, keeps URL-backed hierarchy crumbs clickable, avoids generic `index` leaf collisions with app index nodes, removes the Nav Bar background smudge, separates Nav Bar setup into its own Step 5 after Sidebar, and can seed an enabled empty first-launch Nav Bar tree from configured sidebar accordions.
- **Theme Preview And Switching Polish**: Added a short fade veil for explicit theme changes, paused sidebar repaint during the swap, and allowed Step 7 / Appearance preview to temporarily load a disabled theme stylesheet without widening the runtime theme allowlist.
- **Collapsed Sidebar Parent Alignment Fix**: Fixed Icons Only collapsed sidebars so folder/parent accordion rows stay centered, hidden labels do not linger during collapse, and redundant `flex-grow` behavior no longer pushes parent icons out of place.
- **Sidebar Step 4 Preservation Fixes**: Stopped System Settings from destructively resetting stored sidebar child options when the parent sidebar toggle is off, kept the toolbar child toggle disabled with the sidebar without auto-unchecking it, and synced visible Step 4 sidebar behavior controls back into hidden `sidebar_config` state before save.
- **Sidebar And Theme Polish**: Fixed sidebar active-state matching so exact child URLs win over parent prefix matches, softened Mono sidebar active highlights with inverted active icons, and aligned advanced-filter primary action icons with Mono, Gothic, and Retro button surfaces.
- **Options System Settings Card Refresh**: Reworked the Options System Settings card into a compact tile grid with icons, translated titles, and Microsys tooltip descriptions for each settings area.
- **Initial Setup Step Navigation**: Added a theme-aware, bullet-based step bar to the first-launch System Setup page so developers can jump between setup steps directly while keeping the existing wizard Next/Prev flow synchronized.
- **Portable Setup Import/Export**: Expanded System Settings JSON import/export to include dynamic font settings and added one-time first-launch `BASE_DIR/config.json` bootstrapping, with a translated finish-from-import action in the setup UI.
- **System Settings Management Command**: Added `microsys_settings` for dev/operator workflows around the singleton: status, configure/unconfigure, guarded delete/reset, and portable JSON export/import.
- **Options And Profile Interaction Fixes**: Added pointer cursors for shared Microsys toggles, corrected Options card reorder handles to keep grab/grabbing cursors on the full handle surface, and kept Profile confirm-password modals open through server validation so wrong-password errors render inline instead of falling back to page messages.
- **Profile Activity Classification Fix**: Routed virtual session-revoke activity rows into System Interactions instead of Recent Activity, keeping Profile timelines aligned with Microsys-owned security events.
- **Release Metadata And Scaffold Follow-Up**: Added Django 6 classifiers to the main package and optional SSO package, updated generated nginx services to restart automatically in scaffolded `compose.yml`, and clarified Central Staff wording in the admin guide.

## v2.2.3

- **utils.py Cleanup**: cleaned up the utils.py helpers file a bit, will split into modules in next versions.
- **get_app_version helper**: Added a new utils.py helper to fetch individual django app version from VERSION file within the calling function's directory.

## v2.2.2

- **Email Relay Environment Support**: Fixed Step 2 email readiness gate to properly recognize internal SMTP relay configurations using `SMTP_RELAY_*` environment variables alongside `DEFAULT_FROM_EMAIL`, resolving deployment issues with relay-based email delivery.
- **System Settings Modal Step Resolution**: Fixed stale step resolver in `DynamicModalManagerView` to correctly handle wizard steps 0-5 after the Step 5/6 split, preventing invalid modal rerenders.
- **Single-Step Modal Preservation**: Fixed System Settings modal saves so single-step POSTs that omit Step 6 fields (themes, typography, table density) now preserve existing server-side values instead of failing validation.
- **Typography Selector Unification**: Replaced the Options typography card's custom font strip with the shared selector pattern used by language and density cards for consistent UI behavior.

## v2.2.1

- **Appearance Wizard Restructuring**: Compacted Step 5 to be Titlebar Settings only, and moved the Table Density section to the bottom of Step 6 alongside Themes and Typography settings for logical appearance grouping.
- **Dynamic Choice Translation**: Wired `SystemSettingsForm` choice labels (`default_table_density`) to dynamically translate options based on the active session language, resolving a translation gap between Options and Setup views.
- **Secure Referer Hardening**: Hardened the redirection utility to validate the `HTTP_REFERER` against both the request host and `settings.ALLOWED_HOSTS` wildcards before redirection, backed by the new automated `test_safe_referer` test suite.

## v2.2.0

- **Dynamic Font Management System**: Implemented a centralized font registry in `microsys/fonts.py`, supporting local font hosting with automatic CSS variable injection (`--ms-main-font`) and FOUC prevention.
- **Typography Configuration**: Added system-wide controls for allowed fonts and language-specific default fonts, manageable through the new Appearance setup step.
- **User Font Overrides**: Introduced a Typography card in the Options panel, allowing users to choose their preferred font from the system-approved allowlist.
- **Appearance Wizard Restructuring**: Split the legacy Appearance step into Step 5 (UI & Layout: Tables and Titlebar) and Step 6 (Appearance: Themes and Typography) for better organizational clarity.
- **Centralized Asset Management**: Consolidated all system fonts under `static/microsys/fonts/` with lowercase normalization for reliable cross-platform serving.

## v2.1.9

- **Profile 2FA UX Fixes**: Added missing `enable` translation keys to resolve blank setup buttons and switched the verify script from `disabled` to `readOnly` to prevent OTP code stripping during form auto-submission.
- **Staff Tier Badge Alignment**: Updated the user-detail modal to use shared staff-tier badge classes instead of raw Bootstrap colors, ensuring Global Staff badges remain legible in light themes.
- **Activity Log Normalization**: Hardened the activity-log model-name translation helper to handle varied name formats (spaced/underscored/dotted) consistently before lookup.
- **Translation-First Policy Enforcement**: Rewired recent 2FA, trusted-device, and client-IP UI copy through the Microsys translation framework, removing hardcoded English/Arabic literals from Python, templates, and JS.
- **Regression Fixes**: Restored missing 2FA resend cooldown feedback and fixed the pre-setup middleware gate to properly block host-project root routes before configuration is complete.

## v2.1.8

- **Advanced Login 2FA**: Introduced email-only auto-send with a 120s resend cooldown, authenticator-first default for mixed accounts, and AJAX-driven auto-verification with automatic form submission for seamless login.
- **Trusted Device Persistence**: Added a `TrustedDevice` model to track browser trust for 30 days, integrated into session metadata and managed directly from the user profile with revocation support.
- **Centralized Client IP Resolution**: Implemented a unified `get_client_ip(request)` helper with a dedicated System Settings configuration block for resolution modes, trusted proxy hops, and custom headers.
- **Staff Tier UI Restoration**: Restored the three-tier staff management system (Global, Central, Scoped) with live permission previews, tier-based user hub badges, and high-contrast table badges for all themes.
- **UI Contrast and Asset Versioning**: Applied explicit white foreground text to primary badges across all themes and bumped shared stylesheet/script versions to ensure browser pickup of contrast and layout fixes.
- **Generic CRUD Log Optimization**: Suppressed duplicate activity-log entries during generic modal operations, prioritizing canonical signal-backed records for create/update/delete actions.

## v2.1.7

- **Setup Language Preview Stability**: Prevented first-launch default-language preview from reloading the setup wizard, preserving already entered Step 1 names and selected logo/favicon files while still applying immediate language direction feedback.
- **Default Language Persistence Fix**: Rehydrated the setup language catalog and system-name editor from the saved hidden form state after preview restores so the selected default language is not overwritten back to English before save/login cycles.
- **Table Page Size Active State Fix**: Fixed Microsys-managed tables so inherited base `microsys_per_page` defaults no longer mask `?per_page=` request values, allowing Manage Users and Activity Log page-size chips to correctly show the selected option.

## v2.1.6

- **Access & Security Routing Controls**: Moved the global `home_url` controls into Step 3 / Access & Security, added an optional split between authenticated Home and anonymous public-root destinations, and kept prior redirect behavior unchanged when the split is disabled.
- **Public Root Runtime Alignment**: Root/login/logout redirect behavior and the anonymous public-home titlebar-hide rule now follow the optional anonymous public-root target instead of assuming all users share the same destination.
- **Setup And Options Reliability**: Fixed setup/System Settings state restore so one modal step no longer overrides another after reloads, hardened public-root dependent-field visibility inside dynamic modal flows, and bumped setup asset versions for reliable browser refreshes.
- **Translation And CSP Polish**: Added Microsys translation coverage for the new Access & Security section heading and Step 3 public-root controls, removed the remaining hardcoded Access & Security modal label fallback, and made the dynamic-modal loader script nonce-aware for stricter CSP deployments.
- **Options UI Polishing**: Restored the `bi-grip-vertical` icon for Options card drag handles and transitioned them from absolute positioning to in-flow layout to prevent overlapping with card icons and titles.
- **Setup and Options Accessibility**: Reduced audit noise by adding missing stable IDs, names, and ARIA labels to Options switches and JS-driven setup editor controls.
- **Documentation Refresh**: Updated the README, Features reference, admin guide, and MSRP-1 security standard to reflect the Step 3 routing split, the new focused System Settings modal entrypoint, and CSP-safe modal asset loading.

## v2.1.5

- **Missing Root Redirect Fix**: Fixed an issue in `MicrosysMiddleware` where `_missing_root_redirect` improperly returned `None` instead of the original `HttpResponse` when allowing a public root request to proceed, which previously caused an `AttributeError: 'NoneType' object has no attribute 'status_code'` in subsequent middleware.
- **Middleware Rename**: Renamed the core framework middleware from `ActivityLogMiddleware` to `MicrosysMiddleware` to better reflect its comprehensive responsibilities (thread-locals, setup guards, device tracking). A backward-compatibility alias `ActivityLogMiddleware = MicrosysMiddleware` ensures existing host projects will not break.
- **Simplified Root URL Hijacking**: Replaced the complex `_is_root_mounted_microsys` URL introspection and auth-branching logic with a clean 404-based approach. If `/` returns a 404 (no dev view), microsys redirects to the configured `home_url`. If the dev has their own view at `/`, microsys stays out of the way. The `public_root` setting gates anonymous access: when off, anonymous users at `/` are sent to login instead of `home_url`.
- **Dynamic Auth Redirects**: `LOGIN_REDIRECT_URL` is now dynamically synced to the configured `home_url`. `LOGOUT_REDIRECT_URL` respects `public_root` — when enabled, logout redirects to `home_url`; when disabled, logout redirects to the login page.
- **Asset and Template Cleanup**: Performed a major cleanup of abandoned static assets and templates. Removed obsolete Plotly and Flatpickr libraries, deleted the abandoned dashboard implementation, and purged unreferenced CSS/JS files and redundant template helpers to reduce package weight and improve maintainability.
- **Titlebar Login Button Theming**: Fixed the unauthenticated login trigger (`.ms-login-round`) to correctly inherit global titlebar shape rules and apply appropriate theme-specific styling for Dark, Gothic, Retro, and Neon modes.
- **Wizard Navigation Fix**: Hardened the shared wizard helper to properly manage Bootstrap `d-none` visibility during step transitions, ensuring later setup steps render correctly after navigation.

## v2.1.4

- **User Creation Bug Fix**: Fixed an issue where users could not be created due to missing `save` button.
- **Retired Old User Forms**: Removed old user creation forms that were no longer needed.

## v2.1.3

- **Version Bump**: Updated version to 2.1.3 due to linting changes.

## v2.1.2

- **Improved Management Command**: Added fallback protection for the 'migrate_plus_populate' management command to gracefully handle cases where no 'populate' command is installed, preventing deployment failures and providing helpful guidance to developers.

## v2.1.1

- **Packaging Hygiene Tightening**: Excluded `microsys.tests` from package discovery and pruned repository test modules plus Python cache artifacts (`__pycache__`, `.pyc`, `.pyo`) from published `wheel` and `sdist` distributions so the release payload stays focused on runtime code and shipped assets.
- **MSRP-1 Policy Clarification**: Promoted the no-inline asset rule into the core MSRP-1 standard, explicitly documenting that runtime HTML should avoid inline CSS, inline `style=` attributes, and executable inline JavaScript unless there is a documented unavoidable need.
- **Documentation And Release Organization**: Aligned the live docs/release metadata around the `2.1.1` patch line by keeping the security-policy source explicit, preserving the layered docs structure, and recording the packaging/security policy changes in the release history.

## v2.1.0

- **Public Registration And Email Delivery Release**: Finalized the core public registration playground together with the UI-first Microsys email delivery system. Delivery path (`direct` vs `relay`) and secret storage (`env` vs `encrypted_db`) are now first-class runtime settings, and generated Docker projects use the internal `smtp-relay` sidecar pattern for UI-managed upstream SMTP delivery.
- **Security And 2FA Hardening**: Unified login 2FA challenges across authenticator codes, requested email OTPs, and backup codes; encrypted TOTP secrets at rest; hashed backup codes at rest; enforced POST-only 2FA mutators; added current-password confirmation for destructive profile security actions; and hardened TOTP setup to return sanitized JSON instead of raw 500 pages when provisioning or secret persistence fails.
- **System Settings And Setup UX Refresh**: Expanded setup/System Settings with shared toggle-card rendering across steps, explicit gating for registration-dependent controls, custom Microsys file widgets for import/logo/favicon, responsive toggle-card layout fixes, and improved setup/options parity for the email, sidebar, titlebar, theme, and language surfaces.
- **Options And Profile UX Refresh**: Reworked Options onto shared external CSS/JS assets, merged the new visual card language across the page, restored Autofill and Reset Defaults as standalone cards, added draggable persisted card ordering with a double-width System Info card, exposed signed-in device management in profile, and improved user-hub mobile toolbar behavior on small screens.
- **Template Asset Policy Cleanup**: Removed inline template CSS and executable inline JS across the shipped HTML surfaces, moved behavior into shared static assets, switched theme preview swatches to shared CSS classes, and added regression coverage so the framework stays CSP-friendly by default.
- **Packaging And Dependency Baseline**: The `2.1.0` package declares the runtime dependencies the shipped features require, including `pyotp`, `qrcode`, `psutil`, and `cryptography`. `cryptography` is required for encrypted TOTP secrets and UI-managed encrypted SMTP secrets.

## v2.1.0b1

- **UI-First Email Delivery Setup**: Reworked System Settings email delivery into two independent controls: delivery path (`Direct SMTP from web service` or `Internal SMTP relay`) and secret storage (`Environment / secrets` or `Encrypted database secret`). This supports direct SMTP with DB-backed encrypted secrets and relay-based delivery with DB-backed encrypted secrets.
- **Generated SMTP Relay Integration**: Updated scaffolded Docker projects so the `smtp-relay` sidecar can read UI-managed upstream SMTP settings from `SystemSettings.email_config`, decrypt the password with the project secret, and deliver externally while the `web` and `celery` services stay isolated on the internal network.
- **SMTP Relay Scaffold Updates**: Generated `compose.yml` now gives the relay service the same Django/database settings needed to read UI configuration. Environment SMTP variables remain only a bootstrap/fallback path for projects that intentionally keep mail config outside the UI.
- **Public Registration And Email 2FA Readiness**: Public signup and email 2FA now gate against the selected delivery path and selected secret-storage backend instead of a single overloaded SMTP setting.
- **2FA Secret Migration Merge**: Folded TOTP secret widening/encryption into `0002_public_registration.py` and removed the separate `0003_totp_secret_encryption.py` migration before release.
- **Docs Refresh**: Updated registration, reference, and MSRP-1 docs to describe direct-vs-relay delivery, env-vs-encrypted secret storage, and the generated SMTP relay behavior.

## v2.1.0b0

- **Public Registration Playground**: Added core public registration feature (disabled by default) with email-first signup, verification tokens, activation modes (`auto_login_after_verify` and `verified_pending_approval`), and superuser approval/rejection workflows. Includes provenance badges on user profiles and integration with Microsys mail delivery configuration.
- **Optional SSO v1 Scaffolding**: Implemented separate provider and client packages under `optional_packages/` as `django-microsys-sso` and `django-microsys-sso-client`. OIDC-only with cross-platform flat claims (`microsys_sso_role`, `microsys_sso_client_id`) for generic PHP/.NET/JS/Java/Go/mobile/desktop clients.
- **Microsys Email Delivery Configuration**: Added `SystemSettings.email_config` with `env` and `encrypted_db` modes for SMTP configuration. Supports secure secret storage via `cryptography`, export/import redaction, and gates public registration and email 2FA on mail readiness.
- **Unified Login 2FA Challenge**: Consolidated TOTP, email OTP, and backup code entry into a single input field. Email OTP requires explicit user request to send; authenticator codes and backup codes work directly.
- **Runtime Sidebar Controls**: Added `sidebar_config.enabled` to completely disable sidebar rendering and related UI controls. Added `sidebar_config.collapse_mode` with `locked_expanded` option that hides the desktop collapse toggle without reserving space.
- **Signed-In Devices Management**: Added user profile view of active Django sessions (device, IP, last seen, expiry) with POST-only session revocation for non-current devices.
- **Docker SMTP Relay**: Generated Docker projects now route email through an internal `smtp-relay` sidecar that joins both public and internal networks, keeping `web` and `celery` containers isolated while enabling upstream SMTP egress.
- **Global Staff vs Central Staff Tiers**: Implemented `manage_scopes` permission to distinguish Global Staff (can manage scopes and all users) from Central Staff (scopeless-only user management). Added tier-based enforcement in user creation, editing, and queryset filtering.
- **Table Platform Hardening**: Microsys-managed tables now respect `Meta.microsys_table`, `Meta.microsys_density`, `Meta.microsys_per_page`, `Meta.microsys_per_page_options`, and `Meta.microsys_actions`. Stock host tables auto-capture into the Microsys renderer with rounded corner clipping fixes.
- **Options Security & UX**: Restricted diagnostics to superusers and Global Staff only. Fixed theme persistence without sidebar JS dependency. Modernized System Settings card styling with dark-theme action buttons and split-step modal save behavior.
- **Security Hardening**: MSRP-1 enforcement for modal CRUD, sections, user management, activity log, and 2FA mutators. Backend backup codes now hashed at rest. POST-only enforcement for 2FA state changes.
- **Theme & UI Polish**: Dark/retro/gothic/neon titlebar sidebar toggle transparency fixes. Non-primary button contrast improvements across all themes. Table card corner clipping fixes. Options and System Setup action button dark-theme styling.

## v2.0.3

- **Scan Button Event Isolation**: Stopped clicks and pointer events on the ScanLink button from bubbling into the archive file drop zone, preventing accidental native file-picker opens when starting a scan.
- **Inline Scan Status Feedback**: Added per-widget status updates while a scan is running, restored the original file-widget metadata after completion/reset, and surfaced a specific stalled-helper message for long-running scan jobs.
- **Scanned PDF Filename Stability**: Switched generated scan filenames to timestamped `scanned-document-...pdf` names instead of deriving names from the input field id/name.
- **Scan Timeout Follow-Up**: Passed an explicit 5-minute timeout to the ScanLink result wait so stalled scanner/helper states fail with a clearer client-side message.

## v2.0.2

- **Packaging Republish**: Published a `2.0.2` package/version metadata update after `2.0.1`. The PyPI wheel contents are otherwise unchanged from `2.0.1`.

## v2.0.1

- **REST-First ScanLink Helper**: Refactored the shared ScanLink browser helper around the loopback REST contract so form pages probe helper health, start a scan job, poll status, and fetch the finished PDF without depending on Socket.IO.
- **Per-Button Scan State**: Reworked the scan button controller to track the active job per clicked file widget instead of broadcasting status changes across every `.scan-btn` on the page.
- **Translation-Backed Scan Messaging**: Extended the shared file input template with localized scan labels and error strings so helper availability, busy state, cancellation, timeout, and scanner failures surface through the normal Microsys translation layer.
- **Direct File-Field Injection Flow**: Kept ScanLink scanning aligned with the shared Microsys archive file widget by attaching the scanned PDF directly to the target `<input type="file">` and dispatching the standard change event.
- **Options Sidebar Authorization Fix**: Replaced the old Options-only internal token with `__ms_authenticated__`, aligning sidebar visibility with direct `/sys/options/` access for any authenticated user.

## v2.0.0

- **Sidebar Permission Inference for Function-Based Views**: Added URL pattern-based permission inference that correctly extracts permissions for function-based views. The logic now parses URL namespace as app label and URL name prefix as model name (e.g., `documents:outgoing_list` → `documents.view_outgoing`). This ensures sidebar items are only visible to users who have the actual view permission for the associated model.
- **Strict Sidebar Permission Enforcement**: Simplified `_user_has_sidebar_permission` to strictly check permissions without staff fallback. Users must have the actual permission (e.g., `documents.view_outgoing`) to see the sidebar item. No implicit staff access - explicit permissions are required.
- **System Route Permission Updates**: Added explicit system route tokens in `SYSTEM_ROUTE_META`, including authenticated-user visibility for the options/settings sidebar item.
- **Breaking Change**: Staff users will no longer see sidebar items for models they don't have explicit view permissions for. Ensure users have the appropriate `app.view_model` permissions assigned.

## v1.87.0b4

- **Global Staff vs Central Staff Tier System**: Added new `manage_scopes` permission to separate non-scoped staff into two distinct authorization tiers. Global Staff (`is_staff=True, scope=NULL, manage_scopes permission`) can create/manage scopes and ALL users. Central Staff (`is_staff=True, scope=NULL, NO manage_scopes`) can only create/manage scopeless (NULL scope) users, completely blind to scoped users and their data. Only superusers can create Global Staff.
- **Permission Widget Fix**: Fixed the queryset filter in `CustomUserCreationForm` and `CustomUserPermissionsForm` that was excluding `view_activitylog` and `manage_scopes` permissions from the permission widget. Now both activity log access and Global Staff assignment permissions appear correctly in the UI.
- **Tier-Based User Management Enforcement**: Added `is_global_staff()` and `is_central_staff()` utility functions, updated `can_manage_target_user()` to reject Central Staff from managing scoped users, modified `UserListView` queryset filtering to hide Global Staff from Central Staff, added view-level enforcement in `create_user` and `edit_user` to prevent Central Staff from creating/editing Global Staff users, and added form-level enforcement in `CustomUserPermissionsForm` to strip `manage_scopes` from Central Staff submissions.
- **UI: Hide Scope Field from Central Staff**: Changed from showing disabled scope field with help text to completely hiding it using `HiddenInput` widget. Central Staff users no longer see any scope-related UI when creating or editing users.

## v1.87.0b3

- **CRITICAL: Widget Queryset Caching Fix**: Fixed a security bug where the permission widget (`GroupedPermissionWidget`) was using the class-level cached queryset instead of the filtered queryset. This allowed non-superusers to see and assign permissions they didn't have. Fixed by storing `_filtered_queryset` on the widget and prioritizing it in `get_context()`. Now users can only see and assign permissions they possess.
- **CRITICAL: Sidebar Permission Security Fix**: Fixed a critical security issue where sidebar items with no permissions were visible to ALL users. The `user_has_any_permission_tokens` function returned `True` for empty permissions, making items without explicit permissions visible to everyone. Fixed by adding `default_visible_to_all=False` parameter - now items MUST have explicit permissions to appear in sidebar. Superusers can see all sidebar items regardless of permissions.
- **CRITICAL: Modal Form Parameter Fix**: Fixed `DynamicModalManagerView._get_form_kwargs()` which was passing `request` via `**kwargs` detection to forms. This caused `TypeError` in forms like `CustomUserCreationForm` that don't accept `request`. The fallback then stripped ALL kwargs including `user`, completely breaking permission filtering. Fixed by only passing `request` when explicitly named as a parameter (not via `**kwargs`).
- **Section Manager Context Menu Fix**: Fixed the fallback navigation bug where clicking "view" on section manager entries redirected to `/${app}/${id}/` instead of opening the smart modal. Added `isSectionManagerActive()` detection to `main.js` fallback handlers so they bail out when `section_manager.js` is active.
- **`manage_sections` Permission Integration**: Enhanced `filter_context_actions()` utility to properly respect `manage_sections` permission across all section-related context menu actions, ensuring consistent permission enforcement between server-side and client-side action filtering.
- **Staff User Directory Authorization Fix**: Updated `user_can_view_user_directory()` to accept either `auth.view_user` OR `microsys.manage_staff` permission. Staff users granted via `manage_staff` permission can now access `/sys/users/` and see the manage users icon without requiring explicit `auth.view_user`.
- **Auto-Grant `view_user` Permission**: `CustomUserCreationForm` and `CustomUserPermissionsForm` now automatically grant `auth.view_user` permission when saving a user with `is_staff=True`, ensuring backward compatibility and reducing manual permission management.
- **Translation Fallback Hardening**: Updated form help text fallbacks to use English strings instead of Arabic, ensuring consistent UX when translations are missing.

## v1.87.0b2

- **Governed Theme Allowlist**: Added `SystemSettings.allowed_themes` plus `allow_user_theme_override`, wired setup/System Settings to a theme-allowlist matrix, filtered runtime theme exposure to the approved set, and forced saved disallowed themes back to the system default.
- **Sidebar Density and Collapse Modes**: Expanded sidebar config with `show_icons`, `density`, `allow_user_density`, and `collapse_mode`, added density controls to setup, Options, and the live sidebar toolbar, and normalized `show_icons=false` away from the icon-rail collapse mode.
- **Titlebar Layout Controls**: Added admin-owned titlebar controls for logo/home visibility, home-button shape, title alignment, title size, bar height, and surface style, with data-driven template/CSS wiring and a mobile-safe alignment fallback.
- **Config and Preference Hardening**: Extended `get_system_config()`, context, and preferences persistence to respect theme allowlists, sidebar density locks, locked-expanded sidebars, branding URL normalization, and optional `psutil` / TOTP dependencies in lean environments.
- **Migrator Error handling**: Added a clear visual error output to debug terminal when any of the migrator tasks fails.

## v1.87.0b1

- **System Navigation Authorization Cleanup**: The sidebar discovery layer, user hub, and dashboard now follow the same helper-backed MSRP authorization rules for Users, Sections, and Activity Log instead of older `is_staff`/typo’d-permission checks.
- **Legacy User Reset Route Alignment**: `/sys/reset_password/<pk>/` now requires `auth.change_user` and the same `can_manage_target_user()` staff/scope/superuser target checks as the hardened user-management modal flows, and its invalid-form fallback no longer redirects to the removed `edit_user` route.
- **Explicit Activity-Log Authorization**: The activity-log list/detail views now require the explicit `microsys.view_activitylog` permission (with a temporary legacy alias check) instead of granting access to every staff user by default.
- **Scope View Authorization Cleanup**: The older scope-management AJAX endpoints now fail with `403` for non-superusers instead of redirecting, and the superuser-only manager stays reachable even when scopes are currently disabled.
- **2FA State-Handling Rehab**: Converted 2FA mutators and resend flows to POST-only, switched backup codes to hashed-at-rest storage with legacy in-place migration, validated post-OTP redirects against allowed hosts, and removed secret-leaking debug prints from the 2FA flow.
- **Autofill/API Exposure Reduction**: Stopped autofill/detail APIs from expanding reverse OneToOne relations such as `user.profile`, and routed those reads through the model default manager so scoped query behavior is preserved automatically.

## v1.87.0b0 *all versions past this are not backwards compatible*

- **Table Meta Contract Repair**: Fixed the `django_tables2` patch layer so host tables again honor `Meta`-level `microsys_table`, `microsys_density`, `microsys_per_page`, and `microsys_actions` settings instead of accidentally reading only the runtime `_meta` wrapper.
- **Broad Suite Cleanup**: Removed the remaining stale failures in `test_utils_discovery`, `test_models`, and `test_tables`; the full `microsys.tests` suite now completes green at `247` passing tests.
- **MSRP Security Hardening Phase 1**: Locked down dynamic modal CRUD and section-management routes with backend authorization, enforced self/staff/scope rules on profile and user modals, removed login-only access to operational diagnostics, and sanitized previously raw JSON error payloads.
- **Section Route Model Allowlisting**: Tightened the section AJAX endpoints so `get_section_details`, `delete_section`, and subsection CRUD only operate on models discovered through the Microsys sections registry instead of accepting arbitrary `model=` tokens from the request.
- **Privileged Detail Parity**: Aligned user-detail and activity-log detail views with the newer security contracts so user detail access follows the same staff/scope/superuser rules as user-management modals, while non-superusers cannot open superuser-created activity-log entries from the detail modal.
- **User Directory Authorization Parity**: Embedded recent-activity snippets on user detail only render when the caller also has `microsys.view_activitylog`.

## v1.20.6

- **MSRP Stale-Code Compatibility Cleanup**: Normalized media URL fallback handling for uploaded branding assets, restored `get_system_config()` language-name fallback behavior when only a generic system name is provided, and added backward-compatible `form_class` / `table_class` / `filter_class` aliases to `LazyModelClasses`.
- **Middleware and Root-Route Contract Cleanup**: Brought the setup/root middleware contract in line with the newer security-first behavior, including explicit setup redirect behavior for unconfigured anonymous root requests and test-backed thread-local handling through the actual middleware execution path.
- **Legacy Test Harness Stabilization**: Guarded the optional external `storage` import in `microsys.tests.test_m2m`, updated stale middleware/IP-header expectations, and verified the refreshed utility/context/middleware/default-route slice against the current MSRP behavior.

## v1.20.5

- **Table Surface and Theme Conformance**: Expanded the vNext table platform across the shipped themes by adding Retro table tokens, light/color theme-owned header and row tokens, dark-theme empty-state and density-card tokens, softer header gradients, and wrapper/shell curve fixes including the mono-specific table-card opt-out.
- **Density and Footer Polish**: Added the compact in-footer density switcher beside per-page controls, suppressed it automatically on tables with forced `Meta.microsys_density`, and completed the runtime wiring for system default density plus per-user density/page-size persistence.
- **Filter Helper Contract Clarification**: `set_field_attrs()` now preserves real labels by default, while `setup_filter_helper()` and `advanced_filter_helper()` intentionally default to inline placeholder labels for filter bars via explicit `inline_labels=True` behavior.
- **Activity Log Filter Stability**: Aligned the activity-log page with the working `FilterView + SingleTableView` composition so the filter helper is applied consistently on initial render and follow-up GET interactions.
- **Theme-Specific Filter and Profile Fixes**: Fixed filter search button/icon contrast for `gothic`, `retro`, and `mono`, restored the intended filter-field surface in `gothic` and `retro`, and normalized the profile action-pill sizing in `gothic` and `retro`.
- **Activity Log and Detail UX Hardening**: Refreshed the activity-log detail modal into structured cards, masked OTP/TOTP secret-like values in saved diffs and rendered detail payloads, and made auto-generated detail labels follow the live MicroSys translation contract instead of raw English `verbose_name` values.
- **Options and System Settings Refinements**: Split the Options entry for System Settings into focused branding/languages/sidebar launches, restored missing `email_2fa` and `public_root` translation coverage, and modernized System Settings branding uploads onto the shared Microsys file-input path with automatic multipart modal submission.
- **Sidebar Builder Runtime Polish**: Fixed selected-entry localization drift in Arabic and added cross-pane drag/drop so discovered entries can be moved into or back out of the selected tree without leaving the builder flow.

## v1.20.4

- **Microsys Table Platform vNext**: Added the public `MicrosysTable` base class and aligned generic auto-built tables with the same renderer, density handling, default attrs, sorting, pagination, and row-action contract.
- **Framework-Owned Pagination**: Shipped built-in table pagination controls, per-page options (`10`, `20`, `50`, `100`), global per-user page-size persistence through `Profile.preferences["table_page_size"]`, and centralized `RequestConfig` patching so Microsys-managed tables no longer need manual `per_page` wiring.
- **Zero-Boilerplate CRUD Actions**: Added default `micro:record:view|edit|delete` row actions for Microsys-managed tables, including captured stock-template host tables, with permission filtering, divider cleanup, and a `get_microsys_row_actions()` extension hook for custom tables.
- **Dark Theme Table Conformance**: Added explicit `--ms-table-*` token overrides in the `dark`, `gothic`, and `neon` themes so the new table shell, sticky surfaces, empty state, pagination, and page-size controls render correctly on dark palettes.
- **Scaffold and View Alignment**: Updated built-in Microsys views and scaffolded app templates to use the framework page-size default and `MicrosysTable` path instead of shipping old hardcoded pagination assumptions.

## v1.20.3b0

- **Framework-Owned Table Surface**: Replaced the old CSS-only table polish with a Microsys-owned `django_tables2` template, responsive shell, pagination styling, sort affordances, empty-state rendering, and modern density-aware table tokens.
- **Zero-Boilerplate Table Adoption**: Added runtime remapping so built-in tables, generic generated tables, and host-project tables using stock `django_tables2` templates adopt the Microsys renderer automatically, while explicit custom templates remain untouched by default.
- **Layered Table Density Controls**: Added `SystemSettings.default_table_density`, per-user `Profile.preferences["table_density"]`, and per-table `Meta.microsys_density` / `Meta.microsys_table` controls with precedence from table override to user preference to system default to the `balanced` fallback.

## v1.20.2

- **Windows Docker Desktop Path Translation**: Updated the generated `start.ps1` scaffold to translate Windows project paths such as `C:\Users\...` into Docker Desktop’s daemon-visible Linux form (`/host_mnt/<drive>/...`) before launching the decrypter container.
- **Windows Compose Bind-Mount Compatibility**: Fixed the generated PowerShell launcher so relative compose mounts like `./.nginx/nginx.conf`, `./media`, `./logs`, and the dev override `./:/app` resolve correctly on Windows instead of breaking when the helper container uses a private in-container path.
- **Windows Shell File Reliability**: Kept scaffold file generation on forced LF newlines so generated `entrypoint.sh` and `start.sh` remain executable inside Linux containers even when the project is created on Windows.

## v1.20.1

- **Windows PowerShell Launcher Fix**: Updated the generated `start.ps1` scaffold so the decrypter container always uses `/workspace` as its in-container working directory instead of passing a Windows host path such as `C:\...` to `docker run -w`.
- **Windows Shell Newline Fix**: Updated scaffold file generation to always emit LF newlines so generated `entrypoint.sh` and `start.sh` work correctly inside Linux containers when a project is created on Windows.

## v1.20.0

- **Scaffolding CLI**: Added package-level `microsys startproject` for greenfield MicroSys-ready Django projects and `microsys startapp` for MicroSys-native app scaffolds, including an optional `--register` flag to patch project settings and URLs safely.
- **Scaffold Templates**: Added built-in project and app templates that generate starter docs, tests, translations, filters, tables, views, and templates following current MicroSys conventions.
- **Scaffold Security/Runtime Baseline**: Expanded generated project settings to include `django-health-check`, Celery wiring, generated bootstrap secrets under `.secrets/.env`, `django-cors-headers`, and `django-csp` with starter middleware and baseline policy settings.
- **Settings Helper Hardening**: Fixed the duplicate trailing `microsys_settings()` override in `microsys.utils`, added `LocaleMiddleware` ordering, added Bootstrap-friendly `MESSAGE_TAGS[messages.ERROR] = "danger"` defaulting, and kept the helper as the canonical low-friction integration path.

## v1.19.4b4

- **Anonymous Root Redirect Fix**: Fixed a regression where anonymous users visiting the root URL `/` received a 404 instead of being redirected to the login page. Removed the `is_authenticated` check from `_should_redirect_missing_root()` so the middleware now intercepts all 404s on `/` and routes anonymous users to `/accounts/login/` while authenticated users continue to their configured home URL or setup wizard.

## v1.19.4b3

- **Restored Missing User Views Package**: Recovered the `microsys/views/users.py` module and related files that were accidentally excluded from the package due to a gitignore pattern matching folders named `users`. This restores user management, profile editing, and the user creation wizard functionality.

## v1.19.4b2 `corrupted`

- **Scope Auto-Create Hardening**: Improved the `auto_create_user_scope` feature added in b1 with safer transaction handling and better error reporting when scope creation fails during user registration.

## v1.19.4b1

- **Per-User Scope Auto-Creation**: Added `auto_create_user_scope` toggle to `ScopeSettings` that automatically creates a dedicated `Scope` for each newly registered user. This enables automatic user isolation using the microsys scope system, scoped manager, and permissions infrastructure without manual scope assignment.

## v1.19.4b0

- **Email 2FA Configuration Fix**: Replaced the broken `os.getenv('EMAIL_HOST')` check in `get_2fa_config()` with an explicit `email_2fa` flag read from the merged system config (`MICROSYS_CONFIG` + DB). The old check silently failed when email was configured via Django settings or SOPS injection rather than as a bare OS environment variable.
- **Email 2FA Setup Toggle**: Added an `email_2fa` BooleanField to `SystemSettings` and a corresponding toggle in the System Settings form (Step 1), so administrators can enable email-based two-factor authentication from the UI. The flag is also seedable from `MICROSYS_CONFIG['email_2fa']`.

## v1.19.3

- **Expanded Sidebar Icon Library**: Grew the sidebar builder icon picker from ~190 to over 530 Bootstrap icons, with comprehensive coverage for file types, security, communication, devices, media, and more.
- **Icon Picker Search**: Added a real-time search field inside the icon picker with case-insensitive, space-to-hyphen filtering for fast icon discovery.
- **Theme-Aware Tutorial Controls Bar**: Refactored the tutorial controls bar (`#tutorial-controls`) to use CSS custom properties and added per-theme overrides across all ten themes, so the bottom bar now matches each theme's palette instead of always rendering white.
- **Dark Theme Tutorial Popover**: Added Driver.js popover styling for the Dark theme so tutorial popovers blend with the dark surface.
- **Titlebar Home Button Fix**: Added `.ms-titlebar-home` overrides for Gothic and Retro themes so the home button no longer renders with a bright translucent-white background on dark titlebar surfaces.

## v1.19.2

- **Sidebar Runtime Controls**: Added system-level sidebar builder toggles for runtime reordering and sidebar-toolbar visibility, persisted them through setup and runtime config sanitization, and documented the Dynamic Sections Manager access implication when the toolbar is disabled.
- **Sidebar Visual Overhaul**: Reworked the shared sidebar from rounded floating pills into a flatter edge-to-edge rail, restored clear active states for the older/light themes, added a modern non-arrow folder marker, normalized row geometry in collapsed mode, improved the compact theme picker layout, and separated parent-folder vs child-item active treatment more clearly in `mono` and `dark`.
- **Documentation Refresh**: Updated the README, admin guide, customization guide, and reference material to document the `1.19.1` theme-engine changes, sidebar behavior controls, dark-theme runtime picker behavior, and current runtime configuration expectations.

## v1.19.1

- **Packaging and Dependency Cleanup**: Added the missing runtime package dependencies (`pyotp`, `psutil`, and `qrcode`) to `pyproject.toml` so installs match the features microSYS already exposes in the UI and runtime.
- **Unified Theme Registry**: Centralized theme registration through a shared `microsys/themes.py` registry so theme names, picker ordering, preview swatches, runtime validation, and template CSS inclusion stay aligned across forms, context processors, templates, and JS.
- **Expanded Theme Set and Stability Fixes**: Registered the new `mono`, `gothic`, and `retro` themes, fixed the first-paint `neon` allowlist so navigation no longer flashes back to light mode, and aligned newer theme-specific surfaces such as the user hub, profile cards, activity-log details, tutorial popovers, system-settings badges, options-page theme/language pickers, and sidebar toolbar.
- **Theme Surface Conformance**: Extended the newer themes so dashboard/index cards, toolbar controls, sidebar separators, icon treatments, and dark-theme option controls follow each theme’s palette instead of leaking generic light or white fallback styling.
- **Runtime Theme UX Polish**: Theme changes made from Options now update the sidebar toolbar indicator immediately, and the options-page preview rings now follow the active theme instead of falling back to the generic white active outline on dark themes.

## v1.19.0

- **Settings Helper**: Added `microsys_settings(globals())` in `microsys.utils` as the supported low-friction settings integration path for host projects. The helper prepends the required apps, inserts `MicrosysMiddleware`, adds the Microsys context processor, sets Crispy Bootstrap 5 defaults, and seeds the standard MicroSys language/timezone/format defaults when the host project has not already defined them.
- **Command Upgrade**: `microsys_setup` now appends the recommended helper block to the active project `settings.py` instead of only running migrations, and `microsys_check` now validates the helper pattern explicitly alongside the resulting configuration state.
- **List Base Template**: Added `microsys/list_base.html` plus `microsys/forms/filter_assets_head.html` as the supported entrypoint for list/filter pages, so filter-helper surfaces can use the same modern field/button styling without loading the full form bundle globally.
- **Form Base Template**: Added `microsys/form_base.html` as the supported full-page entrypoint for Microsys forms, so projects can opt into the shared form surface without loading form-only assets through `microsys/base.html`.
- **Reusable Form Asset Includes**: Added `microsys/forms/assets_head.html` and `microsys/forms/assets_scripts.html` for pages that host embedded or modal forms but do not extend `microsys/form_base.html`.
- **Shared Modern Form Bundle**: Added a framework-owned Microsys form asset package under `microsys/static/microsys/forms/` covering standard field surfaces, modern file-field styling, action-dock styling, and file-widget JS.
- **Modern Filter Surface**: `setup_filter_helper()` and `advanced_filter_helper()` now emit Microsys filter classes so shared field/button styling and dark-mode treatment apply automatically when the page uses `microsys/list_base.html` or `microsys/forms/filter_assets_head.html`.
- **Framework Form Templates**: Added Microsys form templates for the reusable file widget and a default Crispy file-field bridge under `templates/bootstrap5/layout/field_file.html`, so projects can point file widgets and field partials at a framework-owned path instead of copying a local bundle.
- **Documentation**: Updated the customization guide to document the new `microsys/form_base.html` and the embedded-form asset-include pattern.

## v1.18.18

- **Official Datepicker Switch**: Replaced Flatpickr as the shared datepicker standard with `vanillajs-datepicker`, added built-in Arabic locale wiring, and kept legacy `.flatpickr` selector compatibility for existing host-project forms.
- **Advanced Filter Helper**: Added `advanced_filter_helper()` for zero-boilerplate list filters with a primary search row, collapsible advanced rows, optional action buttons, and separate hidden-preserve vs clear-preserve query handling.
- **Request-Aware Field Direction**: Updated `set_field_attrs()` to resolve the active request language before assigning placeholders and direction, so English filter inputs no longer inherit Arabic RTL behavior.
- **Sidebar Discovery and Translation Refinement**: Sidebar discovery now excludes noisy AJAX/add/edit route patterns more reliably, prefers route-level translation keys such as `view_*`, and no longer lets stale stored sidebar labels override discovered translated route/group metadata at render time.
- **Sidebar Width and Gutter Polish**: Refined the shared sidebar CSS so expanded sidebars keep enough width for the toolbar while preserving a small inline-end label gutter without leaving the toolbar shade short.
- **Chart and Dark-Theme UI Fixes**: Plotly chart CSS now decouples internal SVG layout from page RTL to stop legend/toggle overlap, dark mode now gives modern tabs and decree tabs a clearly visible active surface instead of only brighter text, and the official datepicker now has dark-theme styling.
- **Documentation**: Expanded the customization and reference guides to document the supported tutorial-extension hook, `advanced_filter_helper()`, and the preferred project-extension path through Microsys base-template injection points.

## v1.18.17

- **First-Launch Guard for Public Roots**: Unconfigured installs now redirect ordinary anonymous traffic into the setup/login path even when the host project already exposes a public `/` view, preventing first-time setup from being bypassed.
- **Signed-Out Layout Fix**: `microsys/base.html` no longer wraps anonymous pages in the authenticated sidebar shell, eliminating the squeezed-content layout issue on public pages that extend the shared base template.
- **Documentation**: Updated integration docs to clarify how root-mounted Microsys behaves before and after initial system configuration.

## v1.18.16

- **License Change**: Changed the license from MIT to NON-COMMERCIAL.
- **Documentation**: Updated the documentation to reflect the license change.
- **Setup**: Updated build from setup.py to pyproject.toml.

## v1.18.15

- **Split User Edit Modals**: Separated user editing into two dedicated dynamic modals, `Edit User` for account/profile data and `Edit Permissions` for staff/permission management, while preserving the existing user-creation wizard unchanged.
- **Manage Users Context Menu Upgrade**: Replaced the single `Edit` action in User Management with distinct `Edit User` and `Edit Permissions` actions, each routing to its own modal flow.
- **Language-Aware Action Alignment**: Fixed wizard and modal action-button layout so controls now align correctly by active UI direction, including prev/next arrow orientation for Arabic vs English.
- **Dynamic Modal Header Cleanup**: Removed the duplicate inner form title from shared dynamic modal rendering so form-only modals show a single clear title instead of stacked headings.

## v1.18.14

- **Guaranteed System Navigation Controls**: Added a conditional sidebar toolbar shortcut for Dynamic Sections Manager and introduced a builder toggle to reveal Microsys system items (`manage_users`, `activity_log`, `options`, `manage_sections`) without forcing them into normal app discovery.
- **Configurable System Sidebar Items**: Extended sidebar discovery, sanitization, and setup persistence so the approved Microsys system routes stay hidden by default but can now be intentionally included in saved sidebar structures.
- **Localization Sweep for Sections & Filters**: Replaced multiple hardcoded Arabic/English strings with translation-backed labels across subsection management, user/activity filters, date range placeholders, and auto-generated section form buttons.
- **Titlebar and Sidebar Polish**: Refined the titlebar sidebar toggle to blend into the bar instead of looking permanently pressed, and matched sidebar toolbar-collapse behavior so the Sections Manager shortcut hides with the collapsed sidebar state.

## v1.18.13

- **Fix**: Fixed an issue where the home URL was not being set correctly.
- **Documentation**: Completely revamped the documentation and split into multiple structured files.

## v1.18.12

- **Broader Curated Icon Set**: Expanded the setup inspector's icon suggestions to a much more diverse, verified set covering navigation, storage, finance, admin, communication, scheduling, and data-oriented icons.

## v1.18.11

- **Inspector Two-Column Layout**: Reworked the setup sidebar inspector into a cleaner two-column layout, with label/icon fields on one side and the icon chooser on the other.
- **Expanded Scrollable Icon Picker**: Greatly increased the available Bootstrap icon suggestions and moved them into a capped inline-scroll picker so the inspector stays compact while offering many more choices.

## v1.18.10

- **Global Home URL Setting**: Moved Home selection out of the sidebar builder and into general System Settings, so developers can choose any discovered page as the project-wide Home destination or type a custom URL directly.
- **Sidebar/Home Decoupling**: Stopped letting sidebar configuration implicitly override `home_url`, and reset the builder's old Home selector so sidebar structure no longer dictates the titlebar Home button.

## v1.18.9

- **Unified Runtime Sidebar Tree**: Replaced the live sidebar's split auto-items/accordion-groups render path with the same single tree model used by the first-launch setup builder, so saved Microsys sidebar structure now renders directly at runtime.
- **Tree-Based Personal Reordering**: Reworked live sidebar reordering to save a user-specific tree override instead of juggling separate root/group/localStorage order buckets, while still merging in newly added base sidebar items from system setup.

## v1.18.8

- **Optional Titlebar Home Target**: Stopped forcing the titlebar Home button to follow a top-level sidebar item, so setup can leave Home on its normal system destination without adding an Index entry to the sidebar.
- **Builder Home Selector Cleanup**: The sidebar builder now offers a default "use the titlebar Home button link" option instead of auto-selecting the first sidebar item or disabling the control when no top-level entries exist.

## v1.18.7

- **Setup Form Initial Sync Fix**: Corrected the first-launch System Settings form so cleaned singleton defaults are pushed into `self.initial` after form construction, preventing stale legacy values like `ادارة النظام` from rendering in the Arabic name field.

## v1.18.6

- **Immediate Setup Language Switching**: Removed the extra Apply action from first-launch setup so language cards now switch the UI immediately, matching the instant-feedback feel of the theme picker.
- **State-Safe Language Reloads**: The immediate setup language switch still preserves the current wizard step and unsaved onboarding values before reloading the page.

## v1.18.5

- **Shared Language Picker UI**: Replaced the setup default-language dropdown with the same language-card toggle UI used in Options, so language and theme selection now feel consistent during first launch.
- **Setup State Preservation**: Applying a setup language change now preserves the wizard step and unsaved text/JSON/sidebar values across the reload instead of resetting the onboarding form.

## v1.18.4

- **Pre-Setup Branding Cleanup**: Removed the legacy Arabic system-name default so fresh and unconfigured installs no longer surface `ادارة النظام` before setup is completed.
- **Blank Arabic Setup Field**: The Arabic system-name field now starts empty during first launch, while runtime branding continues to fall back to `microSYS` until the developer saves real names.

## v1.18.3

- **System Default Theme**: Added `SystemSettings.default_theme` and `MICROSYS_CONFIG['default_theme']` fallback support so new users inherit a configurable default look until they save their own theme preference.
- **Setup Theme Picker**: Added the same circular theme chooser from Options to first-launch setup beside default language, with live preview while editing the system default.

## v1.18.2

- **Theme Fallback Fix**: Added a guaranteed default `light` theme path so titlebar and other theme-scoped surfaces no longer render transparent when no theme preference is saved.
- **Sidebar Toggle Polish**: Refined the titlebar sidebar toggle with a proper default surface and matching dark-theme treatment.

## v1.18.1

- **Theme-Aware Setup Builder**: Refactored the first-launch sidebar builder to derive its surfaces, text, active states, and tree accents from shared Microsys theme tokens instead of hardcoded colors.
- **Shared Control Styling**: Wired setup search, home destination, and inspector inputs onto existing `glass-input` styling for consistent appearance across themes.

## v1.18.0

- **First-Launch Setup Wizard**: Added `/sys/setup/` onboarding for branding, languages, translations, and global sidebar configuration, while keeping System Settings editable later from Options.
- **Resolver-Driven Sidebar Builder**: Replaced suffix-based discovery with reversible URL discovery and a two-pane builder with group selection, add-all/remove-all controls, and persistent home destination handling.
- **Navigation Cleanup**: Excluded Microsys, Django admin, and health-check routes from discovered application navigation.

## v1.17.7

- **Modern Tooltips**: Replaced native browser tooltips in the User Hub with custom, high-fidelity glass-morphism tooltips for a more premium toolbar experience.

## v1.17.6

- **User Hub UX Optimization**: Prevented automatic collapse of the user hub dropdown when interacting with tutorial controls or the sidebar theme picker.

## v1.17.5

- **Avatar Fix**: Enforced circular shape and fixed dimensions for titlebar user avatars to prevent layout issues with square images.

## v1.17.4

- **User Hub Dark Mode**: Complete dark theme overrides for the user trigger and dropdown hub, featuring enhanced glass-morphism and high-contrast toolbars.

## v1.17.3

- **UI Cleanup**: Removed decorative pseudo-element from hero section background to ensure a clean, glitch-free visual across all themes.

## v1.17.2

- **Dark Mode Refinement**: Fixed dashboard hero section gradient in dark mode for a more premium, high-contrast appearance.

## v1.17.1

- **UI Optimization**: Reduced user button height and padding in the titlebar for a more compact and refined navigation experience.

## v1.17.0

- **Modern UX & Branding Overhaul**: Systematic enhancement of the titlebar and sidebar.
- **User Intelligence Center**: Replaced legacy titlebar buttons (Home, Help, Logout) with a modern, circular user trigger.
- **Advanced User Dropdown**: Implemented a professional, rectangular glass-morphism dropdown activated by the user icon. Features real-time info text on the left and a high-fidelity image preview on the right.
- **Fixed Dropdown Toolbar**: Integrated specialized toolbar at the bottom of the user dropdown containing Profile, Manage Users (for staff), Activity Log, and System Options links.
- **Sidebar Streamlining**: Deprecated and removed the `system_group` accordion and its associated dashboard elements to simplify navigation.
- **Circular Login Interface**: Introduced a sleek, circular login icon for unauthenticated users.

## v1.16.0

- **Interactive User Wizard**: Transformed user creation and editing into an interactive 2-step wizard (Account Details & Permissions) within the dynamic modal system.
- **Dynamic Permission Translation**: Implemented a system-wide patch to dynamically translate permission prefixes and labels based on the active language.
- **Permission Widget Polishing**: Fixed "Select All" functionality at both App and Model levels in the permission widget using event delegation for reliable AJAX support.
- **Modal Flow Optimization**: Updated the dynamic modal success handler to trigger a parent page reload specifically for the user management flow, ensuring the list view is always synchronized with changes.

## v1.15.9

- **Leftover `_get_default_strings` Fix**: Replaced two remaining references to the removed `_get_default_strings()` function in `utils.py` (`_build_generic_detail_context` and `_build_generic_table_class`) with `get_strings()`. These stale references caused `NameError` -> 500 Internal Server Error when the Dynamic Modal Manager auto-generated tables/detail views for models like `SystemSettings`.

## v1.15.8

- **Filter Layout Suffix Fix**: Fixed hardcoded fallback strings `'from'` and `'to'` in `set_field_attrs` to properly consult the mapped translation dictionary keys `'filter_from'` and `'filter_to'` when computing translated placeholders for range filters (`__gte` and `__lte`).

## v1.15.7

- **Context Menu Smart View Duplicate Data Fix**: Fixed a bug in `collect_related_objects` where M2M relations were processed twice (via both `auto_created` reverse accessors and `many_to_many` forward accessors), causing duplicate cards in the Smart View modal. Added tracking to ensure relations are only added once.
- **Modal CSS Fix**: Replaced hardcoded `text-white-50` class with theme-adaptive `text-muted` in `section_manager.js` to ensure related records list items are visible in both light and dark themes.

## v1.15.6

- **M2M Serialization Fix**: Wrapped lazy translation proxies (`verbose_name`, `verbose_name_plural`) with `str()` in `utils.py` and `views/sections.py` to prevent `TypeError: Object of type Promise is not JSON serializable` resulting in 500 errors when viewing section details with M2M relations via Context Menu.

## v1.15.5

- **Translation Signature Fix**: Fixed `get_strings` function call and replaced removed `_get_request_lang` usages in `utils.py` and `models.py` with Django's native language detection to prevent `AttributeError` during form generation.

## v1.15.4

- **Translation System Streamlining**: Completely overhauled the translation system to make `get_strings()` the single, smart source of truth. Removed all redundant wrappers from `utils.py` (`_get_default_strings`, `_get_request_lang`, `_get_request_translations`), `forms.py` (`_get_form_strings`), and `filters.py` (`_get_filter_strings`). All views, templates, tables, forms, and filters now route directly through `translations.get_strings()` which automatically handles request/session/profile context language resolution internally.

## v1.15.3

- **Universal Context Menu Translation**: Augmented the `Table.__init__` patch in `AppConfig.ready()` to automatically and globally translate `label` properties inside `row_attrs['data-micro-actions']` dynamically based on the current user linguistic preferences.

## v1.15.2

- **Micro Context Menu Dark Mode Enhancement**: Updated hover background color for context menu items in dark mode to improve contrast and reduce visual harshness.

## v1.15.1

- **Translation Language Resolution Fix**: Rewrote `get_strings()` to use the same robust language fallback as `microsys_context`: user profile prefs -> session -> `MICROSYS_CONFIG['default_language']` -> `get_language()` -> `'ar'`. Previously the function skipped profile prefs and `default_language`, causing Django's default `en-us` to override the intended Arabic default.
- **Table Patch Kwargs Fix**: Fixed `TypeError` in `_patched_init` where microsys-specific kwargs (`translations`, `request`, `model_name`) were forwarded to django-tables2's `Table.__init__()`.

## v1.15.0

- **Universal Auto-Translation**: Augmented `AppConfig.ready()` patches to automatically translate Table headers, Filter labels, and ModelForm field labels by looking up `verbose_name` or `label` in the project's translation dictionary. Supports `tbl_` and `label_` prefixes with zero developer effort.

## v1.14.0

- **Scope Auto-Injection**: Monkey-patches `ModelForm`, `FilterSet`, and `Table` in `AppConfig.ready()` to auto-inject and manage scope for any `ScopedModel`-based component - zero developer effort.
- Auto Scope on Save: `ScopedModel.save()` now auto-sets scope from user's profile (like `created_by`).
- ScopeForeignKey Fix: `formfield()` no longer returns `None` when scopes are disabled.

## v1.13.0

- **User Modal CRUD**: Migrated User add/edit from separate pages into `DynamicModalManagerView`.
- **Smart Form Kwargs**: Auto-introspects form `__init__` signatures and passes `user`/`request` if accepted.
- **`form_class` / `template_name` Overrides**: URL-level customization of form class and template.
- **`show_table` / `show_form` Flags**: Render form-only, table-only, or combined.
- **`handles_save` Flag**: Forms managing their own save cycle (password hashing, M2M).
- **`get_modal_context()` Convention**: Models can define this method to auto-inject extra context into modals.
- **`UserModalForm`**: Smart proxy delegating to creation/change forms based on instance.

## v1.12.7

- **Reusable Global List Template**: Added `microsys/helpers/global_list.html` to standardize form/filter/table list views project-wide.
- **Event Rename**: Renamed `micro:section:*` -> `micro:record:*` for semantic accuracy across AutoTable, `section_manager.js`, and all consumer templates.

## v1.12.6

- **Global Context Menus**: Refactored AutoTable generic context menus to dispatch decoupled `micro:record:edit` events, empowering standard views to handle routing and custom views to pipe explicitly into Dynamic Modals without boilerplate code.

## v1.12.5

- **HR Validation Overhaul**: Shipped powerful `ProfileCompletionMiddleware` and `EmployeeSetupForm` that globally trap unverified dummy users upon login, forcing them to complete their profiles before gaining system access.

## v1.12.4

- **Dynamic Connected Profiles Failsafe**: Universal `post_save` signal that introspects one-to-one user profiles globally and auto-creates them with type-safe dummy values, bypassing database requirements for flawless system-agnostic onboarding.

## v1.12.3

- **Migrator Component Integration**: Integrated `migrator.py` into the `microsys/management/commands` package to centralize and reuse initial deployment logic across projects. Added `-mm` (make-migrations) flag to `migrator.py` to safely force makemigrations.

## v1.12.2

- **`get_model_classes` Performance Enhancement**: Upgraded `get_model_classes` utility to use dictionary caching and `LazyModelClasses` for lazy evaluation, reducing module import overhead during the request loop.
- **`get_model_classes` Overrides**: Added support for explicit convention overrides via the `overrides` argument or the model-level `model_classes_overrides` attribute.

## v1.12.1

- **Universal Filter Standardization**: Migrated `Users`, `Sections`, and `Activity Log` views to the unified `setup_filter_helper` utility. All core lists now benefit from conditional clear buttons, `Hidden` GET parameter preservation, and consistent responsive layouts.

## v1.12.0

- **Smart Filter Controls**: Enhanced `setup_filter_helper` to conditionally render the reset (cancel) button. It now only appears when active filters with non-empty values are present, reducing UI clutter.
- **Alignment Refinement**: Standardized global filter alignment to `start` for improved visual hierarchy.

## v1.11.5

- **Dynamic Sidebar Width**: Converted sidebar layout to `col-auto` with `fit-content` min-width on large screens, allowing it to adapt to the longest item or accordion parent.
- **Flexible Content Layout**: Updated the main content area to utilize fluid grid sizing, ensuring it seamlessly fills the workspace adjacent to the dynamic sidebar.

## v1.11.4

- **Sidebar RTL Precision**: Synchronized direction context with sidebar templatetags to ensure correct chevron mirroring in RTL layouts.
- **Padding Optimization**: Refined RTL padding for sidebar items and accordion buttons to pull navigation elements flush with the sidebar borders, eliminating "phantom" side gaps.

## v1.11.3

- **Separate Accordion URL Button**: Modified sidebar accordion headers to display a separate, non-intrusive URL button (`>`/`<`) for groups with dashboard links, preserving default accordion toggle behavior without JS routing conflicts.

## v1.11.2

- **Premium Dark Theme Legibility**: Comprehensive overhaul of contrast, outlines, and visibility for all UI components in dark mode.
- **Improved Text Contrast**: Enforced high-contrast labels and text utility classes for maximum readability on dark backgrounds.
- **Preserved Utility Borders**: Protected Bootstrap `border-*` classes from global theme overrides.

## v1.11.1

- **Sidebar Parent Reordering**: Enabled reordering for entire accordion groups with dedicated persistence and FOUC prevention.

## v1.11.0

- **Sidebar Accordion Refinement**: Added dashboard navigation behavior to the built-in "System" group header, matching the split-accordion behavior of other functional groups.

## v1.10.3

- **Removed all `hasattr` guards** in views (fields always exist now).
- Simplified `ScopedManager` (no conditional `deleted_at` check).

## v1.10.2

- **UserActivityLog Refactor**: Removed redundant `user`/`timestamp` fields in favor of inherited `created_by`/`created_at` with backward-compat properties.
- **Centralized Logging**: Enhanced `log_user_action()` utility and replaced all manual `UserActivityLog.objects.create()` calls across signals, fetcher, and views.

## v1.10.1

- **Global Soft-Delete**: `delete()` overridden to perform soft-delete; added `soft_delete()`, `restore()`, and `hard_delete()` methods.

## v1.10.0

- **ScopedModel Audit Trail**: Added six built-in fields (`created_at`, `updated_at`, `created_by`, `updated_by`, `deleted_at`, `deleted_by`) with `editable=False` to `ScopedModel`.
- **Auto-Populated Actors**: `save()` override auto-populates `created_by` and `updated_by` from thread-local middleware.

## v1.9.2

- **Comprehensive README Overhaul**: Added extensive developer how-to documentation for Dynamic Modal Manager, 2FA, Template Tags, Double-Submit Prevention, and Preferences API.
- Expanded `ScopedModel` docs (dual managers, `ScopeForeignKey`, soft-delete), Section Mode (class resolution order, customization hooks), Context Menu (permission filtering, event actions, action schema), Autofill (API endpoints), and Activity Logging (safe_log, diffs, masking).
- Updated file structure to reflect the `views/` package refactor.

## v1.9.1

- **Views Modularization**: Refactored monolithic `views.py` into a `views/` package with dedicated modules: `general.py`, `users.py`, `twofa.py`, `sections.py`, `scopes.py`, `activitylog.py`, `profile.py`, and `sidebar.py`.
- Added role-distinguishing top comments to all functions and classes.

## v1.9.0

- **Dynamic Modal Reconstruction**: Successfully restored the deleted `DynamicModalManagerView` and `DynamicModalDeleteView` functionality.
- Standardized dynamic modals with a unified AJAX-driven combined view (List + Form) for auxiliary models.
- Integrated related-record protection in deletion views with localized error messaging.

> Due to data corruption in the codebase and not committing frequently some part of the code was lost specifically a newly implemented Dynamic Modal derived from the subsection modal was lost and had to be re-implemented.

## v1.8.1

- **Auto Profile Creation**: Added a `post_save` signal to automatically create a `Profile` instance whenever a new user is created to prevent profile-missing errors.
- **Sidebar Accordions State**: Updated sidebar accordions to decouple from the active URL and each other, strictly persisting each accordion's open or close state independently based purely on user interaction.

## v1.8.0

- **Dynamic Multi-Language Tutorial**: Completely refactored the guided tutorial system. The tutorial is now fully dynamic based on the current URL path (`/sys/`, `/sys/sections/`, `/sys/users/`, etc.), supports full English and Arabic translations, and intelligently targets elements even if they change positions.

## v1.7.12

- **Offline Twemoji Flags**: Added local hosting for the Twemoji Country Flags web-font polyfill to ensure flag emojis render correctly on Windows without external CDN dependencies.

## v1.7.11

- **Theme Fixes**: Resolved issue where language picker options appeared white in dark theme by adding proper CSS variable overrides in `dark.css`.

## v1.7.10

- **Responsive 2FA UI**: Fixed two-factor authentication method rows to stay side-by-side on small screens, preventing the enable buttons and labels from stacking.

## v1.7.9

- **Premium Navigation Stability**: Finalized logout button with a `warning` theme, fixed icon wobble transitions, and tightened spacing for a high-end, glitch-free feel.

## v1.7.8

- **UI Refinement**: Moved the user's name outside the sign-out button in the titlebar for better separation.

## v1.7.7

- **Navigation Refactor**: Moved Profile to Sidebar and simplified Titlebar to a unified `Username | Logout` button.

## v1.7.6

- **Intuitive Double-Click Feedback (2026-02-17)**: Automatic pointer cursor for double-click targets.

## v1.7.5

- **Unified User Detail Modal (2026-02-17)**: AJAX-driven modal for user details, integrating the activity timeline and migrating context-menu events for users.

## v1.7.3

- **Dashboard Activity Chart**: Added a built-in activity chart powered by Plotly.js, visualizing system activity for the last 24 hours.
- **Responsive Chart**: Chart automatically resizes with the window and sidebar toggles using `ResizeObserver`.

## v1.7.2

- **Premium Modal UI**: Overhauled all section and activity modals with the glass-card/info-label design from the Profile view.
- **Dark Mode Accessibility**: Increased glass-card opacity to `0.92` and refined shadows to ensure data visibility in dark themes.
- **Double Modal Fix**: Resolved redundant script inclusion causing duplicate modal triggers.
- **Log Refinement**: Standardized activity log details with profile-consistent typography and theme-aware badges.

## v1.7.1

- **Enhanced Activity Logging**: Added JSON-based detail tracking for all updates (diffs), including masked password changes and file-download specifics.
- **Log Deduplication**: Implemented smart merging of concurrent User and Profile updates into single log entries.
- **Double Submit Prevention**: Added global JavaScript protection to disable submit buttons immediately after click.
- **Profile UI**: Updated the profile view to display detailed log history with formatted diffs.

## v1.7.0

- **Universal Fetcher**: Added a global, smart single-file and multi-file downloader.
- Added a data-driven Excel exporter for querysets with auto-hidden fields and an optional exclude-fields list.

## v1.6.3

- **Login Enhancements**: Added language switcher, session-based language persistence, and fixed RTL alignment bug.
- **Smart Redirects**: Login now automatically redirects authenticated users and supports `home_url` config fallback.
- **Unified Translations**: Refactored the internal translation helper to support anonymous sessions.

## v1.6.2

- **Custom Password Form**: Refactored the password-change form with dynamic translations and helpful descriptions.
- **RTL/LTR Fixes**: Fixed login screen text direction in English mode.
- **Profile Translations**: Fully translated profile view and edit pages.

## v1.6.1

- **Translation Upgrade**: Improved translation system and coverage.
- Various bug fixes and stability improvements.

## v1.6.0

- **Context Menu**: Added global, data-driven context-menu support for interactive elements.

## v1.5.2

- Completely restructured the README for a clearer understanding of the system and its setup.

## v1.5.1

- Autofill fixes: Resolved `500` and `404` errors during clearing, refined toggle behavior, and standardized console logging.

## v1.5.0

- **Global Dynamic Autofill Feature**: Automatically fill forms from related foreign keys (for example, user-profile data) with smart clearing and toggle controls.

## v1.4.1

- Translation-related fixes and UI enhancements.

## v1.4.0

- **Comprehensive Translation Framework**: Table headers, filter labels and placeholders, and template strings now resolve from `translations.py` per user language.
- Tables, filters, and templates (`manage_users`, `user_activity_log`, `manage_sections`) are fully translated.
- Reset Defaults now purges sidebar reordering from the database and local storage.
- Reset UI redesigned to match other options with inline Confirm and Cancel animation.
- Fixed activity-log actions always showing in Arabic regardless of language due to duplicate `get_table_kwargs`.

## v1.3.6

- Fixed theme-picker popup positioning in LTR mode (CSS logical properties).

## v1.3.5

- Switched to database JSON attached to the user profile for consistent preferences across devices.

## v1.3.4

- Added global head and scripts injection.

## v1.3.3

- Optimized form and filter auto-generation and layout.

## v1.3.2

- Fixed the README and added detailed instructions.

## v1.3.1

- Auto-generated section filters now include date-range pickers (from and to) with Flatpickr integration.
- Added clarifying inline comments to complex view logic.
- Fixed login Enter-key submission.
- PyPI release.

## v1.3.0

- **Section table context menu**: Right-click on table rows for Edit and Delete actions.
- **View Subsections modal**: Sections with many-to-many subsections show linked items in a modal.
- AJAX-based section deletion with related-record protection.
- Auto-generated tables now include row data attributes for JavaScript binding.

## v1.2.1

- Fixed subsection display so subsections show correctly regardless of user scope.
- Fixed `SessionInterrupted` errors by reducing session writes in section management.
- Scope toggle now accepts an explicit target state to prevent race conditions.
- Improved error messaging in Arabic for scope operations.

## v1.2.0

- **Dynamic Section Management**: New powerful zero-boilerplate section-management mode.
- Name changed to `django-microsys`.
- Scope fields now hide automatically when scopes are disabled.
- System sidebar group ships by default and remains configurable.
- `is_staff` moved into the permissions UI.

## v1.1.0

- **Application Complete Restructure** with modular files, templates, static assets, and related cleanup.
- URL restructure: auth at `/accounts/`, system at `/sys/`.
- Added `microsys_setup` and `microsys_check` management commands.
- Runtime configuration validation.

## v1.0.0

- Initial release as a pip package.
