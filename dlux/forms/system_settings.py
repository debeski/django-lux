"""The System Settings wizard form.

Still one module by design: SystemSettingsForm is split into per-group mixins
in a later pass (Phase 1-B of audit_plan.md). Moving it wholesale first keeps
that change reviewable on its own."""

import os
import json
import re
from pathlib import Path
from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, Div, HTML, Row
from crispy_forms.bootstrap import FormActions
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.db import transaction
from django.apps import apps
from django.conf import settings
from django.template.loader import render_to_string
from django.urls import NoReverseMatch, reverse
from ..system.constants import (
    SETUP_STEP_IDENTITY,
    SETUP_STEP_LANGUAGES,
    SETUP_STEP_HOMEPAGE,
    SETUP_STEP_SECURITY,
    SETUP_STEP_EMAIL,
    SETUP_STEP_LOGIN,
    SETUP_STEP_SIDEBAR,
    SETUP_STEP_NAVBAR,
    SETUP_STEP_TITLEBAR,
    SETUP_STEP_SEARCH,
    SETUP_STEP_NOTIFICATIONS,
    SETUP_STEP_APPEARANCE,
    SETUP_STEP_LAYOUT,
    SETUP_STEP_LOGGING,
    SETUP_STEP_PROFILE,
    SETUP_STEP_BACKUPS,
    SETUP_STEP_EXTRAS,
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
from ..translations import build_translation_matrix_groups, discover_translation_languages, get_strings, get_current_language_code
from ..themes import get_theme_choices, get_theme_options, is_valid_theme, normalize_allowed_themes
from ..utils import (
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
    default_homepage_config,
    default_profile_config,
    default_login_config,
    default_navbar_config,
    default_notification_config,
    default_search_config,
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
    normalize_homepage_config,
    normalize_profile_config,
    normalize_login_config,
    normalize_notification_config,
    normalize_search_config,
    normalize_sidebar_behavior,
    normalize_sidebar_toggle_icon,
    normalize_system_names,
    normalize_titlebar_actions_order,
    normalize_titlebar_config,
    normalize_allowed_fonts,
    seed_navbar_config_from_sidebar,
)
from ..system.registry import get_setting_group
from ..widgets import DluxChoiceSelectorWidget
from .assets import AssetPickerField, AssetSelection
from ..assets import adopt_stored_asset, create_managed_asset
from ..fonts import get_font_choices

from ._shared import FONT_CHOICES, THEME_CHOICES, _LEGACY_HOME_URL, _json_dump, logger
from .builders import EMAIL_DEPENDENT_SETTING_FIELDS, _bind_choice_selector_widget, _build_archive_file_widget, _get_ui_direction, build_archive_file_field, build_email_test_control, build_email_toggle_field, build_settings_toggle_field, build_titlebar_actions_order_builder


def _system_settings_sidebar_tools_available(cleaned_data):
    allowed_themes = cleaned_data.get('allowed_themes') or []
    theme_picker_enabled = bool(cleaned_data.get('allow_user_theme_override', True)) and len(allowed_themes) > 1
    density_picker_enabled = bool(cleaned_data.get('sidebar_allow_user_density', True))
    reorder_enabled = bool(cleaned_data.get('sidebar_enable_reorder', True))
    return bool(theme_picker_enabled or density_picker_enabled or reorder_enabled or has_section_models())




from .system_settings_groups.email import EMAIL_CONNECTION_FIELDS
from .system_settings_groups import (
    PreservedValueMixin,
    IdentityCleanMixin,
    SecurityCleanMixin,
    EmailCleanMixin,
    LoginCleanMixin,
    SidebarCleanMixin,
    NavbarCleanMixin,
    TitlebarCleanMixin,
    NotificationsCleanMixin,
    AppearanceCleanMixin,
    LanguageCleanMixin,
    LoggingCleanMixin,
    BackupCleanMixin,
    LayoutMixin,
)


class SystemSettingsForm(
    PreservedValueMixin,
    IdentityCleanMixin,
    SecurityCleanMixin,
    EmailCleanMixin,
    LoginCleanMixin,
    SidebarCleanMixin,
    NavbarCleanMixin,
    TitlebarCleanMixin,
    NotificationsCleanMixin,
    AppearanceCleanMixin,
    LanguageCleanMixin,
    LoggingCleanMixin,
    BackupCleanMixin,
    LayoutMixin,
    forms.ModelForm,
):
    logo = AssetPickerField(kind='image')
    favicon = AssetPickerField(kind='image')
    login_logo = AssetPickerField(kind='image')
    login_background = AssetPickerField(kind='image')
    _SCHEMA_SIMPLE_CONFIG_GROUPS = (
        'auth_config',
        'registration_config',
        'public_root_config',
        'layout_config',
        'client_ip_config',
        'backup_config',
    )

    home_url_discovered = forms.ChoiceField(
        required=False,
        choices=(),
    )
    public_root_url_discovered = forms.ChoiceField(
        required=False,
        choices=(),
    )
    settings_import_file = forms.FileField(
        required=False,
    )
    settings_import_processed = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.HiddenInput(),
    )
    default_language = forms.CharField(
        required=True,
        widget=forms.HiddenInput(),
    )
    system_names = forms.CharField(
        widget=forms.HiddenInput(),
        required=False,
    )
    default_theme = forms.ChoiceField(
        required=True,
        choices=[(value, value) for value, _, _ in THEME_CHOICES],
        widget=forms.HiddenInput(),
    )
    allowed_themes = forms.MultipleChoiceField(
        required=False,
        choices=[(value, value) for value, _, _ in THEME_CHOICES],
    )
    allow_user_theme_override = forms.BooleanField(
        required=False,
        initial=True,
    )
    theme_picker_location = forms.ChoiceField(
        required=False,
        choices=THEME_PICKER_LOCATION_CHOICES,
        initial=DEFAULT_THEME_PICKER_LOCATION,
    )
    allow_user_language_override = forms.BooleanField(
        required=False,
        initial=True,
    )
    # Stored inside profile_config, but surfaced as a standalone toggle next to
    # the Home URL field (Step 3) rather than in the profile builder (Step 12).
    allow_user_home_url = forms.BooleanField(
        required=False,
        initial=False,
    )
    allowed_fonts = forms.MultipleChoiceField(
        required=False,
        choices=FONT_CHOICES,
    )
    allow_user_font_override = forms.BooleanField(
        required=False,
        initial=True,
    )
    default_fonts = forms.CharField(
        widget=forms.HiddenInput(),
        required=False,
    )
    default_table_density = forms.ChoiceField(
        required=True,
        choices=TABLE_DENSITY_CHOICES,
        widget=forms.HiddenInput(),
    )
    default_form_density = forms.ChoiceField(
        required=False,
        choices=FORM_DENSITY_CHOICES,
        widget=forms.HiddenInput(),
    )
    default_modal_size = forms.ChoiceField(
        required=False,
        choices=MODAL_SIZE_CHOICES,
        widget=forms.HiddenInput(),
    )
    options_style = forms.ChoiceField(
        required=False,
        choices=OPTIONS_STYLE_CHOICES,
        widget=forms.HiddenInput(),
    )
    row_actions_style = forms.ChoiceField(
        required=False,
        choices=ROW_ACTIONS_STYLE_CHOICES,
        widget=forms.HiddenInput(),
    )
    sticky_table_headers = forms.BooleanField(
        required=False,
        initial=True,
    )
    resizable_table_columns = forms.BooleanField(
        required=False,
        initial=True,
    )
    zebra_striping = forms.BooleanField(
        required=False,
        initial=True,
    )
    show_audit_fields = forms.BooleanField(
        required=False,
        initial=False,
    )
    show_soft_deleted = forms.BooleanField(
        required=False,
        initial=False,
    )
    footer_enabled = forms.BooleanField(
        required=False,
        initial=True,
    )
    footer_text = forms.CharField(
        required=False,
        max_length=LAYOUT_FOOTER_TEXT_MAX_LENGTH,
        widget=forms.TextInput(attrs={'class': 'form-control glass-input', 'dir': 'auto'}),
    )
    footer_link_text = forms.CharField(
        required=False,
        max_length=LAYOUT_FOOTER_TEXT_MAX_LENGTH,
        widget=forms.TextInput(attrs={'class': 'form-control glass-input', 'dir': 'auto'}),
    )
    footer_link_url = forms.CharField(
        required=False,
        max_length=LAYOUT_FOOTER_TEXT_MAX_LENGTH,
        widget=forms.TextInput(attrs={'class': 'form-control glass-input', 'dir': 'ltr'}),
    )
    languages = forms.CharField(
        widget=forms.HiddenInput(),
        required=False,
    )
    translations_override = forms.CharField(
        widget=forms.HiddenInput(),
        required=False,
    )
    email_config_transport = forms.ChoiceField(
        required=False,
        choices=(
            ('relay', 'Internal SMTP relay'),
            ('direct', 'Direct SMTP from web service'),
        ),
    )
    email_config_secret_storage = forms.ChoiceField(
        required=False,
        choices=(
            ('encrypted_db', 'Encrypted database secret'),
            ('env', 'Environment / secrets'),
        ),
    )
    email_config_provider_preset = forms.ChoiceField(
        required=False,
        choices=(
            ('custom', 'Custom / manual'),
            ('gmail', 'Gmail'),
            ('outlook', 'Outlook / Office 365'),
            ('ses', 'Amazon SES'),
            ('mailgun', 'Mailgun'),
            ('relay', 'Internal relay'),
        ),
    )
    email_config_host = forms.CharField(required=False, max_length=255)
    email_config_port = forms.IntegerField(required=False, min_value=1, max_value=65535)
    email_config_use_tls = forms.BooleanField(required=False, initial=True)
    email_config_use_ssl = forms.BooleanField(required=False, initial=False)
    email_config_username = forms.CharField(required=False, max_length=255)
    email_config_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
    )
    email_config_default_from_email = forms.EmailField(required=False)
    email_config_failure_recipients = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 2}),
    )
    email_config_test_recipient = forms.EmailField(required=False)
    email_config_enabled = forms.BooleanField(required=False, initial=False)
    email_config_timeout = forms.IntegerField(required=False, min_value=0, max_value=300)
    # Declared last on purpose: Django cleans fields in declaration order and
    # clean_email_config() packs this group from the scalar fields above, so it
    # must run after them. Declared first, it packed an empty cleaned_data and
    # silently reset timeout/enabled on any save of another settings step.
    email_config = forms.CharField(
        widget=forms.HiddenInput(),
        required=False,
    )
    sidebar_config = forms.CharField(
        widget=forms.HiddenInput(),
        required=False,
    )
    navbar_config = forms.CharField(
        widget=forms.HiddenInput(),
        required=False,
    )
    log_config = forms.CharField(
        widget=forms.HiddenInput(),
        required=False,
    )
    profile_config = forms.CharField(
        widget=forms.HiddenInput(),
        required=False,
    )
    homepage_config = forms.CharField(widget=forms.HiddenInput(), required=False)
    backup_config = forms.CharField(widget=forms.HiddenInput(), required=False)
    # Extra Features. Not a model field: it lives in the dlux-owned top level of
    # `extra_config`, alongside the `app` namespace that projects own.
    scanlink_enabled = forms.BooleanField(required=False, initial=False)
    backup_scheduled_enabled = forms.BooleanField(required=False, initial=False)
    backup_schedule_interval_hours = forms.IntegerField(required=False, min_value=1, max_value=8760, initial=24)
    backup_retention_days = forms.IntegerField(required=False, min_value=0, max_value=3650, initial=0)
    backup_max_backups_to_keep = forms.IntegerField(required=False, min_value=0, max_value=10000, initial=0)
    backup_auto_export_target = forms.CharField(required=False, max_length=180, initial='dlux_backups')
    backup_stall_timeout_minutes = forms.IntegerField(required=False, min_value=2, max_value=1440, initial=30)
    backup_auto_retry_enabled = forms.BooleanField(required=False, initial=True)
    backup_max_attempts = forms.IntegerField(required=False, min_value=1, max_value=10, initial=3)
    backup_retry_delay_minutes = forms.IntegerField(required=False, min_value=0, max_value=1440, initial=5)
    sidebar_enabled = forms.BooleanField(
        required=False,
        initial=True,
    )
    sidebar_enable_reorder = forms.BooleanField(
        required=False,
        initial=True,
    )
    sidebar_enable_toolbar = forms.BooleanField(
        required=False,
        initial=True,
    )
    sidebar_show_icons = forms.BooleanField(
        required=False,
        initial=True,
    )
    sidebar_show_notification_badges = forms.BooleanField(
        required=False,
        initial=True,
    )
    sidebar_density = forms.ChoiceField(
        required=False,
        choices=SIDEBAR_DENSITY_CHOICES,
        widget=forms.HiddenInput(),
    )
    sidebar_allow_user_density = forms.BooleanField(
        required=False,
        initial=True,
    )
    sidebar_collapse_mode = forms.ChoiceField(
        required=False,
        choices=SIDEBAR_COLLAPSE_MODE_CHOICES,
        initial=DEFAULT_SIDEBAR_COLLAPSE_MODE,
    )
    sidebar_toggle_icon = forms.CharField(
        required=False,
        initial=DEFAULT_SIDEBAR_TOGGLE_ICON,
        max_length=SIDEBAR_TOGGLE_ICON_MAX_LENGTH,
        widget=forms.HiddenInput(),
    )
    navbar_enabled = forms.BooleanField(
        required=False,
        initial=False,
    )
    navbar_default_mode = forms.ChoiceField(
        required=False,
        choices=NAVBAR_MODE_CHOICES,
        initial=DEFAULT_NAVBAR_MODE,
    )
    navbar_allow_user_mode_override = forms.BooleanField(
        required=False,
        initial=True,
    )
    titlebar_show_logo = forms.BooleanField(
        required=False,
        initial=True,
    )
    titlebar_show_title = forms.BooleanField(
        required=False,
        initial=True,
    )
    titlebar_show_home_button = forms.BooleanField(
        required=False,
        initial=True,
    )
    titlebar_home_shape = forms.ChoiceField(
        required=False,
        choices=TITLEBAR_HOME_SHAPE_CHOICES,
        initial='circle',
    )
    titlebar_user_hub_style = forms.ChoiceField(
        required=False,
        choices=TITLEBAR_USER_HUB_STYLE_CHOICES,
        initial=TITLEBAR_USER_HUB_STYLE_DROPDOWN,
    )
    titlebar_show_language_switcher = forms.BooleanField(
        required=False,
        initial=False,
    )
    titlebar_actions_order = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
    )
    titlebar_title_align = forms.ChoiceField(
        required=False,
        choices=TITLEBAR_ALIGN_CHOICES,
        initial='start',
    )
    titlebar_title_size = forms.ChoiceField(
        required=False,
        choices=TITLEBAR_SIZE_CHOICES,
        initial='md',
    )
    titlebar_height = forms.ChoiceField(
        required=False,
        choices=TITLEBAR_HEIGHT_CHOICES,
        initial='balanced',
    )
    titlebar_surface = forms.ChoiceField(
        required=False,
        choices=TITLEBAR_SURFACE_CHOICES,
        initial='default',
    )
    titlebar_logo_treatment = forms.ChoiceField(
        required=False,
        choices=TITLEBAR_LOGO_TREATMENT_CHOICES,
        initial='none',
    )
    titlebar_logo_treatment_shape = forms.ChoiceField(
        required=False,
        choices=TITLEBAR_LOGO_TREATMENT_SHAPE_CHOICES,
        initial='soft',
    )
    titlebar_global_search_mode = forms.ChoiceField(
        required=False,
        choices=TITLEBAR_GLOBAL_SEARCH_CHOICES,
        initial='icon',
    )
    titlebar_global_search_include_data = forms.BooleanField(
        required=False,
        initial=False,
    )
    search_config = forms.CharField(widget=forms.HiddenInput(), required=False)
    notification_config = forms.CharField(
        widget=forms.HiddenInput(),
        required=False,
    )
    notifications_enabled = forms.BooleanField(
        required=False,
        initial=True,
    )
    notification_flash_enabled = forms.BooleanField(
        required=False,
        initial=True,
    )
    notification_flash_position = forms.ChoiceField(
        required=False,
        choices=(
            ('top_center', 'Top center'),
            ('top_start', 'Top start'),
            ('top_end', 'Top end'),
            ('titlebar_end', 'Titlebar end'),
            ('bottom_start', 'Bottom start'),
            ('bottom_end', 'Bottom end'),
        ),
        initial='top_center',
    )
    notification_flash_size = forms.ChoiceField(
        required=False,
        choices=(
            ('compact', 'Compact'),
            ('balanced', 'Balanced'),
            ('prominent', 'Prominent'),
        ),
        initial='balanced',
    )
    notification_flash_text_size = forms.ChoiceField(
        required=False,
        choices=(
            ('sm', 'Small'),
            ('md', 'Medium'),
            ('lg', 'Large'),
        ),
        initial='md',
    )
    notification_flash_timeout_ms = forms.IntegerField(
        required=False,
        min_value=0,
        max_value=60000,
        initial=3200,
    )
    notification_flash_max_visible = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=10,
        initial=3,
    )
    notification_drawer_enabled = forms.BooleanField(
        required=False,
        initial=True,
    )
    notification_badge_enabled = forms.BooleanField(
        required=False,
        initial=True,
    )
    notification_bridge_enabled = forms.BooleanField(
        required=False,
        initial=False,
    )
    notification_email_enabled = forms.BooleanField(
        required=False,
        initial=False,
    )
    notification_email_default = forms.BooleanField(
        required=False,
        initial=False,
    )
    notification_auto_crud_enabled = forms.BooleanField(
        required=False,
        initial=True,
    )
    notification_auto_create = forms.BooleanField(
        required=False,
        initial=True,
    )
    notification_auto_update = forms.ChoiceField(
        required=False,
        choices=(
            ('off', 'Off'),
            ('summary', 'Summary'),
            ('full', 'Full'),
        ),
        initial='summary',
    )
    notification_auto_delete = forms.BooleanField(
        required=False,
        initial=True,
    )
    login_config = forms.CharField(
        widget=forms.HiddenInput(),
        required=False,
    )
    login_style = forms.ChoiceField(
        required=False,
        choices=(
            ('split', ''),
            ('centered', ''),
            ('minimal', ''),
            ('fullpage', ''),
        ),
        initial='split',
    )
    login_show_logo = forms.BooleanField(
        required=False,
        initial=True,
    )
    login_banner_color = forms.CharField(
        required=False,
        initial='',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '#2b3035',
            'pattern': r'^(#[0-9a-fA-F]{3,8}|[a-z]+)?$',
            'spellcheck': 'false',
        }),
    )
    login_logo_treatment = forms.ChoiceField(
        required=False,
        choices=TITLEBAR_LOGO_TREATMENT_CHOICES,
        initial='none',
    )
    login_logo_treatment_shape = forms.ChoiceField(
        required=False,
        choices=TITLEBAR_LOGO_TREATMENT_SHAPE_CHOICES,
        initial='soft',
    )
    # login_hero_message_{lang} fields are added dynamically per language in __init__
    email_2fa = forms.BooleanField(
        required=False,
        initial=False,
    )
    forgot_password_enabled = forms.BooleanField(
        required=False,
        initial=False,
    )
    prevent_multiple_active_sessions = forms.BooleanField(
        required=False,
        initial=False,
    )
    login_lockout_enabled = forms.BooleanField(
        required=False,
        initial=True,
    )
    login_lockout_threshold = forms.IntegerField(required=False, min_value=1, max_value=50, initial=5)
    login_lockout_window_minutes = forms.IntegerField(required=False, min_value=1, max_value=1440, initial=15)
    login_lockout_duration_minutes = forms.IntegerField(required=False, min_value=1, max_value=1440, initial=15)
    enforce_strong_passwords = forms.BooleanField(
        required=False,
        initial=False,
    )
    strong_password_min_length = forms.IntegerField(required=False, min_value=8, max_value=64, initial=12)
    purge_session_on_exit = forms.BooleanField(
        required=False,
        initial=False,
    )
    inactivity_timeout_enabled = forms.BooleanField(
        required=False,
        initial=False,
    )
    inactivity_timeout_minutes = forms.IntegerField(required=False, min_value=1, max_value=1440, initial=10)
    auth_config = forms.CharField(
        widget=forms.HiddenInput(),
        required=False,
    )
    client_ip_config = forms.CharField(
        widget=forms.HiddenInput(),
        required=False,
    )
    client_ip_mode = forms.ChoiceField(
        required=False,
        choices=(),
    )
    client_ip_trusted_proxy_hops = forms.IntegerField(
        required=False,
        min_value=0,
        max_value=8,
    )
    client_ip_custom_header = forms.CharField(
        required=False,
        max_length=255,
    )
    public_root = forms.BooleanField(
        required=False,
        initial=False,
    )
    public_root_split_enabled = forms.BooleanField(
        required=False,
        initial=False,
    )
    public_root_url = forms.CharField(
        required=False,
        max_length=255,
    )
    public_root_theme = forms.ChoiceField(
        required=False,
        widget=forms.HiddenInput(),
    )
    public_root_title = forms.CharField(
        required=False,
        max_length=PUBLIC_ROOT_TITLE_MAX_LENGTH,
        widget=forms.TextInput(attrs={'class': 'form-control glass-input', 'dir': 'auto'}),
    )
    public_root_meta_description = forms.CharField(
        required=False,
        max_length=PUBLIC_ROOT_META_DESCRIPTION_MAX_LENGTH,
        widget=forms.Textarea(attrs={'class': 'form-control glass-input', 'dir': 'auto', 'rows': 2}),
    )
    show_titlebar_on_public = forms.BooleanField(
        required=False,
        initial=False,
    )
    show_sidebar_on_public = forms.BooleanField(
        required=False,
        initial=False,
    )
    public_registration_enabled = forms.BooleanField(
        required=False,
        initial=False,
    )
    registration_activation_mode = forms.ChoiceField(
        required=False,
        choices=REGISTRATION_ACTIVATION_CHOICES,
    )
    registration_throttle_enabled = forms.BooleanField(
        required=False,
        initial=True,
    )
    honeypot_enabled = forms.BooleanField(
        required=False,
        initial=True,
    )
    privacy_policy_url = forms.CharField(required=False, max_length=500)
    terms_url = forms.CharField(required=False, max_length=500)
    privacy_notice_text = forms.CharField(required=False, max_length=500)
    registration_require_consent = forms.BooleanField(required=False, initial=False)

    class Meta:
        model = apps.get_model('dlux', 'SystemSettings')
        exclude = ['logo', 'favicon']
        fields = [
            'system_names',
            'logo',
            'favicon',
            'login_logo',
            'login_background',
            'home_url',
            'homepage_config',
            'default_language',
            'default_theme',
            'allowed_themes',
            'allow_user_theme_override',
            'theme_picker_location',
            'allowed_fonts',
            'allow_user_font_override',
            'default_fonts',
            'allow_user_language_override',
            'default_table_density',
            'default_form_density',
            'default_modal_size',
            'sticky_table_headers',
            'resizable_table_columns',
            'zebra_striping',
            'show_audit_fields',
            'show_soft_deleted',
            'footer_enabled',
            'footer_text',
            'footer_link_text',
            'footer_link_url',
            'auth_config',
            'client_ip_config',
            'public_root',
            'public_root_split_enabled',
            'public_root_url',
            'public_root_theme',
            'public_root_title',
            'public_root_meta_description',
            'show_titlebar_on_public',
            'show_sidebar_on_public',
            'public_registration_enabled',
            'registration_activation_mode',
            'registration_throttle_enabled',
            'honeypot_enabled',
            'privacy_policy_url',
            'terms_url',
            'privacy_notice_text',
            'registration_require_consent',
            'email_config',
            'languages',
            'translations_override',
            'sidebar_config',
            'sidebar_show_notification_badges',
            'sidebar_toggle_icon',
            'navbar_config',
            'log_config',
            'profile_config',
            'backup_config',
            'titlebar_config',
            'search_config',
            'notification_config',
            'login_config',
        ]




    def __init__(self, *args, request=None, user=None, mode='modal', **kwargs):
        self.request = request if request is not None else kwargs.pop('request', None)
        self._user = user if user is not None else kwargs.pop('user', None)
        self.mode = mode if mode is not None else kwargs.pop('mode', 'modal')
        super().__init__(*args, **kwargs)
        extra_config = getattr(self.instance, 'extra_config', None) or {}
        scanlink_config = extra_config.get('scanlink') if isinstance(extra_config, dict) else None
        self.initial.setdefault(
            'scanlink_enabled',
            bool(scanlink_config.get('enabled', False)) if isinstance(scanlink_config, dict) else False,
        )
        self.fields['allowed_fonts'].choices = get_font_choices()
        # A bound (POST) settings save must source its data from the AUTHORITATIVE
        # DB row. Views hand this form ``SystemSettings.load()`` (the cached
        # singleton), and single-step saves re-serialise the WHOLE config while
        # preserving non-edited fields from ``self.instance`` (see the
        # ``clean_*`` preservers below). If that instance is a stale cache, the
        # save writes stale values back to the DB permanently — the reported bug
        # where saving one step (e.g. the public theme) silently reverts
        # ``default_theme`` to 'light'. Refresh from the DB before any
        # clean/preserve or initial-building reads ``self.instance``.
        if self.is_bound and self.mode != 'setup' and getattr(self.instance, 'pk', None):
            try:
                self.instance.refresh_from_db()
            except Exception:
                logger.warning("SystemSettingsForm: could not refresh instance from DB before save.", exc_info=True)
        self.refresh_parent = True
        self.extra_form_class = 'dlux-system-setup-form'
        # Closing this modal with pending edits prompts before discarding.
        self.dlux_unsaved_guard = True
        self.single_step_mode = False
        self.single_step_index = None
        s = get_strings()
        if hasattr(self, 'translations') and self.translations:
            s = self.translations

        if self.mode != 'setup' and self.request is not None:
            raw_step = self.request.GET.get('step')
            try:
                parsed_step = int(raw_step)
            except (TypeError, ValueError):
                parsed_step = None
            if parsed_step in range(SETUP_STEP_COUNT):
                self.single_step_mode = True
                self.single_step_index = parsed_step
        if self.mode != 'setup' and self.single_step_mode:
            # Single-step modal posts can legitimately omit values owned by
            # another wizard step; field-level required validation must not fire
            # before the step-preservation cleaners get a chance to restore them.
            self.fields['default_theme'].required = False
            self.fields['default_table_density'].required = False

        from dlux.discovery import (
            discover_routes_for,
            discover_sidebar_catalog,
            sanitize_navbar_config,
            sanitize_sidebar_config,
        )
        from dlux.system.constants import DISCOVERY_PROFILE_LANDING, DISCOVERY_PROFILE_NAVBAR
        from dlux.utils import get_system_config

        config = get_system_config()
        current_languages = normalize_language_catalog(config.get('languages', {}))
        if isinstance(getattr(self.instance, 'languages', None), dict):
            current_languages = normalize_language_catalog(current_languages, self.instance.languages)
        discovered_theme_choices = [(value, value) for value, _, _ in get_theme_choices()]
        self.fields['default_theme'].choices = discovered_theme_choices
        self.fields['allowed_themes'].choices = discovered_theme_choices

        self.fields['system_names'].label = s.get('form_sys_system_names', "System names")
        self.fields['settings_import_file'].label = s.get('form_sys_import_config', "Import system setup file")
        self.fields['settings_import_file'].help_text = s.get(
            'help_sys_import_config',
            'Optional: choose a Dlux-exported JSON setup file to populate these settings.',
        )
        self.fields['settings_import_file'].widget = _build_archive_file_widget(
            attrs={
                'accept': 'application/json,.json',
                'data-settings-import-file': 'true',
            },
            field_label=self.fields['settings_import_file'].label,
        )
        self.fields['languages'].label = s.get('form_sys_languages', "Available languages")
        self.fields['translations_override'].label = s.get('form_sys_translations', "Translation overrides")
        self.fields['home_url'].required = False
        self.fields['home_url'].label = s.get('form_sys_home_url', "Home URL")
        self.fields['home_url'].help_text = s.get(
            'help_sys_home_url',
            'Choose the main Home URL. It remains the authenticated home destination and login redirect even when anonymous public-root traffic is split elsewhere.',
        )
        self.fields['home_url'].widget.attrs.update({
            'class': 'form-control glass-input',
            'dir': 'ltr',
            'placeholder': DEFAULT_HOME_URL,
        })
        self.fields['home_url_discovered'].label = s.get('form_sys_home_url_discovered', "Select from discovered pages")
        self.fields['home_url_discovered'].help_text = s.get(
            'help_sys_home_url_discovered',
            'Optional: select a discovered page to auto-fill the Home URL, or leave it blank and enter a custom URL.',
        )
        self.fields['home_url_discovered'].widget.attrs.update({
            'class': 'form-select glass-input',
        })
        self.fields['public_root_url'].required = False
        self.fields['public_root_url'].label = s.get('form_sys_public_root_url', 'Anonymous Public Root URL')
        self.fields['public_root_url'].help_text = s.get(
            'help_sys_public_root_url',
            'Optional: when separate public-root mode is enabled, anonymous users landing on `/` are redirected here instead of the main Home URL.',
        )
        self.fields['public_root_url'].widget.attrs.update({
            'class': 'form-control glass-input',
            'dir': 'ltr',
            'placeholder': '/',
        })
        self.fields['public_root_url_discovered'].label = s.get(
            'form_sys_public_root_url_discovered',
            'Choose anonymous public root from discovered pages',
        )
        self.fields['public_root_url_discovered'].help_text = s.get(
            'help_sys_public_root_url_discovered',
            'Optional: select a discovered page to auto-fill the anonymous public-root destination, or leave it blank and enter a custom URL.',
        )
        self.fields['public_root_url_discovered'].widget.attrs.update({
            'class': 'form-select glass-input',
        })
        self.fields['public_root_theme'].choices = (
            ('', s.get('form_sys_public_root_theme_default', 'Use system default theme')),
            *[(theme['slug'], theme['label']) for theme in get_theme_options(s, config.get('allowed_themes'))],
        )
        self.fields['public_root_theme'].label = s.get('form_sys_public_root_theme', 'Public root theme')
        self.fields['public_root_theme'].help_text = s.get(
            'help_sys_public_root_theme',
            'Theme applied to the public root for anonymous visitors. Leave on the system default to inherit the normal theme.',
        )
        self.fields['public_root_title'].label = s.get('form_sys_public_root_title', 'Public root page title')
        self.fields['public_root_title'].help_text = s.get(
            'help_sys_public_root_title',
            'Optional browser/tab title shown to anonymous visitors on the public root. Leave blank to use the system name.',
        )
        self.fields['public_root_meta_description'].label = s.get(
            'form_sys_public_root_meta_description', 'Public root meta description'
        )
        self.fields['public_root_meta_description'].help_text = s.get(
            'help_sys_public_root_meta_description',
            'Optional meta description tag emitted on the public root for search engines and link previews.',
        )
        self.fields['show_titlebar_on_public'].label = s.get(
            'form_sys_show_titlebar_on_public', 'Show titlebar on public root'
        )
        self.fields['show_titlebar_on_public'].help_text = s.get(
            'help_sys_show_titlebar_on_public',
            'Show the titlebar to anonymous visitors on the public root. Hidden by default.',
        )
        self.fields['show_sidebar_on_public'].label = s.get(
            'form_sys_show_sidebar_on_public', 'Show sidebar on public root'
        )
        self.fields['show_sidebar_on_public'].help_text = s.get(
            'help_sys_show_sidebar_on_public',
            'Show the sidebar to anonymous visitors on the public root. Hidden by default.',
        )
        self.fields['default_language'].label = s.get('form_sys_default_lang', "Default Language")
        self.fields['default_theme'].label = s.get('form_sys_default_theme', "Default Theme")
        self.fields['allowed_themes'].label = s.get('form_sys_allowed_themes', 'Allowed themes')
        self.fields['allowed_themes'].help_text = s.get(
            'help_sys_allowed_themes',
            'Choose which themes are available in this project. The default theme must remain enabled.',
        )
        self.fields['theme_picker_location'].label = s.get(
            'form_sys_theme_picker_location', 'Theme picker location')
        self.fields['theme_picker_location'].help_text = s.get(
            'help_sys_theme_picker_location',
            'Where users switch theme. The Options page always keeps a themes card unless the '
            'sidebar toolbar already offers a direct two-theme toggle.',
        )
        self.fields['theme_picker_location'].choices = (
            (DEFAULT_THEME_PICKER_LOCATION, s.get('theme_picker_location_sidebar', 'Sidebar toolbar')),
            ('titlebar', s.get('theme_picker_location_titlebar', 'Titlebar action')),
            ('disabled', s.get('theme_picker_location_disabled', 'Options only')),
        )
        _bind_choice_selector_widget(
            self.fields['theme_picker_location'],
            DluxChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    DEFAULT_THEME_PICKER_LOCATION: {
                        'icon': 'bi-layout-sidebar-inset',
                        'description': s.get(
                            'theme_picker_location_sidebar_desc',
                            'In the sidebar toolbar, next to density and reorder.',
                        ),
                    },
                    'titlebar': {
                        'icon': 'bi-window-sidebar',
                        'description': s.get(
                            'theme_picker_location_titlebar_desc',
                            'A titlebar action, beside the language switcher.',
                        ),
                    },
                    'disabled': {
                        'icon': 'bi-slash-circle',
                        'description': s.get(
                            'theme_picker_location_disabled_desc',
                            'Nowhere in the chrome — the Options page only.',
                        ),
                    },
                },
            ),
        )
        self.fields['allow_user_theme_override'].label = s.get('form_sys_allow_user_theme_override', 'Allow user theme override')
        self.fields['allow_user_theme_override'].help_text = s.get(
            'help_sys_allow_user_theme_override',
            'Allow users to switch between the allowed themes at runtime from Options and the sidebar toolbar.',
        )
        self.fields['allow_user_language_override'].label = s.get('form_sys_allow_user_language_override', 'Allow user language override')
        self.fields['allow_user_language_override'].help_text = s.get(
            'help_sys_allow_user_language_override',
            'Allow users to change their display language from Options. When disabled, the system default language is enforced.',
        )
        self.fields['allow_user_home_url'].label = s.get('profile_allow_user_home_url', 'Allow users to set their landing page')
        self.fields['allow_user_home_url'].help_text = s.get(
            'help_sys_allow_user_home_url',
            'Let each user choose their own landing page (from Options) instead of always using the system Home URL above.',
        )
        self.fields['allowed_fonts'].label = s.get('form_sys_allowed_fonts', 'Allowed fonts')
        self.fields['allowed_fonts'].help_text = s.get(
            'help_sys_allowed_fonts',
            'Choose which fonts are available in this project. The default fonts for each language must remain enabled.',
        )
        self.fields['allow_user_font_override'].label = s.get('form_sys_allow_user_font_override', 'Allow user font override')
        self.fields['allow_user_font_override'].help_text = s.get(
            'help_sys_allow_user_font_override',
            'Allow users to switch between the allowed fonts at runtime from Options.',
        )
        self.fields['default_fonts'].label = s.get('form_sys_default_fonts', 'Default fonts by language')
        self.fields['default_table_density'].label = s.get('form_sys_default_table_density', "Default Table Density")
        self.fields['default_table_density'].help_text = s.get(
            'help_sys_default_table_density',
            'Choose the default table density for new users; each user can still override it later from Options.',
        )
        self.fields['default_table_density'].choices = (
            ('dense', s.get('table_density_dense', 'Dense')),
            (DEFAULT_TABLE_DENSITY, s.get('table_density_balanced', 'Balanced')),
            ('roomy', s.get('table_density_roomy', 'Roomy')),
        )
        self.fields['default_form_density'].label = s.get('form_sys_default_form_density', "Default Form Density")
        self.fields['default_form_density'].help_text = s.get(
            'help_sys_default_form_density',
            'Spacing of form fields in dynamic modals and pages, independent of table density.',
        )
        self.fields['default_form_density'].choices = (
            ('dense', s.get('table_density_dense', 'Dense')),
            (DEFAULT_FORM_DENSITY, s.get('table_density_balanced', 'Balanced')),
            ('roomy', s.get('table_density_roomy', 'Roomy')),
        )
        self.fields['default_modal_size'].label = s.get('form_sys_default_modal_size', "Default Modal Size")
        self.fields['default_modal_size'].help_text = s.get(
            'help_sys_default_modal_size',
            'Default width of the dynamic modal: compact, standard, or wide.',
        )
        self.fields['default_modal_size'].choices = (
            ('compact', s.get('modal_size_compact', 'Compact')),
            (DEFAULT_MODAL_SIZE, s.get('modal_size_standard', 'Standard')),
            ('wide', s.get('modal_size_wide', 'Wide')),
        )
        self.fields['options_style'].label = s.get('form_sys_options_style', 'Options page style')
        self.fields['options_style'].help_text = s.get(
            'help_sys_options_style',
            'How the Options page is laid out: rearrangeable cards, a tabbed view, or a dense single-page compact view.',
        )
        self.fields['options_style'].choices = (
            ('cards', s.get('options_style_cards', 'Cards')),
            ('tabs', s.get('options_style_tabs', 'Tabs')),
            ('compact', s.get('options_style_compact', 'Compact')),
        )
        self.fields['row_actions_style'].label = s.get('form_sys_row_actions_style', 'Table row actions')
        self.fields['row_actions_style'].help_text = s.get(
            'help_sys_row_actions_style',
            'How row actions are triggered in tables: a right-click / long-press context menu, a dedicated three-dot actions column, or both.',
        )
        self.fields['row_actions_style'].choices = (
            (DEFAULT_ROW_ACTIONS_STYLE, s.get('row_actions_context', 'Context menu')),
            ('column', s.get('row_actions_column', 'Actions column')),
            ('both', s.get('row_actions_both', 'Both')),
        )
        self.fields['sticky_table_headers'].label = s.get('form_sys_sticky_table_headers', 'Sticky table headers')
        self.fields['sticky_table_headers'].help_text = s.get(
            'help_sys_sticky_table_headers',
            'Keep table header rows pinned to the top while scrolling long tables.',
        )
        self.fields['resizable_table_columns'].label = s.get('form_sys_resizable_table_columns', 'Resizable table columns')
        self.fields['resizable_table_columns'].help_text = s.get(
            'help_sys_resizable_table_columns',
            'Let users drag table header edges to resize columns in Dlux data tables.',
        )
        self.fields['zebra_striping'].label = s.get('form_sys_zebra_striping', 'Zebra striping')
        self.fields['zebra_striping'].help_text = s.get(
            'help_sys_zebra_striping',
            'Alternate row background shading in tables for easier scanning.',
        )
        self.fields['show_audit_fields'].label = s.get('form_sys_show_audit_fields', 'Show audit fields')
        self.fields['show_audit_fields'].help_text = s.get(
            'help_sys_show_audit_fields',
            'Show created/updated by and at columns in tables and detail views. Only users with the "view audit fields" permission see them.',
        )
        self.fields['show_soft_deleted'].label = s.get('form_sys_show_soft_deleted', 'Show soft-deleted entries')
        self.fields['show_soft_deleted'].help_text = s.get(
            'help_sys_show_soft_deleted',
            'List entries that were soft-deleted (a deletion timestamp is set). Superadmins only.',
        )
        self.fields['footer_text'].label = s.get('form_sys_footer_text', "Footer text")
        self.fields['footer_text'].help_text = s.get(
            'help_sys_footer_text',
            'Optional copyright or short note shown in the faint footer at the bottom of every page. Leave blank to show the default "© year · system name" line.',
        )
        self.fields['footer_text'].widget.attrs.setdefault(
            'placeholder',
            s.get('form_sys_footer_text_placeholder', '© 2026 Your Organization · All rights reserved'),
        )
        self.fields['footer_enabled'].label = s.get('form_sys_footer_enabled', 'Show page footer')
        self.fields['footer_enabled'].help_text = s.get(
            'help_sys_footer_enabled',
            'Show the faint footer strip at the bottom of every page. Turn off to remove it entirely.',
        )
        self.fields['footer_link_text'].label = s.get('form_sys_footer_link_text', 'Footer link text')
        self.fields['footer_link_text'].help_text = s.get(
            'help_sys_footer_link_text',
            'Optional label for a link shown after the footer text. Falls back to the URL if left blank.',
        )
        self.fields['footer_link_url'].label = s.get('form_sys_footer_link_url', 'Footer link URL')
        self.fields['footer_link_url'].help_text = s.get(
            'help_sys_footer_link_url',
            'Optional link beside the footer text (http(s)://, mailto:, or a /relative path). Left blank or invalid — no link is shown.',
        )
        self.fields['footer_link_url'].widget.attrs.setdefault(
            'placeholder',
            s.get('form_sys_footer_link_url_placeholder', 'https://example.com'),
        )
        self.fields['logo'].label = s.get('form_sys_logo', "System Logo (Logo)")
        self.fields['favicon'].label = s.get('form_sys_favicon', "Site Icon (Favicon)")
        self.fields['login_logo'].label = s.get('form_sys_login_logo', 'Login Logo')
        self.fields['login_background'].label = s.get('form_sys_login_background', 'Login Background')
        for asset_field_name in ('logo', 'favicon', 'login_logo', 'login_background'):
            self.fields[asset_field_name].widget.field_label = self.fields[asset_field_name].label
        try:
            Asset = apps.get_model('dlux', 'ManagedAsset')
            image_assets = list(Asset.objects.filter(kind='image', is_active=True).order_by('title', 'pk'))
        except Exception:
            image_assets = None
        if image_assets is not None:
            for asset_field_name in ('logo', 'favicon', 'login_logo', 'login_background'):
                self.fields[asset_field_name].widget.set_asset_choices(image_assets)
        self.fields['logo'].help_text = s.get('help_sys_logo_asset', 'Choose a reusable image or upload a new system logo.')
        self.fields['favicon'].help_text = s.get('help_sys_favicon_asset', 'Choose a reusable image or upload a new site icon.')
        self.fields['login_logo'].help_text = s.get('help_sys_login_logo', 'Choose a separate reusable logo for public authentication screens. Leave empty to use the system logo.')
        self.fields['login_background'].help_text = s.get('help_sys_login_background', 'Choose a reusable image for the public authentication background.')
        self.initial['logo'] = getattr(self.instance, 'logo_asset', None)
        self.initial['favicon'] = getattr(self.instance, 'favicon_asset', None)
        self.initial['login_logo'] = getattr(self.instance, 'login_logo_asset', None)
        self.initial['login_background'] = getattr(self.instance, 'login_background_asset', None)
        for field_name, legacy_name in (('logo', 'logo'), ('favicon', 'favicon')):
            if self.initial.get(field_name):
                continue
            legacy_file = getattr(self.instance, legacy_name, None)
            if not legacy_file:
                continue
            try:
                if legacy_file.storage.exists(legacy_file.name):
                    self.fields[field_name].widget.legacy_url = legacy_file.url
                    self.fields[field_name].widget.legacy_name = Path(legacy_file.name).name
            except Exception:
                pass
        self.fields['sidebar_config'].label = s.get('form_sys_sidebar', "Sidebar Configuration")
        self.fields['sidebar_enabled'].label = s.get('form_sys_sidebar_enabled', 'Enable sidebar')
        self.fields['sidebar_enabled'].help_text = s.get(
            'help_sys_sidebar_enabled',
            'Show the runtime sidebar. When disabled, content expands and sidebar toolbar controls are ignored.',
        )
        self.fields['sidebar_enable_reorder'].label = s.get('form_sys_sidebar_enable_reorder', 'Enable sidebar reorder')
        self.fields['sidebar_enable_reorder'].help_text = s.get(
            'help_sys_sidebar_enable_reorder',
            'Show the quick reorder control in the sidebar toolbar so users can rearrange sidebar items from the UI.',
        )
        self.fields['sidebar_enable_toolbar'].label = s.get('form_sys_sidebar_enable_toolbar', 'Enable sidebar toolbar')
        self.fields['sidebar_enable_toolbar'].help_text = s.get(
            'help_sys_sidebar_enable_toolbar',
            'Show the sidebar toolbar that contains the quick theme picker, reorder toggle, and dynamic section manager shortcut.',
        )
        self.fields['sidebar_show_icons'].label = s.get('form_sys_sidebar_show_icons', 'Show sidebar icons')
        self.fields['sidebar_show_icons'].help_text = s.get(
            'help_sys_sidebar_show_icons',
            'Show icons beside sidebar items and folders in the expanded sidebar.',
        )
        self.fields['sidebar_show_notification_badges'].label = s.get(
            'form_sys_sidebar_show_notification_badges',
            'Show notification badges in sidebar',
        )
        self.fields['sidebar_show_notification_badges'].help_text = s.get(
            'help_sys_sidebar_show_notification_badges',
            'Show unread notification counters beside model-backed sidebar sections and their groups.',
        )
        self.fields['sidebar_density'].label = s.get('form_sys_sidebar_density', 'Sidebar density')
        self.fields['sidebar_density'].help_text = s.get(
            'help_sys_sidebar_density',
            'Choose the default row density for the sidebar.',
        )
        self.fields['sidebar_density'].choices = (
            ('dense', s.get('table_density_dense', 'Dense')),
            (DEFAULT_SIDEBAR_DENSITY, s.get('table_density_balanced', 'Balanced')),
            ('roomy', s.get('table_density_roomy', 'Roomy')),
        )
        self.fields['sidebar_allow_user_density'].label = s.get('form_sys_sidebar_allow_user_density', 'Allow user sidebar density override')
        self.fields['sidebar_allow_user_density'].help_text = s.get(
            'help_sys_sidebar_allow_user_density',
            'Allow users to change sidebar density from the sidebar toolbar at runtime.',
        )
        self.fields['sidebar_collapse_mode'].label = s.get('form_sys_sidebar_collapse_mode', 'Desktop collapse mode')
        self.fields['sidebar_collapse_mode'].help_text = s.get(
            'help_sys_sidebar_collapse_mode',
            'Choose how the sidebar behaves when collapsed on large screens.',
        )
        self.fields['sidebar_collapse_mode'].choices = (
            ('icons', s.get('sidebar_collapse_icons', 'Icons only')),
            ('hidden', s.get('sidebar_collapse_hidden', 'Hide completely')),
            ('locked_expanded', s.get('sidebar_collapse_locked_expanded', 'Always expanded')),
        )
        self.fields['sidebar_toggle_icon'].label = s.get('form_sys_sidebar_toggle_icon', 'Sidebar toggle icon')
        self.fields['sidebar_toggle_icon'].help_text = s.get(
            'help_sys_sidebar_toggle_icon',
            'Choose the icon shown on the titlebar button that opens and closes the sidebar.',
        )
        self.fields['navbar_config'].label = s.get('form_sys_navbar', '')
        self.fields['log_config'].label = s.get('form_sys_log', 'Logging Configuration')
        self.fields['profile_config'].label = s.get('form_sys_profile', 'Profile Page Configuration')
        self.fields['backup_config'].label = s.get('form_sys_backup', 'Backup Configuration')
        self.fields['scanlink_enabled'].label = s.get('form_sys_scanlink_enabled', 'Enable ScanLink scanning')
        self.fields['scanlink_enabled'].help_text = s.get('help_sys_scanlink_enabled', 'Adds a Scan button to file fields, driven by the ScanLink helper installed on each operator workstation. Leave this off where the helper is not installed: the browser logs a failed connection for every scan attempt.')
        self.fields['backup_scheduled_enabled'].label = s.get('form_sys_backup_scheduled_enabled', 'Enable scheduled backups')
        self.fields['backup_scheduled_enabled'].help_text = s.get('help_sys_backup_scheduled_enabled', 'Create full encrypted system backups automatically through Celery beat.')
        self.fields['backup_schedule_interval_hours'].label = s.get('form_sys_backup_schedule_interval_hours', 'Backup interval (hours)')
        self.fields['backup_schedule_interval_hours'].help_text = s.get('help_sys_backup_schedule_interval_hours', 'How often a scheduled backup becomes due. The scheduler checks every 15 minutes.')
        self.fields['backup_retention_days'].label = s.get('form_sys_backup_retention_days', 'Retention age (days)')
        self.fields['backup_retention_days'].help_text = s.get('help_sys_backup_retention_days', 'Delete completed backups older than this many days. Use 0 to keep them indefinitely.')
        self.fields['backup_max_backups_to_keep'].label = s.get('form_sys_backup_max_backups_to_keep', 'Maximum backups to keep')
        self.fields['backup_max_backups_to_keep'].help_text = s.get('help_sys_backup_max_backups_to_keep', 'Keep only the newest completed backups after each successful backup. Use 0 for no count limit.')
        self.fields['backup_auto_export_target'].label = s.get('form_sys_backup_auto_export_target', 'Automatic export target')
        self.fields['backup_auto_export_target'].help_text = s.get('help_sys_backup_auto_export_target', 'Storage-relative folder in Django default storage, for example dlux_backups or protected/dlux.')
        self.fields['backup_stall_timeout_minutes'].label = s.get('form_sys_backup_stall_timeout_minutes', 'Stall timeout (minutes)')
        self.fields['backup_stall_timeout_minutes'].help_text = s.get('help_sys_backup_stall_timeout_minutes', 'A running backup that reports no progress for this long is treated as dead and marked failed, so an interrupted worker cannot leave it running forever.')
        self.fields['backup_auto_retry_enabled'].label = s.get('form_sys_backup_auto_retry_enabled', 'Retry failed backups automatically')
        self.fields['backup_auto_retry_enabled'].help_text = s.get('help_sys_backup_auto_retry_enabled', 'Re-run a failed or stalled backup by itself. Backups protected by a passphrase are never retried automatically because the passphrase is never stored; resume those from the Backup & Restore page.')
        self.fields['backup_max_attempts'].label = s.get('form_sys_backup_max_attempts', 'Maximum attempts')
        self.fields['backup_max_attempts'].help_text = s.get('help_sys_backup_max_attempts', 'Total attempts per backup, counting the first one. Use 1 to disable retrying.')
        self.fields['backup_retry_delay_minutes'].label = s.get('form_sys_backup_retry_delay_minutes', 'Retry delay (minutes)')
        self.fields['backup_retry_delay_minutes'].help_text = s.get('help_sys_backup_retry_delay_minutes', 'How long to wait after a failure before the next automatic attempt starts.')
        self.fields['navbar_enabled'].label = s.get('form_sys_navbar_enabled', '')
        self.fields['navbar_enabled'].help_text = s.get('help_sys_navbar_enabled', '')
        self.fields['navbar_default_mode'].label = s.get('form_sys_navbar_default_mode', '')
        self.fields['navbar_default_mode'].help_text = s.get('help_sys_navbar_default_mode', '')
        self.fields['navbar_default_mode'].choices = (
            ('hierarchy', s.get('navbar_mode_hierarchy', '')),
            ('history', s.get('navbar_mode_history', '')),
        )
        self.fields['navbar_allow_user_mode_override'].label = s.get(
            'form_sys_navbar_allow_user_mode_override',
            '',
        )
        self.fields['navbar_allow_user_mode_override'].help_text = s.get(
            'help_sys_navbar_allow_user_mode_override',
            '',
        )
        self.fields['titlebar_show_title'].label = s.get('form_sys_titlebar_show_title', 'Show titlebar title')
        self.fields['titlebar_show_logo'].label = s.get('form_sys_titlebar_show_logo', 'Show titlebar logo')
        self.fields['titlebar_show_home_button'].label = s.get('form_sys_titlebar_show_home_button', 'Show titlebar home button')
        self.fields['titlebar_home_shape'].label = s.get('form_sys_titlebar_home_shape', 'Titlebar buttons shape')
        self.fields['titlebar_user_hub_style'].label = s.get('form_sys_titlebar_user_hub_style', 'Titlebar and user hub style')
        self.fields['titlebar_show_language_switcher'].label = s.get(
            'form_sys_titlebar_show_language_switcher', 'Show titlebar language switcher')
        language_override_allowed = bool(config.get('allow_user_language_override', True))
        multiple_languages_available = len(current_languages) > 1
        language_switching_possible = language_override_allowed and multiple_languages_available
        if language_switching_possible:
            self.fields['titlebar_show_language_switcher'].help_text = s.get(
                'help_sys_titlebar_show_language_switcher',
                'Show a single-button switcher in the titlebar that cycles through the available languages.')
        else:
            if not multiple_languages_available and not language_override_allowed:
                lock_reason = s.get(
                    'help_sys_titlebar_show_language_switcher_unavailable',
                    'Add a second active language and allow users to change their display language to enable the titlebar language switcher.',
                )
            elif not multiple_languages_available:
                lock_reason = s.get(
                    'help_sys_titlebar_show_language_switcher_requires_languages',
                    'Add at least two active languages to enable the titlebar language switcher.',
                )
            else:
                lock_reason = s.get(
                    'help_sys_titlebar_show_language_switcher_requires_override',
                    'Allow users to change their display language to enable the titlebar language switcher.',
                )
            self.fields['titlebar_show_language_switcher'].disabled = True
            self.fields['titlebar_show_language_switcher'].help_text = lock_reason
            self.fields['titlebar_show_language_switcher'].dlux_lock_reason = lock_reason
        self.fields['titlebar_actions_order'].label = s.get('form_sys_titlebar_actions_order', 'Titlebar action order')
        self.fields['titlebar_title_align'].label = s.get('form_sys_titlebar_title_align', 'Title alignment')
        self.fields['titlebar_title_size'].label = s.get('form_sys_titlebar_title_size', 'Title size')
        self.fields['titlebar_height'].label = s.get('form_sys_titlebar_height', 'Titlebar height')
        self.fields['titlebar_surface'].label = s.get('form_sys_titlebar_surface', 'Titlebar surface')
        self.fields['titlebar_logo_treatment'].label = s.get('form_sys_titlebar_logo_treatment', 'Logo treatment')
        self.fields['titlebar_logo_treatment_shape'].label = s.get(
            'form_sys_titlebar_logo_treatment_shape',
            'Logo treatment shape',
        )
        self.fields['titlebar_global_search_mode'].label = s.get('form_sys_titlebar_global_search', 'Global search')
        self.fields['titlebar_global_search_mode'].help_text = s.get(
            'help_sys_titlebar_global_search',
            'Show a search box in the titlebar to jump to pages, settings, and actions from anywhere.',
        )
        self.fields['titlebar_global_search_mode'].choices = (
            ('always', s.get('global_search_mode_always', 'Always visible')),
            ('icon', s.get('global_search_mode_icon', 'Icon, expand on focus')),
            ('disabled', s.get('global_search_mode_disabled', 'Disabled')),
        )
        self.fields['titlebar_global_search_include_data'].label = s.get(
            'form_sys_titlebar_global_search_include_data', 'Include data records in search')
        self.fields['titlebar_global_search_include_data'].help_text = s.get(
            'help_sys_titlebar_global_search_include_data',
            'When on, global search also matches records the user can view, not just app components (pages, settings, actions).',
        )
        self.fields['titlebar_show_title'].help_text = s.get(
            'help_sys_titlebar_show_title',
            'Show the system title in the titlebar.',
        )
        self.fields['titlebar_show_logo'].help_text = s.get(
            'help_sys_titlebar_show_logo',
            'Show the configured branding logo beside the title.',
        )
        self.fields['titlebar_show_home_button'].help_text = s.get(
            'help_sys_titlebar_show_home_button',
            'Show the quick Home button in the titlebar.',
        )
        self.fields['titlebar_logo_treatment'].help_text = s.get(
            'help_sys_titlebar_logo_treatment',
            'Choose how Dlux visually assists the logo on mixed theme surfaces.',
        )
        self.fields['titlebar_logo_treatment_shape'].help_text = s.get(
            'help_sys_titlebar_logo_treatment_shape',
            'Choose the plate silhouette when the Plate treatment is active.',
        )
        self.fields['titlebar_user_hub_style'].help_text = s.get(
            'help_sys_titlebar_user_hub_style',
            'Choose whether user shortcuts stay in the user hub dropdown or move into orderable titlebar action buttons.',
        )
        self.fields['titlebar_home_shape'].choices = (
            ('circle', s.get('titlebar_home_shape_circle', 'Circle')),
            ('square', s.get('titlebar_home_shape_square', 'Square')),
            ('squircle', s.get('titlebar_home_shape_squircle', 'Squircle')),
        )
        self.fields['titlebar_user_hub_style'].choices = (
            (TITLEBAR_USER_HUB_STYLE_DROPDOWN, s.get('titlebar_user_hub_style_dropdown', 'Dropdown')),
            (TITLEBAR_USER_HUB_STYLE_ACTIONS, s.get('titlebar_user_hub_style_actions', 'Titlebar Actions')),
        )
        self.fields['titlebar_title_align'].choices = (
            ('start', s.get('titlebar_align_start', 'Start')),
            ('center', s.get('titlebar_align_center', 'Center')),
            ('end', s.get('titlebar_align_end', 'End')),
        )
        self.fields['titlebar_title_size'].choices = (
            ('sm', s.get('titlebar_size_sm', 'Small')),
            ('md', s.get('titlebar_size_md', 'Medium')),
            ('lg', s.get('titlebar_size_lg', 'Large')),
        )
        self.fields['titlebar_height'].choices = (
            ('dense', s.get('titlebar_height_dense', 'Dense')),
            ('balanced', s.get('titlebar_height_balanced', 'Balanced')),
            ('roomy', s.get('titlebar_height_roomy', 'Roomy')),
        )
        self.fields['titlebar_surface'].choices = (
            ('default', s.get('titlebar_surface_default', 'Default')),
            ('muted', s.get('titlebar_surface_muted', 'Muted')),
            ('glass', s.get('titlebar_surface_glass', 'Glass')),
        )
        self.fields['titlebar_logo_treatment'].choices = (
            ('none', s.get('titlebar_logo_treatment_none', 'None')),
            ('plate', s.get('titlebar_logo_treatment_plate', 'Plate')),
            ('halo', s.get('titlebar_logo_treatment_halo', 'Halo')),
            ('contrast', s.get('titlebar_logo_treatment_contrast', 'Contrast')),
        )
        self.fields['titlebar_logo_treatment_shape'].choices = (
            ('soft', s.get('titlebar_logo_treatment_shape_soft', 'Soft')),
            ('pill', s.get('titlebar_logo_treatment_shape_pill', 'Pill')),
            ('square', s.get('titlebar_logo_treatment_shape_square', 'Square')),
        )
        self.fields['notification_config'].label = s.get('form_sys_notification_config', 'Notification configuration')
        self.fields['notifications_enabled'].label = s.get('form_sys_notifications_enabled', 'Enable notifications')
        self.fields['notifications_enabled'].help_text = s.get(
            'help_sys_notifications_enabled',
            'Master switch for the entire notification subsystem. When off, flash notices, the titlebar drawer/badge, emails, automatic CRUD notifications, and notify(...) are all suppressed.',
        )
        self.fields['notification_flash_enabled'].label = s.get('form_sys_notification_flash_enabled', 'Show flash notices')
        self.fields['notification_flash_enabled'].help_text = s.get(
            'help_sys_notification_flash_enabled',
            'Show short-lived notices for user-facing events.',
        )
        self.fields['notification_flash_position'].label = s.get('form_sys_notification_flash_position', 'Flash position')
        self.fields['notification_flash_position'].help_text = s.get(
            'help_sys_notification_flash_position',
            'Sets where flash notices appear on the page. Start and end automatically follow the interface direction.',
        )
        self.fields['notification_flash_size'].label = s.get('form_sys_notification_flash_size', 'Flash size')
        self.fields['notification_flash_size'].help_text = s.get(
            'help_sys_notification_flash_size',
            "Controls each flash notice's width and padding: Compact, Balanced, or Prominent.",
        )
        self.fields['notification_flash_text_size'].label = s.get('form_sys_notification_flash_text_size', 'Flash text size')
        self.fields['notification_flash_text_size'].help_text = s.get(
            'help_sys_notification_flash_text_size',
            'Controls the message text size inside flash notices.',
        )
        self.fields['notification_flash_timeout_ms'].label = s.get('form_sys_notification_flash_timeout', 'Flash timeout (ms)')
        self.fields['notification_flash_timeout_ms'].help_text = s.get(
            'help_sys_notification_flash_timeout',
            'Milliseconds before a flash notice closes automatically. Use 0 to keep it visible until dismissed.',
        )
        self.fields['notification_flash_max_visible'].label = s.get('form_sys_notification_flash_max_visible', 'Max visible flash notices')
        self.fields['notification_flash_max_visible'].help_text = s.get(
            'help_sys_notification_flash_max_visible',
            'Maximum number of flash notices rendered together (1-10).',
        )
        self.fields['notification_drawer_enabled'].label = s.get('form_sys_notification_drawer_enabled', 'Enable titlebar notification drawer')
        self.fields['notification_drawer_enabled'].help_text = s.get(
            'help_sys_notification_drawer_enabled',
            'Store user-facing notifications under the titlebar icon for authenticated users.',
        )
        self.fields['notification_badge_enabled'].label = s.get('form_sys_notification_badge_enabled', 'Show unread badge')
        self.fields['notification_bridge_enabled'].label = s.get('form_sys_notification_bridge_enabled', 'Import legacy Django messages')
        self.fields['notification_bridge_enabled'].help_text = s.get(
            'help_sys_notification_bridge_enabled',
            'Drain host-project Django messages into Dlux flash notices when enabled.',
        )
        notification_email_status = get_email_service_status()
        self.notification_email_available = bool(notification_email_status.get('available'))
        notification_email_reason = str(notification_email_status.get('reason') or '').replace('_', ' ')
        self.fields['notification_email_enabled'].label = s.get('form_sys_notification_email_enabled', 'Enable notification email channel')
        self.fields['notification_email_enabled'].help_text = s.get(
            'help_sys_notification_email_enabled',
            'Master gate for notification emails. Requires configured Dlux email delivery; when off, rules and notify(..., email=True) cannot send mail.',
        )
        self.fields['notification_email_default'].label = s.get('form_sys_notification_email_default', 'Email by default')
        self.fields['notification_email_default'].help_text = s.get(
            'help_sys_notification_email_default',
            'After the email channel is allowed, send eligible persisted notifications by email unless a rule or notify(...) call overrides delivery.',
        )
        if not self.notification_email_available:
            unavailable_help = s.get(
                'help_sys_notification_email_unavailable',
                'Disabled until Dlux email delivery is configured.',
            )
            if notification_email_reason:
                unavailable_help = f"{unavailable_help} ({notification_email_reason})"
            self.fields['notification_email_enabled'].help_text = unavailable_help
            self.fields['notification_email_default'].help_text = unavailable_help
            self.fields['notification_email_enabled'].disabled = True
            self.fields['notification_email_default'].disabled = True
        self.fields['notification_auto_crud_enabled'].label = s.get('form_sys_notification_auto_crud', 'Enable automatic ScopedModel CRUD notifications')
        self.fields['notification_auto_crud_enabled'].help_text = s.get(
            'help_sys_notification_auto_crud',
            'Master switch for automatic notifications emitted by ScopedModel create, update, and delete events.',
        )
        self.fields['notification_auto_create'].label = s.get('form_sys_notification_auto_create', 'Automatic create notifications')
        self.fields['notification_auto_create'].help_text = s.get(
            'help_sys_notification_auto_create',
            'When automatic CRUD notifications are enabled, emit notifications for new ScopedModel records.',
        )
        self.fields['notification_auto_update'].label = s.get('form_sys_notification_auto_update', 'Automatic update mode')
        self.fields['notification_auto_update'].help_text = s.get(
            'help_sys_notification_auto_update',
            'Off suppresses update notifications; Summary emits quiet changed-field summaries; Full emits update notifications with full metadata.',
        )
        self.fields['notification_auto_delete'].label = s.get('form_sys_notification_auto_delete', 'Automatic delete notifications')
        self.fields['notification_auto_delete'].help_text = s.get(
            'help_sys_notification_auto_delete',
            'When automatic CRUD notifications are enabled, emit notifications for deleted ScopedModel records.',
        )
        self.fields['notification_flash_position'].choices = (
            ('top_center', s.get('notification_position_top_center', 'Top center')),
            ('top_start', s.get('notification_position_top_start', 'Top start')),
            ('top_end', s.get('notification_position_top_end', 'Top end')),
            ('titlebar_end', s.get('notification_position_titlebar_end', 'Titlebar end')),
            ('bottom_start', s.get('notification_position_bottom_start', 'Bottom start')),
            ('bottom_end', s.get('notification_position_bottom_end', 'Bottom end')),
        )
        self.fields['notification_flash_size'].choices = (
            ('compact', s.get('notification_size_compact', 'Compact')),
            ('balanced', s.get('notification_size_balanced', 'Balanced')),
            ('prominent', s.get('notification_size_prominent', 'Prominent')),
        )
        self.fields['notification_flash_text_size'].choices = (
            ('sm', s.get('titlebar_size_sm', 'Small')),
            ('md', s.get('titlebar_size_md', 'Medium')),
            ('lg', s.get('titlebar_size_lg', 'Large')),
        )
        self.fields['notification_auto_update'].choices = (
            ('off', s.get('notification_update_off', 'Off')),
            ('summary', s.get('notification_update_summary', 'Summary')),
            ('full', s.get('notification_update_full', 'Full')),
        )
        for field_name in ('notification_flash_timeout_ms', 'notification_flash_max_visible'):
            self.fields[field_name].widget.attrs.update({'class': 'form-control glass-input'})
        self.fields['login_style'].label = s.get('form_sys_login_style', 'Login Layout Style')
        self.fields['login_style'].help_text = ''
        self.fields['login_style'].choices = (
            ('split', s.get('login_style_split', 'Split (form + banner)')),
            ('centered', s.get('login_style_centered', 'Centered card')),
            ('minimal', s.get('login_style_minimal', 'Floating with background')),
            ('fullpage', s.get('login_style_fullpage', 'Full-page split')),
        )
        self.fields['login_show_logo'].label = s.get('form_sys_login_show_logo', 'Show Logo')
        self.fields['login_show_logo'].help_text = s.get(
            'help_sys_login_show_logo',
            'Show the logo on the login screen. When off, the logo is hidden across all login styles.',
        )
        self.fields['login_banner_color'].label = s.get('form_sys_login_banner_color', 'Banner Colour')
        self.fields['login_banner_color'].help_text = s.get(
            'help_sys_login_banner_color',
            'Optional — enter a CSS colour (hex, rgb, named). Leave empty for the theme default.',
        )
        self.fields['login_logo_treatment'].label = s.get('form_sys_login_logo_treatment', 'Login Logo Treatment')
        self.fields['login_logo_treatment'].help_text = ''
        self.fields['login_logo_treatment'].choices = (
            ('none', s.get('titlebar_logo_treatment_none', 'None')),
            ('plate', s.get('titlebar_logo_treatment_plate', 'Plate')),
            ('halo', s.get('titlebar_logo_treatment_halo', 'Halo')),
            ('contrast', s.get('titlebar_logo_treatment_contrast', 'Contrast')),
        )
        self.fields['login_logo_treatment_shape'].label = s.get('form_sys_login_logo_treatment_shape', 'Treatment Shape')
        self.fields['login_logo_treatment_shape'].choices = (
            ('soft', s.get('titlebar_logo_treatment_shape_soft', 'Soft')),
            ('pill', s.get('titlebar_logo_treatment_shape_pill', 'Pill')),
            ('square', s.get('titlebar_logo_treatment_shape_square', 'Square')),
        )
        initial_login_config = normalize_login_config(
            getattr(self.instance, 'login_config', None) or config.get('login', {})
        )
        initial_hero = initial_login_config.get('hero_message', {})
        if not isinstance(initial_hero, dict):
            initial_hero = {}
        self._login_hero_lang_fields = []
        for lang_code, lang_meta in current_languages.items():
            field_name = f'login_hero_message_{lang_code}'
            lang_label = lang_meta.get('name', lang_code) if isinstance(lang_meta, dict) else str(lang_meta)
            lang_dir = lang_meta.get('dir', 'ltr') if isinstance(lang_meta, dict) else 'ltr'
            placeholder = s.get('login_hero_placeholder', 'Welcome! Sign in to continue.')
            self.fields[field_name] = forms.CharField(
                required=False,
                initial=initial_hero.get(lang_code, ''),
                label=lang_label,
                widget=forms.Textarea(attrs={
                    'rows': 5,
                    'class': 'form-control font-monospace',
                    'dir': lang_dir,
                    'placeholder': placeholder,
                }),
            )
            self._login_hero_lang_fields.append((lang_code, lang_label, field_name))
        _bind_choice_selector_widget(
            self.fields['login_style'],
            DluxChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    'split': {'icon': 'bi-layout-split'},
                    'centered': {'icon': 'bi-credit-card-2-front'},
                    'minimal': {'icon': 'bi-window-fullscreen'},
                    'fullpage': {'icon': 'bi-layout-text-sidebar-reverse'},
                },
            ),
        )
        _bind_choice_selector_widget(
            self.fields['login_logo_treatment'],
            DluxChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    'none': {'icon': 'bi-slash-circle'},
                    'plate': {'icon': 'bi-badge-ad'},
                    'halo': {'icon': 'bi-brightness-high'},
                    'contrast': {'icon': 'bi-circle-half'},
                },
            ),
        )
        _bind_choice_selector_widget(
            self.fields['login_logo_treatment_shape'],
            DluxChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    'soft': {'icon': 'bi-app'},
                    'pill': {'icon': 'bi-capsule'},
                    'square': {'icon': 'bi-square'},
                },
            ),
        )
        self.fields['email_2fa'].label = s.get('form_sys_email_2fa', 'Enable Email 2FA')
        self.fields['email_2fa'].help_text = s.get(
            'help_sys_email_2fa',
            'Allow users to enable two-factor authentication via email. Requires Dlux email delivery to be ready.',
        )
        self.fields['forgot_password_enabled'].label = s.get('form_sys_forgot_password', 'Enable "Forgot password?"')
        self.fields['forgot_password_enabled'].help_text = s.get(
            'help_sys_forgot_password',
            'Show a "Forgot password?" link on the login page and enable the email-based reset flow. Requires Dlux email delivery to be ready.',
        )
        self.fields['prevent_multiple_active_sessions'].label = s.get('form_sys_prevent_multiple_active_sessions')
        self.fields['prevent_multiple_active_sessions'].help_text = s.get('help_sys_prevent_multiple_active_sessions')
        self.fields['login_lockout_enabled'].label = s.get('form_sys_login_lockout', 'Enable Login Lockout')
        self.fields['login_lockout_enabled'].help_text = s.get(
            'help_sys_login_lockout',
            'Temporarily block sign-in after repeated failed password attempts from the same IP or username.',
        )
        self.fields['login_lockout_threshold'].label = s.get('form_sys_login_lockout_threshold', 'Lockout after (attempts)')
        self.fields['login_lockout_threshold'].help_text = s.get(
            'help_sys_login_lockout_threshold',
            'Failed attempts from the same IP or username before sign-in is locked.',
        )
        self.fields['login_lockout_window_minutes'].label = s.get('form_sys_login_lockout_window_minutes', 'Counting window (minutes)')
        self.fields['login_lockout_window_minutes'].help_text = s.get(
            'help_sys_login_lockout_window_minutes',
            'How long failed attempts keep counting toward the threshold.',
        )
        self.fields['login_lockout_duration_minutes'].label = s.get('form_sys_login_lockout_duration_minutes', 'Lockout duration (minutes)')
        self.fields['login_lockout_duration_minutes'].help_text = s.get(
            'help_sys_login_lockout_duration_minutes',
            'How long sign-in stays blocked once the lock is armed.',
        )
        self.fields['enforce_strong_passwords'].label = s.get('form_sys_enforce_strong_passwords', 'Enforce strong passwords')
        self.fields['enforce_strong_passwords'].help_text = s.get(
            'help_sys_enforce_strong_passwords',
            'Require new passwords to meet the configured minimum length with upper and lower case letters, a digit, and a symbol.',
        )
        self.fields['strong_password_min_length'].label = s.get('form_sys_strong_password_min_length', 'Minimum password length')
        self.fields['strong_password_min_length'].help_text = s.get(
            'help_sys_strong_password_min_length',
            'Minimum characters required while strong passwords are enforced (8-64).',
        )
        self.fields['purge_session_on_exit'].label = s.get('form_sys_purge_session_on_exit', 'Sign out on browser close')
        self.fields['purge_session_on_exit'].help_text = s.get(
            'help_sys_purge_session_on_exit',
            'Keep the session only until the browser is fully closed. Closing one tab does not end the browser-wide session.',
        )
        self.fields['inactivity_timeout_enabled'].label = s.get('form_sys_inactivity_timeout', 'Sign out after inactivity')
        self.fields['inactivity_timeout_enabled'].help_text = s.get(
            'help_sys_inactivity_timeout',
            'Automatically sign users out after a period of no activity. A countdown warning appears shortly before sign-out.',
        )
        self.fields['inactivity_timeout_minutes'].label = s.get('form_sys_inactivity_timeout_minutes', 'Inactivity timeout (minutes)')
        self.fields['inactivity_timeout_minutes'].help_text = s.get(
            'help_sys_inactivity_timeout_minutes',
            'Minutes of inactivity before the user is signed out (1-1440).',
        )
        self.fields['client_ip_mode'].label = s.get('form_sys_client_ip_mode')
        self.fields['client_ip_mode'].help_text = s.get('help_sys_client_ip_mode')
        self.fields['client_ip_mode'].choices = (
            (CLIENT_IP_MODE_AUTO, s.get('client_ip_mode_auto', 'Auto-detect')),
            (CLIENT_IP_MODE_X_FORWARDED_FOR, s.get('client_ip_mode_x_forwarded_for')),
            (CLIENT_IP_MODE_REMOTE_ADDR, s.get('client_ip_mode_remote_addr')),
            (CLIENT_IP_MODE_X_REAL_IP, s.get('client_ip_mode_x_real_ip')),
            (CLIENT_IP_MODE_CLOUDFLARE, s.get('client_ip_mode_cloudflare')),
            (CLIENT_IP_MODE_CUSTOM, s.get('client_ip_mode_custom')),
        )
        self.fields['client_ip_mode'].widget.attrs.update({
            'class': 'form-select glass-input',
            'data-client-ip-mode-input': 'true',
        })
        self.fields['client_ip_trusted_proxy_hops'].label = s.get('form_sys_client_ip_hops')
        self.fields['client_ip_trusted_proxy_hops'].help_text = s.get('help_sys_client_ip_hops')
        self.fields['client_ip_trusted_proxy_hops'].widget.attrs.update({
            'class': 'form-control glass-input',
            'min': '0',
            'max': '8',
        })
        self.fields['client_ip_custom_header'].label = s.get('form_sys_client_ip_custom_header')
        self.fields['client_ip_custom_header'].help_text = s.get('help_sys_client_ip_custom_header')
        self.fields['client_ip_custom_header'].widget.attrs.update({
            'class': 'form-control glass-input',
            'placeholder': s.get('client_ip_custom_header_placeholder'),
            'dir': 'ltr',
        })
        self.fields['email_config'].label = s.get('form_sys_email_config', 'Email delivery configuration')
        self.fields['email_config_transport'].label = s.get('form_sys_email_transport', 'Delivery path')
        self.fields['email_config_secret_storage'].label = s.get('form_sys_email_secret_storage', 'Secret storage')
        self.fields['email_config_host'].label = s.get('form_sys_email_host', 'Provider SMTP host')
        self.fields['email_config_port'].label = s.get('form_sys_email_port', 'Provider SMTP port')
        self.fields['email_config_use_tls'].label = s.get('form_sys_email_use_tls', 'Provider STARTTLS')
        self.fields['email_config_use_ssl'].label = s.get('form_sys_email_use_ssl', 'Provider SSL')
        self.fields['email_config_username'].label = s.get('form_sys_email_username', 'Provider SMTP username')
        self.fields['email_config_password'].label = s.get('form_sys_email_password', 'Provider SMTP password')
        self.fields['email_config_default_from_email'].label = s.get('form_sys_email_default_from', 'Default from email')
        self.fields['email_config_provider_preset'].label = s.get('form_sys_email_provider_preset', 'Provider preset')
        self.fields['email_config_provider_preset'].help_text = s.get(
            'help_sys_email_provider_preset',
            'Prefills SMTP host/port/encryption for common providers. Choose Custom to enter values manually.',
        )
        self.fields['email_config_failure_recipients'].label = s.get(
            'form_sys_email_failure_recipients', 'Failure alert recipients'
        )
        self.fields['email_config_failure_recipients'].help_text = s.get(
            'help_sys_email_failure_recipients',
            'Comma or newline separated emails warned in-app when transactional mail fails to send. Requires notifications enabled.',
        )
        self.fields['email_config_timeout'].label = s.get('form_sys_email_timeout', 'SMTP timeout (seconds)')
        self.fields['email_config_timeout'].help_text = s.get(
            'help_sys_email_timeout',
            'How long to wait for the mail server. Leave blank for the default. Raise it if '
            'your server accepts the connection quickly but is slow to accept the message.',
        )
        self.fields['email_config_enabled'].label = s.get('form_sys_email_config_enabled', 'Enable email delivery')
        self.fields['email_config_enabled'].help_text = s.get(
            'help_sys_email_config_enabled',
            'Turn on to configure SMTP. Features that send mail stay locked until a test email succeeds.',
        )
        self.fields['email_config_test_recipient'].label = s.get('form_sys_email_test_recipient', 'Send a test email to')
        self.fields['email_config_test_recipient'].help_text = s.get(
            'help_sys_email_test_recipient',
            'Sends a one-off message using the saved configuration. Save the form before testing.',
        )
        for field_name in (
            'email_config_host',
            'email_config_username',
            'email_config_password',
            'email_config_default_from_email',
            'email_config_failure_recipients',
            'email_config_test_recipient',
            'email_config_enabled',
            'email_config_timeout',
        ):
            self.fields[field_name].widget.attrs.update({'class': 'form-control glass-input'})
        self.fields['email_config_port'].widget.attrs.update({'class': 'form-control glass-input'})
        self.fields['email_config_provider_preset'].widget.attrs.update({
            'class': 'form-select glass-input',
            'data-email-provider-preset': '',
        })
        self.fields['email_config_test_recipient'].widget.attrs.update({
            'data-email-test-recipient': '',
            'class': 'form-control glass-input',
        })
        self.fields['public_root'].label = s.get('form_sys_public_root', 'Public Root Access')
        self.fields['public_root'].help_text = s.get(
            'help_sys_public_root',
            'Allow anonymous (non-logged-in) users to access the root URL (/). When enabled, the system will not force-redirect to login.',
        )
        self.fields['public_root_split_enabled'].label = s.get(
            'form_sys_public_root_split_enabled',
            'Separate anonymous public root from Home URL',
        )
        self.fields['public_root_split_enabled'].help_text = s.get(
            'help_sys_public_root_split_enabled',
            'When enabled, anonymous users can be redirected to a separate Public Root URL while authenticated users still use the main Home URL.',
        )
        email_status = get_email_service_status()
        # Mail-dependent settings are editable only once email is switched on AND a
        # test send has verified it. Django's disabled=True keeps the *stored* value
        # (it ignores POST and falls back to initial), so locking never silently
        # turns off someone's 2FA or password recovery — it only prevents changes.
        self.email_features_unlocked = email_features_unlocked()
        if not self.email_features_unlocked:
            lock_reason = s.get(
                'email_requires_verification_tooltip',
                'Email must be enabled and verified by a successful test email before this feature can be used.',
            )
            for locked_name in EMAIL_DEPENDENT_SETTING_FIELDS:
                locked_field = self.fields.get(locked_name)
                if locked_field is None:
                    continue
                locked_field.disabled = True
                locked_field.dlux_lock_reason = lock_reason
        smtp_label = s.get('form_sys_email_status_ready', 'ready') if email_status.get('available') else s.get('form_sys_email_status_not_ready', 'not ready')
        self.fields['public_registration_enabled'].label = s.get('form_sys_public_registration', 'Enable Public Registration')
        self.fields['public_registration_enabled'].help_text = s.get(
            'help_sys_public_registration',
            'Allow anonymous users to request an account. Email verification is mandatory and SMTP/email delivery must be configured.',
        ) + f" Email service: {smtp_label}."
        self.fields['registration_activation_mode'].label = s.get('form_sys_registration_activation_mode', 'Registration Activation Mode')
        self.fields['registration_activation_mode'].help_text = s.get(
            'help_sys_registration_activation_mode',
            'Choose whether verified users become active immediately or wait for superuser approval.',
        )
        self.fields['registration_throttle_enabled'].label = s.get('form_sys_registration_throttle', 'Enable Registration Throttles')
        self.fields['registration_throttle_enabled'].help_text = s.get(
            'help_sys_registration_throttle',
            'Use cache-based IP/email throttles and resend cooldowns for public registration.',
        )
        self.fields['honeypot_enabled'].label = s.get('form_sys_honeypot_enabled', 'Enable registration honeypot')
        self.fields['honeypot_enabled'].help_text = s.get(
            'help_sys_honeypot_enabled',
            'Add a hidden bot-trap field to the registration form; submissions that fill it are silently dropped. Low-friction anti-bot before CAPTCHA.',
        )
        self.fields['privacy_policy_url'].label = s.get('form_sys_privacy_policy_url', 'Privacy policy URL')
        self.fields['privacy_policy_url'].help_text = s.get(
            'help_sys_privacy_policy_url',
            "Link to your organization's privacy policy. When set, a privacy line is shown on the sign-in and sign-up pages.",
        )
        self.fields['terms_url'].label = s.get('form_sys_terms_url', 'Terms of service URL')
        self.fields['terms_url'].help_text = s.get(
            'help_sys_terms_url',
            'Optional link to your terms of service, shown alongside the privacy policy in the consent line.',
        )
        self.fields['privacy_notice_text'].label = s.get('form_sys_privacy_notice_text', 'Privacy notice text')
        self.fields['privacy_notice_text'].help_text = s.get(
            'help_sys_privacy_notice_text',
            'Optional short notice shown with the privacy link on the auth pages (e.g. what data you collect and why). Leave blank for a default line.',
        )
        self.fields['registration_require_consent'].label = s.get('form_sys_registration_require_consent', 'Require agreement to sign up')
        self.fields['registration_require_consent'].help_text = s.get(
            'help_sys_registration_require_consent',
            'Show a required "I agree to the Terms & Privacy Policy" checkbox on the public sign-up form. Set the policy links above.',
        )
        self.sidebar_sections_manager_available = bool(has_section_models())
        _bind_choice_selector_widget(
            self.fields['default_table_density'],
            DluxChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    'dense': {
                        'icon': 'bi-list',
                        'description': s.get('table_density_dense_desc', 'Fits more rows on screen with tighter spacing.'),
                    },
                    'balanced': {
                        'icon': 'bi-table',
                        'description': s.get('table_density_balanced_desc', 'Comfortable default for everyday admin work.'),
                    },
                    'roomy': {
                        'icon': 'bi-layout-text-window-reverse',
                        'description': s.get('table_density_roomy_desc', 'Uses larger rows and more breathing room.'),
                    },
                },
            ),
        )
        _bind_choice_selector_widget(
            self.fields['default_form_density'],
            DluxChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    'dense': {
                        'icon': 'bi-text-paragraph',
                        'description': s.get('form_density_dense_desc', 'Tighter field spacing to fit more on screen.'),
                    },
                    'balanced': {
                        'icon': 'bi-textarea-resize',
                        'description': s.get('form_density_balanced_desc', 'Comfortable default spacing for form fields.'),
                    },
                    'roomy': {
                        'icon': 'bi-distribute-vertical',
                        'description': s.get('form_density_roomy_desc', 'Larger fields and more breathing room.'),
                    },
                },
            ),
        )
        _bind_choice_selector_widget(
            self.fields['default_modal_size'],
            DluxChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    'compact': {
                        'icon': 'bi-aspect-ratio',
                        'description': s.get('modal_size_compact_desc', 'A narrower dialog for short forms.'),
                    },
                    'standard': {
                        'icon': 'bi-window',
                        'description': s.get('modal_size_standard_desc', 'The default extra-large dialog width.'),
                    },
                    'wide': {
                        'icon': 'bi-arrows-angle-expand',
                        'description': s.get('modal_size_wide_desc', 'An extra-wide dialog for dense content.'),
                    },
                },
            ),
        )
        _bind_choice_selector_widget(
            self.fields['options_style'],
            DluxChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    'cards': {
                        'icon': 'bi-grid-1x2',
                        'description': s.get('options_style_cards_desc', 'Rearrangeable cards in a grid (the default).'),
                    },
                    'tabs': {
                        'icon': 'bi-segmented-nav',
                        'description': s.get('options_style_tabs_desc', 'One section at a time behind tabs.'),
                    },
                    'compact': {
                        'icon': 'bi-list-ul',
                        'description': s.get('options_style_compact_desc', 'A dense single-page list, desktop-app style.'),
                    },
                },
            ),
        )
        _bind_choice_selector_widget(
            self.fields['row_actions_style'],
            DluxChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    'context': {
                        'icon': 'bi-menu-button-wide',
                        'description': s.get('row_actions_context_desc', 'Right-click (or long-press on touch) any row.'),
                    },
                    'column': {
                        'icon': 'bi-three-dots-vertical',
                        'description': s.get('row_actions_column_desc', 'A three-dot menu button in a dedicated last column.'),
                    },
                    'both': {
                        'icon': 'bi-ui-checks',
                        'description': s.get('row_actions_both_desc', 'Both the context menu and the actions column.'),
                    },
                },
            ),
        )
        _bind_choice_selector_widget(
            self.fields['titlebar_global_search_mode'],
            DluxChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    'always': {
                        'icon': 'bi-search',
                        'description': s.get('global_search_mode_always_desc', 'Show the search field in the titlebar at all times.'),
                    },
                    'icon': {
                        'icon': 'bi-search-heart',
                        'description': s.get('global_search_mode_icon_desc', 'Show a search icon that expands into a field on focus.'),
                    },
                    'disabled': {
                        'icon': 'bi-slash-circle',
                        'description': s.get('global_search_mode_disabled_desc', 'Hide global search entirely.'),
                    },
                },
            ),
        )
        # Reuse the theme picker's swatches: render public_root_theme as a swatch
        # selector (same `dlux-theme-preview--<slug>` swatches as the theme picker),
        # limited to the allowed themes, with the optional "use system default" empty choice.
        _bind_choice_selector_widget(
            self.fields['public_root_theme'],
            DluxChoiceSelectorWidget(
                variant='swatch',
                attrs={'class': 'dlux-public-root-theme-picker'},
                option_meta={
                    '': {'icon': 'bi-circle-half'},
                    **{
                        theme['slug']: {
                            'preview_class': 'theme-preview dlux-theme-preview dlux-theme-preview--{}'.format(theme['slug']),
                        }
                        for theme in get_theme_options(s, config.get('allowed_themes'))
                    },
                },
            ),
        )
        _bind_choice_selector_widget(
            self.fields['sidebar_density'],
            DluxChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    'dense': {
                        'icon': 'bi-list-ul',
                        'description': s.get('sidebar_density_dense_desc', 'Tighter rows and spacing for a denser sidebar.'),
                    },
                    'balanced': {
                        'icon': 'bi-layout-sidebar-inset',
                        'description': s.get('sidebar_density_balanced_desc', 'The default balance between density and readability.'),
                    },
                    'roomy': {
                        'icon': 'bi-distribute-vertical',
                        'description': s.get('sidebar_density_roomy_desc', 'Larger row height and spacing for a more relaxed sidebar.'),
                    },
                },
            ),
        )
        _bind_choice_selector_widget(
            self.fields['sidebar_collapse_mode'],
            DluxChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    'icons': {
                        'icon': 'bi-layout-sidebar-inset',
                        'description': s.get('sidebar_collapse_icons_desc', 'Collapse to an icon rail on desktop.'),
                    },
                    'hidden': {
                        'icon': 'bi-eye-slash',
                        'description': s.get('sidebar_collapse_hidden_desc', 'Collapse to a fully hidden desktop sidebar.'),
                    },
                    'locked_expanded': {
                        'icon': 'bi-lock',
                        'description': s.get('sidebar_collapse_locked_expanded_desc', 'Disable desktop collapsing and keep the sidebar open.'),
                    },
                },
            ),
        )
        _bind_choice_selector_widget(
            self.fields['titlebar_home_shape'],
            DluxChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    'circle': {
                        'icon': 'bi-circle',
                        'description': s.get('titlebar_home_shape_circle_desc', 'Round button silhouette.'),
                    },
                    'square': {
                        'icon': 'bi-square',
                        'description': s.get('titlebar_home_shape_square_desc', 'Sharp square edges.'),
                    },
                    'squircle': {
                        'icon': 'bi-app-indicator',
                        'description': s.get('titlebar_home_shape_squircle_desc', 'Soft rounded square edges.'),
                    },
                },
            ),
        )
        _bind_choice_selector_widget(
            self.fields['titlebar_user_hub_style'],
            DluxChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    TITLEBAR_USER_HUB_STYLE_DROPDOWN: {
                        'icon': 'bi-person-lines-fill',
                        'description': s.get(
                            'titlebar_user_hub_style_dropdown_desc',
                            'Keep user shortcuts inside the current user hub dropdown.',
                        ),
                    },
                    TITLEBAR_USER_HUB_STYLE_ACTIONS: {
                        'icon': 'bi-ui-checks-grid',
                        'description': s.get(
                            'titlebar_user_hub_style_actions_desc',
                            'Render user shortcuts as orderable titlebar action buttons.',
                        ),
                    },
                },
            ),
        )
        _bind_choice_selector_widget(
            self.fields['titlebar_title_align'],
            DluxChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    'start': {
                        'icon': 'bi-text-left',
                        'description': s.get('titlebar_align_start_desc', 'Pin the title to the start side.'),
                    },
                    'center': {
                        'icon': 'bi-text-center',
                        'description': s.get('titlebar_align_center_desc', 'Keep the title visually centered.'),
                    },
                    'end': {
                        'icon': 'bi-text-right',
                        'description': s.get('titlebar_align_end_desc', 'Pin the title to the end side.'),
                    },
                },
            ),
        )
        _bind_choice_selector_widget(
            self.fields['titlebar_title_size'],
            DluxChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    'sm': {
                        'surface_label': 'S',
                        'description': s.get('titlebar_size_sm_desc', 'Compact title sizing.'),
                    },
                    'md': {
                        'surface_label': 'M',
                        'description': s.get('titlebar_size_md_desc', 'Balanced default title sizing.'),
                    },
                    'lg': {
                        'surface_label': 'L',
                        'description': s.get('titlebar_size_lg_desc', 'Larger, more prominent title sizing.'),
                    },
                },
            ),
        )
        _bind_choice_selector_widget(
            self.fields['titlebar_height'],
            DluxChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    'dense': {
                        'surface_label': 'D',
                        'description': s.get('titlebar_height_dense_desc', 'Tighter vertical titlebar spacing.'),
                    },
                    'balanced': {
                        'surface_label': 'B',
                        'description': s.get('titlebar_height_balanced_desc', 'Default titlebar spacing.'),
                    },
                    'roomy': {
                        'surface_label': 'R',
                        'description': s.get('titlebar_height_roomy_desc', 'More breathing room inside the titlebar.'),
                    },
                },
            ),
        )
        _bind_choice_selector_widget(
            self.fields['titlebar_surface'],
            DluxChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    'default': {
                        'surface_label': 'Df',
                        'description': s.get('titlebar_surface_default_desc', 'Standard titlebar surface styling.'),
                    },
                    'muted': {
                        'surface_label': 'Mu',
                        'description': s.get('titlebar_surface_muted_desc', 'Lower-contrast titlebar surface.'),
                    },
                    'glass': {
                        'surface_label': 'Gl',
                        'description': s.get('titlebar_surface_glass_desc', 'Blurred glass-style surface effect.'),
                    },
                },
            ),
        )
        _bind_choice_selector_widget(
            self.fields['titlebar_logo_treatment'],
            DluxChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    'none': {
                        'icon': 'bi-slash-circle',
                        'description': s.get('titlebar_logo_treatment_none_desc', 'Leave the logo as uploaded.'),
                    },
                    'plate': {
                        'icon': 'bi-badge-ad',
                        'description': s.get('titlebar_logo_treatment_plate_desc', 'Place the logo on an adaptive material plate.'),
                    },
                    'halo': {
                        'icon': 'bi-brightness-high',
                        'description': s.get('titlebar_logo_treatment_halo_desc', 'Add a subtle adaptive glow behind the logo.'),
                    },
                    'contrast': {
                        'icon': 'bi-circle-half',
                        'description': s.get('titlebar_logo_treatment_contrast_desc', 'Apply contrast and shadow assistance for simple logos.'),
                    },
                },
            ),
        )
        _bind_choice_selector_widget(
            self.fields['titlebar_logo_treatment_shape'],
            DluxChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    'soft': {
                        'icon': 'bi-app',
                        'description': s.get('titlebar_logo_treatment_shape_soft_desc', 'A modern rounded plate.'),
                    },
                    'pill': {
                        'icon': 'bi-capsule',
                        'description': s.get('titlebar_logo_treatment_shape_pill_desc', 'A fully rounded capsule plate.'),
                    },
                    'square': {
                        'icon': 'bi-square',
                        'description': s.get('titlebar_logo_treatment_shape_square_desc', 'A sharper compact plate.'),
                    },
                },
            ),
        )
        _bind_choice_selector_widget(
            self.fields['navbar_default_mode'],
            DluxChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    'hierarchy': {
                        'icon': 'bi-diagram-3',
                        'description': s.get('navbar_mode_hierarchy_desc', ''),
                    },
                    'history': {
                        'icon': 'bi-clock-history',
                        'description': s.get('navbar_mode_history_desc', ''),
                    },
                },
            ),
        )
        project_config = getattr(settings, 'DLUX_CONFIG', {})
        instance_system_names = normalize_system_names(getattr(self.instance, 'system_names', {}))
        if not instance_system_names:
            instance_system_names = normalize_system_names(
                project_config.get('system_names', config.get('system_names', {}))
            )
        self.initial['system_names'] = _json_dump(instance_system_names, ensure_ascii=False)
        if not self.instance.default_language:
             self.instance.default_language = config.get('default_language', 'en')
        self.initial['default_language'] = self.instance.default_language or config.get('default_language', 'en')
        if not getattr(self.instance, 'pk', None) and not getattr(self.instance, 'is_configured', False):
            self.instance.default_theme = config.get('default_theme', 'light')
        elif not getattr(self.instance, 'default_theme', None):
            self.instance.default_theme = config.get('default_theme', 'light')
        self.initial['default_theme'] = self.instance.default_theme or config.get('default_theme', 'light')
        initial_allowed_themes = normalize_allowed_themes(
            (
                config.get('allowed_themes')
                if (not getattr(self.instance, 'pk', None) and not getattr(self.instance, 'is_configured', False))
                else getattr(self.instance, 'allowed_themes', None)
            ) or config.get('allowed_themes')
        )
        self.initial['allowed_themes'] = list(initial_allowed_themes)
        self.dlux_system_preview_counts = {
            'allowed_themes': len(initial_allowed_themes),
            'languages': len(current_languages),
        }
        self.initial['allow_user_theme_override'] = bool(
            config.get('allow_user_theme_override', True)
            if (not getattr(self.instance, 'pk', None) and not getattr(self.instance, 'is_configured', False))
            else getattr(self.instance, 'allow_user_theme_override', config.get('allow_user_theme_override', True))
        )
        self.initial['allow_user_font_override'] = bool(
            config.get('allow_user_font_override', True)
            if (not getattr(self.instance, 'pk', None) and not getattr(self.instance, 'is_configured', False))
            else getattr(self.instance, 'allow_user_font_override', config.get('allow_user_font_override', True))
        )
        initial_allowed_fonts = normalize_allowed_fonts(
            (
                config.get('allowed_fonts')
                if (not getattr(self.instance, 'pk', None) and not getattr(self.instance, 'is_configured', False))
                else getattr(self.instance, 'allowed_fonts', None)
            ) or config.get('allowed_fonts')
        )
        self.initial['allowed_fonts'] = list(initial_allowed_fonts)
        instance_default_fonts = getattr(self.instance, 'default_fonts', {}) or {}
        if not instance_default_fonts:
             instance_default_fonts = config.get('default_fonts', {})
        self.initial['default_fonts'] = _json_dump(instance_default_fonts, ensure_ascii=False)
        self.initial['allow_user_language_override'] = bool(
            config.get('allow_user_language_override', True)
            if (not getattr(self.instance, 'pk', None) and not getattr(self.instance, 'is_configured', False))
            else getattr(self.instance, 'allow_user_language_override', config.get('allow_user_language_override', True))
        )
        if (
            not getattr(self.instance, 'pk', None)
            and not getattr(self.instance, 'is_configured', False)
        ) or getattr(self.instance, 'default_table_density', None) not in TABLE_DENSITY_VALUES:
            self.instance.default_table_density = config.get('default_table_density', DEFAULT_TABLE_DENSITY)
        self.initial['default_table_density'] = self.instance.default_table_density or config.get('default_table_density', DEFAULT_TABLE_DENSITY)
        instance_home_url = str(self.instance.home_url or '').strip()
        if not getattr(self.instance, 'is_configured', False) and instance_home_url == _LEGACY_HOME_URL:
            instance_home_url = ''
        if not getattr(self.instance, 'pk', None) and not getattr(self.instance, 'is_configured', False):
            homepage_source = config.get('homepage_config') or config
        else:
            profile_source = getattr(self.instance, 'profile_config', None) or {}
            legacy_homepage_source = {
                'home_url': instance_home_url,
                **dict(getattr(self.instance, 'public_root_config', None) or {}),
                'allow_user_home_url': profile_source.get('allow_user_home_url', False),
            }
            homepage_source = getattr(self.instance, 'homepage_config', None) or legacy_homepage_source
            if (
                normalize_homepage_config(homepage_source) == default_homepage_config()
                and normalize_homepage_config(legacy_homepage_source) != default_homepage_config()
            ):
                homepage_source = legacy_homepage_source
        initial_homepage_config = normalize_homepage_config(homepage_source)
        self.initial['homepage_config'] = _json_dump(initial_homepage_config, ensure_ascii=False)
        public_homepage = initial_homepage_config['public']
        current_home_url = initial_homepage_config['default_url']
        self.initial['home_url'] = current_home_url
        current_public_root_url = public_homepage['url']
        self.initial['public_root_url'] = current_public_root_url

        if self.instance and self.instance.pk:
            if isinstance(self.instance.languages, dict):
                self.initial['languages'] = _json_dump(self.instance.languages, ensure_ascii=False, indent=2)
            if isinstance(self.instance.translations_override, dict):
                self.initial['translations_override'] = _json_dump(self.instance.translations_override, ensure_ascii=False, indent=2)
        if isinstance(getattr(self.instance, 'sidebar_config', None), dict) and self.instance.sidebar_config:
            sidebar_config = sanitize_sidebar_config(self.instance.sidebar_config, allow_system_items=True)
            sidebar_config['home_url_name'] = None
            self.initial['sidebar_config'] = _json_dump(sidebar_config, ensure_ascii=False)
        initial_navbar_config = sanitize_navbar_config(
            (
                config.get('navbar', {})
                if (not getattr(self.instance, 'pk', None) and not getattr(self.instance, 'is_configured', False))
                else getattr(self.instance, 'navbar_config', None)
            ) or config.get('navbar', {})
        )
        self.initial['navbar_config'] = _json_dump(initial_navbar_config, ensure_ascii=False)
        initial_log_config = normalize_log_config(
            (
                config.get('log', {})
                if (not getattr(self.instance, 'pk', None) and not getattr(self.instance, 'is_configured', False))
                else getattr(self.instance, 'log_config', None)
            ) or config.get('log', {})
        )
        self.initial['log_config'] = _json_dump(initial_log_config, ensure_ascii=False)
        self._initial_log_config = initial_log_config
        initial_profile_config = normalize_profile_config(
            (
                config.get('profile', {})
                if (not getattr(self.instance, 'pk', None) and not getattr(self.instance, 'is_configured', False))
                else getattr(self.instance, 'profile_config', None)
            ) or config.get('profile', {})
        )
        self.initial['profile_config'] = _json_dump(initial_profile_config, ensure_ascii=False)
        self._initial_profile_config = initial_profile_config
        self.initial['allow_user_home_url'] = bool(initial_homepage_config.get('allow_user_override', False))
        self._apply_schema_group_initials(
            'backup_config',
            getattr(self.instance, 'backup_config', None) or config.get('backup_config') or config.get('backup') or {},
        )
        initial_titlebar_config = normalize_titlebar_config(
            (
                config.get('titlebar', {})
                if (not getattr(self.instance, 'pk', None) and not getattr(self.instance, 'is_configured', False))
                else getattr(self.instance, 'titlebar_config', None)
            ) or config.get('titlebar', {})
        )
        search_source = (
            config.get('search_config', {})
            if (not getattr(self.instance, 'pk', None) and not getattr(self.instance, 'is_configured', False))
            else getattr(self.instance, 'search_config', None)
        ) or initial_titlebar_config
        if (
            normalize_search_config(search_source) == default_search_config()
            and normalize_search_config(initial_titlebar_config) != default_search_config()
        ):
            search_source = initial_titlebar_config
        initial_search_config = normalize_search_config(search_source)
        self.initial['search_config'] = _json_dump(initial_search_config, ensure_ascii=False)

        if not self.initial.get('languages'):
            self.initial['languages'] = _json_dump(config.get('languages', {}), ensure_ascii=False, indent=2)
        if not self.initial.get('translations_override'):
            self.initial['translations_override'] = _json_dump({}, ensure_ascii=False, indent=2)
        if not self.initial.get('default_language'):
            self.initial['default_language'] = config.get('default_language', 'en')
        if not self.initial.get('default_theme'):
            self.initial['default_theme'] = config.get('default_theme', 'light')
        if not self.initial.get('allowed_themes'):
            self.initial['allowed_themes'] = list(normalize_allowed_themes(config.get('allowed_themes')))
        if self.initial.get('default_table_density') not in TABLE_DENSITY_VALUES:
            self.initial['default_table_density'] = config.get('default_table_density', DEFAULT_TABLE_DENSITY)
        # Seed every layout field (footer toggle/text/link, density) from the
        # stored layout_config so the standalone toggles/inputs reflect saved
        # values; the group normalizer fills defaults for anything missing.
        _existing_layout = getattr(self.instance, 'layout_config', None)
        _layout_initial_source = dict(_existing_layout) if isinstance(_existing_layout, dict) else {}
        for _layout_key in (
            'footer_enabled', 'footer_text', 'footer_link_text', 'footer_link_url',
            'default_form_density', 'default_modal_size', 'sticky_table_headers',
            'resizable_table_columns', 'zebra_striping', 'show_audit_fields', 'show_soft_deleted',
        ):
            if _layout_key not in _layout_initial_source and config.get(_layout_key) is not None:
                _layout_initial_source[_layout_key] = config.get(_layout_key)
        _layout_initial_source['default_table_density'] = self.initial.get('default_table_density')
        self._apply_schema_group_initials(
            'layout_config',
            _layout_initial_source,
            hidden_field=False,
        )
        self._apply_schema_group_initials(
            'auth_config',
            getattr(self.instance, 'auth_config', None) or config.get('auth_config') or config
        )
        initial_login_config = normalize_login_config(
            getattr(self.instance, 'login_config', None) or config.get('login', {})
        )
        self.initial['login_config'] = _json_dump(initial_login_config, ensure_ascii=False)
        self.initial['login_style'] = initial_login_config.get('style', 'split')
        self.initial['login_show_logo'] = initial_login_config.get('show_logo', True)
        self.initial['login_banner_color'] = initial_login_config.get('banner_color', '')
        self.initial['login_logo_treatment'] = initial_login_config.get('logo_treatment', 'none')
        self.initial['login_logo_treatment_shape'] = initial_login_config.get('logo_treatment_shape', 'soft')
        # per-language hero message initial values set dynamically in __init__ above
        self._apply_schema_group_initials(
            'client_ip_config',
            (
                getattr(self.instance, 'client_ip_config', None)
                if isinstance(getattr(self.instance, 'client_ip_config', None), dict) and getattr(self.instance, 'client_ip_config', None)
                else config.get('client_ip', {})
            )
        )
        self._apply_schema_group_initials(
            'public_root_config',
            {
                'public_root': public_homepage['enabled'],
                'public_root_split_enabled': public_homepage['separate_url'],
                'public_root_url': current_public_root_url,
                'public_root_theme': public_homepage['theme'],
                'public_root_title': public_homepage['title'],
                'public_root_meta_description': public_homepage['meta_description'],
                'show_titlebar_on_public': public_homepage['show_titlebar'],
                'show_sidebar_on_public': public_homepage['show_sidebar'],
            },
            hidden_field=False,
        )
        registration_activation_mode = (
            getattr(self.instance, 'registration_activation_mode', None)
            or config.get('registration_activation_mode')
        )
        self._apply_schema_group_initials(
            'registration_config',
            {
                'public_registration_enabled': (
                    getattr(self.instance, 'public_registration_enabled', False)
                    or config.get('public_registration_enabled', False)
                ),
                'registration_activation_mode': registration_activation_mode,
                'registration_throttle_enabled': (
                    getattr(self.instance, 'registration_throttle_enabled', True)
                    if hasattr(self.instance, 'registration_throttle_enabled')
                    else config.get('registration_throttle_enabled', True)
                ),
                'honeypot_enabled': (
                    getattr(self.instance, 'honeypot_enabled', True)
                    if hasattr(self.instance, 'honeypot_enabled')
                    else config.get('honeypot_enabled', True)
                ),
                'privacy_policy_url': (
                    getattr(self.instance, 'privacy_policy_url', '')
                    if hasattr(self.instance, 'privacy_policy_url')
                    else config.get('privacy_policy_url', '')
                ),
                'terms_url': (
                    getattr(self.instance, 'terms_url', '')
                    if hasattr(self.instance, 'terms_url')
                    else config.get('terms_url', '')
                ),
                'privacy_notice_text': (
                    getattr(self.instance, 'privacy_notice_text', '')
                    if hasattr(self.instance, 'privacy_notice_text')
                    else config.get('privacy_notice_text', '')
                ),
                'registration_require_consent': (
                    getattr(self.instance, 'registration_require_consent', False)
                    if hasattr(self.instance, 'registration_require_consent')
                    else config.get('registration_require_consent', False)
                ),
            },
            hidden_field=False,
        )
        initial_email_config = normalize_email_config(
            (
                getattr(self.instance, 'email_config', None)
                if isinstance(getattr(self.instance, 'email_config', None), dict) and getattr(self.instance, 'email_config', None)
                else config.get('email_config', {})
            )
        )
        self.initial['email_config'] = _json_dump(normalize_email_config(initial_email_config, redact_secret=True), ensure_ascii=False)
        self.initial['email_config_transport'] = initial_email_config.get('transport', 'direct')
        self.initial['email_config_secret_storage'] = initial_email_config.get('secret_storage', 'env')
        self.initial['email_config_provider_preset'] = initial_email_config.get('provider_preset', 'custom')
        self.initial['email_config_host'] = initial_email_config.get('host', '')
        self.initial['email_config_port'] = initial_email_config.get('port', 587)
        self.initial['email_config_use_tls'] = bool(initial_email_config.get('use_tls', True))
        self.initial['email_config_use_ssl'] = bool(initial_email_config.get('use_ssl', False))
        self.initial['email_config_username'] = initial_email_config.get('username', '')
        self.initial['email_config_default_from_email'] = initial_email_config.get('default_from_email', '')
        self.initial['email_config_failure_recipients'] = '\n'.join(
            initial_email_config.get('failure_notification_recipients', []) or []
        )
        self.initial['email_config_enabled'] = bool(initial_email_config.get('enabled', False))
        self.initial['email_config_timeout'] = initial_email_config.get('timeout', 0) or None
        if initial_email_config.get('password_configured'):
            # A write-only field renders blank whether or not a secret is stored;
            # say which, so "empty" is not mistaken for "lost".
            self.fields['email_config_password'].help_text = get_strings().get(
                'help_sys_email_password_saved',
                'A password is saved. Leave blank to keep it, or type a new one to replace it.',
            )
        if not self.initial.get('sidebar_config'):
            sidebar_config = sanitize_sidebar_config(config.get('sidebar', {}), allow_system_items=True)
            if not isinstance(sidebar_config, dict):
                sidebar_config = normalize_sidebar_behavior({
                    'home_url_name': None,
                    'entries': [],
                })
            sidebar_config.setdefault('entries', [])
            sidebar_config = normalize_sidebar_behavior(sidebar_config)
            sidebar_config['home_url_name'] = None
            self.initial['sidebar_config'] = _json_dump(sidebar_config, ensure_ascii=False)

        initial_sidebar_config = self.initial.get('sidebar_config') or {}
        if isinstance(initial_sidebar_config, str):
            try:
                initial_sidebar_config = json.loads(initial_sidebar_config)
            except (TypeError, ValueError, json.JSONDecodeError):
                initial_sidebar_config = {}

        self.initial['sidebar_enabled'] = bool(initial_sidebar_config.get('enabled', True))
        self.initial['sidebar_enable_reorder'] = bool(initial_sidebar_config.get('enable_reorder', True))
        self.initial['sidebar_enable_toolbar'] = bool(initial_sidebar_config.get('show_toolbar', True))
        self.initial['sidebar_show_icons'] = bool(initial_sidebar_config.get('show_icons', True))
        stored_picker_location = (
            config.get('theme_picker_location', DEFAULT_THEME_PICKER_LOCATION)
            if (not getattr(self.instance, 'pk', None) and not getattr(self.instance, 'is_configured', False))
            else getattr(
                self.instance, 'theme_picker_location',
                config.get('theme_picker_location', DEFAULT_THEME_PICKER_LOCATION),
            )
        )
        if stored_picker_location not in THEME_PICKER_LOCATION_VALUES:
            stored_picker_location = DEFAULT_THEME_PICKER_LOCATION
        # The sidebar toolbar is the picker's host, so it cannot host anything
        # once the sidebar or its toolbar is off. Same rule the runtime applies.
        self._sidebar_toolbar_hostable = bool(
            self.initial.get('sidebar_enabled', True)
        ) and bool(self.initial.get('sidebar_enable_toolbar', True))
        if not self._sidebar_toolbar_hostable and stored_picker_location == DEFAULT_THEME_PICKER_LOCATION:
            stored_picker_location = THEME_PICKER_LOCATION_TITLEBAR
        self.initial['theme_picker_location'] = stored_picker_location
        picker_location_widget = self.fields['theme_picker_location'].widget
        if hasattr(picker_location_widget, 'disabled_values'):
            picker_location_widget.disabled_values = (
                set() if self._sidebar_toolbar_hostable else {DEFAULT_THEME_PICKER_LOCATION}
            )
        self.initial['sidebar_show_notification_badges'] = bool(
            initial_sidebar_config.get('show_notification_badges', True)
        )
        self.initial['sidebar_density'] = initial_sidebar_config.get('density', DEFAULT_SIDEBAR_DENSITY)
        self.initial['sidebar_allow_user_density'] = bool(initial_sidebar_config.get('allow_user_density', True))
        self.initial['sidebar_collapse_mode'] = initial_sidebar_config.get('collapse_mode', DEFAULT_SIDEBAR_COLLAPSE_MODE)
        self.initial['sidebar_toggle_icon'] = normalize_sidebar_toggle_icon(
            initial_sidebar_config.get('toggle_icon')
        )
        if self.mode == 'setup' and not getattr(self.instance, 'is_configured', False):
            initial_navbar_config = seed_navbar_config_from_sidebar(
                initial_navbar_config,
                initial_sidebar_config,
                lang_code=self.initial.get('default_language') or 'en',
            )
            self.initial['navbar_config'] = _json_dump(initial_navbar_config, ensure_ascii=False)
        self.initial['navbar_enabled'] = bool(initial_navbar_config.get('enabled', False))
        self.initial['navbar_default_mode'] = initial_navbar_config.get('default_mode', DEFAULT_NAVBAR_MODE)
        self.initial['navbar_allow_user_mode_override'] = bool(
            initial_navbar_config.get('allow_user_mode_override', True)
        )
        self.initial['titlebar_show_title'] = bool(initial_titlebar_config.get('show_title', True))
        self.initial['titlebar_show_logo'] = bool(initial_titlebar_config.get('show_logo', True))
        self.initial['titlebar_show_home_button'] = bool(initial_titlebar_config.get('show_home_button', True))
        self.initial['titlebar_home_shape'] = initial_titlebar_config.get(
            'buttons_shape',
            initial_titlebar_config.get('home_shape', 'circle'),
        )
        self.initial['titlebar_user_hub_style'] = initial_titlebar_config.get(
            'user_hub_style',
            TITLEBAR_USER_HUB_STYLE_DROPDOWN,
        )
        self.initial['titlebar_show_language_switcher'] = bool(
            initial_titlebar_config.get('show_language_switcher', False))
        self.initial['titlebar_actions_order'] = _json_dump(
            normalize_titlebar_actions_order(initial_titlebar_config.get('actions_order')),
            ensure_ascii=False,
        )
        self.initial['titlebar_title_align'] = initial_titlebar_config.get('title_align', 'start')
        self.initial['titlebar_title_size'] = initial_titlebar_config.get('title_size', 'md')
        self.initial['titlebar_height'] = initial_titlebar_config.get('height', 'balanced')
        self.initial['titlebar_surface'] = initial_titlebar_config.get('surface', 'default')
        self.initial['titlebar_logo_treatment'] = initial_titlebar_config.get('logo_treatment', 'none')
        self.initial['titlebar_logo_treatment_shape'] = initial_titlebar_config.get('logo_treatment_shape', 'soft')
        self.initial['titlebar_global_search_mode'] = (
            initial_search_config.get('display_mode', 'icon')
            if initial_search_config.get('enabled', True)
            else 'disabled'
        )
        self.initial['titlebar_global_search_include_data'] = bool(initial_search_config.get('include_data', False))
        initial_notification_config = normalize_notification_config(
            (
                config.get('notifications', {})
                if (not getattr(self.instance, 'pk', None) and not getattr(self.instance, 'is_configured', False))
                else getattr(self.instance, 'notification_config', None)
            ) or config.get('notifications', {})
        )
        self.initial['notification_config'] = _json_dump(initial_notification_config, ensure_ascii=False)
        flash_config = initial_notification_config.get('flash', {})
        drawer_config = initial_notification_config.get('drawer', {})
        bridge_config = initial_notification_config.get('bridge', {})
        email_notification_config = initial_notification_config.get('email', {})
        automatic_config = initial_notification_config.get('automatic', {})
        self.initial['notifications_enabled'] = bool(initial_notification_config.get('enabled', True))
        self.initial['notification_flash_enabled'] = bool(flash_config.get('enabled', True))
        self.initial['notification_flash_position'] = flash_config.get('position', 'top_center')
        self.initial['notification_flash_size'] = flash_config.get('size', 'balanced')
        self.initial['notification_flash_text_size'] = flash_config.get('text_size', 'md')
        self.initial['notification_flash_timeout_ms'] = flash_config.get('timeout_ms', 3200)
        self.initial['notification_flash_max_visible'] = flash_config.get('max_visible', 3)
        self.initial['notification_drawer_enabled'] = bool(drawer_config.get('enabled', True))
        self.initial['notification_badge_enabled'] = bool(drawer_config.get('badge_enabled', True))
        self.initial['notification_bridge_enabled'] = bool(bridge_config.get('django_messages_enabled', False))
        self.initial['notification_email_enabled'] = bool(email_notification_config.get('enabled', False))
        self.initial['notification_email_default'] = bool(email_notification_config.get('default', False))
        if not getattr(self, 'notification_email_available', False):
            self.initial['notification_email_enabled'] = False
            self.initial['notification_email_default'] = False
        self.initial['notification_auto_crud_enabled'] = bool(automatic_config.get('scoped_model_crud', True))
        self.initial['notification_auto_create'] = bool(automatic_config.get('create', True))
        self.initial['notification_auto_update'] = automatic_config.get('update', 'summary')
        self.initial['notification_auto_delete'] = bool(automatic_config.get('delete', True))

        # Show the builder's discovered/available entries in the admin's CURRENT
        # display language (not the system default), so an English-viewing admin
        # doesn't see an Arabic catalog just because the default language is Arabic.
        # Runtime navigation re-resolves every entry per viewer regardless, so this
        # only affects what the editor sees. Falls back to the configured default.
        catalog_lang = (
            get_current_language_code(self.request)
            or self.initial.get('default_language')
            or self.instance.default_language
            or config.get('default_language', 'en')
        )
        # One global catalog, three projections: a landing picker needs a
        # context-free page, the sidebar offers form pages behind a toggle, and
        # the Nav Bar hierarchy also accepts id-bound routes as parents/children.
        landing_catalog = discover_routes_for(
            DISCOVERY_PROFILE_LANDING, lang_code=catalog_lang, include_system_items=False,
        )
        self.sidebar_catalog = discover_sidebar_catalog(lang_code=catalog_lang, include_system_items=True)
        self.sidebar_catalog_fallback = discover_sidebar_catalog(lang_code='en', include_system_items=True)
        self.navbar_catalog = discover_routes_for(
            DISCOVERY_PROFILE_NAVBAR, lang_code=catalog_lang, include_system_items=True,
        )
        seen_home_urls = set()
        home_url_choices = [('', s.get('form_sys_home_url_custom', 'Use a custom URL'))]
        home_url_option_meta = {
            '': {
                'description': s.get('home_url_custom_desc', 'Keep a custom titlebar home URL instead of a discovered page.'),
            }
        }
        for entry in landing_catalog:
            url_name = entry.get('url_name')
            if not url_name:
                continue
            try:
                resolved_url = reverse(url_name)
            except NoReverseMatch:
                continue
            if resolved_url in seen_home_urls:
                continue
            seen_home_urls.add(resolved_url)
            entry_label = str(entry.get('label') or entry.get('group_label') or url_name).strip()
            home_url_choices.append((resolved_url, entry_label))
            home_url_option_meta[resolved_url] = {
                'description': str(entry.get('group_label') or '').strip(),
                'secondary': url_name,
                'search_text': f"{entry_label} {url_name} {resolved_url}",
            }
        self.fields['home_url_discovered'].choices = home_url_choices
        self.fields['home_url_discovered'].widget.option_meta = home_url_option_meta
        self.initial['home_url_discovered'] = current_home_url if current_home_url in seen_home_urls else ''
        self.fields['public_root_url_discovered'].choices = home_url_choices
        self.fields['public_root_url_discovered'].widget.option_meta = home_url_option_meta
        self.initial['public_root_url_discovered'] = current_public_root_url if current_public_root_url in seen_home_urls else ''

        initial_languages = (
            self.data.get('languages')
            if self.is_bound and 'languages' in self.data
            else self.initial.get('languages')
        ) or {}
        if isinstance(initial_languages, str):
            try:
                initial_languages = json.loads(initial_languages)
            except (TypeError, ValueError, json.JSONDecodeError):
                initial_languages = {}
        current_languages = normalize_language_catalog(initial_languages)
        self.initial['languages'] = _json_dump(current_languages, ensure_ascii=False)
        initial_default_language = (
            self.data.get('default_language')
            if self.is_bound and 'default_language' in self.data
            else self.initial.get('default_language')
        )
        initial_default_language = str(initial_default_language or '').strip().lower().replace('_', '-')
        if initial_default_language in current_languages:
            self.initial['default_language'] = initial_default_language
        else:
            self.initial['default_language'] = 'en' if 'en' in current_languages else next(iter(current_languages), 'en')

        initial_system_names = (
            self.data.get('system_names')
            if self.is_bound and 'system_names' in self.data
            else self.initial.get('system_names')
        ) or {}
        if isinstance(initial_system_names, str):
            try:
                initial_system_names = json.loads(initial_system_names)
            except (TypeError, ValueError, json.JSONDecodeError):
                initial_system_names = {}
        initial_system_names = normalize_system_names(initial_system_names)
        self.initial['system_names'] = _json_dump(initial_system_names, ensure_ascii=False)

        initial_translation_overrides = (
            self.data.get('translations_override')
            if self.is_bound and 'translations_override' in self.data
            else self.initial.get('translations_override')
        ) or {}
        if isinstance(initial_translation_overrides, str):
            try:
                initial_translation_overrides = json.loads(initial_translation_overrides)
            except (TypeError, ValueError, json.JSONDecodeError):
                initial_translation_overrides = {}
        if not isinstance(initial_translation_overrides, dict):
            initial_translation_overrides = {}
        suggested_languages = [
            code for code in discover_translation_languages(config.get('translations', {}), initial_translation_overrides)
            if code not in current_languages
        ]

        self.language_catalog_html = self._step_render(SETUP_STEP_LANGUAGES,
            'dlux/setup/language_catalog_editor.html',
            {
                'language_rows': [
                    {
                        'code': code,
                        'name': payload.get('name', code),
                        'dir': payload.get('dir', 'ltr'),
                        'flag': payload.get('flag', ''),
                        'system_name': initial_system_names.get(code, ''),
                    }
                    for code, payload in current_languages.items()
                ],
                'default_language': self.initial.get('default_language', 'en'),
                'suggested_languages': suggested_languages,
                'DLUX_STRINGS': s,
            },
        )
        self.system_names_html = self._step_render(SETUP_STEP_IDENTITY,
            'dlux/setup/system_names_editor.html',
            {
                'language_rows': [
                    {
                        'code': code,
                        'name': payload.get('name', code),
                        'system_name': initial_system_names.get(code, ''),
                    }
                    for code, payload in current_languages.items()
                ],
                'DLUX_STRINGS': s,
            },
        )
        translation_groups = build_translation_matrix_groups(current_languages, initial_translation_overrides)
        for group in translation_groups:
            if group.get('id') == 'project':
                group['label'] = s.get('translation_matrix_group_project', group.get('label') or 'Project translations')
            elif group.get('id') == 'runtime':
                group['label'] = s.get('translation_matrix_group_runtime', group.get('label') or 'Settings overrides')
        self.translation_matrix_html = self._step_render(SETUP_STEP_LANGUAGES,
            'dlux/setup/translation_matrix_editor.html',
            {
                'languages': current_languages,
                'translation_groups': translation_groups,
                'DLUX_STRINGS': s,
            },
        )

        self.theme_picker_html = self._step_render(SETUP_STEP_APPEARANCE,
            'dlux/setup/theme_settings_matrix.html',
            {
                'selected_theme': self.initial.get('default_theme', 'light'),
                'picker_mode': 'setup',
                'input_id': 'id_default_theme',
                'allowed_input_name': 'allowed_themes',
                'allowed_themes': set(self.initial.get('allowed_themes') if isinstance(self.initial.get('allowed_themes'), (list, tuple, set)) else []),
                'DLUX_STRINGS': s,
                'DLUX_THEMES': get_theme_options(s),
                'label': self.fields['default_theme'].label,
                'help_text': self.fields['allowed_themes'].help_text,
            },
        )

        from ..fonts import get_available_fonts
        self.font_picker_html = self._step_render(SETUP_STEP_APPEARANCE,
            'dlux/setup/font_settings_matrix.html',
            {
                'picker_mode': 'setup',
                'input_id': 'id_allowed_fonts',
                'allowed_input_name': 'allowed_fonts',
                'allowed_fonts': set(self.initial.get('allowed_fonts') if isinstance(self.initial.get('allowed_fonts'), (list, tuple, set)) else []),
                'DLUX_STRINGS': s,
                'DLUX_FONTS': get_available_fonts(),
                'label': self.fields['allowed_fonts'].label,
                'help_text': self.fields['allowed_fonts'].help_text,
            },
        )

        default_fonts_data = self.initial.get('default_fonts') or {}
        if isinstance(default_fonts_data, str):
            try:
                default_fonts_data = json.loads(default_fonts_data)
            except (TypeError, ValueError, json.JSONDecodeError):
                default_fonts_data = {}

        self.language_fonts_editor_html = self._step_render(SETUP_STEP_APPEARANCE,
            'dlux/setup/language_fonts_editor.html',
            {
                'current_languages': current_languages,
                'default_fonts': default_fonts_data,
                'DLUX_FONTS': get_available_fonts(),
                'DLUX_STRINGS': s,
            },
        )

        self.sidebar_toggle_icon_html = self._step_render(SETUP_STEP_SIDEBAR,
            'dlux/helpers/icon_picker.html',
            {
                'field_name': 'sidebar_toggle_icon',
                'label': self.fields['sidebar_toggle_icon'].label,
                'help_text': self.fields['sidebar_toggle_icon'].help_text,
                'current_icon': self.initial.get('sidebar_toggle_icon') or DEFAULT_SIDEBAR_TOGGLE_ICON,
                'default_icon': DEFAULT_SIDEBAR_TOGGLE_ICON,
                # Single source for the RTL/state mirror set: the live preview reads
                # it back off the element instead of keeping a second copy in JS.
                'directional_icons': ' '.join(SIDEBAR_TOGGLE_DIRECTIONAL_ICONS),
                # Popover is the default; pass `inline: True` for the in-flow grid.
                'inline': False,
                # `locked_expanded` hides the toggle on desktop, so its glyph has
                # nothing to style there.
                'disabled': (
                    not self.initial.get('sidebar_enabled', True)
                    or self.initial.get('sidebar_collapse_mode') == 'locked_expanded'
                ),
                'mode': self.mode,
                'DLUX_STRINGS': s,
            },
        )
        self.sidebar_builder_html = self._step_render(SETUP_STEP_SIDEBAR,
            'dlux/setup/sidebar_builder.html',
            {
                'sidebar_catalog': self.sidebar_catalog,
                'sidebar_catalog_json': _json_dump(self.sidebar_catalog, ensure_ascii=False),
                'sidebar_catalog_fallback_json': _json_dump(self.sidebar_catalog_fallback, ensure_ascii=False),
                'sidebar_config_json': _json_dump(self.initial.get('sidebar_config', {}), ensure_ascii=False),
                'languages_json': _json_dump(current_languages, ensure_ascii=False),
                'mode': self.mode,
                'DLUX_STRINGS': s,
            },
        )
        self.navbar_builder_html = self._step_render(SETUP_STEP_NAVBAR,
            'dlux/setup/navbar_builder.html',
            {
                'navbar_catalog_json': _json_dump(self.navbar_catalog, ensure_ascii=False),
                'navbar_config_json': _json_dump(initial_navbar_config, ensure_ascii=False),
                'languages_json': _json_dump(current_languages, ensure_ascii=False),
                'mode': self.mode,
                'DLUX_STRINGS': s,
            },
        )
        from dlux.discovery import build_log_model_catalog
        log_catalog = build_log_model_catalog()

        def _log_action_label(key):
            base = {
                'create': s.get('action_create', 'Create'),
                'update': s.get('action_update', 'Update'),
                'delete': s.get('action_delete', 'Delete'),
            }
            return base.get(key) or s.get(f'action_{key}', key.replace('_', ' ').title())

        for _bucket in ('user', 'system'):
            for _item in log_catalog[_bucket]:
                _item['display_actions'] = [
                    {'key': a, 'label': _log_action_label(a)}
                    for a in _item.get('actions') or ('create', 'update', 'delete')
                ]

        self.log_builder_html = self._step_render(SETUP_STEP_LOGGING,
            'dlux/setup/log_builder.html',
            {
                'log_config_json': _json_dump(initial_log_config, ensure_ascii=False),
                'sections': [
                    {'key': 'user', 'title': s.get('form_sys_log_user', 'User activity (project)'), 'models': log_catalog['user']},
                    {'key': 'system', 'title': s.get('form_sys_log_system', 'System activity (dlux)'), 'models': log_catalog['system']},
                ],
                'actions': [
                    {'key': 'create', 'label': s.get('action_create', 'Create')},
                    {'key': 'update', 'label': s.get('action_update', 'Update')},
                    {'key': 'delete', 'label': s.get('action_delete', 'Delete')},
                ],
                'audit_events': [
                    {'key': key, 'label': s.get(f'form_sys_log_audit_{key}', key.replace('_', ' ').title())}
                    for key in initial_log_config.get('audit', {}).get('events', {}).keys()
                ],
                'DLUX_STRINGS': s,
            },
        )
        self.profile_builder_html = self._step_render(SETUP_STEP_PROFILE,
            'dlux/setup/profile_builder.html',
            {
                'profile_config_json': _json_dump(initial_profile_config, ensure_ascii=False),
                'page_toggles': [
                    {
                        'key': 'show_completion_widget',
                        'label': s.get('profile_show_completion', 'Show profile completion widget'),
                        'help': s.get(
                            'profile_show_completion_help',
                            'A progress meter on the profile page prompting the user to finish setting up their account.',
                        ),
                    },
                    {
                        'key': 'show_session_device_cards',
                        'label': s.get('profile_show_devices', 'Show session/device cards'),
                        'help': s.get(
                            'profile_show_devices_help',
                            'Lets users review their active sessions and known devices, and sign other sessions out.',
                        ),
                    },
                    {
                        'key': 'show_activity_feed',
                        'label': s.get('profile_show_activity', 'Show activity feed'),
                        'help': s.get(
                            'profile_show_activity_help',
                            "A reverse-chronological list of the user's own recent actions on their profile page.",
                        ),
                    },
                ],
                'nudge_options': [
                    {'key': 'off', 'label': s.get('nudge_off', 'Off')},
                    {'key': 'subtle', 'label': s.get('nudge_subtle', 'Subtle')},
                    {'key': 'persistent', 'label': s.get('nudge_persistent', 'Persistent')},
                ],
                'onboarding_toggles': [
                    {'key': 'theme', 'label': s.get('options_theme', 'Theme')},
                    {'key': 'language', 'label': s.get('options_language', 'Language')},
                    {'key': 'fonts', 'label': s.get('options_font', 'Font')},
                ],
                'nudges_help': s.get(
                    'profile_security_nudges_help',
                    'How insistently the profile page prompts a user to fix account-health gaps such as missing two-factor authentication.',
                ),
                'DLUX_STRINGS': s,
            },
        )
        self.titlebar_actions_order_html = build_titlebar_actions_order_builder(
            initial_titlebar_config.get('actions_order'),
            s,
            visible=self.initial.get('titlebar_user_hub_style') == TITLEBAR_USER_HUB_STYLE_ACTIONS,
        )

        self.helper = FormHelper()
        self.helper.form_tag = False


        email_password_field_class = 'col-md-4 dlux-email-config-password-field'
        if self.initial.get('email_config_secret_storage') != 'encrypted_db':
            email_password_field_class += ' d-none'

        # Build step 1 fields dynamically - import only shown in initial setup
        step_1_fields = [
            self._step_badge(s, 'system_setup_step1', 'Step 1: Identity'),
        ]
        if self.mode == 'setup':
            step_1_fields.append(build_archive_file_field('settings_import_file'))
            step_1_fields.append(Field('settings_import_processed'))
            step_1_fields.append(HTML(
                "<div class='dlux-import-finish-cta d-none' data-settings-import-finish>"
                f"<div><strong>{s.get('system_setup_import_finish', 'Finish setup from imported config')}</strong>"
                f"<small>{s.get('system_setup_import_finish_desc', 'Save the imported setup now, or keep editing first.')}</small></div>"
                f"<button type='submit' class='btn btn-primary'>{s.get('system_setup_import_finish_button', 'Finish setup')}</button>"
                "</div>"
            ))
        step_1_fields.extend([
            HTML(self.system_names_html),
            Field('system_names'),
            Row(
                Div(build_archive_file_field('logo'), css_class='col-md-6'),
                Div(build_archive_file_field('favicon'), css_class='col-md-6'),
                css_class='row'
            ),
        ])

        self.helper.layout = self._build_layout(
            s=s,
            step_1_fields=step_1_fields,
            email_password_field_class=email_password_field_class,
            field_name=field_name,
        )
















































































    def _apply_imported_settings(self, cleaned, imported):
        if not imported:
            return
        # Skip re-applying import if JS already populated the form (user may have edited values)
        if cleaned.get('settings_import_processed'):
            return
        direct_fields = (
            'system_names',
            'languages',
            'translations_override',
            'home_url',
            'public_root_url',
            'default_language',
            'default_theme',
            'allowed_themes',
            'allow_user_theme_override',
            'theme_picker_location',
            'allowed_fonts',
            'default_fonts',
            'allow_user_font_override',
            'allow_user_language_override',
            'default_table_density',
            'email_2fa',
            'forgot_password_enabled',
            'prevent_multiple_active_sessions',
            'login_lockout_enabled',
            'login_lockout_threshold',
            'login_lockout_window_minutes',
            'login_lockout_duration_minutes',
            'enforce_strong_passwords',
            'strong_password_min_length',
            'client_ip_config',
            'public_root',
            'public_root_split_enabled',
            'public_registration_enabled',
            'registration_activation_mode',
            'registration_throttle_enabled',
            'privacy_policy_url',
            'terms_url',
            'privacy_notice_text',
            'registration_require_consent',
            'email_config',
            'notification_config',
            'search_config',
            'backup_config',
        )
        for field_name in direct_fields:
            if field_name in imported:
                cleaned[field_name] = imported[field_name]

        email_config = imported.get('email_config')
        if isinstance(email_config, dict):
            cleaned['email_config'] = email_config
            cleaned['email_config_transport'] = email_config.get('transport', 'direct')
            cleaned['email_config_secret_storage'] = email_config.get('secret_storage', 'env')
            cleaned['email_config_provider_preset'] = email_config.get('provider_preset', 'custom')
            cleaned['email_config_host'] = email_config.get('host', '')
            cleaned['email_config_port'] = email_config.get('port', 587)
            cleaned['email_config_use_tls'] = bool(email_config.get('use_tls', True))
            cleaned['email_config_use_ssl'] = bool(email_config.get('use_ssl', False))
            cleaned['email_config_username'] = email_config.get('username', '')
            cleaned['email_config_default_from_email'] = email_config.get('default_from_email', '')
            cleaned['email_config_failure_recipients'] = '\n'.join(
                email_config.get('failure_notification_recipients', []) or []
            )
            cleaned['email_config_password'] = ''

        client_ip_config = imported.get('client_ip_config')
        if isinstance(client_ip_config, dict):
            client_ip_config = normalize_client_ip_config(client_ip_config)
            cleaned['client_ip_config'] = client_ip_config
            cleaned['client_ip_mode'] = client_ip_config.get('mode', CLIENT_IP_MODE_X_FORWARDED_FOR)
            cleaned['client_ip_trusted_proxy_hops'] = client_ip_config.get('trusted_proxy_hops', 1)
            cleaned['client_ip_custom_header'] = client_ip_config.get('custom_header', '')

        sidebar = imported.get('sidebar_config')
        if isinstance(sidebar, dict):
            cleaned['sidebar_config'] = sidebar
            cleaned['sidebar_enabled'] = bool(sidebar.get('enabled', True))
            cleaned['sidebar_enable_reorder'] = bool(sidebar.get('enable_reorder', True))
            cleaned['sidebar_enable_toolbar'] = bool(sidebar.get('show_toolbar', True))
            cleaned['sidebar_show_icons'] = bool(sidebar.get('show_icons', True))
            cleaned['sidebar_show_notification_badges'] = bool(
                sidebar.get('show_notification_badges', True)
            )
            cleaned['sidebar_density'] = sidebar.get('density', DEFAULT_SIDEBAR_DENSITY)
            cleaned['sidebar_allow_user_density'] = bool(sidebar.get('allow_user_density', True))
            cleaned['sidebar_collapse_mode'] = sidebar.get('collapse_mode', DEFAULT_SIDEBAR_COLLAPSE_MODE)
            cleaned['sidebar_toggle_icon'] = sidebar.get('toggle_icon', DEFAULT_SIDEBAR_TOGGLE_ICON)

        navbar = imported.get('navbar_config')
        if isinstance(navbar, dict):
            from dlux.discovery import sanitize_navbar_config

            navbar = sanitize_navbar_config(navbar)
            cleaned['navbar_config'] = navbar
            cleaned['navbar_enabled'] = bool(navbar.get('enabled', False))
            cleaned['navbar_default_mode'] = navbar.get('default_mode', DEFAULT_NAVBAR_MODE)
            cleaned['navbar_allow_user_mode_override'] = bool(navbar.get('allow_user_mode_override', True))

        log = imported.get('log_config')
        if isinstance(log, dict):
            cleaned['log_config'] = normalize_log_config(log)

        profile = imported.get('profile_config')
        if isinstance(profile, dict):
            cleaned['profile_config'] = normalize_profile_config(profile)

        homepage = imported.get('homepage_config')
        if isinstance(homepage, dict):
            homepage = normalize_homepage_config(homepage)
            public = homepage['public']
            cleaned['homepage_config'] = homepage
            cleaned['home_url'] = homepage['default_url']
            cleaned['allow_user_home_url'] = bool(homepage['allow_user_override'])
            cleaned['public_root'] = bool(public['enabled'])
            cleaned['public_root_split_enabled'] = bool(public['separate_url'])
            cleaned['public_root_url'] = public['url']
            cleaned['public_root_theme'] = public['theme']
            cleaned['public_root_title'] = public['title']
            cleaned['public_root_meta_description'] = public['meta_description']
            cleaned['show_titlebar_on_public'] = bool(public['show_titlebar'])
            cleaned['show_sidebar_on_public'] = bool(public['show_sidebar'])

        backup = imported.get('backup_config')
        if isinstance(backup, dict):
            backup = normalize_backup_config(backup)
            cleaned['backup_config'] = backup
            cleaned['backup_scheduled_enabled'] = backup['scheduled_enabled']
            cleaned['backup_schedule_interval_hours'] = backup['schedule_interval_hours']
            cleaned['backup_retention_days'] = backup['retention_days']
            cleaned['backup_max_backups_to_keep'] = backup['max_backups_to_keep']
            cleaned['backup_auto_export_target'] = backup['auto_export_target']
            cleaned['backup_stall_timeout_minutes'] = backup['stall_timeout_minutes']
            cleaned['backup_auto_retry_enabled'] = backup['auto_retry_enabled']
            cleaned['backup_max_attempts'] = backup['max_attempts']
            cleaned['backup_retry_delay_minutes'] = backup['retry_delay_minutes']

        titlebar = imported.get('titlebar_config')
        if isinstance(titlebar, dict):
            titlebar = normalize_titlebar_config(titlebar)
            cleaned['titlebar_show_title'] = bool(titlebar.get('show_title', True))
            cleaned['titlebar_show_logo'] = bool(titlebar.get('show_logo', True))
            cleaned['titlebar_show_home_button'] = bool(titlebar.get('show_home_button', True))
            # Legacy titlebar hide flag now maps to the centralized public-root
            # show toggle (inverted). Only seed it when the import didn't already
            # provide an explicit public-root value.
            if 'show_titlebar_on_public' not in cleaned:
                cleaned['show_titlebar_on_public'] = not bool(
                    titlebar.get('hide_on_public_unauthenticated_index', False)
                )
            cleaned['titlebar_home_shape'] = titlebar.get('buttons_shape', titlebar.get('home_shape', 'circle'))
            cleaned['titlebar_user_hub_style'] = titlebar.get('user_hub_style', TITLEBAR_USER_HUB_STYLE_DROPDOWN)
            cleaned['titlebar_show_language_switcher'] = bool(titlebar.get('show_language_switcher', False))
            cleaned['titlebar_actions_order'] = normalize_titlebar_actions_order(titlebar.get('actions_order'))
            cleaned['titlebar_title_align'] = titlebar.get('title_align', 'start')
            cleaned['titlebar_title_size'] = titlebar.get('title_size', 'md')
            cleaned['titlebar_height'] = titlebar.get('height', 'balanced')
            cleaned['titlebar_surface'] = titlebar.get('surface', 'default')
            cleaned['titlebar_logo_treatment'] = titlebar.get('logo_treatment', 'none')
            cleaned['titlebar_logo_treatment_shape'] = titlebar.get('logo_treatment_shape', 'soft')
            if not isinstance(imported.get('search_config'), dict):
                cleaned['titlebar_global_search_mode'] = titlebar.get('global_search_mode', 'icon')
                cleaned['titlebar_global_search_include_data'] = bool(titlebar.get('global_search_include_data', False))

        search = imported.get('search_config')
        if isinstance(search, dict):
            search = normalize_search_config(search)
            cleaned['search_config'] = search
            cleaned['titlebar_global_search_mode'] = (
                search.get('display_mode', 'icon') if search.get('enabled', True) else 'disabled'
            )
            cleaned['titlebar_global_search_include_data'] = bool(search.get('include_data', False))

        notifications = imported.get('notification_config')
        if isinstance(notifications, dict):
            notifications = normalize_notification_config(notifications)
            cleaned['notification_config'] = notifications
            cleaned['notifications_enabled'] = bool(notifications.get('enabled', True))
            flash_config = notifications.get('flash', {})
            drawer_config = notifications.get('drawer', {})
            bridge_config = notifications.get('bridge', {})
            email_notification_config = notifications.get('email', {})
            automatic_config = notifications.get('automatic', {})
            cleaned['notification_flash_enabled'] = bool(flash_config.get('enabled', True))
            cleaned['notification_flash_position'] = flash_config.get('position', 'top_center')
            cleaned['notification_flash_size'] = flash_config.get('size', 'balanced')
            cleaned['notification_flash_text_size'] = flash_config.get('text_size', 'md')
            cleaned['notification_flash_timeout_ms'] = flash_config.get('timeout_ms', 3200)
            cleaned['notification_flash_max_visible'] = flash_config.get('max_visible', 3)
            cleaned['notification_drawer_enabled'] = bool(drawer_config.get('enabled', True))
            cleaned['notification_badge_enabled'] = bool(drawer_config.get('badge_enabled', True))
            cleaned['notification_bridge_enabled'] = bool(bridge_config.get('django_messages_enabled', False))
            cleaned['notification_email_enabled'] = bool(email_notification_config.get('enabled', False))
            cleaned['notification_email_default'] = bool(email_notification_config.get('default', False))
            cleaned['notification_auto_crud_enabled'] = bool(automatic_config.get('scoped_model_crud', True))
            cleaned['notification_auto_create'] = bool(automatic_config.get('create', True))
            cleaned['notification_auto_update'] = automatic_config.get('update', 'summary')
            cleaned['notification_auto_delete'] = bool(automatic_config.get('delete', True))

        login = imported.get('login_config')
        if isinstance(login, dict):
            cleaned['login_config'] = login
            cleaned['login_style'] = login.get('style', 'split')
            cleaned['login_show_logo'] = bool(login.get('show_logo', True))
            cleaned['login_banner_color'] = login.get('banner_color', '')
            cleaned['login_logo_treatment'] = login.get('logo_treatment', 'none')
            cleaned['login_logo_treatment_shape'] = login.get('logo_treatment_shape', 'soft')
            hero = login.get('hero_message') if isinstance(login.get('hero_message'), dict) else {}
            for lang_code, _label, field_name in getattr(self, '_login_hero_lang_fields', []):
                if lang_code in hero:
                    cleaned[field_name] = hero.get(lang_code, '')

    def clean(self):
        cleaned = super().clean()
        self._imported_settings = self._read_imported_settings()
        self._apply_imported_settings(cleaned, self._imported_settings)
        allowed_themes = cleaned.get('allowed_themes') or []
        default_theme = cleaned.get('default_theme') or 'light'
        if allowed_themes and default_theme not in allowed_themes:
            self.add_error('default_theme', "Default theme must remain allowed.")
        languages = cleaned.get('languages') or normalize_language_catalog()
        default_language = cleaned.get('default_language') or 'en'
        if default_language not in languages:
            fallback_language = 'en' if 'en' in languages else next(iter(languages), 'en')
            cleaned['default_language'] = fallback_language
        layout_config = self._schema_group_from_cleaned('layout_config')
        cleaned['layout_config'] = layout_config
        cleaned.update(layout_config)
        public_root_config = self._schema_group_from_cleaned('public_root_config')
        if not public_root_config.get('public_root', False):
            public_root_config['public_root_split_enabled'] = False
        cleaned['public_root_config'] = public_root_config
        cleaned.update(public_root_config)
        cleaned['homepage_config'] = normalize_homepage_config({
            'default_url': cleaned.get('home_url') or DEFAULT_HOME_URL,
            'allow_user_override': bool(cleaned.get('allow_user_home_url', False)),
            'public': {
                'enabled': bool(public_root_config.get('public_root', False)),
                'separate_url': bool(public_root_config.get('public_root_split_enabled', False)),
                'url': public_root_config.get('public_root_url', ''),
                'theme': public_root_config.get('public_root_theme', ''),
                'title': public_root_config.get('public_root_title', ''),
                'meta_description': public_root_config.get('public_root_meta_description', ''),
                'show_titlebar': bool(public_root_config.get('show_titlebar_on_public', False)),
                'show_sidebar': bool(public_root_config.get('show_sidebar_on_public', False)),
            },
        })
        registration_config = self._schema_group_from_cleaned('registration_config')
        cleaned['registration_config'] = registration_config
        cleaned.update(registration_config)

        sidebar = cleaned.get('sidebar_config')
        if isinstance(sidebar, dict):
            sidebar['enabled'] = bool(cleaned.get('sidebar_enabled', True))
            if sidebar['enabled']:
                sidebar['enable_reorder'] = bool(cleaned.get('sidebar_enable_reorder', True))
                sidebar['show_toolbar'] = bool(cleaned.get('sidebar_enable_toolbar', True))
                sidebar['show_icons'] = bool(cleaned.get('sidebar_show_icons', True))
                sidebar['show_notification_badges'] = bool(
                    cleaned.get('sidebar_show_notification_badges', True)
                )
                sidebar['density'] = cleaned.get('sidebar_density', DEFAULT_SIDEBAR_DENSITY)
                sidebar['allow_user_density'] = bool(cleaned.get('sidebar_allow_user_density', True))
                sidebar['collapse_mode'] = cleaned.get('sidebar_collapse_mode', DEFAULT_SIDEBAR_COLLAPSE_MODE)
                sidebar['toggle_icon'] = cleaned.get('sidebar_toggle_icon', DEFAULT_SIDEBAR_TOGGLE_ICON)
            if sidebar['enabled'] and not _system_settings_sidebar_tools_available(cleaned):
                sidebar['show_toolbar'] = False
                cleaned['sidebar_enable_toolbar'] = False
            sidebar = normalize_sidebar_behavior(sidebar)
            cleaned['sidebar_config'] = sidebar
            cleaned['sidebar_enabled'] = bool(sidebar.get('enabled', True))
            cleaned['sidebar_enable_reorder'] = bool(sidebar.get('enable_reorder', True))
            cleaned['sidebar_enable_toolbar'] = bool(sidebar.get('show_toolbar', True))
            cleaned['sidebar_show_icons'] = bool(sidebar.get('show_icons', True))
            cleaned['sidebar_show_notification_badges'] = bool(
                sidebar.get('show_notification_badges', True)
            )
            cleaned['sidebar_density'] = sidebar.get('density', DEFAULT_SIDEBAR_DENSITY)
            cleaned['sidebar_allow_user_density'] = bool(sidebar.get('allow_user_density', True))
            cleaned['sidebar_collapse_mode'] = sidebar.get('collapse_mode', DEFAULT_SIDEBAR_COLLAPSE_MODE)
            cleaned['sidebar_toggle_icon'] = sidebar.get('toggle_icon', DEFAULT_SIDEBAR_TOGGLE_ICON)
        navbar = cleaned.get('navbar_config')
        if isinstance(navbar, dict):
            from dlux.discovery import sanitize_navbar_config

            navbar['enabled'] = bool(cleaned.get('navbar_enabled', False))
            # Mirrors the sidebar contract: while the step is off its dependent
            # controls are disabled and therefore absent from POST, so the stored
            # values are kept rather than collapsing to defaults.
            if navbar['enabled']:
                mode = cleaned.get('navbar_default_mode') or DEFAULT_NAVBAR_MODE
                navbar['default_mode'] = mode if mode in NAVBAR_MODE_VALUES else DEFAULT_NAVBAR_MODE
                navbar['allow_user_mode_override'] = bool(cleaned.get('navbar_allow_user_mode_override', True))
            navbar = sanitize_navbar_config(navbar)
            cleaned['navbar_config'] = navbar
            cleaned['navbar_enabled'] = navbar.get('enabled', False)
            cleaned['navbar_default_mode'] = navbar.get('default_mode', DEFAULT_NAVBAR_MODE)
            cleaned['navbar_allow_user_mode_override'] = navbar.get('allow_user_mode_override', True)
        log = cleaned.get('log_config')
        if isinstance(log, dict):
            cleaned['log_config'] = normalize_log_config(log)
        profile = cleaned.get('profile_config')
        if isinstance(profile, dict):
            # allow_user_home_url is edited as a standalone Step 3 toggle (next to
            # Home URL), not in the Step 12 profile builder — fold it back into
            # profile_config before normalizing/saving.
            if 'allow_user_home_url' in self.fields:
                profile['allow_user_home_url'] = bool(cleaned.get('allow_user_home_url'))
            cleaned['profile_config'] = normalize_profile_config(profile)
        backup_fields_posted = any(name in self.data for name in (
            'backup_scheduled_enabled',
            'backup_schedule_interval_hours',
            'backup_retention_days',
            'backup_max_backups_to_keep',
            'backup_auto_export_target',
            'backup_stall_timeout_minutes',
            'backup_auto_retry_enabled',
            'backup_max_attempts',
            'backup_retry_delay_minutes',
        ))
        existing_backup = normalize_backup_config(getattr(self.instance, 'backup_config', None) or {})
        if self.is_bound and self.mode != 'setup' and self.single_step_mode and self.single_step_index != SETUP_STEP_BACKUPS and not backup_fields_posted:
            cleaned['backup_config'] = existing_backup
        else:
            submitted_backup = cleaned.get('backup_config')
            backup_base = normalize_backup_config(submitted_backup) if isinstance(submitted_backup, dict) else existing_backup
            cleaned['backup_config'] = normalize_backup_config({
                **backup_base,
                'scheduled_enabled': bool(cleaned.get('backup_scheduled_enabled', False)),
                'schedule_interval_hours': cleaned.get('backup_schedule_interval_hours'),
                'retention_days': cleaned.get('backup_retention_days'),
                'max_backups_to_keep': cleaned.get('backup_max_backups_to_keep'),
                'auto_export_target': cleaned.get('backup_auto_export_target'),
                'stall_timeout_minutes': cleaned.get('backup_stall_timeout_minutes'),
                'auto_retry_enabled': bool(cleaned.get('backup_auto_retry_enabled', False)),
                'max_attempts': cleaned.get('backup_max_attempts'),
                'retry_delay_minutes': cleaned.get('backup_retry_delay_minutes'),
            })
        existing_email_config = normalize_email_config(getattr(self.instance, 'email_config', {}))
        email_features_enabled = bool(cleaned.get('public_registration_enabled') or cleaned.get('email_2fa'))
        email_fields_posted = any(name in self.data for name in EMAIL_CONNECTION_FIELDS)
        imported_email_config = cleaned.get('email_config') if isinstance(cleaned.get('email_config'), dict) else {}
        imported_email_config = normalize_email_config(imported_email_config) if imported_email_config else {}
        if imported_email_config.get('secret_storage') == 'encrypted_db' and not imported_email_config.get('encrypted_password'):
            imported_email_config['password_configured'] = False
        preserved_email_config = None
        if not email_fields_posted and imported_email_config and imported_email_config != default_email_config():
            preserved_email_config = dict(imported_email_config)
        elif not email_features_enabled and not email_fields_posted and existing_email_config:
            preserved_email_config = dict(existing_email_config)

        if preserved_email_config is not None:
            # The step's dependent fields are disabled while email is off, so none
            # of them post and the connection details are preserved above. The
            # enable toggle is not one of those fields, so it must not be
            # preserved with them or turning email off never sticks.
            preserved_email_config['enabled'] = bool(
                cleaned.get('email_config_enabled', preserved_email_config.get('enabled', False))
            )
            cleaned['email_config'] = normalize_email_config(preserved_email_config)
        else:
            email_transport = cleaned.get('email_config_transport') or existing_email_config.get('transport', 'direct')
            email_secret_storage = cleaned.get('email_config_secret_storage') or existing_email_config.get('secret_storage', 'env')
            existing_verified = existing_email_config if isinstance(existing_email_config, dict) else {}
            _payload = {
                'transport': email_transport,
                'secret_storage': email_secret_storage,
                'provider_preset': cleaned.get('email_config_provider_preset') or existing_email_config.get('provider_preset', 'custom'),
                'host': cleaned.get('email_config_host') or '',
                'port': cleaned.get('email_config_port') or 587,
                'use_tls': cleaned.get('email_config_use_tls'),
                'use_ssl': cleaned.get('email_config_use_ssl'),
                'username': cleaned.get('email_config_username') or '',
                'default_from_email': cleaned.get('email_config_default_from_email') or '',
                'failure_notification_recipients': cleaned.get('email_config_failure_recipients') or '',
                'enabled': cleaned.get('email_config_enabled', False),
            'timeout': cleaned.get('email_config_timeout') or 0,
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
                raw_password = cleaned.get('email_config_password') or ''
                if raw_password:
                    _payload['encrypted_password'] = encrypt_email_secret(raw_password)
                elif (
                    existing_email_config.get('transport') == _probe['transport']
                    and existing_email_config.get('secret_storage') == 'encrypted_db'
                ):
                    _payload['encrypted_password'] = existing_email_config.get('encrypted_password', '')
            email_config = normalize_email_config(_payload)
            email_config['password_configured'] = bool(email_config.get('encrypted_password'))
            cleaned['email_config'] = email_config
        email_config = normalize_email_config(cleaned.get('email_config') or existing_email_config)
        client_ip_config = self._schema_group_from_cleaned('client_ip_config')
        cleaned['client_ip_config'] = client_ip_config
        cleaned['client_ip_mode'] = client_ip_config.get('mode', CLIENT_IP_MODE_X_FORWARDED_FOR)
        cleaned['client_ip_trusted_proxy_hops'] = client_ip_config.get('trusted_proxy_hops', 1)
        cleaned['client_ip_custom_header'] = client_ip_config.get('custom_header', '')
        hero_dict = {
            lang_code: str(cleaned.get(field_name) or '').strip()
            for lang_code, _label, field_name in getattr(self, '_login_hero_lang_fields', [])
        }
        auth_config = self._schema_group_from_cleaned('auth_config')
        cleaned['auth_config'] = auth_config
        cleaned.update(auth_config)
        cleaned['login_config'] = normalize_login_config({
            'style': cleaned.get('login_style') or 'split',
            'show_logo': bool(cleaned.get('login_show_logo', True)),
            'banner_color': cleaned.get('login_banner_color') or '',
            'logo_treatment': cleaned.get('login_logo_treatment') or 'none',
            'logo_treatment_shape': cleaned.get('login_logo_treatment_shape') or 'soft',
            'hero_message': hero_dict or '',
        })
        search_mode = cleaned.get('titlebar_global_search_mode') or 'icon'
        cleaned['search_config'] = normalize_search_config({
            'enabled': search_mode != 'disabled',
            'display_mode': search_mode if search_mode != 'disabled' else 'icon',
            'include_data': bool(cleaned.get('titlebar_global_search_include_data', False)),
        })
        cleaned['titlebar_config'] = normalize_titlebar_config({
            'show_title': bool(cleaned.get('titlebar_show_title', True)),
            'show_logo': bool(cleaned.get('titlebar_show_logo', True)),
            'show_home_button': bool(cleaned.get('titlebar_show_home_button', True)),
            # Deprecated: titlebar visibility on the public root is now controlled
            # by public_root_config.show_titlebar_on_public. Keep the legacy key in
            # sync (inverted) so old consumers/exports stay coherent.
            'hide_on_public_unauthenticated_index': not bool(
                cleaned.get('show_titlebar_on_public', False)
            ),
            'buttons_shape': cleaned.get('titlebar_home_shape', 'circle'),
            'home_shape': cleaned.get('titlebar_home_shape', 'circle'),
            'user_hub_style': cleaned.get('titlebar_user_hub_style', TITLEBAR_USER_HUB_STYLE_DROPDOWN),
            'show_language_switcher': bool(cleaned.get('titlebar_show_language_switcher', False)),
            'actions_order': cleaned.get('titlebar_actions_order') or list(TITLEBAR_ACTIONS_ORDER),
            'title_align': cleaned.get('titlebar_title_align', 'start'),
            'title_size': cleaned.get('titlebar_title_size', 'md'),
            'height': cleaned.get('titlebar_height', 'balanced'),
            'surface': cleaned.get('titlebar_surface', 'default'),
            'logo_treatment': cleaned.get('titlebar_logo_treatment', 'none'),
            'logo_treatment_shape': cleaned.get('titlebar_logo_treatment_shape', 'soft'),
            'global_search_mode': cleaned.get('titlebar_global_search_mode', 'icon'),
            'global_search_include_data': bool(cleaned.get('titlebar_global_search_include_data', False)),
        })
        notification_split_fields = (
            'notifications_enabled',
            'notification_flash_enabled',
            'notification_flash_position',
            'notification_flash_size',
            'notification_flash_text_size',
            'notification_flash_timeout_ms',
            'notification_flash_max_visible',
            'notification_drawer_enabled',
            'notification_badge_enabled',
            'notification_bridge_enabled',
            'notification_email_enabled',
            'notification_email_default',
            'notification_auto_crud_enabled',
            'notification_auto_create',
            'notification_auto_update',
            'notification_auto_delete',
        )
        notification_fields_posted = any(field_name in self.data for field_name in notification_split_fields)
        # Turning the master toggle off disables the dependent controls, so they
        # stop posting. Rebuilding the group from them would read every absent
        # field as its default and wipe the configuration the admin is only
        # switching off — keep the stored group and flip `enabled` instead.
        notifications_master_off = (
            self.is_bound
            and 'notifications_enabled' in self.data
            and not cleaned.get('notifications_enabled', True)
        )
        if (
            self.is_bound
            and self.mode != 'setup'
            and self.single_step_mode
            and self.single_step_index != SETUP_STEP_NOTIFICATIONS
            and not notification_fields_posted
        ):
            cleaned['notification_config'] = normalize_notification_config(
                getattr(self.instance, 'notification_config', None) or cleaned.get('notification_config')
            )
        elif notifications_master_off:
            stored = normalize_notification_config(
                getattr(self.instance, 'notification_config', None) or cleaned.get('notification_config')
            )
            stored['enabled'] = False
            cleaned['notification_config'] = normalize_notification_config(stored)
        else:
            notification_email_enabled = bool(cleaned.get('notification_email_enabled', False))
            cleaned['notification_config'] = normalize_notification_config({
                'enabled': bool(cleaned.get('notifications_enabled', True)),
                'flash': {
                    'enabled': bool(cleaned.get('notification_flash_enabled', True)),
                    'position': cleaned.get('notification_flash_position') or 'top_center',
                    'size': cleaned.get('notification_flash_size') or 'balanced',
                    'text_size': cleaned.get('notification_flash_text_size') or 'md',
                    'timeout_ms': cleaned.get('notification_flash_timeout_ms') if cleaned.get('notification_flash_timeout_ms') is not None else 3200,
                    'max_visible': cleaned.get('notification_flash_max_visible') if cleaned.get('notification_flash_max_visible') is not None else 3,
                },
                'drawer': {
                    'enabled': bool(cleaned.get('notification_drawer_enabled', True)),
                    'badge_enabled': bool(cleaned.get('notification_badge_enabled', True)),
                },
                'bridge': {
                    'django_messages_enabled': bool(cleaned.get('notification_bridge_enabled', False)),
                },
                'email': {
                    'enabled': notification_email_enabled,
                    'default': bool(notification_email_enabled and cleaned.get('notification_email_default', False)),
                },
                'automatic': {
                    'scoped_model_crud': bool(cleaned.get('notification_auto_crud_enabled', True)),
                    'create': bool(cleaned.get('notification_auto_create', True)),
                    'update': cleaned.get('notification_auto_update') or 'summary',
                    'delete': bool(cleaned.get('notification_auto_delete', True)),
                    'actor_flash_actions': ['create', 'delete', 'error'],
                    'watchable': True,
                },
            })
        if cleaned.get('registration_activation_mode') not in REGISTRATION_ACTIVATION_VALUES:
            cleaned['registration_activation_mode'] = 'auto_login_after_verify'
        email_ready = get_email_service_status().get('available')
        backend = getattr(settings, 'EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
        local_backends = {
            'django.core.mail.backends.console.EmailBackend',
            'django.core.mail.backends.locmem.EmailBackend',
            'django.core.mail.backends.filebased.EmailBackend',
        }
        if backend in local_backends and getattr(settings, 'DEBUG', False):
            email_ready = True
        elif email_config.get('transport') == 'relay':
            relay_host = str(email_config.get('host') or os.getenv('SMTP_RELAY_HOST') or '').strip()
            relay_port = email_config.get('port')
            relay_from_email = str(
                email_config.get('default_from_email')
                or getattr(settings, 'DEFAULT_FROM_EMAIL', '')
                or os.getenv('DEFAULT_FROM_EMAIL')
                or ''
            ).strip()
            relay_password_ok = True
            if email_config.get('secret_storage') == 'encrypted_db' and email_config.get('username'):
                relay_password_ok = bool(email_config.get('encrypted_password'))
            email_ready = bool(relay_host and relay_port and relay_from_email and relay_password_ok)
        elif email_config.get('secret_storage') == 'encrypted_db':
            email_ready = bool(
                email_config.get('host')
                and email_config.get('port')
                and email_config.get('default_from_email')
                and (not email_config.get('username') or email_config.get('encrypted_password'))
            )
        elif backend == 'django.core.mail.backends.smtp.EmailBackend':
            email_ready = bool(
                (email_config.get('host') or getattr(settings, 'EMAIL_HOST', ''))
                and (email_config.get('port') or getattr(settings, 'EMAIL_PORT', None))
                and (
                    email_config.get('default_from_email')
                    or getattr(settings, 'DEFAULT_FROM_EMAIL', '')
                )
            )
        if not email_ready:
            cleaned['notification_email_enabled'] = False
            cleaned['notification_email_default'] = False
            notification_config = cleaned.get('notification_config')
            if isinstance(notification_config, dict):
                notification_config = {
                    **notification_config,
                    'email': {
                        'enabled': False,
                        'default': False,
                    },
                }
                cleaned['notification_config'] = normalize_notification_config(notification_config)
        if (cleaned.get('public_registration_enabled') or cleaned.get('email_2fa')) and not email_ready:
            self.add_error(
                'email_config',
                "Public registration and email 2FA require configured email delivery. Use env/secrets, the generated internal SMTP relay with a saved upstream secret, local debug email backends during development, or encrypted DB mode with a saved SMTP secret.",
            )
        return cleaned


    def save(self, commit=True):
        instance = super().save(commit=False)
        self._apply_extra_features(instance)
        project_homepage = normalize_homepage_config(getattr(settings, 'DLUX_CONFIG', {}))
        fallback_home = project_homepage['default_url']
        auth_config = self.cleaned_data.get('auth_config') or default_auth_config()
        layout_config = self.cleaned_data.get('layout_config') or {}
        public_root_config = self.cleaned_data.get('public_root_config') or {}
        homepage_config = self.cleaned_data.get('homepage_config') or default_homepage_config()
        search_config = self.cleaned_data.get('search_config') or default_search_config()
        registration_config = self.cleaned_data.get('registration_config') or {}
        apply_system_settings_import(instance, {
            'system_names': self.cleaned_data.get('system_names', {}),
            'languages': self.cleaned_data.get('languages', normalize_language_catalog()),
            'translations_override': self.cleaned_data.get('translations_override', {}),
            'home_url': self.cleaned_data.get('home_url') or fallback_home,
            'homepage_config': homepage_config,
            'default_language': self.cleaned_data.get('default_language') or 'en',
            'default_theme': self.cleaned_data.get('default_theme') or 'light',
            'allowed_themes': self.cleaned_data.get('allowed_themes', list(normalize_allowed_themes())),
            'allow_user_theme_override': bool(self.cleaned_data.get('allow_user_theme_override', True)),
            'theme_picker_location': self.cleaned_data.get(
                'theme_picker_location', DEFAULT_THEME_PICKER_LOCATION,
            ),
            'allowed_fonts': self.cleaned_data.get('allowed_fonts', []),
            'default_fonts': self.cleaned_data.get('default_fonts', {}),
            'allow_user_font_override': bool(self.cleaned_data.get('allow_user_font_override', True)),
            'allow_user_language_override': bool(self.cleaned_data.get('allow_user_language_override', True)),
            # options_style is a JSON-only layout key (no legacy column); pass it
            # flat so apply_system_settings_import routes it into layout_config.
            'options_style': layout_config.get('options_style', DEFAULT_OPTIONS_STYLE),
            'row_actions_style': layout_config.get('row_actions_style', DEFAULT_ROW_ACTIONS_STYLE),
            'default_table_density': layout_config.get(
                'default_table_density',
                self.cleaned_data.get('default_table_density', DEFAULT_TABLE_DENSITY),
            ),
            'default_form_density': layout_config.get(
                'default_form_density',
                self.cleaned_data.get('default_form_density', DEFAULT_FORM_DENSITY),
            ),
            'default_modal_size': layout_config.get(
                'default_modal_size',
                self.cleaned_data.get('default_modal_size', DEFAULT_MODAL_SIZE),
            ),
            'sticky_table_headers': bool(layout_config.get(
                'sticky_table_headers',
                self.cleaned_data.get('sticky_table_headers', True),
            )),
            'resizable_table_columns': bool(layout_config.get(
                'resizable_table_columns',
                self.cleaned_data.get('resizable_table_columns', True),
            )),
            'zebra_striping': bool(layout_config.get(
                'zebra_striping',
                self.cleaned_data.get('zebra_striping', True),
            )),
            'show_audit_fields': bool(layout_config.get(
                'show_audit_fields',
                self.cleaned_data.get('show_audit_fields', False),
            )),
            'show_soft_deleted': bool(layout_config.get(
                'show_soft_deleted',
                self.cleaned_data.get('show_soft_deleted', False),
            )),
            'footer_enabled': bool(layout_config.get(
                'footer_enabled',
                self.cleaned_data.get('footer_enabled', True),
            )),
            'footer_text': layout_config.get(
                'footer_text',
                self.cleaned_data.get('footer_text', ''),
            ),
            'footer_link_text': layout_config.get(
                'footer_link_text',
                self.cleaned_data.get('footer_link_text', ''),
            ),
            'footer_link_url': layout_config.get(
                'footer_link_url',
                self.cleaned_data.get('footer_link_url', ''),
            ),
            'email_2fa': bool(auth_config.get('email_2fa', False)),
            'forgot_password_enabled': bool(auth_config.get('forgot_password_enabled', False)),
            'prevent_multiple_active_sessions': bool(auth_config.get('prevent_multiple_active_sessions', False)),
            'login_lockout_enabled': bool(auth_config.get('login_lockout_enabled', True)),
            'login_lockout_threshold': auth_config.get('login_lockout_threshold', 5),
            'login_lockout_window_minutes': auth_config.get('login_lockout_window_minutes', 15),
            'login_lockout_duration_minutes': auth_config.get('login_lockout_duration_minutes', 15),
            'enforce_strong_passwords': bool(auth_config.get('enforce_strong_passwords', False)),
            'strong_password_min_length': auth_config.get('strong_password_min_length', 12),
            'purge_session_on_exit': bool(auth_config.get('purge_session_on_exit', False)),
            'inactivity_timeout_enabled': bool(auth_config.get('inactivity_timeout_enabled', False)),
            'inactivity_timeout_minutes': auth_config.get('inactivity_timeout_minutes', 10),
            'client_ip_config': self.cleaned_data.get('client_ip_config', default_client_ip_config()),
            'public_root': bool(public_root_config.get('public_root', False)),
            'public_root_split_enabled': bool(public_root_config.get('public_root_split_enabled', False)),
            'public_root_url': str(public_root_config.get('public_root_url') or '').strip(),
            'public_root_theme': str(public_root_config.get('public_root_theme') or '').strip(),
            'public_root_title': str(public_root_config.get('public_root_title') or '').strip(),
            'public_root_meta_description': str(public_root_config.get('public_root_meta_description') or '').strip(),
            'show_titlebar_on_public': bool(public_root_config.get('show_titlebar_on_public', False)),
            'show_sidebar_on_public': bool(public_root_config.get('show_sidebar_on_public', False)),
            'public_registration_enabled': bool(registration_config.get('public_registration_enabled', False)),
            'registration_activation_mode': registration_config.get('registration_activation_mode'),
            'registration_throttle_enabled': bool(registration_config.get('registration_throttle_enabled', True)),
            'honeypot_enabled': bool(registration_config.get('honeypot_enabled', True)),
            'privacy_policy_url': registration_config.get('privacy_policy_url', ''),
            'terms_url': registration_config.get('terms_url', ''),
            'privacy_notice_text': registration_config.get('privacy_notice_text', ''),
            'registration_require_consent': bool(registration_config.get('registration_require_consent', False)),
            'email_config': self.cleaned_data.get('email_config', default_email_config()),
            'sidebar_config': self.cleaned_data.get('sidebar_config', {'home_url_name': None, 'entries': []}),
            'navbar_config': self.cleaned_data.get('navbar_config', default_navbar_config()),
            'log_config': self.cleaned_data.get('log_config', default_log_config()),
            'profile_config': self.cleaned_data.get('profile_config', default_profile_config()),
            'backup_config': self.cleaned_data.get('backup_config', default_backup_config()),
            'titlebar_config': self.cleaned_data.get('titlebar_config', default_titlebar_config()),
            'search_config': search_config,
            'notification_config': self.cleaned_data.get('notification_config', default_notification_config()),
            'login_config': self.cleaned_data.get('login_config', default_login_config()),
        }, commit=False, preserve_email_secret=True)
        imported = getattr(self, '_imported_settings', {}) or {}
        imported_assets = {
            field_name: imported[field_name]
            for field_name in ('logo', 'favicon', 'login_logo', 'login_background')
            if imported.get(field_name)
        }
        if imported_assets:
            apply_system_settings_import(
                instance,
                imported_assets,
                mark_configured=False,
                commit=False,
            )
        if isinstance(instance.sidebar_config, dict):
            instance.sidebar_config['home_url_name'] = None

        if commit:
            with transaction.atomic():
                instance.logo_asset = self._resolve_asset_selection(
                    'logo',
                    getattr(instance, 'logo_asset', None),
                    legacy_file=getattr(instance, 'logo', None),
                )
                instance.favicon_asset = self._resolve_asset_selection(
                    'favicon',
                    getattr(instance, 'favicon_asset', None),
                    legacy_file=getattr(instance, 'favicon', None),
                )
                instance.login_logo_asset = self._resolve_asset_selection(
                    'login_logo',
                    getattr(instance, 'login_logo_asset', None),
                )
                instance.login_background_asset = self._resolve_asset_selection(
                    'login_background',
                    getattr(instance, 'login_background_asset', None),
                )
                if instance.logo_asset_id:
                    instance.logo = None
                elif isinstance(self.cleaned_data.get('logo'), AssetSelection) and self.cleaned_data['logo'].clear:
                    instance.logo = None
                if instance.favicon_asset_id:
                    instance.favicon = None
                elif isinstance(self.cleaned_data.get('favicon'), AssetSelection) and self.cleaned_data['favicon'].clear:
                    instance.favicon = None
                instance.save()
        else:
            logo_selection = self.cleaned_data.get('logo')
            favicon_selection = self.cleaned_data.get('favicon')
            login_logo_selection = self.cleaned_data.get('login_logo')
            login_background_selection = self.cleaned_data.get('login_background')
            if isinstance(logo_selection, AssetSelection) and (logo_selection.asset is not None or logo_selection.clear):
                instance.logo_asset = logo_selection.asset
            if isinstance(favicon_selection, AssetSelection) and (favicon_selection.asset is not None or favicon_selection.clear):
                instance.favicon_asset = favicon_selection.asset
            if isinstance(login_logo_selection, AssetSelection) and (login_logo_selection.asset is not None or login_logo_selection.clear):
                instance.login_logo_asset = login_logo_selection.asset
            if isinstance(login_background_selection, AssetSelection) and (login_background_selection.asset is not None or login_background_selection.clear):
                instance.login_background_asset = login_background_selection.asset
        return instance

    def _apply_extra_features(self, instance):
        """Write the Extra Features toggles into `extra_config`.

        Copy-then-set: `extra_config` also carries every downstream project's own
        config under `app`, so this must never rebuild the dict. Only saves that
        actually rendered the step may write, or a single-step save of another
        step would silently reset the toggle.
        """
        if 'scanlink_enabled' not in self.cleaned_data:
            return
        if self.single_step_mode and self.single_step_index != SETUP_STEP_EXTRAS:
            return
        extra_config = dict(getattr(instance, 'extra_config', None) or {})
        scanlink = dict(extra_config.get('scanlink') or {}) if isinstance(extra_config.get('scanlink'), dict) else {}
        scanlink['enabled'] = bool(self.cleaned_data.get('scanlink_enabled', False))
        extra_config['scanlink'] = scanlink
        instance.extra_config = extra_config
