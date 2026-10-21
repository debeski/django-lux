"""Discover model-keyed table baselines without fetching rows or rendering pages."""

import logging

from django.urls import get_resolver

from .routes import _iterate_named_patterns, _root_urlconf_is_loading
from ..utils.table_columns import baseline_table_columns, configurable_table_columns


logger = logging.getLogger('dlux')


def table_column_catalog(request=None, urlconf=None):
    """Union columns across a model's table variants; log unsupported hosts."""
    if _root_urlconf_is_loading():
        return []
    from ..translations import get_current_language_code, get_strings, resolve_model_label

    strings = get_strings(get_current_language_code(request))
    found = {}

    def collect(table_class, route):
        try:
            with baseline_table_columns():
                table = table_class([])
            model = getattr(table._meta, 'model', None)
            if model is None or not getattr(table, 'dlux_table_enabled', False):
                logger.debug('Table catalog skipped %s: no model or Dlux rendering disabled.', route)
                return
            columns = configurable_table_columns(table)
            if not columns:
                return
            key = model._meta.label_lower
            entry = found.setdefault(key, {
                'key': key, 'label': str(resolve_model_label(model, strings=strings)),
                'columns': [], 'routes': [],
            })
            if route not in entry['routes']:
                entry['routes'].append(route)
            known = {item['name'] for item in entry['columns']}
            for column in columns:
                if column.name not in known:
                    name = column.name
                    raw = str(column.header)
                    label_keys = (
                        f'tbl_{model._meta.model_name}_{name}', f'label_{model._meta.model_name}_{name}',
                        f'tbl_{name}', f'label_{name}', f'tbl_{raw}', f'label_{raw}', raw,
                    )
                    label = next((str(strings[key]) for key in label_keys if key in strings), raw)
                    entry['columns'].append({'name': name, 'label': label})
                    known.add(column.name)
        except Exception:
            logger.warning('Table catalog skipped %s (%r).', route, table_class, exc_info=True)

    try:
        candidates = list(_iterate_named_patterns(get_resolver(urlconf).url_patterns))
    except Exception:
        logger.warning('Table catalog could not enumerate URL patterns.', exc_info=True)
        candidates = []
    for pattern, route, _ in candidates:
        try:
            callback = pattern.callback
            view = getattr(callback, 'view_class', None)
            if view is None:
                continue
            from ..views.sections import DynamicModalManagerView
            if not (hasattr(view, 'get_table_class') or hasattr(view, 'table_class')
                    or issubclass(view, DynamicModalManagerView)):
                continue
            instance = view(**getattr(callback, 'view_initkwargs', {}))
            table_class = getattr(instance, 'table_class', None)
            if hasattr(instance, 'get_table_class'):
                instance.setup(request)
                table_class = instance.get_table_class()
            if table_class is None:
                if isinstance(instance, DynamicModalManagerView) and instance.show_table and instance.model:
                    from ..utils.discovery import get_model_classes
                    model = instance.model
                    table_class = get_model_classes(model._meta.model_name, app_label=model._meta.app_label)['table']
            if table_class is not None:
                collect(table_class, route)
        except Exception:
            logger.warning('Table catalog skipped route %s.', route, exc_info=True)

    try:
        from ..utils.sections import discover_section_models
        for section in discover_section_models():
            collect(section['table_class'], 'manage_sections')
    except Exception:
        logger.warning('Table catalog could not discover section tables.', exc_info=True)
    return sorted(found.values(), key=lambda item: (item['label'].casefold(), item['key']))
