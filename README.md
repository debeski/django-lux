# Django microSYS - System Integration Service

[![PyPI version](https://badge.fury.io/py/django-microsys.svg)](https://pypi.org/project/django-microsys/)

<p align="center">
  <img src="https://raw.githubusercontent.com/debeski/django-microsys/main/microsys/static/img/login_logo.webp" alt="microSys Logo" width="450"/>
</p>

microSYS is a multilingual Django app that gives a project-level system layer for user management, branding, translations, scopes, navigation, activity logging, guided onboarding, data export, and dynamic CRUD tooling. It is not just a themed admin shell: it is a fairly large internal-systems toolkit that bundles runtime configuration, user operations, auditability, UI infrastructure, and zero-boilerplate management patterns into one package. The package keeps the landing README short, You can view the long-form operating and integration guidance at [`docs/`](docs/README.md).

## What microSYS gives you

- A first-launch setup wizard at `/sys/setup/` for identity, explicit language catalog management, translation-matrix overrides, access/security toggles, UI-first Microsys email delivery, themes, default table density, global home URL, and sidebar structure, including full sidebar disable, runtime sidebar-toolbar, and user-reordering controls.
- A runtime system UI for users and superusers, including Options, user management, profiles, 2FA, activity logs, scopes, and system settings.
- A disabled-by-default public registration playground for email-first local signup with mandatory email verification, Microsys email readiness checks, public-account provenance badges, throttles, and optional approval.
- A database-backed `SystemSettings` singleton layered over `MICROSYS_CONFIG`, so projects can seed defaults in code and refine them in the UI later.
- A framework-owned `django_tables2` platform that auto-adopts stock tables, ships built-in pagination and per-page controls, exposes a public `MicrosysTable` base class, and supports per-table `microsys_table`, `microsys_density`, `microsys_per_page`, and `microsys_actions` overrides.
- A `ScopedModel` base with audit fields, soft-delete behavior, actor tracking, filtered managers, and automatic scope handling.
- Zero-boilerplate sections and dynamic modal CRUD flows for auxiliary models, plus a reusable context-menu/event model for richer interactions.
- A built-in audit trail with signal-based logging, merged User/Profile updates, diff capture, masked sensitive fields, and download/export log entries.
- Universal data helpers such as `fetch_file`, `fetch_excel`, sticky-form autofill, tutorial overlays, and persistent UI preferences.

## Requirements
`note: all the requirements will be installed automatically when you install django-microsys.`

- Python 3.11+
- Django 5.1+
- `django-crispy-forms`
- `crispy-bootstrap5`
- `django-tables2`
- `django-filter`
- `pillow` "for image handling"
- `babel` "for translations"
- `psutil` "for system monitoring"
- `pyotp` "for TOTP 2FA"
- `qrcode` "for TOTP 2FA QR codes"
- `cryptography` "for encrypted TOTP and SMTP secret storage"

## Installation

```bash
pip install django-microsys
# OR
pip install git+https://github.com/debeski/django-microsys.git
```

## Scaffold a New Project or App

```bash
python -m microsys startproject myproject
cd myproject
python -m microsys startapp billing --register
```

`python -m microsys startproject` creates a new Django project already wired for MicroSys. `python -m microsys startapp` creates a MicroSys-native app skeleton with models, forms, filters, tables, translations, templates, tests, and optional project registration.

Generated projects also include a baseline Docker stack with `compose.yml`, `compose.dev.yml`, a `config/celery.py` worker entrypoint, and a `/health/` endpoint via `django-health-check`.
They also generate `.secrets/.env` with the bootstrap secrets used by the standard decrypter/startup flow.
The scaffolded settings baseline now also includes `django-cors-headers` and `django-csp` with their apps, middleware, and starter CORS/CSP policy settings.

## Minimal Quick Start

1. Add the MicroSys helper at the end of your project `settings.py`.

```python
from microsys.utils import microsys_settings

microsys_settings(globals())
```

That helper prepends the required apps, inserts `django.middleware.locale.LocaleMiddleware` and `microsys.middleware.MicrosysMiddleware` in the supported order, adds the Microsys context processor, sets the Crispy Bootstrap 5 defaults, adds a Bootstrap-friendly `MESSAGE_TAGS` error mapping, and seeds the standard MicroSys runtime defaults for language, timezone, i18n/tz flags, `FORMAT_MODULE_PATH`, and charset unless your project already defines them.

__Proceed to [Getting Started](docs/getting-started.md) if you prefer to wire everything manually.__

Public registration is documented separately at [Public Registration Playground](docs/registration.md). It is disabled by default and is not part of the optional SSO packages.


2. Mount `microsys.urls` at project root so the bundled auth and system routes stay at `/accounts/...` and `/sys/...`.

```python
from django.urls import include, path

urlpatterns = [
    path("", include("microsys.urls")),
]
```

With that root include in place, microsys provides `/accounts/...` and `/sys/...`. If your project does not define its own `/` view, microsys falls back from an unresolved `/` request into its login/setup flow instead of leaving a 404. On a fresh and unconfigured install, Microsys also guards ordinary anonymous requests so a public root page cannot bypass first-time setup; once setup is complete, your existing root view continues to behave normally.

3. Run the setup command.

```bash
python manage.py microsys_setup
```

4. Sign in as a superuser and complete the first-launch wizard at `/sys/setup/`. On a fresh install, an anonymous request may be sent through `/sys/setup/` and then to login before the wizard can be completed. After setup, the main runtime UI lives under `user_hub`.

For a fuller setup path, prefix-mount guidance, and first-launch expectations, use the [Getting Started guide](docs/getting-started.md).


## Key Capabilities

- Onboarding and runtime configuration:
  first-launch setup wizard, Options view, runtime System Settings modal, source-tabbed translation overrides, setup import/export, language/theme defaults, and a global Home destination.
- User and security operations:
  interactive user wizard, grouped translated permissions, four-tier staff authorization (superuser, Global Staff, Central Staff, Scoped Staff), permission-based sidebar visibility, profile management, multiple 2FA flows (App, Email, Backup), trusted device tracking for 30 days, and runtime preference persistence.
- Generic CRUD infrastructure:
  dynamic sections, AJAX-driven modal CRUD, automatic form/table/filter discovery, context-menu actions, and reusable event dispatch.
- Navigation and UI infrastructure:
  resolver-driven sidebar builder with permission-based visibility, runtime tree rendering, optional user-level reordering, configurable sidebar toolbar visibility, a shared theme registry, tutorial overlays, theme-aware system surfaces, and template injection hooks.
- Data movement and productivity helpers:
  universal file download, Excel export, smart autofill, sticky-form cloning, and generic list/filter helpers.
- Audit and governance:
  signal-based activity logging with configurable IP resolution (direct/proxy/header), diff capture, masked sensitive fields, deduplicated entries, download/export logging, and scoped visibility.
- Optional SSO:
  `django-microsys-sso` and `django-microsys-sso-client` live as separate optional packages for OIDC provider/client deployments without changing core Microsys runtime behavior.
- Framework-level automation:
  translation patches, scoped-model auto-injection, actor tracking, soft-delete, and config layering across defaults, project settings, and runtime UI.

## Documentation

- [Documentation Hub](docs/README.md)
- [Getting Started](docs/getting-started.md)
- [Admin Guide](docs/admin-guide.md)
- [Developer Guide](docs/developer-guide.md)
- [Customization Guide](docs/customization-guide.md)
- [Reference](docs/reference.md)
- [MSRP-1 Security Standard](docs/security-msrp-1.md)
- [Optional SSO Packages](docs/sso.md)
- [Features](docs/FEATURES.md) — complete feature inventory
- [Changelog](CHANGELOG.md)
