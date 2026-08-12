"""Validating and cleaning stored sidebar/navbar configuration."""


from .inference import _normalize_sidebar_labels, _plain_text
from .meta import HIDDEN_SIDEBAR_GROUP_KEYS, SYSTEM_ROUTE_META, _route_leaf
from .routes import _is_api_navigation_route, _is_configurable_system_url


def _is_hidden_sidebar_url(url_name, allow_system_items=False):
    if not url_name or not isinstance(url_name, str):
        return False
    if _route_leaf(url_name) in SYSTEM_ROUTE_META:
        if allow_system_items and _is_configurable_system_url(url_name):
            return False
        return True
    namespace = url_name.split(':')[0] if ':' in url_name else ''
    if allow_system_items and _is_configurable_system_url(url_name):
        return False
    return namespace in HIDDEN_SIDEBAR_GROUP_KEYS


def _is_hidden_sidebar_entry(entry, allow_system_items=False):
    if not isinstance(entry, dict):
        return False

    url_name = entry.get('url_name')
    entry_id = entry.get('id')
    if not url_name and isinstance(entry_id, str):
        url_name = entry_id

    if _is_api_navigation_route(url_name, entry.get('url')):
        return True
    if allow_system_items and _is_configurable_system_url(url_name):
        return False

    group_key = entry.get('group_key')
    if group_key in HIDDEN_SIDEBAR_GROUP_KEYS:
        return True

    if _is_hidden_sidebar_url(url_name, allow_system_items=allow_system_items):
        return True

    if isinstance(entry_id, str) and _is_hidden_sidebar_url(entry_id, allow_system_items=allow_system_items):
        return True

    return False


def _sanitize_sidebar_entry(entry, allow_system_items=False):
    if not isinstance(entry, dict):
        return None

    kind = entry.get('kind', 'item')
    if kind == 'group':
        items = []
        for item in entry.get('items', []):
            cleaned_item = _sanitize_sidebar_entry(item, allow_system_items=allow_system_items)
            if cleaned_item:
                items.append(cleaned_item)

        if not items:
            return None

        cleaned_group = dict(entry)
        cleaned_group['label'] = _plain_text(cleaned_group.get('label') or 'Group')
        cleaned_group['icon'] = _plain_text(cleaned_group.get('icon') or 'bi-folder2-open')
        cleaned_group['items'] = items
        group_labels = _normalize_sidebar_labels(cleaned_group.get('labels'))
        if group_labels:
            cleaned_group['labels'] = group_labels
        else:
            cleaned_group.pop('labels', None)
        return cleaned_group

    if _is_hidden_sidebar_entry(entry, allow_system_items=allow_system_items):
        return None

    cleaned_item = dict(entry)
    if 'label' in cleaned_item:
        cleaned_item['label'] = _plain_text(cleaned_item.get('label'))
    if 'icon' in cleaned_item:
        cleaned_item['icon'] = _plain_text(cleaned_item.get('icon'))
    if 'group_label' in cleaned_item:
        cleaned_item['group_label'] = _plain_text(cleaned_item.get('group_label'))
    item_labels = _normalize_sidebar_labels(cleaned_item.get('labels'))
    if item_labels:
        cleaned_item['labels'] = item_labels
    else:
        cleaned_item.pop('labels', None)
    return cleaned_item


def sanitize_sidebar_config(sidebar_config, allow_system_items=False):
    from ..utils import normalize_sidebar_behavior

    if not isinstance(sidebar_config, dict):
        return normalize_sidebar_behavior({
            'home_url_name': None,
            'entries': [],
        })

    sanitized = dict(sidebar_config)
    sanitized_entries = []
    for entry in sidebar_config.get('entries', []):
        cleaned_entry = _sanitize_sidebar_entry(entry, allow_system_items=allow_system_items)
        if cleaned_entry:
            sanitized_entries.append(cleaned_entry)

    home_url_name = sidebar_config.get('home_url_name')
    if _is_hidden_sidebar_url(home_url_name, allow_system_items=allow_system_items):
        home_url_name = None

    top_level_items = [
        entry.get('url_name')
        for entry in sanitized_entries
        if entry.get('kind') == 'item' and entry.get('url_name')
    ]
    if home_url_name not in top_level_items:
        home_url_name = None

    sanitized['home_url_name'] = home_url_name
    sanitized['entries'] = sanitized_entries
    sanitized.update(normalize_sidebar_behavior(sidebar_config))
    sanitized['home_url_name'] = home_url_name
    sanitized['entries'] = sanitized_entries
    return sanitized


def sanitize_navbar_config(navbar_config):
    from ..system.defaults import default_navbar_config
    from ..system.normalizers import normalize_navbar_config

    sanitized = normalize_navbar_config(navbar_config)

    def sanitize_nodes(nodes):
        cleaned = []
        for raw_node in nodes if isinstance(nodes, list) else []:
            node = dict(raw_node)
            children = sanitize_nodes(node.get('children'))
            kind = node.get('kind')
            url_name = node.get('url_name') or (node.get('id') if kind == 'route' else '')
            url = node.get('url', '')

            if kind == 'route' and _is_api_navigation_route(url_name, url):
                cleaned.extend(children)
                continue
            if kind != 'route' and url and _is_api_navigation_route(url=url):
                node.pop('url', None)
                if not children:
                    continue

            node['children'] = children
            cleaned.append(node)
        return cleaned

    sanitized['hierarchy']['nodes'] = sanitize_nodes(sanitized.get('hierarchy', {}).get('nodes'))
    root = sanitized.get('root', {})
    if root.get('mode') == 'route' and _is_api_navigation_route(root.get('url_name')):
        sanitized['root'] = default_navbar_config()['root']
    return sanitized


def _sidebar_entry_id(entry):
    if not isinstance(entry, dict):
        return None
    return entry.get('id') or entry.get('url_name') or entry.get('url')


def _clone_sidebar_entry(entry):
    cloned = dict(entry)
    if cloned.get('kind') == 'group':
        cloned['items'] = [_clone_sidebar_entry(item) for item in cloned.get('items', []) if isinstance(item, dict)]
    return cloned
