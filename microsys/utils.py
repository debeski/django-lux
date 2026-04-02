from django.apps import apps
from django.utils.module_loading import import_string
from django import forms
from django.forms import modelform_factory
import django_tables2 as tables
from django.http import JsonResponse
import json
# try-except for django_filters as it might not be installed (though likely is)
try:
    import django_filters
except ImportError:
    django_filters = None

from django.db.models import ManyToManyField, ManyToManyRel, Q
from django.db import models as dj_models
from decimal import Decimal, InvalidOperation
import inspect
from .translations import get_strings
from django.conf import settings


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

def get_system_config():
    """
    Returns the deeply merged system configuration.
    1. Default config
    2. settings.MICROSYS_CONFIG (host project codebase)
    3. SystemSettings Singleton (database UI overrides)
    """
    # Default configuration
    default_config = {
        'name': 'microsys',
        'verbose_name': 'ادارة النظام',
        'logo': '/static/img/base_logo.png',
        'login_logo': '/static/img/login_logo.webp',
        'favicon': '/static/favicon.ico',
        'home_url': '/sys/users/',
        'default_language': 'en',
        'languages': {
            'ar': {'name': 'العربية', 'dir': 'rtl', 'flag': '🇱🇾'},
            'en': {'name': 'English', 'dir': 'ltr', 'flag': '🇬🇧'},
        },
        'translations': {}
    }

    # Project settings
    user_config = getattr(settings, 'MICROSYS_CONFIG', {})
    
    # DB settings
    db_config = {}
    try:
        from microsys.models import SystemSettings
        sys_settings = SystemSettings.load()
        # Only pull non-empty values from DB (since UI can leave text fields empty or json fields empty dict/array)
        # Avoid overriding with defaults if user hasn't explicitly set them
        if sys_settings.name and sys_settings.name not in ['microsys', 'ادارة النظام']:
            db_config['name'] = sys_settings.name
        if sys_settings.name_en:
            db_config['name_en'] = sys_settings.name_en
        if sys_settings.logo:
            db_config['logo'] = sys_settings.logo.url
        if sys_settings.favicon:
            db_config['favicon'] = sys_settings.favicon.url
        if sys_settings.home_url != '/sys/':
            db_config['home_url'] = sys_settings.home_url
        if sys_settings.default_language != 'ar':
            db_config['default_language'] = sys_settings.default_language
        if sys_settings.languages:
            db_config['languages'] = sys_settings.languages
        if sys_settings.translations_override:
            db_config['translations'] = sys_settings.translations_override
    except Exception:
        pass

    # Merge
    final_config = default_config.copy()
    final_config.update({k:v for k,v in user_config.items() if k not in ['languages', 'translations']})
    final_config.update({k:v for k,v in db_config.items() if k not in ['languages', 'translations']})
    
    # Preemptively strip localized overrides if the base key was explicitly provided by DB
    for db_k in db_config.keys():
        if db_k not in ['languages', 'translations']:
            for lang_code in final_config.get('languages', {}).keys():
                loc_key = f"{db_k}_{lang_code}"
                if loc_key not in db_config:
                    final_config.pop(loc_key, None)
    
    # Deep merge languages
    langs = default_config['languages'].copy()
    if 'languages' in user_config:
        langs.update(user_config['languages'])
    if 'languages' in db_config:
        langs.update(db_config['languages'])
    final_config['languages'] = langs
    
    # Deep merge translations
    trans = default_config['translations'].copy()
    for layer in [user_config.get('translations', {}), db_config.get('translations', {})]:
        if layer:
            for lang, keys in layer.items():
                if lang not in trans:
                    trans[lang] = {}
                trans[lang].update(keys)
    final_config['translations'] = trans

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

from django.db.models.fields.files import FieldFile
from django.db.models.fields.related import ManyToManyField
def _build_generic_detail_context(instance, request=None):
    """
    Dynamically generates a list of {'label': ..., 'value': ...} dictionaries 
    from a model instance for zero-boilerplate detail views.
    Respects translations and the 'is_scope_enabled' global setting.
    """
    from microsys.utils import is_scope_enabled
    from microsys.translations import get_strings

    s = get_strings()
    if request and request.user.is_authenticated and hasattr(request.user, 'profile'):
        lang = request.user.profile.preferences.get('language', 'en') if request.user.profile.preferences else 'en'
        s = get_strings(lang)

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
            
            label = getattr(field, 'verbose_name', field.name)
            
            fields_data.append({
                'label': str(label).capitalize(),
                'value': value,
                'is_html': isinstance(value, str) and ('<a' in value or '<i' in value)
            })
        except Exception:
            pass

    return fields_data


# Dynamic Table Builder — Generates a django-tables2 Table class at runtime
def _build_generic_table_class(model):
    """
    Build a minimal django-tables2 Table for a model.
    Build Meta dynamically so django-tables2 sees Meta.model at class creation.
    Includes row_attrs for context menu support.
    """
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

    # Scope exclusion deferred to runtime in __init__

    meta_attrs = {
        "model": model,
        "template_name": "django_tables2/bootstrap5.html",
        "attrs": {'class': 'table table-hover align-middle'},
        "row_attrs": {
            'class': 'section-row',
            'data-pk': lambda record: record.pk,
            'data-name': lambda record: str(record),
            
            # Context Menu Injection
            'data-micro-context': 'true',
        },
    }
    def __init__(self, *args, translations=None, request=None, **kwargs):
        if has_scope_field and not is_scope_enabled():
            exclude_kwargs = kwargs.get('exclude', tuple(raw_exclude))
            if isinstance(exclude_kwargs, list):
                exclude_kwargs = tuple(exclude_kwargs)
            if 'scope' not in exclude_kwargs:
                kwargs['exclude'] = exclude_kwargs + ('scope',)
                
        model_name = kwargs.pop('model_name', None)
        super(self.__class__, self).__init__(*args, **kwargs)
        if model_name:
            self.model_name = model_name
        self.request = request
        
        s = translations or get_strings()
        
        # Context Menu Helper
        def get_actions(record):
            actions = [
                {
                    "label": s.get('view_label', 'عرض المحتوى'), # View Details
                    "icon": "bi bi-eye",
                    "type": "event",
                    "event": "micro:record:view", 
                    "data": {"model": model._meta.model_name, "id": record.pk, "name": str(record)},
                    "dblclick": True
                },
                {"type": "divider"},
                {
                    "label": s.get('edit_label', 'تعديل'), # Edit
                    "icon": "bi bi-pencil",
                    "type": "event",
                    "event": "micro:record:edit",
                    "data": {"model": model._meta.model_name, "id": record.pk, "name": str(record)},
                    "permissions": [f"microsys.change_{model._meta.model_name}"]
                },
                {
                    "label": s.get('delete_label', 'حذف'), # Delete
                    "icon": "bi bi-trash",
                    "type": "event",
                    "event": "micro:record:delete", 
                    "data": {"model": model._meta.model_name, "id": record.pk, "name": str(record)},
                    "textClass": "text-danger",
                    "permissions": [f"microsys.delete_{model._meta.model_name}"]
                }
            ]
            
            if self.request and self.request.user:
                actions = filter_context_actions(self.request.user, actions)

            return json.dumps(actions)
        
        self.row_attrs["data-micro-actions"] = get_actions

    if raw_exclude:
        meta_attrs["exclude"] = list(dict.fromkeys(raw_exclude))
    Meta = type("Meta", (), meta_attrs)
    table_attrs = {"Meta": Meta, "__init__": __init__}
    return type(f"{model.__name__}AutoTable", (tables.Table,), table_attrs)

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

    def _parse_number(value):
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None

    def _init(self, *args, **kwargs):
        super(self.__class__, self).__init__(*args, **kwargs)

        if date_field and 'year' in self.filters:
            years = self.Meta.model.objects.dates(date_field, 'year').distinct()
            self.filters['year'].extra['choices'] = [(year.year, year.year) for year in years]
            self.filters['year'].field.widget.attrs.update({
                'class': 'auto-submit-filter'
            })

        if not hasattr(self.form, 'helper') or self.form.helper is None:
            # Layout handled by setup_filter_helper in the view
            pass

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
            widget=dj_forms.DateInput(attrs={'class': 'form-control flatpickr', 'placeholder': 'من تاريخ'}),
        )
        attrs["date_lte"] = django_filters.DateFilter(
            field_name=date_field,
            lookup_expr="lte",
            label='',
            widget=dj_forms.DateInput(attrs={'class': 'form-control flatpickr', 'placeholder': 'إلى تاريخ'}),
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


# Form Helper — Automatically sets placeholders and direction based on language
def set_field_attrs(form, request=None):
    """Set common attributes for all fields in the form."""
    ms_trans = get_strings()
    
    # Detect language for direction
    from microsys.translations import get_current_language_code
    lang = get_current_language_code()
    direction = 'rtl' if lang.startswith('ar') else 'ltr'
    
    for field_name in form.fields:
        field = form.fields.get(field_name)
        # Try to get label from MS_TRANS if it looks like a key, or use verbose name
        label_key = f"label_{field_name}"
        label = ms_trans.get(label_key)
        
        if not label:
            # Handle auto-generated filter suffixes (gte/lte) for cleaner Arabic translation
            clean_name = field_name
            suffix = ""
            if "__gte" in field_name:
                clean_name = field_name.replace("__gte", "")
                suffix = f" ({ms_trans.get('filter_from', 'من')})"
            elif "__lte" in field_name:
                clean_name = field_name.replace("__lte", "")
                suffix = f" ({ms_trans.get('filter_to', 'إلى')})"
            
            # Try to resolve base label (e.g. label_created_at)
            base_label = ms_trans.get(f"label_{clean_name}") or field.label
            
            # If default field.label is messy (auto-generated English), clean it
            if not base_label or 'is greater than' in base_label or 'is less than' in base_label:
                base_label = clean_name.replace('_', ' ').split('.')[-1].title()
                # Secondary lookup for core field name in translations
                base_label = ms_trans.get(f"label_{base_label.lower()}") or base_label
            
            label = f"{base_label}{suffix}"

        # Common attributes
        field.widget.attrs['placeholder'] = label
        field.widget.attrs['dir'] = direction  # Set text direction dynamically
        
        # Inject Bootstrap classes based on widget type
        existing_class = field.widget.attrs.get('class', '')
        if isinstance(field.widget, (forms.Select, forms.NullBooleanSelect)):
            if 'form-select' not in existing_class:
                field.widget.attrs['class'] = f"{existing_class} form-select".strip()
            # Automatically apply label as first choice (placeholder) for dropdowns
            set_first_choice(field, label)
        elif isinstance(field.widget, (forms.SelectMultiple)):
            if 'form-select' not in existing_class:
                field.widget.attrs['class'] = f"{existing_class} form-select".strip()
        elif isinstance(field.widget, (forms.CheckboxInput, forms.RadioSelect)):
            if 'form-check-input' not in existing_class:
                field.widget.attrs['class'] = f"{existing_class} form-check-input".strip()
        else:
            if 'form-control' not in existing_class:
                field.widget.attrs['class'] = f"{existing_class} form-control".strip()
            
        # 3. Inject Flatpickr for date/datetime fields
        # Check by widget, field name, or existing library classes (like datetimeinput from crispy)
        is_date = any(kw in field_name.lower() for kw in ['date', 'time', 'since', 'until']) or \
                  isinstance(field.widget, (forms.DateInput, forms.DateTimeInput)) or \
                  'datetimeinput' in existing_class
        
        if is_date and 'flatpickr' not in field.widget.attrs.get('class', ''):
            current_class = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f"{current_class} flatpickr".strip()

        field.label = ''  # Clear the label for crispy layouts that use placeholders


def setup_filter_helper(filter_instance, request=None, preserve_keys=None):
    """
    Sets up a modern, responsive Crispy layout for a django-filter FilterSet.
    Aligns fields dynamically using Bootstrap 5 flexbox and appends a filter button.
    """
    from crispy_forms.helper import FormHelper
    from crispy_forms.layout import Layout, Div, Field, HTML, Hidden
    
    helper = FormHelper()
    helper.form_method = 'get'
    helper.form_tag = True
    helper.form_class = 'no-print'
    
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
        search_btn = '<button type="submit" class="btn btn-secondary rounded-start-pill rounded-end-0 flex-grow-1"><i class="bi bi-search"></i></button>'
        clear_btn = f'<a href="{clear_url}" class="btn btn-warning rounded-end-pill rounded-start-0 px-3"><i class="bi bi-x-lg"></i></a>'
        btn_html = f'<div class="d-flex w-100">{search_btn}{clear_btn}</div>'
    else:
        search_btn = '<button type="submit" class="btn btn-secondary rounded-pill flex-grow-1"><i class="bi bi-search"></i></button>'
        btn_html = f'<div class="d-flex w-100">{search_btn}</div>'
    
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
    
    # Apply set_field_attrs for placeholders and translation
    set_field_attrs(filter_instance.form, request)

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
