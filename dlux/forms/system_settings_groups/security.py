"""Access and security: lockout, password policy, session and audit toggles.

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


class SecurityCleanMixin:
    def _auth_toggle_clean(self, key, default):
        # The auth toggles now live in the auth_config JSON field. In a non-setup
        # single-step modal post that doesn't own the security step (index 2), the
        # checkbox is omitted; preserve the stored value instead of reading it as
        # an unchecked False.
        if (
            self.is_bound
            and self.mode != 'setup'
            and self.single_step_mode
            and self.single_step_index != SETUP_STEP_SECURITY
            and key not in self.data
        ):
            existing = normalize_auth_config(getattr(self.instance, 'auth_config', None) or {})
            return bool(existing.get(key, default))
        return bool(self.cleaned_data.get(key, default))

    def _auth_int_clean(self, key, default):
        # Same preservation rule as _auth_toggle_clean, for the numeric knobs:
        # a single-step post that doesn't own the security step omits the input,
        # so fall back to the stored auth_config value rather than the default.
        if (
            self.is_bound
            and self.mode != 'setup'
            and self.single_step_mode
            and self.single_step_index != SETUP_STEP_SECURITY
            and key not in self.data
        ):
            existing = normalize_auth_config(getattr(self.instance, 'auth_config', None) or {})
            return existing.get(key, default)
        value = self.cleaned_data.get(key)
        return default if value in (None, '') else value

    def clean_prevent_multiple_active_sessions(self):
        return self._auth_toggle_clean('prevent_multiple_active_sessions', False)

    def clean_login_lockout_enabled(self):
        return self._auth_toggle_clean('login_lockout_enabled', True)

    def clean_login_lockout_threshold(self):
        return self._auth_int_clean('login_lockout_threshold', 5)

    def clean_login_lockout_window_minutes(self):
        return self._auth_int_clean('login_lockout_window_minutes', 15)

    def clean_login_lockout_duration_minutes(self):
        return self._auth_int_clean('login_lockout_duration_minutes', 15)

    def clean_enforce_strong_passwords(self):
        return self._auth_toggle_clean('enforce_strong_passwords', False)

    def clean_strong_password_min_length(self):
        return self._auth_int_clean('strong_password_min_length', 12)

    def clean_purge_session_on_exit(self):
        return self._auth_toggle_clean('purge_session_on_exit', False)

    def clean_inactivity_timeout_enabled(self):
        return self._auth_toggle_clean('inactivity_timeout_enabled', False)

    def clean_inactivity_timeout_minutes(self):
        return self._auth_int_clean('inactivity_timeout_minutes', 10)

    def clean_show_audit_fields(self):
        return self._clean_preserved_toggle('show_audit_fields', SETUP_STEP_LAYOUT, False)

    def clean_show_soft_deleted(self):
        return self._clean_preserved_toggle('show_soft_deleted', SETUP_STEP_LAYOUT, False)
