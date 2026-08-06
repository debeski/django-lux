# Admin Guide

This guide is for superusers and operators who configure DjangoLux from the UI after the package is installed.

## How Runtime Configuration Works

DjangoLux stores configuration in three layers:

- framework defaults from the package itself
- project defaults from `settings.DLUX_CONFIG`
- runtime overrides in the `SystemSettings` singleton

User-specific preferences live separately in `Profile.preferences`. That is where theme, language, sidebar state, and autofill choices are persisted.

## First-Launch Setup Wizard

The setup wizard lives at `/sys/setup/` and is only intended for the initial system configuration pass. It is the canonical place to establish the project-wide defaults that later users inherit. On an unconfigured system, `/sys/setup/` first asks for the setup language; choosing either English or Arabic immediately opens the wizard in that language and direction. This choice controls only the first-launch setup UI. The actual app default language is still chosen separately in the Localization step.

![Setup wizard capture slot](assets/setup-wizard.webp)

The wizard currently runs in fourteen steps:

1. Identity
   This step sets language-keyed system names (a JSON dict such as `{"en": "System", "ar": "النظام"}`), logo, favicon, and footer. It also includes the JSON setup import control and, while public root access is enabled, the public-root page title and meta description.

2. Localization
   This step manages language-keyed system names, the explicit language catalog, default language, user language override policy, and the translation matrix editor. English and Arabic are built in; custom languages are available to users only after an admin adds them here.

3. Email
   SMTP lives in its own step, ahead of Access and security because so much of that step depends on it. An **Enable email delivery** toggle reveals transport, provider preset, secret storage, host/port/TLS, credentials, sender address, and failure-alert recipients. Use `Internal SMTP relay` for generated Docker projects where the web service is isolated, or `Direct SMTP from web service` when web has SMTP egress; secret storage can be environment/secrets or encrypted database.

   **Apply email settings** saves just this step in place, so you can enter SMTP details and test them without closing the modal. The test deliberately sends with the *stored* configuration rather than what is on screen: with relay transport the sending process is a separate container (`python -m dlux.smtp_relay`, shipped inside dlux) that reads config from the database, so a test against unsaved values would prove nothing about what the relay will do. Apply first, then test.

   The **Send test email** button is the gate, not a convenience: a successful send records `email_config.verified` against a fingerprint of the exact connection it used, and that is what unlocks every mail-dependent setting. Editing any connection field (host, port, TLS/SSL, username, password, from-address, transport, secret storage) clears verification and requires a fresh test — the flag only ever vouches for a configuration that was actually proven. A failed test clears it too. Verification is never exported, since one host's result says nothing about another.

   The step also carries three operator aids: a **provider preset** (Gmail, Outlook/Office 365, Amazon SES, Mailgun, internal relay, or custom) that prefills SMTP host/port/STARTTLS/SSL in the UI; **failure alert recipients** — a comma/newline list of emails warned **in-app** (never by email — that path is what failed) through the notification subsystem with a matching `audit` activity-log row whenever transactional mail fails to send (requires notifications enabled); and a **Send test email** button (`POST sys/settings/email/send-test/`, superuser-only) that sends a one-off message using the saved configuration so you can verify SMTP before relying on OTP or registration mail. Save the form before testing — the button uses the persisted config, not unsaved field values. The preset and failure-recipient list persist in `SystemSettings.email_config`; the test recipient is transient.

   When **Internal SMTP relay** is selected the app connects to `smtp-relay:1025` in plaintext and the relay makes the real provider connection, so a failure has two hops to attribute. The app waits 75s in relay mode (30s direct) while the relay gives up on the provider at 60s (`SMTP_RELAY_UPSTREAM_TIMEOUT`), so the relay always answers first with `451 Relay delivery failed: <reason>` carrying the provider's actual error. Those defaults assume a **slow** upstream: a mail server can answer connect, EHLO and AUTH instantly and still take 30-60s to accept the message body, so a timeout tuned to the handshake fails every send while looking like an outage. If yours is slower still, raise `SMTP_RELAY_UPSTREAM_TIMEOUT` and keep the client above it. Keep that ordering if you tune either value — invert it and every relay failure reads as a bare client timeout, with the real cause visible only in `docker compose logs smtp-relay`.

   Until email is both enabled and verified, **email 2FA**, **forgot password**, **public registration**, and the **notification email** toggles render disabled with a hover tooltip explaining why. They are locked, not cleared: the stored value is preserved, so turning email off or editing SMTP can never silently disable someone's 2FA or password recovery. Mail *delivery* itself is unaffected — a deployment that configures SMTP through environment variables keeps sending exactly as before, its toggles simply read locked until someone runs the test once. Local debug email backends unlock without a test send.

4. Access and security
   This step controls public root access, the global Home URL, the optional split between authenticated Home and anonymous public-root destinations, public registration/email 2FA, and centralized Client IP resolution (auto-detect, direct, header-based, or proxy-aware modes). The mail-dependent toggles here stay locked until the Email step above is enabled and verified.

   Public root is the master switch for presentation controls in their canonical categories: page title and metadata in Identity, sidebar visibility in Sidebar, titlebar visibility in Titlebar, and the fixed anonymous theme in Themes and Typography. Those controls stay hidden while public root access is off. When public registration is enabled, a **registration honeypot** toggle (default on) governs the hidden `website` bot-trap field.

5. Login Page
   This step controls how the public login screen is presented: the layout **style** (Split, Centered, Minimal, or Full-page split), a **Show Logo** toggle, the **logo treatment** (none / plate / halo / contrast, with plate shape), an optional **banner colour** (any CSS colour; empty = theme default), and — for the Full-page split style only — a per-language Markdown **hero message** shown on the start half beside the form. Settings persist to `SystemSettings.login_config`.

6. Sidebar
   This step manages the sidebar builder and sidebar behavior controls. **Show sidebar on public root** appears here only while public root access is enabled.

7. Nav Bar
   This step manages the optional authenticated Nav Bar, including hierarchy/history mode, user override policy, and the static hierarchy tree. Its pinned **Navigation Root** selector keeps the existing neutral Root by default, can follow the configured homepage, or can use a specific discovered page. A selected page becomes the trail boundary for itself and its descendants without moving or rewriting nodes in the stored hierarchy. During first-launch setup, enabling an empty Nav Bar tree can seed it from the configured sidebar accordions.

8. Titlebar
   This step manages titlebar controls (logo/home visibility, logo treatment, action-button shape, Dropdown vs Titlebar Actions user-hub layout, action ordering, alignment, height, and surface style). A **Show titlebar language switcher** toggle adds a single titlebar button that cycles through the available languages; it is disabled unless user language override is allowed and more than one language exists. **Show titlebar on public root** appears here only while public root access is enabled.
   This step also configures **Global Search**: a titlebar search box that jumps to pages, settings, and actions from anywhere (press **Ctrl/⌘-K** to focus it). Choose **Icon, expand on focus** (default), **Always visible**, or **Disabled**. While search is enabled, an **Include data records in search** toggle appears — when on, search also matches records the user is allowed to view (not just app components). Settings results deep-link straight to the right settings step, so searching e.g. "inactivity" or "backup" takes you there directly.

9. Notifications
   This step controls the notification subsystem, including the flash, drawer, badge, browser bridge, email delivery, and automatic CRUD notification behavior.

10. Themes and Typography
   This step contains only theme, colour, and Dynamic Font Management controls. The fixed public-root theme appears here only while public root access is enabled.

11. Layout
   This step owns system defaults for table density and behavior, form density, modal size, Options-page style, audit-field visibility, and soft-delete review visibility.

12. Logging
   This step manages user/system activity logging, audit event logging, and retention controls.

13. Profile Page
   This step controls the profile page modules and first-login user setup/onboarding options.

14. Backups
   This step controls scheduled backup, storage, and retention policy.

The first-launch page expands to the available page width and hides the runtime sidebar toggle because the runtime sidebar is not rendered during initial setup. Its bullet-style step navigation bar jumps to the corresponding setup step while staying synchronized with the wizard's Next and Previous buttons. The default-language control is save-only: changing it in first-launch setup or later System Settings modals no longer previews the language or reloads the page, and it remains editable independently of the initial setup-language choice.

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

The translation matrix shows keys from Dlux and installed app `translations.py` files. It is grouped by source tab, such as Dlux, each installed app, project-level translations, and settings-only override keys. Existing code-level translations prefill cells, but only admin edits are saved into the database override layer.

When the wizard is saved:

- the system is marked configured
- the selected default theme and language become the starting point for new users
- the saved sidebar tree becomes the runtime base sidebar
- optional Nav Bar settings decide whether an authenticated top-of-content trail uses a configured hierarchy or session history
- the chosen home URL becomes the global titlebar Home destination
- the sidebar reorder and toolbar flags become part of the runtime sidebar behavior

Superusers can export the current setup from the Options System Settings card. The downloaded filename uses `dlux-{project-slug}-{YYYY-MM-DD}.json`, where the project slug comes from the deployed project `BASE_DIR` folder name (generic container work-dir names such as `app`, `src`, or `code` are skipped), falling back to the configured English System Settings name when one is set, and finally to `project`. The exported JSON is intended for development and staging workflows where the same setup needs to be reused repeatedly. It includes DB-backed operational settings such as names, language catalog, translation overrides, home URL, optional anonymous public-root URL/split toggle, Client IP resolution config, notifications, login page, sidebar, Nav Bar, titlebar, security toggles, themes, fonts, density defaults, and reserved `extra_config` host data. Logo and favicon are exported as stored file names only; the binary media files are not embedded.

The database stores most of those values in grouped `SystemSettings` JSON fields (`auth_config`, `registration_config`, `public_root_config`, `language_config`, `theme_config`, `typography_config`, `layout_config`, and related UI configs), but exports remain flat and imports accept both flat keys and grouped aliases. The `dlux.system` registry is the canonical internal source for those group constants, defaults, normalizers, legacy aliases, export/import field coverage, and simple scalar form packing. The `dlux.models.default_*_config` wrappers must remain importable because published migrations `0001`/`0002` serialize those callable paths. Translation exports include only `translations_override` edits, not the full merged translation catalog.

On a fresh, unconfigured project, `python manage.py migrator` checks `BASE_DIR/config.json` immediately after database migrations and applies a valid exported payload or direct settings dict before web readiness. `/sys/setup/` performs the same row-locked check as a fallback when startup does not use `migrator`. Missing or invalid files leave manual setup available and are reported by the migrator; already configured systems never treat `config.json` as a live settings layer.

## Sidebar Builder and Runtime Navigation

The sidebar builder is not just a setup-only toy. It feeds the actual runtime sidebar tree, so the structure you save is what users start from.

![Sidebar builder capture slot](assets/sidebar-builder.webp)

Important behaviors:

- the builder uses discovered URLs instead of old suffix-only assumptions
- hidden dlux, Django admin, and health-check routes are excluded from the public navigation catalog
- **sidebar items are only visible to users who have the required view permission** — there is no implicit staff access; each item's permission is inferred from the model, URL pattern, or explicit decorator
- icons, labels, and grouping can be curated in the inspector
- **names can be overridden per language** — the inspector shows one name field for each configured language (like the Nav Bar builder). Fill in the languages you want to rename and leave the rest blank; a blank language automatically uses the auto-translated route name, and the runtime sidebar always resolves each viewer's own display language. Overrides are stored per entry as a `labels` map (`{lang_code: name}`)
- the global Home URL is now independent from sidebar structure
- runtime user reordering works as a personal override layered on top of the system base tree when reorder is enabled
- the sidebar toolbar can be disabled entirely if a project does not want the runtime theme picker and reorder entrypoint in the sidebar footer
- the built-in Dynamic Sections Manager shortcut lives in that toolbar; if you disable it and still want UI access, expose the relevant Dlux system item inside the sidebar tree instead
- the runtime sidebar now uses one shared flat rail layout across themes, while each theme can still supply its own accent colors, active states, and toolbar styling without changing the geometry
- model-backed section entries show the current user's unread notification count, and groups show the unique total across their child sections; the Sidebar **Show notification badges in sidebar** toggle is separate from the notification drawer badge toggle, and counts update after read/dismiss actions

Operationally, that means you can keep a carefully curated default navigation while still letting users personalize their own ordering later.

## Optional Nav Bar

Step 6 owns the optional authenticated Nav Bar. When enabled, it appears above page content beside the sidebar and uses the same translated UI layer as the rest of Dlux.

- **Hierarchy** uses the visual Step 6 tree editor. Discovered routes provide translated labels, and manual grouping nodes can add non-clickable labels or URL-backed shared ancestors. The **node inspector sits on its own row above** the tree and available-routes panes: **Add Group** is always available there, while the move/remove actions, a **Clear selection** (✕) button, the optional URL, and the per-language name fields appear once you select a node. Manual grouping-node names are shown in your current display language in the editor.
- **Show system items** — Dlux's own system-management and authentication routes (Options, Users, Activity Log, Backup, Sections) are hidden from the available routes by default; enable the toggle to place or override one of them in the Nav Bar tree.
- **History** keeps one six-entry recent trail in the current browser session, deduplicates repeated paths without treating filters, sorting, or pagination query strings as new pages, and resolves known route labels in the active interface language.
- **User override** is available in Options only when the developer allows it. Otherwise the developer-selected default style stays authoritative.
- Dlux-owned system views are automatically grouped under an unclickable `System` crumb when accessible. When a Dlux route is not explicitly placed in the hierarchy builder, its fallback breadcrumb can infer Dlux-owned page links; for example Backup & Restore appears under Application Options because `/sys/options/` links to `/sys/backup/`. Configurable Dlux system routes are available in the builder, and an explicit placement for that route overrides the inferred parent.

Dynamic object and tab pages can supply a `dlux_navbar_crumbs` runtime context list when their labels cannot be modeled by the static hierarchy tree. Runtime crumbs take precedence over the stored tree; unconfigured pages fall back to the translated Root/System/default route-label chain.

## Themes and the Shared Theme Registry

DjangoLux now keeps its official theme list in one shared registry. That registry drives:

- setup and System Settings theme choices
- runtime theme validation and fallback behavior
- sidebar theme-picker ordering and preview swatches
- base-template theme stylesheet inclusion

The list combines bundled themes with project-owned themes registered through
`DLUX_CUSTOM_THEMES`. Registered project themes participate in the same setup,
allowlist, default, user-picker, and public-root controls. See the
[Customization Guide](customization-guide.md#project-configured-custom-themes)
for the setting and scoped CSS contract.

The current bundled order is:

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
- `prism`
- `aether`

The Aether theme uses a reduced-motion-aware drifting light field. Its sheen reverses
at each endpoint so the background animation remains continuous without a lighting
jump when the cycle repeats.

## Typography and Font Management

DjangoLux features a centralized, dynamic Font Management system that allows admins to control the typography across the entire application without modifying CSS.

### Font Registry

The system combines the bundled registry in `dlux/fonts.py` with project-owned
families declared through `DLUX_CUSTOM_FONTS`. Both use locally hosted WOFF2
static assets, keeping the system functional in offline or air-gapped
environments. See the
[Customization Guide](customization-guide.md#project-configured-custom-fonts)
for the project setting format.

### Admin Controls

From the **Themes and Typography** setup step (or the corresponding System Settings modal), admins can:

- **Theme Matrix**: Each theme card shows a checkbox and a visual preview circle. Click the large preview circle to make a theme the default. Click the rest of the card, or the checkbox inside it, to allow or disable that theme for runtime user selection. The active card and preview-ring styling identify the default theme.
- **Allowed Fonts**: Select which fonts from the registry are available for use in the system.
- **Default Fonts per Language**: Assign a specific default font for each active language (e.g., a specific font for Arabic and another for English).
- **Allow User Overrides**: Decide if individual users can choose their own preferred font from the allowed list in their Options panel.

### Technical implementation notes:

- **FOUC Prevention**: The system includes early-load logic in `base_head.js` to inject the selected font CSS variable (`--dlux-main-font`) before the page renders, preventing "Flash of Unstyled Content".
- **Global Control**: The entire UI honors the `--dlux-main-font` variable for typography consistency.

## Options View

After first launch, day-to-day configuration continues in `/sys/options/`.

![Options view capture slot](assets/options-view.webp)

The Options screen currently provides:

- accessibility toggles such as high contrast, grayscale, invert, large text, and reduced animations
- privileged system information such as server time, storage usage, Python version, Django version, DRF version, and the current app version. Two optional version rows appear only when their environment variables are injected by the deployment: `DECRYPTER_VERSION` → Decrypter Version, and `COMPOSER_VERSION` → Composer Version (set automatically when the project is run through the composer)
- live service diagnostics for the Database, Cache, API, Email, and Tasks (Celery). The Database and Cache rows include the detected server version (the Cache row appends the Redis server version when the default cache is Redis, probed live via the cache client's `INFO`). The Tasks (Celery) row is **on-demand only**: an Options page load never pings the broker. When Celery is configured, the row shows a neutral **Not checked** badge (or the last outcome from a previous check) plus a circular recheck arrow. Clicking the arrow loads the project Celery app and pings the workers once, then shows **Online** with the number of workers that answered, **Offline** when the broker errors or no worker responds, or **Configured** when Celery is set up but its app cannot be loaded to run the ping. The result is persisted (in the default cache, no expiry) so the badge keeps its last outcome across visits until the next manual check. The recheck endpoint (`POST /sys/api/celery-health/`) is restricted to superusers and global staff. (There is no longer an automatic probe or a `DLUX_CELERY_HEALTH_TTL` window — both were removed in favour of this manual check.)
- theme switching
- language switching
- typography/font switching (if allowed by admin)
- table-density switching for the current user
- autofill enable or disable
- reset-to-defaults for user preferences
- a superuser-only System Settings card that opens focused Branding, Languages,
  Access & Security, Login Page, Sidebar, Nav Bar, Titlebar, Notifications,
  Themes & Typography, Layout, Logging, Profile Page, and Backups modals
- a superuser-only setup export action for reusing System Settings across development environments
- a superuser-only Backup & Restore card that summarizes the latest full backup, completed/protected backup counts, and latest restore before opening `/sys/backup/`
- generated Compose deployments also show installed/latest verified DjangoLux versions and the last update check in System Info; Global Staff see read-only state, while superusers can check, review/apply, and roll back manifest-approved releases

Focused System Settings modals render only the active step's heavy theme, font, language, and builder matrices. They retain the saved theme/language catalog counts as lightweight form metadata, allowing the live preview to preserve the Options cards and sidebar theme selector when an unrelated step is opened; the active Themes or Languages step still calculates visibility from its current controls.

Options layout note:

- the cards are intentionally reorganizable from their drag handles
- card order persists per browser in local storage, not in `Profile.preferences`
- the System Info card intentionally stays wider than the rest of the cards inside the grid
- in tabbed Options style, Theme and Language are always separate tabs; the small-choice compact merge is only used by the card/compact layouts

Security note:

- the diagnostics card is now staff/superuser-only
- ordinary authenticated users still keep their personal preference controls in Options
- inline apply/rollback controls are superuser-only, CSRF-protected, and require the current password; no update is installed by the daily background check

Inline update note:

- `v1.2.7` is the current repaired updater baseline and requires one normal project-image rebuild; it also clears stale degraded/maintenance markers left by the v1.2.4-v1.2.6 Celery-startup race
- after that rebuild, only releases that pass the official PyPI hash, attestation, dependency, Python, manifest, migration, and candidate-preflight gates show **Review and update**
- the confirm-update modal offers a pre-update backup choice — **Quick (data-only, default)**, **Full (database + media)**, or **Skip** — persisted on `DluxUpdateRun.backup_mode`; when a backup is requested it is created and verified before briefly enabling the maintenance page (progress persists across browser disconnects) and a backup failure stops the update, while Quick excludes uploaded media (an inline update never alters media on disk) and Skip proceeds with no backup
- **Roll back to previous version** switches code and static assets without reversing migrations or automatically restoring the database
- candidate and rollback web/Celery health/version probes retry for a bounded 120 seconds, allowing normal process-supervisor startup latency
- see [Verified Inline Updater](inline-updater.md) for deployment/bootstrap and recovery details

Operational note:

- dark themes are expected to skin both the language picker and theme-preview selectors on this page so inactive choices do not fall back to light/white treatment

That means the setup wizard is for initial onboarding, while the Options view is the ongoing operational hub.

## Detailed Configuration Instructions

### Client IP Resolution Modes

Admins can configure how DjangoLux identifies the client IP address in Step 3 (Access and Security). This is critical for accurate activity logging and security tracking.

- **Auto-detect**: Tries `X-Forwarded-For` (leftmost) → `X-Real-IP` → `CF-Connecting-IP` → `REMOTE_ADDR` and uses the first non-empty value.
- **Proxy-Aware (X-Forwarded-For)**: The default mode. It selects the client from the right of the proxy chain after ignoring the configured **Trusted Proxy Hops** (default 1, bounded to 0–8). Match that number to infrastructure you control.
- **Direct (`REMOTE_ADDR`)**: Correct when the web server faces the client directly without a proxy.
- **X-Real-IP**: Reads the standard single-value reverse-proxy header.
- **Cloudflare**: Reads `CF-Connecting-IP` explicitly.
- **Custom Header**: Reads a deployment-specific header. Names such as `CF-Connecting-IP` are normalized to Django's `HTTP_CF_CONNECTING_IP` form automatically.

All modes share a hardened fallback: if the configured source returns nothing, DjangoLux still tries `X-Forwarded-For` (leftmost) → `X-Real-IP` → `REMOTE_ADDR` before giving up, so a misconfigured header no longer yields an empty client IP.

### Two-Factor Authentication (2FA) & Trusted Devices

DjangoLux provides multiple layers of authentication security.

- **Email 2FA**: If enabled, the system will send a one-time password (OTP) to the user's registered email during login. Admins must ensure a working **Email Delivery Path** is configured.
- **Authenticator App (TOTP)**: Users can link an app like Google Authenticator for code-based 2FA.
- **Trusted Devices**: During 2FA verification, users can check "Trust this device for 30 days", and users may also trust the current browser from the Profile **Signed-in Devices** card after confirming their password.
    - Trusted sessions take precedence over untrusted sessions. An untrusted current session cannot sign out a trusted session from Profile.
    - Step 3 / Access & Security includes **Prevent multiple active sessions**. When enabled, a newly trusted session signs out every other active session for the same user.
    - Revoking a device trust forces the user to complete a 2FA challenge on their next login from that browser, and revoking a session immediately logs the user out from that device.
- **Login Lockout Tuning**: While **Enable login lockout** is on, Step 3 / Access & Security reveals three number fields — **Lockout after (attempts)** (1–50, default 5), **Counting window (minutes)** (how long failed attempts keep counting, default 15), and **Lockout duration (minutes)** (how long sign-in stays blocked once armed, default 15). Failed attempts are counted per IP *and* per username; a successful login clears the counters.
- **Strong Password Minimum Length**: While **Enforce strong passwords** is on, a **Minimum password length** field (8–64, default 12) is revealed. The strict validator and the live password checklist both honour it.
- **Live Password Checklist**: New-password fields no longer show static requirement bullets. A live checklist card appears under the field on focus and ticks each rule as it is met — the configured strong rules (minimum length + upper/lower case, digit, symbol) when enforcement is on, or Django's stock rules (at least 8 characters, not entirely numeric) when it is off.
- **Forgot Password (Self-Service Reset)**: Step 3 / Access & Security has an **Enable "Forgot password?"** toggle. When on *and* Dlux email delivery is configured, the sign-in page shows a **Forgot password?** link and the email-based reset flow becomes available at `/accounts/password-reset/`. A user submits their account email, receives a reset link (sent through Dlux's own email transport, so it honours your relay/encrypted-secret settings), opens it to choose a new password, and is returned to sign-in — every page rendered in your configured login style, direction (RTL/LTR), and language. The whole flow **self-hides** when email is not ready: if the toggle is on but no email is configured, neither the link nor the reset URLs appear (they 404), so it never presents a dead end. Default off.
- **Sign Out On Browser Close**: Step 3 / Access & Security has a **Sign out on browser close** toggle. When on, Dlux issues a browser-session cookie without a persistent expiry, so starting a new browser session requires signing in again. Browser tabs share that cookie: closing one tab does not sign the user out while the browser session remains open.
- **Sign Out After Inactivity**: The **Sign out after inactivity** toggle reveals an **Inactivity timeout (minutes)** field (1–1440, default 10). After that many minutes with no activity the user is signed out; roughly 30 seconds before, a countdown modal appears with a **Stay signed in** button (which resets the timer) and a **Sign out now** button. Enforcement is both client-side (the modal) and server-side (DluxMiddleware), so it still applies if scripts are disabled.
- **Privacy & Consent**: Step 3 / Access & Security has a **Privacy & Consent** block. Set **Privacy policy URL** (and optionally **Terms of service URL** + **Privacy notice text**) to render a small privacy line/link on the sign-in and sign-up pages, and enable **Require agreement to sign up** to add a mandatory consent checkbox to the public registration form. DjangoLux supplies no legal text — you provide the policy at those URLs. See [Data & Privacy](data-privacy.md) for exactly what personal data DjangoLux stores and the transparency-vs-consent guidance.
- **Default scope/groups for public registrations**: These are not System Settings fields. In **Manage Scopes**, right-click or long-press a scope row and choose **Use for public registrations** to mark the one default landing scope. In **Manage Groups**, right-click or long-press a preset row and choose **Use for public registrations** to mark one or more live Group presets. After email verification or superuser approval activates a public registration, Dlux applies the marked scope (only while scopes are enabled) and assigns the marked global or matching-scope presets as normal `auth.Group` memberships. The admin-created-user **Force password change** checkbox does not apply to public registrations.
- **Bulk Forced Password Change**: The Options **Admin panel** title row has a circular expandable admin-command button. Its **Force passwords** command is superuser-only and asks for the current password before setting `Profile.preferences["force_password_change"]` on every non-superuser account. The next login for those users is forced through the same profile password-change flow used by the create-user **Require password change on first login** checkbox; superusers are skipped.
- **Reset Data**: The same Admin-panel command launcher has a superuser-only **Reset data** command. It asks for the current password, then opens a modal listing the discovered models with their **row counts**. Tick the models to clear, optionally enable **delete related media files** (off by default — only affects permanently-deleted models), and confirm. Deletion respects Dlux semantics: **scoped models are soft-deleted** (the recoverable `deleted_at` mechanism, so their rows and media are kept and can be restored), while non-scoped models are **permanently removed** (honouring each relation's `on_delete` — a `PROTECT` reference blocks that model and is reported, without stopping the others). **System Settings, the updater state, permission groups, and superuser accounts are never touched** — you cannot brick the install or lock yourself out. Every run is audit-logged. This is destructive; take a system backup first.

## Themes, Languages, and Home URL

The most common admin-facing configuration tasks are:

- changing the default theme used before a user saves a personal preference
- changing the default language used before a user saves a personal preference
- changing the default table density used before a user saves a personal preference
- changing the default form density and default modal size (Layout)
- toggling sticky table headers, contained resizable table columns, and zebra striping (Layout); enabled resize handles appear as subtle header dividers and reallocate width without widening the page
- updating the list of available languages
- adding translation overrides without touching code
- adjusting the global home URL used by the titlebar Home button
- optionally routing anonymous public-root traffic to a different destination from the authenticated Home URL

The safest mental model is:

- use `DLUX_CONFIG` to seed defaults in code
- use System Settings to refine the live runtime configuration
- use user preferences for per-user display choices

## Tutorial and User-Facing Runtime Behavior

DjangoLux includes a built-in tutorial system that targets the current view path. Users may see different guided steps on `/sys/`, `/sys/users/`, `/sys/sections/`, and other supported pages.

Project-specific tutorial additions should extend this built-in system rather than replace it. The intended developer path is to load a project script through `templates/dlux/includes/custom_scripts.html` and register `window.get_custom_tutorial_steps(path)`. See the customization guide for the supported extension pattern.

Other admin-facing runtime behaviors to expect:

- user management uses the interactive two-step modal wizard
- permission labels are translated dynamically
- profile pages expose 2FA controls and backup-code workflows
- activity logs show diffs and download/export context
- user rows expose a sensitive User Report for authorized staff with activity-log access

2FA operational note:

- enable, disable, backup-code generation, TOTP setup, and OTP resend flows are now POST-backed actions rather than GET-triggered links
- email 2FA supports background auto-sending on login and enforces a 120s resend cooldown
- destructive profile security actions now ask for the current password before the backend mutation is allowed to proceed
- sessions can be marked as "Trusted" for 30 days during 2FA verification to skip subsequent challenges on the same browser
- when single active session enforcement is enabled, every successful login or completed 2FA login evicts the user's other active sessions, including cache/Redis-backed sessions once Dlux has recorded their presence; older browsers see the session-ended page on their next request
- when single active session enforcement is disabled, the profile password-change form offers an optional **Sign out of all other signed-in devices** toggle; a successful change retains the current browser, ends the user's other recorded sessions, and leaves trusted-device records unchanged

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

## User Reports

The User Report is available from `/sys/users/` for authorized staff who can view the user directory, manage the target user, and view activity logs. It opens in a Dlux dynamic modal, can be printed or saved as PDF through the browser print flow, and can be exported as XLSX.

The report combines account status, staff tier, public-registration provenance, activity counts, recent logs, known devices, trusted-device state, IP observations, browser/OS observations, and estimated active time. Its activity calculations use the same business-data boundary as General Reports: only user-category activity contributes, while Dlux system/audit operations remain operational history. Its activity tabs are live: selecting `week`, `month`, or `all` updates the total-action tile, activity breakdown, recent-activity timeline, and XLSX target together. A detail modal opened from the reports overview starts on the overview's selected window. Account, known-device, and durable presence facts remain lifetime context rather than being hidden by an activity window. Precise device and presence analytics start only after the durable history migration is installed; older projects still show whatever can be derived from existing activity logs and trusted-device rows.

Dlux uses a signed first-party `dlux_device_id` cookie to group non-trusted browser/device history across IP changes. The raw token is never exposed in the UI and is stored server-side only as a hash. This cookie is for reporting continuity only; Django sessions remain authoritative for active authentication, and `TrustedDevice` remains authoritative for 2FA trust decisions.

## System Reports and Backup ZIP

The reports overview at `/sys/reports/` (permission `dlux.view_reports`) aggregates report-eligible activity by user, model, action, and day. Period presets cover the current week, month, calendar quarter, half-year, year, and all time; **Custom Range** reveals inclusive start/end fields using the shared Dlux `vanillajs-datepicker` control (`yyyy-mm-dd`, theme-aware, with Arabic localization). The previous-period comparison uses the immediately preceding interval of equal duration. The overview performs grouped database aggregates rather than loading every activity row into Python, and migration `0013_useractivitylog_report_indexes` adds indexes for the timestamp, scope, actor, model, and action filters used by the page.

The Dlux report builder uses its own report discovery: it walks Django's registered models plus model identities found in end-user activity history; it does not reuse Sidebar/Nav Bar discovery. Developers can exclude a model at its source with `dlux_report = False`, or centrally with `DLUX_CONFIG['reports']['exclude_models'] = ['app_label.model_name']`. Exclusions win over include lists and remove the model from the builder and report ZIP; stable activity rows resolve through the same eligibility check. Use `exclude_activity` for an unresolved legacy activity label that no longer maps to an installed model.

```python
class InternalLedger(models.Model):
    dlux_report = False

DLUX_CONFIG = {
    "reports": {
        "exclude_models": ["billing.importjob"],
        "exclude_activity": ["Legacy import job"],
    },
}
```

Only `ActivityLog.category = "user"` contributes to the report catalog, totals, XLSX workbook, or embedded ZIP workbook. Dlux system/audit activity—system backup and restore, report jobs, notifications, sessions/devices, updater operations, security events, and similar framework bookkeeping—stays in its dedicated operational UI and Activity Log tabs instead of becoming reportable business data. Backup and restore audit rows use distinct `dlux.systembackup`/`dlux.systemrestore` identities; legacy display labels are also hard-excluded even if an old row was misclassified as user activity. Celery bookkeeping models are likewise infrastructure, so `django_celery_results`, `django_celery_beat`, legacy `djcelery`, and their historical Task Result/Periodic Task identities are always excluded. Checked items are included; **Include All** and **Exclude All** act on the currently searched list, and an explicit empty selection returns zero rather than silently reverting to all. Model and operation keys are validated against the actor's scoped catalog before querying. The same normalized period, keyword, model set, and operation set drive the page totals, the entries XLSX, the printable report, and the report ZIP. The Apply/Reset action row uses full logical width: it aligns right in LTR and mirrors to the left in RTL while preserving the mirrored action order.

The builder produces two outputs for the current selection, and they answer different questions:

- **Export Entries (XLSX)** (`/sys/reports/export.xlsx`) is a **data** export. It writes one worksheet per selected model containing that model's **actual rows** — its own columns, its own values — filtered by the chosen period and the viewer's scope, with a leading **Export Info** sheet recording the period, the row limit, and a per-model index of sheet name and exported row count. Foreign keys render as their display label, choice fields as their display value, and file fields as their stored path. Fields whose names look credential-bearing (`password`, `passphrase`, `secret`, `token`, `api_key`, `private_key`, `session_key`, `salt`, recovery/backup codes) are never written; remove additional columns per model with `DLUX_CONFIG['reports']['entries_exclude_fields'] = {'app.model': ['field_name']}`. Each sheet is capped at `DLUX_CONFIG['reports']['entries_row_limit']` (default `20000`) and the Export Info sheet flags any model that was truncated. Selecting `dlux.activitylog` exports the activity rows matching the operation selection, so the sheet agrees with the on-screen figures.
- **Print Report** (`/sys/reports/print/`) is the **analytical** output. It opens a print-ready document for the same selection: a hero total with its delta against the previous period, a KPI row, an activity-over-time area chart, top-models and top-contributors bar charts, an operation-mix stacked bar with a value/percentage legend, and a full table beneath every chart so no value is reachable only by hovering a chart. The A4 print stylesheet deliberately overrides the narrow-screen rules: the overview and chronological trend occupy page one, while distributions and detail tables begin on page two. Chart canvases are remeasured after print media activates so they fill their cards instead of retaining browser-width geometry. Use the browser's print dialog to print or save as PDF. Charts use the bundled Chart.js — no external CDN — and a colour-blind-validated palette.

Celery is reserved for building large downloadable backup files; it is not used for the interactive overview request. Redis is useful as Django's shared cache: set `DLUX_CONFIG['reports']['overview_cache_seconds']` to a small positive TTL (for example `30`) to cache only the aggregate/dropdown portion of the overview per viewer, scope, language, window, and filter set. The default is `0`, which disables this cache and keeps every page load fully current.

This feature is built for the **application supervisor**: monitoring what users input over time and keeping periodic, incremental, window-scoped data exports. It is intentionally scoped/windowed and is **not** a disaster-recovery tool — for full restorable snapshots use the Full System Backup & Restore feature below.

Staff with `dlux.download_backup` can also generate a report ZIP. This is the third builder output and the only one that carries attachments — it is the same **Export Entries** workbook plus the media those records reference, and nothing else:

```
entries.xlsx                                          the same workbook the Export Entries button downloads
files/<app>/<model>/<record-folder>/<field>/<file>     every FileField/ImageField blob those rows reference
manifest.json                                          normalized period/model/operation selection + model, file, and missing-file lists
```

There is deliberately **no serialized JSON** in this archive. It is a periodic deliverable meant to be opened and read by a person, not restored — for restorable snapshots use Full System Backup & Restore below, whose `.dlb` keeps its `data/*.json` payload. In short: **Export Entries** gives you the data alone as a spreadsheet; the **report ZIP** gives you that identical spreadsheet plus the attached files, structured. Operations filter the activity rows in the workbook; model checkboxes control which models contribute both sheets and media. Each included model is filtered on its timestamp column (auto-detected `created_at`/`created`/`created_on`/`date_created`/`timestamp`, overridable per model via `DLUX_CONFIG['reports']['backup_window_fields'] = {'app.model': 'field_name'}`; models with no timestamp column are included in full).

Report-ZIP file folders are human-readable and do not expose database PKs. They use a conventional business identifier when the model has `number`, `document_number`, `reference_number`, `registration_number`, `serial_number`, `code`, `name`, or `title` (for example `files/documents/incoming/number-2000/pdf_file/document.pdf`). Override the identifier without an interactive background-task prompt using `DLUX_CONFIG['reports']['backup_label_fields'] = {'app.model': 'case_reference'}`. Values are Unicode-normalized and path separators/control characters are removed; duplicate business labels receive stable traversal-order suffixes (`number-2000--2`) so files cannot overwrite each other. If no configured/conventional field exists, Dlux uses the model's string label, then an ordinal `record` fallback. The full-system `.dlb` deliberately retains its original PK folder layout because it is a machine-restoration artifact. Both formats remain manifest-driven and restore never infers record identity from folder names.

Backup generation flow:

- The control is labelled **Create Backup ZIP** because it starts a build rather than downloading anything directly: it switches to "Building..." while the job runs, a progress bar tracks position with one status line beneath it naming the current stage, and the finished file downloads automatically. A separate **Download last backup** pill below it — showing the artifact's size and age — re-downloads the most recent completed archive without building a new one.
- Clicking the backup button POSTs to `/sys/reports/backup/start/`. When Celery is importable, the broker is reachable, and a live worker answers a ping, the build is queued as a `dlux.tasks.build_report_backup` task and tracked in the `ReportBackup` model; combined migration `0014_systembackup_liveness` also persists the normalized builder criteria for that worker. The page polls the explicitly no-store `/sys/reports/backup/<token>/status/` feed, renders its persisted percentage/stage progress, and triggers the download from `/sys/reports/backup/<token>/download/` when the row reaches `completed`. This avoids reverse-proxy timeouts (e.g. nginx 504) on large datasets. Repeated clicks reuse the user's existing pending/running job instead of building duplicate archives, active polling resumes after a page reload, and the reports page retains a link to the user's latest completed artifact. Abandoned active rows expire after 24 hours. Worker logs emit an explicit start and completion line containing size/model/file metrics, while failures persist a bounded error on the row.
- Without a usable Celery worker, the client is redirected to the synchronous `/sys/reports/backup.zip?window=<window>` endpoint, which streams the zip from a temp file (constant memory) but remains subject to proxy timeouts on very large `all` backups.
- Status/result hand-off needs only a shared database plus shared default storage between web and worker. Generated zips are stored under `MEDIA_ROOT/dlux_backups/` (prefix configurable via `DLUX_CONFIG['reports']['backup_storage_prefix']`); the last 3 completed backups per user are retained, older ones are pruned automatically. Set `DLUX_CONFIG['reports']['backup_use_celery'] = False` to force the synchronous path.

`client_max_body_size` limits request bodies (uploads), not the size of a backup response. Completed artifacts are streamed by Django through a permission-checked GET, so a large ZIP is not rejected by nginx's upload ceiling. Web, Celery, and nginx still need the same persistent media mount, and the proxy must allow a normal continuously streamed response.

**Deployment requirement:** the backup prefix lives under media so containers can share it, but it must never be served directly. Block it at the reverse proxy. Generated projects ship both proxy configs in `.proxy/` and already include this guard before the general `/media/` handler — **Caddy** (the active default):

```caddyfile
respond /media/dlux_backups/* 404
```

…and the **nginx** fallback:

```nginx
location ^~ /media/dlux_backups/ {
    return 404;
}
```

Existing deployments must add the guard to whichever proxy config they run and reload/recreate that proxy; installing a newer wheel cannot rewrite a project-owned reverse-proxy file.

**Reverse proxy (`.proxy/`): Caddy by default, nginx fallback.** Generated projects ship two interchangeable proxy configs in `.proxy/` plus a shared `maintenance.html`. **Caddy** (`.proxy/Caddyfile`, the active `caddy` service) serves plain HTTP on `:80` with `auto_https off` — front it with your own TLS terminator, or set `CADDY_SITE_ADDRESS` to a hostname to let Caddy terminate TLS itself. Its published host port reads `CADDY_PORT`, then legacy `NGINX_PORT`, then `80`, and the upload ceiling is `CADDY_MAX_SIZE` (default `10MB`). The **nginx** fallback (`.proxy/default.conf.template`, a commented-out `nginx` service you can swap in) is mounted into the official nginx image's template directory (`/etc/nginx/templates/`); at container start nginx runs `envsubst` and writes `/etc/nginx/conf.d/default.conf`, parameterized by `NGINX_SERVER_NAME` (default `localhost`) and `NGINX_MAX_SIZE` (`client_max_body_size`, default `10M`), with `NGINX_ENVSUBST_FILTER: "NGINX_"` preserving nginx's own runtime variables (`$host`, `$remote_addr`, …). Both configs are **not** gated on `web`'s health and re-resolve the recreated `web` container (Caddy natively; nginx via a `resolver` directive), and both serve the composer update progress endpoints (`/_update/status.json`, `/_update/log.txt`), an always-200 `/_edge-alive` probe, and a hybrid `/health` that returns proxy-local `200` during maintenance — point a front proxy's health check at `/_edge-alive` or `/health`, never `/`. Static files receive the one-year immutable header only after Caddy confirms the requested file exists, so an early 404 is never cached as an immutable asset; `{% dlux_static %}` also adds a source-mtime revision in `DEBUG` for mounted development files. To raise the upload limit, change `CADDY_MAX_SIZE` (or `NGINX_MAX_SIZE`) and recreate the proxy — no file edit required.

Database branding paths are validated against their configured storage before Dlux emits them. If an uploaded logo or favicon has been removed from storage, the UI falls back to the packaged Dlux branding instead of repeatedly requesting a broken media URL; re-upload the intended file from the Identity/Branding settings to restore it.

Downloads always go through the permission-checked Django view, which also enforces that only the requesting user can fetch their own backup. Dlux-owned transactional SMTP mail (OTP codes, registration, backup-related notifications) now applies a connection timeout (default 10s, override with `email_config['timeout']`) so an unreachable mail host fails fast instead of hanging the request.

## Full System Backup & Restore (.dlb)

`/sys/backup/` (superuser only) creates encrypted, restorable snapshots — distinct from the supervisor reports backup above. A **Full** backup covers **everything for all time**: every concrete managed model (users, regular-user password hashes, groups, scopes, profiles, system settings, activity history, host-app data) plus every referenced storage file, packaged as a single `.dlb` file. The create form also offers a **Quick — data only** scope that captures the database and migration state but omits uploaded media blobs (much faster on media-heavy sites); the choice is recorded per backup (`SystemBackup.media_included`) and shown as a "Data only" badge in the history. Restoring a data-only `.dlb` replaces the database and leaves existing media on disk untouched (restore only rewrites files the manifest lists). Superuser account rows are included, but superuser password hashes are omitted from the backup payload.

**File format and encryption.** An `.dlb` file is a `DLB1`-tagged container: a cleartext JSON metadata header (format version, creation date, row/file counts, KDF salt, KDF mode — nothing sensitive) followed by the backup zip encrypted with Fernet (`cryptography`) in framed 32MB chunks, so any size encrypts and decrypts at constant memory. By default the key derives from Django `SECRET_KEY` plus the per-file salt. When the superuser enters an optional backup passphrase, the key derives from that passphrase instead; restoring that file requires the same passphrase and does not depend on a separate backup-specific environment variable.

**Creating and managing backups.** The page uses the same Dlux form-density fields, themed glass surfaces, and `dlux-table-shell` tables as the rest of the system UI. It builds backups in the background through Celery (`dlux.tasks.build_system_backup`) with polling, or inline when no worker is available. Pending/running rows initially have zero byte/row/file counts because the artifact does not exist yet; their model-by-model progress percentage and current stage are persisted and rendered in the history table. While the page remains open, a superuser-only no-cache feed discovers manual, scheduled, and updater-triggered runs and replaces those provisional values with the completed metrics plus download/restore controls without a manual reload. An in-progress `.dlb` may already be growing in storage, but it is deliberately excluded from the external-file list until its `SystemBackup` row completes. The optional passphrase is passed only to the active inline run or Celery task; it is not stored on the `SystemBackup` row. Completed backups can be downloaded, deleted, or restored. `.dlb` files can also be uploaded (small files) or copied directly into the protected backup folder (`dlux_backups/` in Django default storage by default — keep the reverse-proxy guard from the reports-backup section); the page lists such external files and can restore from them, which is the path for disaster recovery onto a rebuilt server. Backup history identifies whether each run was manual, scheduled, or created as an inline-update prerequisite.

Both backup types integrate with the Dlux notification drawer. Starting a worker creates one live progress item addressed to the requesting user (or active superusers for scheduled/system-owned runs). That item is non-dismissible while active and refreshes every three seconds while visible in the drawer; completion or failure unlocks it and creates a separate unread terminal notification linking back to the appropriate backup page. This lifecycle respects the global notifications enable switch and never sends backup notifications by email.

**When a backup is interrupted.** A backup that stops midway is the one failure the page has to make obvious, because the process that was building it is usually gone and cannot report anything itself. Every progress tick — including sub-steps inside a single large model and each encryption chunk — stamps a heartbeat on the row, so the history shows the live record/file counters, the current stage, and how many seconds ago the run last said anything. Once a run goes quiet past a third of the stall timeout, its row turns amber ("No progress") and states that it will be failed if it stays silent; the create-form status line does the same. Once it passes `stall_timeout_minutes` (default 30) with no signal, it is marked **failed** with an explicit reason naming the percentage it died at — no more rows stuck at "running" forever with no error and no file. This reaping is trigger-agnostic (manual, scheduled, and updater runs alike) and happens whenever the page or its poller is open, on each scheduled-backup check, and when a Celery worker starts — so a worker restart clears exactly the backups that worker abandoned.

**Retrying.** With `auto_retry_enabled` on (the default), a failed or stalled backup is re-run automatically up to `max_attempts` times (3), `retry_delay_minutes` apart (5); the row shows `Try 2/3` and the next attempt time while it waits. A retry rebuilds the snapshot from the beginning on the same history entry — a half-written `.dlb` is a single encrypted stream and has no resumable state in it. **Passphrase-protected backups are not retried automatically**: the passphrase is deliberately never stored, so re-running one unattended would quietly produce a secret-key-encrypted file instead of the protected one that was asked for. Those rows show a **Retry** button that asks for the passphrase again; the same button is available on any failed backup for an immediate manual attempt.

**Scheduled backups and rotation.** Step 13 of first-launch setup and the **Backups** System Settings tile write `SystemSettings.backup_config`. `scheduled_enabled` is off by default. When enabled, generated deployments' Celery worker/beat process checks `dlux.tasks.run_scheduled_system_backup` every 15 minutes and creates a backup once `schedule_interval_hours` has elapsed since the last scheduled run. `auto_export_target` is a validated relative folder inside Django `default_storage`, so it works with either the shared media volume or a configured remote storage backend. `retention_days` and `max_backups_to_keep` are both `0` by default (unlimited); nonzero values prune completed backup files and rows after each successful backup. The just-created backup is protected from that rotation pass. The same Step 13 form carries the **Interrupted Backup Recovery** controls: `stall_timeout_minutes`, `auto_retry_enabled`, `max_attempts`, and `retry_delay_minutes`.

**Restore semantics.** Restore is a **full replace**: it wipes and reloads every backed-up model in a single transaction (FK checks deferred, models loaded in dependency order, Dlux signals suspended), resets primary-key sequences, restores files to their original storage names, then clears all caches and sessions. The backup manifest records the exact applied-migration state; restore refuses to run against a different migration state unless "ignore version mismatch" is explicitly checked. Starting a restore requires the superuser's current password plus an explicit replace confirmation, and passphrase-protected files also require the backup passphrase. Regular users sign in with the restored credentials. For superusers, Dlux preserves the current target password hash when the restored superuser username matches an existing target superuser; restored superusers without a target username match receive an unusable password and must be reset out-of-band.

The normalized group also preserves code-owned `DLUX_CONFIG['backup']` compatibility for `use_celery` (default `True`) and `exclude_models` (extra `app_label.model` strings to omit from snapshots). Once the DB-backed System Settings singleton is configured, its `backup_config` is the runtime policy, consistent with other System Settings groups.

**Inspecting a backup offline.** A standalone, read-only viewer for `.dlb` files ships in the repo at [`tools/dlb-viewer/`](../tools/dlb-viewer/README.md). It is a single, dependency-free cross-platform binary (Go) that decrypts a backup locally and opens a small browser UI to browse the manifest, every model's serialized rows, the recorded migration state, and any stored files — without a running Dlux instance. On entry it prompts for the backup passphrase, or the originating project's Django `SECRET_KEY` when the file was not passphrase-protected (the cleartext header records which is needed). Prebuilt binaries are attached to each GitHub release; it can also be built with `make` from that directory. Use it to confirm a `.dlb`'s contents before restoring, or to recover specific records/files from a snapshot. Relation columns (foreign keys, one-to-one, many-to-many) carry a `↗` marker and a **"Resolve relations"** toggle that swaps them between the raw stored reference (PK or natural key) and a readable name looked up from the related model — driven by a `schema` block the backup records in `manifest.json`. Backups created before this shipped have no schema, so the toggle is hidden and references display as stored (the viewer stays compatible with older `.dlb` files). The viewer also surfaces the **backup scope** (Full vs Data only, from `media_included`) on both the unlock screen and the overview, and file-field cells in the data tables link directly to the stored file by its readable name: clicking the name opens viewable files (PDF, images, plain text) **inline in a new tab** via the browser's native rendering, with a `↓` to download; unknown or active-content types (HTML/SVG/XML) are forced to download instead. In a data-only (Quick) backup the blobs aren't present, so those cells remain plain text and the Stored-files view explains the media was intentionally excluded.

> macOS note: the downloaded binary is not Apple-notarized, so Gatekeeper blocks it on first run ("cannot verify it is free of malware"). Clear the quarantine flag with `xattr -d com.apple.quarantine ./dlb-viewer-darwin-arm64` (or use Finder → right-click → Open → Open), then run it normally.

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

DjangoLux distinguishes three staff authorization tiers for user management:

| Tier | Scope | Requirements | User Management Powers |
|------|-------|--------------|------------------------|
| **Superuser** | None | `is_superuser=True` | Full god mode — create, edit, delete any user including other superusers |
| **Global Staff** | None (NULL) | `is_staff=True` + `dlux.manage_scopes` permission | Create/manage scopes, assign users to any scope, view and edit ALL users (scoped and scopeless) |
| **Central Staff** | None (NULL) | `is_staff=True` (NO `manage_scopes`) | Create/manage scopeless (NULL scope) users ONLY — completely blind to scoped users and their data |
| **Scoped Staff** | Assigned scope | `is_staff=True` + scope assignment | Create/manage users within their assigned scope only |

The Add User form also includes **Require password change on first login**. It is off by default; when selected, Dlux stores `force_password_change` in the new user's profile preferences and middleware redirects that account to the profile password-change form until the password is changed. If Initial User Setup is also enabled for the account, Dlux defers that onboarding modal until after the password requirement is cleared. Profile password changes and staff reset-password submissions are rejected when the new password is identical to the account's current password.

### Creating Global Staff

Only **superusers** can create Global Staff users. To create a Global Staff member:

1. Sign in as superuser
2. Go to `/sys/users/` → Add User
3. Check **Staff Status**
4. In Permissions, select **"Can manage scopes and all users"** (`dlux.manage_scopes`)
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
4. In Permissions, select `dlux.manage_staff` (but NOT `dlux.manage_scopes`)
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
- Scoped users have privacy from Central Staff
- Central Staff can handle routine user management for the core system without accessing private scoped data
- Global Staff can administer the entire multi-tenant system without needing full superuser privileges

### Permission Assignment Principle

**Users can only assign permissions they themselves have.** This is enforced at the form level:

- Non-superusers see ONLY the permissions they have been granted (directly or through groups)
- `manage_staff` permission can only be assigned by users who have it
- `manage_scopes` permission can only be assigned by superusers (who can create Global Staff)
- `view_activitylog` permission can only be assigned by users who have it

The grouped permission cards show localized descriptions for Dlux-owned permissions such as reports, report backups, sections, activity logs, and staff access so administrators can see what each grant unlocks before assigning it.

This prevents privilege escalation where a user could grant themselves or others permissions they don't possess.

#### Delete permissions

`delete_<model>` permissions are assignable from the grouped permission cards (under each model alongside view/add/change). By default no one holds them except superusers, so deletion is opt-in: grant `delete_<model>` to the specific users who should be able to remove records. The grant is the single control point for both surfaces — it reveals the **Delete** entry in a table row's right-click/long-press context menu *and* authorizes the backend delete view (which independently enforces `delete_<model>` and returns 403 without it). A user who can only view/edit never sees the Delete entry. Sensitive deletes remain non-assignable through this UI: the `auth` user/group/permission models and most internal `dlux` models (e.g. activity logs, scopes, system settings); section structure is governed by `manage_sections`, which does **not** grant delete on unrelated data grids.

## Permission Groups / Presets

Assigning permissions one checkbox at a time gets tedious as a project grows. **Permission groups** (presets) let staff define a named bundle of permissions once and reuse it. A preset is a standard Django `auth.Group`; membership is *live*, so editing a preset's permissions instantly changes what every member can do. Because Django already unions a user's group permissions with their direct permissions, presets are purely additive — users in no preset behave exactly as before, and no existing `has_perm` check changes.

### Who can manage presets

Preset creation, editing, and membership are gated by the **`dlux.manage_groups`** permission (assignable from the grouped permission cards, like `manage_staff`/`manage_scopes`), or by being a superuser. Grant it to the staff who curate access bundles.

### Creating and editing a preset

1. Go to `/sys/users/` → **Manage Groups**.
2. **Add Group** → give it a name, an optional description, an optional **Scope**, and check the permissions it should bundle. You can only include permissions you are allowed to grant yourself.
3. Save. The preset appears in the list with its member and permission counts. Row actions (Edit, Members, public-registration default toggle) live in the shared Dlux right-click/long-press context menu.

Editing a preset's permissions later applies to **all current members** immediately (live inheritance).

### Assigning users to presets

Two ways, both requiring `manage_groups`:

- **During user create/edit** — the Add User wizard (permissions step) and the Edit Permissions modal show a **Groups / Presets** selector above the per-permission checkboxes. Selected presets are applied on save; direct permissions still layer on top.
- **From the preset's Members modal** — open **Manage Groups → (preset) → Members** to add or remove users in bulk. The modal also shows a **membership history** table recording which user was assigned, by whom, and when (`GroupMembership`).
- **As a public-registration default** — in **Manage Groups**, mark safe baseline presets through the row context menu. Public registrations receive those presets only after activation; Dlux stores membership as live `user.groups`, not copied permissions.

### Scope behaviour

A preset can be **global** (no scope) or bound to a single `Scope`:

- For *assignment*, scoped staff see global presets plus presets in their own scope.
- For *management* (edit/delete/membership), global presets are restricted to superusers and Global Staff; scoped staff manage only presets in their own scope. Membership edits never touch members outside the actor's manageable set, so a scoped manager cannot remove a user from a preset they don't control.

Scope management itself uses the same context-menu pattern. In **Manage Scopes**, scope rows expose Edit, Details, disabled Delete, and public-registration default actions. The details view shows the scope description, assigned users, related data counts, and recent activity. `Scope.description` is optional and safe to blank.

### Data model

- `Scope` — named isolation boundary with optional `description` and `is_public_registration_default` marker.
- `GroupProfile` — sidecar on `auth.Group`: `description`, `scope` (nullable = global), `is_active`, `is_public_registration_default`, and audit fields.
- `GroupMembership` — durable who/which/when record (`user`, `group`, `assigned_by`, `assigned_at`), kept in sync with native `user.groups` whenever membership changes.

The group tables and the `dlux.manage_groups` permission were added by migration `0007`; public-registration default markers and `Scope.description` are added by inline-safe migration `0009`.
