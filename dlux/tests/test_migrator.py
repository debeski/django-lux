import json
import tempfile
from io import StringIO
from pathlib import Path

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.test import TestCase, override_settings

from dlux.management.commands.migrator import Command
from dlux.models import SystemSettings
from dlux.utils import (
    SYSTEM_SETTINGS_CONFIG_BOOTSTRAP_APPLIED,
    SYSTEM_SETTINGS_CONFIG_BOOTSTRAP_CONFIGURED,
    SYSTEM_SETTINGS_CONFIG_BOOTSTRAP_MISSING,
)


class MigratorConfigBootstrapTests(TestCase):
    def setUp(self):
        self.settings_obj = SystemSettings.load()
        self.settings_obj.is_configured = False
        self.settings_obj.system_names = {}
        self.settings_obj.home_url = '/accounts/profile/'
        self.settings_obj.save()

    def run_bootstrap(self, base_dir):
        stdout = StringIO()
        with override_settings(BASE_DIR=Path(base_dir)):
            status = Command(stdout=stdout).bootstrap_system_settings()
        return status, stdout.getvalue()

    def test_bootstrap_applies_config_before_web_setup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / 'config.json'
            config_path.write_text(json.dumps({
                'format': 'django-lux.system-settings',
                'version': 1,
                'settings': {
                    'system_names': {'en': 'Bootstrapped System'},
                    'home_url': '/ready/',
                    'default_language': 'en',
                },
            }), encoding='utf-8')

            status, output = self.run_bootstrap(tmpdir)

        self.settings_obj.refresh_from_db()
        self.assertEqual(status, SYSTEM_SETTINGS_CONFIG_BOOTSTRAP_APPLIED)
        self.assertTrue(self.settings_obj.is_configured)
        self.assertEqual(self.settings_obj.system_names, {'en': 'Bootstrapped System'})
        self.assertEqual(self.settings_obj.home_url, '/ready/')
        self.assertIn('Applied first-launch System Settings', output)

    def test_bootstrap_reports_missing_config_and_leaves_setup_available(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            status, output = self.run_bootstrap(tmpdir)

        self.settings_obj.refresh_from_db()
        self.assertEqual(status, SYSTEM_SETTINGS_CONFIG_BOOTSTRAP_MISSING)
        self.assertFalse(self.settings_obj.is_configured)
        self.assertIn('manual setup remains available', output)

    def test_bootstrap_reports_invalid_config_without_configuring(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / 'config.json').write_text('{invalid', encoding='utf-8')

            status, output = self.run_bootstrap(tmpdir)

        self.settings_obj.refresh_from_db()
        self.assertEqual(status, 'invalid')
        self.assertFalse(self.settings_obj.is_configured)
        self.assertIn('Invalid first-launch config', output)
        self.assertIn('manual setup remains available', output.lower())

    def test_bootstrap_ignores_file_after_system_is_configured(self):
        self.settings_obj.is_configured = True
        self.settings_obj.system_names = {'en': 'Existing'}
        self.settings_obj.save()

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / 'config.json').write_text('{invalid', encoding='utf-8')

            status, output = self.run_bootstrap(tmpdir)

        self.settings_obj.refresh_from_db()
        self.assertEqual(status, SYSTEM_SETTINGS_CONFIG_BOOTSTRAP_CONFIGURED)
        self.assertEqual(self.settings_obj.system_names, {'en': 'Existing'})
        self.assertIn('already configured', output)
