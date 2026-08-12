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
from django.template.loader import render_to_string
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from dlux.backup import (
    apply_backup_retention,
    decrypt_dlb_to_tempfile,
    get_system_backup_models,
    get_system_backup_storage_prefix,
    read_dlb_metadata,
    run_scheduled_system_backup,
    run_system_backup,
    run_system_restore,
    write_system_backup,
)
from dlux.utils import backup_progress as dlux_backup_progress
from dlux.reports import build_relation_schema
from dlux.system.defaults import default_backup_config
from dlux.system.normalizers import normalize_backup_config

User = get_user_model()


def _tiny_png():
    from PIL import Image

    stream = io.BytesIO()
    Image.new('RGB', (1, 1), 'red').save(stream, format='PNG')
    return stream.getvalue()


class SystemBackupPolicyTests(TestCase):
    def setUp(self):
        self.SystemSettings = apps.get_model('dlux', 'SystemSettings')
        self.SystemBackup = apps.get_model('dlux', 'SystemBackup')
        self.settings_obj = self.SystemSettings.load()
        self.settings_obj.is_configured = True

    def _save_config(self, **overrides):
        self.settings_obj.backup_config = normalize_backup_config({
            **default_backup_config(),
            **overrides,
        })
        self.settings_obj.save(update_fields=['backup_config', 'is_configured'])

    def test_policy_normalization_is_conservative_and_sanitizes_target(self):
        defaults = normalize_backup_config({})
        self.assertFalse(defaults['scheduled_enabled'])
        self.assertEqual(defaults['retention_days'], 0)
        self.assertEqual(defaults['max_backups_to_keep'], 0)
        self.assertEqual(normalize_backup_config({'auto_export_target': '../escape'})['auto_export_target'], 'dlux_backups')
        self._save_config(auto_export_target='protected/dlux')
        self.assertEqual(get_system_backup_storage_prefix(), 'protected/dlux')

    def test_count_retention_keeps_newest_completed_backups(self):
        self._save_config(max_backups_to_keep=2)
        backups = [
            self.SystemBackup.objects.create(
                requested_by_username='system',
                status=self.SystemBackup.STATUS_COMPLETED,
                trigger=self.SystemBackup.TRIGGER_SCHEDULED,
                completed_at=timezone.now(),
            )
            for _ in range(3)
        ]
        removed = apply_backup_retention(protected_pk=backups[-1].pk)
        self.assertEqual(removed, 1)
        self.assertEqual(self.SystemBackup.objects.filter(status=self.SystemBackup.STATUS_COMPLETED).count(), 2)
        self.assertFalse(self.SystemBackup.objects.filter(pk=backups[0].pk).exists())

    def test_trigger_has_database_default_for_previous_release_inserts(self):
        # Regression for the 1.2.5 inline-update crash: the updater's pre-update
        # backup is created by the *previous* release's code, which has no `trigger`
        # field. An INSERT that omits the column must still succeed, relying on the
        # column's database-level default rather than a (dropped) Python default.
        field = self.SystemBackup._meta.get_field('trigger')
        self.assertEqual(field.db_default, self.SystemBackup.TRIGGER_MANUAL)
        self.assertEqual(self.SystemBackup._meta.get_field('progress_percent').db_default, 0)
        self.assertEqual(self.SystemBackup._meta.get_field('progress_message').db_default, '')

        from django.db import connection

        table = self.SystemBackup._meta.db_table
        with connection.cursor() as cursor:
            cursor.execute(
                f"INSERT INTO {table} "
                "(token, requested_by_username, status, file_path, file_size, "
                " model_count, row_count, file_count, missing_file_count, "
                " passphrase_required, error, created_at) "
                "VALUES ('oldcode-token', 'admin', 'pending', '', 0, 0, 0, 0, 0, 0, '', %s)",
                [timezone.now()],
            )
        row = self.SystemBackup.objects.get(token='oldcode-token')
        self.assertEqual(row.trigger, self.SystemBackup.TRIGGER_MANUAL)

    def test_run_system_backup_reads_media_choice_from_row(self):
        # The runner must derive include_media from the row (not an argument) so the
        # choice survives a Celery handoff, where the task only receives the pk.
        captured = {}

        def fake_write(dest, *, passphrase=None, progress_callback=None, reporter=None, include_media=True):
            captured['include_media'] = include_media
            return (
                {'models': 0, 'rows': 0, 'files': 0, 'media_included': include_media, 'passphrase_required': False},
                {'missing_files': []},
            )

        backup = self.SystemBackup.objects.create(requested_by_username='boss', media_included=False)
        with mock.patch('dlux.backup.create.write_system_backup', side_effect=fake_write):
            run_system_backup(backup.pk)
        self.assertFalse(captured['include_media'])

    def test_scheduler_is_disabled_by_default_and_deduplicates_interval(self):
        self._save_config(scheduled_enabled=False)
        self.assertIsNone(run_scheduled_system_backup())
        self.assertEqual(self.SystemBackup.objects.count(), 0)

        self._save_config(scheduled_enabled=True, schedule_interval_hours=24)
        with mock.patch('dlux.backup.dispatch.run_system_backup', side_effect=lambda pk: self.SystemBackup.objects.get(pk=pk)) as runner:
            first = run_scheduled_system_backup()
            second = run_scheduled_system_backup()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.trigger, self.SystemBackup.TRIGGER_SCHEDULED)
        self.assertEqual(first.requested_by_username, 'system')
        runner.assert_called_once_with(first.pk)


class DlbContainerTests(TestCase):
    def test_data_only_backup_excludes_media_blobs(self):
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            admin = User.objects.create_superuser('media-admin', 'm@example.com', 'pass12345')
            admin.profile.profile_picture.save('avatar.png', ContentFile(_tiny_png()), save=True)

            full = io.BytesIO()
            _meta, full_manifest = write_system_backup(full, include_media=True)
            self.assertTrue(full_manifest['media_included'])
            self.assertTrue(
                any(entry['field'] == 'profile_picture' for entry in full_manifest['files']),
                "full backup should archive the profile picture blob",
            )

            data_only = io.BytesIO()
            meta, data_manifest = write_system_backup(data_only, include_media=False)
            self.assertFalse(data_manifest['media_included'])
            self.assertEqual(data_manifest['files'], [])
            self.assertEqual(meta['files'], 0)
            self.assertFalse(meta['media_included'])
            # The record JSON (including the file-field name) is still present, so the
            # row is fully restorable; only the blob copy is skipped.
            self.assertGreater(meta['rows'], 0)

    def test_manifest_bakes_relation_schema_for_standalone_viewer(self):
        buffer = io.BytesIO()
        _meta, manifest = write_system_backup(buffer)
        schema = manifest.get('schema')
        self.assertIsInstance(schema, dict)
        self.assertTrue(schema)

        # Foreign key recorded on a known dlux model.
        notif_state = schema.get('dlux.dluxnotificationstate', {})
        self.assertEqual(
            notif_state.get('relations', {}).get('notification', {}).get('kind'),
            'fk',
        )

        # One-to-one to the user model recorded as o2o pointing at it.
        profile = schema.get('dlux.profile', {})
        user_rel = profile.get('relations', {}).get('user', {})
        self.assertEqual(user_rel.get('kind'), 'o2o')
        self.assertEqual(user_rel.get('to'), User._meta.label_lower)

        # FKs to the user model serialize as natural keys, so the user model's
        # natural-key fields are recorded for the viewer to resolve them.
        user_schema = schema.get(User._meta.label_lower, {})
        self.assertEqual(user_schema.get('natural_key_fields'), [User.USERNAME_FIELD])

    def test_build_relation_schema_marks_m2m_relations(self):
        schema = build_relation_schema(get_system_backup_models())
        groups_rel = (
            schema.get(User._meta.label_lower, {}).get('relations', {}).get('groups', {})
        )
        self.assertEqual(groups_rel.get('kind'), 'm2m')
        self.assertEqual(groups_rel.get('to'), 'auth.group')

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
                self.assertGreater(backup.file_size, 0)
                self.assertGreater(backup.row_count, 0)
                self.assertEqual(backup.progress_percent, 100)
                self.assertTrue(backup.progress_message)

                DluxNotification = apps.get_model('dlux', 'DluxNotification')
                self.assertTrue(DluxNotification.objects.filter(
                    source_model_key='dlux.systembackup',
                    source_object_id=str(backup.pk),
                    action='backup_completed',
                ).exists())
                backup_log = ActivityLog.objects.get(action='EXPORT', model_key='dlux.systembackup')
                self.assertEqual(backup_log.category, 'system')
                self.assertEqual(backup_log.model_name, 'Dlux System Backup')

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
                restore_log = ActivityLog.objects.get(action='RESTORE')
                self.assertEqual(restore_log.category, 'system')
                self.assertEqual(restore_log.model_key, 'dlux.systemrestore')
                self.assertEqual(restore_log.model_name, 'Dlux System Restore')

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
                    'dlux.backup.restore.get_current_migration_state',
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
                    'dlux.backup.restore.get_current_migration_state',
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
        self.assertEqual(client.get(reverse('system_backup_list_status')).status_code, 403)
        self.assertEqual(client.post(reverse('system_backup_create')).status_code, 403)
        self.assertEqual(client.post(reverse('system_restore_start')).status_code, 403)

    def test_superuser_page_renders(self):
        client = Client()
        client.login(username='boss', password='bosspass123')
        response = client.get(reverse('system_backup_page'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'sysbackup-create-btn')
        self.assertContains(response, reverse('system_backup_list_status'))
        self.assertContains(response, 'id="sysbackup-table-body"')
        self.assertContains(response, 'data-autoclose="false"')
        self.assertContains(response, 'dlux-backup-page')
        self.assertContains(response, 'dlux-form dlux-backup-create-form')
        self.assertContains(response, 'dlux-table-shell')
        self.assertContains(response, 'data-archive-file-widget')
        self.assertContains(response, 'data-max-file-bytes="536870912"')
        self.assertContains(response, 'name="backup_file"')
        self.assertNotContains(response, 'name="backup_file" accept=".dlb" class="form-control')

    def test_manual_backup_scope_choice_sets_media_included_flag(self):
        SystemBackup = apps.get_model('dlux', 'SystemBackup')
        client = Client()
        client.login(username='boss', password='bosspass123')
        # Mock the runners so we only assert the row the view creates from the choice.
        with mock.patch('dlux.views.backup.dispatch_system_backup', return_value=False), \
                mock.patch('dlux.views.backup.run_system_backup'):
            client.post(reverse('system_backup_create'), {'backup_scope': 'data'})
            client.post(reverse('system_backup_create'), {'backup_scope': 'full'})
            client.post(reverse('system_backup_create'))  # default = full

        rows = list(SystemBackup.objects.order_by('pk'))
        self.assertEqual([r.media_included for r in rows], [False, True, True])

    def test_live_backup_list_reports_completed_size_and_download_action(self):
        SystemBackup = apps.get_model('dlux', 'SystemBackup')
        pending = SystemBackup.objects.create(requested_by_username='boss')
        completed = SystemBackup.objects.create(
            requested_by_username='boss',
            status=SystemBackup.STATUS_COMPLETED,
            file_path='protected/dlux/complete.dlb',
            file_size=4096,
            row_count=3000,
            file_count=12,
            completed_at=timezone.now(),
        )
        client = Client()
        client.login(username='boss', password='bosspass123')

        response = client.get(reverse('system_backup_list_status'))

        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response.headers.get('Cache-Control', ''))
        payload = response.json()
        self.assertTrue(payload['active'])
        self.assertTrue(payload['revision'])
        self.assertEqual(
            {item['token']: item['status'] for item in payload['items']},
            {
                pending.token: SystemBackup.STATUS_PENDING,
                completed.token: SystemBackup.STATUS_COMPLETED,
            },
        )
        self.assertIn('<td>3000</td>', payload['html'])
        self.assertIn('4.0\xa0KB', payload['html'])
        self.assertIn(reverse('system_backup_download', args=[completed.token]), payload['html'])

    def test_individual_backup_status_is_never_cached(self):
        SystemBackup = apps.get_model('dlux', 'SystemBackup')
        backup = SystemBackup.objects.create(requested_by_username='boss')
        client = Client()
        client.login(username='boss', password='bosspass123')

        response = client.get(reverse('system_backup_status', args=[backup.token]))

        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response.headers.get('Cache-Control', ''))
        self.assertEqual(response.json()['status'], SystemBackup.STATUS_PENDING)
        self.assertEqual(response.json()['progress_percent'], 0)

    def test_active_artifact_is_not_listed_as_an_external_backup(self):
        SystemBackup = apps.get_model('dlux', 'SystemBackup')
        backup = SystemBackup.objects.create(
            requested_by_username='boss',
            status=SystemBackup.STATUS_RUNNING,
        )
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                path = f'dlux_backups/system-{backup.token}.dlb'
                default_storage.save(path, ContentFile(b'partial-artifact'))
                client = Client()
                client.login(username='boss', password='bosspass123')

                response = client.get(reverse('system_backup_page'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, f'system-{backup.token}.dlb')

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


class DlbUploadViewTests(TestCase):
    """Upload rejection paths.

    The failure these cover: a multi-GB ``.dlb`` cut short by the reverse proxy
    body limit (``CADDY_MAX_SIZE`` / ``NGINX_MAX_SIZE``, both 10M by default)
    leaves ``request.FILES`` empty, and the view used to report that missing part
    as "not a valid backup file" — pointing the operator at the file instead of
    the proxy.
    """

    def setUp(self):
        SystemSettings = apps.get_model('dlux', 'SystemSettings')
        settings_obj = SystemSettings.load()
        settings_obj.is_configured = True
        settings_obj.save(update_fields=['is_configured'])
        User.objects.create_superuser('boss', 'boss@example.com', 'bosspass123')
        self.client = Client()
        self.client.login(username='boss', password='bosspass123')

    def _post(self, **payload):
        with mock.patch('dlux.views.backup.notify') as notify:
            response = self.client.post(reverse('system_backup_upload'), payload)
        return response, notify

    def test_truncated_upload_reports_an_incomplete_transfer_not_a_bad_file(self):
        response, notify = self._post()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(notify.error.call_args.kwargs['action'], 'backup_upload_incomplete')

    def test_oversized_upload_reports_the_size_limit(self):
        from dlux.views import backup as backup_views

        with override_settings(DLUX_DLB_UPLOAD_MAX_MB=1):
            response, notify = self._post(
                backup_file=ContentFile(b'x' * (2 * 1024 * 1024), name='big.dlb'),
            )
        self.assertEqual(backup_views._dlb_upload_max_mb(), backup_views.DLB_UPLOAD_MAX_MB_DEFAULT)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(notify.error.call_args.kwargs['action'], 'backup_upload_too_large')

    def test_complete_but_corrupt_file_is_still_reported_as_invalid(self):
        response, notify = self._post(
            backup_file=ContentFile(b'PK\x03\x04 definitely a zip', name='fake.dlb'),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(notify.error.call_args.kwargs['action'], 'backup_upload_invalid')

    def test_page_shows_the_copy_into_backup_folder_route(self):
        response = self.client.get(reverse('system_backup_page'))
        self.assertContains(response, 'copy the .dlb file straight into the backup folder')


class RestoreProgressTests(TestCase):
    """Live progress for a running restore.

    The failure these cover: a restore reported nothing at all — only a bare
    'running' badge — so an operator watching a multi-GB restore could not tell a
    working run from a hung one. The database phase is the hard part: it runs in
    one transaction, so a row UPDATE from inside it is invisible to the polling
    web process until the whole load commits.
    """

    def setUp(self):
        from django.core.cache import cache

        # notify() dedupes identical events for 2s through the cache, which
        # TestCase does not roll back — so two tests that each restore row pk=1
        # would have the second notification silently swallowed. Local LocMem
        # cache only; this never runs against a shared cache.
        cache.clear()
        SystemSettings = apps.get_model('dlux', 'SystemSettings')
        settings_obj = SystemSettings.load()
        settings_obj.is_configured = True
        settings_obj.save(update_fields=['is_configured'])
        self.SystemRestore = apps.get_model('dlux', 'SystemRestore')
        User.objects.create_superuser('boss', 'boss@example.com', 'bosspass123')
        self.client = Client()
        self.client.login(username='boss', password='bosspass123')

    def _restore(self, **kwargs):
        return self.SystemRestore.objects.create(
            requested_by_username='boss', backup_file_path='x.dlb', **kwargs,
        )

    def test_in_transaction_progress_is_visible_through_the_cache_mirror(self):
        from django.db import transaction

        from dlux.utils.backup_progress import read_restore_progress, set_restore_progress

        restore = self._restore(status=self.SystemRestore.STATUS_RUNNING)
        # Inside an atomic block a row UPDATE is invisible to other connections;
        # the mirror is what the status view must be reading.
        with transaction.atomic():
            set_restore_progress(restore, 42, 'Restoring users', stage='database')
            live = read_restore_progress(restore)
        self.assertEqual(live['progress_percent'], 42)
        self.assertEqual(live['progress_message'], 'Restoring users')
        self.assertEqual(live['stage'], 'database')

    def test_a_stale_mirror_never_drags_the_row_backwards(self):
        from dlux.utils.backup_progress import read_restore_progress, set_restore_progress

        restore = self._restore(status=self.SystemRestore.STATUS_RUNNING)
        set_restore_progress(restore, 20, 'early', stage='database')
        self.SystemRestore.objects.filter(pk=restore.pk).update(progress_percent=80, progress_message='later')
        restore.refresh_from_db()
        self.assertEqual(read_restore_progress(restore)['progress_percent'], 80)

    def test_finished_restore_ignores_the_mirror_entirely(self):
        from dlux.utils.backup_progress import read_restore_progress, set_restore_progress

        restore = self._restore(status=self.SystemRestore.STATUS_RUNNING)
        set_restore_progress(restore, 55, 'mid-flight', stage='files')
        self.SystemRestore.objects.filter(pk=restore.pk).update(
            status=self.SystemRestore.STATUS_COMPLETED, progress_percent=100, progress_message='done',
        )
        restore.refresh_from_db()
        self.assertEqual(read_restore_progress(restore)['progress_percent'], 100)

    def test_status_endpoint_reports_progress(self):
        from dlux.utils.backup_progress import set_restore_progress

        restore = self._restore(status=self.SystemRestore.STATUS_RUNNING)
        set_restore_progress(restore, 61, 'Restoring documents', stage='database')
        payload = self.client.get(
            reverse('system_restore_status', args=[restore.token])
        ).json()
        self.assertEqual(payload['status'], 'running')
        self.assertEqual(payload['progress_percent'], 61)
        self.assertEqual(payload['progress_message'], 'Restoring documents')
        self.assertEqual(payload['stage'], 'database')

    def test_list_status_renders_rows_and_tracks_activity(self):
        from dlux.utils.backup_progress import set_restore_progress

        restore = self._restore(status=self.SystemRestore.STATUS_RUNNING)
        set_restore_progress(restore, 37, 'Restoring groups', stage='database')
        payload = self.client.get(reverse('system_restore_list_status')).json()
        self.assertTrue(payload['active'])
        self.assertIn('Restoring groups', payload['html'])
        self.assertIn('dlux-backup-progress', payload['html'])
        self.assertIn('value="37"', payload['html'])

        first_revision = payload['revision']
        set_restore_progress(restore, 58, 'Restoring documents', stage='database')
        second = self.client.get(reverse('system_restore_list_status')).json()
        self.assertNotEqual(second['revision'], first_revision)

    def test_list_status_requires_superuser(self):
        User.objects.create_user('staffer', 's@example.com', 'staffpass123', is_staff=True)
        client = Client()
        client.login(username='staffer', password='staffpass123')
        self.assertEqual(client.get(reverse('system_restore_list_status')).status_code, 403)

    def test_terminal_notification_is_emitted_for_a_finished_restore(self):
        from dlux.utils.backup_progress import finish_restore_progress

        restore = self._restore(status=self.SystemRestore.STATUS_COMPLETED)
        finish_restore_progress(restore, success=True)

        DluxNotification = apps.get_model('dlux', 'DluxNotification')
        notification = DluxNotification.objects.filter(action='restore_completed').first()
        self.assertIsNotNone(notification)
        self.assertEqual(notification.metadata.get('backup_kind'), 'restore')
        restore.refresh_from_db()
        self.assertEqual(restore.progress_percent, 100)

    def test_failed_restore_notification_carries_the_error(self):
        from dlux.utils.backup_progress import finish_restore_progress

        restore = self._restore(status=self.SystemRestore.STATUS_FAILED, error='boom')
        finish_restore_progress(restore, success=False, error='boom')

        DluxNotification = apps.get_model('dlux', 'DluxNotification')
        notification = DluxNotification.objects.filter(action='restore_failed').first()
        self.assertIsNotNone(notification)
        self.assertIn('boom', notification.message)

    def test_page_renders_the_live_restore_table(self):
        response = self.client.get(reverse('system_backup_page'))
        self.assertContains(response, 'id="sysrestore-table-body"')
        self.assertContains(response, reverse('system_restore_list_status'))

    def test_a_real_restore_reports_every_phase_and_ends_at_100(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                worker = User.objects.create_user('worker', 'w@example.com', 'workerpass1')
                worker.profile.profile_picture.save('pic.png', ContentFile(_tiny_png()), save=True)
                SystemBackup = apps.get_model('dlux', 'SystemBackup')
                backup = SystemBackup.objects.create(requested_by_username='boss')
                run_system_backup(backup.pk)
                backup.refresh_from_db()

                restore = self.SystemRestore.objects.create(
                    requested_by_username='boss', backup_file_path=backup.file_path,
                )
                seen = []
                real = dlux_backup_progress.set_restore_progress

                def record(target, percent, message, stage=None):
                    seen.append((int(percent), stage))
                    return real(target, percent, message, stage=stage)

                with mock.patch.object(dlux_backup_progress, 'set_restore_progress', record):
                    run_system_restore(restore.pk)

                restore.refresh_from_db()
                self.assertEqual(restore.status, self.SystemRestore.STATUS_COMPLETED, restore.error)
                self.assertEqual(restore.progress_percent, 100)
                stages = [stage for _percent, stage in seen]
                for expected in ('reading', 'decrypting', 'database', 'files', 'finalizing'):
                    self.assertIn(expected, stages, stages)
                # Progress only ever moves forward while the run is live.
                percents = [percent for percent, _stage in seen]
                self.assertEqual(percents, sorted(percents), percents)


class ProgressCellLayoutTests(TestCase):
    """The percentage must never be orphaned onto its own line.

    The failure this covers: percentage and status message were one text run
    joined by ' · ', so the spaces around that separator were legal break points.
    A long running-phase message wrapped and stranded "0%" alone on the line
    above, while a short completed message happened to fit — which is why the bug
    only showed at 0%. They are now flex siblings, so the number always shares
    the message's first line.
    """

    LONG_MESSAGE = 'Decrypting 1.2 GB / 9.8 GB of an unusually large container'

    def setUp(self):
        self.SystemBackup = apps.get_model('dlux', 'SystemBackup')
        self.SystemRestore = apps.get_model('dlux', 'SystemRestore')

    def _cell(self, html):
        start = html.index('dlux-backup-progress-status')
        return html[start:html.index('</small>', start)]

    def test_backup_row_keeps_percent_and_message_as_flex_siblings(self):
        from dlux.views.backup import _backup_rows_context

        backup = self.SystemBackup.objects.create(
            requested_by_username='x', status='running',
            progress_percent=0, progress_message=self.LONG_MESSAGE,
        )
        html = render_to_string(
            'dlux/backup/_backup_rows.html', _backup_rows_context([backup]),
        )
        cell = self._cell(html)
        self.assertIn('dlux-backup-progress-percent">0%<', cell)
        self.assertIn(f'dlux-backup-progress-note">{self.LONG_MESSAGE}<', cell)
        # The middot separator is what could break; a gap replaces it.
        self.assertNotIn('·', cell)

    def test_restore_row_keeps_percent_and_message_as_flex_siblings(self):
        from dlux.views.backup import _restore_rows_context

        restore = self.SystemRestore.objects.create(
            requested_by_username='x', backup_file_path='x.dlb', status='running',
            progress_percent=0, progress_message=self.LONG_MESSAGE, stage='decrypting',
        )
        html = render_to_string(
            'dlux/backup/_restore_rows.html', _restore_rows_context([restore]),
        )
        cell = self._cell(html)
        self.assertIn('dlux-backup-progress-percent">0%<', cell)
        self.assertIn(f'dlux-backup-progress-note">{self.LONG_MESSAGE}<', cell)
        self.assertNotIn('·', cell)

    def test_completed_rows_render_the_same_structure(self):
        """100% took the same code path, so it must not diverge either."""
        from dlux.views.backup import _backup_rows_context

        backup = self.SystemBackup.objects.create(
            requested_by_username='x', status='completed',
            progress_percent=100, progress_message='Backup ready.',
        )
        cell = self._cell(render_to_string(
            'dlux/backup/_backup_rows.html', _backup_rows_context([backup]),
        ))
        self.assertIn('dlux-backup-progress-percent">100%<', cell)
        self.assertIn('dlux-backup-progress-note">Backup ready.<', cell)

    def test_stylesheet_defines_the_layout_the_markup_relies_on(self):
        from pathlib import Path

        import dlux

        css = (
            Path(dlux.__file__).parent / 'static' / 'dlux' / 'notifications' / 'css' / 'main.css'
        ).read_text(encoding='utf-8')
        block = css[css.index('.dlux-backup-progress-status'):]
        self.assertIn('display: flex', block)
        self.assertIn('.dlux-backup-progress-percent', block)
        self.assertIn('flex: 0 0 auto', block)
