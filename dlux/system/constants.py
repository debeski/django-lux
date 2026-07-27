"""Canonical constants for Dlux system settings and runtime surfaces."""

DEFAULT_HOME_URL = '/accounts/profile/'

# Profile page security-nudge intensity (missing 2FA / weak account health prompts).
DEFAULT_SECURITY_NUDGE = 'subtle'
SECURITY_NUDGE_CHOICES = (
    ('off', 'Off'),
    ('subtle', 'Subtle'),
    ('persistent', 'Persistent'),
)
SECURITY_NUDGE_VALUES = {value for value, _label in SECURITY_NUDGE_CHOICES}

DEFAULT_TABLE_DENSITY = 'balanced'
DEFAULT_TABLE_PAGE_SIZE = 20
TABLE_PAGE_SIZE_OPTIONS = (10, 20, 50, 100)
TABLE_PAGE_SIZE_VALUES = {int(value) for value in TABLE_PAGE_SIZE_OPTIONS}
TABLE_DENSITY_CHOICES = (
    (DEFAULT_TABLE_DENSITY, 'Balanced'),
    ('dense', 'Dense'),
    ('roomy', 'Roomy'),
)
TABLE_DENSITY_VALUES = {value for value, _label in TABLE_DENSITY_CHOICES}
DEFAULT_SIDEBAR_DENSITY = DEFAULT_TABLE_DENSITY
SIDEBAR_DENSITY_CHOICES = TABLE_DENSITY_CHOICES
SIDEBAR_DENSITY_VALUES = TABLE_DENSITY_VALUES
# Form field spacing density (layout_config) — shares the table density vocabulary
# but is applied independently to dynamic-modal/page forms.
DEFAULT_FORM_DENSITY = DEFAULT_TABLE_DENSITY
FORM_DENSITY_CHOICES = TABLE_DENSITY_CHOICES
FORM_DENSITY_VALUES = TABLE_DENSITY_VALUES
# Default width preset for the shared dynamic modal (layout_config).
DEFAULT_MODAL_SIZE = 'standard'
MODAL_SIZE_CHOICES = (
    ('compact', 'Compact'),
    (DEFAULT_MODAL_SIZE, 'Standard'),
    ('wide', 'Wide'),
)
MODAL_SIZE_VALUES = {value for value, _label in MODAL_SIZE_CHOICES}

# App-owned user preferences: downstream projects store their own per-user state
# under this single reserved top-level key in `Profile.preferences`, namespaced
# by a dotted string (e.g. preferences['app']['myproject.dashboard.v1']). Dlux
# treats everything under this key as opaque pass-through data and never
# validates its shape — it only merges at the namespace level and enforces the
# overall size cap below. Keeps app data cleanly isolated from Dlux-owned keys.
PREFERENCES_APP_NAMESPACE = 'app'
# Hard ceiling (bytes, UTF-8 JSON) on the entire `Profile.preferences` blob.
# The blob is inlined into every authenticated page render (window.USER_PREFS),
# so this bounds that per-request cost. Override with settings.DLUX_MAX_PREFERENCES_BYTES.
DEFAULT_MAX_PREFERENCES_BYTES = 64 * 1024
# Max length of a single app-preference namespace key.
PREFERENCES_APP_NAMESPACE_MAXLEN = 128

# System-level app-owned config: the parallel of the per-user `app` namespace, but
# for GLOBAL project config. Downstream projects store opaque JSON under this
# reserved key inside SystemSettings.extra_config (e.g.
# extra_config['app']['myproject.settings']). Only superusers may write it, via a
# namespace-scoped endpoint; Dlux never validates its shape. Bounded by the cap
# below to protect the get_system_config() payload (loaded app-wide).
SYSTEM_APP_CONFIG_NAMESPACE = 'app'
DEFAULT_MAX_SYSTEM_APP_CONFIG_BYTES = 64 * 1024
# Namespace keys and card ids must match this to keep them injection-safe in
# attributes/CSS classes and URLs (letters, digits, dot, dash, underscore).
SAFE_NAMESPACE_RE = r'^[A-Za-z0-9._-]+$'
# CSS dialog class applied for each modal-size preset (standard preserves modal-xl).
MODAL_SIZE_CLASSES = {
    'compact': 'modal-lg',
    'standard': 'modal-xl',
    'wide': 'modal-xl dlux-modal-wide',
}
# Options page/view layout style (layout_config.options_style): a rearrangeable
# card grid (default), a tabbed layout, or a dense single-page "desktop app" view.
DEFAULT_OPTIONS_STYLE = 'cards'
OPTIONS_STYLE_CHOICES = (
    (DEFAULT_OPTIONS_STYLE, 'Cards'),
    ('tabs', 'Tabs'),
    ('compact', 'Compact'),
)
OPTIONS_STYLE_VALUES = {value for value, _label in OPTIONS_STYLE_CHOICES}
# Table row-actions trigger style (layout_config.row_actions_style): right-click/
# long-press context menu (default, unchanged behavior), a dedicated three-dot
# actions column, or both. Distinct from the per-table `dlux_actions` Meta flag,
# which gates whether row actions are wired at all.
DEFAULT_ROW_ACTIONS_STYLE = 'context'
ROW_ACTIONS_STYLE_CHOICES = (
    (DEFAULT_ROW_ACTIONS_STYLE, 'Context menu'),
    ('column', 'Actions column'),
    ('both', 'Both'),
)
ROW_ACTIONS_STYLE_VALUES = {value for value, _label in ROW_ACTIONS_STYLE_CHOICES}
# Max length of the optional global footer copyright/credit line (layout_config).
LAYOUT_FOOTER_TEXT_MAX_LENGTH = 300
# Max lengths for the optional public-root SEO overrides (public_root_config).
PUBLIC_ROOT_TITLE_MAX_LENGTH = 120
PUBLIC_ROOT_META_DESCRIPTION_MAX_LENGTH = 300
DEFAULT_SIDEBAR_COLLAPSE_MODE = 'icons'
SIDEBAR_COLLAPSE_MODE_CHOICES = (
    (DEFAULT_SIDEBAR_COLLAPSE_MODE, 'Icons'),
    ('hidden', 'Hidden'),
    ('locked_expanded', 'Locked Expanded'),
)
SIDEBAR_COLLAPSE_MODE_VALUES = {value for value, _label in SIDEBAR_COLLAPSE_MODE_CHOICES}
DEFAULT_NAVBAR_MODE = 'hierarchy'
NAVBAR_MODE_CHOICES = (
    (DEFAULT_NAVBAR_MODE, 'Hierarchy'),
    ('history', 'History'),
)
NAVBAR_MODE_VALUES = {value for value, _label in NAVBAR_MODE_CHOICES}
DEFAULT_NAVBAR_ROOT_MODE = 'neutral'
NAVBAR_ROOT_MODE_VALUES = {DEFAULT_NAVBAR_ROOT_MODE, 'home', 'route'}
TITLEBAR_HOME_SHAPE_CHOICES = (
    ('circle', 'Circle'),
    ('square', 'Square'),
    ('squircle', 'Squircle'),
)
TITLEBAR_HOME_SHAPE_VALUES = {value for value, _label in TITLEBAR_HOME_SHAPE_CHOICES}
TITLEBAR_ALIGN_CHOICES = (
    ('start', 'Start'),
    ('center', 'Center'),
    ('end', 'End'),
)
TITLEBAR_ALIGN_VALUES = {value for value, _label in TITLEBAR_ALIGN_CHOICES}
TITLEBAR_SIZE_CHOICES = (
    ('sm', 'Small'),
    ('md', 'Medium'),
    ('lg', 'Large'),
)
TITLEBAR_SIZE_VALUES = {value for value, _label in TITLEBAR_SIZE_CHOICES}
TITLEBAR_HEIGHT_CHOICES = (
    ('dense', 'Dense'),
    ('balanced', 'Balanced'),
    ('roomy', 'Roomy'),
)
TITLEBAR_HEIGHT_VALUES = {value for value, _label in TITLEBAR_HEIGHT_CHOICES}
TITLEBAR_SURFACE_CHOICES = (
    ('default', 'Default'),
    ('muted', 'Muted'),
    ('glass', 'Glass'),
)
TITLEBAR_SURFACE_VALUES = {value for value, _label in TITLEBAR_SURFACE_CHOICES}
TITLEBAR_GLOBAL_SEARCH_CHOICES = (
    ('always', 'Always visible'),
    ('icon', 'Icon, expand on focus'),
    ('disabled', 'Disabled'),
)
TITLEBAR_GLOBAL_SEARCH_VALUES = {value for value, _label in TITLEBAR_GLOBAL_SEARCH_CHOICES}
TITLEBAR_LOGO_TREATMENT_CHOICES = (
    ('none', 'None'),
    ('plate', 'Plate'),
    ('halo', 'Halo'),
    ('contrast', 'Contrast'),
)
TITLEBAR_LOGO_TREATMENT_VALUES = {value for value, _label in TITLEBAR_LOGO_TREATMENT_CHOICES}
TITLEBAR_LOGO_TREATMENT_SHAPE_CHOICES = (
    ('soft', 'Soft'),
    ('pill', 'Pill'),
    ('square', 'Square'),
)
TITLEBAR_LOGO_TREATMENT_SHAPE_VALUES = {value for value, _label in TITLEBAR_LOGO_TREATMENT_SHAPE_CHOICES}
TITLEBAR_USER_HUB_STYLE_DROPDOWN = 'dropdown'
TITLEBAR_USER_HUB_STYLE_ACTIONS = 'titlebar_actions'
TITLEBAR_USER_HUB_STYLE_CHOICES = (
    (TITLEBAR_USER_HUB_STYLE_DROPDOWN, 'Dropdown'),
    (TITLEBAR_USER_HUB_STYLE_ACTIONS, 'Titlebar Actions'),
)
TITLEBAR_USER_HUB_STYLE_VALUES = {value for value, _label in TITLEBAR_USER_HUB_STYLE_CHOICES}
TITLEBAR_ACTIONS_ORDER = (
    'notifications',
    'home',
    'profile',
    'help',
    'users',
    'activity',
    'reports',
    'settings',
    'auth',
)
TITLEBAR_ACTIONS_ORDER_VALUES = set(TITLEBAR_ACTIONS_ORDER)

REGISTRATION_ACTIVATION_AUTO_LOGIN = 'auto_login_after_verify'
REGISTRATION_ACTIVATION_PENDING_APPROVAL = 'verified_pending_approval'
REGISTRATION_ACTIVATION_CHOICES = (
    (REGISTRATION_ACTIVATION_AUTO_LOGIN, 'Auto-login after verification'),
    (REGISTRATION_ACTIVATION_PENDING_APPROVAL, 'Verified pending approval'),
)
REGISTRATION_ACTIVATION_VALUES = {value for value, _label in REGISTRATION_ACTIVATION_CHOICES}

REGISTRATION_STATUS_PENDING_EMAIL = 'pending_email'
REGISTRATION_STATUS_PENDING_APPROVAL = 'pending_approval'
REGISTRATION_STATUS_ACTIVATED = 'activated'
REGISTRATION_STATUS_REJECTED = 'rejected'
REGISTRATION_STATUS_EXPIRED = 'expired'
REGISTRATION_STATUS_CHOICES = (
    (REGISTRATION_STATUS_PENDING_EMAIL, 'Pending email verification'),
    (REGISTRATION_STATUS_PENDING_APPROVAL, 'Pending approval'),
    (REGISTRATION_STATUS_ACTIVATED, 'Activated'),
    (REGISTRATION_STATUS_REJECTED, 'Rejected'),
    (REGISTRATION_STATUS_EXPIRED, 'Expired'),
)

DEFAULT_LANGUAGE_CATALOG = {
    'en': {'name': 'English', 'dir': 'ltr', 'flag': '🇬🇧'},
    'ar': {'name': 'العربية', 'dir': 'rtl', 'flag': '🇱🇾'},
}

EMAIL_CONFIG_TRANSPORTS = {'direct', 'relay'}
EMAIL_CONFIG_SECRET_STORAGES = {'env', 'encrypted_db'}

# Provider presets prefill host/port/TLS/SSL in the UI; 'custom' leaves the
# entered values untouched. Stored on email_config so the picker survives reloads.
EMAIL_CONFIG_PROVIDER_PRESETS = {
    'custom': {'host': '', 'port': 587, 'use_tls': True, 'use_ssl': False},
    'gmail': {'host': 'smtp.gmail.com', 'port': 587, 'use_tls': True, 'use_ssl': False},
    'outlook': {'host': 'smtp.office365.com', 'port': 587, 'use_tls': True, 'use_ssl': False},
    'ses': {'host': 'email-smtp.us-east-1.amazonaws.com', 'port': 587, 'use_tls': True, 'use_ssl': False},
    'mailgun': {'host': 'smtp.mailgun.org', 'port': 587, 'use_tls': True, 'use_ssl': False},
    'relay': {'host': '', 'port': 1025, 'use_tls': False, 'use_ssl': False},
}
EMAIL_CONFIG_PROVIDER_PRESET_VALUES = set(EMAIL_CONFIG_PROVIDER_PRESETS)
# Cap stored failure-alert recipients to keep the JSON config bounded.
EMAIL_CONFIG_MAX_FAILURE_RECIPIENTS = 10

CLIENT_IP_MODE_REMOTE_ADDR = 'remote_addr'
CLIENT_IP_MODE_X_FORWARDED_FOR = 'x_forwarded_for'
CLIENT_IP_MODE_X_REAL_IP = 'x_real_ip'
CLIENT_IP_MODE_CLOUDFLARE = 'cloudflare'
CLIENT_IP_MODE_CUSTOM = 'custom'
CLIENT_IP_MODE_AUTO = 'auto'
CLIENT_IP_MODE_VALUES = {
    CLIENT_IP_MODE_REMOTE_ADDR,
    CLIENT_IP_MODE_X_FORWARDED_FOR,
    CLIENT_IP_MODE_X_REAL_IP,
    CLIENT_IP_MODE_CLOUDFLARE,
    CLIENT_IP_MODE_CUSTOM,
    CLIENT_IP_MODE_AUTO,
}

LOGIN_STYLE_VALUES = {'split', 'centered', 'minimal', 'fullpage'}

NOTIFICATION_FLASH_POSITIONS = {
    'top_center',
    'top_start',
    'top_end',
    'titlebar_end',
    'bottom_start',
    'bottom_end',
}
NOTIFICATION_FLASH_SIZES = {'compact', 'balanced', 'prominent'}
NOTIFICATION_FLASH_TEXT_SIZES = {'sm', 'md', 'lg'}
NOTIFICATION_UPDATE_MODES = {'off', 'summary', 'full'}

SYSTEM_SETTINGS_CONFIG_FIELDS = (
    'auth_config',
    'email_config',
    'registration_config',
    'public_root_config',
    'client_ip_config',
    'notification_config',
    'layout_config',
    'language_config',
    'theme_config',
    'typography_config',
    'login_config',
    'titlebar_config',
    'sidebar_config',
    'navbar_config',
    'log_config',
    'profile_config',
    'backup_config',
    'extra_config',
)

SYSTEM_SETTINGS_EXPORT_FIELDS = (
    'system_names',
    'logo',
    'favicon',
    'home_url',
    'default_language',
    'default_theme',
    'allowed_themes',
    'allow_user_theme_override',
    'allowed_fonts',
    'default_fonts',
    'allow_user_font_override',
    'allow_user_language_override',
    'default_table_density',
    'default_form_density',
    'default_modal_size',
    'sticky_table_headers',
    'resizable_table_columns',
    'zebra_striping',
    'show_audit_fields',
    'show_soft_deleted',
    'options_style',
    'row_actions_style',
    'footer_enabled',
    'footer_text',
    'footer_link_text',
    'footer_link_url',
    'email_2fa',
    'forgot_password_enabled',
    'prevent_multiple_active_sessions',
    'login_lockout_enabled',
    'login_lockout_threshold',
    'login_lockout_window_minutes',
    'login_lockout_duration_minutes',
    'enforce_strong_passwords',
    'strong_password_min_length',
    'purge_session_on_exit',
    'inactivity_timeout_enabled',
    'inactivity_timeout_minutes',
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
    'navbar_config',
    'log_config',
    'profile_config',
    'backup_config',
    'titlebar_config',
    'notification_config',
    'login_config',
    'extra_config',
)

__all__ = [name for name in globals() if name.isupper()]
