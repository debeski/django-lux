"""Notification configuration defaults and coercion helpers."""

NOTIFICATION_FLASH_POSITIONS = {
    'top_center',
    'top_start',
    'top_end',
    'titlebar_end',
    'bottom_start',
    'bottom_end',
}
NOTIFICATION_FLASH_SIZES = {'compact', 'balanced', 'prominent'}
NOTIFICATION_FLASH_TEXT_SIZES = {'sm', 'md', 'lg'}
NOTIFICATION_UPDATE_MODES = {'off', 'summary', 'full'}


def default_notification_config():
    """Return the default Dlux notification runtime policy."""
    return {
        'enabled': True,
        'flash': {
            'enabled': True,
            'position': 'top_center',
            'size': 'balanced',
            'text_size': 'md',
            'timeout_ms': 3200,
            'max_visible': 3,
        },
        'drawer': {
            'enabled': True,
            'badge_enabled': True,
            'preview_limit': 8,
        },
        'bridge': {
            'django_messages_enabled': False,
        },
        'email': {
            'enabled': False,
            'default': False,
        },
        'retention': {
            'default_expiry_days': 30,
        },
        'automatic': {
            'scoped_model_crud': True,
            'create': True,
            'update': 'summary',
            'delete': True,
            'actor_flash_actions': ['create', 'delete', 'error'],
            'watchable': True,
        },
    }


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


def normalize_notification_config(value=None):
    """Coerce arbitrary notification settings into the supported shape."""
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
