"""Inferring a route's label, icon, group and required permissions."""

from django.apps import apps
from django.utils.encoding import force_str

from .meta import SYSTEM_ROUTE_META, _route_leaf


GROUP_ICON_DEFAULTS = {
    'dlux': 'bi-sliders',
    'core': 'bi-grid-1x2',
    'storage': 'bi-box-seam',
    'finance': 'bi-wallet2',
    'treasury': 'bi-safe',
    'hr_payroll': 'bi-person-badge',
}


VIEW_ICON_HINTS = {
    'dashboard': 'bi-speedometer2',
    'index': 'bi-house',
    'home': 'bi-house',
    'profile': 'bi-person-badge',
    'options': 'bi-gear',
    'users': 'bi-people',
    'sections': 'bi-diagram-3',
    'log': 'bi-clock-history',
    'report': 'bi-file-earmark-bar-graph',
    'import': 'bi-box-arrow-in-right',
    'export': 'bi-box-arrow-right',
    'return': 'bi-arrow-return-left',
    'asset': 'bi-inboxes',
    'fiscal': 'bi-calendar3',
    'chapter': 'bi-list-ul',
    'budget': 'bi-wallet2',
    'revenue': 'bi-cash-stack',
    'disbursement': 'bi-receipt',
    'check': 'bi-credit-card',
    'advance': 'bi-currency-exchange',
    'trust': 'bi-safe',
    'guarantee': 'bi-shield-check',
    'ledger': 'bi-book',
    'personnel': 'bi-people',
    'payroll': 'bi-file-earmark-spreadsheet',
    'wage': 'bi-clock-history',
    'transfer': 'bi-bank',
}


def _humanize(name):
    name = (name or '').replace('-', ' ').replace('_', ' ').strip()
    if not name:
        return 'Untitled'
    return ' '.join(part.capitalize() for part in name.split())


def _plain_text(value, fallback=''):
    if value is None:
        return fallback
    return force_str(value)


def _guess_icon(url_name, model=None, callback=None):
    explicit = getattr(callback, 'sidebar_icon', None)
    if explicit:
        return _plain_text(explicit)
    if model and getattr(model._meta, 'sidebar_icon', None):
        return _plain_text(getattr(model._meta, 'sidebar_icon'))

    # Honour the icon declared for a system route (mirrors how label_key is used),
    # so routes without a matching VIEW_ICON_HINTS token still get a real icon.
    meta_leaf = _route_leaf(url_name)
    if meta_leaf in SYSTEM_ROUTE_META and SYSTEM_ROUTE_META[meta_leaf].get('icon'):
        return _plain_text(SYSTEM_ROUTE_META[meta_leaf]['icon'])

    leaf = url_name.split(':')[-1].lower()
    for hint, icon in VIEW_ICON_HINTS.items():
        if hint in leaf:
            return _plain_text(icon)

    namespace = url_name.split(':')[0] if ':' in url_name else ''
    return _plain_text(GROUP_ICON_DEFAULTS.get(namespace, 'bi-link-45deg'))


def _guess_group_icon(group_key):
    return _plain_text(GROUP_ICON_DEFAULTS.get(group_key, 'bi-folder2-open'))


def _normalize_permissions(value):
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [item for item in value if item]
    return []


def _infer_model(pattern):
    callback = getattr(pattern, 'callback', None)
    view_class = getattr(callback, 'view_class', None)
    if view_class is not None:
        queryset = getattr(view_class, 'queryset', None)
        if getattr(queryset, 'model', None) is not None:
            return queryset.model
        model = getattr(view_class, 'model', None)
        if model is not None:
            return model
    return None


def _infer_callback_app_label(callback):
    module_name = getattr(callback, '__module__', '') or ''
    root_module = module_name.split('.')[0] if module_name else ''
    if not root_module:
        return None
    try:
        apps.get_app_config(root_module)
        return root_module
    except LookupError:
        return None


def _infer_group_key(url_name, model, callback):
    explicit = getattr(callback, 'sidebar_group', None)
    if explicit:
        return explicit
    leaf = _route_leaf(url_name)
    if leaf in SYSTEM_ROUTE_META:
        return SYSTEM_ROUTE_META[leaf]['group_key']
    if model is not None:
        return model._meta.app_label
    callback_app = _infer_callback_app_label(callback)
    if callback_app:
        return callback_app
    if ':' in url_name:
        return url_name.split(':')[0]
    return 'general'


def _group_label(group_key, strings, lang_code=None):
    if group_key == 'dlux':
        return _plain_text(strings.get('sidebar_system', 'System Management'))

    translation_key = f'app_{group_key}'
    if translation_key in strings:
        return _plain_text(strings.get(translation_key))

    try:
        app_config = apps.get_app_config(group_key)
        verbose_name = _plain_text(app_config.verbose_name)
    except LookupError:
        verbose_name = ''

    if (lang_code or '').split('-')[0] == 'ar' and verbose_name:
        return verbose_name

    return _humanize(group_key)


def _infer_label(url_name, strings, model=None, callback=None):
    explicit = getattr(callback, 'sidebar_label', None)
    if explicit:
        return _plain_text(explicit)

    leaf = _route_leaf(url_name)
    namespace = url_name.split(':')[0] if ':' in url_name else ''
    group_key = _infer_group_key(url_name, model, callback)
    group_label = _group_label(group_key, strings)

    if leaf in SYSTEM_ROUTE_META:
        return _plain_text(strings.get(SYSTEM_ROUTE_META[leaf]['label_key'], _humanize(leaf)))

    candidates = [
        f'view_{leaf}',
        f'page_title_{namespace}_{leaf}' if namespace else '',
        f'page_title_{leaf}',
        f'{namespace}_{leaf}' if namespace else '',
        leaf,
    ]
    for key in candidates:
        if key and key in strings:
            return _plain_text(strings[key])

    if model is not None:
        from ..translations import resolve_model_label
        if leaf in ['dashboard', 'index', 'home']:
            return _plain_text(strings.get(f'{model._meta.app_label}_{leaf}', _humanize(f'{model._meta.app_label} {leaf}')))
        # Every model-name label (list pages and generic model routes alike)
        # resolves through the shared plural→singular→raw entry point.
        return _plain_text(resolve_model_label(model, strings))

    if leaf in ['dashboard', 'index', 'home'] and namespace:
        return _plain_text(f"{group_label} {_humanize(leaf)}")

    return _plain_text(_humanize(leaf))


def _infer_permissions(url_name, model, callback):
    explicit = _normalize_permissions(getattr(callback, 'sidebar_permissions', None))
    if explicit:
        return explicit, True

    explicit = _normalize_permissions(getattr(callback, 'permission_required', None))
    if explicit:
        return explicit, True

    leaf = _route_leaf(url_name)
    if leaf in SYSTEM_ROUTE_META:
        perms = list(SYSTEM_ROUTE_META[leaf].get('permissions', []))
        return perms, True

    if model is not None:
        perm = f'{model._meta.app_label}.view_{model._meta.model_name}'
        return [perm], False

    # For function-based views, try to infer from URL namespace and name
    app_label = None
    model_name = None
    
    # Try to get app label from URL namespace
    if ':' in url_name:
        namespace = url_name.split(':')[0]
        app_label = namespace
        # Get the leaf part for model name
        leaf = url_name.split(':')[-1]
        # Extract model name from patterns like outgoing_list, incoming_list, etc.
        if '_' in leaf:
            parts = leaf.split('_')
            # For patterns like outgoing_list, incoming_list, use the first part as model name
            if parts[-1] in ['list', 'index', 'dashboard', 'home']:
                model_name = parts[0]
            else:
                # For other patterns, use the first part as model name
                model_name = parts[0]
        else:
            model_name = leaf
    
    # If no namespace, try to infer from callback module
    if not app_label and callback:
        module_name = getattr(callback, '__module__', '') or ''
        if module_name:
            # module_name is like 'documents.views' or 'documents'
            app_label = module_name.split('.')[0]
            # Try to get model name from URL name
            leaf = url_name.split(':')[-1] if ':' in url_name else url_name
            if '_' in leaf:
                parts = leaf.split('_')
                if parts[-1] in ['list', 'index', 'dashboard', 'home']:
                    model_name = parts[0]
                else:
                    model_name = parts[0]
            else:
                model_name = leaf
    
    if app_label and model_name:
        perm = f'{app_label}.view_{model_name}'
        return [perm], False

    return [], False


def _normalize_sidebar_labels(value):
    """Per-language label override map for a sidebar entry: ``{lang_code: label}``.

    Mirrors the navbar builder's ``labels`` model so multilingual apps can name a
    sidebar entry per display language. Values are plain-text sanitized; empty
    codes/labels are dropped. Returns ``{}`` when nothing usable is present.
    """
    if not isinstance(value, dict):
        return {}
    labels = {}
    for raw_code, raw_label in value.items():
        code = str(raw_code or '').strip().lower()
        label = str(_plain_text(raw_label) or '').strip()
        if code and label:
            labels[code] = label
    return labels


def _pick_sidebar_label(labels, lang_code):
    """Resolve a per-language override for the current display language.

    Unlike the navbar (which has no auto-translation and falls back to the first
    available label), the sidebar deliberately returns ``''`` when the current
    language has no explicit override, so the caller falls through to the
    auto-discovered, per-language catalog label instead of a wrong-language one.
    """
    if not isinstance(labels, dict) or not labels:
        return ''
    code = str(lang_code or '').strip().lower()
    base = code.split('-')[0]
    return str(labels.get(code) or labels.get(base) or '').strip()
