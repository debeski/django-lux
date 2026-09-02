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

The User Report is available to authorized staff from the user directory. It combines account/security facts, activity, known devices, and IP observations; the modal can be printed through the browser or exported as XLSX.

General Reports use business activity (`ActivityLog.category = "user"`) rather than framework infrastructure events. They support the selected period and model or operation filters, a printable analytical view, XLSX record export, and a ZIP containing the workbook plus eligible media. Models can opt out with `dlux_report = False` or `DLUX_CONFIG['reports']['exclude_models']`.

## Backup and restore

Open **Options → Admin panel → Backup & Restore** for system backups. A full `.dlb` backup contains restorable data and media; a quick/data-only backup omits media. Backups expose progress, heartbeat, retry state, retention, and explicit failure information. Passphrase-protected backups are never retried unattended because DjangoLux does not retain the passphrase.

Restore is project-local. Inspect a backup before restoring with the read-only [DLB viewer](../tools/dlb-viewer/README.md). Inline-update rollback changes code and static assets only; it never reverses database migrations or restores a database backup automatically.

## Assets and optional features

The Asset Manager stores validated reusable images, WOFF2 fonts, and protected installer files. Referenced assets cannot be deleted. See [Managed Assets](managed-assets.md) for upload and storage policy.

ScanLink is disabled until enabled from **Extra Features**. This is intentional: its browser helper probes a local workstation service, which would otherwise produce refused-connection noise for every user without the tray application.

## Deployment operations

Use [Deployment Doctor](doctor.md) before and after infrastructure changes. For generated Compose stacks, use `composer check` to report missing or drifted Composer services, and `composer check --fix` only after reviewing its planned changes. [Verified Inline Updates](inline-updater.md) documents the release handoff and recovery boundaries.
