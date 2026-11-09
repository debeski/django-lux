# DjangoLux Features

What DjangoLux gives a project, one line per capability, with a link to the doc that
explains it. Release history is in [CHANGELOG.md](../CHANGELOG.md); commands, routes,
tags and helpers are in the [Reference](reference.md).

## Configuration

- **Setup wizard and System Settings:** a 19-step first-run wizard (plus a Project
  Settings step when a project registers settings tiles) and live editors whose
  previews render real pages with the unsaved form. See
  [System Configuration](system-configuration.md).
- **Layered configuration:** database-backed `SystemSettings` over the `DLUX_CONFIG`
  fallback, portable settings import/export and `config.json` bootstrap, with user
  preferences kept per profile. See [Project Configuration](project-configuration.md).
- **App-owned settings:** projects register their own preference and system-setting
  namespaces, Options tiles, grouped tiles and previews. See
  [UI Integration](ui-integration.md#app-preferences-and-app-owned-settings).
- **Themes, fonts and languages:** theme and font registries, custom project themes
  and fonts, RTL/LTR layouts, and translation overrides edited in the UI. See
  [Translations](translation-guide.md).
- **Deployment settings:** every accepted `DLUX_*` setting and environment variable
  in one inventory. See [Deployment Configuration](deployment-configuration.md).

## Security and accounts

- **Sign-in:** password policy, lockout, email and TOTP two-factor authentication,
  trusted devices, session controls and password reset. See
  [DSRP-1](security-dsrp-1.md).
- **Optional public registration** with mandatory email verification and optional
  approval. See [Registration](registration.md).
- **Privacy:** client-IP resolution, privacy and consent notices, and a record of the
  personal data DjangoLux stores. See [Data & Privacy](data-privacy.md).
- **Optional SSO:** separate OIDC provider and client packages. See [SSO](sso.md).

## Operations

- **Users and access:** staff tiers, groups and presets, scopes, grouped
  permissions and permission visibility filters. See [Operations](operations.md).
- **Audit and reports:** an activity log of CRUD, sign-in and download events, and
  searchable printable/XLSX reports. See [Operations](operations.md).
- **Backups:** full, data-only, portable and incremental backups, encrypted with the
  server key or a passphrase, with scheduling, retention, restore and an offline
  viewer. Backups are never served from `/media/`. See [Backups](backups.md) and the
  [DLB viewer](../tools/dlb-viewer/README.md).
- **Managed assets:** uploaded images, WOFF2 fonts and protected installer files.
  See [Managed Assets](managed-assets.md).
- **Built-in task runner:** DjangoLux's background work runs from a database
  queue with `python manage.py dlux_worker` (the `worker` service), and projects
  use the same API for their own tasks. It has a thread pool, a
  beat-style `DLUX_TASK_SCHEDULE` with `crontab`, retries with delays, at-least-once
  recovery for OCR, heartbeats, and a `django.tasks` backend on Django 6+. Celery
  for project tasks is deprecated. See [Task Runner](task-runner.md).

## Tables, forms and UI

- **Tables:** `DluxTable`, filters, row actions, density and edge styles, and
  administrator and personal column layouts. See [Table Columns](table-columns.md).
- **Ribbon:** the list-page band carrying a page's title, filters and actions. See
  [Ribbon](ribbon.md).
- **Sections and modals:** generic CRUD through sections, dynamic modals, context-menu
  actions, downloads and exports. See [UI Integration](ui-integration.md).
- **Assisted entry:** sticky forms and the optional entry clipboard. See
  [Template Customization](template-customization.md#assisted-entry) and
  [Entry Clipboard](entry-clipboard.md).
- **UI primitives:** Dlux-owned inputs, choice selectors, toggles, loading buttons,
  the Dlux icon picker and the Dlux inspector shell. See
  [Developer Guide](developer-guide.md#dlux-owned-ui-primitives).
- **Global search, tutorials and dialogs:** shared search, guided tours, the
  unsaved-changes guard and dismissible dialogs. See [UI Integration](ui-integration.md).
- **Optional weather** widget and dashboard card. See [Weather](weather.md).

## Documents

- **Document files:** one `register_document_file()` call connects upload, scan,
  viewer, page editor, downloads and file history to a model field, with
  permission-checked serving of stored files. See [Document Files](document-files.md).
- **Scanning:** workstation scanning through the ScanLink helper. See
  [ScanLink](scanlink.md).
- **OCR:** text extraction for document files through the optional `ocr` service,
  searchable from global search. See [OCR](ocr.md).
- **PDF toolkit:** the optional `pdf` extra's viewer, editor and history. See
  [PDF Toolkit](pdf-toolkit.md).

## Deployment and updates

- **Generated stack:** `startproject` writes a Compose stack with `web`, `worker`,
  `db`, `redis`, Caddy, the SMTP relay and Composer's agent. See
  [Getting Started](getting-started.md) and [Stack Schema](stack-schema.md).
- **Verified inline updates:** stable and beta channels, official-PyPI provenance
  checks, backup before update, health-gated activation and rollback, run by
  Composer. See [Inline Updater](inline-updater.md) and
  [Composer Agent](composer-agent.md).
- **Operations panel:** deployment checks and repairs, service restarts and logs as
  audited Composer operations. See [Operations](operations.md).
- **Deployment doctor:** a diagnostic report with safe repairs. See
  [Doctor](doctor.md).
- **Outbound requests** go through the Composer relay; `web` and `worker` have no
  internet access. See [Outbound Requests](outbound-requests.md).

## Developer integration

- **Project wiring:** `dlux_settings(globals())`, root `dlux.urls`, app scaffolds,
  discovery and the sidebar. See [Developer Guide](developer-guide.md).
- **Models:** `ScopedModel`, audit fields, soft delete, and actor and scope
  injection. See [Developer Guide](developer-guide.md).
- **Templates:** extension partials, page bases and form footers. See
  [Template Customization](template-customization.md).
- **Adding a system setting:** the procedure for framework contributors. See
  [Adding System Settings](adding-system-settings.md).
- **Upgrading:** removed and deprecated APIs with their removal targets. See
  [Deprecation Countdown](deprecation-countdown.md) and
  [Migrating from microsys](migrating-from-microsys.md).
