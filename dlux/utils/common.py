"""dlux.utils.common — Shared, cross-feature leaf helpers (used by 2+ features).

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

SENSITIVE_ACTIVITY_MASK = "********"

# Asset URLs - Helper turns stored media/static values into browser-safe paths.
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

# User Roles - Function checks staff status defensively.
def is_staff(user):
    return user.is_staff

# User Roles - Function checks superuser status defensively.
def is_superuser(user):
    return user.is_superuser

# Scopes - Function returns a user scope from profile or direct attribute.
def get_user_scope(user):
    """Return the user's scope from profile first, then direct attribute."""
    if not user:
        return None
    profile = get_user_profile(user)
    if profile and getattr(profile, 'scope', None):
        return profile.scope
    return getattr(user, 'scope', None)

# User Profiles - Function returns a related profile when one exists.
def get_user_profile(user):
    """Return the related profile when it exists; missing profiles fail closed elsewhere."""
    if not user:
        return None
    try:
        return getattr(user, 'profile', None)
    except Exception:
        return None

# Scopes - Function verifies whether a user has explicit scoped state.
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

# Permissions - Helper normalizes permission codenames from varied inputs.
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

# Permissions - Helper extracts permission codenames from prefetched user data.
def _get_prefetched_permission_codenames(user):
    prefetched = getattr(user, '_prefetched_objects_cache', None)
    if not isinstance(prefetched, dict):
        return None
    if 'user_permissions' not in prefetched or 'groups' not in prefetched:
        return None

    permissions = set()
    for permission in prefetched.get('user_permissions') or []:
        content_type = getattr(permission, 'content_type', None)
        app_label = getattr(content_type, 'app_label', None)
        codename = getattr(permission, 'codename', None)
        if app_label and codename:
            permissions.add(f'{app_label}.{codename}')

    for group in prefetched.get('groups') or []:
        group_prefetched = getattr(group, '_prefetched_objects_cache', {})
        if 'permissions' not in group_prefetched:
            return None
        for permission in group_prefetched.get('permissions') or []:
            content_type = getattr(permission, 'content_type', None)
            app_label = getattr(content_type, 'app_label', None)
            codename = getattr(permission, 'codename', None)
            if app_label and codename:
                permissions.add(f'{app_label}.{codename}')
    return permissions

DEFAULT_LANGUAGE_CATALOG = {
    'en': {'name': 'English', 'dir': 'ltr', 'flag': '🇬🇧'},
    'ar': {'name': 'العربية', 'dir': 'rtl', 'flag': '🇱🇾'},
}

# System Import Export - Helper coerces imported checkbox-like values.
def _coerce_import_bool(value):
    if isinstance(value, str):
        return value.strip().lower() in {'1', 'true', 'yes', 'on'}
    return bool(value)

# User Profiles - Function discovers models linked one-to-one to users.
def get_user_linked_models():
    """
    Finds all models across the Django project that have a OneToOneField 
    pointing to settings.AUTH_USER_MODEL, excluding dlux.Profile.
    Returns: list of dicts with model identifiers.
    """
    from django.contrib.auth import get_user_model
    linked_models = []
    
    User = get_user_model()
    for model in apps.get_models():
        # Exclude the internal dlux profile since it's already auto-created
        if model._meta.app_label == 'dlux' and model.__name__ == 'Profile':
            continue
        if getattr(model, 'dlux_auto_create_user_profile', True) is False:
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

# Scopes - Function reports whether scope filtering is globally enabled.
def is_scope_enabled():
    """
    Checks if the Scope system is globally enabled.
    Returns:
        bool: True if enabled, False otherwise.
    """
    from django.db.utils import ProgrammingError, OperationalError

    # ScopeSettings.load() is an uncached get_or_create, and this is called once
    # per scoped queryset — dozens of times while rendering one list page, each
    # a database round trip for the same boolean. Memoised on the request rather
    # than cached in the model, because ScopeSettings is deliberately a leaf data
    # module (see BASELINE_DEFERRED_CLUSTERS in test_import_graph) and a
    # process-wide cache would also outlive a test database.
    try:
        from ..middleware import get_current_request

        request = get_current_request()
    except Exception:
        request = None

    if request is not None:
        memo = getattr(request, '_dlux_scope_enabled', None)
        if memo is not None:
            return memo

    try:
        ScopeSettings = apps.get_model('dlux', 'ScopeSettings')
        enabled = ScopeSettings.load().is_enabled
    except (LookupError, ProgrammingError, OperationalError):
        # Fallback if model or table isn't ready (e.g., during migrations or empty DB)
        return False

    if request is not None:
        try:
            request._dlux_scope_enabled = enabled
        except Exception:
            pass
    return enabled


def _iter_queryset_by_pk(qs, chunk_size=200):
    """Yield model rows in bounded primary-key pages without server-side cursors."""
    try:
        chunk_size = int(chunk_size)
    except (TypeError, ValueError):
        chunk_size = 200
    chunk_size = max(1, chunk_size)
    pk_attname = qs.model._meta.pk.attname
    ordered = qs.order_by(pk_attname)
    last_pk = None
    while True:
        page = ordered
        if last_pk is not None:
            page = page.filter(**{f"{pk_attname}__gt": last_pk})
        batch = list(page[:chunk_size])
        if not batch:
            break
        for obj in batch:
            yield obj
        last_pk = getattr(batch[-1], pk_attname)
