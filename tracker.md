# Project Tracker (django-lux)

## Part 1: Project Related
### Current Verified Snapshot:
- Package version source: unreleased `dlux/VERSION` = `1.2.3` (v1.2.2 already tagged/published); `dist/` is absent in this checkout.
- DjangoLux is a Django UX/application framework: `dlux_settings()`, `SystemSettings`, setup wizard, scoped models, user/security, navigation, reports, backup, scaffolding, optional SSO.
- Core resolver flow: `dlux.system` defaults/schema/registry -> `DLUX_CONFIG` -> DB `SystemSettings` -> normalized request/user/runtime context -> backend-enforced views/helpers.
- v1.2.1 published successfully on 2026-06-22; PyPI briefly served stale v1.2.0 project/Simple gzip cache data while version-specific files and the fresh Simple JSON variant already exposed v1.2.1.
- Unreleased v1.2.2 includes the generated-Compose inline updater activation release: persistent version volume, verified queue, admin UI/API, rollback, bootstrap CLI, and release manifest/CI gate.

### Current Project Adopted Standards:
- Settings integration: `from dlux.utils import dlux_settings`; `dlux_settings(globals())`; mount `dlux.urls` at root for `/accounts/` and `/sys/`.
- Settings source of truth: use `dlux.system` for constants/defaults/normalizers/schema/registry; only `dlux.models.default_*_config` wrappers remain as migration-history shims.
- DSRP-1 (`docs/security-dsrp-1.md`): backend authorization must match UI visibility; POST-only security mutators.
- Runtime UI uses one `dlux` prefix for authored CSS/data/events/JS globals; avoid inline runtime JS/CSS except approved JSON/dynamic-font bridges.
- User-facing copy routes through Dlux translations (`DLUX_STRINGS`) and must stay language/direction/theme aware.

### Adopted Standards' rules and policies:
- Maintain `tracker.md` as the brief live source of state, <=100 lines total, and update it after state/docs/tests changes.
- Changelog uses newest `## vX.Y.Z` sections and flat bold-title bullets; released/tagged sections are immutable.
- Preserve user changes and avoid destructive git commands unless explicitly requested.

### Cross-Cutting Audits if any:
- 2026-06-13: Conceptual survey covered docs, `dlux/`, split utils, views/forms/templates/static, backup/reports, tests, scaffolding, SSO, and viewer.
- 2026-06-23: Documentation audit reconciled 24 Markdown files plus generated README templates with v1.2.2 models, routes, settings schema, wizard, scaffold, updater, and release contract.

### Current Project's Unsolved Known Bugs:
- Fallback file/download redirects should remain reviewed in high-risk deployments; current `_safe_referer()` uses allowed-host checks.
- Mounted `test` compose stores sessions in Redis default cache; do not run live `cache.clear()` probes because that deletes browser sessions.

### Incomplete Tasks:
- **Priority 1:**
  - [ ] Browser-validate setup Step 10 (Logging) grid hydrate/serialize + audit tab + prune after collectstatic.
- **Priority 2 (deferred from ActivityLog plan):**
  - [ ] Optional: full request-scoped `transaction.on_commit` aggregator with nested-by-relation details + dev-satellite folding (deferred — `on_commit` doesn't fire under the TestCase suite; satellite scan was order-fragile and over-broad. Rolling-window fix shipped instead).
- **Completed Recently:**
  - [x] v1.2.3 `email_config` additions: provider presets (`EMAIL_CONFIG_PROVIDER_PRESETS` + JS prefill), superuser POST-only send-test endpoint/button, and in-app failure-alert recipients (`notify.error(recipients=…, email=False)` + `audit` `email_delivery_failed` log, no mail recursion). Wired through defaults/normalizer/form/clean/import-export/layout/translations(EN+AR)/docs/tests.
  - [x] Hardened the release pipeline: added a `test` gate job to `release.yml` so publish depends on a green suite; fixed `test_updater` attestation test to mock `find_spec` (no longer needs `pypi_attestations` in CI).
  - [x] Completed the v1.2.2 inline-updater release audit and fixed artifact junk, PyPI workflow identity, interpreter-bound attestations, baked/active version separation, rebuild precedence, liveness/health handoff, log redaction, rollback/degraded handling, dirty migration gating, Global Staff polling, and forced-restart recovery.
  - [x] Reconciled all current Markdown and generated-project documentation with v1.2.2 code: 11-step setup/config schema, models/commands/dependencies, themes/assets, split utils, links, release workflow, and verified updater deployment.
  - [x] Implemented plugin-style inline Dlux updates for generated Compose projects: official PyPI/hash/workflow-attestation verification, unchanged dependency/Python + migration-safe gating, staged preflight/backup/maintenance/atomic switching, web+Celery version health, automatic/manual rollback, persistent models, superuser controls, supervisor/volume/nginx scaffold, and guarded existing-project bootstrap.
  - [x] Made Aether's drifting background sheen reverse at eased endpoints instead of resetting its gradient positions, eliminating the visible lighting seam; theme asset cache-busters, docs, v1.2.2 changelog/version, and regression coverage updated.
  - [x] Mirrored first-launch setup headers on the language gate and wizard: title/description now occupy logical start and logo sits opposite (LTR text-left/logo-right; RTL text-right/logo-left); `system_setup.css` `?v=20260621a`; changelog/tests updated.
  - [x] Fixed English first-launch setup gate no-op: global `prevent_double_submit.js` disabled the first named submitter during serialization and stripped `setup_language=en`; helper now uses `event.submitter`, form-state repeat blocking, deferred disabling, and `?v=20260621a`; EN/AR tests/docs/changelog updated.
  - [x] Added localized descriptions for Dlux-owned assignable permissions without help text (reports, backup downloads, sections, activity log) in grouped user/staff permission cards; widget now uses a Dlux codename-to-translation map; docs/changelog/tests updated.
  - [x] Corrected setup language gate semantics: `/sys/setup/` language choice now controls setup UI language/direction only; `default_language` remains editable/save-only in Localization, bound POST rerenders preserve the chosen default radio, and `system_setup.js` is `?v=20260620l`; docs/changelog/tests updated.
  - [x] Fixed titlebar surface selector no-op with post-theme muted/glass overrides; Chrome verified distinct light/dark/neon surfaces; changelog/tests updated.

### One-line info about last verified Tests:
- 2026-06-23: Full `test_all.py` green at 606 (added `EmailConfigNormalizerTests` + 3 send-test endpoint tests) on Django 6.0.6 venv; `django check` + `makemigrations --check` clean. Removed the release-bump brittleness in `test_updater.py`: added `NEWER_VERSION = _newer_version(__version__)` (patch+1) and routed all version-sensitive apply/rollback/interrupt tests through it instead of a hardcoded "1.2.3" placeholder, so future VERSION bumps no longer break them (the `dlux.__version__`-mocked reconcile tests keep their intentional literals). Bumped system_setup.js cache-buster pin to `?v=20260623a`.
- 2026-06-23: Fixed v1.2.2 CI failure in `test_attestation_requires_official_repository_and_workflow` — its positive path implicitly required `pypi_attestations` to be pip-installed (present in dev, absent in CI's `pip install -e .`); now mocks `manifest.importlib.util.find_spec` truthy on the success/wrong-repo assertions so the unit test is environment-independent.
- 2026-06-23: Closed release-gate gap — `release.yml` published to PyPI on tag with no test dependency (only `ci.yml` ran tests, on branch push, unable to block the tag pipeline). Added a matrixed `test` job to `release.yml` and made `build-dist` (thus `publish-pypi`) `need` it, so a failing suite now blocks publish.
- 2026-06-23: Final source audit passed full `test_all.py` (600), focused updater/scaffold tests (35), Django/migration checks, Ruff/compile/pip/diff checks, inline-safe dirty-worktree release gate, and live v1.2.1 PyPI hash + Trusted Publisher attestation verification.
- 2026-06-23: Final v1.2.2 wheel/sdist passed `twine check`/hygiene/content audits, isolated `[updater]` install, Python 3.14 import/dependency checks, new + tagged-v1.2.1 scaffold Compose validation, bootstrap dry-run/apply/reapply preservation, supervisor compile, and nginx syntax.
- 2026-06-22: Seamless Aether sheen passed focused animation/runtime/setup cache-buster regressions (3), `django check`, `makemigrations --check --dry-run`, and `git diff --check`; live Browser verification was unavailable because the browser connection failed before navigation.

### One-line info about last time edited Docs:
- 2026-06-23: Documented email provider presets, send-test button, and in-app failure-alert recipients in `docs/admin-guide.md` (Step 3) and `docs/FEATURES.md`.
- 2026-06-23: Reconciled root/package/generated-project docs with v1.2.2 and documented complete updater architecture, attestation identity, rebuild precedence, recovery/degraded behavior, and interrupted-run handling.

## Part 2: Global
### Global Standard Helpers, Shortcuts, Info, etc.:
- Prefer `rg`/`rg --files` for repository discovery.

### Global Rulesets:
- Keep tracker brief/grounded; changelog/docs updates happen in the same turn as meaningful changes.

### Agent Handoff Rules:
- Read `tracker.md` every turn; preserve user changes; use tag-driven release docs plus version metadata for changelog decisions.

### References and Links:
- Security: `docs/security-dsrp-1.md`; Release: `docs/RELEASING.md`; Concept report: `docs/conceptual-codebase-report.md`.
