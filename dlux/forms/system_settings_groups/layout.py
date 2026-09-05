"""The settings wizard layout.

Mixed into SystemSettingsForm; see dlux/forms/system_settings.py.
"""

from crispy_forms.layout import Layout, Field, Div, HTML, Row
from crispy_forms.bootstrap import FormActions
from django.urls import NoReverseMatch, reverse
from ...system.constants import (
    SETUP_STEP_IDENTITY,
    SETUP_STEP_INDEX,
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
    SETUP_STEP_RIBBON,
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
from django.urls import reverse
from ..builders import EMAIL_DEPENDENT_SETTING_FIELDS, _bind_choice_selector_widget, _build_file_widget, _get_ui_direction, build_file_field, build_email_test_control, build_email_toggle_field, build_settings_toggle_field, build_titlebar_actions_order_builder


class LayoutMixin:
    def _step_badge(self, strings, slug, fallback):
        """The "Step N: Name" pill inside a wizard panel.

        Both halves are derived: the number is the step's position in
        `SETUP_STEPS`, and the name is the same string the nav and the Options
        tile show. Before this each call spelled out its own number in a
        positional translation key, and the Ribbon panel had drifted to
        announcing itself as step 18 while rendering fourteenth.
        """
        if self.mode != 'setup':
            return HTML('')
        number = SETUP_STEP_INDEX[slug] + 1
        label = strings.get(f'system_settings_{slug}', fallback)
        label = f"{strings.get('system_setup_step_prefix', 'Step')} {number}: {label}"
        return HTML(
            f"<div class='dlux-setup-step-badge mb-3'>"
            f"<span class='badge rounded-pill text-bg-primary'>{label}</span>"
            f"</div>"
        )

    def _step_css_class(self, index):
        """Wizard-step visibility class. Was a closure inside __init__; it only
        ever read `self`, so it is a plain method now."""
        classes = ['wizard-step']
        if self.single_step_mode and self.single_step_index != index:
            classes.append('d-none')
        elif not self.single_step_mode and index > 0:
            classes.append('d-none')
        return ' '.join(classes)

    def _build_layout(self, *, s, step_1_fields, email_password_field_class, field_name):
        """The crispy Layout for the settings wizard.

        Extracted verbatim from __init__ — it was the last statement there and the
        largest single expression in the package. It reads only the locals passed
        in explicitly, so moving it changes nothing about how it is built.
        """
        return Layout(
                    HTML(
                        f"<div class='dlux-system-settings-shell mode-{self.mode}'>"
                    ),
                    Div(
                        *step_1_fields,
                        # Footer lives in Identity — it's branding/credit copy for every page.
                        HTML(f"<hr class='my-4'><h6 class='fw-bold my-3'>{s.get('footer_settings_title', 'Footer')}</h6>"),
                        Row(
                            build_settings_toggle_field(self, 'footer_enabled', css_class='col-12'),
                            css_class='g-3 mb-3',
                        ),
                        Row(
                            Div(Field('footer_text', dir='auto'), css_class='col-12'),
                            css_class='mb-3'
                        ),
                        Row(
                            Div(Field('footer_link_text', dir='auto'), css_class='col-12 col-lg-6'),
                            Div(Field('footer_link_url', dir='ltr'), css_class='col-12 col-lg-6'),
                            css_class='mb-3'
                        ),
                        css_class=self._step_css_class(SETUP_STEP_IDENTITY),
                    ),
                    Div(
                        self._step_badge(s, 'languages', 'Languages'),
                        HTML(self.language_catalog_html),
                        Row(
                            Div(Field('default_language'), css_class='d-none'),
                            build_settings_toggle_field(self, 'allow_user_language_override', css_class='col-lg-12'),
                            css_class='mb-3',
                        ),
                        HTML(self.translation_matrix_html),
                        Field('languages'),
                        Field('translations_override'),
                        css_class=self._step_css_class(SETUP_STEP_LANGUAGES),
                    ),
                    Div(
                        self._step_badge(s, 'email', 'Email'),
                        HTML(f"<h6 class='fw-bold my-3'>{s.get('email_delivery_settings_title', 'Email Delivery')}</h6>"),
                        HTML(f"<p class='small text-muted mb-3'>{s.get('email_step_intro', '')}</p>"),
                        Row(
                            build_settings_toggle_field(self, 'email_config_enabled', css_class='col-lg-12'),
                            css_class='g-3 mb-3',
                        ),
                        HTML(
                            f"<div class='dlux-dependent-settings dlux-email-config-section"
                            f"{'' if self.initial.get('email_config_enabled', False) else ' is-disabled'}' "
                            f"aria-disabled='{'false' if self.initial.get('email_config_enabled', False) else 'true'}' "
                            f"data-email-config-section>"
                            f"<p class='small text-muted mb-3'>"
                            f"{s.get('email_delivery_settings_desc', 'Visible when public signup or email 2FA is enabled. If the web service is isolated, choose Internal SMTP relay and enter the upstream SMTP server below; the generated relay reads this UI config and handles internet egress. If the web service can reach SMTP directly, choose Direct SMTP from web service. Use Encrypted database secret for UI-managed passwords, or Environment / secrets when deployers intentionally keep mail secrets outside the UI.')}"
                            f"</p>"
                        ),
                        HTML(f"<h6 class='fw-bold my-3'>{s.get('email_delivery_path_title', 'Delivery Path')}</h6>"),
                        Row(
                            Div(Field('email_config_transport'), css_class='col-12 col-lg-6'),
                            Div(Field('email_config_secret_storage'), css_class='col-12 col-lg-6'),
                            css_class='g-3 mb-3',
                        ),
                        Row(
                            Div(Field('email_config_provider_preset'), css_class='col-12'),
                            css_class='g-3 mb-3',
                        ),
                        HTML(f"<h6 class='fw-bold my-3'>{s.get('email_connection_settings_title', 'SMTP Connection')}</h6>"),
                        Row(
                            build_email_toggle_field(self, 'email_config_use_tls', css_class='col-6 col-lg-3'),
                            build_email_toggle_field(self, 'email_config_use_ssl', css_class='col-6 col-lg-3'),
                            css_class='g-3 mb-3',
                        ),
                        Row(
                            Div(Field('email_config_host'), css_class='col-12 col-lg-6'),
                            Div(Field('email_config_port'), css_class='col-6 col-lg-3'),
                            Div(Field('email_config_timeout'), css_class='col-6 col-lg-3'),
                            css_class='g-3 mb-3',
                        ),
                        Row(
                            Div(Field('email_config_username'), css_class='col-12 col-lg-6'),
                            Div(Field('email_config_password'), css_class=email_password_field_class),
                            css_class='g-3 mb-3',
                        ),
                        HTML(f"<h6 class='fw-bold my-3'>{s.get('email_sender_settings_title', 'Sender & Alerts')}</h6>"),
                        Row(
                            Div(Field('email_config_default_from_email'), css_class='col-12 col-lg-6'),
                            Div(Field('email_config_failure_recipients'), css_class='col-12 col-lg-6'),
                            css_class='g-3 mb-3',
                        ),
                        Field('email_config'),
                        HTML(
                            "<div class='d-flex flex-wrap align-items-center justify-content-between gap-2 mb-3'>"
                            "<span class='dlux-email-status small text-muted'>"
                            f"<i class='bi bi-info-circle me-1'></i>{s.get('email_service_status_label', 'Email service')}: "
                            f"<code>{get_email_service_status().get('reason', 'unknown')}</code></span>"
                            "<button type='button' class='btn btn-outline-secondary dlux-email-apply-btn' "
                            "data-email-apply "
                            f"data-email-apply-url='{reverse('email_config_apply')}'>"
                            "<span class='spinner-border spinner-border-sm me-2 d-none' role='status' "
                            "aria-hidden='true' data-email-apply-spinner></span>"
                            f"{s.get('email_apply_button', 'Apply email settings')}</button>"
                            "</div>"
                            "<div class='small mb-2' data-email-apply-result aria-live='polite'></div>"
                        ),
                        Row(
                            build_email_test_control(
                                self, reverse('email_send_test'),
                                s.get('email_send_test_button', 'Send test email'),
                            ),
                            css_class='g-3',
                        ),
                        HTML("<div class='small mt-2' data-email-send-test-result aria-live='polite'></div>"),
                        HTML("</div>"),
                        css_class=self._step_css_class(SETUP_STEP_EMAIL),
                    ),
                    Div(
                        self._step_badge(s, 'security', 'Access & Security'),
                        HTML(f"<h6 class='fw-bold my-3'>{s.get('access_security_settings_title', s.get('system_settings_security', 'Access & Security'))}</h6>"),
                        Row(
                            build_settings_toggle_field(self, 'email_2fa', css_class='col-lg-6'),
                            build_settings_toggle_field(self, 'forgot_password_enabled', css_class='col-lg-6'),
                            build_settings_toggle_field(self, 'prevent_multiple_active_sessions', css_class='col-lg-6'),
                            build_settings_toggle_field(self, 'login_lockout_enabled', css_class='col-lg-6'),
                            build_settings_toggle_field(self, 'enforce_strong_passwords', css_class='col-lg-6'),
                            build_settings_toggle_field(self, 'purge_session_on_exit', css_class='col-lg-6'),
                            build_settings_toggle_field(self, 'inactivity_timeout_enabled', css_class='col-lg-6'),
                            css_class='g-3 mb-3',
                        ),
                        # Lockout tuning — revealed only while the lockout toggle is on
                        # (same reveal idiom as the client-ip proxy-hops field).
                        Row(
                            Div(Field('login_lockout_threshold', css_class='form-control'), css_class='col-12 col-lg-4'),
                            Div(Field('login_lockout_window_minutes', css_class='form-control'), css_class='col-12 col-lg-4'),
                            Div(Field('login_lockout_duration_minutes', css_class='form-control'), css_class='col-12 col-lg-4'),
                            css_class=(
                                "g-3 mb-3 dlux-auth-lockout-fields"
                                f"{'' if self.initial.get('login_lockout_enabled', True) else ' d-none'}"
                            ),
                            data_auth_lockout_fields='true',
                            aria_hidden='false' if self.initial.get('login_lockout_enabled', True) else 'true',
                        ),
                        # Independent conditional controls share one compact row.
                        Row(
                            Div(
                                Field('strong_password_min_length', css_class='form-control'),
                                css_class=(
                                    "col-12 col-lg-4 dlux-auth-strong-fields"
                                    f"{'' if self.initial.get('enforce_strong_passwords', False) else ' d-none'}"
                                ),
                                data_auth_strong_fields='true',
                                aria_hidden='false' if self.initial.get('enforce_strong_passwords', False) else 'true',
                            ),
                            Div(
                                Field('inactivity_timeout_minutes', css_class='form-control'),
                                css_class=(
                                    "col-12 col-lg-4 dlux-auth-inactivity-fields"
                                    f"{'' if self.initial.get('inactivity_timeout_enabled', False) else ' d-none'}"
                                ),
                                data_auth_inactivity_fields='true',
                                aria_hidden='false' if self.initial.get('inactivity_timeout_enabled', False) else 'true',
                            ),
                            css_class='g-3 mb-3 dlux-auth-conditional-fields',
                            data_auth_conditional_fields='true',
                        ),
                        Field('auth_config'),
                        HTML(f"<h6 class='fw-bold my-3'>{s.get('record_visibility_settings_title', 'Record Visibility')}</h6>"),
                        Row(
                            build_settings_toggle_field(self, 'show_audit_fields', css_class='col-12 col-lg-6'),
                            build_settings_toggle_field(self, 'show_soft_deleted', css_class='col-12 col-lg-6'),
                            css_class='g-3 mb-3',
                        ),
                        HTML(f"<h6 class='fw-bold my-3'>{s.get('client_ip_settings_title')}</h6>"),
                        HTML(
                            f"<p class='small text-muted mb-3'>"
                            f"{s.get('client_ip_settings_desc')}"
                            f"</p>"
                        ),
                        Row(
                            Div(Field('client_ip_mode'), css_class='col-12'),
                            css_class='g-3 mb-3',
                        ),
                        Row(
                            Div(
                                Field('client_ip_trusted_proxy_hops'),
                                css_class=(
                                    "col-12 col-lg-6 dlux-client-ip-hops-field"
                                    f"{' d-none' if self.initial.get('client_ip_mode') != CLIENT_IP_MODE_X_FORWARDED_FOR else ''}"
                                ),
                                data_client_ip_hops='true',
                                aria_hidden='false' if self.initial.get('client_ip_mode') == CLIENT_IP_MODE_X_FORWARDED_FOR else 'true',
                            ),
                            Div(
                                Field('client_ip_custom_header'),
                                css_class=(
                                    "col-12 col-lg-6 dlux-client-ip-custom-header-field"
                                    f"{' d-none' if self.initial.get('client_ip_mode') != CLIENT_IP_MODE_CUSTOM else ''}"
                                ),
                                data_client_ip_custom_header='true',
                                aria_hidden='false' if self.initial.get('client_ip_mode') == CLIENT_IP_MODE_CUSTOM else 'true',
                            ),
                            css_class='g-3 mb-3',
                        ),
                        Field('client_ip_config'),
                        HTML(f"<h6 class='fw-bold my-3'>{s.get('public_registration_settings_title', 'Public Registration')}</h6>"),
                        Row(
                            build_settings_toggle_field(self, 'public_registration_enabled', css_class='col-lg-12'),
                            css_class='g-3 mb-3',
                        ),
                        Row(
                            build_settings_toggle_field(
                                self,
                                'registration_throttle_enabled',
                                css_class=f"col-12 col-lg-4 dlux-public-registration-dependent dlux-dependent-settings{'' if self.initial.get('public_registration_enabled', False) else ' is-disabled'}",
                                attrs={
                                    'data_public_registration_dependent': 'true',
                                    'aria_disabled': 'false' if self.initial.get('public_registration_enabled', False) else 'true',
                                },
                            ),
                            build_settings_toggle_field(
                                self,
                                'honeypot_enabled',
                                css_class=f"col-12 col-lg-4 dlux-public-registration-dependent dlux-dependent-settings{'' if self.initial.get('public_registration_enabled', False) else ' is-disabled'}",
                                attrs={
                                    'data_public_registration_dependent': 'true',
                                    'aria_disabled': 'false' if self.initial.get('public_registration_enabled', False) else 'true',
                                },
                            ),
                            build_settings_toggle_field(
                                self,
                                'registration_require_consent',
                                css_class=f"col-12 col-lg-4 dlux-public-registration-dependent dlux-dependent-settings{'' if self.initial.get('public_registration_enabled', False) else ' is-disabled'}",
                                attrs={
                                    'data_public_registration_dependent': 'true',
                                    'aria_disabled': 'false' if self.initial.get('public_registration_enabled', False) else 'true',
                                },
                            ),
                            css_class='g-3 mb-3',
                        ),
                        Row(
                            Div(
                                Field('registration_activation_mode'),
                                css_class=f"col-12 dlux-public-registration-dependent dlux-dependent-settings{'' if self.initial.get('public_registration_enabled', False) else ' is-disabled'}",
                                data_public_registration_dependent='true',
                                aria_disabled='false' if self.initial.get('public_registration_enabled', False) else 'true',
                            ),
                            css_class='g-3',
                        ),
                        # Privacy links + notice apply to BOTH the sign-in and sign-up
                        # pages, so they are shown regardless of the registration toggle.
                        HTML(f"<h6 class='fw-bold my-3'>{s.get('privacy_settings_title', 'Privacy & Consent')}</h6>"),
                        HTML(f"<p class='small text-muted mb-3'>{s.get('privacy_settings_desc', 'Point users to your own privacy policy and terms. DjangoLux does not supply legal text — see the Data &amp; Privacy documentation for what personal data it stores.')}</p>"),
                        Row(
                            Div(Field('privacy_policy_url'), css_class='col-lg-6'),
                            Div(Field('terms_url'), css_class='col-lg-6'),
                            Div(Field('privacy_notice_text', dir='auto'), css_class='col-lg-12'),
                            css_class='g-3 mb-3',
                        ),
                        css_class=self._step_css_class(SETUP_STEP_SECURITY),
                    ),
                    Div(
                        self._step_badge(s, 'appearance', 'Themes & Fonts'),
                        Row(
                            Div(
                                HTML(self.theme_picker_html),
                                Field('default_theme'),
                                css_class='mb-3'
                            ),
                        ),
                        Row(
                            build_settings_toggle_field(self, 'allow_user_theme_override', css_class='col-12')
                        ),
                        Row(
                            Div(
                                Field('theme_picker_location'),
                                css_class=(
                                    'col-12 dlux-theme-picker-location dlux-dependent-settings'
                                    + ('' if self.initial.get('allow_user_theme_override', True) else ' is-disabled')
                                ),
                                data_theme_picker_location='true',
                                data_sidebar_hostable='true' if self._sidebar_toolbar_hostable else 'false',
                                aria_disabled='false' if self.initial.get('allow_user_theme_override', True) else 'true',
                            ),
                            css_class='g-3 mb-3',
                        ),
                        HTML(f"<h6 class='fw-bold my-3'>{s.get('typography_settings_title', 'Typography Settings')}</h6>"),
                        HTML(self.font_picker_html),
                        # Field('allowed_fonts'),
                        build_settings_toggle_field(self, 'allow_user_font_override', css_class='col-12 mt-2'),
                        HTML(self.language_fonts_editor_html),
                        Field('default_fonts'),
                        HTML(f"<h6 class='fw-bold my-3'>{s.get('edges_settings_title', 'Surfaces & Edges')}</h6>"),
                        Row(
                            Div(Field('table_edges'), css_class='col-12 col-lg-6'),
                            Div(Field('card_edges'), css_class='col-12 col-lg-6'),
                            css_class='g-3 mb-3'
                        ),
                        css_class=self._step_css_class(SETUP_STEP_APPEARANCE),
                    ),
                    Div(
                        self._step_badge(s, 'titlebar', 'Titlebar'),
                        HTML(f"<h6 class='fw-bold my-3'>{s.get('titlebar_settings_title', 'Titlebar Settings')}</h6>"),
                        Row(
                            build_settings_toggle_field(self, 'titlebar_show_title', css_class='col-lg-4'),
                            build_settings_toggle_field(self, 'titlebar_show_logo', css_class='col-lg-4'),
                            build_settings_toggle_field(self, 'titlebar_show_home_button', css_class='col-lg-4'),
                            css_class='g-3 mb-3',
                        ),
                        Row(
                            build_settings_toggle_field(self, 'titlebar_show_language_switcher', css_class='col-lg-6'),
                            build_settings_toggle_field(self, 'titlebar_accent_edge', css_class='col-lg-6'),
                            css_class='g-3 mb-3',
                        ),
                        Row(
                            Div(Field('titlebar_title_align'), css_class='col-lg-6'),
                            Div(Field('titlebar_title_size'), css_class='col-lg-6'),
                        ),
                        Row(
                            Div(Field('titlebar_home_shape'), css_class='col-lg-6'),
                            Div(Field('titlebar_height'), css_class='col-lg-6'),
                        ),
                        Row(
                            Div(Field('titlebar_user_hub_style'), css_class='col-lg-12'),
                            css_class='g-3 mb-3',
                        ),
                        Row(
                            Div(
                                Field('titlebar_actions_layout'),
                                css_class=(
                                    "col-lg-12 dlux-titlebar-actions-layout-dependent dlux-dependent-settings"
                                    f"{'' if self.initial.get('titlebar_user_hub_style') == TITLEBAR_USER_HUB_STYLE_ACTIONS else ' is-disabled'}"
                                ),
                                aria_disabled=(
                                    'false'
                                    if self.initial.get('titlebar_user_hub_style') == TITLEBAR_USER_HUB_STYLE_ACTIONS
                                    else 'true'
                                ),
                            ),
                            css_class='g-3 mb-3',
                        ),
                        HTML(self.titlebar_actions_order_html),
                        Field('titlebar_actions_order'),
                        Row(
                            Div(Field('titlebar_surface'), css_class='col-lg-12'),
                        ),
                        Row(
                            Div(
                                Field('titlebar_logo_treatment'),
                                css_class=(
                                    "col-lg-8 dlux-logo-treatment-primary dlux-titlebar-logo-dependent dlux-dependent-settings dlux-titlebar-logo-treatment-primary"
                                    f"{'' if self.initial.get('titlebar_show_logo', True) else ' is-disabled'}"
                                    f"{' dlux-logo-treatment-primary--wide' if self.initial.get('titlebar_show_logo', True) and self.initial.get('titlebar_logo_treatment', 'none') != 'plate' else ''}"
                                ),
                                aria_disabled='false' if self.initial.get('titlebar_show_logo', True) else 'true',
                            ),
                            Div(
                                Field('titlebar_logo_treatment_shape'),
                                css_class=(
                                    "col-lg-4 dlux-titlebar-logo-plate-dependent"
                                    f"{' d-none' if not (self.initial.get('titlebar_show_logo', True) and self.initial.get('titlebar_logo_treatment', 'none') == 'plate') else ''}"
                                ),
                                aria_hidden='false' if (
                                    self.initial.get('titlebar_show_logo', True)
                                    and self.initial.get('titlebar_logo_treatment', 'none') == 'plate'
                                ) else 'true',
                            ),
                            css_class='g-3 mb-3',
                        ),
                        css_class=self._step_css_class(SETUP_STEP_TITLEBAR),
                    ),
                    Div(
                        self._step_badge(s, 'sidebar', 'Sidebar'),
                        Row(
                            build_settings_toggle_field(self, 'sidebar_enabled', css_class='col-lg-12'),
                            css_class='g-3 mb-3',
                        ),
                        HTML(
                            f"<div class='alert alert-warning small mb-3{' d-none' if self.initial.get('sidebar_enabled', True) else ''}' "
                            f"data-sidebar-disabled-note>"
                            f"{s.get('sidebar_disabled_navigation_note', 'Disabling the sidebar can leave the app without built-in navigation. You will need to rely on dashboards and modals, or add your own back buttons and navigation entries in forms, lists, and dashboards. As of v2.2.0, Dynamic Sections Manager is only available through the sidebar, so add a dashboard button or custom entry if you need access. This warning will be updated if a built-in workaround is added later.')}"
                            f"</div>"
                        ),
                        HTML("<div class='dlux-sidebar-dependent-settings' data-sidebar-dependent>"),
                        HTML(
                            f"<div class='d-none' data-sidebar-tooling-state "
                            f"data-sections-manager-available=\"{'true' if self.sidebar_sections_manager_available else 'false'}\"></div>"
                        ),
                        Row(
                            build_settings_toggle_field(self, 'sidebar_enable_reorder', css_class='col-lg-6'),
                            build_settings_toggle_field(self, 'sidebar_enable_toolbar', css_class='col-lg-6'),
                            css_class='g-3 mb-3',
                        ),
                        Row(
                            build_settings_toggle_field(self, 'sidebar_show_sections_manager', css_class='col-lg-6'),
                            build_settings_toggle_field(self, 'sidebar_allow_user_density', css_class='col-lg-6'),
                            css_class='g-3 mb-3',
                        ),
                        Row(
                            build_settings_toggle_field(self, 'sidebar_show_icons', css_class='col-lg-6'),
                            build_settings_toggle_field(self, 'sidebar_accent_edge', css_class='col-lg-6'),
                            css_class='g-3 mb-3',
                        ),
                        Row(
                            build_settings_toggle_field(self, 'sidebar_show_notification_badges', css_class='col-lg-6'),
                            css_class='g-3 mb-3',
                        ),
                        HTML(
                            f"<div class='alert alert-warning small mb-3{' d-none' if self.initial.get('sidebar_enable_toolbar', True) and self.initial.get('sidebar_show_sections_manager', True) else ''}' "
                            f"data-sidebar-toolbar-note>"
                            f"{s.get('sidebar_toolbar_disable_note', 'Disabling the sidebar toolbar also removes the only built-in shortcut to Dynamic Sections Manager. If you still want UI access, enable system items in the sidebar builder and add Section Management to your sidebar.')}"
                            f"</div>"
                        ),
                        Row(
                            Div(Field('sidebar_density'), css_class='col-lg-6'),
                            Div(Field('sidebar_collapse_mode'), css_class='col-lg-6'),
                        ),
                        Row(
                            Div(HTML(self.sidebar_toggle_icon_html), css_class='col-lg-12'),
                            css_class='g-3 mb-3',
                        ),
                        HTML(self.sidebar_builder_html),
                        HTML("</div>"),
                        Field('sidebar_config'),
                        Field('sidebar_toggle_icon'),
                        css_class=self._step_css_class(SETUP_STEP_SIDEBAR),
                    ),
                    Div(
                        self._step_badge(s, 'navbar', 'Navbar'),
                        HTML(f"<h6 class='fw-bold my-3'>{s.get('navbar_settings_title', '')}</h6>"),

                        Row(
                            build_settings_toggle_field(self, 'navbar_enabled', css_class='col-lg-12'),
                            css_class='g-3 mb-3',
                        ),
                        HTML(
                            f"<div class='dlux-dependent-settings dlux-navbar-dependent-settings"
                            f"{'' if self.initial.get('navbar_enabled', False) else ' is-disabled'}' "
                            f"aria-disabled='{'false' if self.initial.get('navbar_enabled', False) else 'true'}' "
                            f"data-navbar-dependent>"
                        ),
                        Row(
                            build_settings_toggle_field(self, 'navbar_allow_user_mode_override', css_class='col-lg-12'),
                            css_class='g-3 mb-3',
                        ),
                        Div(Field('navbar_default_mode'), css_class='mb-3'),
                        HTML(self.navbar_builder_html),
                        HTML("</div>"),
                        Field('navbar_config'),
                        css_class=self._step_css_class(SETUP_STEP_NAVBAR),
                    ),
                    Div(
                        self._step_badge(s, 'ribbon', 'Ribbon'),
                        HTML(f"<h6 class='fw-bold my-3'>{s.get('ribbon_settings_title', 'List Page Ribbon')}</h6>"),
                        # Disabled by ribbon_settings.js under `compact`, which
                        # is a single row and so has no title to show.
                        Row(
                            build_settings_toggle_field(self, 'ribbon_title', css_class='col-12'),
                            css_class='g-3 mb-3',
                            data_dlux_ribbon_dependent='ribbon_title',
                        ),
                        Row(
                            Div(Field('ribbon_style'), css_class='col'),
                            css_class='mb-3'
                        ),
                        Row(
                            Div(Field('ribbon_layout'), css_class='col'),
                            css_class='mb-3'
                        ),
                        Row(
                            Div(Field('ribbon_advanced_trigger'), css_class='col'),
                            css_class='mb-3'
                        ),
                        Row(
                            Div(Field('ribbon_nesting'), css_class='col'),
                            css_class='mb-3'
                        ),
                        HTML(f"<h6 class='fw-bold my-3'>{s.get('ribbon_tabs_settings_title', 'Tab Strips')}</h6>"),
                        HTML(self.ribbon_builder_html),
                        Field('ribbon_config'),
                        css_class=self._step_css_class(SETUP_STEP_RIBBON),
                    ),
                    Div(
                        self._step_badge(s, 'layout', 'Layout'),
                        HTML(f"<h6 class='fw-bold my-3'>{s.get('tables_settings_title', 'Tables and Cards')}</h6>"),
                        Row(
                            build_settings_toggle_field(self, 'table_accent_edges', css_class='col-12 col-lg-6'),
                            build_settings_toggle_field(self, 'sticky_table_headers', css_class='col-12 col-lg-6'),
                            css_class='g-3 mb-3',
                        ),
                        Row(
                            build_settings_toggle_field(self, 'resizable_table_columns', css_class='col-12 col-lg-6'),
                            build_settings_toggle_field(self, 'zebra_striping', css_class='col-12 col-lg-6'),
                            css_class='g-3 mb-3',
                        ),
                        Row(
                            Div(Field('default_table_density'), css_class='col'),
                            css_class='mb-3'
                        ),
                        Row(
                            Div(Field('row_actions_style'), css_class='col'),
                            css_class='mb-3'
                        ),
                        HTML(f"<h6 class='fw-bold my-3'>{s.get('forms_settings_title', 'Forms')}</h6>"),
                        Row(
                            Div(Field('default_form_density'), css_class='col'),
                            css_class='mb-3'
                        ),
                        HTML(f"<h6 class='fw-bold my-3'>{s.get('modal_settings_title', 'Modals')}</h6>"),
                        Row(
                            Div(Field('default_modal_size'), css_class='col'),
                            css_class='mb-3'
                        ),
                        HTML(f"<h6 class='fw-bold my-3'>{s.get('options_page_settings_title', 'Options Page')}</h6>"),
                        Row(
                            Div(Field('options_style'), css_class='col'),
                            css_class='mb-3'
                        ),
                        css_class=self._step_css_class(SETUP_STEP_LAYOUT),
                    ),
                    Div(
                        self._step_badge(s, 'homepage', 'Homepage'),
                        HTML(f"<h6 class='fw-bold my-3'>{s.get('root_home_settings_title', 'Home & Public Page Destinations')}</h6>"),
                        Row(
                            Div(Field('home_url_discovered'), css_class='col-lg-6'),
                            Div(Field('home_url', dir='ltr'), css_class='col-lg-6'),
                        ),
                        Row(
                            build_settings_toggle_field(self, 'allow_user_home_url', css_class='col-lg-6'),
                            build_settings_toggle_field(self, 'public_root', css_class='col-lg-6'),
                            css_class='g-3 mb-3',
                        ),
                        Div(
                            Row(
                                build_settings_toggle_field(self, 'public_root_split_enabled', css_class='col-lg-12'),
                                css_class='g-3 mb-3',
                            ),
                            Row(
                                Div(
                                    Field('public_root_url_discovered'),
                                    css_class=(
                                        "col-lg-6 dlux-public-page-split-dependent dlux-dependent-settings"
                                        f"{'' if self.initial.get('public_root_split_enabled', False) else ' is-disabled'}"
                                    ),
                                    data_public_page_split_dependent='true',
                                    aria_disabled='false' if self.initial.get('public_root_split_enabled', False) else 'true',
                                ),
                                Div(
                                    Field('public_root_url', dir='ltr'),
                                    css_class=(
                                        "col-lg-6 dlux-public-page-split-dependent dlux-dependent-settings"
                                        f"{'' if self.initial.get('public_root_split_enabled', False) else ' is-disabled'}"
                                    ),
                                    data_public_page_split_dependent='true',
                                    aria_disabled='false' if self.initial.get('public_root_split_enabled', False) else 'true',
                                ),
                            ),
                            Row(
                                Div(Field('public_root_theme'), css_class='col-lg-12'),
                                css_class='g-3 mb-3',
                            ),
                            HTML(f"<h6 class='fw-bold my-3'>{s.get('public_root_identity_settings_title', 'Public Page Identity')}</h6>"),
                            Row(
                                Div(Field('public_root_title', dir='auto'), css_class='col-lg-6'),
                                Div(Field('public_root_meta_description', dir='auto'), css_class='col-lg-6'),
                                css_class='g-3 mb-3',
                            ),
                            Row(
                                build_settings_toggle_field(self, 'show_titlebar_on_public', css_class='col-lg-6'),
                                build_settings_toggle_field(self, 'show_sidebar_on_public', css_class='col-lg-6'),
                                css_class='g-3 mb-3',
                            ),
                            css_class=f"dlux-public-page-dependent dlux-dependent-settings{'' if self.initial.get('public_root', False) else ' is-disabled'}",
                            data_public_page_dependent='true',
                            aria_disabled='false' if self.initial.get('public_root', False) else 'true',
                        ),
                        Field('homepage_config'),
                        css_class=self._step_css_class(SETUP_STEP_HOMEPAGE),
                    ),
                    Div(
                        self._step_badge(s, 'login_page', 'Login Page'),
                        HTML(f"<h6 class='fw-bold my-3'>{s.get('login_page_settings_title', 'Login Page Settings')}</h6>"),
                        HTML(f"<p class='small text-muted mb-3'>{s.get('login_page_settings_desc', 'Choose the login page layout and customise the side banner and logo treatment.')}</p>"),
                        # Row 1: layout style — full width, as-is
                        Field('login_style'),
                        # Logo visibility toggle
                        Row(
                            build_settings_toggle_field(self, 'login_show_logo', css_class='col-12'),
                            css_class='g-3 mt-1 mb-2',
                        ),
                        Row(
                            Div(build_file_field('login_logo'), css_class='col-lg-6'),
                            Div(build_file_field('login_background'), css_class='col-lg-6'),
                            css_class='g-3 mb-2',
                        ),
                        # Row 2: hero message textareas — one column per language
                        Div(
                            HTML(
                                f"<h6 class='fw-bold mt-4 mb-2'>{s.get('form_sys_login_hero_message', 'Hero Message')}</h6>"
                                f"<p class='small text-muted mb-3'>{s.get('help_sys_login_hero_message', 'Text shown on the start half. Supports Markdown: **bold**, *italic*, # Heading, [link](url), lists.')}</p>"
                            ),
                            Row(
                                *[
                                    Div(
                                        Field(field_name),
                                        css_class=(
                                            'col-lg-6' if len(getattr(self, '_login_hero_lang_fields', [])) == 2
                                            else 'col-lg-4' if len(getattr(self, '_login_hero_lang_fields', [])) == 3
                                            else 'col-lg-3' if len(getattr(self, '_login_hero_lang_fields', [])) >= 4
                                            else 'col-12'
                                        ),
                                    )
                                    for _lang_code, _lang_label, field_name in getattr(self, '_login_hero_lang_fields', [])
                                ],
                                css_class='g-3',
                            ),
                            css_class=(
                                "dlux-login-hero-field"
                                f"{' d-none' if self.initial.get('login_style', 'split') != 'fullpage' else ''}"
                            ),
                            data_login_hero_field='true',
                            aria_hidden='false' if self.initial.get('login_style', 'split') == 'fullpage' else 'true',
                        ),
                        # Row 3: logo treatment + plate shape side by side
                        # col-lg-7 (4 tiles) vs col-lg-5 (3 tiles) gives near-equal tile widths:
                        # 7/12÷4 ≈ 14.6%  vs  5/12÷3 ≈ 13.9% — visually uniform.
                        # align-items-stretch ensures both grids share the same row height.
                        HTML(f"<h6 class='fw-bold mt-4 mb-2'>{s.get('form_sys_login_logo_treatment', 'Logo Treatment')}</h6>"),
                        Row(
                            Div(
                                Field('login_logo_treatment'),
                                css_class=(
                                    "col-lg-7 d-flex flex-column dlux-logo-treatment-primary dlux-login-logo-treatment-primary"
                                    f"{' dlux-logo-treatment-primary--wide' if self.initial.get('login_logo_treatment', 'none') != 'plate' else ''}"
                                ),
                            ),
                            Div(
                                Field('login_logo_treatment_shape'),
                                css_class=(
                                    "col-lg-5 d-flex flex-column dlux-login-plate-shape-field"
                                    f"{' d-none' if self.initial.get('login_logo_treatment', 'none') != 'plate' else ''}"
                                ),
                                data_login_plate_shape='true',
                                aria_hidden='false' if self.initial.get('login_logo_treatment', 'none') == 'plate' else 'true',
                            ),
                            css_class='g-3 align-items-stretch',
                        ),
                        # Row 4: optional banner colour (transparent by default)
                        Row(
                            Div(Field('login_banner_color'), css_class='col-lg-4'),
                            css_class='g-3 mt-2 mb-3',
                        ),
                        Field('login_config'),
                        css_class=self._step_css_class(SETUP_STEP_LOGIN),
                    ),
                    Div(
                        self._step_badge(s, 'profile', 'Profile Page'),
                        HTML(f"<h6 class='fw-bold my-3'>{s.get('profile_settings_title', 'Profile Page & Onboarding')}</h6>"),
                        HTML(self.profile_builder_html),
                        Field('profile_config'),
                        css_class=self._step_css_class(SETUP_STEP_PROFILE),
                    ),
                    Div(
                        self._step_badge(s, 'search', 'Global Search'),
                        HTML(f"<h6 class='fw-bold my-3'>{s.get('global_search_settings_title', 'Global Search')}</h6>"),
                        Row(
                            Div(Field('titlebar_global_search_mode'), css_class='col-lg-12'),
                            css_class='g-3 mb-3',
                        ),
                        Row(
                            build_settings_toggle_field(self, 'titlebar_global_search_include_data', css_class='col-lg-12'),
                            css_class=(
                                "g-3 mb-3 dlux-global-search-data-field"
                                f"{' d-none' if self.initial.get('titlebar_global_search_mode', 'icon') == 'disabled' else ''}"
                            ),
                            data_global_search_data_field='true',
                            aria_hidden='true' if self.initial.get('titlebar_global_search_mode', 'icon') == 'disabled' else 'false',
                        ),
                        Field('search_config'),
                        css_class=self._step_css_class(SETUP_STEP_SEARCH),
                    ),
                    Div(
                        self._step_badge(s, 'notifications', 'Notifications'),
                        HTML(f"<h6 class='fw-bold my-3'>{s.get('notification_settings_title', 'Notifications')}</h6>"),
                        Row(
                            build_settings_toggle_field(self, 'notifications_enabled', css_class='col-lg-12'),
                            css_class='g-3 mb-3',
                        ),
                        HTML(
                            f"<div class='dlux-dependent-settings dlux-notifications-dependent-settings"
                            f"{'' if self.initial.get('notifications_enabled', True) else ' is-disabled'}' "
                            f"aria-disabled='{'false' if self.initial.get('notifications_enabled', True) else 'true'}' "
                            f"data-notifications-dependent>"
                        ),
                        Row(
                            build_settings_toggle_field(self, 'notification_flash_enabled', css_class='col-lg-6 col-xl-3'),
                            build_settings_toggle_field(self, 'notification_drawer_enabled', css_class='col-lg-6 col-xl-3'),
                            build_settings_toggle_field(self, 'notification_badge_enabled', css_class='col-lg-6 col-xl-3'),
                            build_settings_toggle_field(self, 'notification_bridge_enabled', css_class='col-lg-6 col-xl-3'),
                            css_class='g-3 mb-3',
                        ),
                        Row(
                            build_settings_toggle_field(self, 'notification_auto_crud_enabled', css_class='col-lg-4'),
                            build_settings_toggle_field(self, 'notification_auto_create', css_class='col-lg-4'),
                            build_settings_toggle_field(self, 'notification_auto_delete', css_class='col-lg-4'),
                            css_class='g-3 mb-3',
                        ),
                        Row(
                            build_settings_toggle_field(self, 'notification_email_enabled', css_class='col-lg-6'),
                            build_settings_toggle_field(self, 'notification_email_default', css_class='col-lg-6'),
                            css_class='g-3 mb-3',
                        ),
                        # Position carries six options, so it takes the full row
                        # rather than being squeezed into a third of one.
                        Row(
                            Div(Field('notification_flash_position'), css_class='col-12'),
                            css_class='g-3 mb-3',
                        ),
                        Row(
                            Div(Field('notification_flash_size'), css_class='col-12 col-lg-6'),
                            Div(Field('notification_flash_text_size'), css_class='col-12 col-lg-6'),
                            css_class='g-3 mb-3',
                        ),
                        Row(
                            Div(Field('notification_auto_update'), css_class='col-12'),
                            css_class='g-3 mb-3',
                        ),
                        Row(
                            Div(Field('notification_flash_timeout_ms'), css_class='col-12 col-lg-6'),
                            Div(Field('notification_flash_max_visible'), css_class='col-12 col-lg-6'),
                            css_class='g-3 mb-3',
                        ),
                        HTML("</div>"),
                        Field('notification_config'),
                        css_class=self._step_css_class(SETUP_STEP_NOTIFICATIONS),
                    ),
                    Div(
                        self._step_badge(s, 'logging', 'Logging'),
                        HTML(f"<h6 class='fw-bold my-3'>{s.get('log_settings_title', 'Activity Logging')}</h6>"),
                        HTML(self.log_builder_html),
                        Field('log_config'),
                        css_class=self._step_css_class(SETUP_STEP_LOGGING),
                    ),
                    Div(
                        self._step_badge(s, 'backups', 'Backups'),
                        HTML(f"<h6 class='fw-bold my-3'>{s.get('backup_settings_title', 'System Backup Policy')}</h6>"),
                        HTML(f"<div class='alert alert-info'>{s.get('backup_settings_update_notice', 'Inline updates and rollbacks always create and verify a full system backup before maintenance. An update is stopped if that backup fails.')}</div>"),
                        build_settings_toggle_field(self, 'backup_scheduled_enabled', css_class='col-12'),
                        Row(
                            Div(Field('backup_schedule_interval_hours', css_class='form-control'), css_class='col-12 col-lg-4'),
                            Div(Field('backup_retention_days', css_class='form-control'), css_class='col-12 col-lg-4'),
                            Div(Field('backup_max_backups_to_keep', css_class='form-control'), css_class='col-12 col-lg-4'),
                            css_class='g-3',
                        ),
                        Field('backup_auto_export_target', css_class='form-control font-monospace', dir='ltr'),
                        HTML(f"<h6 class='fw-bold my-3'>{s.get('backup_settings_recovery_title', 'Interrupted Backup Recovery')}</h6>"),
                        build_settings_toggle_field(self, 'backup_auto_retry_enabled', css_class='col-12'),
                        Row(
                            Div(Field('backup_stall_timeout_minutes', css_class='form-control'), css_class='col-12 col-lg-4'),
                            Div(Field('backup_max_attempts', css_class='form-control'), css_class='col-12 col-lg-4'),
                            Div(Field('backup_retry_delay_minutes', css_class='form-control'), css_class='col-12 col-lg-4'),
                            css_class='g-3',
                        ),
                        Field('backup_config'),
                        css_class=self._step_css_class(SETUP_STEP_BACKUPS),
                    ),
                    Div(
                        self._step_badge(s, 'extras', 'Extra Features'),
                        HTML(f"<div class='alert alert-info'>{s.get('extras_settings_intro', 'Optional integrations that stay switched off until a deployment needs them. Each one is inert while disabled.')}</div>"),
                        HTML(f"<h6 class='fw-bold my-3'>{s.get('scanlink_settings_title', 'ScanLink Scanning')}</h6>"),
                        build_settings_toggle_field(self, 'scanlink_enabled', css_class='col-12'),
                        HTML(
                            f"<div class='mt-3'>"
                            f"<button type='button' class='btn btn-outline-primary rounded-pill px-4'"
                            f" data-dynamic-modal='{reverse('scanlink_releases_modal')}'"
                            f" data-modal-title=\"{s.get('scanlink_releases_title', 'ScanLink Releases')}\">"
                            f"<i class='bi bi-box-seam me-1'></i> "
                            f"{s.get('scanlink_manage_releases', 'Manage installers')}</button>"
                            f"<div class='form-text'>"
                            f"{s.get('scanlink_manage_releases_help', 'Publish the installer that workstations download and update from.')}"
                            f"</div></div>"
                        ),
                        css_class=self._step_css_class(SETUP_STEP_EXTRAS),
                    ),
                    FormActions(
                        HTML(
                            f"<div class='d-flex flex-wrap justify-content-end align-items-center gap-2 mt-4 dlux-setup-wizard-actions' dir='{_get_ui_direction()}'>"
                            f"<button type='submit' name='submit' class='btn btn-primary px-5 rounded-pill fw-bold dlux-btn-submit'>"
                            f"{s.get('btn_save', 'Save')}</button>"
                            f"</div>"
                        )
                    ) if self.single_step_mode else FormActions(
                        HTML(
                            f"<div class='d-flex flex-wrap justify-content-end align-items-center gap-2 mt-4 dlux-setup-wizard-actions' dir='{_get_ui_direction()}'>"
                            f"<button type='button' class='btn btn-outline-secondary rounded-pill px-4 dlux-btn-prev'>"
                            f"{s.get('btn_prev', 'Previous')}</button>"
                            f"<button type='button' class='btn btn-outline-primary rounded-pill px-4 dlux-btn-next'>"
                            f"{s.get('btn_next', 'Next')}</button>"
                            f"<button type='submit' name='submit' class='btn btn-primary px-5 rounded-pill fw-bold dlux-btn-submit'>"
                            f"{s.get('btn_save', 'Save')}</button>"
                            f"</div>"
                        )
                    ),
                    HTML("</div>")
                )
