"""Themes, fonts and density cleaning.

Mixed into SystemSettingsForm; see dlux/forms/system_settings.py.
"""

import json
from django.core.exceptions import ValidationError
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
from ...themes import get_theme_choices, get_theme_options, is_valid_theme, normalize_allowed_themes
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


class AppearanceCleanMixin:
    def clean_default_theme(self):
        if self.is_bound and self.mode != 'setup' and self.single_step_mode and 'default_theme' not in self.data:
            value = (
                getattr(self.instance, 'default_theme', None)
                or self.initial.get('default_theme')
                or 'light'
            )
        else:
            value = self.cleaned_data.get('default_theme') or 'light'
        if not is_valid_theme(value):
            raise ValidationError("Invalid theme choice.")
        return value

    def clean_allowed_themes(self):
        if self.is_bound and self.mode != 'setup' and self.single_step_mode and 'allowed_themes' not in self.data:
            values = getattr(self.instance, 'allowed_themes', None)
            if not values:
                values = self.initial.get('allowed_themes')
            normalized = list(normalize_allowed_themes(values))
            if not normalized:
                raise ValidationError("At least one theme must remain enabled.")
            return normalized
        values = self.cleaned_data.get('allowed_themes') or []
        if not values:
            raise ValidationError("At least one theme must remain enabled.")
        normalized = list(normalize_allowed_themes(values))
        if not normalized:
            raise ValidationError("At least one theme must remain enabled.")
        return normalized

    def clean_default_fonts(self):
        if self.is_bound and self.mode != 'setup' and self.single_step_mode and 'default_fonts' not in self.data:
            preserved = getattr(self.instance, 'default_fonts', None)
            if preserved in (None, ''):
                preserved = self.initial.get('default_fonts')
            if isinstance(preserved, str):
                try:
                    preserved = json.loads(preserved)
                except json.JSONDecodeError:
                    preserved = {}
            return preserved if isinstance(preserved, dict) else {}
        data = self.cleaned_data.get('default_fonts')
        if not data:
            return {}
        try:
            parsed = json.loads(data) if isinstance(data, str) else data
            if not isinstance(parsed, dict):
                return {}
            return parsed
        except json.JSONDecodeError:
            return {}

    def clean_allowed_fonts(self):
        if self.is_bound and self.mode != 'setup' and self.single_step_mode and 'allowed_fonts' not in self.data:
            preserved = getattr(self.instance, 'allowed_fonts', None)
            if preserved in (None, ''):
                preserved = self.initial.get('allowed_fonts')
            return list(normalize_allowed_fonts(preserved))
        data = self.cleaned_data.get('allowed_fonts')
        if not data:
            return []
        return list(data)

    def clean_theme_picker_location(self):
        return self._clean_preserved_choice(
            'theme_picker_location',
            SETUP_STEP_APPEARANCE,
            THEME_PICKER_LOCATION_VALUES,
            DEFAULT_THEME_PICKER_LOCATION,
        )

    def clean_default_table_density(self):
        if self.is_bound and self.mode != 'setup' and self.single_step_mode and 'default_table_density' not in self.data:
            value = (
                getattr(self.instance, 'default_table_density', None)
                or self.initial.get('default_table_density')
                or DEFAULT_TABLE_DENSITY
            )
        else:
            value = self.cleaned_data.get('default_table_density') or DEFAULT_TABLE_DENSITY
        if value not in TABLE_DENSITY_VALUES:
            raise ValidationError("Invalid table density choice.")
        return value

    def clean_default_form_density(self):
        return self._clean_preserved_choice('default_form_density', SETUP_STEP_LAYOUT, FORM_DENSITY_VALUES, DEFAULT_FORM_DENSITY)

    def clean_default_modal_size(self):
        return self._clean_preserved_choice('default_modal_size', SETUP_STEP_LAYOUT, MODAL_SIZE_VALUES, DEFAULT_MODAL_SIZE)

    def clean_options_style(self):
        return self._clean_preserved_choice('options_style', SETUP_STEP_LAYOUT, OPTIONS_STYLE_VALUES, DEFAULT_OPTIONS_STYLE)

    def clean_row_actions_style(self):
        return self._clean_preserved_choice('row_actions_style', SETUP_STEP_LAYOUT, ROW_ACTIONS_STYLE_VALUES, DEFAULT_ROW_ACTIONS_STYLE)

    def clean_sticky_table_headers(self):
        return self._clean_preserved_toggle('sticky_table_headers', SETUP_STEP_LAYOUT, True)

    def clean_resizable_table_columns(self):
        return self._clean_preserved_toggle('resizable_table_columns', SETUP_STEP_LAYOUT, True)

    def clean_zebra_striping(self):
        return self._clean_preserved_toggle('zebra_striping', SETUP_STEP_LAYOUT, True)
