"""Cache keys and versioning for the discovered route catalog and rendered sidebar."""

import hashlib
import json
from django.conf import settings
from django.core.cache import cache
from django.urls import get_resolver


SIDEBAR_CACHE_TIMEOUT = 300


SIDEBAR_CACHE_VERSION_KEY = 'dlux:sidebar:version'


SIDEBAR_CACHE_SCHEMA_VERSION = 3


def _stable_hash(value):
    try:
        payload = json.dumps(value, sort_keys=True, default=str, separators=(',', ':'))
    except TypeError:
        payload = repr(value)
    return hashlib.md5(payload.encode()).hexdigest()[:12]


def _sidebar_cache_version():
    version = cache.get(SIDEBAR_CACHE_VERSION_KEY)
    if version is None:
        version = 1
        cache.set(SIDEBAR_CACHE_VERSION_KEY, version, timeout=None)
    return version


def bump_sidebar_cache_version():
    try:
        cache.incr(SIDEBAR_CACHE_VERSION_KEY)
    except ValueError:
        cache.set(SIDEBAR_CACHE_VERSION_KEY, 2, timeout=None)


def _urlconf_cache_identity():
    resolver = get_resolver()
    return {
        'root': getattr(settings, 'ROOT_URLCONF', ''),
        'module': getattr(getattr(resolver, 'urlconf_module', None), '__name__', ''),
        'patterns_id': id(getattr(resolver, 'url_patterns', None)),
    }


def _route_catalog_cache_key(lang_code, config):
    # One entry per language for the whole install: the catalog is unfiltered,
    # so per-feature projections no longer each need their own cached copy.
    return 'dlux:routes:catalog:{schema}:{version}:{payload}'.format(
        schema=SIDEBAR_CACHE_SCHEMA_VERSION,
        version=_sidebar_cache_version(),
        payload=_stable_hash({
            'lang': lang_code,
            'urlconf': _urlconf_cache_identity(),
            'config': {
                'default_language': config.get('default_language'),
                'translations': config.get('translations'),
            },
        }),
    )


def _user_sidebar_permission_hash(user):
    if not user or not getattr(user, 'is_authenticated', False):
        return 'anonymous'
    permissions = []
    try:
        permissions = sorted(user.get_all_permissions())
    except Exception:
        permissions = sorted(getattr(user, '_permissions', []) or [])
    try:
        profile = getattr(user, 'profile', None)
    except Exception:
        profile = None
    scope_id = getattr(profile, 'scope_id', None) if profile is not None else getattr(user, 'scope_id', None)
    return _stable_hash({
        'user_id': getattr(user, 'pk', None),
        'is_staff': bool(getattr(user, 'is_staff', False)),
        'is_superuser': bool(getattr(user, 'is_superuser', False)),
        'scope_id': scope_id,
        'permissions': permissions,
    })


def _sidebar_render_cache_key(lang_code, sidebar, override_sidebar, user):
    return 'dlux:sidebar:render:{schema}:{version}:{payload}'.format(
        schema=SIDEBAR_CACHE_SCHEMA_VERSION,
        version=_sidebar_cache_version(),
        payload=_stable_hash({
            'lang': lang_code,
            'sidebar': sidebar,
            'override': override_sidebar,
            'user': _user_sidebar_permission_hash(user),
            'urlconf': _urlconf_cache_identity(),
        }),
    )
