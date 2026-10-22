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
from unittest.mock import patch

import django_tables2 as tables
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, override_settings
from django.urls import path
from django.views import View
from django.template import Context, Template
from django.test.utils import CaptureQueriesContext
from django.db import connection

from dlux.tables import DluxTable
from dlux.discovery.tables import table_column_catalog
from dlux.utils.table_columns import baseline_table_columns, configurable_table_columns


class ColumnFixtureTable(DluxTable):
    computed = tables.Column(verbose_name='Computed label', empty_values=())
    internal = tables.Column(visible=False)

    class Meta:
        model = get_user_model()
        fields = ('username', 'email', 'first_name')
        sequence = ('username', 'email', 'first_name', 'computed', 'internal')


class ColumnFixtureView(View):
    table_class = ColumnFixtureTable


class _TableColumnTestSupport:
    def setUp(self):
        cache.clear()
        clear_system_config_cache()

    def tearDown(self):
        cache.clear()
        clear_system_config_cache()

    def configure(self, overlay, **preferences):
        instance = SystemSettings.load()
        instance.tables_config = {
            **instance.tables_config, **preferences,
            'columns': {get_user_model()._meta.label_lower: overlay},
        }
        instance.save()
        clear_system_config_cache()

    def names(self, table):
        return [column.name for column in table.columns]


class TableColumnOverlayTests(_TableColumnTestSupport, TestCase):
    def test_localized_headers_and_icons_render_escaped_and_do_not_leak_between_instances(self):
        self.configure({'headers': {'email': {'labels': {'en': '<script>mail</script>', 'ar': 'بريد خاص'}, 'icon': 'bi-envelope'}}})
        request = RequestFactory().get('/')
        request.session = {}
        request.user = AnonymousUser()
        request.dlux_preview_language = 'en'
        table = ColumnFixtureTable([], request=request)
        template = Template('{% load django_tables2 %}{% render_table table %}')
        html = template.render(Context({'table': table, 'request': request}))
        self.assertIn('&lt;script&gt;mail&lt;/script&gt;', html)
        self.assertNotIn('<script>mail</script>', html)
        self.assertIn('bi-envelope', html)
        request.dlux_preview_language = 'ar'
        arabic = ColumnFixtureTable([], request=request)
        self.assertEqual(arabic.columns['email'].column.dlux_header_label, 'بريد خاص')
        with baseline_table_columns():
            baseline = ColumnFixtureTable([])
        self.assertFalse(hasattr(baseline.columns['email'].column, 'dlux_header_label'))
        self.assertFalse(hasattr(ColumnFixtureTable.base_columns['email'], 'dlux_header_icon'))

    def test_primary_secondary_sorting_orders_real_rows_and_request_sort_wins(self):
        User = get_user_model()
        User.objects.create(username='zeta', email='b@example.com')
        User.objects.create(username='alpha', email='b@example.com')
        User.objects.create(username='omega', email='a@example.com')
        self.configure({'sorting': ['email', '-username']})
        table = ColumnFixtureTable(User.objects.all())
        self.assertEqual([record.username for record in table.data], ['omega', 'zeta', 'alpha'])
        request = RequestFactory().get('/', {'sort': 'username'})
        request.user = AnonymousUser()
        requested = ColumnFixtureTable(User.objects.all(), request=request)
        self.assertEqual(tuple(requested.order_by), ('username',))
        self.assertEqual([record.username for record in requested.data], ['alpha', 'omega', 'zeta'])

    def test_headers_and_sorting_cannot_target_protected_or_code_hidden_columns(self):
        self.configure({'headers': {'internal': {'labels': {'en': 'Leaked'}}, 'created_at': {'icon': 'bi-lock'}},
                        'sorting': ['internal', 'created_at']})
        table = ColumnFixtureTable([])
        self.assertFalse(hasattr(table.columns['internal'].column, 'dlux_header_label'))
        self.assertNotIn('internal', self.names(table))
        self.assertFalse(table.order_by)

    def test_non_orderable_and_stale_sort_columns_are_ignored(self):
        class NonOrderable(ColumnFixtureTable):
            computed = tables.Column(orderable=False)
            class Meta(ColumnFixtureTable.Meta):
                pass
        self.configure({'sorting': ['computed', 'retired']})
        self.assertFalse(NonOrderable([]).order_by)

    def test_unsupported_computed_default_sort_keeps_developer_order(self):
        self.configure({'sorting': ['computed']})
        with self.assertLogs('dlux', level='WARNING'):
            table = ColumnFixtureTable(get_user_model().objects.all(), order_by='username')
        self.assertEqual(tuple(table.order_by), ('username',))

    def test_reapplying_table_patch_keeps_one_wrapper(self):
        from dlux.patches import _patch_table_init

        original = tables.Table.__init__
        _patch_table_init()
        _patch_table_init()
        self.assertIs(tables.Table.__init__, original)

    def test_handwritten_table_hides_and_reorders_without_mutating_class(self):
        self.configure({'hidden': ['email'], 'order': ['computed', 'username']})
        table = ColumnFixtureTable([])
        self.assertEqual(self.names(table), ['computed', 'username', 'first_name'])
        self.assertTrue(ColumnFixtureTable.base_columns['email'].visible)
        with baseline_table_columns():
            baseline = ColumnFixtureTable([])
        self.assertEqual(self.names(baseline), ['username', 'email', 'first_name', 'computed'])

    def test_generated_table_uses_same_model_overlay(self):
        from dlux.utils.crud import _build_generic_table_class
        self.configure({'hidden': ['email'], 'order': ['first_name', 'username']})
        table = _build_generic_table_class(get_user_model())([])
        self.assertNotIn('email', self.names(table))
        self.assertEqual(self.names(table)[:2], ['first_name', 'username'])

    def test_no_configuration_preserves_rendered_html(self):
        request = RequestFactory().get('/')
        request.session = {}
        request.user = AnonymousUser()
        template = Template('{% load django_tables2 %}{% render_table table %}')
        def render():
            return template.render(Context({'table': ColumnFixtureTable([]), 'request': request}))
        baseline = render()
        self.configure({'hidden': ['removed'], 'order': ['removed']})
        self.assertEqual(render(), baseline)
        self.configure({})
        self.assertEqual(render(), baseline)

    def test_all_hidden_retains_first_data_column_even_with_actions(self):
        self.configure({'hidden': ['username', 'email', 'first_name', 'computed']}, row_actions_style='column')
        self.assertEqual(self.names(ColumnFixtureTable([])), ['username', 'dlux_row_actions'])

    def test_code_hidden_and_excluded_columns_cannot_be_revealed(self):
        self.configure({'order': ['internal', 'email', 'username']})
        table = ColumnFixtureTable([], exclude=('email',))
        self.assertNotIn('internal', self.names(table))
        self.assertNotIn('email', self.names(table))
        self.assertEqual(self.names(table), ['username', 'first_name', 'computed'])

    def test_new_and_removed_columns_are_safe_across_variants(self):
        self.configure({'hidden': ['retired'], 'order': ['retired', 'email', 'email', 'username']})
        self.assertEqual(self.names(ColumnFixtureTable([])), ['email', 'username', 'first_name', 'computed'])

    def test_opted_out_tables_ignore_overlay(self):
        class CustomTable(ColumnFixtureTable):
            class Meta(ColumnFixtureTable.Meta):
                template_name = 'project/custom-table.html'
        self.configure({'hidden': ['email'], 'order': ['computed']})
        self.assertIn('email', self.names(CustomTable([])))
        self.assertEqual(self.names(CustomTable([]))[0], 'username')

    def test_framework_columns_keep_their_positions_and_visibility(self):
        class ProtectedTable(ColumnFixtureTable):
            scope = tables.Column()
            created_at = tables.Column()
            deleted_at = tables.Column()
            class Meta(ColumnFixtureTable.Meta):
                pass
        self.configure({'hidden': ['scope', 'dlux_row_actions', 'created_at', 'deleted_at'],
                        'order': ['dlux_row_actions', 'scope', 'computed']}, row_actions_style='both')
        table = ProtectedTable([])
        self.assertEqual(self.names(table), ['computed', 'username', 'email', 'first_name', 'scope', 'dlux_row_actions'])
        self.assertNotIn('created_at', table.columns.names())
        self.assertNotIn('deleted_at', table.columns.names())

    def test_discovery_context_restores_after_failure(self):
        self.configure({'hidden': ['email']})
        with self.assertRaises(ValueError), baseline_table_columns():
            raise ValueError('broken table')
        self.assertNotIn('email', self.names(ColumnFixtureTable([])))

    def test_overlay_cannot_hide_permitted_audit_or_deletion_columns(self):
        from dlux.models import DluxNotification
        from dlux.system.constants import record_visibility_column_names
        from dlux.utils.crud import _build_generic_table_class
        from dlux.utils.authorization import audit_fields_visible, soft_deleted_visible

        user = get_user_model().objects.create_superuser('column-admin', 'columns@example.com', 'test-password')
        instance = SystemSettings.load()
        instance.is_configured = True
        instance.tables_config = {**instance.tables_config, 'show_audit_fields': True, 'show_soft_deleted': True,
            'columns': {DluxNotification._meta.label_lower: {
                'hidden': list(record_visibility_column_names()),
                'order': list(record_visibility_column_names()),
            }}}
        instance.save()
        clear_system_config_cache()
        self.assertTrue(audit_fields_visible(user), get_system_config().get('tables_config'))
        self.assertTrue(soft_deleted_visible(user))
        request = RequestFactory().get('/')
        request.user = user
        table_class = _build_generic_table_class(DluxNotification)
        with baseline_table_columns():
            baseline = table_class([], request=request)
        table = table_class([], request=request)
        self.assertEqual(self.names(table), self.names(baseline))
        self.assertIn('created_at', self.names(table))
        self.assertIn('deleted_at', self.names(table))

    def test_scope_exclusion_cannot_be_overridden_by_saved_order(self):
        from dlux.models import DluxNotification
        from dlux.utils.crud import _build_generic_table_class
        instance = SystemSettings.load()
        instance.tables_config = {'columns': {DluxNotification._meta.label_lower: {
            'order': ['scope', 'title'],
        }}}
        instance.save()
        clear_system_config_cache()
        with patch('dlux.utils.is_scope_enabled', return_value=False):
            table = _build_generic_table_class(DluxNotification)([])
        self.assertNotIn('scope', self.names(table))


class TableColumnDiscoveryTests(_TableColumnTestSupport, TestCase):
    def test_supplied_users_and_activity_tables_are_system_items(self):
        from dlux.tables import UserTable, UserActivityLogTable
        class Users(View):
            table_class = UserTable
        class Activity(View):
            table_class = UserActivityLogTable
        catalog = self.catalog([
            path('users/', Users.as_view(), name='users'),
            path('activity/', Activity.as_view(), name='activity'),
        ])
        self.assertEqual(len(catalog), 2)
        self.assertTrue(all(entry['is_system'] for entry in catalog))

    def test_generated_project_manager_remains_a_project_table(self):
        from dlux.tests.document_files_app.models import Paper
        from dlux.views.sections import DynamicModalManagerView
        catalog = self.catalog([path('papers/', DynamicModalManagerView.as_view(model=Paper), name='papers')])
        self.assertEqual(catalog[0]['key'], 'document_files_app.paper')
        self.assertFalse(catalog[0]['is_system'])

    def test_any_supplied_table_variant_marks_the_model_as_system(self):
        from dlux.tests.document_files_app.models import Paper
        class ProjectTable(DluxTable):
            __module__ = 'project.tables'
            class Meta(DluxTable.Meta):
                model = Paper
                fields = ('title',)
        class SuppliedTable(ProjectTable):
            __module__ = 'dlux.example.tables'
            class Meta(ProjectTable.Meta):
                pass
        class Project(View):
            table_class = ProjectTable
        class Supplied(View):
            table_class = SuppliedTable
        project = path('project/', Project.as_view(), name='project')
        supplied = path('supplied/', Supplied.as_view(), name='supplied')
        self.assertFalse(self.catalog([project])[0]['is_system'])
        for patterns in ([project, supplied], [supplied, project]):
            self.assertTrue(self.catalog(patterns)[0]['is_system'])

    def catalog(self, patterns):
        with patch('dlux.discovery.tables.get_resolver') as resolver, patch(
            'dlux.utils.sections.discover_section_models', return_value=[]
        ):
            resolver.return_value.url_patterns = patterns
            return table_column_catalog()

    def test_discovers_baseline_and_custom_labels_without_rows(self):
        self.configure({'hidden': ['email']})
        get_system_config()
        self.catalog([path('users/', ColumnFixtureView.as_view(), name='fixture_users')])
        with CaptureQueriesContext(connection) as queries:
            result = self.catalog([path('users/', ColumnFixtureView.as_view(), name='fixture_users')])
        self.assertFalse(any('auth_user' in query['sql'] for query in queries))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['key'], 'auth.user')
        self.assertEqual([item['name'] for item in result[0]['columns']], ['username', 'email', 'first_name', 'computed'])
        self.assertEqual(result[0]['columns'][-1]['label'], 'Computed label')

    def test_merges_variants_and_duplicate_routes_by_model(self):
        class Variant(ColumnFixtureTable):
            other = tables.Column(verbose_name='Other')
            class Meta(ColumnFixtureTable.Meta):
                pass
        class VariantView(View):
            table_class = Variant
        result = self.catalog([
            path('first/', ColumnFixtureView.as_view(), name='first'),
            path('second/', VariantView.as_view(), name='second'),
        ])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['routes'], ['first', 'second'])
        names = [item['name'] for item in result[0]['columns']]
        self.assertEqual(names.count('username'), 1)
        self.assertIn('other', names)

    def test_dynamic_table_class_receives_request_and_route_kwargs_are_skipped_safely(self):
        class DynamicView(View):
            def get_table_class(self):
                return ColumnFixtureTable
        result = self.catalog([path('users/<int:pk>/', DynamicView.as_view(), name='dynamic')])
        self.assertEqual(result[0]['routes'], ['dynamic'])

    def test_broken_host_logs_diagnostic_and_keeps_other_tables(self):
        class BrokenTable(ColumnFixtureTable):
            def __init__(self, *args, **kwargs):
                raise ValueError('missing project dependency')
        class BrokenView(View):
            table_class = BrokenTable
        with self.assertLogs('dlux', level='WARNING') as logs:
            result = self.catalog([
                path('broken/', BrokenView.as_view(), name='broken'),
                path('users/', ColumnFixtureView.as_view(), name='working'),
            ])
        self.assertEqual(result[0]['routes'], ['working'])
        self.assertIn('broken', '\n'.join(logs.output))

    @override_settings(DLUX_AUDIT_COLUMNS=('computed',))
    def test_project_audit_extensions_stay_out_of_catalog(self):
        result = self.catalog([path('users/', ColumnFixtureView.as_view(), name='users')])
        self.assertNotIn('computed', [item['name'] for item in result[0]['columns']])

    def test_generated_manager_and_section_tables_are_discovered(self):
        from dlux.views.sections import DynamicModalManagerView
        from dlux.utils.crud import _build_generic_table_class
        with patch('dlux.utils.sections.discover_section_models', return_value=[{
            'table_class': _build_generic_table_class(get_user_model()),
        }]), patch('dlux.discovery.tables.get_resolver') as resolver:
            resolver.return_value.url_patterns = [path('manage/', DynamicModalManagerView.as_view(
                model=get_user_model()), name='manager')]
            result = table_column_catalog()
        self.assertEqual(result[0]['routes'], ['manager', 'manage_sections'])

    def test_framework_columns_never_appear_as_configurable(self):
        table = ColumnFixtureTable([])
        self.assertNotIn('dlux_row_actions', [column.name for column in configurable_table_columns(table)])

    def test_blank_headers_get_translated_builder_labels_without_changing_table_headers(self):
        class BlankHeaderTable(ColumnFixtureTable):
            status_icon = tables.Column(verbose_name='')
            class Meta(ColumnFixtureTable.Meta):
                pass
        class BlankHeaderView(View):
            table_class = BlankHeaderTable
        with patch('dlux.translations.get_strings', return_value={'table_columns_status_icon': 'حالة الاتصال'}):
            result = self.catalog([path('users/', BlankHeaderView.as_view(), name='users')])
        self.assertEqual(next(item['label'] for item in result[0]['columns'] if item['name'] == 'status_icon'), 'حالة الاتصال')
        self.assertEqual(BlankHeaderTable([]).columns['status_icon'].header, '')

    def test_request_language_uses_model_qualified_translation(self):
        with patch('dlux.translations.get_current_language_code', return_value='ar'), patch(
            'dlux.translations.get_strings', return_value={
                'models_user': 'المستخدمون', 'tbl_user_email': 'البريد الإلكتروني',
            }
        ):
            result = self.catalog([path('users/', ColumnFixtureView.as_view(), name='users')])
        self.assertEqual(result[0]['label'], 'المستخدمون')
        self.assertEqual(next(item['label'] for item in result[0]['columns'] if item['name'] == 'email'), 'البريد الإلكتروني')

    def test_settings_form_catalog_is_lazy_and_reuses_discovery_result(self):
        from dlux.forms.system_settings import SystemSettingsForm
        from dlux.system.constants import SETUP_STEP_APPEARANCE
        request = RequestFactory().get('/', {'step': SETUP_STEP_APPEARANCE})
        with patch('dlux.discovery.tables.table_column_catalog', return_value=[{'key': 'auth.user'}]) as discover:
            form = SystemSettingsForm(instance=SystemSettings.load(), request=request, mode='edit')
            discover.assert_not_called()
            self.assertEqual(form.table_columns_catalog, [{'key': 'auth.user'}])
            self.assertEqual(form.table_columns_catalog, [{'key': 'auth.user'}])
            discover.assert_called_once_with(request=form.request)

    def test_builder_catalog_is_escaped_and_rendered_only_on_its_step(self):
        from dlux.forms.system_settings import SystemSettingsForm
        from dlux.system.constants import SETUP_STEP_TABLES, SETUP_STEP_APPEARANCE
        catalog = [{'key': 'auth.user', 'label': '<unsafe>\'"', 'columns': [{'name': 'email', 'label': '<b>Email</b>'}]}]
        with patch('dlux.discovery.tables.table_column_catalog', return_value=catalog):
            request = RequestFactory().get('/', {'step': SETUP_STEP_TABLES})
            form = SystemSettingsForm(instance=SystemSettings.load(), request=request, mode='edit')
            self.assertIn('data-table-column-builder', form.table_columns_builder_html)
            self.assertIn('&lt;unsafe&gt;', form.table_columns_builder_html)
            self.assertNotIn('<unsafe>', form.table_columns_builder_html)
            self.assertNotIn('<script', form.table_columns_builder_html)
            request = RequestFactory().get('/', {'step': SETUP_STEP_APPEARANCE})
            form = SystemSettingsForm(instance=SystemSettings.load(), request=request, mode='edit')
            self.assertEqual(form.table_columns_builder_html, '')


class TableColumnsNormalizationTests(SimpleTestCase):
    def test_header_and_sorting_preferences_are_defensive_and_sparse(self):
        overlay = {'headers': {
            'email': {'labels': {'en': ' Email ', 'ar': 'البريد', 'bad key': 'bad', 'de': 7}, 'icon': 'bi-envelope'},
            'invalid-name': {'icon': 'bi-lock'},
            'username': {'icon': 'bi-foo" onclick="bad'},
            'first_name': {'labels': {}, 'icon': ''},
        }, 'sorting': ['email', '-email', None, '-username', 'first_name']}
        result = normalize_tables_config({'columns': {'auth.user': overlay}})['columns']['auth.user']
        self.assertEqual(result, {'headers': {
            'email': {'labels': {'en': 'Email', 'ar': 'البريد'}, 'icon': 'bi-envelope'},
            'first_name': {'labels': {}, 'icon': ''},
        }, 'sorting': ['email', '-username']})
        self.assertEqual(normalize_tables_config({'columns': {'auth.user': {'headers': [], 'sorting': 'email'}}})['columns'], {})

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
        value = {'columns': {'auth.user': {
            'hidden': ['email'], 'order': ['username'], 'sorting': ['-username', 'email'],
            'headers': {'email': {'labels': {'en': 'Contact', 'ar': 'التواصل'}, 'icon': 'bi-envelope'}},
        }}}
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
        columns = {'auth.user': {
            'hidden': ['email'], 'order': ['username'], 'sorting': ['-username'],
            'headers': {'email': {'labels': {'en': 'Contact', 'ar': 'التواصل'}, 'icon': 'bi-envelope'}},
        }}
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
