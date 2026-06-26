# Project Tracker (django-lux)

## Part 1: Project Related
### Current Verified Snapshot:
- v1.2.11 is TAGGED + PUBLISHED on PyPI; manifest now bumped to unreleased v1.2.12 (frontend-only: loading button + updater UX). All v1.2.12 work is uncommitted working-tree on top of the v1.2.11 tag — do NOT file it under v1.2.11.
- `dlux/release-manifest.json` is the version source (now v1.2.12, inline-safe, frontend-only). Migration baseline: `0006` (v1.2.10) adds `SystemBackup.media_included` + `DluxUpdateRun.backup_mode`; no new migrations since.
- v1.2.7 remains the mandatory rebuilt baseline before later manifest-approved inline releases.
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
- 2026-06-23: Updater audit covered artifacts, attestation, dependency/migration gates, supervisor/runtime state, recovery, UI/API, scaffold, nginx, and Compose.
- 2026-06-24: ScanLink has no PDF byte/page cap; generated-project nginx imposes an effective `5M` form-upload ceiling.
- 2026-06-24: Reports audit covered activity-window propagation, Celery backup lifecycle, durable polling/download handoff, media sharing, and nginx response/security behavior.

### Current Project's Unsolved Known Bugs:
- Fallback file/download redirects remain a high-risk-deployment review point; `_safe_referer()` currently enforces allowed hosts.
- Mounted test Compose uses Redis sessions; never use live `cache.clear()` probes because they delete browser sessions.

### Incomplete Tasks:
- **Priority 1:**
  - [ ] Browser-validate setup Step 10 logging grid hydrate/serialize, audit tab, and prune after collectstatic.
- **Priority 2:**
  - [ ] Optional request-scoped `transaction.on_commit` activity aggregator; deferred due TestCase/order fragility.
- **Completed Recently:**
  - [x] v1.2.12 dlux_setup AST fix: `_ensure_settings_block` matched literal `from dlux.utils import dlux_settings` → missed scaffold's combined `from dlux.utils import get_secret, dlux_settings` → appended DUPLICATE block. Now `_settings_block_present` parses AST (import-from dlux.utils + called; handles combined/reordered/aliased/multiline; ignores same-name from other module; literal fallback on SyntaxError). New `test_dlux_setup.py` (added to test_all.py list). Validated offline; not run in Django.
  - [x] v1.2.12 footer disable + link: `footer_enabled` toggle (default on; off hides built-in footer; custom_footer/block still render), `footer_link_text`+`footer_link_url` (URL scheme-validated in normalizer — http(s)/mailto//path only, else no link; label falls back to URL). All `legacy_flat` layout_config (no migration), declared on form w/ single-step preservation (`clean_footer_enabled` step-idx 8, `clean_footer_link_*`), exposed as `APP_CONFIG.appearance.*`, export/import. Strings en+ar. Also fixed `allow_user_home_url` single-step wipe (`clean_allow_user_home_url`, step-idx 2). py_compile clean; tests only assert layout_config keys (safe). Not run in Django.
  - [x] v1.2.12 footer z-index + theme colors + setting move: footer was `z-index:1020` over sidebar `900` → now `var(--dlux-footer-z, 850)` (below sidebar/navbar/modals, above content); expanded sidebar renders in front. Footer default colors derived from theme tokens via `color-mix` (`--hbody` bg, `--htitle`/`--title` text/border) so they flip on dark-based themes instead of a hardcoded white bar; vars still overridable. Moved per-user home override `allow_user_home_url` from Step 11 profile builder → standalone toggle under Home URL in Step 3 (Security); storage unchanged (still `profile_config.allow_user_home_url`): declared BooleanField, seed from config, `build_settings_toggle_field` next to `home_url`, fold back into profile_config in `clean()`. New `help_sys_allow_user_home_url` en+ar. py_compile clean; no test asserts old placement (tests use profile_config storage only). Not run in Django.
  - [x] v1.2.12 release hygiene + fixes: 1.2.11 was already tagged/published (PyPI) — moved the wrongly-filed loading-button changelog bullet OUT of `## v1.2.11` into new `## v1.2.12`, bumped manifest 1.2.11→1.2.12. Loading button now PRESERVES host layout: in-place mode swaps a button's leading `<i>` icon for the spinner (keeps its position/margin classes) + text stays; no icon → prepend small spinner; dropped the flex-center CSS. Updater UX (`updater.js`+`options.html`): green **Finish** dismiss button on success (`dlux_update_finish`); removed misleading root "in progress/completed" status (now only errors); completion toast gated to apply/rollback; **Check** button spins via DluxLoadingButton; status line derived+translated (`dlux_update_ready`/new `dlux_update_up_to_date`). Strings en+ar. JS NOT executed (no node) — user verifies live in decrees (mounted).
  - [x] Loading-button migration #1 (v1.2.11): login + register submit buttons now declarative `data-dlux-loading` (removed bespoke spinner block in `login.js`; helper submit handler gained `checkValidity()` guard). Dynamic-modal AJAX submit (`dynamic_modal/js/main.js`) now uses a `DluxLoadingButton.start()` handle (restore on real error only; validation/navigation discard the busy button via footer rebuild) with a plain-disable fallback. No test asserts old markup (verified). JS not executed (no node). Remaining: scan/updater/2FA.
  - [x] Reusable loading button (v1.2.11): new `window.DluxLoadingButton` helper (`dlux/helpers/loading_button/js/main.js` + `css/main.css`, loaded globally in base.html w/ nonce) consolidates the ~7 bespoke spinner-in-button reimplementations. 4 modes: promise API (`run`/`start`→handle `update/done/error/stop`), declarative submit spinner (`data-dlux-loading`, cooperates w/ prevent_double_submit), declarative task-polling (`data-dlux-loading-start` POST + `-poll`; JSON `{status,progress,message,redirect,error}` until terminal — generalizes scan/updater loops), and custom-event (`data-dlux-loading-event`). aria-busy + min-duration anti-flash + bubbling `dlux:loading:*` events. Strings: added `loading_failed`/`loading_timeout` (reuse `loading`) en+ar. Existing call sites NOT migrated (left working). Verified no JS-scanning/inline-script test trips (external `src` scripts excluded). No node + no Django locally — JS not executed, suite not run. Docs: customization-guide.
  - [x] Scaffold nginx → envsubst template (v1.2.11): config now `.nginx/default.conf.template` (mounted into `/etc/nginx/templates/`, rendered by nginx `envsubst` at start). `server_name ${NGINX_SERVER_NAME}` + `client_max_body_size ${NGINX_MAX_SIZE}` (compose defaults localhost/10M; `.secrets/.env` overrides); `NGINX_ENVSUBST_FILTER:"NGINX_"` preserves `$host`/`$scheme`/etc. FIXED the dangling bit the in-progress edit left: `scaffold.py` mapped source→`.nginx/nginx.conf` but compose mounted `default.conf.template` (mismatch = no server block). Renamed source `default.conf.template.tmpl` (template-in-template: nginx `.template` + scaffold `.tmpl`), old `nginx.conf.tmpl`→`.xpose/`. Updated README.md.tmpl + test_scaffold.py (filename/mount/`NGINX_*` asserts). `enable-updater` still targets legacy `.nginx/nginx.conf` (upgrades old projects) — left intentionally. Bonus: fixed adjacent compose typo `POSTGRES_DB:"${POSTGRES_DB:-project_slug}"`→`"${POSTGRES_DB:-{{project_slug}}_db}"`. py_compile clean; NOT run in Django (no local venv). Could not diff vs `../decrees` — macOS TCC blocks the sibling path.
  - [x] Delete permission re-enabled + context-menu gating (v1.2.11): removed the `codename__regex=r'^(delete_)'` exclusion in `get_assignable_permissions_queryset()` (`forms.py`) so `delete_<model>` is now assignable (auth user/group/permission + non-whitelisted dlux models still excluded; `section` model stays the exception). Row context-menu Delete entry already carried `delete_<model>` perm and is filtered by `filter_context_actions`; backend delete view already returns 403 without it — so grant is the single control point. Fixed DSRP-1 leak: `manage_sections` override in `filter_context_actions` (`utils/crud.py`) now only applies to actions flagged `section_action:True`, never bypassing per-model delete/change. Tests added in `test_permissions_ui.py` (assignable delete + context-menu gating + manage_sections non-bypass). py_compile clean; NOT yet run in Django (no local venv). Docs: admin-guide, security-dsrp-1.
  - [x] Global footer + admin footer_text (v1.2.11): reusable faint copyright/credit strip — `dlux/includes/footer.html` + `dlux/main/css/footer.css`, `{% block footer %}` in `base.html`. Fixed bottom, .68rem, muted theme-aware, semi-transparent blur, `pointer-events:none`, z-index 1020, `:empty` collapses. Footer text is now a runtime layout setting: `footer_text` on the `layout` schema group (legacy_flat → `layout_config`-backed property, NO migration), editable in System Settings → Themes&Typography → Footer; normalized in `normalize_layout_config` (`LAYOUT_FOOTER_TEXT_MAX_LENGTH=300`), exposed as `APP_CONFIG.appearance.footer_text`, flat export/import. Form: `footer_text` CharField + `clean_footer_text` single-step preservation + Meta.fields + save payload. Resolution: `footer` block → `custom_footer.html` → admin footer_text → `DLUX_STRINGS.footer_text` → `© <year> <display_name>`. Strings en+ar. py_compile clean; NOT yet run in Django (no local venv). Issue #2 (global form assets) already shipped. Docs: customization-guide, reference.
  - [x] Older released items (v1.2.4–v1.2.11: dlb-viewer inline/relations/full-width, test isolation, backup scope `0006`, updater hardening, etc.) — see CHANGELOG.

### One-line info about last verified Tests:
- 2026-06-26: CI run (633 tests) had ONE failure — `test_startproject_creates_expected_files` asserted `.env` had 12 non-empty lines but it now has 15 (the 3 `NGINX_*` envsubst vars). Fixed: count→15 + added `NGINX_PORT/SERVER_NAME/MAX_SIZE` assertIns. The test died at the count (line 127) BEFORE the new nginx/compose asserts (131+), so those went unvalidated by CI; re-validated all 16 substrings by rendering the templates directly (`{{ }}` string-replace, no Django) — all pass. No local Django env, so re-run the suite in CI to confirm green.
- 2026-06-24: v1.2.11 — full suite 631 OK; supervisor test now derives baked version from `importlib.metadata` (not `__version__`), verified robust under a simulated manifest/metadata mismatch (manifest 1.2.99 vs installed 1.2.11); `protected/dlux/` empty, no stray `.dlb`.
- 2026-06-24: v1.2.10 venv full suite passed 631 (added 2 relation-schema backup tests); `makemigrations --check` clean; dlb-viewer `go test ./...` (5 label/handler tests) + `go vet`/`gofmt` clean; live E2E on a real `.dlb` resolved FK names.
- 2026-06-24: v1.2.9 source-installed full suite passed 624; focused backup 28/notification+backup 40, JS/compile/migration/inline gate/nginx/diff clean; wheel/sdist passed `twine`.

### One-line info about last time edited Docs:
- 2026-06-26: `docs/customization-guide.md` — new "Loading Buttons" section (`DluxLoadingButton`: promise API, submit spinner, task-polling JSON contract, custom-event, `data-dlux-loading-*`).

## Part 2: Global
### Global Standard Helpers, Shortcuts, Info, etc.:
- Prefer `rg`/`rg --files` for discovery; inspect durable updater runs through the database, not web access logs alone.

### Global Rulesets:
- Keep tracker/changelog/docs synchronized with verified code and executed checks.

### Agent Handoff Rules:
- Read `tracker.md` every turn; preserve user work; use tag state plus release manifest before changelog/version edits.

### References and Links:
- Security: `docs/security-dsrp-1.md`; updater: `docs/inline-updater.md`; release: `docs/RELEASING.md`.
