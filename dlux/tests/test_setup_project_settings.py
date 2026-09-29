"""Project settings in the first-run setup wizard.

A project's `register_app_settings()` tiles appear as one extra step after Dlux's
own, each section the tile's own form with prefixed field names. They validate
with the rest of the wizard and save into the same row the wizard saves.
"""
from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django import forms
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from dlux import options
from dlux.models import SystemSettings
from dlux.system.constants import SETUP_STEP_COUNT
from dlux.tests.test_accent_edges import _form_data

NAMESPACE = 'proj.settings'
PREFIX = options.setup_form_prefix(NAMESPACE)


def _register(**overrides):
    kwargs = {
        'namespace': NAMESPACE,
        'title': 'Project Options',
        'description': 'Switches this project adds',
        'fields': [
            {'name': 'enabled', 'type': 'boolean', 'label': 'Enable project feature', 'default': True},
            {'name': 'limit', 'type': 'integer', 'label': 'Limit', 'default': 5, 'min_value': 1, 'max_value': 20},
        ],
    }
    kwargs.update(overrides)
    options.register_app_settings(**kwargs)


class RegistryTests(SimpleTestCase):
    def setUp(self):
        options.clear_registry()
        self.addCleanup(options.clear_registry)

    def test_tiles_join_setup_unless_they_opt_out(self):
        _register()
        _register(namespace='proj.later', setup=False)
        self.assertTrue(options._SETTINGS_REGISTRY[NAMESPACE]['setup'])
        self.assertFalse(options._SETTINGS_REGISTRY['proj.later']['setup'])

    def test_prefix_is_a_safe_name_that_cannot_be_a_dlux_field(self):
        self.assertEqual(options.setup_form_prefix('crm.options-v2'), 'app__crm_options_v2')

    def test_merge_sets_one_namespace_and_keeps_everything_else(self):
        extra = {'scanlink': {'enabled': True}, 'app': {'other.ns': {'x': 1}}}
        merged = options.merge_app_system_config(extra, NAMESPACE, {'limit': 3})
        self.assertEqual(merged['app'], {'other.ns': {'x': 1}, NAMESPACE: {'limit': 3}})
        self.assertEqual(merged['scanlink'], {'enabled': True})
        self.assertNotIn(NAMESPACE, extra['app'], 'the input is not modified')
        cleared = options.merge_app_system_config(merged, NAMESPACE, None)
        self.assertEqual(cleared['app'], {'other.ns': {'x': 1}})

    def test_merge_refuses_what_a_tile_save_refuses(self):
        with self.settings(DLUX_MAX_SYSTEM_APP_CONFIG_BYTES=1024):
            with self.assertRaises(options.AppSystemConfigError):
                options.merge_app_system_config({}, NAMESPACE, {'blob': 'x' * 2000})


class PrefixedFormTests(TestCase):
    def setUp(self):
        options.clear_registry()
        self.addCleanup(options.clear_registry)

    def test_builtin_fields_carry_the_prefix(self):
        _register()
        definition = options._SETTINGS_REGISTRY[NAMESPACE]
        form = options.build_app_settings_form(definition, None, prefix=PREFIX)
        html = str(form['limit'])
        self.assertIn(f'name="{PREFIX}-limit"', html)
        bound = options.build_app_settings_form(definition, None, data={f'{PREFIX}-limit': '7'}, prefix=PREFIX)
        self.assertTrue(bound.is_valid(), bound.errors)
        self.assertEqual(bound.cleaned_data['limit'], 7)

    def test_a_custom_form_without_kwargs_is_still_prefixed(self):
        class Strict(forms.Form):
            name = forms.CharField(required=False)

            def __init__(self, data=None, initial=None):
                super().__init__(data=data, initial=initial)

        _register(fields=None, form_class=Strict)
        form = options.build_app_settings_form(options._SETTINGS_REGISTRY[NAMESPACE], None, prefix=PREFIX)
        self.assertIn(f'name="{PREFIX}-name"', str(form['name']))


class SetupWizardProjectStepTests(TestCase):
    def setUp(self):
        options.clear_registry()
        self.addCleanup(options.clear_registry)
        cache.clear()
        settings_obj = SystemSettings.load()
        settings_obj.is_configured = False
        settings_obj.extra_config = {'scanlink': {'enabled': True}, 'app': {'other.ns': {'x': 1}}}
        settings_obj.save()
        cache.clear()
        self.admin = get_user_model().objects.create_superuser('setup-root', 'root@example.com', 'pw12345!')
        self.client.force_login(self.admin)
        session = self.client.session
        session['dlux_initial_setup_language'] = 'en'
        session.save()

    def _settings(self):
        cache.clear()
        return SystemSettings.load()

    def test_the_step_is_last_and_numbered_after_dlux_steps(self):
        _register()
        response = self.client.get(reverse('system_setup'))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn('data-dlux-project-settings-step', body)
        self.assertIn(f'data-dlux-wizard-step-target="{SETUP_STEP_COUNT}"', body)
        self.assertIn(f'Step {SETUP_STEP_COUNT + 1}: Project Settings', body)
        self.assertIn('Project Options', body)
        self.assertIn(f'name="{PREFIX}-limit"', body)
        # After Extras, before the wizard's buttons: no Dlux step changes index.
        self.assertLess(body.index('data-dlux-project-settings-step'), body.index('dlux-setup-wizard-actions'))

    def test_no_registered_tiles_means_no_step(self):
        body = self.client.get(reverse('system_setup')).content.decode()
        self.assertNotIn('data-dlux-project-settings-step', body)
        self.assertNotIn(f'data-dlux-wizard-step-target="{SETUP_STEP_COUNT}"', body)

    def test_a_tile_that_opts_out_is_not_in_setup(self):
        _register(setup=False)
        body = self.client.get(reverse('system_setup')).content.decode()
        self.assertNotIn('data-dlux-project-settings-step', body)

    def test_finishing_setup_saves_each_section_with_the_wizard(self):
        _register()
        response = self.client.post(reverse('system_setup'), _form_data(**{
            f'{PREFIX}-limit': '12',
            # `enabled` left unchecked: a switched-off toggle posts nothing.
        }))
        self.assertEqual(response.status_code, 302, response.content[:2000])
        saved = self._settings()
        self.assertTrue(saved.is_configured)
        self.assertEqual(saved.extra_config['app'][NAMESPACE], {'enabled': False, 'limit': 12})
        self.assertEqual(saved.extra_config['app']['other.ns'], {'x': 1})
        self.assertIn('scanlink', saved.extra_config)

    def test_an_invalid_section_keeps_the_wizard_unsaved_and_shows_the_error(self):
        _register()
        response = self.client.post(reverse('system_setup'), _form_data(**{f'{PREFIX}-limit': '99'}))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        step = body[body.index('data-dlux-project-settings-step'):]
        self.assertIn('invalid-feedback', step[:step.index('dlux-setup-wizard-actions')])
        saved = self._settings()
        self.assertFalse(saved.is_configured)
        self.assertNotIn(NAMESPACE, saved.extra_config.get('app', {}))

    def test_a_refused_value_is_reported_on_its_section(self):
        _register()
        with self.settings(DLUX_MAX_SYSTEM_APP_CONFIG_BYTES=1024):
            SystemSettings.objects.filter(pk=1).update(extra_config={'pad': 'x' * 2000})
            cache.clear()
            response = self.client.post(reverse('system_setup'), _form_data(**{f'{PREFIX}-limit': '3'}))
        self.assertEqual(response.status_code, 200)
        self.assertIn('too large', response.content.decode())
        self.assertFalse(self._settings().is_configured)

    def test_stored_values_are_rendered_not_evaluated(self):
        _register(fields=[{'name': 'label', 'type': 'string', 'label': 'Label', 'default': ''}])
        settings_obj = self._settings()
        settings_obj.extra_config = {'app': {NAMESPACE: {'label': '{{ request.user.password }}'}}}
        settings_obj.save()
        cache.clear()
        body = self.client.get(reverse('system_setup')).content.decode()
        self.assertIn('{{ request.user.password }}', body)
        self.assertNotIn(self.admin.password, body)
