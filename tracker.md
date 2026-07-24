# Project Tracker (django-lux)

## Part 1: Project Related
### Current Verified Snapshot:
- Current source version: unreleased v1.5.6 in `dlux/release-manifest.json`; v1.5.5 is tagged and published.
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

### Incomplete Tasks:
- **Priority 1:**
  - [ ] Browser-validate setup Step 10 logging grid hydrate/serialize, audit tab, and prune after collectstatic.
  - [ ] Run live Docker staging acceptance for central image update, backup creation, outage replay, and control-panel self-update.
  - [ ] Browser-validate v1.4.15 Navigation Root selector at desktop/mobile widths; in-app browser was unavailable during implementation.
  - [ ] Browser-validate v1.2.13 anon public root with `show_sidebar_on_public` on; confirm `sidebar_items.html` degrades for AnonymousUser.
  - [ ] Browser-validate v1.4.10 table column resizing with sticky headers on/off and RTL/LTR.
  - [ ] Browser-validate the v1.5.6 Control Panel Admin-command rail and pairing page at desktop/mobile widths; in-app browser was unavailable during implementation.
- **Completed Recently:**
  - [x] v1.5.6 moves Control Panel into Admin commands and rebuilds its responsive pairing/status page with Dlux fields, explicit polling hooks, and native flashes; no migration.
  - [x] v1.5.5 repairs the scaffold env regression with an exact 21-key contract and aligns generated docs with UI-first Composer pairing; no migration.
  - [x] v1.5.3 adds shared manifest version discovery and repairs legacy `enable-updater` with the maintained proxy page plus nginx status/log routes; no migration.
  - [x] v1.5.2 deterministic first-launch config: `migrator` applies `BASE_DIR/config.json` after migrations under the singleton lock; setup GET remains fallback with explicit outcomes.
  - [x] v1.5.0 atomic update admission: inline/local/control image queues serialize on `DluxUpdateState`; PostgreSQL contention and live v1.4.15 apply/rollback verified.
  - [x] v1.5.0: moved canonical agent scaffold migration into Composer 1.2; retained a thin wrapper-aware DLUX compatibility forwarder.
  - [x] v1.5.0 agent bridge: atomic typed spool/snapshot with handled-request archival, central/local shared queue lock, finalization correlation, central data/full backup creation, hardened scaffold, migration command, ASGI middleware hooks, and UUID-safe logging.
  - [x] v1.4.15 active Nav Bar roots now match ordinary active crumbs: bold primal text without a filled pill.
  - [x] v1.4.15 configurable Nav Bar root: pinned neutral/home/discovered-route selector, runtime homepage following, true-boundary trimming, history dedupe, legacy-neutral normalization, EN+AR strings; no migration.
  - [x] v1.4.15 optional titlebar language switcher: `titlebar.show_language_switcher` (Step 7 toggle, disabled unless switching possible), mono cycle button via `window.setLanguage`, gated by `language_picker_enabled`; shares `dlux-titlebar-action` styling + `data-titlebar-show-language-switcher` visibility so `applyTitlebarPreview` flips it live like show_title/logo/home; no migration.
  - [x] v1.4.15 updater running state hides review-only Skip/Re-check controls.
  - [x] v1.4.14 reliable background update check: Celery-beat `dlux-update-check` (hourly) enqueues via `queue_daily_check_if_due`; worker loop retained as fallback; 7 scheduling tests; docs/changelog/manifest; no migration.
  - [x] v1.4.14 updater review modal locked (Esc/backdrop/dismiss vetoed via `hide.bs.modal`) while inline apply/rollback runs; releases on terminal status; no migration.
  - [x] v1.4.14 Branding-modal name inputs synchronize directly into `system_names` without requiring the Languages editor; no migration.

### One-line info about last verified Tests:
- 2026-07-24: v1.5.6 full suite GREEN: 896 tests (2 PostgreSQL-only skips); focused Control Panel/admin-action tests, compileall, manifest JSON, and diff checks GREEN.
- 2026-07-24: v1.5.5 full suite GREEN: 891 tests (2 PostgreSQL-only skips); focused scaffold, migration, compile, manifest JSON, tag-separation, and diff checks GREEN.
- 2026-07-23: PostgreSQL 17 contention GREEN: simultaneous image/image and inline/image admission each produced exactly one accepted run.
- 2026-07-23: isolated Docker v1.4.15→v1.5.0 apply/rollback GREEN: backups, migration 0011, static, web/Celery/updater versions/health, and old-ORM insert default.
- 2026-07-23: v1.4.15 full suite GREEN: 861 tests (1 skipped, Celery absent); titlebar language-switcher preview/data-attribute test; browser unavailable.

### One-line info about last time edited Docs:
- 2026-07-24: composer-agent docs locate Control Panel under Admin commands and describe its bridge status, Dlux fields, HTTPS validation, and native feedback.
- 2026-07-24: generated project and Composer-agent docs align the 21-key env contract with UI-first pairing and optional headless fallback.

## Part 2: Global
### Global Standard Helpers, Shortcuts, Info, etc.:
- Prefer `rg`/`rg --files`; inspect durable updater runs through DB/runtime state, not web logs alone.
- Static cache-busting: use `{% dlux_static %}` for versioned dlux assets; it appends `?v=dlux.__version__`.

### Global Rulesets:
- Keep tracker/changelog/docs synchronized with verified code and executed checks.
- File cleanup policy: move obsolete files into `.xpose/<relative path>`; never delete repo files or directories.

### Agent Handoff Rules:
- Preserve user work; if tagged version exists, create next changelog/manifest version.

### References and Links:
- Security: `docs/security-dsrp-1.md`; updater: `docs/inline-updater.md`; release: `docs/RELEASING.md`.
