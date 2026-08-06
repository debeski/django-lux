# Project Tracker (django-lux)

## Part 1: Project Related
### Current Verified Snapshot:
- Current source version: unreleased v1.7.0 in `dlux/release-manifest.json`; v1.6.1 is tagged/published.
- DjangoLux includes the typed Composer bridge and state-row-serialized update admission; generated projects emit one hardened `composer-agent` while Composer owns legacy migration.
- General Reports share criteria across overview, entries XLSX, print, and ZIP; print uses two A4 pages with restored desktop grids/recalculated canvases, ZIP carries workbook + media, and `.dlb` remains restorable JSON.
- Updater state uses `DluxUpdateState`/`DluxUpdateRun` plus `dlux_runtime`; generated proxy baseline is Caddy-default `.proxy/` with updater parity.
- `dlux_seed` emits parseable one-page PDFs; profile password changes can revoke other DB/cache sessions; backup recovery uses migration `0014` liveness/attempt fields.

### Current Project Adopted Standards:
- Integrate settings with `from dlux.utils import dlux_settings`; call `dlux_settings(globals())`; mount `dlux.urls` at root.
- `dlux.system` owns settings defaults/schema/normalizers/registry; migration-history wrappers remain in `dlux.models`.
- DSRP-1: backend authorization must match UI visibility; security mutations are POST-only.
- Runtime CSS/data/events/JS use `dlux` prefix and external assets; user copy uses `DLUX_STRINGS`.
- Releases are tag-driven; version source is `dlux/release-manifest.json`.

### Adopted Standards' rules and policies:
- Read `tracker.md` every turn; keep it under 100 lines; preserve unrelated user work; use `apply_patch` for manual edits.
- Before changelog edits, check `git tag`; tagged versions are immutable, so start a new version and bump manifest.
- Feature/config/schema/API/security/deployment changes require same-turn docs and changelog.
- No raw HTML in i18n strings/form help; crispy help_text is unescaped.
- Reuse Dlux components and full schema -> form -> config import/export patterns.

### Cross-Cutting Audits if any:
- 2026-06/07 updater/report/scaffold audits; 2026-08-03 table integration audit: Archive v1.6.2 matches package/collected assets and uses the supported unwrapped DLUX shell.
- Mounted test Compose uses Redis sessions; never use live `cache.clear()` probes because they delete browser sessions.

### Current Project's Unsolved Known Bugs:
- Fallback file/download redirects remain a high-risk-deployment review point; `_safe_referer()` currently enforces allowed hosts.
- Legacy `switch_pos` v1.2.4 deployments may stay degraded until v1.2.13+ reconcile clears or operator resets runtime flags.
- A stale pre-exclusion `composer-updater` can recreate its Docker socket proxy during the first 1.5.x app-image update and lose `DOCKER_HOST`; update Composer and migrate the legacy block with `enable-agent` before retrying.

### Incomplete Tasks:
- **Priority 1:**
  - [ ] project-archive: unresolved `dlux-updater` restart loop — still runs retired `tools.dlux_runtime_supervisor` (no strictly-newer gate) and `manage.py` lacks the release resolver; run `dlux enable-updater` and re-check `DluxUpdateState.active_version` vs running `dlux.__version__`.
  - [ ] Doctor P3 (composer repo): wire `composer check` drift-diff to exec `dlux_stack_contract` + mirror `diff_attachments()` AND `diff_command_modules()`/`fix_command_modules()` (contract schema 2).
  - [ ] Doctor P4: add `dlux.doctor` remote action + Control Panel surface; redact before the report leaves the host.
  - [ ] Verify `dlux_check --apply` against a live Docker stack (collectstatic + migrator paths); only unit-tested so far.
  - [ ] Browser-validate setup Step 11 logging grid hydrate/serialize, audit tab, and prune after collectstatic.
  - [ ] Run live Docker staging acceptance for central image update, backup creation, outage replay, and control-panel self-update.
  - [ ] Browser-validate General Reports/Backup & Restore plus Navigation Root, anonymous public root, and Control Panel at desktop/mobile widths (in-app browser unavailable 2026-08-03).
  - [ ] Re-export and visually verify the fixed Archive `sys/reports/print/` PDF is exactly two A4 pages (in-app browser has no attached tab).
- **Completed Recently:**
  - [x] v1.7.0 Email is setup Step 3 (before Access & Security) behind `email_config.enabled`; a passed test send sets fingerprinted `verified`, and `email_2fa`/`forgot_password`/`public_registration`/notification-email lock (value preserved) until enabled+verified; wizard indices are `SETUP_STEP_*` constants; +12 tests in `test_email_step.py`.
  - [x] v1.6.2: re-synced `scaffold_templates/project/start.{sh,ps1}.tmpl` from Composer 1.3.4 (`# composer-wrapper: 1`). Composer OWNS these; they are mirrors here — a `test_scaffold` case pins the version so drift fails the suite.
  - [x] v1.6.2 period preview labels both ends via `period['range_label']`; week/month options renamed Current (were 'Last'); query bounds unchanged.
  - [x] v1.6.2 report backup control: 'Create Backup ZIP' label, single status channel (duplicate terminal message fixed), download-last pill with size/age.
  - [x] v1.6.2 report outputs split: XLSX exports selected models' actual rows (credential fields dropped, `entries_row_limit`), ZIP packs that workbook + `files/` media with no JSON (`include_records=False`), analytics moved to printable `sys/reports/print/`; retired aggregate builder to `.xpose/`; +14 tests.
  - [x] v1.6.2 API navigation exclusion covers exact route/path/callback tokens, nested/suffix names, stored sidebar/Nav Bar trees, settings import/export, and a cache schema bump; +5 regressions.
  - [x] v1.6.2 optional password-change revocation retains current session, ends other DB/cache-backed sessions, hides/ignores under single-session enforcement, preserves trust; EN/AR +5 tests.
  - [x] v1.6.2 interrupted-backup recovery: migration `0014`, trigger-agnostic reaper, granular progress, retry policy/manual Resume, passphrase exclusion; +24 tests.
  - [x] v1.6.2 notification-linked sidebar counters with independent Sidebar toggle/live refresh; +6 tests.
  - [x] v1.6.2 valid seeded PDFs: complete one-page object/xref output; 75 Archive placeholders preserved/repaired and parsed with `pypdf`; +1 regression.
  - [x] v1.6.2 corrected `purge_session_on_exit` contract: browser-session expiry only; tabs share the cookie and individual tab close cannot safely sign out; EN/AR/docs +1 regression.
  - [x] v1.6.2 General Reports: business-only builder/exports plus opt-outs/RTL; two-page A4 grids/canvases fixed, print assets collected, Caddy negative caching and missing branding fallback corrected.
  - [x] v1.6.2 focused System Settings modals preserve theme/language counts when matrices are omitted, preventing sidebar/Options pickers from vanishing during live preview.
### One-line info about last verified Tests:
- 2026-08-06: v1.7.0 pre-release — full suite 1214 GREEN (2 PG-only skips); UI SMTP timeout verified through import/runtime/other-step-save round trip, which caught and fixed a clean-order reset of the email group.
- 2026-08-05: Send-test input-group — full suite 1206 GREEN; rendered-HTML guard asserts input and button are siblings in one `.dlux-email-test-group`, so column-alignment drift cannot return.
- 2026-08-05: Contract command drift + always-on Email indicator — full suite 1205 GREEN; `diff_command_modules`/`fix_command_modules` cover retired relay+supervisor paths, indicator asserts off/unproven/verified states.
- 2026-08-05: SMTP relay packaged as `dlux.smtp_relay` — 16 new behavioural tests (protocol loop, dot-stuffing, size cap, config resolution, 451 reason); full suite 1198 GREEN.
- 2026-08-05: Email step layout/unlock — full suite 1184 GREEN; rendered-HTML check confirms md columns pair password+recipients and recipient+test button, inline status replaces the alert banner.
- 2026-08-05: Email in-form Apply — 5 tests (persists only email_config, leaves other groups/home_url untouched, superuser+POST only, apply-then-test verifies); full suite 1184 GREEN.
- 2026-08-05: Email verification persistence — 3 regressions in `test_email_step.py` (save keeps verification; host change and retyped password still re-arm), full suite 1179 GREEN.
- 2026-08-05: SMTP secret visibility + relay timeout pairing — 10 tests (`test_smtp_timeouts.py`, `test_email_step.py`), full suite 1175 GREEN; undecryptable secrets now 409 instead of failing blind.
- 2026-08-05: SMTP relay timeout pairing — 7 tests in `test_smtp_timeouts.py`, full discovery suite 1172 GREEN (2 PG-only skips); relay-vs-client ordering pinned so 451 reasons reach the UI.
- 2026-08-05: Email step + verification guard + dependent locking — 12 focused tests in `test_email_step.py`, full discovery suite 1165 GREEN (2 PG-only skips); fingerprint re-arming proven across form/import/export paths.
- 2026-08-05: System Settings picker preservation — 2 regression, 324 related, and full discovery 1147 GREEN (2 skips); Archive collected/served JS checksum matches source.
- 2026-08-04: Two-page A4 print fix — 33 report tests + full discovery 1147 GREEN (2 skips); Archive collected/served assets match source; visual re-export awaits an attached browser.
### One-line info about last time edited Docs:
- 2026-08-05: Admin Guide rewritten to fourteen wizard steps with the Email step, verification-as-guard contract, and lock-not-clear semantics; CHANGELOG v1.7.0.
- 2026-08-05: Focused System Settings live-preview preservation documented in Features/Admin Guide/changelog.
## Part 2: Global
### Global Standard Helpers, Shortcuts, Info, etc.:
- Prefer `rg`/`rg --files`; inspect durable updater runs through DB/runtime state, not web logs alone.
- Static cache-busting: `{% dlux_static %}` appends the Dlux version plus source mtime in DEBUG; Caddy caches only files that exist.

### Global Rulesets:
- Keep tracker/changelog/docs synchronized with verified code and executed checks.
- File cleanup policy: move obsolete files into `.xpose/<relative path>`; never delete repo files or directories.
- Project-side runtime helpers belong in the package (supervisor, smtp relay): scaffold copies strand fixes in whatever version a project was generated with.

### Agent Handoff Rules:
- Preserve user work; if tagged version exists, create next changelog/manifest version.
- Adding/extending a system setting: read `docs/adding-system-settings.md` first; add keys to `SYSTEM_SETTINGS_EXPORT_FIELDS`.

### References and Links:
- Security: `docs/security-dsrp-1.md`; updater: `docs/inline-updater.md`; release: `docs/RELEASING.md`.
- Add a system setting: `docs/adding-system-settings.md`. Downstream app config: `reference.md` (`extra_config['app']`).
