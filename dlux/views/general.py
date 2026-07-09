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
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.module_loading import import_string
from django.utils.text import slugify

from dlux import __version__
from dlux.system.constants import DEFAULT_HOME_URL
from dlux.notifications import notify
from dlux.translations import get_current_language_code, get_strings
from dlux.utils import (
    apply_system_settings_import,
    export_system_settings_payload,
    get_email_service_status,
    get_system_config,
    send_dlux_mail,
    is_global_staff,
    load_system_settings_config_json,
    normalize_language_catalog,
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


# Worker pings hit the broker and block the request for up to a second, so the
# result is memoized for a short window: the System Info panel stays light no
# matter how often admins reload it, while still reflecting worker state quickly.
CELERY_WORKER_PROBE_CACHE_KEY = 'dlux:health:celery-workers'
CELERY_WORKER_PROBE_TTL = int(getattr(settings, 'DLUX_CELERY_HEALTH_TTL', 30) or 0)


def _probe_celery_workers(app):
    """Return ``(ok, worker_count, error)`` from a live worker ping, cached briefly.

    ``ok`` is False only when the ping itself raised (broker unreachable); a
    reachable broker with zero live workers returns ``(True, 0, '')``.
    """
    cache_backend = caches['default'] if CELERY_WORKER_PROBE_TTL > 0 else None
    if cache_backend is not None:
        try:
            cached = cache_backend.get(CELERY_WORKER_PROBE_CACHE_KEY)
        except Exception:
            cached = None
        if cached is not None:
            return tuple(cached)

    try:
        replies = app.control.ping(timeout=1.0)
        result = (True, len(replies or []), '')
    except Exception as exc:
        result = (False, 0, str(exc))

    if cache_backend is not None:
        try:
            cache_backend.set(CELERY_WORKER_PROBE_CACHE_KEY, list(result), timeout=CELERY_WORKER_PROBE_TTL)
        except Exception:
            pass

    return result


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
    detail = f'Celery {version}'.strip() or 'Celery'

    app = _get_celery_app()
    if app is None:
        return _service_status(
            'configured',
            detail=detail,
            note='Celery settings were detected, but the Celery app could not be loaded to check worker health.',
            note_key='service_celery_app_unavailable',
        )

    ok, worker_count, error = _probe_celery_workers(app)
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
        composer_version = os.getenv('COMPOSER_VERSION', '').strip()

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
    context.update(diagnostic_context)
    return render(request, 'dlux/includes/options.html', context)


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
        target_url = request.build_absolute_uri(request.GET.get('target') or get_system_config().get('home_url') or DEFAULT_HOME_URL)
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
            imported_settings = load_system_settings_config_json()
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
            if imported_settings:
                apply_system_settings_import(instance, imported_settings, mark_configured=True)
                notify.success(
                    strings.get('system_setup_config_auto_loaded', 'System setup loaded from config.json.'),
                    request=request,
                    action='system_setup_import_loaded',
                    category='system',
                )
                return redirect(get_system_config().get('home_url', DEFAULT_HOME_URL))

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
        return render(request, 'dlux/includes/system_setup_language.html', context)

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
        'hide_sidebar_toggle': True,
    }
    return render(request, 'dlux/includes/system_setup.html', context)


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

    subject = strings.get('email_test_subject', 'DjangoLux test email')
    body = strings.get('email_test_body', 'This is a test email confirming your DjangoLux email configuration works.')
    try:
        sent = send_dlux_mail(subject, body, [recipient], fail_silently=False, alert_on_failure=False)
    except Exception as exc:  # noqa: BLE001 — surface any backend/SMTP error to the operator
        logger.warning("Dlux test email to %s failed: %s", recipient, exc)
        return JsonResponse(
            {'ok': False, 'message': strings.get('email_test_failed', 'Sending failed. Check the SMTP host, credentials, and from address.')},
            status=502,
        )

    if not sent:
        return JsonResponse(
            {'ok': False, 'message': strings.get('email_test_failed', 'Sending failed. Check the SMTP host, credentials, and from address.')},
            status=502,
        )
    return JsonResponse({'ok': True, 'message': strings.get('email_test_sent', 'Test email sent. Check the recipient inbox.')})


@login_required
def global_search_view(request):
    """JSON endpoint for the titlebar global search. Returns grouped,
    permission-filtered results for the given ``q``. Respects the titlebar
    ``global_search_mode`` (disabled → no results) and only searches data when
    both the ``global_search_include_data`` setting is on and the client asks
    for it (``?data=1``)."""
    from dlux.search import run_search

    config = get_system_config()
    titlebar = config.get('titlebar_config') or config.get('titlebar') or {}
    if titlebar.get('global_search_mode', 'icon') == 'disabled':
        return JsonResponse({'groups': [], 'disabled': True})

    query = (request.GET.get('q') or '').strip()
    include_data = bool(titlebar.get('global_search_include_data', False)) and \
        request.GET.get('data') in ('1', 'true', 'yes')
    # Resolve the actual display language the way the rest of Dlux does (session
    # preview / user preference / session / config) — NOT request.LANGUAGE_CODE,
    # which Dlux does not populate; otherwise results are always English and an
    # Arabic query never matches.
    from dlux.translations import get_current_language_code
    lang_code = get_current_language_code(request)

    groups = run_search(request.user, query, include_data=include_data, lang_code=lang_code)
    return JsonResponse({'groups': groups, 'query': query, 'include_data': include_data})
