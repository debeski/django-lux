# DjangoLux Documentation

The [package README](../README.md) is the landing page. This folder is the manual: it
describes how DjangoLux works now. Release history is in the
[changelog](../CHANGELOG.md), and [Features](FEATURES.md) is the one-page capability
map.

## Start here

- [Getting Started](getting-started.md): install, configure Django, generate a
  project and launch it.
- [Features](FEATURES.md): what DjangoLux provides, with links to each topic.
- [Migrating from microsys](migrating-from-microsys.md): moving a project off the
  predecessor package.

## Running a deployment

- [System Configuration](system-configuration.md): the 19-step setup wizard at
  `/sys/setup/`, System Settings and the Options view at `/sys/options/`.
- [Operations](operations.md): users, staff tiers, permissions, activity logs,
  reports, data reset and the Operations panel.
- [Backups](backups.md): full, data-only, portable and incremental backups,
  schedules, retention and restore.
- [Managed Assets](managed-assets.md): uploaded images, fonts and installer files.
- [Task Runner](task-runner.md): `dlux_worker`, the database task queue that runs
  DjangoLux's background work, schedules, retries and recovery, and moving project
  tasks from Celery.
- [Data & Privacy](data-privacy.md): the personal data DjangoLux stores, retention,
  and the privacy and consent controls.
- [Public Registration](registration.md): the disabled-by-default, email-verified
  signup.
- [Optional SSO Packages](sso.md): the OIDC provider plugin and client SDK.
- [Deployment Configuration](deployment-configuration.md): every accepted `DLUX_*`
  setting and environment variable, with types, defaults and precedence.
- [Verified Inline Updater](inline-updater.md): how Composer updates, verifies,
  activates and rolls back a generated deployment.
- [Composer Agent Integration](composer-agent.md): what DjangoLux and the Composer
  agent each own.
- [Deployment Doctor](doctor.md): diagnosing a deployment, the JSON report and the
  repair tiers.
- [Stack Schema Stamps](stack-schema.md): the contract schema generated stack files
  carry.
- [Outbound Requests](outbound-requests.md): only `composer-agent` reaches the
  internet; how a project asks for an outbound call.
- [ScanLink](scanlink.md): installing and troubleshooting the workstation scanning
  helper.
- [OCR](ocr.md): the optional `ocr` service, its settings and resource limits.

Rules for operators:

- Interface visibility never replaces backend authorization. Changes are POST-only,
  and security-sensitive ones also ask for the current password.
- Take a full backup before a data reset or a restore.
- Run `composer check` before changing a generated Compose stack.
- Configure the proxy and client-IP policy before relying on lockout, rate limits or
  activity-log attribution.

## Building on DjangoLux

- [Developer Guide](developer-guide.md): the mental model, configuration layers,
  scoped models, discovery and which subsystem to use when.
- [Project Configuration](project-configuration.md): `DLUX_CONFIG`, custom themes
  and fonts, and integration settings.
- [UI Integration](ui-integration.md): sections, modals, tables, filters, downloads,
  activity logging, app-owned settings, global search and dialogs.
- [Table Columns](table-columns.md): administrator and personal column layouts.
- [Ribbon](ribbon.md): the list-page band carrying a page's title, filters and
  actions.
- [Template Customization](template-customization.md): extension partials, page
  bases, form footers and assisted entry.
- [Translations](translation-guide.md): `DLUX_STRINGS`, overrides and RTL checks.
- [Document Files](document-files.md): `register_document_file()`, the file card,
  viewer, page editor and file history.
- [PDF Toolkit](pdf-toolkit.md): the optional `pdf` extra.
- [Entry Clipboard](entry-clipboard.md): reusable text snippets in entry forms.
- [Weather](weather.md): the optional weather widget and card.

Rules for extensions:

- Use the Dlux primitives before writing a local equivalent: `DluxFileInput` and
  `AssetPickerField`, choice widgets, the icon picker, toggle builders, `DluxTable`,
  dynamic-modal responses and loading buttons already handle themes, RTL,
  accessibility and lifecycle.
- Keep UI visibility and backend authorization in step.
- Dynamic-modal endpoints return `JsonResponse({"html": ...})`.
- No raw HTML in translated or form-help strings.

## Reference and policy

- [Reference](reference.md): management commands, routes, template tags, helpers
  and configuration keys.
- [DSRP-1 Security Standard](security-dsrp-1.md): the backend authorization and
  security-flow policy, and the no-inline asset rule.
- [Deprecation Countdown](deprecation-countdown.md): removed and deprecated APIs with
  their removal targets.
- [Adding a System Setting](adding-system-settings.md): the procedure for framework
  contributors.
- [Releasing](RELEASING.md): versioning, betas, release gates and the changelog.
- [Security Policy](../SECURITY.md), [Contributing](../CONTRIBUTING.md) and
  [Code of Conduct](../CODE_OF_CONDUCT.md).
