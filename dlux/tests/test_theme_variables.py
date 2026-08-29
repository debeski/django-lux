"""Bootstrap variables Dlux has to rebind for themes to take effect.

Bootstrap hardcodes a few component colours as literals rather than reading the
palette variables. Under a single-theme site that is invisible; Dlux ships 13
themes, so each literal is a control that stays Bootstrap blue while everything
around it follows the palette.
"""
from pathlib import Path

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.test import SimpleTestCase

_STATIC = Path(__file__).resolve().parents[1] / 'static' / 'dlux'
_BOOTSTRAP = Path(__file__).resolve().parents[1] / 'static' / 'bootstrap'


class NavPillsFollowTheThemeTests(SimpleTestCase):
    def _base_css(self):
        return (_STATIC / 'base' / 'css' / 'main.css').read_text(encoding='utf-8')

    def test_the_active_pill_background_is_rebound_to_the_primary(self):
        self.assertIn('--bs-nav-pills-link-active-bg: var(--bs-primary);', self._base_css())

    def test_it_is_rebound_on_the_selector_bootstrap_declares_it_on(self):
        """Bootstrap declares it on `.nav-pills`. Rebinding it anywhere less
        specific — `:root`, say — loses to that declaration and changes nothing."""
        import re

        css = re.sub(r'/\*.*?\*/', '', self._base_css(), flags=re.S)
        selectors = [
            block.split('{')[0].strip()
            for block in css.split('}')
            if '--bs-nav-pills-link-active-bg' in block
        ]

        self.assertEqual(selectors, ['.nav-pills'])

    def test_bootstrap_still_hardcodes_it(self):
        """The whole reason this override exists. If a Bootstrap upgrade fixes
        it upstream, this fails and the override can be dropped."""
        bootstrap = (_BOOTSTRAP / 'bootstrap.rtl.min.css').read_text(encoding='utf-8')

        self.assertIn('--bs-nav-pills-link-active-bg:#0d6efd', bootstrap)

    def test_themes_actually_repoint_the_primary(self):
        """Without this the rebinding would be a no-op."""
        themes = list((_STATIC / 'themes' / 'css').glob('*.css'))
        repointed = [
            theme.name for theme in themes
            if '--bs-primary:' in theme.read_text(encoding='utf-8')
        ]

        self.assertTrue(repointed, 'no theme repoints --bs-primary')


class LinkButtonsStayGhostsTests(SimpleTestCase):
    """`.btn-link` must not pick up a theme's blanket button fill.

    Bootstrap applies `--bs-btn-hover-bg` to every button variant, so a theme
    setting it on `:root` gives the link button a solid background it was never
    meant to have — and under mono the fill and the text are both dark slate,
    leaving the label invisible on hover.
    """

    def _base_css(self):
        return (_STATIC / 'base' / 'css' / 'main.css').read_text(encoding='utf-8')

    def test_the_fill_is_neutralised(self):
        css = self._base_css()
        block = css[css.index('.btn-link {'):]
        block = block[:block.index('}')]

        for variable in ('--bs-btn-bg', '--bs-btn-hover-bg', '--bs-btn-active-bg'):
            with self.subTest(variable=variable):
                self.assertIn(f'{variable}: transparent;', block)

    def test_the_themes_really_do_set_a_blanket_fill(self):
        """The reason this override exists. If the themes stop setting it, this
        fails and the override can go."""
        setting = [
            theme.name for theme in (_STATIC / 'themes' / 'css').glob('*.css')
            if '--bs-btn-hover-bg' in theme.read_text(encoding='utf-8')
        ]

        self.assertGreater(len(setting), 1, 'no theme sets a blanket button fill')

    def test_mono_is_the_case_that_made_it_unreadable(self):
        """Its hover fill and its link hover colour are both dark slate."""
        mono = (_STATIC / 'themes' / 'css' / 'mono.css').read_text(encoding='utf-8')

        self.assertIn('--bs-btn-hover-bg: var(--mono-700);', mono)
        self.assertIn('--bs-link-hover-color: var(--mono-800);', mono)
