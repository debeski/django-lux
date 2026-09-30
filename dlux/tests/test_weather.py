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

    @override_settings(DEBUG=True)  # a development server makes the call itself
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
        with patch('dlux.views.weather.find_locations', return_value=[LOCATION]) as provider:
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
        with patch('dlux.views.weather.find_locations', return_value=[LOCATION]):
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

    @override_settings(DEBUG=True)
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

    def test_unreachable_network_is_reported_apart_from_provider_errors(self):
        from urllib.error import HTTPError, URLError
        import socket
        from dlux.weather import _request
        cases = [
            (URLError(socket.gaierror(-3, 'Temporary failure in name resolution')), 'network'),
            (TimeoutError(), 'network'),
            (ConnectionRefusedError(), 'network'),
            (HTTPError('https://example.invalid/', 500, 'boom', {}, None), 'provider'),
        ]
        for error, expected in cases:
            with self.subTest(error=type(error).__name__), patch('dlux.weather.build_opener') as opener:
                opener.return_value.open.side_effect = error
                with self.assertRaisesRegex(WeatherUnavailable, f'^{expected}$'):
                    _request('data/2.5/weather', 'secret', lat=1, lon=2)
        with patch('dlux.weather.build_opener') as opener:
            opener.return_value.open.return_value.__enter__.return_value.read.return_value = b'not json'
            with self.assertRaisesRegex(WeatherUnavailable, '^provider$'):
                _request('data/2.5/weather', 'secret', lat=1, lon=2)

    def test_english_and_arabic_cover_dynamic_settings_labels(self):
        from dlux.forms.weather import CHOICES
        from dlux.translations import get_strings
        for language in ('en', 'ar'):
            strings = get_strings(language)
            for choices in CHOICES.values():
                for value, _ in choices:
                    self.assertTrue(strings.get('weather_' + value))


class WeatherWorkerTests(TestCase):
    """In a generated stack web cannot reach the internet; a Celery worker can.

    The worker is faked by running its task function when web sends the task,
    or by not running it at all, which is what a missing worker looks like.
    """

    setUp = WeatherTests.setUp
    save_form = WeatherTests.save_form
    enable = WeatherTests.enable

    def worker(self, run=True):
        from unittest.mock import MagicMock
        from dlux import weather

        app = MagicMock()

        def send_task(name, args, retry=False):
            if not run:
                return
            if name == 'dlux.tasks.weather_refresh':
                try:
                    weather.refresh_reading(*args)
                except WeatherUnavailable:
                    pass
            elif name == 'dlux.tasks.weather_search':
                weather.run_search(*args)

        app.send_task.side_effect = send_task
        return app, patch.multiple('dlux.weather', weather_worker_available=lambda: True, _celery_app=lambda: app)

    def reading(self):
        return {'main': {'temp': 21.0, 'feels_like': 20.0},
                'weather': [{'id': 800, 'description': 'clear sky', 'icon': '01d'}], 'dt': int(time.time())}

    def test_a_first_read_asks_the_worker_and_answers_pending(self):
        from dlux.weather import WeatherPending
        config = self.enable()
        location = config['locations'][0]
        app, worker = self.worker(run=False)
        with worker, patch('dlux.weather._request') as provider:
            with self.assertRaises(WeatherPending):
                current_weather(config, location, 'en')
            provider.assert_not_called()  # web itself never calls OpenWeather
        name, = app.send_task.call_args.args
        self.assertEqual(name, 'dlux.tasks.weather_refresh')
        self.assertEqual(app.send_task.call_args.kwargs['args'][3], config['encrypted_api_key'])

    def test_the_worker_reading_is_what_web_serves(self):
        from dlux.weather import WeatherPending
        config = self.enable()
        location = config['locations'][0]
        _app, worker = self.worker()
        with worker, patch('dlux.weather._request', return_value=self.reading()):
            # Web cannot know the worker finished; the next read finds the reading.
            with self.assertRaises(WeatherPending):
                current_weather(config, location, 'en')
            reading = current_weather(config, location, 'en')
        self.assertEqual(reading['temperature'], 21)
        self.assertFalse(reading['stale'])

    def test_a_worker_failure_is_reported_not_left_pending(self):
        config = self.enable()
        location = config['locations'][0]
        _app, worker = self.worker()
        from dlux.weather import WeatherPending
        with worker, patch('dlux.weather._request', side_effect=WeatherUnavailable('credentials')):
            with self.assertRaises(WeatherPending):
                current_weather(config, location, 'en')
            with self.assertRaisesRegex(WeatherUnavailable, '^credentials$'):
                current_weather(config, location, 'en')

    def test_the_endpoint_answers_202_while_pending(self):
        self.enable()
        self.client.force_login(self.admin)
        _app, worker = self.worker(run=False)
        with worker:
            response = self.client.get(reverse('weather_current'))
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json(), {'status': 'pending'})

    def test_city_search_runs_in_the_worker_with_the_key_encrypted(self):
        from dlux.weather import decrypt_api_key, find_locations
        app, worker = self.worker()
        rows = [{'name': 'Tripoli', 'country': 'LY', 'lat': 32.8872, 'lon': 13.1913}]
        with worker, patch('dlux.weather._request', return_value=rows) as provider:
            found = find_locations('Tripoli', 'draft-key')
        self.assertEqual(found[0]['name'], 'Tripoli, LY')
        _token, _query, sent_key = app.send_task.call_args.kwargs['args']
        self.assertNotEqual(sent_key, 'draft-key', 'the broker never sees the key in the clear')
        self.assertEqual(decrypt_api_key(sent_key), 'draft-key')
        self.assertEqual(provider.call_args.args[1], 'draft-key')

    def test_a_silent_worker_ends_the_search_with_an_error(self):
        from dlux.weather import find_locations
        _app, worker = self.worker(run=False)
        with worker, patch('dlux.weather.SEARCH_WAIT_SECONDS', 0.3):
            with self.assertRaisesRegex(WeatherUnavailable, '^worker$'):
                find_locations('Tripoli', 'draft-key')

    def test_without_a_worker_only_a_development_server_makes_the_call(self):
        from dlux.weather import find_locations
        config = self.enable()
        with patch('dlux.weather.weather_worker_available', return_value=False), \
                patch('dlux.weather._request', return_value=self.reading()) as provider:
            with override_settings(DEBUG=True):
                self.assertEqual(current_weather(config, config['locations'][0], 'en')['temperature'], 21)
            provider.assert_called_once()
            provider.reset_mock()
            cache.clear()
            with override_settings(DEBUG=False):
                with self.assertRaisesRegex(WeatherUnavailable, '^worker$'):
                    current_weather(config, config['locations'][0], 'en')
                with self.assertRaisesRegex(WeatherUnavailable, '^worker$'):
                    find_locations('Tripoli', 'draft-key')
            provider.assert_not_called()

    def test_the_tasks_are_registered_under_the_names_web_sends(self):
        from dlux import tasks
        if tasks.shared_task is None:
            self.skipTest('celery is not installed')
        self.assertEqual(tasks.weather_refresh_task.name, 'dlux.tasks.weather_refresh')
        self.assertEqual(tasks.weather_search_task.name, 'dlux.tasks.weather_search')


class WeatherKeyAndSaveTests(TestCase):
    """Enabling weather and entering the key must save, and the key is not a password."""

    setUp = WeatherTests.setUp
    save_form = WeatherTests.save_form

    def test_the_key_is_a_plain_text_field_the_password_tools_ignore(self):
        html = str(SystemSettingsForm(instance=self.record)['weather_api_key'])
        self.assertIn('type="text"', html)
        self.assertNotIn('type="password"', html)
        self.assertNotIn('new-password', html)

    def test_enabling_with_only_a_key_saves(self):
        self.save_form(dict(weather_enabled='on', weather_api_key='abc123DEF456', weather_locations='[]',
                            weather_placement='titlebar', weather_display='combined', weather_units='metric',
                            weather_corner='bottom-end'))
        config = get_weather_config()
        self.assertTrue(config['enabled'])
        self.assertEqual(api_key(config), 'abc123DEF456')
        self.assertEqual(config['locations'], [])

    def test_a_rejected_location_list_is_shown_not_swallowed(self):
        from django.template import Context, Template
        request = RequestFactory().get('/?step=' + str(SETUP_STEP_EXTRAS))
        request.user = self.admin
        form = SystemSettingsForm(data={**BASE, 'weather_enabled': 'on', 'weather_api_key': 'k',
                                        'weather_locations': '{"bad": 1}'},
                                  instance=SystemSettings.load(), request=request)
        self.assertFalse(form.is_valid())
        self.assertIn('weather_locations', form.errors)
        html = Template('{% load crispy_forms_tags %}{% crispy form %}').render(Context({'form': form}))
        weather = html.split('data-weather-settings')[1].split('data-weather-location-builder')[0]
        self.assertIn('alert alert-danger', weather)


class WeatherDisplayPreviewAndFloatTests(TestCase):
    setUp = WeatherTests.setUp
    save_form = WeatherTests.save_form
    enable = WeatherTests.enable

    def render(self, markup, request=None):
        if request is None:
            request = RequestFactory().get('/')
            request.user = self.admin
        return Template('{% load dlux_weather %}' + markup).render(Context({'request': request}))

    def test_the_full_display_replaces_condition_text(self):
        from dlux.forms.weather import CHOICES
        self.assertEqual([value for value, _ in CHOICES['display']], ['icon', 'temperature', 'combined', 'full'])
        self.assertEqual(normalize_weather_config({'display': 'text'})['display'], 'full', '1.10.0b1 stored "text"')

    def test_a_preview_passes_its_draft_token_to_the_reading_request(self):
        from dlux.system.preview import PREVIEW_PARAM
        config = self.enable()
        request = RequestFactory().get('/', {PREVIEW_PARAM: 'tok123'})
        request.user = self.admin
        request.dlux_preview = {'token': 'tok123'}
        with patch('dlux.weather.get_weather_config', return_value=config):
            html = self.render('{% weather_widget variant="card" %}', request)
            plain = self.render('{% weather_widget variant="card" %}')
        self.assertIn(f'data-weather-url="{reverse("weather_current")}?{PREVIEW_PARAM}=tok123"', html)
        self.assertNotIn(PREVIEW_PARAM, plain)

    def test_extras_previews_on_the_live_page(self):
        from pathlib import Path
        js = (Path(__file__).resolve().parents[1] / 'static/dlux/setup/js/previews.js').read_text(encoding='utf-8')
        self.assertIn("'layout', 'extras']", js)

    def test_the_floating_widget_is_a_draggable_bubble(self):
        config = self.enable()
        with patch('dlux.weather.get_weather_config', return_value=config):
            html = self.render('{% weather_widget placement="floating" %}')
        self.assertIn('dlux-weather__bubble', html)
        self.assertIn('data-weather-draggable', html)

    def test_a_centred_title_is_centred_on_the_bar(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1] / 'static/dlux/titlebar'
        css = (root / 'css/main.css').read_text(encoding='utf-8')
        rail = (root / 'js/action_rail.js').read_text(encoding='utf-8')
        self.assertIn('max-width: var(--dlux-titlebar-title-room, 40vw);', css)
        self.assertIn("titlebar.dataset.titleAlign === 'center'", rail)
        self.assertIn("setProperty('--dlux-titlebar-title-room'", rail)


class WeatherRelayTests(TestCase):
    """OpenWeather is reached through the Composer agent when it offers the operation."""

    setUp = WeatherTests.setUp
    save_form = WeatherTests.save_form
    enable = WeatherTests.enable

    def agent(self, **handlers):
        import tempfile
        from dlux.relay_testing import FakeAgent
        from dlux.updater.runtime import RuntimeStore

        root = tempfile.mkdtemp()
        store = RuntimeStore(root).ensure()
        override = override_settings(DLUX_UPDATE_RUNTIME_ROOT=root)
        override.enable()
        self.addCleanup(override.disable)
        agent = FakeAgent(store, handlers, operations={
            name: {'response': 'json', 'auth': True, 'params': []} for name in handlers})
        agent.publish()
        # The agent answers as soon as a request is written, as a running one would within a poll.
        from dlux import relay
        real_submit = relay.submit

        def submit_and_answer(*args, **kwargs):
            ticket = real_submit(*args, **kwargs)
            agent.step()
            return ticket

        patcher = patch('dlux.relay.submit', submit_and_answer)
        patcher.start()
        self.addCleanup(patcher.stop)
        return agent

    GEOCODE = {'[].name': ['Tripoli', 'Tripoli'], '[].state': ['Tripoli District', None],
               '[].country': ['LY', 'LB'], '[].lat': [32.9, 34.4], '[].lon': [13.2, 35.8]}

    def current(self, **change):
        return {'main.temp': 21.4, 'main.feels_like': 20.0, 'dt': int(time.time()), 'weather.0.id': 800,
                'weather.0.icon': '01d', 'weather.0.description': 'clear sky', **change}

    def test_city_search_goes_through_the_relay_with_the_key_sealed(self):
        from dlux.weather import search_locations
        agent = self.agent(**{'weather.geocode': lambda params, secret: self.GEOCODE})
        with patch('dlux.weather._request') as direct:
            found = search_locations('Tripoli', 'OWM-KEY')
        direct.assert_not_called()
        self.assertEqual([row['name'] for row in found], ['Tripoli, Tripoli District, LY', 'Tripoli, LB'])
        self.assertEqual(agent.seen[-1], {'op': 'weather.geocode', 'params': {'q': 'Tripoli', 'limit': 5}, 'secret': 'OWM-KEY'})

    def test_a_reading_goes_through_the_relay_and_keeps_its_shape(self):
        from dlux.weather import refresh_reading
        agent = self.agent(**{'weather.current': lambda params, secret: self.current()})
        config = self.enable()
        location = config['locations'][0]
        with patch('dlux.weather._request') as direct:
            reading = refresh_reading(location, 'metric', 'ar', config['encrypted_api_key'])
        direct.assert_not_called()
        self.assertEqual((reading['temperature'], reading['feels_like'], reading['icon'], reading['unit']), (21, 20, 'sun', '°C'))
        seen = agent.seen[-1]
        self.assertEqual(seen['params'], {'lat': location['lat'], 'lon': location['lon'], 'units': 'metric', 'lang': 'ar'})
        self.assertEqual(seen['secret'], api_key(config))

    def test_a_missing_or_null_field_is_a_response_error_not_a_crash(self):
        from dlux.weather import refresh_reading, search_locations
        self.agent(**{'weather.current': lambda p, s: self.current(**{'main.temp': None}),
                      'weather.geocode': lambda p, s: {**self.GEOCODE, '[].lat': [None, None]}})
        config = self.enable()
        with self.assertRaisesRegex(WeatherUnavailable, '^response$'):
            refresh_reading(config['locations'][0], 'metric', 'en', config['encrypted_api_key'])
        with self.assertRaisesRegex(WeatherUnavailable, '^response$'):
            search_locations('Tripoli', 'K')

    def test_the_agents_error_codes_become_weather_reasons(self):
        from dlux.weather import search_locations

        class Refused(Exception):
            def __init__(self, code):
                super().__init__(code)
                self.code = code

        expected = {'credentials': 'credentials', 'network': 'network', 'blocked': 'network',
                    'provider': 'provider', 'response': 'response', 'limit': 'provider'}
        for code, reason in expected.items():
            def refuse(params, secret, code=code):
                raise Refused(code)

            with self.subTest(code=code):
                self.agent(**{'weather.geocode': refuse})
                with self.assertRaisesRegex(WeatherUnavailable, f'^{reason}$'):
                    search_locations('Tripoli', 'K')

    def test_an_agent_that_does_not_answer_is_a_relay_problem_with_its_own_message(self):
        from dlux import relay
        from dlux.weather import search_locations
        self.agent(**{'weather.geocode': lambda p, s: self.GEOCODE})
        for code in ('timeout', 'agent', 'unsupported', 'unapproved'):
            with self.subTest(code=code), patch('dlux.relay.fetch', side_effect=relay.RelayError(code)):
                with self.assertRaisesRegex(WeatherUnavailable, '^relay$'):
                    search_locations('Tripoli', 'K')

    def test_without_the_operation_the_worker_calls_directly_and_a_web_process_falls_back_too(self):
        from dlux import relay
        from dlux.weather import search_locations
        rows = [{'name': 'Tripoli', 'country': 'LY', 'lat': 32.9, 'lon': 13.2}]
        with patch('dlux.weather._request', return_value=rows) as direct:
            self.assertEqual(search_locations('Tripoli', 'K')[0]['name'], 'Tripoli, LY')
        direct.assert_called_once()
        self.agent(**{'weather.geocode': lambda p, s: self.GEOCODE})
        with patch('dlux.relay.fetch', side_effect=relay.RelayError('writer')), \
                patch('dlux.weather._request', return_value=rows) as direct:
            self.assertEqual(search_locations('Tripoli', 'K')[0]['name'], 'Tripoli, LY')
        direct.assert_called_once()

    def test_no_key_never_reaches_the_relay(self):
        from dlux.weather import search_locations
        self.agent(**{'weather.geocode': lambda p, s: self.GEOCODE})
        with patch('dlux.relay.fetch') as fetch, self.assertRaisesRegex(WeatherUnavailable, '^credentials$'):
            search_locations('Tripoli', '')
        fetch.assert_not_called()

    def test_the_fields_and_parameters_match_the_specification_composer_ships(self):
        from pathlib import Path
        from dlux import weather
        spec = {op['name']: op for op in json.loads(
            (Path(__file__).parent / 'fixtures' / 'relay_weather_ops.json').read_text())['operations']}
        self.assertEqual(list(weather.GEOCODE_FIELDS), spec[weather.GEOCODE_OPERATION]['response']['fields'])
        self.assertEqual(list(weather.CURRENT_FIELDS), spec[weather.CURRENT_OPERATION]['response']['fields'])
        agent = self.agent(**{'weather.geocode': lambda p, s: self.GEOCODE,
                              'weather.current': lambda p, s: self.current()})
        weather.search_locations('Tripoli', 'K')
        config = self.enable()
        weather.refresh_reading(config['locations'][0], 'imperial', 'en', config['encrypted_api_key'])
        for seen in agent.seen:
            declared = spec[seen['op']]['params']
            self.assertLessEqual(set(seen['params']), set(declared))
            self.assertTrue({name for name, rule in declared.items() if rule.get('required', True)} <= set(seen['params']))
            self.assertTrue(spec[seen['op']]['auth'] and seen['secret'])

    def test_field_projection_matches_the_cases_composer_also_checks(self):
        from pathlib import Path
        from dlux.weather import _project_fields
        cases = json.loads((Path(__file__).parent / 'fixtures' / 'relay_projection_cases.json').read_text())['cases']
        for case in cases:
            with self.subTest(case=case['name']):
                self.assertEqual(_project_fields(case['document'], tuple(case['fields'])), case['expected'])

    def test_the_settings_page_has_a_message_for_every_failure_the_search_can_report(self):
        from dlux.translations import get_strings
        for language in ('en', 'ar'):
            strings = get_strings(language)
            for key in ('weather_search_error_key', 'weather_search_error_egress', 'weather_search_error_worker',
                        'weather_search_error_relay', 'weather_search_error_provider'):
                self.assertTrue(strings.get(key), (language, key))
        template = open(__import__('os').path.join(
            __import__('os').path.dirname(__file__), '..', 'templates', 'dlux', 'weather', 'settings.html')).read()
        for label in ('key', 'egress', 'worker', 'relay', 'provider'):
            self.assertIn(f'data-label-error-{label}=', template)
