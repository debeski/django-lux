# django-lux Agent Rules

These are repo-specific rules; the global rules still apply. This repo's `CLAUDE.md` contains only `@AGENTS.md`.

## Security

- dlux must always stay CSP compliant. Any security-sensitive change follows DSRP-1 (`docs/security-dsrp-1.md`).
- Shipped templates have no inline `<script>` bodies, inline event handlers, `style=""` attributes or `javascript:` URLs.
- Every `<script>` carries `nonce="{{ request.csp_nonce }}"`. Pass data to JS with `json_script` or `data-*` attributes.
- Never use `eval`, `new Function` or string timers.
- UI visibility is never authorization. Enforce the same permission on the backend, through `user_matches_permission_token()` rather than ad hoc `is_staff` checks.
- State-changing security flows are POST-only.
- All user-facing strings go through the dlux translation framework. Templates, CSS and JS stay theme-, language- and RTL-aware.
- Deployments sit behind Caddy, which terminates TLS. Keep `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` in the scaffolded settings so secure cookies, redirects and CSRF work.

## Releases

- Read `docs/RELEASING.md` before touching versions or the changelog. The only version source is `version` in `dlux/release-manifest.json`.
- Every stable release is a beta first (`vX.Y.Zb1`). Never tag or push without my OK.
- Work that isn't released yet goes under `## Unreleased` in `CHANGELOG.md`.
- Set the manifest's migration and inline-install fields as RELEASING.md describes.
- For updater or migration changes, run `python -m dlux.updater.release_check --base-tag <last stable tag>`.

## Checks

- `DJANGO_SETTINGS_MODULE=dlux.tests.settings python -m django check`
- `python dlux/tests/test_all.py`
- For scaffold changes: `python -m dlux startproject myproject` and `python -m dlux startapp billing --register`
