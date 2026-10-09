"""`manage.py dlux_backup`: the snapshot Composer takes before a CLI update."""

import json
import shutil
import tempfile
from io import StringIO

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from unittest import mock

from django.apps import apps
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings


class BackupCommandTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media_root, True)
        self.SystemBackup = apps.get_model('dlux', 'SystemBackup')

    def _run(self, *args):
        out = StringIO()
        with override_settings(MEDIA_ROOT=self.media_root):
            call_command('dlux_backup', *args, stdout=out)
        return json.loads(out.getvalue().strip().splitlines()[-1])

    def test_takes_an_update_backup_and_reports_it(self):
        result = self._run('--trigger', 'update', '--requested-by', 'operator')
        row = self.SystemBackup.objects.get(token=result['token'])
        self.assertTrue(result['ok'])
        self.assertEqual((row.status, row.trigger, row.media_included), ('completed', 'update', False))
        self.assertEqual(row.requested_by_username, 'operator')
        self.assertEqual(result['rows'], row.row_count)
        self.assertTrue(result['path'])

    def test_full_scope_includes_media(self):
        result = self._run('--scope', 'full')
        self.assertTrue(self.SystemBackup.objects.get(token=result['token']).media_included)

    def test_a_failure_exits_non_zero_and_arms_no_retry(self):
        with mock.patch('dlux.backup.create.write_system_backup', side_effect=RuntimeError('disk full')), \
                mock.patch('dlux.backup.retry.system_backup_celery_available', return_value=True):
            with self.assertRaises(CommandError):
                self._run('--trigger', 'update')
        row = self.SystemBackup.objects.get()
        self.assertNotEqual(row.status, 'pending')
        self.assertIsNone(row.next_attempt_at)
