# Admin Guide

This guide is for superusers and operators who configure microSYS from the UI after the package is installed.

## How Runtime Configuration Works

microSYS stores configuration in three layers:

- framework defaults from the package itself
- project defaults from `settings.MICROSYS_CONFIG`
- runtime overrides in the `SystemSettings` singleton

User-specific preferences live separately in `Profile.preferences`. That is where theme, language, sidebar state, and autofill choices are persisted.

## First-Launch Setup Wizard

The setup wizard lives at `/sys/setup/` and is only intended for the initial system configuration pass. It is the canonical place to establish the project-wide defaults that later users inherit.

![Setup wizard capture slot](assets/setup-wizard.webp)

The wizard currently runs in six steps:

1. Identity
   This step sets language-keyed system names (a JSON dict such as `{"en": "System", "ar": "النظام"}`), logo, and favicon. It also includes the JSON setup import control, which can prefill the wizard from a previously exported Microsys setup file.

2. Localization
   This step manages language-keyed system names, the explicit language catalog, default language, user language override policy, and the translation matrix editor. English and Arabic are built in; custom languages are available to users only after an admin adds them here.

3. Access and security
   This step controls public root access, the global Home URL, the optional split between authenticated Home and anonymous public-root destinations, public registration/email 2FA, Microsys email delivery, and centralized Client IP resolution (direct, header-based, or proxy-aware modes). Use delivery path `Internal SMTP relay` for generated Docker projects where the web service is isolated, or `Direct SMTP from web service` when web has SMTP egress. Secret storage can be environment/secrets or encrypted database.

4. Navigation
   This step manages the sidebar builder and sidebar behavior controls.

5. UI and Layout
   This step manages table-density defaults, titlebar controls (logo/home visibility, shape, alignment, height, and surface style), and the optional titlebar-hide rule for anonymous public home traffic.

6. Appearance and Typography
   This step manages theme availability, default theme, theme override policy, and the Dynamic Font Management system.

Useful language/system-name patterns:

```json
{
  "ar": { "name": "العربية", "dir": "rtl", "flag": "🇱🇾" },
  "en": { "name": "English", "dir": "ltr", "flag": "🇬🇧" }
}
```

```json
{
  "en": "System",
  "ar": "النظام",
  "fr": "Systeme"
}
```

The translation matrix shows keys from Microsys and installed app `translations.py` files. It is grouped by source tab, such as Microsys, each installed app, project-level translations, and settings-only override keys. Existing code-level translations prefill cells, but only admin edits are saved into the database override layer.

When the wizard is saved:

- the system is marked configured
- the selected default theme and language become the starting point for new users
- the saved sidebar tree becomes the runtime base sidebar
- the chosen home URL becomes the global titlebar Home destination
- the sidebar reorder and toolbar flags become part of the runtime sidebar behavior

Superusers can export the current setup from the Options System Settings card. The exported JSON is intended for development and staging workflows where the same setup needs to be reused repeatedly. It includes DB-backed operational settings such as names, language catalog, translation overrides, home URL, optional anonymous public-root URL/split toggle, Client IP resolution config, sidebar, titlebar, security toggles, themes, and density defaults. Logo and favicon are exported as stored file names only; the binary media files are not embedded.

## Sidebar Builder and Runtime Navigation

The sidebar builder is not just a setup-only toy. It feeds the actual runtime sidebar tree, so the structure you save is what users start from.

![Sidebar builder capture slot](assets/sidebar-builder.webp)

Important behaviors:

- the builder uses discovered URLs instead of old suffix-only assumptions
- hidden microsys, Django admin, and health-check routes are excluded from the public navigation catalog
- **sidebar items are only visible to users who have the required view permission** — there is no implicit staff access; each item's permission is inferred from the model, URL pattern, or explicit decorator
- icons, labels, and grouping can be curated in the inspector
- the global Home URL is now independent from sidebar structure
- runtime user reordering works as a personal override layered on top of the system base tree when reorder is enabled
- the sidebar toolbar can be disabled entirely if a project does not want the runtime theme picker and reorder entrypoint in the sidebar footer
- the built-in Dynamic Sections Manager shortcut lives in that toolbar; if you disable it and still want UI access, expose the relevant Microsys system item inside the sidebar tree instead
- the runtime sidebar now uses one shared flat rail layout across themes, while each theme can still supply its own accent colors, active states, and toolbar styling without changing the geometry

Operationally, that means you can keep a carefully curated default navigation while still letting users personalize their own ordering later.

## Themes and the Shared Theme Registry

microSYS now keeps its official theme list in one shared registry. That registry drives:

- setup and System Settings theme choices
- runtime theme validation and fallback behavior
- sidebar theme-picker ordering and preview swatches
- base-template theme stylesheet inclusion

Operationally, that means theme additions should be treated as framework-level changes rather than one-off CSS drops. If a theme exists in the official registry, it should appear consistently across setup, options, and the live runtime UI.

The current official order is:

- `light`
- `blue`
- `gold`
- `green`
- `red`
- `mono`
- `dark`
- `gothic`
- `retro`
- `neon`

## Typography and Font Management

microSYS features a centralized, dynamic Font Management system that allows admins to control the typography across the entire application without modifying CSS.

### Font Registry

The system maintains a registry of approved fonts located in `microsys/fonts.py`. These fonts are hosted locally under `static/microsys/fonts/`, ensuring the system remains functional in offline or air-gapped environments.

### Admin Controls

From the **Appearance and Typography** setup step (or the corresponding System Settings modal), admins can:

- **Allowed Fonts**: Select which fonts from the registry are available for use in the system.
- **Default Fonts per Language**: Assign a specific default font for each active language (e.g., a specific font for Arabic and another for English).
- **Allow User Overrides**: Decide if individual users can choose their own preferred font from the allowed list in their Options panel.

### Technical implementation notes:

- **FOUC Prevention**: The system includes early-load logic in `base_head.js` to inject the selected font CSS variable (`--ms-main-font`) before the page renders, preventing "Flash of Unstyled Content".
- **Global Control**: The entire UI honors the `--ms-main-font` variable for typography consistency.

## Options View

After first launch, day-to-day configuration continues in `/sys/options/`.

![Options view capture slot](assets/options-view.webp)

The Options screen currently provides:

- accessibility toggles such as high contrast, grayscale, invert, large text, and reduced animations
- privileged system information such as server time, storage usage, Python version, Django version, DRF version, and the current app version
- theme switching
- language switching
- typography/font switching (if allowed by admin)
- table-density switching for the current user
- autofill enable or disable
- reset-to-defaults for user preferences
- a superuser-only System Settings button that opens focused Branding, Languages, Access & Security, Sidebar, UI & Layout, and Appearance modals
- a superuser-only setup export action for reusing System Settings across development environments

Options layout note:

- the cards are intentionally reorganizable from their drag handles
- card order persists per browser in local storage, not in `Profile.preferences`
- the System Info card intentionally stays wider than the rest of the cards inside the grid

Security note:

- the diagnostics card is now staff/superuser-only
- ordinary authenticated users still keep their personal preference controls in Options

Operational note:

- dark themes are expected to skin both the language picker and theme-preview selectors on this page so inactive choices do not fall back to light/white treatment

That means the setup wizard is for initial onboarding, while the Options view is the ongoing operational hub.

## Detailed Configuration Instructions

### Client IP Resolution Modes

Admins can configure how microSYS identifies the client IP address in Step 3 (Access and Security). This is critical for accurate activity logging and security tracking.

- **Direct**: Use `REMOTE_ADDR` directly. This is the correct choice if the web server is facing the internet directly without a proxy.
- **Proxy-Aware (X-Forwarded-For)**: Parses the `HTTP_X_FORWARDED_FOR` header. Use this if the application is behind a standard reverse proxy (like Nginx or HAProxy). You can specify the number of **Trusted Proxy Hops** to ignore from the right.
- **Custom Header**: Use a specific header provided by your infrastructure (e.g., `HTTP_CF_CONNECTING_IP` for Cloudflare).

### Two-Factor Authentication (2FA) & Trusted Devices

microSYS provides multiple layers of authentication security.

- **Email 2FA**: If enabled, the system will send a one-time password (OTP) to the user's registered email during login. Admins must ensure a working **Email Delivery Path** is configured.
- **Authenticator App (TOTP)**: Users can link an app like Google Authenticator for code-based 2FA.
- **Trusted Devices**: During 2FA verification, users can check "Trust this device for 30 days". 
    - Admins can view and revoke these trust records from the user's profile in the **Signed-in Devices** card.
    - Revoking a device trust forces the user to complete a 2FA challenge on their next login from that browser.
    - Revoking a session immediately logs the user out from that device.

## Themes, Languages, and Home URL

The most common admin-facing configuration tasks are:

- changing the default theme used before a user saves a personal preference
- changing the default language used before a user saves a personal preference
- changing the default table density used before a user saves a personal preference
- updating the list of available languages
- adding translation overrides without touching code
- adjusting the global home URL used by the titlebar Home button
- optionally routing anonymous public-root traffic to a different destination from the authenticated Home URL

The safest mental model is:

- use `MICROSYS_CONFIG` to seed defaults in code
- use System Settings to refine the live runtime configuration
- use user preferences for per-user display choices

## Tutorial and User-Facing Runtime Behavior

microSYS includes a built-in tutorial system that targets the current view path. Users may see different guided steps on `/sys/`, `/sys/users/`, `/sys/sections/`, and other supported pages.

Project-specific tutorial additions should extend this built-in system rather than replace it. The intended developer path is to load a project script through `templates/microsys/includes/custom_scripts.html` and register `window.get_custom_tutorial_steps(path)`. See the customization guide for the supported extension pattern.

Other admin-facing runtime behaviors to expect:

- user management uses the interactive two-step modal wizard
- permission labels are translated dynamically
- profile pages expose 2FA controls and backup-code workflows
- activity logs show diffs and download/export context

2FA operational note:

- enable, disable, backup-code generation, TOTP setup, and OTP resend flows are now POST-backed actions rather than GET-triggered links
- email 2FA supports background auto-sending on login and enforces a 120s resend cooldown
- destructive profile security actions now ask for the current password before the backend mutation is allowed to proceed
- sessions can be marked as "Trusted" for 30 days during 2FA verification to skip subsequent challenges on the same browser

## Activity Logs in Daily Use

The activity log screen lives at `/sys/logs/` and is intended to be an operational audit surface, not just a developer debug page.

What admins and staff can expect to see there:

- CRUD events captured from signal-driven model saves and deletes
- login and logout events
- merged User/Profile updates recorded as one logical "User Profile" history stream
- masked sensitive fields such as passwords and backup codes
- download and export activity coming from the universal fetcher and Excel exporter
- scope-aware visibility for staff who should not see every system-wide action

The detail modal resolves the related object when possible, so an audit row can often be traced back to the underlying model instance instead of staying as a dead log record.

## User Preferences

User preferences are stored in `Profile.preferences` and updated through the Preferences API. Common keys include:

- `theme`
- `lang`
- `table_density`
- `table_page_size`
- `font`
- `sidebar_collapsed`
- `sidebar_accordions`
- `sidebar_order`
- `autofill_enabled`

Resetting preferences from the Options screen clears both the stored preference payload and the related session keys.

## Staff Authorization Tiers

microSYS distinguishes three staff authorization tiers for user management:

| Tier | Scope | Requirements | User Management Powers |
|------|-------|--------------|------------------------|
| **Superuser** | None | `is_superuser=True` | Full god mode — create, edit, delete any user including other superusers |
| **Global Staff** | None (NULL) | `is_staff=True` + `microsys.manage_scopes` permission | Create/manage scopes, assign users to any scope, view and edit ALL users (scoped and scopeless) |
| **Central Staff** | None (NULL) | `is_staff=True` (NO `manage_scopes`) | Create/manage scopeless (NULL scope) users ONLY — completely blind to scoped users and their data |
| **Scoped Staff** | Assigned scope | `is_staff=True` + scope assignment | Create/manage users within their assigned scope only |

### Creating Global Staff

Only **superusers** can create Global Staff users. To create a Global Staff member:

1. Sign in as superuser
2. Go to `/sys/users/` → Add User
3. Check **Staff Status**
4. In Permissions, select **"Can manage scopes and all users"** (`microsys.manage_scopes`)
5. Leave **Scope** empty (NULL)

Global Staff can then:
- Create and manage scopes
- Create users in any scope (or scopeless)
- View and edit ALL users regardless of scope
- Assign scopes to existing users

### Creating Central Staff

**Global Staff** or **superusers** can create Central Staff. To create a Central Staff member:

1. Sign in as Global Staff or superuser
2. Go to `/sys/users/` → Add User
3. Check **Staff Status**
4. In Permissions, select `microsys.manage_staff` (but NOT `microsys.manage_scopes`)
5. Leave **Scope** empty (NULL)

Central Staff can then:
- Create and manage scopeless users only
- Cannot see scoped users in the user list
- Cannot assign scopes to any user
- Cannot access scope management

### Creating Scoped Staff

Any staff member with `manage_staff` permission can create Scoped Staff. To create a Scoped Staff member:

1. Sign in as staff with `manage_staff` permission
2. Go to `/sys/users/` → Add User
3. Check **Staff Status**
4. Select a **Scope** for the user
5. The new user will only be able to manage other users in that same scope

This tier system ensures that:
- Ministers and scoped users have privacy from Central Staff
- Central Staff can handle routine user management for the core system without accessing private ministry data
- Global Staff can administer the entire multi-tenant system without needing full superuser privileges

### Permission Assignment Principle

**Users can only assign permissions they themselves have.** This is enforced at the form level:

- Non-superusers see ONLY the permissions they have been granted (directly or through groups)
- `manage_staff` permission can only be assigned by users who have it
- `manage_scopes` permission can only be assigned by superusers (who can create Global Staff)
- `view_activitylog` permission can only be assigned by users who have it

This prevents privilege escalation where a user could grant themselves or others permissions they don't possess.
