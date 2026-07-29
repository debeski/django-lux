# Project Tracker (django-lux)

## Part 1: Project Related
### Current Verified Snapshot:
- Current source version: unreleased v1.6.0 in `dlux/release-manifest.json`; v1.5.10 is tagged/published. NEVER append to an already-published version — check the tag first, then start a new version + bump the manifest.
- DjangoLux includes the typed Composer agent bridge, migration `0011`, and state-row-serialized inline/image admission.
- Generated projects emit one hardened `composer-agent`; Composer owns legacy migration and `dlux enable-agent` is a one-cycle forwarder.
- First-launch `BASE_DIR/config.json` bootstrap runs during `migrator` after migrations; the setup GET retains the same row-locked fallback.
- Updater state uses `DluxUpdateState`/`DluxUpdateRun` plus `dlux_runtime`; generated proxy baseline is Caddy-default `.proxy/` with updater parity.

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
- 2026-06/07 audits: updater artifacts/attestation/migrations/proxy, report backup/download/media/nginx, scaffold-vs-project-decrees.
- Mounted test Compose uses Redis sessions; never use live `cache.clear()` probes because they delete browser sessions.

### Current Project's Unsolved Known Bugs:
- Fallback file/download redirects remain a high-risk-deployment review point; `_safe_referer()` currently enforces allowed hosts.
- Legacy `switch_pos` v1.2.4 deployments may stay degraded until v1.2.13+ reconcile clears or operator resets runtime flags.
- A stale pre-exclusion `composer-updater` can recreate its own Docker socket proxy during the first 1.5.x app-image update and lose `DOCKER_HOST`; update Composer and migrate the verified legacy block with `enable-agent` before retrying.

### Incomplete Tasks:
- **Priority 1:**
  - [ ] Doctor P3 (composer repo): wire `composer check`'s contract drift-diff to exec `dlux_stack_contract` + mirror `diff_attachments()`; deep relay already execs `dlux_doctor` (v1.2.5).
  - [ ] Doctor P4: `dlux.doctor` remote action in `agent_protocol.REMOTE_ACTIONS` + Control Panel surface; redact before the report leaves the host.
  - [ ] Verify `dlux_check --apply` against a live Docker stack (collectstatic + migrator paths); only unit-tested so far.
  - [ ] Browser-validate setup Step 11 logging grid hydrate/serialize, audit tab, and prune after collectstatic.
  - [ ] Run live Docker staging acceptance for central image update, backup creation, outage replay, and control-panel self-update.
  - [ ] Browser-validate v1.4.15 Navigation Root selector at desktop/mobile widths; in-app browser was unavailable during implementation.
  - [ ] Browser-validate v1.2.13 anon public root with `show_sidebar_on_public` on; confirm `sidebar_items.html` degrades for AnonymousUser.
  - [ ] Browser-validate v1.4.10 table column resizing with sticky headers on/off and RTL/LTR.
  - [ ] Browser-validate the v1.5.6 Control Panel Admin-command rail and pairing page at desktop/mobile widths; in-app browser was unavailable during implementation.
  - [ ] Browser-validate v1.5.10 dynamic-modal title normalization and persistent submit/cancel/wizard footer; in-app browser had no active session.
  - [ ] Browser-validate v1.5.10 row_actions_style `column`/`both`: three-dot button opens the shared menu at the button, toggle-close, hideMenu guard, mobile tap, and RTL column placement (server render + logic unit-tested; no live click yet).
- **Completed Recently:**
  - [x] v1.6.0 Hardened Composer scaffold: `compose.yml.tmpl` adds `composer-executor` (holds docker.sock rw), demotes `docker-socket-proxy` to POST=0/EXEC=0, agent keeps read-only DOCKER_HOST + `composer_exec_sock` socket; `stack_contract.json` + topology tests updated; generated compose passes real `docker compose config`; suite 1040 GREEN. Needs composer executor role (app-composer, 218 tests); existing stacks harden via `composer check --fix`.
  - [x] v1.5.11 `dlux_settings()` isolates `manage.py test`/pytest caches with process-local LocMem by default, preventing test `SystemSettings` and sessions from leaking into a live development Redis; explicit opt-out retained.
  - [x] v1.5.11 Added dry-run-first `dlux_seed`: project-model discovery, typed/random required-field generation, relation ordering, deterministic/model/app controls, and targeted local-`populate` reuse for canonical lookup models; +3 focused tests and Decrees integration.
  - [x] v1.5.11 Dropped `django.contrib.admin` from scaffolds (settings.py.tmpl INSTALLED_APPS + urls.py.tmpl import/path); getting-started example updated; dlux never needed it (test settings already admin-free). Also stripped it from 7 existing projects (archive, decrees, trademarks, min-survey, dlux-panel, dhub, sales-crm gov_edition+switch_pos).
  - [x] v1.5.10 scaffold TIME_ZONE wiring: `compose.yml.tmpl` x-environment gains `TIME_ZONE: "${TIME_ZONE:-UTC}"`, `.secrets/.env.tmpl` ships `TIME_ZONE=UTC`, `stack_contract.json` env_keys + scaffold README updated, `dlux_settings()` fallback `Etc/GMT-2`→env-driven `UTC`.
  - [x] v1.5.10 Arabic variant-aware search: new `dlux.utils.arabic` (`arabic_search_q`/`arabic_search_pattern`/`normalize_arabic`, overridable `ARABIC_EQUIVALENCE_GROUPS`) matches alef/hamza, ي/ى/ئ/ی, ة/ه, ق/غ, و/ؤ, ک, digits via one `__iregex` per field; +15 tests, docs in reference + developer-guide.
  - [x] v1.5.10 Table row-actions style setting `layout_config.row_actions_style` (context|column|both): `column`/`both` add a presentational `dlux_row_actions` three-dot column via patched `Table.__init__` (empty_values=(), reuses row `data-dlux-actions` through shared context-menu JS + new `.dlux-row-actions-trigger` handler); full pipeline + EN/AR + 10 tests (`test_row_actions_style.py`).
  - [x] v1.5.10 System Settings is now 13 category-owned steps: Themes/Typography is theme/font-only, Layout is Step 10, public-root identity/sidebar/titlebar/theme controls follow their categories and master visibility, and EN/AR/options/search/deep links were shifted.
  - [x] v1.5.10 audit-field + soft-delete visibility toggles now live in Layout; permission/superadmin gates, manager/table/detail behavior, export/bootstrap persistence, Decrees override, migration 0013, EN/AR, and +19 tests.
  - [x] v1.5.10 global-search autofill fix: titlebar search box was autofilled with the saved username (`admin`); added non-credential `name` + `data-1p-ignore`/`data-lpignore`/`data-form-type="other"` (our JS never set the value). Template-only.
  - [x] v1.5.10 dynamic-modal chrome normalization: one shell title, legacy header/body/footer folding with context retained, and persistent form-associated submit/cancel/wizard controls; documented and +2 focused regressions.
  - [x] v1.5.10 footer/modal fix: `body.modal-open .dlux-footer { display:none }` so the footer's `backdrop-filter` layer stops bleeding over modal action bars (blocked submit buttons); no z-index change, offcanvas unaffected. CSS-only.
  - [x] v1.5.10 Control Panel disconnect surfacing: `control_link_state()` gains derived `connection_status` (connected/pending/disconnected/unconfigured); distinct "Disconnected" badge + warning banner (names URL, revoked-aware); worker `_detect_control_link_disconnect()` posts a one-time superadmin notification on enrolled→disconnected (runtime-volume dedup marker, re-arms on reconnect). control_url was always read from `agent-status.json`, never hardcoded. EN/AR; +4 tests; no migration.
### One-line info about last verified Tests:
- 2026-07-28: `UtilsTests` 65/65 GREEN in the mounted Decrees container; after the run, live Redis `SystemSettings` still matched PostgreSQL (Arabic name, gold theme, `/documents/`).
- 2026-07-28: Seed tests 7/7 GREEN (Dlux 3 + Decrees 4); isolated full Dlux suite 1037/1038 with sole unrelated existing `test_worker_records_a_bridge_failure_and_drops_the_token` failure (also fails alone).
- 2026-07-27: full suite GREEN: 1010 tests (2 PostgreSQL-only skips); Arabic settings/search tests now identify entries by stable step URLs and catalog-derived labels, so translation copy edits do not break routing coverage.
- 2026-07-27: scaffold/utils/defaults/updater suites GREEN post TIME_ZONE wiring (344 tests, 2 PG-only skips) incl. env-key contract and generated-README key list.
- 2026-07-27: full suite GREEN: 1020 tests (2 PostgreSQL-only skips); +10 `test_row_actions_style.py` (settings round-trip/export-whitelist/normalizer + per-mode column presence/context-attr/button-render/empty-header).

### One-line info about last time edited Docs:
- 2026-07-28: RELEASING.md documents automatic test cache isolation and the dedicated-cache opt-out; reference.md documents `dlux_seed`.

## Part 2: Global
### Global Standard Helpers, Shortcuts, Info, etc.:
- Prefer `rg`/`rg --files`; inspect durable updater runs through DB/runtime state, not web logs alone.
- Static cache-busting: use `{% dlux_static %}` for versioned dlux assets; it appends `?v=dlux.__version__`.

### Global Rulesets:
- Keep tracker/changelog/docs synchronized with verified code and executed checks.
- File cleanup policy: move obsolete files into `.xpose/<relative path>`; never delete repo files or directories.

### Agent Handoff Rules:
- Preserve user work; if tagged version exists, create next changelog/manifest version.
- Adding/extending a system setting: read `docs/adding-system-settings.md` end-to-end FIRST (full pipeline + traps; #1 trap = must add key to `SYSTEM_SETTINGS_EXPORT_FIELDS`).

### References and Links:
- Security: `docs/security-dsrp-1.md`; updater: `docs/inline-updater.md`; release: `docs/RELEASING.md`.
- Add a system setting: `docs/adding-system-settings.md`. Downstream app config: `reference.md` (`extra_config['app']`).
