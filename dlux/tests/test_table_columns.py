from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.test import SimpleTestCase, TestCase
from django.core.cache import cache

from dlux.models import SystemSettings
from dlux.system.registry import normalize_config_group, get_exportable_settings
from dlux.system.table_columns import normalize_tables_config
from dlux.utils.import_export import apply_system_settings_import, export_system_settings_payload
from dlux.utils.config import get_system_config, clear_system_config_cache


class TableColumnsNormalizationTests(SimpleTestCase):
    def test_malformed_containers_are_empty(self):
        for value in (None, [], 'bad', 1, {'columns': []}):
            with self.subTest(value=value):
                self.assertEqual(normalize_tables_config(value), {'columns': {}})

    def test_bad_entries_do_not_discard_valid_models(self):
        value = {'columns': {
            'documents.record': {'hidden': ['title', 'title', {}, None, ''], 'order': ['date', 'title']},
            'invalid': {'hidden': ['title']},
            'documents.other': [],
            'documents.empty': {'hidden': [], 'order': []},
        }}
        self.assertEqual(normalize_tables_config(value), {'columns': {
            'documents.record': {'hidden': ['title'], 'order': ['date', 'title']},
            'documents.empty': {'hidden': [], 'order': []},
        }})

    def test_unknown_columns_remain_for_runtime_to_resolve(self):
        value = {'columns': {'documents.record': {'hidden': ['retired_field'], 'order': ['future_field']}}}
        self.assertEqual(normalize_tables_config(value), value)

    def test_string_is_not_interpreted_as_a_column_list(self):
        self.assertEqual(normalize_tables_config({'columns': {'auth.user': {'hidden': 'username'}}}), {'columns': {}})

    def test_normalization_is_idempotent_and_does_not_mutate_input(self):
        value = {'columns': {'auth.user': {'order': ['username', 'username'], 'extra': True}}}
        normalized = normalize_tables_config(value)
        self.assertEqual(normalize_tables_config(normalized), normalized)
        self.assertEqual(value['columns']['auth.user']['order'], ['username', 'username'])

    def test_group_is_registered_and_exportable(self):
        self.assertEqual(normalize_config_group('tables_config', None), {'columns': {}})
        self.assertIn('tables_config', get_exportable_settings())

    def test_import_review_can_describe_table_configuration(self):
        from dlux.system.settings_diff import build_change_set

        result = build_change_set(
            {'tables_config': {}},
            {'tables_config': {'columns': {'auth.user': {'hidden': ['email']}}}},
        )
        self.assertTrue(result)


class TableColumnsStorageTests(TestCase):
    def setUp(self):
        cache.clear()
        clear_system_config_cache()

    def tearDown(self):
        cache.clear()
        clear_system_config_cache()

    def test_import_round_trip_preserves_unrelated_table_settings(self):
        instance = SystemSettings.load()
        instance.default_table_density = 'dense'
        instance.show_audit_fields = True
        instance.save()
        value = {'columns': {'auth.user': {'hidden': ['email'], 'order': ['username']}}}
        apply_system_settings_import(instance, {'tables_config': value})
        instance.save()
        instance.refresh_from_db()
        self.assertEqual(instance.tables_config, value)
        self.assertEqual(instance.default_table_density, 'dense')
        self.assertTrue(instance.show_audit_fields)
        self.assertEqual(export_system_settings_payload(instance)['settings']['tables_config'], value)
        clear_system_config_cache()
        self.assertEqual(get_system_config()['tables_config'], value)

    def test_malformed_import_is_normalized_before_persistence(self):
        instance = SystemSettings.load()
        apply_system_settings_import(instance, {'tables_config': {'columns': {'bad': [], 'auth.user': {'hidden': ['email', None]}}}})
        instance.save()
        instance.refresh_from_db()
        self.assertEqual(instance.tables_config, {'columns': {'auth.user': {'hidden': ['email']}}})

    def test_group_defaults_are_not_shared_between_instances(self):
        first, second = SystemSettings(), SystemSettings()
        first.tables_config['columns'] = {'auth.user': {'hidden': ['email']}}
        self.assertEqual(second.tables_config, {})

    def test_partial_import_can_clear_hidden_columns_without_removing_order(self):
        instance = SystemSettings.load()
        instance.tables_config = {'columns': {'auth.user': {'hidden': ['email'], 'order': ['username']}}}
        instance.save()
        apply_system_settings_import(instance, {'tables_config': {'columns': {'auth.user': {'hidden': []}}}})
        instance.save()
        instance.refresh_from_db()
        self.assertEqual(instance.tables_config, {'columns': {'auth.user': {'hidden': [], 'order': ['username']}}})
