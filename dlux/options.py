"""Options-page card registry — the *only* supported way for a downstream app to
add a card to ``/sys/options/``.

Security model (firm, Dlux-first):

* **Code-only registration.** Cards are registered from trusted Python at
  startup (an app's ``dlux_options`` module or ``AppConfig.ready``). There is no
  HTTP, database, or settings path to register a card, so a card can never be
  *injected* by a request, a stored value, or a compromised non-superuser.
* **Server-side visibility.** ``superuser_only`` / ``permission`` are enforced in
  :func:`get_visible_cards` *before* a card's builder runs or its template
  renders — not merely hidden in the template.
* **Sandboxed rendering.** Each card renders in isolation inside a ``try/except``
  (:func:`render_cards`); a card that raises is logged and skipped so one bad
  app card can never blank the Options page.
* **Auto-escaping preserved.** A card's template is rendered by Django (its data
  auto-escaped) and Dlux only marks the *already-rendered* trusted-template HTML
  safe. Dlux never marks app-supplied *data* safe. App card templates must not
  ``|safe`` untrusted values themselves.
"""

import inspect
import logging
import re

from django import forms
from django.utils.functional import Promise

from .system.constants import (
    DEFAULT_MAX_SYSTEM_APP_CONFIG_BYTES,
    PREFERENCES_APP_NAMESPACE_MAXLEN,
    SAFE_NAMESPACE_RE,
    SYSTEM_APP_CONFIG_NAMESPACE,
)

logger = logging.getLogger('dlux')

_SAFE_ID = re.compile(SAFE_NAMESPACE_RE)
# One or more Bootstrap-Icons classes, e.g. "bi-grid" or "bi-grid text-primary".
_SAFE_ICON = re.compile(r'^[A-Za-z0-9 _-]+$')
_MAX_ID_LEN = 128

# id -> card dict. Insertion order is irrelevant; render order is (order, id).
_REGISTRY = {}
_SETTINGS_REGISTRY = {}
_SAFE_FIELD_NAME = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
_FIELD_TYPES = {
    'boolean', 'bool', 'toggle',
    'choice', 'select',
    'multiple_choice', 'multichoice', 'multi_choice',
    'char', 'string',
    'text', 'textarea',
    'integer', 'int',
    'number', 'float',
    'json',
}


class AppSystemConfigError(ValueError):
    """Raised when an app-owned system-config write is invalid."""

    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def register_card(*, id, title, template_name, icon='bi-puzzle', order=100,
                  superuser_only=False, permission=None, context_builder=None,
                  visible=None, search_keywords=()):
    """Register one Options-page card. Raises ``ValueError`` on invalid input.

    Args:
        id: Stable unique slug ([A-Za-z0-9._-], <=128). Also the card's
            ``data-options-card`` value, so keep it namespaced (``myapp.thing``).
        title: The card heading — a plain string, or a ``callable(request)->str``
            for per-request localization.
        template_name: A template (resolved by the normal loader) rendered as the
            card *body*. Dlux supplies the surrounding card chrome.
        icon: Bootstrap-Icons class(es) for the heading.
        order: Sort weight (lower first); ties break by ``id``.
        superuser_only: Only render for superusers (enforced server-side).
        permission: Optional ``"app_label.codename"``; only users with it see it.
        context_builder: Optional ``callable(request)->dict`` producing the
            template context. Runs sandboxed with the current request/user.
        visible: Optional ``callable(request)->bool`` for config-driven
            visibility (e.g. show the card only when a feature is enabled in
            ``extra_config``). Evaluated server-side *after* the static gates and
            **fail-closed** — if it raises, the card is hidden.
        search_keywords: Optional strings that also match this card in global
            search, on top of its rendered title. Not translated — list the
            synonyms for every language you ship (``('scanner', 'ماسح')``).
    """
    if not isinstance(id, str) or not id or len(id) > _MAX_ID_LEN or not _SAFE_ID.match(id):
        raise ValueError(f"register_card: invalid id {id!r} (must match {SAFE_NAMESPACE_RE}, <= {_MAX_ID_LEN} chars)")
    if not (isinstance(title, str) and title) and not callable(title):
        raise ValueError(f"register_card[{id}]: title must be a non-empty string or a callable")
    if not isinstance(template_name, str) or not template_name:
        raise ValueError(f"register_card[{id}]: template_name must be a non-empty string")
    if not isinstance(icon, str) or not _SAFE_ICON.match(icon):
        raise ValueError(f"register_card[{id}]: invalid icon {icon!r}")
    if not isinstance(order, int) or isinstance(order, bool):
        raise ValueError(f"register_card[{id}]: order must be an int")
    if permission is not None and not (isinstance(permission, str) and permission):
        raise ValueError(f"register_card[{id}]: permission must be a non-empty string or None")
    if context_builder is not None and not callable(context_builder):
        raise ValueError(f"register_card[{id}]: context_builder must be callable or None")
    if visible is not None and not callable(visible):
        raise ValueError(f"register_card[{id}]: visible must be callable or None")
    if isinstance(search_keywords, str) or not all(
            isinstance(word, str) and word.strip() for word in tuple(search_keywords or ())):
        raise ValueError(f"register_card[{id}]: search_keywords must be an iterable of non-empty strings")

    if id in _REGISTRY:
        # Overwrite (dev autoreload re-imports the module) but make it visible.
        logger.debug("register_card: overwriting already-registered Options card '%s'", id)

    _REGISTRY[id] = {
        'id': id,
        'title': title,
        'template_name': template_name,
        'icon': icon,
        'order': int(order),
        'superuser_only': bool(superuser_only),
        'permission': permission,
        'context_builder': context_builder,
        'visible': visible,
        'search_keywords': tuple(word.strip() for word in tuple(search_keywords or ())),
    }


def unregister_card(id):
    """Remove a card (mainly for tests)."""
    _REGISTRY.pop(id, None)


def clear_registry():
    """Drop all registered cards (test helper)."""
    _REGISTRY.clear()
    _SETTINGS_REGISTRY.clear()


def get_visible_cards(request):
    """Cards the requesting user may see, sorted by (order, id).

    Permission/superuser gating is enforced here, server-side, so an ineligible
    card's ``context_builder`` never runs and its template never renders.
    """
    user = getattr(request, 'user', None)
    if user is None or not getattr(user, 'is_authenticated', False):
        return []
    visible = []
    for card in _REGISTRY.values():
        if card['superuser_only'] and not user.is_superuser:
            continue
        if card['permission'] and not user.has_perm(card['permission']):
            continue
        predicate = card['visible']
        if predicate is not None:
            try:
                if not predicate(request):
                    continue
            except Exception:
                # Fail closed: a broken visibility check hides the card rather
                # than exposing it.
                logger.exception("Options card '%s' visible() raised; hiding it (fail-closed).", card['id'])
                continue
        visible.append(card)
    return sorted(visible, key=lambda c: (c['order'], c['id']))


def _validate_namespace(namespace, *, label='namespace'):
    namespace = str(namespace or '').strip()
    if not namespace or len(namespace) > PREFERENCES_APP_NAMESPACE_MAXLEN or not _SAFE_ID.match(namespace):
        raise ValueError(
            f"{label}: invalid namespace {namespace!r} "
            f"(must match {SAFE_NAMESPACE_RE}, <= {PREFERENCES_APP_NAMESPACE_MAXLEN} chars)"
        )
    return namespace


def _validate_field_name(name, namespace):
    name = str(name or '').strip()
    if not name or len(name) > 80 or not _SAFE_FIELD_NAME.match(name):
        raise ValueError(f"register_app_settings[{namespace}]: invalid field name {name!r}")
    return name


def _normalize_field_specs(fields, namespace):
    if isinstance(fields, dict):
        raw_specs = [dict(spec or {}, name=name) for name, spec in fields.items()]
    elif isinstance(fields, (list, tuple)):
        raw_specs = [dict(spec or {}) for spec in fields]
    else:
        raise ValueError(f"register_app_settings[{namespace}]: fields must be a list/tuple or dict")

    normalized = []
    seen = set()
    for raw in raw_specs:
        name = _validate_field_name(raw.get('name'), namespace)
        if name in seen:
            raise ValueError(f"register_app_settings[{namespace}]: duplicate field {name!r}")
        seen.add(name)

        kind = str(raw.get('type') or raw.get('kind') or 'char').strip().lower()
        if kind not in _FIELD_TYPES:
            raise ValueError(f"register_app_settings[{namespace}.{name}]: unsupported field type {kind!r}")
        if kind in {'bool', 'toggle'}:
            kind = 'boolean'
        elif kind == 'select':
            kind = 'choice'
        elif kind in {'multichoice', 'multi_choice'}:
            kind = 'multiple_choice'
        elif kind == 'string':
            kind = 'char'
        elif kind == 'textarea':
            kind = 'text'
        elif kind == 'int':
            kind = 'integer'
        elif kind == 'float':
            kind = 'number'

        if kind in {'choice', 'multiple_choice'}:
            choices = raw.get('choices')
            if not isinstance(choices, (list, tuple)) or not choices:
                raise ValueError(f"register_app_settings[{namespace}.{name}]: choices are required")
            raw['choices'] = tuple(choices)

        raw['name'] = name
        raw['type'] = kind
        normalized.append(raw)
    if not normalized:
        raise ValueError(f"register_app_settings[{namespace}]: at least one field is required")
    return tuple(normalized)


def register_app_settings(*, namespace, title, fields=None, form_class=None,
                          description='', icon='bi-sliders2', order=100,
                          defaults=None, visible=None):
    """Register one project-specific settings surface backed by extra_config.

    The registered settings appear as a tile in the Options admin settings grid
    for superusers only. The form saves only
    ``SystemSettings.extra_config['app'][namespace]`` and never touches Dlux's
    core ``SystemSettingsForm``.

    ``fields`` is the simple path: a list/dict of field specs using Dlux's built
    in controls (boolean toggles, choice selectors, text/number/json inputs).
    ``form_class`` is the escape hatch: pass a custom ``forms.Form`` subclass and
    optionally implement ``to_app_config(current_value)`` to control the saved
    JSON value. Supply either ``fields`` or ``form_class``.
    """
    namespace = _validate_namespace(namespace, label='register_app_settings')
    # A lazy translation proxy is the natural way to give a title that has to
    # follow the reader's language, and it is neither a `str` nor callable.
    # Rejecting it is what pushed callers into wrapping one in a lambda, where
    # the argument count then became a trap.
    if not isinstance(title, Promise) and not (isinstance(title, str) and title) and not callable(title):
        raise ValueError(
            f"register_app_settings[{namespace}]: title must be a non-empty string, "
            "a lazy string, or a callable"
        )
    if (description is not None and not isinstance(description, (str, Promise))
            and not callable(description)):
        raise ValueError(
            f"register_app_settings[{namespace}]: description must be a string, "
            "a lazy string, a callable, or None"
        )
    # Arity is checked here rather than left to the first render. A callable of
    # the wrong shape used to raise while the Options page was being built, and
    # the tile was dropped — a settings surface silently missing, with the cause
    # only in the log.
    title = _text_callable(title, namespace, 'title')
    description = _text_callable(description, namespace, 'description')
    if not isinstance(icon, str) or not _SAFE_ICON.match(icon):
        raise ValueError(f"register_app_settings[{namespace}]: invalid icon {icon!r}")
    if not isinstance(order, int) or isinstance(order, bool):
        raise ValueError(f"register_app_settings[{namespace}]: order must be an int")
    if visible is not None and not callable(visible):
        raise ValueError(f"register_app_settings[{namespace}]: visible must be callable or None")
    if form_class is not None and fields is not None:
        raise ValueError(f"register_app_settings[{namespace}]: use either fields or form_class, not both")
    if form_class is not None and not callable(form_class):
        raise ValueError(f"register_app_settings[{namespace}]: form_class must be callable")

    field_specs = None
    if form_class is None:
        field_specs = _normalize_field_specs(fields, namespace)

    if defaults is None:
        defaults = {}
    if defaults is not None and not isinstance(defaults, dict):
        raise ValueError(f"register_app_settings[{namespace}]: defaults must be a dict or None")

    if namespace in _SETTINGS_REGISTRY:
        logger.debug("register_app_settings: overwriting already-registered app settings '%s'", namespace)

    _SETTINGS_REGISTRY[namespace] = {
        'namespace': namespace,
        'title': title,
        'description': description or '',
        'icon': icon,
        'order': int(order),
        'defaults': dict(defaults or {}),
        'fields': field_specs,
        'form_class': form_class,
        'visible': visible,
    }


def unregister_app_settings(namespace):
    """Remove an app settings registration (mainly for tests)."""
    _SETTINGS_REGISTRY.pop(namespace, None)


def _text_callable(value, namespace, label):
    """Accept `f(request)` or `f()`, and hand back a one-argument callable.

    Both read naturally at the call site — `lambda request: ...` when the text
    depends on who is asking, `lambda: ...` when it only needs to be evaluated
    late — so both are allowed rather than one being a trap. A lazy translation
    proxy is not callable at all and passes straight through.
    """
    if not callable(value):
        return value
    try:
        signature = inspect.signature(value)
    except (TypeError, ValueError):
        # Builtins and C callables expose no signature; take them as given.
        return value
    try:
        signature.bind(None)
        return value
    except TypeError:
        pass
    try:
        signature.bind()
    except TypeError:
        raise ValueError(
            f"register_app_settings[{namespace}]: {label} callable must accept "
            "the request or no arguments"
        ) from None
    return lambda request, _inner=value: _inner()


def _resolve_registered_text(value, request):
    if callable(value):
        return value(request)
    return value


def get_visible_app_settings(request):
    """Return app settings tiles visible to this request (superuser-only)."""
    user = getattr(request, 'user', None)
    if user is None or not getattr(user, 'is_authenticated', False) or not getattr(user, 'is_superuser', False):
        return []
    visible = []
    for definition in _SETTINGS_REGISTRY.values():
        predicate = definition['visible']
        if predicate is not None:
            try:
                if not predicate(request):
                    continue
            except Exception:
                logger.exception(
                    "App settings '%s' visible() raised; hiding it (fail-closed).",
                    definition['namespace'],
                )
                continue
        item = dict(definition)
        # Unlike visible(), which fails closed because it is a permission
        # decision, text that raises is only cosmetic. Dropping the tile for it
        # hid a whole settings surface and read as "the page lost my settings".
        for key, fallback in (('title', definition['namespace']), ('description', '')):
            try:
                item[key] = _resolve_registered_text(definition[key], request)
            except Exception:
                logger.exception(
                    "App settings '%s' %s raised; showing the tile with a fallback.",
                    definition['namespace'], key,
                )
                item[key] = fallback
        visible.append(item)
    return sorted(visible, key=lambda c: (c['order'], c['namespace']))


def get_visible_app_setting(request, namespace):
    namespace = str(namespace or '').strip()
    for definition in get_visible_app_settings(request):
        if definition['namespace'] == namespace:
            return definition
    return None


def _field_initial(definition, current_value, spec):
    name = spec['name']
    if isinstance(current_value, dict) and name in current_value:
        return current_value.get(name)
    if name in definition['defaults']:
        return definition['defaults'][name]
    return spec.get('default')


def _build_form_field(spec, initial):
    kind = spec['type']
    common = {
        'required': bool(spec.get('required', False)),
        'label': spec.get('label') or spec['name'].replace('_', ' ').title(),
        'help_text': spec.get('help_text') or '',
        'initial': initial,
    }
    if kind == 'boolean':
        return forms.BooleanField(required=False, **{k: v for k, v in common.items() if k != 'required'})
    if kind == 'choice':
        field = forms.ChoiceField(choices=spec['choices'], **common)
    elif kind == 'multiple_choice':
        field = forms.MultipleChoiceField(choices=spec['choices'], **common)
    elif kind == 'text':
        field = forms.CharField(widget=forms.Textarea(attrs={'rows': spec.get('rows', 3)}), **common)
    elif kind == 'integer':
        field = forms.IntegerField(
            min_value=spec.get('min_value'),
            max_value=spec.get('max_value'),
            **common,
        )
    elif kind == 'number':
        field = forms.FloatField(
            min_value=spec.get('min_value'),
            max_value=spec.get('max_value'),
            **common,
        )
    elif kind == 'json':
        field = forms.JSONField(**common)
    else:
        field = forms.CharField(max_length=spec.get('max_length'), **common)

    control = str(spec.get('control') or '').strip().lower()
    if kind in {'choice', 'multiple_choice'} and control in {'selector', 'card', 'cards', 'toggle'}:
        from .widgets import DluxChoiceSelectorWidget, DluxMultipleChoiceSelectorWidget

        variant = str(spec.get('variant') or ('card' if control in {'selector', 'card', 'cards'} else 'toggle'))
        widget_class = DluxMultipleChoiceSelectorWidget if kind == 'multiple_choice' else DluxChoiceSelectorWidget
        field.widget = widget_class(
            variant=variant,
            option_meta=spec.get('option_meta') or {},
            searchable=bool(spec.get('searchable', False)),
            search_placeholder=str(spec.get('search_placeholder') or ''),
        )
        field.widget.choices = field.choices
    else:
        css = 'form-select glass-input' if kind in {'choice', 'multiple_choice'} else 'form-control glass-input'
        field.widget.attrs.update({'class': css})
        if kind in {'char', 'text'}:
            field.widget.attrs.setdefault('dir', spec.get('dir') or 'auto')
    return field


class AppSettingsForm(forms.Form):
    """Generated form for register_app_settings(..., fields=[...])."""

    def __init__(self, *args, definition, current_value=None, request=None, **kwargs):
        self.definition = definition
        self.current_value = current_value if isinstance(current_value, dict) else {}
        self.request = request
        super().__init__(*args, **kwargs)

        for spec in definition['fields']:
            initial = _field_initial(definition, self.current_value, spec)
            self.fields[spec['name']] = _build_form_field(spec, initial)

        from crispy_forms.helper import FormHelper
        from crispy_forms.layout import Div, Field, Layout, Row
        from .forms import build_settings_toggle_field

        self.helper = FormHelper()
        self.helper.form_tag = False
        layout_items = []
        for spec in definition['fields']:
            css_class = spec.get('css_class') or ('col-12' if spec['type'] == 'boolean' else 'col-12 col-lg-6')
            if spec['type'] == 'boolean' and spec.get('control', 'toggle') != 'plain':
                layout_items.append(build_settings_toggle_field(self, spec['name'], css_class=css_class))
            else:
                layout_items.append(Div(Field(spec['name']), css_class=css_class))
        self.helper.layout = Layout(Row(*layout_items, css_class='g-3'))

    def to_app_config(self, current_value=None):
        value = dict(current_value if isinstance(current_value, dict) else self.current_value)
        for spec in self.definition['fields']:
            value[spec['name']] = self.cleaned_data.get(spec['name'])
        return value


def _custom_form_kwargs(form_class, *, data, initial, request, namespace, current_value, definition):
    import inspect

    base = {'data': data, 'initial': initial}
    optional = {
        'request': request,
        'namespace': namespace,
        'current_value': current_value,
        'settings_definition': definition,
    }
    try:
        signature = inspect.signature(form_class.__init__)
    except (TypeError, ValueError):
        return base
    params = signature.parameters
    accepts_kwargs = any(param.kind == inspect.Parameter.VAR_KEYWORD for param in params.values())
    for name, value in optional.items():
        if accepts_kwargs or name in params:
            base[name] = value
    return base


def build_app_settings_form(definition, request, data=None):
    from .utils import get_app_system_config

    current_value = get_app_system_config(definition['namespace'], definition['defaults'])
    initial = current_value if isinstance(current_value, dict) else {}
    form_class = definition.get('form_class')
    if form_class is None:
        return AppSettingsForm(
            data=data,
            definition=definition,
            current_value=current_value,
            request=request,
        )
    kwargs = _custom_form_kwargs(
        form_class,
        data=data,
        initial=initial,
        request=request,
        namespace=definition['namespace'],
        current_value=current_value,
        definition=definition,
    )
    form = form_class(**kwargs)
    helper = getattr(form, 'helper', None)
    if helper is not None and hasattr(helper, 'form_tag'):
        helper.form_tag = False
    return form


def get_app_settings_form_value(definition, form):
    from .utils import get_app_system_config

    current_value = get_app_system_config(definition['namespace'], definition['defaults'])
    if hasattr(form, 'to_app_config') and callable(form.to_app_config):
        return form.to_app_config(current_value)
    value = dict(current_value) if isinstance(current_value, dict) else {}
    value.update(getattr(form, 'cleaned_data', {}) or {})
    return value


def _max_system_app_config_bytes():
    from django.conf import settings

    try:
        return max(int(getattr(settings, 'DLUX_MAX_SYSTEM_APP_CONFIG_BYTES', DEFAULT_MAX_SYSTEM_APP_CONFIG_BYTES)), 1024)
    except (TypeError, ValueError):
        return DEFAULT_MAX_SYSTEM_APP_CONFIG_BYTES


def write_app_system_config(namespace, value, *, request=None):
    """Persist one app-owned system config namespace and refresh config cache."""
    import json

    from django.apps import apps

    try:
        namespace = _validate_namespace(namespace, label='write_app_system_config')
    except ValueError as exc:
        raise AppSystemConfigError(str(exc), status_code=400) from exc

    SystemSettings = apps.get_model('dlux', 'SystemSettings')
    sys_settings = SystemSettings.load()
    extra = sys_settings.extra_config
    extra = dict(extra) if isinstance(extra, dict) else {}

    app_bag = extra.get(SYSTEM_APP_CONFIG_NAMESPACE)
    app_bag = dict(app_bag) if isinstance(app_bag, dict) else {}
    if value is None:
        app_bag.pop(namespace, None)
    else:
        app_bag[namespace] = value

    if app_bag:
        extra[SYSTEM_APP_CONFIG_NAMESPACE] = app_bag
    else:
        extra.pop(SYSTEM_APP_CONFIG_NAMESPACE, None)

    try:
        too_big = len(json.dumps(extra, default=str).encode('utf-8')) > _max_system_app_config_bytes()
    except (TypeError, ValueError) as exc:
        raise AppSystemConfigError('Value is not JSON-serializable.', status_code=400) from exc
    if too_big:
        raise AppSystemConfigError('System config payload too large.', status_code=413)

    sys_settings.extra_config = extra
    sys_settings.save()

    if request is not None:
        try:
            from .utils import log_user_action

            log_user_action(
                request,
                'UPDATE',
                instance=sys_settings,
                model_name='systemsettings',
                details={'app_config_namespace': namespace, 'cleared': value is None},
                category='audit',
            )
        except Exception:
            logger.debug("Audit logging failed for app system-config write '%s'", namespace, exc_info=True)

    return app_bag.get(namespace)


def render_cards(request):
    """Render visible cards to a list of ``{id, title, icon, html}``.

    Every card is rendered inside its own ``try/except`` — a failing card is
    logged and dropped, never propagated, so the Options page always renders.
    """
    from django.template.loader import render_to_string
    from .translations import get_current_language_code, get_strings

    strings = get_strings(get_current_language_code(request))
    rendered = []
    for card in get_visible_cards(request):
        try:
            context = {'request': request, 'user': request.user, 'DLUX_STRINGS': strings}
            builder = card['context_builder']
            if builder is not None:
                extra = builder(request)
                if isinstance(extra, dict):
                    context.update(extra)
            title = card['title']
            if callable(title):
                title = title(request)
            html = render_to_string(card['template_name'], context, request=request)
        except Exception:
            logger.exception("Options card '%s' failed to render; skipping it.", card['id'])
            continue
        rendered.append({
            'id': card['id'],
            'title': title,
            'icon': card['icon'],
            'html': html,
        })
    return rendered
