# Project Tracker (django-microsys)

## Part 1: Project Related
### Current Verified Snapshot:
- `microsys/VERSION` 2.3.8; `CHANGELOG.md` through v2.3.8 (newest-first), including migration-safe runtime translations.
- Reports use a locale-independent `UserActivityLog.model_key` (migration `0011`) so per-user/overview counts work in non-Latin locales; group/resolve on key, display via `model_name`.
- Single active session: `enforce_single_active_session` evicts a user's other sessions on every login; force-ended devices hit the `/accounts/session-ended/` interstitial.
- 8-step setup/System Settings wizard: identity, languages/translations, access/security, login page, sidebar, navbar, titlebar, appearance/fonts.
- Setup v2.3.6: import fixes, project-scoped export filename, deterministic wizard prep, persistent SMTP notices, live validation markers.

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
  - [ ] Commit the uncommitted v2.3.4-v2.3.6 working-tree changes (setup import/scaffold/MSRP-1).
  - [ ] Browser-validate first-launch setup import end-to-end (file chooser, finish CTA, selector visuals) against a real page.
  - [ ] Harden `microsys/fetcher.py` fallback redirects against missing/local/forged referers.
- **Priority 2:**
  - [ ] Bump `?v=` cache-busters for changed `main.css`/`login.css`/`system_setup.js` and refresh the 3 stale tests.
  - [ ] Implement the validated `microsys/utils.py` split (`utils_split_plan.md`), preserving import contracts.
- **Completed Recently:**
  - [x] Fixed `lazy_translator()` migration churn by returning `MigrationSafeTranslation`, preserving runtime translation while serializing stable English/default values (v2.3.8).
  - [x] Reports-0-in-non-Latin-locale fixed via `model_key` + eligibility guard (v2.3.1, migration `0011`).
  - [x] Single active session + signed-out interstitial (v2.3.2).
  - [x] Setup import corrected + language-preview polish + SMTP warning re-sync + step validation markers (v2.3.6).
  - [x] MSRP-1 inline-style removal (login banner-colour data bridge; interstitial CSS classes) (v2.3.4).
  - [x] Scaffold modernized: image-only compose `web`, `{{ config_package }}` Gunicorn, fuller Docker deps, dev port 90, `django-celery-beat`, composer helper image (v2.3.5); fixed unterminated `BASE_URL` quote in `compose.dev.yml.tmpl`.
  - [x] Tooltip flicker/placement fix (v2.3.6); adaptive titlebar brand so a long title truncates/degrades instead of overlapping home/user-hub, full name via tooltip, avatar-only username ≤575.98px (v2.3.7).

### One-line info about last verified Tests:
- 2026-06-10: `microsys.tests.test_utils.UtilsTests.test_lazy_translator_renders_current_language_but_serializes_stably` OK via archive dev compose; archive `makemigrations --check --dry-run` and `check` OK.

### One-line info about last time edited Docs:
- 2026-06-10: `CHANGELOG.md` updated for v2.3.8 migration-safe translation serialization.

## Part 2: Global
### Global Standard Helpers, Shortcuts, Info, etc.:
- Repo search via ripgrep; verify call sites + host import contracts before refactors.
- Persistent actionable `.alert` UI must set `data-autoclose="false"`; see `docs/reference.md`.

### Global Rulesets:
- Global agent rules now live in `~/.claude/CLAUDE.md` (tracker/CHANGELOG/docs/task discipline).

### Agent Handoff Rules:
- Read `tracker.md` each turn; keep grounded in verified code/runtime or explicit user correction; never revert user changes.

### References and Links:
- Security standard: `docs/security-msrp-1.md`. Utils split plan: `utils_split_plan.md`.
