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
    'default_backup_config',
    'default_client_ip_config',
    'default_email_config',
    'default_extra_config',
    'default_homepage_config',
    'default_language_config',
    'default_layout_config',
    'default_log_config',
    'default_login_config',
    'default_navbar_config',
    'default_notification_config',
    'default_profile_config',
    'default_public_root_config',
    'default_registration_config',
    'default_search_config',
    'default_theme_config',
    'default_titlebar_config',
    'default_typography_config',
)


NORMALIZER_NAMES = (
    'normalize_auth_config',
    'normalize_backup_config',
    'normalize_client_ip_config',
    'normalize_email_config',
    'normalize_extra_config',
    'normalize_homepage_config',
    'normalize_language_config',
    'normalize_layout_config',
    'normalize_log_config',
    'normalize_login_config',
    'normalize_navbar_config',
    'normalize_notification_config',
    'normalize_profile_config',
    'normalize_public_root_config',
    'normalize_registration_config',
    'normalize_search_config',
    'normalize_sidebar_behavior',
    'normalize_theme_config',
    'normalize_titlebar_config',
    'normalize_typography_config',
)


class EmailConfigNormalizerTests(SimpleTestCase):
    def test_provider_preset_defaults_to_custom_and_rejects_unknown(self):
        self.assertEqual(system_normalizers.normalize_email_config({})['provider_preset'], 'custom')
        self.assertEqual(
            system_normalizers.normalize_email_config({'provider_preset': 'GMAIL'})['provider_preset'],
            'gmail',
        )
        self.assertEqual(
            system_normalizers.normalize_email_config({'provider_preset': 'bogus'})['provider_preset'],
            'custom',
        )

    def test_failure_recipients_clean_dedupe_and_cap(self):
        normalized = system_normalizers.normalize_email_config({
            'failure_notification_recipients': 'ops@example.com, ops@example.com\nbad-address; lead@example.com',
        })
        self.assertEqual(
            normalized['failure_notification_recipients'],
            ['ops@example.com', 'lead@example.com'],
        )

        many = ','.join(f'user{i}@example.com' for i in range(20))
        capped = system_normalizers.normalize_email_config({'failure_notification_recipients': many})
        self.assertEqual(len(capped['failure_notification_recipients']), 10)

    def test_redact_secret_keeps_new_keys(self):
        normalized = system_normalizers.normalize_email_config(
            {'provider_preset': 'gmail', 'failure_notification_recipients': ['ops@example.com']},
            redact_secret=True,
        )
        self.assertNotIn('encrypted_password', normalized)
        self.assertEqual(normalized['provider_preset'], 'gmail')
        self.assertEqual(normalized['failure_notification_recipients'], ['ops@example.com'])


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
        self.assertEqual(aliases['backup'], 'backup_config')
        self.assertEqual(aliases['client_ip'], 'client_ip_config')
        self.assertEqual(aliases['homepage'], 'homepage_config')
        self.assertEqual(aliases['search'], 'search_config')

    def test_import_aliases_avoid_flat_field_collisions(self):
        aliases = get_import_aliases()

        self.assertEqual(aliases['notifications'], 'notification_config')
        self.assertEqual(aliases['translations'], 'translations_override')
        self.assertEqual(aliases['public_homepage'], 'homepage_config')
        self.assertEqual(aliases['global_search'], 'search_config')
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
            'backup': {'scheduled_enabled': True, 'max_backups_to_keep': 7},
            'enforce_strong_passwords': True,
        })

        self.assertFalse(expanded['notification_config']['enabled'])
        self.assertFalse(expanded['log_config']['enabled'])
        self.assertTrue(expanded['profile_config']['allow_user_home_url'])
        self.assertTrue(expanded['backup_config']['scheduled_enabled'])
        self.assertEqual(expanded['backup_config']['max_backups_to_keep'], 7)
        self.assertTrue(expanded['auth_config']['enforce_strong_passwords'])

    def test_registry_default_config_contains_current_runtime_groups(self):
        default_config = build_default_system_config()

        for storage_field in get_config_defaults():
            self.assertIn(storage_field, default_config)
        self.assertIn('notifications', default_config)
        self.assertIn('sidebar', default_config)
        self.assertIn('titlebar', default_config)
        self.assertIn('homepage_config', default_config)
        self.assertIn('search_config', default_config)


class NewLayoutAndPublicRootKeysTests(SimpleTestCase):
    def test_layout_defaults_include_new_keys(self):
        layout = system_defaults.default_layout_config()
        self.assertEqual(layout['default_form_density'], 'balanced')
        self.assertEqual(layout['default_modal_size'], 'standard')
        self.assertTrue(layout['sticky_table_headers'])
        self.assertTrue(layout['resizable_table_columns'])
        self.assertTrue(layout['zebra_striping'])

    def test_normalize_layout_config_validates_choices_and_coerces_toggles(self):
        normalized = system_normalizers.normalize_layout_config({
            'default_form_density': 'bogus',
            'default_modal_size': 'bogus',
            'sticky_table_headers': 0,
            'resizable_table_columns': '',
            'zebra_striping': '',
        })
        self.assertEqual(normalized['default_form_density'], 'balanced')
        self.assertEqual(normalized['default_modal_size'], 'standard')
        self.assertFalse(normalized['sticky_table_headers'])
        self.assertFalse(normalized['resizable_table_columns'])
        self.assertFalse(normalized['zebra_striping'])

        valid = system_normalizers.normalize_layout_config({
            'default_form_density': 'dense',
            'default_modal_size': 'wide',
        })
        self.assertEqual(valid['default_form_density'], 'dense')
        self.assertEqual(valid['default_modal_size'], 'wide')

    def test_registration_defaults_and_normalizer_include_honeypot(self):
        self.assertTrue(system_defaults.default_registration_config()['honeypot_enabled'])
        self.assertFalse(
            system_normalizers.normalize_registration_config({'honeypot_enabled': False})['honeypot_enabled']
        )

    def test_public_root_defaults_include_new_keys(self):
        cfg = system_defaults.default_public_root_config()
        self.assertEqual(cfg['public_root_theme'], '')
        self.assertEqual(cfg['public_root_title'], '')
        self.assertEqual(cfg['public_root_meta_description'], '')
        self.assertFalse(cfg['show_titlebar_on_public'])
        self.assertFalse(cfg['show_sidebar_on_public'])

    def test_normalize_public_root_config_bounds_text_and_migrates_legacy_titlebar(self):
        normalized = system_normalizers.normalize_public_root_config({
            'public_root_title': '  Welcome  ',
            'public_root_meta_description': 'x' * 5000,
            'hide_on_public_unauthenticated_index': True,
        })
        self.assertEqual(normalized['public_root_title'], 'Welcome')
        self.assertEqual(len(normalized['public_root_meta_description']), 300)
        # Legacy hide=True -> show_titlebar_on_public=False (inverted).
        self.assertFalse(normalized['show_titlebar_on_public'])

        explicit = system_normalizers.normalize_public_root_config({
            'show_titlebar_on_public': True,
            'hide_on_public_unauthenticated_index': True,
        })
        self.assertTrue(explicit['show_titlebar_on_public'])

    def test_expand_migrates_titlebar_hide_into_public_root_show(self):
        expanded = expand_system_config_groups({
            'titlebar_config': {'hide_on_public_unauthenticated_index': True},
        })
        self.assertFalse(expanded['public_root_config']['show_titlebar_on_public'])
        self.assertFalse(expanded['show_titlebar_on_public'])

        expanded_shown = expand_system_config_groups({
            'titlebar_config': {'hide_on_public_unauthenticated_index': False},
        })
        self.assertTrue(expanded_shown['public_root_config']['show_titlebar_on_public'])

    def test_new_keys_are_exportable(self):
        export_fields = set(get_exportable_settings())
        for key in (
            'default_form_density',
            'default_modal_size',
            'sticky_table_headers',
            'resizable_table_columns',
            'zebra_striping',
            'public_root_theme',
            'public_root_title',
            'public_root_meta_description',
            'show_titlebar_on_public',
            'show_sidebar_on_public',
            'honeypot_enabled',
            'homepage_config',
            'search_config',
        ):
            self.assertIn(key, export_fields)

    def test_homepage_normalizer_accepts_legacy_fields_and_emits_canonical_shape(self):
        normalized = system_normalizers.normalize_homepage_config({
            'home_url': '/dashboard/',
            'allow_user_home_url': True,
            'public_root': True,
            'public_root_url': '/welcome/',
            'public_root_title': ' Welcome ',
        })
        self.assertEqual(normalized['default_url'], '/dashboard/')
        self.assertTrue(normalized['allow_user_override'])
        self.assertTrue(normalized['public']['enabled'])
        self.assertEqual(normalized['public']['url'], '/welcome/')
        self.assertEqual(normalized['public']['title'], 'Welcome')

    def test_expand_mirrors_canonical_homepage_and_search_to_legacy_keys(self):
        expanded = expand_system_config_groups({
            'homepage_config': {
                'default_url': '/dashboard/',
                'allow_user_override': True,
                'public': {'enabled': True, 'show_titlebar': True},
            },
            'search_config': {'enabled': False, 'display_mode': 'always', 'include_data': True},
        })
        self.assertEqual(expanded['home_url'], '/dashboard/')
        self.assertTrue(expanded['public_root'])
        self.assertTrue(expanded['show_titlebar_on_public'])
        self.assertTrue(expanded['profile_config']['allow_user_home_url'])
        self.assertEqual(expanded['titlebar_config']['global_search_mode'], 'disabled')
        self.assertTrue(expanded['titlebar_config']['global_search_include_data'])
