from django import template
from django.template.loader import get_template
from django.template import TemplateDoesNotExist
from django.http import QueryDict
from django.utils.timesince import timesince
from django.utils.html import avoid_wrapping
from django.conf import settings
from ..translations import get_strings
from ..navbar import build_navbar_hierarchy_crumbs, build_navbar_route_label_map

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
    current_lang = strings.get('lang_code_id', 'en')  # Safe fallback if needed by template tag processing, but mainly get_strings() handles the translation mapping natively now.
    
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


@register.inclusion_tag('dlux/includes/navbar.html', takes_context=True)
def dlux_navbar(context):
    request = context.get('request')
    navbar = context.get('navbar') or {}
    if request is None or not navbar.get('enabled', False):
        return {'navbar_enabled': False}

    hierarchy_crumbs = build_navbar_hierarchy_crumbs(
        request,
        navbar,
        context.get('CURRENT_LANG', 'en'),
        context.get('MS_TRANS') or {},
        runtime_crumbs=context.get('dlux_navbar_crumbs'),
    )
    page_crumb = hierarchy_crumbs[-1] if hierarchy_crumbs else {}
    return {
        'navbar_enabled': True,
        'navbar_mode': navbar.get('mode', 'hierarchy'),
        'navbar_crumbs': hierarchy_crumbs,
        'navbar_hierarchy_crumbs': hierarchy_crumbs,
        'navbar_route_labels': build_navbar_route_label_map(context.get('CURRENT_LANG', 'en')),
        'navbar_current_label': page_crumb.get('label', ''),
        'navbar_current_path': getattr(request, 'path', ''),
        'MS_TRANS': context.get('MS_TRANS') or {},
    }


@register.simple_tag(takes_context=True)
def ms_querystring(context, key, value):
    """
    Return the current request querystring with one dynamic key updated.
    Usage: {% ms_querystring table.prefixed_order_by_field column.order_by_alias.next %}
    """
    request = context.get('request')
    if request is not None:
        querydict = request.GET.copy()
    else:
        querydict = QueryDict('', mutable=True)

    key = str(key or '').strip()
    if not key:
        encoded = querydict.urlencode()
        return f'?{encoded}' if encoded else ''

    if value in (None, ''):
        querydict.pop(key, None)
    else:
        querydict[key] = value

    encoded = querydict.urlencode()
    return f'?{encoded}' if encoded else ''


@register.simple_tag(takes_context=True)
def ms_querystring_multi(context, *args):
    """
    Return the current request querystring with multiple dynamic keys updated.
    Usage: {% ms_querystring_multi table.prefixed_page_field '' table.dlux_per_page_field 50 %}
    """
    request = context.get('request')
    if request is not None:
        querydict = request.GET.copy()
    else:
        querydict = QueryDict('', mutable=True)

    pair_count = len(args) - (len(args) % 2)
    for index in range(0, pair_count, 2):
        key = str(args[index] or '').strip()
        value = args[index + 1]
        if not key:
            continue
        if value in (None, ''):
            querydict.pop(key, None)
        else:
            querydict[key] = value

    encoded = querydict.urlencode()
    return f'?{encoded}' if encoded else ''


@register.filter
def get_item(dictionary, key):
    """
    Template filter to get an item from a dictionary by key.
    Usage: {{ my_dict|get_item:my_key }}
    """
    if not isinstance(dictionary, dict):
        return None
    return dictionary.get(key)
