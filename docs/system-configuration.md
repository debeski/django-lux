# System Configuration

Use this guide when configuring DjangoLux through `/sys/setup/` or `/sys/options/`. It is for operators; projects that need code-owned defaults should start with [Project Configuration](project-configuration.md).

## Configuration layers

### Starting with manual setup

On DjangoLux 1.9.4+, set `DLUX_SKIP_CONFIG_IMPORT=True` in the web and migrator
service environments to bypass automatic `config.json` import. Composer 1.5.3+
injects this with `./start.sh --skip-config` (also supported with `-d` or
`update`). Both migration bootstrap and setup-page requests honor the option;
the file is neither read nor changed, and the setup wizard remains available.
Explicit settings imports still work. Existing configuration/data is not reset.
Repeat the flag on subsequent deployments until setup is complete, or declare
the environment variable in Compose for a persistent policy. Restarting the
same containers retains the flag; recreating them without it restores normal
auto-import for an unconfigured database.

### Resolution order

DjangoLux resolves configuration in this order:

1. package defaults;
2. project defaults in `settings.DLUX_CONFIG`;
3. live overrides in the `SystemSettings` singleton; and
4. per-user preferences in `Profile.preferences`.

The first three determine system policy. Personal theme, language, sidebar state, density, and assisted-entry choices remain user-specific and do not rewrite system defaults.

## First-launch setup

`/sys/setup/` is the initial configuration workflow. It first asks for the setup language; that choice affects only the wizard UI. The persisted default language is selected later in **Localization**.

The current wizard has eighteen steps:

1. **Branding** — localized names, logo, favicon, footer, and configuration import.
2. **Languages** — language catalog, default language, user overrides, and translation overrides.
3. **Email** — delivery path, provider preset, secrets, test send, and failure alerts.
4. **Access and Security** — authentication, sessions, registration, consent, and client-IP policy.
5. **Themes and Fonts** — theme and font defaults, allowlists, overrides, and edge styles.
6. **Titlebar** — home/logo, actions, language switcher, geometry, and surface.
7. **Sidebar** — navigation tree, visibility, toolbar, and personal reordering policy.
8. **Navbar** — hierarchy/history mode, navigation root, and user override policy.
9. **Ribbon** — list-page ribbon behavior and tab configuration.
10. **Components** — tables, forms, modals, Options layout, audit fields, and soft-delete review.
11. **Home and Public Pages** — authenticated homepage, per-user override, and anonymous public homepage.
12. **Login Page** — layout, logo treatment, color, and localized hero message.
13. **Profile Page** — user modules, onboarding, devices, and activity feed.
14. **Global Search** — titlebar search display and optional record search.
15. **Notifications** — flash, drawer, badge, bridge, email, and CRUD behavior.
16. **Logging** — activity and audit policy plus retention.
17. **System Backup** — schedule, storage, retention, and retry policy.
18. **Extra Features** — opt-in integrations such as ScanLink.

System Settings modal editors opened from Options use these same categories but show only the selected category. Setup export/import is intended for reusable development and staging configuration: it exports settings JSON, not uploaded logo/favicon binaries or host-specific email verification state.

### Unsaved previews

A live preview is an unsaved form value visibly changing a page surface that is already rendered. These mutations are centralized in `setup/js/previews.js` and safely do nothing when the wizard or Options page does not contain the target. Builder previews remain inside their builders and do not represent saved runtime chrome.

Every setup step and focused Options editor includes a **Preview** action. It is disabled, with an explanatory tooltip, for steps whose values have no useful visual representation. Visual steps use one of two modes:

- **Glass** hides the Options modal contents while retaining its outline, exposing real page chrome behind it. Click anywhere, press Escape, or press Q to return; the exit click is consumed so it cannot activate the page below.
- **Popup** renders a contained shell from the current unsaved form state. Closing it returns focus and preserves the form, so settings can be adjusted and previewed repeatedly. This is used by the setup wizard and by off-page targets such as the public home and login pages.

Neither mode saves `SystemSettings`; only the existing Save action persists changes.

| Step | Unsaved preview behavior |
| --- | --- |
| Branding | Logo, favicon, system title, and an already-rendered footer update in place. Managed-library selections and new uploads use the same preview path. |
| Languages | Visible titlebar language-switcher chrome can update; changing the runtime language remains save-only. |
| Email | No page preview. Presets, dependency controls, Apply, and test-send are operational actions. |
| Access and Security | No page preview. Authentication, registration, session, consent, and client-IP values take effect after save. |
| Themes and Fonts | Theme and table/card edge choices can update visible chrome. Personal font preferences are not overwritten by a system-default preview. |
| Titlebar | Visible titlebar layout, actions, title, logo, home link, and surface update in place. |
| Sidebar | Visible Options-page sidebar state, density, toolbar, icons, and controls update in place; the setup wizard has no sidebar target and safely does nothing. |
| Navbar | A rendered runtime Navbar updates in place. When that surface is absent, Preview uses the contained shell. The builder continues to own its internal configuration sample. |
| Ribbon | A real ribbon surface can preview its layout, skin, and heading visibility; otherwise Preview uses the contained shell. The ribbon builder keeps its separate internal tab sample. |
| Components | Visible table density, edges, accent edges, sticky headers, resizing, zebra stripes, and card edges update in place. Personal form-density and modal-size preferences are preserved. |
| Home and Public Pages | The visible titlebar Home link can update, and Preview renders the unsaved public title and description in a contained shell. |
| Login Page | Preview renders the unsaved login presentation in a contained shell. |
| Profile Page | Builder synchronization only; no live page mutation. |
| Global Search | Dependency controls only; no live page mutation. |
| Notifications | Dependency controls only; persistent notification settings do not hide or rewrite the active page's notification UI. |
| Logging | Builder synchronization only; no live page mutation. |
| System Backup | No page preview. |
| Extra Features | No page preview for features that require a reload or another application surface. |

`SystemSettings.homepage_config` and `SystemSettings.search_config` are the canonical homepage and global-search stores. Older flat and titlebar/public page keys remain compatibility mirrors through v1.x; new project code should use the canonical configurations.

## Email delivery

The Email step is grouped as **Delivery Path** (delivery path, secret storage, provider preset), **SMTP Connection** (STARTTLS/SSL, host, port, timeout, credentials), and **Sender & Alerts** (default from address, failure recipients). Each choice is a Dlux selector rather than a dropdown, so every option and its consequence is visible before it is picked. When the internal SMTP relay is not listening, the relay option is locked with the reason attached — unless it is already the stored delivery path, which is never taken away.

Save the Email step before using **Send test email**. The test intentionally uses the stored configuration, which is the only way to validate the separate SMTP relay when that delivery path is selected. A successful send verifies the exact connection fingerprint; changing transport, secret storage, host, port, TLS/SSL, credentials, or sender requires another test.

Email 2FA, password reset, public registration, and notification-email controls are locked until delivery is enabled and verified. They retain their saved values while locked. Direct environment-managed SMTP and local debug backends remain supported; see [Deployment Configuration](deployment-configuration.md) for the runtime settings.

## Access and security

The step reads toggles first, then selectors, then the fields each one reveals: the sign-in and session switches, record visibility, client-IP resolution, public registration, and privacy links. Client IP source and registration activation mode are Dlux selectors; the trusted-hops and custom-header fields still appear only for the mode that uses them.

Configure client-IP resolution to match the proxy chain you control:

- **Proxy-aware X-Forwarded-For** is the default; set trusted proxy hops to the number of trusted hops at the right of the chain.
- **Direct** uses `REMOTE_ADDR` for a directly exposed web service.
- **X-Real-IP**, **Cloudflare**, and **Custom header** select an explicit source.
- **Auto-detect** is a compatibility fallback, not a substitute for correctly configuring a reverse proxy.

All modes retain a guarded fallback rather than returning an empty address. See [Getting Started](getting-started.md#behind-a-front-proxy--tls-terminator) for the required front-proxy headers.

The same category controls login lockout, strong-password policy, browser-close and inactivity sign-out, public registration, email/TOTP 2FA, trusted devices, and privacy-consent presentation. Security mutations are POST-backed and current-password checks protect destructive profile and administrator actions.

## Navigation and appearance

The sidebar and Navbar are runtime navigation, not setup-only previews. Saved sidebar visibility is permission-aware; a page does not become available merely because it appears in the tree. User reordering, if allowed, is a personal layer on top of the saved system tree.

The Navbar can use a curated hierarchy or a browser-session history. Its Navigation Root can remain neutral, follow the configured homepage, or use a discovered route without rewriting the stored hierarchy. Dynamic views can supply `dlux_navbar_crumbs` when their object-level labels cannot be represented by the static tree.

Imported navigation is validated against the live URLconf. Sidebar entries and Navbar route nodes naming a route this project does not define are dropped on import — from a first-launch `config.json`, an Options-page settings import, or `dlux_settings import` — so the builders only ever show entries that can actually render. A stale Navbar node's children are kept and lifted into its place, and a stale Navigation Root falls back to neutral. Manual Navbar nodes and sidebar entries carrying a literal `url` are never route-checked.

Themes and fonts use shared registries, so their setup choices, validation, previews, and runtime stylesheet selection remain aligned. Project-owned entries are documented in [Project Configuration](project-configuration.md#themes-and-fonts).

## Day-to-day Options

`/sys/options/` is the operational hub after setup. It provides personal display preferences to ordinary users and superuser-only System Settings, setup export, backup, Extra Features, and update actions. The System Information card presents deployment facts and on-demand service diagnostics; the Celery check is manual and stores its last result rather than probing on every page load.

For operational procedures, use [Operations](operations.md). For assets, use [Managed Assets](managed-assets.md). For deploy/update safety, use [Verified Inline Updates](inline-updater.md) and [Deployment Doctor](doctor.md).
