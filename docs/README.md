# microSYS Documentation

microSYS now uses a layered documentation structure:

- `README.md` is the package landing page.
- `docs/` is the operating and integration manual.
- `CHANGELOG.md` is the release-history archive.

Use the sections below based on what you are trying to do.

## Start Here

- [Getting Started](getting-started.md) for installation, Django configuration, and first launch.
- [Changelog](../CHANGELOG.md) for release-by-release history and migration context.

## I am Configuring microSYS

- [Admin Guide](admin-guide.md) for the first-launch setup wizard, Options view, sidebar builder, themes, languages, and runtime preferences.
- [MSRP-1 Security Standard](security-msrp-1.md) for the active backend authorization and security-flow policy.
- [Public Registration Playground](registration.md) for the disabled-by-default email-verified local signup path.
- [Optional SSO Packages](sso.md) for the separate OIDC provider plugin and client SDK.

## I am Integrating microSYS into a Django Project

- [Developer Guide](developer-guide.md) for the system mental model, configuration layers, scoped models, discovery, and when to use each subsystem.
- [Customization Guide](customization-guide.md) for `MICROSYS_CONFIG`, translations, sections, dynamic modals, context-menu integrations, fetch/export utilities, activity logging, autofill, and template overrides.

## I Need Reference Material

- [Features](FEATURES.md) — complete feature inventory covering every capability from scaffolding to security, tables, themes, and UI infrastructure.
- [Reference](reference.md) for management commands, endpoints, template tags, helper utilities, and codebase entry points.
- [MSRP-1 Security Standard](security-msrp-1.md) for the core backend authorization contract and the no-inline runtime asset policy.
- [Customization Guide](customization-guide.md#universal-fetcher-and-excel-export) for download/export helpers.
- [Customization Guide](customization-guide.md#context-menu-integration) for action schema and integration patterns.
- [Customization Guide](customization-guide.md#activity-logging-and-audit-trail) for the audit-log model and manual hooks.

## Current Major Capabilities

- Runtime system configuration with a first-launch wizard, live System Settings editing, translation overrides, theme defaults, language defaults, a global home URL, and sidebar behavior controls.
- A full internal-operations UI including user management, profiles, grouped permissions, activity logs, scopes, sections, draggable Options cards, and built-in two-factor authentication flows.
- A disabled-by-default public registration playground with mandatory email verification, SMTP readiness checks, throttles, honeypot protection, and optional superuser approval.
- A resolver-driven sidebar system with discovered app pages, permission-based item visibility, structured groups, runtime tree rendering, optional user-level reordering layered on top of the system default, and a configurable runtime toolbar.
- A shared theme registry that keeps theme validation, ordering, previews, and CSS inclusion aligned across setup, options, and the live runtime UI.
- A generic CRUD layer made of sections, dynamic modals, list/filter helpers, and reusable context-menu actions and events.
- Reusable helper APIs such as `require_current_password(...)`, `set_profile_totp_state(...)`, `build_archive_file_field(...)`, and `build_settings_toggle_field(...)` for extending security and System Settings surfaces without duplicating framework behavior.
- A built-in audit trail that records CRUD, login/logout, user-profile merges, diffs, masked sensitive changes, and download/export actions.
- Optional OIDC SSO packages that keep provider/client behavior separate from core Microsys runtime imports.
- Data-movement helpers such as the universal fetcher, Excel export, sticky autofill, recursive foreign-key autofill, and downloadable file handling.
- Framework-level automation for translations, scope injection, actor tracking, soft-delete, UI preference persistence, and CSP-friendly external asset usage across shipped templates.
- Tutorial and design infrastructure including view-aware walkthroughs, theme-aware surfaces, and extension hooks for head/scripts injection.
