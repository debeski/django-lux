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
