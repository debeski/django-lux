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
        # The initial fetch and the re-render of a form that failed validation both
        # go through renderContent(), which injects, wires up and announces once.
        self.assertEqual(self.js.count('renderContent(data.html, '), 2)
        self.assertEqual(self.js.count('modalBody.innerHTML = html;'), 1)
        self.assertEqual(self.js.count('notifyContentLoaded();'), 1)

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


class ModalOpenListenerReachesEveryCallerTests(TestCase):
    """`dlux:dynamic_modal:open` must reach the modal however it was dispatched.

    The listener moved from `document.body` to `document` in 1.8.0 on the reasoning
    that it was strictly more permissive. It was not. A `new CustomEvent(name, {detail})`
    does not bubble — `bubbles` defaults to false — so a host project dispatching on
    `document.body`, which is the natural thing to write, was caught by the old
    body-bound listener at target and reached nothing at all once it moved up to
    `document`. The symptom is silent: no console error, no request, no modal, while
    every action dlux dispatches itself (those pass `bubbles: true`) keeps working.

    Capture phase runs window -> document -> target on every dispatch regardless of
    `bubbles`, so it catches all three shapes exactly once.
    """

    def setUp(self):
        self.js = _read(STATIC, 'helpers', 'dynamic_modal', 'js', 'main.js')

    def _closer_after_registration(self):
        """The line that closes the modal-open listener: '});' or '}, true);'.

        Matched on the closer rather than the whole block, which contains blank
        lines and would need brace balancing to delimit. A named handler
        registered on one line (`addEventListener(..., openFromRequest, true);`)
        reads as the capture closer.
        """
        marker = "document.addEventListener('dlux:dynamic_modal:open'"
        start = self.js.find(marker)
        self.assertNotEqual(start, -1, 'the modal-open listener is no longer registered on document')
        line = self.js[start:self.js.find('\n', start)].rstrip()
        if line.endswith(');'):
            return '}, true);' if line.endswith(', true);') else '});'

        bubble = self.js.find('\n    });', start)
        capture = self.js.find('\n    }, true);', start)
        if capture == -1:
            return '});'
        if bubble == -1 or capture < bubble:
            return '}, true);'
        return '});'

    def test_the_open_listener_is_registered_in_the_capture_phase(self):
        self.assertEqual(
            self._closer_after_registration(), '}, true);',
            'the modal-open listener must be bound in the capture phase, or a caller '
            'that dispatches a non-bubbling event on document.body is silently ignored',
        )

    def test_dlux_dispatches_this_event_with_bubbles(self):
        # dlux's own context-menu actions must keep working through either phase.
        menu = _read(STATIC, 'helpers', 'context_menu', 'js', 'main.js')
        self.assertIn('bubbles: true', menu)


class SkipSetupSendsItsTokenTests(TestCase):
    """"Skip for now" on the first-login Initial User Setup modal did nothing.

    `syncModalFooter()` moves the `.dlux-modal-form-actions` bar, Skip included,
    out of its `<form>` into the modal footer and re-associates it with `form=`.
    The skip handler read the CSRF token through `closest('form')`, which is null
    there, so it posted `skip=1` with no token; CSRF refused it, the handler
    quietly re-enabled the button, and the unrecorded skip brought the modal back
    on every page. Checked in a browser against the real script and fragment.
    """

    def setUp(self):
        self.js = _read(STATIC, 'helpers', 'dynamic_modal', 'js', 'main.js')
        start = self.js.index('function recordOnboardingSkip(skipBtn) {')
        self.record = self.js[start:self.js.index('\n    }\n', start)]
        start = self.js.index("const skipBtn = e.target.closest('[data-dlux-skip-setup]');")
        self.handler = self.js[start:self.js.index('\n    });', start)]
        start = self.js.index("modalEl.addEventListener('hide.bs.modal', function () {\n        const skipBtn")
        self.close = self.js[start:self.js.index('\n    });', start)]

    def test_the_skip_button_is_one_the_footer_relocates(self):
        """Why `closest('form')` cannot work: the bar holding Skip leaves the form."""
        template = _read(STATIC.parents[1], 'templates', 'dlux', 'users', 'initial_setup.html')
        bar = template[template.index('dlux-modal-form-actions'):]
        self.assertIn('data-dlux-skip-setup', bar[:bar.index('</div>')])
        self.assertIn("'.dlux-form-actions, .dlux-setup-wizard-actions, .dlux-modal-form-actions'", self.js)
        self.assertIn("control.setAttribute('form', form.id)", self.js)

    def test_the_token_is_read_through_the_buttons_form_owner(self):
        self.assertIn('const form = skipBtn.form || skipBtn.closest(\'form\');', self.record)

    def test_the_page_token_is_the_fallback(self):
        self.assertIn('document.querySelector(\'meta[name="csrf-token"]\')', self.record)
        base = _read(STATIC.parents[1], 'templates', 'dlux', 'base.html')
        self.assertIn('<meta name="csrf-token" content="{{ csrf_token }}">', base)

    def test_the_token_travels_in_the_body_and_the_header(self):
        self.assertIn("body.append('csrfmiddlewaretoken', csrf);", self.record)
        self.assertIn("'X-CSRFToken': csrf", self.record)

    def test_a_refused_skip_still_releases_the_page(self):
        self.assertIn('recordOnboardingSkip(skipBtn)', self.handler)
        refused = self.handler[self.handler.index('.catch('):]
        self.assertIn('dynamicModal.hide();', refused)
        self.assertNotIn('location.reload', refused)

    def test_closing_onboarding_without_saving_records_the_skip(self):
        """X, Escape and the backdrop all hide the modal: each counts as "Skip for now"."""
        self.assertIn("modalEl.querySelector('[data-dlux-skip-setup]')", self.close)
        self.assertIn('if (!skipBtn || onboardingSkipSent) return;', self.close)
        self.assertIn('recordOnboardingSkip(skipBtn)', self.close)
        self.assertNotIn('location.reload', self.close)

    def test_the_skip_is_sent_once(self):
        """The Skip button's own failure path hides the modal; that hide must not post again."""
        self.assertIn('onboardingSkipSent = true;', self.record)
        self.assertIn('keepalive: true', self.record)

    def test_a_save_reloads_instead_of_hiding(self):
        """So the close handler never turns a save into a skip."""
        success = self.js[self.js.index('if (data.refresh_parent && (data.close_modal'):]
        self.assertIn('window.location.reload();', success[:success.index('return;')])
