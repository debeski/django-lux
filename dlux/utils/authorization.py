"""dlux.utils.authorization — Permission checks, tokens, and staff/role predicates.

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
from .common import get_user_scope, user_has_scope_state
from .users import can_manage_target_user

# Authorization - Function gates access to user directory surfaces.
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
    return user.has_perm('auth.view_user') or user.has_perm('dlux.manage_staff')

# Authorization - Function gates access to activity logs.
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
    return user.has_perm('dlux.view_activitylog') or user.has_perm('dlux.view_activity_log')

# Authorization - Function gates detailed user reports.
def user_can_view_user_report(actor, target_user=None):
    """
    Full user reports expose activity, network, and device history.
    Require both user-management visibility and activity-log access.
    A user may always view their own report (self-service).
    """
    if (
        actor is not None
        and getattr(actor, 'is_authenticated', False)
        and target_user is not None
        and target_user.pk == actor.pk
    ):
        return True
    if not user_can_view_user_directory(actor):
        return False
    if not user_can_view_activity_log(actor):
        return False
    return can_manage_target_user(actor, target_user)

# Authorization - Function gates project-level report overviews.
def user_can_view_reports(user):
    """
    Project-level report overview access.
    This is staff-only and explicit, unlike the self-service per-user report.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    if not getattr(user, 'is_staff', False):
        return False
    return user.has_perm('dlux.view_reports')

# Authorization - Function gates backup download permissions.
def user_can_download_backup(user):
    """
    Backup ZIP access is intentionally separate from report viewing.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    if not getattr(user, 'is_staff', False):
        return False
    return user.has_perm('dlux.download_backup')

# Authorization - Function checks section view access.
def user_has_section_view_permission(user):
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    return user.has_perm('dlux.view_sections') or user.has_perm('dlux.manage_sections')

# Authorization - Function checks section management access.
def user_has_section_manage_permission(user):
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    return user.has_perm('dlux.manage_sections')

# Authorization - Function checks a Django model action permission.
def user_has_model_permission(user, model, action):
    """Return True when the user has the Django model permission for the given action."""
    if not user or not getattr(user, 'is_authenticated', False) or not model or not action:
        return False
    if getattr(user, 'is_superuser', False):
        return True
    permission = f'{model._meta.app_label}.{action}_{model._meta.model_name}'
    return user.has_perm(permission)

# Authorization - Function resolves Dlux permission tokens and Django permissions.
def user_matches_permission_token(user, permission):
    """
    Resolve Dlux-internal permission tokens plus normal Django permission strings.

    Internal tokens are used by discovery/sidebar/template-adjacent code so those
    surfaces can stay aligned with the newer DSRP authorization helpers.
    """
    if not permission:
        return True
    if not user or not getattr(user, 'is_authenticated', False):
        return False

    if permission == 'is_staff':
        return bool(getattr(user, 'is_staff', False))
    if permission == 'is_superuser':
        return bool(getattr(user, 'is_superuser', False))
    if permission == '__dlux_authenticated__':
        return True
    if permission == '__dlux_user_directory__':
        return user_can_view_user_directory(user)
    if permission == '__dlux_activity_log__':
        return user_can_view_activity_log(user)
    if permission == '__dlux_sections_view__':
        return user_has_section_view_permission(user)
    if permission == '__dlux_sections_manage__':
        return user_has_section_manage_permission(user)

    return bool(user.has_perm(permission))

# Authorization - Function tests whether any configured permission token grants access.
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
