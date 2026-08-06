from functools import lru_cache
import re

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
            {'weight': 400, 'path': 'dlux/fonts/cairo-regular.woff2'},
            {'weight': 600, 'path': 'dlux/fonts/cairo-medium.woff2'},
            {'weight': 800, 'path': 'dlux/fonts/cairo-bold.woff2'},
        ]
    },
    {
        'slug': 'changa',
        'family': 'Changa',
        'label': 'Changa',
        'variants': [
            {'weight': 400, 'path': 'dlux/fonts/Changa-Regular.woff2'},
            {'weight': 600, 'path': 'dlux/fonts/Changa-Medium.woff2'},
            {'weight': 800, 'path': 'dlux/fonts/Changa-Bold.woff2'},
        ]
    },
    {
        'slug': 'readex_pro',
        'family': 'Readex Pro',
        'label': 'Readex Pro',
        'variants': [
            {'weight': 400, 'path': 'dlux/fonts/ReadexPro-Regular.woff2'},
            {'weight': 600, 'path': 'dlux/fonts/ReadexPro-Medium.woff2'},
            {'weight': 800, 'path': 'dlux/fonts/ReadexPro-Bold.woff2'},
        ]
    },
    {
        'slug': 'alexandria',
        'family': 'Alexandria',
        'label': 'Alexandria',
        'variants': [
            {'weight': 400, 'path': 'dlux/fonts/Alexandria-Regular.woff2'},
            {'weight': 600, 'path': 'dlux/fonts/Alexandria-Medium.woff2'},
            {'weight': 800, 'path': 'dlux/fonts/Alexandria-Bold.woff2'},
        ]
    },
)


_FONT_SLUG_RE = re.compile(r'^[a-z][a-z0-9_-]{0,49}$')
_FONT_FAMILY_RE = re.compile(r'^\w[\w .-]{0,99}$')
_FONT_PATH_RE = re.compile(r'^[A-Za-z0-9_./@+-]+\.woff2$')


@lru_cache(maxsize=1)
def get_builtin_fonts():
    """Returns the list of hardcoded fonts available in the package."""
    return _FONT_REGISTRY


def _normalize_custom_font(value):
    if not isinstance(value, dict):
        return None

    slug = str(value.get('slug') or '').strip().lower()
    family = str(value.get('family') or '').strip()
    label = str(value.get('label') or family).strip()
    if (
        not _FONT_SLUG_RE.fullmatch(slug)
        or not _FONT_FAMILY_RE.fullmatch(family)
        or not label
        or len(label) > 100
    ):
        return None

    variants = []
    for variant in value.get('variants') or ():
        if not isinstance(variant, dict):
            continue
        path = str(variant.get('path') or '').strip()
        weight = variant.get('weight')
        if (
            isinstance(weight, bool)
            or not isinstance(weight, int)
            or weight < 100
            or weight > 900
            or weight % 100
            or not _FONT_PATH_RE.fullmatch(path)
            or path.startswith(('/', './', '../'))
            or '/..' in path
        ):
            continue
        variants.append({'weight': weight, 'path': path})

    if not variants:
        return None
    return {
        'slug': slug,
        'family': family,
        'label': label,
        'variants': variants,
    }


def get_available_fonts():
    """Return bundled fonts plus valid project fonts from DLUX_CUSTOM_FONTS."""
    fonts = list(get_builtin_fonts())
    known_slugs = {font['slug'] for font in fonts}
    configured = getattr(settings, 'DLUX_CUSTOM_FONTS', ())
    if not isinstance(configured, (list, tuple)):
        return tuple(fonts)

    for value in configured:
        font = _normalize_custom_font(value)
        if not font or font['slug'] in known_slugs:
            continue
        fonts.append(font)
        known_slugs.add(font['slug'])
    return tuple(fonts)


def get_font_choices():
    """Returns a tuple of (slug, label) for form fields."""
    return tuple((font['slug'], font['label']) for font in get_available_fonts())

def get_font_by_slug(slug):
    """Returns the font configuration dict for a given slug."""
    for font in get_available_fonts():
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
        fonts_to_load = get_available_fonts()

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

        slug = font['slug']
        family = font['family']
        css_lines.append(
            f'.dlux-font-option[data-font="{slug}"] .font-preview-sample,'
        )
        css_lines.append(
            f'.dlux-font-settings-option[data-font-option="{slug}"] .font-preview-sample {{'
        )
        css_lines.append(f"    font-family: '{family}', sans-serif !important;")
        css_lines.append("}")

    return "\n".join(css_lines)
