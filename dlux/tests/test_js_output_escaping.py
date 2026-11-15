"""Browser code that builds markup from data keeps that data text.

- The section manager's View and blocked-Delete modals are built from JSON the
  server sends: the record's name, field labels and values, and related rows.
  That is stored data, so a name such as ``<img src=x onerror=...>`` must arrive
  as text.
- The login page renders the administrator's hero message as light markdown for
  anonymous visitors; a link's URL must not break out of its ``href``.

The real scripts run under node against small shims. Skipped where node is
missing.
"""
import json
import shutil
import subprocess
from pathlib import Path

from django.test import SimpleTestCase

DLUX = Path(__file__).resolve().parents[1]
FIXTURES = DLUX / 'tests' / 'fixtures' / 'js_escaping'
STATIC = DLUX / 'static' / 'dlux'
SECTION_MANAGER = STATIC / 'helpers' / 'context_menu' / 'js' / 'section_manager.js'
LOGIN = STATIC / 'auth' / 'js' / 'login.js'
ESCAPED = '&lt;img src=x onerror=&quot;window.__fired=1&quot;&gt;'


def run_fixture(name, script):
    node = shutil.which('node')
    if not node:
        return None
    result = subprocess.run(
        [node, str(FIXTURES / name), str(script)],
        capture_output=True, text=True, timeout=60, cwd=str(DLUX.parent),
    )
    if result.returncode != 0:
        raise AssertionError(f'{name} failed:\n{result.stderr}')
    return json.loads(result.stdout)


class NodeFixtureTestCase(SimpleTestCase):
    fixture = None
    script = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.results = run_fixture(cls.fixture, cls.script) if cls.fixture else None

    def setUp(self):
        if self.results is None:
            self.skipTest('node is not installed')


class SectionManagerModalTests(NodeFixtureTestCase):
    fixture = 'section_manager.mjs'
    script = SECTION_MANAGER

    def test_view_modal_shows_the_record_as_text(self):
        html = self.results['view']
        self.assertNotIn(self.results['payload'], html)
        # Title, field label, field value, related model and related row.
        self.assertEqual(html.count(ESCAPED), 5)
        self.assertIn('>-</div>', html)

    def test_blocked_delete_modal_shows_related_rows_as_text(self):
        html = self.results['blockedDelete']
        self.assertNotIn(self.results['payload'], html)
        self.assertEqual(html.count(ESCAPED), 2)

    def test_the_payload_never_ran(self):
        self.assertFalse(self.results['fired'])


class LoginHeroMarkdownTests(NodeFixtureTestCase):
    fixture = 'login_markdown.mjs'
    script = LOGIN

    def test_a_link_url_cannot_leave_its_attribute(self):
        html = self.results['breakout']
        self.assertNotIn('<a ', html)
        self.assertNotIn('onmouseover="', html)

    def test_links_and_quotes_still_render(self):
        self.assertIn('<a href="https://example.org/a?b=1" target="_blank"', self.results['link'])
        self.assertIn('&quot;hi&quot;', self.results['quotes'])
        self.assertIn('<strong>fine</strong>', self.results['quotes'])
