"""Outbound mail runs on ``dlux_worker``: queued, sealed, on its own lane, with an inline fallback."""

from dlux.tests.harness import setup_test_environment

setup_test_environment()

import threading
import time
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.db import connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from dlux.models import DluxNotification, DluxNotificationState, DluxTaskRun, DluxTaskWorker
from dlux.taskrunner import queue, task
from dlux.taskrunner.config import MAIL_PRIORITY, MAIL_QUEUE, runner_config
from dlux.taskrunner.worker import EXPRESS, GENERAL, Worker
from dlux.utils import dispatch_mail_task, queue_dlux_mail

MAIL = override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="dlux@example.com",
)

RESET_TEMPLATES = {
    "subject_template_name": "registration/email/password_reset_subject.txt",
    "email_template_name": "registration/email/password_reset_email.txt",
    "extra_email_context": {"system_name": "X"},
}

RELEASE = threading.Event()
STARTED = threading.Event()


@task(name="tests.mail_offload.hold_a_thread")
def hold_a_thread():
    STARTED.set()
    RELEASE.wait(30)


def live_worker():
    return DluxTaskWorker.objects.create(id="live", heartbeat_at=timezone.now())


@MAIL
class QueueDluxMailTests(TestCase):
    def setUp(self):
        cache.clear()
        mail.outbox = []

    def test_a_live_worker_gets_the_mail_sealed_on_the_mail_queue(self):
        live_worker()
        self.assertTrue(queue_dlux_mail("Your code", "Code: 493817", ["a@example.com"]))
        self.assertEqual(mail.outbox, [])
        run = DluxTaskRun.objects.get()
        self.assertEqual(
            (run.task_name, run.queue_name, run.priority, run.status),
            ("dlux.tasks.send_mail", MAIL_QUEUE, MAIL_PRIORITY, "READY"),
        )
        self.assertNotIn("493817", str(DluxTaskRun.objects.values().get()))

        self.assertEqual(Worker(schedule=False).run_burst(), 1)
        self.assertEqual([(m.subject, m.body, m.to) for m in mail.outbox], [("Your code", "Code: 493817", ["a@example.com"])])
        run.refresh_from_db()
        self.assertEqual((run.status, run.sealed_arguments), ("SUCCESSFUL", ""))

    def test_without_a_worker_it_is_sent_here_once_the_caller_commits(self):
        with self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                self.assertTrue(queue_dlux_mail("Hi", "Body", ["a@example.com"]))
                self.assertEqual(mail.outbox, [])
        self.assertEqual(len(mail.outbox), 1)
        self.assertFalse(DluxTaskRun.objects.exists())

    def test_a_rolled_back_caller_sends_nothing(self):
        live_worker()
        with self.captureOnCommitCallbacks(execute=True):
            try:
                with transaction.atomic():
                    queue_dlux_mail("Hi", "Body", ["a@example.com"])
                    raise RuntimeError("the save failed")
            except RuntimeError:
                pass
        self.assertFalse(DluxTaskRun.objects.exists())
        self.assertEqual(mail.outbox, [])

    def test_a_failed_inline_send_returns_false_and_never_raises(self):
        with mock.patch.object(transaction, "on_commit", side_effect=lambda func, **kw: func()), \
                mock.patch("dlux.utils.mail.send_mail", side_effect=OSError("refused")), \
                mock.patch("dlux.utils.mail._alert_email_delivery_failure") as alert:
            self.assertFalse(queue_dlux_mail("Hi", "Body", ["a@example.com"]))
        alert.assert_called_once()

    def test_no_recipient_queues_nothing(self):
        live_worker()
        self.assertFalse(queue_dlux_mail("Hi", "Body", ["", None]))
        self.assertFalse(DluxTaskRun.objects.exists())

    def test_a_queue_that_cannot_take_the_run_falls_back_to_sending_here(self):
        live_worker()
        with mock.patch("dlux.taskrunner.enqueue", side_effect=RuntimeError("no table")), \
                self.captureOnCommitCallbacks(execute=True):
            self.assertTrue(queue_dlux_mail("Hi", "Body", ["a@example.com"]))
        self.assertEqual(len(mail.outbox), 1)

    def test_a_failure_on_the_worker_alerts_and_fails_the_run(self):
        live_worker()
        queue_dlux_mail("Hi", "Body", ["a@example.com"])
        with mock.patch("dlux.utils.mail.send_mail", side_effect=OSError("refused")), \
                mock.patch("dlux.utils.mail._alert_email_delivery_failure") as alert:
            Worker(schedule=False).run_burst()
        alert.assert_called_once()
        run = DluxTaskRun.objects.get()
        self.assertEqual((run.status, run.sealed_arguments), ("FAILED", ""))

    def test_alert_on_failure_false_reaches_the_worker(self):
        live_worker()
        queue_dlux_mail("Hi", "Body", ["a@example.com"], alert_on_failure=False)
        with mock.patch("dlux.utils.mail.send_mail", side_effect=OSError("refused")), \
                mock.patch("dlux.utils.mail._alert_email_delivery_failure") as alert:
            Worker(schedule=False).run_burst()
        alert.assert_not_called()

    def test_dispatch_runs_the_inline_callable_only_without_a_worker(self):
        inline = mock.Mock()
        live_worker()
        dispatch_mail_task("dlux.tasks.send_notification_emails", [[1]], inline)
        inline.assert_not_called()
        run = DluxTaskRun.objects.get()
        self.assertEqual((run.queue_name, run.priority), (MAIL_QUEUE, MAIL_PRIORITY))


@MAIL
class PublicFormsTests(TestCase):
    """Reset and registration only queue: the response no longer waits on SMTP."""

    def setUp(self):
        cache.clear()
        mail.outbox = []

    def test_password_reset_queues_instead_of_sending(self):
        from dlux.auth.password_reset import DluxPasswordResetForm

        get_user_model().objects.create_user("joe", "joe@example.com", "pw12345!")
        live_worker()
        form = DluxPasswordResetForm({"email": "joe@example.com"})
        self.assertTrue(form.is_valid())
        form.save(domain_override="testserver", **RESET_TEMPLATES)
        self.assertEqual(mail.outbox, [])
        run = DluxTaskRun.objects.get()
        self.assertEqual(run.task_name, "dlux.tasks.send_mail")
        self.assertNotIn("/accounts/reset/", str(DluxTaskRun.objects.values().get()))
        Worker(schedule=False).run_burst()
        self.assertRegex(mail.outbox[0].body, r"/accounts/reset/[^/\s]+/[^/\s]+/")

    def test_a_reset_mail_failure_is_no_longer_a_server_error(self):
        from dlux.auth.password_reset import DluxPasswordResetForm

        get_user_model().objects.create_user("joe", "joe@example.com", "pw12345!")
        form = DluxPasswordResetForm({"email": "joe@example.com"})
        self.assertTrue(form.is_valid())
        with mock.patch.object(transaction, "on_commit", side_effect=lambda func, **kw: func()), \
                mock.patch("dlux.utils.mail.send_mail", side_effect=OSError("refused")), \
                mock.patch("dlux.utils.mail._alert_email_delivery_failure"):
            form.save(domain_override="testserver", **RESET_TEMPLATES)


@MAIL
class NotificationEmailTests(TestCase):
    def setUp(self):
        cache.clear()
        mail.outbox = []
        User = get_user_model()
        self.users = [User.objects.create_user(f"u{i}", f"u{i}@example.com", "pw") for i in range(3)]
        self.users.append(User.objects.create_user("nomail", "", "pw"))

    def _notify(self):
        from dlux.notifications import _create_states, _send_notification_email

        notification = DluxNotification.objects.create(title="Saved", message="Record 7 was saved.")
        states = _create_states(notification, self.users)
        with mock.patch("dlux.utils.get_email_service_status", return_value={"available": True}):
            _send_notification_email(notification, states)
        return states

    def test_each_recipient_gets_a_message_of_their_own(self):
        live_worker()
        states = self._notify()
        self.assertEqual(mail.outbox, [])
        self.assertEqual(
            sorted(DluxNotificationState.objects.filter(pk__in=[s.pk for s in states[:3]]).values_list("email_status", flat=True)),
            ["queued"] * 3,
        )
        Worker(schedule=False).run_burst()
        self.assertEqual(sorted(tuple(m.to) for m in mail.outbox), [("u0@example.com",), ("u1@example.com",), ("u2@example.com",)])
        sent = DluxNotificationState.objects.filter(email_status="sent")
        self.assertEqual(sent.count(), 3)
        self.assertTrue(all(state.emailed_at for state in sent))
        self.assertEqual(DluxNotificationState.objects.get(user__username="nomail").email_status, "")

    def test_without_a_worker_they_go_after_commit(self):
        with self.captureOnCommitCallbacks(execute=True):
            self._notify()
            self.assertEqual(mail.outbox, [])
        self.assertEqual(len(mail.outbox), 3)

    def test_failures_are_recorded_per_recipient_with_one_alert(self):
        live_worker()
        self._notify()
        with mock.patch("dlux.utils.mail.send_mail", side_effect=OSError("refused")), \
                mock.patch("dlux.utils.mail._alert_email_delivery_failure") as alert:
            Worker(schedule=False).run_burst()
        self.assertEqual(DluxNotificationState.objects.filter(email_status="failed").count(), 3)
        alert.assert_called_once()
        self.assertEqual(sorted(alert.call_args.args[1]), ["u0@example.com", "u1@example.com", "u2@example.com"])


class ExpressLaneTests(TestCase):
    def test_every_worker_serves_the_mail_queue_with_a_thread_of_its_own(self):
        self.assertEqual(runner_config()["express_queues"], [MAIL_QUEUE])
        worker = Worker(threads=2, queues=["ocr"], schedule=False)
        self.assertEqual(worker.claim_queues, ["ocr", MAIL_QUEUE])
        self.assertEqual(worker._free_lane(), GENERAL)
        worker._inflight = {object(): GENERAL, object(): GENERAL}
        self.assertEqual(worker._free_lane(), EXPRESS)
        worker._inflight[object()] = EXPRESS
        self.assertIsNone(worker._free_lane())

    def test_the_kept_thread_takes_mail_only(self):
        from dlux.taskrunner import enqueue

        enqueue("tests.mail_offload.hold_a_thread", priority=100)
        enqueue("dlux.tasks.send_mail", args=["s", "b", ["a@example.com"]], priority=MAIL_PRIORITY,
                queue_name=MAIL_QUEUE, sensitive=True)
        worker = Worker(threads=1, schedule=False)
        run = queue.claim_next(worker.id, worker.express_queues)
        self.assertEqual(run.task_name, "dlux.tasks.send_mail")
        self.assertIsNone(queue.claim_next(worker.id, worker.express_queues))

    @override_settings(DLUX_TASK_RUNNER={"express_queues": []})
    def test_the_kept_thread_can_be_given_back(self):
        worker = Worker(threads=1, schedule=False)
        self.assertEqual(worker.express_slots, 0)
        worker._inflight = {object(): GENERAL}
        self.assertIsNone(worker._free_lane())


class SharedConnectionWorker(Worker):
    """Every worker thread uses the test's connection, as LiveServerTestCase does: an
    in-memory SQLite test database is not reliably visible to a new connection."""

    def _share(self):
        connections["default"] = connection_for_threads

    def run(self):
        self._share()
        super().run()

    def execute(self, run):
        self._share()
        super().execute(run)

    def _maintenance_loop(self):
        self._share()
        super()._maintenance_loop()


connection_for_threads = None


@MAIL
class MailLatencyTests(TransactionTestCase):
    """A real worker loop: mail goes out within about a poll interval while every general thread is busy."""

    def test_mail_is_sent_promptly_while_the_general_threads_are_held(self):
        from dlux.taskrunner import enqueue

        cache.clear()
        mail.outbox = []
        RELEASE.clear()
        STARTED.clear()
        global connection_for_threads
        connection_for_threads = connections["default"]
        connection_for_threads.inc_thread_sharing()
        worker = SharedConnectionWorker(threads=1, schedule=False)
        thread = threading.Thread(target=worker.run, daemon=True)
        thread.start()
        try:
            enqueue("tests.mail_offload.hold_a_thread")
            self.assertTrue(STARTED.wait(10), "the holding task never started")
            deadline = time.monotonic() + 10
            while not DluxTaskWorker.objects.filter(stopped_at__isnull=True).exists():
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.05)
            queued_at = time.monotonic()
            self.assertTrue(queue_dlux_mail("Your code", "Code: 112233", ["a@example.com"]))
            self.assertTrue(DluxTaskRun.objects.filter(queue_name=MAIL_QUEUE).exists())
            while not mail.outbox:
                self.assertLess(time.monotonic() - queued_at, 5, "mail waited behind the held thread")
                time.sleep(0.05)
            self.assertLess(time.monotonic() - queued_at, 2.5)
            self.assertFalse(RELEASE.is_set())
        finally:
            RELEASE.set()
            worker.stop()
            thread.join(30)
            connection_for_threads.dec_thread_sharing()
