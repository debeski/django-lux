# Contributing

Thanks for helping improve `django-lux`. This package is a Django UX/UI framework and system layer, so contributions should preserve host-project compatibility, security boundaries, multilingual behavior, and theme/runtime configurability.

## Before You Start

- Check existing issues, pull requests, and documentation to avoid duplicate work.
- For security issues, follow [`SECURITY.md`](SECURITY.md) instead of opening a public issue.
- Keep changes focused. Avoid unrelated formatting, rewrites, or dependency changes in the same pull request.

## Local Setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e .
```

If your change touches optional SSO behavior, install the optional dependency set or the affected optional package locally.

```bash
python -m pip install -e ".[sso]"
```

Updater/provenance work also needs the updater extra:

```bash
python -m pip install -e ".[updater]"
```

## Development Guidelines

- Prefer existing Dlux helpers, templates, settings patterns, and translation systems over one-off implementations.
- Keep backend authorization aligned with UI visibility; hidden controls are not authorization.
- Keep user-facing copy translation-ready and avoid hardcoded runtime text where Dlux translations are expected.
- Keep templates, CSS, and JavaScript theme-aware, language-aware, and direction-aware.
- Avoid inline CSS and JavaScript unless there is a documented reason.
- Update related documentation whenever a contribution changes configuration, APIs, security behavior, setup steps, schemas, or user-facing workflows.
- Add or update focused tests for bug fixes, security-sensitive paths, permissions, data export, setup behavior, and cross-project compatibility.

## Useful Checks

Run the narrowest relevant checks first, then broaden based on the change:

```bash
DJANGO_SETTINGS_MODULE=dlux.tests.settings python -m django check
python dlux/tests/test_all.py
```

For generated-project changes, also verify the scaffold commands:

```bash
python -m dlux startproject myproject
python -m dlux startapp billing --register
```

For inline-updater or release-contract changes, also run the focused updater/
scaffold tests and the release gate with the previous core tag:

```bash
DJANGO_SETTINGS_MODULE=dlux.tests.settings python -m django test dlux.tests.test_updater dlux.tests.test_scaffold
python -m dlux.updater.release_check --base-tag vX.Y.Z
```

Some repository workflows may run inside a host Django project or container. Include the exact commands you ran in the pull request description.

## Pull Requests

Good pull requests include:

- A short summary of the behavior changed.
- The reason the change is needed.
- Tests or checks run, including failures that remain.
- Screenshots or short recordings for UI changes.
- Documentation updates when behavior or setup changes.

Pull request templates are not currently required for this repository. Keep the description complete enough for a maintainer to verify the change without guessing.
