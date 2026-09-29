import json
import re
import time
from unittest.mock import patch

from dlux.tests.harness import setup_test_environment
setup_test_environment()

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.template import Context, Template
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from dlux.forms import SystemSettingsForm
from dlux.models import SystemSettings
from dlux.system.constants import SETUP_STEP_EXTRAS, SETUP_STEP_BACKUPS
from dlux.system.weather import normalize_weather_config
from dlux.utils.import_export import apply_system_settings_import, export_system_settings_payload
from dlux.weather import WeatherUnavailable, api_key, current_weather, encrypt_api_key, get_weather_config

LOCATION = dict(name='Tripoli, LY', lat=32.8872, lon=13.1913)
BASE = {'system_names': '{"en":"System","ar":"System"}', 'home_url': '/dashboard/',
        'default_language': 'en', 'default_theme': 'light', 'allowed_themes': ['light'],
        'languages': '{}', 'translations_override': '{}', 'sidebar_config': '{"enabled":true,"entries":[]}'}


class WeatherTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.admin = get_user_model().objects.create_superuser(username='weather-admin', password='test-password')
        self.record = SystemSettings.load()
        self.record.is_configured = True
        self.record.extra_config = {'app': {'crm': {'keep': 7}}, 'scanlink': {'enabled': True}}
        self.record.save()

    def save_form(self, data, step=SETUP_STEP_EXTRAS):
        request = RequestFactory().get('/?step=' + str(step))
        request.user = self.admin
        form = SystemSettingsForm(data={**BASE, **data}, instance=SystemSettings.load(), request=request)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        return form

    def enable(self, **values):
        self.save_form(dict(weather_enabled='on', weather_api_key='test-secret',
                            weather_locations=json.dumps([LOCATION]), weather_placement='floating',
                            weather_display='combined', weather_units='metric', weather_corner='top-start', **values))
        return get_weather_config()

    def test_real_form_save_runtime_and_disable_preservation(self):
        config = self.enable()
        self.assertTrue(config['enabled'])
        self.assertEqual(api_key(config), 'test-secret')
        self.assertNotIn('test-secret', json.dumps(SystemSettings.load().extra_config))
        self.save_form({'weather_enabled': '', 'weather_api_key': 'ignored', 'weather_locations': 'bad'})
        disabled = get_weather_config()
        self.assertFalse(disabled['enabled'])
        self.assertEqual({**disabled, 'enabled': True}, config)
        self.assertEqual(SystemSettings.load().extra_config['app'], {'crm': {'keep': 7}})
        self.save_form({'weather_enabled': 'on', 'weather_locations': json.dumps(config['locations'])})
        self.assertTrue(get_weather_config()['enabled'])
        self.assertEqual(get_weather_config()['corner'], 'top-start')

    def test_other_step_preserves_weather_and_does_not_validate_its_post(self):
        config = self.enable()
        self.save_form({'weather_locations': 'bad', 'weather_placement': 'bogus'}, SETUP_STEP_BACKUPS)
        self.assertEqual(get_weather_config(), config)

    def test_bad_locations_and_missing_key_reject_enabled_form(self):
        form = SystemSettingsForm(data={**BASE, 'weather_enabled': 'on', 'weather_locations': '[{"name":"bad","lat":999,"lon":2}]'},
                                  instance=SystemSettings.load(), request=RequestFactory().get('/?step=' + str(SETUP_STEP_EXTRAS)))
        self.assertFalse(form.is_valid())
        self.assertIn('weather_locations', form.errors)
        self.assertIn('weather_api_key', form.errors)

    def test_export_import_roundtrip_excludes_key_and_preserves_destination_key(self):
        config = self.enable()
        payload = export_system_settings_payload()
        self.assertNotIn('encrypted_api_key', payload['settings']['extra_config']['weather'])
        self.assertNotIn('test-secret', json.dumps(payload))
        apply_system_settings_import(SystemSettings.load(), payload)
        self.assertEqual(get_weather_config(), config)
        payload['settings']['extra_config']['weather']['encrypted_api_key'] = encrypt_api_key('injected')
        apply_system_settings_import(SystemSettings.load(), payload)
        self.assertEqual(api_key(get_weather_config()), 'test-secret')

    def test_key_not_rendered_and_tag_gates_placements(self):
        request = RequestFactory().get('/')
        request.user = self.admin
        template = Template('{% load dlux_weather %}{% weather_widget variant="card" %}')
        context = Context({'request': request})
        self.assertEqual(template.render(context), '')
        config = self.enable()
        html = template.render(context)
        self.assertIn('dlux-weather--card', html)
        self.assertNotIn('test-secret', html)
        self.assertNotIn(config['encrypted_api_key'], html)
        self.assertIn('Tripoli, LY', html)
        self.assertEqual(Template('{% load dlux_weather %}{% weather_widget placement="titlebar" %}').render(context), '')
        self.assertIn('dlux-weather--floating', Template('{% load dlux_weather %}{% weather_widget placement="floating" %}').render(context))
        from django.contrib.auth.models import AnonymousUser
        request.user = AnonymousUser()
        self.assertEqual(template.render(context), '')

    def test_weather_endpoint_authorization_and_location_allowlist(self):
        url = reverse('weather_current')
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.admin)
        with patch('dlux.weather._request') as provider:
            self.assertEqual(self.client.get(url).status_code, 404)
            self.enable()
            self.assertEqual(self.client.get(url, {'location': 'unknown'}).status_code, 400)
            provider.assert_not_called()
        self.assertEqual(self.client.post(url).status_code, 405)

    def test_cache_shares_readings_and_stale_failure_is_marked(self):
        config = self.enable()
        location = config['locations'][0]
        now = time.time()
        response = {'main': {'temp': 28.2, 'feels_like': 29.5}, 'weather': [{'id': 800, 'description': 'clear sky', 'icon': '01d'}], 'dt': int(now)}
        with patch('dlux.weather._request', return_value=response) as provider:
            first = current_weather(config, location, 'en')
            second = current_weather(config, location, 'en')
            self.assertEqual(first, second)
            self.assertEqual(provider.call_count, 1)
        # Cache time is real; change only the weather clock to exercise expiry.
        with patch('dlux.weather.time.time', return_value=now + 901), patch('dlux.weather._request', side_effect=WeatherUnavailable('provider')):
            self.assertTrue(current_weather(config, location, 'en')['stale'])

    def test_search_only_admin_and_enabled_draft(self):
        url = reverse('weather_locations')
        user = get_user_model().objects.create_user(username='weather-reader')
        self.client.force_login(user)
        payload = dict(query='Tripoli', enabled=True, api_key='secret')
        self.assertEqual(self.client.post(url, payload, content_type='application/json').status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(url).status_code, 405)
        with patch('dlux.views.weather.search_locations', return_value=[LOCATION]) as provider:
            self.assertEqual(self.client.post(url, {**payload, 'enabled': False}, content_type='application/json').status_code, 400)
            provider.assert_not_called()
            response = self.client.post(url, payload, content_type='application/json')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['locations'][0]['name'], LOCATION['name'])
            self.assertEqual(self.client.post(url, payload, content_type='application/json').status_code, 429)

    def test_normalization_cannot_enable_string_false_or_nonfinite_coordinates(self):
        config = normalize_weather_config({'enabled': 'false', 'placement': 'navbar', 'locations': [{**LOCATION, 'lat': float('nan')}]})
        self.assertFalse(config['enabled'])
        self.assertEqual(config['locations'], [])
        self.assertEqual(config['placement'], 'titlebar')

    def test_secret_key_rotation_fails_closed(self):
        config = self.enable()
        with override_settings(SECRET_KEY='rotated'):
            self.assertEqual(api_key(config), '')

    def test_first_run_allows_admin_location_search(self):
        self.record.is_configured = False
        self.record.save()
        self.client.force_login(self.admin)
        with patch('dlux.views.weather.search_locations', return_value=[LOCATION]):
            response = self.client.post(reverse('weather_locations'),
                                        {'enabled': True, 'query': 'Tripoli', 'api_key': 'draft'},
                                        content_type='application/json')
        self.assertEqual(response.status_code, 200)

    def test_weather_is_a_titlebar_action_scoped_by_its_placement(self):
        # Titlebar keeps it in the bar under every hub style; User hub lets it
        # follow the hub, so the action rail picks it up in the actions layout.
        from dlux.context_processors import _weather_titlebar_action
        from dlux.system.constants import TITLEBAR_ACTIONS_ORDER
        self.assertIn('weather', TITLEBAR_ACTIONS_ORDER)
        config = self.enable()
        system = lambda **values: {'extra_config': {'weather': {**config, **values}}}
        for placement, scope in (('titlebar', 'shared'), ('user_hub', 'titlebar_actions'),
                                 ('floating', None), ('embed', None)):
            with self.subTest(placement=placement):
                action = _weather_titlebar_action(system(placement=placement), {})
                self.assertEqual(action and action['scope'], scope)
        self.assertIsNone(_weather_titlebar_action(system(enabled=False), {}))
        self.assertIsNone(_weather_titlebar_action({}, {}))

    def test_the_action_is_a_titlebar_button_and_the_picker_a_dlux_selector(self):
        config = self.enable()
        request = RequestFactory().get('/')
        request.user = self.admin
        with patch('dlux.weather.get_weather_config', return_value=config):
            html = Template('{% load dlux_weather %}{% weather_widget variant="action" %}').render(Context({'request': request}))
            second = Template('{% load dlux_weather %}{% weather_widget variant="action" %}').render(Context({'request': request}))
        self.assertIn('dlux-titlebar-btn dlux-titlebar-action', html)
        self.assertIn('data-dlux-selector', html)
        self.assertNotIn('<select', html)
        names = lambda markup: set(re.findall(r'name="(weather-[0-9a-f]+-location)"', markup))
        self.assertTrue(names(html) and names(html).isdisjoint(names(second)), 'each widget groups its own radios')

    def test_shell_slots_render_only_the_chosen_placement(self):
        config = self.enable()
        request = RequestFactory().get('/')
        request.user = self.admin
        context = Context({'request': request})
        with patch('dlux.weather.get_weather_config', return_value={**config, 'placement': 'user_hub'}):
            self.assertIn('data-weather-widget', Template('{% load dlux_weather %}{% weather_widget placement="user_hub" %}').render(context))
            self.assertEqual('', Template('{% load dlux_weather %}{% weather_widget placement="floating" %}').render(context))

    def test_provider_failures_are_bounded_and_do_not_leak_credentials(self):
        from urllib.error import HTTPError
        from dlux.weather import _request
        with patch('dlux.weather.build_opener') as opener:
            opener.return_value.open.side_effect = HTTPError('https://example.invalid/?appid=secret', 401, 'bad', {}, None)
            with self.assertRaisesRegex(WeatherUnavailable, '^credentials$'):
                _request('data/2.5/weather', 'secret', lat=1, lon=2)
            args, kwargs = opener.return_value.open.call_args
            self.assertTrue(args[0].startswith('https://api.openweathermap.org/data/2.5/weather?'))
            self.assertEqual(kwargs['timeout'], 4)
        config = self.enable()
        with patch('dlux.weather._request', side_effect=WeatherUnavailable('provider')) as provider:
            for _ in range(2):
                with self.assertRaises(WeatherUnavailable):
                    current_weather(config, config['locations'][0], 'en')
            self.assertEqual(provider.call_count, 1)

    def test_english_and_arabic_cover_dynamic_settings_labels(self):
        from dlux.forms.weather import CHOICES
        from dlux.translations import get_strings
        for language in ('en', 'ar'):
            strings = get_strings(language)
            for choices in CHOICES.values():
                for value, _ in choices:
                    self.assertTrue(strings.get('weather_' + value))
