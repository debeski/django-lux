# Project Tracker (django-lux)

## Part 1: Project Related
### Current Verified Snapshot:
- `dlux/release-manifest.json` is the version source: unreleased rebuild-required v1.2.7; latest published tag is v1.2.6.
- v1.2.7 is a mandatory one-rebuild repair for the baked v1.2.4-v1.2.6 one-shot Celery health race.
- DjangoLux supplies settings/setup, scoped models, auth/security, navigation, reports, backup, scaffolding, SSO hooks, and the Compose updater.
- Updater state uses `DluxUpdateState`/`DluxUpdateRun` plus `dlux_runtime` releases, atomic pointer, generation, maintenance, heartbeat, and degraded markers.
- `switch_pos` is rolled back to active/baked v1.2.4 but degraded with maintenance retained after candidate and rollback Celery probes raced normal startup.

### Current Project Adopted Standards:
- Integrate settings with `from dlux.utils import dlux_settings`; call `dlux_settings(globals())`; mount `dlux.urls` at root.
- `dlux.system` owns settings defaults/schema/normalizers/registry; migration-history wrappers remain in `dlux.models`.
- DSRP-1 requires backend authorization to match UI visibility and security mutations to be POST-only.
- Authored runtime CSS/data/events/JS use the `dlux` prefix and external assets; user copy uses `DLUX_STRINGS`.
- Releases are tag-driven; package/version/release validation all read `dlux/release-manifest.json`.

### Adopted Standards' rules and policies:
- Maintain this tracker as verified project state, <=100 lines total; Part 1 <=55 lines.
- Root changelog sections are newest-first `## vX.Y.Z` with flat bold-title bullets; tagged sections are immutable.
- Never delete repository files; relocate obsolete/replaced material under `.xpose/` with relative-path preservation.
- Preserve unrelated user changes and use `apply_patch` for source/doc edits.
- Feature/config/schema/API/security/deployment changes require same-turn technical documentation.

### Cross-Cutting Audits if any:
- 2026-06-23: Documentation audit covered 24 Markdown files and generated README templates.
- 2026-06-23: Updater audit covered artifacts, attestation, dependency/migration gates, supervisor/runtime state, recovery, UI/API, scaffold, nginx, and Compose.
- 2026-06-24: ScanLink has no PDF byte/page cap; generated-project nginx imposes an effective `5M` form-upload ceiling.

### Current Project's Unsolved Known Bugs:
- Fallback file/download redirects remain a high-risk-deployment review point; `_safe_referer()` currently enforces allowed hosts.
- Mounted test Compose uses Redis sessions; never use live `cache.clear()` probes because they delete browser sessions.

### Incomplete Tasks:
- **Priority 1:**
  - [ ] Browser-validate setup Step 10 logging grid hydrate/serialize, audit tab, and prune after collectstatic.
- **Priority 2:**
  - [ ] Optional request-scoped `transaction.on_commit` activity aggregator; deferred due TestCase/order fragility.
- **Completed Recently:**
  - [x] v1.2.7 retries Celery readiness/version health, clears stale maintenance on newer-image reconciliation, and requires `db_default` for inline-safe NOT NULL fields.
  - [x] Added DB-backed `backup_config`, scheduled `.dlb` runs, default-storage targeting, successful-backup rotation, trigger history, and mandatory updater-backup messaging.
  - [x] Diagnosed live v1.2.2→v1.2.3 staging: pip rejected the digest-prefixed wheel basename.
  - [x] v1.2.4 stores `downloads/<sha>/<canonical-wheel-name>`, persists bounded/redacted pip diagnostics, and safely reconciles rebuilt-image state.
  - [x] Added persistent apply/rollback modal phase meter and durable log; removed native password form submission/save prompting.
  - [x] v1.2.5 limits “Update operation completed” to a five-second current-session result instead of permanently rendering the latest historical check.
  - [x] Completed updater integrity/recovery audit and current documentation reconciliation.

### One-line info about last verified Tests:
- 2026-06-24: v1.2.7 official suite passed 616; migration/compile/diff/release gates clean; wheel/sdist passed `twine` and packaged rebuild-required manifest/service fix.
- 2026-06-24: Official `test_all.py` passed 613; focused backup/updater 62 and forms 123 passed; migration/gate/Ruff/diff clean; isolated wheel/sdist passed `twine` and packaged `0004`/manifest.
- 2026-06-24: Exact scaffold nginx template passed `nginx -t` in `nginx:latest` with generated upstream names supplied.

### One-line info about last time edited Docs:
- 2026-06-24: Added post-Microsys-migration Redis DB cache/session flush guidance and scoped safety warnings.

## Part 2: Global
### Global Standard Helpers, Shortcuts, Info, etc.:
- Prefer `rg`/`rg --files` for discovery; inspect durable updater runs through the database, not web access logs alone.

### Global Rulesets:
- Keep tracker/changelog/docs synchronized with verified code and executed checks.

### Agent Handoff Rules:
- Read `tracker.md` every turn; preserve user work; use tag state plus release manifest before changelog/version edits.

### References and Links:
- Security: `docs/security-dsrp-1.md`; updater: `docs/inline-updater.md`; release: `docs/RELEASING.md`.
