"""Bootstrap variables Dlux has to rebind for themes to take effect.

Bootstrap hardcodes a few component colours as literals rather than reading the
palette variables. Under a single-theme site that is invisible; Dlux ships 13
themes, so each literal is a control that stays Bootstrap blue while everything
around it follows the palette.
"""
import re
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


class FilterClearChipFollowsDarkThemesTests(SimpleTestCase):
    """The filter bar's Clear chip was a light cream pill in every dark theme.

    `forms/css/form_actions.css` paints it with
    `.dlux-filter .btn.dlux-filter-clear.btn-warning` and is linked after the
    theme stylesheet, so a theme rule only wins by out-ranking that selector. At
    equal specificity the later, light rule wins: that is what dark and neon lost
    to, and the other dark themes had no rule at all.
    """

    LIGHT_SELECTOR = '.dlux-filter .btn.dlux-filter-clear.btn-warning'

    @staticmethod
    def _rules(path):
        css = re.sub(r'/\*.*?\*/', '', path.read_text(encoding='utf-8'), flags=re.S)
        for prelude, body in re.findall(r'([^{}]+)\{([^{}]*)\}', css):
            for selector in prelude.split(','):
                yield ' '.join(selector.split()), body

    @staticmethod
    def _specificity(selector):
        """(ids, classes + attributes + pseudo-classes, elements) for the plain
        compound selectors these rules use; functional pseudo-classes are refused
        rather than miscounted."""
        assert '(' not in selector, f'unsupported selector: {selector}'
        ids = len(re.findall(r'#[\w-]+', selector))
        classes = len(re.findall(r'\.[\w-]+|\[[^\]]*\]|(?<!:):[\w-]+', selector))
        elements = len(re.findall(r'(?:^|[\s>+~])[a-zA-Z][\w-]*', selector))
        return ids, classes, elements

    def _dark_themes(self):
        themes = {}
        for path in sorted((_STATIC / 'themes' / 'css').glob('*.css')):
            for selector, body in self._rules(path):
                if selector == f':root.theme-{path.stem}' and re.search(r'color-scheme:\s*dark', body):
                    themes[path.stem] = path
        return themes

    def test_the_light_rule_is_the_one_to_beat(self):
        rules = dict(self._rules(_STATIC / 'forms' / 'css' / 'form_actions.css'))
        self.assertIn(self.LIGHT_SELECTOR, rules)
        self.assertRegex(rules[self.LIGHT_SELECTOR], r'background:[^;]*!important')

    def test_theme_stylesheets_load_before_form_actions(self):
        """Why a tie is a loss: base.html links the active theme, then the form CSS."""
        templates = Path(__file__).resolve().parents[1] / 'templates' / 'dlux'
        base = (templates / 'base.html').read_text(encoding='utf-8')
        assets = (templates / 'forms' / 'assets_head.html').read_text(encoding='utf-8')

        self.assertIn('dlux/forms/css/form_actions.css', assets)
        self.assertLess(
            base.index('DLUX_ACTIVE_THEME.css_path'),
            base.index("include_once 'dlux/forms/assets_head.html'"),
        )

    def test_every_dark_theme_out_ranks_the_light_chip(self):
        themes = self._dark_themes()
        self.assertEqual(set(themes), {'dark', 'gothic', 'retro', 'neon', 'prism', 'aether'})
        light = self._specificity(self.LIGHT_SELECTOR)

        for slug, path in themes.items():
            with self.subTest(theme=slug):
                winning = [
                    body for selector, body in self._rules(path)
                    if selector.startswith(f':root.theme-{slug} ')
                    and '.dlux-filter-clear' in selector.split()[-1]
                    and ':hover' not in selector
                    and self._specificity(selector) > light
                ]
                self.assertTrue(winning, f'{path.name} has no Clear chip rule that out-ranks {self.LIGHT_SELECTOR}')
                body = winning[-1]
                self.assertRegex(body, r'background:[^;]*!important')
                self.assertRegex(body, r'(?<![\w-])color:[^;]*!important')

    def test_every_dark_theme_lets_the_icon_follow_the_chip(self):
        """`base/css/main.css` forces black icons in soft buttons
        (`:root .btn-warning .bi`), which vanish on a dark chip."""
        black = dict(self._rules(_STATIC / 'base' / 'css' / 'main.css'))
        self.assertRegex(black[':root .btn-warning .bi'], r'color:\s*#000\s*!important')
        forced = self._specificity(':root .btn-warning .bi')

        for slug, path in self._dark_themes().items():
            with self.subTest(theme=slug):
                icon_rules = [
                    body for selector, body in self._rules(path)
                    if selector.startswith(f':root.theme-{slug} ')
                    and (selector.endswith('.btn-warning .bi')
                         or ('.dlux-filter-clear' in selector and selector.endswith((' i', ' .bi'))))
                    and self._specificity(selector) > forced
                    and re.search(r'(?<![\w-])color:[^;]*!important', body)
                ]
                self.assertTrue(icon_rules, f'{path.name} leaves the Clear chip icon black')
                self.assertNotRegex(icon_rules[-1], r'color:\s*#000\b')
