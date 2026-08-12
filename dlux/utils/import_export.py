"""dlux.utils.import_export — System-settings export/import payload handling.

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
from django.db import models as dj_models, transaction
from django.db.models import ManyToManyRel, Q
from django.db.models.fields.files import FieldFile
from django.db.models.fields.related import ManyToManyField
from django.forms import modelform_factory
from django.http import JsonResponse
from django.core.mail import EmailMessage, get_connection, send_mail
from django.core.exceptions import FieldDoesNotExist
from django.utils.module_loading import import_string
from ..system.constants import (
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
from ..system.registry import get_exportable_settings, get_import_aliases
# try-except for django_filters as it might not be installed (though likely is)
try:
    import django_filters
except ImportError:
    django_filters = None

# ── intra-package imports (shared + feature deps) ──
from .common import _coerce_import_bool
from .config import (
    expand_system_config_groups,
    normalize_allowed_fonts,
    normalize_auth_config,
    normalize_backup_config,
    normalize_client_ip_config,
    normalize_default_fonts,
    normalize_email_config,
    normalize_extra_config,
    normalize_layout_config,
    normalize_log_config,
    normalize_login_config,
    normalize_profile_config,
    normalize_notification_config,
    normalize_system_names,
    normalize_titlebar_config,
)
from .localization import _normalize_language_code, normalize_language_catalog

SYSTEM_SETTINGS_EXPORT_FORMAT = 'django-lux.system-settings'

SYSTEM_SETTINGS_EXPORT_VERSION = 1

SYSTEM_SETTINGS_EXPORT_FIELDS = get_exportable_settings()

SYSTEM_SETTINGS_CONFIG_BOOTSTRAP_APPLIED = 'applied'
SYSTEM_SETTINGS_CONFIG_BOOTSTRAP_CONFIGURED = 'configured'
SYSTEM_SETTINGS_CONFIG_BOOTSTRAP_MISSING = 'missing'

# System Import Export - Helper extracts portable names from file fields.
def _field_file_name(value):
    if isinstance(value, FieldFile):
        return value.name or ''
    return str(value or '')

# System Import Export - Function serializes DB-backed settings for transport.
def export_system_settings_payload(instance=None):
    """Return a portable JSON payload for DB-backed setup settings."""
    from ..discovery import sanitize_navbar_config, sanitize_sidebar_config

    if instance is None:
        SystemSettings = apps.get_model('dlux', 'SystemSettings')
        instance = SystemSettings.load()

    from dlux import __version__

    data = {}
    auth_export = normalize_auth_config(getattr(instance, 'auth_config', None) or {})
    layout_export = normalize_layout_config(getattr(instance, 'layout_config', None) or {})
    asset_fields = {
        'logo': 'logo_asset',
        'favicon': 'favicon_asset',
        'login_logo': 'login_logo_asset',
        'login_background': 'login_background_asset',
    }
    for field_name in SYSTEM_SETTINGS_EXPORT_FIELDS:
        if field_name in (
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
            # These toggles/knobs are stored in the consolidated auth_config JSON
            # field; keep exporting them as flat keys for backward-compatible
            # import files.
            value = auth_export.get(field_name)
        elif field_name == 'options_style':
            # JSON-only layout key (no legacy column): export from layout_config.
            value = layout_export.get('options_style')
        elif field_name == 'row_actions_style':
            # JSON-only layout key: export from layout_config.
            value = layout_export.get('row_actions_style')
        elif field_name in asset_fields:
            asset = getattr(instance, asset_fields[field_name], None)
            value = getattr(asset, 'file', None)
            if not value and field_name in {'logo', 'favicon'}:
                value = getattr(instance, field_name, None)
        else:
            value = getattr(instance, field_name, None)
        if field_name in asset_fields:
            data[field_name] = _field_file_name(value)
        elif field_name == 'languages':
            data[field_name] = normalize_language_catalog(value)
        elif field_name == 'system_names':
            data[field_name] = normalize_system_names(value)
        elif field_name == 'sidebar_config':
            data[field_name] = sanitize_sidebar_config(value, allow_system_items=True)
        elif field_name == 'navbar_config':
            data[field_name] = sanitize_navbar_config(value)
        elif field_name == 'log_config':
            data[field_name] = normalize_log_config(value)
        elif field_name == 'profile_config':
            data[field_name] = normalize_profile_config(value)
        elif field_name == 'backup_config':
            data[field_name] = normalize_backup_config(value)
        elif field_name == 'email_config':
            data[field_name] = normalize_email_config(value, redact_secret=True)
        elif field_name == 'client_ip_config':
            data[field_name] = normalize_client_ip_config(value)
        elif field_name == 'titlebar_config':
            data[field_name] = normalize_titlebar_config(value)
        elif field_name == 'notification_config':
            data[field_name] = normalize_notification_config(value)
        elif field_name == 'login_config':
            data[field_name] = normalize_login_config(value)
        elif field_name == 'allowed_themes':
            data[field_name] = list(normalize_allowed_themes(value))
        elif field_name == 'allowed_fonts':
            data[field_name] = list(normalize_allowed_fonts(value))
        elif field_name == 'default_fonts':
            data[field_name] = normalize_default_fonts(value, allowed_fonts=getattr(instance, 'allowed_fonts', None))
        else:
            data[field_name] = deepcopy(value)

    return {
        'format': SYSTEM_SETTINGS_EXPORT_FORMAT,
        'version': SYSTEM_SETTINGS_EXPORT_VERSION,
        'dlux_version': __version__,
        'settings': data,
    }

# System Import Export - Function validates exported or raw settings payloads.
def normalize_system_settings_import_payload(payload):
    """Validate and normalize an exported setup payload or a direct settings dict."""
    from ..discovery import sanitize_navbar_config, sanitize_sidebar_config

    if not isinstance(payload, dict):
        raise ValueError("Setup import must be a JSON object.")

    raw_settings = payload.get('settings') if payload.get('format') == SYSTEM_SETTINGS_EXPORT_FORMAT else payload
    if not isinstance(raw_settings, dict):
        raise ValueError("Setup import is missing a valid settings object.")
    raw_settings = expand_system_config_groups(raw_settings)

    normalized = {}
    for field_name in SYSTEM_SETTINGS_EXPORT_FIELDS:
        if field_name in raw_settings:
            normalized[field_name] = deepcopy(raw_settings[field_name])
    for source_name, target_name in get_import_aliases().items():
        if target_name not in normalized and source_name in raw_settings:
            normalized[target_name] = deepcopy(raw_settings[source_name])

    if 'system_names' in normalized:
        normalized['system_names'] = normalize_system_names(normalized['system_names'])
    if 'languages' in normalized:
        normalized['languages'] = normalize_language_catalog(normalized['languages'])
    if 'translations_override' in normalized and not isinstance(normalized['translations_override'], dict):
        normalized['translations_override'] = {}
    if 'sidebar_config' in normalized:
        normalized['sidebar_config'] = sanitize_sidebar_config(
            normalized['sidebar_config'],
            allow_system_items=True,
        )
    if 'navbar_config' in normalized:
        normalized['navbar_config'] = sanitize_navbar_config(normalized['navbar_config'])
    if 'log_config' in normalized:
        normalized['log_config'] = normalize_log_config(normalized['log_config'])
    if 'profile_config' in normalized:
        normalized['profile_config'] = normalize_profile_config(normalized['profile_config'])
    if 'backup_config' in normalized:
        normalized['backup_config'] = normalize_backup_config(normalized['backup_config'])
    if 'email_config' in normalized:
        normalized['email_config'] = normalize_email_config(normalized['email_config'], redact_secret=True)
    if 'client_ip_config' in normalized:
        normalized['client_ip_config'] = normalize_client_ip_config(normalized['client_ip_config'])
    if 'titlebar_config' in normalized:
        normalized['titlebar_config'] = normalize_titlebar_config(normalized['titlebar_config'])
    if 'notification_config' in normalized:
        normalized['notification_config'] = normalize_notification_config(normalized['notification_config'])
    if 'login_config' in normalized:
        normalized['login_config'] = normalize_login_config(normalized['login_config'])
    if 'extra_config' in normalized:
        normalized['extra_config'] = normalize_extra_config(normalized['extra_config'])
    if 'allowed_themes' in normalized:
        normalized['allowed_themes'] = list(normalize_allowed_themes(normalized['allowed_themes']))
    if 'allowed_fonts' in normalized:
        normalized['allowed_fonts'] = list(normalize_allowed_fonts(normalized['allowed_fonts']))
    if 'default_fonts' in normalized:
        normalized['default_fonts'] = normalize_default_fonts(
            normalized['default_fonts'],
            allowed_fonts=normalized.get('allowed_fonts'),
        )
    if 'default_theme' in normalized and not is_valid_theme(normalized['default_theme']):
        normalized.pop('default_theme', None)
    if 'default_table_density' in normalized and normalized['default_table_density'] not in TABLE_DENSITY_VALUES:
        normalized.pop('default_table_density', None)
    if 'default_language' in normalized:
        normalized['default_language'] = _normalize_language_code(normalized['default_language']) or 'en'
    if 'home_url' in normalized:
        normalized['home_url'] = str(normalized['home_url'] or '').strip()
    if 'public_root_url' in normalized:
        normalized['public_root_url'] = str(normalized['public_root_url'] or '').strip()
    if (
        'registration_activation_mode' in normalized
        and normalized['registration_activation_mode'] not in REGISTRATION_ACTIVATION_VALUES
    ):
        normalized.pop('registration_activation_mode', None)
    for bool_field in (
        'allow_user_theme_override',
        'allow_user_font_override',
        'allow_user_language_override',
        'email_2fa',
        'forgot_password_enabled',
        'prevent_multiple_active_sessions',
        'login_lockout_enabled',
        'enforce_strong_passwords',
        'public_root',
        'public_root_split_enabled',
        'show_titlebar_on_public',
        'show_sidebar_on_public',
        'public_registration_enabled',
        'registration_throttle_enabled',
        'honeypot_enabled',
        'registration_require_consent',
        'sticky_table_headers',
        'resizable_table_columns',
        'zebra_striping',
    ):
        if bool_field in normalized:
            normalized[bool_field] = _coerce_import_bool(normalized[bool_field])
    return normalized

# System Import Export - Function applies normalized settings payloads to SystemSettings.
def apply_system_settings_import(
    instance,
    payload,
    *,
    mark_configured=True,
    commit=True,
    preserve_email_secret=False,
):
    """Apply a normalized System Settings import payload to a SystemSettings instance."""
    raw_settings = payload.get('settings') if isinstance(payload, dict) and payload.get('format') == SYSTEM_SETTINGS_EXPORT_FORMAT else payload
    raw_email_config = raw_settings.get('email_config') if isinstance(raw_settings, dict) else None
    normalized = normalize_system_settings_import_payload(payload)
    if not instance:
        raise ValueError("A SystemSettings instance is required.")

    for field_name, value in normalized.items():
        if field_name in {'logo', 'favicon', 'login_logo', 'login_background'}:
            if value:
                from ..assets import adopt_storage_asset
                asset = adopt_storage_asset(str(value))
                asset_field = {
                    'logo': 'logo_asset',
                    'favicon': 'favicon_asset',
                    'login_logo': 'login_logo_asset',
                    'login_background': 'login_background_asset',
                }[field_name]
                if asset:
                    setattr(instance, asset_field, asset)
                    if field_name in {'logo', 'favicon'}:
                        setattr(instance, field_name, None)
                elif field_name in {'logo', 'favicon'}:
                    setattr(instance, field_name, str(value))
        elif field_name == 'email_config':
            source = raw_email_config if preserve_email_secret and isinstance(raw_email_config, dict) else value
            email_config = normalize_email_config(source)
            if email_config.get('secret_storage') == 'encrypted_db' and not email_config.get('encrypted_password'):
                email_config['password_configured'] = False
            instance.email_config = email_config
        elif field_name == 'allowed_fonts':
            instance.allowed_fonts = list(normalize_allowed_fonts(value))
        elif field_name == 'default_fonts':
            instance.default_fonts = normalize_default_fonts(
                value,
                allowed_fonts=normalized.get('allowed_fonts', getattr(instance, 'allowed_fonts', None)),
            )
        elif field_name in (
            'email_2fa',
            'forgot_password_enabled',
            'prevent_multiple_active_sessions',
            'login_lockout_enabled',
            'enforce_strong_passwords',
            'purge_session_on_exit',
            'inactivity_timeout_enabled',
        ):
            # Flat auth toggles route into the consolidated auth_config JSON field.
            auth = dict(getattr(instance, 'auth_config', None) or {})
            auth[field_name] = _coerce_import_bool(value)
            instance.auth_config = normalize_auth_config(auth)
        elif field_name in (
            'login_lockout_threshold',
            'login_lockout_window_minutes',
            'login_lockout_duration_minutes',
            'strong_password_min_length',
            'inactivity_timeout_minutes',
        ):
            # Flat auth int knobs also route into auth_config; the normalizer
            # clamps out-of-range values back to the shipped defaults.
            auth = dict(getattr(instance, 'auth_config', None) or {})
            auth[field_name] = value
            instance.auth_config = normalize_auth_config(auth)
        elif field_name == 'options_style':
            # JSON-only layout key (no legacy column): route into layout_config.
            layout = dict(getattr(instance, 'layout_config', None) or {})
            layout['options_style'] = value
            instance.layout_config = normalize_layout_config(layout)
        elif field_name == 'row_actions_style':
            # JSON-only layout key: route into layout_config (normalizer validates).
            layout = dict(getattr(instance, 'layout_config', None) or {})
            layout['row_actions_style'] = value
            instance.layout_config = normalize_layout_config(layout)
        elif field_name == 'auth_config' and isinstance(value, dict):
            instance.auth_config = normalize_auth_config(value)
        elif field_name == 'notification_config' and isinstance(value, dict):
            instance.notification_config = normalize_notification_config(value)
        elif hasattr(instance, field_name):
            setattr(instance, field_name, value)

    if mark_configured:
        instance.is_configured = True
    if commit:
        instance.save()
    return instance

# System Import Export - Function resolves the first-launch config.json path.
def resolve_system_settings_config_json_path(path=None):
    if path is None:
        base_dir = getattr(settings, 'BASE_DIR', None)
        if not base_dir:
            return None
        return Path(base_dir) / 'config.json'
    return Path(path)


# System Import Export - Function loads first-launch config.json settings.
def load_system_settings_config_json(path=None):
    """Load and normalize BASE_DIR/config.json for first-launch setup bootstrapping."""
    config_path = resolve_system_settings_config_json_path(path)
    if config_path is None:
        return None
    if not config_path.exists():
        return None
    if not config_path.is_file():
        raise ValueError("config.json exists but is not a file.")
    try:
        payload = json.loads(config_path.read_text(encoding='utf-8') or '{}')
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("config.json is not valid JSON.") from exc
    return normalize_system_settings_import_payload(payload)


def bootstrap_system_settings_config_json(path=None):
    """Apply first-launch config.json once against the authoritative singleton row."""
    config_path = resolve_system_settings_config_json_path(path)
    SystemSettings = apps.get_model('dlux', 'SystemSettings')
    cached_instance = SystemSettings.load()

    with transaction.atomic():
        instance = (
            SystemSettings._default_manager
            .select_for_update()
            .get(pk=cached_instance.pk)
        )
        if getattr(instance, 'is_configured', False):
            return SYSTEM_SETTINGS_CONFIG_BOOTSTRAP_CONFIGURED, config_path, instance

        imported_settings = load_system_settings_config_json(config_path)
        if imported_settings is None:
            return SYSTEM_SETTINGS_CONFIG_BOOTSTRAP_MISSING, config_path, instance
        if not imported_settings:
            raise ValueError("config.json contains no supported System Settings keys.")

        apply_system_settings_import(instance, imported_settings, mark_configured=True)
        return SYSTEM_SETTINGS_CONFIG_BOOTSTRAP_APPLIED, config_path, instance
