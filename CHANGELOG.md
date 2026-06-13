# Changelog

This file owns the release history for `django-lux`.

> `django-lux` is the renamed, actively-maintained successor to
> [`django-microsys`](https://github.com/debeski/django-microsys) (now archived).
> Release history prior to v1.0.0 lives in that archived repository.

## v1.0.3

- **Utils Package Modular Split**: Reorganized the 4,286-line monolithic
  `dlux/utils.py` (140 public symbols) into a `dlux/utils/` package — 13 feature
  modules (`config`, `crud`, `discovery`, `mail`, `navigation`, `twofactor`,
  `authorization`, `users`, `sections`, `activity_log`, `settings`,
  `localization`, `import_export`) plus `common.py` for the cross-feature leaf
  helpers (role/profile/scope/permission accessors, `_normalize_asset_url`,
  `_coerce_import_bool`). The inter-module import graph is an acyclic DAG;
  `__init__.py` re-exports all 140 names so every `from dlux.utils import X` and
  `dlux.utils.X` call site is unchanged. Code was extracted verbatim
  (AST-faithful), with dlux-level relative imports rewritten `.x` → `..x`. The
  original `dlux/utils.py` is kept intact on disk (inert; shadowed by the
  package) as a reference/rollback.
- **Constants Import Cleanup**: Removed stale imports of the deleted legacy
  home-url constant from the split `dlux/utils/` modules and localized the old
  `/sys/` compatibility sentinel in the remaining unconfigured-settings
  fallback checks and regression test.
- **Titlebar Text Clipping Fix**: Relaxed the titlebar title line-height and
  added a small vertical text buffer so Arabic lower dots and Latin descenders
  (`g`, `j`, etc.) are not clipped by the title row's overflow/truncation box;
  bumped the `titlebar.css` cache-buster.
- **Options Sidebar Density Visibility**: Hid the Options-page Sidebar Density
  card when the sidebar runtime surface is disabled, matching the existing
  context processor and setup-preview behavior that already suppress runtime
  sidebar density controls unless `sidebar.enabled` is true.

## v1.0.2

- **Rebrand Wizard Navigation Regression Fix**: Fixed the first-launch System
  Setup wizard step navigation, which silently broke during the
  `microsys`→`dlux` rebrand. The `data-ms-*` → `data-dl-*` kebab-case attribute
  rename was applied to templates and `querySelector` selectors but missed the
  matching camelCase `element.dataset.msX` reads (which a `data-ms-` find/replace
  cannot catch). `dataset.msWizardStepTarget` was reading the now-nonexistent
  `data-ms-wizard-step-target`, yielding `NaN`, so the step-nav bullets never
  highlighted (`is-active`/`is-complete`) and clicks never navigated. Renamed
  every stale read to its correct `dataset` form (shipped as `dataset.dluxX`
  after the prefix streamline below) across `helpers/wizard/js/main.js`,
  `main/js/system_setup.js`, `themes/js/main.js`, `users/js/user_report.js`,
  and `forms/js/filter_form.js`.
- **Related dataset-binding fixes (same root cause)**: `dluxWizardInitialStep`
  (wizard now returns to the correct step after a language-preview reload),
  `dluxPreviewThemeCss` (theme-preview `<link>` de-dupe guard now matches the
  attribute it writes, preventing duplicate stylesheet injection), and the User
  Report export base / window / page-size bindings (`dluxUserReport*`).
- **Full `microsys`/`ms` naming residue sweep**: Eliminated all remaining
  pre-rebrand identifiers so no `ms`/`micro` naming survives in runtime code.
  - **Translation system unified to `DLUX_STRINGS`**: the template/JS context
    variable (`MS_TRANS`/`__MS_TRANS`), the per-app catalog dict
    (`MS_TRANSLATIONS`), and the JS injection (`window.DLUX_STRINGS` via the
    `dlux-strings-data` `json_script`) now share one token. The discovery loader
    reads `DLUX_STRINGS` with an **inert fallback to legacy `MS_TRANSLATIONS`**,
    so apps not yet migrated keep loading; `dlux startapp` scaffolds emit
    `DLUX_STRINGS`. JS helper `window.ms_trans()` → `window.dluxString()`.
  - **`micro:` event bus → `dlux:`**: every custom event (`micro:record:*`,
    `micro:dynamic_modal:open`, `micro:subsection:*`, `micro:reset-password`,
    `micro:soft-delete`, `micro:view-*`, and `ms:wizard-step-change`) renamed to
    the `dlux:` namespace across Python producers and JS listeners; row-action
    attributes `data-micro-actions`/`data-micro-context` → `data-dlux-*`; element
    id `microContextMenu` and template `micro_context_menu.html` →
    `dluxContextMenu`/`dlux_context_menu.html`; `__micro*Initialized` guards →
    `__dlux*`. **Fixed a latent bug**: the context menu read an unset
    `window.MS_TRANS`, so its labels never localized — now reads `DLUX_STRINGS`.
  - **Template tags**: `ms_timesince`→`dlux_timesince`,
    `ms_querystring`/`ms_querystring_multi`→`dlux_querystring`/`dlux_querystring_multi`.
  - **Internal tokens/ids**: permission sentinels `__ms_*__`→`__dlux_*__`,
    session key `ms_force_language_preview`→`dlux_force_language_preview`, CSS
    class `ms-2fa-badge`→`dlux-2fa-badge`, ids `msOptionsGrid`/`msLanguageFontsEditor`/`msFontPreviews`→`dlux*`,
    internal dataset flags and JS globals → `dlux*`.
  - **DB index names**: `ms_ual_*` → `dlux_ual_*` in `models.py` and the initial
    migration (fresh installs only; in-place-migrated DBs keep the harmless
    physical `ms_ual_*` names — documented in the migration guide).
  - **Security standard `MSRP-1` → `DSRP-1`**: the acronym now matches its words
    (Dlux Secure Runtime Policy); `docs/security-msrp-1.md` →
    `docs/security-dsrp-1.md`, all docs/code references updated.
- **Prefix streamline — single `dlux` token across all surfaces**: Unified the
  pre-existing two-tier `dl-`/`dlux` convention onto one brand token. Renamed the
  entire markup/DOM vocabulary — **267 `.dlux-*` CSS classes**, **36
  `data-dlux-*` attributes** (+ their camelCase `dataset.dluxX` reads), **124
  `--dlux-*` CSS custom properties**, button classes (`dlux-btn-*`), component
  classes, and element ids — across every authored CSS, template, and JS file.
  Producer↔consumer pairs (CSS↔HTML↔JS selectors, Python-emitted attributes↔JS
  `dataset` reads) were renamed in lockstep and verified consistent; vendored
  Bootstrap/Chart.js/datepicker assets (`bs-*`) were left untouched.
- **Static cache-buster bump**: Bumped `?v=` to `20260612c` for every changed
  JS/CSS asset so browsers load the corrected scripts (`login.css`/`login.js`
  keep their always-fresh `{% now 'U' %}` busters).

## v1.0.1

- **SSO Companion Release Builds**: Fixed `release-sso.yml` and
  `release-sso-client.yml` to call each companion's `build.py` helper instead
  of `python -m build` from inside a directory containing a local `build.py`,
  preventing recursive self-invocation that caused GitHub Actions exit 143
  during `django-lux-sso` and `django-lux-sso-client` distribution builds. Each
  companion now owns a package-local `VERSION` file used by `__version__`,
  dynamic pyproject metadata, and the workflow tag guard.
- **DjangoLux Brand Logo**: Activated the SVG-first DjangoLux brand system with
  graphite shield/monogram source assets (`base_logo.svg`, `login_logo.svg`) by
  switching default `logo`, `login_logo`, and favicon URLs to the SVG assets,
  centering the separated `Django`/`Lux` login wordmark under the shield,
  refreshing the README hero image, and updating login/titlebar fallbacks plus
  the mobile login mask to avoid stale `django-microsys` WebP branding.

## v1.0.0

- **Rebrand from django-microsys**: First release under the `django-lux` name
  (import package `dlux`). Feature-equivalent to `django-microsys` 2.4.1 — the
  full system/runtime framework (first-launch setup wizard, user & security
  operations, four-tier staff authorization, multiple 2FA flows, scopes, audit
  logging, dynamic modal CRUD, reports/overview, and the encrypted full-system
  backup) carries over with identical behavior. The package imports as `dlux`,
  the Django app label and database tables use the `dlux_*` prefix, project
  configuration lives under `DLUX_CONFIG` (`from dlux.utils import
  dlux_settings`), the scaffolding CLI is `dlux` (`python -m dlux startproject`),
  and the system backup format is `.dlb` (`DLB1`, kind `dlux-system-backup`)
  with the standalone `tools/dlb-viewer` reader. The 545 internal `ms-` CSS
  classes were renamed to `dl-`; the optional SSO companions are
  `django-lux-sso` / `django-lux-sso-client` with OIDC claims `dlux_sso_role`
  and `dlux_sso_client_id`. Migrations are squashed to a fresh `0001_initial`.
- **In-place migration from django-microsys**: Added the
  `dlux_migrate_from_microsys` management command that converts an existing,
  fully-migrated `django-microsys` 2.4.1 database to `django-lux` without data
  loss — renames every `microsys_*` table to `dlux_*`, repoints
  `django_content_type` (so permissions follow automatically), collapses the
  recorded migration history to dlux's `0001_initial`, and rewrites
  app-label-qualified `UserActivityLog.model_key` values (`microsys.*` →
  `dlux.*`). Dry-run by default; pass `--yes` to apply. See
  [docs/migrating-from-microsys.md](docs/migrating-from-microsys.md).
