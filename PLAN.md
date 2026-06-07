# Microsys Supervisor Reports And Backup Plan

## Summary
Build this as a reusable `django-microsys` feature, not as a feature for any one host project. Add two staff/supervisor capabilities:

1. A weekly reporting overview that shows eligible entries for the current week, compares them with the previous week, shows all-time totals, groups work by user/model/action/day, and calculates daily averages.
2. A backup ZIP flow that lets the same authorized staff user export eligible data and related files without hardcoded project models.

Use the existing Microsys user report modal as the base: improve its activity filtering, keep its week/month/all tabs, and make XLSX export honor the selected tab/window.

## Key Changes
- Add a dynamic report-eligible model resolver:
  - Include models marked `is_section=True`.
  - Include host-project managed models discovered from Django apps, excluding Django/Microsys operational internals.
  - Resolve activity rows through `UserActivityLog.model_name`, `resolve_model_by_name()`, verbose names, model names, and `app_label.model_name` where possible.
  - Exclude irrelevant operational activity such as presence sessions, known devices, trusted devices, system settings, authentication/session events, setup/options, and other Microsys infrastructure models.
  - Allow host projects to optionally override include/exclude rules in `MICROSYS_CONFIG["reports"]`, but ship with safe dynamic defaults.

- Improve the existing per-user report:
  - Change `build_user_report()` to accept `actor`, `target_user`, and `window`.
  - Filter activity breakdowns and recent activity to report-eligible entries only.
  - Keep identity, device, network, and presence summary sections, but do not count those operational models as user "entries".
  - Update `/sys/users/<pk>/report.xlsx?window=week|month|all` so XLSX exports only the selected report window.

- Add a supervisor/staff reports overview:
  - New page: `/sys/reports/`.
  - New export: `/sys/reports/export.xlsx?window=week|month|all`.
  - Primary access point is the Microsys user hub staff toolbar, next to Manage Users and Activity Log, shown only when the user can access reports.
  - Options view will include a reports related system settings entry in the future for editing the reports settings, e.g. workdays, 9included/excluded models to calculate for, etc..
  - Show current-week total, previous-week total, delta, all-time total, average entries per active day, average entries per user, and breakdowns by user/model/action/day.
  - Provide drill-down links that open the existing per-user report modal for visible users.
  - Reuse Microsys translation, table/header, Excel, and filename helper patterns where available.

- Add backup ZIP support:
  - New route: `/sys/reports/backup.zip`.
  - ZIP contains a manifest, serialized eligible data, and files referenced by eligible model `FileField`/`ImageField` values.
  - Data discovery is model-based and dynamic; no project model names are embedded.
  - File paths inside the ZIP are normalized and collision-safe.
  - Backup generation logs a Microsys `EXPORT`/`DOWNLOAD` activity without exposing secrets in log details.

## Access Rules
- Add explicit permissions:
  - `microsys.view_reports` for supervisor reporting surfaces.
  - `microsys.download_backup` for backup ZIP downloads.
- Superusers always pass both checks.
- Staff users need the explicit permission for each feature.
- Scope filtering follows existing Microsys tier behavior:
  - Scoped staff see eligible logs/data/users in their scope.
  - Central staff see scopeless eligible logs/data/users.
  - Global staff and superusers see all eligible logs/data/users.
- Normal users keep existing self-report access only; they cannot access `/sys/reports/` or backup ZIPs.

## Implementation Notes
- Add a reporting module, likely `microsys/reports.py`, for reusable helpers:
  - Resolve eligible models and eligible activity model-name keys.
  - Build scoped activity querysets for report windows.
  - Build per-user and aggregate statistics.
  - Build selected-window XLSX exports.
  - Build backup manifests and ZIP payloads.
- Keep URL/view code thin in `microsys/views/users.py` or a new `microsys/views/reports.py`.
- Add templates under `microsys/templates/microsys/reports/` for the overview page while preserving the existing dynamic modal template for per-user details.
- Add a `can_view_reports` context value and render a Reports icon/link in `microsys/templates/microsys/users/user_hub.html`.
- Use local timezone boundaries for `week` and `month`; keep `all` unbounded.
- Define "entry" as eligible activity-log rows, not logins, presence/device tracking, settings changes, or authentication noise.

## Test Plan
- Per-user report:
  - Self-report still works for normal authenticated users.
  - Staff report access still respects existing target-user visibility.
  - Week/month/all counts exclude Microsys operational models and include dynamic eligible host/section models.
  - XLSX export only contains the selected window.

- Supervisor overview:
  - Normal users are denied.
  - Staff without `view_reports` are denied.
  - Staff with `view_reports` see current-week, previous-week, all-time, user/model/action/day, and averages.
  - Scoped, central, global, and superuser accounts each see only their allowed records.

- Backup ZIP:
  - Requires `download_backup`.
  - Includes eligible serialized data, referenced files, and a manifest.
  - Excludes out-of-scope data/files and operational/sensitive Microsys internals.
  - Handles missing files safely and records them in the manifest.

## Assumptions
- This is implemented in the Microsys package so every host project benefits.
- Host projects may configure reporting overrides, but no host project model names are hardcoded in Microsys.
- The existing report modal remains the per-user report UI; the new overview page is an additional supervisor/staff surface built on the same reporting logic.
