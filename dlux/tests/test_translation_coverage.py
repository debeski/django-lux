"""Every referenced translation key must resolve in every shipped language.

A key that exists in neither dict silently falls back to the hardcoded English
default at its call site, so an Arabic UI renders English with no error anywhere.
That is how ~40 strings went unnoticed; this guard fails the build instead.
"""
import ast
import re
from collections import defaultdict
from pathlib import Path

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.test import SimpleTestCase

_ROOT = Path(__file__).resolve().parents[1]

# `{# ... #}` is prose, not a reference — base.html documents DLUX_STRINGS keys
# in comments.
_DJANGO_COMMENT = re.compile(r'\{#.*?#\}', re.S)
_TEMPLATE_REF = re.compile(r"DLUX_STRINGS\.([a-z0-9_]+)")

# Keys the shipped catalogue deliberately leaves undefined: templates test for
# their presence and fall through when absent, so defining one would change
# behaviour rather than translate it. Projects supply them via
# `language_config.translations_override`.
_OPTIONAL_OVERRIDE_KEYS = {
    # footer.html: absent -> generated "© <year> <system name>" line.
    'footer_text',
}
_PYTHON_REF = re.compile(r"\b(?:s|strings|dlux_strings)\.get\(\s*'([a-z0-9_]+)'")


def _dict_literal(path, name):
    for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
        if isinstance(node, ast.Assign) and getattr(node.targets[0], 'id', '') == name:
            return node.value
    raise AssertionError(f'{name} not found in {path}')


def _catalogue():
    node = _dict_literal(_ROOT / 'translations.py', 'DLUX_STRINGS')
    return {
        lang.value: {k.value for k in body.keys if isinstance(k, ast.Constant)}
        for lang, body in zip(node.keys, node.values)
        if isinstance(lang, ast.Constant) and isinstance(body, ast.Dict)
    }


def _aliases():
    node = _dict_literal(_ROOT / 'translation_aliases.py', 'STRING_ALIASES')
    return {k.value: v.value for k, v in zip(node.keys, node.values)}


def _referenced_keys():
    refs = defaultdict(set)
    for path in (_ROOT / 'templates').rglob('*.html'):
        body = _DJANGO_COMMENT.sub('', path.read_text(encoding='utf-8'))
        for match in _TEMPLATE_REF.finditer(body):
            refs[match.group(1)].add(str(path.relative_to(_ROOT)))
    for path in _ROOT.rglob('*.py'):
        if path.name in {'translations.py', 'translation_aliases.py'} or '/tests/' in str(path):
            continue
        for match in _PYTHON_REF.finditer(path.read_text(encoding='utf-8')):
            refs[match.group(1)].add(str(path.relative_to(_ROOT)))
    return refs


class TranslationCoverageTests(SimpleTestCase):
    def test_every_referenced_key_resolves_in_every_language(self):
        catalogue = _catalogue()
        aliases = _aliases()
        refs = _referenced_keys()

        def resolves(key, keys):
            seen = set()
            while key and key not in seen:
                if key in keys:
                    return True
                seen.add(key)
                key = aliases.get(key)
            return False

        broken = []
        for key, sources in sorted(refs.items()):
            if key in _OPTIONAL_OVERRIDE_KEYS:
                continue
            for lang, keys in catalogue.items():
                if not resolves(key, keys):
                    broken.append(f"  {key!r} missing from '{lang}'  <- {sorted(sources)[0]}")

        self.assertEqual(
            broken, [],
            'Referenced translation keys that do not resolve — they render the '
            'hardcoded English default in every language:\n' + '\n'.join(broken),
        )

    def test_languages_define_the_same_keys(self):
        catalogue = _catalogue()
        langs = sorted(catalogue)
        base = langs[0]
        for other in langs[1:]:
            with self.subTest(lang=other):
                self.assertEqual(
                    sorted(catalogue[base] - catalogue[other]), [],
                    f"defined in '{base}' but not '{other}'",
                )
                self.assertEqual(
                    sorted(catalogue[other] - catalogue[base]), [],
                    f"defined in '{other}' but not '{base}'",
                )

    def test_aliases_point_at_keys_that_exist(self):
        catalogue = _catalogue()
        aliases = _aliases()

        dangling = sorted(
            f'{src} -> {dst}'
            for src, dst in aliases.items()
            if not any(dst in keys or dst in aliases for keys in catalogue.values())
        )

        self.assertEqual(dangling, [], f'aliases resolving to nothing: {dangling}')
