"""Dismissible-dialog registry and the Options-page reset action.

A prompt that can be permanently dismissed needs a way back. Registering it
makes it resettable in one action, without touching unrelated preferences.
"""
import json
from pathlib import Path

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from dlux.dialogs import (
    _REGISTRY,
    get_dismissible_dialogs,
    register_dismissible_dialog,
    reset_dismissible_dialogs,
)
from dlux.models import Profile

_STATIC = Path(__file__).resolve().parents[1] / 'static' / 'dlux' / 'base'
_TEMPLATES = Path(__file__).resolve().parents[1] / 'templates' / 'dlux'


class _RegistryIsolation:
    """Registering is process-global, so tests restore the built-ins they touch."""

    def setUp(self):
        super().setUp()
        self._snapshot = {key: dict(value) for key, value in _REGISTRY.items()}

    def tearDown(self):
        _REGISTRY.clear()
        _REGISTRY.update(self._snapshot)
        super().tearDown()


class DialogRegistryTests(_RegistryIsolation, SimpleTestCase):
    def test_builtin_dialogs_are_registered(self):
        ids = {dialog['id'] for dialog in get_dismissible_dialogs()}

        self.assertIn('dlux.unsaved_changes', ids)
        self.assertIn('dlux.initial_user_setup', ids)

    def test_downstream_apps_can_register_an_app_namespaced_prompt(self):
        register_dismissible_dialog(
            id='archive.install_app',
            label='Install as app prompt',
            app_namespace='archive.pwa',
            app_preference_key='dismissed',
        )

        registered = {dialog['id']: dialog for dialog in get_dismissible_dialogs()}
        self.assertEqual(registered['archive.install_app']['app_namespace'], 'archive.pwa')
        self.assertEqual(registered['archive.install_app']['app_preference_key'], 'dismissed')

    def test_registering_the_same_id_replaces_rather_than_duplicates(self):
        register_dismissible_dialog(id='x.y', label='First', preference_key='a')
        register_dismissible_dialog(id='x.y', label='Second', preference_key='b')

        matches = [d for d in get_dismissible_dialogs() if d['id'] == 'x.y']
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]['label'], 'Second')

    def test_invalid_registrations_are_rejected(self):
        with self.assertRaises(ValueError):
            register_dismissible_dialog(id='bad id!', label='X', preference_key='a')
        with self.assertRaises(ValueError):
            register_dismissible_dialog(id='x.z', label='', preference_key='a')
        with self.assertRaises(ValueError):
            register_dismissible_dialog(id='x.z', label='X')
        with self.assertRaises(ValueError):
            # A namespace without a key would clear nothing.
            register_dismissible_dialog(id='x.z', label='X', app_namespace='ns')
        with self.assertRaises(ValueError):
            register_dismissible_dialog(id='x.z', label='X', app_preference_key='k')


class DialogResetTests(_RegistryIsolation, TestCase):
    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_user(
            username='admin', password='pw-12345678', is_staff=True, is_superuser=True,
        )
        self.profile, _ = Profile.all_objects.get_or_create(user=self.user)

    def _reload(self):
        return Profile.all_objects.get(pk=self.profile.pk)

    def test_clears_a_top_level_preference_dismissal(self):
        self.profile.preferences = {'skip_unsaved_settings_prompt': True}
        self.profile.save()

        count = reset_dismissible_dialogs(self._reload())

        self.assertGreaterEqual(count, 1)
        self.assertNotIn('skip_unsaved_settings_prompt', self._reload().preferences)

    def test_clears_an_app_namespaced_dismissal_and_prunes_empty_scaffolding(self):
        register_dismissible_dialog(
            id='archive.install_app', label='Install prompt',
            app_namespace='archive.pwa', app_preference_key='dismissed',
        )
        self.profile.preferences = {'app': {'archive.pwa': {'dismissed': True}}}
        self.profile.save()

        reset_dismissible_dialogs(self._reload())

        prefs = self._reload().preferences
        self.assertNotIn('app', prefs)

    def test_keeps_other_keys_in_the_same_app_namespace(self):
        register_dismissible_dialog(
            id='archive.install_app', label='Install prompt',
            app_namespace='archive.pwa', app_preference_key='dismissed',
        )
        self.profile.preferences = {
            'app': {'archive.pwa': {'dismissed': True, 'variant': 'compact'}},
        }
        self.profile.save()

        reset_dismissible_dialogs(self._reload())

        namespace = self._reload().preferences['app']['archive.pwa']
        self.assertNotIn('dismissed', namespace)
        self.assertEqual(namespace['variant'], 'compact')

    def test_unrelated_preferences_are_untouched(self):
        # This is the whole reason it is separate from the full preferences reset.
        self.profile.preferences = {
            'skip_unsaved_settings_prompt': True,
            'theme': 'dark',
            'table_density': 'dense',
            'sidebar_collapsed': True,
        }
        self.profile.save()

        reset_dismissible_dialogs(self._reload())

        prefs = self._reload().preferences
        self.assertEqual(prefs['theme'], 'dark')
        self.assertEqual(prefs['table_density'], 'dense')
        self.assertIs(prefs['sidebar_collapsed'], True)

    def test_clears_a_profile_field_dismissal(self):
        self.profile.is_configured = True
        self.profile.save()

        reset_dismissible_dialogs(self._reload())

        self.assertFalse(self._reload().is_configured)

    def test_nothing_to_reset_is_not_an_error(self):
        self.profile.preferences = {'theme': 'dark'}
        self.profile.is_configured = False
        self.profile.save()

        self.assertEqual(reset_dismissible_dialogs(self._reload()), 0)
        self.assertEqual(self._reload().preferences, {'theme': 'dark'})

    def test_handles_a_legacy_non_dict_preferences_value(self):
        # Older rows stored preferences as a JSON string.
        Profile.all_objects.filter(pk=self.profile.pk).update(preferences='{}')

        self.assertEqual(reset_dismissible_dialogs(self._reload()), 0)


class DialogResetEndpointTests(_RegistryIsolation, TestCase):
    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_user(
            username='admin', password='pw-12345678', is_staff=True, is_superuser=True,
        )
        self.profile, _ = Profile.all_objects.get_or_create(user=self.user)
        self.client = Client()
        self.client.force_login(self.user)
        self.url = reverse('reset_dialog_prompts')

    def test_endpoint_resets_and_reports_counts(self):
        self.profile.preferences = {'skip_unsaved_settings_prompt': True, 'theme': 'dark'}
        self.profile.save()

        response = self.client.post(self.url, data=json.dumps({}), content_type='application/json')
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])
        self.assertGreaterEqual(payload['reset'], 1)
        self.assertGreaterEqual(payload['registered'], 2)

        prefs = Profile.all_objects.get(pk=self.profile.pk).preferences
        self.assertNotIn('skip_unsaved_settings_prompt', prefs)
        self.assertEqual(prefs['theme'], 'dark')

    def test_endpoint_rejects_get(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_endpoint_requires_login(self):
        anonymous = Client()
        response = anonymous.post(self.url, data=json.dumps({}), content_type='application/json')

        self.assertIn(response.status_code, (302, 403))


class DialogResetUiTests(SimpleTestCase):
    @property
    def _options_html(self):
        return (_TEMPLATES / 'system' / 'options.html').read_text(encoding='utf-8')

    @property
    def _options_js(self):
        return (_STATIC.parent / 'system' / 'js' / 'options.js').read_text(encoding='utf-8')

    def test_both_actions_live_on_one_bar(self):
        html = self._options_html

        self.assertIn('data-reset-scope="dialogs"', html)
        self.assertIn('data-reset-scope="preferences"', html)
        self.assertEqual(html.count('data-reset-bar'), 2)
        # One bar, two action groups — not two stacked bars.
        self.assertEqual(html.count('dlux-options-reset-bar"'), 0)
        self.assertEqual(html.count('class="dlux-options-reset-bar '), 1)
        self.assertEqual(html.count('dlux-options-reset-group'), 2)

    def test_dialog_bar_mirrors_the_inline_confirm_pattern(self):
        html = self._options_html

        self.assertIn('id="btnResetDialogsInit"', html)
        self.assertIn('id="resetDialogsActions"', html)
        self.assertIn('data-reset-confirm', html)
        self.assertIn('data-reset-cancel', html)

    def test_original_reset_bar_keeps_its_ids(self):
        # Released markup other code and tests key off.
        html = self._options_html

        self.assertIn('id="btnResetInit"', html)
        self.assertIn('id="resetActions"', html)
        self.assertIn('id="btnResetConfirm"', html)
        self.assertIn('id="btnResetCancel"', html)

    def test_one_implementation_drives_both_bars(self):
        js = self._options_js

        self.assertIn('function initResetBars(grid)', js)
        self.assertIn("document.querySelectorAll('[data-reset-bar][data-reset-url]')", js)
        self.assertNotIn('function initResetDefaults', js)

    def test_restoring_prompts_does_not_wipe_local_ui_state(self):
        # Card order and theme live in localStorage; only the full reset clears them.
        js = self._options_js

        self.assertIn("const clearsLocalStorage = panel.dataset.resetScope !== 'dialogs';", js)
        self.assertIn('if (clearsLocalStorage) {', js)
