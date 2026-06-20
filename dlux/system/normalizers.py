"""Canonical normalizers for Dlux system settings.

Keep this module free of model/form/admin/view/translations imports. It may use
small leaf registries such as themes/fonts lazily when validating choices.
"""

import re
from copy import deepcopy

from .constants import (
    CLIENT_IP_MODE_CUSTOM,
    CLIENT_IP_MODE_VALUES,
    DEFAULT_LANGUAGE_CATALOG,
    DEFAULT_NAVBAR_MODE,
    DEFAULT_SECURITY_NUDGE,
    DEFAULT_SIDEBAR_COLLAPSE_MODE,
    DEFAULT_SIDEBAR_DENSITY,
    DEFAULT_TABLE_DENSITY,
    EMAIL_CONFIG_SECRET_STORAGES,
    EMAIL_CONFIG_TRANSPORTS,
    LOGIN_STYLE_VALUES,
    NAVBAR_MODE_VALUES,
    NOTIFICATION_FLASH_POSITIONS,
    NOTIFICATION_FLASH_SIZES,
    NOTIFICATION_FLASH_TEXT_SIZES,
    NOTIFICATION_UPDATE_MODES,
    REGISTRATION_ACTIVATION_AUTO_LOGIN,
    REGISTRATION_ACTIVATION_VALUES,
    SECURITY_NUDGE_VALUES,
    SIDEBAR_COLLAPSE_MODE_VALUES,
    SIDEBAR_DENSITY_VALUES,
    TABLE_DENSITY_VALUES,
    TITLEBAR_ACTIONS_ORDER,
    TITLEBAR_ACTIONS_ORDER_VALUES,
    TITLEBAR_ALIGN_VALUES,
    TITLEBAR_HEIGHT_VALUES,
    TITLEBAR_HOME_SHAPE_VALUES,
    TITLEBAR_LOGO_TREATMENT_SHAPE_VALUES,
    TITLEBAR_LOGO_TREATMENT_VALUES,
    TITLEBAR_SIZE_VALUES,
    TITLEBAR_SURFACE_VALUES,
    TITLEBAR_USER_HUB_STYLE_VALUES,
)
from .defaults import (
    default_auth_config,
    default_client_ip_config,
    default_email_config,
    default_extra_config,
    default_language_config,
    default_layout_config,
    default_log_config,
    default_login_config,
    default_navbar_config,
    default_notification_config,
    default_profile_config,
    default_public_root_config,
    default_registration_config,
    default_sidebar_config,
    default_theme_config,
    default_titlebar_config,
    default_typography_config,
)


def _coerce_import_bool(value):
    if isinstance(value, str):
        return value.strip().lower() in {'1', 'true', 'yes', 'on'}
    return bool(value)


def _to_int(value, default, *, min_value=None, max_value=None):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    if min_value is not None:
        parsed = max(min_value, parsed)
    if max_value is not None:
        parsed = min(max_value, parsed)
    return parsed


def _to_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {'1', 'true', 'yes', 'y', 'on'}:
            return True
        if normalized in {'0', 'false', 'no', 'n', 'off'}:
            return False
    return bool(value)


def _normalize_language_code(code):
    normalized = str(code or '').strip().lower().replace('_', '-')
    if not normalized:
        return ''
    if not re.match(r'^[a-z]{2,3}(?:-[a-z0-9]{2,8})?$', normalized):
        return ''
    return normalized


def normalize_language_catalog(*layers):
    merged = deepcopy(DEFAULT_LANGUAGE_CATALOG)
    for layer in layers:
        if not isinstance(layer, dict):
            continue
        for raw_code, payload in layer.items():
            code = _normalize_language_code(raw_code)
            if not code:
                continue
            if isinstance(payload, dict):
                name = str(payload.get('name') or code).strip() or code
                direction = str(payload.get('dir') or '').strip().lower()
                if direction not in {'ltr', 'rtl'}:
                    direction = 'rtl' if code.startswith(('ar', 'fa', 'he', 'ur')) else 'ltr'
                merged[code] = {
                    'name': name,
                    'dir': direction,
                    'flag': str(payload.get('flag') or '').strip(),
                }
            elif payload:
                merged[code] = {
                    'name': str(payload).strip() or code,
                    'dir': 'rtl' if code.startswith(('ar', 'fa', 'he', 'ur')) else 'ltr',
                    'flag': '',
                }
    return merged


def normalize_allowed_fonts(allowed_fonts=None):
    from ..fonts import get_builtin_fonts

    available = {f['slug'] for f in get_builtin_fonts()}
    if allowed_fonts is None:
        return list(available)

    normalized = []
    if isinstance(allowed_fonts, (list, tuple, set)):
        for font in allowed_fonts:
            if font in available and font not in normalized:
                normalized.append(font)

    return normalized or list(available)


def normalize_default_fonts(value=None, *, allowed_fonts=None):
    from ..fonts import get_builtin_fonts

    if not isinstance(value, dict):
        return {}
    allowed = set(normalize_allowed_fonts(allowed_fonts))
    if not allowed:
        allowed = {font['slug'] for font in get_builtin_fonts()}
    normalized = {}
    for raw_code, raw_font in value.items():
        code = _normalize_language_code(raw_code)
        font = str(raw_font or '').strip()
        if code and font in allowed:
            normalized[code] = font
    return normalized


def _normalize_client_ip_header_name(value):
    raw_value = str(value or '').strip()
    if not raw_value:
        return ''
    normalized = raw_value.upper().replace('-', '_')
    if normalized in {'REMOTE_ADDR', 'CONTENT_TYPE', 'CONTENT_LENGTH'}:
        return normalized
    if not normalized.startswith('HTTP_'):
        normalized = f'HTTP_{normalized}'
    return normalized


def normalize_client_ip_config(value):
    normalized = default_client_ip_config()
    if not isinstance(value, dict):
        return normalized

    mode = str(value.get('mode') or '').strip().lower()
    if mode in CLIENT_IP_MODE_VALUES:
        normalized['mode'] = mode

    try:
        trusted_proxy_hops = int(value.get('trusted_proxy_hops', normalized['trusted_proxy_hops']))
    except (TypeError, ValueError):
        trusted_proxy_hops = normalized['trusted_proxy_hops']
    normalized['trusted_proxy_hops'] = max(0, min(trusted_proxy_hops, 8))

    normalized['custom_header'] = _normalize_client_ip_header_name(value.get('custom_header'))
    if normalized['mode'] != CLIENT_IP_MODE_CUSTOM:
        normalized['custom_header'] = ''

    return normalized


def normalize_email_config(value, *, redact_secret=False):
    config = value if isinstance(value, dict) else {}
    normalized = default_email_config()
    transport = str(config.get('transport') or '').strip()
    secret_storage = str(config.get('secret_storage') or '').strip()
    if transport in EMAIL_CONFIG_TRANSPORTS:
        normalized['transport'] = transport
    if secret_storage in EMAIL_CONFIG_SECRET_STORAGES:
        normalized['secret_storage'] = secret_storage
    normalized['host'] = str(config.get('host') or '').strip()
    try:
        normalized['port'] = int(config.get('port') or normalized['port'])
    except (TypeError, ValueError):
        normalized['port'] = 587
    normalized['use_tls'] = _coerce_import_bool(config.get('use_tls', normalized['use_tls']))
    normalized['use_ssl'] = _coerce_import_bool(config.get('use_ssl', normalized['use_ssl']))
    if normalized['use_ssl']:
        normalized['use_tls'] = False
    normalized['username'] = str(config.get('username') or '').strip()
    normalized['default_from_email'] = str(config.get('default_from_email') or '').strip()
    encrypted_password = str(config.get('encrypted_password') or '').strip()
    normalized['encrypted_password'] = encrypted_password
    normalized['password_configured'] = bool(encrypted_password or config.get('password_configured'))
    if redact_secret:
        normalized.pop('encrypted_password', None)
    return normalized


def normalize_auth_config(value):
    cfg = value if isinstance(value, dict) else {}
    return {
        'email_2fa': bool(cfg.get('email_2fa', False)),
        'prevent_multiple_active_sessions': bool(cfg.get('prevent_multiple_active_sessions', False)),
        'login_lockout_enabled': bool(cfg.get('login_lockout_enabled', True)),
        'enforce_strong_passwords': bool(cfg.get('enforce_strong_passwords', False)),
    }


def normalize_registration_config(value):
    cfg = value if isinstance(value, dict) else {}
    activation_mode = cfg.get('registration_activation_mode') or REGISTRATION_ACTIVATION_AUTO_LOGIN
    if activation_mode not in REGISTRATION_ACTIVATION_VALUES:
        activation_mode = REGISTRATION_ACTIVATION_AUTO_LOGIN
    return {
        'public_registration_enabled': bool(cfg.get('public_registration_enabled', False)),
        'registration_activation_mode': activation_mode,
        'registration_throttle_enabled': bool(cfg.get('registration_throttle_enabled', True)),
    }


def normalize_public_root_config(value):
    cfg = value if isinstance(value, dict) else {}
    return {
        'public_root': bool(cfg.get('public_root', False)),
        'public_root_split_enabled': bool(cfg.get('public_root_split_enabled', False)),
        'public_root_url': str(cfg.get('public_root_url') or '').strip(),
    }


def normalize_layout_config(value):
    cfg = value if isinstance(value, dict) else {}
    density = cfg.get('default_table_density') or DEFAULT_TABLE_DENSITY
    if density not in TABLE_DENSITY_VALUES:
        density = DEFAULT_TABLE_DENSITY
    return {
        'default_table_density': density,
    }


def normalize_language_config(value):
    cfg = value if isinstance(value, dict) else {}
    translations_override = cfg.get('translations_override', {})
    if not isinstance(translations_override, dict):
        translations_override = {}
    cleaned_translations = {}
    for lang, values in translations_override.items():
        if not isinstance(values, dict):
            continue
        lang_code = _normalize_language_code(lang)
        if not lang_code:
            continue
        lang_values = {
            str(key): str(text or '').strip()
            for key, text in values.items()
            if str(key or '').strip() and str(text or '').strip()
        }
        if lang_values:
            cleaned_translations[lang_code] = lang_values
    return {
        'languages': normalize_language_catalog(cfg.get('languages', {})),
        'translations_override': cleaned_translations,
        'allow_user_language_override': bool(cfg.get('allow_user_language_override', True)),
    }


def normalize_theme_config(value):
    from ..themes import normalize_allowed_themes

    cfg = value if isinstance(value, dict) else {}
    return {
        'allowed_themes': list(normalize_allowed_themes(cfg.get('allowed_themes'))),
        'allow_user_theme_override': bool(cfg.get('allow_user_theme_override', True)),
    }


def normalize_typography_config(value):
    cfg = value if isinstance(value, dict) else {}
    allowed_fonts = list(normalize_allowed_fonts(cfg.get('allowed_fonts')))
    return {
        'allowed_fonts': allowed_fonts,
        'default_fonts': normalize_default_fonts(cfg.get('default_fonts'), allowed_fonts=allowed_fonts),
        'allow_user_font_override': bool(cfg.get('allow_user_font_override', True)),
    }


def normalize_extra_config(value):
    return dict(value) if isinstance(value, dict) else {}


def normalize_titlebar_actions_order(value):
    if not isinstance(value, (list, tuple)):
        value = []
    normalized = []
    seen = set()
    for item in value:
        action_key = str(item or '').strip()
        if action_key in TITLEBAR_ACTIONS_ORDER_VALUES and action_key not in seen:
            normalized.append(action_key)
            seen.add(action_key)
    for action_key in TITLEBAR_ACTIONS_ORDER:
        if action_key not in seen:
            normalized.append(action_key)
    return normalized


def normalize_titlebar_config(titlebar_config):
    config = titlebar_config if isinstance(titlebar_config, dict) else {}
    normalized = default_titlebar_config()
    normalized['show_title'] = bool(config.get('show_title', normalized['show_title']))
    normalized['show_logo'] = bool(config.get('show_logo', normalized['show_logo']))
    normalized['show_home_button'] = bool(config.get('show_home_button', normalized['show_home_button']))
    normalized['hide_on_public_unauthenticated_index'] = bool(
        config.get('hide_on_public_unauthenticated_index', normalized['hide_on_public_unauthenticated_index'])
    )

    buttons_shape = config.get('buttons_shape', config.get('home_shape'))
    if buttons_shape in TITLEBAR_HOME_SHAPE_VALUES:
        normalized['buttons_shape'] = buttons_shape
        normalized['home_shape'] = buttons_shape

    title_align = config.get('title_align')
    if title_align in TITLEBAR_ALIGN_VALUES:
        normalized['title_align'] = title_align

    title_size = config.get('title_size')
    if title_size in TITLEBAR_SIZE_VALUES:
        normalized['title_size'] = title_size

    height = config.get('height')
    if height in TITLEBAR_HEIGHT_VALUES:
        normalized['height'] = height

    surface = config.get('surface')
    if surface in TITLEBAR_SURFACE_VALUES:
        normalized['surface'] = surface

    logo_treatment = config.get('logo_treatment')
    if logo_treatment in TITLEBAR_LOGO_TREATMENT_VALUES:
        normalized['logo_treatment'] = logo_treatment

    logo_treatment_shape = config.get('logo_treatment_shape')
    if logo_treatment_shape in TITLEBAR_LOGO_TREATMENT_SHAPE_VALUES:
        normalized['logo_treatment_shape'] = logo_treatment_shape

    user_hub_style = config.get('user_hub_style')
    if user_hub_style in TITLEBAR_USER_HUB_STYLE_VALUES:
        normalized['user_hub_style'] = user_hub_style

    normalized['actions_order'] = normalize_titlebar_actions_order(config.get('actions_order'))
    return normalized


def normalize_login_config(value):
    config = value if isinstance(value, dict) else {}
    normalized = default_login_config()
    style = config.get('style')
    if style in LOGIN_STYLE_VALUES:
        normalized['style'] = style
    normalized['show_logo'] = bool(config.get('show_logo', True))
    banner_color = str(config.get('banner_color') or '').strip()
    if banner_color:
        normalized['banner_color'] = banner_color
    logo_treatment = config.get('logo_treatment')
    if logo_treatment in TITLEBAR_LOGO_TREATMENT_VALUES:
        normalized['logo_treatment'] = logo_treatment
    logo_treatment_shape = config.get('logo_treatment_shape')
    if logo_treatment_shape in TITLEBAR_LOGO_TREATMENT_SHAPE_VALUES:
        normalized['logo_treatment_shape'] = logo_treatment_shape
    raw_hero = config.get('hero_message')
    if isinstance(raw_hero, dict):
        normalized['hero_message'] = {
            str(k): str(v or '').strip()
            for k, v in raw_hero.items()
            if str(k or '').strip()
        }
    else:
        normalized['hero_message'] = str(raw_hero or '').strip()
    return normalized


def normalize_sidebar_behavior(sidebar_config):
    config = sidebar_config if isinstance(sidebar_config, dict) else {}
    normalized = default_sidebar_config()
    normalized['enabled'] = bool(config.get('enabled', normalized['enabled']))
    normalized['home_url_name'] = config.get('home_url_name') if config.get('home_url_name') else None
    if isinstance(config.get('entries'), list):
        normalized['entries'] = [entry for entry in config.get('entries', []) if isinstance(entry, dict)]
    normalized['enable_reorder'] = bool(config.get('enable_reorder', normalized['enable_reorder']))
    normalized['show_toolbar'] = bool(config.get('show_toolbar', normalized['show_toolbar']))
    normalized['show_icons'] = bool(config.get('show_icons', normalized['show_icons']))
    normalized['allow_user_density'] = bool(config.get('allow_user_density', normalized['allow_user_density']))

    density = config.get('density')
    if density in SIDEBAR_DENSITY_VALUES:
        normalized['density'] = density

    collapse_mode = config.get('collapse_mode')
    if collapse_mode in SIDEBAR_COLLAPSE_MODE_VALUES:
        normalized['collapse_mode'] = collapse_mode

    if not normalized['show_icons'] and normalized['collapse_mode'] == 'icons':
        normalized['collapse_mode'] = 'hidden'

    return normalized


def _normalize_navbar_labels(value):
    if not isinstance(value, dict):
        return {}
    labels = {}
    for raw_code, raw_label in value.items():
        code = _normalize_language_code(raw_code)
        label = str(raw_label or '').strip()
        if code and label:
            labels[code] = label
    return labels


def _normalize_navbar_nodes(value, depth=0):
    if not isinstance(value, list) or depth > 6:
        return []

    nodes = []
    for raw_node in value:
        if not isinstance(raw_node, dict):
            continue
        kind = 'route' if raw_node.get('kind') == 'route' else 'manual'
        node_id = str(raw_node.get('id') or '').strip()
        if not node_id:
            continue
        node = {
            'kind': kind,
            'id': node_id[:180],
            'children': _normalize_navbar_nodes(raw_node.get('children'), depth + 1),
        }
        labels = _normalize_navbar_labels(raw_node.get('labels'))
        if labels:
            node['labels'] = labels
        url = str(raw_node.get('url') or '').strip()
        if url:
            node['url'] = url[:500]
        if kind == 'route':
            url_name = str(raw_node.get('url_name') or node_id).strip()
            if not url_name:
                continue
            node['url_name'] = url_name[:255]
        nodes.append(node)
    return nodes


def normalize_navbar_config(navbar_config):
    config = navbar_config if isinstance(navbar_config, dict) else {}
    normalized = default_navbar_config()
    normalized['enabled'] = bool(config.get('enabled', normalized['enabled']))
    mode = config.get('default_mode')
    if mode in NAVBAR_MODE_VALUES:
        normalized['default_mode'] = mode
    normalized['allow_user_mode_override'] = bool(
        config.get('allow_user_mode_override', normalized['allow_user_mode_override'])
    )
    hierarchy = config.get('hierarchy')
    hierarchy = hierarchy if isinstance(hierarchy, dict) else {}
    normalized['hierarchy'] = {
        'nodes': _normalize_navbar_nodes(hierarchy.get('nodes')),
    }
    return normalized


_LOG_ACTION_KEYS = ('create', 'update', 'delete')


def _normalize_log_section(value, defaults):
    section = value if isinstance(value, dict) else {}
    out = {
        'enabled': bool(section.get('enabled', defaults['enabled'])),
        'default_actions': {},
        'retention_days': 0,
        'models': {},
    }
    base_actions = defaults['default_actions']
    raw_actions = section.get('default_actions') if isinstance(section.get('default_actions'), dict) else {}
    for key in _LOG_ACTION_KEYS:
        out['default_actions'][key] = bool(raw_actions.get(key, base_actions.get(key, True)))

    try:
        out['retention_days'] = max(0, int(section.get('retention_days', 0) or 0))
    except (TypeError, ValueError):
        out['retention_days'] = 0

    raw_models = section.get('models') if isinstance(section.get('models'), dict) else {}
    for raw_key, raw_override in raw_models.items():
        key = str(raw_key or '').strip().lower()
        if not key or '.' not in key or not isinstance(raw_override, dict):
            continue
        entry = {'enabled': bool(raw_override.get('enabled', True))}
        raw_entry_actions = raw_override.get('actions') if isinstance(raw_override.get('actions'), dict) else {}
        actions = {}
        for act_key, act_val in raw_entry_actions.items():
            norm_act = str(act_key or '').strip().lower()
            if norm_act:
                actions[norm_act] = bool(act_val)
        if actions:
            entry['actions'] = actions
        out['models'][key] = entry
    return out


def normalize_log_config(value):
    config = value if isinstance(value, dict) else {}
    defaults = default_log_config()
    normalized = {
        'enabled': bool(config.get('enabled', True)),
        'user': _normalize_log_section(config.get('user'), defaults['user']),
        'system': _normalize_log_section(config.get('system'), defaults['system']),
        'audit': {},
    }

    audit_in = config.get('audit') if isinstance(config.get('audit'), dict) else {}
    audit_defaults = defaults['audit']
    audit = {
        'enabled': True,
        'immutable': True,
        'retention_days': 0,
        'events': {},
    }
    try:
        audit['retention_days'] = max(0, int(audit_in.get('retention_days', 0) or 0))
    except (TypeError, ValueError):
        audit['retention_days'] = 0
    raw_events = audit_in.get('events') if isinstance(audit_in.get('events'), dict) else {}
    for event_key, default_on in audit_defaults['events'].items():
        audit['events'][event_key] = bool(raw_events.get(event_key, default_on))
    normalized['audit'] = audit
    return normalized


def normalize_profile_config(value):
    config = value if isinstance(value, dict) else {}
    defaults = default_profile_config()
    normalized = {
        'show_completion_widget': bool(config.get('show_completion_widget', defaults['show_completion_widget'])),
        'show_session_device_cards': bool(config.get('show_session_device_cards', defaults['show_session_device_cards'])),
        'show_activity_feed': bool(config.get('show_activity_feed', defaults['show_activity_feed'])),
        'security_nudges': DEFAULT_SECURITY_NUDGE,
        'allow_user_home_url': bool(config.get('allow_user_home_url', defaults['allow_user_home_url'])),
        'onboarding_enabled': bool(config.get('onboarding_enabled', defaults['onboarding_enabled'])),
        'onboarding_options': {},
    }
    nudge = config.get('security_nudges')
    if nudge in SECURITY_NUDGE_VALUES:
        normalized['security_nudges'] = nudge
    raw_options = config.get('onboarding_options') if isinstance(config.get('onboarding_options'), dict) else {}
    for key, default_on in defaults['onboarding_options'].items():
        normalized['onboarding_options'][key] = bool(raw_options.get(key, default_on))
    return normalized


def normalize_notification_config(value=None):
    config = value if isinstance(value, dict) else {}
    defaults = default_notification_config()

    flash = config.get('flash') if isinstance(config.get('flash'), dict) else {}
    position = str(flash.get('position') or defaults['flash']['position']).strip()
    size = str(flash.get('size') or defaults['flash']['size']).strip()
    text_size = str(flash.get('text_size') or defaults['flash']['text_size']).strip()

    drawer = config.get('drawer') if isinstance(config.get('drawer'), dict) else {}
    bridge = config.get('bridge') if isinstance(config.get('bridge'), dict) else {}
    email = config.get('email') if isinstance(config.get('email'), dict) else {}
    retention = config.get('retention') if isinstance(config.get('retention'), dict) else {}
    automatic = config.get('automatic') if isinstance(config.get('automatic'), dict) else {}

    update = str(automatic.get('update') or defaults['automatic']['update']).strip()
    if update not in NOTIFICATION_UPDATE_MODES:
        update = defaults['automatic']['update']
    actor_flash_actions = automatic.get('actor_flash_actions')
    if not isinstance(actor_flash_actions, (list, tuple, set)):
        actor_flash_actions = defaults['automatic']['actor_flash_actions']

    return {
        'enabled': _to_bool(config.get('enabled'), defaults['enabled']),
        'flash': {
            'enabled': _to_bool(flash.get('enabled'), defaults['flash']['enabled']),
            'position': position if position in NOTIFICATION_FLASH_POSITIONS else defaults['flash']['position'],
            'size': size if size in NOTIFICATION_FLASH_SIZES else defaults['flash']['size'],
            'text_size': text_size if text_size in NOTIFICATION_FLASH_TEXT_SIZES else defaults['flash']['text_size'],
            'timeout_ms': _to_int(flash.get('timeout_ms'), defaults['flash']['timeout_ms'], min_value=0, max_value=60000),
            'max_visible': _to_int(flash.get('max_visible'), defaults['flash']['max_visible'], min_value=1, max_value=10),
        },
        'drawer': {
            'enabled': _to_bool(drawer.get('enabled'), defaults['drawer']['enabled']),
            'badge_enabled': _to_bool(drawer.get('badge_enabled'), defaults['drawer']['badge_enabled']),
            'preview_limit': _to_int(drawer.get('preview_limit'), defaults['drawer']['preview_limit'], min_value=1, max_value=50),
        },
        'bridge': {
            'django_messages_enabled': _to_bool(
                bridge.get('django_messages_enabled'),
                defaults['bridge']['django_messages_enabled'],
            ),
        },
        'email': {
            'enabled': _to_bool(email.get('enabled'), defaults['email']['enabled']),
            'default': _to_bool(email.get('default'), defaults['email']['default']),
        },
        'retention': {
            'default_expiry_days': _to_int(
                retention.get('default_expiry_days'),
                defaults['retention']['default_expiry_days'],
                min_value=0,
                max_value=3650,
            ),
        },
        'automatic': {
            'scoped_model_crud': _to_bool(
                automatic.get('scoped_model_crud'),
                defaults['automatic']['scoped_model_crud'],
            ),
            'create': _to_bool(automatic.get('create'), defaults['automatic']['create']),
            'update': update,
            'delete': _to_bool(automatic.get('delete'), defaults['automatic']['delete']),
            'actor_flash_actions': [
                str(action).strip().lower()
                for action in actor_flash_actions
                if str(action or '').strip()
            ],
            'watchable': _to_bool(automatic.get('watchable'), defaults['automatic']['watchable']),
        },
    }


__all__ = [
    '_normalize_client_ip_header_name',
    '_normalize_language_code',
    '_normalize_navbar_labels',
    '_normalize_navbar_nodes',
    'normalize_allowed_fonts',
    'normalize_auth_config',
    'normalize_client_ip_config',
    'normalize_default_fonts',
    'normalize_email_config',
    'normalize_extra_config',
    'normalize_language_catalog',
    'normalize_language_config',
    'normalize_layout_config',
    'normalize_log_config',
    'normalize_login_config',
    'normalize_navbar_config',
    'normalize_notification_config',
    'normalize_profile_config',
    'normalize_public_root_config',
    'normalize_registration_config',
    'normalize_sidebar_behavior',
    'normalize_theme_config',
    'normalize_titlebar_actions_order',
    'normalize_titlebar_config',
    'normalize_typography_config',
]
