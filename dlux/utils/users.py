"""dlux.utils.users — User management tiers, profiles, and scope helpers.

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
from .common import _get_prefetched_permission_codenames, _normalize_permission_codename_set, get_user_scope, is_staff, is_superuser, user_has_scope_state

# User Management - Function removes Global Staff users from querysets.
def exclude_global_staff_users(queryset):
    """Exclude users who have the Global Staff `manage_scopes` permission."""
    return queryset.exclude(
        user_permissions__content_type__app_label='dlux',
        user_permissions__codename='manage_scopes',
    ).exclude(
        groups__permissions__content_type__app_label='dlux',
        groups__permissions__codename='manage_scopes',
    ).distinct()

# User Management - Function removes Global Staff elevation from permission lists.
def strip_manage_scopes_permissions(permissions):
    """Return a permission list with Dlux Global Staff elevation removed."""
    return [
        permission
        for permission in permissions
        if not (
            getattr(permission, 'codename', None) == 'manage_scopes'
            and getattr(getattr(permission, 'content_type', None), 'app_label', None) == 'dlux'
        )
    ]

# User Management - Function enforces staff-tier rules for managing another user.
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

# User Management - Function detects the Global Staff tier.
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
    return user.has_perm('dlux.manage_scopes')

# User Management - Function detects the Central Staff tier.
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
    return not user.has_perm('dlux.manage_scopes')

# User Management - Function classifies a user-management tier from booleans and permissions.
def get_user_management_tier_state(
    *,
    is_superuser,
    is_staff,
    scope,
    permission_codenames,
    strings=None,
):
    """
    Classify the current user-management tier without changing authorization rules.

    The returned payload is intentionally UI-friendly so forms, tables, and templates
    can present the same tier language consistently.
    """
    s = strings or get_strings()
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

# User Management - Function builds the current management tier state for a user.
def get_user_management_tier_state_for_user(user, strings=None):
    if not user or not getattr(user, 'is_authenticated', False):
        return get_user_management_tier_state(
            is_superuser=False,
            is_staff=False,
            scope=None,
            permission_codenames=set(),
            strings=strings,
        )

    permission_codenames = set()
    try:
        permission_codenames = _get_prefetched_permission_codenames(user)
        if permission_codenames is None:
            permission_codenames = user.get_all_permissions()
    except Exception:
        permission_codenames = set()

    return get_user_management_tier_state(
        is_superuser=bool(getattr(user, 'is_superuser', False)),
        is_staff=bool(getattr(user, 'is_staff', False)),
        scope=get_user_scope(user),
        permission_codenames=permission_codenames,
        strings=strings,
    )
