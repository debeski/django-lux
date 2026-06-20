"""dlux.utils.discovery — Model discovery, relation checks, and model-form resolution.

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
from .common import is_scope_enabled
from .crud import _build_generic_filter_class, _build_generic_table_class

# Model Discovery - Helper casefolds names for fuzzy model lookup.
def _normalize_fuzzy_string(s):
    return unicodedata.normalize('NFKD', str(s)).casefold() if s else ""

# Model Discovery - Helper caches fuzzy model identifiers to model classes.
@lru_cache(maxsize=1)
def _get_fuzzy_model_mapping():
    """Builds a cached mapping of normalized model names to model classes."""
    mapping = {}
    for model in apps.get_models():
        # 1. Exact app_label.model_name
        full_path = f"{model._meta.app_label}.{model._meta.model_name}".lower()
        mapping[full_path] = model
        
        # 2. Object name (Class name)
        obj_name = _normalize_fuzzy_string(model._meta.object_name)
        if obj_name and obj_name not in mapping:
            mapping[obj_name] = model
            
        # 3. Verbose name
        v_name = _normalize_fuzzy_string(model._meta.verbose_name)
        if v_name and v_name not in mapping:
            mapping[v_name] = model
            
    return mapping

# Model Discovery - Helper lists import bases for a model app.
def _get_model_app_bases(model):
    """
    Return possible import bases for a model's app.
    Uses AppConfig.name (full python path) and falls back to module/app_label.
    """
    bases = []
    try:
        app_config = apps.get_app_config(model._meta.app_label)
        if app_config and app_config.name:
            bases.append(app_config.name)
    except LookupError:
        pass

    module_base = model.__module__.rsplit('.', 1)[0]
    if module_base not in bases:
        bases.append(module_base)

    if model._meta.app_label not in bases:
        bases.append(model._meta.app_label)

    return bases

# Model Discovery - Helper imports conventional model-adjacent classes.
def _import_by_convention(model, submodule, class_suffix):
    """
    Try importing a class following App.<submodule>.ModelName<class_suffix>.
    Returns class or None if not found.
    """
    class_name = f"{model.__name__}{class_suffix}"
    for base in _get_model_app_bases(model):
        try:
            return import_string(f"{base}.{submodule}.{class_name}")
        except ImportError:
            continue
    return None

# Model Discovery - Helper resolves model-provided class references.
def _resolve_model_class(model, getter_name):
    """
    Resolve class from model method/attr that may return a class or a string path.
    """
    if not hasattr(model, getter_name):
        return None

    try:
        value = getattr(model, getter_name)
        value = value() if callable(value) else value
    except Exception:
        return None

    if isinstance(value, str):
        try:
            return import_string(value)
        except (ImportError, ValueError, AttributeError, TypeError):
            return None

    if inspect.isclass(value):
        return value

    return None

# System Variables for Model Classes Caching
_MODEL_CLASSES_CACHE = {}

# Model Discovery - Class lazily resolves form, table, and filter classes.
class LazyModelClasses(dict):
    """
    Lazy dictionary that only resolves model classes (form, table, filter)
    when they are explicitly requested, and caches them for subsequent accesses.
    """
    # Model Discovery - Method stores the model and optional explicit class overrides.
    def __init__(self, model, overrides=None):
        self._model = model
        
        # Merge model-level registry/overrides with explicit overrides
        model_overrides = getattr(model, 'model_classes_overrides', {})
        self._overrides = {**model_overrides, **(overrides or {})}
        
        super().__init__({
            'model': model,
            'verbose_name': model._meta.verbose_name,
            'verbose_name_plural': model._meta.verbose_name_plural,
        })

    # Model Discovery - Method normalizes lazy lookup keys.
    @staticmethod
    def _normalize_key(key):
        aliases = {
            'form_class': 'form',
            'table_class': 'table',
            'filter_class': 'filter',
        }
        return aliases.get(key, key)
        
    # Model Discovery - Method resolves and caches requested class entries.
    def __getitem__(self, key):
        key = self._normalize_key(key)
        if super().__contains__(key):
            return super().__getitem__(key)
            
        if key == 'form':
            val = self._resolve_form()
        elif key == 'table':
            val = self._resolve_table()
        elif key == 'filter':
            val = self._resolve_filter()
        else:
            raise KeyError(key)
            
        self[key] = val
        return val

    # Model Discovery - Method returns resolved class entries with default fallback.
    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    # Model Discovery - Method reports supported lazy class keys.
    def __contains__(self, key):
        key = self._normalize_key(key)
        if super().__contains__(key):
            return True
        return key in ('form', 'table', 'filter')

    # Model Discovery - Method returns configured class overrides when present.
    def _get_override_or_none(self, key):
        if key in self._overrides:
            val = self._overrides[key]
            if isinstance(val, str):
                try:
                    return import_string(val)
                except Exception:
                    pass
            return val
        return None

    # Model Discovery - Method resolves the form class for the current model.
    def _resolve_form(self):
        override = self._get_override_or_none('form')
        if override: return override
        
        form_class = _import_by_convention(self._model, "forms", "Form")
        if not form_class:
            form_class = resolve_form_class_for_model(self._model)
        return form_class
        
    # Model Discovery - Method resolves the table class for the current model.
    def _resolve_table(self):
        override = self._get_override_or_none('table')
        if override: return override
        
        table_class = _import_by_convention(self._model, "tables", "Table")
        if not table_class:
             table_class = _resolve_model_class(self._model, "get_table_class")
        if not table_class:
             table_class = _build_generic_table_class(self._model)
        return table_class
        
    # Model Discovery - Method resolves the filter class for the current model.
    def _resolve_filter(self):
        override = self._get_override_or_none('filter')
        if override: return override
        
        filter_class = _import_by_convention(self._model, "filters", "Filter")
        if not filter_class:
             filter_class = _resolve_model_class(self._model, "get_filter_class")
        if not filter_class and django_filters:
             filter_class = _build_generic_filter_class(self._model)
        return filter_class

# Model Discovery - Function resolves model, form, table, and filter classes.
def get_model_classes(model_name, app_label=None, overrides=None):
    """
    Dynamically import model, form, table, and filter classes for a given model
    following standard naming conventions. Uses lazy loading and caching.
    """
    if not model_name:
        return None
        
    cache_key = f"{app_label or 'any'}:{model_name}"
    
    # Check cache first if no explicit request-level overrides are provided
    if not overrides and cache_key in _MODEL_CLASSES_CACHE:
        return _MODEL_CLASSES_CACHE[cache_key]
    
    # Resolve Model
    model = resolve_model_by_name(model_name, app_label=app_label)
    if not model:
        # Try to resolve by model_name directly if it might be a full path
        if '.' in model_name:
            try:
                model = apps.get_model(model_name)
            except:
                return None
        else:
            return None
            
    lazy_classes = LazyModelClasses(model, overrides=overrides)
    
    if not overrides:
        _MODEL_CLASSES_CACHE[cache_key] = lazy_classes
        
    return lazy_classes

# Model Discovery - Function resolves models by name, label, or fuzzy match.
def resolve_model_by_name(model_name, app_label=None):
    """
    Resolve a model by name, optionally constrained to an app label.
    Falls back to fuzzy matching against cached registry if app_label is not provided.
    """
    if not model_name:
        return None

    if not isinstance(model_name, str):
        return model_name

    if app_label:
        try:
            return apps.get_model(app_label, model_name)
        except LookupError:
            return None

    # First, try standard Django app registry if it looks like app_label.model
    if '.' in model_name:
        try:
            return apps.get_model(model_name)
        except (LookupError, ValueError):
            pass

    # Fallback to fuzzy matching against cached registry
    norm_name = _normalize_fuzzy_string(model_name)
    return _get_fuzzy_model_mapping().get(norm_name)

# Model Discovery - Function imports a class from a dotted path.
def get_class_from_string(class_path):
    """Dynamically imports and returns a class from a string path."""
    return import_string(class_path)

# Model Forms - Function resolves a model form class or creates a fallback.
def resolve_form_class_for_model(model):
    """
    Resolve a ModelForm class for a model using conventions or fallbacks.
    """
    form_class = _import_by_convention(model, "forms", "Form")
    if not form_class:
        form_class = (
            _resolve_model_class(model, "get_form_class")
            or _resolve_model_class(model, "get_form_class_path")
        )

    # Prepare widgets with autofill attributes for ForeignKeys (Global)
    widgets = {}
    for field in model._meta.get_fields():
        if field.is_relation and (field.many_to_one or field.one_to_one) and field.related_model:
            # Provide the "app_label.model_name" as source
            source = f"{field.related_model._meta.app_label}.{field.related_model._meta.model_name}"
            from django.forms import Select
            widgets[field.name] = Select(attrs={'data-autofill-source': source})

    try:
        has_scope_field = model._meta.get_field("scope") is not None
    except Exception:
        has_scope_field = False

    if form_class:
        # Wrap custom form to inject widgets
        # We explicitly pass fields=None to let it infer from the base form
        try:
            form_class = modelform_factory(model, form=form_class, widgets=widgets)
        except Exception:
            # Fallback for edge cases (e.g. already processed or incompatible)
            pass
    else:
        # Generate generic form
        raw_exclude = getattr(model, "form_exclude", None)
        if raw_exclude is None:
            raw_exclude = []
        elif isinstance(raw_exclude, (str, bytes)):
            raw_exclude = [raw_exclude]
        else:
            raw_exclude = list(raw_exclude)

        # Default exclusions for audit fields
        audit_fields = ['created_at', 'updated_at', 'deleted_at', 'created_by', 'updated_by', 'deleted_by']
        raw_exclude.extend([f for f in audit_fields if f not in raw_exclude])

        if raw_exclude:
            exclude = list(dict.fromkeys(raw_exclude))
            form_class = modelform_factory(model, exclude=exclude, widgets=widgets)
        else:
            form_class = modelform_factory(model, fields='__all__', widgets=widgets)

    if has_scope_field:
        # Model Forms - Class injects request-aware scope defaults into generated forms.
        class ScopeDynamicForm(form_class):
            # Model Forms - Method removes unmanaged request kwargs before Django form init.
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                if 'scope' in self.fields and not is_scope_enabled():
                    del self.fields['scope']
        form_class = ScopeDynamicForm

    return form_class

# Relations - Function checks whether an instance has protected related records.
def has_related_records(instance, ignore_relations=None):
    """
    Check if a model instance has any related records (FK, M2M, OneToOne).
    Returns True if any related objects exist, False otherwise.
    Used for locking logic (preventing deletion/unlinking).
    
    ignore_relations: list of accessor names to skip (e.g. ['affiliates', 'company_set'])
    
    Note: Automatically ignores M2M relations where this model is the 'child' 
    (i.e., the target of a ManyToManyField from a parent section model).
    This includes the M2M reverse accessor AND any FK from through tables
    (both auto-created and custom through models like AffiliateDepartment).
    """
    from django.db.models.fields.related import ManyToManyRel, ManyToOneRel
    
    if not instance:
        return False
    
    if ignore_relations is None:
        ignore_relations = []
    
    # Auto-detect M2M parent relations to ignore
    # Step 1: Collect all through-table models from M2M relationships pointing at us
    auto_ignore = set()
    through_models = set()
    
    for field in instance._meta.get_fields():
        if isinstance(field, ManyToManyRel):
            # This is the "reverse" side of a M2M - the parent points to us
            accessor_name = field.get_accessor_name()
            if accessor_name:
                auto_ignore.add(accessor_name)
            # Track through table (works for both auto-created and custom)
            if hasattr(field, 'through') and field.through:
                through_models.add(field.through)
    
    # Step 2: Any ManyToOneRel whose source model is a known through table
    # should also be ignored (the FK from the through table to this model)
    for field in instance._meta.get_fields():
        if isinstance(field, ManyToOneRel):
            if field.related_model in through_models:
                accessor_name = field.get_accessor_name()
                if accessor_name:
                    auto_ignore.add(accessor_name)
    
    for related_object in instance._meta.get_fields():
        if related_object.is_relation and related_object.auto_created:
            # Reverse relationship (Someone points to us)
            accessor_name = related_object.get_accessor_name()
            if not accessor_name:
                continue
            if accessor_name in ignore_relations or accessor_name in auto_ignore:
                continue
                
            try:
                # Get the related manager/descriptor
                related_item = getattr(instance, accessor_name)
                
                # Check based on relationship type
                if related_object.one_to_many or related_object.many_to_many:
                     if related_item.exists():
                         return True
                elif related_object.one_to_one:
                     # OneToOne
                     pass 
            except Exception:
                # DoesNotExist or other issues
                continue
            
            # For O2O
            if related_object.one_to_one and related_item:
                return True
                
    return False
