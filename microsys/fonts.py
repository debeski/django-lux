from functools import lru_cache
from django.conf import settings
from django.templatetags.static import static

# Registry for built-in fonts provided by the package
_FONT_REGISTRY = (
    {
        'slug': 'shabwa',
        'family': 'Shabwa',
        'label': 'Shabwa',
        'variants': [
            {'weight': 400, 'path': 'microsys/fonts/shabwa-regular.woff2'},
            {'weight': 600, 'path': 'microsys/fonts/shabwa-medium.woff2'},
            {'weight': 800, 'path': 'microsys/fonts/shabwa-bold.woff2'},
        ]
    },
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
