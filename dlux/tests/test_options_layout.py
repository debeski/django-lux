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


class OptionsStyleNormalizerTests(TestCase):
    def test_default_is_cards(self):
        self.assertEqual(normalize_layout_config({})['options_style'], 'cards')

    def test_valid_values(self):
        self.assertEqual(normalize_layout_config({'options_style': 'tabs'})['options_style'], 'tabs')
        self.assertEqual(normalize_layout_config({'options_style': 'compact'})['options_style'], 'compact')

    def test_invalid_falls_back_to_cards(self):
        self.assertEqual(normalize_layout_config({'options_style': 'nope'})['options_style'], 'cards')


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

    def test_each_style_renders_attribute(self):
        for style in ('cards', 'tabs', 'compact'):
            _set_options_style(style)
            self.assertEqual(self._rendered_style(), style)
