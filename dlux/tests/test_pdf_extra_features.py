"""PDF tools settings live in System Settings > Extra Features, not in their own Options card."""

from dlux.tests.harness import setup_test_environment
setup_test_environment()

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import RequestFactory, TestCase

import dlux.options as options
import dlux.pdf as pdf
from dlux.forms import SystemSettingsForm
from dlux.models import SystemSettings
from dlux.system.constants import SETUP_STEP_BACKUPS, SETUP_STEP_EXTRAS
from dlux.tests.test_weather import BASE

PDF_FIELDS = ('pdf_editing_enabled', 'pdf_history_enabled', 'pdf_max_pages', 'pdf_max_source_mb')


class PdfExtraFeaturesTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        registered = patch.object(pdf, '_registered', True)
        registered.start()
        self.addCleanup(registered.stop)
        self.user = get_user_model().objects.create_superuser(username='pdf-admin', password='test-password')
        self.record = SystemSettings.load()
        self.record.is_configured = True
        self.record.extra_config = {'app': {'crm': {'keep': True}, 'dlux.pdf': {'history_enabled': False, 'max_pages': 40}}}
        self.record.save()

    def save_step(self, data, step=SETUP_STEP_EXTRAS):
        request = RequestFactory().get('/?step=' + str(step))
        request.user = self.user
        form = SystemSettingsForm(data={**BASE, **data}, instance=SystemSettings.load(), request=request)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        cache.clear()
        self.record.refresh_from_db()
        return form

    def test_fields_start_from_the_stored_namespace(self):
        initial = SystemSettingsForm(instance=self.record).initial
        self.assertEqual(
            {name: initial[name] for name in PDF_FIELDS},
            {'pdf_editing_enabled': True, 'pdf_history_enabled': False, 'pdf_max_pages': 40, 'pdf_max_source_mb': 100},
        )

    def test_extra_features_save_writes_the_namespace_and_keeps_other_apps(self):
        self.save_step({'pdf_editing_enabled': '', 'pdf_history_enabled': 'on', 'pdf_max_pages': '120', 'pdf_max_source_mb': '64'})
        self.assertEqual(
            self.record.extra_config['app']['dlux.pdf'],
            {'editing_enabled': False, 'history_enabled': True, 'max_pages': 120, 'max_source_mb': 64},
        )
        self.assertTrue(self.record.extra_config['app']['crm']['keep'])
        self.assertEqual(pdf.get_pdf_features(), {'editing_enabled': False, 'history_enabled': True, 'max_pages': 120, 'max_source_mb': 64})

    def test_another_step_leaves_pdf_settings_alone(self):
        form = self.save_step({'pdf_editing_enabled': '', 'pdf_max_pages': '9'}, step=SETUP_STEP_BACKUPS)
        self.assertTrue(all(form.fields[name].disabled for name in PDF_FIELDS))
        self.assertEqual(self.record.extra_config['app']['dlux.pdf'], {'history_enabled': False, 'max_pages': 40})

    def test_limits_are_bounded(self):
        request = RequestFactory().get('/?step=' + str(SETUP_STEP_EXTRAS))
        request.user = self.user
        form = SystemSettingsForm(data={**BASE, 'pdf_max_pages': '5001', 'pdf_max_source_mb': '0'}, instance=self.record, request=request)
        self.assertFalse(form.is_valid())
        self.assertIn('pdf_max_pages', form.errors)
        self.assertIn('pdf_max_source_mb', form.errors)

    def test_extra_features_step_renders_the_section(self):
        from crispy_forms.utils import render_crispy_form

        request = RequestFactory().get('/?step=' + str(SETUP_STEP_EXTRAS))
        request.user = self.user
        form = SystemSettingsForm(instance=self.record, request=request)
        names = {pointer.name for pointer in form.helper.layout.get_field_names()}
        self.assertTrue({'pdf_max_pages', 'pdf_max_source_mb'} <= names)
        html = render_crispy_form(form)
        self.assertIn("name='pdf_editing_enabled'", html)
        self.assertIn("name='pdf_history_enabled'", html)

    def test_unregistered_projects_get_no_pdf_fields(self):
        with patch.object(pdf, '_registered', False):
            form = SystemSettingsForm(instance=self.record)
        self.assertFalse(set(PDF_FIELDS) & set(form.fields))

    def test_register_pdf_options_adds_no_options_card(self):
        before = set(options._SETTINGS_REGISTRY)
        pdf.register_pdf_options()
        self.assertNotIn(pdf.NAMESPACE, set(options._SETTINGS_REGISTRY) - before)
        self.assertNotIn(pdf.NAMESPACE, options._SETTINGS_REGISTRY)
        self.assertTrue(pdf.pdf_tools_registered())
