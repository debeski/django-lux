# DjangoLux Feature Inventory

**Current source:** v1.8.3

This is a current capability map, not a release history. Use [CHANGELOG.md](../CHANGELOG.md) for versioned changes and [Reference](reference.md) for commands, routes, tags, and public helpers.

- **Entry clipboard:** Extra Features enables tab-local snippets through a
  popover opened by a clipboard icon beside the sticky-form header switch, with compact control rows, snippet insert/replace actions and full-content viewing; ribbons and Dlux reports are excluded and eligible entry fields use explicit opt-out. Sticky forms retain ownership of prefill. See
  [Entry clipboard](entry-clipboard.md).
- Custom full-page forms show the Assisted entry legend with clipboard controls;
  sticky reuse remains conditional on explicit model capability metadata.
- Clipboard snippets are isolated by user and cleared on logout/account switches;
  stale browser-history restores reload their clipboard state.

## Platform configuration

- Section-owned settings saves preserve inactive controls, including missing or
  stale hidden inputs. Partial imports merge supplied keys, retain existing SMTP
  credentials, and share boolean parsing with the catalogue normalizers.
  Single and grouped app settings writers lock the current row before merging,
  and so do ordinary section saves, which re-apply a stale submission on top of
  a newer write. Stored groups override `DLUX_CONFIG` by one declared policy;
  Extra Features and app namespaces merge with the project's per entry.
  Nonvisual controls (ScanLink, clipboard, PDF options) never swap the live preview.
  See [System settings persistence](system-configuration.md#settings-persistence-contracts).

- **Optional weather:** OpenWeather current conditions, searchable saved locations,
  Celsius/Fahrenheit, four display styles, titlebar/user hub/floating placements,
  and a reusable dashboard card. Controlled from Extra Features; disabled by
  default. See [Weather](weather.md).

- Database-backed `SystemSettings` layered over `DLUX_CONFIG`, with user-level preferences stored separately in `Profile.preferences`.
- An eighteen-step initial setup wizard (plus a Project Settings step when a project registers settings tiles) and focused System Settings editors whose previews are real pages rendered by the server with the unsaved form: the live page behind the Options modal follows every change (glass mode lifts the modal off it), and the login, home, profile and sample list/form/modal pages open in a popup in the draft's language. Nothing is saved until Save.
- Canonical `homepage_config` and `search_config` stores, with v1.x compatibility mirrors for legacy integrations.
- Per-user landing pages chosen by the user in Options, or assigned by administrators per user and per group preset, when the per-user homepage switch is on.
- App-owned System Settings previews by page: `registerAppPreview(namespace, {path})` renders that page with the unsaved app form applied.
- Grouped project settings tiles: `register_app_settings_group()` + `register_app_settings(group=...)` show several namespaces as sections of one Options tile, validated together and saved in one write (`write_app_system_configs()`).
- Theme/font registries, custom project themes/fonts, RTL/LTR rendering, and system/user override policy.
- Portable setup import/export and `config.json` bootstrap for unconfigured generated projects.

See [System Configuration](system-configuration.md) and [Deployment Configuration](deployment-configuration.md).

## Security and operations

- Local authentication with password policy, lockout, email/TOTP 2FA, trusted devices, session controls, password reset, and optional public registration.
- Centralized client-IP resolution, privacy/consent presentation, audit logging, scope-aware permissions, and POST-only security mutations.
- Permission visibility filters: optional features hide their permissions from the group/user editors while disabled, and saves keep the existing grants.
- Users, staff tiers, groups/presets, scopes, activity logs, printable/XLSX reports, full/data-only/portable and incremental (chained) backups (server-key, passphrase or unencrypted; snapshot-consistent on PostgreSQL; cancellable, with a live details console and time estimates), restore controls, and the offline DLB viewer.
- Managed images, WOFF2 fonts, protected installer assets, and opt-in ScanLink releases.

See [Operations](operations.md), [Data & Privacy](data-privacy.md), and [Managed Assets](managed-assets.md).

## Developer integration

- `dlux_settings(globals())`, root `dlux.urls`, configuration normalization, and project-owned `extra_config['app']` namespaces.
- `ScopedModel`, audit fields, soft-delete, actor/scope injection, discovery, and generated app scaffolds.
- `DluxTable`, filter helpers, sections, dynamic modals, context-menu actions, fetch/export helpers, tutorials, and activity APIs.
- Dlux-owned inputs, choice selectors, toggles, loading buttons, the **Dlux icon picker** (`dlux/helpers/icon_picker.html`, initialized by `initIconPickers()`), and the adapter-driven **Dlux inspector shell** (`window.DluxInspectorShell.create(...)`).
- Translation dictionaries, database-backed override entries, language catalogs, and RTL-aware template behavior.
- `dlux_translations` audit command: missing, undefined, permission-label, duplicate and untranslated keys, with paste-ready stubs and a CI `--fail` mode.

See [Developer Guide](developer-guide.md), [Project Configuration](project-configuration.md), [Translations](translation-guide.md), [UI Integration](ui-integration.md), and [Template Customization](template-customization.md).

## Generated deployment

- A generated Compose baseline with `web`, `celery`, `db`, `redis`, Caddy (nginx fallback), SMTP relay, and Composer's agent/executor/proxy topology.
- Compose `pre_start` reconciliation/migration hooks, a persistent runtime volume, active-release supervisor, maintenance handling, and health checks.
- Composer-owned package/image update execution with manifest safety gates, backup-before-intent behavior, external health-gated activation, and rollback.
- Generated stack files (`compose.yml`, `Dockerfile`, `.env`, proxy configs, entrypoint) carry the stack contract schema they were written for, reported by the `stack.schema` doctor check ([Stack Schema Stamps](stack-schema.md)).
- Stable and beta release channels: stable is the default and excludes every prerelease, beta is an explicit per-deployment opt-in, and opting out never downgrades an installed release.

See [Getting Started](getting-started.md), [Composer Agent Integration](composer-agent.md), [Verified Inline Updates](inline-updater.md), and [Deployment Doctor](doctor.md).


## Document files

Stable 1.12.0 promotes the accepted 1.12.0b3 implementation; see [release acceptance and upgrade requirements](release-1.12-acceptance.md).

See [Document files](document-files.md) for `register_document_file()`: one call that connects the file card (with Scan), viewer, page editor, downloads and file history for a model field, with permission and scope checks. Accepted kinds come from the `dlux.files` registry (PDF and JPG/JPEG, PNG, TIF/TIFF, WebP built in; projects add their own); images become PDF pages, and pages can be rotated or fitted to A4. History lives in `dlux.FileVersion` (migration `0026`, additive); `dlux_adopt_file_history` moves a project's own history rows over. The history table identifies who performed each change in its translated **Changed by** column.

## Optional PDF toolkit

See [PDF toolkit](pdf-toolkit.md) for model-agnostic `dlux.pdf` adapters, modal viewer/editor/history, local assets, and the optional `pdf` extra. Administrator controls sit in System Settings → Extra Features (stored in the app-owned `dlux.pdf` namespace). 1.11 requires an image rebuild (`>=1.11.0b7`) and introduces no PDF-feature migrations.

## In development: table column builder

The 1.14 branch adds a Tables settings step, canonical `tables_config` storage with legacy mirrors, model-keyed discovery and a visibility/ordering overlay for generated and handwritten tables. The builder uses the ribbon shell with wrapping column chips, draggable headers, keyboard/tap ordering and per-model reset. Dlux-supplied tables are hidden behind the default-off **Show system items** filter. Dedicated record-visibility gates remain in control. Release integration is pending; see [table-columns.md](table-columns.md).
