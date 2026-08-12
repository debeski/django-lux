"""Merging a stored sidebar against freshly discovered routes."""


from .inference import _guess_group_icon
from .routes import discover_sidebar_catalog
from .sanitize import _clone_sidebar_entry, _sidebar_entry_id, sanitize_sidebar_config


def merge_sidebar_entries(base_entries, override_entries):
    """
    Merge a user-specific tree override onto the base sidebar tree.

    The override controls ordering and item/group placement, while any new base
    entries that are missing from the override are appended in their natural
    base locations so users do not lose newly added navigation.
    """
    if not isinstance(base_entries, list):
        base_entries = []
    if not isinstance(override_entries, list) or not override_entries:
        return [_clone_sidebar_entry(entry) for entry in base_entries if isinstance(entry, dict)]

    item_pool = {}
    group_pool = {}
    group_item_pool = {}

    for base_entry in base_entries:
        if not isinstance(base_entry, dict):
            continue
        entry_id = _sidebar_entry_id(base_entry)
        if not entry_id:
            continue
        if base_entry.get('kind') == 'group':
            group_pool[entry_id] = {
                key: value
                for key, value in base_entry.items()
                if key != 'items'
            }
            group_pool[entry_id]['id'] = entry_id
            group_pool[entry_id]['kind'] = 'group'
            group_item_pool[entry_id] = []
            for child in base_entry.get('items', []):
                if not isinstance(child, dict):
                    continue
                child_id = _sidebar_entry_id(child)
                if not child_id:
                    continue
                normalized_child = dict(child)
                normalized_child['id'] = child_id
                normalized_child['kind'] = 'item'
                item_pool[child_id] = normalized_child
                group_item_pool[entry_id].append(child_id)
        else:
            normalized_item = dict(base_entry)
            normalized_item['id'] = entry_id
            normalized_item['kind'] = 'item'
            item_pool[entry_id] = normalized_item

    consumed_items = set()
    consumed_groups = set()

    def merge_item(item_id, override_item=None):
        if not item_id or item_id in consumed_items or item_id not in item_pool:
            return None
        merged_item = dict(item_pool[item_id])
        if isinstance(override_item, dict):
            merged_item.update({
                key: value
                for key, value in override_item.items()
                if key != 'items' and value not in [None, '', [], {}]
            })
        merged_item['id'] = item_id
        merged_item['kind'] = 'item'
        consumed_items.add(item_id)
        return merged_item

    def merge_group(group_id, override_group=None):
        if not group_id or group_id in consumed_groups or group_id not in group_pool:
            return None
        merged_group = dict(group_pool[group_id])
        if isinstance(override_group, dict):
            merged_group.update({
                key: value
                for key, value in override_group.items()
                if key != 'items' and value not in [None, '', [], {}]
            })
        merged_group['id'] = group_id
        merged_group['kind'] = 'group'
        merged_group_items = []

        for child in (override_group or {}).get('items', []):
            child_id = _sidebar_entry_id(child)
            merged_child = merge_item(child_id, child)
            if merged_child:
                merged_group_items.append(merged_child)

        for child_id in group_item_pool.get(group_id, []):
            merged_child = merge_item(child_id)
            if merged_child:
                merged_group_items.append(merged_child)

        merged_group['items'] = merged_group_items
        consumed_groups.add(group_id)
        return merged_group if merged_group_items else None

    merged_entries = []

    for override_entry in override_entries:
        if not isinstance(override_entry, dict):
            continue
        entry_id = _sidebar_entry_id(override_entry)
        if override_entry.get('kind') == 'group':
            merged_group = merge_group(entry_id, override_entry)
            if merged_group:
                merged_entries.append(merged_group)
        else:
            merged_item = merge_item(entry_id, override_entry)
            if merged_item:
                merged_entries.append(merged_item)

    for base_entry in base_entries:
        if not isinstance(base_entry, dict):
            continue
        entry_id = _sidebar_entry_id(base_entry)
        if base_entry.get('kind') == 'group':
            merged_group = merge_group(entry_id)
            if merged_group:
                merged_entries.append(merged_group)
        else:
            merged_item = merge_item(entry_id)
            if merged_item:
                merged_entries.append(merged_item)

    return merged_entries


def build_default_sidebar_config(lang_code=None):
    """Build a useful starter sidebar from discovered routes.

    Form pages are discoverable and pickable in the builder, but a zero-config
    sidebar should list places, not actions — so they are never auto-added.
    """
    catalog = [
        entry
        for entry in discover_sidebar_catalog(lang_code=lang_code)
        if not entry.get('is_form_page')
    ]
    grouped = {}
    for entry in catalog:
        grouped.setdefault(entry['group_key'], {
            'label': entry['group_label'],
            'icon': entry.get('group_icon') or _guess_group_icon(entry['group_key']),
            'entries': [],
        })
        grouped[entry['group_key']]['entries'].append(entry)

    final_entries = []
    for group_key, group in grouped.items():
        dashboard_entry = None
        remaining = []
        for entry in group['entries']:
            leaf = entry['url_name'].split(':')[-1]
            if dashboard_entry is None and leaf in ['dashboard', 'index', 'home']:
                dashboard_entry = dict(entry)
            else:
                remaining.append(dict(entry))

        if dashboard_entry is not None:
            final_entries.append(dashboard_entry)

        if group_key == 'dlux' or remaining:
            group_entry = {
                'kind': 'group',
                'id': f'{group_key}-group',
                'label': group['label'],
                'icon': group['icon'],
                'items': remaining if group_key != 'dlux' else [dict(entry) for entry in group['entries'] if entry.get('url_name') != (dashboard_entry or {}).get('url_name')],
            }
            if group_entry['items']:
                final_entries.append(group_entry)

    return sanitize_sidebar_config({
        'home_url_name': None,
        'entries': final_entries,
    })
