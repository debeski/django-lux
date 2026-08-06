import re
from functools import lru_cache
from pathlib import Path

from django.conf import settings


_THEME_REGISTRY = (
    {
        'slug': 'light',
        'color': '#f6f7f9',
        'label_key': 'theme_light',
        'preview_style': 'background: #f6f7f9;',
        'css_path': 'dlux/themes/css/light.css',
    },
    {
        'slug': 'blue',
        'color': '#2363c3',
        'label_key': 'theme_blue',
        'preview_style': 'background: #2363c3;',
        'css_path': 'dlux/themes/css/blue.css',
    },
    {
        'slug': 'gold',
        'color': '#d97706',
        'label_key': 'theme_gold',
        'preview_style': 'background: #d97706;',
        'css_path': 'dlux/themes/css/gold.css',
    },
    {
        'slug': 'green',
        'color': '#166534',
        'label_key': 'theme_green',
        'preview_style': 'background: #166534;',
        'css_path': 'dlux/themes/css/green.css',
    },
    {
        'slug': 'red',
        'color': '#7f1d1d',
        'label_key': 'theme_red',
        'preview_style': 'background: #7f1d1d;',
        'css_path': 'dlux/themes/css/red.css',
    },
    {
        'slug': 'mono',
        'color': '#64748b',
        'label_key': 'theme_mono',
        'preview_style': 'background: linear-gradient(135deg, #f8fafc 0%, #64748b 52%, #0f172a 100%);',
        'css_path': 'dlux/themes/css/mono.css',
    },
    {
        'slug': 'dark',
        'color': '#0f172a',
        'label_key': 'theme_dark',
        'preview_style': 'background: #0f172a;',
        'css_path': 'dlux/themes/css/dark.css',
    },
    {
        'slug': 'gothic',
        'color': '#00b4d8',
        'label_key': 'theme_gothic',
        'preview_style': 'background: linear-gradient(135deg, #00b4d8 0%, #9d4edd 55%, #0a0510 100%);',
        'css_path': 'dlux/themes/css/gothic.css',
    },
    {
        'slug': 'retro',
        'color': '#d4a574',
        'label_key': 'theme_retro',
        'preview_style': 'background: linear-gradient(135deg, #d4a574 0%, #b87333 55%, #0d0b0a 100%);',
        'css_path': 'dlux/themes/css/retro.css',
    },
    {
        'slug': 'neon',
        'color': '#00ffff',
        'label_key': 'theme_neon',
        'preview_style': 'background: linear-gradient(135deg, #00ffff 0%, #ff00ff 50%, #0a0a0f 100%);',
        'css_path': 'dlux/themes/css/neon.css',
    },
    {
        'slug': 'prism',
        'color': '#e8ecf2',
        'label_key': 'theme_prism',
        'preview_style': 'background: linear-gradient(145deg, #eef2f7 0%, #9aa8bc 24%, #3a4150 52%, #181b22 100%);',
        'css_path': 'dlux/themes/css/prism.css',
    },
    {
        'slug': 'aether',
        'color': '#a8ffe4',
        'label_key': 'theme_aether',
        'preview_style': 'background: linear-gradient(135deg, #0d1116 0%, #19212b 34%, #a8ffe4 56%, #83c9ff 72%, #c8a4ff 100%);',
        'css_path': 'dlux/themes/css/aether.css',
    },
)


_THEME_SLUG_RE = re.compile(r'^[a-z][a-z0-9_-]{0,49}$')
_THEME_COLOR_RE = re.compile(r'^#[0-9a-fA-F]{6}$')
_THEME_PATH_RE = re.compile(r'^[A-Za-z0-9_./@+-]+\.css$')


def _themes_dir():
    return Path(__file__).resolve().parent / 'static' / 'dlux' / 'themes' / 'css'


@lru_cache(maxsize=1)
def get_builtin_themes():
    available = {
        path.stem
        for path in _themes_dir().glob('*.css')
        if path.stem != 'main'
    }
    return tuple(theme for theme in _THEME_REGISTRY if theme['slug'] in available)


def _normalize_custom_theme(value):
    if not isinstance(value, dict):
        return None

    slug = str(value.get('slug') or '').strip().lower()
    label = str(value.get('label') or slug.replace('_', ' ').replace('-', ' ').title()).strip()
    preview_color = str(value.get('preview_color') or '').strip()
    css_path = str(value.get('css_path') or '').strip()
    if (
        not _THEME_SLUG_RE.fullmatch(slug)
        or not label
        or len(label) > 100
        or not _THEME_COLOR_RE.fullmatch(preview_color)
        or not _THEME_PATH_RE.fullmatch(css_path)
        or css_path.startswith(('/', './', '../'))
        or '/..' in css_path
    ):
        return None

    return {
        'slug': slug,
        'color': preview_color,
        'label': label,
        'label_key': '',
        'preview_style': f'background: {preview_color};',
        'css_path': css_path,
        'custom': True,
    }


def get_available_themes():
    themes = list(get_builtin_themes())
    known_slugs = {theme['slug'] for theme in themes}
    configured = getattr(settings, 'DLUX_CUSTOM_THEMES', ())
    if not isinstance(configured, (list, tuple)):
        return tuple(themes)

    for value in configured:
        theme = _normalize_custom_theme(value)
        if not theme or theme['slug'] in known_slugs:
            continue
        themes.append(theme)
        known_slugs.add(theme['slug'])
    return tuple(themes)


def get_theme_names():
    return tuple(theme['slug'] for theme in get_available_themes())


def get_theme_choices():
    return tuple(
        (theme['slug'], theme['color'], theme.get('label_key', ''))
        for theme in get_available_themes()
    )


def normalize_allowed_themes(allowed_themes=None):
    available_names = set(get_theme_names())
    if allowed_themes is None:
        return tuple(get_theme_names())

    normalized = []
    if isinstance(allowed_themes, (list, tuple, set)):
        for theme in allowed_themes:
            if theme in available_names and theme not in normalized:
                normalized.append(theme)

    return tuple(normalized or get_theme_names())


def get_theme_options(strings=None, allowed_themes=None):
    names = set(normalize_allowed_themes(allowed_themes))
    strings = strings or {}
    return [
        {
            **theme,
            'label': (
                theme.get('label')
                or strings.get(theme.get('label_key'), theme['slug'].replace('_', ' ').title())
            ),
        }
        for theme in get_available_themes()
        if theme['slug'] in names
    ]


def is_valid_theme(theme):
    return theme in set(get_theme_names())


def generate_theme_preview_css():
    return '\n'.join(
        f".dlux-theme-preview--{theme['slug']} {{ background: {theme['color']}; }}"
        for theme in get_available_themes()
        if theme.get('custom')
    )
