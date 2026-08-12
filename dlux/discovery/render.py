"""Building the sidebar tree for a request: labels, active state, counts."""

import copy
from django.core.cache import cache
from django.urls import NoReverseMatch, reverse

from .cache import SIDEBAR_CACHE_TIMEOUT, _sidebar_render_cache_key
from .inference import _humanize, _normalize_permissions, _pick_sidebar_label
from .merge import merge_sidebar_entries
from .routes import _is_api_navigation_route, discover_sidebar_catalog
from .sanitize import sanitize_sidebar_config


def _user_has_sidebar_permission(user, permissions, permissions_explicitly_set=False):
    from ..utils import user_has_any_permission_tokens

    # Superusers can see all sidebar items
    if user and getattr(user, 'is_superuser', False):
        return True
    
    # If no permissions, hide from non-superusers
    if not permissions:
        return False
    
    # Check permissions strictly - user must have the permission
    return user_has_any_permission_tokens(user, _normalize_permissions(permissions), default_visible_to_all=False)


def _is_active_path(request_path, url):
    if not request_path or not url or url == '#':
        return False
    return request_path == url or request_path.startswith(url.rstrip('/') + '/')


def _normalized_active_path(value):
    value = str(value or '').split('?', 1)[0].strip()
    if not value:
        return ''
    return value.rstrip('/') or '/'


def _iter_render_sidebar_items(entries):
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        if entry.get('kind') == 'group':
            yield from _iter_render_sidebar_items(entry.get('items'))
            continue
        yield entry


def _apply_sidebar_active_state(entries, request_path, open_accordions):
    items = list(_iter_render_sidebar_items(entries))
    current_path = _normalized_active_path(request_path)
    exact_match = any(_normalized_active_path(item.get('url')) == current_path for item in items)
    for item in items:
        item_url = item.get('url')
        item['active'] = (
            _normalized_active_path(item_url) == current_path
            if exact_match
            else _is_active_path(request_path, item_url)
        )

    open_ids = set(open_accordions or [])
    for entry in entries if isinstance(entries, list) else []:
        if isinstance(entry, dict) and entry.get('kind') == 'group':
            has_active = any(item.get('active') for item in entry.get('items', []))
            entry['has_active'] = has_active
            entry['is_open'] = entry.get('id') in open_ids or has_active


def annotate_sidebar_notification_counts(entries, section_counts):
    normalized_counts = {}
    if isinstance(section_counts, dict):
        for raw_key, raw_count in section_counts.items():
            key = str(raw_key or '').strip().lower()
            try:
                count = max(0, int(raw_count))
            except (TypeError, ValueError):
                count = 0
            if key and count:
                normalized_counts[key] = count

    def annotate(entry):
        if not isinstance(entry, dict):
            return set()
        if entry.get('kind') == 'group':
            model_keys = set()
            for item in entry.get('items', []):
                model_keys.update(annotate(item))
        else:
            key = str(entry.get('notification_model_key') or '').strip().lower()
            model_keys = {key} if key else set()

        count = sum(normalized_counts.get(key, 0) for key in model_keys)
        entry['notification_model_keys'] = sorted(model_keys)
        entry['notification_count'] = count
        entry['notification_display_count'] = '99+' if count > 99 else str(count or '')
        return model_keys

    for entry in entries if isinstance(entries, list) else []:
        annotate(entry)
    return entries


def build_sidebar_navigation(lang_code=None, sidebar_override=None, user=None, request_path='', open_accordions=None):
    """
    Transform sidebar JSON config into a single render-ready sidebar tree.
    """
    from ..utils import get_system_config

    config = get_system_config()
    base_sidebar = sanitize_sidebar_config(config.get('sidebar', {}), allow_system_items=True)
    if not base_sidebar.get('enabled', True):
        return {
            'entries': [],
            'auto_items': [],
            'extra_groups': [],
            'home_url_name': None,
            'sidebar': base_sidebar,
        }
    override_sidebar = sanitize_sidebar_config(sidebar_override, allow_system_items=True) if isinstance(sidebar_override, dict) else None
    if override_sidebar and override_sidebar.get('entries'):
        sidebar = {
            'home_url_name': base_sidebar.get('home_url_name'),
            'entries': merge_sidebar_entries(base_sidebar.get('entries', []), override_sidebar.get('entries', [])),
        }
    else:
        sidebar = base_sidebar

    open_accordions = set(open_accordions or [])

    def render_sidebar_entries(raw_entries, catalog):
        if not isinstance(raw_entries, list):
            return []

        render_entries = []
        for entry in raw_entries:
            if not isinstance(entry, dict):
                continue

            kind = entry.get('kind', 'item')
            if kind == 'group':
                items = []
                for raw_item in entry.get('items', []):
                    resolved_item = _resolve_sidebar_item(raw_item, catalog, lang_code)
                    if resolved_item and _user_has_sidebar_permission(user, resolved_item.get('permissions'), resolved_item.get('permissions_explicit', False)):
                        items.append(resolved_item)
                if items:
                    group_id = entry.get('id') or f"group-{len(render_entries) + 1}"
                    group_label_override = _pick_sidebar_label(entry.get('labels'), lang_code)
                    inferred_group_label = next((item.get('group_label') for item in items if item.get('group_label')), None)
                    inferred_group_icon = next((item.get('group_icon') for item in items if item.get('group_icon')), None)
                    render_entries.append({
                        'kind': 'group',
                        'id': group_id,
                        'label': group_label_override or inferred_group_label or entry.get('label') or 'Group',
                        'icon': inferred_group_icon or entry.get('icon') or 'bi-folder2-open',
                        'url': _resolve_group_url(entry),
                        'url_name': entry.get('url_name'),
                        'items': items,
                        'has_active': False,
                        'is_open': False,
                        'raw_name': entry.get('id') or group_id,
                    })
                continue

            resolved = _resolve_sidebar_item(entry, catalog, lang_code)
            if resolved and _user_has_sidebar_permission(user, resolved.get('permissions'), resolved.get('permissions_explicit', False)):
                render_entries.append(resolved)
        return render_entries

    render_cache_key = _sidebar_render_cache_key(lang_code, sidebar, override_sidebar, user)
    cached_navigation = cache.get(render_cache_key)
    if cached_navigation is None:
        catalog = {entry['id']: entry for entry in discover_sidebar_catalog(lang_code=lang_code, include_system_items=True)}
        render_entries = render_sidebar_entries(sidebar.get('entries', []) if isinstance(sidebar, dict) else [], catalog)
        fallback_used = False
        if override_sidebar and override_sidebar.get('entries') and not render_entries and base_sidebar.get('entries'):
            sidebar = base_sidebar
            render_entries = render_sidebar_entries(base_sidebar.get('entries', []), catalog)
            fallback_used = True
        cached_navigation = {
            'entries': render_entries,
            'home_url_name': sidebar.get('home_url_name'),
            'sidebar': sidebar,
            'fallback_used': fallback_used,
        }
        cache.set(render_cache_key, cached_navigation, timeout=SIDEBAR_CACHE_TIMEOUT)

    cached_navigation = copy.deepcopy(cached_navigation)
    render_entries = cached_navigation.get('entries', [])
    _apply_sidebar_active_state(render_entries, request_path, open_accordions)
    sidebar = cached_navigation.get('sidebar') or sidebar
    if cached_navigation.get('fallback_used'):
        sidebar = base_sidebar

    return {
        'entries': render_entries,
        'auto_items': [entry for entry in render_entries if entry.get('kind') != 'group'],
        'extra_groups': [entry for entry in render_entries if entry.get('kind') == 'group'],
        'home_url_name': cached_navigation.get('home_url_name'),
        'sidebar': sidebar,
    }


def _resolve_group_url(entry):
    url_name = entry.get('url_name')
    if url_name:
        try:
            return reverse(url_name)
        except NoReverseMatch:
            return '#'
    url = entry.get('url')
    return url or '#'


def _resolve_sidebar_item(entry, catalog, lang_code=None):
    item = dict(entry)
    label_override = _pick_sidebar_label(entry.get('labels'), lang_code)
    discovered = catalog.get(item.get('id') or item.get('url_name') or '')
    if discovered:
        merged = dict(discovered)
        # Preserve permissions_explicit from catalog (don't let sidebar override it)
        catalog_permissions_explicit = discovered.get('permissions_explicit', False)
        merged.update({
            k: v
            for k, v in item.items()
            if k not in {'label', 'group_label', 'permissions_explicit'}
            and v not in [None, '', [], {}]
        })
        merged['permissions_explicit'] = catalog_permissions_explicit
        item = merged

    url_name = item.get('url_name')
    if url_name:
        try:
            item['url'] = reverse(url_name)
        except NoReverseMatch:
            return None
    elif item.get('url'):
        item['url'] = item['url']
    else:
        return None

    if _is_api_navigation_route(url_name, item.get('url')):
        return None

    # A per-language override wins; otherwise the catalog's per-language label
    # (for discovered routes) or the stored/humanized label is used.
    item['label'] = label_override or item.get('label') or _humanize(item.get('id') or url_name or 'link')
    item['icon'] = item.get('icon') or 'bi-link-45deg'
    item['permissions'] = _normalize_permissions(item.get('permissions') or item.get('permission'))
    item['id'] = item.get('id') or url_name or item.get('url')
    item['url_name'] = url_name or item.get('id') or item.get('url')
    return item
