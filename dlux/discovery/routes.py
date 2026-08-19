"""URLconf traversal: what routes exist, and which are navigable.

`_root_urlconf_is_loading()` lives here: discovery runs during app loading, and
resolving a URL while the project's ROOT_URLCONF is still importing leaves Django
with a half-built module. Nothing in this module may reverse() without that guard."""

import copy
import re
import sys
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.urls import NoReverseMatch, URLPattern, URLResolver, get_resolver, reverse
from ..system.constants import (
    DISCOVERY_PROFILE_SIDEBAR,
    DISCOVERY_PROFILES,
    ROUTE_ACTION_API,
    ROUTE_ACTION_ASYNC,
    ROUTE_ACTION_EDIT,
    ROUTE_ACTION_FORM,
    ROUTE_ACTION_MACHINERY,
    ROUTE_ACTION_PAGE,
    ROUTE_ASYNC_TOKENS,
    ROUTE_EDIT_TOKENS,
    ROUTE_FORM_TOKENS,
    ROUTE_MACHINERY_EXACT_NAMES,
    ROUTE_MACHINERY_NAME_PARTS,
    ROUTE_MACHINERY_NAMESPACES,
    ROUTE_MACHINERY_PATH_PARTS,
)

from .cache import SIDEBAR_CACHE_TIMEOUT, _route_catalog_cache_key
from .inference import _group_label, _guess_group_icon, _guess_icon, _infer_group_key, _infer_label, _infer_model, _infer_permissions
from .meta import CONFIGURABLE_SYSTEM_ROUTE_NAMES, HIDDEN_SIDEBAR_GROUP_KEYS, _route_leaf, _route_name_tokens


def _iterate_named_patterns(patterns, namespaces=None, prefix=''):
    """Yield (pattern, full_route_name, path_template) for every named route.

    The path template is accumulated across nested resolvers so routes that take
    arguments — and therefore cannot be reversed — still carry a path to
    classify against.
    """
    namespaces = namespaces or []
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            next_namespaces = list(namespaces)
            if pattern.namespace:
                next_namespaces.append(pattern.namespace)
            yield from _iterate_named_patterns(
                pattern.url_patterns,
                next_namespaces,
                prefix=f'{prefix}{pattern.pattern}',
            )
        elif isinstance(pattern, URLPattern) and pattern.name:
            full_name = ':'.join(namespaces + [pattern.name]) if namespaces else pattern.name
            yield pattern, full_name, f'/{prefix}{pattern.pattern}'


def _has_api_route_token(value):
    tokens = [token for token in re.split(r'[^a-z0-9]+', str(value or '').lower()) if token]
    return any(token == 'api' or re.fullmatch(r'api(?:v?\d+)', token) for token in tokens)


def _callback_looks_like_api(callback):
    view_class = getattr(callback, 'view_class', None)
    for name in (getattr(callback, '__name__', ''), getattr(view_class, '__name__', '')):
        if _has_api_route_token(name):
            return True
        if re.search(r'(?:^|[a-z0-9])(?:API|Api)(?=[A-Z0-9]|$)', str(name or '')):
            return True
    return False


def _root_urlconf_is_loading():
    """True while the project's ROOT_URLCONF is still executing.

    A project's urls.py calls ``include('dlux.urls')`` inside the ``urlpatterns``
    list literal, so during that call its own module exists but has no
    ``urlpatterns`` yet. Resolving a URL in that window makes Django cache the
    half-built module on the resolver, and every later check then fails with
    "The included URLconf does not appear to have any patterns in it".
    """
    root = getattr(settings, 'ROOT_URLCONF', None)
    if not isinstance(root, str):
        return False
    module = sys.modules.get(root)
    return module is not None and not hasattr(module, 'urlpatterns')


def _is_api_navigation_route(url_name='', url='', callback=None):
    if _has_api_route_token(url_name) or _has_api_route_token(url):
        return True
    if callback is not None and _callback_looks_like_api(callback):
        return True
    # dlux's gettext patch can reach here from a module body (Django resolves a
    # lazy string while building a form class), so this runs mid-import.
    if url_name and not _root_urlconf_is_loading():
        try:
            return _has_api_route_token(reverse(url_name))
        except NoReverseMatch:
            pass
    return False


def _is_configurable_system_url(url_name):
    return isinstance(url_name, str) and _route_leaf(url_name) in CONFIGURABLE_SYSTEM_ROUTE_NAMES


def _classify_route(url_name, url, path_template, callback):
    """Return what a route IS, never whether a given feature wants it."""
    leaf = _route_leaf(url_name)
    lower_name = url_name.lower()
    lower_leaf = leaf.lower()
    namespace = url_name.split(':')[0] if ':' in url_name else ''
    leaf_tokens = set(_route_name_tokens(leaf))
    paths = [value for value in (url, path_template) if value]

    if namespace in ROUTE_MACHINERY_NAMESPACES:
        return ROUTE_ACTION_MACHINERY
    # API counterparts of page views otherwise surface as duplicate,
    # non-navigable sidebar, navbar, and landing-page entries.
    if _is_api_navigation_route(url_name, url, callback):
        return ROUTE_ACTION_API
    # A configurable system page (Manage Users) shares a leaf name with the
    # machinery list; it stays a page and is gated by `include_system_items`.
    if lower_leaf in ROUTE_MACHINERY_EXACT_NAMES and not _is_configurable_system_url(url_name):
        return ROUTE_ACTION_MACHINERY
    if any(part in lower_name for part in ROUTE_MACHINERY_NAME_PARTS):
        return ROUTE_ACTION_MACHINERY
    if any(part in path for path in paths for part in ROUTE_MACHINERY_PATH_PARTS):
        return ROUTE_ACTION_MACHINERY
    if leaf_tokens & ROUTE_ASYNC_TOKENS:
        return ROUTE_ACTION_ASYNC
    if leaf_tokens & ROUTE_EDIT_TOKENS:
        return ROUTE_ACTION_EDIT
    if leaf_tokens & ROUTE_FORM_TOKENS:
        return ROUTE_ACTION_FORM
    return ROUTE_ACTION_PAGE


def _is_candidate(url_name, url, callback, profile=DISCOVERY_PROFILE_SIDEBAR):
    """Whether one route passes a feature profile. Classification plus filter, for
    callers that hold a route rather than a catalog entry."""
    action = _classify_route(url_name, url, '', callback)
    excluded_from = _callback_profile_opt(callback, 'dlux_exclude')
    if getattr(callback, 'sidebar_exclude', False):
        excluded_from = excluded_from | frozenset(DISCOVERY_PROFILES)
    return _profile_allows({
        'url': url,
        'action': action,
        'excluded_from': excluded_from,
        'included_in': _callback_profile_opt(callback, 'dlux_include'),
    }, profile)


def _callback_profile_opt(callback, attribute):
    """Read a per-view opt-in/opt-out declaration as a set of profile names.

    ``dlux_exclude = True`` (or ``dlux_include = True``) applies to every
    profile; a string or iterable names specific ones.
    """
    value = getattr(callback, attribute, None)
    if value is None or value is False:
        return frozenset()
    if value is True:
        return frozenset(DISCOVERY_PROFILES)
    if isinstance(value, str):
        value = (value,)
    return frozenset(str(name).strip() for name in value if str(name).strip())


def _profile_allows(entry, profile):
    """Whether one feature profile accepts a discovered route."""
    rules = DISCOVERY_PROFILES.get(profile)
    if rules is None:
        raise ValueError(f'Unknown discovery profile: {profile!r}')
    if profile in entry.get('excluded_from', ()):
        return False
    if rules['require_url'] and not entry.get('url'):
        return False
    if profile in entry.get('included_in', ()):
        return True
    return entry.get('action') in rules['actions']


def _discover_routes_uncached(lang_code=None, config=None):
    """Walk the URLconf and describe every named route, excluding nothing."""
    from ..translations import get_strings
    from ..utils import get_system_config

    config = config if isinstance(config, dict) else get_system_config()
    lang_code = (lang_code or config.get('default_language', 'en')).split('-')[0]
    strings = get_strings(lang_code, overrides=config.get('translations'))

    catalog = []
    resolver = get_resolver()
    for pattern, url_name, path_template in _iterate_named_patterns(resolver.url_patterns):
        callback = getattr(pattern, 'callback', None)
        try:
            url = reverse(url_name)
        except NoReverseMatch:
            # Reachable only with arguments (an id-bound edit or detail page).
            # Still catalogued: the Nav Bar hierarchy matches on route name.
            url = ''

        model = _infer_model(pattern)
        group_key = _infer_group_key(url_name, model, callback)
        group_label = _group_label(group_key, strings, lang_code=lang_code)
        permissions, permissions_explicit = _infer_permissions(url_name, model, callback)
        action = _classify_route(url_name, url, path_template, callback)
        excluded_from = _callback_profile_opt(callback, 'dlux_exclude')
        if getattr(callback, 'sidebar_exclude', False):
            excluded_from = excluded_from | frozenset(DISCOVERY_PROFILES)
        entry = {
            'kind': 'item',
            'id': url_name,
            'url_name': url_name,
            'url': url,
            'label': _infer_label(url_name, strings, model=model, callback=callback),
            'icon': _guess_icon(url_name, model=model, callback=callback),
            'permissions': permissions,
            'permissions_explicit': permissions_explicit,
            'group_key': group_key,
            'group_label': group_label,
            'group_icon': _guess_group_icon(group_key),
            'is_system': _is_configurable_system_url(url_name),
            'action': action,
            'is_form_page': action == ROUTE_ACTION_FORM,
            'requires_args': not url,
            'path_template': path_template,
            'excluded_from': sorted(excluded_from),
            'included_in': sorted(_callback_profile_opt(callback, 'dlux_include')),
        }
        if model is not None:
            entry['notification_model_key'] = model._meta.label_lower
        catalog.append(entry)

    catalog.sort(key=lambda entry: (entry['group_label'], entry['label']))
    return catalog


def discover_routes(lang_code=None):
    """Return the global route catalog: every named route, classified, unfiltered.

    Consumers should almost always call :func:`discover_routes_for` instead —
    this is the shared, feature-agnostic source those projections are built from.
    """
    from ..utils import get_system_config

    config = get_system_config()
    lang_code = (lang_code or config.get('default_language', 'en')).split('-')[0]
    cache_key = _route_catalog_cache_key(lang_code, config)
    catalog = cache.get(cache_key)
    if catalog is None:
        catalog = _discover_routes_uncached(lang_code=lang_code, config=config)
        cache.set(cache_key, catalog, timeout=SIDEBAR_CACHE_TIMEOUT)
    return copy.deepcopy(catalog)


def discover_routes_for(profile, lang_code=None, include_system_items=False):
    """Project the global catalog through one feature's profile.

    `include_system_items` is orthogonal to the profile: it controls whether the
    hidden `dlux` group's configurable system pages are offered, which every
    feature decides for itself.
    """
    return [
        entry
        for entry in discover_routes(lang_code=lang_code)
        if _profile_allows(entry, profile)
        and not (
            entry['group_key'] in HIDDEN_SIDEBAR_GROUP_KEYS
            and not (include_system_items and entry['is_system'])
        )
    ]


def discover_sidebar_catalog(lang_code=None, include_system_items=False):
    """Sidebar projection of the global catalog. Kept as the released public name."""
    return discover_routes_for(
        DISCOVERY_PROFILE_SIDEBAR,
        lang_code=lang_code,
        include_system_items=include_system_items,
    )


def known_route_names():
    """Every named route the project URLconf currently defines.

    Returns ``None`` — never an empty set — when the URLconf cannot be read yet,
    so callers can tell "no routes exist" apart from "cannot say", and skip
    pruning stored configuration rather than emptying it.
    """
    if _root_urlconf_is_loading():
        return None
    try:
        patterns = get_resolver().url_patterns
    except ImproperlyConfigured:
        return None
    return {url_name for _, url_name, _ in _iterate_named_patterns(patterns)}
