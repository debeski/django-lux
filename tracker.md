# Project Tracker (django-lux) [Max 100 lines total]

## Part 1: Project Related
### Current Verified Snapshot:
- Source manifest is v1.8.1 (unreleased documentation update); v1.8.0 is the latest tag.
- Generated Compose stacks use Composer agent/executor/proxy services; `dlux-updater` is retired. Celery `pre_start` runs reconcile/migrator and Celery Beat writes the state tick.
- Canonical runtime settings are `homepage_config` and `search_config`; legacy keys remain v1.x mirrors.

### Current Project Adopted Standards:
- Integrate settings with `from dlux.utils import dlux_settings; dlux_settings(globals())`; mount `dlux.urls` at root.
- Use Dlux-native UI primitives and feature-first static layout; backend authorization must match UI visibility and mutations are POST-only.
- `dlux.system` owns settings defaults/schema/normalizers; migration-history wrappers remain in `dlux.models`.

### Adopted Standards' rules and policies:
- Read/update this tracker each turn; retain under 100 lines. Use `apply_patch` for edits and preserve user work.
- Check tags before changelog edits; tagged versions are immutable. Change code/config/docs and their changelog together.
- Never delete files; move superseded material into `.xpose/` with its relative path.

### Cross-Cutting Audits if any:
- Import-cycle and template/render-cost guards remain active; do not replace function-scope imports blindly.
- Generated deployment docs must reflect Compose 5.3+ `pre_start`, Composer external execution, and the retired updater service.

### Current Project's Unsolved Known Bugs:
- `test_groups` has two isolated 302 failures before configured-settings cache state exists.
- Inline updates require a writable runtime volume; no fallback path is valid.

### Incomplete Tasks:
- **Priority 1:**
  - [x] Validate the documentation reorganization with targeted Django docs tests, JSON parsing, Markdown-link checks, and `git diff --check`.
  - [ ] Review live Docker staging acceptance for Composer migration and `dlux_check --apply`.
  - [ ] Decide whether builder save (`clean_sidebar_config`) should prune stale routes too, or stay import-only.
- **Priority 2:**
  - [ ] Finish `forms/system_settings.py` group extraction behind existing contracts.
- **Completed Recently:**
  - [x] Import now prunes sidebar/navbar entries naming routes absent from the URLconf (`known_route_names`, `drop_unknown_routes`) (2026-08-19).
  - [x] Replaced stale v1.2.5 Features inventory and split admin/customization documentation into focused v1.8.1 references (2026-08-18).

### One-line info about last verified Tests:
- 2026-08-19: Full `django test dlux` run passed (1778 tests, 2 skipped) after adding `StaleRouteImportPruningTests` and re-pointing two `test_defaults_and_urls` cases at real routes.

### One-line info about last time edited Docs:
- 2026-08-19: `system-configuration.md` navigation section and `adding-system-settings.md` import pipeline document stale-route pruning on import.

## Part 2: Global
### Global Standard Helpers, Shortcuts, Info, etc.:
- Prefer `rg`; run generated Compose commands through `./start.sh`; inspect updater state through DB/runtime records, not web logs.

### Global Rulesets:
- Keep tracker, docs, and changelog grounded in verified code/runtime behavior.

### Agent Handoff Rules:
- Move/rename public paths only after downstream-usage checks; record compatibility shims in `docs/deprecation-countdown.md`.

### References and Links:
- Deployment: `docs/inline-updater.md`, `docs/composer-agent.md`, `docs/doctor.md`; settings: `docs/adding-system-settings.md`.
