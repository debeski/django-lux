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
