# Changelog

This file owns the release history for `django-lux`.

> `django-lux` is the renamed, actively-maintained successor to
> [`django-microsys`](https://github.com/debeski/django-microsys) (now archived).
> Release history prior to v1.0.0 lives in that archived repository.

## v1.0.1

- **SSO Companion Release Builds**: Fixed `release-sso.yml` and
  `release-sso-client.yml` to call each companion's `build.py` helper instead
  of `python -m build` from inside a directory containing a local `build.py`,
  preventing recursive self-invocation that caused GitHub Actions exit 143
  during `django-lux-sso` and `django-lux-sso-client` distribution builds.
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
