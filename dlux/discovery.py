"""
Resolver-driven sidebar discovery and rendering helpers.

This module powers:
1. Discovery of valid, reversible sidebar candidates.
2. Default zero-boilerplate sidebar configuration generation.
3. Transformation of stored sidebar JSON into render-ready items/groups.
"""
import copy
import hashlib
import json
import re

from django.apps import apps
from django.conf import settings
from django.core.cache import cache
from django.urls import NoReverseMatch, URLPattern, URLResolver, get_resolver, reverse
from django.utils.encoding import force_str


SIDEBAR_CACHE_TIMEOUT = 300
SIDEBAR_CACHE_VERSION_KEY = 'dlux:sidebar:version'


EXCLUDED_EXACT_NAMES = {
    'login',
    'logout',
    'toggle_sidebar',
    'verify_otp_enable',
    'verify_otp_login',
    'verify_otp_generic',
    'enable_2fa',
    'setup_totp',
    'disable_2fa',
    'generate_backup_codes',
    'resend_otp',
    'resend_otp_login',
    'system_setup',
    'manage_users',
    'manage_scopes',
    'add_subsection',
}

EXCLUDED_NAME_PARTS = (
    'modal',
    'delete',
    'api_',
    'get_',
    'save_',
    'toggle_',
    'verify_otp',
    'resend_otp',
    'reset_password',
)

EXCLUDED_ROUTE_TOKENS = {
    'ajax',
    'add',
    'create',
    'edit',
    'update',
}

EXCLUDED_EXACT_ROUTE_NAMES = {
    'set_active_model',
}

EXCLUDED_NAMESPACE_PREFIXES = {
    'admin',
    'health_check',
}

EXCLUDED_PATH_PARTS = (
    '/accounts/login/',
    '/accounts/logout/',
    '/health/',
    '/sys/2fa/',
    '/api/',
    '/sys/modals/',
    '/sys/setup/',
)

SYSTEM_ROUTE_META = {
    'manage_sections': {
        'label_key': 'manage_sections',
        'icon': 'bi-diagram-3',
        'permissions': ['__dlux_sections_view__'],
        'group_key': 'dlux',
    },
    'manage_users': {
        'label_key': 'manage_users',
        'icon': 'bi-people',
        'permissions': ['__dlux_user_directory__'],
        'group_key': 'dlux',
    },
    'user_activity_log': {
        'label_key': 'activity_log',
        'icon': 'bi-clock-history',
        'permissions': ['__dlux_activity_log__'],
        'group_key': 'dlux',
    },
    'user_profile': {
        'label_key': 'profile',
        'icon': 'bi-person-badge',
        'permissions': ['__dlux_authenticated__'],
        'group_key': 'dlux',
    },
    'options_view': {
        'label_key': 'options_title',
        'icon': 'bi-gear',
        'permissions': ['__dlux_authenticated__'],
        'group_key': 'dlux',
    },
    'system_backup_page': {
        'label_key': 'sysbackup_title',
        'icon': 'bi-safe2-fill',
        'permissions': ['is_superuser'],
        'group_key': 'dlux',
    },
}

CONFIGURABLE_SYSTEM_ROUTE_NAMES = {
    'manage_sections',
    'manage_users',
    'user_activity_log',
    'options_view',
    'system_backup_page',
}

HIDDEN_SIDEBAR_GROUP_KEYS = {'dlux'}

GROUP_ICON_DEFAULTS = {
    'dlux': 'bi-sliders',
    'core': 'bi-grid-1x2',
    'storage': 'bi-box-seam',
    'finance': 'bi-wallet2',
    'treasury': 'bi-safe',
    'hr_payroll': 'bi-person-badge',
}

VIEW_ICON_HINTS = {
    'dashboard': 'bi-speedometer2',
    'index': 'bi-house',
    'home': 'bi-house',
    'profile': 'bi-person-badge',
    'options': 'bi-gear',
    'users': 'bi-people',
    'sections': 'bi-diagram-3',
    'log': 'bi-clock-history',
    'report': 'bi-file-earmark-bar-graph',
    'import': 'bi-box-arrow-in-right',
    'export': 'bi-box-arrow-right',
    'return': 'bi-arrow-return-left',
    'asset': 'bi-inboxes',
    'fiscal': 'bi-calendar3',
    'chapter': 'bi-list-ul',
    'budget': 'bi-wallet2',
    'revenue': 'bi-cash-stack',
    'disbursement': 'bi-receipt',
    'check': 'bi-credit-card',
    'advance': 'bi-currency-exchange',
    'trust': 'bi-safe',
    'guarantee': 'bi-shield-check',
    'ledger': 'bi-book',
    'personnel': 'bi-people',
    'payroll': 'bi-file-earmark-spreadsheet',
    'wage': 'bi-clock-history',
    'transfer': 'bi-bank',
}


def _iterate_named_patterns(patterns, namespaces=None):
    namespaces = namespaces or []
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            next_namespaces = list(namespaces)
            if pattern.namespace:
                next_namespaces.append(pattern.namespace)
            yield from _iterate_named_patterns(pattern.url_patterns, next_namespaces)
        elif isinstance(pattern, URLPattern) and pattern.name:
            full_name = ':'.join(namespaces + [pattern.name]) if namespaces else pattern.name
            yield pattern, full_name


def _humanize(name):
    name = (name or '').replace('-', ' ').replace('_', ' ').strip()
    if not name:
        return 'Untitled'
    return ' '.join(part.capitalize() for part in name.split())


def _route_name_tokens(value):
    return [token for token in re.split(r'[_:\-]+', (value or '').lower()) if token]


def _route_leaf(url_name):
    return str(url_name or '').split(':')[-1]


def _plain_text(value, fallback=''):
    if value is None:
        return fallback
    return force_str(value)


def _stable_hash(value):
    try:
        payload = json.dumps(value, sort_keys=True, default=str, separators=(',', ':'))
    except TypeError:
        payload = repr(value)
    return hashlib.md5(payload.encode()).hexdigest()[:12]


def _sidebar_cache_version():
    version = cache.get(SIDEBAR_CACHE_VERSION_KEY)
    if version is None:
        version = 1
        cache.set(SIDEBAR_CACHE_VERSION_KEY, version, timeout=None)
    return version


def bump_sidebar_cache_version():
    try:
        cache.incr(SIDEBAR_CACHE_VERSION_KEY)
    except ValueError:
        cache.set(SIDEBAR_CACHE_VERSION_KEY, 2, timeout=None)


def _urlconf_cache_identity():
    resolver = get_resolver()
    return {
        'root': getattr(settings, 'ROOT_URLCONF', ''),
        'module': getattr(getattr(resolver, 'urlconf_module', None), '__name__', ''),
        'patterns_id': id(getattr(resolver, 'url_patterns', None)),
    }


def _sidebar_catalog_cache_key(lang_code, include_system_items, config):
    return 'dlux:sidebar:catalog:{version}:{payload}'.format(
        version=_sidebar_cache_version(),
        payload=_stable_hash({
            'lang': lang_code,
            'include_system_items': bool(include_system_items),
            'urlconf': _urlconf_cache_identity(),
            'config': {
                'default_language': config.get('default_language'),
                'translations': config.get('translations'),
            },
        }),
    )


def _user_sidebar_permission_hash(user):
    if not user or not getattr(user, 'is_authenticated', False):
        return 'anonymous'
    permissions = []
    try:
        permissions = sorted(user.get_all_permissions())
    except Exception:
        permissions = sorted(getattr(user, '_permissions', []) or [])
    try:
        profile = getattr(user, 'profile', None)
    except Exception:
        profile = None
    scope_id = getattr(profile, 'scope_id', None) if profile is not None else getattr(user, 'scope_id', None)
    return _stable_hash({
        'user_id': getattr(user, 'pk', None),
        'is_staff': bool(getattr(user, 'is_staff', False)),
        'is_superuser': bool(getattr(user, 'is_superuser', False)),
        'scope_id': scope_id,
        'permissions': permissions,
    })


def _sidebar_render_cache_key(lang_code, sidebar, override_sidebar, user):
    return 'dlux:sidebar:render:{version}:{payload}'.format(
        version=_sidebar_cache_version(),
        payload=_stable_hash({
            'lang': lang_code,
            'sidebar': sidebar,
            'override': override_sidebar,
            'user': _user_sidebar_permission_hash(user),
            'urlconf': _urlconf_cache_identity(),
        }),
    )


def _guess_icon(url_name, model=None, callback=None):
    explicit = getattr(callback, 'sidebar_icon', None)
    if explicit:
        return _plain_text(explicit)
    if model and getattr(model._meta, 'sidebar_icon', None):
        return _plain_text(getattr(model._meta, 'sidebar_icon'))

    # Honour the icon declared for a system route (mirrors how label_key is used),
    # so routes without a matching VIEW_ICON_HINTS token still get a real icon.
    meta_leaf = _route_leaf(url_name)
    if meta_leaf in SYSTEM_ROUTE_META and SYSTEM_ROUTE_META[meta_leaf].get('icon'):
        return _plain_text(SYSTEM_ROUTE_META[meta_leaf]['icon'])

    leaf = url_name.split(':')[-1].lower()
    for hint, icon in VIEW_ICON_HINTS.items():
        if hint in leaf:
            return _plain_text(icon)

    namespace = url_name.split(':')[0] if ':' in url_name else ''
    return _plain_text(GROUP_ICON_DEFAULTS.get(namespace, 'bi-link-45deg'))


def _guess_group_icon(group_key):
    return _plain_text(GROUP_ICON_DEFAULTS.get(group_key, 'bi-folder2-open'))


def _normalize_permissions(value):
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [item for item in value if item]
    return []


def _is_configurable_system_url(url_name):
    return isinstance(url_name, str) and _route_leaf(url_name) in CONFIGURABLE_SYSTEM_ROUTE_NAMES


def _infer_model(pattern):
    callback = getattr(pattern, 'callback', None)
    view_class = getattr(callback, 'view_class', None)
    if view_class is not None:
        queryset = getattr(view_class, 'queryset', None)
        if getattr(queryset, 'model', None) is not None:
            return queryset.model
        model = getattr(view_class, 'model', None)
        if model is not None:
            return model
    return None


def _infer_callback_app_label(callback):
    module_name = getattr(callback, '__module__', '') or ''
    root_module = module_name.split('.')[0] if module_name else ''
    if not root_module:
        return None
    try:
        apps.get_app_config(root_module)
        return root_module
    except LookupError:
        return None


def _infer_group_key(url_name, model, callback):
    explicit = getattr(callback, 'sidebar_group', None)
    if explicit:
        return explicit
    if model is not None:
        return model._meta.app_label
    callback_app = _infer_callback_app_label(callback)
    if callback_app:
        return callback_app
    leaf = _route_leaf(url_name)
    if leaf in SYSTEM_ROUTE_META:
        return SYSTEM_ROUTE_META[leaf]['group_key']
    if ':' in url_name:
        return url_name.split(':')[0]
    return 'general'


def _group_label(group_key, strings, lang_code=None):
    if group_key == 'dlux':
        return _plain_text(strings.get('sidebar_system', 'System Management'))

    translation_key = f'app_{group_key}'
    if translation_key in strings:
        return _plain_text(strings.get(translation_key))

    try:
        app_config = apps.get_app_config(group_key)
        verbose_name = _plain_text(app_config.verbose_name)
    except LookupError:
        verbose_name = ''

    if (lang_code or '').split('-')[0] == 'ar' and verbose_name:
        return verbose_name

    return _humanize(group_key)


def _infer_label(url_name, strings, model=None, callback=None):
    explicit = getattr(callback, 'sidebar_label', None)
    if explicit:
        return _plain_text(explicit)

    leaf = _route_leaf(url_name)
    namespace = url_name.split(':')[0] if ':' in url_name else ''
    group_key = _infer_group_key(url_name, model, callback)
    group_label = _group_label(group_key, strings)

    if leaf in SYSTEM_ROUTE_META:
        return _plain_text(strings.get(SYSTEM_ROUTE_META[leaf]['label_key'], _humanize(leaf)))

    candidates = [
        f'view_{leaf}',
        f'page_title_{namespace}_{leaf}' if namespace else '',
        f'page_title_{leaf}',
        f'{namespace}_{leaf}' if namespace else '',
        leaf,
    ]
    for key in candidates:
        if key and key in strings:
            return _plain_text(strings[key])

    if model is not None:
        if leaf.endswith('list'):
            return _plain_text(
                strings.get(
                    f'models_{model._meta.model_name}',
                    strings.get(f'model_{model._meta.model_name}', str(model._meta.verbose_name_plural))
                )
            )
        if leaf in ['dashboard', 'index', 'home']:
            return _plain_text(strings.get(f'{model._meta.app_label}_{leaf}', _humanize(f'{model._meta.app_label} {leaf}')))
        return _plain_text(strings.get(f'model_{model._meta.model_name}', str(model._meta.verbose_name_plural)))

    if leaf in ['dashboard', 'index', 'home'] and namespace:
        return _plain_text(f"{group_label} {_humanize(leaf)}")

    return _plain_text(_humanize(leaf))


def _infer_permissions(url_name, model, callback):
    explicit = _normalize_permissions(getattr(callback, 'sidebar_permissions', None))
    if explicit:
        return explicit, True

    explicit = _normalize_permissions(getattr(callback, 'permission_required', None))
    if explicit:
        return explicit, True

    leaf = _route_leaf(url_name)
    if leaf in SYSTEM_ROUTE_META:
        perms = list(SYSTEM_ROUTE_META[leaf].get('permissions', []))
        return perms, True

    if model is not None:
        perm = f'{model._meta.app_label}.view_{model._meta.model_name}'
        return [perm], False

    # For function-based views, try to infer from URL namespace and name
    app_label = None
    model_name = None
    
    # Try to get app label from URL namespace
    if ':' in url_name:
        namespace = url_name.split(':')[0]
        app_label = namespace
        # Get the leaf part for model name
        leaf = url_name.split(':')[-1]
        # Extract model name from patterns like outgoing_list, incoming_list, etc.
        if '_' in leaf:
            parts = leaf.split('_')
            # For patterns like outgoing_list, incoming_list, use the first part as model name
            if parts[-1] in ['list', 'index', 'dashboard', 'home']:
                model_name = parts[0]
            else:
                # For other patterns, use the first part as model name
                model_name = parts[0]
        else:
            model_name = leaf
    
    # If no namespace, try to infer from callback module
    if not app_label and callback:
        module_name = getattr(callback, '__module__', '') or ''
        if module_name:
            # module_name is like 'documents.views' or 'documents'
            app_label = module_name.split('.')[0]
            # Try to get model name from URL name
            leaf = url_name.split(':')[-1] if ':' in url_name else url_name
            if '_' in leaf:
                parts = leaf.split('_')
                if parts[-1] in ['list', 'index', 'dashboard', 'home']:
                    model_name = parts[0]
                else:
                    model_name = parts[0]
            else:
                model_name = leaf
    
    if app_label and model_name:
        perm = f'{app_label}.view_{model_name}'
        return [perm], False

    return [], False


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
    return cleaned_item


def sanitize_sidebar_config(sidebar_config, allow_system_items=False):
    from .utils import normalize_sidebar_behavior

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


def _sidebar_entry_id(entry):
    if not isinstance(entry, dict):
        return None
    return entry.get('id') or entry.get('url_name') or entry.get('url')


def _clone_sidebar_entry(entry):
    cloned = dict(entry)
    if cloned.get('kind') == 'group':
        cloned['items'] = [_clone_sidebar_entry(item) for item in cloned.get('items', []) if isinstance(item, dict)]
    return cloned


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


def _is_candidate(url_name, url, callback, include_system_items=False):
    leaf = url_name.split(':')[-1]
    namespace = url_name.split(':')[0] if ':' in url_name else ''
    lower_name = url_name.lower()
    lower_leaf = leaf.lower()
    leaf_tokens = set(_route_name_tokens(leaf))

    if namespace in EXCLUDED_NAMESPACE_PREFIXES:
        return False
    # API URL namespaces (the `<app>_api` / `api` convention, e.g. DRF routers)
    # expose the same models as the page views under the same inferred label, so
    # they otherwise surface as duplicate, non-navigable sidebar/landing entries.
    if namespace == 'api' or namespace.endswith('_api'):
        return False
    if lower_leaf in EXCLUDED_EXACT_NAMES and not (include_system_items and _is_configurable_system_url(url_name)):
        return False
    if lower_leaf in EXCLUDED_EXACT_ROUTE_NAMES:
        return False
    if leaf_tokens.intersection(EXCLUDED_ROUTE_TOKENS):
        return False
    if any(part in lower_name for part in EXCLUDED_NAME_PARTS):
        return False
    if any(part in url for part in EXCLUDED_PATH_PARTS):
        return False
    if getattr(callback, 'sidebar_exclude', False):
        return False

    return True


def _discover_sidebar_catalog_uncached(lang_code=None, include_system_items=False, config=None):
    """Return all valid, reversible sidebar candidates."""
    from .translations import get_strings
    from .utils import get_system_config

    config = config if isinstance(config, dict) else get_system_config()
    lang_code = (lang_code or config.get('default_language', 'en')).split('-')[0]
    strings = get_strings(lang_code, overrides=config.get('translations'))

    catalog = []
    resolver = get_resolver()
    for pattern, url_name in _iterate_named_patterns(resolver.url_patterns):
        callback = getattr(pattern, 'callback', None)
        try:
            url = reverse(url_name)
        except NoReverseMatch:
            continue

        if not _is_candidate(url_name, url, callback, include_system_items=include_system_items):
            continue

        model = _infer_model(pattern)
        group_key = _infer_group_key(url_name, model, callback)
        if group_key in HIDDEN_SIDEBAR_GROUP_KEYS and not (include_system_items and _is_configurable_system_url(url_name)):
            continue
        group_label = _group_label(group_key, strings, lang_code=lang_code)
        permissions, permissions_explicit = _infer_permissions(url_name, model, callback)
        entry = {
            'kind': 'item',
            'id': url_name,
            'url_name': url_name,
            'url': url,
            'label': _infer_label(url_name, strings, model=model, callback=callback),
            'icon': _guess_icon(url_name, model=model, callback=callback),
            'permissions': permissions,
            'permissions_explicit': permissions_explicit,
            'group_key': group_key,
            'group_label': group_label,
            'group_icon': _guess_group_icon(group_key),
            'is_system': _is_configurable_system_url(url_name),
        }
        catalog.append(entry)

    catalog.sort(key=lambda entry: (entry['group_label'], entry['label']))
    return catalog


def discover_sidebar_catalog(lang_code=None, include_system_items=False):
    """Return all valid, reversible sidebar candidates."""
    from .utils import get_system_config

    config = get_system_config()
    lang_code = (lang_code or config.get('default_language', 'en')).split('-')[0]
    cache_key = _sidebar_catalog_cache_key(lang_code, include_system_items, config)
    catalog = cache.get(cache_key)
    if catalog is None:
        catalog = _discover_sidebar_catalog_uncached(
            lang_code=lang_code,
            include_system_items=include_system_items,
            config=config,
        )
        cache.set(cache_key, catalog, timeout=SIDEBAR_CACHE_TIMEOUT)
    return copy.deepcopy(catalog)


def build_default_sidebar_config(lang_code=None):
    """Build a useful starter sidebar from discovered routes."""
    catalog = discover_sidebar_catalog(lang_code=lang_code)
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


def _user_has_sidebar_permission(user, permissions, permissions_explicitly_set=False):
    from .utils import user_has_any_permission_tokens

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


def build_sidebar_navigation(lang_code=None, sidebar_override=None, user=None, request_path='', open_accordions=None):
    """
    Transform sidebar JSON config into a single render-ready sidebar tree.
    """
    from .utils import get_system_config

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
                    resolved_item = _resolve_sidebar_item(raw_item, catalog)
                    if resolved_item and _user_has_sidebar_permission(user, resolved_item.get('permissions'), resolved_item.get('permissions_explicit', False)):
                        items.append(resolved_item)
                if items:
                    group_id = entry.get('id') or f"group-{len(render_entries) + 1}"
                    inferred_group_label = next((item.get('group_label') for item in items if item.get('group_label')), None)
                    inferred_group_icon = next((item.get('group_icon') for item in items if item.get('group_icon')), None)
                    render_entries.append({
                        'kind': 'group',
                        'id': group_id,
                        'label': inferred_group_label or entry.get('label') or 'Group',
                        'icon': inferred_group_icon or entry.get('icon') or 'bi-folder2-open',
                        'url': _resolve_group_url(entry),
                        'url_name': entry.get('url_name'),
                        'items': items,
                        'has_active': False,
                        'is_open': False,
                        'raw_name': entry.get('id') or group_id,
                    })
                continue

            resolved = _resolve_sidebar_item(entry, catalog)
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


def _resolve_sidebar_item(entry, catalog):
    item = dict(entry)
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

    item['label'] = item.get('label') or _humanize(item.get('id') or url_name or 'link')
    item['icon'] = item.get('icon') or 'bi-link-45deg'
    item['permissions'] = _normalize_permissions(item.get('permissions') or item.get('permission'))
    item['id'] = item.get('id') or url_name or item.get('url')
    item['url_name'] = url_name or item.get('id') or item.get('url')
    return item


# ── Activity-log model catalog (for the Logging settings grid) ──

def _is_section_model(model):
    """True for auxiliary 'section' content models (is_section=True) — project content,
    not dlux framework machinery."""
    try:
        from .utils.sections import _model_is_section
        return bool(_model_is_section(model))
    except Exception:
        return False


_BASE_LOG_ACTIONS = ('create', 'update', 'delete')


def _model_log_actions(model):
    """Loggable actions for a model: the CRUD base plus any custom actions the model declares
    via `dlux_log_actions = ['download', 'approve', ...]`. Unknown actions are still logged at
    runtime by default; declaring them here surfaces a toggle in the settings grid."""
    actions = list(_BASE_LOG_ACTIONS)
    declared = getattr(model, 'dlux_log_actions', None)
    if isinstance(declared, (list, tuple, set)):
        for raw in declared:
            act = str(raw or '').strip().lower()
            if act and act not in actions:
                actions.append(act)
    return actions


def build_log_model_catalog(lang_code=None):
    """Return loggable concrete models grouped for the Logging settings UI.

    Shape: {'user': [{'key','label','actions'}], 'system': [...]}.
    - Excludes models that never produce meaningful logs (Django framework internals, dlux
      operational/identity/self/dummy models — see is_model_loggable) plus auto/through/proxy.
    - 'user' (project) = non-dlux app models and auxiliary section models. 'system' = the
      synthetic "User accounts" identity entry (users are a core dlux component) plus the
      remaining dlux framework/config models.
    - Each item's `actions` = create/update/delete plus any declared `dlux_log_actions`.
    """
    from .translations import get_strings
    from .utils.activity_log import (
        LOG_IDENTITY_MODEL_KEY,
        is_model_loggable,
        translate_activity_log_model_name,
    )

    strings = get_strings(lang_code) if lang_code else get_strings()
    user_items = []
    system_items = []
    for model in apps.get_models():
        meta = model._meta
        if meta.auto_created or meta.proxy:
            continue
        key = meta.label_lower  # "app_label.model"
        if not is_model_loggable(key, meta.app_label):
            continue
        label = translate_activity_log_model_name(key, strings) or str(meta.verbose_name)
        item = {'key': key, 'label': str(label), 'actions': _model_log_actions(model)}
        is_project = (meta.app_label != 'dlux') or _is_section_model(model)
        (user_items if is_project else system_items).append(item)
    user_items.sort(key=lambda i: i['label'].lower())
    system_items.sort(key=lambda i: i['label'].lower())
    # Pin the unified user-identity (User + Profile) toggle to the top of the system list —
    # user accounts are a core dlux component.
    system_items.insert(0, {
        'key': LOG_IDENTITY_MODEL_KEY,
        'label': str(strings.get('log_model_user_accounts', 'User accounts')),
        'actions': list(_BASE_LOG_ACTIONS),
    })
    return {'user': user_items, 'system': system_items}


def build_user_home_url_options(user, lang_code=None):
    """Reversible pages the given user may access, as a list of {'value', 'label'} for a
    landing-page picker. Permission-filtered with the same rules as the sidebar (superusers
    see all; system items included so profile/options/reports appear when accessible)."""
    catalog = discover_sidebar_catalog(lang_code=lang_code, include_system_items=True)
    seen = set()
    options = []
    for entry in catalog:
        url_name = entry.get('url_name')
        if not url_name:
            continue
        if not _user_has_sidebar_permission(user, entry.get('permissions'), entry.get('permissions_explicit', False)):
            continue
        try:
            resolved = reverse(url_name)
        except NoReverseMatch:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        label = str(entry.get('label') or entry.get('group_label') or url_name).strip()
        options.append({'value': resolved, 'label': label})
    options.sort(key=lambda o: o['label'].lower())
    return options
