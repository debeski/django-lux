"""A dynamic modal must announce the content it injects.

`shown.bs.modal` fires once, when the dialog finishes opening — and the dialog is
shown *before* the fetch that fills it goes out. Anything that scanned on that
event therefore saw whatever was in the body at that instant: usually the loading
skeleton on a slow link or a large payload, and always the previous content when a
later injection replaced it (a refused form submit, in-modal navigation, or the
saved-state restore that runs on every page load).

That was the ribbon builder rendering nothing, rendering and then vanishing a
second later, and its "show system items" toggle doing nothing — that listener is
bound inside `init()`, so a builder that never initialised had no toggle either.
"""

from pathlib import Path

from django.test import TestCase

STATIC = Path(__file__).resolve().parents[1] / 'static' / 'dlux'
EVENT = 'dlux:modal-content-loaded'


def _read(*parts):
    return Path(*parts).read_text(encoding='utf-8')


class ModalAnnouncesItsContentTests(TestCase):
    def setUp(self):
        self.js = _read(STATIC, 'helpers', 'dynamic_modal', 'js', 'main.js')

    def test_announcement_bubbles_from_the_body_that_received_the_content(self):
        self.assertIn(
            f"modalBody.dispatchEvent(new CustomEvent('{EVENT}', {{ bubbles: true }}))",
            self.js,
        )

    def test_every_injection_site_announces(self):
        # One per `modalBody.innerHTML = data.html` — the initial fetch and the
        # re-render of a form that failed validation.
        self.assertEqual(self.js.count('modalBody.innerHTML = data.html;'), 2)
        self.assertEqual(self.js.count('notifyContentLoaded();'), 2)

    def test_announcement_follows_the_listeners_it_exists_for(self):
        for block in self.js.split('notifyContentLoaded();')[:-1]:
            self.assertTrue(
                block.rstrip().endswith('});') or 'attachListeners();' in block[-400:],
                'content must be wired up before it is announced',
            )


class ContentDependentInitialisersListenTests(TestCase):
    def test_ribbon_builder_reinitialises_on_new_content(self):
        js = _read(STATIC, 'ribbon', 'js', 'ribbon_builder.js')

        self.assertIn(f"document.addEventListener('{EVENT}'", js)
        self.assertIn('boot(event.target)', js)
        # Both events can fire for one injection, so init has to be idempotent.
        self.assertIn("if (root.dataset.ribbonBuilderReady === '1') return;", js)

    def test_ribbon_settings_reinitialises_on_new_content(self):
        js = _read(STATIC, 'ribbon', 'js', 'ribbon_settings.js')

        self.assertIn(f"document.addEventListener('{EVENT}'", js)

    def test_lookup_reinitialises_on_new_content(self):
        js = _read(STATIC, 'lookup', 'js', 'lookup.js')

        self.assertIn(f"document.addEventListener('{EVENT}'", js)
        self.assertIn('scan(event.target)', js)

    def test_no_content_scanner_is_left_on_shown_alone(self):
        """`shown.bs.modal` alone is the bug. Anything scanning injected content
        for markup must also listen for the content event."""
        offenders = []
        for path in sorted(STATIC.rglob('*.js')):
            source = path.read_text(encoding='utf-8')
            if "document.addEventListener('shown.bs.modal'" not in source:
                continue
            if f"'{EVENT}'" not in source:
                offenders.append(str(path.relative_to(STATIC)))
        self.assertEqual(offenders, [], f'scan injected content on {EVENT} too')
