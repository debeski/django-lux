"""Canonical constants for Dlux system settings and runtime surfaces."""

DEFAULT_HOME_URL = '/accounts/profile/'

# ── route discovery ──────────────────────────────────────────────────────────
# Discovery walks the URLconf once and classifies every named route. It excludes
# nothing on its own; each consuming feature (sidebar, Nav Bar, search, landing
# picker) filters the shared catalog through one of the profiles below. Editing
# a token here changes how a route is CLASSIFIED, not whether it is discovered.

# What a route does, inferred from its name and path.
ROUTE_ACTION_PAGE = 'page'          # a normal navigable page (list, detail, dashboard)
ROUTE_ACTION_FORM = 'form'          # creates a record — no object required to reach it
ROUTE_ACTION_EDIT = 'edit'          # mutates an existing record — needs an id
ROUTE_ACTION_ASYNC = 'async'        # XHR/partial endpoint, never a destination
ROUTE_ACTION_API = 'api'            # API counterpart of a page view
ROUTE_ACTION_MACHINERY = 'machinery'  # auth, 2FA, setup, modal and admin plumbing

ROUTE_FORM_TOKENS = frozenset({'add', 'create'})
ROUTE_EDIT_TOKENS = frozenset({'edit', 'update'})
ROUTE_ASYNC_TOKENS = frozenset({'ajax'})

# Leaf names that are machinery no matter which app declares them.
ROUTE_MACHINERY_EXACT_NAMES = frozenset({
    'login',
    'logout',
    'toggle_sidebar',
    'verify_otp_enable',
    'verify_otp_login',
    'verify_otp_generic',
    'enable_2fa',
    'setup_totp',
    'disable_2fa',
    'generate_backup_codes',
    'resend_otp',
    'resend_otp_login',
    'system_setup',
    'manage_users',
    'manage_scopes',
    'add_subsection',
    'set_active_model',
})

# Substrings anywhere in the full route name that mark machinery.
ROUTE_MACHINERY_NAME_PARTS = (
    'modal',
    'delete',
    'api_',
    'get_',
    'save_',
    'toggle_',
    'verify_otp',
    'resend_otp',
    'reset_password',
)

ROUTE_MACHINERY_NAMESPACES = frozenset({'admin', 'health_check'})

ROUTE_MACHINERY_PATH_PARTS = (
    '/accounts/login/',
    '/accounts/logout/',
    '/health/',
    '/sys/2fa/',
    '/api/',
    '/sys/modals/',
    '/sys/setup/',
)

# Feature profiles. `actions` is what the feature accepts; `require_url` marks a
# feature that needs a real href, which is what keeps id-bound edit routes out of
# everything except the Nav Bar hierarchy (whose nodes match on route name and
# render fine without a URL).
DISCOVERY_PROFILE_SIDEBAR = 'sidebar'
DISCOVERY_PROFILE_NAVBAR = 'navbar'
DISCOVERY_PROFILE_NAVBAR_ROOT = 'navbar_root'
DISCOVERY_PROFILE_SEARCH = 'search'
DISCOVERY_PROFILE_LANDING = 'landing'

DISCOVERY_PROFILES = {
    # Form pages are offered but flagged `is_form_page`, so the builder keeps them
    # out of the available list until the admin asks for them.
    DISCOVERY_PROFILE_SIDEBAR: {
        'actions': (ROUTE_ACTION_PAGE, ROUTE_ACTION_FORM),
        'require_url': True,
    },
    DISCOVERY_PROFILE_NAVBAR: {
        'actions': (ROUTE_ACTION_PAGE, ROUTE_ACTION_FORM, ROUTE_ACTION_EDIT),
        'require_url': False,
    },
    DISCOVERY_PROFILE_NAVBAR_ROOT: {
        'actions': (ROUTE_ACTION_PAGE,),
        'require_url': True,
    },
    DISCOVERY_PROFILE_SEARCH: {
        'actions': (ROUTE_ACTION_PAGE, ROUTE_ACTION_FORM),
        'require_url': True,
    },
    # A landing page must be reachable with no context, so form pages are out.
    DISCOVERY_PROFILE_LANDING: {
        'actions': (ROUTE_ACTION_PAGE,),
        'require_url': True,
    },
}

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
DEFAULT_TABLE_EDGES = 'curved'
TABLE_EDGES_CHOICES = (
    (DEFAULT_TABLE_EDGES, 'Curved'),
    ('half_rounded', 'Half-rounded'),
    ('normal', 'Normal'),
)
TABLE_EDGES_VALUES = {value for value, _label in TABLE_EDGES_CHOICES}
DEFAULT_CARD_EDGES = 'curved'
CARD_EDGES_CHOICES = (
    (DEFAULT_CARD_EDGES, 'Curved'),
    ('half_rounded', 'Half-rounded'),
    ('normal', 'Normal'),
)
CARD_EDGES_VALUES = {value for value, _label in CARD_EDGES_CHOICES}
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
# Origins the ScanLink tray app listens on, on the operator's OWN workstation.
# They must appear in connect-src or the browser blocks the helper regardless of
# the Extra Features toggle. Listing them is safe while ScanLink is off: CSP only
# permits requests, it never causes them.
SCANLINK_CONNECT_ORIGINS = ('https://localhost:5443', 'http://localhost:5000')

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
# Options page/view layout style (layout_config.options_style): a tabbed layout
# (default), a rearrangeable card grid, or a dense single-page "desktop app" view.
# The choices are spelled literally: this constant used to double as the value for
# Cards, so changing which style is default silently relabelled that option.
OPTIONS_STYLE_CHOICES = (
    ('cards', 'Cards'),
    ('tabs', 'Tabs'),
    ('compact', 'Compact'),
)
DEFAULT_OPTIONS_STYLE = 'tabs'
OPTIONS_STYLE_VALUES = {value for value, _label in OPTIONS_STYLE_CHOICES}
# How the ribbon looks, independently of how it is arranged: the standard
# bordered header, the soft rounded surface the reports page uses, or a
# borderless rule for pages that want the list to lead.
DEFAULT_RIBBON_STYLE = 'accent'
RIBBON_STYLE_CHOICES = (
    (DEFAULT_RIBBON_STYLE, 'Accent'),
    ('panel', 'Panel'),
    ('flat', 'Flat'),
)
RIBBON_STYLE_VALUES = {value for value, _label in RIBBON_STYLE_CHOICES}

# Tab strips an administrator drew, keyed by "app_label.ModelName". The value is
# the same shape a view's `ribbon_tabs` takes, so a strip declared in code and
# one drawn in Settings are the same object by the time anything renders it.
#
#   {"storage.Asset": {"param": "category", "sources": [...]}}
#
# A view that declares its own strip wins: the developer had a reason, and a
# setting quietly overriding code is the kind of surprise that costs an hour.
DEFAULT_RIBBON_CONFIG = {}
RIBBON_TAB_SOURCE_TYPES = ('all', 'field', 'flag', 'static')

# Layout keys that live only in layout_config — there is no legacy column on
# SystemSettings for them, so import/export has to route them through the JSON
# rather than setattr. Add a new JSON-only layout key here and the import,
# export and runtime-override paths pick it up.
JSON_ONLY_LAYOUT_KEYS = (
    'options_style',
    'row_actions_style',
    'table_edges',
    'card_edges',
    'table_accent_edges',
    'ribbon_layout',
    'ribbon_style',
    'ribbon_title',
    'ribbon_advanced_trigger',
    'ribbon_nesting',
)

# The ribbon: the band at the top of a list page carrying its title, its actions
# and its filters. Page chrome, like the navbar and the titlebar, and configured
# the same way — the administrator picks how it looks, the developer declares
# nothing. See `dlux.ribbon`.
#
# Style: the standard header card — title and actions on one row, filters on the
# row beneath (default); the same with the actions moved below the filters, for
# a list with many of them; or filters alone, with no title card.
DEFAULT_RIBBON_LAYOUT = 'default'
RIBBON_LAYOUT_CHOICES = (
    (DEFAULT_RIBBON_LAYOUT, 'Default'),
    ('stacked', 'Stacked'),
    ('compact', 'Compact'),
)
RIBBON_LAYOUT_VALUES = {value for value, _label in RIBBON_LAYOUT_CHOICES}
# How the advanced filters are reached: behind a toggle (default), always open,
# or not offered at all — a list whose advanced fields are noise for its users.
#: How a strip nested under another attaches to it. Only ever visible on a list
#: that splits more than one way — with a single strip all three render the same,
#: which is why this is named for nesting rather than for tabs.
DEFAULT_RIBBON_NESTING = 'chain'
RIBBON_NESTING_CHOICES = (
    (DEFAULT_RIBBON_NESTING, 'Inline chain'),
    ('rail', 'Nested rail'),
    ('tiered', 'Tier by weight'),
)
RIBBON_NESTING_VALUES = {value for value, _label in RIBBON_NESTING_CHOICES}

DEFAULT_RIBBON_ADVANCED_TRIGGER = 'button'
RIBBON_ADVANCED_TRIGGER_CHOICES = (
    (DEFAULT_RIBBON_ADVANCED_TRIGGER, 'Toggle button'),
    ('always', 'Always open'),
    ('off', 'Hidden'),
)
RIBBON_ADVANCED_TRIGGER_VALUES = {v for v, _l in RIBBON_ADVANCED_TRIGGER_CHOICES}
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
# Max lengths for the optional public page SEO overrides (public_root_config).
PUBLIC_ROOT_TITLE_MAX_LENGTH = 120
PUBLIC_ROOT_META_DESCRIPTION_MAX_LENGTH = 300
DEFAULT_SIDEBAR_COLLAPSE_MODE = 'icons'
SIDEBAR_COLLAPSE_MODE_CHOICES = (
    (DEFAULT_SIDEBAR_COLLAPSE_MODE, 'Icons'),
    ('hidden', 'Hidden'),
    ('locked_expanded', 'Locked Expanded'),
)
SIDEBAR_COLLAPSE_MODE_VALUES = {value for value, _label in SIDEBAR_COLLAPSE_MODE_CHOICES}

# Glyph on the titlebar's sidebar-toggle button. Any icon from the loaded
# Bootstrap Icons font is allowed; the value lands in a `class` attribute, so the
# normalizer enforces this shape rather than trusting stored input.
DEFAULT_SIDEBAR_TOGGLE_ICON = 'bi-list'
SIDEBAR_TOGGLE_ICON_PATTERN = r'^bi-[a-z0-9]+(?:-[a-z0-9]+)*$'
SIDEBAR_TOGGLE_ICON_MAX_LENGTH = 64

# Arrows and chevrons read as "pointing at the sidebar", which flips meaning in
# RTL. These are mirrored by CSS; anything else renders as authored.
SIDEBAR_TOGGLE_DIRECTIONAL_ICONS = (
    'bi-arrow-bar-left',
    'bi-arrow-bar-right',
    'bi-arrow-left',
    'bi-arrow-left-short',
    'bi-arrow-right',
    'bi-arrow-right-short',
    'bi-chevron-left',
    'bi-chevron-right',
    'bi-chevron-double-left',
    'bi-chevron-double-right',
    'bi-chevron-bar-left',
    'bi-chevron-bar-right',
    'bi-caret-left',
    'bi-caret-left-fill',
    'bi-caret-right',
    'bi-caret-right-fill',
    'bi-text-indent-left',
    'bi-text-indent-right',
    'bi-indent',
    'bi-unindent',
    'bi-layout-sidebar',
    'bi-layout-sidebar-reverse',
    'bi-layout-sidebar-inset',
    'bi-layout-sidebar-inset-reverse',
    'bi-layout-text-sidebar',
    'bi-layout-text-sidebar-reverse',
    'bi-box-arrow-left',
    'bi-box-arrow-right',
    'bi-box-arrow-in-left',
    'bi-box-arrow-in-right',
)
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

# Setup wizard step order — the single source of truth for step indices.
#
# SystemSettingsForm addresses steps by index in three places at once: the layout
# Divs, the per-step `_clean_preserved_*` guards, and single-step modal saves. A
# literal that drifts out of step with the layout does not raise — the cleaner
# reads an absent checkbox as False and silently wipes another step's value
# (docs/adding-system-settings.md, trap 2). Names make that drift impossible.
THEME_PICKER_LOCATION_SIDEBAR = 'sidebar_toolbar'
THEME_PICKER_LOCATION_TITLEBAR = 'titlebar'
THEME_PICKER_LOCATION_DISABLED = 'disabled'
DEFAULT_THEME_PICKER_LOCATION = THEME_PICKER_LOCATION_SIDEBAR
THEME_PICKER_LOCATION_CHOICES = (
    (THEME_PICKER_LOCATION_SIDEBAR, 'Sidebar toolbar'),
    (THEME_PICKER_LOCATION_TITLEBAR, 'Titlebar action'),
    (THEME_PICKER_LOCATION_DISABLED, 'Options only'),
)
THEME_PICKER_LOCATION_VALUES = frozenset(value for value, _ in THEME_PICKER_LOCATION_CHOICES)


#: The setup wizard's steps, in the order they are presented.
#:
#: This tuple is the one place that order lives. The step constants below are
#: positions in it, and the wizard nav, the Options tiles, the step badges and
#: global search all read it instead of restating it — before this, order was
#: spelled out in five places and three of them had drifted: the Ribbon step
#: rendered fourteenth, announced itself as "Step 18", was opened by the nav
#: button labelled "Logging", and was missing from search entirely.
#:
#: A row is (slug, icon, search keywords). The slug names the step's strings:
#: `system_settings_<slug>` for its label, `<slug>_desc` for its description,
#: and `system_setup_step_<slug>` for the badge inside the panel. Adding a step
#: is one row here plus those strings.
#:
#: Order follows what a step depends on, then what it is about. Languages feeds
#: the per-language fonts on Themes & Fonts, which populates `allowed_themes`,
#: which fills the Homepage theme picker — so those three keep that sequence.
#: Titlebar precedes Sidebar and Navbar because it is the one piece of chrome
#: that cannot be turned off; the other two are optional.
SETUP_STEPS = (
    ('branding', 'bi-buildings-fill',
     ('identity', 'system name', 'logo', 'favicon', 'branding', 'organization')),
    ('languages', 'bi-translate',
     ('language', 'locale', 'translation', 'rtl', 'default language')),
    ('email', 'bi-envelope-at',
     ('email', 'smtp', 'mail', 'mail server', 'delivery', 'relay', 'sender',
      'from address', 'test email', 'verify email')),
    ('security', 'bi-shield-lock',
     ('security', '2fa', 'two factor', 'password', 'strong password', 'lockout',
      'login lockout', 'inactivity', 'timeout', 'session', 'purge session',
      'browser close', 'sign out', 'client ip', 'privacy', 'consent', 'registration')),
    ('appearance', 'bi-palette-fill',
     ('theme', 'appearance', 'font', 'typography', 'color', 'dark mode',
      'table edges', 'card edges', 'curved', 'rounded')),
    ('titlebar', 'bi-window-stack',
     ('titlebar', 'title bar', 'user hub', 'actions')),
    ('sidebar', 'bi-layout-sidebar-inset',
     ('sidebar', 'menu', 'navigation', 'collapse', 'side nav')),
    ('navbar', 'bi-signpost-split',
     ('navbar', 'nav bar', 'breadcrumb', 'hierarchy')),
    ('ribbon', 'bi-menu-button-wide-fill',
     ('ribbon', 'tabs', 'tab strip', 'filters', 'list header', 'page ribbon')),
    ('layout', 'bi-grid-1x2-fill',
     ('components', 'layout', 'table density', 'form density', 'modal size',
      'zebra', 'sticky headers', 'resizable columns', 'audit fields',
      'soft deleted', 'options page', 'row actions')),
    ('homepage', 'bi-house-gear-fill',
     ('homepage', 'home url', 'landing page', 'public homepage', 'public page',
      'public theme')),
    ('login_page', 'bi-box-arrow-in-right',
     ('login page', 'hero', 'banner', 'login style', 'split', 'centered')),
    ('profile', 'bi-person-badge',
     ('profile', 'avatar', 'profile page')),
    ('search', 'bi-search',
     ('global search', 'search', 'search mode', 'data records')),
    ('notifications', 'bi-bell-fill',
     ('notification', 'flash', 'toast', 'drawer', 'alerts')),
    ('logging', 'bi-journal-text',
     ('logging', 'activity log', 'audit', 'retention')),
    ('backups', 'bi-safe2-fill',
     ('backup', 'restore', 'export', 'import')),
    ('extras', 'bi-puzzle-fill',
     ('extra', 'features', 'integrations', 'scanlink', 'scanner', 'scan', 'twain')),
)

SETUP_STEP_SLUGS = tuple(slug for slug, _icon, _keywords in SETUP_STEPS)
SETUP_STEP_INDEX = {slug: index for index, slug in enumerate(SETUP_STEP_SLUGS)}

# Names kept as they were: `SETUP_STEP_LAYOUT` still backs `layout_config`, so
# renaming it to match the step's new label would only split the two apart.
SETUP_STEP_IDENTITY = SETUP_STEP_INDEX['branding']
SETUP_STEP_LANGUAGES = SETUP_STEP_INDEX['languages']
SETUP_STEP_EMAIL = SETUP_STEP_INDEX['email']
SETUP_STEP_SECURITY = SETUP_STEP_INDEX['security']
SETUP_STEP_APPEARANCE = SETUP_STEP_INDEX['appearance']
SETUP_STEP_TITLEBAR = SETUP_STEP_INDEX['titlebar']
SETUP_STEP_SIDEBAR = SETUP_STEP_INDEX['sidebar']
SETUP_STEP_NAVBAR = SETUP_STEP_INDEX['navbar']
SETUP_STEP_RIBBON = SETUP_STEP_INDEX['ribbon']
SETUP_STEP_LAYOUT = SETUP_STEP_INDEX['layout']
SETUP_STEP_HOMEPAGE = SETUP_STEP_INDEX['homepage']
SETUP_STEP_LOGIN = SETUP_STEP_INDEX['login_page']
SETUP_STEP_PROFILE = SETUP_STEP_INDEX['profile']
SETUP_STEP_SEARCH = SETUP_STEP_INDEX['search']
SETUP_STEP_NOTIFICATIONS = SETUP_STEP_INDEX['notifications']
SETUP_STEP_LOGGING = SETUP_STEP_INDEX['logging']
SETUP_STEP_BACKUPS = SETUP_STEP_INDEX['backups']
SETUP_STEP_EXTRAS = SETUP_STEP_INDEX['extras']
SETUP_STEP_COUNT = len(SETUP_STEPS)

EMAIL_CONFIG_TRANSPORTS = {'direct', 'relay'}
EMAIL_CONFIG_SECRET_STORAGES = {'env', 'encrypted_db'}
# Connection fields whose value the verification test vouches for. Any change to
# one of these re-arms verification (see normalize_email_config).
EMAIL_CONFIG_VERIFIED_FIELDS = (
    'transport',
    'secret_storage',
    'host',
    'port',
    'use_tls',
    'use_ssl',
    'username',
    'default_from_email',
    'encrypted_password',
)

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
    'homepage_config',
    'client_ip_config',
    'notification_config',
    'layout_config',
    'language_config',
    'theme_config',
    'typography_config',
    'login_config',
    'titlebar_config',
    'search_config',
    'sidebar_config',
    'ribbon_config',
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
    'login_logo',
    'login_background',
    'home_url',
    'homepage_config',
    'default_language',
    'default_theme',
    'allowed_themes',
    'theme_picker_location',
    'allow_user_theme_override',
    'allowed_fonts',
    'default_fonts',
    'allow_user_font_override',
    'allow_user_language_override',
    'default_table_density',
    'table_edges',
    'card_edges',
    'table_accent_edges',
    'default_form_density',
    'default_modal_size',
    'sticky_table_headers',
    'resizable_table_columns',
    'zebra_striping',
    'show_audit_fields',
    'show_soft_deleted',
    'options_style',
    'row_actions_style',
    'ribbon_layout',
    'ribbon_style',
    'ribbon_title',
    'ribbon_advanced_trigger',
    'ribbon_nesting',
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
    'ribbon_config',
    'navbar_config',
    'log_config',
    'profile_config',
    'backup_config',
    'titlebar_config',
    'search_config',
    'notification_config',
    'login_config',
    'extra_config',
)

__all__ = [name for name in globals() if name.isupper()]
