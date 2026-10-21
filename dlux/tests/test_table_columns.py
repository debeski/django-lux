from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.test import SimpleTestCase, TestCase
from django.core.cache import cache

from dlux.models import SystemSettings
from dlux.system.registry import normalize_config_group, get_exportable_settings
from dlux.system.table_columns import normalize_tables_config
from dlux.system.defaults import default_tables_config
from dlux.utils.import_export import apply_system_settings_import, export_system_settings_payload
from dlux.utils.config import get_system_config, clear_system_config_cache


class TableColumnsNormalizationTests(SimpleTestCase):
    def test_malformed_containers_are_empty(self):
        for value in (None, [], 'bad', 1, {'columns': []}):
            with self.subTest(value=value):
                self.assertEqual(normalize_tables_config(value), default_tables_config())

    def test_bad_entries_do_not_discard_valid_models(self):
        value = {'columns': {
            'documents.record': {'hidden': ['title', 'title', {}, None, ''], 'order': ['date', 'title']},
            'invalid': {'hidden': ['title']},
            'documents.other': [],
            'documents.empty': {'hidden': [], 'order': []},
        }}
        self.assertEqual(normalize_tables_config(value)['columns'], {
            'documents.record': {'hidden': ['title'], 'order': ['date', 'title']},
            'documents.empty': {'hidden': [], 'order': []},
        })

    def test_unknown_columns_remain_for_runtime_to_resolve(self):
        value = {'columns': {'documents.record': {'hidden': ['retired_field'], 'order': ['future_field']}}}
        self.assertEqual(normalize_tables_config(value)['columns'], value['columns'])

    def test_string_is_not_interpreted_as_a_column_list(self):
        self.assertEqual(normalize_tables_config({'columns': {'auth.user': {'hidden': 'username'}}}), default_tables_config())

    def test_normalization_is_idempotent_and_does_not_mutate_input(self):
        value = {'columns': {'auth.user': {'order': ['username', 'username'], 'extra': True}}}
        normalized = normalize_tables_config(value)
        self.assertEqual(normalize_tables_config(normalized), normalized)
        self.assertEqual(value['columns']['auth.user']['order'], ['username', 'username'])

    def test_group_is_registered_and_exportable(self):
        self.assertEqual(normalize_config_group('tables_config', None), default_tables_config())
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
        expected = {**default_tables_config(), **value, 'default_table_density': 'dense', 'show_audit_fields': True}
        self.assertEqual(instance.tables_config, expected)
        self.assertEqual(instance.default_table_density, 'dense')
        self.assertTrue(instance.show_audit_fields)
        self.assertEqual(export_system_settings_payload(instance)['settings']['tables_config'], expected)
        clear_system_config_cache()
        self.assertEqual(get_system_config()['tables_config'], expected)

    def test_malformed_import_is_normalized_before_persistence(self):
        instance = SystemSettings.load()
        apply_system_settings_import(instance, {'tables_config': {'columns': {'bad': [], 'auth.user': {'hidden': ['email', None]}}}})
        instance.save()
        instance.refresh_from_db()
        self.assertEqual(instance.tables_config['columns'], {'auth.user': {'hidden': ['email']}})

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
        self.assertEqual(instance.tables_config['columns'], {'auth.user': {'hidden': [], 'order': ['username']}})

    def test_legacy_layout_write_and_flat_property_write_stay_synchronized(self):
        instance = SystemSettings.load()
        instance.layout_config = {**instance.layout_config, 'default_table_density': 'dense', 'show_audit_fields': True}
        instance.save(update_fields=['layout_config'])
        instance.refresh_from_db()
        self.assertEqual(instance.tables_config['default_table_density'], 'dense')
        self.assertTrue(instance.show_audit_fields)
        instance.show_audit_fields = False
        instance.save(update_fields=['show_audit_fields'])
        instance.refresh_from_db()
        self.assertFalse(instance.tables_config['show_audit_fields'])
        self.assertFalse(instance.layout_config['show_audit_fields'])

    def test_canonical_group_wins_when_both_groups_are_explicitly_written(self):
        instance = SystemSettings.load()
        instance.tables_config['show_audit_fields'] = False
        instance.layout_config['show_audit_fields'] = True
        instance.save(update_fields=['tables_config', 'layout_config'])
        instance.refresh_from_db()
        self.assertFalse(instance.tables_config['show_audit_fields'])
        self.assertFalse(instance.layout_config['show_audit_fields'])

    def test_old_project_layout_config_remains_a_runtime_input(self):
        from dlux.utils.config import expand_system_config_groups

        expanded = expand_system_config_groups({'layout_config': {'show_audit_fields': True, 'default_table_density': 'dense'}})
        self.assertTrue(expanded['tables_config']['show_audit_fields'])
        self.assertTrue(expanded['show_audit_fields'])
        self.assertEqual(expanded['default_table_density'], 'dense')

    def test_partial_legacy_group_import_preserves_its_false_values(self):
        instance = SystemSettings.load()
        instance.show_audit_fields = True
        instance.row_actions_style = 'both'
        instance.save()
        apply_system_settings_import(instance, {'layout_config': {'show_audit_fields': 'false', 'default_table_density': 'dense'}})
        instance.save()
        instance.refresh_from_db()
        self.assertFalse(instance.show_audit_fields)
        self.assertEqual(instance.default_table_density, 'dense')
        self.assertEqual(instance.row_actions_style, 'both')

    def test_canonical_project_group_overrides_legacy_group_and_mirrors_it(self):
        from dlux.utils.config import expand_system_config_groups

        expanded = expand_system_config_groups({
            'layout_config': {'show_audit_fields': True},
            'tables_config': {'show_audit_fields': False},
        })
        self.assertFalse(expanded['show_audit_fields'])
        self.assertFalse(expanded['layout_config']['show_audit_fields'])


class TableConfigReadThroughTests(TestCase):
    def setUp(self):
        cache.clear()
        clear_system_config_cache()

    def tearDown(self):
        cache.clear()
        clear_system_config_cache()

    def test_legacy_values_are_read_then_saved_without_replacing_existing_overlays(self):
        row = SystemSettings.load()
        legacy = {'default_table_density': 'dense', 'show_audit_fields': True, 'zebra_striping': False}
        canonical = {'show_audit_fields': False, 'columns': {'auth.user': {'hidden': ['email']}}}
        SystemSettings.objects.filter(pk=row.pk).update(layout_config=legacy, tables_config=canonical)
        cache.clear()
        current = SystemSettings.load()
        self.assertEqual(current.tables_config['default_table_density'], 'dense')
        self.assertFalse(current.tables_config['show_audit_fields'])
        self.assertFalse(current.tables_config['zebra_striping'])
        self.assertEqual(current.tables_config['columns'], canonical['columns'])
        self.assertFalse(current.layout_config['show_audit_fields'])
        self.assertEqual(SystemSettings.objects.get(pk=row.pk).tables_config, canonical, 'Reading must not write data')
        current.save()
        current.refresh_from_db()
        self.assertEqual(current.tables_config['default_table_density'], 'dense')
        self.assertFalse(current.layout_config['show_audit_fields'])

    def test_cached_instance_from_before_the_storage_move_is_refreshed(self):
        row = SystemSettings.load()
        SystemSettings.objects.filter(pk=row.pk).update(layout_config={'default_table_density': 'dense'}, tables_config={})
        del row._table_config_snapshot
        cache.set('SystemSettings', row)
        current = SystemSettings.load()
        self.assertEqual(current.default_table_density, 'dense')


class TableStepTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        from django.test import RequestFactory

        cache.clear()
        clear_system_config_cache()
        self.user = get_user_model().objects.create_superuser('table-admin', 'tables@example.com', 'test-password')
        self.factory = RequestFactory()

    def tearDown(self):
        cache.clear()
        clear_system_config_cache()

    def form(self, obj, step, data):
        from dlux.forms import SystemSettingsForm

        request = self.factory.post(f'/sys/settings/?step={step}', data)
        request.user = self.user
        request.session = {}
        return SystemSettingsForm(request.POST, instance=obj, request=request, user=self.user)

    def test_tables_step_is_between_ribbon_and_components(self):
        from dlux.system.constants import SETUP_STEP_SLUGS

        index = SETUP_STEP_SLUGS.index('tables')
        self.assertEqual(SETUP_STEP_SLUGS[index - 1:index + 2], ('ribbon', 'tables', 'layout'))

    def test_saving_every_other_step_preserves_all_table_settings(self):
        from dlux.system.constants import SETUP_STEP_SLUGS, SETUP_STEP_TABLES, TABLE_CONFIG_KEYS

        for enabled in (False, True):
            for step in range(len(SETUP_STEP_SLUGS)):
                if step == SETUP_STEP_TABLES:
                    continue
                with self.subTest(enabled=enabled, step=SETUP_STEP_SLUGS[step]):
                    obj = SystemSettings.load()
                    obj.is_configured = True
                    obj.default_language = 'en'
                    obj.tables_config = {**default_tables_config(), 'default_table_density': 'dense',
                        'row_actions_style': 'both',
                        **{key: enabled for key in ('table_accent_edges', 'sticky_table_headers', 'resizable_table_columns', 'zebra_striping', 'show_audit_fields', 'show_soft_deleted')},
                        'columns': {'auth.user': {'hidden': ['email']}}}
                    obj.save()
                    before = obj.tables_config.copy()
                    form = self.form(obj, step, {'default_language': 'en'})
                    self.assertTrue(form.is_valid(), form.errors)
                    form.save()
                    obj.refresh_from_db()
                    self.assertEqual(obj.tables_config, before)
                    self.assertEqual({key: obj.layout_config[key] for key in TABLE_CONFIG_KEYS}, {key: before[key] for key in TABLE_CONFIG_KEYS})

    def test_audit_and_soft_deleted_switches_accept_off_and_on_in_tables(self):
        from dlux.system.constants import SETUP_STEP_TABLES

        for enabled in (False, True):
            obj = SystemSettings.load()
            obj.is_configured = True
            obj.show_audit_fields = not enabled
            obj.show_soft_deleted = not enabled
            obj.save()
            data = {'default_language': 'en', 'default_table_density': 'dense', 'row_actions_style': 'both'}
            if enabled:
                data.update(show_audit_fields='on', show_soft_deleted='on')
            form = self.form(obj, SETUP_STEP_TABLES, data)
            self.assertEqual(form.field_steps['show_audit_fields'], SETUP_STEP_TABLES)
            self.assertTrue(form.is_valid(), form.errors)
            form.save()
            obj.refresh_from_db()
            self.assertIs(obj.show_audit_fields, enabled)
            self.assertIs(obj.show_soft_deleted, enabled)
            self.assertEqual(obj.row_actions_style, 'both')

    def test_table_form_round_trips_the_hidden_column_configuration(self):
        import json
        from dlux.system.constants import SETUP_STEP_TABLES

        obj = SystemSettings.load()
        obj.is_configured = True
        obj.save()
        columns = {'auth.user': {'hidden': ['email'], 'order': ['username']}}
        form = self.form(obj, SETUP_STEP_TABLES, {
            'tables_config': json.dumps({'columns': columns}),
            'default_table_density': 'dense', 'row_actions_style': 'both',
        })
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        obj.refresh_from_db()
        self.assertEqual(obj.tables_config['columns'], columns)
        self.assertEqual(obj.default_table_density, 'dense')

    def test_setup_file_import_retains_column_configuration(self):
        import json
        from django.core.files.uploadedfile import SimpleUploadedFile
        from dlux.forms import SystemSettingsForm
        from dlux.tests.test_accent_edges import _form_data

        columns = {'auth.user': {'hidden': ['email'], 'order': ['username']}}
        upload = SimpleUploadedFile('settings.json', json.dumps({'tables_config': {'columns': columns}}).encode(), content_type='application/json')
        form = SystemSettingsForm(
            data=_form_data(), files={'settings_import_file': upload},
            instance=SystemSettings.load(), user=self.user, mode='setup',
        )
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        saved.refresh_from_db()
        self.assertEqual(saved.tables_config['columns'], columns)
