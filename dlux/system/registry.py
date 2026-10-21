"""Registry helpers for the canonical Dlux system settings schema."""

from copy import deepcopy

from ..fonts import DEFAULT_FONT_SLUG
from .constants import (
    DEFAULT_HOME_URL,
    DEFAULT_LANGUAGE_CATALOG,
    SYSTEM_SETTINGS_EXPORT_FIELDS,
)
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


DB_OVERRIDE_POLICIES = frozenset({'configured_or_non_default'})


def db_group_applies(storage_field, value, *, configured):
    """Whether a group stored in `SystemSettings` overrides the project's `DLUX_CONFIG`.

    `configured_or_non_default`: once setup has completed the stored group wins;
    before that it wins only where it differs from the group's defaults, so the
    row a fresh install creates never masks what the project configured.
    """
    group = _GROUPS_BY_STORAGE[storage_field]
    if group.db_override_policy not in DB_OVERRIDE_POLICIES:
        raise ValueError(f'Unknown db_override_policy {group.db_override_policy!r} on {storage_field}')
    if not isinstance(value, dict) or not value:
        return False
    if configured:
        return True
    return group.normalizer(value) != group.normalizer(group.default_factory())


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
    """Names an import file may use for a group, plus `translations`.

    Derived from each group's declared `aliases`. An alias that is also a flat
    setting name (`public_root`, `languages`) keeps its flat meaning.
    """
    flat = get_flat_config_fields()
    aliases = {alias: storage for alias, storage in get_config_aliases().items() if alias not in flat}
    aliases['translations'] = 'translations_override'
    return aliases


def normalize_config_group(storage_field, value):
    return get_setting_group(storage_field).normalizer(value)


# Runtime keys that expose a whole group under its pre-`_config` name.
RUNTIME_GROUP_KEYS = {
    'client_ip': 'client_ip_config',
    'login': 'login_config',
    'notifications': 'notification_config',
    'sidebar': 'sidebar_config',
    'navbar': 'navbar_config',
    'titlebar': 'titlebar_config',
    'search': 'search_config',
}


def build_default_system_config():
    """Framework defaults for `get_system_config()`, derived from the registered groups.

    Only settings that belong to no group are spelled out here.
    """
    config = {
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
        'default_font': DEFAULT_FONT_SLUG,
        'translations': {},
        'is_configured': False,
    }
    for group in SYSTEM_SETTING_GROUPS:
        config[group.storage_field] = group.default_factory()
    for name, (storage_field, key) in get_flat_config_fields().items():
        if key in config[storage_field]:
            config[name] = deepcopy(config[storage_field][key])
    for runtime_key, storage_field in RUNTIME_GROUP_KEYS.items():
        config[runtime_key] = deepcopy(config[storage_field])
    # The stored language group starts empty; the runtime catalog does not.
    config['languages'] = deepcopy(DEFAULT_LANGUAGE_CATALOG)
    return config


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
