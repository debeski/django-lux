# Getting Started

Use this page when adding `django-lux` to a host Django project for the first time.

## Requirements

- Python 3.11+
- Django 5.1+
- `django-crispy-forms`
- `crispy-bootstrap5`
- `django-tables2`
- `django-filter`
- `pillow`
- `babel`
- `psutil`
- `pyotp`
- `qrcode`
- `cryptography`

## Install the Package

```bash
pip install django-lux
# OR
pip install git+https://github.com/debeski/django-lux.git
```

## Fastest Greenfield Start

If you are starting a brand-new project, use the DjangoLux scaffold instead of raw Django defaults:

```bash
python -m dlux startproject myproject
cd myproject
```

For new apps inside a DjangoLux project:

```bash
python -m dlux startapp billing
# or
python -m dlux startapp billing --register
```

The generated project already includes a Docker baseline, a `config/celery.py` entrypoint, a `celery` compose service, a `/health/` endpoint, a generated `.secrets/.env` file with the bootstrap secret values, and a baseline `django-cors-headers` / `django-csp` setup in `config/settings.py`.

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
    "dlux",
]
```

Add middleware, context processor, and Crispy settings:

```python
MIDDLEWARE = [
    # ...
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "dlux.middleware.DluxMiddleware",
]

TEMPLATES = [
    {
        # ...
        "OPTIONS": {
            "context_processors": [
                # ...
                "dlux.context_processors.dlux_context",
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
    path("", include("dlux.urls")),
]
```

This gives you:

- `/accounts/login/` and `/accounts/logout/`
- `/sys/setup/` for first launch
- `/sys/`-prefixed system views such as users, logs, scopes, sections, and options

If your project does not define its own `/` view, dlux will catch an otherwise unresolved `/` request and redirect into the bundled login/setup flow.

On a fresh and unconfigured install, Dlux also guards ordinary anonymous requests before normal app pages render. That means a host project's public `/` page will still be redirected into the setup/login path until the system is configured. After setup completes, control returns to the host project's normal root view behavior.

If your project already owns `/accounts/`, mount dlux under a prefix and update auth redirects explicitly:

```python
urlpatterns = [
    path("dlux/", include("dlux.urls")),
]

LOGIN_URL = "/dlux/accounts/login/"
LOGIN_REDIRECT_URL = "/dlux/accounts/profile/"
LOGOUT_REDIRECT_URL = "/dlux/accounts/login/"
```

## Run Initial Setup

Run the setup helper:

```bash
python manage.py dlux_setup
```

What it does:

- runs `makemigrations dlux` unless `--no-migrate` is used
- runs `migrate dlux` unless `--no-migrate` is used
- runs `dlux_check` unless `--skip-check` is used

Useful follow-up command:

```bash
python manage.py dlux_check
```

Useful scaffold commands:

```bash
python -m dlux startproject myproject
python -m dlux startapp billing --register
```

## What Happens on First Launch

On a fresh install, Dlux protects ordinary requests until the system is configured. In practice, an anonymous visitor can be redirected toward `/sys/setup/`, then on to login, and the first superuser who signs in is guided through the wizard.

The setup wizard runs in eight steps:

1. Identity: language-keyed system names (JSON dict), logo, favicon, and setup import.
2. Localization: explicit language catalog, default language, user language override policy, and the translation matrix editor.
3. Access and security: public root access, global home URL, public registration/email 2FA toggles, trusted-session enforcement, Dlux email delivery path/secret storage, and client IP resolution.
4. Login Page: login layout style (Split / Centered / Minimal / Full-page split), show-logo toggle, logo treatment, banner colour, and per-language Markdown hero message.
5. Sidebar: sidebar builder and sidebar behavior controls.
6. Nav Bar: optional authenticated nav bar mode, override policy, and hierarchy tree.
7. UI and Layout: titlebar controls (logo/home visibility, treatment, shape, alignment, height, surface).
8. Appearance and Typography: theme availability, default theme, theme override policy, fonts, and table-density defaults.

When the form is saved:

- `SystemSettings.is_configured` becomes `True`
- the sidebar tree is stored as the system default
- the selected home URL becomes the project-wide runtime home target

After setup, the same configuration stays editable from the superuser System Settings entry in the Options view.

## Minimum Verification Checklist

- You can log in through `/accounts/login/`.
- The first superuser reaches `/sys/setup/` on a fresh install.
- If your project has a public `/` page, it is redirected into setup/login before configuration and behaves normally again after setup.
- `python manage.py dlux_check` reports the core configuration as valid.
- `/sys/options/` loads after setup.

## Next Reads

- [Admin Guide](admin-guide.md) for operating the setup wizard, Options view, and runtime preferences.
- [Developer Guide](developer-guide.md) for the system mental model and integration patterns.
- [Customization Guide](customization-guide.md) for translations, sections, dynamic modals, and template overrides.
