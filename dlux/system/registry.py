"""Registry helpers for the canonical Dlux system settings schema."""

from copy import deepcopy

from ..fonts import DEFAULT_FONT_SLUG
from ..themes import normalize_allowed_themes
from .constants import (
    DEFAULT_HOME_URL,
    DEFAULT_LANGUAGE_CATALOG,
    DEFAULT_TABLE_DENSITY,
    REGISTRATION_ACTIVATION_AUTO_LOGIN,
    SYSTEM_SETTINGS_EXPORT_FIELDS,
)
from .defaults import (
    default_auth_config,
    default_backup_config,
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
from .normalizers import normalize_allowed_fonts
from .schema import SYSTEM_SETTING_GROUPS


_GROUPS_BY_STORAGE = {group.storage_field: group for group in SYSTEM_SETTING_GROUPS}
_GROUPS_BY_NAME = {}
for _group in SYSTEM_SETTING_GROUPS:
    _GROUPS_BY_NAME[_group.key] = _group
    _GROUPS_BY_NAME[_group.storage_field] = _group
    for _alias in _group.aliases:
        _GROUPS_BY_NAME[_alias] = _group


def iter_setting_groups():
    return SYSTEM_SETTING_GROUPS


def get_setting_group(name):
    try:
        return _GROUPS_BY_NAME[name]
    except KeyError as exc:
        raise KeyError(f'Unknown Dlux setting group: {name}') from exc


def get_config_default_factory(storage_field):
    return get_setting_group(storage_field).default_factory


def get_config_defaults():
    return {
        group.storage_field: group.default_factory
        for group in SYSTEM_SETTING_GROUPS
    }


def get_config_normalizers():
    return {
        group.storage_field: group.normalizer
        for group in SYSTEM_SETTING_GROUPS
    }


def get_flat_config_fields():
    mapping = {}
    for group in SYSTEM_SETTING_GROUPS:
        for field in group.fields:
            if field.legacy_flat:
                mapping[field.form_name] = field.storage
    return mapping


def get_flat_config_keys_by_group():
    by_group = {}
    for flat_name, (storage_field, _key) in get_flat_config_fields().items():
        by_group.setdefault(storage_field, []).append(flat_name)
    return {
        storage_field: tuple(flat_names)
        for storage_field, flat_names in by_group.items()
    }


def get_config_aliases():
    aliases = {}
    for group in SYSTEM_SETTING_GROUPS:
        for alias in group.aliases:
            aliases[alias] = group.storage_field
    return aliases


def get_import_aliases():
    return {
        'translations': 'translations_override',
        'auth': 'auth_config',
        'authentication': 'auth_config',
        'email': 'email_config',
        'mail': 'email_config',
        'smtp': 'email_config',
        'registration': 'registration_config',
        'client_ip': 'client_ip_config',
        'ip': 'client_ip_config',
        'proxy': 'client_ip_config',
        'notifications': 'notification_config',
        'notification': 'notification_config',
        'login': 'login_config',
        'login_page': 'login_config',
        'titlebar': 'titlebar_config',
        'topbar': 'titlebar_config',
        'sidebar': 'sidebar_config',
        'side_nav': 'sidebar_config',
        'navbar': 'navbar_config',
        'nav_bar': 'navbar_config',
        'log': 'log_config',
        'logging': 'log_config',
        'activity_logging': 'log_config',
        'profile': 'profile_config',
        'profile_page': 'profile_config',
        'onboarding': 'profile_config',
        'backup': 'backup_config',
        'backups': 'backup_config',
        'system_backup': 'backup_config',
        'extra': 'extra_config',
        'custom': 'extra_config',
    }


def normalize_config_group(storage_field, value):
    return get_setting_group(storage_field).normalizer(value)


def build_default_system_config():
    return {
        'system_names': {
            'en': 'DjangoLux',
            'ar': 'DjangoLux',
        },
        'verbose_name': 'DjangoLux',
        'logo': '/static/img/base_logo.svg',
        'login_logo': '/static/img/login_logo.svg',
        'favicon': '/static/img/base_logo.svg',
        'home_url': DEFAULT_HOME_URL,
        'default_language': 'en',
        'default_theme': 'light',
        'allowed_themes': list(normalize_allowed_themes()),
        'allow_user_theme_override': True,
        'default_font': DEFAULT_FONT_SLUG,
        'allowed_fonts': list(normalize_allowed_fonts()),
        'default_fonts': {},
        'allow_user_font_override': True,
        'allow_user_language_override': True,
        'default_table_density': DEFAULT_TABLE_DENSITY,
        'email_2fa': False,
        'prevent_multiple_active_sessions': False,
        'login_lockout_enabled': True,
        'login_lockout_threshold': 5,
        'login_lockout_window_minutes': 15,
        'login_lockout_duration_minutes': 15,
        'enforce_strong_passwords': False,
        'strong_password_min_length': 12,
        'auth_config': default_auth_config(),
        'email_config': default_email_config(),
        'registration_config': default_registration_config(),
        'public_root_config': default_public_root_config(),
        'client_ip_config': default_client_ip_config(),
        'notification_config': default_notification_config(),
        'layout_config': default_layout_config(),
        'language_config': default_language_config(),
        'theme_config': default_theme_config(),
        'typography_config': default_typography_config(),
        'login_config': default_login_config(),
        'titlebar_config': default_titlebar_config(),
        'sidebar_config': default_sidebar_config(),
        'navbar_config': default_navbar_config(),
        'log_config': default_log_config(),
        'profile_config': default_profile_config(),
        'backup_config': default_backup_config(),
        'extra_config': default_extra_config(),
        'client_ip': default_client_ip_config(),
        'login': default_login_config(),
        'public_root': False,
        'public_root_split_enabled': False,
        'public_root_url': '',
        'public_registration_enabled': False,
        'registration_activation_mode': REGISTRATION_ACTIVATION_AUTO_LOGIN,
        'registration_throttle_enabled': True,
        'privacy_policy_url': '',
        'terms_url': '',
        'privacy_notice_text': '',
        'registration_require_consent': False,
        'notifications': default_notification_config(),
        'languages': deepcopy(DEFAULT_LANGUAGE_CATALOG),
        'translations': {},
        'sidebar': default_sidebar_config(),
        'navbar': default_navbar_config(),
        'titlebar': default_titlebar_config(),
        'is_configured': False,
    }


def get_exportable_settings():
    return SYSTEM_SETTINGS_EXPORT_FIELDS


__all__ = [
    'build_default_system_config',
    'get_config_aliases',
    'get_config_default_factory',
    'get_config_defaults',
    'get_config_normalizers',
    'get_exportable_settings',
    'get_flat_config_fields',
    'get_flat_config_keys_by_group',
    'get_import_aliases',
    'get_setting_group',
    'iter_setting_groups',
    'normalize_config_group',
]
