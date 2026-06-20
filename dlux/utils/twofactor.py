"""dlux.utils.twofactor — TOTP shared-secret encryption and profile 2FA state.

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

TOTP_SECRET_PREFIX = 'fernet$'

_UNSET = object()

# Two-Factor Secrets - Helper derives the encryption seed for TOTP secrets.
def _totp_secret_seed():
    configured_key = (
        os.getenv('DLUX_TOTP_SECRET_KEY')
        or os.getenv('DLUX_SECRET_KEY')
        or getattr(settings, 'DLUX_TOTP_SECRET_KEY', '')
        or getattr(settings, 'SECRET_KEY', '')
    )
    return str(configured_key or 'dlux-totp-secret-dev-key')

# Two-Factor Secrets - Helper builds the Fernet instance for TOTP secret encryption.
def _totp_fernet():
    from cryptography.fernet import Fernet

    digest = hashlib.sha256(_totp_secret_seed().encode('utf-8')).digest()
    return Fernet(base64.urlsafe_b64encode(digest))

# Two-Factor Secrets - Function detects encrypted TOTP payload markers.
def is_encrypted_totp_secret(value):
    return isinstance(value, str) and value.startswith(TOTP_SECRET_PREFIX)

# Two-Factor Secrets - Function encrypts raw TOTP shared secrets.
def encrypt_totp_secret(raw_secret):
    raw_secret = str(raw_secret or '').strip()
    if not raw_secret:
        return ''
    if is_encrypted_totp_secret(raw_secret):
        return raw_secret
    encrypted = _totp_fernet().encrypt(raw_secret.encode('utf-8')).decode('utf-8')
    return f'{TOTP_SECRET_PREFIX}{encrypted}'

# Two-Factor Secrets - Function decrypts TOTP secrets and tolerates legacy plaintext.
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

# Two-Factor Secrets - Function returns a profile TOTP secret in usable plaintext.
def get_profile_totp_secret(profile):
    return decrypt_totp_secret(getattr(profile, 'totp_secret', ''))

# Two-Factor Secrets - Function updates encrypted TOTP state on a profile.
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
