"""Discover list views and model fields available to the Ribbon builder."""

from django.urls import get_resolver

from .mixin import RibbonMixin
from .tabs import SOURCE_FIELD, SOURCE_FLAG, build_ribbon_tabs


CATALOG_SKIP_FIELDS = (
    'created_by', 'updated_by', 'deleted_by', 'user_permissions',
)


def _source_kind(field):
    """Which source type, if any, this field can populate."""
    if getattr(field, 'choices', None):
        return SOURCE_FIELD
    internal = field.get_internal_type() if hasattr(field, 'get_internal_type') else ''
    if internal == 'BooleanField':
        return SOURCE_FLAG
    if getattr(field, 'is_relation', False) and getattr(field, 'related_model', None):
        return SOURCE_FIELD
    return None


def ribbon_view_models(urlconf=None):
    """Return models behind views that render a Ribbon.

    Each value is ``(model, locked, declared)``. Locked views allow cosmetic
    edits to declared tabs but do not accept administrator-created strips.
    """
    found = {}

    def visit(patterns):
        for entry in patterns:
            nested = getattr(entry, 'url_patterns', None)
            if nested is not None:
                visit(nested)
                continue
            view = getattr(getattr(entry, 'callback', None), 'view_class', None)
            if view is None or not issubclass(view, RibbonMixin):
                continue
            model = getattr(view, 'model', None) or getattr(
                getattr(view, 'queryset', None), 'model', None
            )
            if model is None:
                continue
            locked = bool(getattr(view, 'ribbon_tabs_fixed', None)) or (
                view.get_ribbon_tabs is not RibbonMixin.get_ribbon_tabs
            )
            declared = getattr(view, 'ribbon_tabs_fixed', None) or getattr(
                view, 'ribbon_tabs', None
            )
            key = f'{model._meta.app_label}.{model.__name__}'
            previous = found.get(key)
            found[key] = (
                model,
                (previous[1] if previous else True) and locked,
                declared or (previous[2] if previous else None),
            )

    try:
        visit(get_resolver(urlconf).url_patterns)
    except Exception:
        return {}
    return found


def _split_field(config):
    """Return the first field a declared strip splits on."""
    sources = config.get('sources') if isinstance(config, dict) else None
    for source in (sources or []):
        if isinstance(source, dict) and source.get('field'):
            return str(source['field'])
    return ''


def _declared_strips(config, model, request):
    """Resolve every declared strip without applying stored presentation edits."""
    if not config:
        return []
    configs = config if isinstance(config, (list, tuple)) else [config]
    strips = []
    for index, one in enumerate(configs):
        if not one:
            continue
        try:
            tabs = build_ribbon_tabs(one, model=model, request=request, overlay={})
        except Exception:
            continue
        strips.append({
            'index': index,
            'param': tabs.param,
            'relation': tabs.relation or 'primary',
            'label': str(tabs.label or ''),
            'field': _split_field(one),
            'tabs': [
                {'key': tab.key, 'label': str(tab.label), 'icon': tab.icon or ''}
                for tab in tabs.items
            ],
        })
    return strips


def ribbon_tab_catalog(urlconf=None, request=None):
    """Return Ribbon models, declared strips, and fields that can draw tabs."""
    catalog = []
    for key, (model, locked, declared) in ribbon_view_models(urlconf).items():
        meta = model._meta
        fields = []
        for field in meta.get_fields():
            if not getattr(field, 'name', None) or field.auto_created and not field.concrete:
                continue
            if field.name in CATALOG_SKIP_FIELDS:
                continue
            kind = _source_kind(field)
            if kind is None:
                continue
            fields.append({
                'name': field.name,
                'label': str(getattr(field, 'verbose_name', field.name)).title(),
                'kind': kind,
                'choices': [
                    {'value': str(value), 'label': str(label)}
                    for value, label in (getattr(field, 'choices', None) or [])
                ],
            })
        strips = _declared_strips(declared, model, request)
        if not fields and not strips:
            continue
        catalog.append({
            'key': key,
            'app': meta.app_label,
            'locked': locked,
            'strips': strips,
            'label': str(meta.verbose_name_plural).title(),
            'fields': sorted(fields, key=lambda entry: entry['label']),
        })
    return sorted(catalog, key=lambda entry: (entry['app'], entry['label']))
