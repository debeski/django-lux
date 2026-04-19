import json
import os
import re
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from functools import lru_cache
import inspect

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
from django.utils.module_loading import import_string

from .constants import (
    DEFAULT_HOME_URL,
    DEFAULT_TABLE_DENSITY,
    LEGACY_HOME_URL,
    TABLE_DENSITY_VALUES,
)
from .themes import is_valid_theme
from .translations import get_current_language_code, get_strings
# try-except for django_filters as it might not be installed (though likely is)
try:
    import django_filters
except ImportError:
    django_filters = None


SENSITIVE_ACTIVITY_MASK = "********"
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


def _coerce_list_setting(scope, key):
    value = scope.get(key)
    if value is None:
        value = []
    elif isinstance(value, tuple):
        value = list(value)
    scope[key] = value
    return value


def _insert_middleware_once(middleware, middleware_path, *, after=None, before=None):
    if middleware_path in middleware:
        middleware.remove(middleware_path)

    insert_at = 0
    if before and before in middleware:
        insert_at = middleware.index(before)
    elif after and after in middleware:
        insert_at = middleware.index(after) + 1

    middleware.insert(insert_at, middleware_path)


def get_secret(secret_name, env_var):
    """Read a Docker secret first, then fall back to an environment variable."""
    secret_path = os.path.join("/run/secrets", secret_name)
    try:
        with open(secret_path, "r", encoding="utf-8") as secret_file:
            return secret_file.read().strip()
    except OSError:
        return os.getenv(env_var)


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

def microsys_settings(scope):
    """
    Apply the default MicroSys settings requirements to a Django settings module.

    Intended usage from a host project's settings.py:

        from microsys.utils import microsys_settings
        microsys_settings(globals())
    """
    if not isinstance(scope, dict):
        raise TypeError("microsys_settings() expects the result of globals() from settings.py")

    installed_apps = _coerce_list_setting(scope, "INSTALLED_APPS")
    middleware = _coerce_list_setting(scope, "MIDDLEWARE")
    templates = _coerce_list_setting(scope, "TEMPLATES")

    required_apps = [
        "microsys",
        "crispy_forms",
        "crispy_bootstrap5",
        "django_filters",
        "django_tables2",
    ]
    for app_label in reversed(required_apps):
        if app_label in installed_apps:
            installed_apps.remove(app_label)
        installed_apps.insert(0, app_label)

    auth_middleware = "django.contrib.auth.middleware.AuthenticationMiddleware"
    session_middleware = "django.contrib.sessions.middleware.SessionMiddleware"
    common_middleware = "django.middleware.common.CommonMiddleware"
    locale_middleware = "django.middleware.locale.LocaleMiddleware"
    microsys_middleware = "microsys.middleware.ActivityLogMiddleware"

    if session_middleware in middleware and common_middleware in middleware:
        session_index = middleware.index(session_middleware)
        common_index = middleware.index(common_middleware)
        if session_index < common_index:
            _insert_middleware_once(
                middleware,
                locale_middleware,
                before=common_middleware,
            )
        else:
            _insert_middleware_once(
                middleware,
                locale_middleware,
                after=session_middleware,
            )
    elif session_middleware in middleware:
        _insert_middleware_once(
            middleware,
            locale_middleware,
            after=session_middleware,
        )
    elif common_middleware in middleware:
        _insert_middleware_once(
            middleware,
            locale_middleware,
            before=common_middleware,
        )
    else:
        _insert_middleware_once(middleware, locale_middleware)

    if auth_middleware in middleware:
        _insert_middleware_once(
            middleware,
            microsys_middleware,
            after=auth_middleware,
        )
    else:
        _insert_middleware_once(middleware, microsys_middleware)

    context_proc = "microsys.context_processors.microsys_context"
    for template in templates:
        if not isinstance(template, dict):
            continue
        options = template.setdefault("OPTIONS", {})
        processors = options.setdefault("context_processors", [])
        if context_proc not in processors:
            processors.append(context_proc)

    scope.setdefault("CRISPY_ALLOWED_TEMPLATE_PACKS", "bootstrap5")
    scope.setdefault("CRISPY_TEMPLATE_PACK", "bootstrap5")
    scope.setdefault("LANGUAGE_CODE", "ar")
    scope.setdefault("TIME_ZONE", "Etc/GMT-2")
    scope.setdefault("USE_I18N", True)
    scope.setdefault("USE_TZ", True)
    scope.setdefault("DEFAULT_CHARSET", "utf-8")

    message_tags = scope.get("MESSAGE_TAGS")
    if not isinstance(message_tags, dict):
        message_tags = dict(message_tags or {})
    message_tags.setdefault(messages.ERROR, "danger")
    scope["MESSAGE_TAGS"] = message_tags

    format_module_path = scope.get("FORMAT_MODULE_PATH")
    if not format_module_path:
        scope["FORMAT_MODULE_PATH"] = ["microsys.formats"]
    elif isinstance(format_module_path, (list, tuple)):
        merged_format_module_path = list(format_module_path)
        if "microsys.formats" not in merged_format_module_path:
            merged_format_module_path.append("microsys.formats")
        scope["FORMAT_MODULE_PATH"] = merged_format_module_path
    else:
        scope["FORMAT_MODULE_PATH"] = [format_module_path, "microsys.formats"]
    return scope

def _normalize_asset_url(value, fallback_base='/media/'):
    """Ensure stored media paths render as browser-safe absolute URLs."""
    if not value:
        return value

    normalized = str(value).strip()
    if not normalized:
        return normalized

    if (
        normalized.startswith(('http://', 'https://', '//', '/', 'data:'))
        or ':' in normalized.split('/', 1)[0]
    ):
        return normalized

    base_url = str(getattr(settings, 'MEDIA_URL', '') or fallback_base).strip() or fallback_base
    if not base_url.startswith('/'):
        base_url = f'/{base_url}'
    if not base_url.endswith('/'):
        base_url = f'{base_url}/'
    return f"{base_url}{normalized.lstrip('/')}"

# Auth Check — Staff permission test for @user_passes_test decorator
def is_staff(user):
    return user.is_staff

# Auth Check — Superuser permission test for @user_passes_test decorator
def is_superuser(user):
    return user.is_superuser

# Network Helper — Extract client IP from request (supports X-Forwarded-For)
def get_client_ip(request):
    """Extract client IP address from request."""
    if not request:
        return None
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0]
    else:
        ip = request.META.get("REMOTE_ADDR")
    return ip

# Activity Logging — Universal logging utility for user actions
def log_user_action(request, action, instance=None, model_name=None, details=None, number=None):
    """
    Centralized activity logging. All manual UserActivityLog creation should go through here.
    
    Args:
        request:    Django request object
        action:     Action string (e.g. 'CREATE', 'LOGIN', 'EXPORT')
        instance:   Optional model instance (auto-extracts pk, number, model_name)
        model_name: Optional override for model name (used when no instance exists)
        details:    Optional dict of extra details to attach to log
        number:     Optional override for the document number field
    """
    UserActivityLog = apps.get_model('microsys', 'UserActivityLog')
    UserActivityLog.safe_log(
        user=request.user,
        action=action,
        model_name=model_name or (instance._meta.verbose_name if instance else None),
        object_id=instance.pk if instance else None,
        number=number or (getattr(instance, 'number', '') if instance else None),
        details=details,
        ip_address=get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
    )

# Config Merger — Merges translation dictionaries across language layers
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

# Config Merger — Merges language configuration dictionaries
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

# Sidebar Helper — Removes duplicate sidebar entries by id/url_name/label
def _dedupe_sidebar_entries(entries):
    seen = set()
    deduped = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        key = entry.get('id') or entry.get('url_name') or entry.get('label')
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    return deduped

def get_system_config():
    """
    Returns the deeply merged system configuration.
    1. Default config
    2. settings.MICROSYS_CONFIG (host project codebase)
    3. SystemSettings Singleton (database UI overrides)
    """
    # Default configuration
    default_config = {
        'name': 'microSYS',
        'name_ar': '',
        'name_en': 'microSYS',
        'verbose_name': 'microSYS',
        'logo': '/static/img/base_logo.webp',
        'login_logo': '/static/img/login_logo.webp',
        'favicon': '/static/favicon.ico',
        'home_url': DEFAULT_HOME_URL,
        'default_language': 'en',
        'default_theme': 'light',
        'default_table_density': DEFAULT_TABLE_DENSITY,
        'email_2fa': False,
        'public_root': False,
        'languages': {
            'ar': {'name': 'العربية', 'dir': 'rtl', 'flag': '🇱🇾'},
            'en': {'name': 'English', 'dir': 'ltr', 'flag': '🇬🇧'},
        },
        'translations': {},
        'sidebar': {
            'home_url_name': None,
            'entries': [],
            'enable_reorder': True,
            'show_toolbar': True,
        },
        'is_configured': False,
    }

    # Project settings
    user_config = getattr(settings, 'MICROSYS_CONFIG', {})
    if not isinstance(user_config, dict):
        user_config = {}
    
    # DB settings
    db_config = {}
    try:
        from microsys.models import SystemSettings
        sys_settings = SystemSettings.load()
        legacy_unconfigured_name = (
            not getattr(sys_settings, 'is_configured', False) and
            getattr(sys_settings, 'name', '') in {'ادارة النظام', 'إدارة النظام', None}
        )
        if sys_settings.name and not legacy_unconfigured_name:
            db_config['name'] = sys_settings.name
            db_config['name_ar'] = sys_settings.name
        if sys_settings.name_en:
            db_config['name_en'] = sys_settings.name_en
        if sys_settings.logo:
            db_config['logo'] = sys_settings.logo.url
            db_config['logo_url'] = sys_settings.logo.url
            db_config['login_logo_url'] = sys_settings.logo.url
        if sys_settings.favicon:
            db_config['favicon'] = sys_settings.favicon.url
            db_config['favicon_url'] = sys_settings.favicon.url
        legacy_unconfigured_home_url = (
            not getattr(sys_settings, 'is_configured', False) and
            getattr(sys_settings, 'home_url', '') == LEGACY_HOME_URL
        )
        if sys_settings.home_url and not legacy_unconfigured_home_url:
            db_config['home_url'] = sys_settings.home_url
        if sys_settings.default_language:
            db_config['default_language'] = sys_settings.default_language
        if getattr(sys_settings, 'default_theme', None):
            db_config['default_theme'] = sys_settings.default_theme
        if getattr(sys_settings, 'default_table_density', None):
            db_config['default_table_density'] = sys_settings.default_table_density
        if isinstance(sys_settings.languages, dict) and sys_settings.languages:
            db_config['languages'] = sys_settings.languages
        if isinstance(sys_settings.translations_override, dict) and sys_settings.translations_override:
            db_config['translations'] = sys_settings.translations_override
        if isinstance(getattr(sys_settings, 'sidebar_config', None), dict) and sys_settings.sidebar_config:
            db_config['sidebar'] = sys_settings.sidebar_config
        if hasattr(sys_settings, 'is_configured'):
            db_config['is_configured'] = bool(sys_settings.is_configured)
        if hasattr(sys_settings, 'email_2fa'):
            db_config['email_2fa'] = bool(sys_settings.email_2fa)
        if hasattr(sys_settings, 'public_root'):
            db_config['public_root'] = bool(sys_settings.public_root)
    except Exception:
        pass

    user_sidebar = user_config.get('sidebar', {})
    if not isinstance(user_sidebar, dict):
        user_sidebar = {}
    db_sidebar = db_config.get('sidebar', {})
    if not isinstance(db_sidebar, dict):
        db_sidebar = {}

    final_config = deepcopy(default_config)
    for layer in (user_config, db_config):
        for key, value in layer.items():
            if key in ['languages', 'translations', 'sidebar']:
                continue
            final_config[key] = value

    final_config['languages'] = _merge_language_layers(
        default_config.get('languages', {}),
        user_config.get('languages', {}),
        db_config.get('languages', {}),
    )
    final_config['translations'] = _merge_translation_layers(
        default_config.get('translations', {}),
        user_config.get('translations', {}),
        db_config.get('translations', {}),
    )

    from .discovery import sanitize_sidebar_config

    merged_sidebar = deepcopy(default_config['sidebar'])
    for layer in (user_sidebar, db_sidebar):
        for key, value in layer.items():
            if key == 'entries':
                continue
            merged_sidebar[key] = value
    merged_sidebar['entries'] = _dedupe_sidebar_entries(
        list(db_sidebar.get('entries', [])) + list(user_sidebar.get('entries', []))
    )
    merged_sidebar = sanitize_sidebar_config(merged_sidebar, allow_system_items=True)
    final_config['sidebar'] = merged_sidebar

    if 'name_ar' not in final_config or not final_config.get('name_ar'):
        final_config['name_ar'] = final_config.get('name_en') or final_config.get('name') or default_config['name_en']
    if not final_config.get('name_en'):
        final_config['name_en'] = user_config.get('name_en') or default_config['name_en']
    if not is_valid_theme(final_config.get('default_theme')):
        final_config['default_theme'] = default_config['default_theme']
    if final_config.get('default_table_density') not in TABLE_DENSITY_VALUES:
        final_config['default_table_density'] = default_config['default_table_density']

    final_config['logo_url'] = _normalize_asset_url(
        final_config.get('logo_url') or final_config.get('logo') or default_config['logo']
    )
    final_config['login_logo_url'] = _normalize_asset_url(
        final_config.get('login_logo_url') or final_config.get('login_logo') or final_config['logo_url']
    )
    final_config['favicon_url'] = _normalize_asset_url(
        final_config.get('favicon_url') or final_config.get('favicon') or default_config['favicon']
    )

    final_config['home_url_name'] = None
    final_config['home_url'] = final_config.get('home_url') or default_config['home_url']

    return final_config

# Context Menu Helper — Filters context menu actions based on user permissions
def filter_context_actions(user, actions):
    """
    Filter a list of context menu actions based on user permissions.
    Each action can have a 'permissions' key (list of strings) or 'permission' (string).
    If user lacks any required permission, the action is excluded.
    """
    if not user or not user.is_authenticated:
        return []

    filtered = []
    for action in actions:
        # Check permissions
        required_perms = action.get('permissions', [])
        if not required_perms and 'permission' in action:
            required_perms = [action['permission']]
        
        if required_perms:
            if user.is_superuser:
                # Superuser sees all
                pass
            elif not user.has_perms(required_perms):
                continue
        
        filtered.append(action)
    
    return filtered

# Model Introspection — Returns possible import base paths for a model's app
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

# Model Resolution — Convention-based class importer (App.<submodule>.Model<Suffix>)
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

# Model Resolution — Resolves a class from a model method/attr (class or string path)
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

class LazyModelClasses(dict):
    """
    Lazy dictionary that only resolves model classes (form, table, filter)
    when they are explicitly requested, and caches them for subsequent accesses.
    """
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
        
    def __getitem__(self, key):
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

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key):
        if super().__contains__(key):
            return True
        return key in ('form', 'table', 'filter')

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

    def _resolve_form(self):
        override = self._get_override_or_none('form')
        if override: return override
        
        form_class = _import_by_convention(self._model, "forms", "Form")
        if not form_class:
            form_class = resolve_form_class_for_model(self._model)
        return form_class
        
    def _resolve_table(self):
        override = self._get_override_or_none('table')
        if override: return override
        
        table_class = _import_by_convention(self._model, "tables", "Table")
        if not table_class:
             table_class = _resolve_model_class(self._model, "get_table_class")
        if not table_class:
             table_class = _build_generic_table_class(self._model)
        return table_class
        
    def _resolve_filter(self):
        override = self._get_override_or_none('filter')
        if override: return override
        
        filter_class = _import_by_convention(self._model, "filters", "Filter")
        if not filter_class:
             filter_class = _resolve_model_class(self._model, "get_filter_class")
        if not filter_class and django_filters:
             filter_class = _build_generic_filter_class(self._model)
        return filter_class

# Model Resolution — Dynamically imports model, form, table, and filter classes by name
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


def get_user_linked_models():
    """
    Finds all models across the Django project that have a OneToOneField 
    pointing to settings.AUTH_USER_MODEL, excluding microsys.Profile.
    Returns: list of dicts with model identifiers.
    """
    from django.apps import apps
    from django.contrib.auth import get_user_model
    linked_models = []
    
    User = get_user_model()
    for model in apps.get_models():
        # Exclude the internal microsys profile since it's already auto-created
        if model._meta.app_label == 'microsys' and model.__name__ == 'Profile':
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

# Model Resolution — Dynamically Resolves a Model by Name
def resolve_model_by_name(model_name, app_label=None):
    """
    Resolve a model by name, optionally constrained to an app label.
    Falls back to scanning all apps if app_label is not provided.
    """
    if not model_name:
        return None

    normalized = model_name.lower()

    if app_label:
        try:
            return apps.get_model(app_label, model_name)
        except LookupError:
            return None

    for model in apps.get_models():
        meta = model._meta
        if meta.model_name == normalized or model.__name__.lower() == normalized:
            return model

    return None

# Model Resolution — Dynamically imports and returns a class from a dotted string path
def get_class_from_string(class_path):
    """Dynamically imports and returns a class from a string path."""
    return import_string(class_path)

# Section Detection — Checks if a model is marked as a section model
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

# Form Resolution — Resolves or generates a ModelForm class for any model
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
        class ScopeDynamicForm(form_class):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                if 'scope' in self.fields and not is_scope_enabled():
                    del self.fields['scope']
        form_class = ScopeDynamicForm

    return form_class

# Related Objects Inspector — Introspects all related objects for Smart Delete/View
def collect_related_objects(instance):
    """
    Introspects a model instance to find all related objects (Reverse FK, M2M).
    Returns a dictionary: { 'Verbose Name Plural': ['Item 1', 'Item 2'] }
    Used for Smart Delete functionality and Smart View.
    """
    related_data = {}
    
    # Identify M2M through models to skip their reverse relationships
    through_models = set()
    for f in instance._meta.get_fields():
        if getattr(f, 'many_to_many', False):
            try:
                through = getattr(f, 'through', getattr(getattr(f, 'remote_field', None), 'through', None))
                if through:
                    through_models.add(through)
            except AttributeError:
                pass

    # Iterate over all fields to find relations
    for field in instance._meta.get_fields():
        if getattr(field, 'related_model', None) in through_models:
            continue

        if field.auto_created and not field.concrete:
            # Reverse Relations (OneToMany, OneToOne)
            # e.g. department.affiliate_set
            try:
                accessor = field.get_accessor_name()
                if not accessor: continue
                
                related_msg = getattr(instance, accessor, None)
                if related_msg:
                    # Check if it's a Manager (OneToMany/ManyToMany) or single object (OneToOne)
                    if hasattr(related_msg, 'all'):
                        # Limit to reasonable amount
                        qs = related_msg.all()[:20] 
                        if qs:
                            items = [str(obj) for obj in qs]
                            name = str(field.related_model._meta.verbose_name_plural)
                            if name not in related_data:
                                related_data[name] = items
                    else:
                        # OneToOne
                        name = str(field.related_model._meta.verbose_name)
                        if name not in related_data:
                            related_data[name] = [str(related_msg)]
            except Exception:
                pass
                
        elif hasattr(field, 'many_to_many') and field.many_to_many:
            # Forward M2M
            try:
                manager = getattr(instance, field.name, None)
                if manager:
                    qs = manager.all()[:20]
                    if qs:
                        items = [str(obj) for obj in qs]
                        name = str(field.related_model._meta.verbose_name_plural)
                        if name not in related_data:
                            related_data[name] = items
            except Exception:
                pass
                
    return related_data


def _build_generic_detail_context(instance, request=None):
    """
    Dynamically generates a list of {'label': ..., 'value': ...} dictionaries 
    from a model instance for zero-boilerplate detail views.
    Respects translations and the 'is_scope_enabled' global setting.
    """
    from microsys.utils import is_scope_enabled

    s = get_strings(get_current_language_code(request))

    fields_data = []
    
    # Audit fields and passwords shouldn't generally be shown in generic detail views
    exclude_fields = ['password', 'created_at', 'updated_at', 'deleted_at', 'created_by', 'updated_by', 'deleted_by']
    
    if not is_scope_enabled():
        exclude_fields.append('scope')

    for field in instance._meta.get_fields():
        if field.name in exclude_fields:
            continue
            
        # Ignore reverse relations to keep it clean, only show direct fields and M2M
        if field.auto_created and not field.concrete and not field.many_to_many:
            continue

        try:
            value = getattr(instance, field.name, None)
            
            # Formatting
            if isinstance(field, ManyToManyField):
                if value is not None:
                    # evaluate M2M manager
                    qs = value.all()
                    value = ", ".join(str(item) for item in qs)
                    if not value:
                        value = "-"
            elif isinstance(value,FieldFile):
                if value and value.name:
                    value = f'<a href="{value.url}" target="_blank" class="btn btn-sm btn-outline-primary"><i class="bi bi-download"></i> {s.get("btn_download", "تحميل")}</a>'
                else:
                    value = "-"
            elif isinstance(value, bool):
                value = f'<i class="bi bi-check-circle-fill text-success"></i>' if value else f'<i class="bi bi-x-circle text-danger"></i>'
            elif value is None or value == "":
                value = "-"
            elif hasattr(field, 'choices') and field.choices:
                # get display value for choices
                display_func = getattr(instance, f"get_{field.name}_display", None)
                if display_func:
                    value = display_func()
            
            label = resolve_detail_field_label(instance, field, request=request, strings=s)
            
            fields_data.append({
                'label': str(label).capitalize(),
                'value': value,
                'is_html': isinstance(value, str) and ('<a' in value or '<i' in value)
            })
        except Exception:
            pass

    return fields_data


def resolve_detail_field_label(instance, field, request=None, strings=None):
    """Resolve a translated display label for generic detail views."""
    s = strings or get_strings(get_current_language_code(request))
    raw_label = str(getattr(field, 'verbose_name', '') or getattr(field, 'name', '')).strip()
    field_name = str(getattr(field, 'name', '') or '').strip()
    model_name = ''

    try:
        model_name = instance._meta.model_name
    except Exception:
        try:
            model_name = instance.__class__.__name__.lower()
        except Exception:
            model_name = ''

    keys = []
    if model_name and field_name:
        keys.append(f"label_{model_name}_{field_name}")
    if field_name:
        keys.extend([f"label_{field_name}", field_name])
    if raw_label:
        keys.extend([f"label_{raw_label}", raw_label])

    for key in keys:
        translated = s.get(key)
        if translated:
            return translated

    return raw_label or field_name


# Dynamic Table Builder — Generates a django-tables2 Table class at runtime
def _build_generic_table_class(model):
    """
    Build a minimal django-tables2 Table for a model.
    Build Meta dynamically so django-tables2 sees Meta.model at class creation.
    Generated tables inherit the full Microsys table platform by default.
    """
    from microsys.tables import MicrosysTable
    
    raw_exclude = getattr(model, "table_exclude", None)
    if raw_exclude is None:
        raw_exclude = []
    elif isinstance(raw_exclude, (str, bytes)):
        raw_exclude = [raw_exclude]
    else:
        raw_exclude = list(raw_exclude)

    # Default exclusions for audit fields
    audit_fields = ['created_at', 'updated_at', 'deleted_at', 'created_by', 'updated_by', 'deleted_by']
    raw_exclude.extend([f for f in audit_fields if f not in raw_exclude])

    try:
        has_scope_field = model._meta.get_field("scope") is not None
    except Exception:
        has_scope_field = False

    meta_attrs = {
        "model": model,
        "row_attrs": {
            'class': 'section-row',
            'data-pk': lambda record: record.pk,
            'data-name': lambda record: str(record),
            'data-micro-context': 'true',
        },
    }
    if raw_exclude:
        meta_attrs["exclude"] = list(dict.fromkeys(raw_exclude))
    Meta = type("Meta", (), meta_attrs)
    table_attrs = {"Meta": Meta}
    return type(f"{model.__name__}AutoTable", (MicrosysTable,), table_attrs)

# Dynamic Filter Builder — Generates a django-filters FilterSet class at runtime
def _build_generic_filter_class(model):
    """
    Build a minimal django-filters FilterSet:
    - keyword search across text fields (and numeric fields if value is numeric)
    - optional year dropdown if any date/datetime field exists
    """
    if not django_filters:
        return None

    text_fields = []
    int_fields = []
    num_fields = []
    date_field = None

    for field in model._meta.get_fields():
        if not hasattr(field, 'attname'):
            continue
        if field.many_to_many or field.one_to_many:
            continue

        if isinstance(field, (dj_models.CharField, dj_models.TextField, dj_models.EmailField, dj_models.SlugField, dj_models.URLField)):
            text_fields.append(field.name)
        elif isinstance(field, (dj_models.IntegerField, dj_models.BigIntegerField, dj_models.SmallIntegerField, dj_models.PositiveIntegerField, dj_models.PositiveSmallIntegerField)):
            int_fields.append(field.name)
        elif isinstance(field, (dj_models.FloatField, dj_models.DecimalField)):
            num_fields.append(field.name)
        elif date_field is None and isinstance(field, (dj_models.DateField, dj_models.DateTimeField)):
            date_field = field.name

    # Filter Helper — Parses string value to Decimal for numeric filtering
    def _parse_number(value):
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None

    # Filter Init — Initializes filter with translated labels and year choices
    def _init(self, *args, **kwargs):
        super(self.__class__, self).__init__(*args, **kwargs)
        s = get_strings()

        if date_field and 'year' in self.filters:
            year_label = s.get('filter_year', 'السنة')
            self.filters['year'].label = year_label
            self.filters['year'].extra['empty_label'] = year_label
            years = self.Meta.model.objects.dates(date_field, 'year').distinct()
            self.filters['year'].extra['choices'] = [(year.year, year.year) for year in years]
            self.filters['year'].field.widget.attrs.update({
                'class': 'auto-submit-filter'
            })
            set_first_choice(self.filters['year'].field, year_label)

        if not hasattr(self.form, 'helper') or self.form.helper is None:
            # Layout handled by setup_filter_helper in the view
            pass

    # Filter Method — Performs keyword search across text and numeric fields
    def _filter_keyword(self, queryset, name, value, text_fields=text_fields, int_fields=int_fields, num_fields=num_fields):
        if not value:
            return queryset

        q_obj = Q()
        for field_name in text_fields:
            q_obj |= Q(**{f"{field_name}__icontains": value})

        numeric_value = _parse_number(value)
        if numeric_value is not None:
            is_int = numeric_value == numeric_value.to_integral_value()
            if is_int:
                int_value = int(numeric_value)
                for field_name in int_fields:
                    q_obj |= Q(**{field_name: int_value})
            for field_name in num_fields:
                q_obj |= Q(**{field_name: numeric_value})

        return queryset.filter(q_obj) if q_obj else queryset

    meta_attrs = {"model": model, "fields": []}
    Meta = type("Meta", (), meta_attrs)

    attrs = {
        "Meta": Meta,
        "__init__": _init,
        "filter_keyword": _filter_keyword,
        "keyword": django_filters.CharFilter(method='filter_keyword', label=''),
    }
    if date_field:
        from django import forms as dj_forms
        attrs["date_gte"] = django_filters.DateFilter(
            field_name=date_field,
            lookup_expr="gte",
            label='',
            widget=dj_forms.DateInput(attrs={'class': 'form-control ms-datepicker', 'placeholder': 'من تاريخ', 'autocomplete': 'off'}),
        )
        attrs["date_lte"] = django_filters.DateFilter(
            field_name=date_field,
            lookup_expr="lte",
            label='',
            widget=dj_forms.DateInput(attrs={'class': 'form-control ms-datepicker', 'placeholder': 'إلى تاريخ', 'autocomplete': 'off'}),
        )
        attrs["year"] = django_filters.ChoiceFilter(
            field_name=f"{date_field}__year",
            lookup_expr="exact",
            choices=[],
            empty_label="السنة",
        )

    # Apply same default exclusions to filters to avoid clutter
    audit_fields = ['created_at', 'updated_at', 'deleted_at', 'created_by', 'updated_by', 'deleted_by']
    meta_attrs["exclude"] = audit_fields

    return type(f"{model.__name__}AutoFilter", (django_filters.FilterSet,), attrs)

# Section Detection — Identifies child/subsection models (M2M targets)
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

# Section Discovery — Scans apps for section models and resolves their Form/Table/Filter classes
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

# Section Discovery — Returns the first section model name for default tab selection
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

# Section Management - M2M Helper — Provides through_defaults for scoped M2M relations
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
        # Resolve scope from profile first, then direct user attribute
        scope = None
        if hasattr(request.user, 'profile') and getattr(request.user.profile, 'scope', None):
            scope = request.user.profile.scope
        elif hasattr(request.user, 'scope') and getattr(request.user, 'scope', None):
            scope = request.user.scope
        if scope:
            try:
                through._meta.get_field('scope')
                defaults['scope'] = scope
            except Exception:
                pass

    return defaults or None

# Section Management - Record Creation Helper — Creates a minimal model instance from raw POST data
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

# Scope Management — Checks if the multi-tenant Scope system is globally enabled
def is_scope_enabled():
    """
    Checks if the Scope system is globally enabled.
    Returns:
        bool: True if enabled, False otherwise.
    """
    from django.db.utils import ProgrammingError, OperationalError
    try:
        ScopeSettings = apps.get_model('microsys', 'ScopeSettings')
        return ScopeSettings.load().is_enabled
    except (LookupError, ProgrammingError, OperationalError):
        # Fallback if model or table isn't ready (e.g., during migrations or empty DB)
        return False

# Deletion Safety — Checks if an instance has related records (lock/protect logic)
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

# Sidebar State Manager — Handles sidebar collapse toggle and persists state to session/profile
def toggle_sidebar(request):
    if request.method == "POST" and request.user.is_authenticated:
        collapsed = request.POST.get("collapsed") == "true"
        
        # 1. Update Session
        request.session["sidebarCollapsed"] = collapsed
        
        # 2. Update Profile Preferences if profile exists
        if hasattr(request.user, 'profile'):
            profile = request.user.profile
            if not profile.preferences:
                profile.preferences = {}
            
            # Ensure it's a dict
            if isinstance(profile.preferences, str):
                import json
                try:
                    profile.preferences = json.loads(profile.preferences)
                except:
                    profile.preferences = {}
            
            # Use a copy to ensure Django detects changes
            prefs = dict(profile.preferences)
            prefs['sidebar_collapsed'] = collapsed
            profile.preferences = prefs
            profile.save(update_fields=['preferences'])

        return JsonResponse({"status": "success"})
    return JsonResponse({"status": "error"}, status=400)


# Form Helper — Applies shared field classes, direction, and optional inline labels
def set_field_attrs(form, request=None, inline_labels=False):
    """Set common attributes for all fields in the form."""
    from microsys.translations import get_current_language_code

    lang = get_current_language_code(request)
    ms_trans = get_strings(lang)
    
    # Detect language for direction
    direction = 'rtl' if lang.startswith('ar') else 'ltr'
    
    for field_name in form.fields:
        field = form.fields.get(field_name)
        # Try to get label from MS_TRANS (model-specific first, then generic)
        model_name = ""
        if hasattr(form, '_meta') and hasattr(form._meta, 'model'):
             model_name = form._meta.model.__name__.lower()
        
        label_key_model = f"label_{model_name}_{field_name}" if model_name else None
        label_key_generic = f"label_{field_name}"
        
        label = ms_trans.get(label_key_model) if label_key_model else None
        if not label:
            label = ms_trans.get(label_key_generic)
        
        if not label:
            # Handle auto-generated filter suffixes (gte/lte) for cleaner Arabic translation
            clean_name = field_name
            suffix = ""
            range_type = None
            if "__gte" in field_name:
                clean_name = field_name.replace("__gte", "")
                suffix = f" ({ms_trans.get('filter_from', 'From')})"
                range_type = "from"
            elif "__lte" in field_name:
                clean_name = field_name.replace("__lte", "")
                suffix = f" ({ms_trans.get('filter_to', 'To')})"
                range_type = "to"
            elif field_name.endswith("_gte"):
                clean_name = field_name[:-4]
                suffix = f" ({ms_trans.get('filter_from', 'From')})"
                range_type = "from"
            elif field_name.endswith("_lte"):
                clean_name = field_name[:-4]
                suffix = f" ({ms_trans.get('filter_to', 'To')})"
                range_type = "to"

            if clean_name == "date" and range_type == "from":
                label = ms_trans.get('filter_date_from')
            elif clean_name == "date" and range_type == "to":
                label = ms_trans.get('filter_date_to')
            
            if not label:
                # Try to resolve base label (e.g. label_created_at)
                base_label = (
                    ms_trans.get(f"label_{clean_name}")
                    or ms_trans.get(f"filter_{clean_name}")
                    or field.label
                )
                
                # If default field.label is messy (auto-generated English), clean it
                if (
                    not base_label
                    or '[invalid name]' in str(base_label).lower()
                    or 'is greater than' in str(base_label).lower()
                    or 'is less than' in str(base_label).lower()
                ):
                    base_label = clean_name.replace('_', ' ').split('.')[-1].title()
                    # Secondary lookup for core field name in translations
                    base_label = (
                        ms_trans.get(f"label_{clean_name}")
                        or ms_trans.get(f"filter_{clean_name}")
                        or ms_trans.get(f"label_{base_label.lower()}")
                        or ms_trans.get(f"filter_{base_label.lower()}")
                        or base_label
                    )
                
                label = f"{base_label}{suffix}"

        if label:
            field.label = label

        widget = field.widget
        is_select_multiple = isinstance(widget, forms.SelectMultiple)
        is_select = isinstance(widget, (forms.Select, forms.NullBooleanSelect)) and not is_select_multiple
        is_check_like = isinstance(widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple, forms.RadioSelect))
        is_hidden = isinstance(widget, (forms.HiddenInput, forms.MultipleHiddenInput))

        if label and inline_labels and not is_hidden:
            if is_select:
                set_first_choice(field, label)
                field.label = ''
            elif not is_select_multiple and not is_check_like:
                field.widget.attrs.setdefault('placeholder', label)
                field.label = ''

        field.widget.attrs['dir'] = direction  # Set text direction dynamically
        
        # Inject Bootstrap classes based on widget type
        existing_class = field.widget.attrs.get('class', '')
        if is_select:
            if 'form-select' not in existing_class:
                field.widget.attrs['class'] = f"{existing_class} form-select".strip()
        elif is_select_multiple:
            if 'form-select' not in existing_class:
                field.widget.attrs['class'] = f"{existing_class} form-select".strip()
        elif is_check_like:
            if 'form-check-input' not in existing_class:
                field.widget.attrs['class'] = f"{existing_class} form-check-input".strip()
        else:
            if 'form-control' not in existing_class:
                field.widget.attrs['class'] = f"{existing_class} form-control".strip()
            
        # 3. Inject the shared microSYS datepicker hook for real date/datetime inputs.
        # Keep legacy .flatpickr compatibility so host apps do not need an immediate markup sweep.
        # Do not attach the picker to selects such as date__year choice filters.
        is_select_like = isinstance(widget, (forms.Select, forms.SelectMultiple, forms.NullBooleanSelect))
        is_date = (
            isinstance(widget, (forms.DateInput, forms.DateTimeInput)) or
            'datetimeinput' in existing_class or
            (
                not is_select_like and
                any(kw in field_name.lower() for kw in ['date', 'time', 'since', 'until'])
            )
        )
        
        if is_date and 'ms-datepicker' not in field.widget.attrs.get('class', '') and 'flatpickr' not in field.widget.attrs.get('class', ''):
            current_class = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f"{current_class} ms-datepicker".strip()
        if is_date:
            field.widget.attrs['autocomplete'] = 'off'


def setup_filter_helper(filter_instance, request=None, preserve_keys=None, inline_labels=True):
    """
    Sets up a modern, responsive Crispy layout for a django-filter FilterSet.
    Aligns fields dynamically using Bootstrap 5 flexbox and appends a filter button.
    """
    from crispy_forms.helper import FormHelper
    from crispy_forms.layout import Layout, Div, Field, HTML, Hidden, Row
    
    helper = FormHelper()
    helper.form_method = 'get'
    helper.form_tag = True
    helper.form_class = 'py-3 row g-2 no-print m-0 microsys-form microsys-filter'
    
    # Determine which keys to preserve in the URL and form state
    if preserve_keys is None:
        preserve_keys = ['type', 'sort', 'per_page', 'export_type', 'model', 'id', 'category']
        
    layout_hidden = []
    if request and request.GET:
        for key in preserve_keys:
            if key in request.GET:
                val = request.GET.get(key)
                layout_hidden.append(Hidden(key, val))

    # Dynamically build layout based on fields
    fields = list(filter_instance.form.fields.keys())
    divs = []
    
    # Calculate col width
    col_class = 'col-sm-6 col-md-3 col-lg-auto flex-grow-1'
    
    for f in fields:
        divs.append(Div(Field(f, wrapper_class='mb-0'), css_class=col_class))
    
    # Determine if we have active filters
    has_active_filters = False
    clear_url = "?"
    
    if request and request.GET:
        import urllib.parse
        has_active_filters = any(k not in preserve_keys + ['page'] and v for k, v in request.GET.items())
        clear_params = {k: v for k, v in request.GET.items() if k in preserve_keys}
        qs = urllib.parse.urlencode(clear_params, doseq=True)
        if qs:
            clear_url = f"?{qs}"

    # Build button group
    if has_active_filters:
        search_btn = '<button type="submit" class="btn btn-secondary microsys-filter-chip microsys-filter-submit rounded-start-pill rounded-end-0 flex-grow-1"><i class="bi bi-search"></i></button>'
        clear_btn = f'<a href="{clear_url}" class="btn btn-warning microsys-filter-chip microsys-filter-clear rounded-end-pill rounded-start-0 px-3"><i class="bi bi-x-lg"></i></a>'
        btn_html = f'<div class="d-flex w-100 microsys-filter-controls">{search_btn}{clear_btn}</div>'
    else:
        search_btn = '<button type="submit" class="btn btn-secondary microsys-filter-chip microsys-filter-submit rounded-pill flex-grow-1"><i class="bi bi-search"></i></button>'
        btn_html = f'<div class="d-flex w-100 microsys-filter-controls">{search_btn}</div>'
    
    divs.append(
        Div(
            HTML(btn_html),
            css_class='col-sm-12 col-md-2 col-lg-auto'
        )
    )
    
    # Wrap divs in a row container for consistent layout even if form tag is missing
    helper.layout = Layout(
        *layout_hidden, 
        Div(*divs, css_class='row g-2 align-items-start mb-0')
    )
    filter_instance.form.helper = helper
    
    # Apply shared field attrs, defaulting filters to inline placeholder labels.
    set_field_attrs(filter_instance.form, request, inline_labels=inline_labels)


def advanced_filter_helper(filter_instance, config=None, request=None, preserve_keys=None, inline_labels=True):
    """
    Build an "advanced" filter helper with:
    - a primary row of fields
    - a pill-shaped search/clear control
    - an expand/collapse button for advanced fields
    - one or more advanced rows inside a collapse container
    - an optional bottom action row for add/download/custom buttons

    Config format:
        {
            "fields": [<field spec>, ...],
            "advanced_fields": [[<field spec>, ...], ...],
            "buttons": [<button spec>, ...],
            "hidden_inputs": [<raw html>, ...],
            "hidden_preserve_keys": ["sort", ...],
            "clear_preserve_keys": ["sort", "page"],
            "clear_url": "...",
            "advanced_target": "advanced-search",
            "toggle_label_key": "filter_advanced_search_action",
            "primary_row_class": "g-2",
            "advanced_wrapper_class": "collapse m-0",
            "actions_row_class": "g-2",
        }

    Field spec:
        "field_name"
        {
            "name": "field_name",
            "col_class": "form-group col-auto flex-fill",
            "attrs": {"placeholder": "..."},
            "placeholder": "...",
            "placeholder_key": "translation_key",
            "range_label_key": "label_date",
            "range_direction": "from" | "to",
            "wrapper_class": "mb-0",
        }
        {
            "type": "label" | "html",
            "text": "...",
            "text_key": "translation_key",
            "html": "<strong>...</strong>",
            "col_class": "...",
        }

    Button spec:
        {
            "url": "...",
            "permission": "app.perm_name",
            "label": "...",
            "label_key": "translation_key",
            "icon": "bi bi-plus-lg me-2 h4",
            "btn_class": "btn btn-primary w-100",
            "col_class": "col-auto text-center",
        }
        or {"type": "html", "html": "...", "col_class": "..."}
    """
    from crispy_forms.helper import FormHelper
    from crispy_forms.layout import Layout, Div, Field, HTML, Hidden, Row

    config = config or {}
    helper = FormHelper()
    helper.form_method = 'get'
    helper.form_tag = True
    helper.form_class = config.get('form_class', 'py-3 row g-2 no-print m-0 microsys-form microsys-filter')
    helper.attrs = dict(config.get('form_attrs', {}) or {})
    if config.get('autosubmit_selects', True):
        helper.attrs['data-ms-filter-autosubmit'] = 'true'

    if preserve_keys is None:
        preserve_keys = (
            config.get('hidden_preserve_keys')
            or config.get('preserve_keys')
            or ['sort', 'per_page', 'export_type']
        )

    clear_preserve_keys = config.get('clear_preserve_keys')
    if clear_preserve_keys is None:
        clear_preserve_keys = ['sort', 'page']

    from microsys.translations import get_current_language_code
    lang = get_current_language_code(request)
    s = get_strings(lang)

    set_field_attrs(filter_instance.form, request, inline_labels=inline_labels)

    hidden_layout = []
    if request and request.GET:
        for key in preserve_keys:
            if key in request.GET:
                hidden_layout.append(Hidden(key, request.GET.get(key)))

    for hidden_html in config.get('hidden_inputs', []) or []:
        hidden_layout.append(HTML(hidden_html))

    # Config Helper — Resolves translation text from MS_TRANS with fallback
    def _resolve_text(key=None, fallback=''):
        if key:
            return s.get(key, fallback)
        return fallback

    # Config Helper — Merges custom attributes into field widget
    def _merge_attrs(field_obj, attrs):
        if not attrs:
            return
        field_obj.widget.attrs.update(attrs)

    # Config Helper — Resolves placeholder text from spec with translation support
    def _resolve_placeholder(spec):
        if spec.get('placeholder') is not None:
            return spec['placeholder']
        if spec.get('placeholder_key'):
            return _resolve_text(spec['placeholder_key'], spec['placeholder_key'])

        range_label_key = spec.get('range_label_key')
        range_direction = spec.get('range_direction')
        if range_label_key and range_direction in {'from', 'to'}:
            base = _resolve_text(range_label_key, range_label_key)
            suffix_key = 'filter_from' if range_direction == 'from' else 'filter_to'
            suffix = _resolve_text(suffix_key, 'From' if range_direction == 'from' else 'To')
            return f"{base} {suffix}".strip()
        return None

    # Layout Builder — Renders a field spec into a Crispy Div with proper styling
    def _render_field_spec(spec, default_col_class):
        if isinstance(spec, str):
            spec = {'name': spec}
        if not isinstance(spec, dict):
            return None

        spec_type = spec.get('type', 'field')
        col_class = spec.get('col_class', default_col_class)

        if spec_type == 'html':
            return Div(HTML(spec.get('html', '')), css_class=col_class)

        if spec_type == 'label':
            text = spec.get('text')
            if text is None:
                text = _resolve_text(spec.get('text_key'), '')
            tag = spec.get('tag', 'strong')
            return Div(HTML(f'<{tag}>{text}</{tag}>'), css_class=col_class)

        field_name = spec.get('name')
        if not field_name or field_name not in filter_instance.form.fields:
            return None

        field_obj = filter_instance.form.fields[field_name]
        placeholder = _resolve_placeholder(spec)
        if placeholder:
            field_obj.widget.attrs['placeholder'] = placeholder
            if hasattr(field_obj, 'empty_label'):
                field_obj.empty_label = placeholder
            if hasattr(field_obj, 'choices'):
                set_first_choice(field_obj, placeholder)

        _merge_attrs(field_obj, spec.get('attrs'))
        return Div(
            Field(field_name, wrapper_class=spec.get('wrapper_class', 'mb-0')),
            css_class=col_class,
        )

    # Layout Builder — Builds an action button with permission check support
    def _build_action_button(spec):
        if not isinstance(spec, dict):
            return None

        if spec.get('type') == 'html':
            return Div(HTML(spec.get('html', '')), css_class=spec.get('col_class', 'col-auto text-center'))

        label = spec.get('label')
        if label is None:
            label = _resolve_text(spec.get('label_key'), '')
        icon = spec.get('icon', '')
        icon_html = f'<i class="{icon}"></i>' if icon else ''
        btn_class = spec.get("btn_class", "btn btn-outline-secondary w-100")
        if "microsys-filter-action" not in btn_class:
            btn_class = f"{btn_class} microsys-filter-action".strip()
        button_html = f'<a href="{spec.get("url", "#")}" class="{btn_class}">{icon_html}{label}</a>'

        permission = spec.get('permission')
        if permission:
            app_label, codename = permission.split('.', 1)
            button_html = f'{{% if perms.{app_label}.{codename} %}}{button_html}{{% endif %}}'

        return Div(HTML(button_html), css_class=spec.get('col_class', 'col-auto text-center'))

    # URL Builder — Constructs clear URL preserving specified query parameters
    def _build_clear_url():
        explicit = config.get('clear_url')
        if explicit:
            return explicit

        clear_url = '?'
        if request and request.GET:
            import urllib.parse
            clear_params = {k: v for k, v in request.GET.items() if k in clear_preserve_keys}
            qs = urllib.parse.urlencode(clear_params, doseq=True)
            if qs:
                clear_url = f'?{qs}'
        return clear_url

    # Filter State — Checks if any non-preserved filters are active
    def _has_active_filters():
        if not request or not request.GET:
            return False
        return any(k not in clear_preserve_keys and v for k, v in request.GET.items())

    advanced_specs = config.get('advanced_fields') or []
    advanced_names = {
        spec.get('name')
        for row in advanced_specs
        for spec in (row if isinstance(row, (list, tuple)) else [row])
        if isinstance(spec, dict) and spec.get('type', 'field') == 'field' and spec.get('name')
    }
    show_advanced = bool(
        request and request.GET and any(request.GET.get(name) for name in advanced_names)
    )

    primary_divs = []
    for spec in config.get('fields') or list(filter_instance.form.fields.keys()):
        primary_div = _render_field_spec(spec, config.get('primary_field_col_class', 'col-sm-6 col-md-3 col-lg-auto flex-grow-1'))
        if primary_div:
            primary_divs.append(primary_div)

    clear_url = _build_clear_url()
    has_active_filters = _has_active_filters()
    search_btn = '<button type="submit" class="btn btn-secondary microsys-filter-chip microsys-filter-submit rounded-start-pill rounded-end-0 flex-grow-1"><i class="bi bi-search"></i></button>'
    clear_btn = ''
    if has_active_filters:
        clear_btn = f'<a href="{clear_url}" class="btn btn-warning microsys-filter-chip microsys-filter-clear rounded-end-pill rounded-start-0 px-3"><i class="bi bi-x-lg"></i></a>'
    else:
        search_btn = '<button type="submit" class="btn btn-secondary microsys-filter-chip microsys-filter-submit rounded-pill flex-grow-1"><i class="bi bi-search"></i></button>'

    primary_divs.append(
        Div(
            HTML(f'<div class="d-flex w-100 microsys-filter-controls">{search_btn}{clear_btn}</div>'),
            css_class=config.get('search_controls_col_class', 'col-sm-12 col-md-2 col-lg-auto')
        )
    )

    toggle_target = config.get('advanced_target', 'advanced-search')
    toggle_label = _resolve_text(config.get('toggle_label_key', 'filter_advanced_search_action'), 'Advanced')
    toggle_icon = config.get('toggle_icon', 'bi bi-binoculars-fill')
    primary_divs.append(
        Div(
            HTML(
                '<button class="btn btn-outline-secondary microsys-filter-chip microsys-filter-toggle w-100" type="button" '
                f'data-bs-toggle="collapse" data-bs-target="#{toggle_target}" '
                f'aria-expanded="{"true" if show_advanced else "false"}" aria-controls="{toggle_target}">'
                f'<i class="{toggle_icon} me-2"></i>{toggle_label}'
                '</button>'
            ),
            css_class=config.get('toggle_col_class', 'col-sm-12 col-md-3 col-lg-auto')
        )
    )

    advanced_rows = []
    for row in advanced_specs:
        row_specs = row if isinstance(row, (list, tuple)) else [row]
        row_divs = []
        for spec in row_specs:
            row_div = _render_field_spec(spec, config.get('advanced_field_col_class', 'col-auto flex-fill'))
            if row_div:
                row_divs.append(row_div)
        if row_divs:
            advanced_rows.append(
                Row(
                    *row_divs,
                    css_class=config.get('advanced_row_class', 'g-2 align-items-start mb-0'),
                )
            )

    action_divs = []
    for spec in config.get('buttons', []):
        action_div = _build_action_button(spec)
        if action_div:
            action_divs.append(action_div)

    layout_items = list(hidden_layout)
    layout_items.append(
        Div(
            *primary_divs,
            css_class=config.get('primary_row_class', 'row g-2 align-items-start mb-0'),
        )
    )

    if advanced_rows:
        collapse_class = config.get('advanced_wrapper_class', 'collapse m-0')
        if show_advanced:
            collapse_class = f"{collapse_class} show"
        layout_items.append(
            Div(
                *advanced_rows,
                css_class=collapse_class,
                id=toggle_target,
            )
        )

    if action_divs:
        layout_items.append(
            Div(
                Div(
                    *action_divs,
                    css_class=config.get('actions_row_class', 'row g-2'),
                ),
                css_class=config.get('buttons_wrapper_class', 'p-0 my-2'),
            )
        )

    helper.layout = Layout(*layout_items)
    filter_instance.form.helper = helper

# Form Helper — Renames the first choice in a Selection menu
def set_first_choice(field, placeholder):
    """Set the first choice of a specified field safely without overwriting data."""
    # 1. Handle fields with explicit empty_label (ModelChoiceField, etc.)
    if hasattr(field, 'empty_label'):
        field.empty_label = placeholder
        return

    # 2. Handle ChoiceFields or fields with a choices attribute
    if not hasattr(field, 'choices'):
        return
        
    choices = list(field.choices)
    
    # Check if the first choice looks like an empty placeholder
    is_empty = False
    if choices:
        val, lbl = choices[0]
        # Common empty values: None, '', 0
        # Common empty labels: empty string, or Django's default '---------'
        if val in ('', None) or (isinstance(val, int) and val == 0 and not lbl):
             is_empty = True
        elif lbl and ('---' in str(lbl) or str(lbl).strip() == ''):
             is_empty = True

    if is_empty:
        val = choices[0][0]
        choices[0] = (val, placeholder)
    else:
        # Otherwise insert a standard empty string choice
        choices.insert(0, ('', placeholder))
        
    field.choices = choices


# Form Helper — Translates a choices list using MS_TRANS choice_ prefix
def translate_choices(choices, ms_trans):
    """
    Translate a choices list using MS_TRANS choice_ prefix.
    Expects choices in format [(value, label), ...]
    """
    translated = []
    for value, label in choices:
        if value == '' or value is None:
            # Keep placeholder as is (or '---' if not set)
            translated.append((value, label or '---'))
        else:
            translated.append((value, ms_trans.get(f'choice_{value}', label)))
    return translated


# Form Helper — Detects if a Crispy form layout already contains Submit/Button elements
def has_submit_button(form):
    """
    Recursively inspects a Crispy Form helper layout to determine if the developer
    has already included a Submit or Button object. Used to auto-hide duplicate
    buttons in generic modal/section templates.
    """
    if not hasattr(form, 'helper') or not form.helper or not getattr(form.helper, 'layout', None):
        return False
        
    from crispy_forms.layout import Submit, Button, HTML
    
    # Layout Inspector — Recursively checks for Submit/Button objects in layout
    def check_node(node):
        # Direct match for Submit or Button objects
        if isinstance(node, (Submit, Button)):
            return True
            
        # Match inside raw HTML objects
        if isinstance(node, HTML) and hasattr(node, 'html'):
            html_content = str(node.html).lower()
            if '<button' in html_content and 'type="submit"' in html_content:
                return True
            if '<input' in html_content and 'type="submit"' in html_content:
                return True
            if 'class="btn' in html_content and ('save' in html_content or 'حفظ' in html_content):
                # Catch-all for generic styled buttons that look like save buttons
                return True
                
        # Recursive check for any nested layout objects (Rows, Divs, Fieldsets, etc.)
        if hasattr(node, 'fields') and node.fields:
            for child in node.fields:
                if check_node(child):
                    return True
        return False
        
    for item in form.helper.layout.fields:
        if check_node(item):
            return True
            
    return False

