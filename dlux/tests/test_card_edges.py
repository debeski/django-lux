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


def _set_card_edges(style):
    settings_obj = SystemSettings.load()
    settings_obj.is_configured = True
    settings_obj.layout_config = {**(settings_obj.layout_config or {}), 'card_edges': style}
    settings_obj.save()
    cache.clear()
    return settings_obj


class CardEdgesSettingTests(TestCase):
    def test_default_and_validation(self):
        self.assertEqual(normalize_layout_config({})['card_edges'], 'curved')
        self.assertEqual(normalize_layout_config({'card_edges': 'half_rounded'})['card_edges'], 'half_rounded')
        self.assertEqual(normalize_layout_config({'card_edges': 'normal'})['card_edges'], 'normal')
        self.assertEqual(normalize_layout_config({'card_edges': 'invalid'})['card_edges'], 'curved')

    def test_import_export_and_runtime_exposure(self):
        self.assertIn('card_edges', SYSTEM_SETTINGS_EXPORT_FIELDS)
        settings_obj = SystemSettings.load()
        settings_obj.is_configured = True
        apply_system_settings_import(settings_obj, {'card_edges': 'half_rounded'})
        cache.clear()

        reloaded = SystemSettings.load()
        self.assertEqual(reloaded.layout_config['card_edges'], 'half_rounded')
        self.assertEqual(get_system_config()['card_edges'], 'half_rounded')
        self.assertEqual(export_system_settings_payload(reloaded)['settings']['card_edges'], 'half_rounded')

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
                'table_edges': 'curved',
                'card_edges': 'half_rounded',
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
        self.assertEqual(saved.layout_config['card_edges'], 'half_rounded')

    def test_form_renders_bilingual_choice_selector_contract(self):
        form = SystemSettingsForm(mode='setup')
        html = str(form['card_edges'])
        self.assertIn('data-dlux-selector-variant="toggle"', html)
        self.assertIn('value="curved"', html)
        self.assertIn('value="half_rounded"', html)
        self.assertIn('value="normal"', html)


class CardEdgesRenderTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('card-admin', 'card@example.com', 'pw12345!')
        self.client = Client()
        self.client.force_login(self.user)

    def test_base_emits_each_card_edge_style(self):
        for style in ('curved', 'half_rounded', 'normal'):
            with self.subTest(style=style):
                _set_card_edges(style)
                response = self.client.get(reverse('options_view'), follow=True)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, f'data-dlux-card-edges="{style}"')

    def test_card_css_normalizes_outer_cards_only(self):
        css = (Path(__file__).resolve().parents[1] / 'static/dlux/base/css/card_edges.css').read_text()
        self.assertIn('body[data-dlux-card-edges="normal"]', css)
        self.assertIn('body[data-dlux-card-edges="half_rounded"]', css)
        self.assertIn('--dlux-card-edge-radius: 0.375rem;', css)
        self.assertIn('--dlux-card-edge-shape: 0 0 1.35rem 1.35rem;', css)
        self.assertIn('.card:not(.dlux-table-card)', css)
        self.assertIn('.glass-card:not(.modal-content):not(.dlux-table-card)', css)
        self.assertIn('border-radius: var(--dlux-card-edge-shape) !important;', css)
