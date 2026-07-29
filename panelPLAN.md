# Extend the Existing DjangoLux Control Panel into Full Fleet Management

## 1. Existing foundation and outcome

Extend `project-dlux-panel` in place. Preserve and build upon its existing:

- `ManagedProject`, `ComposerAgent`, `FleetOperation`, `OperationEvent`, `FleetBatch`, `ProjectSnapshot`, and `BreakGlassAudit` models.
- Protocol-v1 enrollment, command polling, events, snapshots, local operations, capability reporting, rotation, and revocation.
- Scoped permissions and project filtering.
- Existing fleet dashboard, action modals, updates, backups, restarts, recovery deployment, batches, and operation history.

Do not replace its DjangoLux foundation, current fleet APIs, dashboard, or operation lifecycle.

The completed extension adds:

- A dedicated workspace route for every existing `ManagedProject`.
- Remote System Settings.
- Health history and diagnostics.
- Rich inventory.
- Durable alerts with email.
- Configuration profiles and reviewed drift reconciliation.
- A unified audit timeline.

Existing dashboard rows and modals remain as fleet-level quick actions and link into the new workspace.

## 2. Extend the existing protocol and security boundary

### Backward-compatible capabilities

Keep the current `/api/agent/v1/` transport and operation lifecycle. Add versioned contracts instead of replacing protocol v1:

- Snapshot contract v2.
- Settings contract v1.
- Diagnostic contract v1.
- Operation-artifact contract v1.

Add these actions to the existing action registry:

- `dlux.settings.read`
- `dlux.settings.validate`
- `dlux.settings.apply`
- `dlux.doctor.run`

DjangoLux publishes a bridge capability manifest. Composer advertises only the intersection of:

1. Operations supported by its installed code.
2. Operations published by the target DjangoLux bridge.
3. Contracts accepted by the panel.

The panel enables buttons and forms only when the connected agent advertises the exact capability. Existing agents continue using snapshot v1 and today’s actions unchanged.

When a control is disabled for a missing capability, the panel must surface **why** — which layer (agent, target bridge, or panel contract) is behind, and the version that would unlock it — rather than showing a dead button.

### Protocol discovery and artifacts

Add an authenticated panel protocol-discovery endpoint, checked by Composer at startup and periodically.

Keep commands and operation events below the existing 64 KiB limit. Add operation artifacts for larger typed results:

- Bound to an existing `FleetOperation`.
- Idempotent chunk upload and replay.
- 48 KiB maximum per chunk, 32 chunks maximum.
- Full-document SHA-256 verification.
- JSON validation, redaction, and permission-gated display.
- Operation events contain only status, summary, and artifact reference.

Use artifacts for settings descriptions, normalized diffs, and doctor reports.

### Composer security gate

This executor rewrite is the highest-risk single change in the plan: it touches the most safety-critical path (container recreation, update, recovery). Ship and canary it as its own standalone Composer hardening release, **decoupled from the remote-settings feature** and ahead of it, so a regression here cannot be forced by settings-work timelines and can be rolled back independently.

Before enabling new remote mutations:

- Replace the agent’s broad POST-enabled Docker proxy access with a purpose-built local executor exposing only typed update, restart, and recovery operations over a private Unix socket.
- Reject arbitrary Docker requests, shell commands, container definitions, mounts, services, and images.
- Require verified release metadata or immutable image digests.
- Make bridge files symlink-safe with private unique temporary files, no-follow reads, restrictive permissions, size/count limits, and atomic replacement.
- Bound command, event, result, snapshot, and artifact queues.

Remote settings and diagnostics themselves continue through the DjangoLux shared bridge and do not require Docker authority.

### Unified target mutation admission

Add one DjangoLux mutation-admission service used by:

- Inline apply and rollback.
- Image update.
- Remote settings apply.
- Restore/recovery mutations.
- Future target mutations.

Use a singleton leased row acquired through `select_for_update`. Store operation type, owner ID, acquisition time, expiry, and terminal state.

Remote reads, validation, snapshots, and doctor runs do not acquire a mutation lease. Settings apply rejects an active update, rollback, restore, maintenance transition, or another apply. This prevents panel, local-admin, and updater operations from racing.

Every mutation is idempotent by its originating operation or change-request ID: a replayed apply — lost acknowledgement, agent restart, panel outage — is a provable no-op rather than a second write. Recovery must never depend on the next snapshot to answer "did it actually apply?".

## 3. Extend the panel’s UI and fleet data

### Dedicated project workspace

Add a full route for each existing `ManagedProject`, preserving the current dashboard:

- **Overview**: current state, incidents, releases, services, profile assignment, recent operations, and quick actions.
- **System Settings**: target-published sections, current values, editing, validation, diff, approval, and apply progress.
- **Health**: component state, 30-day charts, thresholds, alerts, and diagnostics.
- **Updates**: existing update controls plus baked/running/available releases and image digest.
- **Backups**: existing backup actions, history, freshness, and remotely manageable policy.
- **Operations & Audit**: existing operations combined with settings, alerts, approvals, enrollment, and diagnostics.
- **Agent & Connection**: capabilities, versions, last contact, enrollment, rotation, revocation, and troubleshooting.

The existing fleet table and modals remain available for quick actions. They should link to the corresponding workspace tab for deeper management.

Add fleet-wide pages for:

- Health.
- Inventory.
- Alerts.
- Configuration Profiles.
- Central Audit.

Use DjangoLux-native controls, permission handling, dynamic feedback, bilingual English/Arabic presentation, RTL, responsive layouts, and keyboard accessibility.

### Panel-native System Settings

Do not iframe or remotely render the target’s `SystemSettingsForm`.

When a category is opened, the panel queues `dlux.settings.read`. The target returns:

- Stable section ID and order.
- Translated label and help text.
- Sanitized current values.
- Field types and widgets.
- Constraints and target-provided choices.
- Cross-field and cross-section dependencies.
- Visibility conditions.
- `read`, `write`, or `local_only` access.
- `ordinary` or `sensitive` risk.
- Global and section revisions.

The panel consumes the target-published section catalog rather than hard-coding the current 13 sections. Project-specific sections appear only when the project explicitly publishes a compatible schema.

Secrets are never returned. File fields and secrets may expose only a safe configured/not-configured state.

### Settings mutation flow

Add durable `SettingsChangeRequest` and `SettingsApproval` records linked to existing `FleetOperation` rows.

The workflow is:

1. Load the latest target schema and revision.
2. Edit a field patch, never a complete settings payload.
3. Queue `dlux.settings.validate`.
4. Display the target-normalized before/after diff and warnings.
5. Confirm or collect a second approval according to risk.
6. Queue `dlux.settings.apply` with a five-minute deadline.
7. Target locks, revalidates, saves atomically, audits, refreshes caches, and publishes a fresh snapshot.
8. Panel refreshes the section and closes or reports the change request.

The preview hash is computed **only** on the target, never on the panel — the panel stores and echoes it but never derives it, so a panel-versus-target normalizer difference can never make a change look valid. Validation returns the hash; apply recomputes it target-side and rejects changed normalization, stale revisions, unsupported fields, or expired approval. Because the target may inline-update itself between validate and apply, a change in the target's DjangoLux version in that window invalidates the approval exactly like a capability change.

Ordinary changes require preview and requester confirmation. Sensitive or fleet-wide changes require a second authorized user in the same scope. Requesters cannot approve their own changes. Approval expires after 24 hours and becomes invalid after any patch, revision, schema, preview, capability, or target-version change.

Third-phase security-relevant applies (auth enforcement, logging/retention, public-root and registration behavior) additionally require the approver to **re-authenticate (step-up)**, not merely to be a second user, and are recorded against `BreakGlassAudit`.

### Writable settings rollout

Initial ordinary writable fields:

- English and Arabic system names.
- Default and allowed themes.
- Theme override policy.
- Default and allowed fonts.
- Font override policy.
- Table, form, modal, Options-page, and row-actions presentation settings.

Second phase:

- Non-file identity metadata.
- Localization.
- Login presentation.
- Titlebar.
- Sidebar.
- Nav Bar.
- Notifications.
- Backup scheduling and retention policy.

Third phase, always requiring dual approval:

- Non-secret access and authentication enforcement.
- Public-root and registration behavior.
- Audit-field and soft-deleted visibility.
- Security-relevant logging and retention.

Remain local-only:

- SMTP and encrypted credentials.
- Passwords, tokens, API keys, and signing keys.
- Logo, favicon, hero, and other uploads.
- Backup restore.
- Destructive recovery controls.
- Arbitrary `extra_config`.
- Unregistered project-specific settings.

### Target-side settings authority

Extend DjangoLux’s canonical settings registry with remote metadata:

- Stable key.
- UI section.
- field type/widget.
- constraints.
- choices provider.
- dependency conditions.
- remote access.
- risk tier.
- sanitization policy.

Use the same metadata for local section placement and remote descriptions so the local and panel experiences cannot diverge.

`dlux.settings.validate` runs the target version’s normalizers without saving.

`dlux.settings.apply`:

1. Acquires mutation admission.
2. Locks `SystemSettings`.
3. Verifies revisions.
4. Revalidates the patch.
5. Verifies the preview hash and writable-field whitelist.
6. Saves only touched columns or JSON groups.
7. Writes a mandatory DjangoLux audit record.
8. Refreshes caches and publishes a snapshot after commit.

Omitted values, unknown keys, files, secrets, encrypted values, and unrelated JSON keys remain unchanged. The full import/export apply function must not be exposed remotely.

### Profiles and drift

Add immutable configuration-profile versions with:

- Environment/project classification.
- Desired stable settings values.
- Monitoring thresholds.
- Supported settings schema range.
- Risk summary and publisher.

Assign a profile version to projects. Allow documented field exceptions with reason, approver, and optional expiry.

Snapshot v2 sends section revisions and normalized field fingerprints, not complete settings values. The panel classifies each field as:

- Matching.
- Drifted.
- Exempt.
- Unsupported.
- Unknown.

Drift opens an alert and offers a reviewed reconciliation change. It never auto-applies. Multi-project reconciliation uses the panel’s existing maximum batch concurrency of three and requires a second approver.

## 4. Health, diagnostics, inventory, alerts, and audit

### Extend `ProjectSnapshot`

Preserve snapshot v1 ingestion and add snapshot v2 fields for:

- Project identity and environment.
- Application version.
- DjangoLux version.
- Composer deployer and resident-agent versions.
- Django and Python versions.
- Database engine/version.
- Redis version.
- Running versus baked release.
- Image digest.
- Database, Redis/cache, Celery, web, worker, scheduler, proxy, maintenance, and degraded state.
- CPU, memory, and disk utilization.
- Backup freshness and policy.
- Update availability.
- Settings revisions and fingerprints.
- Capability contract versions.

Correct the current persistence gap by storing the sanitized snapshot project identity instead of discarding that block.

Keep the latest snapshot and add five-minute metric rollups retained for 30 days.

### Diagnostics

Implement `dlux.doctor.run` through the existing DjangoLux doctor registry:

- Run in-process through fixed typed groups.
- Preserve the existing JSON schema version.
- No caller-provided command.
- No `--apply`.
- No stateful or source fixes.
- Sanitize in DjangoLux, Composer, and the panel.
- Store reports for 90 days.
- Link recurring findings to alerts and the project audit timeline.

### Durable alert engine

Add alert records with:

- Project and scope.
- Type and severity.
- Stable deduplication fingerprint.
- First and last observation.
- Evidence summary.
- Open, acknowledged, muted, and resolved states.
- Notification state.
- Linked snapshot, diagnostic report, or operation.

Default rules:

- Agent offline after 90 seconds.
- Snapshot stale after three minutes.
- Disk warning at 80%, critical at 90%.
- Memory warning at 85%, critical at 95% when sustained for ten minutes.
- CPU warning at 90% when sustained for 15 minutes.
- Database, Redis, Celery, or degraded runtime failure: immediate critical.
- Backup overdue after its configured interval plus 25% grace.
- Update available: informational.
- Settings drift: warning, elevated for sensitive fields.
- Unexpected agent revocation: critical.

Thresholds are profile-overridable. Expected maintenance suppresses only related availability noise and receives a ten-minute completion grace period. An observed local settings-revision bump also opens a short drift-suppression window, so a local admin editing between snapshots does not raise transient false drift alerts.

Show alerts in the panel and send deduplicated emails to configured operator groups when an alert opens or escalates. Emails contain a summary and panel link, never raw diagnostics or settings diffs.

### Unified audit timeline

Preserve `FleetOperation`, `OperationEvent`, and `BreakGlassAudit`. Add append-only `FleetAuditEvent` records to normalize:

- Settings validation and application.
- Approvals and rejections.
- Profile publication, assignment, exceptions, and reconciliation.
- Updates, backups, restarts, and recovery.
- Enrollment, credential rotation, and revocation.
- Diagnostics.
- Alert creation, acknowledgement, escalation, and resolution.

Record project, scope, actor, source IP where known, operation/change IDs, timestamps, result, and redacted structured diff.

Retain:

- Metric rollups: 30 days.
- Diagnostic reports: 90 days.
- Existing operation logs: 90 days.
- Audit, approvals, settings changes, and alert events: 365 days by default.
- Referenced immutable profile versions indefinitely.

At fleet scale these volumes grow materially (five-minute rollups × 30 days × project count, 90-day diagnostics, 365-day audit). Plan table partitioning and progressive down-sampling of older rollups from the start rather than retrofitting them under load.

## 5. Implementation and rollout sequence

### Milestone 1: secure and negotiate the existing platform

Across the current panel, Composer, and DjangoLux:

- Publish one canonical contract specification and matching golden fixtures, wired as a **failing contract-drift test in every repo** — not documentation. The settings schema is represented in several places (canonical registry, published section catalog, snapshot fingerprints, profile supported-range); drift between any of them must break CI, not surface in production.
- Add protocol discovery and capability intersection.
- Implement artifact transport.
- Harden Composer Docker authority and shared-volume handling.
- Add DjangoLux mutation admission.
- Add panel snapshot v1/v2 compatibility.
- Keep all new UI disabled until matching capabilities are observed.

### Milestone 2: extend observability

In the existing panel:

- Add project workspace routes and tabs.
- Keep dashboard quick actions intact.
- Extend snapshot persistence.
- Add metrics, inventory, health, diagnostics, alerts, email, and audit.
- Deliver read-only fleet visibility before remote settings mutation.

### Milestone 3: remote settings foundation

- Extend the DjangoLux settings registry.
- Implement target read, validate, apply, revisions, audit, and cache refresh.
- Extend Composer bridge processing and artifact relay.
- Add panel-native schema forms and change requests.
- Enable only the initial ordinary writable fields.
- Publish the complete sanitized section catalog with unsupported/local-only states.

### Milestone 4: profiles and expansion

This milestone carries the highest complexity-to-value ratio and is the designated **scope cut line**: everything through Milestone 3 (fleet observability plus governed ordinary-field remote settings) is independently shippable, so profiles and drift can follow once remote settings prove out in production.

- Add profile versions, assignments, exceptions, fingerprints, and drift.
- Add reviewed single-project and batch reconciliation.
- Enable second-phase settings.
- Add dual approval and then enable approved third-phase fields.
- Finish global fleet dashboards, filters, search, Arabic/RTL, accessibility, and responsive polish.

### Release train

Use new minor releases because the current versions are already tagged:

- DjangoLux `v1.6.0`.
- Existing Control Panel `v0.3.0`.
- Composer `v1.3.0`.

Deploy in this order:

1. Panel v0.3.0, accepting old and new contracts.
2. DjangoLux v1.6.0, publishing its capabilities.
3. Composer v1.3.0, advertising the negotiated intersection.
4. Non-production observability canary.
5. Settings read and validate canary.
6. One ordinary theme apply and reversal.
7. Low-risk production canary.
8. Wider settings/profile enablement after the canary passes.

Rolling back DjangoLux or Composer withdraws unsupported capabilities automatically. Existing panel operations remain available.

## 6. Verification and acceptance

DjangoLux tests:

- Remote schema completeness and translation-independent stable keys.
- Secret and file-value omission.
- Target/local normalization parity.
- Validation without database writes.
- Patch preservation of omitted fields and JSON keys.
- Exact diff and preview-hash stability.
- Stale revisions, local edit races, duplicate apply, admission conflicts, rollback, audit, cache refresh, and snapshot publication.
- Read-only doctor enforcement and sanitization.

Composer tests:

- Every old/new capability combination.
- Agent restart and panel-outage replay.
- Artifact deduplication, ordering, corruption, hashing, limits, and recovery.
- Symlink, path traversal, oversized files, queue exhaustion, credential redaction, redirect, and revocation.
- Executor rejection of arbitrary Docker actions and mutable/unverified releases.

Panel tests:

- Existing update, backup, restart, recovery, enrollment, rotation, batch, and snapshot behavior remains passing.
- Scoped workspace and artifact permissions.
- Ordinary confirmation and sensitive dual approval.
- Self-approval rejection, expiry, stale-preview invalidation, and offline deadlines.
- Snapshot v1/v2 ingestion and rollups.
- Alert detection, deduplication, suppression, acknowledgement, resolution, and email failure isolation.
- Profile drift, exceptions, unsupported fields, reconciliation, and no auto-remediation.
- English/Arabic, RTL, keyboard, mobile, stale, loading, unsupported, and validation-error states.

End-to-end tests:

- Existing panel → Composer → DjangoLux read/validate/apply.
- Local target edit between validation and apply.
- Update versus settings-apply concurrency.
- Composer restart during every phase.
- Panel outage and durable replay.
- Revocation during an operation.
- Corrupted and incomplete artifact uploads.
- Old-target/new-agent/new-panel compatibility.
- Health and alert lifecycles for database, Redis, Celery, disk, memory, backup, update, drift, degradation, and revocation.
- Live DjangoLux `v1.5.10 → v1.6.0` inline apply and rollback, confirming the existing panel reconnects, capabilities recover, settings remain intact, and audit/snapshots continue.

Update each repository’s protocol, security, operations, settings-extension, deployment, permissions, environment-variable, and troubleshooting documentation, plus its changelog and tracker under the existing repository rules.

## 7. Key risks, mitigations, and scope guidance

Ranked by exposure, each with where it is addressed:

1. **The Composer executor rewrite gates the most safety-critical path.** A regression breaks the fleet's update/recovery path, not just the new features. *Mitigation:* ship it as an independent, separately-canaried Composer hardening release, decoupled from and ahead of the settings feature (§2.3).
2. **The settings schema is represented in four places** — canonical registry, published section catalog, snapshot fingerprints, and profile supported-range — that must stay consistent across version skew. This is the most likely real-world break point. *Mitigation:* the contract spec + golden fixtures are a failing CI test in every repo, not documentation (§5, Milestone 1).
3. **Preview-hash / normalization parity across a self-updating target.** *Mitigation:* the hash is computed target-side only, and a target-version change between validate and apply invalidates the approval (§3, Settings mutation flow).
4. **Settings-apply idempotency.** *Mitigation:* every apply is idempotent by change-request ID; a replay is a no-op and recovery never depends on the next snapshot (§2.4).
5. **Alert noise from local edits between snapshots.** *Mitigation:* a local settings-revision bump opens a short drift-suppression window (§4, Durable alert engine).
6. **Retention storage growth at fleet scale.** *Mitigation:* partition and progressively down-sample from the start (§4, Unified audit timeline).
7. **Operator friction of dual approval.** Acceptable because ordinary fields — the bulk of the rollout — need only single confirmation; third-phase adds step-up re-authentication rather than more approvers (§3).

Sequencing guidance:

- Everything through Milestone 3 (observability plus governed ordinary-field remote settings) is independently shippable and is the primary deliverable.
- Milestone 4 (profiles and drift) is the designated scope cut line if timelines tighten.
- The Composer executor hardening in Milestone 1 should ship and canary on its own track, ahead of and independent from the remote-settings work.
- Do not write remote-mutation feature code until two gates are met: the contract spec + golden fixtures exist as a tested artifact, and the Composer executor hardening has canaried in a non-production environment.
