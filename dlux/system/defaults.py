"""Canonical defaults for Dlux system settings.

Keep this module free of model/form/admin/view/translations imports so migration
callables and Django startup remain stable.
"""

from .constants import (
    DEFAULT_HOME_URL,
    DEFAULT_FORM_DENSITY,
    DEFAULT_MODAL_SIZE,
    DEFAULT_NAVBAR_MODE,
    DEFAULT_NAVBAR_ROOT_MODE,
    DEFAULT_OPTIONS_STYLE,
    DEFAULT_RIBBON_ADVANCED_TRIGGER,
    DEFAULT_RIBBON_NESTING,
    DEFAULT_RIBBON_LAYOUT,
    DEFAULT_RIBBON_STYLE,
    DEFAULT_ROW_ACTIONS_STYLE,
    DEFAULT_SECURITY_NUDGE,
    DEFAULT_SIDEBAR_COLLAPSE_MODE,
    DEFAULT_SIDEBAR_TOGGLE_ICON,
    DEFAULT_SIDEBAR_DENSITY,
    DEFAULT_TABLE_DENSITY,
    DEFAULT_TABLE_EDGES,
    DEFAULT_CARD_EDGES,
    REGISTRATION_ACTIVATION_AUTO_LOGIN,
    TITLEBAR_ACTIONS_ORDER,
    TITLEBAR_ACTIONS_LAYOUT_SCATTERED,
    TITLEBAR_USER_HUB_STYLE_DROPDOWN,
)


def default_auth_config():
    return {
        'email_2fa': False,
        # Show the "Forgot password?" link on the login page and enable the
        # reset flow. Opt-in, and additionally self-gates on email readiness.
        'forgot_password_enabled': False,
        'prevent_multiple_active_sessions': False,
        'login_lockout_enabled': True,
        # Lockout tuning (effective only while login_lockout_enabled is on):
        # failed attempts before the lock arms, the rolling window counting them,
        # and how long the lock lasts once armed.
        'login_lockout_threshold': 5,
        'login_lockout_window_minutes': 15,
        'login_lockout_duration_minutes': 15,
        'enforce_strong_passwords': False,
        # Minimum length the strict validator (and live checklist) requires while
        # enforce_strong_passwords is on.
        'strong_password_min_length': 12,
        # When on, the session cookie is a browser-session cookie with no persistent
        # Max-Age. Browser tabs share the cookie and cannot expire it independently.
        'purge_session_on_exit': False,
        # Idle sign-out: when enabled, an authenticated session is terminated after
        # inactivity_timeout_minutes of no activity (a client countdown warns first).
        'inactivity_timeout_enabled': False,
        'inactivity_timeout_minutes': 10,
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
        # Seconds to wait for the provider. 0 keeps the shipped default, which is
        # sized for a slow upstream; raise it for a server that scans mail in-line.
        'timeout': 0,
        # Operator opt-in for the Email step. Dependent features (email 2FA,
        # forgot password, public registration, notification email) are only
        # editable while this is on AND a test send has verified the config.
        'enabled': False,
        'verified': False,
        'verified_at': '',
        # Fingerprint of the connection fields the successful test ran against;
        # any later edit no longer matches, which re-arms verification.
        'verified_fingerprint': '',
    }


def default_registration_config():
    return {
        'public_registration_enabled': False,
        'registration_activation_mode': REGISTRATION_ACTIVATION_AUTO_LOGIN,
        'registration_throttle_enabled': True,
        'honeypot_enabled': True,
        # Privacy / consent (operator-supplied; the framework never ships legal
        # text). URLs + optional notice are surfaced on the sign-in / sign-up
        # pages; require_consent gates a mandatory agreement checkbox at signup.
        'privacy_policy_url': '',
        'terms_url': '',
        'privacy_notice_text': '',
        'registration_require_consent': False,
    }


def default_public_root_config():
    return {
        'public_root': False,
        'public_root_split_enabled': False,
        'public_root_url': '',
        'public_root_theme': '',
        'public_root_title': '',
        'public_root_meta_description': '',
        'show_titlebar_on_public': False,
        'show_sidebar_on_public': False,
    }


def default_homepage_config():
    return {
        'default_url': DEFAULT_HOME_URL,
        'allow_user_override': False,
        'public': {
            'enabled': False,
            'separate_url': False,
            'url': '',
            'theme': '',
            'title': '',
            'meta_description': '',
            'show_titlebar': False,
            'show_sidebar': False,
        },
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
            'include_actor': False,
        },
    }


def default_layout_config():
    return {
        'default_table_density': DEFAULT_TABLE_DENSITY,
        'table_edges': DEFAULT_TABLE_EDGES,
        'card_edges': DEFAULT_CARD_EDGES,
        'table_accent_edges': False,
        'default_form_density': DEFAULT_FORM_DENSITY,
        'default_modal_size': DEFAULT_MODAL_SIZE,
        'sticky_table_headers': True,
        'resizable_table_columns': True,
        'zebra_striping': True,
        # Show the audit columns (created_by/at, updated_by/at) in tables and
        # auto-CRUD detail views — additionally gated by the `view_audit_fields`
        # permission per viewer. Show soft-deleted rows (deleted_at set) in lists
        # — additionally gated to superadmins. Both default off.
        'show_audit_fields': False,
        'show_soft_deleted': False,
        'options_style': DEFAULT_OPTIONS_STYLE,
        # The list-page ribbon: its style, whether it carries the page title,
        # how its advanced filters are reached, and where its actions sit.
        'ribbon_layout': DEFAULT_RIBBON_LAYOUT,
        'ribbon_style': DEFAULT_RIBBON_STYLE,
        'ribbon_title': True,
        'ribbon_nesting': DEFAULT_RIBBON_NESTING,
        'ribbon_advanced_trigger': DEFAULT_RIBBON_ADVANCED_TRIGGER,
        # Table row-actions trigger: 'context' (right-click/long-press menu),
        # 'column' (dedicated three-dot column), or 'both'.
        'row_actions_style': DEFAULT_ROW_ACTIONS_STYLE,
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

    from .constants import DEFAULT_THEME_PICKER_LOCATION

    return {
        'allowed_themes': list(get_theme_names()),
        'allow_user_theme_override': True,
        'theme_picker_location': DEFAULT_THEME_PICKER_LOCATION,
    }


def default_typography_config():
    from ..fonts import get_available_fonts

    return {
        'allowed_fonts': [font['slug'] for font in get_available_fonts()],
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
        'accent_edge': False,
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
        # 'scattered' keeps every action on the titlebar; 'grouped' collects them
        # behind a caret next to the user hub. Narrow screens group regardless.
        'actions_layout': TITLEBAR_ACTIONS_LAYOUT_SCATTERED,
        # Optional single-button language switcher that cycles through the
        # available languages. Only surfaces at runtime when language switching is
        # actually possible (override allowed and more than one language).
        'show_language_switcher': False,
        'actions_order': list(TITLEBAR_ACTIONS_ORDER),
        # Global search: 'always' (field shown), 'icon' (icon expands to field on
        # focus), or 'disabled'. include_data extends search from components to
        # data records when on.
        'global_search_mode': 'icon',
        'global_search_include_data': False,
    }


def default_search_config():
    return {
        'enabled': True,
        'display_mode': 'icon',
        'include_data': False,
    }


def default_sidebar_config():
    return {
        'enabled': True,
        'accent_edge': False,
        'home_url_name': None,
        'entries': [],
        'enable_reorder': True,
        'show_toolbar': True,
        'show_sections_manager': True,
        'show_icons': True,
        'show_notification_badges': True,
        'density': DEFAULT_SIDEBAR_DENSITY,
        'allow_user_density': True,
        'collapse_mode': DEFAULT_SIDEBAR_COLLAPSE_MODE,
        'toggle_icon': DEFAULT_SIDEBAR_TOGGLE_ICON,
    }


def default_navbar_config():
    return {
        'enabled': False,
        'default_mode': DEFAULT_NAVBAR_MODE,
        'allow_user_mode_override': True,
        'root': {
            'mode': DEFAULT_NAVBAR_ROOT_MODE,
            'url_name': '',
        },
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
    """System-backup scheduling, storage, rotation, and recovery policy.

    Zero-valued retention limits intentionally mean "keep indefinitely" so
    enabling this settings group never removes an existing backup by default.

    ``stall_timeout_minutes`` is how long a run may go without a progress
    heartbeat before it is treated as dead; ``max_attempts`` counts the first
    attempt, so the default 3 means up to two automatic retries.
    """
    return {
        'scheduled_enabled': False,
        'schedule_interval_hours': 24,
        'retention_days': 0,
        'max_backups_to_keep': 0,
        'auto_export_target': 'dlux_backups',
        'use_celery': True,
        'exclude_models': [],
        'stall_timeout_minutes': 30,
        'auto_retry_enabled': True,
        'max_attempts': 3,
        'retry_delay_minutes': 5,
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
    """Stays empty on purpose.

    Dlux-owned keys sit at the top level (projects own `extra_config['app']`,
    verified across the active projects, so there is no collision). But seeding a
    default key here makes the default win over a host project's
    `DLUX_CONFIG['extra']`, which silently dropped that project's own keys.
    `scanlink` is therefore supplied by normalize_extra_config() and read
    defensively, never seeded as a default.
    """
    return {}


def default_scanlink_config():
    return {'enabled': False}


__all__ = [
    'default_auth_config',
    'default_backup_config',
    'default_client_ip_config',
    'default_email_config',
    'default_extra_config',
    'default_homepage_config',
    'default_scanlink_config',
    'default_language_config',
    'default_layout_config',
    'default_log_config',
    'default_login_config',
    'default_navbar_config',
    'default_notification_config',
    'default_profile_config',
    'default_public_root_config',
    'default_registration_config',
    'default_search_config',
    'default_sidebar_config',
    'default_theme_config',
    'default_titlebar_config',
    'default_typography_config',
]
