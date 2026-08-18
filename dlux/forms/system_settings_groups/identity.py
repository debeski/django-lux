"""Identity and layout: system names, home URL, footer.

Mixed into SystemSettingsForm; see dlux/forms/system_settings.py.
"""

import json
from django.core.exceptions import ValidationError
from django.conf import settings
from ...system.constants import (
    SETUP_STEP_IDENTITY,
    SETUP_STEP_LANGUAGES,
    SETUP_STEP_HOMEPAGE,
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


class IdentityCleanMixin:
    def clean_system_names(self):
        data = self.cleaned_data.get('system_names')
        if not data:
            return {}
        try:
            parsed = json.loads(data) if isinstance(data, str) else data
        except json.JSONDecodeError:
            raise ValidationError("Invalid system names JSON format.")
        if not isinstance(parsed, dict):
            raise ValidationError("System names must be a valid JSON object.")
        return normalize_system_names(parsed)

    def clean_home_url(self):
        value = str(self.cleaned_data.get('home_url') or '').strip()
        discovered_value = str(self.cleaned_data.get('home_url_discovered') or '').strip()
        if self.is_bound and 'home_url' not in self.data and 'home_url_discovered' not in self.data:
            return (
                str(getattr(self.instance, 'home_url', '') or '').strip()
                or str(self.initial.get('home_url') or '').strip()
                or getattr(settings, 'DLUX_CONFIG', {}).get('home_url')
                or DEFAULT_HOME_URL
            )
        return value or discovered_value or getattr(settings, 'DLUX_CONFIG', {}).get('home_url') or DEFAULT_HOME_URL

    def clean_allow_user_home_url(self):
        if (
            self.is_bound and self.mode != 'setup' and self.single_step_mode
            and self.single_step_index != SETUP_STEP_HOMEPAGE
        ):
            stored = getattr(self.instance, 'homepage_config', None)
            if isinstance(stored, dict) and 'allow_user_override' in stored:
                return bool(stored.get('allow_user_override'))
            profile = getattr(self.instance, 'profile_config', None)
            if isinstance(profile, dict) and 'allow_user_home_url' in profile:
                return bool(profile.get('allow_user_home_url'))
            return bool(self.initial.get('allow_user_home_url', False))
        return bool(self.cleaned_data.get('allow_user_home_url'))

    def clean_footer_text(self):
        # Footer text lives in the Identity step. A single-step modal
        # post that does not own that step omits the field — preserve the stored
        # value instead of clearing it.
        if self.is_bound and self.mode != 'setup' and self.single_step_mode and 'footer_text' not in self.data:
            value = getattr(self.instance, 'footer_text', None)
            if value in (None, ''):
                value = self.initial.get('footer_text', '')
        else:
            value = self.cleaned_data.get('footer_text', '')
        return str(value or '').strip()[:LAYOUT_FOOTER_TEXT_MAX_LENGTH].rstrip()

    def clean_footer_enabled(self):
        # Checkbox in the Identity step (index 0). An unchecked box and an
        # omitted-because-other-step box both vanish from POST data, so key off
        # the active step rather than mere presence.
        if (
            self.is_bound and self.mode != 'setup' and self.single_step_mode
            and self.single_step_index != SETUP_STEP_IDENTITY
        ):
            return bool(getattr(self.instance, 'footer_enabled', True))
        return bool(self.cleaned_data.get('footer_enabled'))

    def clean_footer_link_url(self):
        # Scheme validation/sanitizing happens in normalize_layout_config; here we
        # only preserve the raw value across single-step saves.
        return self._clean_preserved_footer_string('footer_link_url')

    def clean_footer_link_text(self):
        return self._clean_preserved_footer_string('footer_link_text')
