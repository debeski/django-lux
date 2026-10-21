"""Normalize the sparse, model-keyed table-column overlay."""

import re
from .constants import TABLE_CONFIG_KEYS
from .normalizers import normalize_layout_config


_MODEL_KEY = re.compile(r'[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*\Z')
_COLUMN_KEY = re.compile(r'[A-Za-z_][A-Za-z0-9_]*\Z')


def normalize_tables_config(value):
    value = value if isinstance(value, dict) else {}
    raw_columns = value.get('columns')
    columns = {}
    if isinstance(raw_columns, dict):
        for model, overlay in raw_columns.items():
            if not isinstance(model, str) or not _MODEL_KEY.fullmatch(model):
                continue
            if not isinstance(overlay, dict):
                continue
            entry = {}
            for key in ('hidden', 'order'):
                raw = overlay.get(key)
                if not isinstance(raw, (list, tuple)):
                    continue
                names = list(dict.fromkeys(
                    name for name in raw
                    if isinstance(name, str) and _COLUMN_KEY.fullmatch(name)
                ))
                if names or not raw:
                    entry[key] = names
            if entry:
                columns[model] = entry
    layout = normalize_layout_config(value)
    return {**{key: layout[key] for key in TABLE_CONFIG_KEYS}, 'columns': columns}
