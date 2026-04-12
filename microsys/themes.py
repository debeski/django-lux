from functools import lru_cache
from pathlib import Path


_THEME_REGISTRY = (
    {
        'slug': 'light',
        'color': '#f6f7f9',
        'label_key': 'theme_light',
        'preview_style': 'background: #f6f7f9;',
        'css_path': 'microsys/themes/css/light.css',
    },
    {
        'slug': 'blue',
        'color': '#2363c3',
        'label_key': 'theme_blue',
        'preview_style': 'background: #2363c3;',
        'css_path': 'microsys/themes/css/blue.css',
    },
    {
        'slug': 'gold',
        'color': '#d97706',
        'label_key': 'theme_gold',
        'preview_style': 'background: #d97706;',
        'css_path': 'microsys/themes/css/gold.css',
    },
    {
        'slug': 'green',
        'color': '#166534',
        'label_key': 'theme_green',
        'preview_style': 'background: #166534;',
        'css_path': 'microsys/themes/css/green.css',
    },
    {
        'slug': 'red',
        'color': '#7f1d1d',
        'label_key': 'theme_red',
        'preview_style': 'background: #7f1d1d;',
        'css_path': 'microsys/themes/css/red.css',
    },
    {
        'slug': 'mono',
        'color': '#64748b',
        'label_key': 'theme_mono',
        'preview_style': 'background: linear-gradient(135deg, #f8fafc 0%, #64748b 52%, #0f172a 100%);',
        'css_path': 'microsys/themes/css/mono.css',
    },
    {
        'slug': 'dark',
        'color': '#0f172a',
        'label_key': 'theme_dark',
        'preview_style': 'background: #0f172a;',
        'css_path': 'microsys/themes/css/dark.css',
    },
    {
        'slug': 'gothic',
        'color': '#00b4d8',
        'label_key': 'theme_gothic',
        'preview_style': 'background: linear-gradient(135deg, #00b4d8 0%, #9d4edd 55%, #0a0510 100%);',
        'css_path': 'microsys/themes/css/gothic.css',
    },
    {
        'slug': 'retro',
        'color': '#d4a574',
        'label_key': 'theme_retro',
        'preview_style': 'background: linear-gradient(135deg, #d4a574 0%, #b87333 55%, #0d0b0a 100%);',
        'css_path': 'microsys/themes/css/retro.css',
    },
    {
        'slug': 'neon',
        'color': '#00ffff',
        'label_key': 'theme_neon',
        'preview_style': 'background: linear-gradient(135deg, #00ffff 0%, #ff00ff 50%, #0a0a0f 100%);',
        'css_path': 'microsys/themes/css/neon.css',
    },
)


def _themes_dir():
    return Path(__file__).resolve().parent / 'static' / 'microsys' / 'themes' / 'css'


@lru_cache(maxsize=1)
def get_theme_names():
    available = {
        path.stem
        for path in _themes_dir().glob('*.css')
        if path.stem != 'main'
    }
    return tuple(theme['slug'] for theme in _THEME_REGISTRY if theme['slug'] in available)


def get_theme_choices():
    names = set(get_theme_names())
    return tuple(
        (theme['slug'], theme['color'], theme['label_key'])
        for theme in _THEME_REGISTRY
        if theme['slug'] in names
    )


def get_theme_options(strings=None):
    names = set(get_theme_names())
    strings = strings or {}
    return [
        {
            **theme,
            'label': strings.get(theme['label_key'], theme['slug'].replace('_', ' ').title()),
        }
        for theme in _THEME_REGISTRY
        if theme['slug'] in names
    ]


def is_valid_theme(theme):
    return theme in set(get_theme_names())
