"""Assisted entry: FK autofill and sticky-forms as two independent features.

They previously shared one `enable_prefill` flag in localStorage, and both were
dead — init bailed when a titlebar injection whose selector no longer matched
failed to produce a toggle.
"""
import json
from pathlib import Path

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from dlux.models import Profile, SystemSettings

_STATIC = Path(__file__).resolve().parents[1] / 'static' / 'dlux'
_TEMPLATES = Path(__file__).resolve().parents[1] / 'templates' / 'dlux'


class AssistedEntryHelperTests(SimpleTestCase):
    @property
    def _js(self):
        # Two sibling modules, one behaviour contract: related lives in
        # helpers/autofill, sticky in helpers/sticky.
        return (
            (_STATIC / 'helpers' / 'autofill' / 'js' / 'main.js').read_text(encoding='utf-8')
            + (_STATIC / 'helpers' / 'sticky' / 'js' / 'main.js').read_text(encoding='utf-8')
        )

    def test_the_two_features_read_separate_preferences(self):
        js = self._js

        self.assertIn("const PREF_RELATED = 'autofill_from_related';", js)
        self.assertIn("const PREF_STICKY = 'sticky_forms';", js)
        self.assertNotIn("'enable_prefill'", js)

    def test_defaults_are_stated_per_feature(self):
        # Related reacts to a deliberate FK choice, so it is on; sticky changes a
        # form nobody touched, so it is off.
        js = self._js

        self.assertIn('return pref(PREF_RELATED, true);', js)
        self.assertIn('return pref(PREF_STICKY, false);', js)

    def test_neither_feature_gates_the_other(self):
        js = self._js

        self.assertIn('if (!sourceEl || !relatedEnabled()) {', js)
        self.assertIn('if (stickyEnabled() && form.dataset.stickyServer === undefined) {', js)

    def test_titlebar_injection_is_gone(self):
        # The old injectToggle() targeted a selector the v1.5.10 titlebar
        # restructure stopped matching, and init returned when it failed —
        # which is what killed both features.
        js = self._js

        code = js[js.index('(function () {'):]

        self.assertNotIn('injectToggle', code)
        self.assertNotIn('.pe-2.d-flex.align-items-center', code)
        self.assertNotIn("getElementById('autofillToggle')", code)

    def test_no_hardcoded_arabic_in_the_control(self):
        js = self._js

        self.assertNotIn('تعبئة تلقائية', js)
        self.assertNotIn('التعبئة التلقائية', js)
        # Copy comes from DLUX_STRINGS with an English fallback.
        self.assertIn("t('assist_sticky_label', 'Reuse my last entry')", js)
        self.assertIn("t('assist_sticky_desc',", js)

    def test_inline_control_is_the_sticky_switch_only(self):
        # "Fill from related record" reacts to a deliberate FK choice and needs no
        # per-form control; it lives in Options only.
        js = self._js

        self.assertIn("if (form.querySelector('[data-dlux-assist-bar]') || !formCapabilities(form).sticky) {", js)
        self.assertNotIn('t(\'assist_related_label\', \'Fill from related record\'),\n                relatedEnabled()', js)
        sticky_js = (_STATIC / 'helpers' / 'sticky' / 'js' / 'main.js').read_text(encoding='utf-8')
        block = sticky_js[sticky_js.index('function renderControl(form)'):]
        block = block[:block.index('\n    function ', 10)]
        self.assertIn('PREF_STICKY', block)
        self.assertNotIn('PREF_RELATED', block)

    def test_capabilities_are_detected_from_the_form(self):
        js = self._js

        self.assertIn('function formCapabilities(form)', js)
        self.assertIn("related: Boolean(form.querySelector('[data-autofill-source]'))", js)
        self.assertIn('sticky: Boolean(form.dataset.modelName && form.dataset.appLabel)', js)
        self.assertIn('form.insertBefore(bar, form.firstChild);', js)

    def test_turning_sticky_off_forgets_what_it_remembered(self):
        # The remembered pk is what kept refilling forms after the switch was off.
        js = self._js

        self.assertIn('function forgetSticky(form)', js)
        self.assertIn('localStorage.removeItem(`${STORAGE_PREFIX}${appLabel}_${modelName}`);', js)
        self.assertIn('forgetSticky(form);', js)

    def test_preferences_are_persisted_not_kept_in_localstorage(self):
        js = self._js

        self.assertIn('window.updatePreferences({ [key]: value })', js)
        self.assertNotIn("localStorage.setItem(TOGGLE_KEY", js)

    def test_modal_forms_are_picked_up_after_injection(self):
        js = self._js

        self.assertIn('new MutationObserver', js)
        self.assertIn('scan(node);', js)


class AssistedEntryOptionsCardTests(SimpleTestCase):
    def test_card_offers_both_switches_with_descriptions(self):
        html = (_TEMPLATES / 'system' / 'options.html').read_text(encoding='utf-8')

        self.assertIn('data-assist-pref="autofill_from_related"', html)
        self.assertIn('data-assist-pref="sticky_forms"', html)
        self.assertIn('assist_related_desc', html)
        self.assertIn('assist_sticky_desc', html)
        self.assertNotIn('id="autofillToggle"', html)

    def test_options_js_binds_both_and_drops_the_cookie_store(self):
        js = (_STATIC / 'system' / 'js' / 'options.js').read_text(encoding='utf-8')

        self.assertIn('function initAssistedEntry()', js)
        self.assertIn('initAssistedEntry();', js)
        self.assertNotIn('function initAutofill', js)
        # The cookie mirror is gone; the preference is the single source.
        self.assertNotIn('function setCookie', js)
        self.assertNotIn('function getCookie', js)

    def test_reset_defaults_sheds_the_retired_keys(self):
        js = (_STATIC / 'system' / 'js' / 'options.js').read_text(encoding='utf-8')

        self.assertIn("key === 'enable_prefill'", js)
        self.assertIn("key.startsWith('dlux_autofill_')", js)


class AssistedEntryPreferenceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username='u', password='pw-12345678', is_staff=True, is_superuser=True,
        )
        Profile.all_objects.get_or_create(user=self.user)
        settings_row = SystemSettings.load()
        settings_row.is_configured = True
        settings_row.save(update_fields=['is_configured'])
        self.client = Client()
        self.client.force_login(self.user)
        self.url = reverse('update_preferences')

    def _post(self, payload):
        return self.client.post(self.url, data=json.dumps(payload), content_type='application/json')

    def _prefs(self):
        return Profile.all_objects.get(user=self.user).preferences or {}

    def test_each_feature_persists_independently(self):
        self._post({'autofill_from_related': False, 'sticky_forms': True})

        prefs = self._prefs()
        self.assertIs(prefs['autofill_from_related'], False)
        self.assertIs(prefs['sticky_forms'], True)

    def test_turning_one_off_leaves_the_other_alone(self):
        self._post({'autofill_from_related': True, 'sticky_forms': True})
        self._post({'sticky_forms': False})

        prefs = self._prefs()
        self.assertIs(prefs['autofill_from_related'], True)
        self.assertIs(prefs['sticky_forms'], False)

    def test_values_are_coerced_to_bools(self):
        self._post({'autofill_from_related': 'on', 'sticky_forms': 'off'})

        prefs = self._prefs()
        self.assertIs(prefs['autofill_from_related'], True)
        self.assertIs(prefs['sticky_forms'], False)

    def test_preferences_reach_the_page_for_the_helper_to_read(self):
        self._post({'sticky_forms': True})

        response = self.client.get(reverse('options_view'))
        blob = response.content.decode()

        self.assertIn('sticky_forms', blob)


class StickyFormMarkerTests(TestCase):
    """dlux never emitted `data-model-name`/`data-app-label`, so its sticky path
    had no producer and could not run — any sticky behaviour seen before this
    came from project-side code."""

    def _render(self, instance):
        from django.template.loader import render_to_string
        from dlux.models import SystemSettings as _S
        from django import forms as dj_forms

        class _Plain(dj_forms.Form):
            name = dj_forms.CharField(required=False)

        return render_to_string('dlux/helpers/dynamic_modal_form.html', {
            'form': _Plain(),
            'sticky_app_label': '' if instance else _S._meta.app_label,
            'sticky_model_name': '' if instance else _S._meta.model_name,
            'request': None,
            'hide_form_buttons': True,
        })

    def test_create_form_advertises_the_model(self):
        html = self._render(instance=None)

        self.assertIn('data-app-label="dlux"', html)
        self.assertIn('data-model-name="systemsettings"', html)

    def test_edit_form_does_not(self):
        # Pre-filling an existing record from a different one would be data loss.
        html = self._render(instance=object())

        self.assertNotIn('data-model-name', html)


class StickyFormsServerHelperTests(TestCase):
    """Sticky prefill is a server-side concern — the initial data must be in the
    form before it renders — so dlux owns the gate, not a cookie."""

    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username='sticky', password='pw-12345678',
        )
        Profile.all_objects.get_or_create(user=self.user)

    def _request(self, method='GET', user=None):
        from django.test import RequestFactory

        request = getattr(RequestFactory(), method.lower())('/add/')
        request.user = user if user is not None else self.user
        return request

    def _set_pref(self, value):
        profile = Profile.all_objects.get(user=self.user)
        profile.preferences = {'sticky_forms': value}
        profile.save(update_fields=['preferences'])
        self.user.refresh_from_db()

    def test_off_by_default(self):
        from dlux.utils import sticky_forms_enabled

        self.assertFalse(sticky_forms_enabled(self._request()))

    def test_follows_the_user_preference(self):
        from dlux.utils import sticky_forms_enabled

        self._set_pref(True)
        self.assertTrue(sticky_forms_enabled(self._request()))

        self._set_pref(False)
        self.assertFalse(sticky_forms_enabled(self._request()))

    def test_anonymous_users_get_the_default(self):
        from django.contrib.auth.models import AnonymousUser
        from dlux.utils import sticky_forms_enabled

        self.assertFalse(sticky_forms_enabled(self._request(user=AnonymousUser())))

    def test_initial_is_empty_while_disabled(self):
        from dlux.models import SystemSettings
        from dlux.utils import sticky_form_initial

        self.assertEqual(
            sticky_form_initial(self._request(), SystemSettings, {'home_url': 'home_url'}),
            {},
        )

    def test_initial_comes_from_the_last_record_when_enabled(self):
        from dlux.models import SystemSettings
        from dlux.utils import sticky_form_initial

        self._set_pref(True)
        row = SystemSettings.load()
        row.home_url = '/dashboard/'
        row.save()

        initial = sticky_form_initial(self._request(), SystemSettings, {'home_url': 'home_url'})

        self.assertEqual(initial, {'home_url': '/dashboard/'})

    def test_never_prefills_a_post(self):
        from dlux.models import SystemSettings
        from dlux.utils import sticky_form_initial

        self._set_pref(True)
        SystemSettings.load().save()

        self.assertEqual(
            sticky_form_initial(self._request('POST'), SystemSettings, {'home_url': 'home_url'}),
            {},
        )

    def test_transform_can_derive_a_value(self):
        from dlux.models import SystemSettings
        from dlux.utils import sticky_form_initial

        self._set_pref(True)
        row = SystemSettings.load()
        row.home_url = '/a/'
        row.save()

        initial = sticky_form_initial(
            self._request(), SystemSettings, {'home_url': 'home_url'},
            transform=lambda data, last: {**data, 'home_url': data['home_url'] + 'b/'},
        )

        self.assertEqual(initial['home_url'], '/a/b/')


class StickyServerFormTests(SimpleTestCase):
    @property
    def _js(self):
        # Two sibling modules, one behaviour contract: related lives in
        # helpers/autofill, sticky in helpers/sticky.
        return (
            (_STATIC / 'helpers' / 'autofill' / 'js' / 'main.js').read_text(encoding='utf-8')
            + (_STATIC / 'helpers' / 'sticky' / 'js' / 'main.js').read_text(encoding='utf-8')
        )

    def test_server_prefilled_forms_are_not_also_filled_client_side(self):
        js = self._js

        self.assertIn("if (stickyEnabled() && form.dataset.stickyServer === undefined) {", js)

    def test_the_reload_waits_for_the_preference_to_be_stored(self):
        # Reloading straight after the fire-and-forget POST raced it: the GET
        # reached the server first, so the page came back with the old value and
        # the switch only appeared to work on the second click.
        js = self._js

        self.assertIn('const saved = setPref(key, enabled);', js)
        self.assertIn('saved.then(reload, reload);', js)
        sidebar = (_STATIC / 'sidebar' / 'js' / 'main.js').read_text(encoding='utf-8')
        self.assertIn('    return fetch(url, {', sidebar)

    def test_toggling_a_server_prefilled_form_reloads(self):
        # The prefill happened before render, so only a reload applies or undoes it.
        js = self._js

        self.assertIn("if (form.dataset.stickyServer !== undefined) {", js)
        self.assertIn('window.location.reload();', js)


class AssistControlUsesTheSettingsSwitchTests(SimpleTestCase):
    """A thin bar at the top of the form, carrying the System Settings switch.

    The bar is dlux's own; the switch inside it must be the shared control from
    `build_settings_toggle_field`, because helpers/toggle/css/main.css and the themes style
    it by those exact class names — a hand-rolled `form-check form-switch` gets
    none of that and renders as a bare browser checkbox.
    """

    @property
    def _js(self):
        # Two sibling modules, one behaviour contract: related lives in
        # helpers/autofill, sticky in helpers/sticky.
        return (
            (_STATIC / 'helpers' / 'autofill' / 'js' / 'main.js').read_text(encoding='utf-8')
            + (_STATIC / 'helpers' / 'sticky' / 'js' / 'main.js').read_text(encoding='utf-8')
        )

    @property
    def _bar_css(self):
        css = (_STATIC / 'base' / 'css' / 'main.css').read_text(encoding='utf-8')
        return '\n'.join(
            rule for rule in css.split('\n}')
            if '.dlux-assist-bar' in rule.split('{')[0]
        )

    @property
    def _builder(self):
        src = (Path(__file__).resolve().parents[1] / 'forms' / 'builders.py').read_text(encoding='utf-8')
        builder = src[src.index('def build_settings_toggle_field'):]
        cut = builder.find('\ndef ', 10)
        return builder[:cut] if cut != -1 else builder

    def test_the_control_is_a_thin_bar(self):
        js = self._js

        self.assertIn("bar.className = 'dlux-assist-bar';", js)
        self.assertIn("legend.className = 'dlux-assist-bar__legend';", js)
        # Not the full settings field card — that is a settings-page layout.
        self.assertNotIn('dlux-settings-toggle-field d-flex', js)
        self.assertNotIn('dlux-settings-toggle-field__label', js)
        self.assertNotIn('dlux-settings-toggle-field__help', js)

    def test_the_switch_classes_match_the_python_builder(self):
        builder = self._builder
        js = self._js

        for cls in (
            'dlux-settings-toggle-field__control form-switch',
            'form-check-input dlux-settings-toggle-field__input',
        ):
            with self.subTest(cls=cls):
                self.assertIn(cls, builder)
                self.assertIn(cls, js)

    def test_the_input_is_a_checkbox(self):
        # Without this Bootstrap's `.form-switch .form-check-input` rules never
        # apply and the control renders as a plain input.
        js = self._js

        self.assertIn("input.type = 'checkbox';", js)
        self.assertIn("type='checkbox'", self._builder)

    def test_the_switch_is_not_hand_rolled(self):
        js = self._js

        self.assertNotIn("'form-check form-switch", js)
        self.assertNotIn('role="switch"', js)
        self.assertNotIn('form-check-label', js)

    def test_the_switch_sits_at_the_end_of_the_bar(self):
        js = self._js

        self.assertLess(js.index('bar.appendChild(legend);'), js.index('bar.appendChild(buildSwitch('))
        self.assertIn('margin-inline-end: auto;', (_STATIC / 'base' / 'css' / 'main.css').read_text(encoding='utf-8'))

    def test_the_switch_cannot_be_squeezed_flat(self):
        # It inherits the bar's 0.85rem text size, and Bootstrap sizes the switch
        # in `em`; an input also has no content to stop a flex parent shrinking it.
        block = self._bar_css

        self.assertIn('font-size: 1rem;', block)
        self.assertIn('flex: 0 0 auto;', block)
        self.assertIn('min-width: 2em;', block)

    def test_the_switch_keeps_bootstraps_rtl_knob(self):
        # Pinning background-position would send the knob the wrong way in Arabic.
        self.assertNotIn('background-position', self._bar_css)

    def test_no_choice_selector_markup_is_emitted(self):
        js = self._js

        self.assertNotIn('dlux-choice-selector', js)
        self.assertNotIn('dlux-choice-toggle', js)

    def test_every_rendered_switch_follows_the_stored_value(self):
        js = self._js

        self.assertIn('document.querySelectorAll(`[data-dlux-assist-pref="${key}"]`)', js)
