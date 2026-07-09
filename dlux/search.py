"""Global search backend.

Builds a unified, permission-aware index of the app's navigable *components* —
pages/views (from the sidebar route discovery), System Settings sections (opened
as the same step-deep-linked dynamic modal the Options page uses), and a few
titlebar/nav actions — plus an optional generic *data* provider that searches
text fields of the project's real models. Powers the titlebar global-search
dropdown (see ``global_search.js`` / ``global_search_view``).

Everything is translated through ``DLUX_STRINGS`` and cached per language +
route/config version (mirroring the sidebar catalog). Results are filtered per
user: pages by their inferred permissions, settings by superuser, data by each
model's ``view`` permission (scoped models are additionally row-filtered for free
because ``ScopedManager`` scopes to the current thread-local user).
"""
import re

from django.conf import settings
from django.core.cache import cache
from django.db import models as dj_models
from django.db.models import Q
from django.urls import NoReverseMatch, reverse
from django.utils.module_loading import import_string

SEARCH_INDEX_CACHE_TIMEOUT = 300
RESULT_LIMIT_PER_GROUP = 8
DATA_LIMIT_PER_MODEL = 5
DATA_TOTAL_LIMIT = 20
MIN_QUERY_LEN = 2

# System Settings sections, mirroring the Options page tiles so a settings hit
# opens exactly the same step-deep-linked dynamic modal the UI already uses:
# (step index, title string key, icon, extra keyword hints for field-level finds).
SETTINGS_SECTIONS = (
    (0, 'system_settings_branding', 'bi-palette-fill',
     ('identity', 'system name', 'logo', 'favicon', 'branding', 'home url', 'organization')),
    (1, 'system_settings_languages', 'bi-translate',
     ('language', 'locale', 'translation', 'rtl', 'default language')),
    (2, 'system_settings_security', 'bi-shield-lock',
     ('security', '2fa', 'two factor', 'password', 'strong password', 'lockout', 'login lockout',
      'inactivity', 'timeout', 'session', 'purge session', 'browser close', 'sign out',
      'client ip', 'privacy', 'consent', 'registration', 'public root')),
    (3, 'system_settings_login_page', 'bi-box-arrow-in-right',
     ('login page', 'hero', 'banner', 'login style', 'split', 'centered')),
    (4, 'system_settings_sidebar', 'bi-layout-sidebar-inset',
     ('sidebar', 'menu', 'navigation', 'collapse', 'side nav')),
    (5, 'system_settings_navbar', 'bi-signpost-split',
     ('navbar', 'nav bar', 'breadcrumb', 'hierarchy')),
    (6, 'system_settings_ui_layout', 'bi-window-stack',
     ('titlebar', 'title bar', 'global search', 'search', 'user hub', 'actions', 'density',
      'modal size', 'zebra', 'sticky headers', 'footer', 'ui', 'layout')),
    (7, 'system_settings_notifications', 'bi-bell-fill',
     ('notification', 'flash', 'toast', 'drawer', 'alerts')),
    (8, 'system_settings_appearance', 'bi-brush',
     ('theme', 'appearance', 'font', 'typography', 'color', 'dark mode')),
    (9, 'system_settings_logging', 'bi-journal-text',
     ('logging', 'activity log', 'audit', 'retention')),
    (10, 'system_settings_profile', 'bi-person-badge',
     ('profile', 'avatar', 'profile page')),
    (11, 'system_settings_backups', 'bi-safe2-fill',
     ('backup', 'restore', 'export', 'import')),
)

# Curated titlebar/nav actions that are not ordinary sidebar routes. Deduped
# against discovered pages by URL. (url_name, string key, fallback, icon, visibility)
CURATED_ACTIONS = (
    ('user_profile', 'btn_profile', 'My Profile', 'bi-person-circle', 'authenticated'),
    ('options_view', 'nav_options', 'Options', 'bi-sliders', 'authenticated'),
)

# User-preference cards on the Options page (available to every authenticated
# user, unlike the superuser System Settings sections). A result deep-links to
# the Options page and scrolls to the card via its data-options-card slug.
# (card slug, title string key, fallback, icon, keyword hints)
OPTIONS_CARDS = (
    ('accessibility', 'accessibility', 'Accessibility', 'bi-eye', ('contrast', 'grayscale', 'large text', 'animations')),
    ('landing-page', 'options_landing_page', 'Landing page', 'bi-house-door', ('home', 'start page')),
    ('theme', 'themes', 'Theme', 'bi-palette', ('theme', 'dark mode', 'color', 'appearance')),
    ('language', 'language', 'Language', 'bi-translate', ('language', 'locale', 'rtl', 'arabic')),
    ('typography', 'typography', 'Typography', 'bi-fonts', ('font', 'typeface', 'text size')),
    ('table-density', 'table_density', 'Table density', 'bi-table', ('table', 'rows', 'spacing')),
    ('form-density', 'form_density', 'Form density', 'bi-textarea-resize', ('form', 'fields', 'spacing')),
    ('modal-size', 'modal_size', 'Modal size', 'bi-window', ('dialog', 'popup', 'width')),
    ('navbar-mode', 'navbar_options_title', 'Nav bar', 'bi-signpost-split', ('breadcrumb', 'navigation')),
    ('sidebar-density', 'sidebar_density', 'Sidebar density', 'bi-layout-sidebar-inset', ('sidebar', 'menu', 'spacing')),
    ('autofill', 'autofill', 'Autofill', 'bi-magic', ('autofill', 'auto fill', 'form')),
)

_EXCLUDE_FIELD_HINTS = ('password', 'secret', 'token', 'hash', 'encrypted', 'salt', 'signature')


def _humanize(value):
    return str(value or '').replace('_', ' ').strip().title()


# ── component index (cached) ─────────────────────────────────────────────────

def _component_index(lang_code):
    from .discovery import discover_sidebar_catalog
    from .translations import get_strings
    from .utils import get_system_config

    config = get_system_config()
    strings = get_strings(lang_code, overrides=config.get('translations'))
    entries = []
    page_urls = set()

    for entry in discover_sidebar_catalog(lang_code=lang_code, include_system_items=True):
        page_urls.add(entry['url'])
        entries.append({
            'type': 'page',
            'label': entry['label'],
            'sublabel': entry.get('group_label', ''),
            'icon': entry.get('icon') or 'bi-link-45deg',
            'url': entry['url'],
            'mode': 'link',
            'keywords': entry.get('group_label', ''),
            '_vis': ('permissions', tuple(entry.get('permissions') or ())),
        })

    try:
        settings_url = reverse('modal_manager', args=['dlux', 'SystemSettings', '1'])
    except NoReverseMatch:
        settings_url = None
    if settings_url:
        settings_group = strings.get('search_group_settings', 'Settings')
        for step, title_key, icon, keywords in SETTINGS_SECTIONS:
            entries.append({
                'type': 'setting',
                'label': strings.get(title_key, _humanize(title_key.replace('system_settings_', ''))),
                'sublabel': settings_group,
                'icon': icon,
                'url': f'{settings_url}?step={step}',
                'mode': 'modal',
                'keywords': ' '.join(keywords),
                '_vis': ('superuser', ()),
            })

    for url_name, label_key, fallback, icon, visibility in CURATED_ACTIONS:
        try:
            url = reverse(url_name)
        except NoReverseMatch:
            continue
        if url in page_urls:
            continue
        entries.append({
            'type': 'action',
            'label': strings.get(label_key, fallback),
            'sublabel': strings.get('search_group_actions', 'Actions'),
            'icon': icon,
            'url': url,
            'mode': 'link',
            'keywords': '',
            '_vis': (visibility, ()),
        })

    try:
        options_url = reverse('options_view')
    except NoReverseMatch:
        options_url = None
    if options_url:
        options_group = strings.get('search_group_options', 'Options')
        for slug, label_key, fallback, icon, keywords in OPTIONS_CARDS:
            entries.append({
                'type': 'option',
                'label': strings.get(label_key, fallback),
                'sublabel': options_group,
                'icon': icon,
                'url': f'{options_url}#dlux-option-{slug}',
                'mode': 'link',
                'keywords': ' '.join(keywords),
                '_vis': ('authenticated', ()),
            })

    return entries


def get_component_index(lang_code=None):
    from .discovery import _sidebar_cache_version
    from .utils import get_system_config

    config = get_system_config()
    lang_code = (lang_code or config.get('default_language', 'en')).split('-')[0]
    key = f'dlux:search:index:{_sidebar_cache_version()}:{lang_code}'
    index = cache.get(key)
    if index is None:
        index = _component_index(lang_code)
        cache.set(key, index, SEARCH_INDEX_CACHE_TIMEOUT)
    return index


# ── permission filter + ranking ──────────────────────────────────────────────

def _entry_visible(entry, user):
    kind, payload = entry['_vis']
    if kind == 'superuser':
        return bool(user and getattr(user, 'is_superuser', False))
    if kind == 'authenticated':
        return bool(user and getattr(user, 'is_authenticated', False))
    if kind == 'permissions':
        from .discovery import _user_has_sidebar_permission
        return _user_has_sidebar_permission(user, list(payload))
    return False


def _score(entry, q):
    label = entry['label'].lower()
    if label == q:
        return 100
    if label.startswith(q):
        return 80
    if any(word.startswith(q) for word in re.split(r'\s+', label) if word):
        return 60
    if q in label:
        return 40
    if q in (entry.get('keywords') or '').lower():
        return 30
    if q in (entry.get('sublabel') or '').lower():
        return 20
    return 0


def search_components(user, query, lang_code=None):
    q = (query or '').strip().lower()
    if len(q) < MIN_QUERY_LEN:
        return []
    scored = []
    for entry in get_component_index(lang_code):
        if not _entry_visible(entry, user):
            continue
        score = _score(entry, q)
        if score > 0:
            scored.append((score, entry))
    scored.sort(key=lambda pair: (-pair[0], pair[1]['label'].lower()))
    return [entry for _, entry in scored]


# ── generic data provider ────────────────────────────────────────────────────

def _identity_labels():
    """The user-account identity models (User + Profile) — searchable data even
    though ``is_model_loggable`` special-cases them out of the log catalog."""
    from django.apps import apps
    from django.contrib.auth import get_user_model

    labels = {get_user_model()._meta.label_lower}
    try:
        labels.add(apps.get_model('dlux', 'Profile')._meta.label_lower)
    except Exception:
        pass
    return labels


def _searchable_models(user):
    from django.apps import apps
    from .utils.activity_log import is_model_loggable

    allow = getattr(settings, 'DLUX_SEARCH_DATA_MODELS', None)
    allow = {str(k).lower() for k in allow} if allow else None
    identity = _identity_labels()
    models = []
    for model in apps.get_models():
        meta = model._meta
        if meta.auto_created or meta.proxy or meta.abstract:
            continue
        key = meta.label_lower
        if allow is not None:
            if key not in allow:
                continue
        elif not (is_model_loggable(key, meta.app_label) or key in identity):
            continue
        if not (getattr(user, 'is_superuser', False)
                or user.has_perm(f'{meta.app_label}.view_{meta.model_name}')):
            continue
        models.append(model)
    return models


def _text_field_names(model):
    names = []
    for field in model._meta.get_fields():
        if not isinstance(field, (dj_models.CharField, dj_models.TextField)):
            continue
        if getattr(field, 'primary_key', False):
            continue
        lname = field.name.lower()
        if any(hint in lname for hint in _EXCLUDE_FIELD_HINTS):
            continue
        names.append(field.name)
    return names


def _data_url_resolver():
    path = getattr(settings, 'DLUX_SEARCH_DATA_URL_RESOLVER', None)
    if not path:
        return None
    try:
        return import_string(path)
    except Exception:
        return None


def _default_data_url(obj):
    meta = obj._meta
    for name in (f'{meta.model_name}_detail', f'{meta.model_name}_update',
                 f'{meta.app_label}_{meta.model_name}_detail'):
        try:
            return reverse(name, args=[obj.pk])
        except NoReverseMatch:
            continue
    return None


def _truncate(value, length=90):
    text = str(value or '').strip()
    return text if len(text) <= length else text[:length - 1] + '…'


def search_data(user, query, lang_code=None, limit=DATA_TOTAL_LIMIT):
    from .translations import get_strings

    q = (query or '').strip()
    if len(q) < MIN_QUERY_LEN:
        return []
    strings = get_strings(lang_code) if lang_code else get_strings()
    resolver = _data_url_resolver()
    results = []
    remaining = limit
    for model in _searchable_models(user):
        if remaining <= 0:
            break
        text_fields = _text_field_names(model)
        condition = Q()
        for field_name in text_fields:
            condition |= Q(**{f'{field_name}__icontains': q})
        if q.isdigit():
            condition |= Q(pk=int(q))
        if not condition:
            continue
        try:
            rows = list(model._default_manager.filter(condition)[:min(DATA_LIMIT_PER_MODEL, remaining)])
        except Exception:
            continue
        model_label = str(model._meta.verbose_name).strip().title()
        for obj in rows:
            url = (resolver(obj) if resolver else None) or _default_data_url(obj)
            results.append({
                'type': 'data',
                'label': _truncate(str(obj)) or f'{model_label} #{obj.pk}',
                'sublabel': model_label,
                'icon': 'bi-database-fill',
                'url': url,
                'mode': 'link' if url else 'none',
            })
            remaining -= 1
    return results


# ── orchestrator (used by the view) ──────────────────────────────────────────

_PUBLIC_KEYS = ('type', 'label', 'sublabel', 'icon', 'url', 'mode')


def _clean(entry):
    return {key: entry.get(key) for key in _PUBLIC_KEYS}


def run_search(user, query, *, include_data=False, lang_code=None):
    """Return grouped, permission-filtered results:
    ``[{'type': 'page'|'setting'|'action'|'data', 'items': [...]}]``."""
    components = search_components(user, query, lang_code)
    buckets = {'page': [], 'setting': [], 'option': [], 'action': []}
    for entry in components:
        buckets.setdefault(entry['type'], []).append(entry)

    groups = []
    for group_type in ('page', 'setting', 'option', 'action'):
        items = [_clean(entry) for entry in buckets.get(group_type, [])[:RESULT_LIMIT_PER_GROUP]]
        if items:
            groups.append({'type': group_type, 'items': items})

    if include_data:
        data_items = [_clean(entry) for entry in search_data(user, query, lang_code)]
        if data_items:
            groups.append({'type': 'data', 'items': data_items})

    return groups
