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

## I am Integrating microSYS into a Django Project

- [Developer Guide](developer-guide.md) for the system mental model, configuration layers, scoped models, discovery, and when to use each subsystem.
- [Customization Guide](customization-guide.md) for `MICROSYS_CONFIG`, translations, sections, dynamic modals, context-menu integrations, fetch/export utilities, activity logging, autofill, and template overrides.

## I Need Reference Material

- [Reference](reference.md) for management commands, endpoints, template tags, helper utilities, and codebase entry points.
- [Customization Guide](customization-guide.md#universal-fetcher-and-excel-export) for download/export helpers.
- [Customization Guide](customization-guide.md#context-menu-integration) for action schema and integration patterns.
- [Customization Guide](customization-guide.md#activity-logging-and-audit-trail) for the audit-log model and manual hooks.

## Current Major Capabilities

- Runtime system configuration with a first-launch wizard, live System Settings editing, translation overrides, theme defaults, language defaults, and a global home URL.
- A full internal-operations UI including user management, profiles, grouped permissions, activity logs, scopes, sections, options, and built-in two-factor authentication flows.
- A resolver-driven sidebar system with discovered app pages, structured groups, runtime tree rendering, and user-level reordering layered on top of the system default.
- A generic CRUD layer made of sections, dynamic modals, list/filter helpers, and reusable context-menu actions and events.
- A built-in audit trail that records CRUD, login/logout, user-profile merges, diffs, masked sensitive changes, and download/export actions.
- Data-movement helpers such as the universal fetcher, Excel export, sticky autofill, recursive foreign-key autofill, and downloadable file handling.
- Framework-level automation for translations, scope injection, actor tracking, soft-delete, and UI preference persistence.
- Tutorial and design infrastructure including view-aware walkthroughs, theme-aware surfaces, and extension hooks for head/scripts injection.

## Maintenance Rule

When a feature changes:

- update the relevant page under `docs/`
- add the release note to `CHANGELOG.md`

That keeps the docs discoverable and stops the README from turning back into a giant mixed-purpose manual.
