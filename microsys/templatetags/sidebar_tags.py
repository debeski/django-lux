"""
Template tags for the sidebar app.

Provides the {% auto_sidebar %} tag for rendering auto-discovered
navigation items.
"""
from django import template
from django.urls import reverse, NoReverseMatch

register = template.Library()


@register.inclusion_tag('microsys/sidebar/auto.html', takes_context=True)
def auto_sidebar(context):
    """
    Render auto-discovered sidebar items.
    
    Uses items from sidebar_auto_items context variable (provided by
    the context processor) and adds resolved URLs and active state.
    
    Usage:
        {% load sidebar_tags %}
        {% auto_sidebar %}
    """
    request = context.get('request')
    items = list(context.get('sidebar_auto_items', []))
    extra_groups = context.get('sidebar_extra_groups', {})
    has_extra = bool(extra_groups)
    
    # Add resolved URLs and active state
    for item in items:
        try:
            item['url'] = reverse(item['url_name'])
            # Check if current path matches or starts with this URL
            item['active'] = request.path == item['url'] or request.path.startswith(item['url'].rstrip('/') + '/')
        except NoReverseMatch:
            item['url'] = '#'
            item['active'] = False
    
    return {
        'items': items, 
        'request': request, 
        'has_extra': has_extra,
        'CURRENT_DIR': context.get('CURRENT_DIR'),
        'CURRENT_LANG': context.get('CURRENT_LANG'),
        'MS_TRANS': context.get('MS_TRANS'),
    }


@register.simple_tag(takes_context=True)
def sidebar_item_class(context, url_name):
    """
    Return 'active' class if current path matches the given URL name.
    
    Usage:
        <a href="{% url 'decree_list' %}" class="list-group-item {% sidebar_item_class 'decree_list' %}">
    """
    request = context.get('request')
    try:
        url = reverse(url_name)
        if request.path == url or request.path.startswith(url.rstrip('/') + '/'):
            return 'active'
    except NoReverseMatch:
        pass
    return ''


@register.inclusion_tag('microsys/sidebar/extra_groups.html', takes_context=True)
def extra_sidebar(context):
    """
    Render extra sidebar items grouped in accordions.
    
    Uses sidebar_extra_groups from context (provided by context processor).
    Groups are rendered as Bootstrap accordions at the end of the sidebar.
    
    Usage:
        {% load sidebar_tags %}
        {% extra_sidebar %}
    """
    groups = context.get('sidebar_extra_groups', {})
    request = context.get('request')
    return {
        'groups': groups, 
        'request': request,
        'CURRENT_DIR': context.get('CURRENT_DIR'),
        'CURRENT_LANG': context.get('CURRENT_LANG'),
        'MS_TRANS': context.get('MS_TRANS'),
    }

