import io
import json
import zipfile
from datetime import timedelta

from django.conf import settings

if not settings.configured:
    settings.configure(
        SECRET_KEY='microsys-test-key',
        ALLOWED_HOSTS=['testserver', 'localhost'],
        INSTALLED_APPS=[
            'django.contrib.auth',
            'django.contrib.contenttypes',
            'django.contrib.sessions',
            'django.contrib.messages',
            'django.contrib.staticfiles',
            'crispy_forms',
            'crispy_bootstrap5',
            'django_filters',
            'django_tables2',
            'microsys',
        ],
        MIDDLEWARE=[
            'django.contrib.sessions.middleware.SessionMiddleware',
            'django.contrib.auth.middleware.AuthenticationMiddleware',
            'microsys.middleware.MicrosysMiddleware',
        ],
        ROOT_URLCONF='microsys.urls',
        TEMPLATES=[
            {
                'BACKEND': 'django.template.backends.django.DjangoTemplates',
                'APP_DIRS': True,
                'OPTIONS': {
                    'context_processors': [
                        'django.template.context_processors.request',
                        'django.contrib.auth.context_processors.auth',
                        'django.contrib.messages.context_processors.messages',
                        'microsys.context_processors.microsys_context',
                    ],
                },
            }
        ],
        DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}},
        STATIC_URL='/static/',
        DEFAULT_AUTO_FIELD='django.db.models.BigAutoField',
        USE_TZ=True,
        CRISPY_ALLOWED_TEMPLATE_PACKS='bootstrap5',
        CRISPY_TEMPLATE_PACK='bootstrap5',
    )

    import django
    django.setup()

import tempfile

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.storage import default_storage
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from microsys.reports import run_report_backup, write_backup_zip

User = get_user_model()

ACTIVITY_BACKUP_CONFIG = {
    'reports': {'include_models': ['microsys.useractivitylog']},
}


def _make_logs():
    """One activity row inside the current week, one ~60 days old."""
    ActivityLog = apps.get_model('microsys', 'UserActivityLog')
    recent = ActivityLog.objects.create(action='CREATE', model_name='Project Entry')
    old = ActivityLog.objects.create(action='CREATE', model_name='Project Entry')
    ActivityLog.objects.filter(pk=old.pk).update(
        created_at=timezone.now() - timedelta(days=60)
    )
    return recent, old


def _zip_activity_rows(zip_bytes):
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        payload = json.loads(zf.read('data/microsys/useractivitylog.json'))
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


@override_settings(MICROSYS_CONFIG=ACTIVITY_BACKUP_CONFIG)
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
        self.assertEqual(model_counts.get('microsys.useractivitylog'), 1)

    def test_invalid_window_defaults_to_all(self):
        recent, old = _make_logs()
        content, manifest = self._build('bogus')
        rows, _ = _zip_activity_rows(content)
        self.assertEqual(manifest['window'], 'all')
        self.assertEqual(len(rows), 2)


@override_settings(MICROSYS_CONFIG=ACTIVITY_BACKUP_CONFIG)
class BackupViewTests(TestCase):
    def setUp(self):
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
        ReportBackup = apps.get_model('microsys', 'ReportBackup')
        self.assertEqual(ReportBackup.objects.count(), 0)

    def test_start_requires_backup_permission(self):
        plain = User.objects.create_user(
            username='plain-user', password='plainpass123', is_staff=True,
        )
        client = Client()
        client.login(username='plain-user', password='plainpass123')
        response = client.post(reverse('reports_backup_start'), {'window': 'all'})
        self.assertEqual(response.status_code, 403)

    def test_run_status_and_download_flow(self):
        recent, old = _make_logs()
        ReportBackup = apps.get_model('microsys', 'ReportBackup')
        backup = ReportBackup.objects.create(user=self.user, window='week')
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                run_report_backup(backup.pk)
                backup.refresh_from_db()
                self.assertEqual(backup.status, ReportBackup.STATUS_COMPLETED)
                self.assertTrue(backup.file_path)
                self.assertTrue(default_storage.exists(backup.file_path))
                self.assertGreater(backup.file_size, 0)

                status = self.client.get(
                    reverse('reports_backup_status', args=[backup.token])
                )
                self.assertEqual(status.status_code, 200)
                payload = status.json()
                self.assertEqual(payload['status'], 'completed')
                self.assertIn('download_url', payload)

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
