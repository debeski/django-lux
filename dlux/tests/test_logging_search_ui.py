from pathlib import Path
from unittest.mock import patch

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.test import TestCase

from dlux.forms import SystemSettingsForm
from dlux.models import SystemSettings
from dlux.translations.strings.ar import STRINGS as ARABIC_STRINGS


ROOT = Path(__file__).resolve().parents[1]


class LoggingStepSurfaceTests(TestCase):
    def test_compact_log_switches_use_the_dlux_wrapper_without_bootstrap_gutters(self):
        template = (ROOT / 'templates' / 'dlux' / 'setup' / 'log_builder.html').read_text(encoding='utf-8')
        stylesheet = (ROOT / 'static' / 'dlux' / 'setup' / 'css' / 'main.css').read_text(encoding='utf-8')

        self.assertNotIn('form-check form-switch dlux-log-switch', template)
        self.assertIn('dlux-settings-toggle-field__control form-switch dlux-log-switch', template)
        switch_rule = stylesheet.split(
            '.dlux-log-switch.dlux-settings-toggle-field__control {', 1
        )[1].split('}', 1)[0]
        self.assertIn('margin-inline-start: 0;', switch_rule)
        self.assertIn('padding: 0;', switch_rule)
        self.assertIn('gap:', switch_rule)

    def test_logging_groups_use_the_setup_theme_surface_contract(self):
        template = (ROOT / 'templates' / 'dlux' / 'setup' / 'log_builder.html').read_text(encoding='utf-8')
        stylesheet = (ROOT / 'static' / 'dlux' / 'setup' / 'css' / 'main.css').read_text(encoding='utf-8')

        self.assertNotIn('card border-0 shadow-sm rounded-4', template)
        self.assertIn('class="dlux-log-section"', template)
        section_rule = stylesheet.split('.dlux-log-section {', 1)[1].split('}', 1)[0]
        self.assertIn('var(--dlux-setup-item-border)', section_rule)
        self.assertIn('var(--dlux-setup-item-bg)', section_rule)
        self.assertIn('var(--dlux-setup-item-shadow)', section_rule)
        row_rule = stylesheet.split('.dlux-log-model-row {', 1)[1].split('}', 1)[0]
        self.assertIn('display: grid;', row_rule)


class GlobalSearchChoiceTranslationTests(TestCase):
    def test_arabic_form_renders_arabic_search_mode_choices(self):
        with patch('dlux.forms.system_settings.get_strings', return_value=ARABIC_STRINGS):
            form = SystemSettingsForm(
                instance=SystemSettings(default_language='ar', is_configured=False),
                mode='setup',
            )

        choices = dict(form.fields['titlebar_global_search_mode'].choices)
        self.assertEqual(choices['always'], ARABIC_STRINGS['global_search_mode_always'])
        self.assertEqual(choices['icon'], ARABIC_STRINGS['global_search_mode_icon'])
        self.assertEqual(choices['disabled'], ARABIC_STRINGS['global_search_mode_disabled'])
        rendered = form.fields['titlebar_global_search_mode'].widget.render(
            'titlebar_global_search_mode',
            'icon',
        )
        for label in choices.values():
            self.assertIn(str(label), rendered)
