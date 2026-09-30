"""dlux.utils.crud — Generic detail/table/filter builders and form/crispy helpers.

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

# Context Menu - Function filters row actions by permissions and section rules.
def filter_context_actions(user, actions, manage_sections_perm=None):
    """
    Filter a list of context menu actions based on user permissions.
    Each action can have a 'permissions' key (list of strings) or 'permission' (string).
    If user lacks any required permission, the action is excluded.

    The manage_sections permission is a *scoped* override: it only grants actions
    that explicitly opt in with a truthy 'section_action' flag (the section/
    subsection management surfaces). It deliberately does NOT bypass per-model
    permissions on generic data-grid actions — e.g. a manage_sections holder
    without `app.delete_model` must not be offered the Delete entry. This keeps
    UI visibility aligned with backend authorization (DSRP-1).

    Args:
        user: The user to check permissions for
        actions: List of action dicts, each may contain 'permissions' or 'permission'
                 and, for section surfaces, 'section_action': True.
        manage_sections_perm: Optional permission string (e.g., 'dlux.manage_sections')
                             that grants section-flagged actions. Defaults to
                             'dlux.manage_sections' if None.
    """
    if not user or not user.is_authenticated:
        return []

    # Determine the manage_sections permission to check
    if manage_sections_perm is None:
        manage_sections_perm = 'dlux.manage_sections'

    # Check if user has manage_sections permission (grants section-flagged actions)
    has_manage_sections = user.has_perm(manage_sections_perm)

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
            elif has_manage_sections and action.get('section_action'):
                # manage_sections only overrides actions explicitly flagged as
                # section-management actions — never generic per-model actions.
                pass
            elif not user.has_perms(required_perms):
                continue

        filtered.append(action)

    return filtered

# Generic Detail - Function gathers reverse and many-to-many related objects.
def collect_related_objects(instance, ignore_relations=None):
    """
    Introspects a model instance to find all related objects (Reverse FK, M2M).
    Returns a dictionary: { 'Verbose Name Plural': ['Item 1', 'Item 2'] }
    Used for Smart Delete functionality and Smart View.
    """
    related_data = {}
    ignored = set(ignore_relations or ())
    
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
                if accessor in ignored:
                    continue
                
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
                if field.name in ignored:
                    continue
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

# Generic Detail - Helper builds field rows for fallback detail views.
def _build_generic_detail_context(instance, request=None):
    """
    Dynamically generates a list of {'label': ..., 'value': ...} dictionaries 
    from a model instance for zero-boilerplate detail views.
    Respects translations and the 'is_scope_enabled' global setting.
    """
    from dlux.utils import is_scope_enabled

    s = get_strings(get_current_language_code(request))

    fields_data = []
    
    # Audit fields are rendered as a dedicated grouped block by the
    # {% dlux_audit_trail %} tag (gated by the show_audit_fields setting +
    # view_audit_fields permission), so they stay out of the flat field loop.
    from ..system.constants import record_visibility_column_names
    exclude_fields = ['password', *record_visibility_column_names()]

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

    try:
        from dlux.models import SystemSettings, _SYSTEM_SETTINGS_FLAT_CONFIG_FIELDS
    except Exception:
        SystemSettings = None
        _SYSTEM_SETTINGS_FLAT_CONFIG_FIELDS = {}

    if SystemSettings is not None and isinstance(instance, SystemSettings):
        concrete_field_names = {field.name for field in instance._meta.get_fields() if getattr(field, 'concrete', False)}

        class _CompatField:
            many_to_many = False
            choices = ()

            def __init__(self, name):
                self.name = name
                self.verbose_name = name.replace('_', ' ')

        for field_name in _SYSTEM_SETTINGS_FLAT_CONFIG_FIELDS:
            if field_name in exclude_fields or field_name in concrete_field_names:
                continue
            try:
                field = _CompatField(field_name)
                value = getattr(instance, field_name, None)
                if isinstance(value, bool):
                    value = f'<i class="bi bi-check-circle-fill text-success"></i>' if value else f'<i class="bi bi-x-circle text-danger"></i>'
                elif value is None or value == "":
                    value = "-"
                label = resolve_detail_field_label(instance, field, request=request, strings=s)
                fields_data.append({
                    'label': str(label).capitalize(),
                    'value': value,
                    'is_html': isinstance(value, str) and ('<a' in value or '<i' in value)
                })
            except Exception:
                pass

    return fields_data

# Generic Detail - Function resolves translated labels for detail fields.
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

# Generic Tables - Helper creates fallback django-tables2 table classes.
def _build_generic_table_class(model):
    """
    Build a minimal django-tables2 Table for a model.
    Build Meta dynamically so django-tables2 sees Meta.model at class creation.
    Generated tables inherit the full Dlux table platform by default.
    """
    from dlux.tables import DluxTable
    
    raw_exclude = getattr(model, "table_exclude", None)
    if raw_exclude is None:
        raw_exclude = []
    elif isinstance(raw_exclude, (str, bytes)):
        raw_exclude = [raw_exclude]
    else:
        raw_exclude = list(raw_exclude)

    # Audit + soft-delete columns are excluded by default. When a viewer is
    # permitted, the patched Table.__init__ ADDS them back via extra_columns —
    # that path works uniformly for auto-tables and for project tables that
    # declare an explicit Meta.fields (which never list audit columns).
    from ..system.constants import record_visibility_column_names
    audit_fields = list(record_visibility_column_names())
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
            'data-dlux-context': 'true',
        },
    }
    if raw_exclude:
        meta_attrs["exclude"] = list(dict.fromkeys(raw_exclude))
    Meta = type("Meta", (), meta_attrs)
    table_attrs = {"Meta": Meta}
    return type(f"{model.__name__}AutoTable", (DluxTable,), table_attrs)

# Generic Filters - Helper creates fallback django-filter FilterSet classes.
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

    # Generic Filters - Helper parses numeric keyword searches without raising.
    def _parse_number(value):
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None

    # Generic Filters - Method patches generated filters with translated labels.
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

    # Generic Filters - Method applies broad keyword search across model fields.
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
            widget=dj_forms.DateInput(attrs={'class': 'form-control dlux-datepicker', 'placeholder': 'من تاريخ', 'autocomplete': 'off'}),
        )
        attrs["date_lte"] = django_filters.DateFilter(
            field_name=date_field,
            lookup_expr="lte",
            label='',
            widget=dj_forms.DateInput(attrs={'class': 'form-control dlux-datepicker', 'placeholder': 'إلى تاريخ', 'autocomplete': 'off'}),
        )
        attrs["year"] = django_filters.ChoiceFilter(
            field_name=f"{date_field}__year",
            lookup_expr="exact",
            choices=[],
            empty_label="السنة",
        )

    # Apply same default exclusions to filters to avoid clutter
    from ..system.constants import record_visibility_column_names
    meta_attrs["exclude"] = list(record_visibility_column_names())

    return type(f"{model.__name__}AutoFilter", (django_filters.FilterSet,), attrs)

# Form Styling - Function applies Dlux widget classes and runtime affordances.
def set_field_attrs(form, request=None, inline_labels=False):
    """Set common attributes for all fields in the form."""
    from dlux.translations import get_current_language_code

    lang = get_current_language_code(request)
    dlux_strings = get_strings(lang)
    
    # Detect language for direction
    direction = 'rtl' if lang.startswith('ar') else 'ltr'
    
    for field_name in form.fields:
        field = form.fields.get(field_name)
        # Try to get label from DLUX_STRINGS (model-specific first, then generic)
        model_name = ""
        if hasattr(form, '_meta') and hasattr(form._meta, 'model'):
             model_name = form._meta.model.__name__.lower()
        
        label_key_model = f"label_{model_name}_{field_name}" if model_name else None
        label_key_generic = f"label_{field_name}"
        
        label = dlux_strings.get(label_key_model) if label_key_model else None
        if not label:
            label = dlux_strings.get(label_key_generic)
        
        if not label:
            # Handle auto-generated filter suffixes (gte/lte) for cleaner Arabic translation
            clean_name = field_name
            suffix = ""
            range_type = None
            if "__gte" in field_name:
                clean_name = field_name.replace("__gte", "")
                suffix = f" ({dlux_strings.get('filter_from', 'From')})"
                range_type = "from"
            elif "__lte" in field_name:
                clean_name = field_name.replace("__lte", "")
                suffix = f" ({dlux_strings.get('filter_to', 'To')})"
                range_type = "to"
            elif field_name.endswith("_gte"):
                clean_name = field_name[:-4]
                suffix = f" ({dlux_strings.get('filter_from', 'From')})"
                range_type = "from"
            elif field_name.endswith("_lte"):
                clean_name = field_name[:-4]
                suffix = f" ({dlux_strings.get('filter_to', 'To')})"
                range_type = "to"

            if clean_name == "date" and range_type == "from":
                label = dlux_strings.get('filter_date_from')
            elif clean_name == "date" and range_type == "to":
                label = dlux_strings.get('filter_date_to')
            
            if not label:
                # Try to resolve base label (e.g. label_created_at)
                base_label = (
                    dlux_strings.get(f"label_{clean_name}")
                    or dlux_strings.get(f"filter_{clean_name}")
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
                        dlux_strings.get(f"label_{clean_name}")
                        or dlux_strings.get(f"filter_{clean_name}")
                        or dlux_strings.get(f"label_{base_label.lower()}")
                        or dlux_strings.get(f"filter_{base_label.lower()}")
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
            if isinstance(widget, forms.Textarea) and field.widget.attrs.get('rows') in (None, 10, '10'):
                field.widget.attrs['rows'] = 2
            
        # 3. Inject the shared DjangoLux datepicker hook for real date/datetime inputs.
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
        
        if is_date and 'dlux-datepicker' not in field.widget.attrs.get('class', '') and 'flatpickr' not in field.widget.attrs.get('class', ''):
            current_class = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f"{current_class} dlux-datepicker".strip()
        if is_date:
            field.widget.attrs['autocomplete'] = 'off'

# Filter UI - Function builds the standard compact filter form layout.
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
    helper.form_class = 'py-3 row g-2 no-print m-0 dlux-form dlux-filter'
    
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
        search_btn = '<button type="submit" class="btn btn-secondary dlux-filter-chip dlux-filter-submit rounded-start-pill rounded-end-0 flex-grow-1"><i class="bi bi-search"></i></button>'
        clear_btn = f'<a href="{clear_url}" class="btn btn-warning dlux-filter-chip dlux-filter-clear rounded-end-pill rounded-start-0 px-3"><i class="bi bi-x-lg"></i></a>'
        btn_html = f'<div class="d-flex w-100 dlux-filter-controls">{search_btn}{clear_btn}</div>'
    else:
        search_btn = '<button type="submit" class="btn btn-secondary dlux-filter-chip dlux-filter-submit rounded-pill flex-grow-1"><i class="bi bi-search"></i></button>'
        btn_html = f'<div class="d-flex w-100 dlux-filter-controls">{search_btn}</div>'
    
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


# Form Choices - Function safely replaces a field placeholder choice.
def _sync_widget_choices(field):
    """Push the field's choices onto its widget.

    A form field and its widget hold choices separately. `ModelChoiceField`
    hands its widget a live `ModelChoiceIterator`, so changing `empty_label`
    shows up in the rendered `<select>` on its own — but a plain `ChoiceField`
    (including django-filter's) gives the widget a snapshot list, so the same
    change never reaches the markup and the placeholder stays "---------".
    That asymmetry is why a model-backed filter picked up its label while a
    year or a status filter did not.
    """
    widget = getattr(field, 'widget', None)
    if widget is None or not hasattr(field, 'choices'):
        return
    try:
        widget.choices = field.choices
    except (AttributeError, TypeError):
        # A widget that does not carry choices (a text input behind a custom
        # field, say) has nothing to sync and is not an error.
        pass


def set_first_choice(field, placeholder):
    """Set the first choice of a specified field safely without overwriting data."""
    # 1. Handle fields with explicit empty_label (ModelChoiceField, etc.)
    if hasattr(field, 'empty_label'):
        field.empty_label = placeholder
        _sync_widget_choices(field)
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
    _sync_widget_choices(field)

# Form Choices - Function translates Django choices through DLUX_STRINGS.
def translate_choices(choices, dlux_strings):
    """
    Translate a choices list using DLUX_STRINGS choice_ prefix.
    Expects choices in format [(value, label), ...]
    """
    translated = []
    for value, label in choices:
        if value == '' or value is None:
            # Keep placeholder as is (or '---' if not set)
            translated.append((value, label or '---'))
        else:
            translated.append((value, dlux_strings.get(f'choice_{value}', label)))
    return translated

# Crispy Layout - Function detects whether a layout already includes submit controls.
def has_submit_button(form):
    """
    Recursively inspects a Crispy Form helper layout to determine if the developer
    has already included a Submit or Button object. Used to auto-hide duplicate
    buttons in generic modal/section templates.
    """
    # NB: an empty FormHelper is falsy (crispy's __len__ counts layout fields),
    # so test for absence explicitly — a helper carrying only inputs is valid.
    if getattr(form, 'helper', None) is None:
        return False

    from crispy_forms.layout import Submit, Button, HTML

    # crispy_forms' `helper.add_input(Submit(...))` — the most common way a form
    # declares its own Save button — stores it on `helper.inputs`, NOT in the
    # layout. Inspect inputs first so those buttons are detected too (otherwise
    # the generic section/modal template renders a duplicate Save button).
    for inp in (getattr(form.helper, 'inputs', None) or []):
        if isinstance(inp, (Submit, Button)):
            return True
        if str(getattr(inp, 'input_type', '')).lower() == 'submit':
            return True

    if not getattr(form.helper, 'layout', None):
        return False

    # Crispy Layout - Helper recursively inspects layout nodes for submit controls.
    def check_node(node):
        # Direct match for Submit or Button objects
        if isinstance(node, (Submit, Button)):
            return True
            
        # Match inside raw HTML objects
        if isinstance(node, HTML) and hasattr(node, 'html'):
            html_content = str(node.html).lower()
            if '<button' in html_content and (
                'type="submit"' in html_content or
                "type='submit'" in html_content or
                'type=submit' in html_content
            ):
                return True
            if '<input' in html_content and (
                'type="submit"' in html_content or
                "type='submit'" in html_content or
                'type=submit' in html_content
            ):
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


# ── Sticky forms ────────────────────────────────────────────────────────────
# Prefilling an add-form from the user's last record is a server-side concern:
# the initial data has to be in the form before it renders. Projects gate their
# prefill on this helper instead of reading a cookie, so the switch in Options
# (and the inline one on the form) actually controls it.

STICKY_FORMS_PREFERENCE = 'sticky_forms'
STICKY_FORMS_DEFAULT = False


def sticky_forms_enabled(request):
    """Whether this user wants add-forms prefilled from their last record.

    Reads the `sticky_forms` user preference. Falls back to the shipped default
    for anonymous users or a profile that has never set it.
    """
    user = getattr(request, 'user', None)
    if user is None or not getattr(user, 'is_authenticated', False):
        return STICKY_FORMS_DEFAULT
    try:
        preferences = user.profile.preferences
    except Exception:
        return STICKY_FORMS_DEFAULT
    if not isinstance(preferences, dict):
        return STICKY_FORMS_DEFAULT
    return bool(preferences.get(STICKY_FORMS_PREFERENCE, STICKY_FORMS_DEFAULT))


def sticky_form_initial(request, model, fields, *, order_by='-pk', transform=None):
    """Initial data for an add-form, taken from the user's most recent record.

    Returns `{}` when sticky forms are off, when the model has no rows, or when
    the request is not a GET — so a call site can hand the result straight to a
    form's `initial=` without branching.

    `fields` maps form field name -> model attribute name (or a callable taking
    the instance). `transform` post-processes the resulting dict, which is where
    a project increments a reference number.
    """
    if request.method != 'GET' or not sticky_forms_enabled(request):
        return {}

    last = model._default_manager.order_by(order_by).first()
    if last is None:
        return {}

    initial = {}
    for form_field, source in (fields or {}).items():
        value = source(last) if callable(source) else getattr(last, source, None)
        if value is not None:
            initial[form_field] = value

    if callable(transform):
        initial = transform(initial, last) or initial
    return initial
