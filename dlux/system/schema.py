"""Typed schema definitions for Dlux system settings."""

from dataclasses import dataclass, field
from typing import Any, Callable

from .constants import DEFAULT_OPTIONS_STYLE, DEFAULT_THEME_PICKER_LOCATION
from .defaults import (
    default_auth_config,
    default_backup_config,
    default_client_ip_config,
    default_email_config,
    default_extra_config,
    default_homepage_config,
    default_language_config,
    default_layout_config,
    default_log_config,
    default_login_config,
    default_navbar_config,
    default_notification_config,
    default_profile_config,
    default_public_root_config,
    default_registration_config,
    default_search_config,
    default_sidebar_config,
    default_theme_config,
    default_titlebar_config,
    default_typography_config,
)
from .normalizers import (
    normalize_auth_config,
    normalize_backup_config,
    normalize_client_ip_config,
    normalize_email_config,
    normalize_extra_config,
    normalize_homepage_config,
    normalize_language_config,
    normalize_layout_config,
    normalize_log_config,
    normalize_login_config,
    normalize_navbar_config,
    normalize_notification_config,
    normalize_profile_config,
    normalize_public_root_config,
    normalize_registration_config,
    normalize_search_config,
    normalize_sidebar_behavior,
    normalize_theme_config,
    normalize_titlebar_config,
    normalize_typography_config,
)


@dataclass(frozen=True)
class SettingField:
    key: str
    storage: tuple[str, str]
    form_name: str = ''
    field_type: str = 'str'
    default: Any = None
    label_key: str = ''
    help_key: str = ''
    widget: str = ''
    export: bool = True
    import_aliases: tuple[str, ...] = ()
    legacy_flat: bool = False


@dataclass(frozen=True)
class SettingGroup:
    key: str
    storage_field: str
    default_factory: Callable[[], dict]
    normalizer: Callable[..., dict]
    aliases: tuple[str, ...] = ()
    label_key: str = ''
    help_key: str = ''
    setup_step: str = ''
    admin_section: str = ''
    db_override_policy: str = 'configured_or_non_default'
    export: bool = True
    import_aliases: tuple[str, ...] = ()
    fields: tuple[SettingField, ...] = field(default_factory=tuple)


def _field(group, name, *, field_type='str', default=None, form_name='', widget='', legacy_flat=False, export=True):
    return SettingField(
        key=f'{group}.{name}',
        storage=(f'{group}_config', name),
        form_name=form_name or name,
        field_type=field_type,
        default=default,
        label_key=f'form_sys_{name}',
        help_key=f'help_sys_{name}',
        widget=widget,
        export=export,
        legacy_flat=legacy_flat,
        import_aliases=(name,) if legacy_flat else (),
    )


SYSTEM_SETTING_GROUPS = (
    SettingGroup(
        key='auth',
        storage_field='auth_config',
        aliases=('auth', 'authentication', 'security'),
        default_factory=default_auth_config,
        normalizer=normalize_auth_config,
        label_key='settings_access_security',
        setup_step='access_security',
        admin_section='security',
        fields=(
            _field('auth', 'email_2fa', field_type='bool', default=False, widget='switch', legacy_flat=True),
            _field('auth', 'forgot_password_enabled', field_type='bool', default=False, widget='switch', legacy_flat=True),
            _field('auth', 'prevent_multiple_active_sessions', field_type='bool', default=False, widget='switch', legacy_flat=True),
            _field('auth', 'login_lockout_enabled', field_type='bool', default=True, widget='switch', legacy_flat=True),
            _field('auth', 'login_lockout_threshold', field_type='int', default=5, legacy_flat=True),
            _field('auth', 'login_lockout_window_minutes', field_type='int', default=15, legacy_flat=True),
            _field('auth', 'login_lockout_duration_minutes', field_type='int', default=15, legacy_flat=True),
            _field('auth', 'enforce_strong_passwords', field_type='bool', default=False, widget='switch', legacy_flat=True),
            _field('auth', 'strong_password_min_length', field_type='int', default=12, legacy_flat=True),
            _field('auth', 'purge_session_on_exit', field_type='bool', default=False, widget='switch', legacy_flat=True),
            _field('auth', 'inactivity_timeout_enabled', field_type='bool', default=False, widget='switch', legacy_flat=True),
            _field('auth', 'inactivity_timeout_minutes', field_type='int', default=10, legacy_flat=True),
        ),
    ),
    SettingGroup(
        key='email',
        storage_field='email_config',
        aliases=('email', 'mail', 'smtp'),
        default_factory=default_email_config,
        normalizer=normalize_email_config,
        label_key='settings_email',
        setup_step='access_security',
        admin_section='security',
        fields=(
            _field('email', 'transport', default='direct', widget='choice'),
            _field('email', 'secret_storage', default='env', widget='choice'),
            _field('email', 'host'),
            _field('email', 'port', field_type='int', default=587),
            _field('email', 'use_tls', field_type='bool', default=True, widget='switch'),
            _field('email', 'use_ssl', field_type='bool', default=False, widget='switch'),
            _field('email', 'username'),
            _field('email', 'default_from_email', field_type='email'),
            _field('email', 'encrypted_password', export=False),
            _field('email', 'password_configured', field_type='bool', export=False),
        ),
    ),
    SettingGroup(
        key='registration',
        storage_field='registration_config',
        aliases=('registration', 'public_registration'),
        default_factory=default_registration_config,
        normalizer=normalize_registration_config,
        label_key='settings_registration',
        setup_step='access_security',
        admin_section='security',
        fields=(
            _field('registration', 'public_registration_enabled', field_type='bool', default=False, widget='switch', legacy_flat=True),
            _field('registration', 'registration_activation_mode', default='auto_login_after_verify', widget='choice', legacy_flat=True),
            _field('registration', 'registration_throttle_enabled', field_type='bool', default=True, widget='switch', legacy_flat=True),
            _field('registration', 'honeypot_enabled', field_type='bool', default=True, widget='switch', legacy_flat=True),
            _field('registration', 'privacy_policy_url', field_type='str', default='', legacy_flat=True),
            _field('registration', 'terms_url', field_type='str', default='', legacy_flat=True),
            _field('registration', 'privacy_notice_text', field_type='str', default='', legacy_flat=True),
            _field('registration', 'registration_require_consent', field_type='bool', default=False, widget='switch', legacy_flat=True),
        ),
    ),
    SettingGroup(
        key='public_root',
        storage_field='public_root_config',
        aliases=('public_root', 'public'),
        default_factory=default_public_root_config,
        normalizer=normalize_public_root_config,
        label_key='settings_public_root',
        setup_step='homepage',
        admin_section='routing',
        fields=(
            _field('public_root', 'public_root', field_type='bool', default=False, widget='switch', legacy_flat=True),
            _field('public_root', 'public_root_split_enabled', field_type='bool', default=False, widget='switch', legacy_flat=True),
            _field('public_root', 'public_root_url', legacy_flat=True),
            _field('public_root', 'public_root_theme', default='', widget='choice', legacy_flat=True),
            _field('public_root', 'public_root_title', default='', widget='text', legacy_flat=True),
            _field('public_root', 'public_root_meta_description', default='', widget='text', legacy_flat=True),
            _field('public_root', 'show_titlebar_on_public', field_type='bool', default=False, widget='switch', legacy_flat=True),
            _field('public_root', 'show_sidebar_on_public', field_type='bool', default=False, widget='switch', legacy_flat=True),
        ),
    ),
    SettingGroup(
        key='homepage',
        storage_field='homepage_config',
        aliases=('homepage', 'public_homepage'),
        default_factory=default_homepage_config,
        normalizer=normalize_homepage_config,
        label_key='system_settings_homepage',
        setup_step='homepage',
        admin_section='routing',
    ),
    SettingGroup(
        key='client_ip',
        storage_field='client_ip_config',
        aliases=('client_ip', 'ip', 'proxy'),
        default_factory=default_client_ip_config,
        normalizer=normalize_client_ip_config,
        label_key='settings_client_ip',
        setup_step='access_security',
        admin_section='security',
        fields=(
            _field('client_ip', 'mode', form_name='client_ip_mode', default='x_forwarded_for', widget='choice'),
            _field(
                'client_ip',
                'trusted_proxy_hops',
                form_name='client_ip_trusted_proxy_hops',
                field_type='int',
                default=1,
            ),
            _field('client_ip', 'custom_header', form_name='client_ip_custom_header'),
        ),
    ),
    SettingGroup(
        key='notification',
        storage_field='notification_config',
        aliases=('notifications', 'notification'),
        default_factory=default_notification_config,
        normalizer=normalize_notification_config,
        label_key='settings_notifications',
        setup_step='notifications',
        admin_section='notifications',
    ),
    SettingGroup(
        key='layout',
        storage_field='layout_config',
        aliases=('layout', 'ui_layout'),
        default_factory=default_layout_config,
        normalizer=normalize_layout_config,
        label_key='settings_layout',
        setup_step='appearance',
        admin_section='appearance',
        fields=(
            _field('layout', 'default_table_density', default='balanced', widget='choice', legacy_flat=True),
            _field('layout', 'default_form_density', default='balanced', widget='choice', legacy_flat=True),
            _field('layout', 'default_modal_size', default='standard', widget='choice', legacy_flat=True),
            _field('layout', 'sticky_table_headers', field_type='bool', default=True, widget='switch', legacy_flat=True),
            _field('layout', 'resizable_table_columns', field_type='bool', default=True, widget='switch', legacy_flat=True),
            _field('layout', 'zebra_striping', field_type='bool', default=True, widget='switch', legacy_flat=True),
            _field('layout', 'show_audit_fields', field_type='bool', default=False, widget='switch', legacy_flat=True),
            _field('layout', 'show_soft_deleted', field_type='bool', default=False, widget='switch', legacy_flat=True),
            _field('layout', 'options_style', default=DEFAULT_OPTIONS_STYLE, widget='choice', legacy_flat=True),
            _field('layout', 'row_actions_style', default='context', widget='choice', legacy_flat=True),
            _field('layout', 'footer_enabled', field_type='bool', default=True, widget='switch', legacy_flat=True),
            _field('layout', 'footer_text', default='', widget='text', legacy_flat=True),
            _field('layout', 'footer_link_text', default='', widget='text', legacy_flat=True),
            _field('layout', 'footer_link_url', default='', widget='text', legacy_flat=True),
        ),
    ),
    SettingGroup(
        key='language',
        storage_field='language_config',
        aliases=('language', 'languages', 'localization'),
        default_factory=default_language_config,
        normalizer=normalize_language_config,
        label_key='settings_languages',
        setup_step='languages',
        admin_section='localization',
        fields=(
            _field('language', 'languages', field_type='dict', default={}, widget='json', legacy_flat=True),
            _field('language', 'translations_override', field_type='dict', default={}, widget='json', legacy_flat=True),
            _field('language', 'allow_user_language_override', field_type='bool', default=True, widget='switch', legacy_flat=True),
        ),
    ),
    SettingGroup(
        key='theme',
        storage_field='theme_config',
        aliases=('theme', 'themes'),
        default_factory=default_theme_config,
        normalizer=normalize_theme_config,
        label_key='settings_themes',
        setup_step='appearance',
        admin_section='appearance',
        fields=(
            _field('theme', 'allowed_themes', field_type='list', default=[], widget='multiselect', legacy_flat=True),
            _field('theme', 'allow_user_theme_override', field_type='bool', default=True, widget='switch', legacy_flat=True),
            _field('theme', 'theme_picker_location', default=DEFAULT_THEME_PICKER_LOCATION,
                   widget='choice', legacy_flat=True),
        ),
    ),
    SettingGroup(
        key='typography',
        storage_field='typography_config',
        aliases=('typography', 'fonts'),
        default_factory=default_typography_config,
        normalizer=normalize_typography_config,
        label_key='settings_typography',
        setup_step='appearance',
        admin_section='appearance',
        fields=(
            _field('typography', 'allowed_fonts', field_type='list', default=[], widget='multiselect', legacy_flat=True),
            _field('typography', 'default_fonts', field_type='dict', default={}, widget='json', legacy_flat=True),
            _field('typography', 'allow_user_font_override', field_type='bool', default=True, widget='switch', legacy_flat=True),
        ),
    ),
    SettingGroup(
        key='login',
        storage_field='login_config',
        aliases=('login', 'login_page'),
        default_factory=default_login_config,
        normalizer=normalize_login_config,
        label_key='settings_login_page',
        setup_step='login',
        admin_section='login',
    ),
    SettingGroup(
        key='titlebar',
        storage_field='titlebar_config',
        aliases=('titlebar', 'topbar'),
        default_factory=default_titlebar_config,
        normalizer=normalize_titlebar_config,
        label_key='settings_titlebar',
        setup_step='titlebar',
        admin_section='navigation',
    ),
    SettingGroup(
        key='search',
        storage_field='search_config',
        aliases=('search', 'global_search'),
        default_factory=default_search_config,
        normalizer=normalize_search_config,
        label_key='system_settings_search',
        setup_step='search',
        admin_section='search',
    ),
    SettingGroup(
        key='sidebar',
        storage_field='sidebar_config',
        aliases=('sidebar', 'side_nav'),
        default_factory=default_sidebar_config,
        normalizer=normalize_sidebar_behavior,
        label_key='settings_sidebar',
        setup_step='sidebar',
        admin_section='navigation',
    ),
    SettingGroup(
        key='navbar',
        storage_field='navbar_config',
        aliases=('navbar', 'nav_bar'),
        default_factory=default_navbar_config,
        normalizer=normalize_navbar_config,
        label_key='settings_navbar',
        setup_step='navbar',
        admin_section='navigation',
    ),
    SettingGroup(
        key='log',
        storage_field='log_config',
        aliases=('log', 'logging', 'activity_logging'),
        default_factory=default_log_config,
        normalizer=normalize_log_config,
        label_key='settings_logging',
        setup_step='logging',
        admin_section='logging',
    ),
    SettingGroup(
        key='profile',
        storage_field='profile_config',
        aliases=('profile', 'profile_page', 'onboarding'),
        default_factory=default_profile_config,
        normalizer=normalize_profile_config,
        label_key='settings_profile_page',
        setup_step='profile',
        admin_section='profile',
    ),
    SettingGroup(
        key='backup',
        storage_field='backup_config',
        aliases=('backup', 'backups', 'system_backup'),
        default_factory=default_backup_config,
        normalizer=normalize_backup_config,
        label_key='settings_backups',
        setup_step='backups',
        admin_section='backups',
        fields=(
            _field('backup', 'scheduled_enabled', form_name='backup_scheduled_enabled', field_type='bool', default=False, widget='switch'),
            _field('backup', 'schedule_interval_hours', form_name='backup_schedule_interval_hours', field_type='int', default=24),
            _field('backup', 'retention_days', form_name='backup_retention_days', field_type='int', default=0),
            _field('backup', 'max_backups_to_keep', form_name='backup_max_backups_to_keep', field_type='int', default=0),
            _field('backup', 'auto_export_target', form_name='backup_auto_export_target', default='dlux_backups'),
            _field('backup', 'stall_timeout_minutes', form_name='backup_stall_timeout_minutes', field_type='int', default=30),
            _field('backup', 'auto_retry_enabled', form_name='backup_auto_retry_enabled', field_type='bool', default=True, widget='switch'),
            _field('backup', 'max_attempts', form_name='backup_max_attempts', field_type='int', default=3),
            _field('backup', 'retry_delay_minutes', form_name='backup_retry_delay_minutes', field_type='int', default=5),
        ),
    ),
    SettingGroup(
        key='extra',
        storage_field='extra_config',
        aliases=('extra', 'custom'),
        default_factory=default_extra_config,
        normalizer=normalize_extra_config,
        label_key='settings_extra',
        setup_step='advanced',
        admin_section='advanced',
    ),
)

__all__ = ['SettingField', 'SettingGroup', 'SYSTEM_SETTING_GROUPS']
