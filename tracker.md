# Project Tracker (django-microsys)

## Part 1: Project Related
### Current Verified Snapshot:
- `microsys/VERSION` 2.3.4; root `CHANGELOG.md` current through v2.3.4 (newest-first).
- Reports use a locale-independent `UserActivityLog.model_key` (migration `0011`) so per-user/overview counts work in non-Latin locales; group/resolve on key, display via `model_name`.
- Single active session: `enforce_single_active_session` evicts a user's other sessions on every login; force-ended devices hit the `/accounts/session-ended/` interstitial.
- 8-step setup/System Settings wizard: identity, languages/translations, access/security, login page, sidebar, navbar, titlebar, appearance/fonts.
- Setup-file import now restores `login_config` + `registration_activation_mode`; choice-selectors re-sync on import; a redacted SMTP secret blocks "Finish" until re-entered.

### Current Project Adopted Standards:
- Settings: `from microsys.utils import microsys_settings`; `microsys_settings(globals())`. Scaffold: `python -m microsys startproject/startapp --register`.
- Page entrypoints: `microsys/form_base.html`, `microsys/list_base.html`. Helpers: `require_current_password`, `build_archive_file_field`, `build_settings_toggle_field`.
- MSRP-1 (`docs/security-msrp-1.md`) is the active security contract for runtime-exposed surfaces.

### Adopted Standards' rules and policies:
- Backend authorization must match UI visibility; hidden controls are not authorization. State-changing security flows are POST-only.
- No inline CSS/`style=`/executable inline JS in runtime HTML — use external assets + `data-*`/`json_script` bridges (nonce only for unavoidable dynamic CSS).
- All user-facing copy via the Microsys translation framework; no hardcoded EN/AR literals in Python/templates/JS. Stay theme/language/direction aware.

### Cross-Cutting Audits if any:
- 2026-06-10: template inline-style/script audit clean (only nonce'd dynamic-fonts `<style>` and `application/json` data blocks remain).

### Current Project's Unsolved Known Bugs:
- Prod 403 at `forms.eidc.gov.ly` is a deployment CSRF config issue (HTTPS host missing from `CSRF_TRUSTED_ORIGINS` / no `SECURE_PROXY_SSL_HEADER`), not microsys code — pending host env fix (`BASE_URL=https://…`, `DEBUG_STATUS=False`, proxy `X-Forwarded-Proto: https`).
- `microsys/fetcher.py` fallback download/export still trusts raw `HTTP_REFERER`.
- 3 stale `test_defaults_and_urls` tests (outdated `?v=` cache-busters in `base.html`/`dynamic_modal.html`; brittle `system_setup.css` string assertions) — code is compliant; tests need updating/cache-bumps.

### Incomplete Tasks:
- **Priority 1:**
  - [ ] Commit the uncommitted v2.3.4 working-tree changes (setup-import + MSRP-1).
  - [ ] Browser-validate wizard import (login_config, activation mode, selector re-sync, SMTP-password notice) — not exercised by Python tests.
  - [ ] Harden `microsys/fetcher.py` fallback redirects against missing/local/forged referers.
- **Priority 2:**
  - [ ] Bump `?v=` cache-busters for changed `main.css`/`login.css`/`system_setup.js` and refresh the 3 stale tests.
  - [ ] Implement the validated `microsys/utils.py` split (`utils_split_plan.md`), preserving import contracts.
- **Completed Recently:**
  - [x] Reports-0-in-non-Latin-locale fixed via `model_key` + eligibility guard (v2.3.1, migration `0011`).
  - [x] Single active session + signed-out interstitial (v2.3.2).
  - [x] Setup-file import: login_config + activation mode + selector double-select + SMTP-secret awareness (v2.3.4).
  - [x] MSRP-1 inline-style removal (login banner-colour data bridge; interstitial CSS classes) (v2.3.4).

### One-line info about last verified Tests:
- 2026-06-10: `test_views` 131 OK, `test_middleware` 25 OK, `test_defaults_and_urls` import/login_config tests OK (3 pre-existing stale failures unrelated to code).

### One-line info about last time edited Docs:
- 2026-06-10: `CHANGELOG.md` updated to v2.3.4; active standard remains `docs/security-msrp-1.md`.

## Part 2: Global
### Global Standard Helpers, Shortcuts, Info, etc.:
- Repo search via ripgrep; verify call sites + host import contracts before refactors.

### Global Rulesets:
- Global agent rules now live in `~/.claude/CLAUDE.md` (tracker/CHANGELOG/docs/task discipline).

### Agent Handoff Rules:
- Read `tracker.md` each turn; keep grounded in verified code/runtime or explicit user correction; never revert user changes.

### References and Links:
- Security standard: `docs/security-msrp-1.md`. Utils split plan: `utils_split_plan.md`.
