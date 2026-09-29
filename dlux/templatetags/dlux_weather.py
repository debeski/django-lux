"""Reusable weather indicator and dashboard card."""
import uuid

from django import template
from django.template.loader import render_to_string

register = template.Library()


@register.simple_tag(takes_context=True)
def weather_widget(context, variant='compact', location='', placement=''):
    """Render nothing while disabled; ``placement`` is reserved for shell slots."""
    request = context.get('request')
    if request is None or not getattr(request.user, 'is_authenticated', False):
        return ''
    from ..weather import get_weather_config
    from ..translations import get_strings
    config = get_weather_config()
    if not config['enabled']:
        return ''
    slot = config['placement']
    if slot == 'user_hub' and context.get('titlebar', {}).get('user_hub_style') == 'titlebar_actions':
        slot = 'titlebar'
    if placement and placement != slot:
        return ''
    selected = location or config['default_location']
    if selected not in [item['id'] for item in config['locations']]:
        return ''
    return render_to_string('dlux/weather/widget.html', {
        **context.flatten(), 'DLUX_STRINGS': get_strings(),
        'weather': dict(locations=config['locations'], selected=selected, display=config['display'],
                        corner=config['corner'], floating=placement == 'floating',
                        card=variant == 'card', uid='weather-' + uuid.uuid4().hex),
    })
