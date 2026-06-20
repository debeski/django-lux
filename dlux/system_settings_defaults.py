"""Storage defaults for SystemSettings JSON config groups.

Keep this module free of model imports so migration defaults stay stable.
"""

from .constants import DEFAULT_TABLE_DENSITY, REGISTRATION_ACTIVATION_AUTO_LOGIN
from .notification_defaults import default_notification_config


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
        'host': '',
        'port': 587,
        'use_tls': True,
        'use_ssl': False,
        'username': '',
        'default_from_email': '',
        'encrypted_password': '',
        'password_configured': False,
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


def default_layout_config():
    return {
        'default_table_density': DEFAULT_TABLE_DENSITY,
    }


def default_language_config():
    return {
        'languages': {},
        'translations_override': {},
        'allow_user_language_override': True,
    }


def default_theme_config():
    from .themes import get_theme_names

    return {
        'allowed_themes': list(get_theme_names()),
        'allow_user_theme_override': True,
    }


def default_typography_config():
    from .fonts import get_builtin_fonts

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
    from .constants import TITLEBAR_ACTIONS_ORDER, TITLEBAR_USER_HUB_STYLE_DROPDOWN

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


def default_navbar_config():
    return {
        'enabled': False,
        'default_mode': 'hierarchy',
        'allow_user_mode_override': True,
        'hierarchy': {'nodes': []},
    }


def default_profile_config():
    """User profile page + account experience (NOT personalization defaults — those live in
    theme/typography/layout/language configs; NOT per-user prefs — those live in
    Profile.preferences). System-level group: what the profile page shows and whether the
    first-login Initial User Setup modal runs and what it offers."""
    from .constants import DEFAULT_SECURITY_NUDGE
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


def default_log_config():
    """Activity-logging policy (user / system / audit), consolidated into one JSON field.

    Per-section `models` is a sparse override map keyed by "app_label.model"; absent models
    are included with `default_actions`. High-churn dlux operational models and Django
    framework internals are hard-excluded (never logged or shown) rather than seeded here.
    Audit is privileged: it is not disabled by per-model toggles and is never auto-pruned by
    default.
    """
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
            },
        },
    }
