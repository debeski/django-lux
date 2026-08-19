# System Configuration

Use this guide when configuring DjangoLux through `/sys/setup/` or `/sys/options/`. It is for operators; projects that need code-owned defaults should start with [Project Configuration](project-configuration.md).

## Configuration layers

DjangoLux resolves configuration in this order:

1. package defaults;
2. project defaults in `settings.DLUX_CONFIG`;
3. live overrides in the `SystemSettings` singleton; and
4. per-user preferences in `Profile.preferences`.

The first three determine system policy. Personal theme, language, sidebar state, density, and assisted-entry choices remain user-specific and do not rewrite system defaults.

## First-launch setup

`/sys/setup/` is the initial configuration workflow. It first asks for the setup language; that choice affects only the wizard UI. The persisted default language is selected later in **Localization**.

The current wizard has seventeen steps:

1. **Identity** — localized names, logo, favicon, footer, and configuration import.
2. **Localization** — language catalog, default language, user overrides, and translation overrides.
3. **Homepage** — authenticated homepage, per-user override, and anonymous public homepage.
4. **Email** — delivery path, provider preset, secrets, test send, and failure alerts.
5. **Access and security** — authentication, sessions, registration, consent, and client-IP policy.
6. **Login page** — layout, logo treatment, color, and localized hero message.
7. **Sidebar** — navigation tree, visibility, toolbar, and personal reordering policy.
8. **Nav Bar** — hierarchy/history mode, navigation root, and user override policy.
9. **Titlebar** — home/logo, actions, language switcher, geometry, and surface.
10. **Global Search** — titlebar search display and optional record search.
11. **Notifications** — flash, drawer, badge, bridge, email, and CRUD behavior.
12. **Themes and typography** — theme and font defaults, allowlists, and overrides.
13. **Layout** — tables, forms, modals, Options layout, audit fields, and soft-delete review.
14. **Logging** — activity and audit policy plus retention.
15. **Profile page** — user modules, onboarding, devices, and activity feed.
16. **Backups** — schedule, storage, retention, and retry policy.
17. **Extra Features** — opt-in integrations such as ScanLink.

System Settings modal editors opened from Options use these same categories but show only the selected category. Setup export/import is intended for reusable development and staging configuration: it exports settings JSON, not uploaded logo/favicon binaries or host-specific email verification state.

`SystemSettings.homepage_config` and `SystemSettings.search_config` are the canonical homepage and global-search stores. Older flat and titlebar/public-root keys remain compatibility mirrors through v1.x; new project code should use the canonical configurations.

## Email delivery

Save the Email step before using **Send test email**. The test intentionally uses the stored configuration, which is the only way to validate the separate SMTP relay when that delivery path is selected. A successful send verifies the exact connection fingerprint; changing transport, secret storage, host, port, TLS/SSL, credentials, or sender requires another test.

Email 2FA, password reset, public registration, and notification-email controls are locked until delivery is enabled and verified. They retain their saved values while locked. Direct environment-managed SMTP and local debug backends remain supported; see [Deployment Configuration](deployment-configuration.md) for the runtime settings.

## Access and security

Configure client-IP resolution to match the proxy chain you control:

- **Proxy-aware X-Forwarded-For** is the default; set trusted proxy hops to the number of trusted hops at the right of the chain.
- **Direct** uses `REMOTE_ADDR` for a directly exposed web service.
- **X-Real-IP**, **Cloudflare**, and **Custom header** select an explicit source.
- **Auto-detect** is a compatibility fallback, not a substitute for correctly configuring a reverse proxy.

All modes retain a guarded fallback rather than returning an empty address. See [Getting Started](getting-started.md#behind-a-front-proxy--tls-terminator) for the required front-proxy headers.

The same category controls login lockout, strong-password policy, browser-close and inactivity sign-out, public registration, email/TOTP 2FA, trusted devices, and privacy-consent presentation. Security mutations are POST-backed and current-password checks protect destructive profile and administrator actions.

## Navigation and appearance

The sidebar and Nav Bar are runtime navigation, not setup-only previews. Saved sidebar visibility is permission-aware; a page does not become available merely because it appears in the tree. User reordering, if allowed, is a personal layer on top of the saved system tree.

The Nav Bar can use a curated hierarchy or a browser-session history. Its Navigation Root can remain neutral, follow the configured homepage, or use a discovered route without rewriting the stored hierarchy. Dynamic views can supply `dlux_navbar_crumbs` when their object-level labels cannot be represented by the static tree.

Imported navigation is validated against the live URLconf. Sidebar entries and Nav Bar route nodes naming a route this project does not define are dropped on import — from a first-launch `config.json`, an Options-page settings import, or `dlux_settings import` — so the builders only ever show entries that can actually render. A stale Nav Bar node's children are kept and lifted into its place, and a stale Navigation Root falls back to neutral. Manual Nav Bar nodes and sidebar entries carrying a literal `url` are never route-checked.

Themes and fonts use shared registries, so their setup choices, validation, previews, and runtime stylesheet selection remain aligned. Project-owned entries are documented in [Project Configuration](project-configuration.md#themes-and-fonts).

## Day-to-day Options

`/sys/options/` is the operational hub after setup. It provides personal display preferences to ordinary users and superuser-only System Settings, setup export, backup, Extra Features, and update actions. The System Information card presents deployment facts and on-demand service diagnostics; the Celery check is manual and stores its last result rather than probing on every page load.

For operational procedures, use [Operations](operations.md). For assets, use [Managed Assets](managed-assets.md). For deploy/update safety, use [Verified Inline Updates](inline-updater.md) and [Deployment Doctor](doctor.md).
