# Django microSYS - System Integration Service

[![PyPI version](https://badge.fury.io/py/django-microsys.svg)](https://pypi.org/project/django-microsys/)

<p align="center">
  <img src="https://raw.githubusercontent.com/debeski/django-microsys/main/microsys/static/img/login_logo.webp" alt="microSys Logo" width="450"/>
</p>

microSYS is a multilingual Django app that gives a project-level system layer for user management, branding, translations, scopes, navigation, activity logging, guided onboarding, and dynamic CRUD tooling. The package now keeps the landing README short and moves the long-form operating and integration guidance into [`docs/`](docs/README.md).

## What microSYS gives you

- A first-launch setup wizard at `/sys/setup/` for branding, languages, themes, home URL, and sidebar structure.
- A runtime system UI for users and superusers, including Options, user management, activity logs, 2FA, and scoped data tools.
- A database-backed `SystemSettings` singleton layered over `MICROSYS_CONFIG`, so projects can seed defaults in code and refine them in the UI later.
- A `ScopedModel` base with audit fields, soft-delete behavior, actor tracking, and automatic scope handling.
- Zero-boilerplate sections, dynamic modals, context menus, translations, and autofill helpers for common internal Django workflows.
- Persistent user preferences for theme, language, sidebar state, and autofill behavior.

## Requirements

- Python 3.11+
- Django 5.1+
- `django-crispy-forms`
- `crispy-bootstrap5`
- `django-tables2`
- `django-filter`
- `psutil`
- `pyotp`
- `qrcode`

## Installation

```bash
pip install django-microsys crispy-bootstrap5 psutil pyotp qrcode
# OR
pip install git+https://github.com/debeski/django-microsys.git crispy-bootstrap5 psutil pyotp qrcode
```

## Minimal Quick Start

1. Add the app and its companion packages to `INSTALLED_APPS`.

```python
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "crispy_forms",
    "crispy_bootstrap5",
    "django_filters",
    "django_tables2",
    "microsys",
]
```

2. Add the middleware, context processor, and Crispy Bootstrap 5 settings.

```python
MIDDLEWARE = [
    # ...
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "microsys.middleware.ActivityLogMiddleware",
]

TEMPLATES = [
    {
        # ...
        "OPTIONS": {
            "context_processors": [
                # ...
                "microsys.context_processors.microsys_context",
            ],
        },
    },
]

CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"
```

3. Mount `microsys.urls` at project root so the bundled auth and system routes stay at `/accounts/...` and `/sys/...`.

```python
from django.urls import include, path

urlpatterns = [
    path("", include("microsys.urls")),
]
```

4. Run the setup command.

```bash
python manage.py microsys_setup
```

5. Sign in as a superuser and complete the first-launch wizard at `/sys/setup/`. After that, the main runtime UI lives under `/sys/`.

For a fuller setup path, prefix-mount guidance, and first-launch expectations, use the [Getting Started guide](docs/getting-started.md).

## Key Capabilities

- First-launch setup wizard and runtime System Settings modal.
- Resolver-driven sidebar builder with runtime tree rendering and user-level reordering.
- Interactive user wizard with translated grouped permissions.
- Dynamic sections and AJAX-driven modal CRUD flows.
- Translation framework with runtime overrides and automatic label translation.
- Scoped models with audit fields, actor tracking, soft-delete, and automatic scope injection.
- Built-in tutorial, autofill engine, preferences API, and activity logging.

## Documentation

- [Documentation Hub](docs/README.md)
- [Getting Started](docs/getting-started.md)
- [Admin Guide](docs/admin-guide.md)
- [Developer Guide](docs/developer-guide.md)
- [Customization Guide](docs/customization-guide.md)
- [Reference](docs/reference.md)
- [Changelog](CHANGELOG.md)

## Maintenance

microSYS documentation now follows a simple rule:

- Evergreen usage and customization docs live under [`docs/`](docs/README.md).
- Release-by-release history lives in [`CHANGELOG.md`](CHANGELOG.md).

That keeps the landing page easy to scan while still giving the project a thorough in-repo manual.
