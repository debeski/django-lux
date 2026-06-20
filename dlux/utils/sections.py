"""dlux.utils.sections — Section model discovery and minimal instance creation.

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
from .common import get_user_scope, is_scope_enabled
from .crud import _build_generic_filter_class, _build_generic_table_class
from .discovery import _import_by_convention, _resolve_model_class, resolve_form_class_for_model

# Sections - Helper detects explicit section model declarations.
def _model_is_section(model):
    """
    Determine if a model should be treated as a section model.
    Accepts class attr, Meta attr, or any non-falsey marker.
    """
    val = getattr(model, 'is_section', None)
    if isinstance(val, bool):
        return val
    if val is not None:
        return True
    return bool(getattr(model._meta, 'is_section', False))

# Sections - Helper identifies models primarily linked through parent M2M fields.
def _is_child_model(model, app_name=None):
    """
    Detect if a model is a "child model" - one that exists primarily 
    to be linked via M2M to a parent model.
    
    A model is considered a child if:
    - It has a ManyToManyRel (is the target of a M2M from another model)
    - It doesn't have its own table classmethod (won't be displayed standalone)
    """
    meta = model._meta
    
    # Check if this model is referenced via M2M from another model
    has_m2m_rel = any(
        isinstance(f, ManyToManyRel) 
        for f in meta.get_fields()
    )
    
    # Check if model lacks table classmethod (not meant for standalone display)
    lacks_table = not hasattr(model, 'get_table_class_path') and not hasattr(model, 'get_table_class')
    
    return has_m2m_rel and lacks_table

# Sections - Function discovers configured section models and optional children.
def discover_section_models(app_name=None, include_children=False):
    """
    Discover section models based on explicit `is_section = True` in class/meta.
    Automatically resolves Form, Table, and Filter classes (by convention or generation).
    Identifies 'subsection' models (M2M children) for automatic modal handling.
    
    Args:
        app_name: Optional. If provided, filter results to this app only.
        include_children: If True, includes child models (M2M targets) even if not
                          explicitly marked as sections. Default False.
    
    Returns:
        List of dicts containing section model info:
        {
            'model': Model class,
            'model_name': Model name (lowercase),
            'app_label': App label,
            'verbose_name': Arabic verbose name,
            'verbose_name_plural': Arabic verbose name plural,
            'form_class': Form class (imported or generated),
            'table_class': Table class (imported or generated),
            'filter_class': Filter class (imported or generated),
            'subsections': List of dicts for child models (M2M targets):
                {
                    'model': ChildModel,
                    'model_name': ...,
                    'verbose_name': ...,
                    'related_field': field_name (in parent),
                    'form_class': ChildFormClass (imported or generated)
                }
        }
    """
    section_models = []
    
    # Get app configs to iterate
    if app_name:
        try:
            app_configs = [apps.get_app_config(app_name)]
        except LookupError:
            return []
    else:
        app_configs = apps.get_app_configs()
    
    for app_config in app_configs:
        # Skip Django's built-in apps
        if app_config.name.startswith('django.'):
            continue
        
        for model in app_config.get_models():
            meta = model._meta
            
            # SKIP: Dummy models (managed = False)
            if not meta.managed:
                continue
            
            # SKIP: Abstract models
            if meta.abstract:
                continue
            
            # Detect if this is a child model (M2M target without table)
            is_child = _is_child_model(model, app_config.label)

            # Include models explicitly marked as sections, plus children if requested
            is_section = _model_is_section(model)
            if not is_section and not (include_children and is_child):
                continue
            
            # --- Resolve Classes (Form, Table, Filter) ---
            # 1. Form
            form_class = resolve_form_class_for_model(model)

            # 2. Table
            table_class = _import_by_convention(model, "tables", "Table")
            if not table_class:
                # Fallback: legacy methods
                table_class = (
                    _resolve_model_class(model, "get_table_class")
                    or _resolve_model_class(model, "get_table_class_path")
                )
            
            # Generate if not found
            if not table_class:
                 table_class = _build_generic_table_class(model)

            # 3. Filter
            filter_class = _import_by_convention(model, "filters", "Filter")
            if not filter_class:
                # Fallback
                filter_class = (
                    _resolve_model_class(model, "get_filter_class")
                    or _resolve_model_class(model, "get_filter_class_path")
                )
            
            # Generate if not found (optional, requires django_filters)
            if not filter_class and django_filters:
                 filter_class = _build_generic_filter_class(model)

            # --- Identify Subsections (M2M Children) ---
            subsections = []
            for field in meta.get_fields():
                if isinstance(field, ManyToManyField):
                    child_model = field.related_model
                    child_meta = child_model._meta
                    
                    # Verify it's a "subsection/child" type model
                    if _is_child_model(child_model):
                         # Resolve child form for the "Add" modal
                         child_form_class = resolve_form_class_for_model(child_model)
                             
                         subsections.append({
                             'model': child_model,
                             'model_name': child_meta.model_name,
                             'verbose_name': child_meta.verbose_name,
                             'verbose_name_plural': child_meta.verbose_name_plural,
                             'related_field': field.name,
                             'form_class': child_form_class
                         })

            section_models.append({
                'model': model,
                'model_name': meta.model_name,
                'app_label': meta.app_label,
                'verbose_name': meta.verbose_name,
                'verbose_name_plural': meta.verbose_name_plural,
                'form_class': form_class,
                'table_class': table_class,
                'filter_class': filter_class,
                'subsections': subsections,
                'is_child': is_child,
            })
    
    return section_models

# Sections - Function reports whether section models are available.
@lru_cache(maxsize=None)
def has_section_models(app_name=None):
    """
    Return True when at least one model is explicitly marked as a section model.
    """
    if app_name:
        try:
            app_configs = [apps.get_app_config(app_name)]
        except LookupError:
            return False
    else:
        app_configs = apps.get_app_configs()

    for app_config in app_configs:
        if app_config.name.startswith('django.'):
            continue

        for model in app_config.get_models():
            meta = model._meta
            if not meta.managed or meta.abstract:
                continue
            if _model_is_section(model):
                return True

    return False

# Sections - Function chooses the first available section model name.
def get_default_section_model(app_name=None):
    """
    Get the first available section model name for auto-selection.
    
    Returns:
        String model_name of the first section model, or None if none found.
    """
    section_models = discover_section_models(app_name=app_name)
    if section_models:
        return section_models[0]['model_name']
    return None

# Sections - Helper prepares scoped through-model defaults for M2M additions.
def _get_m2m_through_defaults(model, field_name, request):
    """
    Provide through_defaults for M2M relations when the through model is scoped.
    This prevents relations from disappearing when scope filtering is enabled.
    """
    try:
        field = model._meta.get_field(field_name)
    except FieldDoesNotExist:
        return None

    # Only M2M fields can have through tables
    if not getattr(field, "many_to_many", False):
        return None

    through = field.remote_field.through
    if not through:
        return None

    defaults = {}
    if is_scope_enabled():
        scope = get_user_scope(request.user)
        if scope:
            try:
                through._meta.get_field('scope')
                defaults['scope'] = scope
            except Exception:
                pass

    return defaults or None

# Sections - Helper creates inline child records from POST data.
def _create_minimal_instance_from_post(model, data, request):
    """
    Fallback: create a minimal instance from POST data when a simple
    inline add is used (e.g., just a `name` field).
    Only proceeds if all required concrete fields are present.
    """
    field_map = {}
    missing_required = []

    # Identify truly required fields (skip auto-managed and optional ones)
    for field in model._meta.fields:
        if field.primary_key or field.auto_created:
            continue
        if getattr(field, "auto_now", False) or getattr(field, "auto_now_add", False):
            continue
        if field.has_default() or field.blank or field.null:
            continue

        if field.name not in data:
            missing_required.append(field.name)

    if missing_required:
        return None, missing_required

    for field in model._meta.fields:
        if field.primary_key or field.auto_created:
            continue
        if field.name in data:
            if isinstance(field, dj_models.ForeignKey):
                try:
                    field_map[field.name] = field.remote_field.model.objects.get(pk=data[field.name])
                except Exception:
                    return None, [field.name]
            else:
                field_map[field.name] = data[field.name]

    instance = model(**field_map)
    # created_by auto-populated by ScopedModel.save()
    # Ensure scope is set for scoped models
    if is_scope_enabled() and hasattr(instance, 'scope'):
        try:
            user_scope = getattr(getattr(request.user, 'profile', None), 'scope', None)
            if not user_scope and hasattr(request.user, 'scope'):
                user_scope = request.user.scope
            # Non-superusers always get their scope forced; superusers only if unset
            if user_scope:
                if not request.user.is_superuser:
                    instance.scope = user_scope
                elif not getattr(instance, 'scope', None):
                    instance.scope = user_scope
        except Exception:
            pass
    instance.save()
    return instance, []
