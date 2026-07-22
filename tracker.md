# Project Tracker (django-lux)

## Part 1: Project Related
### Current Verified Snapshot:
- Current source version: unreleased v1.4.13 in `dlux/release-manifest.json`; v1.4.12 is tagged.
- DjangoLux supplies settings/setup, auth/security, navigation, reports, backup, scaffolding, SSO hooks, tables, and updater; migration baseline remains `0010`.
- Latest work: generated wrappers hand private env values to Composer 1.1.15+ resident updaters; compact metadata and quote-safe manifests remain in v1.4.13.
- Runtime table renderer is centralized in `DluxTable` + `dlux/tables/table.html` + `tables.js`/`tables.css`; responsive proportions persist per table in browser `localStorage`.
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
  - [ ] Browser-validate v1.2.13 anon public root with `show_sidebar_on_public` on; confirm `sidebar_items.html` degrades for AnonymousUser.
  - [ ] Browser-validate v1.4.10 table column resizing with sticky headers on/off and RTL/LTR.
- **Priority 2:**
  - [ ] Publish/tag v1.4.13 after release review; pair with app-composer v1.1.13+ for quote-safe manifest decoding.
- **Completed Recently:**
  - [x] v1.4.13 generated wrappers pass private env files/key manifests into Composer 1.1.15+ resident updater creation; no ACL/migration.
  - [x] v1.4.13 compact Updates tile containment: wrapping rows, break-safe image names, bounded baked/target badges, regression coverage, docs/changelog; no migration.
  - [x] v1.4.13 quote-safe project manifest build contract in generated Dockerfile/docs; raw JSON remains Composer-compatible; no migration.
  - [x] v1.4.12 optional project image release manifest: normalized state/UI notes, display-version fallback chain, runtime-target separation, Docker/Compose scaffold labels, docs/changelog/tests; no migration.
  - [x] v1.4.11 archive-file validation visibility + declarative client size limit with concise release manifest notes; no migration.
  - [x] v1.4.10 resizable Dlux table columns: default-on toggle, visible dividers, fixed-footprint proportional rebalancing, nowrap-cell ellipsis, pointer+keyboard+RTL controls, responsive persistence, per-table opt-out, docs/changelog/manifest; no migration.
  - [x] v1.4.9 updater review re-check, Caddy `.proxy/` scaffold parity, Composer self-exclusion/events, image-dialog target fix, token-matched image-handoff ack recovery, and automatic maintenance-page return; no migration.
  - [x] v1.4.8 permanent skip-a-version and failed-version retry guard; migration `0010` for `DluxUpdateState.skipped_versions`.
  - [x] v1.4.7 alert auto-hide opt-in, no-op activity-log suppression, project image target/version badges, and notification progress-only polling.

### One-line info about last verified Tests:
- 2026-07-22: v1.4.13 full suite GREEN: 839 tests including scaffold secrets handoff and compact updater-row containment; migration/manifest/diff checks GREEN; browser visual unavailable.
- 2026-07-18: v1.4.12 full suite GREEN: 838 tests; migration drift, manifest validator, and diff check GREEN.
- 2026-07-18: v1.4.11 full suite GREEN: 835 tests; manifest JSON + validator GREEN.
- 2026-07-18: full suite GREEN via `.venv/bin/python dlux/tests/test_all.py`: 834 tests; focused table 25 GREEN including resized nowrap-cell containment; migrations unchanged; manifest v1.4.10 valid; `git diff --check` clean.
- 2026-07-18: live pointer/viewport browser validation unavailable; keep sticky on/off plus RTL/LTR drag check before release.

### One-line info about last time edited Docs:
- 2026-07-22: `docs/inline-updater.md` documents Composer 1.1.15 automatic private-secrets handoff and legacy ACL fallback.
- 2026-07-18: table docs specify visible dividers, proportional containment/persistence, and nowrap-cell ellipsis after resizing.

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
