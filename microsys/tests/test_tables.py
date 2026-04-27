from django.conf import settings

if not settings.configured:
    settings.configure(
        SECRET_KEY='microsys-test-key',
        ALLOWED_HOSTS=['testserver', 'localhost'],
        INSTALLED_APPS=[
            'django.contrib.auth',
            'django.contrib.contenttypes',
            'django.contrib.sessions',
            'django.contrib.messages',
            'django.contrib.staticfiles',
            'crispy_forms',
            'crispy_bootstrap5',
            'django_filters',
            'django_tables2',
            'microsys',
        ],
        MIDDLEWARE=[
            'django.contrib.sessions.middleware.SessionMiddleware',
            'django.contrib.auth.middleware.AuthenticationMiddleware',
            'microsys.middleware.ActivityLogMiddleware',
        ],
        ROOT_URLCONF='microsys.urls',
        TEMPLATES=[
            {
                'BACKEND': 'django.template.backends.django.DjangoTemplates',
                'APP_DIRS': True,
                'OPTIONS': {
                    'context_processors': [
                        'django.template.context_processors.request',
                        'django.contrib.auth.context_processors.auth',
                        'django.contrib.messages.context_processors.messages',
                        'microsys.context_processors.microsys_context',
                    ],
                },
            }
        ],
        DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}},
        STATIC_URL='/static/',
        DEFAULT_AUTO_FIELD='django.db.models.BigAutoField',
        USE_TZ=True,
        CRISPY_ALLOWED_TEMPLATE_PACKS='bootstrap5',
        CRISPY_TEMPLATE_PACK='bootstrap5',
    )

    import django

    django.setup()

import json

import django_tables2 as tables
from django.contrib.auth import get_user_model
from django.template import Context, Template
from django.test import RequestFactory, TestCase

from microsys.constants import DEFAULT_TABLE_PAGE_SIZE
from microsys.tables import MicrosysTable, UserTable
from microsys.utils import _build_generic_table_class

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
        microsys_table = False


class DenseHostTable(tables.Table):
    class Meta:
        model = User
        fields = ('username',)
        microsys_density = 'dense'


class FixedPageSizeTable(MicrosysTable):
    class Meta(MicrosysTable.Meta):
        model = User
        fields = ('username',)
        microsys_per_page = 50


class ActionlessTable(MicrosysTable):
    class Meta(MicrosysTable.Meta):
        model = User
        fields = ('username',)
        microsys_actions = False


class ExtendedActionsTable(MicrosysTable):
    class Meta(MicrosysTable.Meta):
        model = User
        fields = ('username',)

    def get_microsys_row_actions(self, record, base_actions):
        base_actions.append({
            'label': 'custom_action',
            'icon': 'bi bi-stars',
            'type': 'event',
            'event': 'micro:record:custom',
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

    def test_builtin_table_uses_microsys_template(self):
        table = UserTable(User.objects.filter(pk=self.user.pk), request=self._request())

        self.assertEqual(table.template_name, 'microsys/tables/table.html')
        self.assertIn('ms-data-table', table.attrs.get('class', ''))

    def test_host_table_without_template_is_auto_captured(self):
        table = AutoCapturedHostTable(User.objects.filter(pk=self.user.pk), request=self._request())

        self.assertEqual(table.template_name, 'microsys/tables/table.html')

    def test_host_table_with_stock_template_is_auto_captured(self):
        table = StockTemplateHostTable(User.objects.filter(pk=self.user.pk), request=self._request())

        self.assertEqual(table.template_name, 'microsys/tables/table.html')

    def test_custom_template_is_left_untouched(self):
        table = CustomTemplateHostTable(User.objects.filter(pk=self.user.pk), request=self._request())

        self.assertEqual(table.template_name, 'project/custom_table.html')
        self.assertNotIn('ms-data-table', table.attrs.get('class', ''))

    def test_microsys_table_false_opts_out(self):
        table = OptOutHostTable(User.objects.filter(pk=self.user.pk), request=self._request())

        self.assertEqual(table.template_name, 'django_tables2/bootstrap5.html')
        self.assertNotIn('ms-data-table', table.attrs.get('class', ''))

    def test_density_resolution_prefers_table_meta_then_user_pref(self):
        dense_table = DenseHostTable(User.objects.filter(pk=self.user.pk), request=self._request())
        roomy_table = AutoCapturedHostTable(User.objects.filter(pk=self.user.pk), request=self._request())

        self.assertEqual(dense_table.microsys_density, 'dense')
        self.assertEqual(roomy_table.microsys_density, 'roomy')

    def test_generic_auto_table_is_auto_captured_and_uses_microsys_base(self):
        table_class = _build_generic_table_class(self.user.profile.__class__)
        table = table_class(self.user.profile.__class__.objects.none(), request=self._request())

        self.assertTrue(issubclass(table_class, MicrosysTable))
        self.assertEqual(table.template_name, 'microsys/tables/table.html')
        self.assertEqual(table.microsys_per_page, DEFAULT_TABLE_PAGE_SIZE)

    def test_rendered_table_uses_microsys_shell_and_density_attribute(self):
        table = AutoCapturedHostTable(User.objects.filter(pk=self.user.pk), request=self._request())
        template = Template('{% load django_tables2 %}{% render_table table %}')
        html = template.render(Context({'table': table, 'request': self._request()}))

        self.assertIn('ms-table-shell', html)
        self.assertIn('data-ms-table-density="roomy"', html)

    def test_rendered_table_outputs_dynamic_sort_querystring(self):
        request = self._request('page=3')
        table = AutoCapturedHostTable(User.objects.order_by('username'), request=request)
        template = Template('{% load django_tables2 %}{% render_table table %}')
        html = template.render(Context({'table': table, 'request': request}))

        self.assertIn('?page=3&amp;sort=-username', html)

    def test_rendered_table_outputs_per_page_options_and_resets_page(self):
        request = self._request('page=3&sort=username')
        table = AutoCapturedHostTable(User.objects.order_by('username'), request=request)
        template = Template('{% load django_tables2 %}{% render_table table %}')
        html = template.render(Context({'table': table, 'request': request}))

        self.assertIn('ms-table-page-size__option', html)
        self.assertIn('data-ms-table-density-inline', html)
        self.assertIn('data-ms-table-density-option="balanced"', html)
        self.assertIn('?sort=username&amp;per_page=50', html)
        self.assertNotIn('?page=3&amp;sort=username&amp;per_page=50', html)

    def test_forced_density_tables_do_not_render_footer_density_picker(self):
        request = self._request()
        table = DenseHostTable(User.objects.order_by('username'), request=request)
        template = Template('{% load django_tables2 %}{% render_table table %}')
        html = template.render(Context({'table': table, 'request': request}))

        self.assertIn('data-ms-table-density="dense"', html)
        self.assertIn('data-ms-table-density-locked="true"', html)
        self.assertNotIn('data-ms-table-density-inline', html)

    def test_request_per_page_overrides_saved_preference_and_persists(self):
        request = self._request('per_page=100')
        table = AutoCapturedHostTable(User.objects.order_by('username'), request=request)

        self.assertEqual(table.microsys_per_page, 100)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.preferences.get('table_page_size'), 100)

    def test_invalid_request_per_page_falls_back_to_saved_preference(self):
        self.user.profile.preferences = {'table_density': 'roomy', 'table_page_size': 50}
        self.user.profile.save(update_fields=['preferences'])

        table = AutoCapturedHostTable(User.objects.order_by('username'), request=self._request('per_page=15'))

        self.assertEqual(table.microsys_per_page, 50)

    def test_table_meta_per_page_override_beats_request_and_saved_preference(self):
        self.user.profile.preferences = {'table_page_size': 100}
        self.user.profile.save(update_fields=['preferences'])

        table = FixedPageSizeTable(User.objects.order_by('username'), request=self._request('per_page=10'))

        self.assertEqual(table.microsys_per_page, 50)

    def test_default_actions_are_auto_wired_for_superuser(self):
        request = self._request(user=self.superuser)
        table = AutoCapturedHostTable(User.objects.filter(pk=self.user.pk), request=request)
        actions = json.loads(table.row_attrs['data-micro-actions'](self.user))

        self.assertEqual(
            [action.get('event') for action in actions if action.get('type') == 'event'],
            ['micro:record:view', 'micro:record:edit', 'micro:record:delete'],
        )
        self.assertEqual(actions[1].get('type'), 'divider')

    def test_default_actions_filter_permissions_and_trim_dividers(self):
        request = self._request(user=self.user)
        table = AutoCapturedHostTable(User.objects.filter(pk=self.user.pk), request=request)
        actions = json.loads(table.row_attrs['data-micro-actions'](self.user))

        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].get('event'), 'micro:record:view')

    def test_custom_row_actions_extend_base_actions(self):
        request = self._request(user=self.superuser)
        table = ExtendedActionsTable(User.objects.filter(pk=self.user.pk), request=request)
        actions = json.loads(table.row_attrs['data-micro-actions'](self.user))

        self.assertEqual(actions[-1].get('event'), 'micro:record:custom')

    def test_microsys_actions_false_disables_default_action_wiring(self):
        table = ActionlessTable(User.objects.filter(pk=self.user.pk), request=self._request())

        self.assertNotIn('data-micro-actions', table.row_attrs)
