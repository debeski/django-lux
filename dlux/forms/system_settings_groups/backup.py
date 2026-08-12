"""Backup configuration cleaning.

Mixed into SystemSettingsForm; see dlux/forms/system_settings.py.
"""

import json
import re
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


class BackupCleanMixin:
    def clean_backup_config(self):
        data = self.cleaned_data.get('backup_config')
        if not data:
            return normalize_backup_config(getattr(self.instance, 'backup_config', None) or default_backup_config())
        if isinstance(data, dict):
            return normalize_backup_config(data)
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            raise ValidationError("Invalid backup JSON format.")
        if not isinstance(parsed, dict):
            raise ValidationError("Backup configuration must be a valid JSON object.")
        return normalize_backup_config(parsed)

    def clean_backup_auto_export_target(self):
        target = str(self.cleaned_data.get('backup_auto_export_target') or '').strip().strip('/')
        if not target:
            existing = normalize_backup_config(getattr(self.instance, 'backup_config', None) or {})
            return existing['auto_export_target']
        parts = target.split('/') if target else []
        if not parts or any(part in {'', '.', '..'} or not re.fullmatch(r'[A-Za-z0-9._-]+', part) for part in parts):
            raise ValidationError("Use a relative storage folder containing only letters, numbers, dots, underscores, hyphens, and slashes.")
        return target
