"""
Auto-injection patches for ScopedModel.
Applied in AppConfig.ready() to monkey-patch Django base classes so that
ANY ModelForm / FilterSet / Table whose model inherits from ScopedModel
gets automatic scope handling — zero developer effort required.
"""
import copy
import logging

logger = logging.getLogger('microsys')

# Cache for issubclass checks to avoid repeated MRO lookups
_scoped_model_cache = {}


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
    """Check if scope should be locked for this user."""
    if not user or not hasattr(user, 'is_authenticated'):
        return False
    if not user.is_authenticated or user.is_superuser:
        return False
    return bool(
        hasattr(user, 'profile')
        and user.profile.scope_id
    )


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
            user = getattr(self, 'user_context', None)
        if not user:
            req = getattr(self, 'request', None)
            if req:
                user = getattr(req, 'user', None)

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
                self.fields['scope'].initial = user.profile.scope
            self.fields['scope'].disabled = True
            self.fields['scope'].widget = django_forms.HiddenInput()
            self.fields['scope'].required = False

        # ── Universal Translation Logic ──
        from microsys.translations import get_strings, lazy_translator
        from .utils import get_system_config
        config = get_system_config()
        s = get_strings(overrides=config.get('translations'))

        for name, field in self.fields.items():
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
        lock_scope = bool(
            request and hasattr(request, 'user')
            and _should_lock_scope(request.user)
        )

        if not scope_enabled or lock_scope:
            if 'scope' in self.filters:
                del self.filters['scope']

        # ── Universal Translation Logic ──
        from microsys.translations import get_strings, lazy_translator
        from .utils import get_system_config
        config = get_system_config()
        s = get_strings(overrides=config.get('translations'))

        for name, filt in self.filters.items():
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
    """Patch Table.__init__ to auto-manage scope column."""
    try:
        import django_tables2 as tables
    except ImportError:
        return

    _original_init = tables.Table.__init__

    def _patched_init(self, *args, **kwargs):
        # ── Pop microsys-specific kwargs before forwarding to django-tables2 ──
        # Views/tables may pass these custom kwargs which Table.__init__ doesn't accept.
        _ms_translations = kwargs.pop('translations', None)
        kwargs.pop('request', None)
        kwargs.pop('model_name', None)

        # Determine model BEFORE calling original (need to modify kwargs)
        table_meta = getattr(type(self), '_meta', None) or getattr(type(self), 'Meta', None)
        model = getattr(table_meta, 'model', None)

        if _is_scoped_model(model):
            from microsys.utils import is_scope_enabled
            scope_enabled = is_scope_enabled()

            if not scope_enabled:
                # Add 'scope' to exclude
                exclude = kwargs.get('exclude', getattr(table_meta, 'exclude', ()) or ())
                if isinstance(exclude, list):
                    exclude = tuple(exclude)
                if 'scope' not in exclude:
                    kwargs['exclude'] = exclude + ('scope',)
            else:
                # Auto-add scope column if not already defined on the class
                has_scope_col = hasattr(type(self), 'scope') or (
                    hasattr(table_meta, 'fields') and table_meta.fields
                    and 'scope' in (table_meta.fields if table_meta.fields else ())
                )
                if not has_scope_col:
                    extra = list(kwargs.get('extra_columns', []))
                    # Don't add if already in extra_columns
                    if not any(name == 'scope' for name, _ in extra):
                        extra.append(('scope', tables.Column(verbose_name='النطاق')))
                        kwargs['extra_columns'] = extra

        _original_init(self, *args, **kwargs)

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

    tables.Table.__init__ = _patched_init


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
    logger.debug("microsys: Scope auto-injection patches applied.")

def apply_global_translation_patches():
    """Apply global monkey-patches for translations."""
    _patch_django_gettext()
    _patch_model_meta()
    logger.debug("microsys: Global translation patches applied.")
