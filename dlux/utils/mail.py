"""dlux.utils.mail — Email secret encryption and transactional mail runtime.

Split from the original ``dlux/utils.py`` (kept intact, inert).
"""
import base64
import hashlib
import json
import logging
import os
import re
import threading
import time
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
from django.db import transaction
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
from .. import smtp_session
from django.core.mail.backends.smtp import EmailBackend as _DjangoSMTPBackend

logger = logging.getLogger('dlux')

DLUX_INTERNAL_SMTP_RELAY_HOST = 'smtp-relay'

DLUX_INTERNAL_SMTP_RELAY_PORT = 1025

# How long the relay reachability probe waits in total, name lookup included. It
# runs while a settings page is being rendered, so it has to fail fast: the relay
# either sits on the same internal network (a millisecond away) or is not
# deployed at all, and there is no middle case worth waiting for.
DLUX_SMTP_RELAY_PROBE_TIMEOUT = 1.5

# Probes still running, by (host, port). A caller that finds one waits on it
# instead of starting another.
_relay_probes = {}
_relay_probes_lock = threading.Lock()

# How long a settings form reuses the last finished probe's answer. Every
# SystemSettingsForm construction asks, and a page can build several.
DLUX_SMTP_RELAY_GREETING_MAX_AGE = 10

# The last finished probe's answer, by (host, port): (monotonic time, greeting or None).
_relay_answers = {}


def _smtp_relay_greeting(host, port, timeout):
    """One unbounded check: resolve ``host``, connect and read the greeting.

    The greeting's text after ``220``, or None when nothing greets.
    """
    import smtplib

    # The probe never says EHLO, so naming the local host skips smtplib's
    # getfqdn(), which would be a second resolver call.
    client = smtplib.SMTP(timeout=timeout, local_hostname='localhost')
    try:
        code, message = client.connect(host, port)
    except (OSError, smtplib.SMTPException):
        client.close()
        return None
    try:
        client.quit()
    except (OSError, smtplib.SMTPException):
        client.close()
    if code != 220:
        return None
    return message.decode('utf-8', 'replace') if isinstance(message, bytes) else str(message or '')


class _RelayProbe:
    """A relay check in a daemon thread, so its caller can stop waiting.

    Socket timeouts bound the connection and the greeting, not ``getaddrinfo``:
    a resolver that has stopped answering holds a lookup for its whole retry
    cycle (glibc: 5 s, two attempts).
    """

    def __init__(self, host, port, timeout):
        self.key = (host, port)
        self.timeout = timeout
        self.deadline = time.monotonic() + timeout
        self.finished = threading.Event()
        self.greeting = None
        self.error = None
        self._thread = threading.Thread(
            target=self._run, name=f'dlux-relay-probe {host}:{port}', daemon=True)

    def start(self):
        self._thread.start()

    def _run(self):
        try:
            self.greeting = _smtp_relay_greeting(*self.key, self.timeout)
        except Exception as exc:
            self.error = exc
        finally:
            with _relay_probes_lock:
                if _relay_probes.get(self.key) is self:
                    del _relay_probes[self.key]
                _relay_answers[self.key] = (
                    time.monotonic(), self.greeting if self.error is None else None)
            self.finished.set()

    def wait(self, timeout):
        """The greeting, or None once this probe's deadline or ``timeout`` passes."""
        remaining = min(timeout, self.deadline - time.monotonic())
        if not self.finished.wait(max(remaining, 0)):
            return None
        if self.error is not None:
            raise self.error
        return self.greeting


def internal_smtp_relay_available(host=None, port=None, timeout=None):
    """Whether the internal SMTP relay is listening (see ``internal_smtp_relay_greeting``)."""
    return internal_smtp_relay_greeting(host=host, port=port, timeout=timeout) is not None


def internal_smtp_relay_greeting(host=None, port=None, timeout=None, max_age=0):
    """The internal SMTP relay's greeting, or None when it is not listening.

    The greeting says what the relay does: ``smtp_session.relay_checks_certificates``
    tells a relay that checks the provider's certificate from an older one.

    Answers "is that process deployed", which is deliberately independent of
    what `email_config` says: `dlux.smtp_relay` starts its listener
    unconditionally and resolves its upstream per message, so it accepts
    connections before it has ever been configured. That is what makes it safe
    to offer relay transport only when this is true — the two cannot deadlock.

    Reads the SMTP greeting rather than just completing a TCP handshake, so
    something else holding the port does not read as a relay. Sends no mail and
    needs no credentials: the listener speaks plaintext with no auth, because
    only the app can reach it.

    Returns within ``timeout`` (DLUX_SMTP_RELAY_PROBE_TIMEOUT) in total, name
    lookup included: the check runs in a daemon thread and a check still
    running at its deadline answers None. Calls for the same host and port
    share a check that is still running, and once its deadline has passed they
    answer None at once. So a stalled resolver costs one timeout per lookup it
    holds rather than one per settings page, and leaves at most one thread per
    target behind.

    ``max_age`` (seconds, default 0) accepts the answer of a check that finished
    that recently instead of starting a new one; the settings form passes
    ``DLUX_SMTP_RELAY_GREETING_MAX_AGE``. With the default, the first call after
    a check finishes starts a new one.
    """
    from django.conf import settings as django_settings

    host = host or getattr(django_settings, 'DLUX_SMTP_RELAY_HOST', DLUX_INTERNAL_SMTP_RELAY_HOST)
    port = int(port or getattr(django_settings, 'DLUX_SMTP_RELAY_PORT', DLUX_INTERNAL_SMTP_RELAY_PORT))
    timeout = timeout or DLUX_SMTP_RELAY_PROBE_TIMEOUT
    key = (host, port)
    with _relay_probes_lock:
        answered = _relay_answers.get(key)
        if max_age and answered is not None and time.monotonic() - answered[0] < max_age:
            return answered[1]
        probe = _relay_probes.get(key)
        if probe is None or probe.finished.is_set():
            probe = _relay_probes[key] = _RelayProbe(host, port, timeout)
            try:
                probe.start()
            except RuntimeError:
                del _relay_probes[key]
                raise
    return probe.wait(timeout)

# Client-side SMTP timeouts. These are deliberately a *pair* with the relay's own
# upstream timeout (DLUX_SMTP_RELAY_UPSTREAM_TIMEOUT, used by the scaffolded
# dlux/smtp_session.py), and the ordering between them is the whole point:
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

    # Direct transport with environment storage: the web service's EMAIL_*
    # settings are the connection. Only the sender and timeout come from the step.
    backend = getattr(settings, 'EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
    return {
        'transport': 'direct',
        'secret_storage': 'env',
        'backend': backend,
        'host': getattr(settings, 'EMAIL_HOST', '') or '',
        'port': getattr(settings, 'EMAIL_PORT', None),
        'use_tls': bool(getattr(settings, 'EMAIL_USE_TLS', False)),
        'use_ssl': bool(getattr(settings, 'EMAIL_USE_SSL', False)),
        'username': getattr(settings, 'EMAIL_HOST_USER', '') or '',
        'password': getattr(settings, 'EMAIL_HOST_PASSWORD', '') if include_secret else '',
        'from_email': stored_config.get('default_from_email') or (getattr(settings, 'DEFAULT_FROM_EMAIL', '') or ''),
        'password_configured': bool(getattr(settings, 'EMAIL_HOST_PASSWORD', '')),
        'timeout': stored_config.get('timeout', 0),
    }


def _default_sender():
    return getattr(settings, 'DEFAULT_FROM_EMAIL', '') or os.getenv('DEFAULT_FROM_EMAIL', '') or ''


def _encryption_name(use_tls, use_ssl):
    if use_ssl:
        return 'ssl'
    return 'starttls' if use_tls else 'none'


# Email Runtime - What a send will actually use, without secrets.
def effective_email_settings(email_config=None):
    """The provider connection a send uses, never the password itself.

    ``source`` names where the provider values come from: ``database`` (entered
    on the Email step), ``relay_env`` (the relay's ``SMTP_RELAY_*`` variables,
    which compose shares with web and worker, password excepted) or ``django``
    (the web service's ``EMAIL_*`` settings). ``visible`` is False when this
    process cannot see the relay's variables: a stack whose compose.yml predates
    sharing them. ``password_set`` is True/False, or None when unknown.
    ``tls_verify`` is whether the provider's certificate is checked and
    ``ca_file`` the relay's extra CA bundle (``SMTP_RELAY_CA_FILE``), if any.
    ``internal_relay`` is True when the web service's ``EMAIL_*`` settings point
    at the internal relay (a generated stack), so direct sends go through it.
    """
    if email_config is None:
        try:
            SystemSettings = apps.get_model('dlux', 'SystemSettings')
            email_config = getattr(SystemSettings.load(), 'email_config', {})
        except Exception:
            email_config = {}
    config = normalize_email_config(email_config)
    transport = config.get('transport', 'direct')
    storage = config.get('secret_storage', 'env')
    result = {
        'transport': transport,
        'secret_storage': storage,
        'from_email': config.get('default_from_email') or _default_sender(),
        'timeout': config.get('timeout', 0),
        'visible': True,
        'encryption_derived': False,
        'internal_relay': False,
    }
    if storage == 'encrypted_db':
        result.update({
            'source': 'database',
            'host': config.get('host', ''),
            'port': config.get('port'),
            'use_tls': bool(config.get('use_tls')),
            'use_ssl': bool(config.get('use_ssl')),
            'username': config.get('username', ''),
            'password_set': bool(config.get('encrypted_password')),
            'tls_verify': transport != 'relay' or config.get('tls_verify', True) is not False,
            'ca_file': smtp_session.env_ca_file() if transport == 'relay' else '',
        })
    elif transport == 'relay':
        relay_env = smtp_session.env_upstream_config()
        # Compose hands web a yes/empty flag, never the password itself.
        password_set = smtp_session.env_flag(os.getenv('SMTP_RELAY_PASSWORD_SET'))
        if password_set is None and os.getenv('SMTP_RELAY_PASSWORD'):
            password_set = True
        if password_set is None and 'SMTP_RELAY_PASSWORD_SET' in os.environ:
            password_set = False
        result.update({
            'source': 'relay_env',
            'visible': 'SMTP_RELAY_HOST' in os.environ,
            'host': relay_env['host'],
            'port': relay_env['port'],
            'use_tls': relay_env['use_tls'],
            'use_ssl': relay_env['use_ssl'],
            'encryption_derived': relay_env['encryption_derived'],
            'username': relay_env['username'],
            'password_set': password_set,
            'tls_verify': relay_env['tls_verify'],
            'ca_file': relay_env['ca_file'],
        })
    else:
        host = getattr(settings, 'EMAIL_HOST', '') or ''
        relay_host = getattr(settings, 'DLUX_SMTP_RELAY_HOST', DLUX_INTERNAL_SMTP_RELAY_HOST) or ''
        result.update({
            'source': 'django',
            'internal_relay': bool(host) and host.strip().lower() == relay_host.strip().lower(),
            'host': host,
            'port': getattr(settings, 'EMAIL_PORT', None),
            'use_tls': bool(getattr(settings, 'EMAIL_USE_TLS', False)),
            'use_ssl': bool(getattr(settings, 'EMAIL_USE_SSL', False)),
            'username': getattr(settings, 'EMAIL_HOST_USER', '') or '',
            'password_set': bool(getattr(settings, 'EMAIL_HOST_PASSWORD', '')),
            'tls_verify': True,
            'ca_file': '',
        })
    if not result['visible']:
        for key in ('host', 'port', 'username'):
            result[key] = ''
        result['password_set'] = None
    result['encryption'] = _encryption_name(result['use_tls'], result['use_ssl'])
    return result

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
def get_email_service_status(email_config=None):
    """
    Report whether Dlux-owned email flows are configured without touching
    SMTP networks or returning secrets.

    ``email_config`` checks a candidate configuration (a form being saved)
    instead of the stored one.
    """
    if email_config is None:
        try:
            SystemSettings = apps.get_model('dlux', 'SystemSettings')
            email_config = getattr(SystemSettings.load(), 'email_config', {})
        except Exception:
            email_config = default_email_config()
    stored = normalize_email_config(email_config)
    effective = effective_email_settings(stored)
    transport = stored.get('transport') or 'direct'
    secret_storage = stored.get('secret_storage') or 'env'
    if transport == 'direct' and secret_storage == 'env':
        backend = getattr(settings, 'EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
    else:
        backend = 'django.core.mail.backends.smtp.EmailBackend'
    from_email = effective.get('from_email') or ''
    debug = bool(getattr(settings, 'DEBUG', False))
    host = effective.get('host') or ''
    port = effective.get('port')
    local_backends = {
        'django.core.mail.backends.console.EmailBackend',
        'django.core.mail.backends.locmem.EmailBackend',
        'django.core.mail.backends.filebased.EmailBackend',
    }
    base = {
        'backend': backend,
        'from_email': from_email,
        'transport': transport,
        'secret_storage': secret_storage,
    }

    if backend in local_backends and debug:
        return {**base, 'available': True, 'configured': True, 'reason': 'local_debug_backend'}

    if backend == 'django.core.mail.backends.smtp.EmailBackend':
        password_ok = True
        if effective.get('username') and effective.get('password_set') is False:
            password_ok = False
        detail = f"{host}:{port}" if host and port else ''
        if transport == 'relay':
            if not effective.get('visible'):
                # The relay holds its settings and web cannot see them: only a
                # test send can tell, so do not refuse to try one.
                configured = bool(from_email)
                reason = 'relay_env_not_visible' if configured else 'relay_missing_upstream_host_port_or_from_email'
            else:
                configured = bool(host and port and from_email and password_ok)
                reason = 'relay_configured' if configured else (
                    'relay_missing_password' if not password_ok else 'relay_missing_upstream_host_port_or_from_email'
                )
            return {**base, 'available': configured, 'configured': configured, 'detail': detail, 'reason': reason}
        configured = bool(host and port and from_email and password_ok)
        missing_reason = 'smtp_missing_host_port_or_from_email'
        if secret_storage == 'encrypted_db' and not password_ok:
            missing_reason = 'encrypted_db_missing_password'
        return {
            **base,
            'available': configured,
            'configured': configured,
            'detail': detail,
            'reason': 'smtp_configured' if configured else missing_reason,
        }

    configured = bool(from_email)
    return {
        **base,
        'available': configured,
        'configured': configured,
        'reason': 'custom_backend_configured' if configured else 'missing_default_from_email',
    }


class DluxSMTPBackend(_DjangoSMTPBackend):
    """Django's SMTP backend, recording the step a failure happened in.

    The original exception is re-raised unchanged, so callers that catch
    ``smtplib``/``OSError`` types keep working; it only gains ``dlux_step``.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dlux_tracker = smtp_session.StepTracker()

    @property
    def connection_class(self):
        import functools

        staged = smtp_session.StagedSMTP_SSL if self.use_ssl else smtp_session.StagedSMTP
        return functools.partial(staged, dlux_tracker=self.dlux_tracker)

    def send_messages(self, email_messages):
        try:
            return super().send_messages(email_messages)
        except Exception as exc:
            if not hasattr(exc, 'dlux_step'):
                try:
                    exc.dlux_step = self.dlux_tracker.step
                except AttributeError:
                    pass
            raise


_RELAY_REPLY_TARGET = re.compile(r'\b[a-z]+ (?P<host>[^\s:]+):(?P<port>\d+) (?P<enc>ssl|starttls|none):\s*(?P<detail>.*)$')


def _relay_reply_text(exc):
    """The relay's 451 text when ``exc`` carries one, else ``''``."""
    import smtplib

    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        replies = list((exc.recipients or {}).values())
        if replies:
            code, message = replies[0]
            return message.decode('utf-8', 'replace') if isinstance(message, bytes) else str(message)
        return ''
    message = getattr(exc, 'smtp_error', None)
    if message is None:
        return ''
    text = message.decode('utf-8', 'replace') if isinstance(message, bytes) else str(message)
    return text if 'Relay delivery failed' in text or 'step=' in text else ''


# Email Runtime - Names the hop and step a failed send stopped at.
def describe_mail_failure(exc, strings=None, *, email_config=None):
    """Which hop and SMTP step a send failed at, as data and as one sentence.

    Returns ``hop`` (``relay``: web to the internal relay; ``provider_relay``: the
    relay to the provider; ``provider_direct``: web to the provider), ``step``
    (config, connect, tls, greeting, auth, send, unknown), ``reason``, ``hint`` and
    a localized ``message``.
    """
    strings = strings if strings is not None else get_strings()
    effective = effective_email_settings(email_config)
    transport = effective.get('transport')
    host = effective.get('host') or ''
    port = effective.get('port') or ''
    _upstream, client_timeout = resolve_smtp_timeouts(effective)
    seconds = ''
    detail = ''
    hint = ''
    # Direct sends whose EMAIL_* names the internal relay take the relay's hops.
    via_relay = transport == 'relay' or bool(effective.get('internal_relay'))
    relay_text = _relay_reply_text(exc) if via_relay else ''

    if relay_text:
        hop = 'provider_relay'
        tokens = smtp_session.parse_failure_reply(relay_text)
        target = _RELAY_REPLY_TARGET.search(relay_text)
        if target:
            host, port = target.group('host'), target.group('port')
            detail = target.group('detail').strip()
        else:
            detail = relay_text.split(':', 1)[-1].strip()
        step = tokens.get('step', 'unknown')
        reason = tokens.get('reason') or ('timeout' if 'timed out' in relay_text else 'error')
        hint = tokens.get('hint', '')
        seconds = tokens.get('seconds', '')
    else:
        hop = 'relay' if via_relay else 'provider_direct'
        step = getattr(exc, 'dlux_step', None) or 'unknown'
        reason = smtp_session.failure_reason(exc)
        detail = ' '.join(str(exc).split()) or exc.__class__.__name__
        if reason == 'rejected':
            detail = smtp_session.server_detail(exc)
        if reason == 'timeout':
            seconds = client_timeout
        if hop == 'provider_direct':
            hint = smtp_session.failure_hint(step, reason, port, effective.get('use_tls'), effective.get('use_ssl'))

    if hop == 'relay':
        target = strings.get('email_fail_target_relay', 'the relay service')
    elif host:
        target = f"{host}:{port}" if port else host
    else:
        target = strings.get('email_fail_target_provider', 'the provider')

    hop_text = strings.get(f'email_fail_hop_{hop}', hop)
    step_text = strings.get(f'email_fail_step_{step}', strings.get('email_fail_step_unknown', 'delivery to {target}'))
    if reason == 'timeout' and not seconds:
        reason_key = 'email_fail_reason_timeout_plain'
    else:
        reason_key = f'email_fail_reason_{reason}'
    reason_text = strings.get(reason_key, strings.get('email_fail_reason_error', '{detail}'))
    message = strings.get('email_fail_message', '{hop}: {step} failed — {reason}.').format(
        hop=hop_text,
        step=step_text.format(target=target),
        reason=reason_text.format(seconds=seconds, detail=detail or reason),
    )
    if hint:
        hint_key = f'email_fail_hint_{hint}'
        relay_env_route = effective.get('source') == 'relay_env' or effective.get('internal_relay')
        if relay_env_route and hint in {'implicit_tls', 'starttls_port', 'credentials', 'tls_verify'}:
            hint_key += '_env'
        hint_text = strings.get(hint_key, '')
        if hint_text:
            message = f"{message} {hint_text.format(port=port)}"
    return {'hop': hop, 'step': step, 'reason': reason, 'hint': hint, 'message': message}

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
        try:
            reason = describe_mail_failure(error, get_strings('en'))['message']
        except Exception:
            reason = str(error)
        message = (
            f"Transactional email failed to send (subject: {subject or '—'}; "
            f"to: {attempted}). Error: {reason[:300]}"
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

        log_activity('email_delivery_failed', details={'subject': subject or '', 'error': reason[:300]}, category='audit')
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
            backend='dlux.utils.mail.DluxSMTPBackend',
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


# Email Runtime - Hands mail work to the task worker, or runs it here once the caller commits.
def dispatch_mail_task(task_name, args, inline, *, kwargs=None, sensitive=False):
    """Run mail work off the request path; True unless an inline run already failed.

    With a live ``dlux_worker`` the work is queued as ``task_name`` on the mail
    queue, inside the caller's transaction, so the worker sees it once that
    commits and picks it up within a poll interval (1 s) on the thread every
    worker keeps for mail. Without one, ``inline()`` runs here after the caller's
    transaction commits (at once outside a transaction), so a slow provider never
    holds a transaction open. Exceptions from ``inline`` are logged, not raised.
    """
    from ..taskrunner import enqueue, worker_alive
    from ..taskrunner.config import MAIL_PRIORITY, MAIL_QUEUE

    if worker_alive():
        try:
            # A savepoint: a failed insert must not break the caller's transaction.
            with transaction.atomic():
                enqueue(task_name, args=args, kwargs=kwargs, priority=MAIL_PRIORITY,
                        queue_name=MAIL_QUEUE, sensitive=sensitive)
            return True
        except Exception:
            logger.warning("Could not queue %s; running it in this process instead.", task_name, exc_info=True)

    outcome = {}

    def run_inline():
        try:
            inline()
        except Exception:
            outcome['ok'] = False
            logger.warning("Inline %s failed.", task_name, exc_info=True)
        else:
            outcome['ok'] = True

    transaction.on_commit(run_inline)
    return outcome.get('ok', True)


# Email Runtime - Function queues Dlux transactional mail so no request waits on SMTP.
def queue_dlux_mail(subject, message, recipient_list, *, from_email=None, alert_on_failure=True):
    """Send Dlux mail through ``dlux_worker`` (``dlux.tasks.send_mail``), or here after commit.

    The arguments are sealed at rest in the queue (OTP codes and reset links are
    secrets) and cleared when the run ends. A failed send alerts the configured
    failure recipients (``alert_on_failure``) and fails the run; it never raises
    into the caller. Returns False when the message cannot go (no recipient) or an
    inline send already failed, else True.
    """
    recipients = [str(address).strip() for address in (recipient_list or []) if str(address or '').strip()]
    if not recipients:
        return False
    return dispatch_mail_task(
        'dlux.tasks.send_mail',
        [subject, message, recipients],
        lambda: send_dlux_mail(subject, message, recipients, from_email=from_email, alert_on_failure=alert_on_failure),
        kwargs={'from_email': from_email, 'alert_on_failure': alert_on_failure},
        sensitive=True,
    )
