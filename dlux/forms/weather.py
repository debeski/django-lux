"""Weather's Extra Features controls and save policy."""
import json

from crispy_forms.layout import Div, Field, HTML
from django.template.loader import render_to_string
from django.core.exceptions import ValidationError

from ..system.constants import SETUP_STEP_EXTRAS
from ..system.weather import normalize_locations, normalize_weather_config
from ..widgets import DluxChoiceSelectorWidget
from .builders import _bind_choice_selector_widget, build_settings_toggle_field

CHOICES = {
    'placement': [('titlebar', 'Titlebar'), ('user_hub', 'User hub'), ('floating', 'Floating'), ('embed', 'Project embeds only')],
    'display': [('icon', 'Icon only'), ('text', 'Condition text'), ('temperature', 'Temperature only'), ('combined', 'Icon + temperature')],
    'units': [('metric', 'Celsius'), ('imperial', 'Fahrenheit')],
    'corner': [('bottom-end', 'Bottom end'), ('bottom-start', 'Bottom start'), ('top-end', 'Top end'), ('top-start', 'Top start')],
}


def configure_weather_fields(form, strings):
    config = normalize_weather_config((form.instance.extra_config or {}).get('weather'))
    active_step = not form.single_step_mode or form.single_step_index == SETUP_STEP_EXTRAS
    enabled = bool(form.data.get('weather_enabled')) if form.is_bound and active_step else config['enabled']
    for key in ('enabled', 'placement', 'display', 'units', 'corner', 'locations', 'default_location'):
        value = config[key]
        form.initial['weather_' + key] = json.dumps(value) if key == 'locations' else value
    for name in [name for name in form.fields if name.startswith('weather_')]:
        field = form.fields[name]
        label_key = 'form_sys_' + name
        field.label = strings.get(label_key, name)
        field.disabled = not active_step or (name != 'weather_enabled' and not enabled)
    for key, choices in CHOICES.items():
        name = 'weather_' + key
        translated = []
        for value, label in choices:
            label_key = 'weather_' + value
            translated.append((value, strings.get(label_key, label)))
        form.fields[name].choices = translated
        _bind_choice_selector_widget(form.fields[name], DluxChoiceSelectorWidget(choices=translated))
    form.fields['weather_corner'].help_text = strings.get('weather_corner_help', 'Start and end follow the interface direction.')
    form.fields['weather_api_key'].help_text = strings.get('weather_key_saved', 'API key saved. Leave blank to keep it, or enter a replacement.') if config['encrypted_api_key'] else strings.get('weather_key_help', 'Enter an OpenWeather API key with Current Weather and Geocoding access.')


def weather_settings_layout(form, strings):
    return Div(
        HTML('<h6 class="fw-bold my-3">' + strings.get('weather_title', 'Weather') + '</h6>'),
        build_settings_toggle_field(form, 'weather_enabled', css_class='col-12'),
        Div(
            Field('weather_placement'), Field('weather_display'), Field('weather_units'),
            Div(Field('weather_corner'), **{'data-weather-corner': ''}),
            Field('weather_api_key'),
            Field('weather_locations'), Field('weather_default_location'),
            HTML(render_to_string('dlux/weather/settings.html', {'DLUX_STRINGS': strings})),
            **{'data-weather-dependent': ''},
        ),
        **{'data-weather-settings': ''},
    )


def clean_weather(form, cleaned):
    if form.single_step_mode and form.single_step_index != SETUP_STEP_EXTRAS:
        return
    if not cleaned.get('weather_enabled'):
        return
    from ..weather import api_key
    from ..translations import get_strings
    strings = get_strings()
    config = normalize_weather_config((form.instance.extra_config or {}).get('weather'))
    try:
        locations = normalize_locations(json.loads(cleaned.get('weather_locations') or '[]'))
        if not locations:
            raise ValueError
        cleaned['weather_locations'] = locations
    except (ValueError, TypeError):
        form.add_error('weather_locations', ValidationError(strings['weather_choose_location']))
    if not cleaned.get('weather_api_key') and not api_key(config):
        form.add_error('weather_api_key', strings['weather_key_help'])


def apply_weather(form, instance):
    if 'weather_enabled' not in form.cleaned_data:
        return
    if form.single_step_mode and form.single_step_index != SETUP_STEP_EXTRAS:
        return
    extra = dict(instance.extra_config or {})
    config = normalize_weather_config(extra.get('weather'))
    config['enabled'] = bool(form.cleaned_data.get('weather_enabled'))
    if config['enabled']:
        for key in ('placement', 'display', 'units', 'corner', 'locations', 'default_location'):
            value = form.cleaned_data.get('weather_' + key)
            if value not in (None, ''):
                config[key] = value
        if form.cleaned_data.get('weather_api_key'):
            from ..weather import encrypt_api_key
            config['encrypted_api_key'] = encrypt_api_key(form.cleaned_data['weather_api_key'])
    extra['weather'] = normalize_weather_config(config)
    instance.extra_config = extra
