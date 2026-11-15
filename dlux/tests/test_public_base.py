"""The thin public shell, ``dlux/public_base.html``, and its font stylesheet.

The shell is for citizen-facing pages under a strict content security policy. It
follows System Settings' public page settings, renders the same for every
visitor, and carries no configuration, URL map, preferences, strings or staff
scripts, and nothing inline.
"""

import re

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import include, path
from django.views.generic import TemplateView

from dlux.models import SystemSettings

urlpatterns = [
    path('storefront/', TemplateView.as_view(template_name='dlux/public_base.html')),
    path('', include('dlux.urls')),
]

RUNTIME_BLOCKS = (
    'dlux-config-data', 'dlux-url-data', 'user-prefs-data', 'dlux-strings-data',
    'dlux-theme-names', 'dlux-font-families', 'application/json', 'csrf-token',
)


def _configure(**public):
    record = SystemSettings.load()
    record.is_configured = True
    record.allowed_themes = ['light', 'dark', 'gold']
    record.default_theme = 'light'
    record.allowed_fonts = ['cairo', 'changa']
    record.default_fonts = {'en': 'cairo', 'ar': 'changa'}
    record.email_config = {**(record.email_config or {}), 'host': 'smtp.sentinel.example'}
    record.homepage_config = {
        **(record.homepage_config or {}),
        'public': {
            'enabled': True,
            'title': 'Citizen Services',
            'meta_description': 'Find a public service',
            'theme': 'dark',
            'show_titlebar': True,
            **public,
        },
    }
    record.save()


@override_settings(ROOT_URLCONF='dlux.tests.test_public_base')
class PublicBaseTests(TestCase):
    def setUp(self):
        _configure()

    def _page(self, language=None):
        if language:
            session = self.client.session
            session['lang'] = language
            session.save()
        response = self.client.get('/storefront/')
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_the_page_carries_no_runtime_data(self):
        html = self._page()
        for marker in RUNTIME_BLOCKS:
            self.assertNotIn(marker, html)
        self.assertNotIn('smtp.sentinel.example', html)

    def test_the_page_passes_a_policy_without_inline_code(self):
        html = self._page()
        self.assertNotIn('<script', html)
        self.assertNotIn('<style', html)
        self.assertIsNone(re.search(r'\sstyle\s*=', html))
        self.assertIsNone(re.search(r'\son[a-z]+\s*=', html, re.I))
        self.assertNotIn('javascript:', html)
        self.assertNotIn('nonce', html)

    def test_public_page_settings_shape_the_page(self):
        html = self._page()
        self.assertIn('<title>Citizen Services</title>', html)
        self.assertIn('<meta name="description" content="Find a public service">', html)
        self.assertIn('class="theme-dark"', html)
        self.assertRegex(html, r'href="[^"]*dlux/themes/css/dark\.css')
        self.assertIn('class="dlux-public-header"', html)
        self.assertIn('href="/fonts/cairo.css"', html)

    def test_a_hidden_public_titlebar_hides_the_header(self):
        _configure(show_titlebar=False)
        self.assertNotIn('dlux-public-header', self._page())

    def test_without_a_public_theme_the_system_default_applies(self):
        _configure(theme='')
        self.assertIn('class="theme-light"', self._page())

    def test_arabic_renders_right_to_left_with_its_default_font(self):
        html = self._page(language='ar')
        self.assertIn('lang="ar" dir="rtl"', html)
        self.assertIn('bootstrap.rtl.min.css', html)
        self.assertIn('انتقل إلى المحتوى', html)
        self.assertIn('href="/fonts/changa.css"', html)

    def test_a_signed_in_visitor_gets_the_same_page(self):
        anonymous = self._page()
        user = get_user_model().objects.create_superuser('shell-admin', 'shell@example.org', 'pw-for-tests-only')
        user.profile.preferences = {'theme': 'gold', 'font': 'changa'}
        user.profile.save()
        self.client.force_login(user)
        self.assertEqual(self._page(), anonymous)


@override_settings(ROOT_URLCONF='dlux.tests.test_public_base')
class FontStylesheetTests(TestCase):
    def setUp(self):
        _configure()

    def test_an_allowed_font_is_served_as_css(self):
        response = self.client.get('/fonts/changa.css')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/css; charset=utf-8')
        self.assertEqual(response['Cache-Control'], 'public, max-age=3600')
        self.assertNotIn('Set-Cookie', response.headers)
        css = response.content.decode()
        self.assertEqual(css.count('@font-face'), 3)
        self.assertIn("font-family:'Changa'", css)
        self.assertIn("--dlux-main-font:'Changa',sans-serif", css)

    def test_a_font_settings_do_not_allow_is_not_served(self):
        self.assertEqual(self.client.get('/fonts/readex_pro.css').status_code, 404)
        self.assertEqual(self.client.get('/fonts/unknown.css').status_code, 404)

    def test_only_reads_are_accepted(self):
        self.assertEqual(self.client.post('/fonts/cairo.css').status_code, 405)

    def test_unsafe_names_and_urls_never_reach_the_stylesheet(self):
        from dlux.fonts import font_stylesheet_css

        self.assertIsNone(font_stylesheet_css({'family': "X'}body{color:red", 'variants': []}))
        css = font_stylesheet_css({
            'family': 'Safe',
            'variants': [
                {'weight': 400, 'url': "/fonts/a.woff2') ; x:url('http://evil"},
                {'weight': 700, 'url': '/static/fonts/b.woff2'},
            ],
        })
        self.assertEqual(css.count('@font-face'), 1)
        self.assertIn("url('/static/fonts/b.woff2')", css)
