"""Reusable weather indicator and dashboard card."""
import uuid

from django import template
from django.template.loader import render_to_string

register = template.Library()

VARIANTS = ('compact', 'card', 'action')


@register.simple_tag(takes_context=True)
def weather_widget(context, variant='compact', location='', placement=''):
    """Render nothing while disabled.

    ``variant`` is ``compact`` (a clickable indicator), ``card`` (a dashboard
    card) or ``action`` (the titlebar's weather action; the context processor
    has already decided it belongs there). ``placement`` is for the shell's own
    slots (``floating``, ``user_hub``): the widget renders only in the slot
    System Settings chose. Project embeds omit it.
    """
    request = context.get('request')
    if request is None or not getattr(request.user, 'is_authenticated', False):
        return ''
    from ..translations import get_strings
    from ..weather import get_weather_config
    from ..widgets import DluxChoiceSelectorWidget

    config = get_weather_config()
    if not config['enabled']:
        return ''
    if placement and placement != config['placement']:
        return ''
    selected = location or config['default_location']
    if selected not in [item['id'] for item in config['locations']]:
        return ''
    variant = variant if variant in VARIANTS else 'compact'
    uid = 'weather-' + uuid.uuid4().hex
    # Radios group by name across the page, so every widget gets its own.
    selector = DluxChoiceSelectorWidget(
        choices=[(item['id'], item['name']) for item in config['locations']], variant='chip',
    ).render(f'{uid}-location', selected, attrs={'id': f'{uid}-location'})
    return render_to_string('dlux/weather/widget.html', {
        **context.flatten(), 'DLUX_STRINGS': get_strings(),
        'weather': dict(selected=selected, display=config['display'], corner=config['corner'],
                        variant=variant, floating=placement == 'floating', uid=uid,
                        selector=selector),
    })
