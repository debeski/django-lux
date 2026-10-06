from dlux.tests.harness import setup_test_environment
setup_test_environment()

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template import Context, Template
from django.test import RequestFactory, TestCase

from dlux.forms import SystemSettingsForm
from dlux.models import SystemSettings
from dlux.system.constants import SETUP_STEP_EXTRAS, SETUP_STEP_BACKUPS
from dlux.tests.test_weather import BASE


class EntryClipboardSettingsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.user = get_user_model().objects.create_superuser(username='clipboard-admin', password='test-password')
        self.record = SystemSettings.load()
        self.record.is_configured = True
        self.record.extra_config = {'app': {'crm': {'keep': True}}}
        self.record.save()

    def save_step(self, enabled, step=SETUP_STEP_EXTRAS):
        request = RequestFactory().get('/?step=' + str(step))
        request.user = self.user
        form = SystemSettingsForm(data={**BASE, 'entry_clipboard_enabled': 'on' if enabled else ''},
                                  instance=SystemSettings.load(), request=request)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.record.refresh_from_db()

    def test_real_settings_round_trip_and_other_step_preservation(self):
        self.assertFalse(SystemSettingsForm(instance=self.record).initial['entry_clipboard_enabled'])
        self.save_step(True)
        self.assertTrue(self.record.extra_config['entry_clipboard']['enabled'])
        self.assertTrue(self.record.extra_config['app']['crm']['keep'])
        self.assertTrue(SystemSettingsForm(instance=self.record).initial['entry_clipboard_enabled'])
        self.save_step(False, SETUP_STEP_BACKUPS)
        self.assertTrue(self.record.extra_config['entry_clipboard']['enabled'])
        self.save_step(False)
        self.assertFalse(self.record.extra_config['entry_clipboard']['enabled'])

    def test_asset_gate_requires_enabled_and_authenticated(self):
        from types import SimpleNamespace
        template = Template('{% include "dlux/helpers/dynamic_modal.html" %}')
        for enabled, authenticated, expected in [(False, True, False), (True, False, False), (True, True, True)]:
            request = SimpleNamespace(user=SimpleNamespace(is_authenticated=authenticated, pk=1), csp_nonce='test')
            html = template.render(Context({'request': request, 'DLUX_ENTRY_CLIPBOARD_ENABLED': enabled}))
            self.assertEqual('entry_clipboard.js' in html, expected)
            self.assertEqual('entry_clipboard.css' in html, expected)

    def test_runtime_context_gate(self):
        from dlux.context_processors import dlux_context
        request = RequestFactory().get('/')
        request.session = {}
        request.user = self.user
        self.assertFalse(dlux_context(request)['DLUX_ENTRY_CLIPBOARD_ENABLED'])
        self.save_step(True)
        self.assertTrue(dlux_context(request)['DLUX_ENTRY_CLIPBOARD_ENABLED'])

    def test_bound_form_seeds_clipboard_after_refreshing_stale_instance(self):
        self.record.extra_config = {'entry_clipboard': {'enabled': True}}
        self.record.save()
        SystemSettings.objects.filter(pk=self.record.pk).update(extra_config={'entry_clipboard': {'enabled': False}})
        request = RequestFactory().get('/?step=' + str(SETUP_STEP_BACKUPS))
        request.user = self.user
        form = SystemSettingsForm(data=BASE, instance=self.record, request=request)
        self.assertFalse(form.initial['entry_clipboard_enabled'])
        self.assertTrue(form.fields['entry_clipboard_enabled'].disabled)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.record.refresh_from_db()
        self.assertFalse(self.record.extra_config['entry_clipboard']['enabled'])

    def test_clipboard_can_save_without_scanlink_field(self):
        self.record.extra_config = {'scanlink': {'enabled': True}, 'app': {'crm': {'keep': True}}}
        self.record.save()
        request = RequestFactory().get('/?step=' + str(SETUP_STEP_EXTRAS))
        request.user = self.user
        form = SystemSettingsForm(instance=self.record, request=request)
        form.cleaned_data = {'entry_clipboard_enabled': True}
        form._apply_extra_features(self.record)
        self.record.save()
        self.record.refresh_from_db()
        self.assertTrue(self.record.extra_config['entry_clipboard']['enabled'])
        self.assertTrue(self.record.extra_config['scanlink']['enabled'])
        self.assertTrue(self.record.extra_config['app']['crm']['keep'])

    def test_export_import_and_uploaded_file_round_trip(self):
        import json
        from dlux.utils.import_export import apply_system_settings_import, export_system_settings_payload
        self.save_step(True)
        payload = export_system_settings_payload(self.record)
        self.assertTrue(payload['settings']['extra_config']['entry_clipboard']['enabled'])
        self.save_step(False)
        apply_system_settings_import(self.record, payload)
        self.record.refresh_from_db()
        self.assertTrue(self.record.extra_config['entry_clipboard']['enabled'])
        self.save_step(False)
        upload = SimpleUploadedFile('config.json', json.dumps(payload).encode(), content_type='application/json')
        form = SystemSettingsForm(data={**BASE, 'default_table_density': 'balanced'}, files={'settings_import_file': upload}, instance=self.record, mode='setup')
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.record.refresh_from_db()
        self.assertTrue(self.record.extra_config['entry_clipboard']['enabled'])


class EntryClipboardNormalizationTests(TestCase):
    def test_import_aliases_normalize_the_persisted_boolean(self):
        from dlux.utils.import_export import normalize_system_settings_import_payload
        for alias in ['extra_config', 'extra', 'custom']:
            with self.subTest(alias=alias):
                payload = normalize_system_settings_import_payload({alias: {'entry_clipboard': {'enabled': 'false'}}})
                self.assertIs(payload['extra_config']['entry_clipboard']['enabled'], False)

    def test_legacy_boolean_inputs_and_malformed_sections(self):
        from dlux.system.normalizers import normalize_extra_config
        for raw, expected in [('true', True), ('on', True), ('false', False), ('off', False), (1, True), (0, False)]:
            with self.subTest(raw=raw):
                config = normalize_extra_config({'entry_clipboard': {'enabled': raw, 'keep': 7}, 'app': {'crm': {'keep': True}}})
                self.assertIs(config['entry_clipboard']['enabled'], expected)
                self.assertEqual(config['entry_clipboard']['keep'], 7)
                self.assertTrue(config['app']['crm']['keep'])
        self.assertEqual(normalize_extra_config({'entry_clipboard': 'invalid'})['entry_clipboard'], {'enabled': False})

    def test_absent_clipboard_does_not_seed_the_extra_group(self):
        from dlux.system.defaults import default_extra_config
        from dlux.system.normalizers import normalize_extra_config
        self.assertEqual(default_extra_config(), {})
        self.assertEqual(normalize_extra_config({'app': {'crm': {'keep': True}}}), {'app': {'crm': {'keep': True}}})
