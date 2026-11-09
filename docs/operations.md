# Operations

This guide covers routine administration after system configuration. Use
[System Configuration](system-configuration.md) for the wizard and Options settings,
and [Deployment Configuration](deployment-configuration.md) for environment-owned
settings.

## Users, staff, and permissions

User management is available at `/sys/users/`. Staff access is governed by the same
backend permissions that control its UI: visibility is never authorization. Use
groups/presets for repeatable permission bundles and scopes when access must be
limited to an organizational subset of records.

The relevant tiers are:

- **Superuser** — framework-wide administration, including security-sensitive configuration and update approval.
- **Global staff** — staff access across scopes, limited by assigned permissions.
- **Scoped staff** — staff access constrained to the user's active scope.

Public-registration defaults are selected in Manage Scopes and Manage Groups, not by
editing a System Settings field. Mark one landing scope and any applicable group
presets; DjangoLux applies them after registration activation.

## Account security in daily use

Users can configure TOTP, recover backup codes, manage trusted devices, and end
recorded sessions from Profile. Trusted sessions take precedence over untrusted
sessions. When single-session enforcement is enabled, a successful login or
completed 2FA login ends the user's other sessions. Otherwise, password change can
optionally end other signed-in devices while retaining the current browser.

Administrators can use the Admin panel command rail for bulk forced password change
and destructive data reset. Both require the current password. Reset data excludes
System Settings, updater state, permission groups, superusers, and any model whose
rows are only a line of another record (an invoice's items go with the invoice).
Take a full system backup before using data reset.

Reset data runs in one of two modes:

- **Soft**, the default, soft-deletes `ScopedModel` subclasses so they stay
  recoverable, and hard-deletes everything else.
- **Permanent** hard-deletes every selected model and empties those models' recycle
  bins as well, so rows soft-deleted by any earlier action go too. It requires the
  confirmation word typed into the dialog on top of the password, and there is no
  undo. Use it only to start a system over.

Bulk writes run no `save()` or `delete()`, so a figure a project derives in those
methods — a stock balance, a cached total — is stale once the rows behind it are
cleared. A project repairs its own by connecting to
`dlux.admin_actions.data_reset.data_reset_finished`.

## Activity logs and reports

`/sys/logs/` is an operational audit surface. It records configured CRUD events,
login/logout, merged User/Profile changes, masked sensitive values, and
download/export activity. Scope-aware staff see only the activity they are
authorized to inspect.

The User Report is available to authorized staff from the user directory. It
combines account/security facts, activity, known devices, and IP observations; the
modal can be printed through the browser or exported as XLSX.

From **General Reports**, a staff user with the reports permission (but not
user-directory and activity-log access) opens an *activity* version for the users
that page lists. It holds account basics plus that user's creates, edits and deletes
per model and their recent actions, counted within the viewer's report scope,
without devices, addresses, sessions or e-mail. Its XLSX has no network columns.

The user report modal and its XLSX take the page's `window`, plus `custom_start`/
`custom_end` for a custom range. Opened from General Reports, a user's report keeps
the page's period: a period other than week, month or all (a quarter, half-year,
year or custom range) gets its own tab in the modal (`report.selected_period_tab`).

### General Reports

General Reports (`/sys/reports/`) count business activity
(`ActivityLog.category = "user"`) rather than framework infrastructure events. They
need `dlux.view_reports` (superusers always pass). The page, its workbook, its print
view and its archive share one set of criteria:

- `window`, with optional inclusive `custom_start`/`custom_end`;
- repeated `models` and repeated `operations`;
- `builder=1` for the report builder;
- `q`, the search field.

An archive job stores the normalized, allow-listed criteria in
`ReportBackup.criteria`.

`q` matches the username or full name, the document number, the stored action or
model name, and any operation or model label as the page shows it (a translated
model or operation label, for instance). The field suggests the visible users'
usernames and full names and the offered models and operations.

Report model discovery is separate from navigation discovery, and each model has
one entry. Activity logged under a legacy name (such as `decree`), a translated
verbose name or an older key that resolves to an installed model counts under its
`label_lower` (`dlux.reports.report_model_key`), with the label the sidebar and
tables use (`report_model_label`). Configure the model list under
`DLUX_CONFIG['reports']`:

- set `dlux_report = False` on a model, or list its `app_label.model_name` under
  `exclude_models`, to leave it out. Exclusions win over `include_models`;
- `exclude_activity` drops activity by its logged model name, including legacy
  names that resolve to no installed model;
- infrastructure packages (`health_check`, `rest_framework`, `corsheaders`, `csp`)
  are left out unless listed under `include_models`.

General Reports produce three outputs:

- **Print view** (`/sys/reports/print/`): the selected criteria as a print-ready
  analytical report, with charts and a table twin for each chart, drawn with the
  bundled Chart.js on a fixed paper surface.
- **Export Entries** (`/sys/reports/export.xlsx`): the selected models' actual rows,
  one sheet per model filtered by period and scope, plus an Export Info index sheet.
  Credential-named fields (password, passphrase, secret, token, API key) are always
  dropped. `DLUX_CONFIG['reports']['entries_exclude_fields'] = {'app.model': ['field']}`
  drops more, and `entries_row_limit` (default `20000`) caps each sheet.
- **Archive ZIP**: `entries.xlsx` (the Export Entries workbook), the referenced media
  under `files/`, and `manifest.json`, whose `selection` records the exact
  normalized criteria. Downloading it needs `dlux.download_backup`.

The archive is a periodic deliverable, never a restore source, so it carries no
`data/*.json`: `stream_model_into_zip(include_records=False)` leaves the JSON out
for this ZIP only. The restorable system backup is described in
[Backups](backups.md). Both read rows in primary-key pages with a backup-local JSON
serializer, so PostgreSQL deployments need no server-side named cursors.

Reports count the activity log. Records saved before the deployment logged activity
(imports, seeds, a project that adopted DjangoLux reports later) are not counted
until they have a `CREATE` row. `python manage.py dlux_backfill_report_activity`
lists how many are missing per model. With `--apply` it writes them from each
record's own creation time, creator, scope and number, marked `details.backfilled`,
and skips any record that already has one.

On a generated stack run it as `./start.sh run -m web dlux_backfill_report_activity`
(add `--apply` to write). A plain `docker compose exec web python manage.py …` runs
the DjangoLux baked into the image, which lacks the command until the image is
rebuilt after an inline update. Models without a creation timestamp (`created_at`,
`created`, `created_on`, `date_created`, `timestamp`, or
`DLUX_CONFIG['reports']['backup_window_fields']`) are skipped.

## Backup and restore

Open **Options → Admin panel → Backup & Restore** for system backups. The policy,
the `.dlb` format and how restore works are in [Backups](backups.md). In short:

- A **full** `.dlb` backup holds restorable data and media; a **quick** one omits
  media. Turning **Include system data** off writes a *portable* backup of project
  data that keeps the target system's settings and logs when restored.
- Encryption is the server's `SECRET_KEY` (default), a one-off passphrase that is
  stored nowhere, or **None**. Passphrase-protected backups are never retried
  unattended, because DjangoLux does not keep the passphrase.
- After a full backup, *Type → Incremental* stores only what changed. A full backup
  and its increments form a chain that is restored, retained and deleted as a whole.
- Scheduling, retention, stall detection and automatic retries are set in the
  **System Backup** step of System Settings.

The backup history and the restore history are DluxTables (`SystemBackupTable`, ten
per page; `SystemRestoreTable`, five per page; `dlux/views/backup_tables.py`),
newest first, refreshed live on the page you are on. With sticky table headers on,
each history scrolls inside its own card and its header sticks to that card.

A backup row's actions — **Details**, **Download** (or **Download chain**),
**Restore**, **Retry**, **Cancel**, **Delete** — open from the shared row-action
trigger chosen in **System Settings → Layout → Table row actions** (right-click /
long-press, a three-dot column, or both), not from buttons in the row. Delete asks
for confirmation, and warns when later incremental backups of the chain will go
with it.

Only one backup runs at a time: while one is pending or running, the create form is
disabled with a note. A running or pending backup offers **Cancel** instead of
Delete; the run notices within a few seconds, discards what it built and is recorded
as *Cancelled* (it can be retried). **Details** shows the run's timestamped progress
log, elapsed time and, while running, the estimated time remaining. Finished rows
show how long they took instead of their last progress message.

Restore is project-local. Inspect a backup before restoring with the read-only
[DLB viewer](../tools/dlb-viewer/README.md). Inline-update rollback changes code and
static assets only; it never reverses database migrations or restores a database
backup automatically.

## Assets and optional features

The Asset Manager stores validated reusable images, WOFF2 fonts, and protected
installer files. Referenced assets cannot be deleted. See
[Managed Assets](managed-assets.md) for upload and storage policy.

ScanLink is disabled until enabled from **Extra Features**. This is intentional: its
browser helper probes a local workstation service, which would otherwise produce
refused-connection noise for every user without the tray application.

## Deployment operations

Operations is available to superusers from the admin command rail even when inline
DjangoLux updates are disabled, including Composer development mode. The panel uses
the resident Composer agent's availability; each action retains its backend
permission, password, version and runtime checks. Without a detected agent the
panel explains why operations cannot run.

From **Operations** a superuser can:

- run the deployment check and apply its repairs;
- list services, restart or recreate allow-listed ones, and read a service's recent
  logs (Composer 1.7.0 or later);
- **Start** and **Stop** auxiliary services (Composer 1.8.0 or later).

Use [Deployment Doctor](doctor.md) before and after infrastructure changes. For
generated Compose stacks, use `composer check` to report missing or drifted Composer
services, and `composer check --fix` only after reviewing its planned changes.
[Verified Inline Updates](inline-updater.md) documents the release handoff and
recovery boundaries.

Start and Stop apply to services approved by `COMPOSER_AGENT_RESTART_SERVICES`. Both
require a superuser, a CSRF-protected POST, the current password and an audit event.
Composer and its executor independently enforce the allowlist, protected labels and
current state. `web`, `worker`, a project's own `celery` and beat services, the
standard proxy names, data stores and Composer services remain protected so a later
Start stays reachable. Restart and
Recreate keep their own permissions.

Start operates on an existing stopped/created container without recreation; use
Recreate for absent services. Stop keeps containers and volumes. Controls follow the
reported state and refresh after completion; a Composer too old for them disables
them.

Opening Operations only reads its saved results: it starts no deployment check or
service refresh. Use Run deployment check or Refresh the service list explicitly. An operation that is already running is resumed: the live status area
names it, with accessible progress feedback, while controls are disabled, including
when the panel is reopened during the run. Explicit service lifecycle actions
refresh their result afterward. A failed status load is shown as an error.
