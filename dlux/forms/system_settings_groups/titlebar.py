"""Titlebar configuration cleaning.

Mixed into SystemSettingsForm; see dlux/forms/system_settings.py.
"""

import json
from django.core.exceptions import ValidationError
from ...system.constants import (
    SETUP_STEP_IDENTITY,
    SETUP_STEP_LANGUAGES,
    SETUP_STEP_SEARCH,
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
    TITLEBAR_ACTIONS_LAYOUT_CHOICES,
    TITLEBAR_ACTIONS_LAYOUT_GROUPED,
    TITLEBAR_ACTIONS_LAYOUT_SCATTERED,
    TITLEBAR_ACTIONS_LAYOUT_VALUES,
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
    normalize_search_config,
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


class TitlebarCleanMixin:
    def clean_titlebar_actions_order(self):
        value = self.cleaned_data.get('titlebar_actions_order')
        if isinstance(value, str):
            value = value.strip()
            if value:
                try:
                    value = json.loads(value)
                except (TypeError, ValueError, json.JSONDecodeError):
                    value = []
            else:
                value = []
        return normalize_titlebar_actions_order(value)

    def clean_titlebar_home_shape(self):
        value = self.cleaned_data.get('titlebar_home_shape') or 'circle'
        if value not in TITLEBAR_HOME_SHAPE_VALUES:
            raise ValidationError("Invalid titlebar home shape.")
        return value

    def clean_titlebar_user_hub_style(self):
        value = self.cleaned_data.get('titlebar_user_hub_style') or TITLEBAR_USER_HUB_STYLE_DROPDOWN
        if value not in TITLEBAR_USER_HUB_STYLE_VALUES:
            raise ValidationError("Invalid titlebar and user hub style.")
        return value

    def clean_titlebar_actions_layout(self):
        value = self.cleaned_data.get('titlebar_actions_layout') or TITLEBAR_ACTIONS_LAYOUT_SCATTERED
        if value not in TITLEBAR_ACTIONS_LAYOUT_VALUES:
            raise ValidationError("Invalid titlebar action layout.")
        return value

    def clean_titlebar_global_search_mode(self):
        if (
            self.is_bound and self.mode != 'setup' and self.single_step_mode
            and self.single_step_index != SETUP_STEP_SEARCH
        ):
            stored = getattr(self.instance, 'search_config', None)
            if isinstance(stored, dict):
                normalized = normalize_search_config(stored)
                if not normalized.get('enabled', True):
                    return 'disabled'
                return normalized.get('display_mode', 'icon')
        value = self.cleaned_data.get('titlebar_global_search_mode') or 'icon'
        if value not in TITLEBAR_GLOBAL_SEARCH_VALUES:
            raise ValidationError("Invalid global search mode.")
        return value

    def clean_titlebar_global_search_include_data(self):
        if (
            self.is_bound and self.mode != 'setup' and self.single_step_mode
            and self.single_step_index != SETUP_STEP_SEARCH
        ):
            stored = getattr(self.instance, 'search_config', None)
            if isinstance(stored, dict):
                return bool(normalize_search_config(stored).get('include_data', False))
            return bool(self.initial.get('titlebar_global_search_include_data', False))
        return bool(self.cleaned_data.get('titlebar_global_search_include_data'))

    def clean_titlebar_title_align(self):
        value = self.cleaned_data.get('titlebar_title_align') or 'start'
        if value not in TITLEBAR_ALIGN_VALUES:
            raise ValidationError("Invalid title alignment.")
        return value

    def clean_titlebar_title_size(self):
        value = self.cleaned_data.get('titlebar_title_size') or 'md'
        if value not in TITLEBAR_SIZE_VALUES:
            raise ValidationError("Invalid title size.")
        return value

    def clean_titlebar_height(self):
        value = self.cleaned_data.get('titlebar_height') or 'balanced'
        if value not in TITLEBAR_HEIGHT_VALUES:
            raise ValidationError("Invalid titlebar height.")
        return value

    def clean_titlebar_surface(self):
        value = self.cleaned_data.get('titlebar_surface') or 'default'
        if value not in TITLEBAR_SURFACE_VALUES:
            raise ValidationError("Invalid titlebar surface.")
        return value

    def clean_titlebar_logo_treatment(self):
        value = self.cleaned_data.get('titlebar_logo_treatment') or 'none'
        if value not in TITLEBAR_LOGO_TREATMENT_VALUES:
            raise ValidationError("Invalid titlebar logo treatment.")
        return value

    def clean_titlebar_logo_treatment_shape(self):
        value = self.cleaned_data.get('titlebar_logo_treatment_shape') or 'soft'
        if value not in TITLEBAR_LOGO_TREATMENT_SHAPE_VALUES:
            raise ValidationError("Invalid titlebar logo treatment shape.")
        return value
