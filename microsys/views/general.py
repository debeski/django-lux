# Fundemental imports
import os
import platform
import sys
import json
import logging
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import django
from django.apps import apps
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.cache import caches
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.module_loading import import_string
from django.utils.text import slugify

from microsys import __version__
from microsys.constants import DEFAULT_HOME_URL
from microsys.translations import get_current_language_code, get_strings
from microsys.utils import (
    apply_system_settings_import,
    export_system_settings_payload,
    get_email_service_status,
    get_system_config,
    is_global_staff,
    load_system_settings_config_json,
    normalize_system_names,
)

logger = logging.getLogger(__name__)

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
}


def _system_settings_english_name(system_settings=None):
    """The admin-configured English system name, only when one was actually set."""
    try:
        if system_settings is None:
            SystemSettings = apps.get_model('microsys', 'SystemSettings')
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
    return f"microsys-{_resolve_project_export_slug(system_settings)}-{today}.json"

SERVICE_STATE_LABEL_KEYS = {
    'online': 'status_online',
    'degraded': 'status_degraded',
    'configured': 'status_configured',
    'offline': 'status_offline',
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


def _get_cache_service():
    default_cache_config = (getattr(settings, 'CACHES', {}) or {}).get('default', {})
    backend_path = default_cache_config.get('BACKEND', '')
    if backend_path.endswith('.DummyCache'):
        return None

    label = _cache_backend_label(backend_path)
    cache_backend = caches['default']
    cache_key = f'microsys:health:{uuid.uuid4().hex}'

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

    return _service_status('online', detail=label)


def _get_drf_service():
    if not rest_framework:
        return None
    if not (apps.is_installed('rest_framework') or hasattr(settings, 'REST_FRAMEWORK')):
        return None
    return {
        'version': getattr(rest_framework, 'VERSION', 'N/A'),
    }


def _resolve_api_status_url():
    if getattr(settings, 'MICROSYS_API_STATUS_URL', ''):
        return settings.MICROSYS_API_STATUS_URL
    if getattr(settings, 'MICROSYS_API_URL', ''):
        return settings.MICROSYS_API_URL

    microsys_config = getattr(settings, 'MICROSYS_CONFIG', {})
    if isinstance(microsys_config, dict):
        return microsys_config.get('api_status_url') or microsys_config.get('api_url') or ''

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


def _get_celery_service():
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
    detail = f'Celery {version}'.strip()
    return _service_status(
        'configured',
        detail=detail or 'Celery',
        note='Celery settings were detected. Worker health is not auto-checked here.',
        note_key='service_celery_configured',
    )


def _get_system_backup_summary():
    try:
        SystemBackup = apps.get_model('microsys', 'SystemBackup')
        SystemRestore = apps.get_model('microsys', 'SystemRestore')
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
        show_email_service = bool(system_config.get('public_registration_enabled') or system_config.get('email_2fa'))
        db_service = _localize_service_status(_get_database_service(), strings)
        cache_service = _localize_service_status(_get_cache_service(), strings)
        api_service = _localize_service_status(_get_api_service(), strings)
        celery_service = _localize_service_status(_get_celery_service(), strings)
        email_service = None
        if show_email_service:
            email_status = get_email_service_status()
            email_service = _service_status(
                'online' if email_status.get('available') else 'offline',
                detail=email_status.get('backend', ''),
                note=email_status.get('reason', ''),
            )
            email_service = _localize_service_status(email_service, strings)
        drf_service = _get_drf_service()
        os_info = f"{platform.system()} {platform.release()}"
        python_version = sys.version.split()[0]
        django_version = django.get_version()
        decrypter_version = os.getenv('DECRYPTER_VERSION', '').strip()

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
    }
    if request.user.is_superuser:
        context['system_backup_summary'] = _get_system_backup_summary()
    context.update(diagnostic_context)
    return render(request, 'microsys/includes/options.html', context)


@login_required
def system_setup_view(request):
    """Dedicated first-launch setup page for superusers."""
    if not request.user.is_superuser:
        raise PermissionDenied

    SystemSettings = apps.get_model('microsys', 'SystemSettings')
    instance = SystemSettings.load()
    if getattr(instance, 'is_configured', False):
        return redirect('options_view')

    SystemSettingsForm = import_string('microsys.forms.SystemSettingsForm')

    if request.method != 'POST':
        strings = get_strings()
        try:
            imported_settings = load_system_settings_config_json()
        except ValueError as exc:
            logger.warning("Ignoring invalid first-launch config.json: %s", exc)
            messages.warning(
                request,
                strings.get(
                    'system_setup_config_auto_invalid',
                    'config.json could not be loaded; continue with manual setup.',
                ),
                fail_silently=True,
            )
        else:
            if imported_settings:
                apply_system_settings_import(instance, imported_settings, mark_configured=True)
                messages.success(
                    request,
                    strings.get('system_setup_config_auto_loaded', 'System setup loaded from config.json.'),
                    fail_silently=True,
                )
                return redirect(get_system_config().get('home_url', DEFAULT_HOME_URL))

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
            return redirect(get_system_config().get('home_url', DEFAULT_HOME_URL))
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
    }
    return render(request, 'microsys/includes/system_setup.html', context)


@login_required
def export_system_settings_view(request):
    """Download the DB-backed Microsys setup settings as a portable JSON file."""
    if not request.user.is_superuser:
        raise PermissionDenied

    SystemSettings = apps.get_model('microsys', 'SystemSettings')
    instance = SystemSettings.load()
    payload = export_system_settings_payload(instance)
    content = json.dumps(payload, ensure_ascii=False, indent=2)
    response = HttpResponse(content, content_type='application/json; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{_system_settings_export_filename(instance)}"'
    return response
