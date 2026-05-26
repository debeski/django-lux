# Project Tracker (django-microsys)

## Part 1: Project Related
### Current Verified Snapshot:
- Verified 2026-05-25: critical/high performance remediation added user/activity eager loading, permission-form query helpers, and versioned sidebar caching.
- Package version markers include `microsys/VERSION` 2.2.7; changelog now has unreleased/next `v2.2.8` performance notes.
- System setup/System Settings uses seven steps: identity, languages/translations, access/security, sidebar, navbar, titlebar, appearance/fonts.
- Dynamic fonts, runtime theme allowlisting, optional Nav Bar, Titlebar logo treatments, shared tooltips, and User Existence Report are active feature areas.
- DynamicModal loading keeps the existing AJAX contract; real previous content is a covered sizing fallback, empty loads use a self-contained skeleton.
- Theme picker surfaces include Aether/Mono polish; Prism/Aether cover archive file widgets, titlebar logo treatments, and Aether Options System Settings tiles.

### Current Project Adopted Standards:
- Preferred settings integration: `from microsys.utils import microsys_settings`; `microsys_settings(globals())`.
- Preferred scaffolding: `python -m microsys startproject ...`; `python -m microsys startapp ... --register`.
- Preferred page entrypoints: `microsys/form_base.html`, `microsys/list_base.html`.
- Preferred helpers include `require_current_password`, `build_archive_file_field`, `build_settings_toggle_field`, `set_profile_totp_state`.

### Adopted Standards' rules and policies:
- Backend authorization must match protected UI visibility; hidden controls are not authorization.
- Keep Microsys defaults framework-neutral unless behavior is an explicit framework contract.
- Prefer additive helpers/templates/extension points over project-rewriting behavior.
- New/revised user-facing copy must use Microsys translations; avoid inline CSS/JS unless unavoidable.
- django-microsys must remain theme, language, and direction aware through built-in systems.

### Cross-Cutting Audits if any:
- Prior audits covered CSP cleanup, setup toggles, permissions UI filtering, modal JSON tolerance, staff-tier surfaces, packaged exclusions.
- Browser/manual coverage remains incomplete for mounted setup flows, Options selectors, sidebar/titlebar runtime behavior, and POST-only 2FA flows.

### Current Project's Unsolved Known Bugs:
- Live confirmation pending for Step 2 matrix source fix, Options font highlight, Step 6 disabled-theme preview, theme-switch veil/flicker, Aether theme, and collapsed Icons Only sidebar.
- First-launch setup has a mismatch between sidebar-toolbar removal warning and Options modal behavior.
- Mounted-app System Settings Step 3 modal save returned HTTP 400 while local full modal POST returned 200.
- `microsys/fetcher.py` fallback download/export redirects still trust raw `HTTP_REFERER`.

### Incomplete Tasks:
- **Priority 1:**
  - [ ] Implement validated `microsys/utils.py` split using `utils_split_plan.md`, preserving `microsys.utils` compatibility exports and `toggle_sidebar` wiring.
  - [ ] Browser-check Nav Bar, Aether, sidebar collapsed Icons Only, Options font highlight, Step 6 preview, tooltips, theme-switch veil, and Profile confirm-password flows.
  - [ ] Capture live Step 3 System Settings modal HTTP 400 JSON/log details if it still reproduces.
  - [ ] Harden `microsys/fetcher.py` fallback redirects for missing/local/forged external referers.
- **Priority 1 browser validation:**
  - [ ] Setup/System Settings wizard, Options persistence/selectors, pre-setup guard, 2FA flows, trusted devices/sessions, User Report modal/XLSX, staff-tier surfaces.
- **Priority 2:**
  - [ ] Validate generated `startproject`, generated `startapp --register`, Docker/Celery/health baseline, and optional SSO provider/client dependencies.
- **Completed Recently:**
  - [x] Added mandatory MSRP-1 compliance language to root `SECURITY.md`.
  - [x] Added root GitHub governance docs: `SECURITY.md`, `CONTRIBUTING.md`, and `CODE_OF_CONDUCT.md`.
  - [x] Added critical/high performance fixes for UserListView, Activity Log relation access, permission-form filtering, and sidebar discovery/render caching.
  - [x] Added Prism/Aether archive file widget and titlebar logo treatment overrides; extended Options System Settings tile theme coverage to Aether.
  - [x] Updated Mono shared theme preview swatch to a clean light diagonal split without a dark ribbon.
  - [x] Added missing Aether theme preview swatch surface in `template_cleanup.css` and bumped base asset version.

### One-line info about last verified Tests:
- 2026-05-26: `git diff --check` and trailing-whitespace scan passed for governance docs including MSRP-1 policy note; runtime tests not run.

### One-line info about last time edited Docs:
- 2026-05-26: updated `SECURITY.md` to require MSRP-1 compliance for security-sensitive work.

## Part 2: Global
### Global Standard Helpers, Shortcuts, Info, etc.:
- Use `rg`/`rg --files` first for repo search; use `apply_patch` for manual edits.
- Before refactors, verify call sites and package import behavior; preserve host-project import contracts unless intentionally versioned.

### Global Rulesets:
- Maintain `tracker.md` as live state under 100 total lines.
- Maintain root `CHANGELOG.md` for implemented features, fixes, milestones, and critical config changes.
- Update technical docs in the same turn as feature/env/schema/API/security/install changes.

### Agent Handoff Rules:
- Read `tracker.md` at the start of every turn; keep it compact and grounded in verified code/runtime behavior or explicit user corrections.
- Do not revert user changes; ignore unrelated dirty worktree changes.
- For code review requests, lead with findings ordered by severity and include file/line references.

### References and Links:
- Active security standard: `docs/security-msrp-1.md`.
- Current utils split planning doc: `utils_split_plan.md`.
