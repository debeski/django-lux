"""A step's master toggle dims and disables its dependent settings; it never
hides them and never resets them.

Disabled controls do not post, so every conversion from hide→disable needs a
matching server-side guard or switching a feature off would silently wipe the
configuration the admin is only parking.
"""
from pathlib import Path

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.template import Context, Template
from django.test import RequestFactory, SimpleTestCase, TestCase

from dlux.forms import SystemSettingsForm
from dlux.models import SystemSettings

_SETUP_JS = Path(__file__).resolve().parents[1] / 'static' / 'dlux' / 'main' / 'js' / 'system_setup.js'
_SETUP_CSS = Path(__file__).resolve().parents[1] / 'static' / 'dlux' / 'main' / 'css' / 'system_setup.css'

_BASE_DATA = {
    'system_names': '{"en": "System", "ar": "System"}',
    'home_url': '/dashboard/',
    'default_language': 'en',
    'default_theme': 'light',
    'allowed_themes': ['light'],
    'languages': '{}',
    'translations_override': '{}',
    'sidebar_config': '{"enabled":true,"entries":[]}',
}


class DependentSectionAssetTests(SimpleTestCase):
    @property
    def _js(self):
        return _SETUP_JS.read_text(encoding='utf-8')

    def test_one_helper_owns_the_disabled_state(self):
        js = self._js

        self.assertIn('function setDependentSectionEnabled(form, section, enabled, fieldNames, reason)', js)
        self.assertIn("section.classList.toggle('is-disabled', !enabled);", js)
        self.assertIn("section.setAttribute('aria-disabled', enabled ? 'false' : 'true');", js)

    def test_dependent_sections_are_never_hidden(self):
        js = self._js

        self.assertIn("section.removeAttribute('aria-hidden');", js)
        self.assertIn("section.classList.remove('d-none');", js)

    def test_every_step_master_toggle_uses_the_helper(self):
        js = self._js

        self.assertIn('DEPENDENT_FIELDS.navbar, dependentReason(enabledToggle))', js)
        self.assertIn('DEPENDENT_FIELDS.notifications, dependentReason(masterToggle))', js)
        self.assertIn('setDependentSectionEnabled(form, section, enabled, [], dependentReason(emailEnabledToggle))', js)
        self.assertIn('DEPENDENT_FIELDS.sidebar,', js)

    def test_no_step_master_toggle_still_hides_its_section(self):
        js = self._js

        for stale in (
            "dependentSection.classList.toggle('d-none', !enabledToggle.checked)",
            "dependentSection.classList.toggle('d-none', !masterToggle.checked)",
            "section.classList.toggle('d-none', !enabled)",
        ):
            with self.subTest(stale=stale):
                self.assertNotIn(stale, js)

    def test_field_lists_are_declared_once(self):
        js = self._js

        # The sidebar list previously existed twice and drifted between copies.
        self.assertEqual(js.count("'sidebar_collapse_mode',\n            'sidebar_toggle_icon',"), 1)
        self.assertEqual(js.count('const DEPENDENT_FIELDS = {'), 1)

    def test_disabled_section_reads_as_inert(self):
        css = _SETUP_CSS.read_text(encoding='utf-8')

        self.assertIn('.dlux-dependent-settings.is-disabled', css)
        self.assertIn('opacity: 0.58;', css)
        self.assertIn('.dlux-dependent-settings.is-disabled .dlux-navbar-builder', css)


class DependentSectionMarkupTests(TestCase):
    """The server renders the same state the JS maintains, so an off step shows
    its settings on first paint instead of hiding them until JS runs."""

    def _render(self, instance):
        form = SystemSettingsForm(instance=instance)
        return Template('{% load crispy_forms_tags %}{% crispy form %}').render(Context({'form': form}))

    def test_navbar_section_renders_disabled_not_hidden(self):
        html = self._render(SystemSettings(is_configured=True, navbar_config={'enabled': False}))

        self.assertIn('data-navbar-dependent', html)
        self.assertIn('dlux-navbar-dependent-settings is-disabled', html)
        self.assertNotIn('dlux-navbar-dependent-settings d-none', html)

    def test_navbar_section_renders_enabled_when_on(self):
        html = self._render(SystemSettings(is_configured=True, navbar_config={'enabled': True}))

        self.assertIn('data-navbar-dependent', html)
        self.assertNotIn('dlux-navbar-dependent-settings is-disabled', html)

    def test_notifications_section_renders_disabled_not_hidden(self):
        html = self._render(SystemSettings(is_configured=True, notification_config={'enabled': False}))

        self.assertIn('data-notifications-dependent', html)
        self.assertIn('dlux-notifications-dependent-settings is-disabled', html)
        self.assertNotIn('dlux-notifications-dependent-settings d-none', html)

    def test_email_section_renders_disabled_not_hidden(self):
        html = self._render(SystemSettings(is_configured=True, email_config={'enabled': False}))

        self.assertIn('data-email-config-section', html)
        self.assertIn('dlux-email-config-section is-disabled', html)
        self.assertNotIn('dlux-email-config-section d-none', html)


class DependentSettingsPreservedOnDisableTests(TestCase):
    """The point of the pattern: an off switch parks settings, never erases them."""

    def _save(self, step, data, instance):
        request = RequestFactory().get(f'/sys/modals/dlux/systemsettings/1/?step={step}')
        form = SystemSettingsForm(data={**_BASE_DATA, **data}, instance=instance, request=request)
        self.assertTrue(form.is_valid(), form.errors)
        return form.save(commit=False)

    def test_turning_the_navbar_off_keeps_its_mode_and_hierarchy(self):
        instance = SystemSettings(
            is_configured=True,
            navbar_config={
                'enabled': True,
                'default_mode': 'history',
                'allow_user_mode_override': False,
                'root': {'mode': 'neutral', 'url_name': ''},
                'hierarchy': {'nodes': [{'kind': 'manual', 'id': 'ops', 'children': []}]},
            },
        )

        # The dependent controls are disabled, so they are absent from POST —
        # exactly what the browser sends once the master toggle is off.
        saved = self._save(6, {
            'navbar_config': (
                '{"enabled":false,"default_mode":"history","allow_user_mode_override":false,'
                '"root":{"mode":"neutral","url_name":""},'
                '"hierarchy":{"nodes":[{"kind":"manual","id":"ops","children":[]}]}}'
            ),
        }, instance)

        self.assertFalse(saved.navbar_config['enabled'])
        self.assertEqual(saved.navbar_config['default_mode'], 'history')
        self.assertFalse(saved.navbar_config['allow_user_mode_override'])
        self.assertEqual(len(saved.navbar_config['hierarchy']['nodes']), 1)

    def test_turning_notifications_off_keeps_the_whole_configuration(self):
        instance = SystemSettings(
            is_configured=True,
            notification_config={
                'enabled': True,
                'flash': {
                    'enabled': True,
                    'position': 'bottom_end',
                    'size': 'roomy',
                    'text_size': 'lg',
                    'timeout_ms': 9000,
                    'max_visible': 7,
                },
                'drawer': {'enabled': False, 'badge_enabled': False, 'preview_limit': 8},
                'bridge': {'django_messages_enabled': True},
                'automatic': {'scoped_model_crud': False, 'create': False,
                              'update': 'off', 'delete': False},
            },
        )

        saved = self._save(8, {'notifications_enabled': ''}, instance)

        stored = saved.notification_config
        self.assertFalse(stored['enabled'])
        self.assertEqual(stored['flash']['position'], 'bottom_end')
        self.assertEqual(stored['flash']['timeout_ms'], 9000)
        self.assertEqual(stored['flash']['max_visible'], 7)
        self.assertFalse(stored['drawer']['badge_enabled'])
        self.assertTrue(stored['bridge']['django_messages_enabled'])
        self.assertFalse(stored['automatic']['create'])

    def test_turning_notifications_back_on_still_reads_the_posted_values(self):
        # The preservation branch must not swallow a real edit.
        instance = SystemSettings(is_configured=True, notification_config={'enabled': False})

        saved = self._save(8, {
            'notifications_enabled': 'on',
            'notification_flash_enabled': 'on',
            'notification_flash_position': 'top_start',
            'notification_flash_timeout_ms': '4500',
        }, instance)

        self.assertTrue(saved.notification_config['enabled'])
        self.assertEqual(saved.notification_config['flash']['position'], 'top_start')
        self.assertEqual(saved.notification_config['flash']['timeout_ms'], 4500)

    def test_turning_the_sidebar_off_keeps_its_settings(self):
        # The pattern this consistency pass is modelled on — pinned so the
        # reference implementation cannot regress either.
        instance = SystemSettings(
            is_configured=True,
            sidebar_config={
                'enabled': True,
                'entries': [],
                'collapse_mode': 'hidden',
                'density': 'roomy',
                'toggle_icon': 'bi-arrow-bar-left',
                'show_icons': False,
            },
        )

        saved = self._save(5, {
            'sidebar_config': (
                '{"enabled":false,"entries":[],"collapse_mode":"hidden","density":"roomy",'
                '"toggle_icon":"bi-arrow-bar-left","show_icons":false}'
            ),
        }, instance)

        self.assertFalse(saved.sidebar_config['enabled'])
        self.assertEqual(saved.sidebar_config['collapse_mode'], 'hidden')
        self.assertEqual(saved.sidebar_config['density'], 'roomy')
        self.assertEqual(saved.sidebar_config['toggle_icon'], 'bi-arrow-bar-left')


class DependentFieldConversionTests(SimpleTestCase):
    """Access & Security, Logging and Profile steps follow the same rule as the
    Sidebar/Nav Bar/Email steps: dependents are dimmed and inert, never hidden."""

    @property
    def _js(self):
        return _SETUP_JS.read_text(encoding='utf-8')

    def test_field_level_helper_matches_the_section_contract(self):
        js = self._js

        self.assertIn('function setDependentFieldEnabled(field, enabled, reason)', js)
        self.assertIn("field.classList.remove('d-none');", js)
        self.assertIn("field.setAttribute('aria-disabled', enabled ? 'false' : 'true');", js)

    def test_builder_helper_disables_json_builder_controls(self):
        js = self._js

        self.assertIn('function setBuilderSectionEnabled(section, enabled, reason)', js)
        self.assertIn("section.classList.remove('d-none');", js)

    def test_security_step_dependents_no_longer_hide(self):
        js = self._js

        self.assertIn('setDependentFieldEnabled(field, enabled, registrationReason)', js)
        self.assertIn('setDependentFieldEnabled(field, publicRootEnabled, rootReason)', js)
        self.assertIn('setDependentFieldEnabled(field, splitEnabled, splitReason)', js)
        self.assertNotIn("field.classList.toggle('d-none', !publicRootEnabled)", js)
        self.assertNotIn("field.classList.toggle('d-none', !enabled)", js)

    def test_logging_and_profile_builders_no_longer_hide(self):
        js = self._js

        self.assertIn('setBuilderSectionEnabled(dependent, master.checked,', js)
        self.assertIn('setBuilderSectionEnabled(depEl, enabledInput.checked,', js)
        self.assertIn('setBuilderSectionEnabled(onbDep, onbEnabled.checked,', js)
        self.assertNotIn("dependent.classList.toggle('d-none', !master.checked)", js)
        self.assertNotIn("depEl.classList.toggle('d-none', !enabledInput.checked)", js)
        self.assertNotIn("onbDep.classList.toggle('d-none', !onbEnabled.checked)", js)

    def test_email_actions_are_disabled_with_their_step(self):
        # A plain <button> carries no field name, so the name-based disabling
        # missed it and the apply/test actions stayed clickable.
        js = self._js

        self.assertIn("section.querySelectorAll('button, a.btn').forEach((control) => {", js)
        self.assertIn('control.disabled = !enabled;', js)


class DisabledReasonTooltipTests(SimpleTestCase):
    """A disabled control should say why it is disabled."""

    @property
    def _js(self):
        return _SETUP_JS.read_text(encoding='utf-8')

    def test_reason_is_taken_from_the_controlling_toggles_own_label(self):
        js = self._js

        self.assertIn('function dependentReason(toggle)', js)
        self.assertIn(".dlux-settings-toggle-field__label", js)
        self.assertIn("template.replace('{name}', name)", js)

    def test_tooltip_is_set_while_disabled_and_removed_when_enabled(self):
        js = self._js

        self.assertIn('function applyDependentTooltip(el, enabled, reason)', js)
        self.assertIn("el.removeAttribute('data-dlux-tooltip');", js)
        self.assertIn("el.setAttribute('data-dlux-tooltip', reason);", js)

    def test_tooltip_lands_on_the_container_not_the_disabled_control(self):
        # A disabled input does not emit pointer events in every browser, so the
        # tooltip has to hang off the wrapper, which is never disabled.
        js = self._js
        block = js[js.index('function setDependentFieldEnabled'):]
        block = block[:block.index('\n    function ', 10)]

        self.assertIn('applyDependentTooltip(field, enabled, reason);', block)
