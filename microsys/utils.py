import base64
import hashlib
import json
import os
import re
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from functools import lru_cache
import inspect
import unicodedata
from django import forms
from django.apps import apps
from django.conf import settings
from django.contrib.messages import constants as messages
from django.db import models as dj_models
from django.db.models import ManyToManyRel, Q
from django.db.models.fields.files import FieldFile
from django.db.models.fields.related import ManyToManyField
from django.forms import modelform_factory
from django.http import JsonResponse
from django.core.mail import EmailMessage, get_connection, send_mail
from django.core.exceptions import FieldDoesNotExist
from django.utils.module_loading import import_string
from .constants import (
    DEFAULT_HOME_URL,
    DEFAULT_SIDEBAR_COLLAPSE_MODE,
    DEFAULT_SIDEBAR_DENSITY,
    DEFAULT_TABLE_DENSITY,
    LEGACY_HOME_URL,
    REGISTRATION_ACTIVATION_AUTO_LOGIN,
    REGISTRATION_ACTIVATION_VALUES,
    SIDEBAR_COLLAPSE_MODE_VALUES,
    SIDEBAR_DENSITY_VALUES,
    TABLE_DENSITY_VALUES,
    TITLEBAR_ALIGN_VALUES,
    TITLEBAR_HEIGHT_VALUES,
    TITLEBAR_HOME_SHAPE_VALUES,
    TITLEBAR_SIZE_VALUES,
    TITLEBAR_SURFACE_VALUES,
)
from .fonts import get_builtin_fonts
from .themes import is_valid_theme, normalize_allowed_themes
from .translations import get_current_language_code, get_strings
# try-except for django_filters as it might not be installed (though likely is)
try:
    import django_filters
except ImportError:
    django_filters = None

SENSITIVE_ACTIVITY_MASK = "********"
_SENSITIVE_ACTIVITY_FIELD_NAMES = {
    "password",
    "secret",
    "secretkey",
    "totpsecret",
    "otpsecret",
    "otpkey",
    "otpbase32",
    "backupcode",
    "backupcodes",
    "token",
    "accesstoken",
    "refreshtoken",
    "apitoken",
}

# Normalize activity log model names for translation lookup
def normalize_activity_log_model_key(value):
    raw = str(value or '').strip().lower()
    if not raw:
        return ''
    normalized = re.sub(r'[^a-z0-9]+', '_', raw)
    normalized = re.sub(r'_+', '_', normalized).strip('_')
    return normalized

# Normalize string for fuzzy model matching
def _normalize_fuzzy_string(s):
    return unicodedata.normalize('NFKD', str(s)).casefold() if s else ""

# Fuzzy Model Lookup — Builds a cached mapping of normalized model names to model classes
@lru_cache(maxsize=1)
def _get_fuzzy_model_mapping():
    """Builds a cached mapping of normalized model names to model classes."""
    mapping = {}
    for model in apps.get_models():
        # 1. Exact app_label.model_name
        full_path = f"{model._meta.app_label}.{model._meta.model_name}".lower()
        mapping[full_path] = model
        
        # 2. Object name (Class name)
        obj_name = _normalize_fuzzy_string(model._meta.object_name)
        if obj_name and obj_name not in mapping:
            mapping[obj_name] = model
            
        # 3. Verbose name
        v_name = _normalize_fuzzy_string(model._meta.verbose_name)
        if v_name and v_name not in mapping:
            mapping[v_name] = model
            
    return mapping

# Translate activity log model names using MS_TRANS
def translate_activity_log_model_name(value, strings=None):
    if not value:
        return ""
    s = strings or get_strings()
    normalized = normalize_activity_log_model_key(value)
    keys_to_try = []
    if normalized:
        keys_to_try.append(f"model_{normalized}")
        keys_to_try.append(f"model_{normalized.replace('_', '')}")
        if '.' in str(value):
            tail = normalize_activity_log_model_key(str(value).split('.')[-1])
            if tail:
                keys_to_try.append(f"model_{tail}")
                keys_to_try.append(f"model_{tail.replace('_', '')}")
    for key in keys_to_try:
        if key in s:
            return s[key]
    return value

# Coerce a setting value to a list
def _coerce_list_setting(scope, key):
    value = scope.get(key)
    if value is None:
        value = []
    elif isinstance(value, tuple):
        value = list(value)
    scope[key] = value
    return value

# Insert middleware at specified position, removing duplicates
def _insert_middleware_once(middleware, middleware_path, *, after=None, before=None):
    if middleware_path in middleware:
        middleware.remove(middleware_path)

    insert_at = 0
    if before and before in middleware:
        insert_at = middleware.index(before)
    elif after and after in middleware:
        insert_at = middleware.index(after) + 1

    middleware.insert(insert_at, middleware_path)

# Secret Management — Reads a Docker secret first, then falls back to an environment variable
def get_secret(secret_name, env_var):
    """Read a Docker secret first, then fall back to an environment variable."""
    secret_path = os.path.join("/run/secrets", secret_name)
    try:
        with open(secret_path, "r", encoding="utf-8") as secret_file:
            return secret_file.read().strip()
    except OSError:
        return os.getenv(env_var)

EMAIL_CONFIG_TRANSPORTS = {'direct', 'relay'}
EMAIL_CONFIG_SECRET_STORAGES = {'env', 'encrypted_db'}
MICROSYS_INTERNAL_SMTP_RELAY_HOST = 'smtp-relay'
MICROSYS_INTERNAL_SMTP_RELAY_PORT = 1025
CLIENT_IP_MODE_REMOTE_ADDR = 'remote_addr'
CLIENT_IP_MODE_X_FORWARDED_FOR = 'x_forwarded_for'
CLIENT_IP_MODE_X_REAL_IP = 'x_real_ip'
CLIENT_IP_MODE_CLOUDFLARE = 'cloudflare'
CLIENT_IP_MODE_CUSTOM = 'custom'
CLIENT_IP_MODE_VALUES = {
    CLIENT_IP_MODE_REMOTE_ADDR,
    CLIENT_IP_MODE_X_FORWARDED_FOR,
    CLIENT_IP_MODE_X_REAL_IP,
    CLIENT_IP_MODE_CLOUDFLARE,
    CLIENT_IP_MODE_CUSTOM,
}

# Return default email configuration structure
def default_email_config():
    return {
        'transport': 'direct',
        'secret_storage': 'env',
        'host': '',
        'port': 587,
        'use_tls': True,
        'use_ssl': False,
        'username': '',
        'default_from_email': '',
        'encrypted_password': '',
        'password_configured': False,
    }

# Return default client IP resolution configuration
def default_client_ip_config():
    return {
        'mode': CLIENT_IP_MODE_X_FORWARDED_FOR,
        'trusted_proxy_hops': 1,
        'custom_header': '',
    }

# Normalize custom header name for client IP resolution
def _normalize_client_ip_header_name(value):
    raw_value = str(value or '').strip()
    if not raw_value:
        return ''
    normalized = raw_value.upper().replace('-', '_')
    if normalized in {'REMOTE_ADDR', 'CONTENT_TYPE', 'CONTENT_LENGTH'}:
        return normalized
    if not normalized.startswith('HTTP_'):
        normalized = f'HTTP_{normalized}'
    return normalized

# Normalize and validate client IP configuration
def normalize_client_ip_config(value):
    normalized = default_client_ip_config()
    if not isinstance(value, dict):
        return normalized

    mode = str(value.get('mode') or '').strip().lower()
    if mode in CLIENT_IP_MODE_VALUES:
        normalized['mode'] = mode

    try:
        trusted_proxy_hops = int(value.get('trusted_proxy_hops', normalized['trusted_proxy_hops']))
    except (TypeError, ValueError):
        trusted_proxy_hops = normalized['trusted_proxy_hops']
    normalized['trusted_proxy_hops'] = max(0, min(trusted_proxy_hops, 8))

    normalized['custom_header'] = _normalize_client_ip_header_name(value.get('custom_header'))
    if normalized['mode'] != CLIENT_IP_MODE_CUSTOM:
        normalized['custom_header'] = ''

    return normalized

# Normalize and validate email configuration
def normalize_email_config(value, *, redact_secret=False):
    config = value if isinstance(value, dict) else {}
    normalized = default_email_config()
    transport = str(config.get('transport') or '').strip()
    secret_storage = str(config.get('secret_storage') or '').strip()
    if transport in EMAIL_CONFIG_TRANSPORTS:
        normalized['transport'] = transport
    if secret_storage in EMAIL_CONFIG_SECRET_STORAGES:
        normalized['secret_storage'] = secret_storage
    normalized['host'] = str(config.get('host') or '').strip()
    try:
        normalized['port'] = int(config.get('port') or normalized['port'])
    except (TypeError, ValueError):
        normalized['port'] = 587
    normalized['use_tls'] = _coerce_import_bool(config.get('use_tls', normalized['use_tls']))
    normalized['use_ssl'] = _coerce_import_bool(config.get('use_ssl', normalized['use_ssl']))
    if normalized['use_ssl']:
        normalized['use_tls'] = False
    normalized['username'] = str(config.get('username') or '').strip()
    normalized['default_from_email'] = str(config.get('default_from_email') or '').strip()
    encrypted_password = str(config.get('encrypted_password') or '').strip()
    normalized['encrypted_password'] = encrypted_password
    normalized['password_configured'] = bool(encrypted_password or config.get('password_configured'))
    if redact_secret:
        normalized.pop('encrypted_password', None)
    return normalized

# Normalize allowed fonts list against available fonts
def normalize_allowed_fonts(allowed_fonts=None):
    from .fonts import get_builtin_fonts
    available = {f['slug'] for f in get_builtin_fonts()}
    if allowed_fonts is None:
        return list(available)

    normalized = []
    if isinstance(allowed_fonts, (list, tuple, set)):
        for font in allowed_fonts:
            if font in available and font not in normalized:
                normalized.append(font)

    return normalized or list(available)

# Get seed key for email encryption
def _email_secret_seed():
    configured_key = (
        os.getenv('MICROSYS_EMAIL_SECRET_KEY')
        or os.getenv('MICROSYS_SECRET_KEY')
        or getattr(settings, 'MICROSYS_EMAIL_SECRET_KEY', '')
        or getattr(settings, 'SECRET_KEY', '')
    )
    return str(configured_key or 'microsys-email-secret-dev-key')

# Get Fernet instance for email encryption
def _email_fernet():
    from cryptography.fernet import Fernet

    digest = hashlib.sha256(_email_secret_seed().encode('utf-8')).digest()
    return Fernet(base64.urlsafe_b64encode(digest))

# Encrypt email secret using Fernet
def encrypt_email_secret(raw_secret):
    raw_secret = str(raw_secret or '')
    if not raw_secret:
        return ''
    return _email_fernet().encrypt(raw_secret.encode('utf-8')).decode('utf-8')

# Decrypt email secret using Fernet
def decrypt_email_secret(encrypted_secret):
    encrypted_secret = str(encrypted_secret or '').strip()
    if not encrypted_secret:
        return ''
    try:
        return _email_fernet().decrypt(encrypted_secret.encode('utf-8')).decode('utf-8')
    except Exception:
        return ''

TOTP_SECRET_PREFIX = 'fernet$'
_UNSET = object()

# Get seed key for TOTP encryption
def _totp_secret_seed():
    configured_key = (
        os.getenv('MICROSYS_TOTP_SECRET_KEY')
        or os.getenv('MICROSYS_SECRET_KEY')
        or getattr(settings, 'MICROSYS_TOTP_SECRET_KEY', '')
        or getattr(settings, 'SECRET_KEY', '')
    )
    return str(configured_key or 'microsys-totp-secret-dev-key')

# Get Fernet instance for TOTP encryption
def _totp_fernet():
    from cryptography.fernet import Fernet

    digest = hashlib.sha256(_totp_secret_seed().encode('utf-8')).digest()
    return Fernet(base64.urlsafe_b64encode(digest))

# Check if TOTP secret is encrypted
def is_encrypted_totp_secret(value):
    return isinstance(value, str) and value.startswith(TOTP_SECRET_PREFIX)

# Encrypt TOTP secret using Fernet
def encrypt_totp_secret(raw_secret):
    raw_secret = str(raw_secret or '').strip()
    if not raw_secret:
        return ''
    if is_encrypted_totp_secret(raw_secret):
        return raw_secret
    encrypted = _totp_fernet().encrypt(raw_secret.encode('utf-8')).decode('utf-8')
    return f'{TOTP_SECRET_PREFIX}{encrypted}'

# Decrypt TOTP secret using Fernet
def decrypt_totp_secret(stored_secret):
    stored_secret = str(stored_secret or '').strip()
    if not stored_secret:
        return ''
    if not is_encrypted_totp_secret(stored_secret):
        return stored_secret
    encrypted = stored_secret[len(TOTP_SECRET_PREFIX):]
    try:
        return _totp_fernet().decrypt(encrypted.encode('utf-8')).decode('utf-8')
    except Exception:
        return ''

# Get decrypted TOTP secret from profile
def get_profile_totp_secret(profile):
    return decrypt_totp_secret(getattr(profile, 'totp_secret', ''))

# Update profile TOTP state without full profile save
def set_profile_totp_state(profile, *, raw_secret=_UNSET, enabled=_UNSET):
    if profile is None or not getattr(profile, 'pk', None):
        raise ValueError('Profile must be saved before updating TOTP state.')

    updates = {}
    if raw_secret is not _UNSET:
        updates['totp_secret'] = encrypt_totp_secret(raw_secret) if raw_secret else ''
    if enabled is not _UNSET:
        updates['is_totp_2fa_enabled'] = bool(enabled)
    if not updates:
        return profile

    profile.__class__._default_manager.filter(pk=profile.pk).update(**updates)
    for field_name, value in updates.items():
        setattr(profile, field_name, value)
    return profile

# Get effective email configuration from settings or database
def get_microsys_email_config(*, include_secret=False):
    try:
        SystemSettings = apps.get_model('microsys', 'SystemSettings')
        raw_stored_config = getattr(SystemSettings.load(), 'email_config', {})
        stored_config = normalize_email_config(raw_stored_config)
    except Exception:
        raw_stored_config = {}
        stored_config = default_email_config()

    if stored_config.get('transport') == 'relay':
        return {
            'transport': 'relay',
            'secret_storage': stored_config.get('secret_storage', 'encrypted_db'),
            'backend': 'django.core.mail.backends.smtp.EmailBackend',
            'host': getattr(settings, 'MICROSYS_SMTP_RELAY_HOST', MICROSYS_INTERNAL_SMTP_RELAY_HOST),
            'port': getattr(settings, 'MICROSYS_SMTP_RELAY_PORT', MICROSYS_INTERNAL_SMTP_RELAY_PORT),
            'use_tls': False,
            'use_ssl': False,
            'username': '',
            'password': '',
            'from_email': stored_config.get('default_from_email', ''),
            'password_configured': False,
        }

    if stored_config.get('secret_storage') == 'encrypted_db':
        config = {
            'transport': 'direct',
            'secret_storage': 'encrypted_db',
            'backend': 'django.core.mail.backends.smtp.EmailBackend',
            'host': stored_config.get('host', ''),
            'port': stored_config.get('port', 587),
            'use_tls': bool(stored_config.get('use_tls', True)),
            'use_ssl': bool(stored_config.get('use_ssl', False)),
            'username': stored_config.get('username', ''),
            'password': '',
            'from_email': stored_config.get('default_from_email', ''),
            'password_configured': bool(stored_config.get('encrypted_password')),
        }
        if include_secret:
            config['password'] = decrypt_email_secret(stored_config.get('encrypted_password'))
        return config

    backend = getattr(settings, 'EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
    stored_hints = normalize_email_config(raw_stored_config, redact_secret=True)
    hint_keys = set(raw_stored_config.keys()) if isinstance(raw_stored_config, dict) else set()
    return {
        'transport': 'direct',
        'secret_storage': 'env',
        'backend': backend,
        'host': stored_hints.get('host') if 'host' in hint_keys else (getattr(settings, 'EMAIL_HOST', '') or ''),
        'port': stored_hints.get('port') if 'port' in hint_keys else getattr(settings, 'EMAIL_PORT', None),
        'use_tls': bool(stored_hints.get('use_tls')) if 'use_tls' in hint_keys else bool(getattr(settings, 'EMAIL_USE_TLS', False)),
        'use_ssl': bool(stored_hints.get('use_ssl')) if 'use_ssl' in hint_keys else bool(getattr(settings, 'EMAIL_USE_SSL', False)),
        'username': stored_hints.get('username') if 'username' in hint_keys else (getattr(settings, 'EMAIL_HOST_USER', '') or ''),
        'password': getattr(settings, 'EMAIL_HOST_PASSWORD', '') if include_secret else '',
        'from_email': stored_hints.get('default_from_email') if 'default_from_email' in hint_keys else (getattr(settings, 'DEFAULT_FROM_EMAIL', '') or ''),
        'password_configured': bool(getattr(settings, 'EMAIL_HOST_PASSWORD', '')),
        'ui_hints': stored_hints,
    }

# Get email service status
def get_email_service_status():
    """
    Report whether Microsys-owned email flows are configured without touching
    SMTP networks or returning secrets.
    """
    try:
        SystemSettings = apps.get_model('microsys', 'SystemSettings')
        raw_stored_email_config = getattr(SystemSettings.load(), 'email_config', {})
        stored_email_config = normalize_email_config(raw_stored_email_config)
    except Exception:
        raw_stored_email_config = {}
        stored_email_config = default_email_config()
    stored_hint_keys = set(raw_stored_email_config.keys()) if isinstance(raw_stored_email_config, dict) else set()
    email_config = get_microsys_email_config(include_secret=False)
    backend = email_config.get('backend') or 'django.core.mail.backends.smtp.EmailBackend'
    from_email = email_config.get('from_email') or ''
    debug = bool(getattr(settings, 'DEBUG', False))
    host = email_config.get('host') or ''
    port = email_config.get('port')
    transport = email_config.get('transport') or 'direct'
    secret_storage = email_config.get('secret_storage') or 'env'
    local_backends = {
        'django.core.mail.backends.console.EmailBackend',
        'django.core.mail.backends.locmem.EmailBackend',
        'django.core.mail.backends.filebased.EmailBackend',
    }

    if backend in local_backends and debug:
        return {
            'available': True,
            'configured': True,
            'backend': backend,
            'from_email': from_email,
            'transport': transport,
            'secret_storage': secret_storage,
            'reason': 'local_debug_backend',
        }

    if backend == 'django.core.mail.backends.smtp.EmailBackend':
        password_ok = True
        if secret_storage == 'encrypted_db' and email_config.get('username'):
            password_ok = bool(email_config.get('password_configured'))
        if transport == 'relay':
            relay_upstream_host = (
                stored_email_config.get('host')
                if 'host' in stored_hint_keys and stored_email_config.get('host')
                else (os.getenv('SMTP_RELAY_HOST', '') or '')
            )
            relay_upstream_port = (
                stored_email_config.get('port')
                if 'port' in stored_hint_keys and stored_email_config.get('port')
                else int(os.getenv('SMTP_RELAY_PORT', '587') or '587')
            )
            relay_from_email = (
                stored_email_config.get('default_from_email')
                if 'default_from_email' in stored_hint_keys and stored_email_config.get('default_from_email')
                else (getattr(settings, 'DEFAULT_FROM_EMAIL', '') or os.getenv('DEFAULT_FROM_EMAIL', '') or '')
            )
            relay_password_ok = True
            if stored_email_config.get('secret_storage') == 'encrypted_db' and stored_email_config.get('username'):
                relay_password_ok = bool(stored_email_config.get('password_configured'))
            configured = bool(
                relay_upstream_host
                and relay_upstream_port
                and relay_from_email
                and relay_password_ok
            )
            return {
                'available': configured,
                'configured': configured,
                'backend': backend,
                'from_email': from_email,
                'transport': transport,
                'secret_storage': secret_storage,
                'detail': f"{host}:{port} -> {relay_upstream_host}:{relay_upstream_port}"
                if host and port and relay_upstream_host and relay_upstream_port else '',
                'reason': 'relay_configured' if configured else (
                    'relay_missing_password' if not relay_password_ok else 'relay_missing_upstream_host_port_or_from_email'
                ),
            }
        configured = bool(host and port and from_email and password_ok)
        missing_reason = 'smtp_missing_host_port_or_from_email'
        if secret_storage == 'encrypted_db' and not password_ok:
            missing_reason = 'encrypted_db_missing_password'
        return {
            'available': configured,
            'configured': configured,
            'backend': backend,
            'from_email': from_email,
            'transport': transport,
            'secret_storage': secret_storage,
            'detail': f"{host}:{port}" if host and port else '',
            'reason': 'smtp_configured' if configured else missing_reason,
        }

    configured = bool(from_email)
    return {
        'available': configured,
        'configured': configured,
        'backend': backend,
        'from_email': from_email,
        'transport': transport,
        'secret_storage': secret_storage,
        'reason': 'custom_backend_configured' if configured else 'missing_default_from_email',
    }

# Send Microsys-owned transactional email
def send_microsys_mail(subject, message, recipient_list, *, from_email=None, fail_silently=False):
    """Send Microsys-owned transactional email through the selected delivery path."""
    email_config = get_microsys_email_config(include_secret=True)
    effective_from = from_email or email_config.get('from_email') or getattr(settings, 'DEFAULT_FROM_EMAIL', None)

    backend = email_config.get('backend') or getattr(settings, 'EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
    if backend != 'django.core.mail.backends.smtp.EmailBackend':
        return send_mail(subject, message, effective_from, recipient_list, fail_silently=fail_silently)

    connection = get_connection(
        backend=backend,
        host=email_config.get('host') or None,
        port=email_config.get('port') or None,
        username=email_config.get('username') or None,
        password=email_config.get('password') or None,
        use_tls=bool(email_config.get('use_tls')),
        use_ssl=bool(email_config.get('use_ssl')),
        fail_silently=fail_silently,
    )
    email = EmailMessage(
        subject=subject,
        body=message,
        from_email=effective_from,
        to=list(recipient_list or []),
        connection=connection,
    )
    return email.send(fail_silently=fail_silently)


def is_sensitive_activity_field_name(field_name):
    """Return True when an activity-log field should be masked before display/storage."""
    if not field_name:
        return False

    normalized = re.sub(r"[^a-z0-9]+", "", str(field_name).lower())
    if not normalized:
        return False

    if normalized in _SENSITIVE_ACTIVITY_FIELD_NAMES:
        return True
    if "password" in normalized:
        return True
    if "backup" in normalized and "code" in normalized:
        return True
    if ("otp" in normalized or "totp" in normalized) and any(
        marker in normalized for marker in ("secret", "key", "token", "base32")
    ):
        return True
    if normalized.endswith("secret") or normalized.endswith("secretkey"):
        return True
    return False


def microsys_settings(scope):
    """
    Apply the default MicroSys settings requirements to a Django settings module.

    Intended usage from a host project's settings.py:

        from microsys.utils import microsys_settings
        microsys_settings(globals())
    """
    if not isinstance(scope, dict):
        raise TypeError("microsys_settings() expects the result of globals() from settings.py")

    installed_apps = _coerce_list_setting(scope, "INSTALLED_APPS")
    middleware = _coerce_list_setting(scope, "MIDDLEWARE")
    templates = _coerce_list_setting(scope, "TEMPLATES")

    required_apps = [
        "microsys",
        "crispy_forms",
        "crispy_bootstrap5",
        "django_filters",
        "django_tables2",
    ]
    for app_label in reversed(required_apps):
        if app_label in installed_apps:
            installed_apps.remove(app_label)
        installed_apps.insert(0, app_label)

    auth_middleware = "django.contrib.auth.middleware.AuthenticationMiddleware"
    session_middleware = "django.contrib.sessions.middleware.SessionMiddleware"
    common_middleware = "django.middleware.common.CommonMiddleware"
    locale_middleware = "django.middleware.locale.LocaleMiddleware"
    microsys_middleware = "microsys.middleware.MicrosysMiddleware"

    if session_middleware in middleware and common_middleware in middleware:
        session_index = middleware.index(session_middleware)
        common_index = middleware.index(common_middleware)
        if session_index < common_index:
            _insert_middleware_once(
                middleware,
                locale_middleware,
                before=common_middleware,
            )
        else:
            _insert_middleware_once(
                middleware,
                locale_middleware,
                after=session_middleware,
            )
    elif session_middleware in middleware:
        _insert_middleware_once(
            middleware,
            locale_middleware,
            after=session_middleware,
        )
    elif common_middleware in middleware:
        _insert_middleware_once(
            middleware,
            locale_middleware,
            before=common_middleware,
        )
    else:
        _insert_middleware_once(middleware, locale_middleware)

    if auth_middleware in middleware:
        _insert_middleware_once(
            middleware,
            microsys_middleware,
            after=auth_middleware,
        )
    else:
        _insert_middleware_once(middleware, microsys_middleware)

    context_proc = "microsys.context_processors.microsys_context"
    for template in templates:
        if not isinstance(template, dict):
            continue
        options = template.setdefault("OPTIONS", {})
        processors = options.setdefault("context_processors", [])
        if context_proc not in processors:
            processors.append(context_proc)

    scope.setdefault("CRISPY_ALLOWED_TEMPLATE_PACKS", "bootstrap5")
    scope.setdefault("CRISPY_TEMPLATE_PACK", "bootstrap5")
    scope.setdefault("LANGUAGE_CODE", "ar")
    scope.setdefault("TIME_ZONE", "Etc/GMT-2")
    scope.setdefault("USE_I18N", True)
    scope.setdefault("USE_TZ", True)
    scope.setdefault("DEFAULT_CHARSET", "utf-8")

    message_tags = scope.get("MESSAGE_TAGS")
    if not isinstance(message_tags, dict):
        message_tags = dict(message_tags or {})
    message_tags.setdefault(messages.ERROR, "danger")
    scope["MESSAGE_TAGS"] = message_tags

    format_module_path = scope.get("FORMAT_MODULE_PATH")
    if not format_module_path:
        scope["FORMAT_MODULE_PATH"] = ["microsys.formats"]
    elif isinstance(format_module_path, (list, tuple)):
        merged_format_module_path = list(format_module_path)
        if "microsys.formats" not in merged_format_module_path:
            merged_format_module_path.append("microsys.formats")
        scope["FORMAT_MODULE_PATH"] = merged_format_module_path
    else:
        scope["FORMAT_MODULE_PATH"] = [format_module_path, "microsys.formats"]
    return scope


def _normalize_asset_url(value, fallback_base='/media/'):
    """Ensure stored media paths render as browser-safe absolute URLs."""
    if not value:
        return value

    normalized = str(value).strip()
    if not normalized:
        return normalized

    configured_media_url = str(getattr(settings, 'MEDIA_URL', '') or '').strip()
    if configured_media_url in {'', '/'}:
        base_url = fallback_base
    else:
        base_url = configured_media_url
    if not base_url.startswith('/'):
        base_url = f'/{base_url}'
    if not base_url.endswith('/'):
        base_url = f'{base_url}/'

    if (
        normalized.startswith(('http://', 'https://', '//', 'data:'))
        or ':' in normalized.split('/', 1)[0]
    ):
        return normalized

    if normalized.startswith('/'):
        if normalized.startswith(base_url) or normalized.startswith('/static/'):
            return normalized
        normalized = normalized.lstrip('/')

    return f"{base_url}{normalized.lstrip('/')}"

# Auth Check — Staff permission test for @user_passes_test decorator
def is_staff(user):
    return user.is_staff

# Auth Check — Superuser permission test for @user_passes_test decorator
def is_superuser(user):
    return user.is_superuser

# Network Helper — Extract client IP from request (supports X-Forwarded-For)
def get_client_ip(request):
    """Extract client IP address from request."""
    if not request:
        return None

    try:
        config = normalize_client_ip_config(get_system_config().get('client_ip'))
    except Exception:
        config = default_client_ip_config()

    meta = getattr(request, 'META', {}) or {}
    remote_addr = str(meta.get('REMOTE_ADDR') or '').strip()

    def _header_value(header_name):
        return str(meta.get(header_name) or '').strip()

    def _parse_chain(raw_value):
        parts = [part.strip() for part in str(raw_value or '').split(',') if part.strip()]
        if not parts:
            return ''
        trusted_proxy_hops = max(0, int(config.get('trusted_proxy_hops', 1) or 0))
        if len(parts) > trusted_proxy_hops:
            return parts[-(trusted_proxy_hops + 1)]
        return parts[0]

    mode = config.get('mode', CLIENT_IP_MODE_X_FORWARDED_FOR)
    candidate = ''
    if mode == CLIENT_IP_MODE_REMOTE_ADDR:
        candidate = remote_addr
    elif mode == CLIENT_IP_MODE_X_FORWARDED_FOR:
        candidate = _parse_chain(_header_value('HTTP_X_FORWARDED_FOR'))
    elif mode == CLIENT_IP_MODE_X_REAL_IP:
        candidate = _header_value('HTTP_X_REAL_IP')
    elif mode == CLIENT_IP_MODE_CLOUDFLARE:
        candidate = _header_value('HTTP_CF_CONNECTING_IP')
    elif mode == CLIENT_IP_MODE_CUSTOM:
        candidate = _header_value(config.get('custom_header'))

    if candidate:
        return candidate

    fallback_xff = _parse_chain(_header_value('HTTP_X_FORWARDED_FOR'))
    if fallback_xff:
        return fallback_xff
    return remote_addr or None


def get_user_scope(user):
    """Return the user's scope from profile first, then direct attribute."""
    if not user:
        return None
    profile = get_user_profile(user)
    if profile and getattr(profile, 'scope', None):
        return profile.scope
    return getattr(user, 'scope', None)


def get_user_profile(user):
    """Return the related profile when it exists; missing profiles fail closed elsewhere."""
    if not user:
        return None
    try:
        return getattr(user, 'profile', None)
    except Exception:
        return None


def user_has_scope_state(user):
    """
    Return True when the user's scoped/unscoped state is knowable.

    Real Django users should have a Profile row. Lightweight test doubles may
    expose a direct `scope` attribute instead.
    """
    if not user:
        return False
    if hasattr(user, 'scope'):
        return True
    return get_user_profile(user) is not None


def exclude_global_staff_users(queryset):
    """Exclude users who have the Global Staff `manage_scopes` permission."""
    return queryset.exclude(
        user_permissions__content_type__app_label='microsys',
        user_permissions__codename='manage_scopes',
    ).exclude(
        groups__permissions__content_type__app_label='microsys',
        groups__permissions__codename='manage_scopes',
    ).distinct()


def strip_manage_scopes_permissions(permissions):
    """Return a permission list with Microsys Global Staff elevation removed."""
    return [
        permission
        for permission in permissions
        if not (
            getattr(permission, 'codename', None) == 'manage_scopes'
            and getattr(getattr(permission, 'content_type', None), 'app_label', None) == 'microsys'
        )
    ]


def can_manage_target_user(actor, target_user=None):
    """
    Reuse the existing user-management guardrails:
    - actor must be staff
    - superuser targets are self-only
    - scoped non-superusers can only manage users in their own scope
    - Central Staff (non-scoped without manage_scopes) can ONLY manage scopeless users
    - Global Staff (non-scoped with manage_scopes) can manage ALL users
    """
    if not actor or not getattr(actor, 'is_authenticated', False) or not getattr(actor, 'is_staff', False):
        return False

    if target_user is None:
        return True

    if not getattr(actor, 'is_superuser', False) and not user_has_scope_state(actor):
        return False
    if not getattr(actor, 'is_superuser', False) and not user_has_scope_state(target_user):
        return False

    if getattr(target_user, 'is_superuser', False) and actor != target_user:
        return False

    # Central Staff: can only manage scopeless (NULL scope) users
    if is_central_staff(actor):
        target_scope = get_user_scope(target_user)
        if target_scope is not None:
            return False
        return True

    # Global Staff: can manage all users (fall through to default logic)
    # Scoped staff: can only manage same scope
    if not getattr(actor, 'is_superuser', False) and not is_global_staff(actor):
        actor_scope = get_user_scope(actor)
        target_scope = get_user_scope(target_user)
        if actor_scope and actor_scope != target_scope:
            return False
    return True


def is_global_staff(user):
    """
    Global Staff tier: Non-scoped staff with manage_scopes permission.
    Can create/manage scopes and ALL users (scoped and scopeless).
    Only superusers can create Global Staff.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    if not getattr(user, 'is_staff', False):
        return False
    if not user_has_scope_state(user):
        return False
    # Must have no scope and have manage_scopes permission
    user_scope = get_user_scope(user)
    if user_scope is not None:
        return False
    return user.has_perm('microsys.manage_scopes')


def is_central_staff(user):
    """
    Central Staff tier: Non-scoped staff WITHOUT manage_scopes permission.
    Can only create/manage scopeless (NULL scope) users.
    Cannot view scoped users, manage scopes, or assign scopes.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return False  # Superuser is not Central Staff
    if not getattr(user, 'is_staff', False):
        return False
    if not user_has_scope_state(user):
        return False
    # Must have no scope and NOT have manage_scopes permission
    user_scope = get_user_scope(user)
    if user_scope is not None:
        return False
    return not user.has_perm('microsys.manage_scopes')

# Normalize permission codenames to a set
def _normalize_permission_codename_set(permission_codenames):
    normalized = set()
    for permission in permission_codenames or []:
        value = str(permission or '').strip()
        if not value:
            continue
        normalized.add(value)
        if '.' in value:
            normalized.add(value.rsplit('.', 1)[-1])
    return normalized


def get_user_management_tier_state(
    *,
    is_superuser,
    is_staff,
    scope,
    permission_codenames,
):
    """
    Classify the current user-management tier without changing authorization rules.

    The returned payload is intentionally UI-friendly so forms, tables, and templates
    can present the same tier language consistently.
    """
    s = get_strings()
    normalized_permissions = _normalize_permission_codename_set(permission_codenames)
    has_scope = scope is not None
    scope_label = getattr(scope, 'name', '') if has_scope else ''
    has_manage_scopes = 'manage_scopes' in normalized_permissions
    has_manage_staff = 'manage_staff' in normalized_permissions

    tier_catalog = {
        'regular_user': {
            'title': s.get('tier_regular_user', 'Standard User'),
            'description': s.get(
                'tier_desc_regular_user',
                'No staff user-management access is enabled for this account.',
            ),
            'badge_classes': 'bg-secondary',
            'icon': 'bi-person',
            'capabilities': [
                s.get('tier_cap_regular_1', 'No staff access to the user directory.'),
                s.get('tier_cap_regular_2', 'Can use normal account features only.'),
                s.get('tier_cap_regular_3', 'Staff-related permissions stay inactive until staff access is enabled.'),
            ],
        },
        'superuser': {
            'title': s.get('tier_superuser', 'Superuser'),
            'description': s.get(
                'tier_desc_superuser',
                'Full system administration access without scope or permission limits.',
            ),
            'badge_classes': 'bg-danger',
            'icon': 'bi-stars',
            'capabilities': [
                s.get('tier_cap_superuser_1', 'Can view and manage all users and scopes.'),
                s.get('tier_cap_superuser_2', 'Can assign any staff tier or permission.'),
                s.get('tier_cap_superuser_3', 'Can access full system administration features.'),
            ],
        },
        'global_staff': {
            'title': s.get('tier_global_staff', 'Global Staff'),
            'description': s.get(
                'tier_desc_global_staff',
                'Staff access across all scopes, including scope management.',
            ),
            'badge_classes': 'bg-primary',
            'icon': 'bi-globe2',
            'capabilities': [
                s.get('tier_cap_global_1', 'Can view and manage users across all scopes.'),
                s.get('tier_cap_global_2', 'Can create and manage scopes.'),
                s.get('tier_cap_global_3', 'Can assign users to any scope or leave them scopeless.'),
            ],
        },
        'central_staff': {
            'title': s.get('tier_central_staff', 'Central Staff'),
            'description': s.get(
                'tier_desc_central_staff',
                'Staff access limited to scopeless users in the core system.',
            ),
            'badge_classes': 'bg-info text-dark',
            'icon': 'bi-building',
            'capabilities': [
                s.get('tier_cap_central_1', 'Can manage scopeless users only.'),
                s.get('tier_cap_central_2', 'Cannot view scoped users or their data.'),
                s.get('tier_cap_central_3', 'Cannot assign scopes or manage scopes.'),
            ],
        },
        'scoped_staff': {
            'title': s.get('tier_scoped_staff', 'Scoped Staff'),
            'description': s.get(
                'tier_desc_scoped_staff',
                'Staff access is limited to the assigned scope.',
            ),
            'badge_classes': 'bg-warning text-dark',
            'icon': 'bi-diagram-2',
            'capabilities': [
                s.get('tier_cap_scoped_1', 'Can manage users inside the assigned scope only.'),
                s.get('tier_cap_scoped_2', 'Cannot access users outside the assigned scope.'),
                s.get('tier_cap_scoped_3', 'Scope assignment controls visibility and user-management actions.'),
            ],
        },
    }

    warning_catalog = {
        'needs_staff': {
            'key': 'needs_staff',
            'message': s.get(
                'tier_warning_needs_staff',
                'Staff-related permissions are selected, but staff access is not enabled yet.',
            ),
        },
        'scoped_manage_scopes_conflict': {
            'key': 'scoped_manage_scopes_conflict',
            'message': s.get(
                'tier_warning_scoped_manage_scopes',
                'Global Staff access is ineffective while a scope is assigned.',
            ),
        },
    }

    if is_superuser:
        tier_key = 'superuser'
    elif not is_staff:
        tier_key = 'regular_user'
    elif has_scope:
        tier_key = 'scoped_staff'
    elif has_manage_scopes:
        tier_key = 'global_staff'
    else:
        tier_key = 'central_staff'

    warnings = []
    if not is_staff and (has_manage_scopes or has_manage_staff):
        warnings.append(warning_catalog['needs_staff'])
    if is_staff and has_scope and has_manage_scopes:
        warnings.append(warning_catalog['scoped_manage_scopes_conflict'])

    tier_state = dict(tier_catalog[tier_key])
    tier_state.update({
        'tier_key': tier_key,
        'scope_label': scope_label,
        'has_scope': has_scope,
        'has_manage_scopes': has_manage_scopes,
        'has_manage_staff': has_manage_staff,
        'can_delegate_staff': bool(is_staff and has_manage_staff),
        'delegation_badge_label': s.get('tier_delegate_badge', 'Can Assign Staff Roles'),
        'warnings': warnings,
    })
    return tier_state

# Get user management tier state for a specific user
def get_user_management_tier_state_for_user(user):
    if not user or not getattr(user, 'is_authenticated', False):
        return get_user_management_tier_state(
            is_superuser=False,
            is_staff=False,
            scope=None,
            permission_codenames=set(),
        )

    permission_codenames = set()
    try:
        permission_codenames = user.get_all_permissions()
    except Exception:
        permission_codenames = set()

    return get_user_management_tier_state(
        is_superuser=bool(getattr(user, 'is_superuser', False)),
        is_staff=bool(getattr(user, 'is_staff', False)),
        scope=get_user_scope(user),
        permission_codenames=permission_codenames,
    )


def user_can_view_user_directory(user):
    """
    The full user-management surfaces stay staff-only.
    Global Staff and Central Staff can access the directory (with different visibility).
    Scoped staff can also access if they have view_user or manage_staff.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    if not getattr(user, 'is_staff', False):
        return False
    if not user_has_scope_state(user):
        return False
    # Global Staff and Central Staff (both non-scoped) can access
    if get_user_scope(user) is None:
        return True
    # Scoped staff need explicit permissions
    return user.has_perm('auth.view_user') or user.has_perm('microsys.manage_staff')


def user_can_view_activity_log(user):
    """
    Activity-log access is explicit.
    Keep a legacy alias check for the old typo'd codename while the package
    finishes converging on `view_activitylog`.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    return user.has_perm('microsys.view_activitylog') or user.has_perm('microsys.view_activity_log')

# Check if user has section view permission
def user_has_section_view_permission(user):
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    return user.has_perm('microsys.view_sections') or user.has_perm('microsys.manage_sections')


# Check if user has section manage permission
def user_has_section_manage_permission(user):
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    return user.has_perm('microsys.manage_sections')


def user_has_model_permission(user, model, action):
    """Return True when the user has the Django model permission for the given action."""
    if not user or not getattr(user, 'is_authenticated', False) or not model or not action:
        return False
    if getattr(user, 'is_superuser', False):
        return True
    permission = f'{model._meta.app_label}.{action}_{model._meta.model_name}'
    return user.has_perm(permission)


def user_matches_permission_token(user, permission):
    """
    Resolve Microsys-internal permission tokens plus normal Django permission strings.

    Internal tokens are used by discovery/sidebar/template-adjacent code so those
    surfaces can stay aligned with the newer MSRP authorization helpers.
    """
    if not permission:
        return True
    if not user or not getattr(user, 'is_authenticated', False):
        return False

    if permission == 'is_staff':
        return bool(getattr(user, 'is_staff', False))
    if permission == 'is_superuser':
        return bool(getattr(user, 'is_superuser', False))
    if permission == '__ms_authenticated__':
        return True
    if permission == '__ms_user_directory__':
        return user_can_view_user_directory(user)
    if permission == '__ms_activity_log__':
        return user_can_view_activity_log(user)
    if permission == '__ms_sections_view__':
        return user_has_section_view_permission(user)
    if permission == '__ms_sections_manage__':
        return user_has_section_manage_permission(user)

    return bool(user.has_perm(permission))


def user_has_any_permission_tokens(user, permissions, default_visible_to_all=False):
    """
    Check if user has any of the given permissions.
    
    Args:
        user: The user to check
        permissions: List or string of permissions
        default_visible_to_all: If True and permissions is empty, returns True (backward compatible).
                              If False and permissions is empty, returns False (secure default).
    """
    if not permissions:
        return default_visible_to_all
    if isinstance(permissions, str):
        permissions = [permissions]
    return any(user_matches_permission_token(user, p) for p in permissions)

# Activity Logging — Universal logging utility for user actions
def log_user_action(request, action, instance=None, model_name=None, details=None, number=None, object_id=None):
    """
    Centralized activity logging. All manual UserActivityLog creation should go through here.
    
    Args:
        request:    Django request object
        action:     Action string (e.g. 'CREATE', 'LOGIN', 'EXPORT')
        instance:   Optional model instance (auto-extracts pk, number, model_name)
        model_name: Optional override for model name (used when no instance exists)
        details:    Optional dict of extra details to attach to log
        number:     Optional override for the document number field
    """
    UserActivityLog = apps.get_model('microsys', 'UserActivityLog')
    user = getattr(request, 'user', None) if request else None
    if not user or not getattr(user, 'is_authenticated', False):
        try:
            from .middleware import get_current_user
            user = get_current_user()
        except Exception:
            user = None

    UserActivityLog.safe_log(
        user=user,
        action=action,
        model_name=model_name or (instance._meta.verbose_name if instance else None),
        object_id=object_id if object_id is not None else (instance.pk if instance else None),
        number=number or (getattr(instance, 'number', '') if instance else None),
        details=details,
        ip_address=get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
    )

# Config Merger — Merges translation dictionaries across language layers
def _merge_translation_layers(*layers):
    merged = {}
    for layer in layers:
        if not isinstance(layer, dict):
            continue
        for lang, values in layer.items():
            if not isinstance(values, dict):
                continue
            merged.setdefault(lang, {})
            merged[lang].update(values)
    return merged

# Config Merger — Merges language configuration dictionaries
def _merge_language_layers(*layers):
    merged = {}
    for layer in layers:
        if not isinstance(layer, dict):
            continue
        for code, payload in layer.items():
            if isinstance(payload, dict):
                merged[code] = {**merged.get(code, {}), **payload}
            elif payload:
                merged[code] = {'name': str(payload)}
    return merged


DEFAULT_LANGUAGE_CATALOG = {
    'en': {'name': 'English', 'dir': 'ltr', 'flag': '🇬🇧'},
    'ar': {'name': 'العربية', 'dir': 'rtl', 'flag': '🇱🇾'},
}

# Normalize language code to standard format
def _normalize_language_code(code):
    normalized = str(code or '').strip().lower().replace('_', '-')
    if not normalized:
        return ''
    if not re.match(r'^[a-z]{2,3}(?:-[a-z0-9]{2,8})?$', normalized):
        return ''
    return normalized


def normalize_language_catalog(*layers):
    """Normalize explicitly enabled UI languages without enabling discovered translations."""
    merged = deepcopy(DEFAULT_LANGUAGE_CATALOG)
    for layer in layers:
        if not isinstance(layer, dict):
            continue
        for raw_code, payload in layer.items():
            code = _normalize_language_code(raw_code)
            if not code:
                continue
            if isinstance(payload, dict):
                name = str(payload.get('name') or code).strip() or code
                direction = str(payload.get('dir') or '').strip().lower()
                if direction not in {'ltr', 'rtl'}:
                    direction = 'rtl' if code.startswith(('ar', 'fa', 'he', 'ur')) else 'ltr'
                merged[code] = {
                    'name': name,
                    'dir': direction,
                    'flag': str(payload.get('flag') or '').strip(),
                }
            elif payload:
                merged[code] = {
                    'name': str(payload).strip() or code,
                    'dir': 'rtl' if code.startswith(('ar', 'fa', 'he', 'ur')) else 'ltr',
                    'flag': '',
                }
    return merged

# Normalize system names dictionary
def normalize_system_names(value):
    names = {}
    if isinstance(value, dict):
        for raw_code, raw_name in value.items():
            code = _normalize_language_code(raw_code)
            name = str(raw_name or '').strip()
            if code and name:
                names[code] = name
    return names

# Resolve system name for a given language
def resolve_system_name(system_names, lang_code=None, default_language='en'):
    names = normalize_system_names(system_names)
    lang = _normalize_language_code(lang_code) or _normalize_language_code(default_language) or 'en'
    default_lang = _normalize_language_code(default_language) or 'en'
    for code in (lang, default_lang):
        if code in names and names[code]:
            return names[code]
    for value in names.values():
        if value:
            return value
    return 'microSYS'

# Build grouped configuration structure
def build_config_groups(config, current_language=None):
    languages = normalize_language_catalog(config.get('languages', {}))
    default_language = _normalize_language_code(config.get('default_language')) or 'en'
    if default_language not in languages:
        default_language = 'en' if 'en' in languages else next(iter(languages), 'en')
    display_language = _normalize_language_code(current_language) or default_language
    if display_language not in languages:
        display_language = default_language
    system_names = normalize_system_names(config.get('system_names'))
    display_name = resolve_system_name(system_names, display_language, default_language)
    return {
        'identity': {
            'system_names': system_names,
            'display_name': display_name,
            'logo_url': config.get('logo_url'),
            'login_logo_url': config.get('login_logo_url'),
            'favicon_url': config.get('favicon_url'),
        },
        'localization': {
            'languages': languages,
            'default_language': default_language,
            'translations': config.get('translations', {}),
            'allow_user_language_override': bool(config.get('allow_user_language_override', True)),
        },
        'security': {
            'public_root': bool(config.get('public_root', False)),
            'email_2fa': bool(config.get('email_2fa', False)),
            'email_config': normalize_email_config(config.get('email_config', {}), redact_secret=True),
            'public_registration_enabled': bool(config.get('public_registration_enabled', False)),
            'registration_activation_mode': config.get(
                'registration_activation_mode',
                REGISTRATION_ACTIVATION_AUTO_LOGIN,
            ),
            'registration_throttle_enabled': bool(config.get('registration_throttle_enabled', True)),
        },
        'navigation': {
            'home_url': config.get('home_url') or DEFAULT_HOME_URL,
            'sidebar': config.get('sidebar', default_sidebar_config()),
        },
        'appearance': {
            'default_theme': config.get('default_theme', 'light'),
            'allowed_themes': list(config.get('allowed_themes', [])),
            'default_table_density': config.get('default_table_density', DEFAULT_TABLE_DENSITY),
            'titlebar': config.get('titlebar', default_titlebar_config()),
        },
        'personalization': {
            'allow_user_theme_override': bool(config.get('allow_user_theme_override', True)),
            'allow_user_language_override': bool(config.get('allow_user_language_override', True)),
            'allow_user_sidebar_density': bool(
                normalize_sidebar_behavior(config.get('sidebar', {})).get('allow_user_density', True)
            ),
        },
    }

# Sidebar Helper — Removes duplicate sidebar entries by id/url_name/label
def _dedupe_sidebar_entries(entries):
    seen = set()
    deduped = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        key = entry.get('id') or entry.get('url_name') or entry.get('label')
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    return deduped

# Return default titlebar configuration
def default_titlebar_config():
    return {
        'show_title': True,
        'show_logo': True,
        'show_home_button': True,
        'hide_on_public_unauthenticated_index': False,
        'home_shape': 'circle',
        'title_align': 'start',
        'title_size': 'md',
        'height': 'balanced',
        'surface': 'default',
    }

# Normalize and validate titlebar configuration
def normalize_titlebar_config(titlebar_config):
    config = titlebar_config if isinstance(titlebar_config, dict) else {}
    normalized = default_titlebar_config()
    normalized['show_title'] = bool(config.get('show_title', normalized['show_title']))
    normalized['show_logo'] = bool(config.get('show_logo', normalized['show_logo']))
    normalized['show_home_button'] = bool(config.get('show_home_button', normalized['show_home_button']))
    normalized['hide_on_public_unauthenticated_index'] = bool(
        config.get(
            'hide_on_public_unauthenticated_index',
            normalized['hide_on_public_unauthenticated_index'],
        )
    )

    home_shape = config.get('home_shape')
    if home_shape in TITLEBAR_HOME_SHAPE_VALUES:
        normalized['home_shape'] = home_shape

    title_align = config.get('title_align')
    if title_align in TITLEBAR_ALIGN_VALUES:
        normalized['title_align'] = title_align

    title_size = config.get('title_size')
    if title_size in TITLEBAR_SIZE_VALUES:
        normalized['title_size'] = title_size

    height = config.get('height')
    if height in TITLEBAR_HEIGHT_VALUES:
        normalized['height'] = height

    surface = config.get('surface')
    if surface in TITLEBAR_SURFACE_VALUES:
        normalized['surface'] = surface

    return normalized

# Return default sidebar configuration
def default_sidebar_config():
    return {
        'enabled': True,
        'home_url_name': None,
        'entries': [],
        'enable_reorder': True,
        'show_toolbar': True,
        'show_icons': True,
        'density': DEFAULT_SIDEBAR_DENSITY,
        'allow_user_density': True,
        'collapse_mode': DEFAULT_SIDEBAR_COLLAPSE_MODE,
    }

# Normalize and validate sidebar behavior configuration
def normalize_sidebar_behavior(sidebar_config):
    config = sidebar_config if isinstance(sidebar_config, dict) else {}
    normalized = default_sidebar_config()
    normalized['enabled'] = bool(config.get('enabled', normalized['enabled']))
    normalized['home_url_name'] = config.get('home_url_name') if config.get('home_url_name') else None
    if isinstance(config.get('entries'), list):
        normalized['entries'] = [entry for entry in config.get('entries', []) if isinstance(entry, dict)]
    normalized['enable_reorder'] = bool(config.get('enable_reorder', normalized['enable_reorder']))
    normalized['show_toolbar'] = bool(config.get('show_toolbar', normalized['show_toolbar']))
    normalized['show_icons'] = bool(config.get('show_icons', normalized['show_icons']))
    normalized['allow_user_density'] = bool(config.get('allow_user_density', normalized['allow_user_density']))

    if not normalized['enabled']:
        normalized['show_toolbar'] = False
        normalized['enable_reorder'] = False
        normalized['allow_user_density'] = False

    density = config.get('density')
    if density in SIDEBAR_DENSITY_VALUES:
        normalized['density'] = density

    collapse_mode = config.get('collapse_mode')
    if collapse_mode in SIDEBAR_COLLAPSE_MODE_VALUES:
        normalized['collapse_mode'] = collapse_mode

    if not normalized['show_icons'] and normalized['collapse_mode'] == 'icons':
        normalized['collapse_mode'] = 'hidden'

    return normalized

# Get effective allowed themes from configuration
def get_effective_allowed_themes(config):
    if not isinstance(config, dict):
        return tuple(normalize_allowed_themes())
    return tuple(normalize_allowed_themes(config.get('allowed_themes')))

# Resolve user theme preference against allowed themes
def resolve_user_theme_preference(user_prefs, config):
    prefs = dict(user_prefs or {})
    allowed_themes = set(get_effective_allowed_themes(config))
    default_theme = config.get('default_theme', 'light')
    if default_theme not in allowed_themes:
        default_theme = next(iter(allowed_themes), 'light')

    if not config.get('allow_user_theme_override', True):
        prefs.pop('theme', None)
        prefs['theme'] = default_theme
        return prefs

    if prefs.get('theme') not in allowed_themes:
        prefs['theme'] = default_theme
    return prefs

# Resolve user sidebar density preference
def resolve_sidebar_density_preference(user_prefs, config):
    prefs = dict(user_prefs or {})
    sidebar_config = normalize_sidebar_behavior(config.get('sidebar', {}))
    if not sidebar_config.get('allow_user_density', True):
        prefs.pop('sidebar_density', None)
        prefs['sidebar_density'] = sidebar_config.get('density', DEFAULT_SIDEBAR_DENSITY)
        return prefs

    if prefs.get('sidebar_density') not in SIDEBAR_DENSITY_VALUES:
        prefs['sidebar_density'] = sidebar_config.get('density', DEFAULT_SIDEBAR_DENSITY)
    return prefs

# Resolve user sidebar collapsed preference
def resolve_sidebar_collapsed_preference(user_prefs, config, session_collapsed=False):
    prefs = dict(user_prefs or {})
    collapse_mode = normalize_sidebar_behavior(config.get('sidebar', {})).get('collapse_mode', DEFAULT_SIDEBAR_COLLAPSE_MODE)
    if collapse_mode == 'locked_expanded':
        prefs.pop('sidebar_collapsed', None)
        return False, prefs

    raw_value = prefs.get('sidebar_collapsed', session_collapsed)
    if isinstance(raw_value, str):
        raw_value = raw_value.lower() == 'true'
    return bool(raw_value), prefs

SYSTEM_SETTINGS_EXPORT_FORMAT = 'django-microsys.system-settings'
SYSTEM_SETTINGS_EXPORT_VERSION = 1

SYSTEM_SETTINGS_EXPORT_FIELDS = (
    'system_names',
    'logo',
    'favicon',
    'home_url',
    'default_language',
    'default_theme',
    'allowed_themes',
    'allow_user_theme_override',
    'allow_user_language_override',
    'default_table_density',
    'email_2fa',
    'client_ip_config',
    'public_root',
    'public_root_split_enabled',
    'public_root_url',
    'public_registration_enabled',
    'registration_activation_mode',
    'registration_throttle_enabled',
    'email_config',
    'languages',
    'translations_override',
    'sidebar_config',
    'titlebar_config',
)

# Extract filename from FieldFile or string
def _field_file_name(value):
    if isinstance(value, FieldFile):
        return value.name or ''
    return str(value or '')

# Coerce value to boolean for import settings
def _coerce_import_bool(value):
    if isinstance(value, str):
        return value.strip().lower() in {'1', 'true', 'yes', 'on'}
    return bool(value)


def export_system_settings_payload(instance=None):
    """Return a portable JSON payload for DB-backed setup settings."""
    if instance is None:
        SystemSettings = apps.get_model('microsys', 'SystemSettings')
        instance = SystemSettings.load()

    from microsys import __version__

    data = {}
    for field_name in SYSTEM_SETTINGS_EXPORT_FIELDS:
        value = getattr(instance, field_name, None)
        if field_name in {'logo', 'favicon'}:
            data[field_name] = _field_file_name(value)
        elif field_name == 'languages':
            data[field_name] = normalize_language_catalog(value)
        elif field_name == 'system_names':
            data[field_name] = normalize_system_names(value)
        elif field_name == 'sidebar_config':
            data[field_name] = normalize_sidebar_behavior(value)
        elif field_name == 'email_config':
            data[field_name] = normalize_email_config(value, redact_secret=True)
        elif field_name == 'client_ip_config':
            data[field_name] = normalize_client_ip_config(value)
        elif field_name == 'titlebar_config':
            data[field_name] = normalize_titlebar_config(value)
        elif field_name == 'allowed_themes':
            data[field_name] = list(normalize_allowed_themes(value))
        else:
            data[field_name] = deepcopy(value)

    return {
        'format': SYSTEM_SETTINGS_EXPORT_FORMAT,
        'version': SYSTEM_SETTINGS_EXPORT_VERSION,
        'microsys_version': __version__,
        'settings': data,
    }


def normalize_system_settings_import_payload(payload):
    """Validate and normalize an exported setup payload or a direct settings dict."""
    if not isinstance(payload, dict):
        raise ValueError("Setup import must be a JSON object.")

    raw_settings = payload.get('settings') if payload.get('format') == SYSTEM_SETTINGS_EXPORT_FORMAT else payload
    if not isinstance(raw_settings, dict):
        raise ValueError("Setup import is missing a valid settings object.")

    normalized = {}
    for field_name in SYSTEM_SETTINGS_EXPORT_FIELDS:
        if field_name in raw_settings:
            normalized[field_name] = deepcopy(raw_settings[field_name])

    if 'system_names' in normalized:
        normalized['system_names'] = normalize_system_names(normalized['system_names'])
    if 'languages' in normalized:
        normalized['languages'] = normalize_language_catalog(normalized['languages'])
    if 'translations_override' in normalized and not isinstance(normalized['translations_override'], dict):
        normalized['translations_override'] = {}
    if 'sidebar_config' in normalized:
        normalized['sidebar_config'] = normalize_sidebar_behavior(normalized['sidebar_config'])
    if 'email_config' in normalized:
        normalized['email_config'] = normalize_email_config(normalized['email_config'], redact_secret=True)
    if 'client_ip_config' in normalized:
        normalized['client_ip_config'] = normalize_client_ip_config(normalized['client_ip_config'])
    if 'titlebar_config' in normalized:
        normalized['titlebar_config'] = normalize_titlebar_config(normalized['titlebar_config'])
    if 'allowed_themes' in normalized:
        normalized['allowed_themes'] = list(normalize_allowed_themes(normalized['allowed_themes']))
    if 'default_theme' in normalized and not is_valid_theme(normalized['default_theme']):
        normalized.pop('default_theme', None)
    if 'default_table_density' in normalized and normalized['default_table_density'] not in TABLE_DENSITY_VALUES:
        normalized.pop('default_table_density', None)
    if 'default_language' in normalized:
        normalized['default_language'] = _normalize_language_code(normalized['default_language']) or 'en'
    if 'home_url' in normalized:
        normalized['home_url'] = str(normalized['home_url'] or '').strip()
    if 'public_root_url' in normalized:
        normalized['public_root_url'] = str(normalized['public_root_url'] or '').strip()
    if (
        'registration_activation_mode' in normalized
        and normalized['registration_activation_mode'] not in REGISTRATION_ACTIVATION_VALUES
    ):
        normalized.pop('registration_activation_mode', None)
    for bool_field in (
        'allow_user_theme_override',
        'allow_user_language_override',
        'email_2fa',
        'public_root',
        'public_root_split_enabled',
        'public_registration_enabled',
        'registration_throttle_enabled',
    ):
        if bool_field in normalized:
            normalized[bool_field] = _coerce_import_bool(normalized[bool_field])
    return normalized


def get_system_config():
    """
    Returns the deeply merged system configuration.
    1. Default config
    2. settings.MICROSYS_CONFIG (host project codebase)
    3. SystemSettings Singleton (database UI overrides)
    """
    # Default configuration
    default_config = {
        'system_names': {
            'en': 'microSYS',
            'ar': 'microSYS',
        },
        'verbose_name': 'microSYS',
        'logo': '/static/img/base_logo.webp',
        'login_logo': '/static/img/login_logo.webp',
        'favicon': '/static/favicon.ico',
        'home_url': DEFAULT_HOME_URL,
        'default_language': 'en',
        'default_theme': 'light',
        'allowed_themes': list(normalize_allowed_themes()),
        'allow_user_theme_override': True,
        'default_font': 'shabwa',
        'allowed_fonts': list(normalize_allowed_fonts()),
        'default_fonts': {},
        'allow_user_font_override': True,
        'allow_user_language_override': True,
        'default_table_density': DEFAULT_TABLE_DENSITY,
        'email_2fa': False,
        'client_ip': default_client_ip_config(),
        'public_root': False,
        'public_root_split_enabled': False,
        'public_root_url': '',
        'public_registration_enabled': False,
        'registration_activation_mode': REGISTRATION_ACTIVATION_AUTO_LOGIN,
        'registration_throttle_enabled': True,
        'email_config': default_email_config(),
        'languages': deepcopy(DEFAULT_LANGUAGE_CATALOG),
        'translations': {},
        'sidebar': default_sidebar_config(),
        'titlebar': default_titlebar_config(),
        'is_configured': False,
    }

    # Project settings
    user_config = getattr(settings, 'MICROSYS_CONFIG', {})
    if not isinstance(user_config, dict):
        user_config = {}
    
    # DB settings
    db_config = {}
    try:
        from microsys.models import SystemSettings
        sys_settings = SystemSettings.load()
        system_is_configured = bool(getattr(sys_settings, 'is_configured', False))

        def _should_apply_db_override(value, default):
            return system_is_configured or value != default

        if (
            isinstance(getattr(sys_settings, 'system_names', None), dict)
            and sys_settings.system_names
            and _should_apply_db_override(
                normalize_system_names(sys_settings.system_names),
                default_config['system_names'],
            )
        ):
            db_config['system_names'] = sys_settings.system_names
        if sys_settings.logo:
            db_config['logo'] = sys_settings.logo.url
            db_config['logo_url'] = sys_settings.logo.url
            db_config['login_logo_url'] = sys_settings.logo.url
        if sys_settings.favicon:
            db_config['favicon'] = sys_settings.favicon.url
            db_config['favicon_url'] = sys_settings.favicon.url
        legacy_unconfigured_home_url = (
            not system_is_configured and
            getattr(sys_settings, 'home_url', '') == LEGACY_HOME_URL
        )
        if (
            sys_settings.home_url
            and not legacy_unconfigured_home_url
            and _should_apply_db_override(sys_settings.home_url, default_config['home_url'])
        ):
            db_config['home_url'] = sys_settings.home_url
        if (
            getattr(sys_settings, 'default_language', None)
            and _should_apply_db_override(sys_settings.default_language, default_config['default_language'])
        ):
            db_config['default_language'] = sys_settings.default_language
        if (
            getattr(sys_settings, 'default_theme', None)
            and _should_apply_db_override(sys_settings.default_theme, default_config['default_theme'])
        ):
            db_config['default_theme'] = sys_settings.default_theme
        if (
            isinstance(getattr(sys_settings, 'allowed_themes', None), list)
            and sys_settings.allowed_themes
            and _should_apply_db_override(sys_settings.allowed_themes, default_config['allowed_themes'])
        ):
            db_config['allowed_themes'] = sys_settings.allowed_themes
        if (
            hasattr(sys_settings, 'allow_user_theme_override')
            and _should_apply_db_override(
                bool(sys_settings.allow_user_theme_override),
                default_config['allow_user_theme_override'],
            )
        ):
            db_config['allow_user_theme_override'] = bool(sys_settings.allow_user_theme_override)
        if (
            hasattr(sys_settings, 'allow_user_language_override')
            and _should_apply_db_override(
                bool(sys_settings.allow_user_language_override),
                default_config['allow_user_language_override'],
            )
        ):
            db_config['allow_user_language_override'] = bool(sys_settings.allow_user_language_override)
        if (
            getattr(sys_settings, 'default_table_density', None)
            and _should_apply_db_override(
                sys_settings.default_table_density,
                default_config['default_table_density'],
            )
        ):
            db_config['default_table_density'] = sys_settings.default_table_density
        if isinstance(sys_settings.languages, dict) and sys_settings.languages:
            db_config['languages'] = sys_settings.languages
        if isinstance(sys_settings.translations_override, dict) and sys_settings.translations_override:
            db_config['translations'] = sys_settings.translations_override
        if isinstance(getattr(sys_settings, 'sidebar_config', None), dict) and sys_settings.sidebar_config:
            db_config['sidebar'] = sys_settings.sidebar_config
        if isinstance(getattr(sys_settings, 'email_config', None), dict) and sys_settings.email_config:
            db_config['email_config'] = normalize_email_config(sys_settings.email_config)
        if (
            isinstance(getattr(sys_settings, 'titlebar_config', None), dict)
            and sys_settings.titlebar_config
            and (
                system_is_configured
                or sys_settings.titlebar_config != default_titlebar_config()
            )
        ):
            db_config['titlebar'] = sys_settings.titlebar_config
        if system_is_configured:
            db_config['is_configured'] = True
        if (
            hasattr(sys_settings, 'email_2fa')
            and _should_apply_db_override(bool(sys_settings.email_2fa), default_config['email_2fa'])
        ):
            db_config['email_2fa'] = bool(sys_settings.email_2fa)
        client_ip_config = normalize_client_ip_config(getattr(sys_settings, 'client_ip_config', {}))
        if _should_apply_db_override(client_ip_config, default_config['client_ip']):
            db_config['client_ip'] = client_ip_config
        if (
            hasattr(sys_settings, 'public_root')
            and _should_apply_db_override(bool(sys_settings.public_root), default_config['public_root'])
        ):
            db_config['public_root'] = bool(sys_settings.public_root)
        if (
            hasattr(sys_settings, 'public_root_split_enabled')
            and _should_apply_db_override(
                bool(sys_settings.public_root_split_enabled),
                default_config['public_root_split_enabled'],
            )
        ):
            db_config['public_root_split_enabled'] = bool(sys_settings.public_root_split_enabled)
        if (
            hasattr(sys_settings, 'public_root_url')
            and _should_apply_db_override(
                str(getattr(sys_settings, 'public_root_url', '') or '').strip(),
                default_config['public_root_url'],
            )
        ):
            db_config['public_root_url'] = str(sys_settings.public_root_url or '').strip()
        if (
            hasattr(sys_settings, 'public_registration_enabled')
            and _should_apply_db_override(
                bool(sys_settings.public_registration_enabled),
                default_config['public_registration_enabled'],
            )
        ):
            db_config['public_registration_enabled'] = bool(sys_settings.public_registration_enabled)
        if (
            hasattr(sys_settings, 'registration_activation_mode')
            and sys_settings.registration_activation_mode in REGISTRATION_ACTIVATION_VALUES
            and _should_apply_db_override(
                sys_settings.registration_activation_mode,
                default_config['registration_activation_mode'],
            )
        ):
            db_config['registration_activation_mode'] = sys_settings.registration_activation_mode
        if (
            hasattr(sys_settings, 'registration_throttle_enabled')
            and _should_apply_db_override(
                bool(sys_settings.registration_throttle_enabled),
                default_config['registration_throttle_enabled'],
            )
        ):
            db_config['registration_throttle_enabled'] = bool(sys_settings.registration_throttle_enabled)

        if (
            isinstance(getattr(sys_settings, 'allowed_fonts', None), (list, tuple, set))
            and _should_apply_db_override(
                normalize_allowed_fonts(sys_settings.allowed_fonts),
                default_config['allowed_fonts'],
            )
        ):
            db_config['allowed_fonts'] = normalize_allowed_fonts(sys_settings.allowed_fonts)

        if isinstance(getattr(sys_settings, 'default_fonts', None), dict) and sys_settings.default_fonts:
            db_config['default_fonts'] = sys_settings.default_fonts

        if _should_apply_db_override(
            bool(getattr(sys_settings, 'allow_user_font_override', True)),
            default_config['allow_user_font_override'],
        ):
            db_config['allow_user_font_override'] = bool(sys_settings.allow_user_font_override)
    except Exception:
        pass

    user_sidebar = user_config.get('sidebar', {})
    if not isinstance(user_sidebar, dict):
        user_sidebar = {}
    user_client_ip = user_config.get('client_ip', user_config.get('client_ip_config', {}))
    if not isinstance(user_client_ip, dict):
        user_client_ip = {}
    db_sidebar = db_config.get('sidebar', {})
    if not isinstance(db_sidebar, dict):
        db_sidebar = {}
    user_titlebar = user_config.get('titlebar', {})
    if not isinstance(user_titlebar, dict):
        user_titlebar = {}
    db_titlebar = db_config.get('titlebar', {})
    if not isinstance(db_titlebar, dict):
        db_titlebar = {}

    final_config = deepcopy(default_config)
    for layer in (user_config, db_config):
        for key, value in layer.items():
            if key in ['system_names', 'languages', 'translations', 'sidebar', 'titlebar']:
                continue
            final_config[key] = value

    final_config['system_names'] = normalize_system_names(
        {
            **normalize_system_names(default_config.get('system_names', {})),
            **normalize_system_names(user_config.get('system_names', {})),
            **normalize_system_names(db_config.get('system_names', {})),
        }
    )

    final_config['languages'] = normalize_language_catalog(
        default_config.get('languages', {}),
        user_config.get('languages', {}),
        db_config.get('languages', {}),
    )
    final_config['translations'] = _merge_translation_layers(
        default_config.get('translations', {}),
        user_config.get('translations', {}),
        db_config.get('translations', {}),
    )

    from .discovery import sanitize_sidebar_config

    merged_sidebar = deepcopy(default_config['sidebar'])
    for layer in (user_sidebar, db_sidebar):
        for key, value in layer.items():
            if key == 'entries':
                continue
            merged_sidebar[key] = value
    merged_sidebar['entries'] = _dedupe_sidebar_entries(
        list(db_sidebar.get('entries', [])) + list(user_sidebar.get('entries', []))
    )
    merged_sidebar = sanitize_sidebar_config(merged_sidebar, allow_system_items=True)
    final_config['sidebar'] = normalize_sidebar_behavior(merged_sidebar)
    merged_titlebar = deepcopy(default_config['titlebar'])
    for layer in (user_titlebar, db_titlebar):
        for key, value in layer.items():
            merged_titlebar[key] = value
    final_config['titlebar'] = normalize_titlebar_config(merged_titlebar)
    merged_client_ip = deepcopy(default_config['client_ip'])
    if isinstance(user_client_ip, dict):
        merged_client_ip.update(user_client_ip)
    if isinstance(db_config.get('client_ip', {}), dict):
        merged_client_ip.update(db_config.get('client_ip', {}))
    final_config['client_ip'] = normalize_client_ip_config(merged_client_ip)
    final_config['client_ip_config'] = deepcopy(final_config['client_ip'])

    final_config['allowed_themes'] = list(normalize_allowed_themes(final_config.get('allowed_themes')))
    if final_config.get('default_theme') not in set(final_config['allowed_themes']):
        final_config['default_theme'] = final_config['allowed_themes'][0]
    elif not is_valid_theme(final_config.get('default_theme')):
        final_config['default_theme'] = final_config['allowed_themes'][0]
    final_config['allow_user_theme_override'] = bool(final_config.get('allow_user_theme_override', True))
    final_config['allow_user_language_override'] = bool(final_config.get('allow_user_language_override', True))
    final_config['email_config'] = normalize_email_config(final_config.get('email_config', {}))
    if final_config.get('default_table_density') not in TABLE_DENSITY_VALUES:
        final_config['default_table_density'] = default_config['default_table_density']

    final_config['logo_url'] = _normalize_asset_url(
        final_config.get('logo_url') or final_config.get('logo') or default_config['logo']
    )
    final_config['login_logo_url'] = _normalize_asset_url(
        final_config.get('login_logo_url') or final_config.get('login_logo') or final_config['logo_url']
    )
    final_config['favicon_url'] = _normalize_asset_url(
        final_config.get('favicon_url') or final_config.get('favicon') or default_config['favicon']
    )

    final_config['home_url_name'] = None
    final_config['home_url'] = final_config.get('home_url') or default_config['home_url']
    final_config['public_root_split_enabled'] = bool(final_config.get('public_root_split_enabled', False))
    final_config['public_root_url'] = str(final_config.get('public_root_url') or '').strip()
    if final_config.get('default_language') not in final_config['languages']:
        final_config['default_language'] = 'en' if 'en' in final_config['languages'] else next(iter(final_config['languages']), 'en')

    final_config.update(build_config_groups(final_config, final_config.get('default_language')))

    return final_config

# Context Menu Helper — Filters context menu actions based on user permissions
def filter_context_actions(user, actions, manage_sections_perm=None):
    """
    Filter a list of context menu actions based on user permissions.
    Each action can have a 'permissions' key (list of strings) or 'permission' (string).
    If user lacks any required permission, the action is excluded.

    Args:
        user: The user to check permissions for
        actions: List of action dicts, each may contain 'permissions' or 'permission'
        manage_sections_perm: Optional permission string (e.g., 'microsys.manage_sections')
                             that grants full access to all section-related actions.
                             Defaults to checking 'microsys.manage_sections' if None.
    """
    if not user or not user.is_authenticated:
        return []

    # Determine the manage_sections permission to check
    if manage_sections_perm is None:
        manage_sections_perm = 'microsys.manage_sections'

    # Check if user has manage_sections permission (grants full section access)
    has_manage_sections = user.has_perm(manage_sections_perm)

    filtered = []
    for action in actions:
        # Check permissions
        required_perms = action.get('permissions', [])
        if not required_perms and 'permission' in action:
            required_perms = [action['permission']]

        if required_perms:
            if user.is_superuser:
                # Superuser sees all
                pass
            elif has_manage_sections:
                # Users with manage_sections should see all section-related actions
                pass
            elif not user.has_perms(required_perms):
                continue

        filtered.append(action)

    return filtered

# Model Introspection — Returns possible import base paths for a model's app
def _get_model_app_bases(model):
    """
    Return possible import bases for a model's app.
    Uses AppConfig.name (full python path) and falls back to module/app_label.
    """
    bases = []
    try:
        app_config = apps.get_app_config(model._meta.app_label)
        if app_config and app_config.name:
            bases.append(app_config.name)
    except LookupError:
        pass

    module_base = model.__module__.rsplit('.', 1)[0]
    if module_base not in bases:
        bases.append(module_base)

    if model._meta.app_label not in bases:
        bases.append(model._meta.app_label)

    return bases

# Model Resolution — Convention-based class importer (App.<submodule>.Model<Suffix>)
def _import_by_convention(model, submodule, class_suffix):
    """
    Try importing a class following App.<submodule>.ModelName<class_suffix>.
    Returns class or None if not found.
    """
    class_name = f"{model.__name__}{class_suffix}"
    for base in _get_model_app_bases(model):
        try:
            return import_string(f"{base}.{submodule}.{class_name}")
        except ImportError:
            continue
    return None

# Model Resolution — Resolves a class from a model method/attr (class or string path)
def _resolve_model_class(model, getter_name):
    """
    Resolve class from model method/attr that may return a class or a string path.
    """
    if not hasattr(model, getter_name):
        return None

    try:
        value = getattr(model, getter_name)
        value = value() if callable(value) else value
    except Exception:
        return None

    if isinstance(value, str):
        try:
            return import_string(value)
        except (ImportError, ValueError, AttributeError, TypeError):
            return None

    if inspect.isclass(value):
        return value

    return None

# System Variables for Model Classes Caching
_MODEL_CLASSES_CACHE = {}

class LazyModelClasses(dict):
    """
    Lazy dictionary that only resolves model classes (form, table, filter)
    when they are explicitly requested, and caches them for subsequent accesses.
    """
    def __init__(self, model, overrides=None):
        self._model = model
        
        # Merge model-level registry/overrides with explicit overrides
        model_overrides = getattr(model, 'model_classes_overrides', {})
        self._overrides = {**model_overrides, **(overrides or {})}
        
        super().__init__({
            'model': model,
            'verbose_name': model._meta.verbose_name,
            'verbose_name_plural': model._meta.verbose_name_plural,
        })

    @staticmethod
    def _normalize_key(key):
        aliases = {
            'form_class': 'form',
            'table_class': 'table',
            'filter_class': 'filter',
        }
        return aliases.get(key, key)
        
    def __getitem__(self, key):
        key = self._normalize_key(key)
        if super().__contains__(key):
            return super().__getitem__(key)
            
        if key == 'form':
            val = self._resolve_form()
        elif key == 'table':
            val = self._resolve_table()
        elif key == 'filter':
            val = self._resolve_filter()
        else:
            raise KeyError(key)
            
        self[key] = val
        return val

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key):
        key = self._normalize_key(key)
        if super().__contains__(key):
            return True
        return key in ('form', 'table', 'filter')

    def _get_override_or_none(self, key):
        if key in self._overrides:
            val = self._overrides[key]
            if isinstance(val, str):
                try:
                    return import_string(val)
                except Exception:
                    pass
            return val
        return None

    def _resolve_form(self):
        override = self._get_override_or_none('form')
        if override: return override
        
        form_class = _import_by_convention(self._model, "forms", "Form")
        if not form_class:
            form_class = resolve_form_class_for_model(self._model)
        return form_class
        
    def _resolve_table(self):
        override = self._get_override_or_none('table')
        if override: return override
        
        table_class = _import_by_convention(self._model, "tables", "Table")
        if not table_class:
             table_class = _resolve_model_class(self._model, "get_table_class")
        if not table_class:
             table_class = _build_generic_table_class(self._model)
        return table_class
        
    def _resolve_filter(self):
        override = self._get_override_or_none('filter')
        if override: return override
        
        filter_class = _import_by_convention(self._model, "filters", "Filter")
        if not filter_class:
             filter_class = _resolve_model_class(self._model, "get_filter_class")
        if not filter_class and django_filters:
             filter_class = _build_generic_filter_class(self._model)
        return filter_class

# Model Resolution — Dynamically imports model, form, table, and filter classes by name
def get_model_classes(model_name, app_label=None, overrides=None):
    """
    Dynamically import model, form, table, and filter classes for a given model
    following standard naming conventions. Uses lazy loading and caching.
    """
    if not model_name:
        return None
        
    cache_key = f"{app_label or 'any'}:{model_name}"
    
    # Check cache first if no explicit request-level overrides are provided
    if not overrides and cache_key in _MODEL_CLASSES_CACHE:
        return _MODEL_CLASSES_CACHE[cache_key]
    
    # Resolve Model
    model = resolve_model_by_name(model_name, app_label=app_label)
    if not model:
        # Try to resolve by model_name directly if it might be a full path
        if '.' in model_name:
            try:
                model = apps.get_model(model_name)
            except:
                return None
        else:
            return None
            
    lazy_classes = LazyModelClasses(model, overrides=overrides)
    
    if not overrides:
        _MODEL_CLASSES_CACHE[cache_key] = lazy_classes
        
    return lazy_classes


def get_user_linked_models():
    """
    Finds all models across the Django project that have a OneToOneField 
    pointing to settings.AUTH_USER_MODEL, excluding microsys.Profile.
    Returns: list of dicts with model identifiers.
    """
    from django.contrib.auth import get_user_model
    linked_models = []
    
    User = get_user_model()
    for model in apps.get_models():
        # Exclude the internal microsys profile since it's already auto-created
        if model._meta.app_label == 'microsys' and model.__name__ == 'Profile':
            continue
        if getattr(model, 'microsys_auto_create_user_profile', True) is False:
            continue
            
        for field in model._meta.get_fields():
            if field.is_relation and field.one_to_one:
                if field.related_model == User:
                    linked_models.append({
                        'app_label': model._meta.app_label,
                        'model_name': model.__name__,
                        'verbose_name': model._meta.verbose_name,
                        'field_name': field.name,
                    })
    return linked_models

# Model Resolution — Dynamically Resolves a Model by Name
def resolve_model_by_name(model_name, app_label=None):
    """
    Resolve a model by name, optionally constrained to an app label.
    Falls back to fuzzy matching against cached registry if app_label is not provided.
    """
    if not model_name:
        return None

    if not isinstance(model_name, str):
        return model_name

    if app_label:
        try:
            return apps.get_model(app_label, model_name)
        except LookupError:
            return None

    # First, try standard Django app registry if it looks like app_label.model
    if '.' in model_name:
        try:
            return apps.get_model(model_name)
        except (LookupError, ValueError):
            pass

    # Fallback to fuzzy matching against cached registry
    norm_name = _normalize_fuzzy_string(model_name)
    return _get_fuzzy_model_mapping().get(norm_name)

# Model Resolution — Dynamically imports and returns a class from a dotted string path
def get_class_from_string(class_path):
    """Dynamically imports and returns a class from a string path."""
    return import_string(class_path)

# Section Detection — Checks if a model is marked as a section model
def _model_is_section(model):
    """
    Determine if a model should be treated as a section model.
    Accepts class attr, Meta attr, or any non-falsey marker.
    """
    val = getattr(model, 'is_section', None)
    if isinstance(val, bool):
        return val
    if val is not None:
        return True
    return bool(getattr(model._meta, 'is_section', False))

# Form Resolution — Resolves or generates a ModelForm class for any model
def resolve_form_class_for_model(model):
    """
    Resolve a ModelForm class for a model using conventions or fallbacks.
    """
    form_class = _import_by_convention(model, "forms", "Form")
    if not form_class:
        form_class = (
            _resolve_model_class(model, "get_form_class")
            or _resolve_model_class(model, "get_form_class_path")
        )

    # Prepare widgets with autofill attributes for ForeignKeys (Global)
    widgets = {}
    for field in model._meta.get_fields():
        if field.is_relation and (field.many_to_one or field.one_to_one) and field.related_model:
            # Provide the "app_label.model_name" as source
            source = f"{field.related_model._meta.app_label}.{field.related_model._meta.model_name}"
            from django.forms import Select
            widgets[field.name] = Select(attrs={'data-autofill-source': source})

    try:
        has_scope_field = model._meta.get_field("scope") is not None
    except Exception:
        has_scope_field = False

    if form_class:
        # Wrap custom form to inject widgets
        # We explicitly pass fields=None to let it infer from the base form
        try:
            form_class = modelform_factory(model, form=form_class, widgets=widgets)
        except Exception:
            # Fallback for edge cases (e.g. already processed or incompatible)
            pass
    else:
        # Generate generic form
        raw_exclude = getattr(model, "form_exclude", None)
        if raw_exclude is None:
            raw_exclude = []
        elif isinstance(raw_exclude, (str, bytes)):
            raw_exclude = [raw_exclude]
        else:
            raw_exclude = list(raw_exclude)

        # Default exclusions for audit fields
        audit_fields = ['created_at', 'updated_at', 'deleted_at', 'created_by', 'updated_by', 'deleted_by']
        raw_exclude.extend([f for f in audit_fields if f not in raw_exclude])

        if raw_exclude:
            exclude = list(dict.fromkeys(raw_exclude))
            form_class = modelform_factory(model, exclude=exclude, widgets=widgets)
        else:
            form_class = modelform_factory(model, fields='__all__', widgets=widgets)

    if has_scope_field:
        class ScopeDynamicForm(form_class):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                if 'scope' in self.fields and not is_scope_enabled():
                    del self.fields['scope']
        form_class = ScopeDynamicForm

    return form_class

# Related Objects Inspector — Introspects all related objects for Smart Delete/View
def collect_related_objects(instance):
    """
    Introspects a model instance to find all related objects (Reverse FK, M2M).
    Returns a dictionary: { 'Verbose Name Plural': ['Item 1', 'Item 2'] }
    Used for Smart Delete functionality and Smart View.
    """
    related_data = {}
    
    # Identify M2M through models to skip their reverse relationships
    through_models = set()
    for f in instance._meta.get_fields():
        if getattr(f, 'many_to_many', False):
            try:
                through = getattr(f, 'through', getattr(getattr(f, 'remote_field', None), 'through', None))
                if through:
                    through_models.add(through)
            except AttributeError:
                pass

    # Iterate over all fields to find relations
    for field in instance._meta.get_fields():
        if getattr(field, 'related_model', None) in through_models:
            continue

        if field.auto_created and not field.concrete:
            # Reverse Relations (OneToMany, OneToOne)
            # e.g. department.affiliate_set
            try:
                accessor = field.get_accessor_name()
                if not accessor: continue
                
                related_msg = getattr(instance, accessor, None)
                if related_msg:
                    # Check if it's a Manager (OneToMany/ManyToMany) or single object (OneToOne)
                    if hasattr(related_msg, 'all'):
                        # Limit to reasonable amount
                        qs = related_msg.all()[:20] 
                        if qs:
                            items = [str(obj) for obj in qs]
                            name = str(field.related_model._meta.verbose_name_plural)
                            if name not in related_data:
                                related_data[name] = items
                    else:
                        # OneToOne
                        name = str(field.related_model._meta.verbose_name)
                        if name not in related_data:
                            related_data[name] = [str(related_msg)]
            except Exception:
                pass
                
        elif hasattr(field, 'many_to_many') and field.many_to_many:
            # Forward M2M
            try:
                manager = getattr(instance, field.name, None)
                if manager:
                    qs = manager.all()[:20]
                    if qs:
                        items = [str(obj) for obj in qs]
                        name = str(field.related_model._meta.verbose_name_plural)
                        if name not in related_data:
                            related_data[name] = items
            except Exception:
                pass
                
    return related_data

# Generate detail context from model instance
def _build_generic_detail_context(instance, request=None):
    """
    Dynamically generates a list of {'label': ..., 'value': ...} dictionaries 
    from a model instance for zero-boilerplate detail views.
    Respects translations and the 'is_scope_enabled' global setting.
    """
    from microsys.utils import is_scope_enabled

    s = get_strings(get_current_language_code(request))

    fields_data = []
    
    # Audit fields and passwords shouldn't generally be shown in generic detail views
    exclude_fields = ['password', 'created_at', 'updated_at', 'deleted_at', 'created_by', 'updated_by', 'deleted_by']
    
    if not is_scope_enabled():
        exclude_fields.append('scope')

    for field in instance._meta.get_fields():
        if field.name in exclude_fields:
            continue
            
        # Ignore reverse relations to keep it clean, only show direct fields and M2M
        if field.auto_created and not field.concrete and not field.many_to_many:
            continue

        try:
            value = getattr(instance, field.name, None)
            
            # Formatting
            if isinstance(field, ManyToManyField):
                if value is not None:
                    # evaluate M2M manager
                    qs = value.all()
                    value = ", ".join(str(item) for item in qs)
                    if not value:
                        value = "-"
            elif isinstance(value,FieldFile):
                if value and value.name:
                    value = f'<a href="{value.url}" target="_blank" class="btn btn-sm btn-outline-primary"><i class="bi bi-download"></i> {s.get("btn_download", "تحميل")}</a>'
                else:
                    value = "-"
            elif isinstance(value, bool):
                value = f'<i class="bi bi-check-circle-fill text-success"></i>' if value else f'<i class="bi bi-x-circle text-danger"></i>'
            elif value is None or value == "":
                value = "-"
            elif hasattr(field, 'choices') and field.choices:
                # get display value for choices
                display_func = getattr(instance, f"get_{field.name}_display", None)
                if display_func:
                    value = display_func()
            
            label = resolve_detail_field_label(instance, field, request=request, strings=s)
            
            fields_data.append({
                'label': str(label).capitalize(),
                'value': value,
                'is_html': isinstance(value, str) and ('<a' in value or '<i' in value)
            })
        except Exception:
            pass

    return fields_data

# Resolve translated display label for detail views
def resolve_detail_field_label(instance, field, request=None, strings=None):
    """Resolve a translated display label for generic detail views."""
    s = strings or get_strings(get_current_language_code(request))
    raw_label = str(getattr(field, 'verbose_name', '') or getattr(field, 'name', '')).strip()
    field_name = str(getattr(field, 'name', '') or '').strip()
    model_name = ''

    try:
        model_name = instance._meta.model_name
    except Exception:
        try:
            model_name = instance.__class__.__name__.lower()
        except Exception:
            model_name = ''

    keys = []
    if model_name and field_name:
        keys.append(f"label_{model_name}_{field_name}")
    if field_name:
        keys.extend([f"label_{field_name}", field_name])
    if raw_label:
        keys.extend([f"label_{raw_label}", raw_label])

    for key in keys:
        translated = s.get(key)
        if translated:
            return translated

    return raw_label or field_name

# Dynamic Table Builder — Generates a django-tables2 Table class at runtime
def _build_generic_table_class(model):
    """
    Build a minimal django-tables2 Table for a model.
    Build Meta dynamically so django-tables2 sees Meta.model at class creation.
    Generated tables inherit the full Microsys table platform by default.
    """
    from microsys.tables import MicrosysTable
    
    raw_exclude = getattr(model, "table_exclude", None)
    if raw_exclude is None:
        raw_exclude = []
    elif isinstance(raw_exclude, (str, bytes)):
        raw_exclude = [raw_exclude]
    else:
        raw_exclude = list(raw_exclude)

    # Default exclusions for audit fields
    audit_fields = ['created_at', 'updated_at', 'deleted_at', 'created_by', 'updated_by', 'deleted_by']
    raw_exclude.extend([f for f in audit_fields if f not in raw_exclude])

    try:
        has_scope_field = model._meta.get_field("scope") is not None
    except Exception:
        has_scope_field = False

    meta_attrs = {
        "model": model,
        "row_attrs": {
            'class': 'section-row',
            'data-pk': lambda record: record.pk,
            'data-name': lambda record: str(record),
            'data-micro-context': 'true',
        },
    }
    if raw_exclude:
        meta_attrs["exclude"] = list(dict.fromkeys(raw_exclude))
    Meta = type("Meta", (), meta_attrs)
    table_attrs = {"Meta": Meta}
    return type(f"{model.__name__}AutoTable", (MicrosysTable,), table_attrs)

# Dynamic Filter Builder — Generates a django-filters FilterSet class at runtime
def _build_generic_filter_class(model):
    """
    Build a minimal django-filters FilterSet:
    - keyword search across text fields (and numeric fields if value is numeric)
    - optional year dropdown if any date/datetime field exists
    """
    if not django_filters:
        return None

    text_fields = []
    int_fields = []
    num_fields = []
    date_field = None

    for field in model._meta.get_fields():
        if not hasattr(field, 'attname'):
            continue
        if field.many_to_many or field.one_to_many:
            continue

        if isinstance(field, (dj_models.CharField, dj_models.TextField, dj_models.EmailField, dj_models.SlugField, dj_models.URLField)):
            text_fields.append(field.name)
        elif isinstance(field, (dj_models.IntegerField, dj_models.BigIntegerField, dj_models.SmallIntegerField, dj_models.PositiveIntegerField, dj_models.PositiveSmallIntegerField)):
            int_fields.append(field.name)
        elif isinstance(field, (dj_models.FloatField, dj_models.DecimalField)):
            num_fields.append(field.name)
        elif date_field is None and isinstance(field, (dj_models.DateField, dj_models.DateTimeField)):
            date_field = field.name

    # Filter Helper — Parses string value to Decimal for numeric filtering
    def _parse_number(value):
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None

    # Filter Init — Initializes filter with translated labels and year choices
    def _init(self, *args, **kwargs):
        super(self.__class__, self).__init__(*args, **kwargs)
        s = get_strings()

        if date_field and 'year' in self.filters:
            year_label = s.get('filter_year', 'السنة')
            self.filters['year'].label = year_label
            self.filters['year'].extra['empty_label'] = year_label
            years = self.Meta.model.objects.dates(date_field, 'year').distinct()
            self.filters['year'].extra['choices'] = [(year.year, year.year) for year in years]
            self.filters['year'].field.widget.attrs.update({
                'class': 'auto-submit-filter'
            })
            set_first_choice(self.filters['year'].field, year_label)

        if not hasattr(self.form, 'helper') or self.form.helper is None:
            # Layout handled by setup_filter_helper in the view
            pass

    # Filter Method — Performs keyword search across text and numeric fields
    def _filter_keyword(self, queryset, name, value, text_fields=text_fields, int_fields=int_fields, num_fields=num_fields):
        if not value:
            return queryset

        q_obj = Q()
        for field_name in text_fields:
            q_obj |= Q(**{f"{field_name}__icontains": value})

        numeric_value = _parse_number(value)
        if numeric_value is not None:
            is_int = numeric_value == numeric_value.to_integral_value()
            if is_int:
                int_value = int(numeric_value)
                for field_name in int_fields:
                    q_obj |= Q(**{field_name: int_value})
            for field_name in num_fields:
                q_obj |= Q(**{field_name: numeric_value})

        return queryset.filter(q_obj) if q_obj else queryset

    meta_attrs = {"model": model, "fields": []}
    Meta = type("Meta", (), meta_attrs)

    attrs = {
        "Meta": Meta,
        "__init__": _init,
        "filter_keyword": _filter_keyword,
        "keyword": django_filters.CharFilter(method='filter_keyword', label=''),
    }
    if date_field:
        from django import forms as dj_forms
        attrs["date_gte"] = django_filters.DateFilter(
            field_name=date_field,
            lookup_expr="gte",
            label='',
            widget=dj_forms.DateInput(attrs={'class': 'form-control ms-datepicker', 'placeholder': 'من تاريخ', 'autocomplete': 'off'}),
        )
        attrs["date_lte"] = django_filters.DateFilter(
            field_name=date_field,
            lookup_expr="lte",
            label='',
            widget=dj_forms.DateInput(attrs={'class': 'form-control ms-datepicker', 'placeholder': 'إلى تاريخ', 'autocomplete': 'off'}),
        )
        attrs["year"] = django_filters.ChoiceFilter(
            field_name=f"{date_field}__year",
            lookup_expr="exact",
            choices=[],
            empty_label="السنة",
        )

    # Apply same default exclusions to filters to avoid clutter
    audit_fields = ['created_at', 'updated_at', 'deleted_at', 'created_by', 'updated_by', 'deleted_by']
    meta_attrs["exclude"] = audit_fields

    return type(f"{model.__name__}AutoFilter", (django_filters.FilterSet,), attrs)

# Section Detection — Identifies child/subsection models (M2M targets)
def _is_child_model(model, app_name=None):
    """
    Detect if a model is a "child model" - one that exists primarily 
    to be linked via M2M to a parent model.
    
    A model is considered a child if:
    - It has a ManyToManyRel (is the target of a M2M from another model)
    - It doesn't have its own table classmethod (won't be displayed standalone)
    """
    meta = model._meta
    
    # Check if this model is referenced via M2M from another model
    has_m2m_rel = any(
        isinstance(f, ManyToManyRel) 
        for f in meta.get_fields()
    )
    
    # Check if model lacks table classmethod (not meant for standalone display)
    lacks_table = not hasattr(model, 'get_table_class_path') and not hasattr(model, 'get_table_class')
    
    return has_m2m_rel and lacks_table

# Section Discovery — Scans apps for section models and resolves their Form/Table/Filter classes
def discover_section_models(app_name=None, include_children=False):
    """
    Discover section models based on explicit `is_section = True` in class/meta.
    Automatically resolves Form, Table, and Filter classes (by convention or generation).
    Identifies 'subsection' models (M2M children) for automatic modal handling.
    
    Args:
        app_name: Optional. If provided, filter results to this app only.
        include_children: If True, includes child models (M2M targets) even if not
                          explicitly marked as sections. Default False.
    
    Returns:
        List of dicts containing section model info:
        {
            'model': Model class,
            'model_name': Model name (lowercase),
            'app_label': App label,
            'verbose_name': Arabic verbose name,
            'verbose_name_plural': Arabic verbose name plural,
            'form_class': Form class (imported or generated),
            'table_class': Table class (imported or generated),
            'filter_class': Filter class (imported or generated),
            'subsections': List of dicts for child models (M2M targets):
                {
                    'model': ChildModel,
                    'model_name': ...,
                    'verbose_name': ...,
                    'related_field': field_name (in parent),
                    'form_class': ChildFormClass (imported or generated)
                }
        }
    """
    section_models = []
    
    # Get app configs to iterate
    if app_name:
        try:
            app_configs = [apps.get_app_config(app_name)]
        except LookupError:
            return []
    else:
        app_configs = apps.get_app_configs()
    
    for app_config in app_configs:
        # Skip Django's built-in apps
        if app_config.name.startswith('django.'):
            continue
        
        for model in app_config.get_models():
            meta = model._meta
            
            # SKIP: Dummy models (managed = False)
            if not meta.managed:
                continue
            
            # SKIP: Abstract models
            if meta.abstract:
                continue
            
            # Detect if this is a child model (M2M target without table)
            is_child = _is_child_model(model, app_config.label)

            # Include models explicitly marked as sections, plus children if requested
            is_section = _model_is_section(model)
            if not is_section and not (include_children and is_child):
                continue
            
            # --- Resolve Classes (Form, Table, Filter) ---
            # 1. Form
            form_class = resolve_form_class_for_model(model)

            # 2. Table
            table_class = _import_by_convention(model, "tables", "Table")
            if not table_class:
                # Fallback: legacy methods
                table_class = (
                    _resolve_model_class(model, "get_table_class")
                    or _resolve_model_class(model, "get_table_class_path")
                )
            
            # Generate if not found
            if not table_class:
                 table_class = _build_generic_table_class(model)

            # 3. Filter
            filter_class = _import_by_convention(model, "filters", "Filter")
            if not filter_class:
                # Fallback
                filter_class = (
                    _resolve_model_class(model, "get_filter_class")
                    or _resolve_model_class(model, "get_filter_class_path")
                )
            
            # Generate if not found (optional, requires django_filters)
            if not filter_class and django_filters:
                 filter_class = _build_generic_filter_class(model)

            # --- Identify Subsections (M2M Children) ---
            subsections = []
            for field in meta.get_fields():
                if isinstance(field, ManyToManyField):
                    child_model = field.related_model
                    child_meta = child_model._meta
                    
                    # Verify it's a "subsection/child" type model
                    if _is_child_model(child_model):
                         # Resolve child form for the "Add" modal
                         child_form_class = resolve_form_class_for_model(child_model)
                             
                         subsections.append({
                             'model': child_model,
                             'model_name': child_meta.model_name,
                             'verbose_name': child_meta.verbose_name,
                             'verbose_name_plural': child_meta.verbose_name_plural,
                             'related_field': field.name,
                             'form_class': child_form_class
                         })

            section_models.append({
                'model': model,
                'model_name': meta.model_name,
                'app_label': meta.app_label,
                'verbose_name': meta.verbose_name,
                'verbose_name_plural': meta.verbose_name_plural,
                'form_class': form_class,
                'table_class': table_class,
                'filter_class': filter_class,
                'subsections': subsections,
                'is_child': is_child,
            })
    
    return section_models


@lru_cache(maxsize=None)
def has_section_models(app_name=None):
    """
    Return True when at least one model is explicitly marked as a section model.
    """
    if app_name:
        try:
            app_configs = [apps.get_app_config(app_name)]
        except LookupError:
            return False
    else:
        app_configs = apps.get_app_configs()

    for app_config in app_configs:
        if app_config.name.startswith('django.'):
            continue

        for model in app_config.get_models():
            meta = model._meta
            if not meta.managed or meta.abstract:
                continue
            if _model_is_section(model):
                return True

    return False

# Section Discovery — Returns the first section model name for default tab selection
def get_default_section_model(app_name=None):
    """
    Get the first available section model name for auto-selection.
    
    Returns:
        String model_name of the first section model, or None if none found.
    """
    section_models = discover_section_models(app_name=app_name)
    if section_models:
        return section_models[0]['model_name']
    return None

# Section Management - M2M Helper — Provides through_defaults for scoped M2M relations
def _get_m2m_through_defaults(model, field_name, request):
    """
    Provide through_defaults for M2M relations when the through model is scoped.
    This prevents relations from disappearing when scope filtering is enabled.
    """
    try:
        field = model._meta.get_field(field_name)
    except FieldDoesNotExist:
        return None

    # Only M2M fields can have through tables
    if not getattr(field, "many_to_many", False):
        return None

    through = field.remote_field.through
    if not through:
        return None

    defaults = {}
    if is_scope_enabled():
        scope = get_user_scope(request.user)
        if scope:
            try:
                through._meta.get_field('scope')
                defaults['scope'] = scope
            except Exception:
                pass

    return defaults or None

# Section Management - Record Creation Helper — Creates a minimal model instance from raw POST data
def _create_minimal_instance_from_post(model, data, request):
    """
    Fallback: create a minimal instance from POST data when a simple
    inline add is used (e.g., just a `name` field).
    Only proceeds if all required concrete fields are present.
    """
    field_map = {}
    missing_required = []

    # Identify truly required fields (skip auto-managed and optional ones)
    for field in model._meta.fields:
        if field.primary_key or field.auto_created:
            continue
        if getattr(field, "auto_now", False) or getattr(field, "auto_now_add", False):
            continue
        if field.has_default() or field.blank or field.null:
            continue

        if field.name not in data:
            missing_required.append(field.name)

    if missing_required:
        return None, missing_required

    for field in model._meta.fields:
        if field.primary_key or field.auto_created:
            continue
        if field.name in data:
            if isinstance(field, dj_models.ForeignKey):
                try:
                    field_map[field.name] = field.remote_field.model.objects.get(pk=data[field.name])
                except Exception:
                    return None, [field.name]
            else:
                field_map[field.name] = data[field.name]

    instance = model(**field_map)
    # created_by auto-populated by ScopedModel.save()
    # Ensure scope is set for scoped models
    if is_scope_enabled() and hasattr(instance, 'scope'):
        try:
            user_scope = getattr(getattr(request.user, 'profile', None), 'scope', None)
            if not user_scope and hasattr(request.user, 'scope'):
                user_scope = request.user.scope
            # Non-superusers always get their scope forced; superusers only if unset
            if user_scope:
                if not request.user.is_superuser:
                    instance.scope = user_scope
                elif not getattr(instance, 'scope', None):
                    instance.scope = user_scope
        except Exception:
            pass
    instance.save()
    return instance, []

# Scope Management — Checks if the multi-tenant Scope system is globally enabled
def is_scope_enabled():
    """
    Checks if the Scope system is globally enabled.
    Returns:
        bool: True if enabled, False otherwise.
    """
    from django.db.utils import ProgrammingError, OperationalError
    try:
        ScopeSettings = apps.get_model('microsys', 'ScopeSettings')
        return ScopeSettings.load().is_enabled
    except (LookupError, ProgrammingError, OperationalError):
        # Fallback if model or table isn't ready (e.g., during migrations or empty DB)
        return False

# Deletion Safety — Checks if an instance has related records (lock/protect logic)
def has_related_records(instance, ignore_relations=None):
    """
    Check if a model instance has any related records (FK, M2M, OneToOne).
    Returns True if any related objects exist, False otherwise.
    Used for locking logic (preventing deletion/unlinking).
    
    ignore_relations: list of accessor names to skip (e.g. ['affiliates', 'company_set'])
    
    Note: Automatically ignores M2M relations where this model is the 'child' 
    (i.e., the target of a ManyToManyField from a parent section model).
    This includes the M2M reverse accessor AND any FK from through tables
    (both auto-created and custom through models like AffiliateDepartment).
    """
    from django.db.models.fields.related import ManyToManyRel, ManyToOneRel
    
    if not instance:
        return False
    
    if ignore_relations is None:
        ignore_relations = []
    
    # Auto-detect M2M parent relations to ignore
    # Step 1: Collect all through-table models from M2M relationships pointing at us
    auto_ignore = set()
    through_models = set()
    
    for field in instance._meta.get_fields():
        if isinstance(field, ManyToManyRel):
            # This is the "reverse" side of a M2M - the parent points to us
            accessor_name = field.get_accessor_name()
            if accessor_name:
                auto_ignore.add(accessor_name)
            # Track through table (works for both auto-created and custom)
            if hasattr(field, 'through') and field.through:
                through_models.add(field.through)
    
    # Step 2: Any ManyToOneRel whose source model is a known through table
    # should also be ignored (the FK from the through table to this model)
    for field in instance._meta.get_fields():
        if isinstance(field, ManyToOneRel):
            if field.related_model in through_models:
                accessor_name = field.get_accessor_name()
                if accessor_name:
                    auto_ignore.add(accessor_name)
    
    for related_object in instance._meta.get_fields():
        if related_object.is_relation and related_object.auto_created:
            # Reverse relationship (Someone points to us)
            accessor_name = related_object.get_accessor_name()
            if not accessor_name:
                continue
            if accessor_name in ignore_relations or accessor_name in auto_ignore:
                continue
                
            try:
                # Get the related manager/descriptor
                related_item = getattr(instance, accessor_name)
                
                # Check based on relationship type
                if related_object.one_to_many or related_object.many_to_many:
                     if related_item.exists():
                         return True
                elif related_object.one_to_one:
                     # OneToOne
                     pass 
            except Exception:
                # DoesNotExist or other issues
                continue
            
            # For O2O
            if related_object.one_to_one and related_item:
                return True
                
    return False

# Sidebar State Manager — Handles sidebar collapse toggle and persists state to session/profile
def toggle_sidebar(request):
    if request.method == "POST" and request.user.is_authenticated:
        collapsed = request.POST.get("collapsed") == "true"
        
        # 1. Update Session
        request.session["sidebarCollapsed"] = collapsed
        
        # 2. Update Profile Preferences if profile exists
        if hasattr(request.user, 'profile'):
            profile = request.user.profile
            if not profile.preferences:
                profile.preferences = {}
            
            # Ensure it's a dict
            if isinstance(profile.preferences, str):
                import json
                try:
                    profile.preferences = json.loads(profile.preferences)
                except:
                    profile.preferences = {}
            
            # Use a copy to ensure Django detects changes
            prefs = dict(profile.preferences)
            prefs['sidebar_collapsed'] = collapsed
            profile.preferences = prefs
            profile.save(update_fields=['preferences'])

        return JsonResponse({"status": "success"})
    return JsonResponse({"status": "error"}, status=400)

# Form Helper — Applies shared field classes, direction, and optional inline labels
def set_field_attrs(form, request=None, inline_labels=False):
    """Set common attributes for all fields in the form."""
    from microsys.translations import get_current_language_code

    lang = get_current_language_code(request)
    ms_trans = get_strings(lang)
    
    # Detect language for direction
    direction = 'rtl' if lang.startswith('ar') else 'ltr'
    
    for field_name in form.fields:
        field = form.fields.get(field_name)
        # Try to get label from MS_TRANS (model-specific first, then generic)
        model_name = ""
        if hasattr(form, '_meta') and hasattr(form._meta, 'model'):
             model_name = form._meta.model.__name__.lower()
        
        label_key_model = f"label_{model_name}_{field_name}" if model_name else None
        label_key_generic = f"label_{field_name}"
        
        label = ms_trans.get(label_key_model) if label_key_model else None
        if not label:
            label = ms_trans.get(label_key_generic)
        
        if not label:
            # Handle auto-generated filter suffixes (gte/lte) for cleaner Arabic translation
            clean_name = field_name
            suffix = ""
            range_type = None
            if "__gte" in field_name:
                clean_name = field_name.replace("__gte", "")
                suffix = f" ({ms_trans.get('filter_from', 'From')})"
                range_type = "from"
            elif "__lte" in field_name:
                clean_name = field_name.replace("__lte", "")
                suffix = f" ({ms_trans.get('filter_to', 'To')})"
                range_type = "to"
            elif field_name.endswith("_gte"):
                clean_name = field_name[:-4]
                suffix = f" ({ms_trans.get('filter_from', 'From')})"
                range_type = "from"
            elif field_name.endswith("_lte"):
                clean_name = field_name[:-4]
                suffix = f" ({ms_trans.get('filter_to', 'To')})"
                range_type = "to"

            if clean_name == "date" and range_type == "from":
                label = ms_trans.get('filter_date_from')
            elif clean_name == "date" and range_type == "to":
                label = ms_trans.get('filter_date_to')
            
            if not label:
                # Try to resolve base label (e.g. label_created_at)
                base_label = (
                    ms_trans.get(f"label_{clean_name}")
                    or ms_trans.get(f"filter_{clean_name}")
                    or field.label
                )
                
                # If default field.label is messy (auto-generated English), clean it
                if (
                    not base_label
                    or '[invalid name]' in str(base_label).lower()
                    or 'is greater than' in str(base_label).lower()
                    or 'is less than' in str(base_label).lower()
                ):
                    base_label = clean_name.replace('_', ' ').split('.')[-1].title()
                    # Secondary lookup for core field name in translations
                    base_label = (
                        ms_trans.get(f"label_{clean_name}")
                        or ms_trans.get(f"filter_{clean_name}")
                        or ms_trans.get(f"label_{base_label.lower()}")
                        or ms_trans.get(f"filter_{base_label.lower()}")
                        or base_label
                    )
                
                label = f"{base_label}{suffix}"

        if label:
            field.label = label

        widget = field.widget
        is_select_multiple = isinstance(widget, forms.SelectMultiple)
        is_select = isinstance(widget, (forms.Select, forms.NullBooleanSelect)) and not is_select_multiple
        is_check_like = isinstance(widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple, forms.RadioSelect))
        is_hidden = isinstance(widget, (forms.HiddenInput, forms.MultipleHiddenInput))

        if label and inline_labels and not is_hidden:
            if is_select:
                set_first_choice(field, label)
                field.label = ''
            elif not is_select_multiple and not is_check_like:
                field.widget.attrs.setdefault('placeholder', label)
                field.label = ''

        field.widget.attrs['dir'] = direction  # Set text direction dynamically
        
        # Inject Bootstrap classes based on widget type
        existing_class = field.widget.attrs.get('class', '')
        if is_select:
            if 'form-select' not in existing_class:
                field.widget.attrs['class'] = f"{existing_class} form-select".strip()
        elif is_select_multiple:
            if 'form-select' not in existing_class:
                field.widget.attrs['class'] = f"{existing_class} form-select".strip()
        elif is_check_like:
            if 'form-check-input' not in existing_class:
                field.widget.attrs['class'] = f"{existing_class} form-check-input".strip()
        else:
            if 'form-control' not in existing_class:
                field.widget.attrs['class'] = f"{existing_class} form-control".strip()
            
        # 3. Inject the shared microSYS datepicker hook for real date/datetime inputs.
        # Keep legacy .flatpickr compatibility so host apps do not need an immediate markup sweep.
        # Do not attach the picker to selects such as date__year choice filters.
        is_select_like = isinstance(widget, (forms.Select, forms.SelectMultiple, forms.NullBooleanSelect))
        is_date = (
            isinstance(widget, (forms.DateInput, forms.DateTimeInput)) or
            'datetimeinput' in existing_class or
            (
                not is_select_like and
                any(kw in field_name.lower() for kw in ['date', 'time', 'since', 'until'])
            )
        )
        
        if is_date and 'ms-datepicker' not in field.widget.attrs.get('class', '') and 'flatpickr' not in field.widget.attrs.get('class', ''):
            current_class = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f"{current_class} ms-datepicker".strip()
        if is_date:
            field.widget.attrs['autocomplete'] = 'off'

# Set up modern Crispy layout for django-filter FilterSet
def setup_filter_helper(filter_instance, request=None, preserve_keys=None, inline_labels=True):
    """
    Sets up a modern, responsive Crispy layout for a django-filter FilterSet.
    Aligns fields dynamically using Bootstrap 5 flexbox and appends a filter button.
    """
    from crispy_forms.helper import FormHelper
    from crispy_forms.layout import Layout, Div, Field, HTML, Hidden, Row
    
    helper = FormHelper()
    helper.form_method = 'get'
    helper.form_tag = True
    helper.form_class = 'py-3 row g-2 no-print m-0 microsys-form microsys-filter'
    
    # Determine which keys to preserve in the URL and form state
    if preserve_keys is None:
        preserve_keys = ['type', 'sort', 'per_page', 'export_type', 'model', 'id', 'category']
        
    layout_hidden = []
    if request and request.GET:
        for key in preserve_keys:
            if key in request.GET:
                val = request.GET.get(key)
                layout_hidden.append(Hidden(key, val))

    # Dynamically build layout based on fields
    fields = list(filter_instance.form.fields.keys())
    divs = []
    
    # Calculate col width
    col_class = 'col-sm-6 col-md-3 col-lg-auto flex-grow-1'
    
    for f in fields:
        divs.append(Div(Field(f, wrapper_class='mb-0'), css_class=col_class))
    
    # Determine if we have active filters
    has_active_filters = False
    clear_url = "?"
    
    if request and request.GET:
        import urllib.parse
        has_active_filters = any(k not in preserve_keys + ['page'] and v for k, v in request.GET.items())
        clear_params = {k: v for k, v in request.GET.items() if k in preserve_keys}
        qs = urllib.parse.urlencode(clear_params, doseq=True)
        if qs:
            clear_url = f"?{qs}"

    # Build button group
    if has_active_filters:
        search_btn = '<button type="submit" class="btn btn-secondary microsys-filter-chip microsys-filter-submit rounded-start-pill rounded-end-0 flex-grow-1"><i class="bi bi-search"></i></button>'
        clear_btn = f'<a href="{clear_url}" class="btn btn-warning microsys-filter-chip microsys-filter-clear rounded-end-pill rounded-start-0 px-3"><i class="bi bi-x-lg"></i></a>'
        btn_html = f'<div class="d-flex w-100 microsys-filter-controls">{search_btn}{clear_btn}</div>'
    else:
        search_btn = '<button type="submit" class="btn btn-secondary microsys-filter-chip microsys-filter-submit rounded-pill flex-grow-1"><i class="bi bi-search"></i></button>'
        btn_html = f'<div class="d-flex w-100 microsys-filter-controls">{search_btn}</div>'
    
    divs.append(
        Div(
            HTML(btn_html),
            css_class='col-sm-12 col-md-2 col-lg-auto'
        )
    )
    
    # Wrap divs in a row container for consistent layout even if form tag is missing
    helper.layout = Layout(
        *layout_hidden, 
        Div(*divs, css_class='row g-2 align-items-start mb-0')
    )
    filter_instance.form.helper = helper
    
    # Apply shared field attrs, defaulting filters to inline placeholder labels.
    set_field_attrs(filter_instance.form, request, inline_labels=inline_labels)

# Build advanced filter helper with expandable fields
def advanced_filter_helper(filter_instance, config=None, request=None, preserve_keys=None, inline_labels=True):
    """
    Build an "advanced" filter helper with:
    - a primary row of fields
    - a pill-shaped search/clear control
    - an expand/collapse button for advanced fields
    - one or more advanced rows inside a collapse container
    - an optional bottom action row for add/download/custom buttons

    Config format:
        {
            "fields": [<field spec>, ...],
            "advanced_fields": [[<field spec>, ...], ...],
            "buttons": [<button spec>, ...],
            "hidden_inputs": [<raw html>, ...],
            "hidden_preserve_keys": ["sort", ...],
            "clear_preserve_keys": ["sort", "page"],
            "clear_url": "...",
            "advanced_target": "advanced-search",
            "toggle_label_key": "filter_advanced_search_action",
            "primary_row_class": "g-2",
            "advanced_wrapper_class": "collapse m-0",
            "actions_row_class": "g-2",
        }

    Field spec:
        "field_name"
        {
            "name": "field_name",
            "col_class": "form-group col-auto flex-fill",
            "attrs": {"placeholder": "..."},
            "placeholder": "...",
            "placeholder_key": "translation_key",
            "range_label_key": "label_date",
            "range_direction": "from" | "to",
            "wrapper_class": "mb-0",
        }
        {
            "type": "label" | "html",
            "text": "...",
            "text_key": "translation_key",
            "html": "<strong>...</strong>",
            "col_class": "...",
        }

    Button spec:
        {
            "url": "...",
            "permission": "app.perm_name",
            "label": "...",
            "label_key": "translation_key",
            "icon": "bi bi-plus-lg me-2 h4",
            "btn_class": "btn btn-primary w-100",
            "col_class": "col-auto text-center",
        }
        or {"type": "html", "html": "...", "col_class": "..."}
    """
    from crispy_forms.helper import FormHelper
    from crispy_forms.layout import Layout, Div, Field, HTML, Hidden, Row

    config = config or {}
    helper = FormHelper()
    helper.form_method = 'get'
    helper.form_tag = True
    helper.form_class = config.get('form_class', 'py-3 row g-2 no-print m-0 microsys-form microsys-filter')
    helper.attrs = dict(config.get('form_attrs', {}) or {})
    if config.get('autosubmit_selects', True):
        helper.attrs['data-ms-filter-autosubmit'] = 'true'

    if preserve_keys is None:
        preserve_keys = (
            config.get('hidden_preserve_keys')
            or config.get('preserve_keys')
            or ['sort', 'per_page', 'export_type']
        )

    clear_preserve_keys = config.get('clear_preserve_keys')
    if clear_preserve_keys is None:
        clear_preserve_keys = ['sort', 'page']

    from microsys.translations import get_current_language_code
    lang = get_current_language_code(request)
    s = get_strings(lang)

    set_field_attrs(filter_instance.form, request, inline_labels=inline_labels)

    hidden_layout = []
    if request and request.GET:
        for key in preserve_keys:
            if key in request.GET:
                hidden_layout.append(Hidden(key, request.GET.get(key)))

    for hidden_html in config.get('hidden_inputs', []) or []:
        hidden_layout.append(HTML(hidden_html))

    # Config Helper — Resolves translation text from MS_TRANS with fallback
    def _resolve_text(key=None, fallback=''):
        if key:
            return s.get(key, fallback)
        return fallback

    # Config Helper — Merges custom attributes into field widget
    def _merge_attrs(field_obj, attrs):
        if not attrs:
            return
        field_obj.widget.attrs.update(attrs)

    # Config Helper — Resolves placeholder text from spec with translation support
    def _resolve_placeholder(spec):
        if spec.get('placeholder') is not None:
            return spec['placeholder']
        if spec.get('placeholder_key'):
            return _resolve_text(spec['placeholder_key'], spec['placeholder_key'])

        range_label_key = spec.get('range_label_key')
        range_direction = spec.get('range_direction')
        if range_label_key and range_direction in {'from', 'to'}:
            base = _resolve_text(range_label_key, range_label_key)
            suffix_key = 'filter_from' if range_direction == 'from' else 'filter_to'
            suffix = _resolve_text(suffix_key, 'From' if range_direction == 'from' else 'To')
            return f"{base} {suffix}".strip()
        return None

    # Layout Builder — Renders a field spec into a Crispy Div with proper styling
    def _render_field_spec(spec, default_col_class):
        if isinstance(spec, str):
            spec = {'name': spec}
        if not isinstance(spec, dict):
            return None

        spec_type = spec.get('type', 'field')
        col_class = spec.get('col_class', default_col_class)

        if spec_type == 'html':
            return Div(HTML(spec.get('html', '')), css_class=col_class)

        if spec_type == 'label':
            text = spec.get('text')
            if text is None:
                text = _resolve_text(spec.get('text_key'), '')
            tag = spec.get('tag', 'strong')
            return Div(HTML(f'<{tag}>{text}</{tag}>'), css_class=col_class)

        field_name = spec.get('name')
        if not field_name or field_name not in filter_instance.form.fields:
            return None

        field_obj = filter_instance.form.fields[field_name]
        placeholder = _resolve_placeholder(spec)
        if placeholder:
            field_obj.widget.attrs['placeholder'] = placeholder
            if hasattr(field_obj, 'empty_label'):
                field_obj.empty_label = placeholder
            if hasattr(field_obj, 'choices'):
                set_first_choice(field_obj, placeholder)

        _merge_attrs(field_obj, spec.get('attrs'))
        return Div(
            Field(field_name, wrapper_class=spec.get('wrapper_class', 'mb-0')),
            css_class=col_class,
        )

    # Layout Builder — Builds an action button with permission check support
    def _build_action_button(spec):
        if not isinstance(spec, dict):
            return None

        if spec.get('type') == 'html':
            return Div(HTML(spec.get('html', '')), css_class=spec.get('col_class', 'col-auto text-center'))

        label = spec.get('label')
        if label is None:
            label = _resolve_text(spec.get('label_key'), '')
        icon = spec.get('icon', '')
        icon_html = f'<i class="{icon}"></i>' if icon else ''
        btn_class = spec.get("btn_class", "btn btn-outline-secondary w-100")
        if "microsys-filter-action" not in btn_class:
            btn_class = f"{btn_class} microsys-filter-action".strip()
        button_html = f'<a href="{spec.get("url", "#")}" class="{btn_class}">{icon_html}{label}</a>'

        permission = spec.get('permission')
        if permission:
            app_label, codename = permission.split('.', 1)
            button_html = f'{{% if perms.{app_label}.{codename} %}}{button_html}{{% endif %}}'

        return Div(HTML(button_html), css_class=spec.get('col_class', 'col-auto text-center'))

    # URL Builder — Constructs clear URL preserving specified query parameters
    def _build_clear_url():
        explicit = config.get('clear_url')
        if explicit:
            return explicit

        clear_url = '?'
        if request and request.GET:
            import urllib.parse
            clear_params = {k: v for k, v in request.GET.items() if k in clear_preserve_keys}
            qs = urllib.parse.urlencode(clear_params, doseq=True)
            if qs:
                clear_url = f'?{qs}'
        return clear_url

    # Filter State — Checks if any non-preserved filters are active
    def _has_active_filters():
        if not request or not request.GET:
            return False
        return any(k not in clear_preserve_keys and v for k, v in request.GET.items())

    advanced_specs = config.get('advanced_fields') or []
    advanced_names = {
        spec.get('name')
        for row in advanced_specs
        for spec in (row if isinstance(row, (list, tuple)) else [row])
        if isinstance(spec, dict) and spec.get('type', 'field') == 'field' and spec.get('name')
    }
    show_advanced = bool(
        request and request.GET and any(request.GET.get(name) for name in advanced_names)
    )

    primary_divs = []
    for spec in config.get('fields') or list(filter_instance.form.fields.keys()):
        primary_div = _render_field_spec(spec, config.get('primary_field_col_class', 'col-sm-6 col-md-3 col-lg-auto flex-grow-1'))
        if primary_div:
            primary_divs.append(primary_div)

    clear_url = _build_clear_url()
    has_active_filters = _has_active_filters()
    search_btn = '<button type="submit" class="btn btn-secondary microsys-filter-chip microsys-filter-submit rounded-start-pill rounded-end-0 flex-grow-1"><i class="bi bi-search"></i></button>'
    clear_btn = ''
    if has_active_filters:
        clear_btn = f'<a href="{clear_url}" class="btn btn-warning microsys-filter-chip microsys-filter-clear rounded-end-pill rounded-start-0 px-3"><i class="bi bi-x-lg"></i></a>'
    else:
        search_btn = '<button type="submit" class="btn btn-secondary microsys-filter-chip microsys-filter-submit rounded-pill flex-grow-1"><i class="bi bi-search"></i></button>'

    primary_divs.append(
        Div(
            HTML(f'<div class="d-flex w-100 microsys-filter-controls">{search_btn}{clear_btn}</div>'),
            css_class=config.get('search_controls_col_class', 'col-sm-12 col-md-2 col-lg-auto')
        )
    )

    toggle_target = config.get('advanced_target', 'advanced-search')
    toggle_label = _resolve_text(config.get('toggle_label_key', 'filter_advanced_search_action'), 'Advanced')
    toggle_icon = config.get('toggle_icon', 'bi bi-binoculars-fill')
    primary_divs.append(
        Div(
            HTML(
                '<button class="btn btn-outline-secondary microsys-filter-chip microsys-filter-toggle w-100" type="button" '
                f'data-bs-toggle="collapse" data-bs-target="#{toggle_target}" '
                f'aria-expanded="{"true" if show_advanced else "false"}" aria-controls="{toggle_target}">'
                f'<i class="{toggle_icon} me-2"></i>{toggle_label}'
                '</button>'
            ),
            css_class=config.get('toggle_col_class', 'col-sm-12 col-md-3 col-lg-auto')
        )
    )

    advanced_rows = []
    for row in advanced_specs:
        row_specs = row if isinstance(row, (list, tuple)) else [row]
        row_divs = []
        for spec in row_specs:
            row_div = _render_field_spec(spec, config.get('advanced_field_col_class', 'col-auto flex-fill'))
            if row_div:
                row_divs.append(row_div)
        if row_divs:
            advanced_rows.append(
                Row(
                    *row_divs,
                    css_class=config.get('advanced_row_class', 'g-2 align-items-start mb-0'),
                )
            )

    action_divs = []
    for spec in config.get('buttons', []):
        action_div = _build_action_button(spec)
        if action_div:
            action_divs.append(action_div)

    layout_items = list(hidden_layout)
    layout_items.append(
        Div(
            *primary_divs,
            css_class=config.get('primary_row_class', 'row g-2 align-items-start mb-0'),
        )
    )

    if advanced_rows:
        collapse_class = config.get('advanced_wrapper_class', 'collapse m-0')
        if show_advanced:
            collapse_class = f"{collapse_class} show"
        layout_items.append(
            Div(
                *advanced_rows,
                css_class=collapse_class,
                id=toggle_target,
            )
        )

    if action_divs:
        layout_items.append(
            Div(
                Div(
                    *action_divs,
                    css_class=config.get('actions_row_class', 'row g-2'),
                ),
                css_class=config.get('buttons_wrapper_class', 'p-0 my-2'),
            )
        )

    helper.layout = Layout(*layout_items)
    filter_instance.form.helper = helper

# Form Helper — Set the first choice of a selection field safely
def set_first_choice(field, placeholder):
    """Set the first choice of a specified field safely without overwriting data."""
    # 1. Handle fields with explicit empty_label (ModelChoiceField, etc.)
    if hasattr(field, 'empty_label'):
        field.empty_label = placeholder
        return

    # 2. Handle ChoiceFields or fields with a choices attribute
    if not hasattr(field, 'choices'):
        return
        
    choices = list(field.choices)
    
    # Check if the first choice looks like an empty placeholder
    is_empty = False
    if choices:
        val, lbl = choices[0]
        # Common empty values: None, '', 0
        # Common empty labels: empty string, or Django's default '---------'
        if val in ('', None) or (isinstance(val, int) and val == 0 and not lbl):
             is_empty = True
        elif lbl and ('---' in str(lbl) or str(lbl).strip() == ''):
             is_empty = True

    if is_empty:
        val = choices[0][0]
        choices[0] = (val, placeholder)
    else:
        # Otherwise insert a standard empty string choice
        choices.insert(0, ('', placeholder))
        
    field.choices = choices

# Form Helper — Translates a choices list using MS_TRANS choice_ prefix
def translate_choices(choices, ms_trans):
    """
    Translate a choices list using MS_TRANS choice_ prefix.
    Expects choices in format [(value, label), ...]
    """
    translated = []
    for value, label in choices:
        if value == '' or value is None:
            # Keep placeholder as is (or '---' if not set)
            translated.append((value, label or '---'))
        else:
            translated.append((value, ms_trans.get(f'choice_{value}', label)))
    return translated

# Form Helper — Detects if a Crispy form layout already contains Submit/Button elements
def has_submit_button(form):
    """
    Recursively inspects a Crispy Form helper layout to determine if the developer
    has already included a Submit or Button object. Used to auto-hide duplicate
    buttons in generic modal/section templates.
    """
    if not hasattr(form, 'helper') or not form.helper or not getattr(form.helper, 'layout', None):
        return False
        
    from crispy_forms.layout import Submit, Button, HTML
    
    # Layout Inspector — Recursively checks for Submit/Button objects in layout
    def check_node(node):
        # Direct match for Submit or Button objects
        if isinstance(node, (Submit, Button)):
            return True
            
        # Match inside raw HTML objects
        if isinstance(node, HTML) and hasattr(node, 'html'):
            html_content = str(node.html).lower()
            if '<button' in html_content and (
                'type="submit"' in html_content or
                "type='submit'" in html_content or
                'type=submit' in html_content
            ):
                return True
            if '<input' in html_content and (
                'type="submit"' in html_content or
                "type='submit'" in html_content or
                'type=submit' in html_content
            ):
                return True
            if 'class="btn' in html_content and ('save' in html_content or 'حفظ' in html_content):
                # Catch-all for generic styled buttons that look like save buttons
                return True
                
        # Recursive check for any nested layout objects (Rows, Divs, Fieldsets, etc.)
        if hasattr(node, 'fields') and node.fields:
            for child in node.fields:
                if check_node(child):
                    return True
        return False
        
    for item in form.helper.layout.fields:
        if check_node(item):
            return True
            
    return False

# Return app version from VERSION file at the parent caller's folder
def get_app_version(calling_file_path: str) -> str:
    """
    Reads the VERSION file from the same directory as the calling file.
    Usage: VERSION = get_app_version(__file__)
    """
    try:
        # Resolves the directory of the file that called this function
        app_dir = Path(calling_file_path).resolve().parent
        with open(app_dir / "VERSION", "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "unknown"
