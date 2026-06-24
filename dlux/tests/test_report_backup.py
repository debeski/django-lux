import io
import json
import zipfile
from datetime import timedelta

from dlux.tests.harness import setup_test_environment

setup_test_environment()

import tempfile
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.storage import default_storage
from django.db import models
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from dlux.reports import backup_record_folder, run_report_backup, write_backup_zip

User = get_user_model()

ACTIVITY_BACKUP_CONFIG = {
    'reports': {'include_models': ['dlux.activitylog']},
}


class NumberedBackupRecord(models.Model):
    number = models.CharField(max_length=100)

    class Meta:
        app_label = 'backup_tests'
        managed = False


class ConfiguredBackupRecord(models.Model):
    case_reference = models.CharField(max_length=100)

    class Meta:
        app_label = 'backup_tests'
        managed = False


def _make_logs():
    """One activity row inside the current week, one ~60 days old."""
    ActivityLog = apps.get_model('dlux', 'ActivityLog')
    recent = ActivityLog.objects.create(action='CREATE', model_name='Project Entry')
    old = ActivityLog.objects.create(action='CREATE', model_name='Project Entry')
    ActivityLog.objects.filter(pk=old.pk).update(
        created_at=timezone.now() - timedelta(days=60)
    )
    return recent, old


def _zip_activity_rows(zip_bytes):
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        payload = json.loads(zf.read('data/dlux/activitylog.json'))
        manifest = json.loads(zf.read('manifest.json'))
    return payload, manifest


def _make_backup_user(username='backup-user'):
    user = User.objects.create_user(
        username=username,
        email=f'{username}@example.com',
        password='backuppass123',
        is_staff=True,
    )
    user.user_permissions.add(
        Permission.objects.get(codename='view_reports'),
        Permission.objects.get(codename='download_backup'),
    )
    return user


@override_settings(DLUX_CONFIG=ACTIVITY_BACKUP_CONFIG)
class WriteBackupZipWindowTests(TestCase):
    def setUp(self):
        self.actor = User.objects.create_superuser(
            username='backup-admin',
            email='backup-admin@example.com',
            password='adminpass123',
        )

    def _build(self, window):
        buffer = io.BytesIO()
        manifest = write_backup_zip(self.actor, buffer, window=window)
        return buffer.getvalue(), manifest

    def test_window_all_includes_everything(self):
        recent, old = _make_logs()
        content, manifest = self._build('all')
        rows, zip_manifest = _zip_activity_rows(content)
        self.assertEqual({row['pk'] for row in rows}, {recent.pk, old.pk})
        self.assertEqual(zip_manifest['window'], 'all')

    def test_window_week_filters_old_rows(self):
        recent, old = _make_logs()
        content, manifest = self._build('week')
        rows, zip_manifest = _zip_activity_rows(content)
        self.assertEqual({row['pk'] for row in rows}, {recent.pk})
        self.assertEqual(zip_manifest['window'], 'week')
        model_counts = {item['model']: item['count'] for item in manifest['models']}
        self.assertEqual(model_counts.get('dlux.activitylog'), 1)

    def test_invalid_window_defaults_to_all(self):
        recent, old = _make_logs()
        content, manifest = self._build('bogus')
        rows, _ = _zip_activity_rows(content)
        self.assertEqual(manifest['window'], 'all')
        self.assertEqual(len(rows), 2)

    def test_record_folder_prefers_business_number_and_keeps_pk(self):
        record = NumberedBackupRecord(pk=37, number='2000 / A')

        self.assertEqual(
            backup_record_folder(record),
            'number-2000-A',
        )

    @override_settings(DLUX_CONFIG={
        'reports': {
            'backup_label_fields': {
                'backup_tests.configuredbackuprecord': 'case_reference',
            },
        },
    })
    def test_record_folder_supports_explicit_per_model_label_field(self):
        record = ConfiguredBackupRecord(pk=8, case_reference='../CASE\\42')

        self.assertEqual(
            backup_record_folder(record),
            'case-reference-CASE-42',
        )


@override_settings(DLUX_CONFIG=ACTIVITY_BACKUP_CONFIG)
class BackupViewTests(TestCase):
    def setUp(self):
        settings_obj = apps.get_model('dlux', 'SystemSettings').load()
        settings_obj.is_configured = True
        settings_obj.save(update_fields=['is_configured'])
        self.user = _make_backup_user()
        self.client = Client()
        self.client.login(username='backup-user', password='backuppass123')

    def test_sync_backup_zip_honors_window(self):
        recent, old = _make_logs()
        response = self.client.get(reverse('reports_backup_zip'), {'window': 'week'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/zip')
        content = b''.join(response.streaming_content)
        rows, manifest = _zip_activity_rows(content)
        # The EXPORT row logged for this download postdates the snapshot, so only
        # `recent` is guaranteed; `old` must be filtered out by the week window.
        self.assertIn(recent.pk, {row['pk'] for row in rows})
        self.assertNotIn(old.pk, {row['pk'] for row in rows})
        self.assertEqual(manifest['window'], 'week')

    def test_start_falls_back_to_sync_without_worker(self):
        response = self.client.post(reverse('reports_backup_start'), {'window': 'month'})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['ok'])
        self.assertFalse(payload['async'])
        self.assertIn('window=month', payload['download_url'])
        # No orphaned pending row is left behind on fallback.
        ReportBackup = apps.get_model('dlux', 'ReportBackup')
        self.assertEqual(ReportBackup.objects.count(), 0)

    def test_start_requires_backup_permission(self):
        plain = User.objects.create_user(
            username='plain-user', password='plainpass123', is_staff=True,
        )
        client = Client()
        client.login(username='plain-user', password='plainpass123')
        response = client.post(reverse('reports_backup_start'), {'window': 'all'})
        self.assertEqual(response.status_code, 403)

    def test_start_reuses_active_backup_instead_of_queueing_duplicate(self):
        ReportBackup = apps.get_model('dlux', 'ReportBackup')
        active = ReportBackup.objects.create(user=self.user, window='all')

        with patch('dlux.views.reports.dispatch_report_backup') as dispatch:
            response = self.client.post(reverse('reports_backup_start'), {'window': 'week'})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['async'])
        self.assertTrue(payload['reused'])
        self.assertEqual(payload['token'], active.token)
        self.assertEqual(ReportBackup.objects.count(), 1)
        dispatch.assert_not_called()

    def test_overview_resumes_active_backup_and_links_latest_completed(self):
        ReportBackup = apps.get_model('dlux', 'ReportBackup')
        completed = ReportBackup.objects.create(
            user=self.user,
            window='week',
            status=ReportBackup.STATUS_COMPLETED,
            file_path='dlux_backups/completed.zip',
            completed_at=timezone.now(),
        )
        active = ReportBackup.objects.create(user=self.user, window='all')

        response = self.client.get(reverse('reports_overview'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse('reports_backup_status', args=[active.token]),
        )
        self.assertContains(
            response,
            reverse('reports_backup_download', args=[completed.token]),
        )

    def test_run_status_and_download_flow(self):
        recent, old = _make_logs()
        ReportBackup = apps.get_model('dlux', 'ReportBackup')
        backup = ReportBackup.objects.create(user=self.user, window='week')
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                run_report_backup(backup.pk)
                backup.refresh_from_db()
                self.assertEqual(backup.status, ReportBackup.STATUS_COMPLETED)
                self.assertTrue(backup.file_path)
                self.assertTrue(default_storage.exists(backup.file_path))
                self.assertGreater(backup.file_size, 0)
                self.assertEqual(backup.progress_percent, 100)
                self.assertTrue(backup.progress_message)

                DluxNotification = apps.get_model('dlux', 'DluxNotification')
                self.assertTrue(DluxNotification.objects.filter(
                    source_model_key='dlux.reportbackup',
                    source_object_id=str(backup.pk),
                    action='backup_progress',
                    metadata__locked=False,
                ).exists())
                self.assertTrue(DluxNotification.objects.filter(
                    source_model_key='dlux.reportbackup',
                    source_object_id=str(backup.pk),
                    action='backup_completed',
                ).exists())

                status = self.client.get(
                    reverse('reports_backup_status', args=[backup.token])
                )
                self.assertEqual(status.status_code, 200)
                payload = status.json()
                self.assertEqual(payload['status'], 'completed')
                self.assertEqual(payload['progress_percent'], 100)
                self.assertIn('download_url', payload)
                self.assertIn('no-cache', status['Cache-Control'])

                download = self.client.get(payload['download_url'])
                self.assertEqual(download.status_code, 200)
                self.assertEqual(download['Content-Type'], 'application/zip')
                content = b''.join(download.streaming_content)
                rows, manifest = _zip_activity_rows(content)
                self.assertIn(recent.pk, {row['pk'] for row in rows})
                self.assertNotIn(old.pk, {row['pk'] for row in rows})

                # Another permitted user cannot see someone else's backup.
                other = _make_backup_user('backup-other')
                other_client = Client()
                other_client.login(username='backup-other', password='backuppass123')
                denied = other_client.get(
                    reverse('reports_backup_status', args=[backup.token])
                )
                self.assertEqual(denied.status_code, 404)
