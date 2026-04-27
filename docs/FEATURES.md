
# Django-Microsys Complete Feature Reference

**Version:** 1.20.4b0  
**Package:** `django-microsys` — A multilingual Django framework layer for internal systems

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

---

## 1. Core System & Configuration

### SystemSettings (Singleton Model)
- **Database-backed singleton** for runtime system configuration
- **Caching layer** (24h TTL) for performance
- **Seeding from `MICROSYS_CONFIG`** — seed defaults in code, refine in UI
- **Fields include:**
  - System name (Arabic/English)
  - Logo & favicon upload with image optimization
  - Default language & theme
  - Allowed themes list with user-override permissions
  - Default table density (dense/balanced/roomy)
  - Home URL configuration
  - Public root access toggle
  - Email 2FA enable/disable
  - JSON language definitions
  - Translation overrides
  - Sidebar configuration
  - Titlebar configuration

### First-Launch Setup Wizard
- **4-step wizard:** Identity/Defaults → Languages → Sidebar → Titlebar/Appearance
- **Live preview** for theme, language, sidebar, and titlebar changes
- **Unsaved preview state** with session-based language switching
- **Dynamic sidebar builder** with drag-and-drop cross-pane support
- **Theme allowlist matrix** with visual selector cards

### Options View (`/sys/options/`)
- Split System Settings modal entrypoints (Branding, Languages, Sidebar, Titlebar)
- Theme picker with live preview
- Language picker (when enabled)
- Table density picker
- System diagnostics (privileged-only)
- User preferences panel

### Utilities & Helpers
- `microsys_settings(globals())` — one-line settings integration
- `get_system_config()` — cached config retrieval with fallback handling
- `is_scope_enabled()` — scope system status check
- `get_secret()` — env-driven secret retrieval for Docker/decrypter flows
- Settings auto-injection: apps, middleware, context processors, Crispy defaults, message tags, i18n/tz defaults

---

## 2. Scaffolding & Project Generation

### CLI Commands
| Command | Description |
|---------|-------------|
| `python -m microsys startproject <name>` | Create new MicroSys-ready Django project |
| `python -m microsys startapp <name>` | Create MicroSys-native app skeleton |
| `python -m microsys startapp <name> --register` | Create app + auto-register in settings/URLs |

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
- [forms.py](cci:7://file:///home/debeski/depy/projects/microsys-pkg/microsys/forms.py:0:0-0:0), [tables.py](cci:7://file:///home/debeski/depy/projects/microsys-pkg/microsys/tables.py:0:0-0:0), `filters.py` — with Microsys imports
- `views.py` — with list/create/update/delete views
- [urls.py](cci:7://file:///home/debeski/depy/projects/microsys-pkg/microsys/urls.py:0:0-0:0) — with namespace routing
- [translations.py](cci:7://file:///home/debeski/depy/projects/microsys-pkg/microsys/translations.py:0:0-0:0) — MS_TRANSLATIONS dictionary
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

### Scope & ScopeSettings Models
- Scope isolation for multi-tenant scenarios
- Toggle for scope system enable/disable
- Auto-create scope per user option

---

## 4. Security & Authentication (MSRP)

### Multi-Factor Authentication (2FA)
| Method | Features |
|--------|----------|
| **Email 2FA** | OTP sent via email, configurable via SystemSettings |
| **TOTP (App)** | QR code generation, pyotp-based verification |
| **Backup Codes** | 8x8-digit codes, hashed storage, generation/regeneration |

**2FA Flows:**
- Login challenge (if 2FA enabled)
- Enable/disable endpoints (POST-only for security)
- Resend OTP with rate limiting
- Backup code verification with usage tracking

### Security Hardening (MSRP)
- **Dynamic Modal CRUD** — backend permission enforcement
- **Section Management** — explicit `microsys.view_sections` / `microsys.manage_sections` required
- **User/Profile Modals** — self-or-staff/scope rules
- **Activity Log Access** — `microsys.view_activitylog` permission (not just `is_staff`)
- **Reset Password Flow** — requires `auth.change_user` + scope/staff/superuser checks
- **Options Diagnostics** — superuser-only access
- **AJAX Endpoints** — 403 for non-superusers on scope management
- **Section Model Allowlisting** — only discovered section models accepted
- **2FA State Mutators** — POST-only with hashed backup codes

### Activity Log Security
- Superuser-created log entries hidden from non-superusers
- Sensitive field masking (passwords, backup codes, TOTP secrets)
- 2-second deduplication window for duplicate action suppression

---

## 5. User Management & Profiles

### User Management Interface
- User list view with filtering
- User detail page with recent activity
- User detail modal
- Create/Edit/Permissions modals

### Profile Management
- Edit profile modal
- Profile picture upload with WebP conversion
- Phone number management
- Preferences persistence

### Permissions
- Grouped translated permissions display
- Custom permission: `manage_staff`
- Scope-based permission filtering

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
- `home_shape` — circle, square, rounded, pill
- `title_align` — start, center, end
- `title_size` — sm, md, lg
- `height` — compact, balanced, tall
- `surface` — default, glass, gradient, solid

### Shared Form Surface
- `microsys/form_base.html` — full-page forms
- `microsys/list_base.html` — list/filter pages
- Glass morphism styling
- Bootstrap 5 + Crispy Forms integration
- Theme-aware form controls
- Datepicker: `vanillajs-datepicker` with `.ms-datepicker` class

### Tutorial/Driver System
- Driver.js integration for onboarding tours
- Step-based guided tours
- Highlight and popover positioning

---

## 7. Tables & Data Display

### MicrosysTable Base Class
```python
class Meta:
    template_name = "microsys/tables/table.html"
    microsys_actions = True  # Enable context menu
    microsys_per_page = 20
    microsys_per_page_options = (10, 20, 50, 100)
    microsys_density = None  # 'dense' | 'balanced' | 'roomy'
    microsys_table = True    # Use Microsys renderer
```

**Features:**
- Framework-owned `django_tables2` renderer
- Auto-adoption of stock tables into Microsys template
- Built-in pagination with per-page controls
- Density picker in footer (unless locked)
- Responsive scroll container
- Empty state with theme tokens
- Sort indicators with direction arrows

### Row Actions (Context Menu)
- View, Edit, Delete actions per row
- Permission-filtered actions
- Double-click to view
- Event-based dispatch (`micro:record:view|edit|delete`)
- Custom action injection via [get_microsys_row_actions()](cci:1://file:///home/debeski/depy/projects/microsys-pkg/microsys/tables.py:85:4-86:27)

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
- `MicrosysChoiceSelectorWidget` — card/chip selector for single choice
- `MicrosysMultipleChoiceSelectorWidget` — searchable multi-select with chips
- `ArchiveFileInput` — file upload with preview (used for logo/favicon)

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

### UserActivityLog Model
- `action` — create/update/delete/export/login/etc.
- `model_name`, `object_id` — related object reference
- `number` — document/record identifier
- `ip_address`, `user_agent` — request metadata
- `details` — JSON diff of changes
- `created_by`, `created_at` — inherited from ScopedModel

### Safe Logging
```python
UserActivityLog.safe_log(
    user, action, model_name, object_id, 
    number, details, ip_address, user_agent, scope
)
```
- 2-second deduplication
- Auto-scope from user profile

### Diff Capture
- Field-level change tracking
- Sensitive field masking (passwords, secrets)
- Related object auto-resolution for detail modal

### Log Views
- Activity log list (staff/superuser scoped)
- Detail modal with structured field cards
- Profile timeline (compact format)

---

## 10. API & AJAX Infrastructure

### Dynamic Modal CRUD
- `DynamicModalManagerView` — generic list/create/update
- `DynamicModalDeleteView` — generic delete
- Auto-form/table/filter discovery via `LazyModelClasses`
- Section-based model allowlisting
- Permission enforcement

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
- `/sys/2fa/verify/` — verify OTP
- `/sys/2fa/enable/` — enable 2FA
- `/sys/2fa/setup/totp/` — TOTP setup with QR
- `/sys/2fa/disable/` — disable 2FA
- `/sys/2fa/backup-codes/generate/` — generate codes
- `/sys/2fa/resend/<intent>/` — resend OTP

---

## 11. Translation & Internationalization

### Translation System
- **Bidirectional:** Arabic (RTL) + English (LTR) default
- **Database overrides:** `translations_override` JSON field
- **Lazy translator:** Runtime translation resolution
- **Universal patching:** gettext/gettext_lazy/pgettext patches check MS_TRANS first
- **Model meta patching:** `verbose_name` and `verbose_name_plural` wrapped with lazy translators

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
| [prevent_double_submit.js](cci:7://file:///home/debeski/depy/projects/microsys-pkg/microsys/static/microsys/helpers/prevent_double_submit.js:0:0-0:0) | Disable submit button on form submit (5s timeout) |
| [dynamic_modal/js/main.js](cci:7://file:///home/debeski/depy/projects/microsys-pkg/microsys/static/microsys/helpers/dynamic_modal/js/main.js:0:0-0:0) | AJAX modal CRUD with fetch |
| [context_menu/js/main.js](cci:7://file:///home/debeski/depy/projects/microsys-pkg/microsys/static/microsys/helpers/context_menu/js/main.js:0:0-0:0) | Row-level context menu events |
| [context_menu/js/section_manager.js](cci:7://file:///home/debeski/depy/projects/microsys-pkg/microsys/static/microsys/helpers/context_menu/js/section_manager.js:0:0-0:0) | Section tree interactions |
| [wizard/js/main.js](cci:7://file:///home/debeski/depy/projects/microsys-pkg/microsys/static/microsys/helpers/wizard/js/main.js:0:0-0:0) | Multi-step form controller |
| [autofill/js/main.js](cci:7://file:///home/debeski/depy/projects/microsys-pkg/microsys/static/microsys/helpers/autofill/js/main.js:0:0-0:0) | Sticky form autofill |
| [scan_link/js/main.js](cci:7://file:///home/debeski/depy/projects/microsys-pkg/microsys/static/microsys/helpers/scan_link/js/main.js:0:0-0:0) | QR/barcode scanning |
| [scan_link/js/scan_button.js](cci:7://file:///home/debeski/depy/projects/microsys-pkg/microsys/static/microsys/helpers/scan_link/js/scan_button.js:0:0-0:0) | Scan button widget |

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
- [main.css](cci:7://file:///home/debeski/depy/projects/microsys-pkg/microsys/static/microsys/main/css/main.css:0:0-0:0) — Core layout and variables
- [tables.css](cci:7://file:///home/debeski/depy/projects/microsys-pkg/microsys/static/microsys/main/css/tables.css:0:0-0:0) — Table platform with density tokens
- [buttons.css](cci:7://file:///home/debeski/depy/projects/microsys-pkg/microsys/static/microsys/main/css/buttons.css:0:0-0:0) — Button variants
- [titlebar.css](cci:7://file:///home/debeski/depy/projects/microsys-pkg/microsys/static/microsys/main/css/titlebar.css:0:0-0:0) — Titlebar layout
- [system_setup.css](cci:7://file:///home/debeski/depy/projects/microsys-pkg/microsys/static/microsys/main/css/system_setup.css:0:0-0:0) — Setup wizard styling
- [selectors.css](cci:7://file:///home/debeski/depy/projects/microsys-pkg/microsys/static/microsys/main/css/selectors.css:0:0-0:0) — Choice selector widgets

---

## 13. Template Tags & Filters

### microsys_tags
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

### microsys_translation
- Translation string resolution
- Lazy translation proxy

---

## 14. Middleware & Request Handling

### ActivityLogMiddleware
- Thread-local user/request storage
- Setup guard (redirects unconfigured anonymous requests)
- Root URL redirect handling
- Thread-local cleanup

### Patch System (AppConfig.ready)
**Applied on startup:**
1. **ModelForm patch** — auto-inject scope field, visibility control, translation
2. **FilterSet patch** — auto-inject scope filter, translation
3. **Table patch** — Microsys renderer adoption, scope column, translation, actions
4. **RequestConfig patch** — page size resolution with preferences
5. **Global translation patches** — gettext/pgettext/model meta

### Context Processor ([microsys_context](cci:1://file:///home/debeski/depy/projects/microsys-pkg/microsys/context_processors.py:135:0-309:18))
Provides to all templates:
- `APP_CONFIG` — system branding
- `CURRENT_LANG`, `CURRENT_DIR` — language state
- `MS_TRANS` — translation dictionary
- `MICROSYS_THEMES` — available themes
- `user_preferences` — user prefs JSON
- [sidebar](cci:9://file:///home/debeski/depy/projects/microsys-pkg/microsys/static/microsys/sidebar:0:0-0:0) — navigation tree
- `sidebar_*` — toolbar visibility flags
- `scope_settings`, `can_view_*` — permission booleans

---

## 15. Discovery System

### Sidebar Discovery
- **URL resolver scanning** for list views
- **Name-based exclusion** (login, logout, modal, delete, etc.)
- **Permission filtering** — only show routes user can access
- **Auto-grouping** by app label
- **Custom groups** via `EXTRA_ITEMS` config

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

## Management Commands

| Command | Purpose |
|---------|---------|
| `microsys_setup` | Create migrations, apply migrations, run checks |
| `microsys_check` | Validate settings, apps, middleware, URLs, Crispy |

---

## Integration Hooks

### Template Extension Points
- `microsys/includes/custom_head.html` — Custom CSS/head content
- `microsys/includes/custom_scripts.html` — Custom JS
- `microsys/base.html` — Root template with blocks

### Settings Extension
```python
from microsys.utils import microsys_settings
microsys_settings(globals())
```

Auto-handles:
- `INSTALLED_APPS` prepending
- `MIDDLEWARE` insertion (LocaleMiddleware, ActivityLogMiddleware)
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

**Optional (degrade gracefully):**
- psutil — system monitoring
- pyotp — TOTP 2FA
- qrcode — QR code generation
- babel — translations
- celery + redis — background tasks
- django-cors-headers — CORS
- django-csp — Content Security Policy
- django-health-check — health endpoint

---
```markdown
*Generated from codebase analysis — reflects package version 1.20.4b0*
```
