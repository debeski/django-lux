"""Operations resilience: backup retries and storage, restore, outages, services.

Each class pins one break-it round-2 finding (R2-###) so its regression names
the failure it guards against.
"""

from dlux.tests.harness import setup_test_environment

setup_test_environment()

import errno
import os
import shutil
import tempfile
from collections import namedtuple
from datetime import timedelta
from unittest import mock

from django.apps import apps
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage, default_storage
from django.test import TestCase, override_settings
from django.utils import timezone

from dlux.backup import run_system_backup
from dlux.backup.config import get_system_backup_storage_prefix
from dlux.system.defaults import default_backup_config
from dlux.system.normalizers import normalize_backup_config


def _configure(**backup_overrides):
    SystemSettings = apps.get_model('dlux', 'SystemSettings')
    settings_obj = SystemSettings.load()
    settings_obj.is_configured = True
    settings_obj.backup_config = normalize_backup_config({**default_backup_config(), **backup_overrides})
    settings_obj.save(update_fields=['is_configured', 'backup_config'])
    return settings_obj


class StalledBackupReaperScheduleTests(TestCase):
    """R2-043: an armed retry waited for someone to open the backup page."""

    def test_the_reaper_runs_on_the_worker_every_minute(self):
        from dlux.taskrunner import registered_tasks
        from dlux.utils.settings import DLUX_BUILTIN_TASK_SCHEDULE

        entry = DLUX_BUILTIN_TASK_SCHEDULE['dlux-reap-stalled-backups']
        self.assertEqual(entry['task'], 'dlux.tasks.reap_stalled_system_backups')
        self.assertLessEqual(float(entry['schedule']), 60.0)
        import dlux.jobs  # noqa: F401  registers the tasks
        self.assertIn(entry['task'], registered_tasks())

    def test_a_due_retry_starts_with_scheduled_backups_off(self):
        _configure(scheduled_enabled=False, auto_retry_enabled=True, max_attempts=3)
        SystemBackup = apps.get_model('dlux', 'SystemBackup')
        backup = SystemBackup.objects.create(requested_by_username='boss')
        SystemBackup.objects.filter(pk=backup.pk).update(
            next_attempt_at=timezone.now() - timedelta(seconds=5), attempt_count=1,
        )
        from dlux.taskrunner import registered_tasks
        import dlux.jobs  # noqa: F401

        task = registered_tasks()['dlux.tasks.reap_stalled_system_backups']
        with mock.patch('dlux.backup.dispatch.dispatch_system_backup', return_value=True) as dispatched:
            task.func()
        dispatched.assert_called_once()
        backup.refresh_from_db()
        self.assertIsNone(backup.next_attempt_at)


class _FullDiskStorage(FileSystemStorage):
    """Writes the first 1 KiB of every file, then fails like a full volume."""

    def _save(self, name, content):
        full = self.path(name)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'wb') as fh:
            fh.write(b'x' * 1024)
        raise OSError(errno.ENOSPC, 'No space left on device')


class BackupOutOfDiskTests(TestCase):
    """R2-044: a backup that ran out of disk left its partial .dlb behind."""

    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, True)
        _configure(auto_retry_enabled=False)

    def _files(self):
        folder = os.path.join(self.media, get_system_backup_storage_prefix())
        return sorted(os.listdir(folder)) if os.path.isdir(folder) else []

    def test_a_failed_save_leaves_no_partial_file(self):
        SystemBackup = apps.get_model('dlux', 'SystemBackup')
        with override_settings(MEDIA_ROOT=self.media):
            full = _FullDiskStorage(location=self.media)
            with mock.patch.object(default_storage, '_wrapped', full):
                for _attempt in range(2):
                    backup = SystemBackup.objects.create(requested_by_username='boss')
                    run_system_backup(backup.pk)
                    backup.refresh_from_db()
                    self.assertEqual(backup.status, SystemBackup.STATUS_FAILED)
                    self.assertIn('No space left', backup.error)
        self.assertEqual(self._files(), [])

    def test_a_backup_that_cannot_fit_fails_before_writing(self):
        SystemBackup = apps.get_model('dlux', 'SystemBackup')
        usage = namedtuple('usage', 'total used free')(100, 99, 1)
        with override_settings(MEDIA_ROOT=self.media), \
                mock.patch('dlux.backup._shared.shutil.disk_usage', return_value=usage):
            backup = SystemBackup.objects.create(requested_by_username='boss')
            run_system_backup(backup.pk)
        backup.refresh_from_db()
        self.assertEqual(backup.status, SystemBackup.STATUS_FAILED)
        self.assertIn('Not enough free space', backup.error)
        self.assertEqual(self._files(), [])

    def test_the_index_sidecar_cleans_up_too(self):
        from dlux.backup.chain import write_index_sidecar

        with override_settings(MEDIA_ROOT=self.media):
            full = _FullDiskStorage(location=self.media)
            with mock.patch.object(default_storage, '_wrapped', full):
                with self.assertRaises(OSError):
                    write_index_sidecar(f'{get_system_backup_storage_prefix()}/x.idx', {}, encrypt=False)
        self.assertEqual(self._files(), [])

    def test_an_upload_to_a_full_disk_reports_it(self):
        from django.contrib.auth import get_user_model
        from django.test import Client
        from django.urls import reverse

        get_user_model().objects.create_superuser('boss', 'boss@example.invalid', 'bosspass123')
        client = Client()
        client.login(username='boss', password='bosspass123')
        with override_settings(MEDIA_ROOT=self.media), \
                mock.patch('dlux.views.backup.read_dlb_metadata', return_value={}), \
                mock.patch('dlux.views.backup.notify') as notify:
            full = _FullDiskStorage(location=self.media)
            with mock.patch.object(default_storage, '_wrapped', full):
                response = client.post(reverse('system_backup_upload'), {
                    'backup_file': ContentFile(b'DLB' * 100, name='mine.dlb'),
                })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(notify.error.call_args.kwargs['action'], 'backup_upload_store_failed')
        self.assertEqual(self._files(), [])


from django.db import OperationalError, ProgrammingError
from django.db.utils import InternalError
from django.http import HttpResponse
from django.test import Client, SimpleTestCase
from django.urls import path


class _ReadOnly(Exception):
    sqlstate = '25006'


class _TooManyClients(Exception):
    sqlstate = '53300'


def _raise(exc_factory):
    def view(request):
        raise exc_factory()
    return view


def _read_only():
    exc = InternalError('cannot execute INSERT in a read-only transaction')
    exc.__cause__ = _ReadOnly()
    return exc


def _too_many():
    exc = OperationalError('sorry, too many clients already')
    exc.__cause__ = _TooManyClients()
    return exc


class _SessionLoadFails:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        raise OperationalError('connection to server failed: timeout expired')


urlpatterns = [
    path('down/', _raise(lambda: OperationalError('could not connect to server: Connection refused'))),
    path('full/', _raise(_too_many)),
    path('readonly/', _raise(_read_only)),
    path('bug/', _raise(lambda: ProgrammingError('relation "x" does not exist'))),
    path('fine/', lambda request: HttpResponse('ok')),
    path('sys/backup/restore/<str:token>/status/', lambda request, token: HttpResponse('poll'), name='system_restore_status'),
]


@override_settings(ROOT_URLCONF=__name__, MIDDLEWARE=['dlux.db_outage.DatabaseOutageMiddleware'])
class DatabaseOutageMiddlewareTests(SimpleTestCase):
    """R2-045: a paused, full or read-only database gave hangs and 500s."""

    def _get(self, url, **headers):
        return Client(raise_request_exception=False).get(url, **headers)

    def test_outages_answer_503(self):
        for url in ('/down/', '/full/', '/readonly/'):
            with self.subTest(url=url), self.assertLogs('dlux.db', level='WARNING'):
                response = self._get(url)
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response['Retry-After'], '15')
                self.assertIn('database is not responding', response.content.decode().lower())

    def test_ajax_gets_json(self):
        with self.assertLogs('dlux.db', level='WARNING'):
            response = self._get('/down/', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json()['success'])

    @override_settings(MIDDLEWARE=[
        'dlux.db_outage.DatabaseOutageMiddleware',
        'dlux.tests.test_ops_resilience._SessionLoadFails',
    ])
    def test_an_inner_middleware_failing_answers_503(self):
        with self.assertLogs('django.request', level='ERROR'):
            response = self._get('/fine/')
        self.assertEqual(response.status_code, 503)

    def test_a_query_bug_stays_a_500(self):
        with self.assertLogs('django.request', level='ERROR'):
            self.assertEqual(self._get('/bug/').status_code, 500)
        self.assertEqual(self._get('/fine/').status_code, 200)

    def test_the_page_needs_no_database(self):
        from dlux.db_outage import database_outage_response
        from django.test import RequestFactory

        with mock.patch('dlux.translations.runtime._language_config', side_effect=AssertionError('db read')):
            response = database_outage_response(RequestFactory().get('/'))
        self.assertEqual(response.status_code, 503)


@override_settings(ROOT_URLCONF=__name__, MIDDLEWARE=['dlux.db_outage.DatabaseOutageMiddleware'])
class RestoreInProgressTests(SimpleTestCase):
    """R2-047: a restore hung every request on its transaction's locks."""

    def tearDown(self):
        from dlux.db_outage import clear_restore_in_progress

        clear_restore_in_progress()

    def test_requests_get_503_while_a_restore_runs_and_the_status_poll_still_answers(self):
        from dlux.db_outage import clear_restore_in_progress, set_restore_in_progress

        set_restore_in_progress('tok')
        response = Client().get('/fine/')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response['Retry-After'], '30')
        self.assertIn('Restore in progress', response.content.decode())
        self.assertEqual(Client().get('/sys/backup/restore/tok/status/').status_code, 200)
        clear_restore_in_progress()
        self.assertEqual(Client().get('/fine/').status_code, 200)


class RestoreRunClosesTheSiteTests(TestCase):
    def test_the_flag_is_up_during_the_load_and_down_afterwards(self):
        from dlux.backup import run_system_backup
        from dlux.backup.restore import run_system_restore
        from dlux.db_outage import restore_in_progress

        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, True)
        _configure()
        SystemBackup = apps.get_model('dlux', 'SystemBackup')
        SystemRestore = apps.get_model('dlux', 'SystemRestore')
        seen = []
        with override_settings(MEDIA_ROOT=media):
            backup = SystemBackup.objects.create(requested_by_username='boss')
            run_system_backup(backup.pk)
            backup.refresh_from_db()
            self.assertEqual(backup.status, SystemBackup.STATUS_COMPLETED)
            restore = SystemRestore.objects.create(requested_by_username='boss', backup_file_path=backup.file_path)
            from dlux.backup import restore as restore_module
            real = restore_module._wipe_and_load

            def spy(*args, **kwargs):
                seen.append(restore_in_progress())
                return real(*args, **kwargs)

            with mock.patch.object(restore_module, '_wipe_and_load', spy):
                run_system_restore(restore.pk)
        restore.refresh_from_db()
        self.assertEqual(restore.status, SystemRestore.STATUS_COMPLETED, restore.error)
        self.assertEqual(seen, [True])
        self.assertFalse(restore_in_progress())

    def test_a_lost_restore_reports_its_live_progress(self):
        """R2-126 (1): the lost restore said 32% 'reading' while it was at 60%."""
        from django.core.cache import cache
        from dlux.backup.restore import fail_lost_system_restore
        from dlux.db_outage import restore_in_progress, set_restore_in_progress
        from dlux.utils.backup_progress import set_restore_progress

        SystemRestore = apps.get_model('dlux', 'SystemRestore')
        restore = SystemRestore.objects.create(requested_by_username='boss', backup_file_path='x.dlb')
        SystemRestore.objects.filter(pk=restore.pk).update(
            status=SystemRestore.STATUS_RUNNING, progress_percent=32, stage=SystemRestore.STAGE_READING,
        )
        restore.refresh_from_db()
        set_restore_progress(restore, 60, 'Restoring Activity Log (27/36)', stage=SystemRestore.STAGE_DATABASE)
        set_restore_in_progress(restore.token)
        SystemRestore.objects.filter(pk=restore.pk).update(progress_percent=32, stage=SystemRestore.STAGE_READING)
        self.assertTrue(fail_lost_system_restore(restore.pk))
        restore.refresh_from_db()
        self.assertIn('60%', restore.error)
        self.assertEqual(restore.stage, SystemRestore.STAGE_DATABASE)
        self.assertFalse(restore_in_progress())
        cache.clear()


class MigrationMismatchMessageTests(TestCase):
    """R2-114: a refused restore after a rollback gave only a bare English string."""

    def test_the_message_names_the_versions_the_migrations_and_both_ways_out(self):
        from dlux.backup.restore import migration_mismatch_message

        for lang in ('en', 'ar'):
            with self.subTest(lang=lang), mock.patch(
                'dlux.translations.runtime.get_current_language_code', return_value=lang,
            ):
                message = migration_mismatch_message({
                    'missing_on_target': [],
                    'extra_on_target': ['dlux.0031_dluxjob', 'dlux.0032_more'],
                    'backup_dlux_version': '1.17.0b1',
                    'current_dlux_version': '1.16.3',
                })
                self.assertIn('1.17.0b1', message)
                self.assertIn('1.16.3', message)
                self.assertIn('dlux.0031_dluxjob', message)
                from dlux.translations import get_strings
                override = get_strings(lang)['sysrestore_ignore_mismatch'].rstrip('.۔')
                self.assertIn(override, message)


class ProgressSizeLanguageTests(SimpleTestCase):
    """R2-126 (2): an English progress message carried an Arabic size unit."""

    def test_sizes_follow_the_strings_language(self):
        from django.utils import translation
        from dlux.backup.reporters import format_size

        with translation.override('ar'), mock.patch(
            'dlux.translations.runtime.get_current_language_code', return_value='en',
        ):
            self.assertEqual(format_size(8_600_000), '8.2\xa0MB')


import asyncio
import socket
import threading
import time

from django.db import InterfaceError, connection

from dlux import smtp_relay


class RelayConfigAfterDatabaseRestartTests(TestCase):
    """R2-048: after a db restart the relay never read the UI mail settings again."""

    def test_a_dead_connection_is_replaced_and_closed_after_each_read(self):
        from dlux.models import SystemSettings

        real = SystemSettings.load
        calls = []

        def load():
            calls.append(1)
            if len(calls) == 1:
                raise InterfaceError('connection already closed')
            return real()

        # The relay reads on a pool thread, outside any transaction.
        with mock.patch.dict(os.environ, {'DJANGO_SETTINGS_MODULE': 'dlux.tests.settings'}), \
                mock.patch.object(SystemSettings, 'load', side_effect=load), \
                mock.patch.object(connection, 'in_atomic_block', False), \
                mock.patch('django.db.close_old_connections'), \
                mock.patch('django.db.connection.close') as close:
            config = smtp_relay.stored_email_config()
        self.assertIsNotNone(config)
        self.assertEqual(len(calls), 2)
        self.assertGreaterEqual(close.call_count, 2, 'closed after the failure and after the read')

    def test_each_read_retires_a_stale_connection_first(self):
        with mock.patch.dict(os.environ, {'DJANGO_SETTINGS_MODULE': 'dlux.tests.settings'}), \
                mock.patch.object(connection, 'in_atomic_block', False), \
                mock.patch('django.db.close_old_connections') as retire, \
                mock.patch('django.db.connection.close') as close:
            smtp_relay.stored_email_config()
        retire.assert_called_once()
        close.assert_called_once()

    def test_inside_a_transaction_the_callers_connection_is_left_open(self):
        # Closing a connection inside atomic() would end the caller's transaction
        # (on PostgreSQL every later query then fails with "connection already closed").
        self.assertTrue(connection.in_atomic_block)
        with mock.patch.dict(os.environ, {'DJANGO_SETTINGS_MODULE': 'dlux.tests.settings'}), \
                mock.patch('django.db.close_old_connections') as retire, \
                mock.patch('django.db.connection.close') as close:
            self.assertIsNotNone(smtp_relay.stored_email_config())
        retire.assert_not_called()
        close.assert_not_called()


class _Relay:
    """The real relay listener on an ephemeral port, in its own event loop."""

    def __init__(self, **env):
        self.env = mock.patch.dict(os.environ, {k: str(v) for k, v in env.items()})

    def __enter__(self):
        self.env.start()
        smtp_relay._active_connections = 0
        self.loop = asyncio.new_event_loop()
        ready = threading.Event()

        async def start():
            self.server = await asyncio.start_server(
                smtp_relay.handle_client, '127.0.0.1', 0, limit=smtp_relay.max_line_bytes(),
            )
            self.port = self.server.sockets[0].getsockname()[1]
            ready.set()

        self.thread = threading.Thread(target=lambda: (self.loop.run_until_complete(start()), self.loop.run_forever()))
        self.thread.daemon = True
        self.thread.start()
        ready.wait(5)
        return self

    def connect(self):
        sock = socket.create_connection(('127.0.0.1', self.port), timeout=5)
        reader = sock.makefile('rb')
        return sock, reader

    def __exit__(self, *exc):
        self.loop.call_soon_threadsafe(self.server.close)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(5)
        self.env.stop()


class RelayHardeningTests(SimpleTestCase):
    """R2-098: long lines dropped the session with a traceback; no idle timeout, no cap."""

    def test_a_long_command_line_gets_a_reply_not_a_traceback(self):
        with _Relay(SMTP_RELAY_MAX_LINE_BYTES=2048) as relay:
            sock, reader = relay.connect()
            self.assertTrue(reader.readline().startswith(b'220'))
            sock.sendall(b'EHLO ' + b'a' * 10_000 + b'\r\n')
            self.assertEqual(reader.readline(), b'500 Line too long\r\n')
            sock.close()

    def test_a_long_data_line_refuses_the_message_and_keeps_the_session(self):
        with _Relay(SMTP_RELAY_MAX_LINE_BYTES=2048) as relay, \
                mock.patch.object(smtp_relay, 'deliver') as deliver:
            sock, reader = relay.connect()
            reader.readline()
            sock.sendall(b'MAIL FROM:<a@example.invalid>\r\nRCPT TO:<b@example.invalid>\r\nDATA\r\n')
            for _ in range(3):
                reader.readline()
            sock.sendall(b'x' * 10_000 + b'\r\n.\r\nNOOP\r\n')
            self.assertEqual(reader.readline(), b'552 Message exceeds configured size limit\r\n')
            self.assertEqual(reader.readline(), b'250 OK\r\n')
            sock.close()
        deliver.assert_not_called()

    def test_an_idle_connection_is_closed(self):
        with _Relay(SMTP_RELAY_IDLE_TIMEOUT=1) as relay:
            sock, reader = relay.connect()
            reader.readline()
            started = time.monotonic()
            self.assertTrue(reader.readline().startswith(b'421'))
            self.assertEqual(reader.readline(), b'')
            self.assertLess(time.monotonic() - started, 4)
            sock.close()

    def test_connections_over_the_cap_are_turned_away(self):
        with _Relay(SMTP_RELAY_MAX_CONNECTIONS=1) as relay:
            first, first_reader = relay.connect()
            self.assertTrue(first_reader.readline().startswith(b'220'))
            second, second_reader = relay.connect()
            self.assertTrue(second_reader.readline().startswith(b'421'))
            second.close()
            first.close()


class _TarpitProvider:
    """An SMTP server that takes ``delay`` seconds before every reply."""

    def __init__(self, delay):
        self.delay = delay
        self.sock = socket.socket()
        self.sock.bind(('127.0.0.1', 0))
        self.sock.listen(1)
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        try:
            conn, _ = self.sock.accept()
        except OSError:
            return
        with conn:
            reader = conn.makefile('rb')
            try:
                time.sleep(self.delay)
                conn.sendall(b'220 slow\r\n')
                while True:
                    line = reader.readline()
                    if not line:
                        return
                    time.sleep(self.delay)
                    conn.sendall(b'354 go\r\n' if line.upper().startswith(b'DATA') else b'250 ok\r\n')
            except OSError:
                return

    def close(self):
        self.sock.close()


class RelayDeliveryDeadlineTests(SimpleTestCase):
    """R2-098: a tarpit provider kept the relay going after the app gave up."""

    def test_the_timeout_bounds_the_whole_delivery(self):
        provider = _TarpitProvider(delay=0.7)
        self.addCleanup(provider.close)
        upstream = {'host': '127.0.0.1', 'port': provider.port, 'use_tls': False, 'use_ssl': False, 'timeout': 2}
        started = time.monotonic()
        with mock.patch.object(smtp_relay, 'upstream_config', return_value=upstream):
            with self.assertRaises(smtp_relay.SMTPStepError) as caught:
                smtp_relay.deliver('a@example.invalid', ['b@example.invalid'], b'Subject: x\r\n\r\nbody\r\n')
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 3.5, 'each step took 0.7 s, under the 2 s step timeout; the total must still stop at 2 s')
        self.assertIn('2 seconds', str(caught.exception.detail))


from dlux.tests import test_ocr as _ocr_tests


class LostOCRRunTests(_ocr_tests.OCRTestCase):
    """R2-049: a worker killed mid-OCR left the file 'running' for good."""

    def _running_row(self):
        row = self.rows(self.paper()).get()
        type(row).all_objects.filter(pk=row.pk).update(status='running', started_at=timezone.now(), attempts=1)
        row.refresh_from_db()
        return row

    def _task_run(self, row, recoveries):
        from dlux.taskrunner import enqueue

        run_id = enqueue('dlux.tasks.ocr_file', args=(row.pk,))
        apps.get_model('dlux', 'DluxTaskRun').objects.filter(pk=run_id).update(recoveries=recoveries)
        return run_id

    def _run_task(self, run_id, row):
        import dlux.jobs  # noqa: F401
        from dlux.taskrunner import TaskContext, registered_tasks

        task = registered_tasks()['dlux.tasks.ocr_file']
        context = TaskContext(task_name=task.name, run_id=run_id)
        with mock.patch('dlux.ocr.client._opener.open', return_value=_ocr_tests.FakeResponse(_ocr_tests.payload())):
            task.func(context, row.pk)
        row.refresh_from_db()

    def test_a_recovered_run_takes_over_the_dead_claim(self):
        row = self._running_row()
        with self.assertLogs('dlux', level='WARNING'):
            self._run_task(self._task_run(row, recoveries=1), row)
        self.assertEqual(row.status, 'done')
        self.assertTrue(row.text)

    def test_a_fresh_duplicate_run_still_leaves_a_live_claim_alone(self):
        row = self._running_row()
        self._run_task(self._task_run(row, recoveries=0), row)
        self.assertEqual(row.status, 'running')


from dlux.ocr import serve as ocr_serve


class _OCREngine:
    name = version = model_version = 'test'

    def __init__(self):
        self.calls = 0
        self.pages_done = 0

    def convert(self, path, **options):
        self.calls += 1
        cancelled = options.get('cancelled')
        for _ in range(50):
            if cancelled is not None and cancelled():
                break
            time.sleep(0.05)
            self.pages_done += 1
        return {'pages': [{'index': 0, 'source': 'ocr', 'text': 't', 'markdown': 't', 'lines': [], 'timings': {}}]}


class OCRServiceTieUpTests(SimpleTestCase):
    """R2-097: slow-header connections filled the pool; /health went 503; orphans kept the engine."""

    def setUp(self):
        self.engine = _OCREngine()
        for name, value in {
            'ENGINE': self.engine, 'MAX_CONNECTIONS': 2, 'READ_TIMEOUT': 0.6, 'HEADER_DEADLINE': 0.8,
            'QUEUE_WAIT': 0.05, 'SLOTS': threading.BoundedSemaphore(1), 'MIN_UPLOAD_RATE': 1024,
        }.items():
            patcher = mock.patch.object(ocr_serve, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.server = ocr_serve.OCRHTTPServer(('127.0.0.1', 0), ocr_serve.Handler)
        self.server.daemon_threads = True
        thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
        thread.start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close(), thread.join(2)))

    def _connect(self):
        return socket.create_connection(self.server.server_address, timeout=5)

    def _status(self, sock):
        data = b''
        while b'\r\n' not in data:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
        return int(data.split(b' ', 2)[1]) if data else None

    def test_a_trickled_header_is_cut_at_the_header_deadline(self):
        sock = self._connect()
        sock.sendall(b'POST /v1/ocr HTTP/1.1\r\n')
        started = time.monotonic()
        closed = False
        while time.monotonic() - started < 3:
            try:
                sock.sendall(b'X-Slow: 1\r\n')
            except OSError:
                closed = True
                break
            time.sleep(0.3)
            try:
                sock.settimeout(0.01)
                if sock.recv(1) == b'':
                    closed = True
                    break
            except socket.timeout:
                pass
            except OSError:
                closed = True
                break
        sock.close()
        self.assertTrue(closed)
        self.assertLess(time.monotonic() - started, 2.5)

    def test_health_answers_while_slow_connections_fill_the_pool(self):
        held = [self._connect() for _ in range(2)]
        for sock in held:
            sock.sendall(b'POST /v1/ocr HTTP/1.1\r\n')
        time.sleep(0.1)
        probe = self._connect()
        probe.sendall(b'GET /health HTTP/1.1\r\nHost: ocr\r\n\r\n')
        self.assertEqual(self._status(probe), 200)
        probe.close()
        for sock in held:
            sock.close()

    def test_a_trickled_upload_misses_its_deadline(self):
        sock = self._connect()
        sock.sendall(b'POST /v1/ocr HTTP/1.1\r\nHost: ocr\r\nContent-Length: 100\r\n\r\n%PDF-')
        started = time.monotonic()
        status = None
        sock.settimeout(0.2)
        while time.monotonic() - started < 4 and status is None:
            try:
                sock.sendall(b'0')
            except OSError:
                break
            try:
                status = self._status(sock)
            except socket.timeout:
                pass
        sock.close()
        self.assertEqual(status, 408)
        self.assertEqual(self.engine.calls, 0)

    def test_the_engine_stops_when_the_client_is_gone(self):
        sock = self._connect()
        body = b'%PDF-1.4\n%%EOF\n'
        sock.sendall(b'POST /v1/ocr HTTP/1.1\r\nHost: ocr\r\nContent-Length: '
                     + str(len(body)).encode() + b'\r\n\r\n' + body)
        time.sleep(0.2)
        sock.close()
        deadline = time.monotonic() + 3
        while self.engine.calls and time.monotonic() < deadline and ocr_serve.SLOTS._value == 0:
            time.sleep(0.05)
        time.sleep(0.2)
        self.assertEqual(self.engine.calls, 1)
        self.assertLess(self.engine.pages_done, 20)


from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import CommandError

from dlux.management.commands import migrator as migrator_module


class _LockCursor:
    """A cursor answering pg_try_advisory_lock from a script and recording calls."""

    def __init__(self, answers, log):
        self.answers, self.log = answers, log

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.log.append(sql.split('(')[0].split()[-1])
        self._last = sql

    def fetchone(self):
        return (self.answers.pop(0) if 'try' in self._last else True,)


class MigratorLockTests(SimpleTestCase):
    """R2-099: two migrators at once, one failed with 'relation already exists'."""

    def _command(self):
        return migrator_module.Command(stdout=StringIO(), stderr=StringIO())

    def _connection(self, answers, log):
        fake = mock.Mock(vendor='postgresql')
        fake.cursor.side_effect = lambda: _LockCursor(answers, log)
        return mock.patch.object(migrator_module, 'connection', fake)

    def test_the_second_run_waits_for_the_lock_and_releases_it(self):
        log, ran = [], []
        command = self._command()
        with self._connection([False, False, True], log), \
                mock.patch.object(migrator_module, 'MIGRATOR_LOCK_POLL_SECONDS', 0), \
                mock.patch.object(command, 'resolve_target_apps', return_value=[]), \
                mock.patch.object(command, 'initialize', side_effect=lambda *a: ran.append(list(log))):
            command.handle(app=None, make_migrations=False, no_migrate=False)
        self.assertEqual(ran, [['pg_try_advisory_lock'] * 3], 'the run starts only once the lock is held')
        self.assertEqual(log[-1], 'pg_advisory_unlock')
        self.assertIn('Another migrator is running', command.stdout.getvalue())

    def test_a_lock_held_too_long_fails_clearly(self):
        log = []
        command = self._command()
        with self._connection([False] * 10, log), \
                mock.patch.object(migrator_module, 'MIGRATOR_LOCK_POLL_SECONDS', 0), \
                mock.patch.dict(os.environ, {'DLUX_MIGRATOR_LOCK_TIMEOUT': '0'}), \
                mock.patch.object(command, 'resolve_target_apps', return_value=[]), \
                mock.patch.object(command, 'initialize') as initialize:
            with self.assertRaises(CommandError) as caught:
                command.handle(app=None, make_migrations=False, no_migrate=False)
        initialize.assert_not_called()
        self.assertIn('DLUX_MIGRATOR_LOCK_TIMEOUT', str(caught.exception))

    def test_the_lock_is_released_when_the_run_fails(self):
        log = []
        command = self._command()
        with self._connection([True], log), \
                mock.patch.object(command, 'resolve_target_apps', return_value=[]), \
                mock.patch.object(command, 'initialize', side_effect=RuntimeError('migrate failed')):
            with self.assertRaises(RuntimeError):
                command.handle(app=None, make_migrations=False, no_migrate=False)
        self.assertEqual(log, ['pg_try_advisory_lock', 'pg_advisory_unlock'])


class MigratorSuperuserEmailTests(TestCase):
    """R2-039: the auto-created superuser got a real organisation's mailbox."""

    def test_no_address_unless_admin_email_is_set(self):
        command = migrator_module.Command(stdout=StringIO(), stderr=StringIO())
        with mock.patch.dict(os.environ, {'ADMIN_PASS': 'a-test-pass-123'}):
            os.environ.pop('ADMIN_EMAIL', None)
            command.ensure_superuser([])
        self.assertEqual(get_user_model().objects.get(username='admin').email, '')
        source = open(migrator_module.__file__, encoding='utf-8').read()
        self.assertNotIn('.gov.', source)

    def test_admin_email_sets_the_address(self):
        command = migrator_module.Command(stdout=StringIO(), stderr=StringIO())
        with mock.patch.dict(os.environ, {'ADMIN_PASS': 'a-test-pass-123', 'ADMIN_EMAIL': 'ops@example.invalid'}):
            command.ensure_superuser([])
        self.assertEqual(get_user_model().objects.get(username='admin').email, 'ops@example.invalid')


import json
from pathlib import Path

from dlux import doctor


def crm_like_context(request):
    from dlux.context_processors import dlux_context

    context = dict(dlux_context(request))
    context['crm'] = True
    return context


def unrelated_context(request):
    return {'other': True}


def _templates(*processors):
    return [{
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'APP_DIRS': True,
        'OPTIONS': {'context_processors': ['django.template.context_processors.request', *processors]},
    }]


class DoctorContextProcessorTests(SimpleTestCase):
    """R2-113: a false 'context processor missing' on CRM sales."""

    def test_a_processor_that_calls_dlux_context_counts(self):
        with override_settings(TEMPLATES=_templates('dlux.tests.test_ops_resilience.crm_like_context')):
            finding = doctor._check_context_processors(None)
        self.assertEqual(finding.status, doctor.OK)
        self.assertIn('crm_like_context', finding.detail)

    def test_a_processor_that_does_not_still_fails(self):
        with override_settings(TEMPLATES=_templates('dlux.tests.test_ops_resilience.unrelated_context')):
            self.assertEqual(doctor._check_context_processors(None).status, doctor.ERROR)


class _Cursor:
    def __init__(self, row):
        self.row = row

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, *args):
        pass

    def fetchone(self):
        return self.row


class DoctorDatabaseWritableTests(SimpleTestCase):
    """R2-045: on a read-only database the doctor said 'reachable' and blamed the worker."""

    def _finding(self, row):
        fake = mock.Mock(vendor='postgresql')
        fake.cursor.side_effect = lambda: _Cursor(row)
        ctx = mock.Mock(db_available=True)
        with mock.patch('django.db.connection', fake):
            return doctor._check_db_writable(ctx)

    def test_read_only_transactions_are_an_error(self):
        finding = self._finding((False, 'on'))
        self.assertEqual(finding.status, doctor.ERROR)
        self.assertIn('read-only', finding.detail)

    def test_a_standby_is_an_error(self):
        self.assertIn('standby', self._finding((True, 'off')).detail)

    def test_a_writable_primary_is_ok(self):
        self.assertEqual(self._finding((False, 'off')).status, doctor.OK)


class DoctorComposerPairTests(SimpleTestCase):
    """R2-102: with composer-agent stopped the doctor said the policy was enforced."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        (self.root / 'agent').mkdir()
        for target in ('dlux.updater.runtime.state_dir', 'dlux.updater.policy.state_dir'):
            patcher = mock.patch(target, return_value=self.root)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _status(self, minutes_ago, **extra):
        observed = (timezone.now() - timedelta(minutes=minutes_ago)).isoformat()
        (self.root / 'agent' / 'agent-status.json').write_text(json.dumps({
            'composer_version': '1.11.0b3', 'observed_at': observed, 'update_policy': 'inline', **extra,
        }))

    def test_no_pair_is_skipped(self):
        self.assertEqual(doctor._check_composer_pair(None).status, doctor.SKIPPED)

    def test_a_silent_agent_is_a_warning(self):
        self._status(10, heartbeat_seconds=60)
        finding = doctor._check_composer_pair(None)
        self.assertEqual(finding.status, doctor.WARNING)
        self.assertIn('10 min', finding.detail)

    def test_a_reporting_agent_is_ok(self):
        self._status(0.5, heartbeat_seconds=60)
        self.assertEqual(doctor._check_composer_pair(None).status, doctor.OK)

    def test_an_agent_without_a_heartbeat_is_not_judged_by_age(self):
        self._status(600)
        finding = doctor._check_composer_pair(None)
        self.assertEqual(finding.status, doctor.OK)
        self.assertIn('not checked', finding.detail)

    def test_the_policy_row_warns_when_the_pair_is_silent(self):
        self._status(10, heartbeat_seconds=60)
        with override_settings(DLUX_UPDATE_POLICY='inline'):
            finding = doctor._check_update_policy(None)
        self.assertEqual(finding.status, doctor.WARNING)
        self.assertIn('last reported', finding.detail)


class DoctorOCRServiceTests(SimpleTestCase):
    """R2-102: no doctor row for the OCR service."""

    def _finding(self, enabled, health):
        options = {'enabled': enabled, 'service_url': 'http://ocr:8080'}
        with mock.patch('dlux.ocr.config', return_value=options), \
                mock.patch('dlux.ocr.client.service_health', return_value=health):
            return doctor._check_ocr_service(mock.Mock(db_available=True))

    def test_off_is_skipped(self):
        self.assertEqual(self._finding(False, None).status, doctor.SKIPPED)

    def test_on_but_silent_is_an_error(self):
        self.assertEqual(self._finding(True, None).status, doctor.ERROR)

    def test_an_engine_missing_is_an_error(self):
        self.assertEqual(self._finding(True, {'status': 'unavailable', 'error': 'not installed'}).status, doctor.ERROR)

    def test_a_healthy_engine_is_ok(self):
        finding = self._finding(True, {'status': 'ok', 'engine': 'indra-ocr', 'engine_version': '1.1'})
        self.assertEqual(finding.status, doctor.OK)


class WorkerHealthcheckTests(SimpleTestCase):
    """R2-102: the worker healthcheck stayed healthy while the worker could not reach db."""

    def test_check_fails_when_the_database_does_not_answer(self):
        from django.core.management import call_command

        with mock.patch('django.db.connection.ensure_connection', side_effect=OperationalError('could not translate host name "db"')):
            with self.assertRaises(CommandError) as caught:
                call_command('dlux_worker', '--check', stdout=StringIO())
        self.assertIn('database does not answer', str(caught.exception))


class DatabaseResilienceSettingsTests(SimpleTestCase):
    """R2-045: no connect_timeout or keepalives, and no database outage middleware."""

    def _scope(self, **extra):
        return {
            'SECRET_KEY': 'x' * 50,
            'INSTALLED_APPS': [],
            'MIDDLEWARE': ['django.contrib.sessions.middleware.SessionMiddleware'],
            'TEMPLATES': [],
            'DATABASES': {
                'default': {'ENGINE': 'django.db.backends.postgresql', 'NAME': 'x', 'OPTIONS': {'connect_timeout': 2}},
                'other': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'},
            },
            **extra,
        }

    def test_postgres_gets_bounded_waits_and_the_middleware(self):
        from dlux.utils.settings import dlux_settings

        scope = dlux_settings(self._scope())
        options = scope['DATABASES']['default']['OPTIONS']
        self.assertEqual(options['connect_timeout'], 2, 'a value the settings file sets is kept')
        self.assertEqual(options['keepalives'], 1)
        self.assertNotIn('OPTIONS', scope['DATABASES']['other'])
        middleware = scope['MIDDLEWARE']
        self.assertEqual(
            middleware.index('dlux.db_outage.DatabaseOutageMiddleware') + 1,
            middleware.index('django.contrib.sessions.middleware.SessionMiddleware'),
        )
        self.assertEqual(dlux_settings(scope)['MIDDLEWARE'].count('dlux.db_outage.DatabaseOutageMiddleware'), 1)

    def test_the_opt_out_keeps_everything_as_written(self):
        from dlux.utils.settings import dlux_settings

        scope = dlux_settings(self._scope(DLUX_DB_FAIL_FAST=False))
        self.assertNotIn('keepalives', scope['DATABASES']['default']['OPTIONS'])
        self.assertNotIn('dlux.db_outage.DatabaseOutageMiddleware', scope['MIDDLEWARE'])


class ConnectBreakerTests(SimpleTestCase):
    """R2-045 live proof: with db paused, one page waited out connect_timeout once per read (25 s)."""

    def setUp(self):
        from dlux import db_outage

        db_outage.install_connect_breaker()
        db_outage._connect_failed_at.clear()
        self.addCleanup(db_outage._connect_failed_at.clear)

    def test_a_failed_connect_fails_the_next_ones_at_once_then_retries(self):
        import sqlite3

        from django.db import connections
        from django.db.backends.sqlite3.base import DatabaseWrapper
        from dlux import db_outage

        wrapper = DatabaseWrapper({**connections['default'].settings_dict}, alias='breaker-test')
        attempts = []

        def refuse(self, params):
            attempts.append(1)
            raise sqlite3.OperationalError('timeout expired')

        with mock.patch.object(DatabaseWrapper, 'get_new_connection', refuse):
            with self.assertRaises(OperationalError):
                wrapper.ensure_connection()
            started = time.monotonic()
            with self.assertRaises(db_outage.DatabaseUnavailable):
                wrapper.ensure_connection()
            self.assertLess(time.monotonic() - started, 0.5)
            self.assertEqual(len(attempts), 1)
            db_outage._connect_failed_at['breaker-test'] -= 60
            with self.assertRaises(OperationalError):
                wrapper.ensure_connection()
            self.assertEqual(len(attempts), 2, 'after the window it tries again')
        self.assertTrue(db_outage.is_database_outage(db_outage.DatabaseUnavailable('x')))

    def test_a_non_driver_error_does_not_trip_it(self):
        from django.db import connections
        from django.db.backends.sqlite3.base import DatabaseWrapper
        from dlux import db_outage

        wrapper = DatabaseWrapper({**connections['default'].settings_dict}, alias='breaker-test-2')
        with mock.patch.object(DatabaseWrapper, 'get_new_connection', side_effect=RuntimeError('mock')):
            with self.assertRaises(RuntimeError):
                wrapper.ensure_connection()
        self.assertNotIn('breaker-test-2', db_outage._connect_failed_at)


class RestoreErrorTranslationTests(TestCase):
    """R2-110 (restore half): restore failures were stored as bare English text."""

    def test_backup_errors_are_stored_in_the_operator_language(self):
        from dlux.backup.errors import BackupError
        from dlux.backup.restore import restore_error_message

        exc = BackupError(
            'sysrestore_error_chain_incomplete',
            'Backup chain is incomplete: member {position} of {sequence} is missing from the backup folder',
            position=1, sequence=3,
        )
        self.assertIn('member 1 of 3', str(exc), 'str() stays English for logs')
        self.assertIsInstance(exc, ValueError)
        with mock.patch('dlux.translations.runtime.get_current_language_code', return_value='ar'):
            arabic = restore_error_message(exc)
            unexpected = restore_error_message(RuntimeError('boom'))
        self.assertIn('سلسلة النسخ غير مكتملة', arabic)
        self.assertIn('boom', unexpected)
        self.assertIn('خطأ غير متوقع', unexpected)

    def test_a_missing_file_fails_the_restore_with_the_translated_text(self):
        from dlux.backup.restore import run_system_restore

        SystemRestore = apps.get_model('dlux', 'SystemRestore')
        restore = SystemRestore.objects.create(requested_by_username='boss', backup_file_path='gone.dlb')
        with mock.patch('dlux.translations.runtime.get_current_language_code', return_value='ar'), \
                self.assertLogs('dlux', level='ERROR'):
            run_system_restore(restore.pk)
        restore.refresh_from_db()
        self.assertEqual(restore.status, SystemRestore.STATUS_FAILED)
        self.assertEqual(restore.error, 'ملف النسخة الاحتياطية غير موجود في التخزين')


class MigratorDefaultPasswordTests(TestCase):
    """R2-039 (password half): the superuser fell back to the password 'admin'."""

    def _ensure(self, env):
        command = migrator_module.Command(stdout=StringIO(), stderr=StringIO())
        warnings = []
        with mock.patch.dict(os.environ, env):
            if 'ADMIN_PASS' not in env:
                os.environ.pop('ADMIN_PASS', None)
            command.ensure_superuser(warnings)
        return command.stdout.getvalue(), warnings

    def test_no_superuser_without_a_real_password(self):
        for env in ({}, {'ADMIN_PASS': ''}, {'ADMIN_PASS': 'admin'}):
            with self.subTest(env=env):
                output, warnings = self._ensure(env)
                self.assertFalse(get_user_model().objects.filter(username='admin').exists())
                self.assertIn('No superuser created', output)
                self.assertIn('createsuperuser', warnings[0])
                self.assertIn('.secrets/.env', warnings[0])

    def test_an_existing_admin_is_never_touched(self):
        user = get_user_model().objects.create_superuser('admin', '', 'kept-pass-123')
        output, warnings = self._ensure({'ADMIN_PASS': 'admin'})
        user.refresh_from_db()
        self.assertTrue(user.check_password('kept-pass-123'))
        self.assertIn('already exists', output)
        self.assertEqual(warnings, [])


class ConfigOutageLoggingTests(TestCase):
    """Runtime-recovery follow-up: a database outage logs once, not a traceback per config build."""

    def setUp(self):
        from dlux.utils import config

        self.config = config
        from dlux import db_errors

        self.db_errors = db_errors
        config._config_db_outage = False
        db_errors.clear_read_failure()
        self.addCleanup(setattr, config, '_config_db_outage', False)
        self.addCleanup(db_errors.clear_read_failure)

    def _build_while_down(self, times, build=None):
        from django.db.utils import OperationalError

        SystemSettings = apps.get_model('dlux', 'SystemSettings')
        refused = OperationalError('connection to server failed: Connection refused\n\tIs the server running?')
        objects = mock.Mock()
        objects.filter.side_effect = refused
        with mock.patch.object(SystemSettings, 'load', side_effect=refused) as load, \
                mock.patch.object(SystemSettings, 'objects', objects):
            for _ in range(times):
                (build or self.config._build_system_config)()
        return load.call_count + objects.filter.call_count

    def test_outside_a_request_one_failed_read_stops_the_rest_for_the_breaker_window(self):
        """Runtime-recovery: ~200 translated strings in `manage.py check` each rebuilt
        the config and tried the database twice, 400 connection attempts in all."""
        with self.assertLogs('dlux', level='DEBUG'):
            attempts = self._build_while_down(200, build=self.config.get_system_config)
        self.assertEqual(attempts, 1)
        self.db_errors._read_failed_at -= 60
        with self.assertLogs('dlux', level='DEBUG'):
            self.assertEqual(self._build_while_down(1), 1, 'past the window the database is tried again')

    def test_one_failed_font_read_stops_config_and_scope_reads_and_logs_one_line(self):
        """`manage.py check` with no database: the font list, System Settings and
        ScopeSettings each tried it, 5 connect timeouts (26 s) for one check."""
        from django.db.utils import OperationalError

        from dlux import fonts
        from dlux.utils.common import get_scope_settings

        refused = OperationalError('connection to server failed: timeout expired')
        SystemSettings = apps.get_model('dlux', 'SystemSettings')
        ScopeSettings = apps.get_model('dlux', 'ScopeSettings')
        FontFamily = apps.get_model('dlux', 'ManagedFontFamily')
        fonts.clear_font_cache()
        self.addCleanup(fonts.clear_font_cache)
        with mock.patch.object(FontFamily.objects, 'filter', side_effect=refused) as font_read, \
                mock.patch.object(SystemSettings, 'load', side_effect=refused) as config_read, \
                mock.patch.object(ScopeSettings, 'load', side_effect=refused) as scope_read, \
                self.assertLogs('dlux', level='DEBUG') as logs:
            fonts.get_available_fonts()
            for _ in range(50):
                self.config.get_system_config()
                self.assertIsNone(get_scope_settings())
        self.assertEqual((font_read.call_count, config_read.call_count, scope_read.call_count), (1, 0, 0))
        loud = [record.getMessage() for record in logs.records if record.levelno >= 30]
        self.assertEqual(len(loud), 1, loud)
        self.assertIn('OperationalError: connection to server failed: timeout expired', loud[0])

    def test_a_missing_sqlite_table_is_not_an_outage(self):
        from django.db.utils import OperationalError

        self.assertFalse(self.db_errors.note_read_failure(OperationalError('no such table: dlux_scopesettings')))
        self.assertFalse(self.db_errors.read_recently_failed())

    def test_a_request_still_tries_the_database(self):
        from django.test import RequestFactory

        with self.assertLogs('dlux', level='DEBUG'):
            self._build_while_down(1)
        with mock.patch.object(self.config, '_current_request', return_value=RequestFactory().get('/')), \
                self.assertLogs('dlux', level='DEBUG'):
            self.assertEqual(self._build_while_down(1), 1)

    def test_outage_logs_one_warning_without_traceback(self):
        with self.assertLogs('dlux', level='DEBUG') as logs:
            self._build_while_down(5)
        loud = [record for record in logs.records if record.levelno >= 30]
        self.assertEqual(len(loud), 1, [record.getMessage() for record in loud])
        self.assertIsNone(loud[0].exc_info)
        self.assertIn('Connection refused', loud[0].getMessage())
        self.assertNotIn('\n', loud[0].getMessage())

    @override_settings(DLUX_DB_BREAKER_SECONDS=0)
    def test_recovery_logs_one_line_then_a_new_outage_warns_again(self):
        with self.assertLogs('dlux', level='DEBUG'):
            self._build_while_down(2)
        with self.assertLogs('dlux', level='INFO') as logs:
            self.config._build_system_config()
            self.config._build_system_config()
        answered = [record for record in logs.records if 'answers again' in record.getMessage()]
        self.assertEqual(len(answered), 1)
        with self.assertLogs('dlux', level='WARNING') as logs:
            self._build_while_down(3)
        self.assertEqual(len(logs.records), 1)

    def test_other_errors_keep_their_traceback(self):
        SystemSettings = apps.get_model('dlux', 'SystemSettings')
        with mock.patch.object(SystemSettings, 'load', side_effect=RuntimeError('bad row')), \
                self.assertLogs('dlux', level='WARNING') as logs:
            self.config._build_system_config()
        self.assertTrue(any(record.exc_info for record in logs.records))
        self.assertFalse(self.config._config_db_outage)


import signal
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


class _RelayProcess:
    """``python -m dlux.smtp_relay`` as its own process, on the environment route."""

    def __init__(self, **env):
        probe = socket.socket()
        probe.bind(('127.0.0.1', 0))
        self.port = probe.getsockname()[1]
        probe.close()
        environ = {k: v for k, v in os.environ.items() if k != 'DJANGO_SETTINGS_MODULE'}
        environ.update({
            'PYTHONPATH': str(_REPO_ROOT), 'PYTHONUNBUFFERED': '1',
            'SMTP_RELAY_LISTEN_HOST': '127.0.0.1', 'SMTP_RELAY_LISTEN_PORT': str(self.port),
        })
        environ.update({k: str(v) for k, v in env.items()})
        self.proc = subprocess.Popen(
            [sys.executable, '-m', 'dlux.smtp_relay'], cwd=str(_REPO_ROOT), env=environ,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        ready = self.proc.stdout.readline()
        if b'listening' not in ready:
            self.proc.kill()
            raise AssertionError(f'relay did not start: {ready!r}')

    def connect(self):
        sock = socket.create_connection(('127.0.0.1', self.port), timeout=10)
        reader = sock.makefile('rb')
        assert reader.readline().startswith(b'220')
        return sock, reader

    def terminate(self):
        self.started = time.monotonic()
        self.proc.send_signal(signal.SIGTERM)

    def wait(self, timeout):
        rc = self.proc.wait(timeout)
        self.elapsed = time.monotonic() - self.started
        self.output = self.proc.stdout.read().decode(errors='replace')
        return rc

    def close(self):
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait(5)
        self.proc.stdout.close()


class RelayStopsOnSigtermTests(SimpleTestCase):
    """R2-073 (smtp-relay half): as PID 1 the relay ignored SIGTERM, so `docker stop` killed it."""

    MESSAGE = (b'MAIL FROM:<a@example.invalid>\r\nRCPT TO:<b@example.invalid>\r\nDATA\r\n'
               b'Subject: r2-073\r\n\r\nbody\r\n.\r\n')

    def _relay(self, **env):
        relay = _RelayProcess(**env)
        self.addCleanup(relay.close)
        return relay

    def _provider(self, delay):
        provider = _TarpitProvider(delay)
        self.addCleanup(provider.close)
        return {'SMTP_RELAY_HOST': '127.0.0.1', 'SMTP_RELAY_PORT': provider.port,
                'SMTP_RELAY_USE_TLS': 'False', 'SMTP_RELAY_USE_SSL': 'False'}

    def test_sigterm_closes_idle_connections_and_exits_zero(self):
        relay = self._relay()
        sock, reader = relay.connect()
        self.addCleanup(sock.close)
        relay.terminate()
        self.assertEqual(relay.wait(5), 0)
        self.assertLess(relay.elapsed, 3)
        self.assertTrue(reader.readline().startswith(b'421'))
        self.assertIn('Dlux SMTP relay stopped', relay.output)

    def test_a_delivery_under_way_finishes_before_the_exit(self):
        relay = self._relay(**self._provider(delay=0.3))
        sock, reader = relay.connect()
        self.addCleanup(sock.close)
        sock.sendall(self.MESSAGE)
        for _ in range(3):
            reader.readline()
        time.sleep(0.5)
        relay.terminate()
        time.sleep(0.2)
        with self.assertRaises(OSError):
            socket.create_connection(('127.0.0.1', relay.port), timeout=2).close()
        self.assertEqual(reader.readline(), b'250 Message accepted\r\n')
        self.assertTrue(reader.readline().startswith(b'421'))
        self.assertEqual(relay.wait(8), 0)

    def test_a_delivery_stuck_before_the_greeting_is_given_up_with_421(self):
        relay = self._relay(SMTP_RELAY_DRAIN_SECONDS=1, SMTP_RELAY_UPSTREAM_TIMEOUT=60, **self._provider(delay=5))
        sock, reader = relay.connect()
        self.addCleanup(sock.close)
        sock.sendall(self.MESSAGE)
        for _ in range(3):
            reader.readline()
        time.sleep(0.3)
        relay.terminate()
        self.assertEqual(relay.wait(6), 0)
        self.assertLess(relay.elapsed, 3.5)
        # Stalled before the provider's greeting: the relay gives up on it and
        # tells the client to retry.
        self.assertTrue(reader.readline().startswith(b'421'))

    def test_a_delivery_stalled_after_the_greeting_is_answered_451(self):
        provider = _StallAfterBodyProvider()
        self.addCleanup(provider.close)
        relay = self._relay(
            SMTP_RELAY_DRAIN_SECONDS=1, SMTP_RELAY_UPSTREAM_TIMEOUT=60,
            SMTP_RELAY_HOST='127.0.0.1', SMTP_RELAY_PORT=provider.port,
            SMTP_RELAY_USE_TLS='False', SMTP_RELAY_USE_SSL='False',
        )
        sock, reader = relay.connect()
        self.addCleanup(sock.close)
        sock.sendall(self.MESSAGE)
        for _ in range(3):
            reader.readline()
        self.assertTrue(provider.stalled.wait(5))
        relay.terminate()
        self.assertEqual(relay.wait(6), 0)
        self.assertLess(relay.elapsed, 3.5)
        reply = reader.readline()
        self.assertTrue(reply.startswith(b'451'), reply)
        self.assertIn(b'relay stopped', reply)


class _StallAfterBodyProvider:
    """An SMTP server that answers at once, then never acknowledges the message body."""

    def __init__(self):
        self.stalled = threading.Event()
        self.sock = socket.socket()
        self.sock.bind(('127.0.0.1', 0))
        self.sock.listen(1)
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        try:
            conn, _ = self.sock.accept()
        except OSError:
            return
        with conn:
            reader = conn.makefile('rb')
            try:
                conn.sendall(b'220 quick\r\n')
                in_data = False
                while True:
                    line = reader.readline()
                    if not line:
                        return
                    if in_data:
                        if line == b'.\r\n':
                            self.stalled.set()
                            reader.readline()
                            return
                        continue
                    if line.upper().startswith(b'DATA'):
                        in_data = True
                        conn.sendall(b'354 go\r\n')
                    else:
                        conn.sendall(b'250 ok\r\n')
            except OSError:
                return

    def close(self):
        self.sock.close()
