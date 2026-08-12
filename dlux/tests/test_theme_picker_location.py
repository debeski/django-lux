"""Where the theme picker lives: sidebar toolbar, titlebar action, or nowhere.

The stored value is intent. The sidebar toolbar can only host the picker while
the sidebar and its toolbar exist, so an unhostable choice resolves to the
titlebar rather than leaving users with no way to switch theme.
"""
from pathlib import Path

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from dlux.models import SystemSettings
from dlux.system.constants import (
    DEFAULT_THEME_PICKER_LOCATION,
    SYSTEM_SETTINGS_EXPORT_FIELDS,
    THEME_PICKER_LOCATION_VALUES,
)
from dlux.system.defaults import default_theme_config
from dlux.system.normalizers import normalize_theme_config
from dlux.utils.config import get_system_config
from dlux.utils.import_export import apply_system_settings_import

_STATIC = Path(__file__).resolve().parents[1] / 'static' / 'dlux'
_TEMPLATES = Path(__file__).resolve().parents[1] / 'templates' / 'dlux'


class ThemePickerLocationSettingTests(SimpleTestCase):
    def test_sidebar_toolbar_is_the_shipped_default(self):
        self.assertEqual(default_theme_config()['theme_picker_location'], 'sidebar_toolbar')
        self.assertEqual(DEFAULT_THEME_PICKER_LOCATION, 'sidebar_toolbar')

    def test_the_three_locations(self):
        self.assertEqual(THEME_PICKER_LOCATION_VALUES, {'sidebar_toolbar', 'titlebar', 'disabled'})

    def test_an_unknown_value_falls_back(self):
        self.assertEqual(
            normalize_theme_config({'theme_picker_location': 'nonsense'})['theme_picker_location'],
            'sidebar_toolbar',
        )

    def test_it_is_in_the_export_whitelist(self):
        # Without this the import normalizer silently drops it.
        self.assertIn('theme_picker_location', SYSTEM_SETTINGS_EXPORT_FIELDS)


class ThemePickerLocationPersistenceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.settings_row = SystemSettings.load()
        self.user = get_user_model().objects.create_user(
            username='p', password='pw-12345678', is_staff=True, is_superuser=True,
        )

    def test_it_survives_the_import_path_and_reaches_runtime(self):
        apply_system_settings_import(self.settings_row, {'theme_picker_location': 'titlebar'})
        cache.clear()

        self.assertEqual(SystemSettings.load().theme_picker_location, 'titlebar')
        self.assertEqual(get_system_config().get('theme_picker_location'), 'titlebar')

    def test_a_junk_value_clamps_at_runtime(self):
        apply_system_settings_import(self.settings_row, {'theme_picker_location': 'garbage'})
        cache.clear()

        self.assertEqual(get_system_config().get('theme_picker_location'), 'sidebar_toolbar')

    def test_saving_another_step_does_not_wipe_it(self):
        from dlux.forms import SystemSettingsForm

        apply_system_settings_import(self.settings_row, {'theme_picker_location': 'disabled'})
        cache.clear()
        row = SystemSettings.load()

        from django.test import RequestFactory

        # Single-step mode is driven by ?step=; step 0 is Identity, not Appearance.
        request = RequestFactory().post('/sys/settings/?step=0')
        request.user = self.user
        form = SystemSettingsForm(
            data={'system_name_en': 'X', 'system_name_ar': 'X'},
            instance=row,
            mode='options',
            request=request,
        )
        form.is_valid()

        self.assertEqual(form.cleaned_data.get('theme_picker_location'), 'disabled')


class ThemePickerLocationFormTests(TestCase):
    def setUp(self):
        cache.clear()

    def _form(self, **overrides):
        from dlux.forms import SystemSettingsForm

        row = SystemSettings.load()
        for key, value in overrides.items():
            setattr(row, key, value)
        row.is_configured = True
        row.save()
        cache.clear()
        return SystemSettingsForm(instance=SystemSettings.load())

    def test_the_sidebar_option_is_choosable_while_the_toolbar_exists(self):
        form = self._form()

        self.assertEqual(form.fields['theme_picker_location'].widget.disabled_values, set())
        self.assertEqual(form.initial['theme_picker_location'], 'sidebar_toolbar')

    def test_turning_the_sidebar_off_disables_the_option_and_moves_the_choice(self):
        row = SystemSettings.load()
        row.sidebar_config = {**(row.sidebar_config or {}), 'enabled': False}
        form = self._form(sidebar_config=row.sidebar_config)

        self.assertEqual(
            form.fields['theme_picker_location'].widget.disabled_values, {'sidebar_toolbar'},
        )
        self.assertEqual(form.initial['theme_picker_location'], 'titlebar')

    def test_turning_the_toolbar_off_disables_the_option_and_moves_the_choice(self):
        row = SystemSettings.load()
        row.sidebar_config = {**(row.sidebar_config or {}), 'show_toolbar': False}
        form = self._form(sidebar_config=row.sidebar_config)

        self.assertEqual(
            form.fields['theme_picker_location'].widget.disabled_values, {'sidebar_toolbar'},
        )
        self.assertEqual(form.initial['theme_picker_location'], 'titlebar')

    def test_a_disabled_option_renders_unchoosable(self):
        row = SystemSettings.load()
        row.sidebar_config = {**(row.sidebar_config or {}), 'enabled': False}
        form = self._form(sidebar_config=row.sidebar_config)

        html = str(form['theme_picker_location'])

        self.assertIn('is-disabled', html)
        self.assertIn('disabled', html)


class ThemePickerSurfaceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username='u', password='pw-12345678', is_staff=True, is_superuser=True,
        )
        row = SystemSettings.load()
        row.is_configured = True
        row.allowed_themes = ['light', 'dark']
        row.allow_user_theme_override = True
        row.layout_config = {**(row.layout_config or {}), 'options_style': 'tabs'}
        row.save()
        cache.clear()
        self.client = Client()
        self.client.force_login(self.user)

    def _set_location(self, location, **extra):
        row = SystemSettings.load()
        row.theme_picker_location = location
        for key, value in extra.items():
            setattr(row, key, value)
        row.save()
        cache.clear()

    def _options_html(self):
        return self.client.get(reverse('options_view')).content.decode()

    def test_the_titlebar_action_appears_only_for_that_location(self):
        self._set_location('titlebar')
        self.assertIn('data-dlux-theme-cycle', self._options_html())

        self._set_location('sidebar_toolbar')
        self.assertNotIn('data-dlux-theme-cycle', self._options_html())

        self._set_location('disabled')
        self.assertNotIn('data-dlux-theme-cycle', self._options_html())

    def test_the_card_vanishes_when_the_sidebar_toolbar_offers_a_two_theme_toggle(self):
        self._set_location('sidebar_toolbar')

        self.assertNotIn('data-options-card="theme"', self._options_html())

    def test_the_card_returns_when_the_picker_is_options_only(self):
        self._set_location('disabled')

        self.assertIn('data-options-card="theme"', self._options_html())

    def test_the_card_returns_when_the_sidebar_is_off(self):
        row = SystemSettings.load()
        self._set_location(
            'sidebar_toolbar',
            sidebar_config={**(row.sidebar_config or {}), 'enabled': False},
        )

        html = self._options_html()

        self.assertIn('data-options-card="theme"', html)
        # The picker had nowhere to live, so it resolved to the titlebar.
        self.assertIn('data-dlux-theme-cycle', html)

    def test_the_card_stays_with_three_themes(self):
        row = SystemSettings.load()
        row.allowed_themes = ['light', 'dark', 'neon']
        row.save()
        self._set_location('sidebar_toolbar')

        self.assertIn('data-options-card="theme"', self._options_html())


class ThemeCycleAssetTests(SimpleTestCase):
    def test_the_titlebar_action_has_its_own_script(self):
        js = (_STATIC / 'titlebar' / 'js' / 'theme_cycle.js').read_text(encoding='utf-8')

        self.assertIn("querySelectorAll('[data-dlux-theme-cycle]')", js)
        self.assertIn('window.setTheme(next);', js)
        self.assertIn("window.updatePreferences({ theme: next });", js)

    def test_it_is_loaded_globally(self):
        base = (_TEMPLATES / 'base.html').read_text(encoding='utf-8')

        self.assertIn("dlux/titlebar/js/theme_cycle.js", base)

    def test_the_settings_form_moves_the_choice_live(self):
        js = (_STATIC / 'setup' / 'js' / 'main.js').read_text(encoding='utf-8')

        self.assertIn('function syncThemePickerLocationAvailability(form)', js)
        self.assertIn('syncThemePickerLocationAvailability(form);', js)
        self.assertIn(".dlux-choice-option__input[value=\"sidebar_toolbar\"]", js)
        self.assertIn("titlebarInput.checked = true;", js)
