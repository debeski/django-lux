# Project Tracker (django-lux)

## Part 1: Project Related
### Current Verified Snapshot:
- REBRAND PUBLISHED per user correction: `django-microsys`→`django-lux` is complete and published to git/PyPI; package imports as `dlux`, app_label/db use `dlux_*`, config is `DLUX_CONFIG`, CLI is `dlux`, backups are `.dlb`/`DLB1`, migrations squashed to `0001_initial`.
- `dlux/VERSION` is the release source of truth (`1.0.1` in current tree); GitHub Actions tag-driven release flow owns dist build + PyPI/GitHub publishing. Do not use the old local `dist/` changelog rule.
- Default branding is SVG-first: `base_logo.svg` and `login_logo.svg` are the active graphite/crimson DjangoLux mark/wordmark; WebP files remain compatibility artifacts.
- Migration helper from microsys is included: `dlux_migrate_from_microsys` dry-runs by default and can relabel a fully migrated `django-microsys` 2.4.1 DB to `django-lux`.
- Standalone `tools/dlb-viewer/` (Go), tag-driven CI/CD, and `optional_packages/`→`tools/` reorg remain current.
- Restore = full replace: migration-state gate, dependency-ordered load, `suspend_dlux_signals()`, sequence reset, file restore, cache+session flush. `.dlb` uses Django `SECRET_KEY` by default or optional passphrase; `/sys/options/` superuser Backup & Restore card shows latest backup/restore summary.

### Current Project Adopted Standards:
- Settings: `from dlux.utils import dlux_settings`; `dlux_settings(globals())`. Scaffold: `python -m dlux startproject/startapp --register`.
- Page entrypoints: `dlux/form_base.html`, `dlux/list_base.html`. Helpers: `require_current_password`, `build_archive_file_field`, `build_settings_toggle_field`.
- MSRP-1 (`docs/security-msrp-1.md`) is the active security contract for runtime-exposed surfaces.

### Adopted Standards' rules and policies:
- Backend authorization must match UI visibility; hidden controls are not authorization. State-changing security flows are POST-only.
- No inline CSS/`style=`/executable inline JS in runtime HTML — use external assets + `data-*`/`json_script` bridges (nonce only for unavoidable dynamic CSS).
- All user-facing copy via the Dlux translation framework; no hardcoded EN/AR literals in Python/templates/JS. Stay theme/language/direction aware.

### Cross-Cutting Audits if any:
- 2026-06-10: template inline-style/script audit clean (only nonce'd dynamic-fonts `<style>` and `application/json` data blocks remain).

### Current Project's Unsolved Known Bugs:
- Prod 403 at `forms.eidc.gov.ly` is a deployment CSRF config issue (HTTPS host missing from `CSRF_TRUSTED_ORIGINS` / no `SECURE_PROXY_SSL_HEADER`), not dlux code — pending host env fix (`BASE_URL=https://…`, `DEBUG_STATUS=False`, proxy `X-Forwarded-Proto: https`).
- `dlux/fetcher.py` fallback download/export still trusts raw `HTTP_REFERER`.
- `test_defaults_and_urls.py` still needs harness/assertion cleanup: some cache-buster/string checks are stale, and targeted `DluxDefaultRouteTests` hit missing `dlux_systemsettings` table because `SimpleTestCase.setUp()` touches DB.

### Incomplete Tasks:
- **Priority 1:**
  - [ ] Sweep stale rebrand leftovers: search docs/code/assets for obsolete `microsys`, `django-microsys`, `ms-`, old logos, and package metadata inconsistencies.
  - [ ] Consolidate tests for CI: make `test_m2m`/`test_scaffold`/`verify_detailed_logs` standalone (drop `xPy.settings` dep) + fix `test_defaults_and_urls`, then mark CI a required check.
  - [ ] Commit the uncommitted v2.3.4-v2.3.6 working-tree changes (setup import/scaffold/MSRP-1).
  - [ ] Browser-validate first-launch setup import end-to-end (file chooser, finish CTA, selector visuals) against a real page.
  - [ ] Harden `dlux/fetcher.py` fallback redirects against missing/local/forged referers.
- **Priority 2:**
  - [ ] Bump `?v=` cache-busters for changed `main.css`/`login.css`/`system_setup.js` and refresh the 3 stale tests.
  - [ ] Implement the validated `dlux/utils.py` split (`utils_split_plan.md`), preserving import contracts.
- **Completed Recently:**
  - [x] Fixed SSO companion release builds: `release-sso*.yml` now call companion `build.py` helpers; helpers invoke PyPA `build` from repo root to avoid local `build.py` shadowing/recursive `python -m build` exit 143.
  - [x] Replaced stale default branding with SVG-first DjangoLux logo assets and switched README/default config/titlebar/favicon/login-mask fallbacks to the new mark.
  - [x] Rebrand publish: `django-lux` package/repo/PyPI release completed per user correction; local release docs use GitHub Actions tag-driven publishing, not `dist/` checks.
  - [x] Standalone `.dlb` viewer: `tools/dlb-viewer/` — dependency-free Go single-binary, stdlib-only Fernet/PBKDF2 (`dlb.go`), local 127.0.0.1 web UI (token+Host guard), browse models/files/manifest; verified end-to-end vs a real Fernet fixture. Build needs Go 1.21+ (installed via brew).
  - [x] Full System Backup & Restore (v2.4.0): encrypted `.dlb`, optional passphrase, superuser-password omission, full-replace restore, `/sys/backup/` UI/static JS, `/sys/options/` summary card, Celery tasks.
  - [x] v2.4.0 reports backup rework: window filter + constant-memory zip streaming + Celery task with sync fallback; prune to last 3 per user.
  - [x] SMTP socket timeout (default 10s, `email_config['timeout']`) in `send_dlux_mail`.
  - [x] Fixed `lazy_translator()` migration churn via `MigrationSafeTranslation` (v2.3.8); `model_key` reports fix (`0011`); single active session (v2.3.2); setup import fixes (v2.3.6); MSRP-1 (v2.3.4); scaffold (v2.3.5); titlebar (v2.3.7).

### One-line info about last verified Tests:
- 2026-06-12: companion builds verified in temp venv: `python build.py` + `twine check dist/*` passed for `django-lux-sso` and `django-lux-sso-client`; logo render check also clean.

### One-line info about last time edited Docs:
- 2026-06-12: `docs/RELEASING.md` and CHANGELOG v1.0.1 updated for SSO companion build.py release fix; release docs remain canonical.

## Part 2: Global
### Global Standard Helpers, Shortcuts, Info, etc.:
- Repo search via ripgrep; verify call sites + host import contracts before refactors.
- Persistent actionable `.alert` UI must set `data-autoclose="false"`; see `docs/reference.md`.

### Global Rulesets:
- Global agent rules now live in `~/.claude/CLAUDE.md` (tracker/CHANGELOG/docs/task discipline).

### Agent Handoff Rules:
- Read `tracker.md` each turn; keep grounded in verified code/runtime or explicit user correction; never revert user changes; for changelog/version decisions use tag-driven release docs, not local `dist/` artifacts.

### References and Links:
- Security standard: `docs/security-msrp-1.md`. Release standard: `docs/RELEASING.md`. Utils split plan: `utils_split_plan.md`.
