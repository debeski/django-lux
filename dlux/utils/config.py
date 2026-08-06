"""dlux.utils.config — Runtime config defaults/validators and the system-config builder.

Split from the original ``dlux/utils.py`` (kept intact, inert).
"""
import base64
import hashlib
import json
import logging
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
from django.db.utils import OperationalError, ProgrammingError
from django.utils.module_loading import import_string
from ..system.constants import (
    DEFAULT_HOME_URL,
    DEFAULT_NAVBAR_MODE,
    DEFAULT_SIDEBAR_COLLAPSE_MODE,
    DEFAULT_SIDEBAR_DENSITY,
    DEFAULT_FORM_DENSITY,
    DEFAULT_MODAL_SIZE,
    DEFAULT_OPTIONS_STYLE,
    DEFAULT_ROW_ACTIONS_STYLE,
    DEFAULT_TABLE_DENSITY,
    MODAL_SIZE_CLASSES,
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
    TITLEBAR_ACTIONS_ORDER,
    TITLEBAR_ACTIONS_ORDER_VALUES,
    TITLEBAR_USER_HUB_STYLE_DROPDOWN,
    TITLEBAR_USER_HUB_STYLE_VALUES,
)
from ..fonts import DEFAULT_FONT_SLUG, get_available_fonts
from ..system.constants import (
    CLIENT_IP_MODE_AUTO,
    CLIENT_IP_MODE_CLOUDFLARE,
    CLIENT_IP_MODE_CUSTOM,
    CLIENT_IP_MODE_REMOTE_ADDR,
    CLIENT_IP_MODE_VALUES,
    CLIENT_IP_MODE_X_FORWARDED_FOR,
    CLIENT_IP_MODE_X_REAL_IP,
    EMAIL_CONFIG_SECRET_STORAGES,
    EMAIL_CONFIG_TRANSPORTS,
    LOGIN_STYLE_VALUES,
)
from ..system.defaults import (
    default_auth_config as _default_auth_config,
    default_backup_config as _default_backup_config,
    default_client_ip_config as _default_client_ip_config,
    default_email_config as _default_email_config,
    default_extra_config as _default_extra_config,
    default_language_config as _default_language_config,
    default_layout_config as _default_layout_config,
    default_login_config as _default_login_config,
    default_navbar_config as _default_navbar_config,
    default_notification_config as _default_notification_config,
    default_public_root_config as _default_public_root_config,
    default_registration_config as _default_registration_config,
    default_theme_config as _default_theme_config,
    default_titlebar_config as _default_titlebar_config,
    default_typography_config as _default_typography_config,
    default_log_config as _default_log_config,
    default_profile_config as _default_profile_config,
)
from ..system.normalizers import (
    _normalize_client_ip_header_name as _system_normalize_client_ip_header_name,
    normalize_allowed_fonts as _system_normalize_allowed_fonts,
    normalize_auth_config as _system_normalize_auth_config,
    normalize_backup_config as _system_normalize_backup_config,
    normalize_client_ip_config as _system_normalize_client_ip_config,
    normalize_default_fonts as _system_normalize_default_fonts,
    normalize_email_config as _system_normalize_email_config,
    normalize_extra_config as _system_normalize_extra_config,
    normalize_language_config as _system_normalize_language_config,
    normalize_layout_config as _system_normalize_layout_config,
    normalize_log_config as _system_normalize_log_config,
    normalize_login_config as _system_normalize_login_config,
    normalize_navbar_config as _system_normalize_navbar_config,
    normalize_notification_config as _system_normalize_notification_config,
    normalize_profile_config as _system_normalize_profile_config,
    normalize_public_root_config as _system_normalize_public_root_config,
    normalize_registration_config as _system_normalize_registration_config,
    normalize_sidebar_behavior as _system_normalize_sidebar_behavior,
    normalize_theme_config as _system_normalize_theme_config,
    normalize_titlebar_actions_order as _system_normalize_titlebar_actions_order,
    normalize_titlebar_config as _system_normalize_titlebar_config,
    normalize_typography_config as _system_normalize_typography_config,
)
from ..system.registry import (
    build_default_system_config,
    get_config_aliases,
    get_config_normalizers,
    get_flat_config_keys_by_group,
)
from ..themes import is_valid_theme, normalize_allowed_themes
from ..translations import get_current_language_code, get_strings
# try-except for django_filters as it might not be installed (though likely is)
try:
    import django_filters
except ImportError:
    django_filters = None

logger = logging.getLogger('dlux')


def _system_config_db_unavailable_error(exc):
    """Return True for expected startup/test cases where config DB cannot be read yet."""
    if exc.__class__.__name__ == 'DatabaseOperationForbidden':
        return True
    if isinstance(exc, (OperationalError, ProgrammingError)):
        message = str(exc).lower()
        return any(
            fragment in message
            for fragment in (
                'no such table',
                'does not exist',
                'undefined table',
            )
        )
    return False

# ── intra-package imports (shared + feature deps) ──
from .common import DEFAULT_LANGUAGE_CATALOG, _coerce_import_bool, _normalize_asset_url
from .localization import _merge_translation_layers, _normalize_language_code, normalize_language_catalog
from .navigation import _dedupe_sidebar_entries, default_navbar_config, default_sidebar_config, normalize_navbar_config, normalize_sidebar_behavior

_LEGACY_HOME_URL = '/sys/'

# Email Config - Function returns the default outbound email configuration.
def default_email_config():
    return _default_email_config()

# Client IP - Function returns the default client address resolution policy.
def default_client_ip_config():
    return _default_client_ip_config()


def default_notification_config():
    return _default_notification_config()

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
    available = {font['slug'] for font in get_available_fonts()}
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
            'honeypot_enabled': bool(config.get('honeypot_enabled', True)),
            'privacy_policy_url': config.get('privacy_policy_url', '') or '',
            'terms_url': config.get('terms_url', '') or '',
            'privacy_notice_text': config.get('privacy_notice_text', '') or '',
            'registration_require_consent': bool(config.get('registration_require_consent', False)),
            'forgot_password_enabled': bool(config.get('forgot_password_enabled', False)),
            'login_lockout_enabled': bool(config.get('login_lockout_enabled', True)),
            'login_lockout_threshold': int(config.get('login_lockout_threshold', 5) or 5),
            'login_lockout_window_minutes': int(config.get('login_lockout_window_minutes', 15) or 15),
            'login_lockout_duration_minutes': int(config.get('login_lockout_duration_minutes', 15) or 15),
            'enforce_strong_passwords': bool(config.get('enforce_strong_passwords', False)),
            'strong_password_min_length': int(config.get('strong_password_min_length', 12) or 12),
            'purge_session_on_exit': bool(config.get('purge_session_on_exit', False)),
            'inactivity_timeout_enabled': bool(config.get('inactivity_timeout_enabled', False)),
            'inactivity_timeout_minutes': int(config.get('inactivity_timeout_minutes', 10) or 10),
            'public_root_theme': config.get('public_root_theme', '') or '',
            'public_root_title': config.get('public_root_title', '') or '',
            'public_root_meta_description': config.get('public_root_meta_description', '') or '',
            'show_titlebar_on_public': bool(config.get('show_titlebar_on_public', False)),
            'show_sidebar_on_public': bool(config.get('show_sidebar_on_public', False)),
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
            'default_form_density': config.get('default_form_density', DEFAULT_FORM_DENSITY),
            'default_modal_size': config.get('default_modal_size', DEFAULT_MODAL_SIZE),
            'modal_size_class': MODAL_SIZE_CLASSES.get(
                config.get('default_modal_size', DEFAULT_MODAL_SIZE),
                MODAL_SIZE_CLASSES[DEFAULT_MODAL_SIZE],
            ),
            'sticky_table_headers': bool(config.get('sticky_table_headers', True)),
            'resizable_table_columns': bool(config.get('resizable_table_columns', True)),
            'zebra_striping': bool(config.get('zebra_striping', True)),
            'options_style': config.get('options_style', DEFAULT_OPTIONS_STYLE),
            'row_actions_style': config.get('row_actions_style', DEFAULT_ROW_ACTIONS_STYLE),
            'footer_enabled': bool(config.get('footer_enabled', True)),
            'footer_text': config.get('footer_text', '') or '',
            'footer_link_text': config.get('footer_link_text', '') or '',
            'footer_link_url': config.get('footer_link_url', '') or '',
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
    return _default_titlebar_config()

# Titlebar Config - Function returns a sanitized right-side action order.
def normalize_titlebar_actions_order(value):
    if not isinstance(value, (list, tuple)):
        value = []
    normalized = []
    seen = set()
    for item in value:
        action_key = str(item or '').strip()
        if action_key in TITLEBAR_ACTIONS_ORDER_VALUES and action_key not in seen:
            normalized.append(action_key)
            seen.add(action_key)
    for action_key in TITLEBAR_ACTIONS_ORDER:
        if action_key not in seen:
            normalized.append(action_key)
    return normalized

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

    buttons_shape = config.get('buttons_shape', config.get('home_shape'))
    if buttons_shape in TITLEBAR_HOME_SHAPE_VALUES:
        normalized['buttons_shape'] = buttons_shape
        normalized['home_shape'] = buttons_shape

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

    user_hub_style = config.get('user_hub_style')
    if user_hub_style in TITLEBAR_USER_HUB_STYLE_VALUES:
        normalized['user_hub_style'] = user_hub_style

    normalized['actions_order'] = normalize_titlebar_actions_order(config.get('actions_order'))

    return normalized

# Login Config - Function returns default public login/register page settings.
def default_login_config():
    return _default_login_config()


# Auth Config - Default authentication/session-security policy.
def default_auth_config():
    return _default_auth_config()


def default_backup_config():
    return _default_backup_config()


# Auth Config - Function coerces the consolidated auth/session toggles/knobs.
def normalize_auth_config(value):
    # Delegate to the schema-owned normalizer so the key set (including the
    # lockout threshold/window/duration and strong-password minimum length)
    # can never drift between the two entry points.
    return _system_normalize_auth_config(value)


def default_registration_config():
    return _default_registration_config()


def normalize_registration_config(value):
    cfg = value if isinstance(value, dict) else {}
    activation_mode = cfg.get('registration_activation_mode') or REGISTRATION_ACTIVATION_AUTO_LOGIN
    if activation_mode not in REGISTRATION_ACTIVATION_VALUES:
        activation_mode = REGISTRATION_ACTIVATION_AUTO_LOGIN
    return {
        'public_registration_enabled': bool(cfg.get('public_registration_enabled', False)),
        'registration_activation_mode': activation_mode,
        'registration_throttle_enabled': bool(cfg.get('registration_throttle_enabled', True)),
    }


def default_public_root_config():
    return _default_public_root_config()


def normalize_public_root_config(value):
    cfg = value if isinstance(value, dict) else {}
    public_root = bool(cfg.get('public_root', False))
    split_enabled = bool(cfg.get('public_root_split_enabled', False))
    return {
        'public_root': public_root,
        'public_root_split_enabled': split_enabled,
        'public_root_url': str(cfg.get('public_root_url') or '').strip(),
    }


def default_layout_config():
    return _default_layout_config()


def normalize_layout_config(value):
    # Delegate to the schema normalizer (also rebound below at module load) so
    # layout fields like footer_text stay in one place.
    return _system_normalize_layout_config(value)


def default_language_config():
    return _default_language_config()


def normalize_language_config(value):
    cfg = value if isinstance(value, dict) else {}
    translations_override = cfg.get('translations_override', {})
    if not isinstance(translations_override, dict):
        translations_override = {}
    cleaned_translations = {}
    for lang, values in translations_override.items():
        if not isinstance(values, dict):
            continue
        lang_code = _normalize_language_code(lang)
        if not lang_code:
            continue
        lang_values = {
            str(key): str(text or '').strip()
            for key, text in values.items()
            if str(key or '').strip() and str(text or '').strip()
        }
        if lang_values:
            cleaned_translations[lang_code] = lang_values
    return {
        'languages': normalize_language_catalog(cfg.get('languages', {})),
        'translations_override': cleaned_translations,
        'allow_user_language_override': bool(cfg.get('allow_user_language_override', True)),
    }


def default_theme_config():
    return _default_theme_config()


def normalize_theme_config(value):
    cfg = value if isinstance(value, dict) else {}
    return {
        'allowed_themes': list(normalize_allowed_themes(cfg.get('allowed_themes'))),
        'allow_user_theme_override': bool(cfg.get('allow_user_theme_override', True)),
    }


def default_typography_config():
    return _default_typography_config()


def normalize_typography_config(value):
    cfg = value if isinstance(value, dict) else {}
    allowed_fonts = list(normalize_allowed_fonts(cfg.get('allowed_fonts')))
    return {
        'allowed_fonts': allowed_fonts,
        'default_fonts': normalize_default_fonts(cfg.get('default_fonts'), allowed_fonts=allowed_fonts),
        'allow_user_font_override': bool(cfg.get('allow_user_font_override', True)),
    }


def default_extra_config():
    return _default_extra_config()


def normalize_extra_config(value):
    return dict(value) if isinstance(value, dict) else {}


_CONFIG_GROUP_FLAT_KEYS = get_flat_config_keys_by_group()

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


def default_log_config():
    return _default_log_config()


_LOG_ACTION_KEYS = ('create', 'update', 'delete')


def _normalize_log_section(value, defaults):
    """Normalize a user/system log section: enabled, default_actions, retention_days, models."""
    section = value if isinstance(value, dict) else {}
    out = {
        'enabled': bool(section.get('enabled', defaults['enabled'])),
        'default_actions': {},
        'retention_days': 0,
        'models': {},
    }
    base_actions = defaults['default_actions']
    raw_actions = section.get('default_actions') if isinstance(section.get('default_actions'), dict) else {}
    for key in _LOG_ACTION_KEYS:
        out['default_actions'][key] = bool(raw_actions.get(key, base_actions.get(key, True)))

    try:
        out['retention_days'] = max(0, int(section.get('retention_days', 0) or 0))
    except (TypeError, ValueError):
        out['retention_days'] = 0

    raw_models = section.get('models') if isinstance(section.get('models'), dict) else {}
    for raw_key, raw_override in raw_models.items():
        key = str(raw_key or '').strip().lower()
        if not key or '.' not in key or not isinstance(raw_override, dict):
            continue
        entry = {'enabled': bool(raw_override.get('enabled', True))}
        raw_entry_actions = raw_override.get('actions') if isinstance(raw_override.get('actions'), dict) else {}
        actions = {}
        for act_key, act_val in raw_entry_actions.items():
            norm_act = str(act_key or '').strip().lower()
            if norm_act:
                actions[norm_act] = bool(act_val)
        if actions:
            entry['actions'] = actions
        out['models'][key] = entry
    return out


# Logging Config - Function validates user/system/audit activity-logging policy.
def normalize_log_config(value):
    config = value if isinstance(value, dict) else {}
    defaults = default_log_config()
    normalized = {
        'enabled': bool(config.get('enabled', True)),
        'user': _normalize_log_section(config.get('user'), defaults['user']),
        'system': _normalize_log_section(config.get('system'), defaults['system']),
        'audit': {},
    }

    audit_in = config.get('audit') if isinstance(config.get('audit'), dict) else {}
    audit_defaults = defaults['audit']
    audit = {
        # Audit is privileged: always enabled and immutable, never silently disabled.
        'enabled': True,
        'immutable': True,
        'retention_days': 0,
        'events': {},
    }
    try:
        audit['retention_days'] = max(0, int(audit_in.get('retention_days', 0) or 0))
    except (TypeError, ValueError):
        audit['retention_days'] = 0
    raw_events = audit_in.get('events') if isinstance(audit_in.get('events'), dict) else {}
    for event_key, default_on in audit_defaults['events'].items():
        audit['events'][event_key] = bool(raw_events.get(event_key, default_on))
    normalized['audit'] = audit
    return normalized


def default_profile_config():
    return _default_profile_config()


# Profile Config - Function validates the profile-page + onboarding experience settings.
def normalize_profile_config(value):
    from ..system.constants import DEFAULT_SECURITY_NUDGE, SECURITY_NUDGE_VALUES
    config = value if isinstance(value, dict) else {}
    defaults = default_profile_config()
    normalized = {
        'show_completion_widget': bool(config.get('show_completion_widget', defaults['show_completion_widget'])),
        'show_session_device_cards': bool(config.get('show_session_device_cards', defaults['show_session_device_cards'])),
        'show_activity_feed': bool(config.get('show_activity_feed', defaults['show_activity_feed'])),
        'security_nudges': DEFAULT_SECURITY_NUDGE,
        'allow_user_home_url': bool(config.get('allow_user_home_url', defaults['allow_user_home_url'])),
        'onboarding_enabled': bool(config.get('onboarding_enabled', defaults['onboarding_enabled'])),
        'onboarding_options': {},
    }
    nudge = config.get('security_nudges')
    if nudge in SECURITY_NUDGE_VALUES:
        normalized['security_nudges'] = nudge
    raw_options = config.get('onboarding_options') if isinstance(config.get('onboarding_options'), dict) else {}
    for key, default_on in defaults['onboarding_options'].items():
        normalized['onboarding_options'][key] = bool(raw_options.get(key, default_on))
    return normalized


def resolve_user_home_url(user, config=None):
    """Return the user's per-user landing page (``Profile.preferences['user_home_url']``)
    when ``profile_config.allow_user_home_url`` is enabled, else ''. Safe/never raises."""
    try:
        if config is None:
            config = get_system_config()
        profile_config = config.get('profile_config') or {}
        if not profile_config.get('allow_user_home_url'):
            return ''
        profile = getattr(user, 'profile', None)
        prefs = getattr(profile, 'preferences', None) if profile is not None else None
        if isinstance(prefs, dict):
            return str(prefs.get('user_home_url') or '').strip()
    except Exception:
        pass
    return ''


_CONFIG_GROUP_NORMALIZERS = get_config_normalizers()


def expand_system_config_groups(config):
    """Return config with nested group aliases normalized and flattened.

    Existing flat keys remain authoritative when both flat and nested keys are
    present. This keeps the public settings contract stable while allowing the
    storage model to use grouped JSON fields.
    """
    if not isinstance(config, dict):
        return {}
    expanded = deepcopy(config)
    alias_map = get_config_aliases()
    for alias, canonical in alias_map.items():
        if canonical not in expanded and isinstance(expanded.get(alias), dict):
            expanded[canonical] = deepcopy(expanded[alias])
    # Legacy migration: titlebar_config.hide_on_public_unauthenticated_index now
    # maps to public_root_config.show_titlebar_on_public (inverted). Only seed it
    # when the new key is not already provided, so explicit values always win.
    _titlebar_group = expanded.get('titlebar_config')
    if isinstance(_titlebar_group, dict) and 'hide_on_public_unauthenticated_index' in _titlebar_group:
        _public_root_group = expanded.get('public_root_config')
        _has_show_titlebar = (
            (isinstance(_public_root_group, dict) and 'show_titlebar_on_public' in _public_root_group)
            or 'show_titlebar_on_public' in expanded
        )
        if not _has_show_titlebar:
            expanded['show_titlebar_on_public'] = not bool(
                _titlebar_group.get('hide_on_public_unauthenticated_index', False)
            )
    for group_name, flat_keys in _CONFIG_GROUP_FLAT_KEYS.items():
        if group_name not in expanded and not any(flat_key in expanded for flat_key in flat_keys):
            continue
        group = deepcopy(expanded.get(group_name, {})) if isinstance(expanded.get(group_name), dict) else {}
        for flat_key in flat_keys:
            if flat_key in expanded:
                group[flat_key] = expanded[flat_key]
        normalized = _CONFIG_GROUP_NORMALIZERS[group_name](group)
        expanded[group_name] = normalized
        for flat_key in flat_keys:
            if flat_key not in expanded and flat_key in normalized:
                expanded[flat_key] = normalized[flat_key]
    for group_name in (
        'client_ip_config',
        'email_config',
        'notification_config',
        'login_config',
        'titlebar_config',
        'navbar_config',
        'sidebar_config',
        'log_config',
        'profile_config',
        'backup_config',
        'extra_config',
    ):
        if group_name in expanded:
            expanded[group_name] = _CONFIG_GROUP_NORMALIZERS[group_name](expanded[group_name])
    canonical_aliases = {
        'client_ip_config': 'client_ip',
        'notification_config': 'notifications',
        'login_config': 'login',
        'titlebar_config': 'titlebar',
        'navbar_config': 'navbar',
        'sidebar_config': 'sidebar',
        'log_config': 'log',
        'profile_config': 'profile',
        'backup_config': 'backup',
    }
    for canonical, alias in canonical_aliases.items():
        if alias not in expanded and canonical in expanded:
            expanded[alias] = deepcopy(expanded[canonical])
    if 'translations' not in expanded and 'translations_override' in expanded:
        expanded['translations'] = deepcopy(expanded['translations_override'])
    return expanded

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
        allowed = {font['slug'] for font in get_available_fonts()}
    normalized = {}
    for raw_code, raw_font in value.items():
        code = _normalize_language_code(raw_code)
        font = str(raw_font or '').strip()
        if code and font in allowed:
            normalized[code] = font
    return normalized


# Canonical settings normalizers live in ``dlux.system.normalizers``. Keep the
# public names in this module as aliases for existing callers.
_normalize_client_ip_header_name = _system_normalize_client_ip_header_name
normalize_allowed_fonts = _system_normalize_allowed_fonts
normalize_auth_config = _system_normalize_auth_config
normalize_backup_config = _system_normalize_backup_config
normalize_client_ip_config = _system_normalize_client_ip_config
normalize_default_fonts = _system_normalize_default_fonts
normalize_email_config = _system_normalize_email_config
normalize_extra_config = _system_normalize_extra_config
normalize_language_config = _system_normalize_language_config
normalize_layout_config = _system_normalize_layout_config
normalize_log_config = _system_normalize_log_config
normalize_login_config = _system_normalize_login_config
normalize_navbar_config = _system_normalize_navbar_config
normalize_notification_config = _system_normalize_notification_config
normalize_profile_config = _system_normalize_profile_config
normalize_public_root_config = _system_normalize_public_root_config
normalize_registration_config = _system_normalize_registration_config
normalize_sidebar_behavior = _system_normalize_sidebar_behavior
normalize_theme_config = _system_normalize_theme_config
normalize_titlebar_actions_order = _system_normalize_titlebar_actions_order
normalize_titlebar_config = _system_normalize_titlebar_config
normalize_typography_config = _system_normalize_typography_config


def _stored_asset_url(field_file):
    if not field_file:
        return ''
    name = str(getattr(field_file, 'name', '') or '').strip()
    if not name:
        return ''
    storage = getattr(field_file, 'storage', None)
    if storage is not None:
        try:
            if not storage.exists(name):
                return ''
        except Exception:
            pass
    try:
        return str(field_file.url or '').strip()
    except Exception:
        return ''


# System Config - Function merges defaults, settings, and DB-backed runtime config.
def get_system_config():
    """
    Returns the deeply merged system configuration.
    1. Default config
    2. settings.DLUX_CONFIG (host project codebase)
    3. SystemSettings Singleton (database UI overrides)
    """
    default_config = build_default_system_config()

    # Project settings
    user_config = getattr(settings, 'DLUX_CONFIG', {})
    if not isinstance(user_config, dict):
        user_config = {}
    default_config = expand_system_config_groups(default_config)
    user_config = expand_system_config_groups(user_config)
    
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
        logo_url = _stored_asset_url(sys_settings.logo)
        if logo_url:
            db_config['logo'] = logo_url
            db_config['logo_url'] = logo_url
            db_config['login_logo_url'] = logo_url
        favicon_url = _stored_asset_url(sys_settings.favicon)
        if favicon_url:
            db_config['favicon'] = favicon_url
            db_config['favicon_url'] = favicon_url
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
        # footer_enabled is a real toggle (False is meaningful), but it must use
        # the same gate as the other layout keys: applying it unconditionally
        # would materialize a full layout_config group (via expand) that clobbers
        # a settings-level default_table_density override on unconfigured systems.
        _footer_enabled = bool(getattr(sys_settings, 'footer_enabled', True))
        if _should_apply_db_override(_footer_enabled, bool(default_config.get('footer_enabled', True))):
            db_config['footer_enabled'] = _footer_enabled
        if (
            getattr(sys_settings, 'default_form_density', None)
            and _should_apply_db_override(
                sys_settings.default_form_density,
                default_config['default_form_density'],
            )
        ):
            db_config['default_form_density'] = sys_settings.default_form_density
        if (
            getattr(sys_settings, 'default_modal_size', None)
            and _should_apply_db_override(
                sys_settings.default_modal_size,
                default_config['default_modal_size'],
            )
        ):
            db_config['default_modal_size'] = sys_settings.default_modal_size
        # sticky_table_headers / resizable_table_columns / zebra_striping default
        # True (False is meaningful);
        # gate like footer_enabled so toggling them does not clobber a settings-level
        # layout override on an unconfigured system.
        _sticky_headers = bool(getattr(sys_settings, 'sticky_table_headers', True))
        if _should_apply_db_override(_sticky_headers, bool(default_config.get('sticky_table_headers', True))):
            db_config['sticky_table_headers'] = _sticky_headers
        _resizable_columns = bool(getattr(sys_settings, 'resizable_table_columns', True))
        if _should_apply_db_override(_resizable_columns, bool(default_config.get('resizable_table_columns', True))):
            db_config['resizable_table_columns'] = _resizable_columns
        _zebra_striping = bool(getattr(sys_settings, 'zebra_striping', True))
        if _should_apply_db_override(_zebra_striping, bool(default_config.get('zebra_striping', True))):
            db_config['zebra_striping'] = _zebra_striping
        # options_style is JSON-only (no legacy column, inline-safe): read it from
        # the stored layout_config dict rather than a model attribute.
        _layout_json = getattr(sys_settings, 'layout_config', None)
        if isinstance(_layout_json, dict):
            _options_style = _layout_json.get('options_style')
            if _options_style and _should_apply_db_override(
                _options_style, default_config.get('options_style', DEFAULT_OPTIONS_STYLE)
            ):
                db_config['options_style'] = _options_style
            _row_actions_style = _layout_json.get('row_actions_style')
            if _row_actions_style and _should_apply_db_override(
                _row_actions_style, default_config.get('row_actions_style', DEFAULT_ROW_ACTIONS_STYLE)
            ):
                db_config['row_actions_style'] = _row_actions_style
            # JSON-only opt-in flags (default False): surface them as flat keys so
            # audit_fields_visible()/soft_deleted_visible() can read them.
            for _flag in ('show_audit_fields', 'show_soft_deleted'):
                if bool(_layout_json.get(_flag)):
                    db_config[_flag] = True
        if str(getattr(sys_settings, 'footer_text', '') or '').strip():
            db_config['footer_text'] = sys_settings.footer_text
        if str(getattr(sys_settings, 'footer_link_text', '') or '').strip():
            db_config['footer_link_text'] = sys_settings.footer_link_text
        if str(getattr(sys_settings, 'footer_link_url', '') or '').strip():
            db_config['footer_link_url'] = sys_settings.footer_link_url
        if isinstance(sys_settings.languages, dict) and sys_settings.languages:
            db_config['languages'] = sys_settings.languages
        if isinstance(sys_settings.translations_override, dict) and sys_settings.translations_override:
            db_config['translations_override'] = sys_settings.translations_override
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
        if hasattr(sys_settings, 'notification_config'):
            notification_config = normalize_notification_config(getattr(sys_settings, 'notification_config', None) or {})
            if _should_apply_db_override(notification_config, default_config['notifications']):
                db_config['notifications'] = notification_config
        if hasattr(sys_settings, 'log_config'):
            log_config = normalize_log_config(getattr(sys_settings, 'log_config', None) or {})
            if _should_apply_db_override(log_config, default_config['log_config']):
                db_config['log_config'] = log_config
                db_config['log'] = log_config
        if hasattr(sys_settings, 'profile_config'):
            profile_config = normalize_profile_config(getattr(sys_settings, 'profile_config', None) or {})
            if _should_apply_db_override(profile_config, default_config['profile_config']):
                db_config['profile_config'] = profile_config
                db_config['profile'] = profile_config
        if hasattr(sys_settings, 'backup_config'):
            backup_config = normalize_backup_config(getattr(sys_settings, 'backup_config', None) or {})
            if _should_apply_db_override(backup_config, default_config['backup_config']):
                db_config['backup_config'] = backup_config
                db_config['backup'] = backup_config
        if system_is_configured:
            db_config['is_configured'] = True
        # Authentication/session toggles live in the consolidated auth_config JSON
        # field. We flatten them back to top-level config keys so every existing
        # read site (`config.get('email_2fa')`, etc.) keeps working unchanged.
        if hasattr(sys_settings, 'auth_config'):
            auth_config = normalize_auth_config(getattr(sys_settings, 'auth_config', None) or {})
            if _should_apply_db_override(auth_config, default_config['auth_config']):
                db_config['auth_config'] = auth_config
            for auth_key in (
                'email_2fa',
                'forgot_password_enabled',
                'prevent_multiple_active_sessions',
                'login_lockout_enabled',
                'login_lockout_threshold',
                'login_lockout_window_minutes',
                'login_lockout_duration_minutes',
                'enforce_strong_passwords',
                'strong_password_min_length',
                'purge_session_on_exit',
                'inactivity_timeout_enabled',
                'inactivity_timeout_minutes',
            ):
                # auth_config is already normalized (bools are bools, the lockout /
                # min-length knobs are clamped ints) — don't bool()-coerce here.
                if _should_apply_db_override(auth_config.get(auth_key), default_config[auth_key]):
                    db_config[auth_key] = auth_config.get(auth_key)
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
        if str(getattr(sys_settings, 'public_root_theme', '') or '').strip():
            db_config['public_root_theme'] = str(sys_settings.public_root_theme or '').strip()
        if str(getattr(sys_settings, 'public_root_title', '') or '').strip():
            db_config['public_root_title'] = str(sys_settings.public_root_title or '').strip()
        if str(getattr(sys_settings, 'public_root_meta_description', '') or '').strip():
            db_config['public_root_meta_description'] = str(
                sys_settings.public_root_meta_description or ''
            ).strip()
        # show_titlebar_on_public supersedes the legacy titlebar-owned hide flag.
        # When the new key is unset on an upgraded install, derive it (inverted)
        # from titlebar_config.hide_on_public_unauthenticated_index.
        _pub_cfg = getattr(sys_settings, 'public_root_config', None)
        _has_show_titlebar = isinstance(_pub_cfg, dict) and 'show_titlebar_on_public' in _pub_cfg
        if _has_show_titlebar:
            _show_titlebar = bool(getattr(sys_settings, 'show_titlebar_on_public', False))
        else:
            _tb_cfg = getattr(sys_settings, 'titlebar_config', None)
            _show_titlebar = not bool(
                (_tb_cfg or {}).get('hide_on_public_unauthenticated_index', False)
            ) if isinstance(_tb_cfg, dict) else False
        if _should_apply_db_override(_show_titlebar, default_config['show_titlebar_on_public']):
            db_config['show_titlebar_on_public'] = _show_titlebar
        if (
            hasattr(sys_settings, 'show_sidebar_on_public')
            and _should_apply_db_override(
                bool(sys_settings.show_sidebar_on_public),
                default_config['show_sidebar_on_public'],
            )
        ):
            db_config['show_sidebar_on_public'] = bool(sys_settings.show_sidebar_on_public)
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

        for _reg_url_key in ('privacy_policy_url', 'terms_url', 'privacy_notice_text'):
            if hasattr(sys_settings, _reg_url_key):
                _reg_url_val = str(getattr(sys_settings, _reg_url_key) or '').strip()
                if _should_apply_db_override(_reg_url_val, default_config[_reg_url_key]):
                    db_config[_reg_url_key] = _reg_url_val
        if hasattr(sys_settings, 'registration_require_consent') and _should_apply_db_override(
            bool(sys_settings.registration_require_consent),
            default_config['registration_require_consent'],
        ):
            db_config['registration_require_consent'] = bool(sys_settings.registration_require_consent)

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

        allow_user_font_override = bool(getattr(sys_settings, 'allow_user_font_override', True))
        if _should_apply_db_override(
            allow_user_font_override,
            default_config['allow_user_font_override'],
        ):
            db_config['allow_user_font_override'] = allow_user_font_override
        if isinstance(getattr(sys_settings, 'extra_config', None), dict) and sys_settings.extra_config:
            db_config['extra_config'] = normalize_extra_config(sys_settings.extra_config)
    except Exception as exc:
        if _system_config_db_unavailable_error(exc):
            logger.debug(
                "SystemSettings are unavailable while building system config; using defaults."
            )
        else:
            logger.warning(
                "Failed to read SystemSettings while building system config; using defaults for the failed fields.",
                exc_info=True,
            )

    # Safety net: a failure while *reading* config above (e.g. an unreadable cache
    # entry, or any error in the merge block) must never masquerade as "system not
    # configured" — that bounces authenticated users into the setup wizard. If the
    # persisted row says the system is configured, honor it via a direct, cache-free
    # DB check regardless of whatever went wrong above.
    if not db_config.get('is_configured'):
        try:
            from dlux.models import SystemSettings
            if SystemSettings.objects.filter(pk=1, is_configured=True).exists():
                db_config['is_configured'] = True
        except Exception as exc:
            if _system_config_db_unavailable_error(exc):
                logger.debug(
                    "SystemSettings are unavailable during fallback is_configured check."
                )
            else:
                logger.warning("Fallback is_configured DB check failed.", exc_info=True)

    db_config = expand_system_config_groups(db_config)

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
    user_notifications = user_config.get('notifications', user_config.get('notification_config', {}))
    if not isinstance(user_notifications, dict):
        user_notifications = {}
    db_notifications = db_config.get('notifications', db_config.get('notification_config', {}))
    if not isinstance(db_notifications, dict):
        db_notifications = {}

    final_config = deepcopy(default_config)
    for layer in (user_config, db_config):
        for key, value in layer.items():
            if key in ['system_names', 'languages', 'translations', 'sidebar', 'navbar', 'titlebar', 'notifications', 'notification_config']:
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

    from ..discovery import sanitize_navbar_config, sanitize_sidebar_config

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
    final_config['navbar'] = sanitize_navbar_config(merged_navbar)
    merged_titlebar = deepcopy(default_config['titlebar'])
    for layer in (user_titlebar, db_titlebar):
        for key, value in layer.items():
            merged_titlebar[key] = value
    final_config['titlebar'] = normalize_titlebar_config(merged_titlebar)
    merged_notifications = deepcopy(default_config['notifications'])
    for layer in (user_notifications, db_notifications):
        if not isinstance(layer, dict):
            continue
        for key, value in layer.items():
            if isinstance(value, dict) and isinstance(merged_notifications.get(key), dict):
                merged_notifications[key].update(value)
            else:
                merged_notifications[key] = value
    final_config['notifications'] = normalize_notification_config(merged_notifications)
    final_config['notification_config'] = deepcopy(final_config['notifications'])
    final_config['backup_config'] = normalize_backup_config(final_config.get('backup_config', {}))
    final_config['backup'] = deepcopy(final_config['backup_config'])
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

    auth_seed = (
        dict(final_config.get('auth_config'))
        if isinstance(final_config.get('auth_config'), dict)
        else {}
    )
    for auth_key in (
        'email_2fa',
        'forgot_password_enabled',
        'prevent_multiple_active_sessions',
        'login_lockout_enabled',
        'login_lockout_threshold',
        'login_lockout_window_minutes',
        'login_lockout_duration_minutes',
        'enforce_strong_passwords',
        'strong_password_min_length',
        'purge_session_on_exit',
        'inactivity_timeout_enabled',
        'inactivity_timeout_minutes',
    ):
        if auth_key in final_config:
            auth_seed[auth_key] = final_config[auth_key]
    final_config['auth_config'] = normalize_auth_config(auth_seed)
    for auth_key, auth_value in final_config['auth_config'].items():
        final_config[auth_key] = auth_value
    final_config['registration_config'] = normalize_registration_config(final_config)
    final_config.update(final_config['registration_config'])
    final_config['public_root_config'] = normalize_public_root_config(final_config)
    final_config.update(final_config['public_root_config'])
    final_config['layout_config'] = normalize_layout_config(final_config)
    final_config.update(final_config['layout_config'])
    final_config['theme_config'] = normalize_theme_config(final_config)
    final_config.update(final_config['theme_config'])
    final_config['typography_config'] = normalize_typography_config(final_config)
    final_config.update(final_config['typography_config'])
    final_config['language_config'] = normalize_language_config({
        'languages': final_config.get('languages', {}),
        'translations_override': _merge_translation_layers(
            user_config.get('translations_override', {}),
            db_config.get('translations_override', {}),
        ),
        'allow_user_language_override': final_config.get('allow_user_language_override', True),
    })
    final_config['extra_config'] = normalize_extra_config(final_config.get('extra_config', {}))

    final_config.update(build_config_groups(final_config, final_config.get('default_language')))

    return final_config


def get_app_system_config(namespace, default=None):
    """Read one app-owned system-config namespace.

    Returns the opaque value stored at ``SystemSettings.extra_config['app'][namespace]``
    (see the superuser-only write endpoint), or ``default`` when unset. This is the
    global, project-wide counterpart of the per-user ``app`` preferences namespace.
    """
    from ..system.constants import SYSTEM_APP_CONFIG_NAMESPACE
    extra = get_system_config().get('extra_config') or {}
    app_bag = extra.get(SYSTEM_APP_CONFIG_NAMESPACE)
    if not isinstance(app_bag, dict) or namespace not in app_bag:
        return default
    return app_bag[namespace]
