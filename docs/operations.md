# Operations

This guide covers routine administration after system configuration. Use [System Configuration](system-configuration.md) for the wizard and Options settings, and [Deployment Configuration](deployment-configuration.md) for environment-owned settings.

## Users, staff, and permissions

User management is available at `/sys/users/`. Staff access is governed by the same backend permissions that control its UI: visibility is never authorization. Use groups/presets for repeatable permission bundles and scopes when access must be limited to an organizational subset of records.

The relevant tiers are:

- **Superuser** — framework-wide administration, including security-sensitive configuration and update approval.
- **Global staff** — staff access across scopes, limited by assigned permissions.
- **Scoped staff** — staff access constrained to the user's active scope.

Public-registration defaults are selected in Manage Scopes and Manage Groups, not by editing a System Settings field. Mark one landing scope and any applicable group presets; DjangoLux applies them after registration activation.

## Account security in daily use

Users can configure TOTP, recover backup codes, manage trusted devices, and end recorded sessions from Profile. Trusted sessions take precedence over untrusted sessions. When single-session enforcement is enabled, a successful login or completed 2FA login ends the user's other sessions. Otherwise, password change can optionally end other signed-in devices while retaining the current browser.

Administrators can use the Admin panel command rail for bulk forced password change and destructive data reset. Both require the current password; reset data excludes System Settings, updater state, permission groups, superusers, and any model whose rows are only a line of another record (an invoice's items go with the invoice). Take a full system backup before using data reset.

Reset data runs in one of two modes. **Soft** — the default — soft-deletes `ScopedModel` subclasses so they stay recoverable, and hard-deletes everything else. **Permanent** hard-deletes every selected model and empties those models' recycle bins as well, so rows soft-deleted by any earlier action go too; it requires the confirmation word typed into the dialog on top of the password, and there is no undo. Use it only to start a system over.

Bulk writes run no `save()` or `delete()`, so a figure a project derives in those methods — a stock balance, a cached total — is stale once the rows behind it are cleared. A project repairs its own by connecting to `dlux.admin_actions.data_reset.data_reset_finished`.

## Activity logs and reports

`/sys/logs/` is an operational audit surface. It records configured CRUD events, login/logout, merged User/Profile changes, masked sensitive values, and download/export activity. Scope-aware staff see only the activity they are authorized to inspect.

The User Report is available to authorized staff from the user directory. It combines account/security facts, activity, known devices, and IP observations; the modal can be printed through the browser or exported as XLSX. From **General Reports**, a staff user with the reports permission (but not user-directory and activity-log access) opens an *activity* version for the users that page lists: account basics plus that user's creates, edits and deletes per model and their recent actions, counted within the viewer's report scope, without devices, addresses, sessions or e-mail; its XLSX has no network columns.

General Reports use business activity (`ActivityLog.category = "user"`) rather than framework infrastructure events. They support the selected period and model or operation filters, a printable analytical view, XLSX record export, and a ZIP containing the workbook plus eligible media. Models can opt out with `dlux_report = False` or `DLUX_CONFIG['reports']['exclude_models']`.

## Backup and restore

Open **Options → Admin panel → Backup & Restore** for system backups. A full `.dlb` backup contains restorable data and media; a quick/data-only backup omits media. Backups expose progress, heartbeat, retry state, retention, and explicit failure information. Passphrase-protected backups are never retried unattended because DjangoLux does not retain the passphrase.

Each backup chooses:

- **Encryption** — the server's Django `SECRET_KEY` (default), a one-off passphrase (entered twice, cleared from the form as soon as the backup starts, stored nowhere), or **None**. An unencrypted file exposes regular-user password hashes and all data to whoever holds it; the page warns before you choose it.
- **Scope** — full (data + media) or quick (data only).
- **Include system data** — on by default. Off produces a *portable* backup of project data only: users, groups, scopes, group access and managed assets are kept, while Dlux's own settings, notifications, activity log, preferences, devices and update runs are left out. Restoring a portable backup replaces only the tables it carries and keeps the target system's settings and logs; rows of those that point at users the backup does not contain are cleared (nullable links) or removed.

The backup history and the restore history are DluxTables (`SystemBackupTable`, ten per page; `SystemRestoreTable`, five per page; `dlux/views/backup_tables.py`), newest first, refreshed live on the page you are on. A backup row's actions — **Details**, **Download** (or **Download chain**), **Restore**, **Retry**, **Cancel**, **Delete** — open from the shared row-action trigger chosen in **System Settings → Layout → Table row actions** (right-click / long-press, a three-dot column, or both), not from buttons in the row. Delete asks for confirmation, and warns when later incremental backups of the chain will go with it. With sticky table headers on, each history scrolls inside its own card and its header sticks to that card.

Only one backup runs at a time: while one is pending or running, the create form is disabled with a note, and the server refuses a second (HTTP 409). A running or pending backup offers **Cancel** instead of Delete; the run notices within a few seconds, discards what it built and is recorded as *Cancelled* (it can be retried). Every row has a **Details** console with the run's timestamped progress log, elapsed time and, while running, the estimated time remaining. Finished rows show how long they took instead of their last progress message, and the create form estimates a new backup's duration from the last three of the same scope.

**Incremental backups.** After a full backup, choose *Type → Incremental* to store only what changed since the previous backup: changed and new rows, the keys of deleted rows, and new media files. A full backup and its increments form a *chain*; restoring an increment restores the whole chain up to that point in one transaction, and checks first that every member is present and belongs to it. Increments use the chain's scope and encryption (a passphrase chain needs the same passphrase each time). A chain closes, and the next backup must be full, when its full backup is older than **New full backup every (days)**, after **Increments per chain** increments, or when a migration changed the schema. Turn on **Incremental scheduled backups** in the backup settings to make scheduled runs incremental. Retention keeps or removes chains as a whole; deleting a member also deletes the later ones; an increment downloads as a ZIP of its chain.

On PostgreSQL a backup reads the whole database inside one read-only `REPEATABLE READ` transaction, so the archive is a single point-in-time snapshot while the site keeps writing (other engines read model by model; the manifest records `consistency: snapshot|live`). Records are serialized with natural-key lookups cached per run and related rows joined or prefetched in pages of 1,000, and the archive is encrypted by a background thread while it is written — there is no separate encryption pass. Already-compressed media (images, PDFs, archives, office files) is stored, not re-deflated.

Restore is project-local. Inspect a backup before restoring with the read-only [DLB viewer](../tools/dlb-viewer/README.md). Inline-update rollback changes code and static assets only; it never reverses database migrations or restores a database backup automatically.

## Assets and optional features

The Asset Manager stores validated reusable images, WOFF2 fonts, and protected installer files. Referenced assets cannot be deleted. See [Managed Assets](managed-assets.md) for upload and storage policy.

ScanLink is disabled until enabled from **Extra Features**. This is intentional: its browser helper probes a local workstation service, which would otherwise produce refused-connection noise for every user without the tray application.

## Deployment operations

1.14.0b3 adds **Start** and **Stop** for auxiliary services approved by `COMPOSER_AGENT_RESTART_SERVICES` (paired Composer 1.8.0b1+, also the release manifest's floor). Both require a superuser, CSRF-protected POST, current password and audit event. Composer and its executor independently enforce the allowlist, protected labels and current state. Web/Celery, standard worker/beat/proxy names, data stores and Composer services remain protected so a later Start stays reachable. Existing Restart/Recreate permissions are unchanged.

Start operates on an existing stopped/created container without recreation; use Recreate for absent services. Stop keeps containers and volumes. Controls follow the reported state and refresh after completion; old Composer versions disable them. Accept the paired beta before promotion.

In the app, superusers open **Operations** from the admin panel's actions rail to run the deployment check and apply its repairs, restart or recreate allow-listed services, and read a service's recent logs (Composer 1.7.0b2+). Use [Deployment Doctor](doctor.md) before and after infrastructure changes. For generated Compose stacks, use `composer check` to report missing or drifted Composer services, and `composer check --fix` only after reviewing its planned changes. [Verified Inline Updates](inline-updater.md) documents the release handoff and recovery boundaries.

### Published paired-beta acceptance — 2026-10-24

- DjangoLux [1.14.0b3](https://github.com/debeski/django-lux/releases/tag/v1.14.0b3) ships from main `cdd4f56` after owner merge of PR #8; all nine release jobs passed. Composer [1.8.0b1](https://github.com/debeski/composer/releases/tag/v1.8.0b1) ships from main `bb80d91`; all release jobs passed. Composer's `beta` alias matches b1 and `latest` remains 1.7.0. DjangoLux stable remains 1.13.2.
- DjangoLux: full 3,005 tests OK/six skips; release-focused 147 OK/two skips; chain22 and backup browser17 pass. CI passes on Python 3.11/3.12/3.13 and PostgreSQL. Earlier builder8/Operations16/previews12/setup4/weather2 acceptance remains valid. Composer: 861 OK/four skips, fresh candidate and published-image runtime smoke pass.
- The published PyPI wheel matches its PyPI SHA and all 676 candidate/source files. Both Web and Celery run those exact files after a real published b2 → b3 inline update on the beta channel, with pre-update backup `F189zQ6Y`. User and table/layout/ribbon state matches the full-backup snapshot taken before the final refresh. The published Composer image matches all 59 source payload files.
- The owner-requested isolated testbed on 8096 passes real full/incremental creation against a chosen older chain, inherited scope/encryption, context-menu Details opening and closing, and single-field search across all three section models in EN/AR at 1440/390px. Real password-confirmed SMTP Stop → exited → Start → running passes with Web/Celery/Caddy lifecycle protected; restart/recreate/update permissions remain unchanged. No page errors; SMTP is left healthy.
- Merged feature checkouts were retired with ignored evidence preserved. The active testbed moved to `main/.xclude/validation/service-controls/testbed/`; it uses `.secrets/.env`, a published b2 base image with inline-installed b3, and published Composer `v1.8.0b1`. Relocation was followed by another real service cycle and deep check: 23 OK, zero errors, one local DEBUG warning and three skips.
- Official testbed8088 remains stable1.13.2; published-b2 testbed8095 and older draft8094 were not changed. Evidence: `main/.xclude/validation/1.14.0b3-paired-2026-10-24/`; retired raw evidence under each repo's `main/.xclude/retired-worktrees/2026-10-24/`.
- Stable promotion still requires the planned Updates-card manifest/history work and acceptance of the final candidate. These beta tags do not promote stable.
