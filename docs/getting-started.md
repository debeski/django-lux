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
- `openpyxl`
- `packaging`

## Install the Package

```bash
pip install django-lux
# OR
pip install git+https://github.com/debeski/django-lux.git
```

## Fastest Greenfield Start

If you are starting a brand-new project, use the DjangoLux scaffold instead of raw Django defaults:

```bash
python -m dlux startproject myproject --image acme/myproject --repo acme/myproject
cd myproject
```

`startproject` prompts on a terminal for the two release settings (press Enter to
accept the default):

- `--image name[:tag]` — the Docker image the deployment pulls and the generated
  release workflow pushes; written to `.secrets/.env` as `WEB_IMAGE`. Defaults to
  the bare project name, which exists in no registry, so image-update discovery
  never fires unless you set it.
- `--repo owner/name` — the GitHub repository (or a full GitHub URL) for the
  release URL in `release-manifest.json`. Optional; blank leaves an `OWNER/REPO`
  placeholder.
- `--no-input` — never prompt (CI); use the flag values or their defaults.

For new apps inside a DjangoLux project:

```bash
python -m dlux startapp billing
# or
python -m dlux startapp billing --register
```

The generated project already includes a Docker baseline, a `config/celery.py`
entrypoint, `celery`, `dlux-updater`, and outbound-only `composer-agent` services,
persistent `dlux_runtime` and private agent-state volumes, a Caddy proxy (nginx fallback) with a
maintenance/progress page, a `/health/` endpoint, a generated
`.secrets/.env` file with the bootstrap secret values, baseline
`django-cors-headers` / `django-csp` setup in `config/settings.py`, and a
tag-driven release pipeline (`release-manifest.json`,
`.github/workflows/release.yml`, and `tools/validate_project_release_manifest.py`).

The deployment timezone is driven by the `TIME_ZONE` variable (IANA name, e.g.
`Africa/Tripoli`) in `.secrets/.env`, passed through the Compose `x-environment`
block into `settings.TIME_ZONE` and `CELERY_TIMEZONE`; it defaults to `UTC`.
See [Deployment Configuration](deployment-configuration.md) for the canonical
list of accepted `DLUX_*` Django settings and environment variables.

The scaffold pins `django-lux[updater]` and enables verified inline updates.
Hand-wired and non-Compose projects remain updater-disabled by default. Existing
generated projects can adopt the infrastructure once with
`python -m dlux enable-updater`; see the [Verified Inline Updater](inline-updater.md).
Deployments with the former resident updater migrate with a dry run of
`./start.sh enable-agent`, followed by `./start.sh enable-agent --apply` after
reviewing the diff. Pull Composer 1.2.0 first with `./start.sh --update`.
See [Composer Agent Integration](composer-agent.md) for enrollment, volumes,
security boundaries, and the typed DLUX bridge.

### Behind a Front Proxy / TLS Terminator

The scaffold's Caddy (and the nginx fallback) listens on plain HTTP and expects
a front proxy or TLS terminator (pfSense/HAProxy, another nginx, a cloud load
balancer) in production. Caddy trusts private-range upstreams
(`servers { trusted_proxies static private_ranges }`), and the nginx fallback
appends to `X-Forwarded-For` and passes an incoming `X-Forwarded-Proto`
through — so forwarded headers from the front hop reach Django instead of
being replaced. The front proxy must do its half:

- **Overwrite `X-Forwarded-Proto`** on the TLS frontend (HAProxy:
  `http-request set-header X-Forwarded-Proto https`; in pfSense's HAProxy
  package: frontend action *http-request header set*, name
  `X-Forwarded-Proto`, fmt `https`, no condition). Use *set*, not *add*, so
  clients cannot spoof it.
- **Append the real client IP to `X-Forwarded-For`** (HAProxy:
  `option forwardfor`; in pfSense: the frontend's "Use 'forwardfor' option"
  checkbox).

With both in place, the chain arriving at Django is `client_ip, front_proxy_ip`
and dlux's default `client_ip_config` (`x_forwarded_for` mode,
`trusted_proxy_hops = 1`) resolves the real client IP — required for correct
per-IP login lockout, registration/2FA throttling, and audit-log attribution.
Without them, every visitor appears as the front proxy's address.

## Minimum Django Configuration

Add the required apps:

```python
INSTALLED_APPS = [
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

Dlux's own browser code resolves runtime API URLs from Django-reversed metadata,
so built-in preferences, theme switching, notifications, search, session
keepalive, and autofill continue to work when mounted at `/dlux/` or behind an
i18n prefix. Project JavaScript should follow the same rule: use `{% url %}` in
templates for concrete endpoints, or use `window.dluxEndpoint(name, params,
fallbackPath)` / `window.dluxUrl("/sys/...")` for Dlux routes instead of
hardcoding root-relative `/sys/...` or `/accounts/...` URLs.

## Run Initial Setup

Run the setup helper:

```bash
python manage.py dlux_setup
```

What it does:

- runs `makemigrations dlux` unless `--no-migrate` is used
- runs `migrate dlux` unless `--no-migrate` is used
- runs `dlux_doctor` unless `--skip-check` is used

Useful follow-up command:

```bash
python manage.py dlux_doctor
```

`dlux_doctor` is the deployment doctor. It reports on settings wiring, URL
mounting, database reachability, pending migrations, cache and SMTP round-trips,
collected static files, and production-safety settings, and exits 1 when any
check fails — so it works in CI. `--apply` runs the safe fixes it found;
database-mutating fixes additionally require `--allow-stateful`. See
[reference.md](reference.md) for the full flag list.

Useful scaffold commands:

```bash
python -m dlux startproject myproject --image acme/myproject --repo acme/myproject
python -m dlux startapp billing --register
```

## What Happens on First Launch

On a fresh install, Dlux protects ordinary requests until the system is configured. In practice, an anonymous visitor can be redirected toward `/sys/setup/`, then on to login, and the first superuser who signs in is guided through the wizard.

The setup flow first asks the superuser to choose the setup language. That choice controls only the first-launch setup UI language and direction. The actual saved system default language is selected separately in the Localization step and can be different.

The setup wizard then runs in thirteen steps:

1. Identity: language-keyed system names (JSON dict), logo, favicon, setup import, and public-root title/metadata when public root access is enabled.
2. Localization: explicit language catalog, default language, user language override policy, and the translation matrix editor.
3. Access and security: public root access, global home URL, public registration/email 2FA toggles, trusted-session enforcement, Dlux email delivery path/secret storage, and client IP resolution.
4. Login Page: login layout style (Split / Centered / Minimal / Full-page split), show-logo toggle, logo treatment, banner colour, and per-language Markdown hero message.
5. Sidebar: sidebar builder and sidebar behavior controls, plus public-root sidebar visibility when public root access is enabled.
6. Nav Bar: optional authenticated nav bar mode, override policy, and hierarchy tree.
7. Titlebar: titlebar controls (logo/home visibility, treatment, button shape, user-hub layout style, action order, alignment, height, surface), plus public-root titlebar visibility when public root access is enabled.
8. Notifications: flash, drawer, badge, browser bridge, email delivery, and automatic CRUD notification behavior.
9. Themes and Typography: theme availability, default theme, theme override policy, fonts, and the public-root theme when public root access is enabled.
10. Layout: table, form, modal, Options-page, audit-field, and soft-delete visibility controls.
11. Logging: user/system activity logging, audit event logging, and retention controls.
12. Profile Page: profile-page modules and first-login user setup/onboarding options.
13. Backups: scheduled backup, storage, and retention policy.

When the form is saved:

- `SystemSettings.is_configured` becomes `True`
- the sidebar tree is stored as the system default
- the selected home URL becomes the project-wide runtime home target

After setup, the same configuration stays editable from the superuser System Settings entry in the Options view.

## Minimum Verification Checklist

- You can log in through `/accounts/login/`.
- The first superuser reaches `/sys/setup/` on a fresh install.
- If your project has a public `/` page, it is redirected into setup/login before configuration and behaves normally again after setup.
- `python manage.py dlux_doctor` reports the core configuration as valid.
- `/sys/options/` loads after setup.

## Next Reads

- [Admin Guide](admin-guide.md) for operating the setup wizard, Options view, and runtime preferences.
- [Developer Guide](developer-guide.md) for the system mental model and integration patterns.
- [Customization Guide](customization-guide.md) for translations, sections, dynamic modals, and template overrides.
- [Verified Inline Updater](inline-updater.md) for generated-Compose deployment, guarded bootstrap, updates, and rollback.
