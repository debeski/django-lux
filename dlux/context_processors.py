from urllib.parse import urlsplit

from . import __version__
from .system.constants import (
    DEFAULT_TABLE_DENSITY,
    TABLE_DENSITY_CHOICES,
    TABLE_DENSITY_VALUES,
)
from .navbar import resolve_navbar_mode, strip_navbar_mode_preference
from .utils import (
    get_effective_allowed_themes,
    get_user_management_tier_state_for_user,
    has_section_models,
    is_scope_enabled,
    normalize_navbar_config,
    normalize_sidebar_behavior,
    normalize_titlebar_actions_order,
    resolve_sidebar_collapsed_preference,
    resolve_sidebar_density_preference,
    resolve_user_theme_preference,
    user_can_view_activity_log,
    user_can_view_reports,
    user_can_view_user_directory,
    user_has_any_permission_tokens,
    user_has_section_view_permission,
)
from django.conf import settings
import hashlib
import json
from django.urls import reverse, NoReverseMatch
from .discovery import SYSTEM_ROUTE_META, build_sidebar_navigation
from .themes import get_theme_names, get_theme_options


def _normalize_runtime_path(value):
    raw_value = str(value or '').strip()
    if not raw_value:
        return ''
    parsed = urlsplit(raw_value)
    path = str(parsed.path or raw_value).strip()
    if not path.startswith('/'):
        return ''
    return path if path == '/' else path.rstrip('/')


def _should_hide_titlebar_for_public_index(request, final_config, titlebar_config):
    user = getattr(request, 'user', None)
    if not titlebar_config.get('hide_on_public_unauthenticated_index', False):
        return False
    if not final_config.get('public_root', False):
        return False
    if user and getattr(user, 'is_authenticated', False):
        return False

    current_path = _normalize_runtime_path(getattr(request, 'path', ''))
    if not current_path:
        return False

    public_paths = {'/'}
    anonymous_public_path = final_config.get('public_root_url') if final_config.get('public_root_split_enabled', False) else final_config.get('home_url')
    target_path = _normalize_runtime_path(anonymous_public_path)
    if target_path:
        public_paths.add(target_path)
    return current_path in public_paths


def _reverse_or_empty(url_name):
    try:
        return reverse(url_name)
    except NoReverseMatch:
        return ''


def _build_titlebar_actions(request, context, final_config, dlux_strings):
    titlebar_config = context.get('titlebar') or {}
    action_order = normalize_titlebar_actions_order(titlebar_config.get('actions_order'))
    user = getattr(request, 'user', None)
    resolver_match = getattr(request, 'resolver_match', None)
    current_url_name = getattr(resolver_match, 'url_name', '')
    available_actions = {}

    if user and getattr(user, 'is_authenticated', False):
        if context.get('dlux_notifications_enabled'):
            available_actions['notifications'] = {
                'key': 'notifications',
                'kind': 'notifications',
                'label': dlux_strings.get('notifications', 'Notifications'),
                'icon': 'bi-bell-fill',
            }
        if titlebar_config.get('show_home_button', True):
            available_actions['home'] = {
                'key': 'home',
                'kind': 'link',
                'label': dlux_strings.get('btn_home', 'Home'),
                'icon': 'bi-house-fill',
                'url': final_config.get('home_url') or '/',
            }

        profile_url = _reverse_or_empty('user_profile')
        if profile_url:
            available_actions['profile'] = {
                'key': 'profile',
                'kind': 'link',
                'label': dlux_strings.get('profile', 'Profile'),
                'icon': 'bi-person-bounding-box',
                'url': profile_url,
            }

        available_actions['help'] = {
            'key': 'help',
            'kind': 'help',
            'label': dlux_strings.get('help', 'Help'),
            'icon': 'bi-question-circle-fill',
        }

        users_url = _reverse_or_empty('manage_users')
        if context.get('can_view_user_directory') and users_url:
            available_actions['users'] = {
                'key': 'users',
                'kind': 'link',
                'label': dlux_strings.get('manage_users', 'Manage users'),
                'icon': 'bi-people-fill',
                'url': users_url,
            }

        activity_url = _reverse_or_empty('user_activity_log')
        if context.get('can_view_activity_log') and activity_url:
            available_actions['activity'] = {
                'key': 'activity',
                'kind': 'link',
                'label': dlux_strings.get('activity_log', 'Activity log'),
                'icon': 'bi-clock-history',
                'url': activity_url,
            }

        reports_url = _reverse_or_empty('reports_overview')
        if context.get('can_view_reports') and reports_url:
            available_actions['reports'] = {
                'key': 'reports',
                'kind': 'link',
                'label': dlux_strings.get('reports_title', 'Reports'),
                'icon': 'bi-bar-chart-fill',
                'url': reports_url,
            }

        settings_url = _reverse_or_empty('options_view')
        if settings_url:
            available_actions['settings'] = {
                'key': 'settings',
                'kind': 'link',
                'label': dlux_strings.get('options_title', 'Options'),
                'icon': 'bi-gear-fill',
                'url': settings_url,
            }

        logout_url = _reverse_or_empty('logout')
        if logout_url:
            available_actions['auth'] = {
                'key': 'auth',
                'kind': 'logout',
                'label': dlux_strings.get('logout', 'Logout'),
                'icon': 'bi-box-arrow-right',
                'url': logout_url,
            }
    elif current_url_name != 'login':
        login_url = _reverse_or_empty('login')
        if login_url:
            available_actions['auth'] = {
                'key': 'auth',
                'kind': 'link',
                'label': dlux_strings.get('login', 'Login'),
                'icon': 'bi-person-lock',
                'url': login_url,
            }

    return [available_actions[key] for key in action_order if key in available_actions]

# Helper functions for Sidebar - KEPT PRIVATE
def _get_config_hash(config):
    """Generate a hash of the config for cache key."""
    # Exclude EXTRA_ITEMS from hash since they're processed separately
    config_copy = {k: v for k, v in config.items() if k != 'EXTRA_ITEMS'}
    config_str = json.dumps(config_copy, sort_keys=True)
    return hashlib.md5(config_str.encode()).hexdigest()[:8]

def _process_extra_items(config, request, user_prefs=None, dlux_strings=None):
    """
    Process EXTRA_ITEMS config into sidebar-ready format.
    
    Returns dict of groups, each with icon and list of items with resolved URLs.
    """
    from django.utils.text import slugify
    if user_prefs is None:
        user_prefs = {}
    if dlux_strings is None:
        dlux_strings = {}
    open_accordions = user_prefs.get('open_accordions', [])

    extra_items = config.get('EXTRA_ITEMS', {})
    processed_groups = {}
    
    for group_name, group_config in extra_items.items():
        # Prefer the explicitly provided 'label' in config, then translation, then group_name itself
        translated_group_name = group_config.get('label', dlux_strings.get(group_name, group_name))
        group_icon = group_config.get('icon', 'bi-gear')
        
        group_url_name = group_config.get('url_name', '')
        group_url = '#'
        try:
            if group_url_name:
                group_url = reverse(group_url_name)
        except NoReverseMatch:
            import logging
            logging.getLogger('dlux').warning(
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
                if not user_has_any_permission_tokens(request.user, perms):
                    continue
            
            # Resolve URL
            try:
                url = reverse(url_name)
                active = request.path == url or request.path.startswith(url.rstrip('/') + '/')
            except NoReverseMatch:
                url = '#'
                active = False
            
            raw_label = item.get('label', url_name)
            translated_label = dlux_strings.get(raw_label, raw_label)
            
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

def dlux_context(request):
    """
    Unified context processor for the entire Dlux package.
    Combines:
    1. Branding Configuration (APP_CONFIG)
    2. Scope Settings
    3. Sidebar Navigation items
    4. Theme Settings
    """
    context = {}

    # 1. Branding / App Config
    from .utils import build_config_groups, get_system_config, normalize_allowed_fonts
    final_config = get_system_config()
    current_route_name = getattr(getattr(request, 'resolver_match', None), 'url_name', '')

    # 4. Language / i18n (resolved BEFORE branding overrides so we know current_lang)
    from .translations import get_strings

    # Available languages from config (default: English and Arabic)
    languages = final_config.get('localization', {}).get('languages') or final_config.get('languages', {})

    # Resolve active language: preview session → user pref/session override → config default → 'en'
    default_lang = final_config.get('localization', {}).get('default_language') or final_config.get('default_language', 'en')
    allow_user_language_override = bool(
        final_config.get('localization', {}).get(
            'allow_user_language_override',
            final_config.get('allow_user_language_override', True),
        )
    )
    
    current_lang = None
    preview_lang = request.session.get('lang')
    if request.session.get('dlux_force_language_preview') and preview_lang in languages:
        current_lang = preview_lang

    setup_lang = request.session.get('dlux_initial_setup_language')
    if (
        not current_lang
        and current_route_name == 'system_setup'
        and not final_config.get('is_configured', False)
        and setup_lang in languages
    ):
        current_lang = setup_lang

    # 1. User Preference
    if not current_lang and request.user.is_authenticated and hasattr(request.user, 'profile'):
        user_prefs = request.user.profile.preferences or {}
        if not allow_user_language_override:
            user_prefs = {key: value for key, value in user_prefs.items() if key != 'language'}
        elif 'language' in user_prefs:
            current_lang = user_prefs.get('language')
    else:
        user_prefs = {}
    
    # 2. Session Preference (for anonymous users or overrides)
    if not current_lang and allow_user_language_override:
        current_lang = request.session.get('lang')
        
    # 3. Default
    if not current_lang:
        current_lang = default_lang

    # Validate the resolved language exists in available languages
    if current_lang not in languages:
        current_lang = default_lang if default_lang in languages else 'en'

    final_config.update(build_config_groups(final_config, current_lang))

    context['APP_CONFIG'] = final_config
    context['DLUX_VERSION'] = __version__


    # 2. Scope Settings
    # We add this boolean so templates know if the scope feature is ON globally
    context['scope_settings'] = {'is_enabled': is_scope_enabled()}
    context['can_view_user_directory'] = user_can_view_user_directory(request.user)
    context['can_view_activity_log'] = user_can_view_activity_log(request.user)
    context['can_view_reports'] = user_can_view_reports(request.user)
    context['can_view_sections'] = user_has_section_view_permission(request.user)
    context['current_user_management_tier'] = get_user_management_tier_state_for_user(request.user)

    # 3. User Preferences (for JS injection & server-side logic)
    user_prefs = {}
    if request.user.is_authenticated and hasattr(request.user, 'profile'):
        user_prefs = request.user.profile.preferences or {}
    if not isinstance(user_prefs, dict):
        user_prefs = {}
    if not allow_user_language_override and not request.session.get('dlux_force_language_preview'):
        user_prefs = {key: value for key, value in user_prefs.items() if key != 'language'}
    user_prefs = resolve_user_theme_preference(user_prefs, final_config)
    navbar_runtime_config = normalize_navbar_config(final_config.get('navbar', {}))
    user_prefs = strip_navbar_mode_preference(user_prefs, navbar_runtime_config)
    default_table_density = final_config.get('default_table_density', DEFAULT_TABLE_DENSITY)
    if default_table_density not in TABLE_DENSITY_VALUES:
        default_table_density = DEFAULT_TABLE_DENSITY
    if user_prefs.get('table_density') not in TABLE_DENSITY_VALUES:
        user_prefs = {**user_prefs, 'table_density': default_table_density}
    user_prefs = resolve_sidebar_density_preference(user_prefs, final_config)
    context['user_preferences'] = user_prefs # Injected for JS use

    lang_config = languages.get(current_lang, {'name': 'English', 'dir': 'ltr', 'flag': '🇬🇧'})
    current_dir = lang_config.get('dir', 'ltr')

    # Get translated strings (with project-level overrides from config)
    project_overrides = final_config.get('localization', {}).get('translations', final_config.get('translations', None))
    dlux_strings = get_strings(current_lang, overrides=project_overrides)
    allowed_theme_names = list(get_effective_allowed_themes(final_config))
    context['DLUX_THEME_NAMES'] = allowed_theme_names
    context['DLUX_THEMES'] = get_theme_options(dlux_strings, allowed_themes=allowed_theme_names)
    context['DLUX_TABLE_DENSITIES'] = list(TABLE_DENSITY_CHOICES)

    context['CURRENT_LANG'] = current_lang
    context['CURRENT_DIR'] = current_dir
    context['LANGUAGES'] = languages
    context['LANG_CONFIG'] = lang_config
    context['DLUX_STRINGS'] = dlux_strings

    # 5. Setup State
    system_setup_required = bool(
        request.user.is_authenticated and
        request.user.is_superuser and
        not final_config.get('is_configured', False)
    )
    context['SYSTEM_SETUP_REQUIRED'] = system_setup_required
    context['SYSTEM_SETUP_URL'] = reverse('system_setup')

    # Initial User Setup (first-login onboarding modal): a non-superuser who hasn't completed
    # it yet, when onboarding is enabled and we're not mid system-setup. Superusers own the
    # system (and run the system-setup wizard), so they are excluded from this user-facing nudge.
    profile_config = final_config.get('profile_config') or {}
    profile_obj = getattr(request.user, 'profile', None) if request.user.is_authenticated else None
    profile_preferences = getattr(profile_obj, 'preferences', {}) if profile_obj is not None else {}
    force_password_change_required = bool(
        isinstance(profile_preferences, dict)
        and profile_preferences.get('force_password_change')
    )
    context['DLUX_SHOW_INITIAL_USER_SETUP'] = bool(
        profile_obj is not None
        and not getattr(request.user, 'is_superuser', False)
        and not getattr(profile_obj, 'is_configured', False)
        and not force_password_change_required
        and profile_config.get('onboarding_enabled', True)
        and not system_setup_required
    )

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
    sidebar_runtime_config = normalize_sidebar_behavior(final_config.get('sidebar', {}))
    sidebar_enabled = bool(sidebar_runtime_config.get('enabled', True))
    context['sidebar_enabled'] = sidebar_enabled
    context['sidebar_theme_picker_enabled'] = bool(
        sidebar_enabled and final_config.get('allow_user_theme_override', True) and len(allowed_theme_names) > 1
    )
    context['language_picker_enabled'] = bool(
        final_config.get('allow_user_language_override', True) and len(languages) > 1
    )
    context['sidebar_density_picker_enabled'] = bool(sidebar_enabled and sidebar_runtime_config.get('allow_user_density', True))
    context['sidebar_reorder_enabled'] = bool(sidebar_enabled and sidebar_runtime_config.get('enable_reorder', True))
    context['sidebar_has_sections_manager'] = bool(
        sidebar_enabled and
        request.user.is_authenticated and
        has_section_models() and
        context['can_view_sections']
    )
    context['sidebar_toolbar_enabled'] = bool(sidebar_runtime_config.get('show_toolbar', True)) and any([
        context['sidebar_theme_picker_enabled'],
        context['sidebar_density_picker_enabled'],
        context['sidebar_reorder_enabled'],
        context['sidebar_has_sections_manager'],
    ])
    navbar_enabled = bool(navbar_runtime_config.get('enabled', False)) and current_route_name != 'system_setup'
    context['navbar_enabled'] = navbar_enabled
    context['navbar_mode'] = resolve_navbar_mode(user_prefs, navbar_runtime_config)
    context['navbar'] = {
        **navbar_runtime_config,
        'enabled': navbar_enabled,
        'mode': context['navbar_mode'],
    }

    # 7. Sidebar State (Collapsed/Expanded)
    # Prioritize DB preference if available, else session, else default
    session_collapsed = request.session.get('sidebarCollapsed', False)
    db_collapsed, user_prefs = resolve_sidebar_collapsed_preference(user_prefs, final_config, session_collapsed=session_collapsed)
    context['sidebar_collapsed'] = db_collapsed
    context['sidebar_density'] = user_prefs.get('sidebar_density', sidebar_runtime_config.get('density', 'balanced'))
    context['user_preferences'] = user_prefs
    context['config'] = final_config
    context['user'] = request.user
    context['languages'] = languages
    context['translations'] = dlux_strings
    context['sidebar'] = {
        **sidebar_runtime_config,
        'entries': context['sidebar_entries'],
        'auto_items': context['sidebar_auto_items'],
        'extra_groups': context['sidebar_extra_groups'],
    }
    context['titlebar'] = final_config.get('appearance', {}).get('titlebar', final_config.get('titlebar', {}))
    try:
        from .notifications import get_flash_notifications, get_notification_context

        notification_context = get_notification_context(request)
        context['dlux_notification_config'] = notification_context.get('config', final_config.get('notifications', {}))
        context['dlux_notifications'] = notification_context.get('items', [])
        context['dlux_notifications_enabled'] = notification_context.get('enabled', False)
        context['dlux_unread_notifications_count'] = notification_context.get('unread_count', 0)
        context['dlux_unread_notifications_level'] = notification_context.get('unread_level', '')
        context['dlux_flash_notifications'] = get_flash_notifications(request)
    except Exception:
        context['dlux_notification_config'] = final_config.get('notifications', {})
        context['dlux_notifications'] = []
        context['dlux_notifications_enabled'] = False
        context['dlux_unread_notifications_count'] = 0
        context['dlux_unread_notifications_level'] = ''
        context['dlux_flash_notifications'] = []
    context['titlebar_actions'] = _build_titlebar_actions(request, context, final_config, dlux_strings)
    context['hide_titlebar_for_public_index'] = _should_hide_titlebar_for_public_index(
        request,
        final_config,
        context['titlebar'],
    )
    # 8. Font Resolution
    from .fonts import (
        DEFAULT_FONT_SLUG,
        generate_font_face_css,
        get_builtin_fonts,
        get_default_font_family,
        get_font_by_slug,
    )
    builtin_fonts = get_builtin_fonts()
    allowed_fonts = normalize_allowed_fonts(final_config.get('allowed_fonts'))
    context['font_face_css'] = generate_font_face_css(allowed_fonts)
    context['default_font_family'] = get_default_font_family()
    context['font_families'] = {
        font['slug']: font['family']
        for font in builtin_fonts
    }
    context['option_fonts'] = [font for font in builtin_fonts if font.get('slug') in allowed_fonts]
    
    allow_user_font_override = bool(final_config.get('allow_user_font_override', True))
    default_fonts_by_lang = final_config.get('default_fonts', {})
    
    active_font = None
    if allow_user_font_override:
        active_font = user_prefs.get('font')
    
    if not active_font or active_font not in allowed_fonts:
        active_font = default_fonts_by_lang.get(current_lang)
    
    if not active_font or active_font not in allowed_fonts:
        active_font = DEFAULT_FONT_SLUG

    # Ensure active_font is valid, else hard fallback to cairo
    if active_font not in allowed_fonts and allowed_fonts:
        active_font = allowed_fonts[0]
    elif not active_font:
        active_font = DEFAULT_FONT_SLUG

    active_font_config = get_font_by_slug(active_font) if active_font else None
    context['active_font'] = active_font
    context['active_font_family'] = (
        active_font_config.get('family')
        if active_font_config
        else get_default_font_family()
    )
    context['font_picker_enabled'] = bool(allow_user_font_override and len(allowed_fonts) > 1)
    
    return context

def clear_sidebar_cache():
    """
    Clear the sidebar items cache.
    Call this when models or URLs change and sidebar needs refresh.
    """
    from .discovery import bump_sidebar_cache_version

    bump_sidebar_cache_version()
