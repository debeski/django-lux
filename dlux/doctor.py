"""Diagnostic checks for a running DjangoLux deployment.

The JSON report is a contract: Composer executes ``manage.py dlux_doctor
--format json`` inside the app container, merges the result with its own
project-directory findings, and renders one report. Adding checks is
backwards-compatible; renaming a check id or changing the emitted field set is
not, and requires a ``SCHEMA_VERSION`` bump.

Checks never raise. The doctor is most useful when the deployment is broken, so
a check that blows up is reported as a failing check rather than taking the
whole report down with it. Nothing in a report may carry a secret value: emit
key names, lengths, and booleans instead.
"""
import importlib
import os
import socket
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings

from . import __version__


SCHEMA_VERSION = 1

OK = 'ok'
WARNING = 'warning'
ERROR = 'error'
SKIPPED = 'skipped'

_STATUS_RANK = {OK: 0, SKIPPED: 0, WARNING: 1, ERROR: 2}

# How much authority applying a fix needs. `safe` is idempotent and touches no
# persistent data; `stateful` mutates the database; `source` edits project files.
SAFE = 'safe'
STATEFUL = 'stateful'
SOURCE = 'source'

SETTINGS_HELPER_REMEDY = (
    "Add to the end of your settings.py:\n"
    "    from dlux.utils import dlux_settings\n"
    "    dlux_settings(globals())"
)

_REGISTRY = []


@dataclass
class Finding:
    status: str
    detail: str
    remedy: str = ''
    fix: dict = None


@dataclass
class CheckResult:
    id: str
    group: str
    title: str
    status: str
    detail: str
    remedy: str = ''
    fix: dict = None

    def as_dict(self):
        return {
            'id': self.id,
            'group': self.group,
            'title': self.title,
            'status': self.status,
            'detail': self.detail,
            'remedy': self.remedy,
            'fix': self.fix,
        }


def ok(detail):
    return Finding(OK, detail)


def warn(detail, remedy='', fix=None):
    return Finding(WARNING, detail, remedy, fix)


def fail(detail, remedy='', fix=None):
    return Finding(ERROR, detail, remedy, fix)


def skip(detail):
    return Finding(SKIPPED, detail)


def management_fix(argv, label, safety=SAFE):
    return {'kind': 'management_command', 'argv': list(argv), 'label': label, 'safety': safety}


def check(check_id, group, title):
    def decorator(func):
        _REGISTRY.append((check_id, group, title, func))
        return func
    return decorator


@dataclass
class Context:
    """Shared probe state, so a dead database is diagnosed once rather than by
    every check that depends on it."""

    _db_error: str = field(default=None, init=False)
    _db_probed: bool = field(default=False, init=False)

    @property
    def db_available(self):
        if not self._db_probed:
            self._db_probed = True
            from django.db import connection
            try:
                connection.ensure_connection()
                self._db_error = ''
            except Exception as exc:
                self._db_error = f"{type(exc).__name__}: {exc}"
        return not self._db_error

    @property
    def db_error(self):
        self.db_available
        return self._db_error

    @property
    def base_url(self):
        return str(getattr(settings, 'DLUX_BASE_URL', '') or os.environ.get('BASE_URL', '')).strip()

    @property
    def expects_https(self):
        return self.base_url.startswith('https://')


def _settings_file():
    module_name = getattr(settings, 'SETTINGS_MODULE', None)
    if not module_name:
        return None
    try:
        module = importlib.import_module(module_name)
    except Exception:
        return None
    module_file = getattr(module, '__file__', None)
    return Path(module_file).resolve() if module_file else None


def _installed(module_name):
    try:
        importlib.import_module(module_name)
        return True
    except Exception:
        return False


# ── Settings wiring ────────────────────────────────────────────────────────

@check('settings.installed_apps', 'settings', 'INSTALLED_APPS includes dlux')
def _check_installed_apps(ctx):
    installed = list(getattr(settings, 'INSTALLED_APPS', []))
    if 'dlux' not in installed:
        return fail("'dlux' is not in INSTALLED_APPS.", SETTINGS_HELPER_REMEDY)
    required = ['crispy_forms', 'crispy_bootstrap5', 'django_filters', 'django_tables2']
    missing = [name for name in required if name not in installed]
    if missing:
        return warn(
            f"'dlux' is installed but these dependencies are missing: {', '.join(missing)}.",
            SETTINGS_HELPER_REMEDY,
        )
    return ok("'dlux' and all four rendering dependencies are installed.")


@check('settings.installed_apps_order', 'settings', 'dlux precedes crispy_bootstrap5')
def _check_installed_apps_order(ctx):
    installed = list(getattr(settings, 'INSTALLED_APPS', []))
    if 'dlux' not in installed or 'crispy_bootstrap5' not in installed:
        return skip('Ordering is only meaningful once both apps are installed.')
    if installed.index('dlux') > installed.index('crispy_bootstrap5'):
        return warn(
            "'dlux' appears after 'crispy_bootstrap5', so dlux template overrides lose precedence.",
            SETTINGS_HELPER_REMEDY,
        )
    return ok("'dlux' template overrides take precedence.")


@check('settings.middleware', 'settings', 'DluxMiddleware is installed')
def _check_middleware(ctx):
    middleware = list(getattr(settings, 'MIDDLEWARE', []))
    configured = getattr(settings, 'DLUX_MIDDLEWARE', 'dlux.middleware.DluxMiddleware')
    legacy = 'dlux.middleware.ActivityLogMiddleware'
    present = [path for path in (configured, legacy) if path in middleware]
    if not present:
        return fail('No dlux middleware is installed; activity logging and scope resolution are inactive.',
                    SETTINGS_HELPER_REMEDY)
    if legacy in middleware and configured not in middleware:
        return warn(f"Using the legacy '{legacy}'. Replace it with '{configured}'.", SETTINGS_HELPER_REMEDY)
    return ok(f"'{present[0]}' is installed.")


@check('settings.middleware_order', 'settings', 'DluxMiddleware runs after auth')
def _check_middleware_order(ctx):
    middleware = list(getattr(settings, 'MIDDLEWARE', []))
    configured = getattr(settings, 'DLUX_MIDDLEWARE', 'dlux.middleware.DluxMiddleware')
    if configured not in middleware:
        return skip('Ordering is only meaningful once the middleware is installed.')
    index = middleware.index(configured)
    required_before = [
        'django.contrib.sessions.middleware.SessionMiddleware',
        'django.contrib.auth.middleware.AuthenticationMiddleware',
    ]
    late = [path for path in required_before if path in middleware and middleware.index(path) > index]
    if late:
        return fail(
            'dlux middleware runs before ' + ', '.join(late) + ', so request.user is unavailable to it.',
            SETTINGS_HELPER_REMEDY,
        )
    return ok('dlux middleware runs after session and authentication middleware.')


@check('settings.context_processors', 'settings', 'dlux context processor is wired')
def _check_context_processors(ctx):
    target = 'dlux.context_processors.dlux_context'
    for template in getattr(settings, 'TEMPLATES', []) or []:
        processors = (template.get('OPTIONS') or {}).get('context_processors') or []
        if target in processors:
            return ok(f"'{target}' is configured.")
    return fail(f"'{target}' is missing; dlux templates will render without branding or navigation.",
                SETTINGS_HELPER_REMEDY)


@check('settings.crispy', 'settings', 'Crispy template pack is bootstrap5')
def _check_crispy(ctx):
    pack = getattr(settings, 'CRISPY_TEMPLATE_PACK', None)
    if pack == 'bootstrap5':
        return ok("CRISPY_TEMPLATE_PACK is 'bootstrap5'.")
    if pack:
        return warn(f"CRISPY_TEMPLATE_PACK is '{pack}'; dlux forms are authored for 'bootstrap5'.",
                    SETTINGS_HELPER_REMEDY)
    return warn('CRISPY_TEMPLATE_PACK is not configured.', SETTINGS_HELPER_REMEDY)


@check('settings.helper', 'settings', 'dlux_settings() helper is wired')
def _check_settings_helper(ctx):
    path = _settings_file()
    if not path or not path.exists():
        return skip('Settings module file could not be located for inspection.')
    try:
        contents = path.read_text(encoding='utf-8')
    except OSError as exc:
        return skip(f'Settings module is unreadable: {exc}.')
    if 'from dlux.utils import' in contents and 'dlux_settings(globals())' in contents:
        return ok(f'{path.name} calls dlux_settings(globals()).')
    return warn(
        f'{path.name} configures dlux manually rather than through the helper, so new dlux '
        'releases will not pick up settings defaults automatically.',
        SETTINGS_HELPER_REMEDY,
    )


@check('urls.mounted', 'urls', 'dlux URLs are mounted')
def _check_urls(ctx):
    from django.urls import NoReverseMatch, reverse
    try:
        reverse('login')
    except NoReverseMatch:
        return fail(
            "Cannot reverse 'login'; dlux URLs are not mounted.",
            "In your project's urls.py:\n"
            "    from django.urls import include, path\n"
            "    urlpatterns = [path('', include('dlux.urls'))]",
        )
    except Exception as exc:
        return fail(f'URL resolution failed: {type(exc).__name__}: {exc}.')
    return ok("dlux URLs resolve ('login' reversed successfully).")


# ── Database ───────────────────────────────────────────────────────────────

@check('db.reachable', 'database', 'Database is reachable')
def _check_db_reachable(ctx):
    if ctx.db_available:
        engine = (settings.DATABASES.get('default') or {}).get('ENGINE', 'unknown')
        return ok(f'Connected using {engine}.')
    return fail(f'Database connection failed. {ctx.db_error}',
                'Confirm the db service is healthy and POSTGRES_* credentials match compose.yml.')


@check('db.migrations', 'database', 'All migrations are applied')
def _check_migrations(ctx):
    if not ctx.db_available:
        return skip('Skipped: the database is unreachable.')
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor
    executor = MigrationExecutor(connection)
    targets = executor.loader.graph.leaf_nodes()
    plan = executor.migration_plan(targets)
    if not plan:
        return ok('No unapplied migrations.')
    labels = ', '.join(f'{migration.app_label}.{migration.name}' for migration, _ in plan[:5])
    if len(plan) > 5:
        labels += f' (+{len(plan) - 5} more)'
    return fail(
        f'{len(plan)} unapplied migration(s): {labels}.',
        'Run: python manage.py migrator',
        management_fix(['migrator'], 'Apply pending migrations', STATEFUL),
    )


@check('db.system_config', 'database', 'System settings row loads')
def _check_system_config(ctx):
    if not ctx.db_available:
        return skip('Skipped: the database is unreachable.')
    from .models import SystemSettings
    try:
        row = SystemSettings.load()
    except Exception as exc:
        return fail(f'SystemSettings.load() failed: {type(exc).__name__}: {exc}.',
                    'Run: python manage.py migrator')
    if row is None or not row.pk:
        return warn('No SystemSettings row exists yet; defaults are in use.',
                    'Complete the setup wizard, or run: python manage.py dlux_setup')
    return ok('SystemSettings singleton loaded.')


@check('db.setup_status', 'database', 'Initial setup is complete')
def _check_setup_status(ctx):
    if not ctx.db_available:
        return skip('Skipped: the database is unreachable.')
    from .models import SystemSettings
    try:
        row = SystemSettings.load()
    except Exception as exc:
        return skip(f'System settings unavailable: {type(exc).__name__}.')
    if row is not None and getattr(row, 'is_configured', False):
        return ok('Setup wizard has been completed.')
    return warn('Setup is incomplete; requests are redirected to the setup wizard.',
                'Complete the setup wizard in the browser, or run: python manage.py dlux_setup')


# ── Runtime services ───────────────────────────────────────────────────────

@check('cache.reachable', 'services', 'Cache backend responds')
def _check_cache(ctx):
    from django.core.cache import cache
    backend = (settings.CACHES.get('default') or {}).get('BACKEND', 'unknown')
    probe_key = 'dlux.doctor.probe'
    try:
        cache.set(probe_key, 'ok', 10)
        value = cache.get(probe_key)
        cache.delete(probe_key)
    except Exception as exc:
        return fail(f'Cache round-trip failed on {backend}: {type(exc).__name__}: {exc}.',
                    'Confirm the redis service is healthy and REDIS_URL_DB is correct.')
    if value != 'ok':
        return fail(f'Cache round-trip on {backend} returned {value!r}.')
    return ok(f'Round-trip succeeded on {backend}.')


@check('email.configured', 'services', 'Email backend is configured')
def _check_email_config(ctx):
    backend = getattr(settings, 'EMAIL_BACKEND', '')
    if 'smtp' not in backend.lower():
        return warn(f"EMAIL_BACKEND is '{backend}', so no mail leaves this deployment.",
                    'Set EMAIL_BACKEND to django.core.mail.backends.smtp.EmailBackend for real delivery.')
    host = getattr(settings, 'EMAIL_HOST', '')
    port = getattr(settings, 'EMAIL_PORT', None)
    if not host:
        return fail('EMAIL_BACKEND is SMTP but EMAIL_HOST is empty.')
    return ok(f'SMTP backend targets {host}:{port}.')


@check('email.reachable', 'services', 'SMTP relay accepts connections')
def _check_email_reachable(ctx):
    backend = getattr(settings, 'EMAIL_BACKEND', '')
    if 'smtp' not in backend.lower():
        return skip('Skipped: the configured backend is not SMTP.')
    host = getattr(settings, 'EMAIL_HOST', '')
    port = getattr(settings, 'EMAIL_PORT', None)
    if not host or not port:
        return skip('Skipped: EMAIL_HOST/EMAIL_PORT are incomplete.')
    try:
        socket.create_connection((host, int(port)), timeout=3).close()
    except Exception as exc:
        return fail(
            f'Could not open a TCP connection to {host}:{port}: {type(exc).__name__}: {exc}.',
            'Confirm the smtp-relay service is healthy and shares a network with this container.',
        )
    return ok(f'{host}:{port} accepted a TCP connection.')


@check('celery.configured', 'services', 'Celery broker is configured')
def _check_celery(ctx):
    broker = getattr(settings, 'CELERY_BROKER_URL', '')
    if not broker:
        return warn('CELERY_BROKER_URL is empty; scheduled work (update checks, backups) will not run.')
    if not _installed('celery'):
        return warn('CELERY_BROKER_URL is set but the celery package is not importable.')
    scheme = broker.split('://', 1)[0]
    return ok(f'Broker configured over {scheme}.')


@check('static.collected', 'static', 'Static files are collected')
def _check_static(ctx):
    static_root = getattr(settings, 'STATIC_ROOT', '')
    if not static_root:
        return warn('STATIC_ROOT is not set, so collectstatic has nowhere to write.', SETTINGS_HELPER_REMEDY)
    root = Path(static_root)
    if not root.exists():
        return fail(
            f'STATIC_ROOT ({root}) does not exist; the app will serve no CSS or JS.',
            'Run: python manage.py collectstatic --noinput',
            management_fix(['collectstatic', '--noinput'], 'Collect static files'),
        )
    if not any(root.iterdir()):
        return fail(
            f'STATIC_ROOT ({root}) is empty.',
            'Run: python manage.py collectstatic --noinput',
            management_fix(['collectstatic', '--noinput'], 'Collect static files'),
        )
    if not (root / 'dlux').exists():
        return warn(
            f'{root} has content but no dlux/ directory; dlux assets may be missing.',
            'Run: python manage.py collectstatic --noinput',
            management_fix(['collectstatic', '--noinput'], 'Collect static files'),
        )
    return ok(f'{root} is populated and contains dlux assets.')


# ── Production safety ──────────────────────────────────────────────────────

@check('security.debug', 'security', 'DEBUG is disabled')
def _check_debug(ctx):
    if not getattr(settings, 'DEBUG', False):
        return ok('DEBUG is False.')
    return warn(
        'DEBUG is True. Tracebacks, settings, and SQL are exposed to anyone who triggers an error.',
        'Set DEBUG_STATUS=False in .secrets/.env for any deployment reachable by others.',
    )


@check('security.secret_key', 'security', 'SECRET_KEY is not a placeholder')
def _check_secret_key(ctx):
    key = str(getattr(settings, 'SECRET_KEY', '') or '')
    if not key:
        return fail('SECRET_KEY is empty.', 'Set DJANGO_SECRET_KEY in .secrets/.env.')
    if key in {'local_secret', 'changeme', 'secret'}:
        return fail(
            'SECRET_KEY is the scaffold placeholder, so sessions and password-reset tokens are forgeable.',
            'Generate one and set DJANGO_SECRET_KEY in .secrets/.env.',
        )
    if len(key) < 32:
        return warn(f'SECRET_KEY is only {len(key)} characters; 50+ is recommended.')
    return ok(f'SECRET_KEY is set ({len(key)} characters).')


@check('security.allowed_hosts', 'security', 'ALLOWED_HOSTS is restrictive')
def _check_allowed_hosts(ctx):
    hosts = list(getattr(settings, 'ALLOWED_HOSTS', []) or [])
    if getattr(settings, 'DEBUG', False):
        return skip('Skipped: DEBUG is True, where Django relaxes host validation.')
    if not hosts:
        return fail('ALLOWED_HOSTS is empty; every request will be rejected.',
                    'Set ALLOWED_HOSTS in .secrets/.env.')
    if '*' in hosts:
        return warn("ALLOWED_HOSTS contains '*', which disables Host header validation.",
                    'List the hostnames this deployment actually serves.')
    return ok(f'{len(hosts)} host(s) allowed.')


@check('security.csrf_origins', 'security', 'CSRF_TRUSTED_ORIGINS covers BASE_URL')
def _check_csrf_origins(ctx):
    base_url = ctx.base_url
    if not base_url:
        return skip('Skipped: BASE_URL is not set.')
    origins = list(getattr(settings, 'CSRF_TRUSTED_ORIGINS', []) or [])
    if not origins:
        if base_url.startswith('https://'):
            return fail(
                f'CSRF_TRUSTED_ORIGINS is empty while BASE_URL is {base_url}; POST requests behind '
                'the TLS terminator will be rejected.',
                f'Add {base_url} to CSRF_TRUSTED_ORIGINS (ALLOWED_URLS in .secrets/.env).',
            )
        return warn('CSRF_TRUSTED_ORIGINS is empty.')
    normalized = {origin.rstrip('/') for origin in origins}
    if base_url.rstrip('/') not in normalized:
        return warn(
            f'BASE_URL ({base_url}) is not listed in CSRF_TRUSTED_ORIGINS.',
            f'Add {base_url} to ALLOWED_URLS in .secrets/.env.',
        )
    return ok(f'BASE_URL is covered by {len(origins)} trusted origin(s).')


@check('security.proxy_ssl_header', 'security', 'Proxy SSL header is set for HTTPS')
def _check_proxy_ssl_header(ctx):
    if not ctx.expects_https:
        return skip('Skipped: BASE_URL is not HTTPS.')
    if getattr(settings, 'SECURE_PROXY_SSL_HEADER', None):
        return ok('SECURE_PROXY_SSL_HEADER is configured.')
    return warn(
        'BASE_URL is HTTPS but SECURE_PROXY_SSL_HEADER is unset, so Django treats proxied requests '
        'as insecure and may redirect in a loop.',
        "Set SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https') and ensure the proxy sends it.",
    )


@check('security.cookies', 'security', 'Cookies are marked secure over HTTPS')
def _check_cookies(ctx):
    if not ctx.expects_https:
        return skip('Skipped: BASE_URL is not HTTPS.')
    insecure = [
        name for name in ('SESSION_COOKIE_SECURE', 'CSRF_COOKIE_SECURE')
        if not getattr(settings, name, False)
    ]
    if insecure:
        return warn(
            f'{" and ".join(insecure)} are False while BASE_URL is HTTPS, so cookies may be sent in clear text.',
            'Set both to True once TLS terminates in front of this deployment.',
        )
    return ok('Session and CSRF cookies are restricted to HTTPS.')


@check('packages.optional', 'packages', 'Optional packages')
def _check_optional_packages(ctx):
    optional = {
        'pypi_attestations': 'inline updater attestation verification',
        'dlux_sso': 'single sign-on',
        'celery': 'scheduled tasks',
        'redis': 'cache and broker client',
    }
    present = [name for name in optional if _installed(name)]
    missing = {name: purpose for name, purpose in optional.items() if name not in present}
    detail = f"Installed: {', '.join(present) or 'none'}."
    if missing:
        detail += ' Absent: ' + ', '.join(f'{name} ({purpose})' for name, purpose in missing.items()) + '.'
    return ok(detail)


def run_checks(only_groups=None):
    """Execute every registered check and return the report dict."""
    ctx = Context()
    results = []
    for check_id, group, title, func in _REGISTRY:
        if only_groups and group not in only_groups:
            continue
        try:
            finding = func(ctx)
        except Exception as exc:
            finding = fail(f'Check raised {type(exc).__name__}: {exc}.')
        results.append(CheckResult(
            id=check_id,
            group=group,
            title=title,
            status=finding.status,
            detail=finding.detail,
            remedy=finding.remedy,
            fix=finding.fix,
        ))
    return build_report(results)


def build_report(results):
    counts = {OK: 0, WARNING: 0, ERROR: 0, SKIPPED: 0}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    overall = OK
    for result in results:
        if _STATUS_RANK.get(result.status, 0) > _STATUS_RANK[overall]:
            overall = result.status
    return {
        'schema_version': SCHEMA_VERSION,
        'producer': 'dlux',
        'producer_version': __version__,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'status': overall,
        'counts': counts,
        'checks': [result.as_dict() for result in results],
    }


def applicable_fixes(report, allowed_safety):
    """Fixes for failing checks whose safety tier the caller has authorized."""
    fixes = []
    for entry in report['checks']:
        fix = entry.get('fix')
        if not fix or entry['status'] not in {WARNING, ERROR}:
            continue
        if fix.get('safety') in allowed_safety:
            fixes.append((entry['id'], fix))
    return fixes
