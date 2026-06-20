"""dlux.utils.localization — Translation layer merging and language-catalog normalize.

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
from .common import DEFAULT_LANGUAGE_CATALOG

# Localization - Helper deep-merges translation dictionaries by language.
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

# Localization - Helper merges language catalog metadata across config layers.
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

# Localization - Helper canonicalizes supported language codes.
def _normalize_language_code(code):
    normalized = str(code or '').strip().lower().replace('_', '-')
    if not normalized:
        return ''
    if not re.match(r'^[a-z]{2,3}(?:-[a-z0-9]{2,8})?$', normalized):
        return ''
    return normalized

# Localization - Function validates enabled language catalog settings.
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
