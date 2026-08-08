"""Unsaved-changes guard for modal forms.

Closing a guarded form with pending edits prompts before discarding, offering
save / discard / go back, plus a reversible "don't ask again" opt-out.
"""
import json
from pathlib import Path

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from dlux.forms import SystemSettingsForm
from dlux.models import Profile, SystemSettings

_STATIC = Path(__file__).resolve().parents[1] / 'static' / 'dlux' / 'main'
_TEMPLATES = Path(__file__).resolve().parents[1] / 'templates' / 'dlux'


class UnsavedGuardAssetTests(SimpleTestCase):
    @property
    def _js(self):
        return (_STATIC / 'js' / 'unsaved_guard.js').read_text(encoding='utf-8')

    def test_guard_intercepts_every_way_out_of_the_modal(self):
        js = self._js

        # Bootstrap routes the backdrop, the X button and Escape through the same
        # event, so one interception covers all three.
        self.assertIn("modalEl.addEventListener('hide.bs.modal', function (event) {", js)
        self.assertIn('event.preventDefault();', js)

    def test_clean_form_closes_without_a_prompt(self):
        js = self._js

        self.assertIn('const form = dirtyFormIn(modalEl);', js)
        self.assertIn('if (!form) {\n                return;\n            }', js)

    def test_opt_out_skips_the_prompt(self):
        js = self._js

        self.assertIn("const SKIP_PREFERENCE = 'skip_unsaved_settings_prompt';", js)
        self.assertIn('if (shouldSkipPrompt()) {', js)

    def test_dirtiness_is_a_snapshot_not_an_input_listener(self):
        # The settings form rewrites its own hidden JSON carriers during init and
        # live preview, dispatching synthetic events; a listener would report the
        # form dirty before the admin touched anything.
        js = self._js

        self.assertIn('function serializeForm(form)', js)
        self.assertIn("return serializeForm(form) !== form.dataset.dluxUnsavedBaseline;", js)
        self.assertNotIn("addEventListener('input', () => { dirty = true", js)

    def test_baseline_is_taken_after_initializers_settle(self):
        js = self._js

        self.assertIn('window.requestAnimationFrame(() => {\n            window.requestAnimationFrame(', js)

    def test_release_flag_prevents_an_interception_loop(self):
        # Discarding re-calls hide(); without the release flag the guard would
        # intercept its own close forever.
        js = self._js

        self.assertIn("modalEl.dataset.dluxUnsavedRelease = 'true';", js)
        self.assertIn("if (modalEl.dataset.dluxUnsavedRelease === 'true') {", js)

    def test_save_goes_through_the_forms_own_validation(self):
        js = self._js

        self.assertIn('form.requestSubmit(submitter);', js)
        self.assertNotIn('form.submit()', js)

    def test_missing_prompt_never_traps_the_admin(self):
        js = self._js

        self.assertIn('// No prompt available — never trap the admin inside the modal.', js)

    def test_baseline_is_dropped_when_the_modal_closes(self):
        js = self._js

        self.assertIn('delete form.dataset.dluxUnsavedBaseline;', js)


class UnsavedGuardMarkupTests(SimpleTestCase):
    def test_prompt_offers_save_discard_and_go_back(self):
        html = render_to_string('dlux/includes/unsaved_changes_modal.html', {'DLUX_STRINGS': {}})

        self.assertIn('data-dlux-unsaved-save', html)
        self.assertIn('data-dlux-unsaved-discard', html)
        self.assertIn('data-dlux-unsaved-stay', html)
        self.assertIn('Save changes', html)
        self.assertIn('Discard changes', html)
        self.assertIn('Go back', html)

    def test_prompt_offers_the_dont_ask_again_switch(self):
        html = render_to_string('dlux/includes/unsaved_changes_modal.html', {'DLUX_STRINGS': {}})

        self.assertIn('data-dlux-unsaved-skip', html)
        self.assertIn("Don't ask again", html)

    def test_prompt_x_button_goes_back_rather_than_dismissing(self):
        # A bare data-bs-dismiss would close the prompt without telling the guard
        # which outcome was chosen, leaving the settings modal in limbo.
        html = render_to_string('dlux/includes/unsaved_changes_modal.html', {'DLUX_STRINGS': {}})
        header = html[html.index('modal-header'):html.index('modal-body')]

        self.assertIn('data-dlux-unsaved-stay', header)
        self.assertNotIn('data-bs-dismiss', header)

    def test_base_template_ships_the_prompt_and_script(self):
        base = (_TEMPLATES / 'base.html').read_text(encoding='utf-8')

        self.assertIn("dlux/includes/unsaved_changes_modal.html", base)
        self.assertIn("dlux/main/js/unsaved_guard.js", base)


class UnsavedGuardFormOptInTests(TestCase):
    def test_system_settings_form_opts_in(self):
        form = SystemSettingsForm(instance=SystemSettings(is_configured=True))

        self.assertTrue(form.dlux_unsaved_guard)

    def test_modal_form_template_emits_the_marker(self):
        form = SystemSettingsForm(instance=SystemSettings(is_configured=True))
        html = render_to_string('dlux/helpers/dynamic_modal_form.html', {
            'form': form,
            'request': None,
            'hide_form_buttons': True,
        })

        self.assertIn('data-dlux-unsaved-guard', html)

    def test_a_form_without_the_flag_is_not_guarded(self):
        # Opt-in, not opt-out: an ordinary modal form must not get the guard just
        # by being rendered through the same partial.
        from django import forms as dj_forms

        class _Plain(dj_forms.Form):
            name = dj_forms.CharField(required=False)

        html = render_to_string('dlux/helpers/dynamic_modal_form.html', {
            'form': _Plain(),
            'request': None,
            'hide_form_buttons': True,
        })

        self.assertNotIn('data-dlux-unsaved-guard', html)


class UnsavedGuardPreferenceTests(TestCase):
    """The opt-out is a real, reversible preference — not a one-way door."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='admin', password='pw-12345678', is_staff=True, is_superuser=True,
        )
        Profile.all_objects.get_or_create(user=self.user)
        self.client = Client()
        self.client.force_login(self.user)
        self.url = reverse('update_preferences')

    def _post(self, payload):
        return self.client.post(self.url, data=json.dumps(payload), content_type='application/json')

    def _prefs(self):
        return Profile.all_objects.get(user=self.user).preferences or {}

    def test_opting_out_is_persisted(self):
        response = self._post({'skip_unsaved_settings_prompt': True})

        self.assertEqual(response.status_code, 200)
        self.assertIs(self._prefs().get('skip_unsaved_settings_prompt'), True)

    def test_opting_back_in_removes_the_key(self):
        self._post({'skip_unsaved_settings_prompt': True})
        self._post({'skip_unsaved_settings_prompt': False})

        self.assertNotIn('skip_unsaved_settings_prompt', self._prefs())

    def test_value_is_coerced_to_a_bool(self):
        self._post({'skip_unsaved_settings_prompt': 'true'})
        self.assertIs(self._prefs().get('skip_unsaved_settings_prompt'), True)

        self._post({'skip_unsaved_settings_prompt': 'off'})
        self.assertNotIn('skip_unsaved_settings_prompt', self._prefs())

    def test_junk_never_persists_as_truthy_garbage(self):
        self._post({'skip_unsaved_settings_prompt': {'nested': 'object'}})

        stored = self._prefs().get('skip_unsaved_settings_prompt')
        self.assertIn(stored, (True, None))
        if stored is not None:
            self.assertIs(stored, True)


class UnsavedGuardOptionsCardTests(SimpleTestCase):
    def test_options_page_can_turn_the_prompt_back_on(self):
        options = (_TEMPLATES / 'includes' / 'options.html').read_text(encoding='utf-8')
        js = (_STATIC / 'js' / 'options.js').read_text(encoding='utf-8')

        self.assertIn('data-unsaved-warning-toggle', options)
        self.assertIn('data-options-card="unsaved-warning"', options)
        self.assertIn('function initUnsavedWarningToggle()', js)
        self.assertIn('initUnsavedWarningToggle();', js)
        # The card reads as "warn me", so it is the inverse of the stored skip flag.
        self.assertIn('toggle.checked = !skipped;', js)
        self.assertIn('skip_unsaved_settings_prompt: !warn', js)

    def test_card_is_searchable(self):
        from dlux.search import OPTIONS_CARDS

        slugs = {card[0] for card in OPTIONS_CARDS}
        self.assertIn('unsaved-warning', slugs)


class UnsavedPromptStackingTests(SimpleTestCase):
    """The prompt opens over the settings modal; Bootstrap does not restack
    modals, so it needs an explicit z-index or it renders underneath and cannot
    be clicked."""

    def test_prompt_declares_the_stacked_class(self):
        html = render_to_string('dlux/includes/unsaved_changes_modal.html', {'DLUX_STRINGS': {}})

        self.assertIn('dlux-modal-stacked', html)

    def test_stacked_modal_is_raised_above_the_one_underneath(self):
        css = (_STATIC / 'css' / 'main.css').read_text(encoding='utf-8')

        self.assertIn('.dlux-modal-stacked', css)
        self.assertIn('z-index: 1075;', css)
        self.assertIn('body.dlux-modal-stacked-open .modal-backdrop:last-of-type', css)

    def test_body_class_is_added_and_removed_around_the_prompt(self):
        js = (_STATIC / 'js' / 'unsaved_guard.js').read_text(encoding='utf-8')

        self.assertIn("document.body.classList.add('dlux-modal-stacked-open');", js)
        self.assertIn("document.body.classList.remove('dlux-modal-stacked-open');", js)

    def test_closing_the_prompt_keeps_the_page_scroll_locked(self):
        # Bootstrap strips `modal-open` whenever any modal hides, including this
        # prompt closing over a settings modal that is staying open.
        js = (_STATIC / 'js' / 'unsaved_guard.js').read_text(encoding='utf-8')

        self.assertIn("if (document.querySelector('.modal.show')) {", js)
        self.assertIn("document.body.classList.add('modal-open');", js)
