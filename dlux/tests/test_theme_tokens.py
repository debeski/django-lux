"""Custom-property contract between the theme files and the rest of the CSS.

The theme de-duplication planned for 1.8.x moves ~264 selectors shared by the
seven full themes into one structural stylesheet written against tokens, leaving
each theme as a block of token values. That refactor has exactly one silent
failure mode: a token the structural sheet references that some theme forgets to
define. CSS does not error on it — `var(--gone)` with no fallback makes the whole
declaration invalid at computed-value time, so the property falls back to
inherited or initial and the page merely looks slightly wrong, in one theme, on
one component.

These tests make that failure loud. They are deliberately written against the
current file layout *and* the post-refactor one: the rule is about tokens, not
about which file declares them.
"""
import re
from pathlib import Path

from django.test import SimpleTestCase

STATIC = Path(__file__).resolve().parents[1] / 'static'
THEME_DIR = STATIC / 'dlux' / 'themes' / 'css'

# previews.css generates swatches, it is not a selectable theme. Files whose
# name starts with an underscore are shared partials (`_structure.css`), not
# themes either — they are the sheets the themes supply tokens *to*.
NOT_A_THEME = {'previews'}

DEFINITION = re.compile(r'(--[a-zA-Z0-9_-]+)\s*:')
# Group 2 is the comma that introduces a fallback: var(--x, something).
REFERENCE = re.compile(r'var\(\s*(--[a-zA-Z0-9_-]+)\s*(,)?')


def _strip_comments(css):
    return re.sub(r'/\*.*?\*/', '', css, flags=re.S)


def _theme_files():
    return sorted(
        p for p in THEME_DIR.glob('*.css')
        if p.stem not in NOT_A_THEME and not p.stem.startswith('_')
    )


def _dlux_css(include_themes=True):
    """Stylesheets dlux owns — the only ones whose references are policed.

    `include_themes=False` means "the shared layer": everything that is not a
    per-theme value sheet. `_structure.css` lives in the themes directory for
    filing reasons but IS shared — it is the sheet the themes supply tokens to,
    so its references must fall under the cross-theme contract. Excluding it
    just because of its folder would blind the one test written to guard it.
    """
    theme_files = {p for p in _theme_files()}
    for path in sorted((STATIC / 'dlux').rglob('*.css')):
        if not include_themes and path in theme_files:
            continue
        yield path


def _vendor_css():
    """Vendored third-party CSS: a source of definitions, never of obligations.

    Bootstrap references several of its own tokens that it deliberately leaves
    undefined (`--bs-nav-link-font-size`, `--bs-body-text-align`,
    `--bs-breadcrumb-font-size`), where unset means "inherit the default". Those
    are Bootstrap's business. But it also *defines* most of the `--bs-*` tokens
    dlux builds on, so it must still count when resolving our references.
    """
    dlux_root = STATIC / 'dlux'
    for path in sorted(STATIC.rglob('*.css')):
        if not path.is_relative_to(dlux_root):
            yield path


def _tokens_defined_by(path):
    return set(DEFINITION.findall(_strip_comments(path.read_text(encoding='utf-8'))))


# Tokens referenced with no fallback that nothing defines. Every one of these is
# a dead declaration today — verified in a real browser, where each resolves to
# the empty string while a working token such as `--title` resolves to a colour.
#
# They are recorded rather than fixed because making them live is a visual
# change, not a mechanical one: the declarations would begin applying colours
# that have never rendered. Fixing them means deciding what each should map to.
#
#   --text        7 uses  panel/css/main.css, system/css/options.css
#                         (three inside color-mix(), which invalidates the whole
#                          function, not just the one component)
#   --muted       )  navbar/css/main.css — `var(--muted, var(--text-muted))`
#   --text-muted  )  and `var(--glass-bg, var(--body-bg))`: in both, the
#   --glass-bg    )  fallback is itself undefined, so the chain is dead end to
#   --body-bg     )  end and the declaration never applies.
#
# The point of the allowlist is that it must never grow. A new entry means new
# dead CSS.
KNOWN_DEAD_TOKENS = {
    '--text',
    '--text-muted',
    '--muted',
    '--glass-bg',
    '--body-bg',
}

# Set from JavaScript at runtime via `style.setProperty`, never in a stylesheet,
# and every rule that reads one is guarded by the matching data-attribute
# (`.page[data-login-background-url]`, `.right[data-login-banner-color]`) so the
# declaration only exists once the value does. Undefined in CSS is correct here,
# not a defect — see the DSRP-1 note in auth/css/login.css.
RUNTIME_SET_TOKENS = {
    '--dlux-login-background-image',
    '--login-banner-color',
}


class ThemeTokenContractTests(SimpleTestCase):
    def test_no_new_dangling_token_references(self):
        """Every no-fallback var() resolves, or is a recorded known-dead token.

        Guards the refactor's silent failure mode: a structural stylesheet that
        references a token no theme supplies renders wrong instead of failing.
        """
        defined = set()
        for path in (*_dlux_css(), *_vendor_css()):
            defined |= _tokens_defined_by(path)

        dangling = {}
        for path in _dlux_css():
            css = _strip_comments(path.read_text(encoding='utf-8'))
            for name, fallback in REFERENCE.findall(css):
                if fallback or name in defined:
                    continue
                dangling.setdefault(name, set()).add(path.relative_to(STATIC).as_posix())

        allowed = KNOWN_DEAD_TOKENS | RUNTIME_SET_TOKENS
        new = {k: sorted(v) for k, v in dangling.items() if k not in allowed}
        self.assertEqual(
            new, {},
            'CSS references these custom properties with no fallback and nothing '
            'defines them, so the declarations are silently dropped:\n'
            + '\n'.join(f'  {k}  <- {", ".join(v)}' for k, v in sorted(new.items())),
        )

    def test_known_dead_tokens_are_still_dead(self):
        """The allowlist must shrink, never linger once a token is fixed.

        Without this, defining `--text` would leave a stale entry that keeps
        hiding a genuine future regression on the same name.
        """
        defined = set()
        for path in (*_dlux_css(), *_vendor_css()):
            defined |= _tokens_defined_by(path)

        resurrected = sorted(KNOWN_DEAD_TOKENS & defined)
        self.assertEqual(
            resurrected, [],
            'These are now defined somewhere, so remove them from '
            f'KNOWN_DEAD_TOKENS: {resurrected}',
        )

    def test_theme_supplied_tokens_are_supplied_by_every_theme(self):
        """A token the shared CSS needs, and no base file defines, must come
        from *every* theme.

        This is the invariant the extraction depends on. Scope matters: only
        references made from NON-theme stylesheets count. A theme is free to
        define private palette tokens for its own use — `--neon-cyan`,
        `--mono-500`, `--gothic-black` and friends are deliberately local, and
        requiring every theme to define another theme's palette would be
        nonsense.

        Today the shared sheets reference few theme-supplied tokens, so this
        passes easily. Once the ~264 shared selectors move into a structural
        stylesheet, that sheet is a non-theme file, so everything it references
        lands in this contract and the test starts doing real work — without
        being rewritten. It is written against the rule, not the file layout.
        """
        base = set()
        for path in (*_dlux_css(include_themes=False), *_vendor_css()):
            base |= _tokens_defined_by(path)

        per_theme = {p.stem: _tokens_defined_by(p) for p in _theme_files()}
        self.assertTrue(per_theme, 'no theme files found')

        # Scope matters a second time, now on the reference side. A rule in the
        # shared layer may target a subset of themes — `_structure.css` scopes
        # every rule to the seven full themes with
        # `:root:is(.theme-mono, ... , .theme-aether)`, and the five palette
        # themes never match it. Demanding that they define tokens they can
        # never use would be a false failure, so each token is only required
        # from the themes whose rules actually reference it.
        all_themes = set(per_theme)
        required_from = {}
        for path in _dlux_css(include_themes=False):
            css = _strip_comments(path.read_text(encoding='utf-8'))
            for sel, body in re.findall(r'([^{}]+)\{([^{}]*)\}', css):
                scoped = set(re.findall(r'\.theme-([a-z0-9_-]+)', sel)) & all_themes
                audience = scoped or all_themes
                for name, fallback in REFERENCE.findall(body):
                    if fallback:
                        continue
                    required_from.setdefault(name, set()).update(audience)

        for name in list(required_from):
            if name in base or name in KNOWN_DEAD_TOKENS or name in RUNTIME_SET_TOKENS:
                del required_from[name]

        gaps = {}
        for theme, tokens in per_theme.items():
            missing = sorted(
                name for name, audience in required_from.items()
                if theme in audience and name not in tokens
            )
            if missing:
                gaps[theme] = missing
        self.assertEqual(
            gaps, {},
            'Some themes do not define tokens that only themes can supply. Any '
            'page using one renders with an inherited or initial value instead:\n'
            + '\n'.join(f'  {t}: {", ".join(v)}' for t, v in sorted(gaps.items())),
        )

    def test_every_selectable_theme_declares_a_root_token_block(self):
        """Each theme owns exactly one `:root.theme-<name>` token block.

        The extraction rewrites these blocks wholesale, so it matters that the
        shape is uniform and that the block is addressable by theme name.
        """
        for path in _theme_files():
            css = _strip_comments(path.read_text(encoding='utf-8'))
            blocks = [
                sel for sel, _ in re.findall(r'([^{}]+)\{([^{}]*)\}', css)
                if re.fullmatch(rf':root\.theme-{re.escape(path.stem)}', ' '.join(sel.split()))
            ]
            self.assertEqual(
                len(blocks), 1,
                f'{path.name} should declare exactly one ":root.theme-{path.stem}" '
                f'token block, found {len(blocks)}',
            )
