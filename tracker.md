# Project Tracker (django-lux) [Max 100 lines total]

## Part 1: Project Related
### Current Verified Snapshot:
- Dlux v1.8.3 is tagged/published on PyPI and GitHub Release; workflow run 33624156322 succeeded from commit 6f5b9cd.
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
- 2026-08-31 scoped-model audit: Dlux tenant/user-visible records using row isolation are scoped (`Profile`, `ActivityLog`, notifications/rules/watches); remaining non-scoped concrete tables are global/system/owner-filtered infrastructure, with `GroupProfile.scope` managed manually by preset gates.

### Current Project's Unsolved Known Bugs:
- Inline updates require a writable runtime volume; no fallback path is valid.
- 2026-08-31: `SystemBackupViewTests.test_restore_requires_password_and_confirmation` leaves restore status `pending` in the gov container; isolated from Backup page layout changes.

### Incomplete Tasks:
- **Priority 1:**
  - [ ] Finish framework promotion from dlux-crm-gov's `common` app; only the generic list-page decision remains.
  - [ ] 4/4 Generic list page: dlux ships it, `activity_log` uses it, and gov's three generic lists now extend it through a 3-line `scoped_list.html`. Remaining — decide whether `ScopedListView` itself is promoted; `manage_users`, `manage_sections` and the scope/group fragments stay as they are until touched.
  - [ ] Review live Docker staging acceptance for Composer migration and `dlux_check --apply`.
- **Priority 2:**
  - [ ] System Settings > Login Page > Full-page split: EN/AR hero-message textareas reuse the active UI language's empty Markdown placeholder, so both show Arabic under an Arabic UI (and both English under an English UI). Cosmetic only; resolve per field and preserve configured language order.
  - [ ] Postponed 2026-08-28: keep stale-route pruning import-only; revisit builder-save pruning only if an actual stale-entry problem appears.
  - [ ] Finish `forms/system_settings.py` group extraction behind existing contracts.
- **Completed Recently:**
  - [x] File widget renamed off `project-archive`'s `archive_file` names to `build_file_field` / `file_field_*` / `.dlux-file-*`, with v1.x shims for the two helpers, the old string keys and the `archive-file-input` opt-in class (2026-09-01).
  - [x] `activity_log` is the first screen on `dlux/list_page.html` — 42 template lines to 27, detail modal moved into `list_modals`, table card dropped (2026-09-01).
  - [x] `dlux/list_page.html` promoted from the reference project: Ribbon over table, no card, blocks `list_before_table` / `list_body` / `list_after_table` / `list_modals` / `list_page_attrs`, plus `extra_styles` / `extra_scripts` (2026-09-01).
  - [x] Standalone `manage_sections` now uses a manage-only expandable form above the table: default collapsed, ribbon Add opens create, row Edit opens edit, Cancel returns to table state, invalid POST stays open (2026-09-01).
  - [x] Section Management's expanding form has one dismiss, in its action row; the header X is gone and a form with its own submit gets a cancel-only row (2026-09-01).
  - [x] `Ctrl/Cmd-U` opens User Management, navigating by the rendered Users link like the J/H keys; the three now share one selector table in `user_hub.js` (2026-09-01).
  - [x] Stacked dynamic-modal managers for `is_section` records use section permissions and self-contained modal delete URLs, so custom section tables can expose guarded Delete without model-level delete perms (2026-09-01).

### One-line info about last verified Tests:
- 2026-09-02: v1.8.3 release checks pass: `release_check --base-tag v1.8.2`, JS builder tests 61 OK, translation coverage 4 OK, full `dlux.tests` 2257 OK/2 skips, `/tmp` build + `twine check` OK, GitHub release workflow OK.
- 2026-09-01: `list_page.html` consumed downstream — gov's 3 generic lists render through it with no semantic diff (only the wrapper class changed); `list_page_attrs` carries a host project's own data hooks, which is what kept its `scoped_list.html` from being retired outright.
- 2026-09-01: Gov stack after the file-widget rename — `collectstatic` copied 13 files; Caddy now serves `dlux-file` CSS/JS (23/23, 0 legacy) and every JS `[data-dlux-file-*]` hook is present in the rendered widget (library/scan absent only in their unguarded-off branches).
- 2026-09-01: File-widget rename — 3 new compat tests (shim removed → the template one fails, restored → passes); full `dlux.tests` 2264 run, 1 pre-existing unrelated failure; `node --check` x3 OK.
- 2026-09-01: Activity Log on the list page — new arrangement test plus `test_activitylog`/`test_views`/`test_tables`/`test_ribbon` 436 OK; live page renders wrapper+ribbon+20 rows, modal outside the wrapper; gov `check` and storage 142 OK.

### One-line info about last time edited Docs:
- 2026-09-02: `CHANGELOG.md` v1.8.3 compressed, `dlux/release-manifest.json` summary/highlights/effect fixed, and `docs/FEATURES.md` marked current source v1.8.3.
- 2026-09-01: `docs/deprecation-countdown.md` gained the `archive_file` → `file_field` rename table and its v1.9.0 removal target; `docs/reference.md`/`README.md`/`developer-guide.md` now name `build_file_field`.

## Part 2: Global
### Global Standard Helpers, Shortcuts, Info, etc.:
- Gov stack serves `/static/*` from the `static` volume via Caddy, so changed dlux assets need `collectstatic` in `project-sales-crm/gov_edition` before they reach the browser — and Caddy sends `Cache-Control: immutable, max-age=31536000` on unhashed filenames, so a hard reload is required too.
- Prefer `rg`; run generated Compose commands through `./start.sh`; inspect updater state through DB/runtime records, not web logs.

### Global Rulesets:
- Keep tracker, docs, and changelog grounded in verified code/runtime behavior.

### Agent Handoff Rules:
- Move/rename public paths only after downstream-usage checks; record compatibility shims in `docs/deprecation-countdown.md`.

### References and Links:
- Deployment: `docs/inline-updater.md`, `docs/composer-agent.md`, `docs/doctor.md`; settings: `docs/adding-system-settings.md`.
