"""Backup options: encryption modes, portable scope, cancel, busy guard, speed."""

import io
import json
import threading
import zipfile
from unittest import skipUnless

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from unittest import mock

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from dlux.backup import (
    SYSTEM_DATA_MODELS,
    BackupCancelled,
    DlbPayloadWriter,
    cancel_system_backup,
    decrypt_dlb_to_tempfile,
    get_system_backup_models,
    read_dlb_metadata,
    run_system_backup,
    run_system_restore,
    write_system_backup,
)

User = get_user_model()


def _zip_from(buffer, passphrase=None):
    buffer.seek(0)
    _meta, tmp = decrypt_dlb_to_tempfile(buffer, passphrase=passphrase)
    return zipfile.ZipFile(tmp)


class EncryptionModeTests(TestCase):
    def test_unencrypted_container_round_trips_and_says_so(self):
        User.objects.create_user('plain', 'p@example.com', 'plainpass1')
        buffer = io.BytesIO()
        metadata, _manifest = write_system_backup(buffer, encrypt=False)
        self.assertEqual(metadata['encryption']['scheme'], 'none')
        self.assertFalse(metadata['passphrase_required'])
        buffer.seek(0)
        self.assertEqual(read_dlb_metadata(buffer)['encryption']['scheme'], 'none')
        # The payload after the header is the ZIP itself, readable as-is.
        buffer.seek(0)
        read_dlb_metadata(buffer)
        self.assertTrue(zipfile.is_zipfile(io.BytesIO(buffer.read())))
        with _zip_from(buffer) as zf:
            users = json.loads(zf.read('data/auth/user.json'))
        self.assertIn('plain', {item['fields']['username'] for item in users})

    def test_streaming_writer_spans_many_frames(self):
        payload = bytes(range(256)) * 4096  # 1 MiB
        for encrypt in (True, False):
            writer = DlbPayloadWriter(encrypt=encrypt, chunk_size=64 * 1024)
            for start in range(0, len(payload), 10_000):
                writer.write(payload[start:start + 10_000])
            dest = io.BytesIO()
            writer.finish(dest, {})
            dest.seek(0)
            _meta, tmp = decrypt_dlb_to_tempfile(dest)
            self.assertEqual(tmp.read(), payload)
            tmp.close()

    def test_wrong_passphrase_says_so(self):
        buffer = io.BytesIO()
        write_system_backup(buffer, passphrase='right-pass', include_media=False)
        buffer.seek(0)
        with self.assertRaisesRegex(ValueError, 'Wrong passphrase'):
            decrypt_dlb_to_tempfile(buffer, passphrase='wrong-pass')

    def test_passphrase_row_without_passphrase_fails_instead_of_using_server_key(self):
        SystemBackup = apps.get_model('dlux', 'SystemBackup')
        backup = SystemBackup.objects.create(
            requested_by_username='x', encryption=SystemBackup.ENCRYPTION_PASSPHRASE,
        )
        run_system_backup(backup.pk)
        backup.refresh_from_db()
        self.assertEqual(backup.status, SystemBackup.STATUS_FAILED)
        self.assertFalse(backup.file_path)


class PortableScopeTests(TestCase):
    def test_portable_backup_leaves_system_data_out(self):
        exported = {model._meta.label_lower for model in get_system_backup_models(include_system_data=False)}
        self.assertIn('auth.user', exported)
        self.assertIn('dlux.managedasset', exported)
        self.assertFalse(exported & SYSTEM_DATA_MODELS)

    def test_system_model_still_referenced_by_a_kept_model_is_kept(self):
        from dlux.backup.config import _system_data_exclusions

        Profile = apps.get_model('dlux', 'Profile')

        class _Referrer:
            class _meta:
                label_lower = 'project.referrer'
                concrete_fields = []
                many_to_many = []

        field = mock.Mock(is_relation=True, related_model=Profile, null=True)
        _Referrer._meta.concrete_fields = [field]
        dropped = _system_data_exclusions([Profile, _Referrer])
        self.assertNotIn(Profile, dropped)

    def test_portable_restore_keeps_target_system_data_and_drops_dangling_rows(self):
        ActivityLog = apps.get_model('dlux', 'ActivityLog')
        SystemBackup = apps.get_model('dlux', 'SystemBackup')
        SystemRestore = apps.get_model('dlux', 'SystemRestore')
        keeper = User.objects.create_user('keeper', 'k@example.com', 'keeperpass1')
        backup = SystemBackup.objects.create(requested_by_username='x', system_data_included=False)
        run_system_backup(backup.pk)
        backup.refresh_from_db()
        self.assertEqual(backup.status, SystemBackup.STATUS_COMPLETED)

        # After the snapshot: a user the backup does not know, with a profile
        # and a log entry, plus a log entry by a user it does know.
        ghost = User.objects.create_user('ghost', 'g@example.com', 'ghostpass1')
        ActivityLog.objects.create(created_by=ghost, action='CREATE', model_name='Thing')
        ActivityLog.objects.create(created_by=keeper, action='UPDATE', model_name='Thing')

        restore = SystemRestore.objects.create(requested_by_username='x', backup_file_path=backup.file_path)
        run_system_restore(restore.pk)
        restore.refresh_from_db()
        self.assertEqual(restore.status, SystemRestore.STATUS_COMPLETED, restore.error)
        self.assertFalse(User.objects.filter(username='ghost').exists())
        Profile = apps.get_model('dlux', 'Profile')
        self.assertFalse(Profile.objects.filter(user_id=ghost.pk).exists())
        # System data the backup did not carry is kept, minus what dangled.
        actions = set(ActivityLog.objects.filter(model_name='Thing').values_list('action', 'created_by_id'))
        self.assertIn(('UPDATE', keeper.pk), actions)
        self.assertNotIn(('CREATE', ghost.pk), actions)


class CancelTests(TestCase):
    def setUp(self):
        self.SystemBackup = apps.get_model('dlux', 'SystemBackup')

    def test_cancelled_pending_backup_is_never_built(self):
        backup = self.SystemBackup.objects.create(requested_by_username='x')
        self.assertTrue(cancel_system_backup(backup))
        run_system_backup(backup.pk)
        backup.refresh_from_db()
        self.assertEqual(backup.status, self.SystemBackup.STATUS_CANCELLED)
        self.assertEqual(backup.attempt_count, 0)

    def test_running_backup_stops_at_its_next_progress_write(self):
        backup = self.SystemBackup.objects.create(requested_by_username='x')
        real_write = write_system_backup

        def cancel_midway(dest, **kwargs):
            self.SystemBackup.objects.filter(pk=backup.pk).update(status=self.SystemBackup.STATUS_CANCELLED)
            return real_write(dest, **kwargs)

        with mock.patch('dlux.backup.create.write_system_backup', side_effect=cancel_midway):
            run_system_backup(backup.pk)
        backup.refresh_from_db()
        self.assertEqual(backup.status, self.SystemBackup.STATUS_CANCELLED)
        self.assertFalse(backup.file_path)
        self.assertFalse(backup.error)

    def test_cancel_landing_while_storing_removes_the_file(self):
        backup = self.SystemBackup.objects.create(requested_by_username='x')
        saved = []
        from django.core.files.storage import default_storage
        real_save = default_storage.save

        def save_then_cancel(name, content, **kwargs):
            path = real_save(name, content, **kwargs)
            saved.append(path)
            self.SystemBackup.objects.filter(pk=backup.pk).update(status=self.SystemBackup.STATUS_CANCELLED)
            return path

        with mock.patch('dlux.backup.create.default_storage.save', side_effect=save_then_cancel):
            run_system_backup(backup.pk)
        backup.refresh_from_db()
        self.assertEqual(backup.status, self.SystemBackup.STATUS_CANCELLED)
        self.assertTrue(saved)
        self.assertFalse(default_storage.exists(saved[0]))

    def test_reporter_raises_once_the_row_is_no_longer_running(self):
        from dlux.backup import _BackupReporter

        backup = self.SystemBackup.objects.create(requested_by_username='x', status='running')
        reporter = _BackupReporter(backup)
        reporter.checkpoint(10, 'working')
        self.SystemBackup.objects.filter(pk=backup.pk).update(status='cancelled')
        with self.assertRaises(BackupCancelled):
            reporter.checkpoint(20, 'still working')

    def test_finished_backup_cannot_be_cancelled(self):
        backup = self.SystemBackup.objects.create(requested_by_username='x', status='completed')
        self.assertFalse(cancel_system_backup(backup))


class BackupPageOptionTests(TestCase):
    def setUp(self):
        SystemSettings = apps.get_model('dlux', 'SystemSettings')
        settings_obj = SystemSettings.load()
        settings_obj.is_configured = True
        settings_obj.save(update_fields=['is_configured'])
        User.objects.create_superuser('boss', 'boss@example.com', 'bosspass123')
        self.client = Client()
        self.client.login(username='boss', password='bosspass123')
        self.SystemBackup = apps.get_model('dlux', 'SystemBackup')

    def _create(self, data):
        with mock.patch('dlux.views.backup.dispatch_system_backup', return_value=True):
            return self.client.post(reverse('system_backup_create'), data)

    def test_create_stores_encryption_and_scope(self):
        response = self._create({'backup_encryption': 'none', 'include_system_data': ['0']})
        self.assertEqual(response.status_code, 200)
        row = self.SystemBackup.objects.get()
        self.assertEqual(row.encryption, 'none')
        self.assertFalse(row.system_data_included)
        self.assertFalse(row.passphrase_required)

    def test_checked_switch_and_legacy_clients_keep_system_data(self):
        self._create({'include_system_data': ['0', '1']})
        self.SystemBackup.objects.update(status='completed')
        self._create({})
        self.assertEqual(
            list(self.SystemBackup.objects.order_by('pk').values_list('system_data_included', 'encryption')),
            [(True, 'server_key'), (True, 'server_key')],
        )

    def test_passphrase_mode_requires_a_passphrase(self):
        response = self._create({'backup_encryption': 'passphrase'})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.SystemBackup.objects.exists())

    def test_second_backup_is_refused_while_one_runs(self):
        self.SystemBackup.objects.create(requested_by_username='boss', status='running')
        response = self._create({})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.SystemBackup.objects.count(), 1)
        page = self.client.get(reverse('system_backup_page')).content.decode()
        self.assertIn('id="sysbackup-create-fields" class="dlux-backup-create-form" disabled', page)
        self.assertIn('data-busy="1"', page)

    def test_running_row_offers_cancel_not_delete(self):
        running = self.SystemBackup.objects.create(requested_by_username='boss', status='running')
        html = self.client.get(reverse('system_backup_list_status')).json()['html']
        self.assertIn(reverse('system_backup_cancel', args=[running.token]), html)
        self.assertNotIn(reverse('system_backup_delete', args=[running.token]), html)
        response = self.client.post(
            reverse('system_backup_cancel', args=[running.token]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertTrue(response.json()['ok'])
        running.refresh_from_db()
        self.assertEqual(running.status, 'cancelled')

    def test_running_row_cannot_be_deleted(self):
        running = self.SystemBackup.objects.create(requested_by_username='boss', status='running')
        self.client.post(reverse('system_backup_delete', args=[running.token]))
        self.assertTrue(self.SystemBackup.objects.filter(pk=running.pk).exists())

    def test_status_carries_console_log_and_timing(self):
        backup = self.SystemBackup.objects.create(requested_by_username='boss')
        run_system_backup(backup.pk)
        payload = self.client.get(reverse('system_backup_status', args=[backup.token])).json()
        self.assertEqual(payload['status'], 'completed')
        self.assertGreater(len(payload['log']), 2)
        self.assertEqual(payload['log'][-1]['percent'], 100)
        self.assertIsNotNone(payload['elapsed_seconds'])
        self.assertFalse(payload['active'])


class SerializationQueryTests(TestCase):
    def test_natural_key_lookups_do_not_scale_with_rows(self):
        """Each FK to a user used to cost one query per serialized row."""
        ActivityLog = apps.get_model('dlux', 'ActivityLog')
        users = [User.objects.create_user(f'u{i}', password='x') for i in range(3)]

        def queries_for(rows):
            ActivityLog.objects.all().delete()
            ActivityLog.objects.bulk_create([
                ActivityLog(created_by=users[i % 3], action='CREATE', model_name='X') for i in range(rows)
            ])
            with CaptureQueriesContext(connection) as ctx:
                write_system_backup(io.BytesIO(), include_media=False)
            return len(ctx.captured_queries)

        self.assertEqual(queries_for(50), queries_for(400))


@skipUnless(connection.vendor == 'postgresql', 'snapshot reads need PostgreSQL')
class SnapshotConsistencyTests(TransactionTestCase):
    def test_rows_written_during_a_backup_are_not_in_it(self):
        SystemBackup = apps.get_model('dlux', 'SystemBackup')
        User.objects.create_user('before', password='x')
        backup = SystemBackup.objects.create(requested_by_username='x')
        from dlux.utils.archive import build_relation_schema as real_schema

        def write_meanwhile(models_list, **kwargs):
            # By now the snapshot is fixed (migration state was already read).
            def writer():
                User.objects.create_user('during', password='x')
                connection.close()

            thread = threading.Thread(target=writer)
            thread.start()
            thread.join()
            return real_schema(models_list, **kwargs)

        with mock.patch('dlux.backup.create.build_relation_schema', side_effect=write_meanwhile):
            run_system_backup(backup.pk)
        backup.refresh_from_db()
        self.assertEqual(backup.status, SystemBackup.STATUS_COMPLETED, backup.error)
        self.assertTrue(User.objects.filter(username='during').exists())
        from django.core.files.storage import default_storage
        with default_storage.open(backup.file_path, 'rb') as fh:
            buffer = io.BytesIO(fh.read())
        with _zip_from(buffer) as zf:
            manifest = json.loads(zf.read('manifest.json'))
            usernames = {item['fields']['username'] for item in json.loads(zf.read('data/auth/user.json'))}
        self.assertEqual(manifest['consistency'], 'snapshot')
        self.assertIn('before', usernames)
        self.assertNotIn('during', usernames)
        # Progress was written from the reporter thread while reads were frozen.
        self.assertGreater(len(backup.progress_log), 2)

    def test_cancel_reaches_a_snapshot_backup(self):
        SystemBackup = apps.get_model('dlux', 'SystemBackup')
        backup = SystemBackup.objects.create(requested_by_username='x')
        from dlux.utils.archive import build_relation_schema as real_schema

        def cancel_meanwhile(models_list, **kwargs):
            def canceller():
                SystemBackup.objects.filter(pk=backup.pk).update(status=SystemBackup.STATUS_CANCELLED)
                connection.close()

            thread = threading.Thread(target=canceller)
            thread.start()
            thread.join()
            return real_schema(models_list, **kwargs)

        with mock.patch('dlux.backup.create.build_relation_schema', side_effect=cancel_meanwhile):
            run_system_backup(backup.pk)
        backup.refresh_from_db()
        self.assertEqual(backup.status, SystemBackup.STATUS_CANCELLED)
        self.assertFalse(backup.file_path)
