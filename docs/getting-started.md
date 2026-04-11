# Getting Started

Use this page when adding `django-microsys` to a host Django project for the first time.

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

## Install the Package

```bash
pip install django-microsys crispy-bootstrap5 psutil pyotp qrcode
# OR
pip install git+https://github.com/debeski/django-microsys.git crispy-bootstrap5 psutil pyotp qrcode
```

## Minimum Django Configuration

Add the required apps:

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

Add middleware, context processor, and Crispy settings:

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

Mount URLs at project root:

```python
from django.urls import include, path

urlpatterns = [
    path("", include("microsys.urls")),
]
```

This gives you:

- `/accounts/login/` and `/accounts/logout/`
- `/sys/setup/` for first launch
- `/sys/`-prefixed system views such as users, logs, scopes, sections, and options

If your project does not define its own `/` view, microsys will catch an otherwise unresolved `/` request and redirect into the bundled login/setup flow.

On a fresh and unconfigured install, Microsys also guards ordinary anonymous requests before normal app pages render. That means a host project's public `/` page will still be redirected into the setup/login path until the system is configured. After setup completes, control returns to the host project's normal root view behavior.

If your project already owns `/accounts/`, mount microsys under a prefix and update auth redirects explicitly:

```python
urlpatterns = [
    path("microsys/", include("microsys.urls")),
]

LOGIN_URL = "/microsys/accounts/login/"
LOGIN_REDIRECT_URL = "/microsys/accounts/profile/"
LOGOUT_REDIRECT_URL = "/microsys/accounts/login/"
```

## Run Initial Setup

Run the setup helper:

```bash
python manage.py microsys_setup
```

What it does:

- runs `makemigrations microsys` unless `--no-migrate` is used
- runs `migrate microsys` unless `--no-migrate` is used
- runs `microsys_check` unless `--skip-check` is used

Useful follow-up command:

```bash
python manage.py microsys_check
```

## What Happens on First Launch

On a fresh install, Microsys protects ordinary requests until the system is configured. In practice, an anonymous visitor can be redirected toward `/sys/setup/`, then on to login, and the first superuser who signs in is guided through the wizard.

The setup flow currently has three steps:

1. Branding and defaults: Arabic name, English name, logo, favicon, default language, default theme, discovered home URL, or a custom home URL.
2. Language catalog and translation overrides: JSON-based language definitions and JSON-based translation overrides.
3. Sidebar structure: a builder driven by discovered application pages plus manual grouping and icon customization.

When the form is saved:

- `SystemSettings.is_configured` becomes `True`
- the sidebar tree is stored as the system default
- the selected home URL becomes the project-wide runtime home target

After setup, the same configuration stays editable from the superuser System Settings entry in the Options view.

## Minimum Verification Checklist

- You can log in through `/accounts/login/`.
- The first superuser reaches `/sys/setup/` on a fresh install.
- If your project has a public `/` page, it is redirected into setup/login before configuration and behaves normally again after setup.
- `python manage.py microsys_check` reports the core configuration as valid.
- `/sys/options/` loads after setup.

## Next Reads

- [Admin Guide](admin-guide.md) for operating the setup wizard, Options view, and runtime preferences.
- [Developer Guide](developer-guide.md) for the system mental model and integration patterns.
- [Customization Guide](customization-guide.md) for translations, sections, dynamic modals, and template overrides.
