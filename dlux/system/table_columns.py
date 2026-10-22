"""Normalize the sparse, model-keyed table-column overlay."""

import re
from .constants import TABLE_CONFIG_KEYS
from .normalizers import normalize_layout_config


_MODEL_KEY = re.compile(r'[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*\Z')
_COLUMN_KEY = re.compile(r'[A-Za-z_][A-Za-z0-9_]*\Z')
_LANGUAGE_KEY = re.compile(r'[A-Za-z][A-Za-z0-9_-]{0,31}\Z')
_ICON = re.compile(r'bi-[a-z0-9]+(?:-[a-z0-9]+)*\Z')


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
            raw_headers = overlay.get('headers')
            if isinstance(raw_headers, dict):
                headers = {}
                for name, raw_header in raw_headers.items():
                    if not isinstance(name, str) or not _COLUMN_KEY.fullmatch(name) or not isinstance(raw_header, dict):
                        continue
                    header = {}
                    if isinstance(raw_header.get('labels'), dict):
                        header['labels'] = {
                            code: label.strip()[:200]
                            for code, label in raw_header['labels'].items()
                            if isinstance(code, str) and _LANGUAGE_KEY.fullmatch(code)
                            and isinstance(label, str) and label.strip()
                        }
                    if 'icon' in raw_header and isinstance(raw_header['icon'], str):
                        icon = raw_header['icon'].strip()
                        if not icon or (len(icon) <= 80 and _ICON.fullmatch(icon)):
                            header['icon'] = icon
                    if header or not raw_header:
                        headers[name] = header
                if headers or not raw_headers:
                    entry['headers'] = headers
            raw_sorting = overlay.get('sorting')
            if isinstance(raw_sorting, (list, tuple)):
                sorting = []
                seen = set()
                for alias in raw_sorting:
                    if not isinstance(alias, str):
                        continue
                    name = alias.removeprefix('-')
                    if _COLUMN_KEY.fullmatch(name) and name not in seen:
                        sorting.append(alias)
                        seen.add(name)
                    if len(sorting) == 2:
                        break
                if sorting or not raw_sorting:
                    entry['sorting'] = sorting
            if entry:
                columns[model] = entry
    layout = normalize_layout_config(value)
    return {**{key: layout[key] for key in TABLE_CONFIG_KEYS}, 'columns': columns}
