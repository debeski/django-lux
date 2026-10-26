# DjangoLux Feature Inventory

- **ScanLink stress fixes (pending 1.15.1b2 / 0.8.0b1):** Scan requests use one
  negotiated transport and never resubmit after an ambiguous connection loss;
  English/Arabic guidance asks operators to check the helper. The paired worker
  fixes completion timing, hard deadlines, request validation and result races.

Forms declaring `dlux_sticky_server = True` retain their server-computed sticky defaults in dynamic modals, including next reference numbers and validation rerenders. See [assisted entry](template-customization.md#assisted-entry).

**Current source:** v1.8.3

This is a current capability map, not a release history. Use [CHANGELOG.md](../CHANGELOG.md) for versioned changes and [Reference](reference.md) for commands, routes, tags, and public helpers.

- **ScanLink setup fixes:** ScanLink 0.7.5 provisions trusted Windows localhost
  HTTPS and renews it automatically. The shared scanner and installer panel
  retain HTTP loopback fallback and explain connection failures in English and
  Arabic. See [ScanLink workstation setup](scanlink.md).

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
- Manual incrementals let superusers choose an eligible chain head or keep Automatic; scope/encryption follow the parent, with locked eligibility checks and no chain forks. Backup Details uses a body-level modal so its backdrop cannot block its controls.
- Managed images, WOFF2 fonts, protected installer assets, and opt-in ScanLink releases.

See [Operations](operations.md), [Data & Privacy](data-privacy.md), and [Managed Assets](managed-assets.md).

## Developer integration

- `dlux_settings(globals())`, root `dlux.urls`, configuration normalization, and project-owned `extra_config['app']` namespaces.
- `ScopedModel`, audit fields, soft-delete, actor/scope injection, discovery, and generated app scaffolds.
- `DluxTable`, filter helpers, sections, dynamic modals, context-menu actions, fetch/export helpers, tutorials, and activity APIs.
- Section Manager provides one general keyword search for its selected model, preserving project queryset restrictions without importing project-specific filter controls.
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
- The maintenance page ships in the Composer image and is published on the runtime volume (stack schema 3); a project keeps its own page in `.proxy/maintenance/`.
- An Operations panel (Options admin rail) runs the deployment check and its repairs, restarts or recreates allow-listed services, and shows recent logs of one service or all of them merged — each a named, audited Composer operation; the write ones confirm with the current password. Operations remains available with inline package updates disabled, including Composer development mode; the resident agent gates execution.
- Published beta 1.14.0b3: password-confirmed Start/Stop for approved auxiliary services with Composer 1.8.0b1+. Web/Celery, proxies and data/control services remain protected; stopped existing containers can be started without recreation. Older Composer versions disable these controls.

See [Getting Started](getting-started.md), [Composer Agent Integration](composer-agent.md), [Verified Inline Updates](inline-updater.md), and [Deployment Doctor](doctor.md).


## Document files

Stable 1.12.0 promotes the accepted 1.12.0b3 implementation; see [release acceptance and upgrade requirements](release-1.12-acceptance.md).

See [Document files](document-files.md) for `register_document_file()`: one call that connects the file card (with Scan), viewer, page editor, downloads and file history for a model field, with permission and scope checks. Accepted kinds come from the `dlux.files` registry (PDF and JPG/JPEG, PNG, TIF/TIFF, WebP built in; projects add their own); images become PDF pages, and pages can be rotated or fitted to A4. History lives in `dlux.FileVersion` (migration `0026`, additive); `dlux_adopt_file_history` moves a project's own history rows over. The history table identifies who performed each change in its translated **Changed by** column.

## OCR text

Core-only imports work without optional Celery; queued viewer, automatic and background processing require a configured worker.

Background catch-up reads older files in bounded batches, with interval/queue controls and model selection. Excluded models retain manual viewer OCR.

Extraction uses bounded upload/worker queues, retries overload, and keeps an older in-flight result historical after file replacement.

See [OCR text](ocr.md) (1.15, unreleased): `dlux.ocr` reads registered document files with the stack's optional `ocr` service (`python -m dlux.ocr.serve` from the project image with the optional `ocr` extra, Indra OCR, internal network only). Every `register_document_file()` field takes part unless it passes `ocr=False`. Options live in System Settings > Extra Features (`extra_config['ocr']`, `OCR_*` environment strings only as fallbacks); saving a change of the switch starts/stops the service through Composer after a current-password check (Operations panel as fallback). Text is stored per file SHA-256 in `dlux.FileText` (migration `0029`, additive), shown from the viewer's **Extracted text (OCR)** button with Run OCR, searchable through global search and `arabic_search_q(..., model=...)`. `dlux_ocr_backfill` (batched, resumable) and `dlux_adopt_ocr_text` cover existing files and a project's own OCR rows.

## Optional PDF toolkit

See [PDF toolkit](pdf-toolkit.md) for model-agnostic `dlux.pdf` adapters, modal viewer/editor/history, local assets, and the optional `pdf` extra. Administrator controls sit in System Settings → Extra Features (stored in the app-owned `dlux.pdf` namespace). 1.11 requires an image rebuild (`>=1.11.0b7`) and introduces no PDF-feature migrations.

## 1.14 beta: table column builder

Unreleased hardening enforces the configured page-size choices at the actual paginator boundary, preventing arbitrary `?per_page=` sizes. Browser coverage for Extra Features and the final project setup step follows named steps instead of fixed indices.

Beta 1.14.0b2 merges the published 1.13.2b1 fixes into the table-builder line: paginated backup/restore histories with Dlux row actions and fixed restore density, user-menu tour closing, and the preceding 1.13.1 setup-upload/search/tour fixes. It preserves the shared inspector and adds no migrations beyond b1.

Finishing controls use the short **Restore** label and enable it only while a column override exists. Reverted table edits leave the form clean, including visibility toggles that now retain column position. Ribbon buttons also support drag ordering alongside the existing draggable tabs, with saved per-host order applied to actual pages.

Published beta 1.14.0b1 adds a Tables settings step, canonical `tables_config` storage with legacy mirrors, model-keyed discovery and presentation overlays for generated and handwritten tables. The ribbon shell and shared element inspector support localized header labels, optional icons, visibility, primary/secondary default sorting, per-column reset and per-table reset with the rewind icon. Removed developer columns remain restorable; shown headers support drag and keyboard/tap ordering. Dlux-supplied tables are hidden behind the default-off **Show system items** filter. Dedicated record-visibility gates remain in control. Admin-created columns are deferred. See [table-columns.md](table-columns.md).

The 1.14.1 candidate adds **Arrange columns** for each authenticated table viewer: personal order/visibility, drag or arrow controls and restore. Administrator-hidden/developer-excluded columns and dedicated controls remain enforced. Preferences are isolated per user and table variant; no migration or Composer protocol change. See [personal column organization](table-columns.md#personal-column-organization-1141).

Mono supports readable table-builder header controls and borderless disclosure
links across normal, hover and keyboard-focus states.
