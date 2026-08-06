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

# Client-side SMTP timeouts. These are deliberately a *pair* with the relay's own
# upstream timeout (DLUX_SMTP_RELAY_UPSTREAM_TIMEOUT, used by the scaffolded
# dlux/smtp_relay.py), and the ordering between them is the whole point:
#
#   relay upstream timeout  <  relay client timeout
#
# Relay delivery is two hops — app → relay → provider — and only the relay can see
# why the provider hop failed. If the app gives up first it reports a meaningless
# "Connection unexpectedly closed: timed out" and the real reason lands in the
# relay's log ~20s later, where nobody looks. Letting the relay lose the race means
# it answers `451` with the actual cause and the operator sees it in the UI.
# Values are sized for a SLOW upstream, not a fast one. Plenty of real mail
# servers (virus/spam scanning in-line, legacy government and university relays)
# take 30-60s to accept a DATA payload while answering the connect, EHLO and AUTH
# steps instantly — so a timeout tuned to the handshake looks fine right up until
# the message body, then fails every send. Raise these rather than lower them; a
# too-short timeout is indistinguishable from a broken server.
DLUX_SMTP_DIRECT_TIMEOUT = 30
# Slack the app allows the relay on top of its own upstream budget, so the relay
# always answers first with the reason. Derived rather than hand-set, so an
# operator raising the timeout in the UI cannot invert the ordering by accident.
DLUX_SMTP_RELAY_CLIENT_HEADROOM = 15
# Consumed by the packaged relay; exported so a project can import the value
# instead of hard-coding a number that must stay under the client timeout.
DLUX_SMTP_RELAY_UPSTREAM_TIMEOUT = 60
DLUX_SMTP_RELAY_CLIENT_TIMEOUT = DLUX_SMTP_RELAY_UPSTREAM_TIMEOUT + DLUX_SMTP_RELAY_CLIENT_HEADROOM


def resolve_smtp_timeouts(email_config):
    """``(upstream, client)`` seconds for one email configuration.

    The UI exposes a single number — how long to wait for the provider — because
    two independent boxes invite an operator to invert the ordering the relay's
    error reporting depends on. For relay transport that number is the relay's
    upstream budget and the client gets it plus headroom; for direct transport the
    app *is* the only hop, so it is the client timeout outright.
    """
    try:
        configured = int(email_config.get('timeout') or 0)
    except (TypeError, ValueError):
        configured = 0
    if email_config.get('transport') == 'relay':
        upstream = configured or DLUX_SMTP_RELAY_UPSTREAM_TIMEOUT
        return upstream, upstream + DLUX_SMTP_RELAY_CLIENT_HEADROOM
    client = configured or DLUX_SMTP_DIRECT_TIMEOUT
    return client, client

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

# Email Secrets - Sentinel for a stored secret that cannot be decrypted here.
EMAIL_SECRET_ABSENT = 'absent'
EMAIL_SECRET_OK = 'ok'
EMAIL_SECRET_UNDECRYPTABLE = 'undecryptable'


# Email Secrets - Function decrypts stored SMTP passwords with legacy fallback.
def decrypt_email_secret(encrypted_secret, *, strict=False):
    """Decrypt a stored SMTP password.

    Returns '' on failure by default so callers on the send path degrade rather
    than crash. Pass ``strict=True`` to tell the two failure modes apart: an empty
    return is ambiguous between "no password stored" and "stored but encrypted
    under a different key", and those need very different operator action. The
    second happens whenever the process decrypting has a different SECRET_KEY from
    the one that encrypted — a rotated key, or a sidecar container (the SMTP relay)
    started with a different DJANGO_SECRET_KEY.
    """
    encrypted_secret = str(encrypted_secret or '').strip()
    if not encrypted_secret:
        return ''
    try:
        return _email_fernet().decrypt(encrypted_secret.encode('utf-8')).decode('utf-8')
    except Exception:
        if strict:
            raise
        return ''


# Email Secrets - Function reports whether a stored secret is usable *here*.
def email_secret_state(encrypted_secret):
    """Classify a stored secret as absent / ok / undecryptable for this process."""
    if not str(encrypted_secret or '').strip():
        return EMAIL_SECRET_ABSENT
    try:
        decrypt_email_secret(encrypted_secret, strict=True)
    except Exception:
        return EMAIL_SECRET_UNDECRYPTABLE
    return EMAIL_SECRET_OK

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
            'timeout': stored_config.get('timeout', 0),
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
            'timeout': stored_config.get('timeout', 0),
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

# Email Runtime - Gate for the settings that depend on Dlux sending mail.
def email_features_unlocked():
    """True when mail-dependent SETTINGS may be edited.

    Requires both operator intent (email_config.enabled) and proof the config
    actually works (a successful test send, still matching the connection it was
    run against). Deliberately stricter than get_email_service_status(), which
    reports whether mail *can* be sent and stays the runtime gate: a deployment
    configuring SMTP purely through env vars keeps sending mail exactly as before
    even though its toggles read locked until someone runs the test once.

    Local debug backends unlock without a test so development is not blocked on
    a real SMTP round trip.
    """
    status = get_email_service_status()
    if status.get('reason') == 'local_debug_backend':
        return True
    try:
        SystemSettings = apps.get_model('dlux', 'SystemSettings')
        config = normalize_email_config(getattr(SystemSettings.load(), 'email_config', {}) or {})
    except Exception:
        return False
    return bool(config.get('enabled') and config.get('verified'))


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

# Email Runtime - Function warns configured operators in-app when transactional mail fails.
def _alert_email_delivery_failure(subject, recipient_list, error):
    """Notify the configured failure recipients in-app (never by email — that path is broken).

    Routed through the notification subsystem so it inherits the global enable flag; a
    matching audit row records the outage. Best-effort: never raises into the caller.
    """
    try:
        SystemSettings = apps.get_model('dlux', 'SystemSettings')
        stored_config = normalize_email_config(getattr(SystemSettings.load(), 'email_config', {}))
    except Exception:
        return
    recipients = stored_config.get('failure_notification_recipients') or []
    if not recipients:
        return
    try:
        from django.contrib.auth import get_user_model
        from ..notifications import notify

        User = get_user_model()
        users = list(User._default_manager.filter(email__in=recipients, is_active=True))
        attempted = ', '.join(list(recipient_list or [])[:3]) or '—'
        message = (
            f"Transactional email failed to send (subject: {subject or '—'}; "
            f"to: {attempted}). Error: {str(error)[:200]}"
        )
        if users:
            notify.error(
                message,
                recipients=users,
                persist=True,
                flash=False,
                email=False,  # do not re-enter the broken mail path
                source='email_delivery_failure',
                title_key='email_delivery_failure_title',
            )
        from .. import log_activity

        log_activity('email_delivery_failed', details={'subject': subject or '', 'error': str(error)[:200]}, category='audit')
    except Exception:
        # Alerting must never mask or replace the original delivery error.
        return


# Email Runtime - Function sends Dlux transactional mail through direct or relay transport.
def send_dlux_mail(subject, message, recipient_list, *, from_email=None, fail_silently=False, alert_on_failure=True):
    """Send Dlux-owned transactional email through the selected delivery path.

    ``alert_on_failure`` routes send failures to the configured in-app failure
    recipients. Callers on the alert path itself (or the test sender) pass
    ``False`` to avoid recursion / noise.
    """
    email_config = get_dlux_email_config(include_secret=True)
    effective_from = from_email or email_config.get('from_email') or getattr(settings, 'DEFAULT_FROM_EMAIL', None)

    backend = email_config.get('backend') or getattr(settings, 'EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
    try:
        if backend != 'django.core.mail.backends.smtp.EmailBackend':
            return send_mail(subject, message, effective_from, recipient_list, fail_silently=fail_silently)

        # Without a timeout a slow/unreachable SMTP host blocks the calling request
        # (e.g. login-time OTP emails) until the OS socket timeout, which can take
        # minutes. Cap it so mail failures surface quickly instead of hanging auth.
        #
        # Relay transport gets a longer cap on purpose: the app is only the first of
        # two hops, and the relay needs to finish losing its own upstream race before
        # it can answer with *why*. Timing out first here would replace the relay's
        # real 451 reason with an uninformative client-side timeout.
        _upstream, smtp_timeout = resolve_smtp_timeouts(email_config)
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
    except Exception as exc:
        if alert_on_failure:
            _alert_email_delivery_failure(subject, recipient_list, exc)
        raise
