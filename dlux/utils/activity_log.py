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
from ..constants import (
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

# Activity Log - Function creates normalized audit entries for user actions.
def log_user_action(request, action, instance=None, model_name=None, details=None, number=None, object_id=None, model_key=None):
    """
    Centralized activity logging. All manual UserActivityLog creation should go through here.

    Args:
        request:    Django request object
        action:     Action string (e.g. 'CREATE', 'LOGIN', 'EXPORT')
        instance:   Optional model instance (auto-extracts pk, number, model_name, model_key)
        model_name: Optional override for the display label (used when no instance exists)
        model_key:  Optional override for the stable "app_label.model_name" key
        details:    Optional dict of extra details to attach to log
        number:     Optional override for the document number field
    """
    UserActivityLog = apps.get_model('dlux', 'UserActivityLog')
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

    UserActivityLog.safe_log(
        user=user,
        action=action,
        model_name=resolved_name,
        model_key=resolved_key,
        object_id=object_id if object_id is not None else (instance.pk if instance else None),
        number=number or (getattr(instance, 'number', '') if instance else None),
        details=details,
        ip_address=get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
    )
