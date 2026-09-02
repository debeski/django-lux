from pathlib import Path

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.template import Context, Template
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from dlux.forms import SystemSettingsForm
from dlux.models import SystemSettings
from dlux.system.constants import SETUP_STEP_LAYOUT, SETUP_STEP_SIDEBAR, SETUP_STEP_TITLEBAR, SYSTEM_SETTINGS_EXPORT_FIELDS
from dlux.system.normalizers import normalize_layout_config, normalize_sidebar_behavior, normalize_titlebar_config
from dlux.utils.config import get_system_config
from dlux.utils.import_export import apply_system_settings_import, export_system_settings_payload


User = get_user_model()


def _set_accent_edges(*, sidebar=False, titlebar=False, table=False):
    settings_obj = SystemSettings.load()
    settings_obj.is_configured = True
    settings_obj.sidebar_config = {**(settings_obj.sidebar_config or {}), 'accent_edge': sidebar}
    settings_obj.titlebar_config = {**(settings_obj.titlebar_config or {}), 'accent_edge': titlebar}
    settings_obj.layout_config = {**(settings_obj.layout_config or {}), 'table_accent_edges': table}
    settings_obj.save()
    cache.clear()
    return settings_obj


def _form_data(**overrides):
    data = {
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
        'card_edges': 'curved',
        'default_form_density': 'balanced',
        'default_modal_size': 'standard',
        'row_actions_style': 'context',
        'ribbon_layout': 'default',
        'ribbon_style': 'accent',
        'ribbon_advanced_trigger': 'button',
    }
    data.update(overrides)
    return data


class AccentEdgesSettingTests(TestCase):
    def test_default_and_normalization(self):
        self.assertIs(normalize_layout_config({})['table_accent_edges'], False)
        self.assertIs(normalize_sidebar_behavior({})['accent_edge'], False)
        self.assertIs(normalize_titlebar_config({})['accent_edge'], False)
        self.assertIs(normalize_layout_config({'table_accent_edges': True})['table_accent_edges'], True)
        self.assertIs(normalize_sidebar_behavior({'accent_edge': True})['accent_edge'], True)
        self.assertIs(normalize_titlebar_config({'accent_edge': True})['accent_edge'], True)

    def test_import_export_and_runtime_exposure(self):
        self.assertIn('table_accent_edges', SYSTEM_SETTINGS_EXPORT_FIELDS)
        settings_obj = SystemSettings.load()
        settings_obj.is_configured = True
        apply_system_settings_import(settings_obj, {
            'table_accent_edges': True,
            'sidebar_config': {'entries': [], 'accent_edge': True},
            'titlebar_config': {'accent_edge': True},
        })
        cache.clear()

        reloaded = SystemSettings.load()
        self.assertIs(reloaded.layout_config['table_accent_edges'], True)
        self.assertIs(reloaded.sidebar_config['accent_edge'], True)
        self.assertIs(reloaded.titlebar_config['accent_edge'], True)
        runtime = get_system_config()
        self.assertIs(runtime['appearance']['table_accent_edges'], True)
        self.assertIs(runtime['navigation']['sidebar']['accent_edge'], True)
        self.assertIs(runtime['appearance']['titlebar']['accent_edge'], True)
        exported = export_system_settings_payload(reloaded)['settings']
        self.assertIs(exported['table_accent_edges'], True)
        self.assertIs(exported['sidebar_config']['accent_edge'], True)
        self.assertIs(exported['titlebar_config']['accent_edge'], True)

    def test_each_step_saves_only_its_accent_setting(self):
        settings_obj = SystemSettings.load()
        settings_obj.is_configured = True
        settings_obj.save()

        cases = (
            (SETUP_STEP_SIDEBAR, {'sidebar_enabled': 'on', 'sidebar_accent_edge': 'on'}, 'sidebar_config'),
            (SETUP_STEP_TITLEBAR, {'titlebar_accent_edge': 'on'}, 'titlebar_config'),
            (SETUP_STEP_LAYOUT, {'table_accent_edges': 'on'}, 'layout_config'),
        )
        for step, overrides, storage_field in cases:
            with self.subTest(step=step):
                request = RequestFactory().get(f'/sys/modals/dlux/systemsettings/{settings_obj.pk}/?step={step}')
                form = SystemSettingsForm(
                    data=_form_data(**overrides),
                    instance=settings_obj,
                    request=request,
                )
                self.assertTrue(form.is_valid(), form.errors)
                saved = form.save(commit=False)
                key = 'table_accent_edges' if storage_field == 'layout_config' else 'accent_edge'
                self.assertIs(getattr(saved, storage_field)[key], True)
                settings_obj = saved

    def test_switches_are_rendered_in_their_own_steps(self):
        source = (Path(__file__).resolve().parents[1] / 'forms/system_settings_groups/layout.py').read_text(encoding='utf-8')
        def step_source(slug, constant):
            """A step's body, sliced by its own markers rather than by position.

            This used to slice between numbered badge keys, which made a test
            about where three switches live fail the moment the steps were
            reordered.
            """
            start = source.index(f"self._step_badge(s, '{slug}'")
            return source[start:source.index(f"_step_css_class(SETUP_STEP_{constant})", start)]

        sidebar_step = step_source('sidebar', 'SIDEBAR')
        titlebar_step = step_source('titlebar', 'TITLEBAR')
        layout_step = step_source('layout', 'LAYOUT')

        self.assertIn("'sidebar_accent_edge'", sidebar_step)
        self.assertIn("'titlebar_accent_edge'", titlebar_step)
        self.assertIn("'table_accent_edges'", layout_step)
        self.assertNotIn("'titlebar_accent_edge'", sidebar_step)
        self.assertNotIn("'sidebar_accent_edge'", titlebar_step)

        def row_from(step_source, first_field):
            start = step_source.index(f"'{first_field}'")
            end = step_source.index("css_class='g-3 mb-3'", start)
            return step_source[start:end]

        self.assertIn("'sidebar_accent_edge'", row_from(sidebar_step, 'sidebar_show_icons'))
        self.assertIn("'titlebar_accent_edge'", row_from(titlebar_step, 'titlebar_show_language_switcher'))
        self.assertIn("'sticky_table_headers'", row_from(layout_step, 'table_accent_edges'))
        self.assertIn("'zebra_striping'", row_from(layout_step, 'resizable_table_columns'))

        form = SystemSettingsForm(instance=SystemSettings(is_configured=False), mode='setup')
        html = Template('{% load crispy_forms_tags %}{% crispy form %}').render(Context({'form': form}))
        for field_name in ('sidebar_accent_edge', 'titlebar_accent_edge', 'table_accent_edges'):
            self.assertIn(f"data-dlux-settings-toggle-field='{field_name}'", html)
            self.assertIn(f"id='id_{field_name}'", html)


class AccentEdgesRenderTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('accent-admin', 'accent@example.com', 'pw12345!')
        self.client = Client()
        self.client.force_login(self.user)

    def test_base_emits_independent_accent_edge_states(self):
        _set_accent_edges(sidebar=True, titlebar=False, table=True)
        response = self.client.get(reverse('options_view'), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-dlux-sidebar-accent="on"')
        self.assertContains(response, 'data-dlux-titlebar-accent="off"')
        self.assertContains(response, 'data-dlux-table-accent="on"')

    def test_css_uses_native_served_stylesheets_and_logical_edges(self):
        root = Path(__file__).resolve().parents[1]
        sidebar_css = (root / 'static/dlux/sidebar/css/main.css').read_text(encoding='utf-8')
        titlebar_css = (root / 'static/dlux/titlebar/css/surfaces.css').read_text(encoding='utf-8')
        table_css = (root / 'static/dlux/tables/css/main.css').read_text(encoding='utf-8')
        base = (root / 'templates/dlux/base.html').read_text(encoding='utf-8')

        self.assertIn('body[data-dlux-sidebar-accent="on"] #sidebar', sidebar_css)
        self.assertIn('border-inline-end: .25rem solid var(--primal', sidebar_css)
        self.assertIn(':root body[data-dlux-titlebar-accent="on"] .titlebar', titlebar_css)
        self.assertIn('border-block-end: .25rem solid var(--primal', titlebar_css)
        self.assertGreater(
            titlebar_css.index('data-dlux-titlebar-accent="on"'),
            titlebar_css.index('data-titlebar-surface="glass"'),
        )
        self.assertIn('body[data-dlux-table-accent="on"] .dlux-table-shell', table_css)
        self.assertIn('border-inline: .25rem solid var(--primal', table_css)
        self.assertIn('border-block: 1px solid color-mix(', table_css)
        self.assertNotIn('dlux/base/css/accent_edges.css', base)
