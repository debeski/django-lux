DEFAULT_HOME_URL = '/accounts/profile/'
LEGACY_HOME_URL = '/sys/'
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
