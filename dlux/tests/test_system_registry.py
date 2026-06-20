from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.db import models
from django.test import SimpleTestCase

from dlux.models import SystemSettings
from dlux.system import defaults as system_defaults
from dlux.system import normalizers as system_normalizers
from dlux.system.registry import (
    build_default_system_config,
    get_config_aliases,
    get_config_default_factory,
    get_config_defaults,
    get_config_normalizers,
    get_exportable_settings,
    get_flat_config_fields,
    get_import_aliases,
    iter_setting_groups,
)
from dlux.utils.config import expand_system_config_groups
from dlux.utils.import_export import SYSTEM_SETTINGS_EXPORT_FIELDS


DEFAULT_CALLABLE_NAMES = (
    'default_auth_config',
    'default_client_ip_config',
    'default_email_config',
    'default_extra_config',
    'default_language_config',
    'default_layout_config',
    'default_log_config',
    'default_login_config',
    'default_navbar_config',
    'default_notification_config',
    'default_profile_config',
    'default_public_root_config',
    'default_registration_config',
    'default_theme_config',
    'default_titlebar_config',
    'default_typography_config',
)


NORMALIZER_NAMES = (
    'normalize_auth_config',
    'normalize_client_ip_config',
    'normalize_email_config',
    'normalize_extra_config',
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
    'normalize_titlebar_config',
    'normalize_typography_config',
)


class SystemSettingsRegistryTests(SimpleTestCase):
    def test_registry_covers_every_system_settings_config_json_field(self):
        model_config_fields = {
            field.name
            for field in SystemSettings._meta.fields
            if isinstance(field, models.JSONField) and field.name.endswith('_config')
        }
        registry_fields = {group.storage_field for group in iter_setting_groups()}

        self.assertEqual(registry_fields, model_config_fields)
        for storage_field in model_config_fields:
            self.assertTrue(callable(get_config_default_factory(storage_field)))
            self.assertTrue(callable(get_config_normalizers()[storage_field]))

    def test_flat_registry_paths_point_to_real_default_keys(self):
        for flat_name, (storage_field, config_key) in get_flat_config_fields().items():
            defaults = get_config_default_factory(storage_field)()

            self.assertIn(config_key, defaults, flat_name)

    def test_export_registry_matches_import_export_public_constant(self):
        self.assertEqual(get_exportable_settings(), SYSTEM_SETTINGS_EXPORT_FIELDS)

    def test_runtime_aliases_include_group_level_settings(self):
        aliases = get_config_aliases()

        self.assertEqual(aliases['notifications'], 'notification_config')
        self.assertEqual(aliases['log'], 'log_config')
        self.assertEqual(aliases['logging'], 'log_config')
        self.assertEqual(aliases['profile'], 'profile_config')
        self.assertEqual(aliases['client_ip'], 'client_ip_config')

    def test_import_aliases_avoid_flat_field_collisions(self):
        aliases = get_import_aliases()

        self.assertEqual(aliases['notifications'], 'notification_config')
        self.assertEqual(aliases['translations'], 'translations_override')
        self.assertNotIn('public_root', aliases)
        self.assertNotIn('languages', aliases)

    def test_old_default_import_paths_match_system_defaults(self):
        from dlux import models as dlux_models
        from dlux.utils import config as utils_config

        for name in DEFAULT_CALLABLE_NAMES:
            expected = getattr(system_defaults, name)()
            self.assertEqual(getattr(dlux_models, name)(), expected, name)
            self.assertEqual(getattr(utils_config, name)(), expected, name)

    def test_old_normalizer_import_paths_are_system_normalizer_aliases(self):
        from dlux.utils import config as utils_config

        for name in NORMALIZER_NAMES:
            self.assertIs(getattr(utils_config, name), getattr(system_normalizers, name), name)

    def test_migration_callable_paths_remain_importable_from_models(self):
        from dlux import models as dlux_models

        for name in DEFAULT_CALLABLE_NAMES:
            self.assertTrue(callable(getattr(dlux_models, name)), name)

    def test_expand_system_config_groups_uses_registry_alias_and_flat_maps(self):
        expanded = expand_system_config_groups({
            'notifications': {'enabled': False},
            'log': {'enabled': False},
            'profile': {'allow_user_home_url': True},
            'enforce_strong_passwords': True,
        })

        self.assertFalse(expanded['notification_config']['enabled'])
        self.assertFalse(expanded['log_config']['enabled'])
        self.assertTrue(expanded['profile_config']['allow_user_home_url'])
        self.assertTrue(expanded['auth_config']['enforce_strong_passwords'])

    def test_registry_default_config_contains_current_runtime_groups(self):
        default_config = build_default_system_config()

        for storage_field in get_config_defaults():
            self.assertIn(storage_field, default_config)
        self.assertIn('notifications', default_config)
        self.assertIn('sidebar', default_config)
        self.assertIn('titlebar', default_config)
