from django import template
from django.template.loader import get_template
from django.template import TemplateDoesNotExist
from django.utils.timesince import timesince
from django.utils.html import avoid_wrapping
from django.conf import settings
from ..translations import get_strings

register = template.Library()

@register.simple_tag(takes_context=True)
def ms_timesince(context, value, arg=None):
    """
    Standard timesince but translates units using MS_TRANS.
    Example: 9 hours, 52 minutes -> 9 ساعات و 52 دقيقة
    Usage: {% ms_timesince user.last_login %}
    """
    if not value:
        return ""
    
    try:
        ts = timesince(value, arg)
    except Exception:
        return ""

    strings = get_strings()
    current_lang = strings.get('lang_code_id', 'ar')  # Safe fallback if needed by template tag processing, but mainly get_strings() handles the translation mapping natively now.
    
    # Normalize buffer (replace non-breaking spaces)
    ts = ts.replace('\xa0', ' ')
    
    # Replacement map (Order matters: plural first)
    replacements = [
        ("minutes", strings.get('duration_minutes', 'minutes')),
        ("minute", strings.get('duration_minute', 'minute')),
        ("hours", strings.get('duration_hours', 'hours')),
        ("hour", strings.get('duration_hour', 'hour')),
        ("days", strings.get('duration_days', 'days')),
        ("day", strings.get('duration_day', 'day')),
        ("weeks", strings.get('duration_weeks', 'weeks')),
        ("week", strings.get('duration_week', 'week')),
        ("months", strings.get('duration_months', 'months')),
        ("month", strings.get('duration_month', 'month')),
        (",", f" {strings.get('duration_and', ',')} " if current_lang == 'ar' else strings.get('duration_and', ', ')),
    ]
    
    for en, localized in replacements:
        ts = ts.replace(en, localized)
        
    return avoid_wrapping(ts)

@register.simple_tag(takes_context=True)
def include_if_exists(context, template_name):
    """
    Include a template if it exists, otherwise do nothing.
    Usage: {% include_if_exists 'path/to/template.html' %}
    """
    try:
        t = get_template(template_name)
        return t.render(context.flatten())
    except TemplateDoesNotExist:
        return ""
