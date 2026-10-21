"""Presence-aware settings patches: dictionaries merge, explicit lists replace."""

from copy import deepcopy


def merge_settings_patch(current, incoming):
    if not isinstance(current, dict) or not isinstance(incoming, dict):
        return deepcopy(incoming)
    merged = deepcopy(current)
    for key, value in incoming.items():
        merged[key] = merge_settings_patch(merged.get(key), value)
    return merged


def _supplied_values(normalized, supplied):
    if not isinstance(normalized, dict) or not isinstance(supplied, dict):
        return deepcopy(normalized)
    return {
        key: _supplied_values(value, supplied[key])
        for key, value in normalized.items() if key in supplied
    }


def retain_import_presence(normalized, raw):
    from .registry import get_flat_config_fields, get_import_aliases

    canonical = dict(raw)
    for alias, name in get_import_aliases().items():
        if name not in canonical and alias in raw:
            canonical[name] = raw[alias]
    flat_fields = get_flat_config_fields()
    present = {}
    for name, value in normalized.items():
        if name in canonical:
            present[name] = _supplied_values(value, canonical[name])
        elif name in flat_fields:
            group, key = flat_fields[name]
            supplied = canonical.get(group)
            if isinstance(supplied, dict) and key in supplied:
                present[name] = value
    return present
