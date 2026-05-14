"""
Auto-injection patches for ScopedModel.
Applied in AppConfig.ready() to monkey-patch Django base classes so that
ANY ModelForm / FilterSet / Table whose model inherits from ScopedModel
gets automatic scope handling — zero developer effort required.
"""
import copy
import json
import logging

logger = logging.getLogger('microsys')

# Cache for issubclass checks to avoid repeated MRO lookups
_scoped_model_cache = {}
_MICROSYS_TABLE_TEMPLATE = 'microsys/tables/table.html'
_STOCK_TABLE_TEMPLATES = {
    '',
    None,
    'django_tables2/bootstrap.html',
    'django_tables2/bootstrap4.html',
    'django_tables2/bootstrap5.html',
    'django_tables2/semantic.html',
    'django_tables2/table.html',
}


def _is_scoped_model(model):
    """Check (with cache) if a model class inherits from ScopedModel."""
    if model is None:
        return False
    model_id = id(model)
    if model_id not in _scoped_model_cache:
        try:
            from microsys.models import ScopedModel
            _scoped_model_cache[model_id] = issubclass(model, ScopedModel)
        except (ImportError, TypeError):
            _scoped_model_cache[model_id] = False
    return _scoped_model_cache[model_id]


def _get_user_from_kwargs(kwargs):
    """
    Extract user from kwargs before subclass __init__ pops them.
    Supports both 'user' and 'request.user' patterns.
    """
    user = kwargs.get('user')
    if not user:
        request = kwargs.get('request')
        if request:
            user = getattr(request, 'user', None)
    return user


def _should_lock_scope(user):
    """
    Check if scope should be locked for this user.
    Locked means the user cannot see or change the scope field in forms.
    Only superusers are exempt from locking.
    """
    if not user or not hasattr(user, 'is_authenticated') or not user.is_authenticated:
        return False
    return not user.is_superuser


def _table_meta_value(table_meta, name, default=None):
    if table_meta is None:
        return default
    if isinstance(table_meta, type):
        meta = getattr(table_meta, 'Meta', None)
        if meta is not None and hasattr(meta, name):
            return getattr(meta, name)
        runtime_meta = getattr(table_meta, '_meta', None)
        if runtime_meta is not None and hasattr(runtime_meta, name):
            return getattr(runtime_meta, name)
        if hasattr(table_meta, name):
            value = getattr(table_meta, name)
            if not isinstance(value, property):
                return value
        return default
    if hasattr(table_meta, name):
        return getattr(table_meta, name)
    meta = getattr(table_meta, 'Meta', None)
    if meta is not None and hasattr(meta, name):
        return getattr(meta, name)
    return default


def _table_meta_explicit_value(table_meta, name, default=None):
    if table_meta is None:
        return default
    meta = getattr(table_meta, 'Meta', None) if isinstance(table_meta, type) else None
    if meta is not None and name in getattr(meta, '__dict__', {}):
        return getattr(meta, name)
    if not isinstance(table_meta, type):
        meta = getattr(table_meta, 'Meta', None)
        if meta is not None and name in getattr(meta, '__dict__', {}):
            return getattr(meta, name)
        if name in getattr(table_meta, '__dict__', {}):
            value = getattr(table_meta, name)
            if not isinstance(value, property):
                return value
    return default


def _merge_class_tokens(existing, *tokens):
    merged = [token for token in str(existing or '').split() if token]
    for token in tokens:
        if token and token not in merged:
            merged.append(token)
    return ' '.join(merged)


def _is_valid_table_density(value):
    from microsys.constants import TABLE_DENSITY_VALUES

    return value in TABLE_DENSITY_VALUES


def _resolve_table_density(request, table_meta):
    from microsys.constants import DEFAULT_TABLE_DENSITY
    from microsys.middleware import get_current_user
    from microsys.utils import get_system_config

    forced_density = _table_meta_value(table_meta, 'microsys_density')
    if _is_valid_table_density(forced_density):
        return forced_density

    user = getattr(request, 'user', None) if request is not None else None
    if user is None:
        user = get_current_user()

    if user is not None and getattr(user, 'is_authenticated', False) and hasattr(user, 'profile'):
        preferences = getattr(user.profile, 'preferences', None) or {}
        if isinstance(preferences, dict) and _is_valid_table_density(preferences.get('table_density')):
            return preferences['table_density']

    default_density = get_system_config().get('default_table_density', DEFAULT_TABLE_DENSITY)
    if _is_valid_table_density(default_density):
        return default_density

    return DEFAULT_TABLE_DENSITY


def _coerce_positive_int(value):
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        return None
    if coerced <= 0:
        return None
    return coerced


def _normalize_table_page_size_options(raw_options):
    from microsys.constants import TABLE_PAGE_SIZE_OPTIONS

    if raw_options is None:
        return TABLE_PAGE_SIZE_OPTIONS
    if isinstance(raw_options, (str, bytes)):
        raw_options = [raw_options]
    elif not isinstance(raw_options, (list, tuple, set)):
        return TABLE_PAGE_SIZE_OPTIONS

    cleaned = []
    for value in raw_options:
        coerced = _coerce_positive_int(value)
        if coerced is not None and coerced not in cleaned:
            cleaned.append(coerced)

    return tuple(cleaned) or TABLE_PAGE_SIZE_OPTIONS


def _resolve_table_page_size_options(table_meta):
    return _normalize_table_page_size_options(_table_meta_value(table_meta, 'microsys_per_page_options'))


def _resolve_table_per_page_field(table):
    prefix = getattr(table, 'prefix', '') or ''
    return f"{prefix}per_page"


def _get_table_page_size_preference(request):
    if request is None:
        return None
    user = getattr(request, 'user', None)
    if user is None or not getattr(user, 'is_authenticated', False) or not hasattr(user, 'profile'):
        return None
    preferences = getattr(user.profile, 'preferences', None) or {}
    if not isinstance(preferences, dict):
        return None
    return _coerce_positive_int(preferences.get('table_page_size'))


def _persist_table_page_size_preference(request, page_size):
    if request is None:
        return
    user = getattr(request, 'user', None)
    if user is None or not getattr(user, 'is_authenticated', False) or not hasattr(user, 'profile'):
        return

    preferences = getattr(user.profile, 'preferences', None) or {}
    if not isinstance(preferences, dict):
        preferences = {}
    if preferences.get('table_page_size') == page_size:
        return

    preferences = {**preferences, 'table_page_size': page_size}
    user.profile.preferences = preferences
    user.profile.save(update_fields=['preferences'])


def _resolve_table_page_size(request, table, table_meta, explicit_default=None):
    from microsys.constants import DEFAULT_TABLE_PAGE_SIZE

    options = getattr(table, 'microsys_per_page_options', None) or _resolve_table_page_size_options(table_meta)
    override = _coerce_positive_int(_table_meta_explicit_value(table_meta, 'microsys_per_page'))
    if override in options:
        return override

    per_page_field = getattr(table, 'microsys_per_page_field', None) or _resolve_table_per_page_field(table)
    requested_value = None
    if request is not None:
        requested_value = _coerce_positive_int(request.GET.get(per_page_field))
    if requested_value in options:
        _persist_table_page_size_preference(request, requested_value)
        return requested_value

    saved_preference = _get_table_page_size_preference(request)
    if saved_preference in options:
        return saved_preference

    fallback_default = _coerce_positive_int(explicit_default)
    if fallback_default in options:
        return fallback_default

    if DEFAULT_TABLE_PAGE_SIZE in options:
        return DEFAULT_TABLE_PAGE_SIZE
    return options[0]


def _should_enable_microsys_actions(table_meta):
    return _table_meta_value(table_meta, 'microsys_actions', True) is not False


def _should_use_microsys_table(table_meta):
    if _table_meta_value(table_meta, 'microsys_table', True) is False:
        return False
    template_name = _table_meta_value(table_meta, 'template_name')
    return template_name in _STOCK_TABLE_TEMPLATES or template_name == _MICROSYS_TABLE_TEMPLATE


def _clean_context_menu_actions(actions):
    cleaned = []
    for action in actions or []:
        if not isinstance(action, dict):
            continue
        if action.get('type') == 'divider':
            if not cleaned or cleaned[-1].get('type') == 'divider':
                continue
        cleaned.append(action)

    while cleaned and cleaned[-1].get('type') == 'divider':
        cleaned.pop()
    return cleaned


def _get_microsys_record_name(record):
    if hasattr(record, 'get_full_name'):
        value = record.get_full_name() or ''
        if value:
            return value
    return str(record)


def _get_microsys_model_name(table, model):
    if getattr(table, 'model_name', None):
        return table.model_name
    if model is not None:
        return model._meta.model_name
    return ''


def _build_default_microsys_actions(table, record):
    model = getattr(getattr(table, '_meta', None), 'model', None)
    if model is None or getattr(record, 'pk', None) is None:
        return []

    payload = {
        'app': model._meta.app_label,
        'model': _get_microsys_model_name(table, model),
        'id': record.pk,
        'name': _get_microsys_record_name(record),
    }
    return [
        {
            'label': 'view_label',
            'icon': 'bi bi-eye',
            'type': 'event',
            'event': 'micro:record:view',
            'data': payload,
            'dblclick': True,
        },
        {'type': 'divider'},
        {
            'label': 'edit_label',
            'icon': 'bi bi-pencil',
            'type': 'event',
            'event': 'micro:record:edit',
            'data': payload,
            'permissions': [f"{model._meta.app_label}.change_{model._meta.model_name}"],
        },
        {
            'label': 'delete_label',
            'icon': 'bi bi-trash',
            'type': 'event',
            'event': 'micro:record:delete',
            'data': payload,
            'textClass': 'text-danger',
            'permissions': [f"{model._meta.app_label}.delete_{model._meta.model_name}"],
        },
    ]


# ──────────────────────────────────────────────────────────
# 1. ModelForm patch
# ──────────────────────────────────────────────────────────

def _patch_modelform_init():
    """Patch ModelForm.__init__ to auto-inject and manage scope."""
    from django import forms as django_forms

    _original_init = django_forms.ModelForm.__init__

    def _patched_init(self, *args, **kwargs):
        # Peek at user BEFORE subclass __init__ might pop it
        user = _get_user_from_kwargs(kwargs)

        # Call the full MRO chain (subclass → ModelForm → BaseForm)
        _original_init(self, *args, **kwargs)

        # Fallback: check if subclass stored user on self
        if not user:
            from microsys.middleware import get_current_user
            user = get_current_user()

        # Determine model
        meta = getattr(self, 'Meta', None) or getattr(type(self), 'Meta', None)
        model = getattr(meta, 'model', None)
        if not _is_scoped_model(model):
            return

        # Respect explicit exclude
        form_meta = getattr(self, '_meta', None)
        if form_meta and form_meta.exclude and 'scope' in form_meta.exclude:
            return

        # Auto-inject scope field if not present
        if not hasattr(self, 'fields'):
            return

        if 'scope' not in self.fields:
            try:
                scope_model_field = model._meta.get_field('scope')
                form_field = scope_model_field.formfield()
                if form_field is None:
                    # ScopeForeignKey.formfield() returned None, build manually
                    from microsys.models import Scope
                    form_field = django_forms.ModelChoiceField(
                        queryset=Scope.objects.all(),
                        required=False,
                        label=scope_model_field.verbose_name,
                    )
                self.fields['scope'] = form_field

                # Set initial from instance (editing)
                if self.instance and self.instance.pk:
                    self.fields['scope'].initial = getattr(self.instance, 'scope_id', None)

                # Ensure save compatibility: add 'scope' to _meta.fields
                if form_meta and form_meta.fields is not None:
                    self._meta = copy.copy(form_meta)
                    if isinstance(self._meta.fields, tuple):
                        self._meta.fields = self._meta.fields + ('scope',)
                    else:
                        self._meta.fields = list(self._meta.fields) + ['scope']
            except Exception:
                logger.debug("microsys: Could not auto-inject scope into %s", type(self).__name__)
                return

        # ── Visibility logic ──
        from microsys.utils import is_scope_enabled
        scope_enabled = is_scope_enabled()
        lock_scope = _should_lock_scope(user)

        if not scope_enabled or lock_scope:
            if lock_scope and user:
                self.fields['scope'].initial = getattr(getattr(user, 'profile', None), 'scope', None)
            self.fields['scope'].disabled = True
            self.fields['scope'].widget = django_forms.HiddenInput()
            self.fields['scope'].required = False

        # ── Universal Translation Logic ──
        from microsys.translations import get_strings, lazy_translator
        from .utils import get_system_config
        config = get_system_config()
        s = get_strings(overrides=config.get('translations'))

        for name, field in self.fields.items():
            # ── Auto-Scope Logic ──
            # If the field is a ModelChoiceField and uses a ScopedManager, refresh its queryset
            # so that ScopedManager.get_queryset() is re-evaluated with the current user.
            if isinstance(field, (django_forms.ModelChoiceField, django_forms.ModelMultipleChoiceField)):
                try:
                    # Refresh the queryset to trigger ScopedManager filtering with the current user context
                    if hasattr(field.queryset.model, 'objects') and hasattr(field.queryset.model.objects, 'apply_scoping'):
                        field.queryset = field.queryset.model.objects.apply_scoping(field.queryset)
                    else:
                        # Calling .all() on a ScopedManager queryset will re-trigger our filtering
                        field.queryset = field.queryset.all()
                except Exception:
                    pass

            # ── Universal Translation Logic ──
            # Try prefixes: 1. label_[name], 2. label_[raw_label], 3. [name], 4. [raw_label]
            raw_label = str(field.label) if field.label else name
            
            keys = [f"label_{name}", f"label_{raw_label}", name, raw_label]
            for k in keys:
                if k in s:
                    field.label = lazy_translator(k, raw_label)
                    break

    django_forms.ModelForm.__init__ = _patched_init


# ──────────────────────────────────────────────────────────
# 2. FilterSet patch
# ──────────────────────────────────────────────────────────

def _patch_filterset_init():
    """Patch FilterSet.__init__ to auto-inject and manage scope filter."""
    try:
        import django_filters
    except ImportError:
        return

    _original_init = django_filters.FilterSet.__init__

    def _patched_init(self, *args, **kwargs):
        _original_init(self, *args, **kwargs)

        # Determine model
        meta = getattr(type(self), 'Meta', None) or getattr(type(self), '_meta', None)
        model = getattr(meta, 'model', None)
        if not _is_scoped_model(model):
            return

        if not hasattr(self, 'filters'):
            return

        # Auto-inject scope filter if not present
        if 'scope' not in self.filters:
            try:
                from microsys.models import Scope
                self.filters['scope'] = django_filters.ModelChoiceFilter(
                    queryset=Scope.objects.all(),
                    field_name='scope',
                    label='النطاق',
                )
            except Exception:
                return

        # ── Visibility logic: remove if disabled or user is locked ──
        from microsys.utils import is_scope_enabled
        scope_enabled = is_scope_enabled()

        request = getattr(self, 'request', None) or kwargs.get('request')
        user = getattr(request, 'user', None) if request else None
        if not user:
            from microsys.middleware import get_current_user
            user = get_current_user()

        lock_scope = bool(user and _should_lock_scope(user))

        if not scope_enabled or lock_scope:
            if 'scope' in self.filters:
                del self.filters['scope']

        # ── Universal Translation Logic ──
        from microsys.translations import get_strings, lazy_translator
        from .utils import get_system_config
        config = get_system_config()
        s = get_strings(overrides=config.get('translations'))

        from django import forms
        from django_filters import ModelChoiceFilter, ModelMultipleChoiceFilter
        for name, filt in self.filters.items():
            # ── Auto-Scope Logic ──
            # If the filter is a ModelChoiceFilter, refresh its queryset
            if isinstance(filt, (ModelChoiceFilter, ModelMultipleChoiceFilter)):
                try:
                    # Refresh the queryset to trigger ScopedManager filtering with the current user context
                    target_qs = filt.extra.get('queryset')
                    if target_qs is not None and hasattr(target_qs.model, 'objects') and hasattr(target_qs.model.objects, 'apply_scoping'):
                        filt.extra['queryset'] = target_qs.model.objects.apply_scoping(target_qs)
                    elif target_qs is not None:
                        filt.extra['queryset'] = target_qs.all()
                    
                    if hasattr(filt, 'field') and hasattr(filt.field, 'queryset'):
                         filt.field.queryset = filt.field.queryset.all()
                except Exception:
                    pass

            # ── Universal Translation Logic ──
            # Try prefixes: 1. label_[name], 2. label_[raw_label], 3. [name], 4. [raw_label]
            raw_label = str(filt.label) if filt.label else name
            
            keys = [f"label_{name}", f"label_{raw_label}", name, raw_label]
            for k in keys:
                if k in s:
                    filt.label = lazy_translator(k, raw_label)
                    break

    django_filters.FilterSet.__init__ = _patched_init


# ──────────────────────────────────────────────────────────
# 3. Table patch
# ──────────────────────────────────────────────────────────

def _patch_table_init():
    """Patch Table.__init__ to auto-manage scope column and Microsys rendering."""
    try:
        import django_tables2 as tables
    except ImportError:
        return

    _original_init = tables.Table.__init__

    def _patched_init(self, *args, **kwargs):
        # ── Pop microsys-specific kwargs before forwarding to django-tables2 ──
        # Views/tables may pass these custom kwargs which Table.__init__ doesn't accept.
        _ms_translations = kwargs.pop('translations', None)
        request = kwargs.pop('request', None)
        model_name = kwargs.pop('model_name', None)

        # Determine model BEFORE calling original (need to modify kwargs)
        table_cls = type(self)
        model = _table_meta_value(table_cls, 'model')

        if _is_scoped_model(model):
            from microsys.utils import is_scope_enabled
            scope_enabled = is_scope_enabled()

            if not scope_enabled:
                # Add 'scope' to exclude
                exclude = kwargs.get('exclude', _table_meta_value(table_cls, 'exclude', ()) or ())
                if isinstance(exclude, list):
                    exclude = tuple(exclude)
                if 'scope' not in exclude:
                    kwargs['exclude'] = exclude + ('scope',)
            else:
                # Auto-add scope column if not already defined on the class
                has_scope_col = hasattr(table_cls, 'scope') or (
                    'scope' in (_table_meta_value(table_cls, 'fields', ()) or ())
                )
                if not has_scope_col:
                    extra = list(kwargs.get('extra_columns', []))
                    # Don't add if already in extra_columns
                    if not any(name == 'scope' for name, _ in extra):
                        extra.append(('scope', tables.Column(verbose_name='النطاق')))
                        kwargs['extra_columns'] = extra

        _original_init(self, *args, **kwargs)

        # Framework-owned rendering path: adopt the Microsys template unless
        # the table explicitly points at a non-stock custom template or opts out.
        if _should_use_microsys_table(table_cls):
            try:
                self.template_name = _MICROSYS_TABLE_TEMPLATE
            except Exception:
                pass
            try:
                self._meta.template_name = _MICROSYS_TABLE_TEMPLATE
            except Exception:
                pass

        self.request = request
        if model_name:
            self.model_name = model_name
        self.microsys_density_locked = _is_valid_table_density(_table_meta_value(table_cls, 'microsys_density'))
        self.microsys_density = _resolve_table_density(request, table_cls)
        self.microsys_table_enabled = bool(_should_use_microsys_table(table_cls))
        self.microsys_per_page_options = _resolve_table_page_size_options(table_cls)
        self.microsys_per_page_field = _resolve_table_per_page_field(self)
        self.microsys_per_page = _resolve_table_page_size(request, self, table_cls)

        if self.microsys_table_enabled:
            try:
                self.attrs['class'] = _merge_class_tokens(
                    self.attrs.get('class', ''),
                    'table',
                    'table-hover',
                    'align-middle',
                    'ms-data-table',
                )
            except Exception:
                pass

        if self.microsys_table_enabled and _should_enable_microsys_actions(table_cls):
            try:
                if getattr(self, 'row_attrs', None) is None:
                    self.row_attrs = {}
                self.row_attrs.setdefault('data-micro-context', 'true')
                if 'data-micro-actions' not in self.row_attrs:
                    def _default_actions(record, table=self):
                        try:
                            if hasattr(table, 'get_microsys_base_actions'):
                                base_actions = table.get_microsys_base_actions(record) or []
                            else:
                                base_actions = _build_default_microsys_actions(table, record)
                            actions = base_actions
                            if hasattr(table, 'get_microsys_row_actions'):
                                actions = table.get_microsys_row_actions(record, copy.deepcopy(base_actions))
                                if actions is None:
                                    actions = base_actions
                            if table.request and getattr(table.request, 'user', None):
                                from .utils import filter_context_actions
                                actions = filter_context_actions(table.request.user, actions)
                            actions = _clean_context_menu_actions(actions)
                            return json.dumps(actions)
                        except Exception:
                            return "[]"

                    self.row_attrs['data-micro-actions'] = _default_actions
            except Exception:
                pass

        # ── Universal Translation Logic ──
        from microsys.translations import get_strings, lazy_translator
        from .utils import get_system_config
        config = get_system_config()
        s = get_strings(overrides=config.get('translations'))

        # django-tables2: Translate column headers using a lazy proxy
        for name, column in self.columns.items():
            # BoundColumn.verbose_name is read-only, so we must patch the underlying Column object's verbose_name.
            # The underlying Column is shared across requests, so we wrap the string inside a Django lazy proxy
            # that translates dynamically using the current thread's language at render time.
            
            raw_vname = str(column.header) if column.header else name
            
            keys = [f"tbl_{name}", f"label_{name}", f"tbl_{raw_vname}", f"label_{raw_vname}", raw_vname]
            
            for k in keys:
                if k in s:
                    # Found a valid translation key. Wrap it in a lazy translator and attach to the underlying column.
                    column.column.verbose_name = lazy_translator(k, raw_vname)
                    break

        # django-tables2: Translate context menu actions inside row_attrs
        if hasattr(self, 'row_attrs') and 'data-micro-actions' in self.row_attrs:
            orig_actions = self.row_attrs['data-micro-actions']
            if callable(orig_actions):
                def _translated_actions(record):
                    import json
                    try:
                        raw_json = orig_actions(record)
                        if not raw_json:
                            return raw_json
                        actions = json.loads(raw_json)
                        for act in actions:
                            if 'label' in act and isinstance(act['label'], str):
                                # Translate the label using the resolved translation dictionary `s`
                                act['label'] = str(s.get(act['label'], act['label']))
                        return json.dumps(actions)
                    except Exception:
                        return orig_actions(record)
                self.row_attrs['data-micro-actions'] = _translated_actions

        if request is not None and self.microsys_table_enabled and not getattr(self, '_microsys_request_configured', False):
            try:
                tables.RequestConfig(request).configure(self)
            except Exception:
                pass

    tables.Table.__init__ = _patched_init


def _patch_requestconfig_configure():
    try:
        import django_tables2 as tables
    except ImportError:
        return

    _original_configure = tables.RequestConfig.configure

    def _patched_configure(self, table):
        table_cls = type(table)
        request = getattr(self, 'request', None)
        if getattr(table, 'request', None) is None:
            table.request = request

        table.microsys_per_page_options = getattr(table, 'microsys_per_page_options', None) or _resolve_table_page_size_options(table_cls)
        table.microsys_per_page_field = getattr(table, 'microsys_per_page_field', None) or _resolve_table_per_page_field(table)

        original_paginate = getattr(self, 'paginate', None)
        if original_paginate is False:
            table._microsys_request_configured = True
            return _original_configure(self, table)

        if original_paginate in (None, True):
            paginate = {}
        elif isinstance(original_paginate, dict):
            paginate = dict(original_paginate)
        else:
            paginate = {}

        table.microsys_per_page = _resolve_table_page_size(
            request,
            table,
            table_cls,
            explicit_default=paginate.get('per_page'),
        )
        paginate['per_page'] = table.microsys_per_page

        self.paginate = paginate
        table._microsys_request_configured = True
        try:
            return _original_configure(self, table)
        finally:
            self.paginate = original_paginate

    tables.RequestConfig.configure = _patched_configure


# ──────────────────────────────────────────────────────────
# 4. Global gettext patch
# ──────────────────────────────────────────────────────────

def _patch_django_gettext():
    """Patch Django's gettext, gettext_lazy, and pgettext to check MS_TRANS first."""
    import django.utils.translation as translation
    from django.utils.functional import lazy
    
    _original_gettext = translation.gettext
    _original_pgettext = translation.pgettext
    
    def _patched_gettext(message):
        try:
            from microsys.translations import get_strings
            ms_trans = get_strings()
            
            if message in ms_trans:
                return ms_trans[message]
                
            slug_key = str(message).lower().replace(' ', '_')
            if slug_key in ms_trans:
                return ms_trans[slug_key]
        except Exception:
            pass
        return _original_gettext(message)
        
    def _patched_pgettext(context, message):
        try:
            from microsys.translations import get_strings
            ms_trans = get_strings()
            
            context_key = f"{context}_{message}".lower().replace(' ', '_')
            if context_key in ms_trans:
                return ms_trans[context_key]
                
            if message in ms_trans:
                return ms_trans[message]
                
            slug_key = str(message).lower().replace(' ', '_')
            if slug_key in ms_trans:
                return ms_trans[slug_key]
        except Exception:
            pass
        return _original_pgettext(context, message)

    translation.gettext = _patched_gettext
    if hasattr(translation, 'ugettext'):
        translation.ugettext = _patched_gettext
    
    translation.gettext_lazy = lazy(_patched_gettext, str)
    if hasattr(translation, 'ugettext_lazy'):
        translation.ugettext_lazy = lazy(_patched_gettext, str)
    
    translation.pgettext = _patched_pgettext
    translation.pgettext_lazy = lazy(_patched_pgettext, str)

# ──────────────────────────────────────────────────────────
# 5. Model Meta proxy patch
# ──────────────────────────────────────────────────────────

def _patch_model_meta():
    """Wrap model._meta.verbose_name and verbose_name_plural with lazy translators."""
    from django.apps import apps
    from microsys.translations import lazy_translator
    
    for model in apps.get_models():
        meta = model._meta
        
        # verbose_name
        raw_vn = str(meta.verbose_name) if meta.verbose_name else meta.model_name
        meta.verbose_name = lazy_translator(f"model_{meta.model_name}", raw_vn)
        
        # verbose_name_plural
        raw_vnp = str(meta.verbose_name_plural) if meta.verbose_name_plural else f"{raw_vn}s"
        meta.verbose_name_plural = lazy_translator(f"models_{meta.model_name}", raw_vnp)


# ──────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────

def apply_scoped_patches():
    """Apply all scope auto-injection patches. Called from AppConfig.ready()."""
    _patch_modelform_init()
    _patch_filterset_init()
    _patch_table_init()
    _patch_requestconfig_configure()
    logger.debug("microsys: Scope auto-injection patches applied.")

def apply_global_translation_patches():
    """Apply global monkey-patches for translations."""
    _patch_django_gettext()
    _patch_model_meta()
    logger.debug("microsys: Global translation patches applied.")
