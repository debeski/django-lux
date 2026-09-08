"""A preserved settings field must be anchored to the step it renders in.

`_clean_preserved_toggle()` / `_clean_preserved_text()` restore the *stored*
value whenever the step being saved is not the anchored one — that is what keeps
a single-step save from reading an absent checkbox as False. It also means an
anchor pointing at the wrong step silently discards edits made on the page that
actually shows the field.

That is not hypothetical: `show_audit_fields` and `show_soft_deleted` were moved
into Access & Security and their anchors stayed on Components, so the audit
columns could be switched on and never off. Nothing caught it, because nothing
compared the two. This does.
"""

import re
from pathlib import Path

from django.test import SimpleTestCase

from dlux.system import constants as dlux_constants

FORMS_DIR = Path(__file__).resolve().parents[1] / 'forms'
GROUPS_DIR = FORMS_DIR / 'system_settings_groups'
LAYOUT = GROUPS_DIR / 'layout.py'

ANCHOR_RE = re.compile(
    r"_clean_preserved_(?:toggle|text)\(\s*'(?P<field>\w+)'\s*,\s*(?P<step>SETUP_STEP_\w+)"
)
STEP_END_RE = re.compile(r"_step_css_class\((?P<step>SETUP_STEP_\w+)\)")

#: Fields whose anchor deliberately differs from where they render, with why.
EXEMPT = {}


def _anchored_fields():
    """field name -> anchor constant, across every settings group module."""
    found = {}
    for path in sorted(GROUPS_DIR.glob('*.py')) + [FORMS_DIR / 'system_settings.py']:
        if not path.exists():
            continue
        for match in ANCHOR_RE.finditer(path.read_text(encoding='utf-8')):
            found[match.group('field')] = match.group('step')
    return found


def _render_steps():
    """field name -> the step constant of the block it is rendered inside.

    Each step's Div ends with `_step_css_class(SETUP_STEP_X)`, so the block a
    field belongs to is the one whose marker comes next after it.
    """
    source = LAYOUT.read_text(encoding='utf-8')
    ends = [(m.start(), m.group('step')) for m in STEP_END_RE.finditer(source)]
    steps = {}
    for field in _anchored_fields():
        pos = source.find(f"'{field}'")
        if pos == -1:
            continue
        following = next((step for start, step in ends if start > pos), None)
        if following:
            steps[field] = following
    return steps


class PreservedFieldsAreAnchoredToTheirOwnStepTests(SimpleTestCase):
    def test_every_preserved_field_is_anchored_where_it_renders(self):
        anchors = _anchored_fields()
        renders = _render_steps()
        mismatched = []
        for field, anchor in sorted(anchors.items()):
            if field in EXEMPT:
                continue
            rendered_in = renders.get(field)
            if rendered_in and rendered_in != anchor:
                mismatched.append(f'{field}: renders in {rendered_in}, anchored to {anchor}')
        self.assertEqual(
            mismatched, [],
            'these fields are anchored to a different step than the one they render '
            'in, so saving the page that shows them discards the change:\n  '
            + '\n  '.join(mismatched),
        )

    def test_the_anchor_constants_all_exist(self):
        for field, step in sorted(_anchored_fields().items()):
            with self.subTest(field=field):
                self.assertTrue(
                    hasattr(dlux_constants, step),
                    f'{field} is anchored to {step}, which is not a real step constant',
                )

    def test_the_guard_actually_finds_fields(self):
        # A regex that silently matches nothing would make this suite pass forever.
        self.assertGreater(len(_anchored_fields()), 10)
        self.assertGreater(len(_render_steps()), 5)

    def test_every_exemption_states_a_reason(self):
        for field, reason in EXEMPT.items():
            with self.subTest(field=field):
                self.assertTrue(str(reason).strip(), f'{field} is exempt with no reason given')
