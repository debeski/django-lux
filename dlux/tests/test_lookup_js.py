"""The lookup control's browser half, executed rather than read.

`test_lookup.py` covers the server's matching. This covers what the reader
actually touches, and it runs the real `lookup.js` under node against a small
DOM shim, because the bug it was written for could not be seen any other way:
every handler was attached by a scan over the document, so the near-match panel
— which only ever appears *after* a submit is refused, and inside a modal is
injected by an AJAX re-render with no `shown.bs.modal` behind it — was never
bound at all. The markup was right, the code was right, and clicking the
suggestion did nothing.

Skipped where node is missing; nothing here gates a deployment.
"""
import json
import shutil
import subprocess
from pathlib import Path

from django.test import SimpleTestCase

DLUX = Path(__file__).resolve().parents[1]
SCENARIOS = DLUX / 'tests' / 'fixtures' / 'lookup' / 'scenarios.mjs'
SCRIPT = DLUX / 'static' / 'dlux' / 'lookup' / 'js' / 'lookup.js'

NEAR_NAME = 'التشاركية العصرية'


def run_scenarios(script=SCRIPT):
    node = shutil.which('node')
    if not node:
        return None
    result = subprocess.run(
        [node, str(SCENARIOS), str(script)],
        capture_output=True, text=True, timeout=60, cwd=str(DLUX.parent),
    )
    if result.returncode != 0:
        raise AssertionError(f'lookup scenarios failed:\n{result.stderr}')
    return json.loads(result.stdout)


class LookupControlTests(SimpleTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.results = run_scenarios()

    def setUp(self):
        if self.results is None:
            self.skipTest('node is not installed')

    def test_picking_the_suggestion_selects_it(self):
        """The reported bug: the name changed, the key did not follow.

        The click sets the key *after* dispatching `input`, because the handler
        that runs on `input` recomputes the key from the rows the box holds and
        would wipe a suggestion those rows do not carry.
        """
        pick = self.results['pick']
        self.assertEqual(pick['input'], NEAR_NAME)
        self.assertEqual(pick['hidden'], '75')
        self.assertEqual(pick['typed'], NEAR_NAME)

    def test_picking_the_suggestion_withdraws_consent(self):
        """Taking the suggestion answers the question consent was asked about."""
        self.assertEqual(self.results['pick']['confirm'], '')

    def test_consent_reaches_the_hidden_field(self):
        self.assertEqual(self.results['consent']['confirm'], 'on')

    def test_search_only_panel_has_no_consent_to_clear(self):
        """A field that cannot create renders no consent box; picking still works."""
        search_only = self.results['searchOnly']
        self.assertEqual(search_only['input'], 'Acme Trading')
        self.assertEqual(search_only['hidden'], '40')

    def test_typeahead_binds_on_reaching_an_injected_field(self):
        """No scan ran over this field — focusing it is what bound it."""
        self.assertEqual(self.results['typeahead']['exact'], '40')

    def test_editing_away_from_a_match_clears_the_key(self):
        """An id left behind is the one way this saves a record nobody chose."""
        self.assertEqual(self.results['typeahead']['afterEdit'], '')

    def test_arabic_variants_resolve_to_the_same_key(self):
        """The client folds what the server folds, or the two disagree."""
        self.assertEqual(self.results['folding']['hidden'], '12')


class LookupSourceContractTests(SimpleTestCase):
    """The same regressions, checked where node is not installed.

    The container the suite normally runs in has no node, so everything above
    skips there. These read the source instead. Source-shape assertions are
    usually a poor trade, but each of these maps to a bug that has already
    happened once, and neither shows up in `node --check`.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.source = SCRIPT.read_text()

    def test_the_panel_handlers_are_delegated_on_the_document(self):
        """Bound per panel, they miss every panel a modal injects after load."""
        for event in ("'click'", "'change'", "'focusin'"):
            self.assertIn(
                f'document.addEventListener({event}', self.source,
                f'{event} must be delegated on the document, not attached by a scan',
            )

    def test_the_client_folds_what_the_server_folds(self):
        """Divergence here means the box clears a key the server would reuse."""
        from .. import lookup as matching

        for char in matching.ARABIC_EQUIVALENTS:
            self.assertIn(
                f'\\u{char:04x}', self.source.lower(),
                f'{chr(char)!r} is folded server-side but not in lookup.js',
            )
