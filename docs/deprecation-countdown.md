# Deprecation Countdown

This page records live compatibility contracts and their concrete removal targets. Historical detail from the pre-v1.8 documentation reorganization is retained in `.xclude/docs/deprecation-countdown.md`.

## Active through v1.x

### Celery for project tasks

DjangoLux runs none of its own work on Celery: its tasks run on `dlux_worker`
(the `worker` service, stack schema 5), and new projects get no Celery. See
[Task Runner](task-runner.md).
- **1.16.0:** Celery for project tasks is deprecated. Doctor check
  `tasks.celery_deprecated` warns while a project has a Celery app, beat entries
  or `CELERY_BROKER_URL`. A stack migrated by `./start.sh check --fix` keeps a
  project-only `celery` service for the project's own tasks.
- **1.18.0:** generated stacks stop installing Celery. A project that still uses
  it is warned to move to `@dlux.taskrunner.task` and `DLUX_TASK_SCHEDULE`
  ([Moving project tasks from Celery](task-runner.md#moving-project-tasks-from-celery)).

Compatibility kept until **1.18.0**:
- `dlux_settings()` still defines `CELERY_BEAT_SCHEDULE` (as a dict without
  DjangoLux's entries) for projects that add their own beat entries to it after
  the call.
- `dlux.backup.system_backup_celery_available` and
  `dlux.reports.report_backup_celery_available` alias
  `system_backup_worker_available` and `report_backup_worker_available`.
- The `dlux.tasks` attribute names (`build_system_backup_task`, `ocr_file`, ...)
  are the `DluxTask` objects from `dlux.jobs`; send by name with
  `dlux.taskrunner.enqueue()` instead.

Task names stay `dlux.tasks.*`. The stored config keys `use_celery` (backups)
and `backup_use_celery` (reports) keep their names; they switch background
builds on the task worker.

### The `docker-socket-proxy` service

Generated stacks have no `docker-socket-proxy`: `composer-executor` answers
`composer-agent`'s Docker reads, and the proxy's container inspect would hand the
agent every service's environment. The stack contract lists it under
`removed_services` and tolerates its read-only socket mount
(`invariants.docker_socket.tolerated`) on stacks that still run it. Composer's
`./start.sh check` warns about it (`docker-proxy`), and `./start.sh check --fix`
removes its container and its service from the generated Composer block.
- **1.18.0:** the tolerance ends. A proxy still in the stack is a contract
  violation.

### Homepage settings aliases

`SystemSettings.homepage_config` is canonical. The legacy `home_url`, `public_root_config`, and profile landing-page permission paths are mirrored on save, accepted by runtime configuration/import, and scheduled for removal in v2.0. Move host code to `homepage_config` now; user-facing copy should call the anonymous destination the public page.

### Global-search titlebar aliases

`SystemSettings.search_config` is canonical. `titlebar_config.global_search_mode` and `titlebar_config.global_search_include_data` remain accepted/mirrored through v1.x and are removed in v2.0. Move host code to `search_config` now.

### Static/template compatibility paths

The `dlux/main/css/{main,buttons,index_cards}.css` compatibility stylesheets and `dlux/includes/messages.html` template shim remain until the next major release. New project code should use `dlux/base/css/...` and `dlux/notifications/messages.html`.

### Embedded strings block

Pages load the strings table as a script and set `window.DLUX_STRINGS`
([Translations](translation-guide.md#strings-in-the-browser)); they no longer embed
it as `<script id="dlux-strings-data" type="application/json">`. For project scripts
that still parse that block (Trademarks' dashboard chart), `base_head.js` adds an
empty element with that id whose `textContent` serialises `window.DLUX_STRINGS`
when read. Read `window.DLUX_STRINGS` or `window.dluxString()` instead; the element
is removed in v2.0.

### Public package facades

The `dlux.forms`, `dlux.models`, `dlux.reports`, `dlux.discovery`, `dlux.backup`, and `dlux.translations` package facades are public API and remain permanently. Their internal module splits do not require host-project import changes.

### Project-owned PDF adapters and file-history models

As of v1.12.0b2 DjangoLux owns file history (`dlux.FileVersion`) and the wiring between the file card, Scan, viewer, page editor and history (`register_document_file()`, see [Document files](document-files.md)). `PdfEditorView` with a project adapter, and project history models such as Archive's and Decrees' `DocumentFileVersion`, keep working unchanged through v1.x. Move to `register_document_file()` and run `dlux_adopt_file_history <app.Model>`; the adapter path is scheduled for removal in v2.0.

### `pdfjsLib` before PDF.js loads

`dlux/pdf/assets.html` loads PDF.js on demand (see
[PDF Toolkit](pdf-toolkit.md#integration)). Before it has loaded,
`dlux/pdf/js/pdfjs.js` sets `window.pdfjsLib` to a stand-in whose
`getDocument(source).promise` (and `destroy()`) loads PDF.js first and a
`GlobalWorkerOptions.workerSrc` set on it carries over, so project code that
calls `window.pdfjsLib.getDocument()` keeps working (Archive's
`documents/composition/js/paper.js`). Nothing else on the stand-in works. Switch
to `const pdfjsLib = await window.DluxPdfJs.load()`; the stand-in is removed in
v2.0.

### `destroy()` on a loaded PDF.js document

PDF.js 6 removed `PDFDocumentProxy.prototype.destroy()`; a document is released
by destroying its loading task. So that project code calling `pdf.destroy()` on
a resolved document keeps working (Archive's
`documents/composition/js/paper.js`), `DluxPdfJs.load().getDocument()` restores a
`destroy()` on the returned document that destroys the loading task. Call
`loadingTask.destroy()` instead; the document-level shim is removed in v2.0.

### `dlux/tutorial/main.html`

The guided tour loads on its first click, so `dlux/base.html` does not include
`dlux/tutorial/main.html`. The template is kept and renders nothing for projects
that include it; remove the include. Removed in v2.0.

### Composer `self update`

Composer 1.9.1b1 (wrapper 5) replaces `./start.sh self update` with `./start.sh update self`, and a plain `./start.sh update` now refreshes the deployer before the stack. `self update` stays as a deprecated alias that prints a pointer to `update self`. DjangoLux keeps showing `./start.sh self update` to stacks whose Composer is too old for an operation (`dlux.updater.ops`, `dlux.relay`, `dlux_relay`, `dlux_ops_composer_behind_host`), because those stacks' wrappers and Composer do not know `update self`. Remove the alias, and switch that guidance to `update self`, only once DjangoLux's Composer floor is at least 1.9.1 and wrapper 5 has been out through one stable cycle; target v2.0.

### Archive form class names

The document-form and form-card classes kept the names they had in `project-archive`. Their
DjangoLux names are canonical; the old names select the same rules until they are removed in
**v1.19.0**:

| Deprecated | Use |
| --- | --- |
| `.archive-form-actions` | `.dlux-form-cards` |
| `.archive-form-action`, `-icon`, `-copy`, `-title`, `-meta`, `-primary`, `-secondary`, `-neutral` | `.dlux-form-card`, with the same suffixes |
| `.archive-document-form` | `.dlux-document-form` |
| `.archive-checkbox-field` | `.dlux-checkbox-field` |

The `--archive-form-*` custom properties are renamed to `--dlux-document-form-*` without an alias;
no project set them. `project-archive` (`documents/forms.py`, `documents/modals.py`, the
`document_modal.html`, `incoming_list.html` and `partials/checkbox_field.html` templates, and its
modal CSS) and `project-decrees` (`documents/forms.py`, `documents/css/overrides.css`) still use the
old classes and must move to the new names before v1.19.0.

### Raw `ImageField` for project images

As of v1.8.4 a model image or font belongs in the asset library through
`ManagedAssetField`, not a plain `ImageField`/`FileField`. See
[Managed assets](managed-assets.md).

Nothing is removed — Django's own fields are not dlux's to deprecate — but a
project adding a new raw image field is going against the standard, and the
namespaced picker, the permission-checked instant upload and the clean-up action
do not apply to it. Existing fields migrate by adding the asset field beside the
old one and adopting the stored file on first save; `SystemSettings.logo` and
`favicon` are dlux's own example of that pairing and stay readable indefinitely.

`Profile.profile_picture` is a deliberate exception and stays an `ImageField`.
An avatar is one person's, not a reusable library file, and nothing else should
be able to pick it — putting it in a shared, de-duplicating library would be the
wrong shape even before the permission question of a user editing their own row.

### `'unsafe-inline'` and `'unsafe-eval'` in a project's `script-src`

Generated projects send a nonce-only `script-src` (`[SELF, NONCE]`). A project
whose `CONTENT_SECURITY_POLICY` still allows `'unsafe-inline'` or `'unsafe-eval'`
for scripts gets system check warning `dlux.W201`. In **v1.20.0** the warning
becomes an error, so `manage.py check` and the deploy fail until the policy is
nonce-only. Move inline scripts and handlers as
[Content Security Policy](security-dsrp-1.md#content-security-policy) describes.

## Removed in v1.8.0

- `dlux.constants` — import from `dlux.system.constants`.
- Cookie-based assisted-entry preference (`enable_prefill`) — use `sticky_forms_enabled()` and `sticky_form_initial()`.
- The generated `dlux-updater` Compose service — reconciliation/migrations moved to `celery` `pre_start`; the state tick moved to Celery Beat. Existing generated stacks migrate through `./start.sh check --fix`.

## Removed in v1.10.0

Four compatibility contracts reached their removal date. Nothing below is importable, selectable
or accepted any more; each entry says what to use instead.

### `AUDIT_FIELD_NAMES`

`dlux.utils.AUDIT_FIELD_NAMES` was a plain alias of `DEFAULT_AUDIT_COLUMNS` and never carried a
project's additions. Use `dlux.system.constants`: `audit_column_names()` for the columns gated by
`show_audit_fields`, `deletion_column_names()` for the soft-delete pair, and
`record_visibility_column_names()` for both. Each is extensible by a host project through
`DLUX_AUDIT_COLUMNS` / `DLUX_DELETION_COLUMNS`. Note also that `deleted_by` is no longer treated
as an audit column: a deletion is not a change history, so it answers to `show_soft_deleted` and
the superuser gate along with `deleted_at`.

### In-container update executor

Removed: `DLUX_UPDATE_EXECUTOR = "inline"`, the executor behind it (the in-container check,
apply and rollback paths of `dlux.updater.service`, and the release-selection helpers
`fetch_simple_index` / `select_latest_candidate` that only it used), and the
`python -m dlux enable-updater` / `enable-agent` Compose migrations (`dlux.scaffold.legacy`).
Composer has performed every inline update since v1.8.0; `DLUX_UPDATE_EXECUTOR` is now ignored.
Existing generated stacks migrate with `./start.sh check --fix`. See
[Verified Inline Updates](inline-updater.md#who-does-what).

### `archive_file` names on the file widget

The file-upload widget kept the names it had in `project-archive`'s document forms. They were
replaced in v1.8.3 and the shims are gone:

| Removed | Use |
| --- | --- |
| `build_archive_file_field(...)` | `build_file_field(...)` |
| `_build_archive_file_widget(...)` | `_build_file_widget(...)` |
| `archive_file_*` translation keys (read as a fallback) | `file_field_*` |
| `class="archive-file-input"` selecting the file-card template | `dlux-file-input` |
| `.archive-file-*` classes, `data-archive-file-*` attributes | `.dlux-file-*`, `data-dlux-file-*` |

`apply_archive_file_widgets` / `build_archive_file_fields_row` in archive and dhub are those
projects' own helpers built on `DluxFileInput`, not these shims. A project whose own widget
still carries `archive-file-input` (project-dhub) must move to `dlux-file-input`.

### `advanced_filter_helper`

`dlux.utils.advanced_filter_helper` is removed. It is superseded by the ribbon (`dlux.ribbon`),
which derives a list page's filter band from the FilterSet instead of a per-view
`advanced_config` dict, and whose layout is an administrator setting rather than fixed markup. See
[Ribbon](ribbon.md). `setup_filter_helper()` remains for a plain filter bar. `project-archive`,
`project-decrees`, `project-trademarks` and both `project-sales-crm` editions had moved to the
ribbon; `project-dhub` still calls the helper (6 sites in `documents/filters.py`) and must adopt the
ribbon before it upgrades past v1.9.x.

## Removed in v1.16.3

### App-side wheel download, attestation and install

Reconcile rebuilds a lost active pointer from the runtime volume only: `web` and
`worker` have no internet, and Composer stages every release. The helpers that
fetched, attested and installed a wheel inside the application container are
removed:

| Removed | Use |
| --- | --- |
| `dlux.updater.manifest.download_wheel`, `verify_pypi_attestation` | Composer's agent (`composer/dlux_release_source.py`) |
| `dlux.updater.manifest` constants `ALLOWED_DOWNLOAD_HOSTS`, `MAX_INDEX_BYTES`, `MAX_WHEEL_BYTES`, `PYPI_PROJECT_REPOSITORY`, `PYPI_PROJECT_REPOSITORY_NAME`, `PYPI_RELEASE_WORKFLOW` | Composer's own release-source constants |
| `RuntimeStore.install_wheel`, `wheel_path`, `activate_stage` | Composer's staging into `releases/<version>/` |

No consumer project imported them. The `DluxUpdateState` columns `active_wheel_url`
and `active_wheel_sha256` stay, and nothing reads them. See
[Recovery and rollback](inline-updater.md#recovery-and-rollback).
