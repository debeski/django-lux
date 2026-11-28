"""DjangoLux pages work under ``style-src 'self'`` (ZAP 10055).

A policy without ``'unsafe-inline'`` blocks ``<style>`` blocks, ``style=""``
attributes and markup with ``style=`` handed to ``innerHTML``. It allows the
CSSOM (``el.style.x = …``, ``setProperty``) and same-origin stylesheets. These
guards keep every shipped template and script inside that line; the browser
proof is ``tests-e2e/csp_style_self.test.mjs``.
"""

import re
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from dlux.page_styles import page_stylesheet_css, page_stylesheet_version

DLUX = Path(__file__).resolve().parents[1]
STYLE_ATTRIBUTE = re.compile(r'(?<![\w-])style\s*=\s*["\'\\$]', re.IGNORECASE)
STYLE_ELEMENT = re.compile(r'<style\b|createElement\(\s*["\']style["\']\s*\)', re.IGNORECASE)
STYLE_SET_ATTRIBUTE = re.compile(r'setAttribute\(\s*["\']style["\']|\.cssText\s*=', re.IGNORECASE)


def _shipped_scripts():
    static = DLUX / 'static'
    for path in sorted(static.rglob('*.js')):
        rel = path.relative_to(static).as_posix()
        # pdf.js is vendored and checked by the PDF viewer's own test.
        if not path.is_file() or rel.startswith('dlux/pdf/') or path.name.endswith('.min.js'):
            continue
        yield rel, path.read_text(encoding='utf-8', errors='replace')


class StyleSourceGuardTests(TestCase):
    def test_templates_have_no_style_blocks_or_attributes(self):
        found = []
        for path in sorted((DLUX / 'templates').rglob('*.html')):
            rel = path.relative_to(DLUX / 'templates').as_posix()
            text = path.read_text(encoding='utf-8')
            for number, line in enumerate(text.splitlines(), 1):
                if STYLE_ELEMENT.search(line) or STYLE_ATTRIBUTE.search(line):
                    found.append(f'{rel}:{number}')
        self.assertEqual(found, [])

    def test_scripts_style_through_the_cssom_only(self):
        found = []
        for rel, text in _shipped_scripts():
            for number, line in enumerate(text.splitlines(), 1):
                if STYLE_ELEMENT.search(line) or STYLE_SET_ATTRIBUTE.search(line) or STYLE_ATTRIBUTE.search(line):
                    found.append(f'{rel}:{number}')
        self.assertEqual(found, [])

    def test_vendored_scripts_inject_no_inline_style(self):
        static = DLUX / 'static'
        for rel in ('bootstrap/bootstrap.bundle.min.js', 'chart.js/chart.umd.min.js',
                    'vanillajs-datepicker/datepicker.min.js', 'dlux/tutorial/js/driver.js'):
            text = (static / rel).read_text(encoding='utf-8')
            self.assertIsNone(STYLE_ELEMENT.search(text), rel)
            self.assertIsNone(STYLE_SET_ATTRIBUTE.search(text), rel)
            self.assertIsNone(re.search(r'style="', text), rel)

    def test_python_attrs_carry_no_style(self):
        found = []
        for path in sorted(DLUX.rglob('*.py')):
            rel = path.relative_to(DLUX).as_posix()
            if rel.startswith(('tests/', 'scaffold/', 'migrations/')):
                continue
            text = path.read_text(encoding='utf-8')
            if re.search(r'["\']style["\']\s*:\s*["\'][^"\']*[:;]', text) or re.search(r'(?<![\w_])style=\\?["\'][^"\']*:', text):
                found.append(rel)
        self.assertEqual(found, [])


class PageStylesheetTests(TestCase):
    def test_registry_rules_are_served_as_a_cacheable_stylesheet(self):
        css = page_stylesheet_css()
        self.assertIn('@font-face', css)
        self.assertIn('--dlux-font-fallback', css)
        url = reverse('dlux_page_styles', kwargs={'version': page_stylesheet_version(css)})
        response = Client().get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/css; charset=utf-8')
        self.assertIn('immutable', response['Cache-Control'])
        self.assertEqual(response.content.decode(), css)
        self.assertNotIn('Cookie', response.get('Vary', ''))

    def test_a_stale_version_is_served_uncached(self):
        response = Client().get(reverse('dlux_page_styles', kwargs={'version': '0' * 16}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'no-cache')

    def test_pages_link_it_instead_of_inline_rules(self):
        User = get_user_model()
        user = User.objects.create_superuser('style-admin', 'style@example.test', 'pw-12345-long')
        client = Client()
        client.force_login(user)
        for url in (reverse('login'), '/sys/options/'):
            client_for = Client() if url == reverse('login') else client
            html = client_for.get(url, follow=True).content.decode()
            self.assertNotIn('<style', html, url)
            self.assertIn('id="dlux-page-styles"', html, url)
            self.assertIn(f'/sys/api/styles/{page_stylesheet_version()}.css', html, url)
