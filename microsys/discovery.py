"""
Auto-discovery module for sidebar navigation items.

Scans Django URL patterns for list views and matches them to models
to automatically generate sidebar navigation items.
"""
from django.urls import get_resolver, URLPattern, URLResolver
from django.apps import apps
from django.conf import settings
from difflib import get_close_matches


def get_sidebar_config(lang_code=None):
    """Get sidebar configuration from Django settings with defaults."""
    from .translations import get_strings
    from .utils import get_system_config

    config_dict = get_system_config()
    default_lang = config_dict.get('default_language', 'ar')
    project_overrides = config_dict.get('translations', None)

    if lang_code is None:
        lang_code = default_lang
    strings = get_strings(lang_code, overrides=project_overrides)

    system_group = {
        'name': strings.get('sidebar_system', 'System Management'),
        'icon': 'bi-sliders',
        'url_name': 'sys_dashboard',
        'items': [
            {
                'url_name': 'manage_sections',
                'label': strings.get('manage_sections', 'Section Management'),
                'icon': 'bi-diagram-3',
                'permission': ['is_staff', 'microsys.manage_sections', 'microsys.view_sections'],
            },
            {
                'url_name': 'manage_users',
                'label': strings.get('manage_users', 'User Management'),
                'icon': 'bi-people',
                'permission': 'is_staff',
            },
            {
                'url_name': 'user_activity_log',
                'label': strings.get('activity_log', 'Activity Log'),
                'icon': 'bi-clock-history',
                'permission': 'microsys.view_activity_log',
            },
            {
                'url_name': 'user_profile',
                'label': strings.get('profile', 'Profile'),
                'icon': 'bi-person-badge',
            },
            {
                'url_name': 'options_view',
                'label': strings.get('options_title', 'Options'),
                'icon': 'bi-gear',
            },
        ],
    }
    defaults = {
        'ENABLED': True,
        'URL_PATTERNS': ['list'],
        'EXCLUDE_APPS': ['admin', 'auth', 'contenttypes', 'sessions'],
        'EXCLUDE_MODELS': [],
        'CACHE_TIMEOUT': 3600,
        'DEFAULT_ICON': 'bi-list',
        # Extra items that don't require model matching
        # Format: {'group_name': {'icon': 'bi-gear', 'items': [{'url_name': 'x', 'label': 'X', 'icon': 'bi-x'}]}}
        'EXTRA_ITEMS': {},
        # Built-in system group (appended after user EXTRA_ITEMS when enabled)
        'SYSTEM_GROUP_ENABLED': False,
        'SYSTEM_GROUP': system_group,
        # Default overrides for auto-discovered items
        # Format: {'url_name': {'label': 'X', 'icon': 'bi-x', 'order': 10}}
        'DEFAULT_ITEMS': {},
    }
    user_config = getattr(settings, 'SIDEBAR_AUTO', {})
    config = {**defaults, **user_config}

    # Merge EXTRA_ITEMS so user groups don't overwrite the system group
    merged_extra = {}
    user_extra = user_config.get('EXTRA_ITEMS', {})
    if isinstance(user_extra, dict):
        merged_extra.update(user_extra)

    if config.get('SYSTEM_GROUP_ENABLED', True):
        sys_group = config.get('SYSTEM_GROUP', system_group)
        # Use a stable ASCII key for the group instead of the translated name
        sys_key = 'sidebar_system'
        sys_name = sys_group.get('name', 'إدارة النظام')
        sys_icon = sys_group.get('icon', 'bi-sliders')
        sys_url_name = sys_group.get('url_name')
        sys_items = list(sys_group.get('items', []))

        # We first check if the user overrode the group using the translation key (sidebar_system)
        # We also check the translated name (sys_name) for backwards compatibility
        existing_key = sys_key if sys_key in merged_extra else (sys_name if sys_name in merged_extra else None)

        if existing_key:
            existing = merged_extra[existing_key]
            if not existing.get('icon'):
                existing['icon'] = sys_icon
            if not existing.get('url_name'):
                existing['url_name'] = sys_url_name
            # Ensure label is set
            if not existing.get('label'):
                existing['label'] = sys_name

            existing_items = list(existing.get('items', []))
            existing_urls = {item.get('url_name') for item in existing_items}
            for item in sys_items:
                if item.get('url_name') in existing_urls:
                    continue
                existing_items.append(item)
            existing['items'] = existing_items
            merged_extra[existing_key] = existing
        else:
            merged_extra[sys_key] = {'label': sys_name, 'icon': sys_icon, 'url_name': sys_url_name, 'items': sys_items}

    config['EXTRA_ITEMS'] = merged_extra
    return config



def discover_list_urls(lang_code=None):
    """
    Scan all URL patterns for names containing configured keywords.
    Match them to Django models and extract verbose_name_plural.
    
    Returns:
        List of sidebar item dictionaries sorted by order.
    """
    config = get_sidebar_config(lang_code=lang_code)
    
    if not config['ENABLED']:
        return []
    
    resolver = get_resolver()
    items = []
    
    for pattern in _iterate_patterns(resolver.url_patterns):
        url_name = getattr(pattern, 'name', '') or ''
        
        # Check if URL name contains any of the configured patterns
        matched_keyword = None
        for kw in config['URL_PATTERNS']:
            if kw in url_name.lower():
                matched_keyword = kw
                break
        
        if matched_keyword:
            # Extract model hint (e.g., 'decree' from 'decree_list')
            model_hint = url_name
            for kw in config['URL_PATTERNS']:
                model_hint = model_hint.replace(f'_{kw}', '').replace(f'-{kw}', '').replace(kw, '')
            
            model_hint = model_hint.strip('_-')
            
            # Try to find model - first with stripped hint, then with keyword itself
            model = None
            if model_hint:
                model = _find_model(model_hint, config)
            
            # If no model found and keyword looks like it could be a model name, try that
            if not model and matched_keyword not in ['list', 'index', 'view', 'page']:
                model = _find_model(matched_keyword, config)
            
            if model:
                # Check exclusions
                if model._meta.app_label in config['EXCLUDE_APPS']:
                    continue
                if f"{model._meta.app_label}.{model.__name__}" in config['EXCLUDE_MODELS']:
                    continue
                
                items.append({
                    'url_name': url_name,
                    'label': getattr(model._meta, 'sidebar_label', None) or str(model._meta.verbose_name_plural),
                    'icon': getattr(model._meta, 'sidebar_icon', config['DEFAULT_ICON']),
                    'order': getattr(model._meta, 'sidebar_order', 100),
                    'app_label': model._meta.app_label,
                    'model_name': model._meta.model_name,
                    'permissions': [f'{model._meta.app_label}.view_{model._meta.model_name}'],
                })

            # Override with DEFAULT_ITEMS if present
            default_items = config.get('DEFAULT_ITEMS', {})
            if url_name in default_items:
                item_config = default_items[url_name]
                # Update last added item
                if items:
                    item = items[-1]
                    if 'label' in item_config:
                        item['label'] = item_config['label']
                    if 'icon' in item_config:
                        item['icon'] = item_config['icon']
                    if 'order' in item_config:
                        item['order'] = item_config['order']
    
    return sorted(items, key=lambda x: (x['order'], x['label']))


def _iterate_patterns(patterns, prefix=''):
    """Recursively iterate through URL patterns."""
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            yield from _iterate_patterns(pattern.url_patterns, prefix + str(pattern.pattern))
        elif isinstance(pattern, URLPattern):
            yield pattern


def _find_model(hint, config):
    """
    Find model by name using exact and fuzzy matching.
    
    Args:
        hint: The model name hint extracted from URL
        config: Sidebar configuration dictionary
        
    Returns:
        Model class or None if not found
    """
    all_models = apps.get_models()
    
    # Build lookup excluding configured apps
    model_names = {}
    for m in all_models:
        if m._meta.app_label not in config['EXCLUDE_APPS']:
            model_names[m.__name__.lower()] = m
    
    hint_lower = hint.lower()
    
    # Exact match first
    if hint_lower in model_names:
        return model_names[hint_lower]
    
    # Handle common pluralization (simple 's' suffix)
    if hint_lower.endswith('s') and hint_lower[:-1] in model_names:
        return model_names[hint_lower[:-1]]
    
    # Fuzzy match as fallback
    matches = get_close_matches(hint_lower, model_names.keys(), n=1, cutoff=0.8)
    return model_names[matches[0]] if matches else None
