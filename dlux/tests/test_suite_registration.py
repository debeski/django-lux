"""Every test module must actually be in the suite.

`test_all.py` runs an explicit list rather than discovering modules, which keeps
the run ordered and lets a module be excluded deliberately — but a new file is
then only run if someone remembers to add it. Three did not get added, so
`test_modal_content_init`, `test_titlebar_action_rail` and `test_inspector_shell`
never ran: 61 tests, cited by release notes, that CI was not executing. They all
passed once registered, which is luck rather than process.

A module that should genuinely stay out of the run belongs in EXCLUDED below,
with the reason — an explicit exemption instead of a silent omission.
"""

import ast
from pathlib import Path

from django.test import SimpleTestCase

TESTS_DIR = Path(__file__).resolve().parent

#: Modules deliberately outside the suite, each with the reason it is exempt.
EXCLUDED = {
    'test_all': 'the runner itself, not a test module',
}


def _registered_labels():
    """The labels in `test_all.TEST_LABELS`, read without importing the runner."""
    tree = ast.parse((TESTS_DIR / 'test_all.py').read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == 'TEST_LABELS':
                return {
                    element.value for element in node.value.elts
                    if isinstance(element, ast.Constant) and isinstance(element.value, str)
                }
    raise AssertionError('TEST_LABELS is no longer a literal list in test_all.py')


class EveryTestModuleIsRegisteredTests(SimpleTestCase):
    def test_no_test_module_is_left_out_of_the_suite(self):
        on_disk = {path.stem for path in TESTS_DIR.glob('test_*.py')} - set(EXCLUDED)
        registered = {label.rsplit('.', 1)[-1] for label in _registered_labels()}
        missing = sorted(on_disk - registered)
        self.assertEqual(
            missing, [],
            'these test modules exist but are not in test_all.TEST_LABELS, so they '
            'never run: ' + ', '.join(missing) + '. Add them, or add them to '
            'EXCLUDED here with the reason they are exempt.',
        )

    def test_the_suite_does_not_name_a_module_that_is_gone(self):
        on_disk = {path.stem for path in TESTS_DIR.glob('test_*.py')}
        registered = {label.rsplit('.', 1)[-1] for label in _registered_labels()}
        stale = sorted(registered - on_disk)
        self.assertEqual(stale, [], 'test_all.TEST_LABELS names modules that no longer exist: ' + ', '.join(stale))

    def test_every_exclusion_states_a_reason(self):
        for module, reason in EXCLUDED.items():
            with self.subTest(module=module):
                self.assertTrue(str(reason).strip(), f'{module} is excluded with no reason given')
