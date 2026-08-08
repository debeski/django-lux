from pathlib import Path

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase

from dlux.context_processors import dlux_context
from dlux.models import SystemSettings


class SidebarThemeToggleTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = get_user_model().objects.create_user(
            username='theme-toggle-user',
            password='testpass123',
        )

    def _context(self, themes):
        cache.clear()
        settings_obj = SystemSettings.load()
        settings_obj.is_configured = True
        settings_obj.default_theme = themes[0]
        settings_obj.allowed_themes = themes
        settings_obj.allow_user_theme_override = True
        settings_obj.save()

        request = self.factory.get('/')
        request.session = {}
        request.user = self.user
        context = dlux_context(request)
        return request, context

    def _render_sidebar(self, themes):
        request, context = self._context(themes)
        return context, render_to_string('dlux/sidebar/main.html', context, request=request)

    def test_two_allowed_themes_render_direct_toggle_without_popup(self):
        context, html = self._render_sidebar(['light', 'dark'])

        self.assertTrue(context['sidebar_theme_picker_enabled'])
        self.assertTrue(context['sidebar_theme_toggle_enabled'])
        self.assertIn('data-sidebar-theme-toggle', html)
        self.assertIn('data-theme-cycle="light,dark"', html)
        self.assertEqual(html.count('data-theme-swatch'), 2)
        self.assertNotIn('id="sidebarThemePopup"', html)
        self.assertNotIn('id="sidebarThemeArrow"', html)
        self.assertNotIn('theme-option-circle', html)

    def test_three_allowed_themes_keep_popup_picker(self):
        context, html = self._render_sidebar(['light', 'dark', 'retro'])

        self.assertTrue(context['sidebar_theme_picker_enabled'])
        self.assertFalse(context['sidebar_theme_toggle_enabled'])
        self.assertNotIn('data-sidebar-theme-toggle', html)
        self.assertIn('id="sidebarThemePopup"', html)
        self.assertIn('id="sidebarThemeArrow"', html)
        self.assertEqual(html.count('theme-option-circle'), 3)

    def test_one_allowed_theme_hides_runtime_theme_control(self):
        context, html = self._render_sidebar(['light'])

        self.assertFalse(context['sidebar_theme_picker_enabled'])
        self.assertFalse(context['sidebar_theme_toggle_enabled'])
        self.assertNotIn('id="sidebarThemeIndicator"', html)

    def test_theme_script_cycles_only_the_two_theme_mode_and_persists(self):
        source = (
            Path(__file__).resolve().parents[1]
            / 'static/dlux/sidebar/js/theme_picker.js'
        ).read_text(encoding='utf-8')

        self.assertIn("indicator?.hasAttribute('data-sidebar-theme-toggle')", source)
        self.assertIn('if (themeNames.length !== 2) return;', source)
        self.assertIn('const next = themeNames[index === 0 ? 1 : 0];', source)
        self.assertIn('window.updatePreferences({ theme: theme });', source)
