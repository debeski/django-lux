from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django import forms
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from dlux import options
from dlux.models import SystemSettings

User = get_user_model()


class LimitForm(forms.Form):
    limit = forms.IntegerField(min_value=1, max_value=20)

    def __init__(self, *args, current_value=None, **kwargs):
        kwargs.pop('request', None)
        kwargs.pop('namespace', None)
        kwargs.pop('settings_definition', None)
        super().__init__(*args, **kwargs)

    def to_app_config(self, current_value=None):
        return {'limit': self.cleaned_data['limit']}


def register_store_group(visible=None):
    options.register_app_settings_group(
        id='proj.store', title='Store options', description='Store-wide settings', icon='bi-shop', order=40,
        visible=visible,
    )
    options.register_app_settings(
        namespace='proj.layout', title='Layout', group='proj.store', order=10,
        fields=[{'name': 'mode', 'type': 'choice', 'choices': [('grid', 'Grid'), ('table', 'Table')], 'default': 'grid'}],
    )
    options.register_app_settings(
        namespace='proj.till', title='Till', description='Walk-in sales', group='proj.store', order=20,
        form_class=LimitForm,
    )


class SettingsGroupRegistryTests(TestCase):
    def setUp(self):
        cache.clear()
        options.clear_registry()
        self.request = RequestFactory().get('/sys/options/')
        self.request.user = User.objects.create_superuser('group-root', 'group-root@example.com', 'pw')

    def tearDown(self):
        options.clear_registry()

    def test_grouped_settings_fold_into_one_tile(self):
        register_store_group()
        options.register_app_settings(namespace='proj.alone', title='Alone', order=50, fields=[{'name': 'x'}])
        tiles = options.get_visible_app_settings_tiles(self.request)
        self.assertEqual([(tile['kind'], tile['id']) for tile in tiles], [('group', 'proj.store'), ('settings', 'proj.alone')])
        self.assertEqual([section['namespace'] for section in tiles[0]['sections']], ['proj.layout', 'proj.till'])
        # The per-namespace registry is unchanged, so the single-tile URL and the
        # setup wizard still see every registration.
        self.assertEqual(len(options.get_visible_app_settings(self.request)), 3)

    def test_unknown_group_leaves_settings_on_their_own_tile(self):
        options.register_app_settings(namespace='proj.orphan', title='Orphan', group='proj.nowhere', fields=[{'name': 'x'}])
        tiles = options.get_visible_app_settings_tiles(self.request)
        self.assertEqual([(tile['kind'], tile['id']) for tile in tiles], [('settings', 'proj.orphan')])

    def test_group_visibility_fails_closed_and_empty_groups_show_no_tile(self):
        def boom(request):
            raise RuntimeError('bad config')
        register_store_group(visible=boom)
        self.assertEqual(options.get_visible_app_settings_tiles(self.request), [])
        options.clear_registry()
        options.register_app_settings_group(id='proj.empty', title='Empty')
        self.assertEqual(options.get_visible_app_settings_tiles(self.request), [])

    def test_rejects_invalid_group_registrations(self):
        with self.assertRaises(ValueError):
            options.register_app_settings_group(id='bad/id', title='Bad')
        with self.assertRaises(ValueError):
            options.register_app_settings_group(id='proj.ok', title='')
        with self.assertRaises(ValueError):
            options.register_app_settings(namespace='proj.x', title='X', group='bad/group', fields=[{'name': 'x'}])


class SettingsGroupModalTests(TestCase):
    def setUp(self):
        cache.clear()
        options.clear_registry()
        ss = SystemSettings.load()
        ss.is_configured = True
        ss.extra_config = {'app': {'proj.layout': {'legacy': 'keep'}, 'other.ns': {'x': 1}}}
        ss.save()
        self.superuser = User.objects.create_superuser('group-admin', 'group-admin@example.com', 'pw12345!')
        self.client = Client()
        self.client.force_login(self.superuser)
        self.url = reverse('dlux_app_settings_group_modal', kwargs={'group_id': 'proj.store'})
        register_store_group()

    def tearDown(self):
        options.clear_registry()

    def post(self, data):
        return self.client.post(self.url, data, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

    def test_options_page_shows_one_tile_for_the_group(self):
        body = self.client.get('/sys/options/').content.decode()
        self.assertIn(self.url, body)
        self.assertIn('Store options', body)
        self.assertNotIn(reverse('dlux_app_settings_modal', kwargs={'namespace': 'proj.till'}), body)

    def test_modal_renders_every_section_with_prefixed_fields_and_the_guard(self):
        html = self.client.get(self.url, HTTP_X_REQUESTED_WITH='XMLHttpRequest').json()['html']
        self.assertEqual(html.count("fw-bold my-3"), 2)
        self.assertIn('Walk-in sales', html)
        self.assertIn('name="app__proj_layout-mode"', html)
        self.assertIn('name="app__proj_till-limit"', html)
        self.assertIn('data-dlux-unsaved-guard', html)

    def test_save_writes_every_section_in_one_save_and_keeps_other_keys(self):
        saves = []
        original = SystemSettings.save

        def counting_save(instance, *args, **kwargs):
            saves.append(1)
            return original(instance, *args, **kwargs)

        SystemSettings.save = counting_save
        try:
            response = self.post({'app__proj_layout-mode': 'table', 'app__proj_till-limit': '7'})
        finally:
            SystemSettings.save = original
        self.assertTrue(response.json()['success'])
        self.assertEqual(len(saves), 1)
        cache.clear()
        app = SystemSettings.load().extra_config['app']
        self.assertEqual(app['proj.layout'], {'legacy': 'keep', 'mode': 'table'})
        self.assertEqual(app['proj.till'], {'limit': 7})
        self.assertEqual(app['other.ns'], {'x': 1})

    def test_one_invalid_section_saves_nothing(self):
        response = self.post({'app__proj_layout-mode': 'table', 'app__proj_till-limit': '99'})
        self.assertNotIn('success', response.json())
        cache.clear()
        app = SystemSettings.load().extra_config['app']
        self.assertEqual(app['proj.layout'], {'legacy': 'keep'})
        self.assertNotIn('proj.till', app)

    def test_a_section_still_opens_on_its_own(self):
        url = reverse('dlux_app_settings_modal', kwargs={'namespace': 'proj.till'})
        self.assertEqual(self.client.get(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest').status_code, 200)

    def test_group_modal_requires_superuser_and_a_known_group(self):
        regular = User.objects.create_user('group-joe', 'group-joe@example.com', 'pw12345!')
        client = Client()
        client.force_login(regular)
        self.assertEqual(client.get(self.url, HTTP_X_REQUESTED_WITH='XMLHttpRequest').status_code, 403)
        missing = reverse('dlux_app_settings_group_modal', kwargs={'group_id': 'proj.missing'})
        self.assertEqual(self.client.get(missing, HTTP_X_REQUESTED_WITH='XMLHttpRequest').status_code, 404)
