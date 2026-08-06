import json
import os
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.core.management.base import CommandError
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


class FakeAppConfig:
    """Stands in for an AppConfig; only .name/.label/.path are read."""

    def __init__(self, name, path, models=()):
        self.name = name
        self.label = name
        self.path = str(path)
        self._models = list(models)

    def get_models(self):
        return self._models


def _app(tmpdir, name, *, initial=False, extra=None):
    """Build an app tree, optionally with a 0001_* migration already present."""
    app_path = Path(tmpdir) / name
    migrations = app_path / 'migrations'
    migrations.mkdir(parents=True)
    (migrations / '__init__.py').write_text('')
    if initial:
        (migrations / '0001_initial.py').write_text('')
    if extra:
        (migrations / extra).write_text('')
    return FakeAppConfig(name, app_path)


class MigratorSchemaSelectionTests(TestCase):
    """The contract: -mm forces every app, bare picks only apps with no 0001_*."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _run_schema(self, apps, force_mm):
        command = Command(stdout=StringIO(), stderr=StringIO())
        with mock.patch('dlux.management.commands.migrator.call_command') as called:
            command.run_schema(apps, force_mm)
        return called

    def test_bare_run_only_targets_apps_without_an_initial_migration(self):
        migrated = _app(self.tmp.name, 'shop', initial=True)
        fresh = _app(self.tmp.name, 'blog')

        called = self._run_schema([migrated, fresh], force_mm=False)

        self.assertEqual(
            called.call_args_list[0],
            mock.call('makemigrations', 'blog', '--noinput'),
        )
        self.assertEqual(called.call_args_list[1], mock.call('migrate', '--noinput'))

    def test_a_stray_module_does_not_count_as_an_initial_migration(self):
        # The old check accepted any *.py that was not __init__, so a helper left
        # in migrations/ made an unmigrated app look migrated.
        stray = _app(self.tmp.name, 'blog', extra='helpers.py')

        called = self._run_schema([stray], force_mm=False)

        self.assertEqual(
            called.call_args_list[0],
            mock.call('makemigrations', 'blog', '--noinput'),
        )

    def test_mm_forces_every_app_in_a_single_makemigrations_call(self):
        migrated = _app(self.tmp.name, 'shop', initial=True)
        fresh = _app(self.tmp.name, 'blog')

        called = self._run_schema([migrated, fresh], force_mm=True)

        # One call for the whole set: per-app calls resolve cross-app
        # dependencies against a half-written migration graph.
        self.assertEqual(
            called.call_args_list[0],
            mock.call('makemigrations', 'shop', 'blog', '--noinput'),
        )
        self.assertEqual(len(called.call_args_list), 2)

    def test_migrate_runs_even_when_nothing_needs_makemigrations(self):
        migrated = _app(self.tmp.name, 'shop', initial=True)

        called = self._run_schema([migrated], force_mm=False)

        self.assertEqual(called.call_args_list, [mock.call('migrate', '--noinput')])

    def test_an_unwritable_migrations_dir_is_refused_before_django_runs(self):
        fresh = _app(self.tmp.name, 'blog')
        migrations = Path(fresh.path) / 'migrations'
        os.chmod(migrations, 0o500)
        self.addCleanup(os.chmod, migrations, 0o700)

        command = Command(stdout=StringIO(), stderr=StringIO())
        with mock.patch('dlux.management.commands.migrator.call_command') as called:
            with self.assertRaises(CommandError) as ctx:
                command.run_schema([fresh], force_mm=True)

        self.assertIn('not writable', str(ctx.exception))
        called.assert_not_called()


class MigratorFlagContractTests(TestCase):
    """-mm/-nm reach the right phases; collectstatic is unconditional."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = _app(self.tmp.name, 'blog', initial=True)

    def _call(self, **options):
        command = Command(stdout=StringIO(), stderr=StringIO())
        with mock.patch.object(command, 'resolve_target_apps', return_value=[self.app]), \
             mock.patch.object(command, 'run_schema') as schema, \
             mock.patch.object(command, 'run_collectstatic') as static, \
             mock.patch.object(command, 'bootstrap_system_settings'), \
             mock.patch.object(command, 'ensure_superuser'), \
             mock.patch.object(command, 'run_populate'), \
             mock.patch('dlux.management.commands.migrator.call_command'):
            command.handle(
                app=options.get('app'),
                make_migrations=options.get('make_migrations', False),
                no_migrate=options.get('no_migrate', False),
            )
        return schema, static

    def test_bare_run_does_schema_work_and_collects_static(self):
        schema, static = self._call()
        schema.assert_called_once_with([self.app], False)
        static.assert_called_once_with()

    def test_mm_forces_makemigrations_and_still_collects_static(self):
        schema, static = self._call(make_migrations=True)
        schema.assert_called_once_with([self.app], True)
        static.assert_called_once_with()

    def test_nm_skips_schema_work_but_still_collects_static(self):
        schema, static = self._call(no_migrate=True)
        schema.assert_not_called()
        static.assert_called_once_with()

    def test_mm_and_nm_together_are_refused(self):
        command = Command(stdout=StringIO(), stderr=StringIO())
        with self.assertRaises(CommandError) as ctx:
            command.handle(app=None, make_migrations=True, no_migrate=True)
        self.assertIn('mutually exclusive', str(ctx.exception))


class MigratorFailureBoundaryTests(TestCase):
    """Unrelated setup steps must not take a deploy down with them."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = _app(self.tmp.name, 'blog', initial=True)

    def _command(self):
        command = Command(stdout=StringIO(), stderr=StringIO())
        command._stdout = command.stdout
        return command

    def test_a_failing_populate_warns_instead_of_failing_the_run(self):
        command = self._command()
        warnings = []
        with mock.patch('dlux.management.commands.migrator.get_commands',
                        return_value={'populate': 'app'}), \
             mock.patch('dlux.management.commands.migrator.call_command',
                        side_effect=RuntimeError('boom')):
            command.run_populate([], warnings)
        self.assertEqual(len(warnings), 1)
        self.assertIn('populate failed', warnings[0])

    def test_a_failing_superuser_creation_warns_instead_of_failing_the_run(self):
        command = self._command()
        warnings = []
        with mock.patch('dlux.management.commands.migrator.get_user_model',
                        side_effect=RuntimeError('no user model')):
            command.ensure_superuser(warnings)
        self.assertEqual(len(warnings), 1)
        self.assertIn('superuser creation failed', warnings[0])

    def test_dlux_setup_failure_is_fatal(self):
        command = Command(stdout=StringIO(), stderr=StringIO())
        with mock.patch.object(command, 'resolve_target_apps', return_value=[self.app]), \
             mock.patch.object(command, 'run_schema'), \
             mock.patch.object(command, 'run_collectstatic'), \
             mock.patch.object(command, 'bootstrap_system_settings'), \
             mock.patch.object(command, 'ensure_superuser'), \
             mock.patch.object(command, 'run_populate'), \
             mock.patch('dlux.management.commands.migrator.call_command',
                        side_effect=RuntimeError('dlux_setup exploded')):
            with self.assertRaises(RuntimeError):
                command.handle(app=None, make_migrations=False, no_migrate=False)

    def test_an_unknown_target_app_is_refused(self):
        command = Command(stdout=StringIO(), stderr=StringIO())
        with self.assertRaises(CommandError):
            command.resolve_target_apps('definitely_not_an_app')
