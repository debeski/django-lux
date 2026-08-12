# Project Tracker (django-lux)

## Part 1: Project Related
### Current Verified Snapshot:
- BOOT ORDER (1.8.0, requires Compose 5.3.0+): reconcile+migrator are native Compose `pre_start` init containers on CELERY (not web — a step inherits its service's mounts and `dlux_reconcile` writes the runtime pointer, which is ro on web, where it silently no-ops). Each step needs `DLUX_BOOT_GATE: "off"` — a step inherits the entrypoint, whose gate waits on those very migrations (verified empirically). Flags reach the static step via `${DLUX_MIGRATOR_FLAGS:-}`, set by composer's compose env. `entrypoint.sh` waits on `migrate --check` — the net for reboots, which Compose skips pre_start on. web depends only on db/redis/smtp-relay. `composer check` FAILs Compose <5.3.0 (it IGNORES pre_start rather than erroring).
- Current source version: unreleased v1.8.0; v1.7.1 is tagged/published — append to the v1.8.0 entry, never a tagged one.
- DjangoLux includes the typed Composer bridge and state-row-serialized update admission; generated projects emit one hardened `composer-agent` while Composer owns legacy migration.
- `Scope.default_theme` supplies the runtime fallback when scopes are enabled and multiple themes are selectable; valid personal preferences still win.
- Updater state uses `DluxUpdateState`/`DluxUpdateRun` plus `dlux_runtime`; generated proxy baseline is Caddy-default `.proxy/` with updater parity.
- The migrator contract: `-mm` forces makemigrations for ALL target apps; bare only for apps with no `migrations/0001_*.py`; `-nm` skips makemigrations+migrate but STILL collects static; `-mm`/`-nm` exclusive. Composer runs it ONCE via the `org.dlux.post-start` label (never Compose's native `post_start`, which Compose runs itself unflagged).

### Current Project Adopted Standards:
- ONE switch: reuse `dlux-settings-toggle-field__control form-switch` + `form-check-input dlux-settings-toggle-field__input` + `type=checkbox`; `helpers/toggle/css/main.css` + the themes style those names only. Never hand-roll `form-check form-switch`. Keep host layout (e.g. `dlux-assist-bar`) separate from it.
- Integrate settings with `from dlux.utils import dlux_settings`; call `dlux_settings(globals())`; mount `dlux.urls` at root.
- `dlux.system` owns settings defaults/schema/normalizers/registry; migration-history wrappers remain in `dlux.models`.
- DSRP-1: backend authorization must match UI visibility; security mutations are POST-only.
- Static layout is feature-first: `dlux/static/dlux/<feature>/{css,js}/main.*`; a single-file feature uses `main.*`, extra files keep descriptive names. Shared primitives live under `helpers/<name>/`. Never add assets back into `base/`.
- Dlux-first UI: use `DluxFileInput`/`AssetPickerField` (never raw file inputs), Dlux choice widgets, Dlux icon picker, toggle builders, `DluxTable` shells, dynamic-modal protocol, and `DluxLoadingButton` before generic controls; catalog: `docs/developer-guide.md`.

### Adopted Standards' rules and policies:
- Read `tracker.md` every turn; keep it under 100 lines; preserve unrelated user work; use `apply_patch` for manual edits.
- Before changelog edits, check `git tag`; tagged versions are immutable, so start a new version and bump manifest.
- Feature/config/schema/API/security/deployment changes require same-turn docs and changelog.
- No raw HTML in i18n strings/form help; crispy help_text is unescaped.
- Reuse Dlux components and full schema -> form -> config import/export patterns.

### Cross-Cutting Audits if any:
- 2026-06/07 updater/report/scaffold audits; 2026-08-03 table integration audit: Archive v1.6.2 matches package/collected assets and uses the supported unwrapped DLUX shell.
- Mounted test Compose uses Redis sessions; never use live `cache.clear()` probes because they delete browser sessions.
- 2026-08-07 structure audit: preserve root public import façades; reduce `forms.py`, `views/general.py`, `reports.py`, `discovery.py`, `backup.py`, and domain-specific `utils` incrementally behind contract tests.

### Current Project's Unsolved Known Bugs:
- Inline updates need a WRITABLE runtime volume; `runtime_volume_problem()` (pure stat, no mkdir) gates `queue_run` + `serialize_state` + a doctor check. Never fall back to another directory — supervisor/Composer resolve releases via `runtime_contract.json`, so staging elsewhere silently no-ops the update.
- PERF INVARIANTS (guarded by `test_render_cost.py`): template wrapper tags must render into the CURRENT context (a new RequestContext re-runs all context processors); `get_available_fonts()` must stay memoised per request (config normalisation calls it ~278x/page, and each call is BEGIN/SELECT/COMMIT).
- PG-only class of bug: a swallowed `ProgrammingError` around an ORM query does NOT un-abort the transaction, so the NEXT statement dies and the traceback blames the wrong operation. Invisible on SQLite. Always wrap such queries in `with transaction.atomic()`. Guard: `dlux/tests/test_transaction_safety.py`.
- Isolated `dlux.tests.test_groups` has two 302 failures because setup middleware sees default unconfigured settings; package discovery passes after earlier tests cache configured state.
- dlux has ZERO module-scope import cycles (verified v1.8.0); the 421 function-scope imports are load-bearing mitigation, not clutter. Two deferred-coupling clusters (28 + 7 modules) remain — promoting any of their imports to module scope creates a real cycle. Detector: `scripts/import_cycles.py`; guards: `dlux/tests/test_import_graph.py`.
- Fallback file/download redirects remain a high-risk-deployment review point; `_safe_referer()` currently enforces allowed hosts.
- Legacy `switch_pos` v1.2.4 deployments may stay degraded until v1.2.13+ reconcile clears or operator resets runtime flags.
- A stale pre-exclusion `composer-updater` can recreate its Docker socket proxy during the first 1.5.x app-image update and lose `DOCKER_HOST`; update Composer and migrate the legacy block with `enable-agent` before retrying.

### Incomplete Tasks:
- **Priority 1:**
  - [ ] Updater consolidation (`docs/updater-consolidation.md`), dlux-side executor DEPRECATED 1.8.0 / REMOVED 1.9.0. STEPS 1-4 DONE, ready at the 1.8.0 release: composer executes apply/rollback/check (`dlux.package_update`, `dlux_runtime.py`, `dlux_release_source.py`, `dlux_package_update.py`, `composer dlux-update`), runtime contract asserted both sides, `DLUX_UPDATE_EXECUTOR` (default composer; `inline` = legacy until 1.9.0), `_process_check` reads composer's `package-available.json` (absent = UNKNOWN, never 'up to date'), `enable-updater` deprecation notice, `composer check` verifies loop + `dlux_runtime` mount. CORRECTED: the `dlux-updater` SERVICE is never removed — it also runs `dlux_reconcile`/`migrator`, `web` gates on its health, and `dlux_update_worker` is the sole `process_next()` caller. Suites 1567 + 425 GREEN. DECIDED 2026-08-11: Composer is a HARD REQUIREMENT from 1.8.0 — a service in the deployment (latest stable image), not just the deployer; dlux is being stripped of outbound responsibilities by design. `check` FAILs a dlux stack with no Composer service; `check --fix` installs the hardened trio via `install_composer_stack()`. The "does anyone run dlux without composer" question is CLOSED — not a constraint. NEXT: `composer check` diff of a DEPLOYED volume vs the fetched contract.
  - [ ] project-archive: unresolved `dlux-updater` restart loop — still runs retired `tools.dlux_runtime_supervisor` (no strictly-newer gate) and `manage.py` lacks the release resolver; run `dlux enable-updater` and re-check `DluxUpdateState.active_version` vs running `dlux.__version__`.
  - [ ] Doctor P3 (composer repo): wire `composer check` drift-diff to exec `dlux_stack_contract` + mirror `diff_attachments()` AND `diff_command_modules()`/`fix_command_modules()` (contract schema 2).
  - [ ] Doctor P4: add `dlux.doctor` remote action + Control Panel surface; redact before the report leaves the host.
  - [ ] Verify `dlux_check --apply` against a live Docker stack (collectstatic + migrator paths); only unit-tested so far.
  - [ ] Browser-validate setup Step 11 logging grid hydrate/serialize, audit tab, and prune after collectstatic.
  - [ ] Run live Docker staging acceptance for central image update, backup creation, outage replay, and control-panel self-update.
  - [ ] Browser-validate General Reports/Backup & Restore plus Navigation Root, anonymous public root, and Control Panel at desktop/mobile widths (in-app browser unavailable 2026-08-03).
  - [ ] Re-export and visually verify the fixed Archive `sys/reports/print/` PDF is exactly two A4 pages (in-app browser has no attached tab).
- **Priority 2:**
  - [ ] Stage the domain-oriented package restructure after adding public-import, URL-name, migration-drift, template/static-path, and task-path contract checks.
- **Completed Recently:**
  - [x] v1.7.2 per-scope default theme: `Scope.default_theme` + inline-safe migration 0016; scope form gated by enabled scopes and >1 allowed theme; request/onboarding fallback; valid personal preference wins. +11 tests.
  - [x] v1.7.2 two-theme sidebar control switches directly to the other allowed theme; one theme hides it and 3+ retain the popup. Native buttons, focus state, live swatch/label, persistence. +4 tests.
  - [x] v1.7.2 FIXED archive startup: dlux resolved a URL while the project's ROOT_URLCONF was mid-import (gettext patch -> get_system_config -> sidebar sanitize -> reverse), so Django cached the half-built module and all URL checks failed. Guard + 3 mutation-verified regressions.
  - [x] v1.7.2 server-side sticky helpers in `dlux.utils` (`sticky_forms_enabled`/`sticky_form_initial`, read the `sticky_forms` pref). project-archive uses them (6 views + 6 templates, +6 archive tests); its helper falls back to reading the pref directly because archive pins `django-lux==1.7.1`.
  - [x] SUPERSEDED projects (archive, decrees) prefill SERVER-SIDE in views/forms and used to gate on the `enable_prefill` COOKIE (default 'true'). Dropping the cookie writer made it permanently on — fixed by `dlux.utils.sticky_forms_enabled(request)` / `sticky_form_initial(...)` reading the `sticky_forms` preference. `data-sticky-server` marks server-prefilled forms (skip client fill, reload on toggle). project-archive converted (6 sites + 6 templates); **project-decrees still reads the cookie and needs the same change**.
### One-line info about last verified Tests:
- 2026-08-12: dlux 1602 GREEN. `toggle_sidebar` utils->views/sidebar.py (urls.py no longer imports utils); new `dlux/admin_actions/` holds data_reset + force_password_change (extracted from views/general.py) with 6 new mutation-verified tests for the latter, which had none.
- 2026-08-11: updater consolidation steps 1-3 — dlux 1555 GREEN, composer 406 GREEN; full cross-repo hand-off verified (dlux intent -> composer executor -> ack).
- 2026-08-11: updater consolidation steps 1-2 — dlux 1536 GREEN, composer 406 GREEN; composer writes the runtime volume and dlux's own RuntimeStore reads it back; both sides conform to `runtime_contract.json`.
- 2026-08-10: downstream-compat audit — found+fixed a REAL break (project-sales-crm includes `dlux/includes/messages.html`, moved this session); all shims now guarded by `test_downstream_compat.py`. Suite 1521 GREEN.
### One-line info about last time edited Docs:
- 2026-08-11: `docs/inline-updater.md` leads with "Composer is required (1.8.0)" + who-executes protocol table; `updater-consolidation.md` records the hard-requirement decision and the corrected deletion list; `deprecation-countdown.md` + `deployment-configuration.md` + FEATURES/reference aligned.
- 2026-08-10: `audit_plan.md` replaced with the Python restructure plan (layers over vertical slices, Phase 0 done, Phase 1 order).
- 2026-08-09: new `docs/deprecation-countdown.md` (shim ledger, removal targets); `docs/FEATURES.md` + `docs/reference.md` static paths refreshed.

## Part 2: Global
### Global Standard Helpers, Shortcuts, Info, etc.:
- Prefer `rg`/`rg --files`; inspect durable updater runs through DB/runtime state, not web logs alone.
- Static cache-busting: `{% dlux_static %}` appends the Dlux version plus source mtime in DEBUG; Caddy caches only files that exist.

### Global Rulesets:
- Keep tracker/changelog/docs synchronized with verified code and executed checks.
- File cleanup policy: move obsolete files into `.xpose/<relative path>`; never delete repo files or directories.
- Project-side runtime helpers belong in the package (supervisor, smtp relay): scaffold copies strand fixes in whatever version a project was generated with.

### Agent Handoff Rules:
- Moving/renaming a template, static file or public symbol: grep the six active projects FIRST, shim what they use, and record it in `docs/deprecation-countdown.md` + `test_downstream_compat.py`.
- Preserve user work; if tagged version exists, create next changelog/manifest version.
- Adding/extending a system setting: read `docs/adding-system-settings.md` first; add keys to `SYSTEM_SETTINGS_EXPORT_FIELDS`.

### References and Links:
- Updater consolidation proposal (move the executor to Composer, v2.0): `docs/updater-consolidation.md`.
- Compat shims and their removal targets: `docs/deprecation-countdown.md`.
- Security: `docs/security-dsrp-1.md`; updater: `docs/inline-updater.md`; release: `docs/RELEASING.md`.
- Add a system setting: `docs/adding-system-settings.md`. Downstream app config: `reference.md` (`extra_config['app']`).
