"""Scripts that build markup from superuser-editable data keep that data text.

Translation overrides, sidebar and navbar builder entries, language names and
scope names are all stored values. The setup builder, the language catalog, the
permissions tier preview and the scripts that put translated labels beside an
icon or spinner must escape them or insert them as text.

This is a static guard over those scripts: every ``${...}`` in a template literal
that holds markup goes through ``escapeHtml()`` unless it is listed as safe below,
and no ``innerHTML`` assignment concatenates a value onto markup. The browser
behaviour is covered by ``tests-e2e/html_sinks.test.mjs``.
"""
import re
from pathlib import Path

from django.test import SimpleTestCase

STATIC = Path(__file__).resolve().parents[1] / 'static' / 'dlux'

# Interpolations that are not data: fixed strings, counts, or markup the script
# has already escaped.
SAFE_INTERPOLATIONS = {
    'setup/js/main.js': {
        "node.kind === 'route' ? 'bi-link-45deg' : 'bi-folder2-open'",
        'idBound',
        'group.items.length',
        '(entry.items || []).length',
        "state.selectedId === node.id ? ' is-active' : ''",
    },
    'setup/js/language.js': {
        "dir !== 'rtl' ? ' selected' : ''",
        "dir === 'rtl' ? ' selected' : ''",
        "locked ? ' disabled' : ''",
    },
    'users/js/permissions.js': set(),
    'activitylog/js/main.js': set(),
    'helpers/icon_picker/js/main.js': set(),
    'pdf/js/editor.js': set(),
    'auth/js/twofa_verify.js': set(),
    'system/js/confirm_password.js': set(),
    'system/js/data_reset.js': set(),
}

TEMPLATE = re.compile(r'`([^`]*)`', re.S)
INTERPOLATION = re.compile(r'\$\{((?:[^{}]|\{[^{}]*\})*)\}')
INNER_HTML_CONCAT = re.compile(r"\.innerHTML\s*\+?=\s*[^;]*?['\"]\s*\+\s*(?!['\"])", re.S)


def html_interpolations(source):
    for match in TEMPLATE.finditer(source):
        body = match.group(1)
        if not re.search(r'<[a-zA-Z/]', body):
            continue
        line = source[:match.start()].count('\n') + 1
        for expression in INTERPOLATION.findall(body):
            yield line, expression.strip()


class SuperuserDataSinkTests(SimpleTestCase):
    def test_markup_templates_escape_every_value(self):
        unescaped = []
        for rel_path, safe in SAFE_INTERPOLATIONS.items():
            source = (STATIC / rel_path).read_text(encoding='utf-8')
            for line, expression in html_interpolations(source):
                if expression.startswith('escapeHtml(') or expression in safe:
                    continue
                unescaped.append(f'{rel_path}:{line}: ${{{expression}}}')
        self.assertEqual(unescaped, [])

    def test_inner_html_never_concatenates_a_value(self):
        concatenated = []
        for rel_path in SAFE_INTERPOLATIONS:
            source = (STATIC / rel_path).read_text(encoding='utf-8')
            for match in INNER_HTML_CONCAT.finditer(source):
                line = source[:match.start()].count('\n') + 1
                concatenated.append(f'{rel_path}:{line}')
        self.assertEqual(concatenated, [])

    def test_the_guard_flags_the_old_patterns(self):
        old_permissions = '`<li>${item}</li>`'
        old_verify = "errorEl.innerHTML = '<i class=\"bi\"></i>' + message;"
        self.assertEqual([e for _, e in html_interpolations(old_permissions)], ['item'])
        self.assertIsNotNone(INNER_HTML_CONCAT.search(old_verify))
        self.assertIsNone(INNER_HTML_CONCAT.search("el.innerHTML = '<i class=\"bi\"></i>';"))
