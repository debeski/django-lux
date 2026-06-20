"""dlux.utils.activity_log — Activity-log model keys, masking, and action logging.

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
from .config import get_client_ip

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

# Activity Log - Function normalizes model labels into stable translation keys.
def normalize_activity_log_model_key(value):
    raw = str(value or '').strip().lower()
    if not raw:
        return ''
    normalized = re.sub(r'[^a-z0-9]+', '_', raw)
    normalized = re.sub(r'_+', '_', normalized).strip('_')
    return normalized

# Activity Log - Function resolves activity model labels through DLUX_STRINGS.
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

# Activity Log - Function identifies fields that must be masked in audit records.
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

LOG_CATEGORY_USER = 'user'
LOG_CATEGORY_SYSTEM = 'system'
LOG_CATEGORY_AUDIT = 'audit'
_LOG_CATEGORY_VALUES = {LOG_CATEGORY_USER, LOG_CATEGORY_SYSTEM, LOG_CATEGORY_AUDIT}

# Action strings that are always security/audit events, regardless of model.
AUDIT_ACTIONS = {
    'LOGIN', 'LOGOUT', 'LOGIN_FAILED', 'LOCKOUT',
    '2FA_ENABLE', '2FA_DISABLE', '2FA_FAILED',
    'PASSWORD_CHANGE', 'PASSWORD_RESET', 'SESSION_REVOKE',
    'TRUSTED_DEVICE', 'TRUSTED_DEVICE_REVOKE', 'PERMISSION_DENIED',
    'REGISTER_VERIFY', 'APPROVE', 'REJECT',
}

# Locale-display labels (model_key is NULL for these) that denote dlux-internal/system
# events. NOTE: "User Profile" is intentionally NOT here — the merged user-identity entry
# is self-service work and resolves to 'user'.
_SYSTEM_MODEL_NAMES = {
    'session',
    'dlux system backup',
    'dlux reports backup',
}


# Correctness floor: models that must NEVER be logged regardless of config. object_id is an
# IntegerField, so models with non-integer/string PKs would break; plus the log model itself.
LOG_FORCED_EXCLUDED_MODEL_KEYS = {
    'sessions.session',
    'dlux.activitylog',
    'contenttypes.contenttype',
    'admin.logentry',
    'auth.permission',
}

# Synthetic config/catalog key for the unified user identity (User + Profile changes). The
# real auth.user / dlux.profile models are never gated directly; this key drives whether the
# "User Profile" identity entry is logged, and surfaces as a "User accounts" grid toggle.
LOG_IDENTITY_MODEL_KEY = 'dlux.useridentity'

# Django framework apps (plus health-check's `db` app) whose models are internal bookkeeping,
# never project/system activity. Their models are not logged and never appear in the grid.
LOG_NEVER_LOGGED_APP_LABELS = frozenset({'admin', 'auth', 'contenttypes', 'sessions', 'db'})

# Model names that are always noise regardless of app (e.g. django-health-check's TestModel).
LOG_NEVER_LOGGED_MODEL_NAMES = frozenset({'testmodel'})

# dlux models that produce no meaningful activity log: the unified identity Profile, the log
# model itself, the fieldless Section permission placeholder, high-churn device/presence/
# notification state, and backup-run rows. Never logged and never offered as toggles.
LOG_NEVER_LOGGED_MODEL_KEYS = LOG_FORCED_EXCLUDED_MODEL_KEYS | {
    'dlux.profile',
    'dlux.section',
    'dlux.trusteddevice',
    'dlux.userknowndevice',
    'dlux.userpresencesession',
    'dlux.dluxnotification',
    'dlux.dluxnotificationstate',
    'dlux.dluxnotificationrule',
    'dlux.dluxnotificationwatch',
    'dlux.reportbackup',
    'dlux.systembackup',
    'dlux.systemrestore',
}


# Activity Log - Function: is this model eligible to be logged / shown in the settings grid?
def is_model_loggable(model_key, app_label=None):
    """False for the correctness floor, dlux operational/identity/self/dummy models, Django
    framework apps, and health-check/test models — i.e. anything that never produces
    meaningful, user-relevant activity. The synthetic identity key is always loggable."""
    key = str(model_key or '').strip().lower()
    if not key:
        return False
    if key == LOG_IDENTITY_MODEL_KEY:
        return True
    if key in LOG_NEVER_LOGGED_MODEL_KEYS:
        return False
    label = (app_label or (key.split('.', 1)[0] if '.' in key else '')).strip().lower()
    if label in LOG_NEVER_LOGGED_APP_LABELS:
        return False
    if key.rsplit('.', 1)[-1] in LOG_NEVER_LOGGED_MODEL_NAMES:
        return False
    return True


# Activity Log - Function decides whether a model CRUD event should be logged per log_config.
def is_model_logging_enabled(category, model_key, action, log_config):
    """Consult log_config for a model CRUD event. Audit bypasses per-model gating (it is
    governed by its event flags elsewhere). Non-loggable models always return False."""
    key = str(model_key or '').strip().lower()
    if not is_model_loggable(key):
        return False
    if not isinstance(log_config, dict):
        return True
    if not log_config.get('enabled', True):
        return False
    if category == LOG_CATEGORY_AUDIT:
        return True
    section = log_config.get(category)
    if not isinstance(section, dict):
        return True
    if not section.get('enabled', True):
        return False
    act = str(action or '').strip().lower()
    models = section.get('models') if isinstance(section.get('models'), dict) else {}
    override = models.get(key) if key else None
    if isinstance(override, dict):
        if not override.get('enabled', True):
            return False
        actions = override.get('actions') if isinstance(override.get('actions'), dict) else {}
        if act in actions:
            return bool(actions[act])
    default_actions = section.get('default_actions') if isinstance(section.get('default_actions'), dict) else {}
    if act in default_actions:
        return bool(default_actions[act])
    return True


# Activity Log - Function returns the active normalized log_config from system settings.
def get_active_log_config():
    """Resolve the effective log_config for signal gating.

    Reads the cached SystemSettings singleton (falling back to a non-creating query).
    Critically it must NOT create the singleton: this runs inside save/delete signals, and
    a get_or_create here would recreate the row mid-mutation (e.g. during settings reset).
    """
    from ..system.defaults import default_log_config
    try:
        from django.apps import apps
        from django.core.cache import cache
        instance = cache.get('SystemSettings')
        if instance is None:
            SystemSettings = apps.get_model('dlux', 'SystemSettings')
            instance = SystemSettings.objects.filter(pk=1).first()
        if instance is not None and hasattr(instance, 'log_config'):
            from .config import normalize_log_config
            return normalize_log_config(getattr(instance, 'log_config', None))
    except Exception:
        pass
    return default_log_config()


# Activity Log - Function classifies a log row into user/system/audit.
def resolve_log_category(action, model=None, model_key=None, model_name=None, explicit=None):
    """Resolve the log category for an entry. Precedence:
    1. explicit argument, 2. model.dlux_log_category attribute,
    3. security action -> audit, 4. app_label == 'dlux' -> system, 5. default 'user'.
    """
    if explicit in _LOG_CATEGORY_VALUES:
        return explicit

    if model is not None:
        declared = getattr(model, 'dlux_log_category', None)
        if declared in _LOG_CATEGORY_VALUES:
            return declared

    act = str(action or '').strip().upper()
    if act in AUDIT_ACTIONS:
        return LOG_CATEGORY_AUDIT

    app_label = None
    if model is not None:
        app_label = getattr(getattr(model, '_meta', None), 'app_label', None)
    if not app_label and model_key and '.' in str(model_key):
        app_label = str(model_key).split('.', 1)[0].strip().lower()
    if app_label == 'dlux':
        return LOG_CATEGORY_SYSTEM

    if not model_key and model_name and str(model_name).strip().lower() in _SYSTEM_MODEL_NAMES:
        return LOG_CATEGORY_SYSTEM

    return LOG_CATEGORY_USER


# Activity Log - Function records a security/audit event if enabled in log_config.
def log_audit_event(request, event_key, action, *, instance=None, model_name=None,
                    details=None, number=None, object_id=None, model_key=None):
    """Record a security event under the privileged 'audit' category, gated by
    ``log_config['audit']['events'][event_key]``. Returns None when audit logging or the
    specific event is disabled. The actor may be anonymous (e.g. failed login)."""
    log_config = get_active_log_config()
    audit = log_config.get('audit') if isinstance(log_config, dict) else None
    if not isinstance(audit, dict) or not audit.get('enabled', True):
        return None
    events = audit.get('events') if isinstance(audit.get('events'), dict) else {}
    if event_key in events and not events.get(event_key):
        return None
    return log_user_action(
        request, action,
        instance=instance, model_name=model_name, details=details,
        number=number, object_id=object_id, model_key=model_key,
        category=LOG_CATEGORY_AUDIT,
    )


# Activity Log - Function creates normalized audit entries for user actions.
def log_user_action(request, action, instance=None, model_name=None, details=None, number=None, object_id=None, model_key=None, category=None):
    """
    Centralized activity logging. All manual ActivityLog creation should go through here.

    Args:
        request:    Django request object
        action:     Action string (e.g. 'CREATE', 'LOGIN', 'EXPORT')
        instance:   Optional model instance (auto-extracts pk, number, model_name, model_key)
        model_name: Optional override for the display label (used when no instance exists)
        model_key:  Optional override for the stable "app_label.model_name" key
        details:    Optional dict of extra details to attach to log
        number:     Optional override for the document number field
        category:   Optional 'user'/'system'/'audit' override; derived when omitted.
    """
    ActivityLog = apps.get_model('dlux', 'ActivityLog')
    user = getattr(request, 'user', None) if request else None
    if not user or not getattr(user, 'is_authenticated', False):
        try:
            from ..middleware import get_current_user
            user = get_current_user()
        except Exception:
            user = None

    # When an explicit model_name override is given (e.g. "password", "session"), it is a
    # synthetic event label that does not correspond to `instance`'s model, so don't derive
    # the stable key from the instance — keep it None unless the caller passed one.
    if model_name:
        resolved_name = model_name
        resolved_key = model_key
    else:
        resolved_name = instance._meta.verbose_name if instance else None
        resolved_key = model_key or (instance._meta.label_lower if instance else None)

    return ActivityLog.safe_log(
        user=user,
        action=action,
        model_name=resolved_name,
        model_key=resolved_key,
        object_id=object_id if object_id is not None else (instance.pk if instance else None),
        number=number or (getattr(instance, 'number', '') if instance else None),
        details=details,
        ip_address=get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
        category=category,
    )
