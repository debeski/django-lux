# DjangoLux Feature Inventory

**Current source:** v1.8.3

This is a current capability map, not a release history. Use [CHANGELOG.md](../CHANGELOG.md) for versioned changes and [Reference](reference.md) for commands, routes, tags, and public helpers.

## Platform configuration

- Database-backed `SystemSettings` layered over `DLUX_CONFIG`, with user-level preferences stored separately in `Profile.preferences`.
- A seventeen-step initial setup wizard and focused System Settings editors for identity, localization, homepage, email, security, navigation, search, notifications, appearance, logging, profiles, backups, and optional features.
- Canonical `homepage_config` and `search_config` stores, with v1.x compatibility mirrors for legacy integrations.
- Theme/font registries, custom project themes/fonts, RTL/LTR rendering, and system/user override policy.
- Portable setup import/export and `config.json` bootstrap for unconfigured generated projects.

See [System Configuration](system-configuration.md) and [Deployment Configuration](deployment-configuration.md).

## Security and operations

- Local authentication with password policy, lockout, email/TOTP 2FA, trusted devices, session controls, password reset, and optional public registration.
- Centralized client-IP resolution, privacy/consent presentation, audit logging, scope-aware permissions, and POST-only security mutations.
- Users, staff tiers, groups/presets, scopes, activity logs, printable/XLSX reports, full/data-only backups, restore controls, and the offline DLB viewer.
- Managed images, WOFF2 fonts, protected installer assets, and opt-in ScanLink releases.

See [Operations](operations.md), [Data & Privacy](data-privacy.md), and [Managed Assets](managed-assets.md).

## Developer integration

- `dlux_settings(globals())`, root `dlux.urls`, configuration normalization, and project-owned `extra_config['app']` namespaces.
- `ScopedModel`, audit fields, soft-delete, actor/scope injection, discovery, and generated app scaffolds.
- `DluxTable`, filter helpers, sections, dynamic modals, context-menu actions, fetch/export helpers, tutorials, and activity APIs.
- Dlux-owned inputs, choice selectors, toggles, loading buttons, the **Dlux icon picker** (`dlux/helpers/icon_picker.html`, initialized by `initIconPickers()`), and the adapter-driven **Dlux inspector shell** (`window.DluxInspectorShell.create(...)`).
- Translation dictionaries, database-backed override entries, language catalogs, and RTL-aware template behavior.

See [Developer Guide](developer-guide.md), [Project Configuration](project-configuration.md), [Translations](translation-guide.md), [UI Integration](ui-integration.md), and [Template Customization](template-customization.md).

## Generated deployment

- A generated Compose baseline with `web`, `celery`, `db`, `redis`, Caddy (nginx fallback), SMTP relay, and Composer's agent/executor/proxy topology.
- Compose `pre_start` reconciliation/migration hooks, a persistent runtime volume, active-release supervisor, maintenance handling, and health checks.
- Composer-owned package/image update execution with manifest safety gates, backup-before-intent behavior, external health-gated activation, and rollback.

See [Getting Started](getting-started.md), [Composer Agent Integration](composer-agent.md), [Verified Inline Updates](inline-updater.md), and [Deployment Doctor](doctor.md).
