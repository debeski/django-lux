"""Discover ribbon-hosting views and model fields available to the builder."""

import logging

from django.urls import NoReverseMatch, get_resolver, reverse

from dlux.system.constants import (
    ROUTE_ACTION_FORM,
    ROUTE_ACTION_MACHINERY,
    ROUTE_ACTION_PAGE,
)

from .mixin import RibbonMixin
from .tabs import SOURCE_FIELD, SOURCE_FLAG, RibbonTabs, build_ribbon_tabs


# Every discovery step below degrades instead of raising: the builder showing a
# short list is better than the settings page refusing to open. That made the
# whole path silent, though — an empty builder in production looked identical to
# a project with no ribbon hosts, with nothing in the logs and nothing in the
# browser console to tell them apart. Each fallback now says what it swallowed.
logger = logging.getLogger('dlux')


CATALOG_SKIP_FIELDS = (
    'created_by', 'updated_by', 'deleted_by', 'user_permissions',
)
DESTINATION_EXCLUDED_PAGE_TOKENS = {
    'api',
    'apply',
    'approve',
    'cancel',
    'clear',
    'connect',
    'decline',
    'delete',
    'dismiss',
    'download',
    'execute',
    'finalize',
    'health',
    'mark',
    'populate',
    'receive',
    'reject',
    'request',
    'reset',
    'resume',
    'revert',
    'save',
    'send',
    'status',
    'toggle',
    'upload',
}


def _source_kind(field):
    """Which source type, if any, this field can populate."""
    if getattr(field, 'choices', None):
        return SOURCE_FIELD
    internal = field.get_internal_type() if hasattr(field, 'get_internal_type') else ''
    if internal == 'BooleanField':
        return SOURCE_FLAG
    if getattr(field, 'is_relation', False) and getattr(field, 'related_model', None):
        return SOURCE_FIELD
    return None


def _iter_named_patterns(patterns, namespaces=None):
    """Yield ``(pattern, full_route_name)`` for every named URL pattern."""
    namespaces = namespaces or []
    for entry in patterns:
        nested = getattr(entry, 'url_patterns', None)
        if nested is not None:
            next_namespaces = list(namespaces)
            if getattr(entry, 'namespace', None):
                next_namespaces.append(entry.namespace)
            yield from _iter_named_patterns(nested, next_namespaces)
            continue
        name = getattr(entry, 'name', None)
        if not name:
            continue
        route_name = ':'.join(namespaces + [name]) if namespaces else name
        yield entry, route_name


def _route_metadata(request=None):
    try:
        from dlux.discovery import discover_routes
        from dlux.translations import get_current_language_code

        lang_code = get_current_language_code(request)
        return {
            entry.get('url_name'): entry
            for entry in discover_routes(lang_code=lang_code)
            if entry.get('url_name')
        }
    except Exception:
        logger.warning(
            "Ribbon catalog could not read route metadata; hosts will fall back to "
            "view-derived labels.",
            exc_info=True,
        )
        return {}


def _route_url(route_name):
    try:
        return reverse(route_name)
    except NoReverseMatch:
        return ''


def _route_callbacks(urlconf=None):
    try:
        patterns = get_resolver(urlconf).url_patterns
        return {
            route_name: getattr(pattern, 'callback', None)
            for pattern, route_name in _iter_named_patterns(patterns)
        }
    except Exception:
        logger.warning(
            "Ribbon catalog could not walk the URLconf for route callbacks.",
            exc_info=True,
        )
        return {}


def _is_system_host(route_meta, view, callback):
    if route_meta.get('is_system'):
        return True
    module = getattr(view, '__module__', '') or getattr(callback, '__module__', '')
    return module == 'dlux' or module.startswith('dlux.')


def _host_label(route_meta, view, model=None):
    label = str(route_meta.get('label') or '').strip()
    if label:
        return label
    if view is not None:
        for attr in ('ribbon_title', 'page_title'):
            value = str(getattr(view, attr, '') or '').strip()
            if value:
                return value
    if model is not None:
        return str(model._meta.verbose_name_plural).title()
    return ''


def _view_locked(view):
    return bool(getattr(view, 'ribbon_tabs_fixed', None)) or (
        view.get_ribbon_tabs is not RibbonMixin.get_ribbon_tabs
    )


def _view_declared_strips(view):
    return getattr(view, 'ribbon_tabs_fixed', None) or getattr(view, 'ribbon_tabs', None)


def _route_storage_key(route_name):
    cleaned = str(route_name or '').replace(':', '.')
    return f'route.{cleaned}' if cleaned else ''


def _view_built_strips(view, request):
    if view is None or request is None:
        return None
    try:
        instance = view()
        instance.request = request
        if view.get_ribbon_strips is not RibbonMixin.get_ribbon_strips:
            return instance.get_ribbon_strips()
        if view.get_ribbon_tabs is not RibbonMixin.get_ribbon_tabs:
            tabs = instance.get_ribbon_tabs()
            return [tabs] if tabs else []
    except Exception:
        logger.debug(
            "Ribbon catalog could not build strips for %r.", view, exc_info=True
        )
        return None
    return None


def _action_summary(spec, index):
    if not isinstance(spec, dict):
        # A built `RibbonAction`, which is what `get_ribbon_actions()` returns.
        if not hasattr(spec, 'label'):
            return None
        spec = {
            'label': getattr(spec, 'label', '') or '',
            'labels': {},
            'icon': getattr(spec, 'icon', '') or '',
            'url': getattr(spec, 'url', '') or '',
            'attrs': dict(getattr(spec, 'attrs', None) or {}),
            'html': getattr(spec, 'html', '') or '',
        }
    labels = spec.get('labels') if isinstance(spec.get('labels'), dict) else {}
    label = str(spec.get('label') or '').strip()
    if not label:
        label = next((str(text).strip() for text in labels.values() if str(text or '').strip()), '')
    if not label and spec.get('html'):
        label = 'Developer action'
    # An explicit `kind` is how a spec that stands in for rendered markup says so:
    # the builder offers Remove and Restore for it and no rename, because there is
    # no label or icon in it to change.
    kind = str(spec.get('kind') or '').strip() or (
        'html' if spec.get('html') else ('link' if spec.get('url') else 'button')
    )
    # The destination is the button's identity: what an administrator's edits are
    # keyed by and what the runtime dedupes on. Kept in step with
    # `ribbon.build.action_destination_key`, whichever attribute carries the
    # endpoint. A raw-html button has none, so it cannot be edited or deduped —
    # `key` is empty and the builder leaves it alone.
    from .build import action_destination_key

    attrs = spec.get('attrs') if isinstance(spec.get('attrs'), dict) else {}
    key = action_destination_key(type('_Spec', (), {
        'attrs': attrs,
        'url': str(spec.get('url') or '').strip(),
    }))
    return {
        'id': f'developer:{index}',
        'key': key,
        'origin': 'developer',
        'locked': True,
        'kind': kind,
        'label': label,
        'labels': labels,
        'icon': str(spec.get('icon') or '').strip(),
        'permission': str(spec.get('permission') or '').strip(),
    }


def _declared_actions(view):
    actions = []
    for index, spec in enumerate(getattr(view, 'ribbon_actions', None) or []):
        summary = _action_summary(spec, index)
        if summary is not None:
            actions.append(summary)
    return actions


def _view_built_actions(view, request):
    """The buttons a view builds rather than declares.

    Almost nothing sets the `ribbon_actions` attribute: a real view overrides
    `get_ribbon_actions()` and appends to `super()`, because which buttons it
    shows usually depends on the reader's permissions. Reading only the static
    attribute meant the builder listed no buttons at all for any page — nothing
    to rename, remove or restore. Built the same way declared strips are, by
    asking the view.
    """
    if view is None or request is None:
        return None
    if view.get_ribbon_actions is RibbonMixin.get_ribbon_actions:
        return None
    from django.db import transaction

    try:
        # Asking a view for its buttons runs the view's own code, which reads —
        # and, through a settings singleton it happens to touch, can write. A
        # catalog is a description of what exists; building one must not change
        # anything, so whatever the view does here is rolled back.
        with transaction.atomic():
            instance = view()
            instance.request = request
            actions = list(instance.get_ribbon_actions() or [])
            transaction.set_rollback(True)
        return actions
    except Exception:
        logger.debug(
            "Ribbon catalog could not build actions for %r.", view, exc_info=True
        )
        return None


def _declared_function_actions(callback, request):
    """Buttons a function-based ribbon host declares for the builder.

    A function host builds its ribbon inline and there is no instance to ask, so
    it names its buttons on the function: a list of specs, or a callable taking
    the request when they depend on it. Without this the builder listed a function
    page as a ribbon host with no buttons at all — Reports being the obvious one.
    """
    specs = getattr(callback, 'dlux_ribbon_actions', None)
    if callable(specs):
        try:
            specs = specs(request)
        except Exception:
            logger.debug(
                "Ribbon catalog could not resolve declared actions for %r.",
                callback,
                exc_info=True,
            )
            return []
    if not specs:
        return []
    summaries = []
    for index, spec in enumerate(specs):
        summary = _action_summary(spec, index)
        if summary is not None:
            summaries.append(summary)
    return summaries


def _host_actions(view, request, callback=None):
    if view is None:
        return _declared_function_actions(callback, request)
    declared = _declared_actions(view)
    if declared:
        return declared
    built = _view_built_actions(view, request)
    if not built:
        return []
    summaries = []
    for index, action in enumerate(built):
        summary = _action_summary(action, index)
        if summary is not None:
            summaries.append(summary)
    return summaries


def _ribbon_view_hosts(urlconf=None, request=None):
    """Return concrete URL views that render a Ribbon through ``RibbonMixin``."""
    route_meta = _route_metadata(request)
    hosts = []

    try:
        patterns = get_resolver(urlconf).url_patterns
    except Exception:
        logger.warning(
            "Ribbon catalog could not resolve the root URLconf; the builder will list "
            "no ribbon hosts.",
            exc_info=True,
        )
        return []

    try:
        # Descending into every include imports each URLconf module, which nothing
        # else in a request does — so a module that only fails to import under this
        # deployment's settings surfaces here and nowhere else.
        candidates = list(_iter_named_patterns(patterns))
    except Exception:
        logger.warning(
            "Ribbon catalog could not enumerate named URL patterns; the builder will "
            "list no ribbon hosts.",
            exc_info=True,
        )
        return []

    for pattern, route_name in candidates:
        callback = getattr(pattern, 'callback', None)
        view = getattr(callback, 'view_class', None)
        explicit = getattr(callback, 'dlux_ribbon_host', None)
        if view is not None and not issubclass(view, RibbonMixin):
            view = None
        if view is None and not explicit:
            continue
        model = getattr(view, 'model', None) or getattr(
            getattr(view, 'queryset', None), 'model', None
        ) if view is not None else None
        if model is None and not explicit:
            continue
        meta = route_meta.get(route_name) or {}
        declared = _view_declared_strips(view) if view is not None else None
        if not declared and view is not None:
            declared = _view_built_strips(view, request)
        model_key = f'{model._meta.app_label}.{model.__name__}' if model is not None else _route_storage_key(route_name)
        hosts.append({
            'key': route_name,
            'route_name': route_name,
            'url': meta.get('url') or _route_url(route_name),
            'label': _host_label(meta, view, model),
            'group_key': meta.get('group_key') or '',
            'group_label': meta.get('group_label') or '',
            'route_app': route_name.split(':', 1)[0] if ':' in route_name else '',
            'is_system': _is_system_host(meta, view, callback),
            'model': model,
            'model_key': model_key,
            'locked': True if model is None else _view_locked(view),
            'declared': declared,
            'actions': _host_actions(view, request, callback),
            'actions_dynamic': True if model is None else view.get_ribbon_actions is not RibbonMixin.get_ribbon_actions,
        })
    return hosts


def ribbon_view_models(urlconf=None):
    """Return models behind views that render a Ribbon.

    Each value is ``(model, locked, declared)``. Locked views allow cosmetic
    edits to declared tabs but do not accept administrator-created strips.
    """
    found = {}
    for host in _ribbon_view_hosts(urlconf=urlconf):
        if host['model'] is None:
            continue
        key = host['model_key']
        previous = found.get(key)
        found[key] = (
            host['model'],
            (previous[1] if previous else True) and host['locked'],
            host['declared'] or (previous[2] if previous else None),
        )
    return found


def _split_field(config):
    """Return the first field a declared strip splits on."""
    sources = config.get('sources') if isinstance(config, dict) else None
    for source in (sources or []):
        if isinstance(source, dict) and source.get('field'):
            return str(source['field'])
    return ''


def _declared_strips(config, model, request):
    """Resolve every declared strip without applying stored presentation edits."""
    if not config:
        return []
    configs = config if isinstance(config, (list, tuple)) else [config]
    strips = []
    for index, one in enumerate(configs):
        if not one:
            continue
        if isinstance(one, RibbonTabs):
            tabs = one
        else:
            try:
                tabs = build_ribbon_tabs(one, model=model, request=request, overlay={})
            except Exception:
                logger.debug(
                    "Ribbon catalog could not build declared strip %s for %r.",
                    index,
                    model,
                    exc_info=True,
                )
                continue
        strips.append({
            'index': index,
            'param': tabs.param,
            'relation': tabs.relation or 'primary',
            'label': str(tabs.label or ''),
            'field': _split_field(one) if isinstance(one, dict) else '',
            'tabs': [
                {'key': tab.key, 'label': str(tab.label), 'icon': tab.icon or ''}
                for tab in tabs.items
            ],
        })
    return strips


def ribbon_tab_catalog(urlconf=None, request=None):
    """Return ribbon hosts, declared strips, and fields that can draw tabs."""
    catalog = []
    for host in _ribbon_view_hosts(urlconf=urlconf, request=request):
        model = host['model']
        meta = model._meta if model is not None else None
        fields = []
        if meta is not None:
            for field in meta.get_fields():
                if not getattr(field, 'name', None) or field.auto_created and not field.concrete:
                    continue
                if field.name in CATALOG_SKIP_FIELDS:
                    continue
                kind = _source_kind(field)
                if kind is None:
                    continue
                fields.append({
                    'name': field.name,
                    'label': str(getattr(field, 'verbose_name', field.name)).title(),
                    'kind': kind,
                    'choices': [
                        {'value': str(value), 'label': str(label)}
                        for value, label in (getattr(field, 'choices', None) or [])
                    ],
                })
        strips = _declared_strips(host['declared'], model, request)
        catalog.append({
            'key': host['key'],
            'route_name': host['route_name'],
            'url': host['url'],
            'model_key': host['model_key'],
            'app': meta.app_label if meta is not None else host['route_app'],
            'route_app': host['route_app'],
            'group_key': host['group_key'],
            'group_label': host['group_label'],
            'is_system': host['is_system'],
            'locked': host['locked'],
            'actions_locked': True,
            'actions_dynamic': host['actions_dynamic'],
            'actions': host['actions'],
            'strips': strips,
            'label': host['label'],
            'model_label': str(meta.verbose_name_plural).title() if meta is not None else '',
            'fields': sorted(fields, key=lambda entry: entry['label']),
        })
    return sorted(catalog, key=lambda entry: (
        entry['is_system'], entry['group_label'], entry['app'], entry['label'],
    ))


def _destination_kind(entry):
    action = entry.get('action')
    route_name = str(entry.get('url_name') or '').lower()
    path = str(entry.get('path_template') or entry.get('url') or '').lower()
    callback = entry.get('callback')
    view = getattr(callback, 'view_class', None)
    view_name = getattr(view, '__name__', '')
    looks_modal = (
        # A function view that answers `{"html": ...}` is a modal endpoint however
        # it is named or routed, and only it can say so. Without this, the Group,
        # Scope and Asset managers were offered as pages and a button pointing at
        # one navigated to raw JSON.
        bool(getattr(callback, 'dlux_modal', False))
        or 'modal' in route_name
        or '/modal' in path
        or view_name == 'DynamicModalManagerView'
        or view_name.endswith('ModalView')
    )
    if looks_modal:
        return 'modal'
    if action == ROUTE_ACTION_FORM:
        return 'form'
    if action == ROUTE_ACTION_PAGE:
        return 'page'
    if action == ROUTE_ACTION_MACHINERY and looks_modal:
        return 'modal'
    return ''


def _route_tokens(route_name):
    import re

    leaf = str(route_name or '').rsplit(':', 1)[-1]
    return {token for token in re.split(r'[^a-z0-9]+', leaf.lower()) if token}


def _is_safe_destination(entry, kind):
    if entry.get('requires_args'):
        return False
    if kind == 'page' and (_route_tokens(entry.get('url_name')) & DESTINATION_EXCLUDED_PAGE_TOKENS):
        return False
    return True


def _destination_permitted(entry, request):
    if request is None:
        return None
    user = getattr(request, 'user', None)
    try:
        from dlux.discovery.render import _user_has_sidebar_permission

        return _user_has_sidebar_permission(
            user,
            entry.get('permissions'),
            entry.get('permissions_explicit', False),
        )
    except Exception:
        return None


def _destination_action_spec(entry, kind):
    permissions = list(entry.get('permissions') or [])
    destination = {
        'kind': kind,
        'route_name': entry.get('url_name') or '',
        'url': entry.get('url') or '',
        'label': entry.get('label') or '',
        'permissions': permissions,
    }
    spec = {
        'destination': destination,
        'labels': {},
        'icon': entry.get('icon') or '',
        'permissions': permissions,
    }
    if kind == 'modal':
        spec['attrs'] = {
            'data-dynamic-modal': entry.get('url') or '',
            'data-modal-title': entry.get('label') or '',
        }
    else:
        spec['url'] = entry.get('url') or ''
    return spec


def ribbon_destination_catalog(request=None, include_system_items=True):
    """Return context-free destinations an admin can bind to a ribbon button."""
    try:
        from dlux.discovery import discover_routes
        from dlux.discovery.routes import route_allowed_for
        from dlux.discovery.meta import HIDDEN_SIDEBAR_GROUP_KEYS
        from dlux.system.constants import DISCOVERY_PROFILE_RIBBON_DESTINATION
        from dlux.translations import get_current_language_code

        routes = discover_routes(lang_code=get_current_language_code(request))
    except Exception:
        logger.warning(
            "Ribbon destination catalog could not discover routes; the builder will "
            "offer no destinations.",
            exc_info=True,
        )
        return []

    callbacks = _route_callbacks()
    destinations = []
    for entry in routes:
        url_name = entry.get('url_name')
        url = entry.get('url')
        if not url_name or not url:
            continue
        entry = dict(entry)
        entry['callback'] = callbacks.get(url_name)
        kind = _destination_kind(entry)
        if not kind:
            continue
        if not _is_safe_destination(entry, kind):
            continue
        # The profile carries the per-view exclusions a raw walk of the URLconf
        # ignores. Without it the list offered sign-up, session-keepalive,
        # import-preview, export and global-search endpoints as if they were pages.
        if not route_allowed_for(entry, DISCOVERY_PROFILE_RIBBON_DESTINATION):
            continue
        # The hidden `dlux` group is machinery. Two things come out of it: the
        # configurable system pages — the same set the sidebar offers — and any
        # dynamic-modal manager, whoever registered it. Everything else is plumbing.
        dlux_owned = entry.get('group_key') in HIDDEN_SIDEBAR_GROUP_KEYS
        if dlux_owned:
            configurable = include_system_items and entry.get('is_system')
            if not (kind == 'modal' or configurable):
                continue
        permitted = _destination_permitted(entry, request)
        destinations.append({
            'id': url_name,
            'kind': kind,
            'route_name': url_name,
            'url': url,
            'label': entry.get('label') or url_name,
            'icon': entry.get('icon') or '',
            'group_key': entry.get('group_key') or '',
            'group_label': entry.get('group_label') or '',
            # Everything dlux owns reads as System in the picker, so a reader can
            # tell it from their project's own pages. A project's own modal manager
            # is namespaced and is not dlux's.
            'is_system': bool(entry.get('is_system')) or (dlux_owned and ':' not in str(url_name)),
            'permissions': list(entry.get('permissions') or []),
            'permissions_explicit': bool(entry.get('permissions_explicit')),
            'permitted': permitted,
            'action_spec': _destination_action_spec(entry, kind),
        })
    return sorted(destinations, key=lambda item: (
        item['is_system'], item['group_label'], item['kind'], item['label'],
    ))
