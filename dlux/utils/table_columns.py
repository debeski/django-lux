"""Apply presentation preferences without widening a table's baseline visibility."""

from contextlib import contextmanager
from contextvars import ContextVar


_discovering = ContextVar('dlux_table_column_discovery', default=False)


@contextmanager
def baseline_table_columns():
    token = _discovering.set(True)
    try:
        yield
    finally:
        _discovering.reset(token)


def configurable_table_columns(table):
    from ..system.constants import record_visibility_column_names

    protected = set(record_visibility_column_names()) | {'scope', 'dlux_row_actions'}
    return [column for column in table.columns.itervisible() if column.name not in protected]


def apply_table_column_overlay(table, config):
    if _discovering.get() or not getattr(table, 'dlux_table_enabled', False):
        return
    model = getattr(table._meta, 'model', None)
    if model is None or not isinstance(config, dict):
        return
    raw_columns = config.get('columns')
    key = model._meta.label_lower
    if not isinstance(raw_columns, dict) or key not in raw_columns:
        return
    from ..system.table_columns import normalize_tables_config

    overlay = normalize_tables_config({'columns': {key: raw_columns[key]}})['columns'].get(key)
    if not overlay:
        return
    names = [column.name for column in configurable_table_columns(table)]
    hidden = set(overlay.get('hidden', ())) & set(names)
    # Keep the first baseline data column if an imported/stale overlay hides all.
    if names and len(hidden) == len(names):
        hidden.discard(names[0])
    for name in hidden:
        table.columns.hide(name)
    ordered = [name for name in overlay.get('order', ()) if name in names]
    if ordered:
        ordered.extend(name for name in names if name not in ordered)
        replacements = iter(ordered)
        table.sequence = [next(replacements) if name in names else name for name in table.sequence]
