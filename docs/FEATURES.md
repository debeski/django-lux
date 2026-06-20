# DjangoLux Complete Feature Reference

**Version:** 1.0.4
**Package:** `django-lux` — A multilingual Django framework layer for internal systems

---

## Table of Contents

1. [Core System & Configuration](#1-core-system--configuration)
2. [Scaffolding & Project Generation](#2-scaffolding--project-generation)
3. [Models & Data Layer](#3-models--data-layer)
4. [Security & Authentication](#4-security--authentication)
5. [User Management & Profiles](#5-user-management--profiles)
6. [UI Infrastructure](#6-ui-infrastructure)
7. [Tables & Data Display](#7-tables--data-display)
8. [Forms & Widgets](#8-forms--widgets)
9. [Activity Logging & Audit](#9-activity-logging--audit)
10. [API & AJAX Infrastructure](#10-api--ajax-infrastructure)
11. [Translation & Internationalization](#11-translation--internationalization)
12. [Static Assets & JS Helpers](#12-static-assets--js-helpers)
13. [Template Tags & Filters](#13-template-tags--filters)
14. [Middleware & Request Handling](#14-middleware--request-handling)
15. [Discovery System](#15-discovery-system)
16. [Notifications](#16-notifications)

---

## 1. Core System & Configuration

### SystemSettings (Singleton Model)
- **Database-backed singleton** for runtime system configuration
- **Caching layer** (24h TTL) for performance
- **Seeding from `DLUX_CONFIG`** — seed defaults in code, refine in UI
- **Stable storage layout** keeps only identity columns standalone (`system_names`, logo/favicon, default language/theme, home URL, configured flag) and stores future-changing settings in JSON groups:
  - `auth_config`, `email_config`, `registration_config`, `public_root_config`, `client_ip_config`, `notification_config`
  - `layout_config`, `language_config`, `theme_config`, `typography_config`
  - `login_config`, `titlebar_config`, `sidebar_config`, `navbar_config`, and reserved `extra_config`
- **Backward-compatible runtime contract:** `get_system_config()`, `DLUX_CONFIG`, setup import/export, templates, and host callers still use flat keys such as `allowed_themes`, `public_root`, `translations_override`, and `default_table_density`.
- **Override-only translations:** `language_config.translations_override` stores only admin/dev overrides, never the merged discovered translation catalog.

### First-Launch Setup Wizard
- **8-step wizard:** Identity → Localization → Access and security → Login Page → Sidebar → Nav Bar → UI and Layout → Appearance and Typography
- **Step 3 routing controls** for the main Home URL plus optional anonymous public-root split when public root access is enabled
- **Step 4 Login Page** controls login layout style (Split / Centered / Minimal / Full-page split), show-logo toggle, logo treatment, banner colour, and per-language Markdown hero message
- **Step 7 Titlebar** includes titlebar button-shape controls, Dropdown vs Titlebar Actions user-hub layout, and orderable titlebar actions
- **Step 8 Notifications** is a dedicated step (notifications were split out of the Titlebar step) with a top-level `notifications_enabled` master toggle — like the sidebar/nav-bar enablement switches — gating flash/drawer/badge/bridge/email and automatic CRUD controls; when off, the whole notification subsystem (including `notify(...)`) is suppressed
- **Setup import/export path** for reusing System Settings payloads across environments
- **Live preview** for theme, language, sidebar, titlebar, and notification drawer/flash presentation changes
- **Unsaved preview state** with session-based language switching
- **Dynamic sidebar builder** with drag-and-drop cross-pane support
- **Theme allowlist matrix** with visual selector cards: preview circle sets the default theme, the rest of the card and checkbox toggle whether that theme is allowed
- **Translation matrix editor** plus explicit language-catalog management
- **Dlux email delivery controls** for delivery path (`direct` vs `relay`) and secret storage (`env` vs `encrypted_db`)
- **Centralized IP resolution setup** for configuring how the system identifies client IPs for logs and security throttles

### Options View (`/sys/options/`)
- Split System Settings modal entrypoints (Branding, Languages, Access & Security, Login Page, Sidebar, Nav Bar, Titlebar, Appearance)
- Theme picker with live preview
- Language picker (when enabled)
- Table density picker
- System diagnostics (privileged-only)
- User preferences panel
- Draggable card layout with browser-persisted ordering
- Double-width System Info card inside the shared Options card grid
- Standalone Autofill and Reset Defaults cards using shared external CSS/JS assets
- Titlebar notification icon with unread badge, drawer list, detail view, dismiss, mark-all-read, and clear-read actions

### Utilities & Helpers
- `dlux_settings(globals())` — one-line settings integration
- `get_system_config()` — cached config retrieval with fallback handling
- `is_scope_enabled()` — scope system status check
- `get_secret()` — env-driven secret retrieval for Docker/decrypter flows
- `require_current_password(request)` — reusable backend guard for destructive profile/security actions
- `set_profile_totp_state(profile, raw_secret=..., enabled=...)` — direct TOTP persistence helper
- `from dlux.notifications import notify` — one-line user-facing notification API with `notify.success(...)`, `notify.warning(...)`, and `notify.error(...)` helpers
- `build_archive_file_field('field_name', css_class='...')` — explicit Dlux custom file widget bridge
- `build_settings_toggle_field(form, 'field_name', css_class='...')` — shared setup/System Settings toggle-card renderer
- Settings auto-injection: apps, middleware, context processors, Crispy defaults, message tags, i18n/tz defaults

---

## 2. Scaffolding & Project Generation

### CLI Commands
| Command | Description |
|---------|-------------|
| `python -m dlux startproject <name>` | Create new DjangoLux-ready Django project |
| `python -m dlux startapp <name>` | Create DjangoLux-native app skeleton |
| `python -m dlux startapp <name> --register` | Create app + auto-register in settings/URLs |

### Generated Project Structure
- **Config package** (`config/` instead of project name reuse)
- **Docker baseline:** `.dockerignore`, `Dockerfile`, `compose.yml`, `compose.dev.yml`
- **Nginx config:** `.nginx/nginx.conf`
- **Entry scripts:** `entrypoint.sh`, `start.sh`, `start.ps1` (Windows path translation)
- **Secrets:** `.secrets/.env` with 6 bootstrap values
- **Celery worker:** `config/celery.py` with Redis broker
- **Health check:** `/health/` endpoint via `django-health-check`
- **Security headers:** `django-cors-headers` + `django-csp` pre-wired

### Generated App Structure
- `models.py` — with `ScopedModel` base import
- [forms.py](cci:7://file:///home/debeski/depy/projects/dlux-pkg/dlux/forms.py:0:0-0:0), [tables.py](cci:7://file:///home/debeski/depy/projects/dlux-pkg/dlux/tables.py:0:0-0:0), `filters.py` — with Dlux imports
- `views.py` — with list/create/update/delete views
- [urls.py](cci:7://file:///home/debeski/depy/projects/dlux-pkg/dlux/urls.py:0:0-0:0) — with namespace routing
- [translations.py](cci:7://file:///home/debeski/depy/projects/dlux-pkg/dlux/translations.py:0:0-0:0) — DLUX_STRINGS dictionary
- Templates: list and form HTML templates
- Tests: app-specific test scaffold

---

## 3. Models & Data Layer

### ScopedModel (Abstract Base)
**Audit Fields (auto-populated):**
- `created_at`, `updated_at` — timestamps
- `created_by`, `updated_by` — actor foreign keys
- `deleted_at`, `deleted_by` — soft-delete tracking

**Soft-Delete Behavior:**
- `delete()` — performs soft-delete (sets `deleted_at`)
- `restore()` — undoes soft-delete
- `hard_delete()` — permanent deletion escape hatch

**Scope Integration:**
- `scope` field (auto-hidden when scopes disabled)
- `ScopedManager` — auto-filters by user scope + excludes soft-deleted
- `all_objects` — standard manager bypass

### ScopeForeignKey
- Custom ForeignKey that hides from ModelForms when scopes disabled
- Migration-safe (deconstructs as normal ForeignKey)

### Profile Model
- One-to-one with User
- Phone number
- Profile picture (auto-resized to 300x300, converted to WebP)
- JSON preferences storage
- **2FA state fields:** email, phone, TOTP, backup codes
- `is_2fa_enabled` property
- **Trusted Device tracking**: 30-day browser trust persistence for verified 2FA logins
- **Signed-in device/session list** on the profile page with POST-only revocation, trust-status indicators, and profile activity feeds capped to the latest five project entries plus latest five system interactions

### Scope & ScopeSettings Models
- Scope isolation for multi-tenant scenarios
- Toggle for scope system enable/disable
- Auto-create scope per user option

### Notification Models
- `DluxNotification(ScopedModel)` stores durable user-facing events with level, category, source/action, model/object metadata, target URL, audience type, metadata, and expiry.
- `DluxNotificationState` stores per-user read, dismiss, and email state.
- `DluxNotificationRule(ScopedModel)` stores admin-configured JSON match/delivery routing rules.
- `DluxNotificationWatch(ScopedModel)` stores model-level watches per user/scope; object-level watches are deferred.

---

## 4. Security & Authentication (DSRP-1)

DSRP-1, the Dlux Secure Runtime Policy, is the active authorization standard.
Every runtime-exposed surface must have backend authorization that matches its
UI visibility and shortcut behavior. See [DSRP-1 Security Standard](security-dsrp-1.md).

### Multi-Factor Authentication (2FA)
| Method | Features |
|--------|----------|
| **Email 2FA** | OTP sent via Dlux email delivery, configurable in System Setup/System Settings; supports auto-send on login and 120s resend cooldown |
| **TOTP (App)** | QR code generation, pyotp-based verification |
| **Backup Codes** | 8x8-digit codes, hashed storage, generation/regeneration |
| **Trusted Devices** | 30-day browser trust for 2FA-verified or Profile-confirmed sessions, with trusted-session precedence |

**2FA Flows:**
- Unified login challenge accepts app codes, explicitly requested email OTPs, and backup codes
- TOTP setup persists secret/enabled state through `set_profile_totp_state(...)` instead of the full `Profile.save()` path
- Enable/disable endpoints and backup-code regeneration are POST-only
- Email OTP supports automatic background delivery on login and enforces a 120s resend cooldown
- Unified login challenge prioritizes Authenticator (TOTP) codes for accounts with mixed 2FA methods enabled
- AJAX-driven auto-verification on 2FA challenge screens with automatic form submission on code entry
- Backup code verification with usage tracking
- Destructive profile security actions such as 2FA disable, backup-code regeneration, and session revocation require current-password confirmation
- Trusted device status is managed per-session from the profile page with immediate revocation support
- Optional single active-session enforcement can force out every other active session when a new login or completed 2FA login connects; trusted-device records remain, but older sessions are evicted and see the session-ended page on their next request

### Public Registration Playground
- Disabled by default and SMTP-gated in setup/System Settings
- Email-first form at `/accounts/register/` with generated internal usernames
- Inactive local user creation until mandatory email verification succeeds
- Publicly created accounts display a “Public signup” provenance badge in account surfaces
- Hashed verification tokens, honeypot field, duplicate-email generic response, and cache throttles
- Activation modes: `auto_login_after_verify` and `verified_pending_approval`
- Superuser-only pending registration approval view at `/sys/registrations/`

### Security Hardening (DSRP)
- **Dynamic Modal CRUD** — backend permission enforcement
- **Section Management** — explicit `dlux.view_sections` / `dlux.manage_sections` required
- **User/Profile Modals** — self-or-staff/scope rules
- **Activity Log Access** — `dlux.view_activitylog` permission (not just `is_staff`)
- **Reset Password Flow** — requires `auth.change_user` + scope/staff/superuser checks
- **Options View** — authenticated users keep personal preferences; diagnostics remain privileged-only
- **Options Diagnostics** — superuser and Global Staff only
- **AJAX Endpoints** — 403 for non-superusers on scope management
- **Section Model Allowlisting** — only discovered section models accepted
- **2FA State Mutators** — POST-only with hashed backup codes
- **Public Registration** — disabled-by-default, email-verified, SMTP-gated, throttled, and approval actions are POST-only
- **Sidebar Permission Enforcement** — items only visible to users with the required permission; no implicit staff access
- **Runtime Asset Policy** — no inline `<style>`, executable inline `<script>`, or inline `style=` attributes unless a documented unavoidable runtime need exists

### Optional OIDC SSO Packages
- **Provider plugin** — `django-lux-sso`, installed only in a Dlux deployment that acts as the identity provider
- **Client SDK** — `django-lux-sso-client`, installable in connected Django projects without depending on `django-lux`
- **Cross-platform clients** — PHP, .NET, JavaScript, Java, Go, mobile, and desktop clients can connect through standard OIDC discovery and Authorization Code flow
- **Per-client roles** — portable `admin`, `staff`, and `user` roles; no project-generated Django permission mirroring
- **Secure defaults** — exact redirect URI checks, HTTPS outside local development, RS256 OIDC signing, and fail-closed client policy checks
- **Client mapping** — local users link by `(issuer, subject)` and provider `admin` never becomes Django `is_superuser`

### Activity Log Security
- Superuser-created log entries hidden from non-superusers
- Sensitive field masking (passwords, backup codes, TOTP secrets)
- 2-second deduplication window for duplicate action suppression

---

## 5. User Management & Profiles

### User Management Interface
- User list view with filtering
- **Online status indicator**: a live presence dot per row (pulsing green when the user was seen within the last 5 minutes via `UserPresenceSession`, muted when offline), driven by an `Exists` subquery annotation — no extra field or polling endpoint
- **2FA method badges**: a `2FA` column showing coloured badges for each active method (TOTP app / Email), or a muted "No" when none is configured
- User detail page with recent activity
- User detail modal
- Create/Edit/Permissions modals
- Optional create-user checkbox to require a first-login password change; the flag is stored in profile preferences, enforced by middleware, and cleared after the user changes their password to a value different from the current password

### Profile Management
- Edit profile modal
- Profile picture upload with WebP conversion
- Phone number management
- Preferences persistence

### Permissions
- Grouped translated permissions display
- Custom permissions: `manage_staff`, `manage_scopes`
- Scope-based permission filtering
- Permission assignment principle: users can only assign permissions they themselves have
- **Four-tier staff authorization**: Superuser, Global Staff, Central Staff, Scoped Staff
- **Staff Tier Visuals**: Shared badge classes (`dlux-staff-tier-badge`) ensure high-contrast tier visibility across all management modals and tables

---

## 6. UI Infrastructure

### Theme System (10 Built-in Themes)
| Theme | Description |
|-------|-------------|
| `light` | Clean light default |
| `blue` | Blue-tinted light |
| `gold` | Gold/amber accent |
| `green` | Green accent |
| `red` | Red accent |
| `mono` | Monochrome grayscale |
| `dark` | Dark mode with blue primal |
| `gothic` | Dark purple/cyberpunk |
| `retro` | Sepia/amber vintage |
| `neon` | Cyan glow cyber theme |

**Theme Features:**
- Runtime theme switching
- User preference persistence
- Admin-configurable allowed themes
- CSS variable-based theming
- Per-theme toolbar/popover/chip overrides

### Sidebar System
- **Resolver-driven discovery** of valid URL candidates
- **Auto-discovery** of list views from URL patterns
- **Permission-based visibility** — each sidebar item requires the user to have the associated view permission
- **Permission inference** — for class-based views, inferred from model (`app.view_model`); for function-based views, inferred from URL namespace and name pattern (`app:view_list` → `app.view_view`)
- **Explicit permission decorators** — `sidebar_permissions` and `permission_required` on views take precedence
- **Internal permission tokens** — `__dlux_user_directory__`, `__dlux_activity_log__`, `__dlux_sections_view__`, and `__dlux_authenticated__` for system routes.
- **Drag-and-drop builder** with cross-pane support
- **Runtime rendering** from stored JSON tree
- **User-level reordering** (optional)
- **Accordion groups** with state persistence
- **Active state highlighting**
- **Desktop collapse modes:** `icons`, `hidden`, `locked_expanded`
- **Density options:** dense, balanced, roomy
- **Icon visibility toggle**

### Sidebar Toolbar
- Theme picker indicator (circle showing current theme)
- Theme picker popover with color circles
- Sidebar density picker with icon chips
- Sections manager link (when models registered)
- Reorder toggle
- Auto-hide when no tools available

### Titlebar System
**Configurable Options:**
- `show_logo` — logo visibility
- `show_title` — title visibility
- `show_home_button` — home button visibility
- `logo_treatment` — none, plate, halo, contrast
- `logo_treatment_shape` — soft, pill, square for plate treatment
- `buttons_shape` — titlebar action button shape (`circle`, `square`, `squircle`); legacy `home_shape` remains accepted as an alias
- `user_hub_style` — `dropdown` preserves the user hub menu; `titlebar_actions` moves shortcuts into the right-side titlebar rail
- `actions_order` — order for `notifications`, `home`, `profile`, `help`, `users`, `activity`, `reports`, `settings`, and `auth`
- `title_align` — start, center, end
- `title_size` — sm, md, lg
- `height` — dense, balanced, roomy
- `surface` — default, muted, glass

### Shared Form Surface
- `dlux/form_base.html` — full-page forms
- `dlux/list_base.html` — list/filter pages
- Glass morphism styling
- Bootstrap 5 + Crispy Forms integration
- Theme-aware form controls
- Datepicker: `vanillajs-datepicker` with `.dlux-datepicker` class

### Tutorial/Driver System
- Driver.js integration for onboarding tours
- Step-based guided tours
- Highlight and popover positioning

---

## 7. Tables & Data Display

### DluxTable Base Class
```python
class Meta:
    template_name = "dlux/tables/table.html"
    dlux_actions = True  # Enable context menu
    dlux_per_page = 20
    dlux_per_page_options = (10, 20, 50, 100)
    dlux_density = None  # 'dense' | 'balanced' | 'roomy'
    dlux_table = True    # Use Dlux renderer
```

**Features:**
- Framework-owned `django_tables2` renderer
- Auto-adoption of stock tables into Dlux template
- Built-in pagination with per-page controls
- Density picker in footer (unless locked)
- Responsive scroll container
- Empty state with theme tokens
- Sort indicators with direction arrows

### Row Actions (Context Menu)
- View, Edit, Delete actions per row
- Permission-filtered actions
- Double-click to view
- Event-based dispatch (`dlux:record:view|edit|delete`)
- Custom action injection via [get_dlux_row_actions()](cci:1://file:///home/debeski/depy/projects/dlux-pkg/dlux/tables.py:85:4-86:27)

### Table Features
- **Density precedence:** Meta override → request `per_page` → user preference → system default → 20
- **Page size preference persistence** per user
- **RTL-aware** sort chevrons
- **Theme-aware** density cards

---

## 8. Forms & Widgets

### Form Helpers
- `setup_filter_helper()` — basic list filters
- `advanced_filter_helper()` — multi-row advanced filters with action rows
- `set_field_attrs()` — placeholder/inline label support

### Custom Widgets
- `DluxChoiceSelectorWidget` — card/chip selector for single choice
- `DluxMultipleChoiceSelectorWidget` — searchable multi-select with chips
- `ArchiveFileInput` — file upload with preview (used for logo/favicon)
- Shared crispy file/toggle helpers keep System Settings and setup widgets aligned without relying on app-order template shadowing

### Filter Helpers
- Inline label support
- Placeholder-first filter inputs
- Search submit button with theme overrides
- Direction-aware layout

### Form Assets
- `assets_head.html` — CSS includes for embedded forms
- `assets_scripts.html` — JS includes for embedded forms
- `filter_assets_head.html` — lightweight filter-only assets

---

## 9. Activity Logging & Audit

### ActivityLog Model (single source of truth)
`ActivityLog` (renamed from `UserActivityLog`, which stays importable as an alias) stores
every log with a `category`:
- `user` — project/dev work · `system` — dlux-internal · `audit` — security events
- `action` — create/update/delete/export/login/etc.
- `model_name`/`model_key`, `object_id` — related object reference
- `number` — document/record identifier
- `ip_address`, `user_agent` — request metadata
- `details` — JSON diff of changes
- `created_by`, `created_at` — inherited from ScopedModel

### Configurable logging (`log_config`, setup Step 10)
- Master switch plus per-section (`user`/`system`) enable, default create/update/delete
  toggles, retention days, and a per-model + per-action include/exclude grid.
- Replaces the old hardcoded exclusion list with config-driven gating over a non-toggleable
  correctness floor (Session and other non-integer-PK tables).

### Audit category (security trail)
- Captures failed logins, lockouts, 2FA enable/disable/failure, password changes,
  session & trusted-device revokes, and permission-denied events, each gated by a
  per-event flag.
- **Append-only**: audit rows cannot be edited or deleted in-app, and are never auto-pruned
  by default. The `dlux_prune_activity_log` command enforces per-category retention and
  skips audit unless an audit retention window is set.

### Zero-boilerplate dev logging
```python
from dlux import log_activity
log_activity("APPROVE", obj)
```
Resolves model/scope/actor/IP from the current request; honours `log_config` gating.

### Safe Logging
```python
ActivityLog.safe_log(
    user, action, model_name, object_id,
    number, details, ip_address, user_agent, scope, category
)
```
- 2-second deduplication; rolling-window User/Profile unification
- Auto-scope from user profile; category derived via `resolve_log_category`

### Diff Capture
- Field-level change tracking
- Sensitive field masking (passwords, secrets)
- Related object auto-resolution for detail modal

### Log Views
- Activity log list with user/system/audit category tabs (audit restricted to
  superusers/global staff); staff/superuser scoped
- Detail modal with structured field cards
- Profile timeline (compact format)
- User Report modal with print/PDF browser flow and XLSX export for authorized staff
- Durable known-device and presence-session history for forward-looking device, IP, browser, OS, request, and estimated-time reporting

### User Report Data Sources
- `UserActivityLog` remains the action/audit source.
- `UserKnownDevice` groups browser/device observations through a signed first-party device cookie stored only as a hash.
- `UserPresenceSession` tracks session-level presence estimates while Django sessions remain authoritative for authentication.
- `TrustedDevice` remains the 2FA trust source and can be linked to known devices for reporting context.

### Backup & Restore Operations
- Permission-gated report ZIP exports for activity/report data.
- Superuser-only system backup and restore surface at `/sys/backup/`.
- Encrypted `.dlb` full-system backups with chunked Fernet payloads, manifest metadata, migration-state comparison, and optional one-off passphrase protection.
- Cursor-safe export streaming uses primary-key pagination and a backup-local JSON serializer, avoiding PostgreSQL server-side named cursors for both model rows and many-to-many fields.
- Full system backups exclude environment/run-bookkeeping models such as sessions, content types, permissions, admin logs, report backup rows, system backup rows, and restore rows.
- Superuser password hashes are omitted from `.dlb` payloads and preserved from the target database during restore.

---

## 10. API & AJAX Infrastructure

### Dynamic Modal CRUD
- `DynamicModalManagerView` — generic list/create/update
- `DynamicModalDeleteView` — generic delete
- Auto-form/table/filter discovery via `LazyModelClasses`
- Section-based model allowlisting
- Permission enforcement
- External modal loader asset shipped with CSP nonce support in the shared base layout
- **Responsive sizing**: centered `modal-xl` at ≥1200px, full-screen below 1200px (split-screen / laptop friendly)
- **Sticky header + footer, scrolling body** (`modal-dialog-scrollable`): the title/close row and the action bar stay pinned while only the content scrolls, with a themed thin scrollbar
- **Action-bar relocation**: the standard action bar (`.dlux-form-actions` / `.dlux-setup-wizard-actions` / `.dlux-modal-form-actions`) is auto-moved into the pinned footer with form association preserved via the `form=` attribute; multi-step wizard bars (with prev/next) are left in place for the wizard controller, and table/detail/dev-custom views simply keep a hidden footer
- **Dev opt-in footer pinning**: add `data-dlux-modal-footer` to any container in a custom modal template / options view to have it pinned into the sticky footer (takes priority over the built-in bars). Submit buttons inside it are auto-associated to the modal form via `form=`; for custom buttons that need their own JS, bind via document-level delegation since the element is moved out of the modal body

### AJAX Endpoints
| Endpoint | Purpose |
|----------|---------|
| `/sys/api/last-entry/<app>/<model>/` | Autofill last entry |
| `/sys/api/details/<app>/<model>/<pk>/` | Model instance details |
| `/sys/api/details/<app>/<model>/empty_schema/` | Empty form schema |
| `/sys/api/preferences/update/` | Update user preferences |
| `/sys/api/preferences/reset/` | Reset preferences to default |

### Section Management API
- `/sys/section/details/` — section metadata
- `/sys/section/delete/` — delete section
- `/sys/subsection/add/` — create subsection
- `/sys/subsection/edit/<pk>/` — update subsection
- `/sys/subsection/delete/<pk>/` — delete subsection

### Scope Management API
- `/sys/scopes/manage/` — scope list
- `/sys/scopes/form/` — create/edit form
- `/sys/scopes/save/` — save scope
- `/sys/scopes/delete/<pk>/` — delete scope
- `/sys/scopes/toggle/` — enable/disable system
- `/sys/scopes/toggle-auto/` — toggle auto-creation

### 2FA API
- `/sys/2fa/enable/` — enable 2FA
- `/sys/2fa/setup/totp/` — TOTP setup with QR
- `/sys/2fa/verify/login/` — verify OTP during login
- `/sys/2fa/verify/enable/` — verify OTP during enable flow
- `/sys/2fa/disable/` — disable 2FA
- `/sys/2fa/backup-codes/generate/` — generate codes
- `/sys/2fa/resend/<intent>/` — resend OTP

---

## 11. Translation & Internationalization

### Translation System
- **Bidirectional:** Arabic (RTL) + English (LTR) default
- **Database overrides:** `translations_override` JSON field
- **Lazy translator:** Runtime translation resolution
- **Universal patching:** gettext/gettext_lazy/pgettext patches check DLUX_STRINGS first
- **Model meta patching:** `verbose_name` and `verbose_name_plural` wrapped with lazy translators
- **Translation-First Policy**: All new UI components (2FA, Trusted Devices, IP Config) are built without hardcoded strings, utilizing the Dlux translation framework for all user-facing copy

### Key Translation Keys
- `label_<field>` — form field labels
- `tbl_<column>` — table column headers
- `model_<name>` / `models_<name>` — model names
- `form_*`, `help_*` — form labels and help text
- `btn_*` — button labels
- `msg_*` — flash messages

### Language Picker
- Runtime language switching
- Session-based preview (for admin changes)
- User preference persistence
- Admin lock capability (`allow_user_language_override`)

---

## 12. Static Assets & JS Helpers

### JavaScript Helpers
| File | Purpose |
|------|---------|
| [prevent_double_submit.js](cci:7://file:///home/debeski/depy/projects/dlux-pkg/dlux/static/dlux/helpers/prevent_double_submit.js:0:0-0:0) | Disable submit button on form submit (5s timeout) |
| [dynamic_modal/js/main.js](cci:7://file:///home/debeski/depy/projects/dlux-pkg/dlux/static/dlux/helpers/dynamic_modal/js/main.js:0:0-0:0) | AJAX modal CRUD with fetch |
| [context_menu/js/main.js](cci:7://file:///home/debeski/depy/projects/dlux-pkg/dlux/static/dlux/helpers/context_menu/js/main.js:0:0-0:0) | Row-level context menu events |
| [context_menu/js/section_manager.js](cci:7://file:///home/debeski/depy/projects/dlux-pkg/dlux/static/dlux/helpers/context_menu/js/section_manager.js:0:0-0:0) | Section tree interactions |
| [wizard/js/main.js](cci:7://file:///home/debeski/depy/projects/dlux-pkg/dlux/static/dlux/helpers/wizard/js/main.js:0:0-0:0) | Multi-step form controller |
| [autofill/js/main.js](cci:7://file:///home/debeski/depy/projects/dlux-pkg/dlux/static/dlux/helpers/autofill/js/main.js:0:0-0:0) | Sticky form autofill |
| [scan_link/js/main.js](cci:7://file:///home/debeski/depy/projects/dlux-pkg/dlux/static/dlux/helpers/scan_link/js/main.js:0:0-0:0) | QR/barcode scanning |
| [scan_link/js/scan_button.js](cci:7://file:///home/debeski/depy/projects/dlux-pkg/dlux/static/dlux/helpers/scan_link/js/scan_button.js:0:0-0:0) | Scan button widget |
| [main/js/options.js](cci:7://file:///home/debeski/depy/projects/dlux-pkg/dlux/static/dlux/main/js/options.js:0:0-0:0) | Options card reordering, reset/defaults, and shared page behavior |
| [users/js/profile_2fa.js](cci:7://file:///home/debeski/depy/projects/dlux-pkg/dlux/static/dlux/users/js/profile_2fa.js:0:0-0:0) | POST-backed profile 2FA flows and current-password-confirmed destructive actions |

### CSS Structure
| Directory | Contents |
|-----------|----------|
| `main/css/` | Core styles (buttons, tables, forms, titlebar) |
| `sidebar/css/` | Sidebar-specific styles |
| `forms/css/` | Form widgets and fields |
| `themes/css/` | 10 theme files |
| `users/css/` | Login, profile, permissions |
| `helpers/context_menu/css/` | Context menu styling |
| `language/css/` | Language picker styles |
| `tutorial/css/` | Tutorial overlay styles |

### Key CSS Files
- [main.css](cci:7://file:///home/debeski/depy/projects/dlux-pkg/dlux/static/dlux/main/css/main.css:0:0-0:0) — Core layout and variables
- [tables.css](cci:7://file:///home/debeski/depy/projects/dlux-pkg/dlux/static/dlux/main/css/tables.css:0:0-0:0) — Table platform with density tokens
- [buttons.css](cci:7://file:///home/debeski/depy/projects/dlux-pkg/dlux/static/dlux/main/css/buttons.css:0:0-0:0) — Button variants
- [titlebar.css](cci:7://file:///home/debeski/depy/projects/dlux-pkg/dlux/static/dlux/main/css/titlebar.css:0:0-0:0) — Titlebar layout
- [options.css](cci:7://file:///home/debeski/depy/projects/dlux-pkg/dlux/static/dlux/main/css/options.css:0:0-0:0) — Shared Options card system and drag layout
- [system_setup.css](cci:7://file:///home/debeski/depy/projects/dlux-pkg/dlux/static/dlux/main/css/system_setup.css:0:0-0:0) — Setup wizard styling
- [selectors.css](cci:7://file:///home/debeski/depy/projects/dlux-pkg/dlux/static/dlux/main/css/selectors.css:0:0-0:0) — Choice selector widgets
- [template_cleanup.css](cci:7://file:///home/debeski/depy/projects/dlux-pkg/dlux/static/dlux/main/css/template_cleanup.css:0:0-0:0) — Shared CSS replacements for previously inline template styling

---

## 13. Template Tags & Filters

### dlux_tags
| Tag/Filter | Purpose |
|------------|---------|
| `{% include_if_exists %}` | Include template if it exists |
| `{% has_permission %}` | Check user permission |
| `{% get_item %}` | Dict/list item access |
| `|add_class` | Add CSS class to field |

### sidebar_tags
| Tag | Purpose |
|-----|---------|
| `{% sidebar_nav %}` | Render sidebar navigation |
| `{% sidebar_class %}` | Generate sidebar CSS classes |

### dlux_translation
- Translation string resolution
- Lazy translation proxy

---

## 14. Middleware & Request Handling

### DluxMiddleware
- Thread-local user/request storage
- Setup guard (redirects unconfigured anonymous requests)
- Root URL redirect handling
- Thread-local cleanup

### Patch System (AppConfig.ready)
**Applied on startup:**
1. **ModelForm patch** — auto-inject scope field, visibility control, translation
2. **FilterSet patch** — auto-inject scope filter, translation
3. **Table patch** — Dlux renderer adoption, scope column, translation, actions
4. **RequestConfig patch** — page size resolution with preferences
5. **Global translation patches** — gettext/pgettext/model meta

### Context Processor ([dlux_context](cci:1://file:///home/debeski/depy/projects/dlux-pkg/dlux/context_processors.py:135:0-309:18))
Provides to all templates:
- `APP_CONFIG` — system branding
- `CURRENT_LANG`, `CURRENT_DIR` — language state
- `DLUX_STRINGS` — translation dictionary
- `DLUX_THEMES` — available themes
- `user_preferences` — user prefs JSON
- [sidebar](cci:9://file:///home/debeski/depy/projects/dlux-pkg/dlux/static/dlux/sidebar:0:0-0:0) — navigation tree
- `sidebar_*` — toolbar visibility flags
- `scope_settings`, `can_view_*` — permission booleans

---

## 15. Discovery System

### Sidebar Discovery
- **URL resolver scanning** for list views
- **Name-based exclusion** (login, logout, modal, delete, etc.)
- **Permission filtering** — only show routes user can access
- **Permission inference** from model metadata, URL namespace/name patterns, and explicit decorators
- **Auto-grouping** by app label
- **Custom groups** via `EXTRA_ITEMS` config
- **Internal tokens** — system routes use `__dlux_*` tokens resolved by `user_matches_permission_token()`

### Section Discovery
- Model registry for dynamic sections
- Auto-form/table/filter class resolution
- Permission checking for section access
- Detail/delete model allowlisting

### URL Discovery
- `home_url_discovered` dropdown in setup
- Automatic list of valid named URLs
- Default home URL fallback

---

## 16. Notifications

### Zero-Boilerplate API
```python
from dlux.notifications import notify

notify("Invoice approved.")
notify.success("Saved.")
notify.error("Could not delete record.", obj=record)
notify.success(message_key="msg_password_changed")
```

Optional richer usage can target watches/email/rules without becoming mandatory boilerplate:

```python
notify("Payroll batch exported.", obj=batch, action="export", category="reports", to="watchers", email=True)
```

### Automatic Pipeline
- `ScopedModel` create/update/delete events emit notification events by default.
- Create/delete/errors flash for the actor by default; updates persist as quiet summaries.
- Update summaries reuse activity-log diff details and existing sensitive-field masking.
- Generic modal and context-menu CRUD annotate events with route/surface metadata.
- Dlux-owned backend feedback uses `notify(...)`; legacy Django messages are only drained when the compatibility bridge is enabled.
- Built-in notices can carry `message_key`/`title_key` metadata so flash notices, the titlebar drawer, and notification API responses resolve text in the current request language instead of freezing the first emitted string. Legacy rows without metadata also rerender when their stored text exactly matches a known translation value.

### Settings And UI
- `SystemSettings.notification_config` has a top-level `enabled` master gate (edited from the dedicated Notifications settings step) that turns the whole subsystem off, plus flash position, size, text size, timeout, max-visible count, drawer/badge enablement, Django-message bridge, email defaults, retention, and automatic CRUD defaults.
- Notification email toggles are disabled and server-coerced off until Dlux email delivery is configured.
- Automatic CRUD has one master switch plus per-action create/delete gates and an update mode (`off`, `summary`, `full`).
- Authenticated titlebars show a notification icon with colored unread badge, drawer list, detail view, dismiss, mark-all-read, and clear-read controls.
- Public/login pages keep flash behavior without rendering the authenticated drawer.
- Email delivery is available through existing Dlux email configuration but remains off by default.

### Routing Models
- `DluxNotificationRule` matches level/category/source/action/model/scope and can decide persist, flash, badge, email, recipients, expiry, and stop-processing.
- `DluxNotificationWatch` supports model-level watches per user/scope; object-level watches are intentionally deferred.

---

## Management Commands

| Command | Purpose |
|---------|---------|
| `dlux_setup` | Create migrations, apply migrations, run checks |
| `dlux_check` | Validate settings, apps, middleware, URLs, Crispy |
| `dlux_settings` | Inspect, unconfigure, reset, delete, export, and import the System Settings singleton |

---

## Integration Hooks

### Template Extension Points
- `dlux/includes/custom_head.html` — Custom CSS/head content
- `dlux/includes/custom_scripts.html` — Custom JS
- `dlux/base.html` — Root template with blocks

### Settings Extension
```python
from dlux.utils import dlux_settings
dlux_settings(globals())
```

Auto-handles:
- `INSTALLED_APPS` prepending
- `MIDDLEWARE` insertion (LocaleMiddleware, DluxMiddleware)
- `TEMPLATES` context processor injection
- `CRISPY_*` defaults
- `MESSAGE_TAGS` Bootstrap mapping
- i18n/tz defaults

---

## Dependencies

**Required:**
- Django 5.1+
- django-crispy-forms
- crispy-bootstrap5
- django-tables2
- django-filter
- Pillow

**Required for shipped features:**
- babel — translations
- cryptography — encrypted TOTP secrets and UI-managed encrypted SMTP secrets
- psutil — diagnostics/system monitoring
- pyotp — TOTP 2FA
- qrcode — QR code generation

**Optional (project/runtime dependent):**
- celery + redis — background tasks
- django-cors-headers — CORS
- django-csp — Content Security Policy
- django-health-check — health endpoint

---
```markdown
*Generated from codebase analysis — reflects package version 2.1.9*
```
