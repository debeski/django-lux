# Project Tracker (django-lux)

## Part 1: Project Related
### Current Verified Snapshot:
- `dlux/release-manifest.json` is the version source: unreleased inline-safe v1.2.6 (migration `0005` repairs the 1.2.5 backup-trigger NOT NULL bug); latest published tag is v1.2.5.
- v1.2.4 is a mandatory one-rebuild updater-bootstrap repair for v1.2.2/v1.2.3 generated Compose deployments.
- DjangoLux supplies settings/setup, scoped models, auth/security, navigation, reports, backup, scaffolding, SSO hooks, and the Compose updater.
- Updater state uses `DluxUpdateState`/`DluxUpdateRun` plus `dlux_runtime` releases, atomic pointer, generation, maintenance, heartbeat, and degraded markers.
- `switch_pos` is healthy and idle on baked/active v1.2.4; latest check is completed, active-run token is empty, and degraded state is false.

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

### Current Project's Unsolved Known Bugs:
- v1.2.5 yanked (bad migration): `SystemBackup.trigger` was NOT NULL with no DB default, so the updater's pre-update backup (run by the previous release's code after a rollback) hit a NOT NULL violation. v1.2.6 corrects `0004` in place to give `trigger` a `db_default='manual'`. Any DB that already applied the broken `0004` (e.g. the test deployment) is not re-migrated and needs a one-time `ALTER TABLE dlux_systembackup ALTER COLUMN trigger SET DEFAULT 'manual';`.
- Follow-up (not done): `release_check` inline gate still treats a plain Python `default` as safe (the gap that let v1.2.5 through). Tightening it to require `db_default` for NOT NULL AddField also flags `backup_config` (a singleton JSONField never inserted by old code) as a false positive — needs a smarter gate before enforcing.
- Fallback file/download redirects remain a high-risk-deployment review point; `_safe_referer()` currently enforces allowed hosts.
- Mounted test Compose uses Redis sessions; never use live `cache.clear()` probes because they delete browser sessions.

### Incomplete Tasks:
- **Priority 1:**
  - [ ] Browser-validate setup Step 10 logging grid hydrate/serialize, audit tab, and prune after collectstatic.
- **Priority 2:**
  - [ ] Optional request-scoped `transaction.on_commit` activity aggregator; deferred due TestCase/order fragility.
- **Completed Recently:**
  - [x] Added DB-backed `backup_config`, scheduled `.dlb` runs, default-storage targeting, successful-backup rotation, trigger history, and mandatory updater-backup messaging.
  - [x] Diagnosed live v1.2.2→v1.2.3 staging: pip rejected the digest-prefixed wheel basename.
  - [x] v1.2.4 stores `downloads/<sha>/<canonical-wheel-name>`, persists bounded/redacted pip diagnostics, and safely reconciles rebuilt-image state.
  - [x] Added persistent apply/rollback modal phase meter and durable log; removed native password form submission/save prompting.
  - [x] v1.2.5 limits “Update operation completed” to a five-second current-session result instead of permanently rendering the latest historical check.
  - [x] Added v1.2.3 email presets, send-test endpoint, delivery-failure alerts, and a blocking release test gate.
  - [x] Completed updater integrity/recovery audit and current documentation reconciliation.

### One-line info about last verified Tests:
- 2026-06-24: Official `test_all.py` passed 613; focused backup/updater 62 and forms 123 passed; migration/gate/Ruff/diff clean; isolated wheel/sdist passed `twine` and packaged `0004`/manifest.
- 2026-06-23: v1.2.5 idle-status fix passed full `test_all.py` (609), focused updater tests (35), Ruff/diff/release gates, and JavaScript syntax validation.
- 2026-06-23: Final wheel/sdist passed `twine check`, artifact hygiene, exact canonical `pip --target` staging, packaged progress UI, and new-scaffold production/dev Compose parsing.
- 2026-06-23: Live v1.2.3 wheel succeeded after canonical renaming plus `check`, `dlux_check`, and `migrate --plan` inside `switch_pos`.

### One-line info about last time edited Docs:
- 2026-06-24: Documented `backup_config`, scheduling/rotation/storage policy, Step 12, trigger history, and updater backup guarantees across admin/reference/updater/feature/scaffold docs.

## Part 2: Global
### Global Standard Helpers, Shortcuts, Info, etc.:
- Prefer `rg`/`rg --files` for discovery; inspect durable updater runs through the database, not web access logs alone.

### Global Rulesets:
- Keep tracker/changelog/docs synchronized with verified code and executed checks.

### Agent Handoff Rules:
- Read `tracker.md` every turn; preserve user work; use tag state plus release manifest before changelog/version edits.

### References and Links:
- Security: `docs/security-dsrp-1.md`; updater: `docs/inline-updater.md`; release: `docs/RELEASING.md`.
