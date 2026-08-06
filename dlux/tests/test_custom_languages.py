from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.test import SimpleTestCase, TestCase

from dlux.forms import SystemSettingsForm
from dlux.system.normalizers import normalize_language_catalog
from dlux.translations import discover_translation_languages


CUSTOM_CATALOG = {
    'sw': {'name': 'Kiswahili', 'dir': 'ltr', 'flag': '🇰🇪'},
    'ckb': {'name': 'Soranî', 'dir': 'rtl', 'flag': '🏴'},
}


class CustomLanguageRegistryTests(SimpleTestCase):
    def test_custom_language_joins_the_default_catalog(self):
        catalog = normalize_language_catalog(CUSTOM_CATALOG)

        self.assertIn('en', catalog)
        self.assertIn('ar', catalog)
        self.assertEqual(catalog['sw'], {'name': 'Kiswahili', 'dir': 'ltr', 'flag': '🇰🇪'})
        self.assertEqual(catalog['ckb']['dir'], 'rtl')

    def test_string_shorthand_and_direction_inference(self):
        catalog = normalize_language_catalog({'sw': 'Kiswahili', 'fa': 'فارسی'})

        self.assertEqual(catalog['sw'], {'name': 'Kiswahili', 'dir': 'ltr', 'flag': ''})
        self.assertEqual(catalog['fa']['dir'], 'rtl')

    def test_bogus_language_codes_are_dropped(self):
        catalog = normalize_language_catalog({
            'x': {'name': 'Too short'},
            '123': {'name': 'Numeric'},
            '': {'name': 'Empty'},
            'sw': {'name': 'Kiswahili'},
        })

        self.assertNotIn('x', catalog)
        self.assertNotIn('123', catalog)
        self.assertNotIn('', catalog)
        self.assertIn('sw', catalog)

    def test_translation_only_language_is_discoverable(self):
        discovered = discover_translation_languages({'sw': {'greeting': 'Habari'}})

        self.assertIn('sw', discovered)
        self.assertNotIn('sw', normalize_language_catalog())


class CustomLanguageFormTests(TestCase):
    def _form(self, **initial):
        return SystemSettingsForm(mode='modal', initial=initial)

    def test_custom_language_flows_into_the_settings_editors(self):
        form = self._form(
            languages=CUSTOM_CATALOG,
            system_names={'sw': 'Mfumo'},
        )

        self.assertIn('sw', form.language_catalog_html)
        self.assertIn('Kiswahili', form.language_catalog_html)
        self.assertIn('ckb', form.language_catalog_html)
        self.assertIn('sw', form.system_names_html)
        self.assertIn('Kiswahili', form.system_names_html)
        self.assertIn('sw', form.translation_matrix_html)

    def test_translation_only_language_is_surfaced_as_a_suggestion(self):
        form = self._form(translations_override={'sw': {'greeting': 'Habari'}})

        self.assertIn('sw', form.language_catalog_html)

    def test_custom_language_survives_clean(self):
        form = SystemSettingsForm(mode='setup')
        form.cleaned_data = {'languages': CUSTOM_CATALOG}

        cleaned = form.clean_languages()

        self.assertEqual(cleaned['sw']['name'], 'Kiswahili')
        self.assertEqual(cleaned['ckb']['dir'], 'rtl')
        self.assertIn('en', cleaned)
