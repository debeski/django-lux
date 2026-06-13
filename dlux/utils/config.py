"""dlux.utils.config — Runtime config defaults/validators and the system-config builder.

Split from the original ``dlux/utils.py`` (kept intact, inert).
"""
import base64
import hashlib
import json
import os
import re
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from functools import lru_cache
import inspect
from pathlib import Path
import unicodedata
from django import forms
from django.apps import apps
from django.conf import settings
from django.contrib.messages import constants as messages
from django.db import models as dj_models
from django.db.models import ManyToManyRel, Q
from django.db.models.fields.files import FieldFile
from django.db.models.fields.related import ManyToManyField
from django.forms import modelform_factory
from django.http import JsonResponse
from django.core.mail import EmailMessage, get_connection, send_mail
from django.core.exceptions import FieldDoesNotExist
from django.utils.module_loading import import_string
from ..constants import (
    DEFAULT_HOME_URL,
    DEFAULT_NAVBAR_MODE,
    DEFAULT_SIDEBAR_COLLAPSE_MODE,
    DEFAULT_SIDEBAR_DENSITY,
    DEFAULT_TABLE_DENSITY,
    REGISTRATION_ACTIVATION_AUTO_LOGIN,
    REGISTRATION_ACTIVATION_VALUES,
    NAVBAR_MODE_VALUES,
    SIDEBAR_COLLAPSE_MODE_VALUES,
    SIDEBAR_DENSITY_VALUES,
    TABLE_DENSITY_VALUES,
    TITLEBAR_ALIGN_VALUES,
    TITLEBAR_HEIGHT_VALUES,
    TITLEBAR_HOME_SHAPE_VALUES,
    TITLEBAR_LOGO_TREATMENT_SHAPE_VALUES,
    TITLEBAR_LOGO_TREATMENT_VALUES,
    TITLEBAR_SIZE_VALUES,
    TITLEBAR_SURFACE_VALUES,
)
from ..fonts import DEFAULT_FONT_SLUG, get_builtin_fonts
from ..themes import is_valid_theme, normalize_allowed_themes
from ..translations import get_current_language_code, get_strings
# try-except for django_filters as it might not be installed (though likely is)
try:
    import django_filters
except ImportError:
    django_filters = None

# ── intra-package imports (shared + feature deps) ──
from .common import DEFAULT_LANGUAGE_CATALOG, _coerce_import_bool, _normalize_asset_url
from .localization import _merge_translation_layers, _normalize_language_code, normalize_language_catalog
from .navigation import _dedupe_sidebar_entries, default_navbar_config, default_sidebar_config, normalize_navbar_config, normalize_sidebar_behavior

_LEGACY_HOME_URL = '/sys/'

EMAIL_CONFIG_TRANSPORTS = {'direct', 'relay'}

EMAIL_CONFIG_SECRET_STORAGES = {'env', 'encrypted_db'}

CLIENT_IP_MODE_REMOTE_ADDR = 'remote_addr'

CLIENT_IP_MODE_X_FORWARDED_FOR = 'x_forwarded_for'

CLIENT_IP_MODE_X_REAL_IP = 'x_real_ip'

CLIENT_IP_MODE_CLOUDFLARE = 'cloudflare'

CLIENT_IP_MODE_CUSTOM = 'custom'

CLIENT_IP_MODE_AUTO = 'auto'

CLIENT_IP_MODE_VALUES = {
    CLIENT_IP_MODE_REMOTE_ADDR,
    CLIENT_IP_MODE_X_FORWARDED_FOR,
    CLIENT_IP_MODE_X_REAL_IP,
    CLIENT_IP_MODE_CLOUDFLARE,
    CLIENT_IP_MODE_CUSTOM,
    CLIENT_IP_MODE_AUTO,
}

# Email Config - Function returns the default outbound email configuration.
def default_email_config():
    return {
        'transport': 'direct',
        'secret_storage': 'env',
        'host': '',
        'port': 587,
        'use_tls': True,
        'use_ssl': False,
        'username': '',
        'default_from_email': '',
        'encrypted_password': '',
        'password_configured': False,
    }

# Client IP - Function returns the default client address resolution policy.
def default_client_ip_config():
    return {
        'mode': CLIENT_IP_MODE_X_FORWARDED_FOR,
        'trusted_proxy_hops': 1,
        'custom_header': '',
    }

# Client IP - Helper converts custom proxy headers to Django META keys.
def _normalize_client_ip_header_name(value):
    raw_value = str(value or '').strip()
    if not raw_value:
        return ''
    normalized = raw_value.upper().replace('-', '_')
    if normalized in {'REMOTE_ADDR', 'CONTENT_TYPE', 'CONTENT_LENGTH'}:
        return normalized
    if not normalized.startswith('HTTP_'):
        normalized = f'HTTP_{normalized}'
    return normalized

# Client IP - Function validates and clamps stored client IP settings.
def normalize_client_ip_config(value):
    normalized = default_client_ip_config()
    if not isinstance(value, dict):
        return normalized

    mode = str(value.get('mode') or '').strip().lower()
    if mode in CLIENT_IP_MODE_VALUES:
        normalized['mode'] = mode

    try:
        trusted_proxy_hops = int(value.get('trusted_proxy_hops', normalized['trusted_proxy_hops']))
    except (TypeError, ValueError):
        trusted_proxy_hops = normalized['trusted_proxy_hops']
    normalized['trusted_proxy_hops'] = max(0, min(trusted_proxy_hops, 8))

    normalized['custom_header'] = _normalize_client_ip_header_name(value.get('custom_header'))
    if normalized['mode'] != CLIENT_IP_MODE_CUSTOM:
        normalized['custom_header'] = ''

    return normalized

# Email Config - Function validates transport settings and optional secret redaction.
def normalize_email_config(value, *, redact_secret=False):
    config = value if isinstance(value, dict) else {}
    normalized = default_email_config()
    transport = str(config.get('transport') or '').strip()
    secret_storage = str(config.get('secret_storage') or '').strip()
    if transport in EMAIL_CONFIG_TRANSPORTS:
        normalized['transport'] = transport
    if secret_storage in EMAIL_CONFIG_SECRET_STORAGES:
        normalized['secret_storage'] = secret_storage
    normalized['host'] = str(config.get('host') or '').strip()
    try:
        normalized['port'] = int(config.get('port') or normalized['port'])
    except (TypeError, ValueError):
        normalized['port'] = 587
    normalized['use_tls'] = _coerce_import_bool(config.get('use_tls', normalized['use_tls']))
    normalized['use_ssl'] = _coerce_import_bool(config.get('use_ssl', normalized['use_ssl']))
    if normalized['use_ssl']:
        normalized['use_tls'] = False
    normalized['username'] = str(config.get('username') or '').strip()
    normalized['default_from_email'] = str(config.get('default_from_email') or '').strip()
    encrypted_password = str(config.get('encrypted_password') or '').strip()
    normalized['encrypted_password'] = encrypted_password
    normalized['password_configured'] = bool(encrypted_password or config.get('password_configured'))
    if redact_secret:
        normalized.pop('encrypted_password', None)
    return normalized

# Typography Config - Function keeps configured font slugs valid and unique.
def normalize_allowed_fonts(allowed_fonts=None):
    from ..fonts import get_builtin_fonts
    available = {f['slug'] for f in get_builtin_fonts()}
    if allowed_fonts is None:
        return list(available)

    normalized = []
    if isinstance(allowed_fonts, (list, tuple, set)):
        for font in allowed_fonts:
            if font in available and font not in normalized:
                normalized.append(font)

    return normalized or list(available)

# Client IP - Function resolves the request IP from the configured proxy strategy.
def get_client_ip(request):
    """Extract client IP address from request."""
    if not request:
        return None

    try:
        config = normalize_client_ip_config(get_system_config().get('client_ip'))
    except Exception:
        config = default_client_ip_config()

    meta = getattr(request, 'META', {}) or {}
    remote_addr = str(meta.get('REMOTE_ADDR') or '').strip()

    # Client IP - Helper reads a configured request header safely.
    def _header_value(header_name):
        return str(meta.get(header_name) or '').strip()

    # Client IP - Helper splits proxy IP chains into ordered candidates.
    def _parse_chain(raw_value):
        parts = [part.strip() for part in str(raw_value or '').split(',') if part.strip()]
        if not parts:
            return ''
        trusted_proxy_hops = max(0, int(config.get('trusted_proxy_hops', 1) or 0))
        if len(parts) > trusted_proxy_hops:
            return parts[-(trusted_proxy_hops + 1)]
        return parts[0]

    mode = config.get('mode', CLIENT_IP_MODE_X_FORWARDED_FOR)
    candidate = ''

    if mode == CLIENT_IP_MODE_AUTO:
        # Try each source in order; take the first non-empty result.
        # Leftmost XFF is the original client when a single trusted proxy is in play.
        xff_raw = _header_value('HTTP_X_FORWARDED_FOR')
        if xff_raw:
            candidate = xff_raw.split(',')[0].strip()
        if not candidate:
            candidate = _header_value('HTTP_X_REAL_IP')
        if not candidate:
            candidate = _header_value('HTTP_CF_CONNECTING_IP')
        if not candidate:
            candidate = remote_addr
    elif mode == CLIENT_IP_MODE_REMOTE_ADDR:
        candidate = remote_addr
    elif mode == CLIENT_IP_MODE_X_FORWARDED_FOR:
        candidate = _parse_chain(_header_value('HTTP_X_FORWARDED_FOR'))
    elif mode == CLIENT_IP_MODE_X_REAL_IP:
        candidate = _header_value('HTTP_X_REAL_IP')
    elif mode == CLIENT_IP_MODE_CLOUDFLARE:
        candidate = _header_value('HTTP_CF_CONNECTING_IP')
    elif mode == CLIENT_IP_MODE_CUSTOM:
        candidate = _header_value(config.get('custom_header'))

    if candidate:
        return candidate

    # Ordered fallback: XFF leftmost → X-Real-IP → REMOTE_ADDR
    xff_raw = _header_value('HTTP_X_FORWARDED_FOR')
    if xff_raw:
        leftmost = xff_raw.split(',')[0].strip()
        if leftmost:
            return leftmost
    x_real = _header_value('HTTP_X_REAL_IP')
    if x_real:
        return x_real
    return remote_addr or None

# Branding Config - Function normalizes language-keyed system display names.
def normalize_system_names(value):
    names = {}
    if isinstance(value, dict):
        for raw_code, raw_name in value.items():
            code = _normalize_language_code(raw_code)
            name = str(raw_name or '').strip()
            if code and name:
                names[code] = name
    return names

# Branding Config - Function selects the best system name for a language.
def resolve_system_name(system_names, lang_code=None, default_language='en'):
    names = normalize_system_names(system_names)
    lang = _normalize_language_code(lang_code) or _normalize_language_code(default_language) or 'en'
    default_lang = _normalize_language_code(default_language) or 'en'
    for code in (lang, default_lang):
        if code in names and names[code]:
            return names[code]
    for value in names.values():
        if value:
            return value
    return 'DjangoLux'

# System Config - Function builds grouped config views for templates and forms.
def build_config_groups(config, current_language=None):
    languages = normalize_language_catalog(config.get('languages', {}))
    default_language = _normalize_language_code(config.get('default_language')) or 'en'
    if default_language not in languages:
        default_language = 'en' if 'en' in languages else next(iter(languages), 'en')
    display_language = _normalize_language_code(current_language) or default_language
    if display_language not in languages:
        display_language = default_language
    system_names = normalize_system_names(config.get('system_names'))
    display_name = resolve_system_name(system_names, display_language, default_language)
    return {
        'identity': {
            'system_names': system_names,
            'display_name': display_name,
            'logo_url': config.get('logo_url'),
            'login_logo_url': config.get('login_logo_url'),
            'favicon_url': config.get('favicon_url'),
        },
        'localization': {
            'languages': languages,
            'default_language': default_language,
            'translations': config.get('translations', {}),
            'allow_user_language_override': bool(config.get('allow_user_language_override', True)),
        },
        'security': {
            'public_root': bool(config.get('public_root', False)),
            'email_2fa': bool(config.get('email_2fa', False)),
            'email_config': normalize_email_config(config.get('email_config', {}), redact_secret=True),
            'public_registration_enabled': bool(config.get('public_registration_enabled', False)),
            'registration_activation_mode': config.get(
                'registration_activation_mode',
                REGISTRATION_ACTIVATION_AUTO_LOGIN,
            ),
            'registration_throttle_enabled': bool(config.get('registration_throttle_enabled', True)),
        },
        'navigation': {
            'home_url': config.get('home_url') or DEFAULT_HOME_URL,
            'sidebar': config.get('sidebar', default_sidebar_config()),
            'navbar': config.get('navbar', default_navbar_config()),
        },
        'appearance': {
            'default_theme': config.get('default_theme', 'light'),
            'allowed_themes': list(config.get('allowed_themes', [])),
            'default_table_density': config.get('default_table_density', DEFAULT_TABLE_DENSITY),
            'titlebar': config.get('titlebar', default_titlebar_config()),
        },
        'personalization': {
            'allow_user_theme_override': bool(config.get('allow_user_theme_override', True)),
            'allow_user_language_override': bool(config.get('allow_user_language_override', True)),
            'allow_user_sidebar_density': bool(
                normalize_sidebar_behavior(config.get('sidebar', {})).get('allow_user_density', True)
            ),
        },
    }

# Titlebar Config - Function returns default titlebar behavior.
def default_titlebar_config():
    return {
        'show_title': True,
        'show_logo': True,
        'show_home_button': True,
        'hide_on_public_unauthenticated_index': False,
        'home_shape': 'circle',
        'title_align': 'start',
        'title_size': 'md',
        'height': 'balanced',
        'surface': 'default',
        'logo_treatment': 'none',
        'logo_treatment_shape': 'soft',
    }

# Titlebar Config - Function validates titlebar display settings.
def normalize_titlebar_config(titlebar_config):
    config = titlebar_config if isinstance(titlebar_config, dict) else {}
    normalized = default_titlebar_config()
    normalized['show_title'] = bool(config.get('show_title', normalized['show_title']))
    normalized['show_logo'] = bool(config.get('show_logo', normalized['show_logo']))
    normalized['show_home_button'] = bool(config.get('show_home_button', normalized['show_home_button']))
    normalized['hide_on_public_unauthenticated_index'] = bool(
        config.get(
            'hide_on_public_unauthenticated_index',
            normalized['hide_on_public_unauthenticated_index'],
        )
    )

    home_shape = config.get('home_shape')
    if home_shape in TITLEBAR_HOME_SHAPE_VALUES:
        normalized['home_shape'] = home_shape

    title_align = config.get('title_align')
    if title_align in TITLEBAR_ALIGN_VALUES:
        normalized['title_align'] = title_align

    title_size = config.get('title_size')
    if title_size in TITLEBAR_SIZE_VALUES:
        normalized['title_size'] = title_size

    height = config.get('height')
    if height in TITLEBAR_HEIGHT_VALUES:
        normalized['height'] = height

    surface = config.get('surface')
    if surface in TITLEBAR_SURFACE_VALUES:
        normalized['surface'] = surface

    logo_treatment = config.get('logo_treatment')
    if logo_treatment in TITLEBAR_LOGO_TREATMENT_VALUES:
        normalized['logo_treatment'] = logo_treatment

    logo_treatment_shape = config.get('logo_treatment_shape')
    if logo_treatment_shape in TITLEBAR_LOGO_TREATMENT_SHAPE_VALUES:
        normalized['logo_treatment_shape'] = logo_treatment_shape

    return normalized

LOGIN_STYLE_VALUES = {'split', 'centered', 'minimal', 'fullpage'}

# Login Config - Function returns default public login/register page settings.
def default_login_config():
    return {
        'style': 'split',
        'show_logo': True,
        'banner_color': '',
        'logo_treatment': 'none',
        'logo_treatment_shape': 'soft',
        'hero_message': '',
    }

# Login Config - Function validates login page branding and registration settings.
def normalize_login_config(value):
    config = value if isinstance(value, dict) else {}
    normalized = default_login_config()
    style = config.get('style')
    if style in LOGIN_STYLE_VALUES:
        normalized['style'] = style
    normalized['show_logo'] = bool(config.get('show_logo', True))
    banner_color = str(config.get('banner_color') or '').strip()
    if banner_color:
        normalized['banner_color'] = banner_color
    logo_treatment = config.get('logo_treatment')
    if logo_treatment in TITLEBAR_LOGO_TREATMENT_VALUES:
        normalized['logo_treatment'] = logo_treatment
    logo_treatment_shape = config.get('logo_treatment_shape')
    if logo_treatment_shape in TITLEBAR_LOGO_TREATMENT_SHAPE_VALUES:
        normalized['logo_treatment_shape'] = logo_treatment_shape
    raw_hero = config.get('hero_message')
    if isinstance(raw_hero, dict):
        normalized['hero_message'] = {
            str(k): str(v or '').strip()
            for k, v in raw_hero.items()
            if str(k or '').strip()
        }
    else:
        # Legacy plain string — store as-is for backwards compatibility
        normalized['hero_message'] = str(raw_hero or '').strip()
    return normalized

# Theme Config - Function resolves the allowed theme set with default protection.
def get_effective_allowed_themes(config):
    if not isinstance(config, dict):
        return tuple(normalize_allowed_themes())
    return tuple(normalize_allowed_themes(config.get('allowed_themes')))

# Theme Config - Function resolves user theme preference under system policy.
def resolve_user_theme_preference(user_prefs, config):
    prefs = dict(user_prefs or {})
    allowed_themes = set(get_effective_allowed_themes(config))
    default_theme = config.get('default_theme', 'light')
    if default_theme not in allowed_themes:
        default_theme = next(iter(allowed_themes), 'light')

    if not config.get('allow_user_theme_override', True):
        prefs.pop('theme', None)
        prefs['theme'] = default_theme
        return prefs

    if prefs.get('theme') not in allowed_themes:
        prefs['theme'] = default_theme
    return prefs

# Typography Config - Function validates per-language default font settings.
def normalize_default_fonts(value=None, *, allowed_fonts=None):
    """Normalize language-keyed default font settings against available fonts."""
    if not isinstance(value, dict):
        return {}
    allowed = set(normalize_allowed_fonts(allowed_fonts))
    if not allowed:
        allowed = {font['slug'] for font in get_builtin_fonts()}
    normalized = {}
    for raw_code, raw_font in value.items():
        code = _normalize_language_code(raw_code)
        font = str(raw_font or '').strip()
        if code and font in allowed:
            normalized[code] = font
    return normalized

# System Config - Function merges defaults, settings, and DB-backed runtime config.
def get_system_config():
    """
    Returns the deeply merged system configuration.
    1. Default config
    2. settings.DLUX_CONFIG (host project codebase)
    3. SystemSettings Singleton (database UI overrides)
    """
    # Default configuration
    default_config = {
        'system_names': {
            'en': 'DjangoLux',
            'ar': 'DjangoLux',
        },
        'verbose_name': 'DjangoLux',
        'logo': '/static/img/base_logo.svg',
        'login_logo': '/static/img/login_logo.svg',
        'favicon': '/static/img/base_logo.svg',
        'home_url': DEFAULT_HOME_URL,
        'default_language': 'en',
        'default_theme': 'light',
        'allowed_themes': list(normalize_allowed_themes()),
        'allow_user_theme_override': True,
        'default_font': DEFAULT_FONT_SLUG,
        'allowed_fonts': list(normalize_allowed_fonts()),
        'default_fonts': {},
        'allow_user_font_override': True,
        'allow_user_language_override': True,
        'default_table_density': DEFAULT_TABLE_DENSITY,
        'email_2fa': False,
        'prevent_multiple_active_sessions': False,
        'client_ip': default_client_ip_config(),
        'login': default_login_config(),
        'public_root': False,
        'public_root_split_enabled': False,
        'public_root_url': '',
        'public_registration_enabled': False,
        'registration_activation_mode': REGISTRATION_ACTIVATION_AUTO_LOGIN,
        'registration_throttle_enabled': True,
        'email_config': default_email_config(),
        'languages': deepcopy(DEFAULT_LANGUAGE_CATALOG),
        'translations': {},
        'sidebar': default_sidebar_config(),
        'navbar': default_navbar_config(),
        'titlebar': default_titlebar_config(),
        'is_configured': False,
    }

    # Project settings
    user_config = getattr(settings, 'DLUX_CONFIG', {})
    if not isinstance(user_config, dict):
        user_config = {}
    
    # DB settings
    db_config = {}
    try:
        from dlux.models import SystemSettings
        sys_settings = SystemSettings.load()
        system_is_configured = bool(getattr(sys_settings, 'is_configured', False))

        # System Config - Helper decides when DB settings should override file settings.
        def _should_apply_db_override(value, default):
            return system_is_configured or value != default

        if (
            isinstance(getattr(sys_settings, 'system_names', None), dict)
            and sys_settings.system_names
            and _should_apply_db_override(
                normalize_system_names(sys_settings.system_names),
                default_config['system_names'],
            )
        ):
            db_config['system_names'] = sys_settings.system_names
        if sys_settings.logo:
            db_config['logo'] = sys_settings.logo.url
            db_config['logo_url'] = sys_settings.logo.url
            db_config['login_logo_url'] = sys_settings.logo.url
        if sys_settings.favicon:
            db_config['favicon'] = sys_settings.favicon.url
            db_config['favicon_url'] = sys_settings.favicon.url
        legacy_unconfigured_home_url = (
            not system_is_configured and
            getattr(sys_settings, 'home_url', '') == _LEGACY_HOME_URL
        )
        if (
            sys_settings.home_url
            and not legacy_unconfigured_home_url
            and _should_apply_db_override(sys_settings.home_url, default_config['home_url'])
        ):
            db_config['home_url'] = sys_settings.home_url
        if (
            getattr(sys_settings, 'default_language', None)
            and _should_apply_db_override(sys_settings.default_language, default_config['default_language'])
        ):
            db_config['default_language'] = sys_settings.default_language
        if (
            getattr(sys_settings, 'default_theme', None)
            and _should_apply_db_override(sys_settings.default_theme, default_config['default_theme'])
        ):
            db_config['default_theme'] = sys_settings.default_theme
        if (
            isinstance(getattr(sys_settings, 'allowed_themes', None), list)
            and sys_settings.allowed_themes
            and _should_apply_db_override(sys_settings.allowed_themes, default_config['allowed_themes'])
        ):
            db_config['allowed_themes'] = sys_settings.allowed_themes
        if (
            hasattr(sys_settings, 'allow_user_theme_override')
            and _should_apply_db_override(
                bool(sys_settings.allow_user_theme_override),
                default_config['allow_user_theme_override'],
            )
        ):
            db_config['allow_user_theme_override'] = bool(sys_settings.allow_user_theme_override)
        if (
            hasattr(sys_settings, 'allow_user_language_override')
            and _should_apply_db_override(
                bool(sys_settings.allow_user_language_override),
                default_config['allow_user_language_override'],
            )
        ):
            db_config['allow_user_language_override'] = bool(sys_settings.allow_user_language_override)
        if (
            getattr(sys_settings, 'default_table_density', None)
            and _should_apply_db_override(
                sys_settings.default_table_density,
                default_config['default_table_density'],
            )
        ):
            db_config['default_table_density'] = sys_settings.default_table_density
        if isinstance(sys_settings.languages, dict) and sys_settings.languages:
            db_config['languages'] = sys_settings.languages
        if isinstance(sys_settings.translations_override, dict) and sys_settings.translations_override:
            db_config['translations'] = sys_settings.translations_override
        if isinstance(getattr(sys_settings, 'sidebar_config', None), dict) and sys_settings.sidebar_config:
            db_config['sidebar'] = sys_settings.sidebar_config
        if isinstance(getattr(sys_settings, 'navbar_config', None), dict) and sys_settings.navbar_config:
            db_config['navbar'] = sys_settings.navbar_config
        if isinstance(getattr(sys_settings, 'email_config', None), dict) and sys_settings.email_config:
            db_config['email_config'] = normalize_email_config(sys_settings.email_config)
        if (
            isinstance(getattr(sys_settings, 'titlebar_config', None), dict)
            and sys_settings.titlebar_config
            and (
                system_is_configured
                or sys_settings.titlebar_config != default_titlebar_config()
            )
        ):
            db_config['titlebar'] = sys_settings.titlebar_config
        if isinstance(getattr(sys_settings, 'login_config', None), dict) and sys_settings.login_config:
            db_config['login'] = sys_settings.login_config
        if system_is_configured:
            db_config['is_configured'] = True
        if (
            hasattr(sys_settings, 'email_2fa')
            and _should_apply_db_override(bool(sys_settings.email_2fa), default_config['email_2fa'])
        ):
            db_config['email_2fa'] = bool(sys_settings.email_2fa)
        if (
            hasattr(sys_settings, 'prevent_multiple_active_sessions')
            and _should_apply_db_override(
                bool(sys_settings.prevent_multiple_active_sessions),
                default_config['prevent_multiple_active_sessions'],
            )
        ):
            db_config['prevent_multiple_active_sessions'] = bool(sys_settings.prevent_multiple_active_sessions)
        client_ip_config = normalize_client_ip_config(getattr(sys_settings, 'client_ip_config', {}))
        if _should_apply_db_override(client_ip_config, default_config['client_ip']):
            db_config['client_ip'] = client_ip_config
        if (
            hasattr(sys_settings, 'public_root')
            and _should_apply_db_override(bool(sys_settings.public_root), default_config['public_root'])
        ):
            db_config['public_root'] = bool(sys_settings.public_root)
        if (
            hasattr(sys_settings, 'public_root_split_enabled')
            and _should_apply_db_override(
                bool(sys_settings.public_root_split_enabled),
                default_config['public_root_split_enabled'],
            )
        ):
            db_config['public_root_split_enabled'] = bool(sys_settings.public_root_split_enabled)
        if (
            hasattr(sys_settings, 'public_root_url')
            and _should_apply_db_override(
                str(getattr(sys_settings, 'public_root_url', '') or '').strip(),
                default_config['public_root_url'],
            )
        ):
            db_config['public_root_url'] = str(sys_settings.public_root_url or '').strip()
        if (
            hasattr(sys_settings, 'public_registration_enabled')
            and _should_apply_db_override(
                bool(sys_settings.public_registration_enabled),
                default_config['public_registration_enabled'],
            )
        ):
            db_config['public_registration_enabled'] = bool(sys_settings.public_registration_enabled)
        if (
            hasattr(sys_settings, 'registration_activation_mode')
            and sys_settings.registration_activation_mode in REGISTRATION_ACTIVATION_VALUES
            and _should_apply_db_override(
                sys_settings.registration_activation_mode,
                default_config['registration_activation_mode'],
            )
        ):
            db_config['registration_activation_mode'] = sys_settings.registration_activation_mode
        if (
            hasattr(sys_settings, 'registration_throttle_enabled')
            and _should_apply_db_override(
                bool(sys_settings.registration_throttle_enabled),
                default_config['registration_throttle_enabled'],
            )
        ):
            db_config['registration_throttle_enabled'] = bool(sys_settings.registration_throttle_enabled)

        if (
            isinstance(getattr(sys_settings, 'allowed_fonts', None), (list, tuple, set))
            and _should_apply_db_override(
                normalize_allowed_fonts(sys_settings.allowed_fonts),
                default_config['allowed_fonts'],
            )
        ):
            db_config['allowed_fonts'] = normalize_allowed_fonts(sys_settings.allowed_fonts)

        if isinstance(getattr(sys_settings, 'default_fonts', None), dict) and sys_settings.default_fonts:
            db_config['default_fonts'] = sys_settings.default_fonts

        if _should_apply_db_override(
            bool(getattr(sys_settings, 'allow_user_font_override', True)),
            default_config['allow_user_font_override'],
        ):
            db_config['allow_user_font_override'] = bool(sys_settings.allow_user_font_override)
    except Exception:
        pass

    user_sidebar = user_config.get('sidebar', {})
    if not isinstance(user_sidebar, dict):
        user_sidebar = {}
    user_client_ip = user_config.get('client_ip', user_config.get('client_ip_config', {}))
    if not isinstance(user_client_ip, dict):
        user_client_ip = {}
    db_sidebar = db_config.get('sidebar', {})
    if not isinstance(db_sidebar, dict):
        db_sidebar = {}
    user_navbar = user_config.get('navbar', {})
    if not isinstance(user_navbar, dict):
        user_navbar = {}
    db_navbar = db_config.get('navbar', {})
    if not isinstance(db_navbar, dict):
        db_navbar = {}
    user_titlebar = user_config.get('titlebar', {})
    if not isinstance(user_titlebar, dict):
        user_titlebar = {}
    db_titlebar = db_config.get('titlebar', {})
    if not isinstance(db_titlebar, dict):
        db_titlebar = {}

    final_config = deepcopy(default_config)
    for layer in (user_config, db_config):
        for key, value in layer.items():
            if key in ['system_names', 'languages', 'translations', 'sidebar', 'navbar', 'titlebar']:
                continue
            final_config[key] = value

    final_config['system_names'] = normalize_system_names(
        {
            **normalize_system_names(default_config.get('system_names', {})),
            **normalize_system_names(user_config.get('system_names', {})),
            **normalize_system_names(db_config.get('system_names', {})),
        }
    )

    final_config['languages'] = normalize_language_catalog(
        default_config.get('languages', {}),
        user_config.get('languages', {}),
        db_config.get('languages', {}),
    )
    final_config['translations'] = _merge_translation_layers(
        default_config.get('translations', {}),
        user_config.get('translations', {}),
        db_config.get('translations', {}),
    )

    from ..discovery import sanitize_sidebar_config

    merged_sidebar = deepcopy(default_config['sidebar'])
    for layer in (user_sidebar, db_sidebar):
        for key, value in layer.items():
            if key == 'entries':
                continue
            merged_sidebar[key] = value
    merged_sidebar['entries'] = _dedupe_sidebar_entries(
        list(db_sidebar.get('entries', [])) + list(user_sidebar.get('entries', []))
    )
    merged_sidebar = sanitize_sidebar_config(merged_sidebar, allow_system_items=True)
    final_config['sidebar'] = normalize_sidebar_behavior(merged_sidebar)
    merged_navbar = deepcopy(default_config['navbar'])
    for layer in (user_navbar, db_navbar):
        if isinstance(layer, dict):
            merged_navbar.update(layer)
    final_config['navbar'] = normalize_navbar_config(merged_navbar)
    merged_titlebar = deepcopy(default_config['titlebar'])
    for layer in (user_titlebar, db_titlebar):
        for key, value in layer.items():
            merged_titlebar[key] = value
    final_config['titlebar'] = normalize_titlebar_config(merged_titlebar)
    merged_client_ip = deepcopy(default_config['client_ip'])
    if isinstance(user_client_ip, dict):
        merged_client_ip.update(user_client_ip)
    if isinstance(db_config.get('client_ip', {}), dict):
        merged_client_ip.update(db_config.get('client_ip', {}))
    final_config['client_ip'] = normalize_client_ip_config(merged_client_ip)
    final_config['client_ip_config'] = deepcopy(final_config['client_ip'])
    user_login = user_config.get('login', {})
    if not isinstance(user_login, dict):
        user_login = {}
    merged_login = deepcopy(default_config['login'])
    merged_login.update(user_login)
    merged_login.update(db_config.get('login', {}))
    final_config['login'] = normalize_login_config(merged_login)

    final_config['allowed_themes'] = list(normalize_allowed_themes(final_config.get('allowed_themes')))
    if final_config.get('default_theme') not in set(final_config['allowed_themes']):
        final_config['default_theme'] = final_config['allowed_themes'][0]
    elif not is_valid_theme(final_config.get('default_theme')):
        final_config['default_theme'] = final_config['allowed_themes'][0]
    final_config['allow_user_theme_override'] = bool(final_config.get('allow_user_theme_override', True))
    final_config['allow_user_language_override'] = bool(final_config.get('allow_user_language_override', True))
    final_config['email_config'] = normalize_email_config(final_config.get('email_config', {}))
    if final_config.get('default_table_density') not in TABLE_DENSITY_VALUES:
        final_config['default_table_density'] = default_config['default_table_density']

    final_config['logo_url'] = _normalize_asset_url(
        final_config.get('logo_url') or final_config.get('logo') or default_config['logo']
    )
    final_config['login_logo_url'] = _normalize_asset_url(
        final_config.get('login_logo_url') or final_config.get('login_logo') or final_config['logo_url']
    )
    final_config['favicon_url'] = _normalize_asset_url(
        final_config.get('favicon_url') or final_config.get('favicon') or default_config['favicon']
    )

    final_config['home_url_name'] = None
    final_config['home_url'] = final_config.get('home_url') or default_config['home_url']
    final_config['public_root_split_enabled'] = bool(final_config.get('public_root_split_enabled', False))
    final_config['public_root_url'] = str(final_config.get('public_root_url') or '').strip()
    if final_config.get('default_language') not in final_config['languages']:
        final_config['default_language'] = 'en' if 'en' in final_config['languages'] else next(iter(final_config['languages']), 'en')

    final_config.update(build_config_groups(final_config, final_config.get('default_language')))

    return final_config
