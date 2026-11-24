"""What every page loads, and what loads only when it is needed.

dlux/base.html used to load the System Settings editors, the guided tour and
(through dlux/pdf/assets.html) PDF.js on every page. They are now on-demand
bundles (dlux/lazy_assets.py) loaded by dlux/base/js/lazy.js. These tests keep
them out of the page shell and keep every framework script deferred except
Bootstrap and the form-field scripts, which project scripts may use as they load. The browser side is covered by tests-e2e/lazy_assets.test.mjs.
"""
from dlux.tests.harness import setup_test_environment

setup_test_environment()

import json
import pathlib
import re

from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.core.cache import cache
from django.test import Client, SimpleTestCase, TestCase

from dlux.lazy_assets import ASSET_BUNDLES, asset_bundle_urls
from dlux.models import SystemSettings
from dlux.templatetags.dlux_tags import dlux_asset_bundles

PACKAGE = pathlib.Path(__file__).resolve().parents[1]
TEMPLATES = PACKAGE / 'templates'


def _template(name):
    return (TEMPLATES / name).read_text(encoding='utf-8')


def _script_tags(source):
    return re.findall(r'<script\b[^>]*\bsrc=[^>]*>', source)


class BundleDefinitionTests(SimpleTestCase):
    def test_every_bundle_file_is_shipped(self):
        for name, bundle in ASSET_BUNDLES.items():
            for path in (*bundle.get('css', ()), *bundle.get('js', ())):
                with self.subTest(bundle=name, path=path):
                    self.assertTrue(finders.find(path), f'{path} is listed in bundle {name} but not shipped.')

    def test_resolved_bundles_carry_versioned_urls_and_selectors(self):
        bundles = dlux_asset_bundles()
        self.assertEqual(set(bundles), set(ASSET_BUNDLES))
        for name, bundle in bundles.items():
            for url in (*bundle['css'], *bundle['js']):
                with self.subTest(bundle=name, url=url):
                    self.assertIn('?v=', url)
        self.assertIn('form.dlux-system-setup-form', bundles['settings']['selector'])
        self.assertNotIn('selector', bundles['tutorial'])
        json.dumps(bundles)

    def test_settings_scripts_keep_their_dependency_order(self):
        js = list(ASSET_BUNDLES['settings']['js'])
        self.assertLess(js.index('dlux/setup/js/dom.js'), js.index('dlux/setup/js/main.js'))
        self.assertLess(js.index('dlux/helpers/inspector/js/main.js'), js.index('dlux/ribbon/js/ribbon_builder.js'))
        self.assertEqual(js[-1], 'dlux/table_columns/js/main.js')
        self.assertEqual(ASSET_BUNDLES['tutorial']['js'][0], 'dlux/tutorial/js/driver.js')

    def test_asset_bundle_urls_uses_the_given_resolver(self):
        bundles = asset_bundle_urls(lambda path: f'/s/{path}')
        self.assertEqual(bundles['pdf']['js'], ['/s/dlux/pdf/vendor/pdf.min.js'])


class PageShellTests(SimpleTestCase):
    def test_base_loads_no_bundle_file_up_front(self):
        base = _template('dlux/base.html')
        for name, bundle in ASSET_BUNDLES.items():
            for path in bundle['js']:
                with self.subTest(bundle=name, path=path):
                    self.assertNotIn(path, base)
        for path in ASSET_BUNDLES['settings']['css']:
            with self.subTest(path=path):
                self.assertNotIn(path, base)
        self.assertNotIn("'dlux/tutorial/main.html'", base)

    def test_base_publishes_the_bundles_and_loads_the_loader(self):
        base = _template('dlux/base.html')
        self.assertIn('json_script:"dlux-asset-bundles"', base)
        self.assertIn("dlux/base/js/lazy.js", base)
        self.assertIn('<meta name="dlux-lazy-styles">', base)
        anchor = base.index('<meta name="dlux-lazy-styles">')
        self.assertLess(anchor, base.index('DLUX_ACTIVE_THEME.css_path'))

    def test_framework_scripts_are_deferred_except_bootstrap_and_form_assets(self):
        base = _template('dlux/base.html')
        tags = _script_tags(base)
        # The strings script blocks on purpose: base_head.js reads it.
        self.assertIn('DLUX_STRINGS_URL', tags[0])
        self.assertIn('base_head.js', tags[1])
        for tag in tags[:2]:
            with self.subTest(tag=tag):
                self.assertNotIn(' defer', tag)
        bootstrap = [tag for tag in tags if 'bootstrap.bundle.min.js' in tag]
        self.assertEqual(len(bootstrap), 1)
        self.assertNotIn(' defer', bootstrap[0])
        for tag in tags[2:]:
            if tag in bootstrap:
                continue
            with self.subTest(tag=tag):
                self.assertIn(' defer', tag)
        self.assertLess(
            base.index('vanillajs-datepicker/datepicker.min.js'),
            base.index('dlux/base/js/base_runtime.js'),
        )
        for name in ('dlux/helpers/dlux_context_menu.html', 'dlux/pdf/assets.html'):
            for tag in _script_tags(_template(name)):
                with self.subTest(template=name, tag=tag):
                    self.assertIn(' defer', tag)
                    self.assertIn('request.csp_nonce', tag)

    def test_project_scripts_can_use_bootstrap_and_form_assets_as_they_load(self):
        """Consumer `{% block scripts %}` files that call bootstrap.Modal on load
        (Trademarks' payment OTP modal) rely on this order, and an inline update
        never changes their templates."""
        base = _template('dlux/base.html')
        scripts_block = base.index('{% block scripts %}')
        self.assertLess(base.index('bootstrap/bootstrap.bundle.min.js'), scripts_block)
        self.assertLess(base.index("{% include_once 'dlux/forms/assets_scripts.html' %}"), scripts_block)
        self.assertLess(base.index("include_if_exists 'dlux/includes/custom_scripts.html'"), base.index('bootstrap/bootstrap.bundle.min.js'))
        for tag in _script_tags(_template('dlux/forms/assets_scripts.html')):
            with self.subTest(tag=tag):
                self.assertNotIn(' defer', tag)
                self.assertIn('request.csp_nonce', tag)

    def test_pdf_assets_load_pdfjs_on_demand(self):
        assets = _template('dlux/pdf/assets.html')
        self.assertNotIn('pdf.min.js', assets)
        self.assertLess(assets.index('dlux/pdf/js/pdfjs.js'), assets.index('dlux/pdf/js/viewer.js'))

    def test_options_and_setup_keep_the_settings_stylesheet_ahead_of_the_theme(self):
        for name in ('dlux/system/options.html', 'dlux/setup/main.html'):
            source = _template(name)
            block = source.split('{% block settings_styles %}', 1)[1].split('{% endblock %}', 1)[0]
            with self.subTest(template=name):
                self.assertIn('dlux/setup/css/main.css', block)
        self.assertIn('data-dlux-assets-warm="settings"', _template('dlux/system/options.html'))

    def test_shared_watch_replaces_document_wide_rescans(self):
        for path, selector in (
            ('dlux/weather/js/main.js', '[data-weather-widget]'),
            ('dlux/weather/js/settings.js', '[data-weather-settings]'),
            ('dlux/helpers/password_reveal/js/main.js', 'input[type="password"]'),
            ('dlux/tables/js/main.js', '.dlux-table-shell[data-dlux-table-resizable="true"]'),
        ):
            source = (PACKAGE / 'static' / path).read_text(encoding='utf-8')
            with self.subTest(path=path):
                self.assertIn(f"window.DluxDom.onAdded('{selector}'", source)


class RenderedPageTests(TestCase):
    def _bundles(self, html):
        match = re.search(r'<script id="dlux-asset-bundles" type="application/json">(.*?)</script>', html, re.S)
        self.assertIsNotNone(match, 'the page does not publish #dlux-asset-bundles')
        return json.loads(match.group(1))

    def test_the_sign_in_page_ships_no_settings_tour_or_pdf_script(self):
        html = Client().get('/accounts/login/').content.decode()
        bundles = self._bundles(html)
        for name, bundle in bundles.items():
            for url in bundle['js']:
                with self.subTest(bundle=name, url=url):
                    self.assertNotIn(f'src="{url}"', html)

    def test_options_ships_the_settings_stylesheet_but_not_its_scripts(self):
        settings_obj = SystemSettings.load()
        settings_obj.is_configured = True
        settings_obj.save()
        cache.clear()
        user = get_user_model().objects.create_superuser('lazy-admin', 'lazy@example.com', 'pw-for-tests-only')
        client = Client()
        client.force_login(user)
        response = client.get('/sys/options/')
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        bundles = self._bundles(html)
        self.assertIn(f'<link rel="stylesheet" href="{bundles["settings"]["css"][0]}">', html)
        for url in bundles['settings']['js']:
            with self.subTest(url=url):
                self.assertNotIn(f'src="{url}"', html)
