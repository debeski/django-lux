import os

from django import template
from django.contrib.staticfiles import finders
from django.template.loader import get_template
from django.template import TemplateDoesNotExist
from django.templatetags.static import static as _django_static
from django.http import QueryDict
from django.utils.timesince import timesince
from django.utils.html import avoid_wrapping
from django.utils.safestring import mark_safe
from django.conf import settings
from .. import __version__ as _DLUX_VERSION
from ..translations import get_strings
from ..navbar import build_navbar_hierarchy_crumbs, build_navbar_route_label_map

register = template.Library()


@register.simple_tag
def dlux_static(path):
    """Like ``{% static path %}`` but appends a ``?v=<DjangoLux version>`` cache
    buster. The version is read from the package (``dlux.__version__``), NOT the
    template context, so it works everywhere — including widget-rendered
    partials (grouped permissions, profile image) that have no request context
    and thus no ``DLUX_VERSION`` context variable.

    Because the version changes on every release, every static asset is
    re-fetched by browsers after an inline update. In DEBUG, the source file's
    modification time is added so mounted development assets also refresh
    without pretending an unreleased edit is a new Dlux release. Interim
    measure; once the generated project adopts ManifestStaticFilesStorage
    (content-hashed names) this can be dropped in favour of a plain
    ``{% static %}``.
    """
    revision = _DLUX_VERSION
    if settings.DEBUG:
        try:
            source_path = finders.find(path)
            if source_path:
                revision = f"{revision}-{os.stat(source_path).st_mtime_ns:x}"
        except (OSError, TypeError, ValueError):
            pass
    url = _django_static(path)
    separator = '&' if '?' in url else '?'
    return f"{url}{separator}v={revision}"

@register.simple_tag(takes_context=True)
def dlux_timesince(context, value, arg=None):
    """
    Standard timesince but translates units using DLUX_STRINGS.
    Example: 9 hours, 52 minutes -> 9 ساعات و 52 دقيقة
    Usage: {% dlux_timesince user.last_login %}
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


@register.simple_tag(takes_context=True)
def include_once(context, template_name):
    """
    Include a template at most once per request, no matter how many places
    invoke it. Used for shared asset partials (e.g. form CSS/JS) that may be
    pulled both globally from base.html and again from form_base.html or the
    dynamic modal — the first render wins, later calls render nothing so the
    same <link>/<script> tags are never emitted twice on one page.
    Usage: {% include_once 'path/to/template.html' %}
    """
    request = context.get("request")
    seen = getattr(request, "_dlux_included_once", None) if request is not None else None
    if seen is None:
        seen = set()
        if request is not None:
            request._dlux_included_once = seen
    if template_name in seen:
        return ""
    seen.add(template_name)
    try:
        t = get_template(template_name)
    except TemplateDoesNotExist:
        return ""
    return t.render(context.flatten())


@register.simple_tag(takes_context=True)
def dlux_ribbon(context, ribbon=None):
    """Render a list page's ribbon — its title, filters and actions.

    Reads `ribbon` from the context (put there by `dlux.ribbon.RibbonMixin`)
    unless one is passed explicitly.
    """
    from django.template.loader import render_to_string

    ribbon = ribbon if ribbon is not None else context.get('ribbon')
    if ribbon is None:
        return ""
    return mark_safe(render_to_string(
        'dlux/ribbon/ribbon.html',
        {'ribbon': ribbon, 'request': context.get('request')},
    ))


@register.filter
def dlux_ribbon_field(form, name):
    """The bound field for `name`, or empty when the form does not have it."""
    if form is None or name not in getattr(form, 'fields', {}):
        return ""
    return form[name]


@register.inclusion_tag('dlux/navbar/main.html', takes_context=True)
def dlux_navbar(context):
    request = context.get('request')
    navbar = context.get('navbar') or {}
    app_config = context.get('APP_CONFIG') or {}
    if request is None or not navbar.get('enabled', False):
        return {'navbar_enabled': False}

    hierarchy_crumbs = build_navbar_hierarchy_crumbs(
        request,
        navbar,
        context.get('CURRENT_LANG', 'en'),
        context.get('DLUX_STRINGS') or {},
        runtime_crumbs=context.get('dlux_navbar_crumbs'),
        home_url=(app_config.get('homepage_config') or {}).get('default_url') or app_config.get('home_url') or '',
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
        'DLUX_STRINGS': context.get('DLUX_STRINGS') or {},
    }


@register.simple_tag(takes_context=True)
def dlux_querystring(context, key, value):
    """
    Return the current request querystring with one dynamic key updated.
    Usage: {% dlux_querystring table.prefixed_order_by_field column.order_by_alias.next %}
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
def dlux_querystring_multi(context, *args):
    """
    Return the current request querystring with multiple dynamic keys updated.
    Usage: {% dlux_querystring_multi table.prefixed_page_field '' table.dlux_per_page_field 50 %}
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


@register.inclusion_tag('dlux/activitylog/audit_trail.html', takes_context=True)
def dlux_audit_trail(context, instance):
    """Render the audit trail (created/updated/deleted by/at) for a model
    instance, gated by the show_audit_fields setting + the view_audit_fields
    permission. Renders nothing unless the viewer is permitted. The deleted-by
    line additionally requires the superadmin soft-delete gate. Drop it into any
    detail template: ``{% dlux_audit_trail object %}``.
    """
    from ..utils.authorization import audit_fields_visible, soft_deleted_visible

    request = context.get('request')
    user = getattr(request, 'user', None)
    visible = bool(instance is not None and audit_fields_visible(user))
    return {
        'instance': instance,
        'visible': visible,
        'show_deleted': visible and soft_deleted_visible(user),
        'DLUX_STRINGS': context.get('DLUX_STRINGS') or get_strings(),
    }


class _WrapperNode(template.Node):
    """Renders a wrapper around its block content from a template partial.

    The partial receives the rendered inner HTML as ``content`` plus whatever
    keyword arguments the tag was given, so a wrapper stays editable as markup
    instead of being built by string concatenation in Python.
    """

    def __init__(self, nodelist, template_name, kwargs):
        self.nodelist = nodelist
        self.template_name = template_name
        self.kwargs = kwargs
        self._template = None

    def render(self, context):
        resolved = {key: value.resolve(context) for key, value in self.kwargs.items()}
        resolved['content'] = mark_safe(self.nodelist.render(context))

        # Render into the *current* context, exactly as {% include %} does.
        #
        # The obvious `get_template(name).render(resolved, request)` builds a new
        # RequestContext, which re-runs every context processor — so a page with
        # 13 wrapped cards ran `dlux_context` (and its config/font lookups) 13
        # extra times. Pushing onto the existing context keeps the outer
        # variables visible to the partial and costs nothing.
        if self._template is None:
            self._template = get_template(self.template_name).template
        with context.push(**resolved):
            return self._template.render(context)


def _wrapper_tag(name, template_name):
    """Register ``{% name key=value %}...{% endname %}`` for a wrapper partial."""

    def compile_wrapper(parser, token):
        bits = token.split_contents()[1:]
        kwargs = {}
        for bit in bits:
            if '=' not in bit:
                raise template.TemplateSyntaxError(
                    f"{name} takes keyword arguments only, got '{bit}'")
            key, value = bit.split('=', 1)
            kwargs[key] = parser.compile_filter(value)
        nodelist = parser.parse((f'end{name}',))
        parser.delete_first_token()
        return _WrapperNode(nodelist, template_name, kwargs)

    register.tag(name, compile_wrapper)


_wrapper_tag('dlux_table_shell', 'dlux/tables/shell.html')
_wrapper_tag('dlux_card', 'dlux/base/card.html')
_wrapper_tag('dlux_alert', 'dlux/notifications/alert.html')
_wrapper_tag('dlux_option_card', 'dlux/system/option_card.html')
