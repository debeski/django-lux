from dlux.tests.harness import setup_test_environment

setup_test_environment()

import json
from pathlib import Path

import django_tables2 as tables
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.template import Context, Template
from django.test import RequestFactory, TestCase
from django.urls import reverse

from dlux.system.constants import DEFAULT_TABLE_PAGE_SIZE
from dlux.tables import DluxTable, UserTable
from dlux.utils import _build_generic_table_class

User = get_user_model()


class AutoCapturedHostTable(tables.Table):
    class Meta:
        model = User
        fields = ('username',)


class StockTemplateHostTable(tables.Table):
    class Meta:
        model = User
        fields = ('username',)
        template_name = 'django_tables2/bootstrap5.html'


class CustomTemplateHostTable(tables.Table):
    class Meta:
        model = User
        fields = ('username',)
        template_name = 'project/custom_table.html'


class OptOutHostTable(tables.Table):
    class Meta:
        model = User
        fields = ('username',)
        template_name = 'django_tables2/bootstrap5.html'
        dlux_table = False


class DenseHostTable(tables.Table):
    class Meta:
        model = User
        fields = ('username',)
        dlux_density = 'dense'


class FixedPageSizeTable(DluxTable):
    class Meta(DluxTable.Meta):
        model = User
        fields = ('username',)
        dlux_per_page = 50


class ActionlessTable(DluxTable):
    class Meta(DluxTable.Meta):
        model = User
        fields = ('username',)
        dlux_actions = False


class FooterlessTable(DluxTable):
    class Meta(DluxTable.Meta):
        model = User
        fields = ('username',)
        dlux_show_footer = False


class NonResizableTable(DluxTable):
    class Meta(DluxTable.Meta):
        model = User
        fields = ('username', 'email')
        dlux_resizable_columns = False


class ExtendedActionsTable(DluxTable):
    class Meta(DluxTable.Meta):
        model = User
        fields = ('username',)

    def get_dlux_row_actions(self, record, base_actions):
        base_actions.append({
            'label': 'custom_action',
            'icon': 'bi bi-stars',
            'type': 'event',
            'event': 'dlux:record:custom',
            'data': {'id': record.pk},
        })
        return base_actions


class TableRenderingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='tableuser',
            email='table@example.com',
            password='tablepass123',
        )
        cls.superuser = User.objects.create_superuser(
            username='tablesuper',
            email='tablesuper@example.com',
            password='tablepass123',
        )
        extra_users = [
            User(username=f'bulkuser{index}', email=f'bulkuser{index}@example.com')
            for index in range(1, 31)
        ]
        User.objects.bulk_create(extra_users)
        cls.global_staff = User.objects.create_user(
            username='tableglobal',
            email='tableglobal@example.com',
            password='tablepass123',
            is_staff=True,
        )
        profile_type = ContentType.objects.get(app_label='dlux', model='profile')
        cls.global_staff.user_permissions.add(
            Permission.objects.get(content_type=profile_type, codename='manage_scopes'),
            Permission.objects.get(content_type=profile_type, codename='manage_staff'),
        )

    def setUp(self):
        self.factory = RequestFactory()
        self.user.profile.preferences = {'table_density': 'roomy', 'table_page_size': 20}
        self.user.profile.save(update_fields=['preferences'])
        self.superuser.profile.preferences = {}
        self.superuser.profile.save(update_fields=['preferences'])

    def _request(self, query_string='', user=None):
        path = '/'
        if query_string:
            path = f'/?{query_string}'
        request = self.factory.get(path)
        request.user = user or self.user
        request.session = {}
        return request

    def test_builtin_table_uses_dlux_template(self):
        table = UserTable(User.objects.filter(pk=self.user.pk), request=self._request())

        self.assertEqual(table.template_name, 'dlux/tables/table.html')
        self.assertIn('dlux-data-table', table.attrs.get('class', ''))

    def test_host_table_without_template_is_auto_captured(self):
        table = AutoCapturedHostTable(User.objects.filter(pk=self.user.pk), request=self._request())

        self.assertEqual(table.template_name, 'dlux/tables/table.html')

    def test_host_table_with_stock_template_is_auto_captured(self):
        table = StockTemplateHostTable(User.objects.filter(pk=self.user.pk), request=self._request())

        self.assertEqual(table.template_name, 'dlux/tables/table.html')

    def test_custom_template_is_left_untouched(self):
        table = CustomTemplateHostTable(User.objects.filter(pk=self.user.pk), request=self._request())

        self.assertEqual(table.template_name, 'project/custom_table.html')
        self.assertNotIn('dlux-data-table', table.attrs.get('class', ''))

    def test_dlux_table_false_opts_out(self):
        table = OptOutHostTable(User.objects.filter(pk=self.user.pk), request=self._request())

        self.assertEqual(table.template_name, 'django_tables2/bootstrap5.html')
        self.assertNotIn('dlux-data-table', table.attrs.get('class', ''))

    def test_density_resolution_prefers_table_meta_then_user_pref(self):
        dense_table = DenseHostTable(User.objects.filter(pk=self.user.pk), request=self._request())
        roomy_table = AutoCapturedHostTable(User.objects.filter(pk=self.user.pk), request=self._request())

        self.assertEqual(dense_table.dlux_density, 'dense')
        self.assertEqual(roomy_table.dlux_density, 'roomy')

    def test_generic_auto_table_is_auto_captured_and_uses_dlux_base(self):
        table_class = _build_generic_table_class(self.user.profile.__class__)
        table = table_class(self.user.profile.__class__.objects.none(), request=self._request())

        self.assertTrue(issubclass(table_class, DluxTable))
        self.assertEqual(table.template_name, 'dlux/tables/table.html')
        self.assertEqual(table.dlux_per_page, DEFAULT_TABLE_PAGE_SIZE)

    def test_rendered_table_uses_dlux_shell_and_density_attribute(self):
        table = AutoCapturedHostTable(User.objects.filter(pk=self.user.pk), request=self._request())
        template = Template('{% load django_tables2 %}{% render_table table %}')
        html = template.render(Context({'table': table, 'request': self._request()}))

        self.assertIn('dlux-table-shell', html)
        self.assertIn('data-dlux-table-density="roomy"', html)

    def test_rendered_table_outputs_column_resize_markup(self):
        table = UserTable(User.objects.filter(pk=self.user.pk), request=self._request())
        template = Template('{% load django_tables2 %}{% render_table table %}')
        html = template.render(Context({'table': table, 'request': self._request()}))

        self.assertIn('data-dlux-table-resizable="true"', html)
        self.assertRegex(html, r'data-dlux-table-key="[a-f0-9]{20}"')
        self.assertIn('<col data-dlux-table-col="username">', html)
        self.assertIn('data-dlux-table-resize-handle', html)
        self.assertIn('tabindex="0"', html)

    def test_table_meta_can_disable_column_resize_markup(self):
        table = NonResizableTable(User.objects.filter(pk=self.user.pk), request=self._request())
        template = Template('{% load django_tables2 %}{% render_table table %}')
        html = template.render(Context({'table': table, 'request': self._request()}))

        self.assertIn('data-dlux-table-resizable="false"', html)
        self.assertNotIn('data-dlux-table-resize-handle', html)

    def test_column_resize_assets_keep_resized_tables_contained(self):
        static_root = Path(__file__).resolve().parents[1] / 'static' / 'dlux' / 'base'
        script = (static_root.parent / 'tables' / 'js' / 'main.js').read_text(encoding='utf-8')
        stylesheet = (static_root.parent / 'tables' / 'css' / 'main.css').read_text(encoding='utf-8')

        self.assertIn('function redistributeColumnWidths(', script)
        self.assertIn("cols[index].style.width = `${(width / totalWidth) * 100}%`;", script)
        self.assertNotIn("style.minWidth =", script)
        self.assertIn('.dlux-data-table.is-dlux-column-resized {', stylesheet)
        self.assertIn('table-layout: fixed;', stylesheet)
        self.assertNotIn('var(--dlux-table-width', stylesheet)
        self.assertIn('background: var(--dlux-table-border-strong);', stylesheet)
        self.assertIn(
            '.dlux-data-table.is-dlux-column-resized > tbody > tr > :is(td, th):not(:has(.dropdown-menu)) {',
            stylesheet,
        )
        self.assertIn('text-overflow: ellipsis;', stylesheet)

    def test_rendered_table_outputs_dynamic_sort_querystring(self):
        request = self._request('page=3')
        table = AutoCapturedHostTable(User.objects.order_by('username'), request=request)
        template = Template('{% load django_tables2 %}{% render_table table %}')
        html = template.render(Context({'table': table, 'request': request}))

        self.assertIn('?page=3&amp;sort=-username', html)

    def test_user_table_renders_staff_tier_badges(self):
        table = UserTable(User.objects.filter(pk=self.global_staff.pk), request=self._request())
        html = Template('{% load django_tables2 %}{% render_table table %}').render(
            Context({'table': table, 'request': self._request()})
        )

        self.assertIn('Global Staff', html)
        self.assertIn('Can Assign Staff Roles', html)
        self.assertIn('dlux-staff-tier-badge--global_staff', html)
        self.assertIn('dlux-staff-tier-badge--delegate', html)

    def test_model_qualified_header_overrides_generic(self):
        # The User table's is_active column resolves the model-qualified key
        # tbl_user_is_active in preference to the generic tbl_is_active.
        table = UserTable(User.objects.none(), request=self._request())
        header = str(table.columns['is_active'].column.verbose_name)
        self.assertIn(header, ('Account Active', 'حساب نشط'))
        self.assertNotIn(header, ('Active', 'نشط'))

    def test_generic_header_still_used_when_no_qualified_key(self):
        # A column without a model-qualified key falls back to the generic one.
        table = UserTable(User.objects.none(), request=self._request())
        header = str(table.columns['username'].column.verbose_name)
        self.assertIn(header, ('Username', 'اسم المستخدم'))

    def test_rendered_table_outputs_per_page_options_and_resets_page(self):
        request = self._request('page=3&sort=username')
        table = AutoCapturedHostTable(User.objects.order_by('username'), request=request)
        template = Template('{% load django_tables2 %}{% render_table table %}')
        html = template.render(Context({'table': table, 'request': request}))

        self.assertIn('dlux-table-page-size__option', html)
        self.assertIn('data-dlux-table-density-inline', html)
        self.assertIn('data-dlux-table-density-option="balanced"', html)
        self.assertIn('?sort=username&amp;per_page=50', html)
        self.assertNotIn('?page=3&amp;sort=username&amp;per_page=50', html)

    def test_forced_density_tables_do_not_render_footer_density_picker(self):
        request = self._request()
        table = DenseHostTable(User.objects.order_by('username'), request=request)
        template = Template('{% load django_tables2 %}{% render_table table %}')
        html = template.render(Context({'table': table, 'request': request}))

        self.assertIn('data-dlux-table-density="dense"', html)
        self.assertIn('data-dlux-table-density-locked="true"', html)
        self.assertNotIn('data-dlux-table-density-inline', html)

    def test_manager_tables_point_their_rows_at_the_managers_own_surfaces(self):
        from dlux.patches import _build_default_dlux_actions

        table = AutoCapturedHostTable(User.objects.filter(pk=self.user.pk), request=self._request())
        table.dlux_modal_manager_url = '/sys/modals/people/'
        actions = _build_default_dlux_actions(table, self.user)

        by_label = {action.get('label'): action for action in actions if action.get('label')}
        self.assertEqual(by_label['view_label']['event'], 'dlux:dynamic_modal:open')
        self.assertEqual(
            by_label['view_label']['data']['url'],
            f'/sys/modals/people/?id={self.user.pk}&action=view',
        )
        self.assertEqual(by_label['edit_label']['event'], 'dlux:dynamic_modal:open')
        self.assertEqual(by_label['edit_label']['data']['url'], f'/sys/modals/people/?id={self.user.pk}')
        self.assertEqual(by_label['delete_label']['event'], 'dlux:record:delete')
        self.assertEqual(
            by_label['delete_label']['data']['delete_url'],
            reverse('modal_delete', args=['auth', 'User', self.user.pk]),
        )

    def test_section_manager_base_actions_opt_into_section_permissions(self):
        table = FixedPageSizeTable(User.objects.filter(pk=self.user.pk), request=self._request())
        table.dlux_modal_manager_url = '/sys/modals/people/'
        table.dlux_section_actions = True

        actions = table.get_dlux_base_actions(self.user)
        by_label = {action.get('label'): action for action in actions if action.get('label')}

        self.assertTrue(by_label['edit_label']['section_action'])
        self.assertTrue(by_label['delete_label']['section_action'])
        self.assertEqual(
            by_label['delete_label']['data']['delete_url'],
            reverse('modal_delete', args=['auth', 'User', self.user.pk]),
        )

    def test_rows_outside_a_manager_keep_the_record_events(self):
        from dlux.patches import _build_default_dlux_actions

        table = AutoCapturedHostTable(User.objects.filter(pk=self.user.pk), request=self._request())
        events = {action.get('event') for action in _build_default_dlux_actions(table, self.user)}

        self.assertEqual(events, {'dlux:record:view', 'dlux:record:edit', 'dlux:record:delete', None})

    def test_meta_opt_out_drops_the_footer_and_paginates_nothing(self):
        request = self._request()
        table = FooterlessTable(User.objects.order_by('username'), request=request)
        template = Template('{% load django_tables2 %}{% render_table table %}')
        html = template.render(Context({'table': table, 'request': request}))

        self.assertFalse(table.dlux_show_footer)
        self.assertNotIn('dlux-table-footer', html)
        self.assertNotIn('dlux-table-page-size', html)
        self.assertEqual(len(table.paginated_rows), User.objects.count())

    def test_footer_opt_out_kwarg_survives_a_later_paginating_configure(self):
        import django_tables2 as tables2

        request = self._request()
        table = AutoCapturedHostTable(
            User.objects.order_by('username'),
            request=request,
            dlux_show_footer=False,
        )
        tables2.RequestConfig(request).configure(table)
        template = Template('{% load django_tables2 %}{% render_table table %}')
        html = template.render(Context({'table': table, 'request': request}))

        self.assertNotIn('dlux-table-footer', html)
        self.assertEqual(len(table.paginated_rows), User.objects.count())

    def test_request_per_page_overrides_saved_preference_and_persists(self):
        request = self._request('per_page=100')
        table = AutoCapturedHostTable(User.objects.order_by('username'), request=request)

        self.assertEqual(table.dlux_per_page, 100)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.preferences.get('table_page_size'), 100)

    def test_builtin_table_request_per_page_is_not_masked_by_base_default(self):
        request = self._request('per_page=50')
        table = UserTable(User.objects.order_by('username'), request=request)
        template = Template('{% load django_tables2 %}{% render_table table %}')
        html = template.render(Context({'table': table, 'request': request}))

        self.assertEqual(table.dlux_per_page, 50)
        self.assertRegex(html, r'dlux-table-page-size__option is-active[\s\S]*?>\s*50\s*</a>')

    def test_invalid_request_per_page_falls_back_to_saved_preference(self):
        self.user.profile.preferences = {'table_density': 'roomy', 'table_page_size': 50}
        self.user.profile.save(update_fields=['preferences'])

        table = AutoCapturedHostTable(User.objects.order_by('username'), request=self._request('per_page=15'))

        self.assertEqual(table.dlux_per_page, 50)

    def test_table_meta_per_page_override_beats_request_and_saved_preference(self):
        self.user.profile.preferences = {'table_page_size': 100}
        self.user.profile.save(update_fields=['preferences'])

        table = FixedPageSizeTable(User.objects.order_by('username'), request=self._request('per_page=10'))

        self.assertEqual(table.dlux_per_page, 50)

    def test_default_actions_are_auto_wired_for_superuser(self):
        request = self._request(user=self.superuser)
        table = AutoCapturedHostTable(User.objects.filter(pk=self.user.pk), request=request)
        actions = json.loads(table.row_attrs['data-dlux-actions'](self.user))

        self.assertEqual(
            [action.get('event') for action in actions if action.get('type') == 'event'],
            ['dlux:record:view', 'dlux:record:edit', 'dlux:record:delete'],
        )
        self.assertEqual(actions[1].get('type'), 'divider')

    def test_default_actions_filter_permissions_and_trim_dividers(self):
        request = self._request(user=self.user)
        table = AutoCapturedHostTable(User.objects.filter(pk=self.user.pk), request=request)
        actions = json.loads(table.row_attrs['data-dlux-actions'](self.user))

        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].get('event'), 'dlux:record:view')

    def test_custom_row_actions_extend_base_actions(self):
        request = self._request(user=self.superuser)
        table = ExtendedActionsTable(User.objects.filter(pk=self.user.pk), request=request)
        actions = json.loads(table.row_attrs['data-dlux-actions'](self.user))

        self.assertEqual(actions[-1].get('event'), 'dlux:record:custom')

    def test_dlux_actions_false_disables_default_action_wiring(self):
        table = ActionlessTable(User.objects.filter(pk=self.user.pk), request=self._request())

        self.assertNotIn('data-dlux-actions', table.row_attrs)
