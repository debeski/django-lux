"""Long or unbounded work kept off web's request threads."""
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings


class ApiStatusProbeTests(TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_no_url_means_no_row(self):
        from dlux.utils.api_status import cached_api_status

        self.assertIsNone(cached_api_status())

    @override_settings(DLUX_API_STATUS_URL="http://api.internal/health")
    def test_web_never_opens_the_connection_and_queues_the_worker(self):
        from dlux.utils.api_status import cached_api_status

        with mock.patch("urllib.request.urlopen") as urlopen, \
                mock.patch("dlux.taskrunner.worker_alive", return_value=True), \
                mock.patch("dlux.taskrunner.enqueue") as enqueue:
            first = cached_api_status()
            second = cached_api_status()
        urlopen.assert_not_called()
        self.assertEqual(first["state"], "unknown")
        self.assertEqual(first["note_key"], "service_api_pending")
        self.assertEqual(second["state"], "unknown")
        enqueue.assert_called_once_with("dlux.tasks.api_status_probe")

    @override_settings(DLUX_API_STATUS_URL="http://api.internal/health", DEBUG=False)
    def test_without_a_worker_it_says_so(self):
        from dlux.utils.api_status import cached_api_status

        with mock.patch("urllib.request.urlopen") as urlopen, \
                mock.patch("dlux.taskrunner.worker_alive", return_value=False):
            status = cached_api_status()
        urlopen.assert_not_called()
        self.assertEqual(status["note_key"], "service_api_no_worker")

    @override_settings(DLUX_API_STATUS_URL="http://api.internal/health")
    def test_the_worker_result_is_what_options_shows(self):
        from dlux.jobs import api_status_probe
        from dlux.utils.api_status import cached_api_status

        response = mock.MagicMock(status=200)
        response.__enter__.return_value = response
        with mock.patch("urllib.request.urlopen", return_value=response):
            api_status_probe.call()
        with mock.patch("urllib.request.urlopen") as urlopen, \
                mock.patch("dlux.taskrunner.enqueue") as enqueue:
            status = cached_api_status()
        urlopen.assert_not_called()
        enqueue.assert_not_called()
        self.assertEqual(status["state"], "online")

    def test_a_changed_url_does_not_reuse_the_old_answer(self):
        from dlux.utils import api_status

        cache.set(api_status.CACHE_KEY, {"state": "online", "url": "http://old/", "checked_at": 9e12})
        with override_settings(DLUX_API_STATUS_URL="http://new/"), \
                mock.patch("dlux.taskrunner.worker_alive", return_value=True), \
                mock.patch("dlux.taskrunner.enqueue"):
            self.assertEqual(api_status.cached_api_status()["state"], "unknown")


class RelayGreetingCacheTests(TestCase):
    def setUp(self):
        from dlux.utils import mail

        mail._relay_answers.clear()
        self.addCleanup(mail._relay_answers.clear)

    def test_the_settings_form_reuses_a_recent_answer(self):
        from dlux.utils import internal_smtp_relay_greeting, mail

        key = ("relay-cache.test", 2525)
        with mock.patch.object(mail, "_smtp_relay_greeting", return_value="dlux smtp relay ready") as probe:
            first = internal_smtp_relay_greeting(*key, max_age=10)
            second = internal_smtp_relay_greeting(*key, max_age=10)
        self.assertEqual(first, "dlux smtp relay ready")
        self.assertEqual(second, first)
        self.assertEqual(probe.call_count, 1)

    def test_a_negative_answer_is_reused_and_expires(self):
        from dlux.utils import internal_smtp_relay_greeting, mail

        key = ("relay-cache.test", 2526)
        with mock.patch.object(mail, "_smtp_relay_greeting", return_value=None) as probe:
            self.assertIsNone(internal_smtp_relay_greeting(*key, max_age=10))
            self.assertIsNone(internal_smtp_relay_greeting(*key, max_age=10))
            self.assertEqual(probe.call_count, 1)
            mail._relay_answers[key] = (mail.time.monotonic() - 11, None)
            self.assertIsNone(internal_smtp_relay_greeting(*key, max_age=10))
            self.assertEqual(probe.call_count, 2)

    def test_callers_without_max_age_always_probe(self):
        from dlux.utils import internal_smtp_relay_greeting, mail

        key = ("relay-cache.test", 2527)
        with mock.patch.object(mail, "_smtp_relay_greeting", return_value="220 ready") as probe:
            internal_smtp_relay_greeting(*key)
            internal_smtp_relay_greeting(*key)
        self.assertEqual(probe.call_count, 2)

    def test_the_form_asks_with_a_max_age(self):
        from dlux.forms.system_settings import SystemSettingsForm
        from dlux.utils.mail import DLUX_SMTP_RELAY_GREETING_MAX_AGE

        with mock.patch("dlux.utils.internal_smtp_relay_greeting", return_value=None) as probe:
            SystemSettingsForm()
        probe.assert_called_with(max_age=DLUX_SMTP_RELAY_GREETING_MAX_AGE)


from dlux.tests.test_ocr import OCRTestCase  # noqa: E402


class OCRHashOnTheWorkerTests(OCRTestCase):
    def test_a_save_with_a_worker_queues_the_check_and_hashes_nothing(self):
        from dlux.tests.document_files_app.models import Paper

        with mock.patch("dlux.taskrunner.worker_alive", return_value=True), \
                mock.patch("dlux.taskrunner.enqueue") as enqueue, \
                mock.patch("dlux.ocr.service.file_sha256") as digest:
            paper = self.paper()
        digest.assert_not_called()
        self.assertFalse(self.rows(paper).exists())
        name, = {call.args[0] for call in enqueue.call_args_list}
        self.assertEqual(name, "dlux.tasks.ocr_saved_document")
        args = enqueue.call_args.kwargs["args"]
        self.assertEqual(args, ("document_files_app.paper", paper.pk, ["pdf_file"]))
        self.assertEqual(enqueue.call_args.kwargs["priority"], -6)

        from dlux.jobs import ocr_saved_document

        with self.captureOnCommitCallbacks(execute=True):
            ocr_saved_document.call(*args)
        row = self.rows(paper).get()
        self.assertEqual(row.status, "pending")
        self.assertTrue(row.is_current)
        self.apply_async.assert_called_once()
        self.assertIs(Paper, row.content_type.model_class())

    def test_without_a_worker_the_save_checks_inline(self):
        paper = self.paper()
        self.assertEqual(self.rows(paper).count(), 1)

    def test_an_unknown_model_label_is_ignored(self):
        from dlux.jobs import ocr_saved_document

        ocr_saved_document.call("missing.model", 1, ["pdf_file"])


class ForcePasswordChangeQueryCountTests(TestCase):
    def test_query_count_does_not_grow_with_users(self):
        from django.contrib.auth import get_user_model
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from dlux.admin_actions.force_password_change import force_password_change_for_all_non_superusers

        User = get_user_model()

        def run():
            with CaptureQueriesContext(connection) as queries:
                force_password_change_for_all_non_superusers()
            return len(queries)

        for index in range(5):
            User.objects.create_user(username=f"few-{index}")
        few = run()
        for index in range(60):
            User.objects.create_user(username=f"many-{index}")
        many = run()
        self.assertEqual(few, many)
        self.assertEqual(
            sum(1 for user in User.objects.filter(is_superuser=False)
                if user.profile.preferences.get("force_password_change") is True),
            65,
        )


class ChainZipStreamTests(TestCase):
    def test_nothing_is_read_before_the_first_chunk_and_the_zip_is_valid(self):
        import io
        import zipfile

        from django.core.files.base import ContentFile
        from django.core.files.storage import default_storage

        from dlux.views.backup import stream_chain_zip

        paths = [
            default_storage.save("dlux_backups/test-chain/base.dlb", ContentFile(b"A" * 5000)),
            default_storage.save("dlux_backups/test-chain/inc-1.dlb", ContentFile(b"B" * 3000)),
        ]
        self.addCleanup(lambda: [default_storage.delete(path) for path in paths])
        with mock.patch("dlux.views.backup.default_storage.open", wraps=default_storage.open) as opened:
            stream = stream_chain_zip(paths, chunk_size=1024)
            opened.assert_not_called()
            first = next(stream)
            self.assertEqual(opened.call_count, 1)
            body = first + b"".join(stream)
        with zipfile.ZipFile(io.BytesIO(body)) as zf:
            self.assertEqual(zf.namelist(), ["base.dlb", "inc-1.dlb"])
            self.assertEqual(zf.read("base.dlb"), b"A" * 5000)
            self.assertEqual(zf.read("inc-1.dlb"), b"B" * 3000)
            self.assertIsNone(zf.testzip())


class BackgroundJobTestCase(TestCase):
    """A live worker is faked: queueing is captured, the task body run on demand."""

    def setUp(self):
        import shutil
        import tempfile

        from dlux.tests.test_data_reset import _configured

        _configured()
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, True)
        override = override_settings(MEDIA_ROOT=media)
        override.enable()
        self.addCleanup(override.disable)
        self.queued = []
        alive = mock.patch("dlux.taskrunner.worker_alive", return_value=True)
        enqueue = mock.patch("dlux.taskrunner.enqueue", side_effect=lambda name, args=(), **kw: self.queued.append((name, list(args))))
        alive.start()
        enqueue.start()
        self.addCleanup(alive.stop)
        self.addCleanup(enqueue.stop)

    def run_queued(self):
        from dlux.jobs import run_background_job

        while self.queued:
            name, args = self.queued.pop(0)
            self.assertEqual(name, "dlux.tasks.run_job")
            run_background_job.call(*args)


class ReportsXlsxJobTests(BackgroundJobTestCase):
    def setUp(self):
        super().setUp()
        from django.contrib.auth import get_user_model

        self.admin = get_user_model().objects.create_superuser("xlsx-admin", "x@example.com", "pw")
        self.client.force_login(self.admin)
        from dlux.tests.document_files_app.models import Paper

        Paper.objects.create(title="ROW-7")

    def test_the_worker_builds_the_workbook_and_the_owner_downloads_it(self):
        from django.urls import reverse

        from dlux.tests.test_report_backup import _load_workbook

        started = self.client.post(reverse("reports_overview_xlsx_start"), {"window": "all"})
        self.assertEqual(started.status_code, 200)
        data = started.json()
        self.assertTrue(data["async"])
        pending = self.client.get(data["status_url"]).json()
        self.assertEqual(pending["status"], "pending")
        self.assertNotIn("download_url", pending)

        self.run_queued()
        done = self.client.get(data["status_url"]).json()
        self.assertEqual(done["status"], "completed")
        self.assertEqual(done["progress_percent"], 100)
        self.assertTrue(done["file_name"].startswith("dlux-entries-all-"))
        response = self.client.get(done["download_url"])
        self.assertEqual(response.status_code, 200)
        self.assertIn("dlux-entries-all-", response["Content-Disposition"])
        workbook = _load_workbook(b"".join(response.streaming_content))
        values = {cell.value for sheet in workbook.worksheets for row in sheet.iter_rows() for cell in row}
        self.assertIn("ROW-7", values)

        from django.contrib.auth import get_user_model

        other = get_user_model().objects.create_superuser("xlsx-other", "o@example.com", "pw")
        self.client.force_login(other)
        self.assertEqual(self.client.get(data["status_url"]).status_code, 404)
        self.assertEqual(self.client.get(done["download_url"]).status_code, 404)

    def test_without_a_worker_the_page_gets_the_synchronous_url(self):
        from django.apps import apps
        from django.urls import reverse

        with mock.patch("dlux.taskrunner.worker_alive", return_value=False):
            data = self.client.post(reverse("reports_overview_xlsx_start"), {"window": "month"}).json()
        self.assertFalse(data["async"])
        self.assertTrue(data["download_url"].startswith(reverse("reports_overview_xlsx")))
        self.assertIn("window=month", data["download_url"])
        self.assertEqual(apps.get_model("dlux", "DluxJob").objects.count(), 0)

    def test_start_needs_reports_permission_and_post(self):
        from django.contrib.auth import get_user_model
        from django.urls import reverse

        plain = get_user_model().objects.create_user("xlsx-plain", password="pw", is_staff=True)
        self.client.force_login(plain)
        self.assertEqual(self.client.post(reverse("reports_overview_xlsx_start"), {"window": "all"}).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("reports_overview_xlsx_start")).status_code, 405)

    def test_the_export_button_starts_a_job(self):
        from django.urls import reverse

        page = self.client.get(reverse("reports_overview")).content.decode()
        self.assertIn(f'data-dlux-job-start-url="{reverse("reports_overview_xlsx_start")}"', page)

    def test_a_user_who_lost_permission_gets_a_failed_job(self):
        from django.urls import reverse

        data = self.client.post(reverse("reports_overview_xlsx_start"), {"window": "all"}).json()
        with mock.patch("dlux.utils.user_can_view_reports", return_value=False):
            self.run_queued()
        from django.apps import apps

        job = apps.get_model("dlux", "DluxJob").objects.get(token=data["token"])
        self.assertEqual(job.status, "failed")
        self.assertFalse(job.file_path)

    def test_finished_jobs_are_pruned_with_their_files(self):
        from django.apps import apps
        from django.core.files.base import ContentFile
        from django.core.files.storage import default_storage
        from django.urls import reverse

        DluxJob = apps.get_model("dlux", "DluxJob")
        paths = []
        for index in range(4):
            path = default_storage.save(f"dlux_backups/jobs/old-{index}.xlsx", ContentFile(b"x"))
            paths.append(path)
            DluxJob.objects.create(kind="reports_xlsx", user=self.admin, status="completed", file_path=path)
        self.client.post(reverse("reports_overview_xlsx_start"), {"window": "all"})
        self.assertEqual(DluxJob.objects.filter(status="completed").count(), 3)
        self.assertEqual(sum(default_storage.exists(path) for path in paths), 3)


class DataResetJobTests(BackgroundJobTestCase):
    def setUp(self):
        super().setUp()
        from django.contrib.auth import get_user_model

        self.su = get_user_model().objects.create_superuser("reset-root", "r@example.com", "pw12345!")
        self.client.force_login(self.su)

    def test_the_reset_is_queued_and_its_outcome_polled(self):
        from django.apps import apps

        ActivityLog = apps.get_model("dlux", "ActivityLog")
        ActivityLog.objects.create(action="CREATE", model_name="Project Entry")
        response = self.client.post(
            "/sys/admin/data-reset/execute/",
            {"current_password": "pw12345!", "models": ["dlux.activitylog"]},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest", REMOTE_ADDR="10.9.8.7",
        )
        self.assertEqual(response.status_code, 202)
        body = response.json()
        self.assertEqual(body["status"], "queued")
        status_url = body["job"]["status_url"]
        self.assertEqual(ActivityLog.objects.filter(model_name="Project Entry").count(), 1, "nothing ran in web")

        with mock.patch("dlux.utils.log_audit_event") as audit:
            self.run_queued()
        job = self.client.get(status_url).json()
        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["result"]["status"], "success")
        self.assertTrue(job["result"]["message"])
        self.assertEqual(ActivityLog.objects.filter(model_name="Project Entry").count(), 0)
        request = audit.call_args.args[0]
        self.assertEqual(request.user, self.su)
        self.assertEqual(request.META["REMOTE_ADDR"], "10.9.8.7")
        self.assertEqual(audit.call_args.args[1:3], ("data_reset", "DELETE"))

    def test_a_lost_worker_fails_the_job(self):
        from django.apps import apps

        from dlux.jobs import background_job_lost

        self.client.post(
            "/sys/admin/data-reset/execute/",
            {"current_password": "pw12345!", "models": ["dlux.activitylog"]},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        job = apps.get_model("dlux", "DluxJob").objects.get()
        background_job_lost(job.pk)
        job.refresh_from_db()
        self.assertEqual(job.status, "failed")
        self.assertTrue(job.error)
        self.run_queued()
        job.refresh_from_db()
        self.assertEqual(job.status, "failed", "a failed job is never claimed again")


class DluxJobBookkeepingTests(TestCase):
    def test_jobs_are_not_data(self):
        from django.apps import apps

        from dlux.admin_actions.data_reset import is_reset_eligible
        from dlux.backup.config import _SYSTEM_BACKUP_EXCLUDED
        from dlux.utils.activity_log import LOG_NEVER_LOGGED_MODEL_KEYS

        DluxJob = apps.get_model("dlux", "DluxJob")
        for label in ("dlux.DluxJob", "dlux.DluxTaskRun", "dlux.DluxTaskWorker"):
            self.assertFalse(is_reset_eligible(apps.get_model(label)), label)
        self.assertIn("dlux.dluxjob", _SYSTEM_BACKUP_EXCLUDED)
        self.assertIn("dlux.dluxjob", LOG_NEVER_LOGGED_MODEL_KEYS)

    def test_the_task_is_registered(self):
        from dlux.taskrunner import registered_tasks

        self.assertIn("dlux.tasks.run_job", registered_tasks())
        self.assertIn("dlux.tasks.ocr_saved_document", registered_tasks())
        self.assertIn("dlux.tasks.api_status_probe", registered_tasks())
