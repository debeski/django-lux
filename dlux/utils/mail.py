"""dlux.utils.mail — Email secret encryption and transactional mail runtime.

Split from the original ``dlux/utils.py`` (kept intact, inert).
"""
import base64
import hashlib
import json
import os
import re
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from functools import lru_cache
import inspect
from pathlib import Path
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
from ..system.constants import (
    DEFAULT_HOME_URL,
    DEFAULT_NAVBAR_MODE,
    DEFAULT_SIDEBAR_COLLAPSE_MODE,
    DEFAULT_SIDEBAR_DENSITY,
    DEFAULT_TABLE_DENSITY,
    REGISTRATION_ACTIVATION_AUTO_LOGIN,
    REGISTRATION_ACTIVATION_VALUES,
    NAVBAR_MODE_VALUES,
    SIDEBAR_COLLAPSE_MODE_VALUES,
    SIDEBAR_DENSITY_VALUES,
    TABLE_DENSITY_VALUES,
    TITLEBAR_ALIGN_VALUES,
    TITLEBAR_HEIGHT_VALUES,
    TITLEBAR_HOME_SHAPE_VALUES,
    TITLEBAR_LOGO_TREATMENT_SHAPE_VALUES,
    TITLEBAR_LOGO_TREATMENT_VALUES,
    TITLEBAR_SIZE_VALUES,
    TITLEBAR_SURFACE_VALUES,
)
from ..fonts import DEFAULT_FONT_SLUG, get_builtin_fonts
from ..themes import is_valid_theme, normalize_allowed_themes
from ..translations import get_current_language_code, get_strings
# try-except for django_filters as it might not be installed (though likely is)
try:
    import django_filters
except ImportError:
    django_filters = None

# ── intra-package imports (shared + feature deps) ──
from .config import default_email_config, normalize_email_config

DLUX_INTERNAL_SMTP_RELAY_HOST = 'smtp-relay'

DLUX_INTERNAL_SMTP_RELAY_PORT = 1025

# Email Secrets - Helper derives the encryption seed for stored email passwords.
def _email_secret_seed():
    configured_key = (
        os.getenv('DLUX_EMAIL_SECRET_KEY')
        or os.getenv('DLUX_SECRET_KEY')
        or getattr(settings, 'DLUX_EMAIL_SECRET_KEY', '')
        or getattr(settings, 'SECRET_KEY', '')
    )
    return str(configured_key or 'dlux-email-secret-dev-key')

# Email Secrets - Helper builds the Fernet instance for email password encryption.
def _email_fernet():
    from cryptography.fernet import Fernet

    digest = hashlib.sha256(_email_secret_seed().encode('utf-8')).digest()
    return Fernet(base64.urlsafe_b64encode(digest))

# Email Secrets - Function encrypts SMTP passwords for DB storage.
def encrypt_email_secret(raw_secret):
    raw_secret = str(raw_secret or '')
    if not raw_secret:
        return ''
    return _email_fernet().encrypt(raw_secret.encode('utf-8')).decode('utf-8')

# Email Secrets - Function decrypts stored SMTP passwords with legacy fallback.
def decrypt_email_secret(encrypted_secret):
    encrypted_secret = str(encrypted_secret or '').strip()
    if not encrypted_secret:
        return ''
    try:
        return _email_fernet().decrypt(encrypted_secret.encode('utf-8')).decode('utf-8')
    except Exception:
        return ''

# Email Runtime - Function resolves the active Dlux email backend configuration.
def get_dlux_email_config(*, include_secret=False):
    try:
        SystemSettings = apps.get_model('dlux', 'SystemSettings')
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
            'host': getattr(settings, 'DLUX_SMTP_RELAY_HOST', DLUX_INTERNAL_SMTP_RELAY_HOST),
            'port': getattr(settings, 'DLUX_SMTP_RELAY_PORT', DLUX_INTERNAL_SMTP_RELAY_PORT),
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
        'host': stored_hints.get('host') or (getattr(settings, 'EMAIL_HOST', '') or ''),
        'port': stored_hints.get('port') or getattr(settings, 'EMAIL_PORT', None),
        'use_tls': bool(stored_hints.get('use_tls')) if 'use_tls' in hint_keys else bool(getattr(settings, 'EMAIL_USE_TLS', False)),
        'use_ssl': bool(stored_hints.get('use_ssl')) if 'use_ssl' in hint_keys else bool(getattr(settings, 'EMAIL_USE_SSL', False)),
        'username': stored_hints.get('username') or (getattr(settings, 'EMAIL_HOST_USER', '') or ''),
        'password': getattr(settings, 'EMAIL_HOST_PASSWORD', '') if include_secret else '',
        'from_email': stored_hints.get('default_from_email') or (getattr(settings, 'DEFAULT_FROM_EMAIL', '') or ''),
        'password_configured': bool(getattr(settings, 'EMAIL_HOST_PASSWORD', '')),
        'ui_hints': stored_hints,
    }

# Email Runtime - Function reports configured email capability without network I/O.
def get_email_service_status():
    """
    Report whether Dlux-owned email flows are configured without touching
    SMTP networks or returning secrets.
    """
    try:
        SystemSettings = apps.get_model('dlux', 'SystemSettings')
        raw_stored_email_config = getattr(SystemSettings.load(), 'email_config', {})
        stored_email_config = normalize_email_config(raw_stored_email_config)
    except Exception:
        raw_stored_email_config = {}
        stored_email_config = default_email_config()
    stored_hint_keys = set(raw_stored_email_config.keys()) if isinstance(raw_stored_email_config, dict) else set()
    email_config = get_dlux_email_config(include_secret=False)
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

# Email Runtime - Function sends Dlux transactional mail through direct or relay transport.
def send_dlux_mail(subject, message, recipient_list, *, from_email=None, fail_silently=False):
    """Send Dlux-owned transactional email through the selected delivery path."""
    email_config = get_dlux_email_config(include_secret=True)
    effective_from = from_email or email_config.get('from_email') or getattr(settings, 'DEFAULT_FROM_EMAIL', None)

    backend = email_config.get('backend') or getattr(settings, 'EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
    if backend != 'django.core.mail.backends.smtp.EmailBackend':
        return send_mail(subject, message, effective_from, recipient_list, fail_silently=fail_silently)

    # Without a timeout a slow/unreachable SMTP host blocks the calling request
    # (e.g. login-time OTP emails) until the OS socket timeout, which can take
    # minutes. Cap it so mail failures surface quickly instead of hanging auth.
    try:
        smtp_timeout = int(email_config.get('timeout') or 0) or 10
    except (TypeError, ValueError):
        smtp_timeout = 10
    connection = get_connection(
        backend=backend,
        host=email_config.get('host') or None,
        port=email_config.get('port') or None,
        username=email_config.get('username') or None,
        password=email_config.get('password') or None,
        use_tls=bool(email_config.get('use_tls')),
        use_ssl=bool(email_config.get('use_ssl')),
        timeout=smtp_timeout,
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
