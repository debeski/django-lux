from functools import lru_cache
from django.conf import settings
from django.templatetags.static import static

DEFAULT_FONT_SLUG = 'cairo'
DEFAULT_FONT_FAMILY = 'Cairo'

# Registry for built-in fonts provided by the package
_FONT_REGISTRY = (
    {
        'slug': 'cairo',
        'family': 'Cairo',
        'label': 'Cairo',
        'variants': [
            {'weight': 400, 'path': 'microsys/fonts/cairo-regular.woff2'},
            {'weight': 600, 'path': 'microsys/fonts/cairo-medium.woff2'},
            {'weight': 800, 'path': 'microsys/fonts/cairo-bold.woff2'},
        ]
    },
    {
        'slug': 'changa',
        'family': 'Changa',
        'label': 'Changa',
        'variants': [
            {'weight': 400, 'path': 'microsys/fonts/Changa-Regular.woff2'},
            {'weight': 600, 'path': 'microsys/fonts/Changa-Medium.woff2'},
            {'weight': 800, 'path': 'microsys/fonts/Changa-Bold.woff2'},
        ]
    },
    # {
    #     'slug': 'markazi_text',
    #     'family': 'Markazi Text',
    #     'label': 'Markazi Text',
    #     'variants': [
    #         {'weight': 400, 'path': 'microsys/fonts/MarkaziText-Regular.woff2'},
    #         {'weight': 600, 'path': 'microsys/fonts/MarkaziText-Medium.woff2'},
    #         {'weight': 800, 'path': 'microsys/fonts/MarkaziText-Bold.woff2'},
    #     ]
    # },
    {
        'slug': 'readex_pro',
        'family': 'Readex Pro',
        'label': 'Readex Pro',
        'variants': [
            {'weight': 400, 'path': 'microsys/fonts/ReadexPro-Regular.woff2'},
            {'weight': 600, 'path': 'microsys/fonts/ReadexPro-Medium.woff2'},
            {'weight': 800, 'path': 'microsys/fonts/ReadexPro-Bold.woff2'},
        ]
    },
    {
        'slug': 'alexandria',
        'family': 'Alexandria',
        'label': 'Alexandria',
        'variants': [
            {'weight': 400, 'path': 'microsys/fonts/Alexandria-Regular.woff2'},
            {'weight': 600, 'path': 'microsys/fonts/Alexandria-Medium.woff2'},
            {'weight': 800, 'path': 'microsys/fonts/Alexandria-Bold.woff2'},
        ]
    },
)

@lru_cache(maxsize=1)
def get_builtin_fonts():
    """Returns the list of hardcoded fonts available in the package."""
    return _FONT_REGISTRY

def get_font_choices():
    """Returns a tuple of (slug, label) for form fields."""
    return tuple((f['slug'], f['label']) for f in _FONT_REGISTRY)

def get_font_by_slug(slug):
    """Returns the font configuration dict for a given slug."""
    for font in _FONT_REGISTRY:
        if font['slug'] == slug:
            return font
    return None

def get_default_font_family():
    default_font = get_font_by_slug(DEFAULT_FONT_SLUG)
    if default_font:
        return default_font['family']
    return DEFAULT_FONT_FAMILY

def generate_font_face_css(allowed_fonts=None):
    """
    Generates the @font-face CSS block for all allowed fonts.
    This can be injected into the base template.
    """
    fonts_to_load = []
    if allowed_fonts:
        for slug in allowed_fonts:
            font = get_font_by_slug(slug)
            if font:
                fonts_to_load.append(font)
    else:
        fonts_to_load = _FONT_REGISTRY

    css_lines = []
    for font in fonts_to_load:
        for variant in font['variants']:
            # We use static() to resolve the path correctly
            url = static(variant['path'])
            css_lines.append(f"@font-face {{")
            css_lines.append(f"    font-family: '{font['family']}';")
            css_lines.append(f"    font-weight: {variant['weight']};")
            css_lines.append(f"    font-style: normal;")
            css_lines.append(f"    src: url('{url}') format('woff2');")
            css_lines.append(f"    font-display: swap;")
            css_lines.append(f"}}")
    
    return "\n".join(css_lines)
