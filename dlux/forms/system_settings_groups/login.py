"""Login page and public root cleaning.

Mixed into SystemSettingsForm; see dlux/forms/system_settings.py.
"""

from django.conf import settings
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


class LoginCleanMixin:
    def clean_public_root_url(self):
        value = str(self.cleaned_data.get('public_root_url') or '').strip()
        discovered_value = str(self.cleaned_data.get('public_root_url_discovered') or '').strip()
        home_url = str(self.cleaned_data.get('home_url') or '').strip()
        if self.is_bound and 'public_root_url' not in self.data and 'public_root_url_discovered' not in self.data:
            return (
                str(getattr(self.instance, 'public_root_url', '') or '').strip()
                or str(self.initial.get('public_root_url') or '').strip()
                or str(getattr(settings, 'DLUX_CONFIG', {}).get('public_root_url') or '').strip()
                or home_url
                or getattr(settings, 'DLUX_CONFIG', {}).get('home_url')
                or DEFAULT_HOME_URL
            )
        return (
            value
            or discovered_value
            or str(getattr(settings, 'DLUX_CONFIG', {}).get('public_root_url') or '').strip()
            or home_url
            or getattr(settings, 'DLUX_CONFIG', {}).get('home_url')
            or DEFAULT_HOME_URL
        )

    def clean_public_root_theme(self):
        # Stored value can be empty (= use system default), which is valid, so
        # accept '' alongside known theme slugs.
        valid = {''} | {value for value, _, _ in get_theme_choices()}
        if (
            self.is_bound and self.mode != 'setup' and self.single_step_mode
            and self.single_step_index != SETUP_STEP_APPEARANCE and 'public_root_theme' not in self.data
        ):
            value = getattr(self.instance, 'public_root_theme', '') or self.initial.get('public_root_theme', '')
        else:
            value = self.cleaned_data.get('public_root_theme', '')
        value = str(value or '').strip()
        return value if value in valid else ''

    def clean_public_root_meta_description(self):
        return self._clean_preserved_text(
            'public_root_meta_description', 0, PUBLIC_ROOT_META_DESCRIPTION_MAX_LENGTH
        )

    def clean_public_root_title(self):
        return self._clean_preserved_text('public_root_title', SETUP_STEP_IDENTITY, PUBLIC_ROOT_TITLE_MAX_LENGTH)

    def clean_show_titlebar_on_public(self):
        return self._clean_preserved_toggle('show_titlebar_on_public', SETUP_STEP_TITLEBAR, False)

    def clean_show_sidebar_on_public(self):
        return self._clean_preserved_toggle('show_sidebar_on_public', SETUP_STEP_SIDEBAR, False)

    def clean_forgot_password_enabled(self):
        return self._auth_toggle_clean('forgot_password_enabled', False)

    def clean_honeypot_enabled(self):
        return self._clean_preserved_toggle('honeypot_enabled', SETUP_STEP_SECURITY, True)

    def clean_registration_require_consent(self):
        return self._clean_preserved_toggle('registration_require_consent', SETUP_STEP_SECURITY, False)

    def clean_privacy_policy_url(self):
        return self._clean_preserved_text('privacy_policy_url', SETUP_STEP_SECURITY, 500)

    def clean_terms_url(self):
        return self._clean_preserved_text('terms_url', SETUP_STEP_SECURITY, 500)

    def clean_privacy_notice_text(self):
        return self._clean_preserved_text('privacy_notice_text', SETUP_STEP_SECURITY, 500)
