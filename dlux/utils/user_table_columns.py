"""Personal column overlays constrained by the table actually rendered to a user."""

import hashlib

from django.core import signing
from django.urls import reverse
from django.utils.html import strip_tags

from .table_columns import _discovering, configurable_table_columns

PREFERENCE_KEY = 'table_columns'
TOKEN_SALT = 'dlux.user-table-columns.v1'
TOKEN_MAX_AGE = 3600


def personal_table_key(table):
    identity = '|'.join((type(table).__module__, type(table).__qualname__,
                         table._meta.model._meta.label_lower, table.prefix or ''))
    return hashlib.sha256(identity.encode()).hexdigest()[:24]


def available_columns(model_key, columns, config):
    overlay = (config.get('columns') or {}).get(model_key, {})
    hidden = set(overlay.get('hidden', ()))
    return [column for column in columns if column['name'] not in hidden]


def personal_overlay(preferences, key, names):
    stored = preferences.get(PREFERENCE_KEY, {}) if isinstance(preferences, dict) else {}
    raw = stored.get(key, {}) if isinstance(stored, dict) else {}
    raw = raw if isinstance(raw, dict) else {}
    order = raw.get('order', [])
    order = list(dict.fromkeys(n for n in order if isinstance(n, str) and n in names)) if isinstance(order, list) else []
    order.extend(n for n in names if n not in order)
    raw_hidden = raw.get('hidden', [])
    hidden = [n for n in names if n in raw_hidden] if isinstance(raw_hidden, list) else []
    if names and len(hidden) == len(names):
        hidden.remove(order[0])
    return {'order': order, 'hidden': sorted(hidden)}


def apply_user_table_columns(table, config):
    request = getattr(table, 'request', None)
    if request is None:
        from ..middleware import get_current_request
        request = get_current_request()
    user = getattr(request, 'user', None)
    model = getattr(table._meta, 'model', None)
    if (_discovering.get() or not table.dlux_table_enabled or model is None
            or not getattr(user, 'is_authenticated', False)
            or getattr(user, 'pk', None) is None
            or getattr(getattr(type(table), 'Meta', None), 'dlux_user_columns', True) is False):
        return
    config = config if isinstance(config, dict) else {}
    columns = available_columns(model._meta.label_lower, [
        {'name': c.name, 'label': strip_tags(str(c.header))}
        for c in configurable_table_columns(table)
    ], config)
    if not columns:
        return
    key = personal_table_key(table)
    table.dlux_user_columns_key = key
    token = signing.dumps({'user': str(user.pk), 'key': key,
                           'model': model._meta.label_lower, 'columns': columns},
                          salt=TOKEN_SALT, compress=True)
    table.dlux_user_columns_url = reverse('user_table_columns') + '?token=' + token
    try:
        preferences = user.profile.preferences
    except AttributeError:
        preferences = {}
    names = [c['name'] for c in columns]
    overlay = personal_overlay(preferences, key, names)
    for name in overlay['hidden']:
        table.columns.hide(name)
    ordered = iter(overlay['order'])
    table.sequence = [next(ordered) if name in names else name for name in table.sequence]
