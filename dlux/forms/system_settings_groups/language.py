"""Languages and translation overrides cleaning.

Mixed into SystemSettingsForm; see dlux/forms/system_settings.py.
"""

import json
from django.core.exceptions import ValidationError
from ...utils import (
    CLIENT_IP_MODE_AUTO,
    CLIENT_IP_MODE_CLOUDFLARE,
    CLIENT_IP_MODE_CUSTOM,
    CLIENT_IP_MODE_REMOTE_ADDR,
    CLIENT_IP_MODE_X_FORWARDED_FOR,
    CLIENT_IP_MODE_X_REAL_IP,
    default_client_ip_config,
    default_auth_config,
    default_backup_config,
    default_log_config,
    default_profile_config,
    default_login_config,
    default_navbar_config,
    default_notification_config,
    default_titlebar_config,
    default_email_config,
    encrypt_email_secret,
    apply_system_settings_import,
    get_email_service_status,
    email_features_unlocked,
    get_system_config,
    has_section_models,
    normalize_system_settings_import_payload,
    normalize_email_config,
    normalize_client_ip_config,
    normalize_language_catalog,
    normalize_auth_config,
    normalize_backup_config,
    normalize_log_config,
    normalize_profile_config,
    normalize_login_config,
    normalize_notification_config,
    normalize_sidebar_behavior,
    normalize_sidebar_toggle_icon,
    normalize_system_names,
    normalize_titlebar_actions_order,
    normalize_titlebar_config,
    normalize_allowed_fonts,
    seed_navbar_config_from_sidebar,
)


class LanguageCleanMixin:
    def clean_languages(self):
        data = self.cleaned_data.get('languages')
        if not data:
            return normalize_language_catalog()
        try:
            parsed = json.loads(data) if isinstance(data, str) else data
            if not isinstance(parsed, dict):
                raise ValidationError("Must be a valid JSON dictionary.")
            return normalize_language_catalog(parsed)
        except json.JSONDecodeError:
            raise ValidationError("Invalid JSON format.")

    def clean_default_language(self):
        return str(self.cleaned_data.get('default_language') or 'en').strip().lower().replace('_', '-')

    def clean_translations_override(self):
        data = self.cleaned_data.get('translations_override')
        if not data:
            return {}
        try:
            parsed = json.loads(data) if isinstance(data, str) else data
            if not isinstance(parsed, dict):
                raise ValidationError("Must be a valid JSON dictionary.")
            cleaned = {}
            for lang, values in parsed.items():
                if not isinstance(values, dict):
                    continue
                lang_values = {}
                for key, value in values.items():
                    text = str(value or '').strip()
                    if key and text:
                        lang_values[str(key)] = text
                if lang_values:
                    cleaned[str(lang).split('-')[0].lower()] = lang_values
            return cleaned
        except json.JSONDecodeError:
            raise ValidationError("Invalid JSON format.")
