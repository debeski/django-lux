"""System options views.

Serves `sys/options/` (`options_view`) and the system administration actions
that hang off it: the live service probes (database, cache, DRF/API, Celery,
email), the System Settings dynamic modal, first-run setup, settings export,
email configuration and test sends, and the two destructive admin actions. Was
named `general.py` until 1.8.0, which undersold it — nothing here is general,
it is one domain, and the route has always been `sys/options/`.
"""
# Fundemental imports
import os
import platform
import sys
import json
import importlib
import logging
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import django
from django.apps import apps
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.cache import caches
from django.core.validators import validate_email
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import connection, transaction
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST, require_http_methods
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.module_loading import import_string
from django.utils.text import slugify

from dlux import __version__
from dlux.guards import require_current_password
from dlux.system.constants import DEFAULT_HOME_URL
from dlux.notifications import notify
from dlux.translations import get_current_language_code, get_strings
from dlux.utils import (
    SYSTEM_SETTINGS_CONFIG_BOOTSTRAP_APPLIED,
    SYSTEM_SETTINGS_CONFIG_BOOTSTRAP_CONFIGURED,
    bootstrap_system_settings_config_json,
    export_system_settings_payload,
    get_email_service_status,
    get_system_config,
    send_dlux_mail,
    is_global_staff,
    normalize_language_catalog,
    normalize_homepage_config,
    normalize_system_names,
)

logger = logging.getLogger(__name__)




@login_required
@require_POST
def ribbon_tabs_preview_view(request):
    """The tabs a strip would draw, for a strip that has not been saved yet.

    The builder cannot work this out itself. Tabs from a choice field are in the
    catalog already, but a strip over a relation is one tab per *row* — the
    reader's own scoped rows at that — and only the server can enumerate those.
    Without this a strip drawn in Settings rendered as an empty preview: nothing
    to reorder, rename, hide, or even look at, until it had been saved and the
    page reopened.

    Draws through `build_ribbon_tabs`, the same call a list page makes, so the
    preview cannot drift from what the page will actually show.
    """
    if not (request.user.is_superuser or is_global_staff(request.user)):
        raise PermissionDenied

    from ..ribbon.tabs import build_ribbon_tabs

    try:
        payload = json.loads(request.body or '{}')
    except ValueError:
        return JsonResponse({'error': 'invalid payload'}, status=400)

    model_key = str(payload.get('model') or '')
    sources = payload.get('sources')
    if not model_key or not isinstance(sources, list):
        return JsonResponse({'error': 'model and sources are required'}, status=400)

    # Only models the builder itself offers, so this cannot be used to enumerate
    # rows of a table that has nothing to do with the ribbon.
    from ..ribbon.catalog import ribbon_view_models

    entry = ribbon_view_models().get(model_key)
    if entry is None:
        return JsonResponse({'error': 'unknown model'}, status=404)

    try:
        tabs = build_ribbon_tabs(
            {'param': str(payload.get('param') or 'tab'), 'sources': sources},
            model=entry[0], request=request,
        )
    except Exception as exc:
        # A half-built strip is normal here — the operator is still choosing.
        return JsonResponse({'error': str(exc)}, status=400)

    return JsonResponse({'tabs': [
        {'key': tab.key, 'label': tab.label, 'icon': tab.icon or ''} for tab in tabs
    ]})


def setup_step_cards(strings):
    """The wizard's steps with their strings resolved, in presentation order.

    Both the Options tiles and the setup nav render from this, so neither can
    drift from the other or from `SETUP_STEPS` — the drift this replaces had the
    nav opening the wrong panel for every step past the thirteenth.
    """
    from ..system.constants import SETUP_STEPS

    return [
        {
            'index': index,
            'number': index + 1,
            'slug': slug,
            'icon': icon,
            'label': strings.get(f'system_settings_{slug}', slug.replace('_', ' ').title()),
            'description': strings.get(f'system_settings_{slug}_desc', ''),
        }
        for index, (slug, icon, _keywords) in enumerate(SETUP_STEPS)
    ]

def _configured_home_url():
    config = get_system_config()
    return normalize_homepage_config(config.get('homepage_config') or config)['default_url']

try:
    import psutil
except ImportError:
    psutil = None

try:
    import rest_framework
except ImportError:
    rest_framework = None

try:
    import celery
except ImportError:
    celery = None


SERVICE_BADGE_CLASSES = {
    'online': 'bg-success',
    'degraded': 'bg-warning text-dark',
    'configured': 'bg-warning text-dark',
    'offline': 'bg-danger',
    'unknown': 'bg-secondary',
}


def _system_settings_english_name(system_settings=None):
    """The admin-configured English system name, only when one was actually set."""
    try:
        if system_settings is None:
            SystemSettings = apps.get_model('dlux', 'SystemSettings')
            system_settings = SystemSettings.load()
        names = normalize_system_names(getattr(system_settings, 'system_names', None))
        return str(names.get('en') or '').strip()
    except Exception:
        return ''


# Generic container / work-dir names (e.g. Docker `WORKDIR /app`) that don't identify a
# project, so the BASE_DIR slug is skipped for these and the configured name takes over.
_GENERIC_PROJECT_DIR_SLUGS = frozenset({
    'app', 'apps', 'src', 'source', 'code', 'project', 'projects',
    'web', 'www', 'site', 'sites', 'backend', 'server', 'srv', 'service',
    'usr', 'opt', 'home', 'workspace', 'root', 'tmp',
})


def _resolve_project_export_slug(system_settings=None):
    """Resolve a stable, human-readable slug for the settings export filename.

    Priority: project directory name (BASE_DIR, when not a generic work-dir name) → the
    configured English system name → the literal ``project``. The first one that produces
    a non-empty slug wins.
    """
    candidates = []

    base_dir = getattr(settings, 'BASE_DIR', None)
    if base_dir:
        try:
            base_name = Path(base_dir).resolve().name
        except (OSError, RuntimeError, TypeError, ValueError):
            base_name = str(base_dir).strip()
        base_slug = slugify(base_name or '').strip('-_')
        if base_slug and base_slug not in _GENERIC_PROJECT_DIR_SLUGS:
            candidates.append(base_slug)

    candidates.append(_system_settings_english_name(system_settings))

    for candidate in candidates:
        slug = slugify(candidate or '').strip('-_')
        if slug:
            return slug
    return 'project'


def _system_settings_export_filename(system_settings=None):
    today = timezone.localdate().isoformat()
    return f"dlux-{_resolve_project_export_slug(system_settings)}-{today}.json"

SERVICE_STATE_LABEL_KEYS = {
    'online': 'status_online',
    'degraded': 'status_degraded',
    'configured': 'status_configured',
    'offline': 'status_offline',
    'unknown': 'status_unknown',
}


def _service_status(state, detail='', note='', url='', note_key='', note_context=None):
    return {
        'state': state,
        'detail': detail,
        'note': note,
        'note_key': note_key,
        'note_context': note_context or {},
        'url': url,
        'badge_class': SERVICE_BADGE_CLASSES.get(state, 'bg-secondary'),
    }


def _localize_service_status(service, strings):
    if not service:
        return None
    service['label'] = strings.get(
        SERVICE_STATE_LABEL_KEYS.get(service['state'], ''),
        service['state'].replace('_', ' ').title(),
    )
    if service.get('note_key'):
        template = strings.get(service['note_key'], service.get('note', ''))
        try:
            service['note'] = template.format(**service.get('note_context', {}))
        except Exception:
            service['note'] = template
    return service


def _database_label():
    vendor = getattr(connection, 'vendor', '') or ''
    label_map = {
        'postgresql': 'PostgreSQL',
        'sqlite': 'SQLite',
        'mysql': 'MySQL',
        'oracle': 'Oracle',
    }
    if vendor in label_map:
        return label_map[vendor]
    engine = connection.settings_dict.get('ENGINE', '')
    if engine:
        return engine.rsplit('.', 1)[-1].replace('_', ' ').title()
    return 'Database'


def _fetch_database_version(cursor):
    vendor = getattr(connection, 'vendor', '')
    if vendor == 'postgresql':
        cursor.execute('SHOW server_version')
    elif vendor == 'sqlite':
        cursor.execute('SELECT sqlite_version()')
    elif vendor == 'mysql':
        cursor.execute('SELECT VERSION()')
    else:
        return ''

    row = cursor.fetchone()
    version = str(row[0]).strip() if row and row[0] else ''

    if vendor == 'postgresql':
        return version.partition(' ')[0]

    return version


def _get_database_service():
    label = _database_label()
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
            try:
                version = _fetch_database_version(cursor)
            except Exception as exc:
                return _service_status(
                    'degraded',
                    detail=label,
                    note=f'Connected, but version lookup failed: {exc}',
                    note_key='service_db_version_lookup_failed',
                    note_context={'error': str(exc)},
                )
    except Exception as exc:
        return _service_status(
            'offline',
            detail=label,
            note=f'Error: {exc}',
            note_key='service_error_detail',
            note_context={'error': str(exc)},
        )

    detail = f'{label} {version}'.strip() if version else label
    return _service_status('online', detail=detail)


def _cache_backend_label(backend_path):
    label_map = {
        'RedisCache': 'Redis',
        'LocMemCache': 'Local Memory Cache',
        'FileBasedCache': 'File Cache',
        'DatabaseCache': 'Database Cache',
        'PyLibMCCache': 'Memcached',
        'PyMemcacheCache': 'Memcached',
        'DummyCache': 'Dummy Cache',
    }
    backend_name = (backend_path or '').rsplit('.', 1)[-1]
    if backend_name in label_map:
        return label_map[backend_name]
    return backend_name.replace('_', ' ') or 'Cache'


def _fetch_redis_version(cache_backend):
    """Best-effort Redis server version lookup across django-redis and Django's builtin backend."""
    client = None
    getter = getattr(getattr(cache_backend, 'client', None), 'get_client', None)
    if callable(getter):
        try:
            client = getter(write=False)
        except TypeError:
            client = getter()
    if client is None:
        getter = getattr(getattr(cache_backend, '_cache', None), 'get_client', None)
        if callable(getter):
            try:
                client = getter(None)
            except TypeError:
                client = getter()
    if client is None:
        return ''

    info = client.info('server')
    return str(info.get('redis_version', '')).strip()


def _get_cache_service():
    default_cache_config = (getattr(settings, 'CACHES', {}) or {}).get('default', {})
    backend_path = default_cache_config.get('BACKEND', '')
    if backend_path.endswith('.DummyCache'):
        return None

    label = _cache_backend_label(backend_path)
    cache_backend = caches['default']
    cache_key = f'dlux:health:{uuid.uuid4().hex}'

    try:
        cache_backend.set(cache_key, 'ok', timeout=15)
        value = cache_backend.get(cache_key)
        cache_backend.delete(cache_key)
    except Exception as exc:
        return _service_status(
            'offline',
            detail=label,
            note=f'Error: {exc}',
            note_key='service_error_detail',
            note_context={'error': str(exc)},
        )

    if value != 'ok':
        return _service_status(
            'degraded',
            detail=label,
            note='Cache responded, but the health probe returned an unexpected value.',
            note_key='service_cache_probe_unexpected',
        )

    detail = label
    if label == 'Redis':
        try:
            version = _fetch_redis_version(cache_backend)
        except Exception:
            version = ''
        if version:
            detail = f'{label} {version}'.strip()

    return _service_status('online', detail=detail)


def _get_drf_service():
    if not rest_framework:
        return None
    if not (apps.is_installed('rest_framework') or hasattr(settings, 'REST_FRAMEWORK')):
        return None
    return {
        'version': getattr(rest_framework, 'VERSION', 'N/A'),
    }


def _resolve_api_status_url():
    if getattr(settings, 'DLUX_API_STATUS_URL', ''):
        return settings.DLUX_API_STATUS_URL
    if getattr(settings, 'DLUX_API_URL', ''):
        return settings.DLUX_API_URL

    dlux_config = getattr(settings, 'DLUX_CONFIG', {})
    if isinstance(dlux_config, dict):
        return dlux_config.get('api_status_url') or dlux_config.get('api_url') or ''

    return ''


def _get_api_service():
    api_url = _resolve_api_status_url()
    if not api_url:
        return None

    request_obj = urllib.request.Request(api_url)
    api_key = getattr(settings, 'X_API_KEY', '')
    secret_key = getattr(settings, 'X_SECRET_KEY', '')

    if api_key:
        request_obj.add_header('X-API-KEY', api_key)
    if secret_key:
        request_obj.add_header('X-SECRET-KEY', secret_key)

    try:
        with urllib.request.urlopen(request_obj, timeout=3) as response:
            if 200 <= response.status < 400:
                return _service_status('online', note='', url=api_url)
            return _service_status(
                'degraded',
                note=f'Endpoint responded with HTTP {response.status}.',
                note_key='service_api_http_status',
                note_context={'status': response.status},
                url=api_url,
            )
    except urllib.error.HTTPError as exc:
        state = 'degraded' if exc.code < 500 else 'offline'
        return _service_status(
            state,
            note=f'Endpoint responded with HTTP {exc.code}.',
            note_key='service_api_http_status',
            note_context={'status': exc.code},
            url=api_url,
        )
    except Exception as exc:
        return _service_status(
            'offline',
            note=f'Error: {exc}',
            note_key='service_error_detail',
            note_context={'error': str(exc)},
            url=api_url,
        )


def _get_celery_app():
    """Resolve the project's Celery app so worker health can be inspected in-process."""
    settings_module = str(os.environ.get('DJANGO_SETTINGS_MODULE') or '')
    project = settings_module.split('.', 1)[0]
    if project:
        try:
            return importlib.import_module(f'{project}.celery').app
        except Exception:
            pass
    try:
        from celery import current_app
        return current_app
    except Exception:
        return None


# A worker ping hits the broker and blocks the request for up to a second, so it
# is NEVER run on a normal Options page load. The check is on-demand only
# (triggered by the recheck button → `celery_health_check_view`); its result is
# persisted so the panel keeps showing the last outcome until the next manual
# check, instead of re-pinging on every visit.
CELERY_HEALTH_RESULT_KEY = 'dlux:health:celery-workers:last-result'


def _probe_celery_workers(app):
    """Return ``(ok, worker_count, error)`` from a single live worker ping.

    ``ok`` is False only when the ping itself raised (broker unreachable); a
    reachable broker with zero live workers returns ``(True, 0, '')``. No
    caching — the caller decides when to probe (on demand only).
    """
    try:
        replies = app.control.ping(timeout=1.0)
        return (True, len(replies or []), '')
    except Exception as exc:
        return (False, 0, str(exc))


def _load_celery_probe_result():
    """Return the last persisted on-demand probe result, or None if never run."""
    try:
        cached = caches['default'].get(CELERY_HEALTH_RESULT_KEY)
    except Exception:
        return None
    if not cached:
        return None
    try:
        ok, worker_count, error = cached
        return (bool(ok), int(worker_count), str(error or ''))
    except Exception:
        return None


def _store_celery_probe_result(result):
    """Persist the on-demand probe result until the next manual check (no TTL)."""
    try:
        caches['default'].set(CELERY_HEALTH_RESULT_KEY, list(result), timeout=None)
    except Exception:
        pass


def _celery_status_from_result(detail, result):
    """Build a service-status dict from a ``(ok, worker_count, error)`` probe."""
    ok, worker_count, error = result
    if not ok:
        return _service_status(
            'offline',
            detail=detail,
            note=f'Error: {error}',
            note_key='service_error_detail',
            note_context={'error': error},
        )
    if worker_count == 0:
        return _service_status(
            'offline',
            detail=detail,
            note='Celery is configured, but no workers responded to the health ping.',
            note_key='service_celery_no_workers',
        )
    return _service_status(
        'online',
        detail=detail,
        note='{count} worker(s) responded to the health ping.',
        note_key='service_celery_workers_online',
        note_context={'count': worker_count},
    )


def _get_email_service():
    """Resolve the Email service status for the admin panel.

    Always resolvable, and deliberately not gated on any feature toggle. It used
    to render only while public registration or email 2FA was on — the two
    settings that are themselves locked until email is verified, so the indicator
    was hidden exactly when an operator needed it to set email up.

    Four distinct states, because "not working" is not one condition:
      offline  — enabled and configured, but the config cannot send
      unknown  — configured but never proven by a test send
      degraded — turned off by the operator
      online   — enabled, configured and verified
    """
    from ..system.normalizers import normalize_email_config
    from ..utils import email_features_unlocked

    status = get_email_service_status()
    SystemSettings = apps.get_model('dlux', 'SystemSettings')
    try:
        config = normalize_email_config(getattr(SystemSettings.load(), 'email_config', {}) or {})
    except Exception:
        config = {}

    transport = config.get('transport') or status.get('transport') or 'direct'
    detail = 'smtp-relay' if transport == 'relay' else (status.get('backend', '') or '')

    if not config.get('enabled'):
        state, note_key = 'degraded', 'service_email_disabled'
    elif not status.get('available'):
        state, note_key = 'offline', 'service_email_unavailable'
    elif not (config.get('verified') or email_features_unlocked()):
        state, note_key = 'unknown', 'service_email_unverified'
    else:
        state, note_key = 'online', 'service_email_verified'

    return _service_status(state, detail=detail, note_key=note_key)


def _get_celery_service(probe=False):
    """Resolve the Tasks (Celery) service status.

    The cheap configuration/package/app checks always run, but the broker is
    pinged ONLY when ``probe=True`` (the on-demand recheck endpoint). On a normal
    page load (``probe=False``) the last persisted result is shown, or a neutral
    "not checked yet" state when no check has been run.
    """
    is_configured = any([
        getattr(settings, 'CELERY_BROKER_URL', ''),
        getattr(settings, 'CELERY_RESULT_BACKEND', ''),
        apps.is_installed('django_celery_beat'),
        apps.is_installed('django_celery_results'),
    ])
    if not is_configured:
        return None

    if not celery:
        return _service_status(
            'offline',
            detail='Celery',
            note='Celery-related settings were detected, but the celery package is not installed.',
            note_key='service_celery_missing_package',
        )

    version = getattr(celery, '__version__', '')
    detail = f'Celery {version}'.strip() or 'Celery'

    app = _get_celery_app()
    if app is None:
        return _service_status(
            'configured',
            detail=detail,
            note='Celery settings were detected, but the Celery app could not be loaded to check worker health.',
            note_key='service_celery_app_unavailable',
        )

    if probe:
        result = _probe_celery_workers(app)
        _store_celery_probe_result(result)
        return _celery_status_from_result(detail, result)

    stored = _load_celery_probe_result()
    if stored is None:
        # Never checked (or the store was cleared) — neutral, not-green state.
        return _service_status(
            'unknown',
            detail=detail,
            note='Celery settings were detected. Worker health is not auto-checked here.',
            note_key='service_celery_configured',
        )
    return _celery_status_from_result(detail, stored)


def _get_system_backup_summary():
    try:
        SystemBackup = apps.get_model('dlux', 'SystemBackup')
        SystemRestore = apps.get_model('dlux', 'SystemRestore')
    except LookupError:
        return {
            'backup_count': 0,
            'completed_count': 0,
            'protected_count': 0,
            'latest_backup': None,
            'latest_completed_backup': None,
            'latest_restore': None,
        }

    backups = SystemBackup.objects.all()
    completed = backups.filter(status=SystemBackup.STATUS_COMPLETED)
    return {
        'backup_count': backups.count(),
        'completed_count': completed.count(),
        'protected_count': completed.filter(passphrase_required=True).count(),
        'latest_backup': backups.order_by('-created_at').first(),
        'latest_completed_backup': completed.order_by('-completed_at', '-created_at').first(),
        'latest_restore': SystemRestore.objects.order_by('-created_at').first(),
    }




# Dashboard View removed as per UX enhancements
# @login_required
# def dashboard(request):
#     ...

# System Options — Displays accessibility settings and live runtime health
@login_required
def options_view(request):
    """
    View for system options, accessibility settings, and live system info.
    """
    strings = get_strings(get_current_language_code(request))
    show_system_diagnostics = bool(request.user.is_superuser or is_global_staff(request.user))

    diagnostic_context = {}

    if show_system_diagnostics:
        system_config = get_system_config()
        db_service = _localize_service_status(_get_database_service(), strings)
        cache_service = _localize_service_status(_get_cache_service(), strings)
        api_service = _localize_service_status(_get_api_service(), strings)
        celery_service = _localize_service_status(_get_celery_service(), strings)
        email_service = _localize_service_status(_get_email_service(), strings)
        drf_service = _get_drf_service()
        os_info = f"{platform.system()} {platform.release()}"
        python_version = sys.version.split()[0]
        django_version = django.get_version()
        decrypter_version = os.getenv('DECRYPTER_VERSION', '').strip()
        # Two distinct Composer versions: the deployer image ./start.sh runs
        # (COMPOSER_VERSION env), and the resident composer-agent binary that
        # reports its own composer_version into the agent bridge. The two images
        # are pulled independently, so they can legitimately differ.
        composer_version = os.getenv('COMPOSER_VERSION', '').strip()
        composer_agent_version = ''
        try:
            from ..updater import control_link as _control_link
            from ..updater.service import runtime_store as _runtime_store
            _agent_status = _control_link.read_agent_status(_runtime_store()) or {}
            composer_agent_version = (
                _agent_status.get('composer_version')
                or _agent_status.get('agent_version') or ''
            ).strip()
        except Exception:
            composer_agent_version = ''

        try:
            if psutil is None:
                raise RuntimeError("psutil is not installed")
            mem = psutil.virtual_memory()
            ram_total_gb = mem.total / (1024 ** 3)
            ram_used_gb = mem.used / (1024 ** 3)
            ram_percent = mem.percent

            disk = psutil.disk_usage('/')
            disk_total_gb = disk.total / (1024 ** 3)
            disk_used_gb = disk.used / (1024 ** 3)
            disk_percent = disk.percent
        except Exception:
            ram_total_gb = ram_used_gb = ram_percent = 0
            disk_total_gb = disk_used_gb = disk_percent = 0

        diagnostic_context = {
            'os_info': os_info,
            'python_version': python_version,
            'django_version': django_version,
            'decrypter_version': decrypter_version,
            'composer_version': composer_version,
            'composer_agent_version': composer_agent_version,
            'drf_service': drf_service,
            'api_service': api_service,
            'db_service': db_service,
            'cache_service': cache_service,
            'celery_service': celery_service,
            'email_service': email_service,
            'version': __version__,
            'ram_total': f"{ram_total_gb:.1f}",
            'ram_used': f"{ram_used_gb:.1f}",
            'ram_percent': ram_percent,
            'disk_total': f"{disk_total_gb:.1f}",
            'disk_used': f"{disk_used_gb:.1f}",
            'disk_percent': disk_percent,
        }

    server_time = timezone.localtime(timezone.now())
    context = {
        'show_system_diagnostics': show_system_diagnostics,
        'current_time': server_time,
        'server_time_backend_display': server_time.strftime('%Y-%m-%d %H:%M:%S'),
        'setup_steps': setup_step_cards(get_strings(get_current_language_code(request))),
    }
    # Permission-filtered landing-page options (when the admin allows per-user landing pages).
    profile_config = get_system_config().get('profile_config') or {}
    if profile_config.get('allow_user_home_url'):
        from dlux.discovery import build_user_home_url_options
        context['user_home_url_options'] = build_user_home_url_options(
            request.user, lang_code=get_current_language_code(request),
        )
    if request.user.is_superuser:
        context['system_backup_summary'] = _get_system_backup_summary()
    if show_system_diagnostics:
        from dlux.updater.service import get_ui_state

        context['dlux_update_state'] = get_ui_state()
        context['can_manage_dlux_updates'] = bool(
            request.user.is_superuser and context['dlux_update_state']['enabled']
        )
    # App-contributed Options cards (registry-driven, permission-filtered and
    # sandbox-rendered — a failing card is dropped, never blanks the page).
    from dlux.options import get_visible_app_settings, render_cards
    context['dlux_option_cards'] = render_cards(request)
    context['dlux_app_settings'] = get_visible_app_settings(request)

    context.update(diagnostic_context)
    return render(request, 'dlux/system/options.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def app_settings_modal_view(request, namespace):
    """Render/save one app-registered project settings form.

    This intentionally stays outside ``SystemSettingsForm``. It is superuser-only
    and writes only the app-owned ``extra_config['app'][namespace]`` value.
    """
    if not request.user.is_superuser:
        raise PermissionDenied

    from dlux.options import (
        AppSystemConfigError,
        build_app_settings_form,
        get_app_settings_form_value,
        get_visible_app_setting,
        write_app_system_config,
    )

    definition = get_visible_app_setting(request, namespace)
    if definition is None:
        raise Http404

    if request.method == 'POST':
        form = build_app_settings_form(definition, request, data=request.POST)
        if form.is_valid():
            try:
                value = get_app_settings_form_value(definition, form)
                stored_value = write_app_system_config(definition['namespace'], value, request=request)
            except AppSystemConfigError as exc:
                form.add_error(None, exc.message)
            else:
                return JsonResponse({
                    'success': True,
                    'namespace': definition['namespace'],
                    'value': stored_value,
                    # App-settings tiles have no records table to reopen; without
                    # this the dynamic-modal JS re-loads the form into the modal on
                    # success (it "hides" then pops back up). refresh_parent tells it
                    # to close and reload the Options page so the saved value shows.
                    'refresh_parent': True,
                })
    else:
        form = build_app_settings_form(definition, request)

    strings = get_strings(get_current_language_code(request))
    html = render_to_string(
        'dlux/system/app_settings_form.html',
        {
            'form': form,
            'app_setting': definition,
            'DLUX_STRINGS': strings,
        },
        request=request,
    )
    return JsonResponse({'html': html})


@login_required
@require_POST
def email_health_check_view(request):
    """On-demand Email posture re-read (superuser / global-staff only).

    Cheap and side-effect free: it re-reads configuration and verification state
    and sends nothing. Proving delivery is the test-send button's job.
    """
    if not (request.user.is_superuser or is_global_staff(request.user)):
        raise PermissionDenied

    strings = get_strings(get_current_language_code(request))
    service = _localize_service_status(_get_email_service(), strings)
    return JsonResponse({
        'state': service['state'],
        'label': service['label'],
        'detail': service['detail'],
        'note': service['note'],
        'badge_class': service['badge_class'],
    })


@login_required
@require_POST
def celery_health_check_view(request):
    """On-demand Celery worker health probe (superuser / global-staff only).

    Pings the broker once, persists the result so the Options panel keeps showing
    it until the next manual check, and returns the localized status for the JS
    to paint the Tasks badge. This is the ONLY place a ping is issued — normal
    Options loads never touch the broker.
    """
    if not (request.user.is_superuser or is_global_staff(request.user)):
        raise PermissionDenied

    strings = get_strings(get_current_language_code(request))
    service = _get_celery_service(probe=True)
    if service is None:
        return JsonResponse({'status': 'not_configured'}, status=404)

    service = _localize_service_status(service, strings)
    return JsonResponse({
        'status': 'ok',
        'service': {
            'state': service['state'],
            'label': service['label'],
            'badge_class': service['badge_class'],
            'detail': service['detail'],
            'note': service['note'],
        },
    })


@login_required
@require_POST
def force_password_change_all_view(request):
    """
    Superuser-only admin-panel command that reuses the existing forced password
    change marker used by the create-user form.
    """
    strings = get_strings(get_current_language_code(request))
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if not request.user.is_superuser:
        message = strings.get('permission_denied', 'Permission denied.')
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': message}, status=403)
        raise PermissionDenied

    if failure_response := require_current_password(request, redirect_name='options_view'):
        return failure_response

    from ..admin_actions.force_password_change import force_password_change_for_all_non_superusers

    updated_count, total_count = force_password_change_for_all_non_superusers()
    message_template = strings.get(
        'force_pass_change_all_success',
        'Password change is required for {total} non-superuser account(s); {count} newly marked.',
    )
    try:
        message = message_template.format(count=updated_count, total=total_count)
    except Exception:
        message = message_template

    try:
        from dlux.utils import log_audit_event
        log_audit_event(
            request,
            'force_password_change_all',
            'PASSWORD_RESET',
            instance=request.user,
            model_name='user',
            details={'updated_count': updated_count, 'total_count': total_count},
        )
    except Exception:
        logger.debug("Failed to write bulk force-password-change audit event.", exc_info=True)

    notify.success(
        message,
        request=request,
        action='force_password_change_all',
        category='security',
        metadata={
            'message_key': 'force_pass_change_all_success',
            'updated_count': updated_count,
            'total_count': total_count,
        },
    )

    return JsonResponse({
        'status': 'success',
        'success': True,
        'message': message,
        'updated_count': updated_count,
        'total_count': total_count,
    })


@login_required
@require_POST
def data_reset_preview_view(request):
    """Superuser-only: current-password-gated listing of the models a data reset
    can clear (row counts, scoped/soft-delete flag, media presence)."""
    strings = get_strings(get_current_language_code(request))
    if not request.user.is_superuser:
        return JsonResponse({'status': 'error', 'message': strings.get('permission_denied', 'Permission denied.')}, status=403)
    if failure := require_current_password(request, redirect_name='options_view'):
        return failure
    from ..admin_actions.data_reset import build_reset_catalog
    return JsonResponse({'status': 'success', 'models': build_reset_catalog(request.user, strings)})


def _permanent_confirmed(request, strings):
    """The typed acknowledgement permanent mode requires on top of the password.

    Either the localized word or the English default is accepted: an operator
    reading an Arabic UI types the Arabic word, and a script or a second-language
    session is not locked out by a translation.
    """
    from ..admin_actions.data_reset import DATA_RESET_CONFIRM_WORD

    typed = str(request.POST.get('confirm_permanent') or '').strip().casefold()
    if not typed:
        return False
    expected = {
        str(strings.get('data_reset_confirm_word') or '').strip().casefold(),
        DATA_RESET_CONFIRM_WORD.casefold(),
    }
    return typed in {word for word in expected if word}


@login_required
@require_POST
def data_reset_execute_view(request):
    """Superuser-only: current-password-gated execution of a data reset on the
    selected models.

    Soft mode (the default) soft-deletes scoped models and hard-deletes the rest.
    Permanent mode hard-deletes everything selected and empties those models'
    recycle bins, so it additionally requires the typed confirmation word — the
    password proves who is asking, this proves they know it cannot be undone.
    """
    strings = get_strings(get_current_language_code(request))
    if not request.user.is_superuser:
        return JsonResponse({'status': 'error', 'message': strings.get('permission_denied', 'Permission denied.')}, status=403)
    if failure := require_current_password(request, redirect_name='options_view'):
        return failure

    from ..admin_actions.data_reset import RESET_MODE_PERMANENT, execute_reset, normalize_mode
    selected = request.POST.getlist('models')
    if not selected:
        return JsonResponse({'status': 'error', 'message': strings.get('data_reset_no_models', 'Select at least one model to reset.')}, status=400)
    delete_media = str(request.POST.get('delete_media') or '').strip().lower() in {'1', 'true', 'yes', 'on'}
    mode = normalize_mode(request.POST.get('mode'))
    if mode == RESET_MODE_PERMANENT and not _permanent_confirmed(request, strings):
        return JsonResponse({'status': 'error', 'message': strings.get(
            'data_reset_confirm_required',
            'Type the confirmation word to permanently delete this data.',
        )}, status=400)

    results = execute_reset(request.user, selected, delete_media=delete_media, mode=mode)
    total_deleted = sum(int(r.get('deleted') or 0) for r in results)
    soft = sum(int(r.get('deleted') or 0) for r in results if r.get('scoped'))
    hard = total_deleted - soft
    blocked = [r for r in results if r.get('status') in ('protected', 'error')]

    message_template = strings.get(
        'data_reset_success',
        'Data reset complete: {total} row(s) cleared ({soft} soft-deleted, {hard} permanently).',
    )
    if mode == RESET_MODE_PERMANENT:
        message_template = strings.get(
            'data_reset_success_permanent',
            'Data reset complete: {total} row(s) permanently deleted.',
        )
    try:
        message = message_template.format(total=total_deleted, soft=soft, hard=hard)
    except Exception:
        message = message_template

    try:
        from dlux.utils import log_audit_event
        log_audit_event(
            request,
            'data_reset',
            'DELETE',
            instance=request.user,
            model_name='user',
            details={'models': selected, 'mode': mode, 'delete_media': delete_media,
                     'total_deleted': total_deleted, 'results': results},
        )
    except Exception:
        logger.debug("Failed to write data-reset audit event.", exc_info=True)

    notify.warning(
        message,
        request=request,
        action='data_reset',
        category='security',
        metadata={'total_deleted': total_deleted, 'soft': soft, 'hard': hard, 'mode': mode},
    )

    return JsonResponse({'status': 'success', 'message': message, 'results': results,
                         'mode': mode, 'total_deleted': total_deleted, 'blocked': bool(blocked)})


def _debug_bool_param(request, name, default=None):
    raw_value = request.GET.get(name)
    if raw_value is None:
        return default
    return str(raw_value).strip().lower() in {'1', 'true', 'yes', 'on'}


@login_required
def debug_notifications_view(request):
    """DEBUG-only internal route for visually testing Dlux notifications."""
    if not settings.DEBUG:
        raise Http404
    if not (request.user.is_superuser or is_global_staff(request.user)):
        raise PermissionDenied

    samples = {
        'success': ('success', 'Dlux notification success test.'),
        'info': ('info', 'Dlux notification info test.'),
        'warning': ('warning', 'Dlux notification warning test.'),
        'error': ('error', 'Dlux notification error test.'),
    }
    requested_level = str(request.GET.get('level') or 'all').strip().lower()
    selected = samples.items() if requested_level == 'all' else [(requested_level, samples.get(requested_level, samples['info']))]
    flash = _debug_bool_param(request, 'flash', None)
    persist = _debug_bool_param(request, 'persist', None)
    email = _debug_bool_param(request, 'email', False)

    try:
        target_url = request.build_absolute_uri(request.GET.get('target') or _configured_home_url())
    except Exception:
        target_url = request.GET.get('target') or DEFAULT_HOME_URL

    for name, (level, text) in selected:
        notify(
            text,
            level=level,
            request=request,
            action=f'debug_notification_{name}',
            category='debug',
            target_url=target_url,
            flash=flash,
            persist=persist,
            email=email,
            to='actor',
            metadata={
                'debug': True,
                'route': 'debug_notifications',
                'nonce': uuid.uuid4().hex,
            },
        )

    next_url = str(request.GET.get('next') or request.META.get('HTTP_REFERER') or '').strip()
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect('options_view')


@login_required
def system_setup_view(request):
    """Dedicated first-launch setup page for superusers."""
    if not request.user.is_superuser:
        raise PermissionDenied

    SystemSettings = apps.get_model('dlux', 'SystemSettings')
    instance = SystemSettings.load()
    if getattr(instance, 'is_configured', False):
        return redirect('options_view')

    SystemSettingsForm = import_string('dlux.forms.SystemSettingsForm')

    if request.method != 'POST':
        strings = get_strings()
        try:
            bootstrap_status, _, _ = bootstrap_system_settings_config_json()
        except ValueError as exc:
            logger.warning("Ignoring invalid first-launch config.json: %s", exc)
            notify.warning(
                strings.get(
                    'system_setup_config_auto_invalid',
                    'config.json could not be loaded; continue with manual setup.',
                ),
                request=request,
                action='system_setup_import_invalid',
                category='system',
            )
        else:
            if bootstrap_status == SYSTEM_SETTINGS_CONFIG_BOOTSTRAP_APPLIED:
                notify.success(
                    strings.get('system_setup_config_auto_loaded', 'System setup loaded from config.json.'),
                    request=request,
                    action='system_setup_import_loaded',
                    category='system',
                )
                return redirect(_configured_home_url())
            if bootstrap_status == SYSTEM_SETTINGS_CONFIG_BOOTSTRAP_CONFIGURED:
                return redirect(_configured_home_url())

    config = get_system_config()
    setup_languages = normalize_language_catalog(config.get('languages', {}))
    selected_setup_language = str(request.session.get('dlux_initial_setup_language') or '').strip().lower()
    if selected_setup_language not in setup_languages:
        selected_setup_language = ''

    if not selected_setup_language:
        if request.method == 'POST' and 'setup_language' in request.POST:
            candidate = str(request.POST.get('setup_language') or '').strip().lower().replace('_', '-')
            if candidate in setup_languages:
                request.session['dlux_initial_setup_language'] = candidate
                request.session['lang'] = candidate
                request.session['django_language'] = candidate
                request.session.pop('dlux_force_language_preview', None)
                return redirect('system_setup')

        context = {
            'page_title': 'System Setup',
            'setup_languages': setup_languages,
            'hide_sidebar_toggle': True,
        }
        return render(request, 'dlux/setup/language.html', context)

    if request.method == 'POST':
        form = SystemSettingsForm(
            request.POST,
            request.FILES,
            instance=instance,
            request=request,
            user=request.user,
            mode='setup',
        )
        if form.is_valid():
            form.save()
            resolved_language = form.cleaned_data.get('default_language') or selected_setup_language
            saved_languages = normalize_language_catalog(form.cleaned_data.get('languages') or setup_languages)
            if resolved_language in saved_languages:
                request.session['lang'] = resolved_language
                request.session['django_language'] = resolved_language
            request.session.pop('dlux_initial_setup_language', None)
            request.session.pop('dlux_force_language_preview', None)
            return redirect(_configured_home_url())
    else:
        form = SystemSettingsForm(
            instance=instance,
            request=request,
            user=request.user,
            mode='setup',
        )

    context = {
        'form': form,
        'page_title': 'System Setup',
        'hide_sidebar_toggle': True,
        'setup_steps': setup_step_cards(get_strings(get_current_language_code(request))),
    }
    return render(request, 'dlux/setup/main.html', context)


@login_required
def export_system_settings_view(request):
    """Download the DB-backed Dlux setup settings as a portable JSON file."""
    if not request.user.is_superuser:
        raise PermissionDenied

    SystemSettings = apps.get_model('dlux', 'SystemSettings')
    instance = SystemSettings.load()
    payload = export_system_settings_payload(instance)
    content = json.dumps(payload, ensure_ascii=False, indent=2)
    response = HttpResponse(content, content_type='application/json; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{_system_settings_export_filename(instance)}"'
    return response


@login_required
@require_POST
def email_config_apply_view(request):
    """Persist just the Email step so a test send can run without leaving it.

    The test button deliberately sends with the *stored* configuration: the SMTP
    relay is a separate container that reads config from the database, so testing
    against unsaved form values would exercise something the relay cannot see.
    Rather than make the test lie, this saves the email group in place — the admin
    edits, applies, and tests in one pass instead of saving the modal, reopening it
    and navigating back to the step.

    Only ``email_config`` is written. The form is bound in single-step mode for the
    Email step, so every other step's values pass through its preservation cleaners
    untouched, and the same packing/normalizing path runs as a full save.
    """
    if not request.user.is_superuser:
        raise PermissionDenied

    strings = get_strings(get_current_language_code(request))
    SystemSettingsForm = import_string('dlux.forms.SystemSettingsForm')
    SystemSettings = apps.get_model('dlux', 'SystemSettings')
    instance = SystemSettings.load()
    form = SystemSettingsForm(data=request.POST, instance=instance, request=request)
    if not form.is_valid() and 'email_config' in form.errors:
        return JsonResponse(
            {'ok': False, 'message': '; '.join(str(e) for e in form.errors['email_config'])},
            status=400,
        )

    config = (form.cleaned_data or {}).get('email_config')
    if not isinstance(config, dict):
        return JsonResponse(
            {'ok': False, 'message': strings.get('email_apply_failed', 'Could not apply the email settings.')},
            status=400,
        )

    instance.email_config = config
    instance.save(update_fields=['email_config'])
    ActivityLog = apps.get_model('dlux', 'ActivityLog')
    ActivityLog.safe_log(user=request.user, action='UPDATE', model_name='Dlux Email Settings')

    status = get_email_service_status()
    return JsonResponse({
        'ok': True,
        'message': strings.get('email_apply_saved', 'Email settings applied. You can send a test now.'),
        'verified': bool(config.get('verified')),
        'password_configured': bool(config.get('password_configured')),
        'service_reason': status.get('reason', ''),
        'available': bool(status.get('available')),
    })


def _record_email_verification(verified):
    """Persist the outcome of a test send onto email_config.

    The test result is what unlocks the mail-dependent settings, so it is stored
    against a fingerprint of the exact connection it was run over; editing any
    connection field later re-arms verification automatically (see
    normalize_email_config). Returns the resulting verified flag.
    """
    from ..system.normalizers import email_config_fingerprint, normalize_email_config

    SystemSettings = apps.get_model('dlux', 'SystemSettings')
    instance = SystemSettings.load()
    config = normalize_email_config(getattr(instance, 'email_config', {}) or {})
    if verified:
        config['verified'] = True
        config['verified_at'] = timezone.now().isoformat()
        config['verified_fingerprint'] = email_config_fingerprint(config)
    else:
        config['verified'] = False
        config['verified_at'] = ''
        config['verified_fingerprint'] = ''
    instance.email_config = config
    instance.save(update_fields=['email_config'])
    return bool(config['verified'])


@require_POST
def email_send_test_view(request):
    """Send a one-off test email using the saved Dlux email configuration."""
    if not request.user.is_superuser:
        raise PermissionDenied

    strings = get_strings(get_current_language_code(request))
    recipient = str(request.POST.get('recipient') or '').strip()
    try:
        validate_email(recipient)
    except ValidationError:
        return JsonResponse(
            {'ok': False, 'message': strings.get('email_test_invalid_recipient', 'Enter a valid recipient email address.')},
            status=400,
        )

    status = get_email_service_status()
    if not status.get('available'):
        return JsonResponse(
            {'ok': False, 'message': strings.get('email_test_not_configured', 'Email delivery is not configured yet. Save a working configuration first.')},
            status=409,
        )

    # A stored secret that this process cannot decrypt is indistinguishable from
    # "no password" once decryption falls back to '' — the send then fails deep in
    # SMTP (or, with relay transport, in a sidecar whose log nobody is watching)
    # with an error that names neither the key nor the password. Say so up front.
    from ..system.normalizers import normalize_email_config
    from ..utils import EMAIL_SECRET_UNDECRYPTABLE, email_secret_state

    SystemSettings = apps.get_model('dlux', 'SystemSettings')
    stored = normalize_email_config(getattr(SystemSettings.load(), 'email_config', {}) or {})
    if stored.get('secret_storage') == 'encrypted_db':
        if email_secret_state(stored.get('encrypted_password')) == EMAIL_SECRET_UNDECRYPTABLE:
            _record_email_verification(False)
            return JsonResponse(
                {
                    'ok': False,
                    'message': strings.get(
                        'email_test_secret_undecryptable',
                        'The stored SMTP password cannot be decrypted with this deployment\'s SECRET_KEY. '
                        'It was saved under a different key (a rotated key, or a container started with a '
                        'different DJANGO_SECRET_KEY). Re-enter the password to store it again.',
                    ),
                },
                status=409,
            )

    subject = strings.get('email_test_subject', 'DjangoLux test email')
    body = strings.get('email_test_body', 'This is a test email confirming your DjangoLux email configuration works.')
    try:
        sent = send_dlux_mail(subject, body, [recipient], fail_silently=False, alert_on_failure=False)
    except Exception as exc:  # noqa: BLE001 — surface any backend/SMTP error to the operator
        logger.warning("Dlux test email to %s failed: %s", recipient, exc)
        _record_email_verification(False)
        return JsonResponse(
            {'ok': False, 'message': strings.get('email_test_failed', 'Sending failed. Check the SMTP host, credentials, and from address.')},
            status=502,
        )

    if not sent:
        _record_email_verification(False)
        return JsonResponse(
            {'ok': False, 'message': strings.get('email_test_failed', 'Sending failed. Check the SMTP host, credentials, and from address.')},
            status=502,
        )
    _record_email_verification(True)
    return JsonResponse({
        'ok': True,
        'verified': True,
        'message': strings.get('email_test_sent', 'Test email sent. Check the recipient inbox.'),
    })
