from dlux.tests.harness import setup_test_environment

setup_test_environment()

import re

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase

from dlux.system.normalizers import normalize_layout_config

User = get_user_model()


def _set_options_style(style):
    from dlux.models import SystemSettings

    SystemSettings.objects.all().delete()
    cache.clear()
    ss = SystemSettings.load()
    ss.is_configured = True
    ss.layout_config = {**(ss.layout_config or {}), 'options_style': style}
    ss.save()
    cache.clear()
    return ss


def _set_small_theme_language_options(style):
    ss = _set_options_style(style)
    ss.default_theme = 'light'
    ss.allowed_themes = ['light', 'dark']
    ss.allow_user_theme_override = True
    ss.default_language = 'en'
    ss.languages = {
        'en': {'name': 'English', 'dir': 'ltr', 'flag': 'GB'},
        'ar': {'name': 'Arabic', 'dir': 'rtl', 'flag': 'SA'},
    }
    ss.allow_user_language_override = True
    # These are the two themes the sidebar toolbar would offer as a direct
    # toggle, which now hides the Options card. Park the picker on the Options
    # page so these cases still have a themes card to lay out.
    ss.theme_picker_location = 'disabled'
    ss.save()
    cache.clear()
    return ss


class OptionsStyleNormalizerTests(TestCase):
    def test_default_is_tabs(self):
        self.assertEqual(normalize_layout_config({})['options_style'], 'tabs')

    def test_valid_values(self):
        self.assertEqual(normalize_layout_config({'options_style': 'tabs'})['options_style'], 'tabs')
        self.assertEqual(normalize_layout_config({'options_style': 'compact'})['options_style'], 'compact')

    def test_invalid_falls_back_to_the_default(self):
        self.assertEqual(normalize_layout_config({'options_style': 'nope'})['options_style'], 'tabs')


class OptionsStyleConfigExposureTests(TestCase):
    def test_flows_into_appearance_group(self):
        from dlux.utils import get_system_config
        from dlux.utils.config import build_config_groups

        _set_options_style('tabs')
        config = get_system_config()
        self.assertEqual(config.get('options_style'), 'tabs')
        self.assertEqual(build_config_groups(config)['appearance']['options_style'], 'tabs')


class OptionsStyleFormTests(TestCase):
    def test_field_present_and_composes(self):
        from dlux.forms import SystemSettingsForm

        form = SystemSettingsForm(mode='setup')
        self.assertIn('options_style', form.fields)
        form.cleaned_data = {'options_style': 'compact'}
        self.assertEqual(form._schema_group_from_cleaned('layout_config')['options_style'], 'compact')


class OptionsStylePersistenceTests(TestCase):
    def test_save_path_persists_json_only_key(self):
        # options_style has no legacy column — it must round-trip through the
        # layout_config JSON via apply_system_settings_import (the save path).
        from dlux.models import SystemSettings
        from dlux.utils import get_system_config
        from dlux.utils.import_export import apply_system_settings_import, export_system_settings_payload

        SystemSettings.objects.all().delete()
        cache.clear()
        ss = SystemSettings.load()
        apply_system_settings_import(ss, {'options_style': 'tabs'}, commit=True)
        self.assertEqual((ss.layout_config or {}).get('options_style'), 'tabs')
        cache.clear()
        self.assertEqual(get_system_config().get('options_style'), 'tabs')
        exported = export_system_settings_payload(ss)
        self.assertEqual(exported.get('settings', exported).get('options_style'), 'tabs')


class OptionsStyleRenderTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser('boss', 'boss@x.com', 'pw12345!')
        self.client = Client()

    def _rendered_style(self):
        self.client.force_login(self.superuser)
        html = self.client.get('/sys/options/').content.decode()
        match = re.search(r'data-options-style="(\w+)"', html)
        return match.group(1) if match else None

    def _rendered_html(self):
        self.client.force_login(self.superuser)
        return self.client.get('/sys/options/').content.decode()

    def test_each_style_renders_attribute(self):
        for style in ('cards', 'tabs', 'compact'):
            _set_options_style(style)
            self.assertEqual(self._rendered_style(), style)

    def test_theme_and_language_are_separate_cards_in_every_style(self):
        """They were once merged below a size threshold. That merge is gone:
        a card's identity no longer depends on how many themes exist."""
        for style in ('cards', 'tabs', 'compact'):
            with self.subTest(style=style):
                _set_small_theme_language_options(style)

                html = self._rendered_html()

                self.assertIn('data-options-card="theme"', html)
                self.assertIn('data-options-card="language"', html)


class OptionsEntranceTests(TestCase):
    """Options fades in like a project index (data-dlux-reveal, base/css/main.css);
    tests-e2e/options_entrance.test.mjs checks it plays once in a browser."""

    def test_options_marks_its_title_cards_tiles_and_footer(self):
        _set_options_style('cards')
        user = User.objects.create_superuser('reveal', 'reveal@x.com', 'pw12345!')
        client = Client()
        client.force_login(user)
        html = client.get('/sys/options/').content.decode()
        self.assertRegex(html, r'<h2 class="page-title[^"]*" data-dlux-reveal>')
        self.assertRegex(html, r'id="dluxOptionsGrid"\s+data-dlux-reveal-group')
        self.assertRegex(html, r'class="dlux-admin-panel-top" data-dlux-reveal-group')
        self.assertRegex(html, r'dlux-admin-settings-grid" data-dlux-reveal-group')
        self.assertRegex(html, r'class="dlux-options-reset-footer no-print" data-dlux-reveal>')

    def test_entrance_is_css_only_once_and_respects_reduced_motion(self):
        from django.contrib.staticfiles import finders

        css = open(finders.find('dlux/base/css/main.css'), encoding='utf-8').read()
        self.assertIn('@keyframes dlux-reveal-in', css)
        rule = css.split(':root:not(.dlux-reveal-done) [data-dlux-reveal-group] > * {', 1)[1].split('}', 1)[0]
        # backwards, not both: a finished entrance leaves no stacking context.
        self.assertIn('dlux-reveal-in 0.55s', rule)
        self.assertIn(' backwards;', rule)
        motion = css.split('@media (prefers-reduced-motion: reduce) {\n    [data-dlux-reveal]', 1)[1].split('}', 1)[0]
        self.assertIn('animation: none !important', motion)
        runtime = open(finders.find('dlux/base/js/base_runtime.js'), encoding='utf-8').read()
        self.assertIn("classList.add('dlux-reveal-done')", runtime)
