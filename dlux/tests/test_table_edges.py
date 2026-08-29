from pathlib import Path

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from dlux.forms import SystemSettingsForm
from dlux.models import SystemSettings
from dlux.system.constants import SETUP_STEP_LAYOUT, SYSTEM_SETTINGS_EXPORT_FIELDS
from dlux.system.normalizers import normalize_layout_config
from dlux.utils.config import get_system_config
from dlux.utils.import_export import apply_system_settings_import, export_system_settings_payload


User = get_user_model()


def _set_table_edges(style):
    settings_obj = SystemSettings.load()
    settings_obj.is_configured = True
    settings_obj.layout_config = {**(settings_obj.layout_config or {}), 'table_edges': style}
    settings_obj.save()
    cache.clear()
    return settings_obj


class TableEdgesSettingTests(TestCase):
    def test_default_and_validation(self):
        self.assertEqual(normalize_layout_config({})['table_edges'], 'curved')
        self.assertEqual(normalize_layout_config({'table_edges': 'half_rounded'})['table_edges'], 'half_rounded')
        self.assertEqual(normalize_layout_config({'table_edges': 'normal'})['table_edges'], 'normal')
        self.assertEqual(normalize_layout_config({'table_edges': 'invalid'})['table_edges'], 'curved')

    def test_import_export_and_runtime_exposure(self):
        self.assertIn('table_edges', SYSTEM_SETTINGS_EXPORT_FIELDS)
        settings_obj = SystemSettings.load()
        settings_obj.is_configured = True
        apply_system_settings_import(settings_obj, {'table_edges': 'half_rounded'})
        cache.clear()

        reloaded = SystemSettings.load()
        self.assertEqual(reloaded.layout_config['table_edges'], 'half_rounded')
        self.assertEqual(get_system_config()['table_edges'], 'half_rounded')
        self.assertEqual(export_system_settings_payload(reloaded)['settings']['table_edges'], 'half_rounded')

    def test_layout_form_saves_half_rounded_edges(self):
        settings_obj = SystemSettings.load()
        settings_obj.is_configured = True
        settings_obj.save()
        request = RequestFactory().get(f'/sys/modals/dlux/systemsettings/{settings_obj.pk}/?step={SETUP_STEP_LAYOUT}')
        form = SystemSettingsForm(
            data={
                'system_names': '{"en":"System","ar":"System"}',
                'home_url': '/accounts/profile/',
                'default_language': 'en',
                'default_theme': 'light',
                'allowed_themes': ['light'],
                'languages': '{}',
                'translations_override': '{}',
                'sidebar_config': '{"entries":[]}',
                'default_table_density': 'balanced',
                'table_edges': 'half_rounded',
                'default_form_density': 'balanced',
                'default_modal_size': 'standard',
                'row_actions_style': 'context',
                'ribbon_layout': 'default',
                'ribbon_style': 'accent',
                'ribbon_advanced_trigger': 'button',
            },
            instance=settings_obj,
            request=request,
        )

        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save(commit=False)
        self.assertEqual(saved.layout_config['table_edges'], 'half_rounded')

    def test_form_renders_bilingual_choice_selector_contract(self):
        form = SystemSettingsForm(mode='setup')
        html = str(form['table_edges'])
        self.assertIn('data-dlux-selector-variant="toggle"', html)
        self.assertIn('value="curved"', html)
        self.assertIn('value="half_rounded"', html)
        self.assertIn('value="normal"', html)


class TableEdgesRenderTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('table-admin', 'table@example.com', 'pw12345!')
        self.client = Client()
        self.client.force_login(self.user)

    def test_base_emits_each_table_edge_style(self):
        for style in ('curved', 'half_rounded', 'normal'):
            with self.subTest(style=style):
                _set_table_edges(style)
                response = self.client.get(reverse('options_view'), follow=True)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, f'data-dlux-table-edges="{style}"')

    def test_table_css_uses_runtime_shape_variables(self):
        css = (Path(__file__).resolve().parents[1] / 'static/dlux/tables/css/main.css').read_text()
        self.assertIn('--dlux-table-edge-radius: 1.35rem;', css)
        self.assertIn('body[data-dlux-table-edges="normal"]', css)
        self.assertIn('body[data-dlux-table-edges="half_rounded"]', css)
        self.assertIn('--dlux-table-edge-radius: 0.375rem;', css)
        self.assertIn('--dlux-table-edge-shape: 0 0 1.35rem 1.35rem;', css)
        self.assertIn('border-radius: var(--dlux-table-edge-shape);', css)
        self.assertIn('clip-path: inset(0 round var(--dlux-table-edge-shape));', css)
