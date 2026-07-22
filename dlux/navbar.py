from urllib.parse import urlsplit

from django.urls import NoReverseMatch, reverse

from .system.constants import DEFAULT_NAVBAR_MODE, NAVBAR_MODE_VALUES
from .discovery import SYSTEM_ROUTE_META, discover_sidebar_catalog
from .utils import normalize_navbar_config


ROOT_LIKE_ROUTE_NAMES = {'root', 'home', 'index'}
SYSTEM_GROUP_KEY = 'dlux'


def _route_leaf(url_name):
    return str(url_name or '').split(':')[-1]


def resolve_navbar_mode(user_preferences, navbar_config):
    config = normalize_navbar_config(navbar_config)
    mode = config.get('default_mode', DEFAULT_NAVBAR_MODE)
    if not config.get('enabled', False) or not config.get('allow_user_mode_override', True):
        return mode
    user_mode = user_preferences.get('navbar_mode') if isinstance(user_preferences, dict) else None
    return user_mode if user_mode in NAVBAR_MODE_VALUES else mode


def strip_navbar_mode_preference(user_preferences, navbar_config):
    prefs = dict(user_preferences) if isinstance(user_preferences, dict) else {}
    config = normalize_navbar_config(navbar_config)
    if (
        not config.get('enabled', False)
        or not config.get('allow_user_mode_override', True)
        or prefs.get('navbar_mode') not in NAVBAR_MODE_VALUES
    ):
        prefs.pop('navbar_mode', None)
    return prefs


def _translated_label(labels, lang_code):
    if not isinstance(labels, dict):
        return ''
    lang_code = str(lang_code or '').strip().lower()
    base_lang = lang_code.split('-')[0]
    return str(labels.get(lang_code) or labels.get(base_lang) or next(iter(labels.values()), '')).strip()


def _humanize(value):
    return str(value or '').split(':')[-1].replace('_', ' ').replace('-', ' ').strip().title()


def _route_candidates(request):
    match = getattr(request, 'resolver_match', None)
    if match is None:
        return []
    candidates = []
    for value in [getattr(match, 'view_name', ''), getattr(match, 'url_name', '')]:
        value = str(value or '').strip()
        leaf = _route_leaf(value)
        for candidate in [value, leaf]:
            if candidate and candidate not in candidates:
                candidates.append(candidate)
    return candidates


def _find_route_chain(nodes, route_names, prefix=None):
    prefix = list(prefix or [])
    for node in nodes if isinstance(nodes, list) else []:
        if not isinstance(node, dict):
            continue
        path = [*prefix, node]
        node_url_name = str(node.get('url_name') or '').strip()
        node_leaf = _route_leaf(node_url_name)
        if node.get('kind') == 'route' and (
            node_url_name in route_names
            or (node_leaf not in ROOT_LIKE_ROUTE_NAMES and node_leaf in route_names)
        ):
            return path
        child_path = _find_route_chain(node.get('children'), route_names, path)
        if child_path:
            return child_path
    return []


def _is_root_like(label='', url_name=''):
    return str(label or '').strip().lower() in ROOT_LIKE_ROUTE_NAMES


def _resolved_route_url(url_name, node, catalog_entry):
    configured_url = str(node.get('url') or '').strip()
    if configured_url:
        return configured_url
    catalog_url = str((catalog_entry or {}).get('url') or '').strip()
    if catalog_url:
        return catalog_url
    try:
        return reverse(url_name)
    except NoReverseMatch:
        return ''


def _node_to_crumb(node, lang_code, catalog_lookup):
    kind = node.get('kind')
    url_name = str(node.get('url_name') or node.get('id') or '').strip()
    catalog_entry = None
    if kind == 'route':
        catalog_entry = catalog_lookup.get(url_name) or catalog_lookup.get(_route_leaf(url_name))
    label = _translated_label(node.get('labels'), lang_code)
    if not label and catalog_entry:
        label = str(catalog_entry.get('label') or '').strip()
    if not label and kind == 'route':
        # Non-sidebar system pages (user profile, reports overview) are not in the
        # catalog, so resolve their translated title from SYSTEM_ROUTE_META's
        # label_key before falling back to an English humanization of the URL.
        meta = SYSTEM_ROUTE_META.get(_route_leaf(url_name)) or SYSTEM_ROUTE_META.get(url_name)
        label_key = str((meta or {}).get('label_key') or '').strip()
        if label_key:
            from .translations import get_strings
            from .utils import get_system_config
            strings = get_strings(lang_code, overrides=get_system_config().get('translations'))
            label = str(strings.get(label_key) or '').strip()
    if not label:
        label = _humanize(url_name if kind == 'route' else node.get('id'))
    configured_url = str(node.get('url') or '').strip()
    url = _resolved_route_url(url_name, node, catalog_entry) if kind == 'route' else str(node.get('url') or '').strip()
    suppress_click = _is_root_like(label, url_name) and not configured_url if kind == 'route' else False
    return {
        'label': label,
        'url': url,
        'clickable': bool(url) and not suppress_click,
        'url_name': url_name if kind == 'route' else '',
        'kind': kind,
        'group_key': (catalog_entry or {}).get('group_key', ''),
    }


def _route_catalog_entry(catalog_lookup, url_name):
    url_name = str(url_name or '').strip()
    return catalog_lookup.get(url_name) or catalog_lookup.get(_route_leaf(url_name))


def _route_crumb(url_name, lang_code, catalog_lookup):
    return _node_to_crumb({
        'kind': 'route',
        'id': url_name,
        'url_name': url_name,
        'children': [],
    }, lang_code, catalog_lookup)


def _runtime_to_crumb(raw_crumb, lang_code, dlux_strings):
    if not isinstance(raw_crumb, dict):
        return None
    label = str(raw_crumb.get('label') or '').strip()
    label_key = str(raw_crumb.get('label_key') or '').strip()
    if not label and label_key:
        label = str(dlux_strings.get(label_key) or '').strip()
    if not label:
        return None
    url_name = str(raw_crumb.get('url_name') or '').strip()
    url = str(raw_crumb.get('url') or '').strip()
    if not url and url_name:
        try:
            url = reverse(url_name)
        except NoReverseMatch:
            url = ''
    return {
        'label': label,
        'url': url,
        'clickable': bool(url) and not _is_root_like(label, url_name),
        'url_name': url_name,
        'kind': 'runtime',
    }


def _normalized_url_path(value):
    try:
        path = urlsplit(str(value or '').strip()).path
    except (TypeError, ValueError):
        return ''
    if not path:
        return ''
    return path.rstrip('/') or '/'


def _root_crumb(dlux_strings, *, label='', url='', url_name='', group_key='', current_path=''):
    normalized_url = _normalized_url_path(url)
    return {
        'label': label or dlux_strings.get('navbar_root', ''),
        'url': url,
        'clickable': bool(url) and normalized_url != _normalized_url_path(current_path),
        'url_name': url_name,
        'kind': 'root',
        'group_key': group_key,
    }


def _configured_root_crumb(config, home_url, request_path, dlux_strings, catalog, catalog_lookup):
    root_config = config.get('root') if isinstance(config.get('root'), dict) else {}
    mode = root_config.get('mode', 'neutral')
    if mode == 'neutral':
        return _root_crumb(dlux_strings, current_path=request_path)

    if mode == 'route':
        url_name = str(root_config.get('url_name') or '').strip()
        catalog_entry = catalog_lookup.get(url_name)
        if not url_name or not catalog_entry:
            return _root_crumb(dlux_strings, current_path=request_path)
        url = str(catalog_entry.get('url') or '').strip()
        if not url:
            try:
                url = reverse(url_name)
            except NoReverseMatch:
                return _root_crumb(dlux_strings, current_path=request_path)
        return _root_crumb(
            dlux_strings,
            label=str(catalog_entry.get('label') or '').strip() or _humanize(url_name),
            url=url,
            url_name=url_name,
            group_key=catalog_entry.get('group_key', ''),
            current_path=request_path,
        )

    if mode == 'home':
        url = str(home_url or '').strip()
        if not url:
            return _root_crumb(dlux_strings, current_path=request_path)
        target_path = _normalized_url_path(url)
        catalog_entry = next(
            (
                entry for entry in catalog
                if _normalized_url_path(entry.get('url')) == target_path
            ),
            None,
        )
        return _root_crumb(
            dlux_strings,
            label=(
                str((catalog_entry or {}).get('label') or '').strip()
                or dlux_strings.get('navbar_home', '')
                or dlux_strings.get('navbar_root', '')
            ),
            url=url,
            url_name=str((catalog_entry or {}).get('url_name') or '').strip(),
            group_key=(catalog_entry or {}).get('group_key', ''),
            current_path=request_path,
        )

    return _root_crumb(dlux_strings, current_path=request_path)


def _apply_root_boundary(root, trail, current_path):
    crumbs = list(trail or [])
    if crumbs and crumbs[0].get('kind') == 'root':
        crumbs = crumbs[1:]
    root_path = _normalized_url_path(root.get('url'))
    if not root_path:
        return [root, *crumbs]
    if root_path == _normalized_url_path(current_path):
        return [root]

    root_url_name = str(root.get('url_name') or '').strip()
    for index, crumb in enumerate(crumbs):
        crumb_url_name = str(crumb.get('url_name') or '').strip()
        name_match = bool(root_url_name and crumb_url_name == root_url_name)
        path_match = (
            crumb.get('kind') != 'manual'
            and _normalized_url_path(crumb.get('url')) == root_path
        )
        if name_match or path_match:
            return [root, *crumbs[index + 1:]]
    return [root, *crumbs]


def _system_crumb(dlux_strings):
    return {
        'label': dlux_strings.get('navbar_system', ''),
        'url': '',
        'clickable': False,
        'url_name': '',
        'kind': 'system',
    }


def _is_system_route(url_name, catalog_entry=None):
    if (catalog_entry or {}).get('group_key') == SYSTEM_GROUP_KEY:
        return True
    route_name = str(url_name or '')
    return route_name in SYSTEM_ROUTE_META or _route_leaf(route_name) in SYSTEM_ROUTE_META


def _inferred_system_route_crumbs(url_name, catalog_entry, lang_code, catalog_lookup):
    if not _is_system_route(url_name, catalog_entry):
        return []

    route_names = []
    seen = set()
    current = str(url_name or '').strip()
    while current:
        leaf = _route_leaf(current)
        if leaf in seen:
            break
        seen.add(leaf)
        route_names.append(current)
        parent = str((SYSTEM_ROUTE_META.get(leaf) or {}).get('breadcrumb_parent') or '').strip()
        if not parent or _route_leaf(parent) in seen:
            break
        current = parent

    return [
        _route_crumb(route_name, lang_code, catalog_lookup)
        for route_name in reversed(route_names)
    ]


def build_navbar_route_label_map(lang_code):
    route_labels = {}
    for entry in discover_sidebar_catalog(lang_code=lang_code, include_system_items=True):
        path = str(entry.get('url') or '').split('?', 1)[0].rstrip('/') or '/'
        label = str(entry.get('label') or '').strip()
        if path and label:
            route_labels[path] = label
    # Also label the system routes that are NOT sidebar candidates (e.g. the
    # user profile and reports overview) so the Nav Bar shows their translated
    # title instead of a client-side English humanization of the URL segment.
    from .translations import get_strings
    from .utils import get_system_config
    strings = get_strings(lang_code, overrides=get_system_config().get('translations'))
    for route_name, meta in SYSTEM_ROUTE_META.items():
        label_key = str((meta or {}).get('label_key') or '').strip()
        if not label_key:
            continue
        try:
            path = reverse(route_name).split('?', 1)[0].rstrip('/') or '/'
        except NoReverseMatch:
            continue
        label = str(strings.get(label_key) or '').strip()
        if label:
            route_labels.setdefault(path, label)
    return route_labels


def _with_system_group(root, crumbs, dlux_strings):
    if not crumbs:
        return [root]
    if any(crumb.get('kind') == 'system' for crumb in crumbs):
        return [root, *crumbs]
    if any(_is_system_route(crumb.get('url_name'), crumb) for crumb in crumbs):
        return [root, _system_crumb(dlux_strings), *crumbs]
    return [root, *crumbs]


def build_navbar_hierarchy_crumbs(
    request,
    navbar_config,
    lang_code,
    dlux_strings,
    runtime_crumbs=None,
    home_url='',
):
    config = normalize_navbar_config(navbar_config)
    request_path = getattr(request, 'path', '')
    neutral_root = _root_crumb(dlux_strings, current_path=request_path)
    catalog = discover_sidebar_catalog(lang_code=lang_code, include_system_items=True)
    catalog_lookup = {}
    for entry in catalog:
        url_name = str(entry.get('url_name') or '').strip()
        if url_name:
            catalog_lookup[url_name] = entry
            catalog_lookup.setdefault(_route_leaf(url_name), entry)
    root = _configured_root_crumb(
        config,
        home_url,
        request_path,
        dlux_strings,
        catalog,
        catalog_lookup,
    )

    def finalize(trail):
        return _apply_root_boundary(root, trail, request_path)

    explicit_crumbs = [
        crumb
        for crumb in (
            _runtime_to_crumb(raw_crumb, lang_code, dlux_strings)
            for raw_crumb in runtime_crumbs or []
        )
        if crumb
    ]
    if explicit_crumbs:
        return finalize([neutral_root, *explicit_crumbs])

    route_names = _route_candidates(request)
    route_chain = _find_route_chain(config.get('hierarchy', {}).get('nodes'), set(route_names))
    if route_chain:
        chain_crumbs = [_node_to_crumb(node, lang_code, catalog_lookup) for node in route_chain]
        return finalize(_with_system_group(neutral_root, chain_crumbs, dlux_strings))

    catalog_entry = None
    for name in route_names:
        catalog_entry = _route_catalog_entry(catalog_lookup, name)
        if catalog_entry:
            break
    fallback_name = route_names[0] if route_names else ''
    inferred_crumbs = _inferred_system_route_crumbs(
        fallback_name,
        catalog_entry,
        lang_code,
        catalog_lookup,
    )
    if inferred_crumbs:
        return finalize(_with_system_group(neutral_root, inferred_crumbs, dlux_strings))

    fallback_label = str((catalog_entry or {}).get('label') or '').strip() or _humanize(fallback_name)
    if not fallback_label:
        return finalize([neutral_root])
    fallback_url = str((catalog_entry or {}).get('url') or '').strip()
    if not fallback_url and fallback_name:
        try:
            fallback_url = reverse(fallback_name)
        except NoReverseMatch:
            fallback_url = ''
    return finalize([
        *(
            [neutral_root, _system_crumb(dlux_strings)]
            if _is_system_route(fallback_name, catalog_entry)
            else [neutral_root]
        ),
        {
            'label': fallback_label,
            'url': fallback_url,
            'clickable': bool(fallback_url) and not _is_root_like(fallback_label, fallback_name),
            'url_name': fallback_name,
            'kind': 'fallback',
            'group_key': (catalog_entry or {}).get('group_key', ''),
        },
    ])
