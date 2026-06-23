import io
import json
import zipfile

from dlux.tests.harness import setup_test_environment

setup_test_environment()

import tempfile
from unittest import mock

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db.models.query import QuerySet
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from dlux.backup import (
    decrypt_dlb_to_tempfile,
    read_dlb_metadata,
    run_system_backup,
    run_system_restore,
    write_system_backup,
)

User = get_user_model()


def _tiny_png():
    from PIL import Image

    stream = io.BytesIO()
    Image.new('RGB', (1, 1), 'red').save(stream, format='PNG')
    return stream.getvalue()


class DlbContainerTests(TestCase):
    def test_container_round_trip(self):
        admin = User.objects.create_superuser('dlb-admin', 'a@example.com', 'pass12345')
        original_hash = admin.password
        buffer = io.BytesIO()
        metadata, manifest = write_system_backup(buffer)
        self.assertEqual(metadata['kind'], 'dlux-system-backup')
        self.assertGreater(metadata['rows'], 0)

        buffer.seek(0)
        header_meta = read_dlb_metadata(buffer)
        self.assertEqual(header_meta['rows'], metadata['rows'])
        self.assertTrue(header_meta['encryption']['salt'])

        read_meta, zip_tmp = decrypt_dlb_to_tempfile(buffer)
        try:
            with zipfile.ZipFile(zip_tmp) as zf:
                inner = json.loads(zf.read('manifest.json'))
                self.assertEqual(inner['kind'], 'dlux-system-backup')
                self.assertTrue(inner['migration_state'])
                model_keys = {item['model'] for item in inner['models']}
                self.assertIn('auth.user', {key.lower() for key in model_keys})
                self.assertNotIn('dlux.systembackup', {key.lower() for key in model_keys})
                users = json.loads(zf.read('data/auth/user.json'))
                admin_payload = next(item for item in users if item['fields']['username'] == 'dlb-admin')
                self.assertNotEqual(admin_payload['fields']['password'], original_hash)
                self.assertTrue(admin_payload['fields']['password'].startswith('!'))
        finally:
            zip_tmp.close()

    def test_passphrase_protected_container_requires_passphrase(self):
        User.objects.create_superuser('dlb-admin', 'a@example.com', 'pass12345')
        buffer = io.BytesIO()
        metadata, _manifest = write_system_backup(buffer, passphrase='vault-pass')
        self.assertTrue(metadata['passphrase_required'])
        self.assertEqual(metadata['encryption']['key_source'], 'passphrase')

        buffer.seek(0)
        with self.assertRaises(ValueError):
            decrypt_dlb_to_tempfile(buffer)

        buffer.seek(0)
        with self.assertRaises(Exception):
            decrypt_dlb_to_tempfile(buffer, passphrase='wrong-pass')

        buffer.seek(0)
        read_meta, zip_tmp = decrypt_dlb_to_tempfile(buffer, passphrase='vault-pass')
        try:
            self.assertTrue(read_meta['passphrase_required'])
            with zipfile.ZipFile(zip_tmp) as zf:
                inner = json.loads(zf.read('manifest.json'))
            self.assertEqual(inner['kind'], 'dlux-system-backup')
        finally:
            zip_tmp.close()

    def test_rejects_non_dlb_file(self):
        with self.assertRaises(ValueError):
            read_dlb_metadata(io.BytesIO(b'PK\x03\x04 definitely a zip'))

    def test_models_are_dependency_ordered(self):
        """Natural-key FK targets must load before their referrers regardless of
        INSTALLED_APPS order (regression: Profile loaded before User NULLed the
        deferred user_id on hosts that list dlux before django.contrib.auth)."""
        from dlux.backup import get_system_backup_models

        ordered = get_system_backup_models()
        index = {model._meta.label_lower: i for i, model in enumerate(ordered)}
        self.assertLess(index['auth.user'], index['dlux.profile'])
        self.assertLess(index['auth.group'], index['auth.user'])
        self.assertLess(index['dlux.scope'], index['dlux.profile'])
        self.assertNotIn('dlux.dluxupdatestate', index)
        self.assertNotIn('dlux.dluxupdaterun', index)

    def test_system_backup_does_not_require_queryset_iterator(self):
        """Regression: PostgreSQL server-side cursors can disappear in pooled deployments."""
        User.objects.create_superuser('dlb-admin', 'a@example.com', 'pass12345')
        buffer = io.BytesIO()
        with mock.patch.object(QuerySet, 'iterator', side_effect=AssertionError('named cursor disabled')):
            metadata, manifest = write_system_backup(buffer)
        self.assertGreater(metadata['rows'], 0)
        self.assertTrue(manifest['models'])


class SystemRestoreRoundTripTests(TestCase):
    def test_full_backup_and_restore_replaces_everything(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                admin = User.objects.create_superuser('root', 'root@example.com', 'rootpass123')
                original_hash = admin.password
                worker = User.objects.create_user('worker', 'w@example.com', 'workerpass1', is_staff=True)
                worker_hash = worker.password
                worker.profile.profile_picture.save('pic.png', ContentFile(_tiny_png()), save=True)
                picture_name = worker.profile.profile_picture.name
                ActivityLog = apps.get_model('dlux', 'ActivityLog')
                ActivityLog.objects.create(created_by=worker, action='CREATE', model_name='Thing')

                SystemBackup = apps.get_model('dlux', 'SystemBackup')
                backup = SystemBackup.objects.create(requested_by_username='root')
                run_system_backup(backup.pk)
                backup.refresh_from_db()
                self.assertEqual(backup.status, SystemBackup.STATUS_COMPLETED)
                self.assertTrue(default_storage.exists(backup.file_path))

                # Mutate the world after the snapshot.
                admin.set_password('changed-pass-9')
                admin.save()
                User.objects.create_user('intruder', 'i@example.com', 'intruderpass')
                ActivityLog.objects.all().delete()
                default_storage.delete(picture_name)
                worker.delete()

                SystemRestore = apps.get_model('dlux', 'SystemRestore')
                restore = SystemRestore.objects.create(
                    requested_by_username='root',
                    backup_file_path=backup.file_path,
                )
                run_system_restore(restore.pk)
                restore.refresh_from_db()
                self.assertEqual(restore.status, SystemRestore.STATUS_COMPLETED, restore.error)
                self.assertGreater(restore.report.get('restored_rows', 0), 0)

                # Snapshot state is back, but the target superuser password is
                # preserved because superuser hashes are omitted from .dlb files.
                restored_admin = User.objects.get(username='root')
                self.assertNotEqual(restored_admin.password, original_hash)
                self.assertTrue(restored_admin.check_password('changed-pass-9'))
                self.assertFalse(User.objects.filter(username='intruder').exists())
                restored_worker = User.objects.get(username='worker')
                self.assertEqual(restored_worker.password, worker_hash)
                self.assertTrue(restored_worker.check_password('workerpass1'))
                self.assertEqual(restored_worker.profile.profile_picture.name, picture_name)
                self.assertTrue(default_storage.exists(picture_name))
                self.assertEqual(ActivityLog.objects.filter(action='CREATE', model_name='Thing').count(), 1)

    def test_restore_blocks_on_migration_mismatch(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                User.objects.create_superuser('root', 'root@example.com', 'rootpass123')
                SystemBackup = apps.get_model('dlux', 'SystemBackup')
                backup = SystemBackup.objects.create(requested_by_username='root')
                run_system_backup(backup.pk)
                backup.refresh_from_db()

                SystemRestore = apps.get_model('dlux', 'SystemRestore')
                restore = SystemRestore.objects.create(
                    requested_by_username='root',
                    backup_file_path=backup.file_path,
                )
                with mock.patch(
                    'dlux.backup.get_current_migration_state',
                    return_value=['fakeapp.0001_initial'],
                ):
                    run_system_restore(restore.pk)
                restore.refresh_from_db()
                self.assertEqual(restore.status, SystemRestore.STATUS_FAILED)
                self.assertFalse(restore.report['migrations']['match'])
                # The data was left untouched.
                self.assertTrue(User.objects.filter(username='root').exists())

                forced = SystemRestore.objects.create(
                    requested_by_username='root',
                    backup_file_path=backup.file_path,
                    ignore_version_mismatch=True,
                )
                with mock.patch(
                    'dlux.backup.get_current_migration_state',
                    return_value=['fakeapp.0001_initial'],
                ):
                    run_system_restore(forced.pk)
                forced.refresh_from_db()
                self.assertEqual(forced.status, SystemRestore.STATUS_COMPLETED, forced.error)


class SystemBackupViewTests(TestCase):
    def setUp(self):
        SystemSettings = apps.get_model('dlux', 'SystemSettings')
        settings_obj = SystemSettings.load()
        settings_obj.is_configured = True
        settings_obj.save(update_fields=['is_configured'])
        self.superuser = User.objects.create_superuser('boss', 'boss@example.com', 'bosspass123')
        self.staff = User.objects.create_user('staffer', 's@example.com', 'staffpass123', is_staff=True)

    def test_page_requires_superuser(self):
        client = Client()
        client.login(username='staffer', password='staffpass123')
        self.assertEqual(client.get(reverse('system_backup_page')).status_code, 403)
        self.assertEqual(client.post(reverse('system_backup_create')).status_code, 403)
        self.assertEqual(client.post(reverse('system_restore_start')).status_code, 403)

    def test_superuser_page_renders(self):
        client = Client()
        client.login(username='boss', password='bosspass123')
        response = client.get(reverse('system_backup_page'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'sysbackup-create-btn')
        self.assertContains(response, 'data-autoclose="false"')

    def test_restore_requires_password_and_confirmation(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                client = Client()
                client.login(username='boss', password='bosspass123')
                SystemBackup = apps.get_model('dlux', 'SystemBackup')
                backup = SystemBackup.objects.create(requested_by_username='boss')
                run_system_backup(backup.pk)
                backup.refresh_from_db()

                SystemRestore = apps.get_model('dlux', 'SystemRestore')
                # Wrong password → bounced, nothing created.
                client.post(reverse('system_restore_start'), {
                    'backup_token': backup.token,
                    'current_password': 'wrong',
                    'confirm_replace': 'yes',
                })
                self.assertEqual(SystemRestore.objects.count(), 0)
                # Missing confirmation checkbox → bounced.
                client.post(reverse('system_restore_start'), {
                    'backup_token': backup.token,
                    'current_password': 'bosspass123',
                })
                self.assertEqual(SystemRestore.objects.count(), 0)
                # Proper request runs (inline, no celery in tests).
                client.post(reverse('system_restore_start'), {
                    'backup_token': backup.token,
                    'current_password': 'bosspass123',
                    'confirm_replace': 'yes',
                })
                self.assertEqual(SystemRestore.objects.count(), 1)
                restore = SystemRestore.objects.first()
                self.assertEqual(restore.status, SystemRestore.STATUS_COMPLETED, restore.error)
