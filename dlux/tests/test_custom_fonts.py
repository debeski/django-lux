from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.test import SimpleTestCase, TestCase, override_settings

from dlux.fonts import (
    generate_font_face_css,
    get_available_fonts,
    get_font_by_slug,
    get_font_choices,
)
from dlux.forms import SystemSettingsForm
from dlux.system.defaults import default_typography_config
from dlux.system.normalizers import normalize_allowed_fonts, normalize_default_fonts


CUSTOM_FONTS = [
    {
        'slug': 'project_sans',
        'family': 'Project Sans',
        'label': 'Project Sans',
        'variants': [
            {'weight': 400, 'path': 'project/fonts/project-sans-regular.woff2'},
            {'weight': 700, 'path': 'project/fonts/project-sans-bold.woff2'},
        ],
    },
]


@override_settings(DLUX_CUSTOM_FONTS=CUSTOM_FONTS)
class CustomFontRegistryTests(SimpleTestCase):
    def test_custom_font_joins_the_available_registry(self):
        font = get_font_by_slug('project_sans')

        self.assertEqual(font['family'], 'Project Sans')
        self.assertIn(('project_sans', 'Project Sans'), get_font_choices())
        self.assertIn('project_sans', [item['slug'] for item in get_available_fonts()])

    def test_custom_font_uses_the_existing_typography_pipeline(self):
        defaults = default_typography_config()

        self.assertIn('project_sans', defaults['allowed_fonts'])
        self.assertEqual(
            normalize_allowed_fonts(['project_sans']),
            ['project_sans'],
        )
        self.assertEqual(
            normalize_default_fonts({'en': 'project_sans'}, allowed_fonts=['project_sans']),
            {'en': 'project_sans'},
        )

    def test_font_face_css_uses_project_static_assets_and_preview_family(self):
        css = generate_font_face_css(['project_sans'])

        self.assertIn("font-family: 'Project Sans';", css)
        self.assertIn(
            "url('/static/project/fonts/project-sans-regular.woff2') format('woff2')",
            css,
        )
        self.assertIn('data-font-option="project_sans"', css)

    @override_settings(DLUX_CUSTOM_FONTS=[
        CUSTOM_FONTS[0],
        {
            'slug': 'cairo',
            'family': 'Replacement',
            'variants': [{'weight': 400, 'path': 'project/fonts/replacement.woff2'}],
        },
        {
            'slug': 'unsafe',
            'family': '</style><script>alert(1)</script>',
            'variants': [{'weight': 400, 'path': 'project/fonts/unsafe.woff2'}],
        },
    ])
    def test_invalid_and_builtin_duplicate_entries_are_ignored(self):
        fonts = get_available_fonts()

        self.assertEqual([font['slug'] for font in fonts].count('cairo'), 1)
        self.assertEqual(get_font_by_slug('cairo')['family'], 'Cairo')
        self.assertIsNone(get_font_by_slug('unsafe'))


@override_settings(DLUX_CUSTOM_FONTS=CUSTOM_FONTS)
class CustomFontFormTests(TestCase):
    def test_system_settings_form_discovers_custom_font_at_runtime(self):
        form = SystemSettingsForm(mode='setup')

        self.assertIn(
            ('project_sans', 'Project Sans'),
            list(form.fields['allowed_fonts'].choices),
        )
        self.assertIn('data-font-option="project_sans"', form.font_picker_html)
