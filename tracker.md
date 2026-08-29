# Project Tracker (django-lux) [Max 100 lines total]

## Part 1: Project Related
### Current Verified Snapshot:
- Source manifest is v1.8.2; all release gates pass and tag/push is pending.
- Generated Compose stacks use Composer agent/executor/proxy services; `dlux-updater` is retired. Celery `pre_start` runs reconcile/migrator and Celery Beat writes the state tick.
- Canonical runtime settings are `homepage_config` and `search_config`; legacy keys remain v1.x mirrors.

### Current Project Adopted Standards:
- Integrate settings with `from dlux.utils import dlux_settings; dlux_settings(globals())`; mount `dlux.urls` at root.
- Use Dlux-native UI primitives and feature-first static layout; backend authorization must match UI visibility and mutations are POST-only.
- `dlux.system` owns settings defaults/schema/normalizers; migration-history wrappers remain in `dlux.models`.
- Settings steps order controls per section: toggles, then selectors, then fields, then builders; a field sits in the step its subject belongs to, not its storage group.

### Adopted Standards' rules and policies:
- Read/update this tracker each turn; retain under 100 lines. Use `apply_patch` for edits and preserve user work.
- Check tags before changelog edits; tagged versions are immutable. Change code/config/docs and their changelog together.
- Never delete files; move superseded material into `.xpose/` with its relative path.

### Cross-Cutting Audits if any:
- Import-cycle and template/render-cost guards remain active; do not replace function-scope imports blindly.
- Generated deployment docs must reflect Compose 5.3+ `pre_start`, Composer external execution, and the retired updater service.

### Current Project's Unsolved Known Bugs:
- Inline updates require a writable runtime volume; no fallback path is valid.

### Incomplete Tasks:
- **Priority 1:**
  - [ ] Tag and publish Dlux v1.8.2 after the verified release commit.
  - [ ] Finish framework promotion from dlux-crm-gov's `common` app; only the generic list-page decision remains.
  - [ ] 4/4 Generic list page: `dlux/templates/dlux/list_base.html` supplies filter assets only — no content block, header, Add button or `render_table` — so dlux's own five list screens (`manage_users`, `activity_log`, `group_manager`, `scope_manager`, `manage_sections`) each hand-roll one. Decide whether dlux takes an opinion on list layout; if yes, promote `ScopedListView` + `scoped_list.html` on top of the Ribbon (which now owns the header/filter/actions band).
  - [ ] Review live Docker staging acceptance for Composer migration and `dlux_check --apply`.
- **Priority 2:**
  - [ ] System Settings > Login Page > Full-page split: EN/AR hero-message textareas reuse the active UI language's empty Markdown placeholder, so both show Arabic under an Arabic UI (and both English under an English UI). Cosmetic only; resolve per field and preserve configured language order.
  - [ ] Postponed 2026-08-28: keep stale-route pruning import-only; revisit builder-save pruning only if an actual stale-entry problem appears.
  - [ ] Finish `forms/system_settings.py` group extraction behind existing contracts.
- **Completed Recently:**
  - [x] System Settings image uploads now persist immediately, select their returned managed-asset ID, and update every compatible open picker; the setup-allowed endpoint works before initial configuration (2026-08-28).
  - [x] Initial setup no longer marks untouched Identity/Login steps invalid (2026-08-28): step validation ignores empty hidden Dlux file-widget feedback while retaining visible non-empty server errors.
  - [x] Public Page naming and dependent state aligned (2026-08-28): current UI/docs use Public Page / الصفحة العامة, storage keys remain `public_root`, and nested selectors clear disabled visuals when the master is enabled.
  - [x] Asset Manager split into fixed Images/Fonts Ribbon tabs (2026-08-28): Images has footer-triggered batch upload, image-only cards, inline title edits, and guarded deletion; Fonts has two metadata rows, a full-width file row, and a family/variant inventory; modal navigation and POST refresh retain the selected tab.
  - [x] Ribbon child strips are scoped to the active parent queryset (2026-08-28): `relation: child` now hides incompatible generated tabs for both choice and relation sources, including Settings-created extra strips.
  - [x] Ribbon builder split saved shape finalized (2026-08-28): pre-defined strips Restore/Remove, admin extra strips Remove only, pre-defined removal stores `enabled: false`, extra strips append separately, and old direct strip config is dropped.
  - [x] Ribbon builder add-extra regression fixed (2026-08-28): extra strip render loop now passes `strip`, so adding a second Parties strip no longer clears the builder.
  - [x] Ribbon adopted across Dlux screens with multi-strip nesting; declared overlays/removals and admin extra strips use the final unreleased split shape (2026-08-28).
  - [x] Row-level ownership and list-page tabs were promoted from gov `common`; downstream patches and `TabbedListMixin` were retired (2026-08-27).
  - [x] Documentation reorganization passed targeted Django docs tests, JSON parsing, Markdown-link checks, and `git diff --check` (2026-08-27).

### One-line info about last verified Tests:
- 2026-08-29: Full package suite passed 2160 tests with 2 expected skips; all 85 test modules are included in the CI runner.
- 2026-08-29: Full browser suite passed 106 tests and standalone builder JavaScript passed 41 tests.
- 2026-08-29: Migration dry-run, schema-2 release check, wheel/sdist build, artifact contents, `twine check`, and `git diff --check` pass.

### One-line info about last time edited Docs:
- 2026-08-29: Release, Ribbon, managed-assets, Public Page, settings, and integration documentation reflects v1.8.2.

## Part 2: Global
### Global Standard Helpers, Shortcuts, Info, etc.:
- Prefer `rg`; run generated Compose commands through `./start.sh`; inspect updater state through DB/runtime records, not web logs.

### Global Rulesets:
- Keep tracker, docs, and changelog grounded in verified code/runtime behavior.

### Agent Handoff Rules:
- Move/rename public paths only after downstream-usage checks; record compatibility shims in `docs/deprecation-countdown.md`.

### References and Links:
- Deployment: `docs/inline-updater.md`, `docs/composer-agent.md`, `docs/doctor.md`; settings: `docs/adding-system-settings.md`.
