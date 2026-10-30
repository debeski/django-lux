# django-lux — package development

This is the framework itself (`dlux`), not a consumer project. The ecosystem
conventions for projects that *consume* dlux apply here too:

@~/.claude/dlux.md

That import is a local file outside the repo, so a fresh clone or a cloud session
cannot read it. The rules below are therefore self-contained — keep them that way.

Project state, tasks and known bugs: see `tracker.md`.

## Package-development rules (do not move to `~/.claude/dlux.md`)

- **Feature isolation.** Start every feature release or independently releasable
  workstream from the current verified `main` on its own dedicated branch before
  changing code, docs, changelog, or version metadata. Keep one feature per branch;
  do not develop features directly on `main` or reuse another active feature's
  branch. Merge only after that branch's implementation, docs, and tests pass;
  perform shared release versioning and tagging after selecting work for integration.
- **Branch names.** Name a branch `<release line>/<work>` in snake_case, for
  example `1.13/operations_panel` or `1.14/table_builder`. Its checkout directory
  is the last path segment (`../operations_panel`).
- **Retire merged branches without asking.** Once a branch is merged into `main`
  and safe to discard, retire it: move its ignored leftovers (`.xclude/`, venv
  links, e2e state and screenshots) into
  `main/.xclude/retired-worktrees/<date>/<checkout>/`, `git worktree remove` the
  checkout, and delete the branch locally and on GitHub. Stop and ask only when
  something blocks it (unmerged commits, a conflict, uncommitted work). This
  overrides any personal rule asking for approval before each worktree removal.
- **Sibling repos stay in step.** `app-composer` (stack contract, manifest
  `requires` keys, updater/ops protocol, relay operations, maintenance page) and
  `app-scanlink` (the ScanLink protocol behind `window.DluxScan`) follow DjangoLux
  in the same release cycle, under the same branch and retirement rules (each has
  its own `AGENTS.md`). A DjangoLux change that needs them ships with their paired
  beta, accepted together on `testbed-dlux`. The DLB viewer (`tools/dlb-viewer`)
  already ships through this repo's release flow.
- **Consumers ship stable only.** Consumer projects (`../project-*`) are committed,
  tagged and published only against published stables of DjangoLux, Composer and
  ScanLink: never a `bN` pin, a `:beta`/`vX.Y.ZbN` image or a beta
  `.composer-channel`, even though Decrees doubles as the testbed app. Betas are
  accepted on `~/Desktop/depy/testbed-*` stacks through compose-level means (source
  mounts, `build-app.sh --wheel` overlays, beta-channel inline updates) that are
  never committed to a consumer. A consumer bumps its DjangoLux pin only after the
  stable is published.
- **Downstream first.** Before moving or renaming a template, static file or public
  symbol, grep the consumer projects (`../project-archive`, `../project-decrees`,
  `../project-dhub`, `../project-dlux-crm`, `../project-dlux-panel`,
  `../project-min-survey`, `../project-trademarks`), shim whatever they import, and
  record it in `docs/deprecation-countdown.md` + `dlux/tests/test_downstream_compat.py`.
- **Import cycles.** `scripts/import_cycles.py` is the detector;
  `dlux/tests/test_import_graph.py` guards it. The function-scope imports are
  load-bearing mitigation for real cycles, not clutter — do not promote them to
  module scope blindly.
- **Docs are same-turn.** Any change to a feature, schema, setting, API, env var or
  setup step updates the matching file under `docs/` in the same turn (`FEATURES.md`,
  `reference.md`, and the topic doc).
- **Outbound network calls.** Never open a connection to a public host from code
  that runs in `web` or `celery`; route it through the Composer relay
  (`docs/outbound-requests.md`). New features that need the internet ship as relay
  operations, not as a `celery` `egress` requirement. The relay shipped in
  DjangoLux 1.10.0 (`dlux.relay`) with Composer 1.6.0.
- **Removed/deprecated APIs** are tracked in `docs/deprecation-countdown.md` with a
  removal target version — keep it current.

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
- Before tagging, also run `python -m dlux.updater.release_check` with no arguments, then `python -m build` and `twine check`: that is what the release's build step runs, and only the bare form validates the manifest's image and migration baselines.

## Checks

Run these with the repo's own interpreter (`.venv/bin/python`); a bare `python` may
not have Django installed.

- `DJANGO_SETTINGS_MODULE=dlux.tests.settings .venv/bin/python -m django check`
- `.venv/bin/python dlux/tests/test_all.py`
- For scaffold changes: `.venv/bin/python -m dlux startproject myproject` and `.venv/bin/python -m dlux startapp billing --register`
