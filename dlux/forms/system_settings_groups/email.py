"""Email configuration cleaning.

Mixed into SystemSettingsForm; see dlux/forms/system_settings.py.
"""

from ...system.constants import (
    SETUP_STEP_IDENTITY,
    SETUP_STEP_LANGUAGES,
    SETUP_STEP_SECURITY,
    SETUP_STEP_EMAIL,
    SETUP_STEP_LOGIN,
    SETUP_STEP_SIDEBAR,
    SETUP_STEP_NAVBAR,
    SETUP_STEP_TITLEBAR,
    SETUP_STEP_NOTIFICATIONS,
    SETUP_STEP_APPEARANCE,
    SETUP_STEP_LAYOUT,
    SETUP_STEP_LOGGING,
    SETUP_STEP_PROFILE,
    SETUP_STEP_BACKUPS,
    SETUP_STEP_COUNT,
    DEFAULT_HOME_URL,
    DEFAULT_NAVBAR_MODE,
    DEFAULT_SIDEBAR_COLLAPSE_MODE,
    DEFAULT_SIDEBAR_TOGGLE_ICON,
    DEFAULT_SIDEBAR_DENSITY,
    DEFAULT_FORM_DENSITY,
    DEFAULT_MODAL_SIZE,
    DEFAULT_TABLE_DENSITY,
    FORM_DENSITY_CHOICES,
    FORM_DENSITY_VALUES,
    LAYOUT_FOOTER_TEXT_MAX_LENGTH,
    MODAL_SIZE_CHOICES,
    MODAL_SIZE_VALUES,
    OPTIONS_STYLE_CHOICES,
    OPTIONS_STYLE_VALUES,
    DEFAULT_OPTIONS_STYLE,
    THEME_PICKER_LOCATION_CHOICES,
    THEME_PICKER_LOCATION_VALUES,
    THEME_PICKER_LOCATION_TITLEBAR,
    DEFAULT_THEME_PICKER_LOCATION,
    ROW_ACTIONS_STYLE_CHOICES,
    ROW_ACTIONS_STYLE_VALUES,
    DEFAULT_ROW_ACTIONS_STYLE,
    PUBLIC_ROOT_META_DESCRIPTION_MAX_LENGTH,
    PUBLIC_ROOT_TITLE_MAX_LENGTH,
    REGISTRATION_ACTIVATION_CHOICES,
    REGISTRATION_ACTIVATION_VALUES,
    NAVBAR_MODE_CHOICES,
    NAVBAR_MODE_VALUES,
    SIDEBAR_COLLAPSE_MODE_CHOICES,
    SIDEBAR_TOGGLE_DIRECTIONAL_ICONS,
    SIDEBAR_TOGGLE_ICON_MAX_LENGTH,
    SIDEBAR_COLLAPSE_MODE_VALUES,
    SIDEBAR_DENSITY_CHOICES,
    SIDEBAR_DENSITY_VALUES,
    TABLE_DENSITY_CHOICES,
    TABLE_DENSITY_VALUES,
    TITLEBAR_ALIGN_CHOICES,
    TITLEBAR_ALIGN_VALUES,
    TITLEBAR_HEIGHT_CHOICES,
    TITLEBAR_HEIGHT_VALUES,
    TITLEBAR_HOME_SHAPE_CHOICES,
    TITLEBAR_HOME_SHAPE_VALUES,
    TITLEBAR_LOGO_TREATMENT_CHOICES,
    TITLEBAR_LOGO_TREATMENT_SHAPE_CHOICES,
    TITLEBAR_LOGO_TREATMENT_SHAPE_VALUES,
    TITLEBAR_LOGO_TREATMENT_VALUES,
    TITLEBAR_SIZE_CHOICES,
    TITLEBAR_SIZE_VALUES,
    TITLEBAR_SURFACE_CHOICES,
    TITLEBAR_SURFACE_VALUES,
    TITLEBAR_GLOBAL_SEARCH_CHOICES,
    TITLEBAR_GLOBAL_SEARCH_VALUES,
    TITLEBAR_ACTIONS_ORDER,
    TITLEBAR_USER_HUB_STYLE_ACTIONS,
    TITLEBAR_USER_HUB_STYLE_CHOICES,
    TITLEBAR_USER_HUB_STYLE_DROPDOWN,
    TITLEBAR_USER_HUB_STYLE_VALUES,
)
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

EMAIL_CONNECTION_FIELDS = (
    'email_config_transport',
    'email_config_secret_storage',
    'email_config_host',
    'email_config_port',
    'email_config_use_tls',
    'email_config_use_ssl',
    'email_config_username',
    'email_config_password',
    'email_config_default_from_email',
    'email_config_provider_preset',
    'email_config_failure_recipients',
)


class EmailCleanMixin:
    def clean_email_config(self):
        existing = normalize_email_config(getattr(self.instance, 'email_config', {}))

        # The connection fields are disabled while the step's master toggle is
        # off, so they are absent from POST and every `cleaned_data.get(...) or
        # ''` below reads empty. Rebuilding from them wiped the stored SMTP host,
        # username and sender. Keep the stored connection and apply only the
        # controls that are still live.
        if not any(name in self.data for name in EMAIL_CONNECTION_FIELDS):
            preserved = dict(existing)
            preserved['enabled'] = self._email_scalar('email_config_enabled', 'enabled', False)
            preserved['timeout'] = self._email_scalar('email_config_timeout', 'timeout', 0) or 0
            return normalize_email_config(preserved)

        transport = self.cleaned_data.get('email_config_transport') or existing.get('transport', 'direct')
        secret_storage = self.cleaned_data.get('email_config_secret_storage') or existing.get('secret_storage', 'env')
        existing_verified = existing if isinstance(existing, dict) else {}
        _payload = {
            'transport': transport,
            'secret_storage': secret_storage,
            'provider_preset': self.cleaned_data.get('email_config_provider_preset') or existing.get('provider_preset', 'custom'),
            'host': self.cleaned_data.get('email_config_host') or '',
            'port': self.cleaned_data.get('email_config_port') or 587,
            'use_tls': self.cleaned_data.get('email_config_use_tls'),
            'use_ssl': self.cleaned_data.get('email_config_use_ssl'),
            'username': self.cleaned_data.get('email_config_username') or '',
            'default_from_email': self.cleaned_data.get('email_config_default_from_email') or '',
            'failure_notification_recipients': self.cleaned_data.get('email_config_failure_recipients') or '',
            'enabled': self._email_scalar('email_config_enabled', 'enabled', False),
            'timeout': self._email_scalar('email_config_timeout', 'timeout', 0) or 0,
            'verified': existing_verified.get('verified', False),
            'verified_at': existing_verified.get('verified_at', ''),
            'verified_fingerprint': existing_verified.get('verified_fingerprint', ''),
        }
        # Normalize once to resolve the canonical transport/secret_storage, attach the
        # secret to the *payload*, then normalize again. The verification fingerprint is
        # computed inside normalize over encrypted_password, so a secret attached after
        # normalizing would fingerprint an empty password and revoke verification on the
        # very next read.
        _probe = normalize_email_config(_payload)
        if _probe['secret_storage'] == 'encrypted_db':
            raw_password = self.cleaned_data.get('email_config_password') or ''
            if raw_password:
                _payload['encrypted_password'] = encrypt_email_secret(raw_password)
            elif existing.get('transport') == _probe['transport'] and existing.get('secret_storage') == 'encrypted_db':
                _payload['encrypted_password'] = existing.get('encrypted_password', '')
        config = normalize_email_config(_payload)
        config['password_configured'] = bool(config.get('encrypted_password'))
        return config

    def clean_email_config_enabled(self):
        # email_config_enabled lives inside the email_config dict rather than as a
        # flat model attribute, so _clean_preserved_toggle cannot read it back.
        if (
            self.is_bound and self.mode != 'setup' and self.single_step_mode
            and self.single_step_index != SETUP_STEP_EMAIL
        ):
            stored = getattr(self.instance, 'email_config', None)
            return bool(stored.get('enabled', False)) if isinstance(stored, dict) else False
        return bool(self.cleaned_data.get('email_config_enabled', False))

    def clean_email_config_timeout(self):
        if (
            self.is_bound and self.mode != 'setup' and self.single_step_mode
            and self.single_step_index != SETUP_STEP_EMAIL
        ):
            stored = getattr(self.instance, 'email_config', None)
            return (stored or {}).get('timeout', 0) if isinstance(stored, dict) else 0
        return self.cleaned_data.get('email_config_timeout') or 0

    def _email_scalar(self, form_name, key, default):
        """Value for one email scalar, whichever cleaner order Django picks.

        ``email_config`` is a model field, so its position in ``self.fields`` comes
        from ``Meta.fields`` — ahead of the declared-only ``email_config_*`` scalars.
        clean_email_config() therefore packs the group *before* those scalars have
        been cleaned, and reading them out of ``cleaned_data`` silently yielded the
        empty default: a save of any other settings step reset timeout and enabled.
        Fall back to the stored value whenever the scalar has not been cleaned yet.
        """
        if form_name in self.cleaned_data:
            return self.cleaned_data[form_name]
        stored = getattr(self.instance, 'email_config', None)
        return stored.get(key, default) if isinstance(stored, dict) else default

    def clean_email_2fa(self):
        return self._auth_toggle_clean('email_2fa', False)
