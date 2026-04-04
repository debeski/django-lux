from .utils import has_section_models, is_scope_enabled
from django.conf import settings
import hashlib
import json
from django.urls import reverse, NoReverseMatch
from .discovery import SYSTEM_ROUTE_META, build_sidebar_navigation

# Helper functions for Sidebar - KEPT PRIVATE
def _get_config_hash(config):
    """Generate a hash of the config for cache key."""
    # Exclude EXTRA_ITEMS from hash since they're processed separately
    config_copy = {k: v for k, v in config.items() if k != 'EXTRA_ITEMS'}
    config_str = json.dumps(config_copy, sort_keys=True)
    return hashlib.md5(config_str.encode()).hexdigest()[:8]

def _process_extra_items(config, request, user_prefs=None, ms_trans=None):
    """
    Process EXTRA_ITEMS config into sidebar-ready format.
    
    Returns dict of groups, each with icon and list of items with resolved URLs.
    """
    from django.utils.text import slugify
    if user_prefs is None:
        user_prefs = {}
    if ms_trans is None:
        ms_trans = {}
    open_accordions = user_prefs.get('open_accordions', [])

    extra_items = config.get('EXTRA_ITEMS', {})
    processed_groups = {}
    
    for group_name, group_config in extra_items.items():
        # Prefer the explicitly provided 'label' in config, then translation, then group_name itself
        translated_group_name = group_config.get('label', ms_trans.get(group_name, group_name))
        group_icon = group_config.get('icon', 'bi-gear')
        
        group_url_name = group_config.get('url_name', '')
        group_url = '#'
        try:
            if group_url_name:
                group_url = reverse(group_url_name)
        except NoReverseMatch:
            import logging
            logging.getLogger('microsys').warning(
                f"SIDEBAR_AUTO EXTRA_ITEMS: Could not resolve url_name '{group_url_name}' "
                f"for group '{group_name}'. Check the URL name exists and includes the correct namespace."
            )
            
        items = []
        
        for item in group_config.get('items', []):
            url_name = item.get('url_name', '')
            
            # Check permission if specified (supports string or list/tuple/set)
            permission = item.get('permission')
            if permission:
                perms = permission if isinstance(permission, (list, tuple, set)) else [permission]
                allowed = False
                for perm in perms:
                    if perm == 'is_staff':
                        allowed = request.user.is_staff
                    elif perm == 'is_superuser':
                        allowed = request.user.is_superuser
                    else:
                        allowed = request.user.has_perm(perm)
                    if allowed:
                        break
                if not allowed:
                    continue
            
            # Resolve URL
            try:
                url = reverse(url_name)
                active = request.path == url or request.path.startswith(url.rstrip('/') + '/')
            except NoReverseMatch:
                url = '#'
                active = False
            
            raw_label = item.get('label', url_name)
            translated_label = ms_trans.get(raw_label, raw_label)
            
            items.append({
                'url_name': url_name,
                'url': url,
                'label': translated_label,
                'icon': item.get('icon', 'bi-link'),
                'active': active,
            })
        
        if items:  # Only add group if it has visible items
            group_id = f"extraGroup-{slugify(group_name)}"
            has_active = any(item['active'] for item in items)
            is_open = (group_id in open_accordions) or has_active
            
            # Auto-expand if the group's dashboard URL is currently active
            # (Behavior removed: we now rely solely on 'active' inner items or explicit user 'open_accordions' state)
            processed_groups[group_name] = {  # Use internal group_name as key for easier sorting logic
                'label': translated_group_name,
                'icon': group_icon,
                'url': group_url,
                'items': items,
                'has_active': any(item['active'] for item in items),
                'is_open': is_open,
                'id': group_id,
                'raw_name': group_name, # Keep for reordering lookups
            }
    
    return processed_groups

def _sort_sidebar(items, order, id_field='url_name'):
    """Helper to sort sidebar items list based on a list of IDs."""
    if not order or not items:
        return items
    
    # items might be a list or a list-like dict values
    items_list = list(items)
    
    item_map = {item.get(id_field): item for item in items_list if item.get(id_field)}
    sorted_items = []
    
    for id_val in order:
        if id_val in item_map:
            sorted_items.append(item_map.pop(id_val))
    
    # Append any remaining items (newly discovered, etc.)
    sorted_items.extend(item_map.values())
    return sorted_items

def _user_has_sidebar_permission(user, permissions):
    permissions = permissions or []
    if not permissions:
        return True
    if getattr(user, 'is_superuser', False):
        return True

    for permission in permissions:
        if permission == 'is_staff' and getattr(user, 'is_staff', False):
            return True
        if permission == 'is_superuser' and getattr(user, 'is_superuser', False):
            return True
        if permission not in ['is_staff', 'is_superuser'] and user.has_perm(permission):
            return True
    return False

def microsys_context(request):
    """
    Unified context processor for the entire Microsys package.
    Combines:
    1. Branding Configuration (APP_CONFIG)
    2. Scope Settings
    3. Sidebar Navigation items
    4. Theme Settings
    """
    context = {}

    # 1. Branding / App Config
    from .utils import get_system_config
    final_config = get_system_config()

    # 4. Language / i18n (resolved BEFORE branding overrides so we know current_lang)
    from .translations import get_strings

    # Available languages from config (default: English and Arabic)
    default_languages = {
        'ar': {'name': 'العربية', 'dir': 'rtl', 'flag': '🇱🇾'},
        'en': {'name': 'English', 'dir': 'ltr', 'flag': '🇬🇧'},
    }
    languages = final_config.get('languages', default_languages)

    # Resolve active language: user pref → session → config default → 'en'
    default_lang = final_config.get('default_language', 'en')
    
    current_lang = None
    # 1. User Preference
    if request.user.is_authenticated and hasattr(request.user, 'profile'):
        user_prefs = request.user.profile.preferences or {}
        if 'language' in user_prefs:
            current_lang = user_prefs.get('language')
    else:
        user_prefs = {}
    
    # 2. Session Preference (for anonymous users or overrides)
    if not current_lang:
        current_lang = request.session.get('lang')
        
    # 3. Default
    if not current_lang:
        current_lang = default_lang

    # Validate the resolved language exists in available languages
    if current_lang not in languages:
        current_lang = default_lang if default_lang in languages else 'en'

    # DYNAMIC BRANDING: Look for [key]_[lang] overrides in final_config
    # (e.g. name_en, logo_ar) and promote them to the base keys
    for key in list(final_config.keys()):
        lang_suffix = f"_{current_lang}"
        if key.endswith(lang_suffix):
            base_key = key[:-len(lang_suffix)]
            final_config[base_key] = final_config[key]

    context['APP_CONFIG'] = final_config


    # 2. Scope Settings
    # We add this boolean so templates know if the scope feature is ON globally
    context['scope_settings'] = {'is_enabled': is_scope_enabled()}

    # 3. User Preferences (for JS injection & server-side logic)
    user_prefs = {}
    if request.user.is_authenticated and hasattr(request.user, 'profile'):
        user_prefs = request.user.profile.preferences or {}
    if not isinstance(user_prefs, dict):
        user_prefs = {}
    default_theme = final_config.get('default_theme', 'light')
    allowed_themes = {'light', 'blue', 'gold', 'green', 'red', 'dark'}
    if user_prefs.get('theme') not in allowed_themes:
        user_prefs = {**user_prefs, 'theme': default_theme}
    context['user_preferences'] = user_prefs # Injected for JS use

    lang_config = languages.get(current_lang, {'name': 'English', 'dir': 'ltr', 'flag': '🇬🇧'})
    current_dir = lang_config.get('dir', 'ltr')

    # Get translated strings (with project-level overrides from config)
    project_overrides = final_config.get('translations', None)
    ms_trans = get_strings(current_lang, overrides=project_overrides)

    context['CURRENT_LANG'] = current_lang
    context['CURRENT_DIR'] = current_dir
    context['LANGUAGES'] = languages
    context['LANG_CONFIG'] = lang_config
    context['MS_TRANS'] = ms_trans

    # 5. Setup State
    system_setup_required = bool(
        request.user.is_authenticated and
        request.user.is_superuser and
        not final_config.get('is_configured', False)
    )
    context['SYSTEM_SETUP_REQUIRED'] = system_setup_required
    context['SYSTEM_SETUP_URL'] = reverse('system_setup')

    # 6. Sidebar Context (single tree model shared with setup builder)
    sidebar_tree_pref = user_prefs.get('sidebar_tree', {})
    if not isinstance(sidebar_tree_pref, dict):
        sidebar_tree_pref = {}

    navigation = build_sidebar_navigation(
        lang_code=current_lang,
        sidebar_override=sidebar_tree_pref,
        user=request.user,
        request_path=request.path,
        open_accordions=user_prefs.get('open_accordions', []),
    )

    context['sidebar_entries'] = navigation.get('entries', [])
    context['sidebar_tree_state'] = navigation.get('entries', [])
    context['sidebar_auto_items'] = navigation.get('auto_items', [])
    context['sidebar_extra_groups'] = navigation.get('extra_groups', [])
    context['sidebar_has_sections_manager'] = bool(
        request.user.is_authenticated and
        has_section_models() and
        _user_has_sidebar_permission(
            request.user,
            SYSTEM_ROUTE_META.get('manage_sections', {}).get('permissions', []),
        )
    )

    # 7. Sidebar State (Collapsed/Expanded)
    # Prioritize DB preference if available, else session, else default
    session_collapsed = request.session.get('sidebarCollapsed', False)
    db_collapsed = user_prefs.get('sidebar_collapsed', session_collapsed)
    context['sidebar_collapsed'] = db_collapsed

    return context

def clear_sidebar_cache():
    """
    Clear the sidebar items cache.
    Call this when models or URLs change and sidebar needs refresh.
    """
    # Note: We can't easily clear specific hash keys, so we might need a more robust clearing strategy
    # or just rely on timeout. For now, this function is a placeholder or partial implementation.
    # To truly clear, we'd need to track keys or use a specific prefix clear if supported by backend.
    # Simpler: Just rely on short timeout during dev.
    pass
