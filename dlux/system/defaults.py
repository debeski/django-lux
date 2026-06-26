"""Canonical defaults for Dlux system settings.

Keep this module free of model/form/admin/view/translations imports so migration
callables and Django startup remain stable.
"""

from .constants import (
    DEFAULT_NAVBAR_MODE,
    DEFAULT_SECURITY_NUDGE,
    DEFAULT_SIDEBAR_COLLAPSE_MODE,
    DEFAULT_SIDEBAR_DENSITY,
    DEFAULT_TABLE_DENSITY,
    REGISTRATION_ACTIVATION_AUTO_LOGIN,
    TITLEBAR_ACTIONS_ORDER,
    TITLEBAR_USER_HUB_STYLE_DROPDOWN,
)


def default_auth_config():
    return {
        'email_2fa': False,
        'prevent_multiple_active_sessions': False,
        'login_lockout_enabled': True,
        'enforce_strong_passwords': False,
    }


def default_email_config():
    return {
        'transport': 'direct',
        'secret_storage': 'env',
        'provider_preset': 'custom',
        'host': '',
        'port': 587,
        'use_tls': True,
        'use_ssl': False,
        'username': '',
        'default_from_email': '',
        'encrypted_password': '',
        'password_configured': False,
        'failure_notification_recipients': [],
    }


def default_registration_config():
    return {
        'public_registration_enabled': False,
        'registration_activation_mode': REGISTRATION_ACTIVATION_AUTO_LOGIN,
        'registration_throttle_enabled': True,
    }


def default_public_root_config():
    return {
        'public_root': False,
        'public_root_split_enabled': False,
        'public_root_url': '',
    }


def default_client_ip_config():
    return {
        'mode': 'x_forwarded_for',
        'trusted_proxy_hops': 1,
        'custom_header': '',
    }


def default_notification_config():
    return {
        'enabled': True,
        'flash': {
            'enabled': True,
            'position': 'top_center',
            'size': 'balanced',
            'text_size': 'md',
            'timeout_ms': 3200,
            'max_visible': 3,
        },
        'drawer': {
            'enabled': True,
            'badge_enabled': True,
            'preview_limit': 8,
        },
        'bridge': {
            'django_messages_enabled': False,
        },
        'email': {
            'enabled': False,
            'default': False,
        },
        'retention': {
            'default_expiry_days': 30,
        },
        'automatic': {
            'scoped_model_crud': True,
            'create': True,
            'update': 'summary',
            'delete': True,
            'actor_flash_actions': ['create', 'delete', 'error'],
            'watchable': True,
        },
    }


def default_layout_config():
    return {
        'default_table_density': DEFAULT_TABLE_DENSITY,
        'footer_enabled': True,
        'footer_text': '',
        'footer_link_text': '',
        'footer_link_url': '',
    }


def default_language_config():
    return {
        'languages': {},
        'translations_override': {},
        'allow_user_language_override': True,
    }


def default_theme_config():
    from ..themes import get_theme_names

    return {
        'allowed_themes': list(get_theme_names()),
        'allow_user_theme_override': True,
    }


def default_typography_config():
    from ..fonts import get_builtin_fonts

    return {
        'allowed_fonts': [font['slug'] for font in get_builtin_fonts()],
        'default_fonts': {},
        'allow_user_font_override': True,
    }


def default_login_config():
    return {
        'style': 'split',
        'show_logo': True,
        'banner_color': '',
        'logo_treatment': 'none',
        'logo_treatment_shape': 'soft',
        'hero_message': '',
    }


def default_titlebar_config():
    return {
        'show_title': True,
        'show_logo': True,
        'show_home_button': True,
        'hide_on_public_unauthenticated_index': False,
        'buttons_shape': 'circle',
        'home_shape': 'circle',
        'title_align': 'start',
        'title_size': 'md',
        'height': 'balanced',
        'surface': 'default',
        'logo_treatment': 'none',
        'logo_treatment_shape': 'soft',
        'user_hub_style': TITLEBAR_USER_HUB_STYLE_DROPDOWN,
        'actions_order': list(TITLEBAR_ACTIONS_ORDER),
    }


def default_sidebar_config():
    return {
        'enabled': True,
        'home_url_name': None,
        'entries': [],
        'enable_reorder': True,
        'show_toolbar': True,
        'show_icons': True,
        'density': DEFAULT_SIDEBAR_DENSITY,
        'allow_user_density': True,
        'collapse_mode': DEFAULT_SIDEBAR_COLLAPSE_MODE,
    }


def default_navbar_config():
    return {
        'enabled': False,
        'default_mode': DEFAULT_NAVBAR_MODE,
        'allow_user_mode_override': True,
        'hierarchy': {'nodes': []},
    }


def default_log_config():
    return {
        'enabled': True,
        'user': {
            'enabled': True,
            'default_actions': {'create': True, 'update': True, 'delete': True},
            'retention_days': 0,
            'models': {},
        },
        'system': {
            'enabled': True,
            'default_actions': {'create': True, 'update': True, 'delete': True},
            'retention_days': 0,
            'models': {},
        },
        'audit': {
            'enabled': True,
            'immutable': True,
            'retention_days': 0,
            'events': {
                'login_success': True,
                'login_failed': True,
                'logout': True,
                'lockout': True,
                'password_change': True,
                '2fa_change': True,
                '2fa_failed': True,
                'session_revoke': True,
                'trusted_device_change': True,
                'permission_denied': True,
                'dlux_update_check': True,
                'dlux_update_apply': True,
                'dlux_update_rollback': True,
            },
        },
    }


def default_backup_config():
    """System-backup scheduling, storage, and rotation policy.

    Zero-valued retention limits intentionally mean "keep indefinitely" so
    enabling this settings group never removes an existing backup by default.
    """
    return {
        'scheduled_enabled': False,
        'schedule_interval_hours': 24,
        'retention_days': 0,
        'max_backups_to_keep': 0,
        'auto_export_target': 'dlux_backups',
        'use_celery': True,
        'exclude_models': [],
    }


def default_profile_config():
    return {
        'show_completion_widget': True,
        'show_session_device_cards': True,
        'show_activity_feed': True,
        'security_nudges': DEFAULT_SECURITY_NUDGE,
        'allow_user_home_url': False,
        'onboarding_enabled': True,
        'onboarding_options': {
            'theme': True,
            'language': True,
            'fonts': True,
        },
    }


def default_extra_config():
    return {}


__all__ = [
    'default_auth_config',
    'default_backup_config',
    'default_client_ip_config',
    'default_email_config',
    'default_extra_config',
    'default_language_config',
    'default_layout_config',
    'default_log_config',
    'default_login_config',
    'default_navbar_config',
    'default_notification_config',
    'default_profile_config',
    'default_public_root_config',
    'default_registration_config',
    'default_sidebar_config',
    'default_theme_config',
    'default_titlebar_config',
    'default_typography_config',
]
