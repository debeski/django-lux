from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.test import SimpleTestCase, TestCase, override_settings

from dlux.forms import SystemSettingsForm
from dlux.system.defaults import default_theme_config
from dlux.system.normalizers import normalize_public_root_config, normalize_theme_config
from dlux.themes import (
    generate_theme_preview_css,
    get_available_themes,
    get_theme_choices,
    get_theme_names,
    get_theme_options,
    is_valid_theme,
    normalize_allowed_themes,
)


CUSTOM_THEMES = [
    {
        'slug': 'project_ocean',
        'label': 'Project Ocean',
        'preview_color': '#0ea5e9',
        'css_path': 'project/themes/ocean.css',
    },
]


@override_settings(DLUX_CUSTOM_THEMES=CUSTOM_THEMES)
class CustomThemeRegistryTests(SimpleTestCase):
    def test_custom_theme_joins_the_available_registry(self):
        options = get_theme_options({}, ['project_ocean'])

        self.assertIn('project_ocean', get_theme_names())
        self.assertTrue(is_valid_theme('project_ocean'))
        self.assertIn(('project_ocean', '#0ea5e9', ''), get_theme_choices())
        self.assertEqual(options[0]['label'], 'Project Ocean')
        self.assertEqual(options[0]['css_path'], 'project/themes/ocean.css')

    def test_custom_theme_uses_the_existing_theme_pipeline(self):
        defaults = default_theme_config()

        self.assertIn('project_ocean', defaults['allowed_themes'])
        self.assertEqual(normalize_allowed_themes(['project_ocean']), ('project_ocean',))
        self.assertEqual(
            normalize_theme_config({'allowed_themes': ['project_ocean']})['allowed_themes'],
            ['project_ocean'],
        )
        self.assertEqual(
            normalize_public_root_config({'public_root_theme': 'project_ocean'})['public_root_theme'],
            'project_ocean',
        )

    def test_custom_theme_generates_safe_preview_css(self):
        css = generate_theme_preview_css()

        self.assertEqual(
            css,
            '.dlux-theme-preview--project_ocean { background: #0ea5e9; }',
        )

    @override_settings(DLUX_CUSTOM_THEMES=[
        CUSTOM_THEMES[0],
        {
            'slug': 'light',
            'label': 'Replacement',
            'preview_color': '#000000',
            'css_path': 'project/themes/replacement.css',
        },
        {
            'slug': 'unsafe',
            'label': 'Unsafe',
            'preview_color': 'url(javascript:alert(1))',
            'css_path': 'project/themes/unsafe.css',
        },
    ])
    def test_invalid_and_builtin_duplicate_entries_are_ignored(self):
        themes = get_available_themes()

        self.assertEqual([theme['slug'] for theme in themes].count('light'), 1)
        self.assertNotEqual(
            next(theme for theme in themes if theme['slug'] == 'light')['css_path'],
            'project/themes/replacement.css',
        )
        self.assertFalse(is_valid_theme('unsafe'))


@override_settings(DLUX_CUSTOM_THEMES=CUSTOM_THEMES)
class CustomThemeFormTests(TestCase):
    def test_system_settings_form_discovers_custom_theme_at_runtime(self):
        form = SystemSettingsForm(mode='setup')

        self.assertIn(
            ('project_ocean', 'project_ocean'),
            list(form.fields['default_theme'].choices),
        )
        self.assertIn('data-theme-option="project_ocean"', form.theme_picker_html)
        self.assertIn('project/themes/ocean.css', form.theme_picker_html)
