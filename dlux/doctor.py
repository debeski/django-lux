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

Checks never hang either. A run happens inside ``session()``: the database and
cache are probed first under short socket timeouts, every check runs in a
worker thread with its own deadline, and the whole pass has one more. A check
that does not answer in time is reported as an error with its timing, and the
report goes on without it.
"""
import copy
import importlib
import logging
import os
import socket
import threading
import time
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings

from . import __version__
from .utils.settings import PLACEHOLDER_SECRET_KEYS


SCHEMA_VERSION = 1

#: Socket timeout, in seconds, for the database and cache connections a run opens,
#: whatever the project's DATABASES and CACHES say.
PROBE_TIMEOUT = 5
#: Seconds one check (or the opening database and cache probe) may take before
#: it is reported as not answering and abandoned.
CHECK_TIMEOUT = 10
#: Seconds the whole check pass may take; checks not started by then are skipped.
RUN_TIMEOUT = 60
#: Seconds ``manage.py dlux_doctor`` may run in all before it prints a deadline
#: error and exits. Below the 120 s ``composer check --deep`` waits for it.
PROCESS_TIMEOUT = 100

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


def _describe(exc):
    """``Type: message`` on one line, for a report or a log record."""
    message = ' '.join(str(exc).split())
    return f'{type(exc).__name__}: {message}' if message else type(exc).__name__


@dataclass
class Outcome:
    value: object = None
    error: BaseException = None
    timed_out: bool = False
    elapsed: float = 0.0


class _Runner:
    """Runs callables in daemon threads, each with a deadline.

    A thread that misses its deadline is abandoned, not killed: Python cannot
    interrupt a blocked socket read, and a daemon thread does not keep the
    process alive.

    Each worker opens its own database connections, so an abandoned one never
    holds a connection this thread goes on to use (``--apply`` runs the
    migrator here, with no deadline). The exception is a connection this
    thread holds inside a transaction, as a test does: the worker must see that
    transaction, so it shares it, until the first timeout.
    """

    def __init__(self):
        self.share_connections = True

    def run(self, func, timeout):
        from django.db import connections

        shared = []
        if self.share_connections:
            shared = [connections[alias] for alias in connections if connections[alias].in_atomic_block]
            for conn in shared:
                conn.inc_thread_sharing()
        box = {}

        def target():
            try:
                for conn in shared:
                    connections[conn.alias] = conn
                box['value'] = func()
            except BaseException as exc:
                box['error'] = exc
            finally:
                for conn in connections.all(initialized_only=True):
                    if conn not in shared:
                        conn.close()

        started = time.monotonic()
        worker = threading.Thread(target=target, name='dlux-doctor-check', daemon=True)
        worker.start()
        worker.join(max(timeout, 0))
        elapsed = time.monotonic() - started
        if worker.is_alive():
            self.share_connections = False
            return Outcome(timed_out=True, elapsed=elapsed)
        for conn in shared:
            conn.dec_thread_sharing()
        return Outcome(value=box.get('value'), error=box.get('error'), elapsed=elapsed)


_runner = threading.local()


def _run_bounded(func, timeout):
    runner = getattr(_runner, 'active', None) or _Runner()
    return runner.run(func, timeout)


def _probe_database():
    from django.db import connection

    connection.ensure_connection()


CACHE_PROBE_KEY = 'dlux.doctor.probe'


def _cache_round_trip():
    from django.core.cache import cache

    cache.set(CACHE_PROBE_KEY, 'ok', 10)
    value = cache.get(CACHE_PROBE_KEY)
    cache.delete(CACHE_PROBE_KEY)
    return value


@dataclass
class Context:
    """Shared probe state, so a dead database or cache is diagnosed once rather
    than by every check that depends on it."""

    _db_error: str = field(default=None, init=False)
    _db_probed: bool = field(default=False, init=False)
    _cache_error: str = field(default=None, init=False)
    _cache_backend: str = field(default='', init=False)
    _cache_probed: bool = field(default=False, init=False)

    @property
    def db_available(self):
        if not self._db_probed:
            self._db_probed = True
            outcome = _run_bounded(_probe_database, CHECK_TIMEOUT)
            if outcome.timed_out:
                self._db_error = f'No answer within {outcome.elapsed:.1f} s.'
            elif outcome.error is not None:
                self._db_error = f'{_describe(outcome.error)} (after {outcome.elapsed:.1f} s)'
            else:
                self._db_error = ''
        return not self._db_error

    @property
    def db_error(self):
        self.db_available
        return self._db_error

    @property
    def cache_available(self):
        if not self._cache_probed:
            self._cache_probed = True
            self._cache_backend = (settings.CACHES.get('default') or {}).get('BACKEND', 'unknown')
            outcome = _run_bounded(_cache_round_trip, CHECK_TIMEOUT)
            if outcome.timed_out:
                self._cache_error = f'no answer within {outcome.elapsed:.1f} s'
            elif outcome.error is not None:
                self._cache_error = f'{_describe(outcome.error)} (after {outcome.elapsed:.1f} s)'
            elif outcome.value != 'ok':
                self._cache_error = f'the round-trip returned {outcome.value!r}'
            else:
                self._cache_error = ''
        return not self._cache_error

    @property
    def cache_error(self):
        self.cache_available
        return self._cache_error

    @property
    def cache_backend(self):
        self.cache_available
        return self._cache_backend

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

DJANGO_CHECKS_ID = 'settings.django_checks'

#: Django's checks and URL resolution import the URLconf, whose modules translate
#: strings as they load, and Django's model checks translate names. Each
#: translation builds the system config, which reads System Settings (and the
#: managed fonts) from the database: with it paused, each read waits out the
#: connect timeout, and the check outlasts its deadline.
NEEDS_DATABASE_FOR_TRANSLATIONS = (
    'Skipped: the database is unreachable, and this check needs it: importing the URLconf '
    'and translating names builds the system config from System Settings.'
)


@check(DJANGO_CHECKS_ID, 'settings', "Django's system checks pass")
def _check_django_system_checks(ctx):
    """Django's own checks, as one finding of the report.

    Run by the command before ``handle()``, an error-level message stopped the
    doctor before it printed anything, and ``composer check --deep`` got no
    report. Here they run under the same deadline as every other check.
    """
    if not ctx.db_available:
        return skip(NEEDS_DATABASE_FOR_TRANSLATIONS)
    from django.core import checks

    messages = [message for message in checks.run_checks() if not message.is_silenced()]
    errors = [message for message in messages if message.level >= checks.ERROR]
    warnings = [message for message in messages if checks.WARNING <= message.level < checks.ERROR]

    def listed(found):
        shown = '; '.join(f'{message.id or "?"} ({message.obj}): {message.msg}' for message in found[:5])
        return shown + (f' (+{len(found) - 5} more)' if len(found) > 5 else '')

    remedy = 'Run: python manage.py check, and fix what it lists (or add the ids to SILENCED_SYSTEM_CHECKS).'
    if errors:
        return fail(f'{len(errors)} error(s): {listed(errors)}.', remedy)
    if warnings:
        return warn(f'{len(warnings)} warning(s): {listed(warnings)}.', remedy)
    return ok('No errors or warnings.')


@check('settings.session_cookie', 'settings', 'Session cookie can be stored by a browser')
def _check_session_cookie(ctx):
    """The pair of settings that turn a correct password into a silent loop.

    Neither is wrong — both are right for a deployment reached over TLS at its
    own hostname — but read together they say exactly where sign-in can work,
    which is not obvious from a login form that simply reappears.
    """
    secure = bool(getattr(settings, 'SESSION_COOKIE_SECURE', False))
    domain = (getattr(settings, 'SESSION_COOKIE_DOMAIN', '') or '').lstrip('.')
    if not secure and not domain:
        return ok('The session cookie is not restricted to HTTPS or to one domain.')
    where = []
    if secure:
        where.append('over HTTPS')
    if domain:
        where.append(f'at {domain} (or a subdomain)')
    return ok(
        'Signing in works only ' + ' and '.join(where) + '. Reached any other way, '
        'the browser discards the session cookie and the login form returns with '
        'no error; the login page reports that when it happens.'
    )


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
    if not ctx.db_available:
        return skip(NEEDS_DATABASE_FOR_TRANSLATIONS)
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
    """Reports the probe ``session()`` made before any other check ran.

    When it failed, the rest of the run used a dummy cache, so the checks after
    it read the database directly instead of each waiting on the dead cache.
    """
    if ctx.cache_available:
        return ok(f'Round-trip succeeded on {ctx.cache_backend}.')
    return fail(
        f'Cache round-trip failed on {ctx.cache_backend}: {ctx.cache_error}. '
        'The rest of this report read the database without the cache.',
        'Confirm the redis service is running and not paused (docker compose ps), '
        'and that REDIS_URL_DB is correct.',
    )


@check('updater.runtime_volume', 'services', 'Inline-update runtime volume is usable')
def _check_updater_runtime_volume(ctx):
    """Inline updates are opt-in; when they are on, the volume must be writable.

    Without this the failure is invisible until someone clicks Update: the run
    queues and nothing can drain it.

    "Writable" means writable *by the process that writes it* — the task worker. Doctor
    usually runs in web, whose mount is read-only by design, so it reports the
    worker's recorded verdict rather than its own probe.
    """
    from .updater.service import (
        local_runtime_volume_problem,
        runtime_volume_problem,
        updates_enabled,
        worker_volume_report,
    )

    if not updates_enabled():
        return skip('Skipped: inline updates are disabled for this deployment.')
    if ctx is not None and not ctx.db_available:
        # The worker's verdict lives in the database. Falling back to this
        # process's own probe would call web's read-only mount a fault.
        return skip('Skipped: the database is unreachable, so the task worker\'s '
                    'runtime-volume report cannot be read.')
    problem = runtime_volume_problem()
    if problem:
        return fail(
            problem,
            'Mount the dlux_runtime volume, or set DLUX_UPDATE_RUNTIME_ROOT to a writable path.',
        )
    root = getattr(settings, 'DLUX_UPDATE_RUNTIME_ROOT', '/opt/dlux-runtime')
    report = worker_volume_report()
    if report is None:
        return ok(f'Runtime volume at {root} is writable from this process; '
                  'no update worker has reported yet.')
    if report['stale']:
        return warn(
            f"The update worker last reported the runtime volume at {root} writable "
            f"at {report['seen_at'].isoformat()}, and has not reported since.",
            'Check that the worker service (python manage.py dlux_worker) is running.',
        )
    if local_runtime_volume_problem():
        return ok(f'The update worker reports the runtime volume at {root} writable '
                  '(this process holds it read-only, which is the expected web mount).')
    return ok(f'Runtime volume at {root} is writable.')


@check('updater.image_floor', 'services', 'This image can run the active DjangoLux release')
def _check_updater_image_floor(ctx):
    """The active volume release needs a newer image.

    The supervisor falls back to the baked release loudly at boot; this makes the
    same verdict an error here, so an image rolled back under a newer release is
    not missed. An image whose own supervisor predates the floor check runs the
    release anyway, and so does this process; the detail says which one runs.
    """
    from .updater.supervisor import baked_version, held_release_outcome, runtime_fallback

    root = getattr(settings, 'DLUX_UPDATE_RUNTIME_ROOT', '/opt/dlux-runtime')
    baked = os.environ.get('DLUX_BAKED_VERSION') or baked_version()
    problem = runtime_fallback(root, baked)
    if problem:
        return fail(
            f'{problem}. {held_release_outcome(baked, __version__)}.',
            'Deploy a project image built on that DjangoLux or later, or roll the inline '
            'release back with ./start.sh dlux rollback.',
        )
    return ok('The image meets the active release\'s floor, or no newer volume release is active.')


@check('updater.update_policy', 'services', 'The deployment update policy is enforced')
def _check_update_policy(ctx):
    """Reports ``DLUX_UPDATE_POLICY`` and whether the resident Composer enforces it."""
    from .updater import policy as update_policy

    status = update_policy.status()
    allowed = {
        update_policy.ALL: 'every update path is allowed',
        update_policy.INLINE: 'DjangoLux inline updates only; application image and Composer updates are refused',
        update_policy.NONE: 'updates are refused; checks and rollbacks still run',
    }[status['policy']]
    detail = f'Policy {status["policy"]}: {allowed}.'
    if not status['configured_valid']:
        return warn(
            f'{detail} DLUX_UPDATE_POLICY has an unknown value, so it counts as none.',
            'Set DLUX_UPDATE_POLICY to all, inline or none in .secrets/.env, then redeploy.',
        )
    if status['mismatch']:
        return warn(
            f'{detail} The application reads {status["configured"]}, the resident Composer '
            f'enforces {status["resident"]}; the stricter one applies.',
            'Run ./start.sh on the server: Composer recreates composer-agent and '
            'composer-executor with the secrets file\'s value.',
        )
    if status['resident_unenforced']:
        return warn(
            f'{detail} The resident Composer does not report the policy, so only the '
            'application refuses; a compromised web container could still request an image update.',
            'Update the resident Composer to 1.11.0 or later: ./start.sh agent update',
        )
    return ok(detail)


@check('stack.schema', 'services', 'Stack files match the stack contract schema')
def _check_stack_schema(ctx):
    """Compares compose.yml's ``DLUX_STACK_SCHEMA`` with the running contract.

    Never an error: an unstamped stack predates stamping, and a mismatch means
    the generated files need the migration notes, not that the site is down.
    """
    from .contracts.stack import STACK_SCHEMA_ENV, stack_schema

    expected = stack_schema()
    raw = os.environ.get(STACK_SCHEMA_ENV, '').strip()
    if not raw:
        return skip(f'No {STACK_SCHEMA_ENV} in this environment: the stack was generated '
                    f'before schema stamping. This DjangoLux expects stack schema {expected}.')
    try:
        declared = int(raw)
    except ValueError:
        return warn(f'{STACK_SCHEMA_ENV}={raw!r} is not a number.',
                    f'Set {STACK_SCHEMA_ENV}: "{expected}" in compose.yml\'s x-environment block.')
    if declared == expected:
        return ok(f'compose.yml declares stack schema {declared}.')
    # The value is this container's environment, fixed when it was created: a
    # stack migrated since (composer check --fix restamps compose.yml) still
    # shows the old number until the service is recreated.
    if declared < expected:
        return warn(
            f'This service runs with stack schema {declared}; this DjangoLux expects {expected}.',
            f'If compose.yml already sets {STACK_SCHEMA_ENV}: "{expected}", recreate web and worker to '
            'pick it up: Recreate in the Operations panel, or ./start.sh. Otherwise run ./start.sh '
            'check --fix, which applies the changes between the two schemas and restamps compose.yml, '
            'then recreate. Composer 1.11.0 or later restamps every stamp in the file; an older one '
            'restamps only the first, so a compose.yml that also carries a "# dlux stack schema" '
            f'comment keeps its old {STACK_SCHEMA_ENV}: set it to "{expected}" by hand. Without '
            'Composer, apply the changes docs/stack-schema.md lists between the two schemas, then '
            f'set {STACK_SCHEMA_ENV}: "{expected}" in compose.yml.',
        )
    return warn(
        f'This service runs with stack schema {declared}; this DjangoLux expects {expected} '
        '(the stack files are newer).',
        'Update DjangoLux to a release that supports this stack schema.',
    )


EMAIL_STEP = 'System Settings > Email'
EMAIL_OFF = f'Skipped: email delivery is off ({EMAIL_STEP}), so features that send mail stay locked.'
_EMAIL_NOT_CONFIGURED = {
    'relay_missing_upstream_host_port_or_from_email': 'the provider host or port, or the sender address, is missing',
    'relay_missing_password': 'a provider username is set but no password',
    'smtp_missing_host_port_or_from_email': 'the provider host or port, or the sender address, is missing',
    'encrypted_db_missing_password': 'a provider username is set but no password is stored',
    'missing_default_from_email': 'there is no sender address',
}


def _email_step(ctx):
    """``(stored, connection, status)`` for the Email step, or a Finding when it cannot be read.

    ``stored`` is the step's saved settings, ``connection`` what a send connects to
    (the internal relay, or the provider), ``status`` whether that is complete.
    """
    if ctx is not None and not ctx.db_available:
        return skip(f'Skipped: the database is unavailable, so {EMAIL_STEP} cannot be read.')
    from django.apps import apps

    from .utils import get_dlux_email_config, get_email_service_status
    from .utils.config import normalize_email_config

    try:
        SystemSettings = apps.get_model('dlux', 'SystemSettings')
        stored = normalize_email_config(getattr(SystemSettings.load(), 'email_config', {}) or {})
    except Exception as exc:
        return skip(f'Skipped: {EMAIL_STEP} cannot be read: {type(exc).__name__}.')
    return stored, get_dlux_email_config(), get_email_service_status(stored)


@check('email.configured', 'services', 'Email delivery is configured')
def _check_email_config(ctx):
    step = _email_step(ctx)
    if isinstance(step, Finding):
        return step
    stored, connection, status = step
    if not stored.get('enabled'):
        return skip(EMAIL_OFF)
    backend = connection.get('backend', '')
    if 'smtp' not in backend.lower():
        return warn(f"EMAIL_BACKEND is '{backend}', so no mail leaves this deployment.",
                    'Set EMAIL_BACKEND to django.core.mail.backends.smtp.EmailBackend for real delivery, or choose '
                    f'the internal SMTP relay in {EMAIL_STEP}.')
    relay = status.get('transport') == 'relay'
    route = 'through the internal SMTP relay' if relay else 'directly from the web service'
    reason = status.get('reason')
    if reason == 'relay_env_not_visible':
        return warn(
            'Email goes through the internal SMTP relay, but the web service cannot see the relay\'s settings '
            '(compose.yml passes them to smtp-relay only), so only a test email can check them.',
            'Run ./start.sh check --fix, then ./start.sh.',
        )
    if status.get('configured'):
        detail = status.get('detail')
        return ok(f'Email goes {route}' + (f' to {detail}.' if detail else '.'))
    return fail(
        f"Email goes {route}, but {_EMAIL_NOT_CONFIGURED.get(reason, reason or 'it is incomplete')}.",
        f'Complete {EMAIL_STEP}, then send a test email.',
    )


@check('email.reachable', 'services', 'Mail server accepts connections')
def _check_email_reachable(ctx):
    step = _email_step(ctx)
    if isinstance(step, Finding):
        return step
    stored, connection, _status = step
    if not stored.get('enabled'):
        return skip(EMAIL_OFF)
    if 'smtp' not in str(connection.get('backend', '')).lower():
        return skip('Skipped: the configured backend is not SMTP.')
    host, port = connection.get('host'), connection.get('port')
    if not host or not port:
        return skip('Skipped: the provider host or port is not set.')
    if connection.get('transport') == 'relay':
        from .utils import internal_smtp_relay_available

        if internal_smtp_relay_available(host=host, port=port):
            return ok(f'The internal SMTP relay answers on {host}:{port}.')
        return fail(
            f'The internal SMTP relay does not answer on {host}:{port}.',
            'Confirm the smtp-relay service is running and healthy (./start.sh check) and shares a network '
            'with this container.',
        )
    try:
        socket.create_connection((host, int(port)), timeout=3).close()
    except Exception as exc:
        return fail(
            f'Could not open a TCP connection to the provider {host}:{port}: {type(exc).__name__}: {exc}.',
            'On this route the web service connects to the provider itself. A stack generated by python -m dlux '
            f'startproject gives web no internet access: choose the internal SMTP relay in {EMAIL_STEP}, or give '
            'web a route to the provider.',
        )
    return ok(f'The provider {host}:{port} accepted a TCP connection.')


@check('tasks.worker', 'services', 'DjangoLux task worker is running')
def _check_task_worker(ctx):
    """An error without a live worker: every DjangoLux task runs there, so
    scheduled backups, update checks and OCR silently stop."""
    from .taskrunner.config import runner_config
    from .taskrunner.queue import live_dlux_workers, queue_summary

    if ctx is not None and not ctx.db_available:
        return skip('Skipped: the database is unreachable, so worker heartbeats cannot be read.')
    try:
        workers = list(live_dlux_workers().values_list('version', flat=True))
        summary = queue_summary()
    except Exception as exc:
        return fail(
            f'The task queue tables cannot be read: {_describe(exc)}.',
            'Apply pending migrations: python manage.py migrate',
        )
    if not workers:
        return fail(
            f'No dlux_worker has sent a heartbeat in the last {runner_config()["stale_after"]} s, so queued and '
            f'scheduled tasks (backups, update checks, OCR) are not running ({summary["ready"]} due now).',
            'Start the worker service. A stack generated before stack schema 5 has none: with this '
            'image deployed, run ./start.sh check --fix (Composer 1.10+), then recreate the stack. Outside Docker: '
            'python manage.py dlux_worker',
        )
    if summary['failed'] or summary['schedules_failing']:
        return warn(
            f'{len(workers)} worker(s) alive, but {summary["failed"]} task run(s) failed and '
            f'{summary["schedules_failing"]} scheduled task(s) failed their last run.',
            'See the Tasks row on the Options page, or the worker log.',
        )
    return ok(f'{len(workers)} worker(s) alive (DjangoLux {", ".join(sorted(set(workers)))}); {summary["ready"]} task(s) due.')


def _project_celery_signals():
    """What still ties this project to Celery: settings, beat entries, its Celery app."""
    import importlib.util

    signals = []
    if getattr(settings, 'CELERY_BROKER_URL', ''):
        signals.append('CELERY_BROKER_URL is set')
    beat = getattr(settings, 'CELERY_BEAT_SCHEDULE', None) or {}
    if beat:
        signals.append('CELERY_BEAT_SCHEDULE has ' + ', '.join(sorted(beat)))
    package = (os.environ.get('DJANGO_SETTINGS_MODULE') or '').rpartition('.')[0]
    if package:
        try:
            if importlib.util.find_spec(f'{package}.celery') is not None:
                signals.append(f'{package}/celery.py defines a Celery app')
        except (ImportError, ValueError):
            pass
    return signals


@check('storage.mount_access', 'services', 'The app can use its mounted data')
def _check_mount_access(ctx):
    from . import mount_access

    base_dir = getattr(settings, 'BASE_DIR', None)
    extra = [
        path for path in (
            getattr(settings, 'MEDIA_ROOT', None),
            getattr(settings, 'STATIC_ROOT', None),
            Path(base_dir) / 'logs' if base_dir else None,
            getattr(settings, 'DLUX_UPDATE_RUNTIME_ROOT', None),
        ) if path
    ]
    result = mount_access.report(extra=extra)
    who = f'uid {result["uid"]} (gid {result["gid"]})'
    sample = '; '.join(
        f'{item["path"]} ({item["kind"]} {item["owner"]} {item["mode"]}, needs {item["needs"]})'
        for item in result['sample'][:5]
    )
    if result['running_as_root']:
        if not result['problems']:
            return ok(f'The app runs as root; its data is also ready for {who}.')
        return skip(
            f'Skipped: the app runs as root. Before it can run as {who}, {result["problems"]} '
            f'entr{"y needs" if result["problems"] == 1 else "ies need"} group access, e.g. {sample}. '
            + mount_access.FIX_HINT
        )
    if result['problems']:
        return fail(
            f'{who} cannot use {result["problems"]} entr{"y" if result["problems"] == 1 else "ies"} '
            f'of its mounted data, e.g. {sample}.',
            mount_access.FIX_HINT,
        )
    return ok(f'{who} can use everything under {", ".join(result["mounts"]) or "its mounts"}.')


@check('tasks.celery_deprecated', 'services', 'Project tasks do not depend on Celery')
def _check_project_celery(ctx):
    signals = _project_celery_signals()
    if not signals:
        return ok('This project has no Celery app, beat entries or broker setting.')
    return warn(
        'Celery for project tasks is deprecated, and generated stacks stop installing it in 1.18: '
        + '; '.join(signals) + '.',
        'Move project tasks to @dlux.taskrunner.task and their schedule to DLUX_TASK_SCHEDULE, then '
        'remove the celery service, celery.py and the CELERY_* settings (docs/task-runner.md, '
        '"Moving project tasks from Celery").',
    )


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
    shipped = _shipped_static_files()
    missing = [name for name in shipped if not (root / name).is_file()]
    if missing:
        sample = ', '.join(missing[:3]) + (f' (+{len(missing) - 3} more)' if len(missing) > 3 else '')
        return fail(
            f'{len(missing)} of the {len(shipped)} static files DjangoLux {__version__} ships are missing '
            f'from {root}, so pages that load them get 404s: {sample}.',
            'Run: python manage.py collectstatic --noinput',
            management_fix(['collectstatic', '--noinput'], 'Collect static files'),
        )
    return ok(f'{root} holds all {len(shipped)} static files DjangoLux {__version__} ships.')


def _shipped_static_files():
    """Paths, relative to STATIC_ROOT, of every file in the running dlux's ``static/``.

    Read from the package that is actually running, so after an inline update
    it names the files the new release needs. Skips what collectstatic ignores
    by default (dotfiles, ``*~``).
    """
    source = Path(__file__).resolve().parent / 'static'
    names = []
    for directory, subdirs, files in os.walk(source):
        subdirs[:] = [name for name in subdirs if not name.startswith('.')]
        for name in files:
            if name.startswith('.') or name.endswith('~'):
                continue
            names.append(Path(directory, name).relative_to(source).as_posix())
    return sorted(names)


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
    if key in PLACEHOLDER_SECRET_KEYS:
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
        'dlux_sso': 'single sign-on',
        'redis': 'cache client',
    }
    present = [name for name in optional if _installed(name)]
    missing = {name: purpose for name, purpose in optional.items() if name not in present}
    detail = f"Installed: {', '.join(present) or 'none'}."
    if missing:
        detail += ' Absent: ' + ', '.join(f'{name} ({purpose})' for name, purpose in missing.items()) + '.'
    return ok(detail)


# ── Run session ────────────────────────────────────────────────────────────

#: Cache backends whose clients take socket timeouts from OPTIONS, and the keys.
_CACHE_TIMEOUT_OPTIONS = {
    'django_redis.cache.RedisCache': ('SOCKET_CONNECT_TIMEOUT', 'SOCKET_TIMEOUT'),
    'dlux.resilient_cache.FailFastRedisCache': ('SOCKET_CONNECT_TIMEOUT', 'SOCKET_TIMEOUT'),
    'django.core.cache.backends.redis.RedisCache': ('socket_connect_timeout', 'socket_timeout'),
    'django.core.cache.backends.memcached.PyMemcacheCache': ('connect_timeout', 'timeout'),
}
_DB_TIMEOUT_VENDORS = {'postgresql', 'mysql'}
DUMMY_CACHE = 'django.core.cache.backends.dummy.DummyCache'


def _capped(value, limit):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 < value <= limit:
        return value
    return limit


def _bounded_caches(caches_setting):
    """A copy of CACHES with every known client's socket timeouts capped at PROBE_TIMEOUT."""
    bounded = copy.deepcopy(caches_setting)
    changed = False
    for conf in bounded.values():
        keys = _CACHE_TIMEOUT_OPTIONS.get(conf.get('BACKEND', ''))
        if not keys:
            continue
        options = conf.setdefault('OPTIONS', {})
        for key in keys:
            options[key] = _capped(options.get(key), PROBE_TIMEOUT)
        changed = True
    return bounded if changed else None


@contextmanager
def _swap_attribute(owner, name, value):
    original = getattr(owner, name)
    setattr(owner, name, value)
    try:
        yield
    finally:
        setattr(owner, name, original)


@contextmanager
def _short_network_timeouts():
    """Cap the cache and database socket timeouts for this run, whatever settings say.

    A project's own CACHES may wait 20 s per read with retries on top, which is
    how a paused Redis held the doctor for minutes. The cap applies to clients
    created inside the run only: django-redis keeps a process-wide pool per URL,
    so the run gets a fresh pool map and puts the old one back afterwards.
    """
    from django.db import connections
    from django.test.utils import override_settings

    with ExitStack() as stack:
        bounded = _bounded_caches(getattr(settings, 'CACHES', {}) or {})
        if bounded is not None:
            try:
                from django_redis.pool import ConnectionFactory
            except ImportError:
                ConnectionFactory = None
            if ConnectionFactory is not None and hasattr(ConnectionFactory, '_pools'):
                stack.enter_context(_swap_attribute(ConnectionFactory, '_pools', {}))
            stack.enter_context(override_settings(CACHES=bounded))

        restore = []
        for alias in connections:
            conn = connections[alias]
            if conn.vendor not in _DB_TIMEOUT_VENDORS:
                continue
            options = conn.settings_dict.setdefault('OPTIONS', {})
            restore.append((options, 'connect_timeout' in options, options.get('connect_timeout')))
            # libpq takes whole seconds and treats anything under 2 as 2.
            options['connect_timeout'] = int(_capped(options.get('connect_timeout'), max(2, PROBE_TIMEOUT)))
        try:
            yield
        finally:
            for options, present, value in restore:
                if present:
                    options['connect_timeout'] = value
                else:
                    options.pop('connect_timeout', None)


class _OncePerRun(logging.Filter):
    """Collapses what a broken dependency makes the rest of the app log.

    With the database down, every config read logged the same warning with a
    full traceback (937 lines before the report). During a run each distinct
    record is shown once, with its exception on the same line.
    """

    VERDICT = '_dlux_doctor_shown'

    def __init__(self):
        super().__init__()
        self.seen = set()

    def filter(self, record):
        # One record reaches every handler it propagates to: decide once, so a
        # second handler is not mistaken for a repeat.
        verdict = getattr(record, self.VERDICT, None)
        if verdict is not None:
            return verdict
        exc = record.exc_info[1] if record.exc_info else None
        if exc is not None:
            key = (record.name, record.levelno, str(record.msg), type(exc).__name__)
        else:
            key = (record.name, record.levelno, record.getMessage())
        verdict = key not in self.seen
        self.seen.add(key)
        if verdict and exc is not None:
            record.msg = f'{record.getMessage()} ({_describe(exc)})'
            record.args = None
            record.exc_info = None
            record.exc_text = None
        setattr(record, self.VERDICT, verdict)
        return verdict


@contextmanager
def _logged_once():
    once = _OncePerRun()
    handlers = set(logging.getLogger().handlers)
    for logger in list(logging.Logger.manager.loggerDict.values()):
        handlers.update(getattr(logger, 'handlers', ()))
    if logging.lastResort is not None:
        # What prints a warning when logging was never configured.
        handlers.add(logging.lastResort)
    for handler in handlers:
        handler.addFilter(once)
    try:
        yield once
    finally:
        for handler in handlers:
            handler.removeFilter(once)


@contextmanager
def _config_built_once():
    """Build the merged system config at most once per pass.

    Outside a request there is nowhere to memoise it, so every translated
    string (Django's system checks evaluate hundreds) rebuilt it: one database
    and one cache round-trip each. With either one down that multiplied every
    timeout by a few hundred.
    """
    from .utils import config as config_module

    original = config_module._build_system_config
    memo = {}

    def build_once():
        if 'config' not in memo:
            memo['config'] = original()
        return memo['config']

    config_module._build_system_config = build_once
    try:
        yield memo
    finally:
        config_module._build_system_config = original


class Session:
    def __init__(self, ctx, runner, config_memo, stack):
        self.ctx = ctx
        self.runner = runner
        self._config_memo = config_memo
        self._stack = stack

    def start(self):
        """Probe the database and cache before anything else touches them."""
        self.ctx.db_available
        if not self.ctx.cache_available:
            from django.test.utils import override_settings

            caches_setting = copy.deepcopy(settings.CACHES)
            caches_setting['default'] = {'BACKEND': DUMMY_CACHE}
            self._stack.enter_context(override_settings(CACHES=caches_setting))

    def fresh_pass(self):
        """Forget per-pass state, so a pass after ``--apply`` sees the fixed deployment."""
        self._config_memo.clear()


@contextmanager
def session():
    """The bounds and quieting every doctor run happens inside.

    The command opens one around Django's own system checks as well as the
    report, because those checks are where most config reads happen.
    """
    runner = _Runner()
    previous = getattr(_runner, 'active', None)
    _runner.active = runner
    try:
        with ExitStack() as stack:
            stack.enter_context(_logged_once())
            stack.enter_context(_short_network_timeouts())
            memo = stack.enter_context(_config_built_once())
            run = Session(Context(), runner, memo, stack)
            run.start()
            yield run
    finally:
        _runner.active = previous


HUNG_REMEDY = (
    'Something this check waits on is not answering: a paused or overloaded database, cache '
    'or network peer. Check the services are running and not paused (docker compose ps), '
    'then run the doctor again.'
)


def run_checks(only_groups=None, run=None, skip_ids=None):
    """Execute every registered check and return the report dict."""
    if run is None:
        with session() as run:
            return run_checks(only_groups, run, skip_ids)

    ctx = run.ctx
    deadline = time.monotonic() + RUN_TIMEOUT
    results = []
    for check_id, group, title, func in _REGISTRY:
        if only_groups and group not in only_groups:
            continue
        if skip_ids and check_id in skip_ids:
            continue
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            finding = skip(f'Skipped: the doctor stopped starting checks after its {RUN_TIMEOUT} s limit.')
        else:
            outcome = run.runner.run(lambda func=func: func(ctx), min(CHECK_TIMEOUT, remaining))
            if outcome.timed_out:
                finding = fail(f'No answer within {outcome.elapsed:.1f} s; the check was abandoned so '
                               'the rest of the report could run.', HUNG_REMEDY)
            elif outcome.error is not None:
                finding = fail(f'Check raised {_describe(outcome.error)}.')
            else:
                finding = outcome.value
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
