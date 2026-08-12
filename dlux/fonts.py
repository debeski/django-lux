from functools import lru_cache
import re
import threading

from django.conf import settings
from django.apps import apps
from django.db import OperationalError, ProgrammingError, transaction
from django.core.signals import setting_changed
from django.dispatch import receiver
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


_request_cache = threading.local()


def clear_font_cache(**_kwargs):
    """Drop the per-request font memo.

    Called by DluxMiddleware at the start of every request, by managed-font
    writes, and whenever a setting the font list depends on changes.
    """
    _request_cache.fonts = None


@receiver(setting_changed)
def _clear_font_cache_on_setting_change(sender, setting=None, **kwargs):
    # The list folds in settings.DLUX_CUSTOM_FONTS, so an override_settings block
    # (or any runtime settings change) must not be served a memo built under the
    # previous value.
    if setting in {'DLUX_CUSTOM_FONTS', 'STATIC_URL', 'DLUX_CONFIG'}:
        clear_font_cache()


def get_available_fonts():
    """Return bundled, configured, and active UI-managed fonts.

    Memoised for the duration of a request. Config normalisation calls this from
    several places (allowed-font validation, defaults, theme resolution), so a
    single page used to run the managed-font query a few hundred times — cheap on
    SQLite, a few hundred round trips on PostgreSQL. The font list cannot change
    mid-request, so one lookup per request is equivalent and vastly cheaper.
    """
    cached = getattr(_request_cache, 'fonts', None)
    if cached is not None:
        return cached
    fonts = _build_available_fonts()
    _request_cache.fonts = fonts
    return fonts


def _build_available_fonts():
    fonts = list(get_builtin_fonts())
    known_slugs = {font['slug'] for font in fonts}
    configured = getattr(settings, 'DLUX_CUSTOM_FONTS', ())
    if isinstance(configured, (list, tuple)):
        for value in configured:
            font = _normalize_custom_font(value)
            if not font or font['slug'] in known_slugs:
                continue
            fonts.append(font)
            known_slugs.add(font['slug'])

    if apps.ready:
        try:
            # Savepoint, not just a try/except. On a bootstrap-from-empty database
            # this query fails because dlux_managedfontfamily does not exist yet —
            # and on PostgreSQL, catching the Python exception does not un-abort the
            # server-side transaction. Without the savepoint the *next* statement in
            # the enclosing atomic block dies instead, which is why the traceback
            # points at an unrelated migration operation and says nothing useful.
            with transaction.atomic():
                FontFamily = apps.get_model('dlux', 'ManagedFontFamily')
                managed_fonts = FontFamily.objects.filter(
                    is_active=True,
                    variants__asset__is_active=True,
                ).prefetch_related('variants__asset').distinct()
                for managed in managed_fonts:
                    if managed.slug in known_slugs:
                        continue
                    variants = [
                        {
                            'weight': variant.weight,
                            'style': variant.style,
                            'url': variant.asset.url,
                        }
                        for variant in managed.variants.all()
                        if variant.asset.is_active and variant.asset.url
                    ]
                    if not variants:
                        continue
                    fonts.append({
                        'slug': managed.slug,
                        'family': managed.family,
                        'label': managed.label,
                        'variants': variants,
                    })
                    known_slugs.add(managed.slug)
        except (AssertionError, LookupError, OperationalError, ProgrammingError, RuntimeError):
            pass
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
            url = variant.get('url') or static(variant['path'])
            css_lines.append(f"@font-face {{")
            css_lines.append(f"    font-family: '{font['family']}';")
            css_lines.append(f"    font-weight: {variant['weight']};")
            css_lines.append(f"    font-style: {variant.get('style', 'normal')};")
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
