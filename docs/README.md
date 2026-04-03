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
- [Customization Guide](customization-guide.md) for `MICROSYS_CONFIG`, translations, sections, dynamic modals, context-menu events, autofill, and template overrides.

## I Need Reference Material

- [Reference](reference.md) for management commands, endpoints, template tags, helper utilities, and codebase entry points.

## Current Major Capabilities

- A three-step first-launch setup wizard for branding, languages, themes, global home URL, and sidebar structure.
- A runtime Options view for accessibility, theme, language, autofill, reset actions, and superuser-only System Settings updates.
- A resolver-driven sidebar builder that feeds the live runtime sidebar tree instead of a separate builder-only format.
- Interactive user management with a two-step wizard and dynamically translated permission labels.
- Automatic translation patches for forms, filters, tables, and context-menu labels.
- `ScopedModel` support with audit fields, soft-delete, actor tracking, and automatic scope injection.
- Dynamic tutorial coverage for the main microsys views based on the active URL.
- Persistent preferences for theme, language, sidebar state, and autofill behavior.

## Maintenance Rule

When a feature changes:

- update the relevant page under `docs/`
- add the release note to `CHANGELOG.md`

That keeps the docs discoverable and stops the README from turning back into a giant mixed-purpose manual.
