"""The DjangoLux task runner: dispatch, claiming, retries, recovery, the scheduler and exclusions."""

from dlux.tests.harness import setup_test_environment

setup_test_environment()

import os
import socket
import tempfile
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from unittest import mock

import django
from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from dlux.models import DluxTaskRun, DluxTaskWorker
from dlux.ocr import RETRY_DELAYS as OCR_RETRY_DELAYS
from dlux.taskrunner import Retry, crontab, enqueue, queue, task, worker_alive
from dlux.taskrunner.checks import check_task_schedule
from dlux.taskrunner.registry import resolve_task
from dlux.taskrunner.schedules import as_schedule, interval, parse_schedule
from dlux.taskrunner.worker import Worker

CALLS = []


@task(name="tests.taskrunner.record")
def record(value):
    CALLS.append(value)
    return {"value": value}


@task(name="tests.taskrunner.boom")
def boom():
    raise RuntimeError("boom")


@task(name="tests.taskrunner.flaky", takes_context=True, max_retries=1)
def flaky(context):
    CALLS.append(context.attempt)
    raise Retry(30)


@task(name="tests.taskrunner.patient", takes_context=True, max_retries=1)
def patient(context):
    CALLS.append(context.attempt)
    if len(CALLS) < 4:
        raise Retry(5, counts=False)
    return "done"


@task(name="tests.taskrunner.secret", sensitive=True)
def secret(passphrase):
    CALLS.append(passphrase)


@task(name="tests.taskrunner.at_least_once", requeue_lost=True)
def at_least_once():
    CALLS.append("ran")


DLUX = override_settings()
UTC = dt_timezone.utc


def burst(schedule=False):
    return Worker(schedule=schedule).run_burst()


def live_worker(worker_id="live", **fields):
    return DluxTaskWorker.objects.create(id=worker_id, heartbeat_at=fields.pop("heartbeat_at", timezone.now()), **fields)


def make_due(**filters):
    DluxTaskRun.objects.filter(**filters).update(run_after=timezone.now() - timedelta(seconds=1))


class TaskRunnerTestCase(TestCase):
    def setUp(self):
        CALLS.clear()


class DispatchTests(TaskRunnerTestCase):
    def test_enqueue_queues_one_ready_row(self):
        run_id = record.enqueue(5)
        run = DluxTaskRun.objects.get()
        self.assertEqual((run.pk, run.task_name, run.args, run.status, run.priority),
                         (run_id, "tests.taskrunner.record", [5], "READY", 0))

    def test_delay_is_enqueue_and_sending_by_name_is_the_same_row(self):
        record.delay(6)
        enqueue("tests.taskrunner.record", args=[7], priority=-6, countdown=30)
        first, second = DluxTaskRun.objects.order_by("enqueued_at", "pk")
        self.assertEqual((first.args, second.args, second.priority), ([6], [7], -6))
        self.assertGreater(second.run_after, timezone.now() + timedelta(seconds=25))

    def test_the_public_api(self):
        import dlux.taskrunner as api

        self.assertEqual(sorted(api.__all__), sorted([
            "DluxTask", "Retry", "TaskContext", "crontab", "enqueue", "registered_tasks",
            "runner_config", "task", "worker_alive", "worker_started", "worker_stopping",
        ]))
        for name in api.__all__:
            self.assertTrue(hasattr(api, name), name)
        self.assertIn("tests.taskrunner.record", api.registered_tasks())

    def test_dlux_tasks_keeps_its_names_and_registers_nothing_with_celery(self):
        from dlux import jobs, tasks

        self.assertIs(tasks.ocr_file, jobs.ocr_file)
        self.assertIs(tasks.build_system_backup_task, jobs.build_system_backup)
        self.assertEqual(tasks.ocr_file.name, "dlux.tasks.ocr_file")
        self.assertFalse(hasattr(tasks, "worker_ready"))
        self.assertFalse(hasattr(jobs.ocr_file, "celery"))

    def test_sensitive_arguments_are_encrypted_at_rest_and_cleared_after_the_run(self):
        secret.enqueue("hunter2")
        raw = DluxTaskRun.objects.values("args", "kwargs", "sealed_arguments").get()
        self.assertNotIn("hunter2", str(raw))
        self.assertEqual(queue.run_arguments(DluxTaskRun.objects.get()), (["hunter2"], {}))
        self.assertEqual(burst(), 1)
        self.assertEqual(CALLS, ["hunter2"])
        run = DluxTaskRun.objects.get()
        self.assertEqual((run.status, run.sealed_arguments), ("SUCCESSFUL", ""))

    def test_a_system_backup_passphrase_never_reaches_the_queue_in_clear(self):
        from dlux.backup import dispatch_system_backup

        SystemBackup = apps.get_model("dlux", "SystemBackup")
        backup = SystemBackup.objects.create(requested_by_username="root")
        live_worker()
        self.assertTrue(dispatch_system_backup(backup, passphrase="pw-123456"))
        run = DluxTaskRun.objects.get()
        self.assertEqual(run.task_name, "dlux.tasks.build_system_backup")
        self.assertNotIn("pw-123456", str(DluxTaskRun.objects.values().get()))
        self.assertEqual(queue.run_arguments(run)[0], [backup.pk, "pw-123456"])

    def test_worker_alive_means_a_fresh_heartbeat(self):
        self.assertFalse(worker_alive())
        worker = live_worker(heartbeat_at=timezone.now() - timedelta(minutes=2))
        self.assertFalse(worker_alive())
        worker.heartbeat_at = timezone.now()
        worker.save()
        self.assertTrue(worker_alive())
        worker.stopped_at = timezone.now()
        worker.save()
        self.assertFalse(worker_alive())


class ClaimTests(TaskRunnerTestCase):
    def add(self, name, priority=0, age=0, **fields):
        return DluxTaskRun.objects.create(task_name=name, priority=priority,
                                          run_after=timezone.now() + timedelta(seconds=-age), **fields)

    def claim_names(self, worker="w1", **kwargs):
        names = []
        while (run := queue.claim_next(worker, **kwargs)) is not None:
            names.append(run.task_name)
        return names

    def test_highest_priority_first_then_the_longest_waiting(self):
        self.add("backfill", priority=-9, age=10)
        self.add("auto", priority=-6, age=20)
        self.add("manual-new", priority=0, age=1)
        self.add("manual-old", priority=0, age=5)
        self.add("later", priority=50, age=-60)
        self.assertEqual(self.claim_names(), ["manual-old", "manual-new", "auto", "backfill"])

    def test_a_run_is_claimed_exactly_once(self):
        self.add("only")
        run = queue.claim_next("w1")
        self.assertIsNone(queue.claim_next("w2"))
        run.refresh_from_db()
        self.assertEqual((run.status, run.attempts, run.worker_id, run.worker_ids), ("RUNNING", 1, "w1", ["w1"]))
        self.assertEqual(len(run.claim_token), 32)
        self.assertIsNotNone(run.started_at)

    def test_workers_take_only_their_queues(self):
        self.add("report", queue_name="reports")
        self.assertIsNone(queue.claim_next("w1"))
        self.assertEqual(queue.claim_next("w1", queues=["reports"]).task_name, "report")

    def test_skip_locked_path_records_the_same_claim(self):
        self.add("pg")
        with mock.patch.object(connection.features, "has_select_for_update_skip_locked", True):
            run = queue.claim_next("w1")
        run.refresh_from_db()
        self.assertEqual((run.status, run.attempts, run.worker_ids), ("RUNNING", 1, ["w1"]))
        self.assertIsNone(queue.claim_next("w2"))

    def test_compare_and_set_skips_a_candidate_another_worker_took(self):
        taken = self.add("taken", age=5)
        self.add("free", age=1)
        DluxTaskRun.objects.filter(pk=taken.pk).update(status="RUNNING", worker_id="w0")
        # Simulate the race: the candidate list still holds the row w0 took.
        everything = lambda queues, now, schedules=None: DluxTaskRun.objects.order_by("run_after")  # noqa: E731
        with mock.patch.object(queue, "_ready", everything), \
                mock.patch.object(connection.features, "has_select_for_update_skip_locked", False):
            self.assertEqual(queue.claim_next("w1").task_name, "free")
        self.assertEqual(DluxTaskRun.objects.get(pk=taken.pk).worker_id, "w0")


@DLUX
class RetryAndFailureTests(TaskRunnerTestCase):
    def test_retry_reuses_the_row_with_its_priority_and_a_delay(self):
        flaky.using(priority=-6).enqueue()
        burst()
        run = DluxTaskRun.objects.get()
        self.assertEqual((run.status, run.attempts, run.priority), ("READY", 1, -6))
        self.assertAlmostEqual((run.run_after - timezone.now()).total_seconds(), 30, delta=3)
        self.assertEqual(run.errors[-1]["exception_class_path"], "dlux.taskrunner.registry.Retry")
        self.assertEqual(burst(), 0, "not due yet")
        make_due()
        burst()
        run.refresh_from_db()
        self.assertEqual(CALLS, [1, 2])
        self.assertEqual((run.status, run.attempts), ("FAILED", 2), "max_retries=1 allows one retry")
        self.assertEqual(DluxTaskRun.objects.count(), 1)

    def test_an_uncounted_retry_leaves_the_retry_budget_alone(self):
        patient.enqueue()
        for _ in range(3):
            burst()
            run = DluxTaskRun.objects.get()
            self.assertEqual((run.status, run.attempts), ("READY", 0))
            self.assertAlmostEqual((run.run_after - timezone.now()).total_seconds(), 5, delta=3)
            make_due()
        burst()
        run = DluxTaskRun.objects.get()
        self.assertEqual(CALLS, [1, 1, 1, 1], "every call is the first counted attempt")
        self.assertEqual((run.status, run.return_value), ("SUCCESSFUL", "done"))

    def test_ocr_file_waits_out_a_busy_engine_without_using_its_retries(self):
        from dlux.ocr.client import OCRBusy

        enqueue("dlux.tasks.ocr_file", args=(123,), priority=-9)
        with mock.patch("dlux.ocr.service.run", side_effect=OCRBusy("The OCR engine is busy.", retry_after=30)), \
                mock.patch("dlux.ocr.service.give_up") as give_up:
            for _ in range(len(OCR_RETRY_DELAYS) + 3):
                burst()
                run = DluxTaskRun.objects.get()
                self.assertEqual((run.status, run.attempts), ("READY", 0))
                wait = (run.run_after - timezone.now()).total_seconds()
                self.assertTrue(25 <= wait <= 65, wait)
                make_due()
            give_up.assert_not_called()
        with mock.patch("dlux.ocr.service.run") as ran:
            burst()
        ran.assert_called_once_with(123)
        self.assertEqual(DluxTaskRun.objects.get().status, "SUCCESSFUL")

    def test_ocr_file_waits_out_the_service_with_growing_delays_then_gives_up(self):
        from dlux.ocr.client import OCRUnavailable

        enqueue("dlux.tasks.ocr_file", args=(123,), priority=-6)
        with mock.patch("dlux.ocr.service.run", side_effect=OCRUnavailable("down")), \
                mock.patch("dlux.ocr.service.give_up") as give_up:
            burst()
            run = DluxTaskRun.objects.get()
            self.assertEqual(run.status, "READY")
            self.assertAlmostEqual((run.run_after - timezone.now()).total_seconds(), OCR_RETRY_DELAYS[0], delta=3)
            self.assertEqual(run.errors[-1]["exception_class_path"], "dlux.ocr.client.OCRUnavailable")
            make_due()
            burst()
            run.refresh_from_db()
            self.assertAlmostEqual((run.run_after - timezone.now()).total_seconds(), OCR_RETRY_DELAYS[1], delta=3)
            give_up.assert_not_called()
            DluxTaskRun.objects.update(attempts=len(OCR_RETRY_DELAYS), run_after=timezone.now())
            burst()
        give_up.assert_called_once()
        self.assertIn(f"gave up after {len(OCR_RETRY_DELAYS)} retries", give_up.call_args.args[1])
        self.assertEqual(DluxTaskRun.objects.get().status, "SUCCESSFUL")

    def test_an_exception_fails_the_run_and_keeps_its_traceback(self):
        boom.enqueue()
        burst()
        run = DluxTaskRun.objects.get()
        self.assertEqual(run.status, "FAILED")
        self.assertEqual(run.errors[0]["exception_class_path"], "builtins.RuntimeError")
        self.assertIn("boom", run.errors[0]["traceback"])
        self.assertIsNotNone(run.finished_at)

    def test_an_unknown_task_fails_without_stopping_the_worker(self):
        enqueue("tests.taskrunner.nope")
        record.enqueue("after")
        self.assertEqual(burst(), 2)
        self.assertEqual(DluxTaskRun.objects.get(task_name="tests.taskrunner.nope").errors[0]["exception_class_path"],
                         "dlux.taskrunner.UnknownTask")
        self.assertEqual(CALLS, ["after"])

    def test_a_queue_row_cannot_name_an_arbitrary_function(self):
        self.assertIsNone(resolve_task("os.system"))
        self.assertIsNone(resolve_task("dlux.taskrunner.queue.prune"))

    def test_arguments_sealed_under_another_secret_key_fail_cleanly(self):
        with override_settings(SECRET_KEY="another-key"):
            secret.enqueue("x")
        burst()
        run = DluxTaskRun.objects.get()
        self.assertEqual((run.status, run.sealed_arguments), ("FAILED", ""))
        self.assertEqual(CALLS, [])


class RecoveryTests(TaskRunnerTestCase):
    def running(self, task_name, worker_id="dead", **fields):
        return DluxTaskRun.objects.create(task_name=task_name, status="RUNNING", worker_id=worker_id,
                                          claim_token="tok", attempts=1, **fields)

    def setUp(self):
        super().setUp()
        live_worker("dead", heartbeat_at=timezone.now() - timedelta(minutes=5))

    def recover(self):
        return queue.recover_lost_runs(resolve=resolve_task)

    def test_a_requeue_lost_task_goes_back_a_bounded_number_of_times(self):
        run = self.running("tests.taskrunner.at_least_once")
        self.assertEqual(self.recover(), (1, 0))
        run.refresh_from_db()
        self.assertEqual((run.status, run.recoveries, run.claim_token), ("READY", 1, ""))
        self.assertEqual(run.errors[-1]["exception_class_path"], queue.WORKER_LOST)
        DluxTaskRun.objects.filter(pk=run.pk).update(status="RUNNING", claim_token="tok", recoveries=3)
        self.assertEqual(self.recover(), (0, 1))
        self.assertEqual(DluxTaskRun.objects.get(pk=run.pk).status, "FAILED")

    def test_ocr_file_is_requeued_when_its_worker_dies(self):
        import dlux.jobs  # noqa: F401

        self.running("dlux.tasks.ocr_file", args=[1])
        self.assertEqual(self.recover(), (1, 0))

    def test_other_tasks_fail_when_their_worker_dies(self):
        run = self.running("tests.taskrunner.record", sealed_arguments="x")
        self.assertEqual(self.recover(), (0, 1))
        run.refresh_from_db()
        self.assertEqual((run.status, run.sealed_arguments), ("FAILED", ""))

    def test_a_lost_schedule_row_is_armed_again(self):
        run = self.running("tests.taskrunner.record", schedule_name="tick")
        self.recover()
        run.refresh_from_db()
        self.assertEqual((run.status, run.last_status), ("READY", "FAILED"))
        self.assertLessEqual(run.run_after, timezone.now())

    def test_runs_of_a_live_worker_are_left_alone(self):
        live_worker("busy")
        run = self.running("tests.taskrunner.record", worker_id="busy")
        self.assertEqual(self.recover(), (0, 0))
        run.refresh_from_db()
        self.assertEqual(run.status, "RUNNING")

    def test_a_late_outcome_from_the_lost_worker_is_dropped(self):
        stale = self.running("tests.taskrunner.at_least_once")
        self.recover()
        self.assertFalse(queue.complete_run(stale, return_value=1))
        self.assertEqual(DluxTaskRun.objects.get(pk=stale.pk).status, "READY")

    def test_a_restarted_container_releases_its_previous_incarnation_at_once(self):
        live_worker("previous", hostname=socket.gethostname()[:255], pid=os.getpid())
        run = self.running("tests.taskrunner.at_least_once", worker_id="previous")
        Worker(schedule=False).setup()
        self.assertIsNotNone(DluxTaskWorker.objects.get(id="previous").stopped_at)
        run.refresh_from_db()
        self.assertEqual(run.status, "READY")

    def test_worker_start_reaps_stalled_system_backups(self):
        with mock.patch("dlux.backup.reap_stalled_system_backups", return_value=(0, 0)) as reap:
            Worker(schedule=False).setup()
        reap.assert_called_once_with()


@DLUX
class ScheduleTests(TaskRunnerTestCase):
    TICK = {"tick": {"task": "tests.taskrunner.record", "schedule": 5, "args": ["tick"]}}

    def test_a_schedule_entry_keeps_one_row_however_many_ticks_run(self):
        for _ in range(6):
            burst(schedule=self.TICK)
            make_due()
        self.assertEqual(CALLS, ["tick"] * 6)
        run = DluxTaskRun.objects.get()
        self.assertEqual((run.schedule_name, run.status, run.last_status, run.attempts), ("tick", "READY", "SUCCESSFUL", 0))

    def test_the_next_tick_is_on_the_interval_grid(self):
        burst(schedule=self.TICK)
        run = DluxTaskRun.objects.get()
        self.assertGreater(run.run_after, timezone.now())
        self.assertLessEqual((run.run_after - timezone.now()).total_seconds(), 5)
        start = datetime(2026, 11, 6, 10, 0, tzinfo=UTC)
        every = interval(5)
        self.assertEqual(every.next_after(start + timedelta(seconds=12), previous_due=start), start + timedelta(seconds=15))
        self.assertEqual(every.next_after(start, previous_due=None), start + timedelta(seconds=5))

    def test_a_failing_scheduled_task_stays_armed(self):
        burst(schedule={"bad": {"task": "tests.taskrunner.boom", "schedule": 60}})
        run = DluxTaskRun.objects.get()
        self.assertEqual((run.status, run.last_status), ("READY", "FAILED"))
        self.assertEqual(run.errors[-1]["exception_class_path"], "builtins.RuntimeError")

    def test_two_workers_cannot_run_the_same_tick(self):
        queue.sync_schedule(parse_schedule(self.TICK))
        self.assertIsNotNone(queue.claim_next("w1"))
        self.assertIsNone(queue.claim_next("w2"))

    def test_sync_follows_changed_and_removed_entries(self):
        queue.sync_schedule(parse_schedule(self.TICK))
        signature = DluxTaskRun.objects.get().schedule_signature
        queue.sync_schedule(parse_schedule(self.TICK))
        self.assertEqual(DluxTaskRun.objects.get().schedule_signature, signature)
        changed = {"tick": dict(self.TICK["tick"], schedule=10)}
        queue.sync_schedule(parse_schedule(changed))
        self.assertNotEqual(DluxTaskRun.objects.get().schedule_signature, signature)
        DluxTaskRun.objects.update(status="RUNNING")
        self.assertEqual(queue.sync_schedule([]), 0, "a running row is not pulled from under its worker")
        DluxTaskRun.objects.update(status="READY")
        self.assertEqual(queue.sync_schedule([]), 1)
        self.assertFalse(DluxTaskRun.objects.exists())

    def test_a_cron_entry_first_runs_at_its_next_match(self):
        queue.sync_schedule(parse_schedule({"hourly": {"task": "tests.taskrunner.record", "schedule": crontab(minute=0)}}))
        run = DluxTaskRun.objects.get()
        self.assertGreater(run.run_after, timezone.now())
        self.assertEqual(timezone.localtime(run.run_after).minute, 0)

    def test_an_entry_dropped_from_settings_is_removed_by_the_worker(self):
        burst(schedule=self.TICK)
        burst(schedule={})
        self.assertFalse(DluxTaskRun.objects.exists())

    def test_a_worker_never_claims_an_entry_it_has_no_spec_for(self):
        queue.sync_schedule(parse_schedule(self.TICK))
        record.enqueue("one-off")
        self.assertEqual(Worker(schedule=False).run_burst(), 1)
        self.assertEqual(CALLS, ["one-off"])
        self.assertEqual(DluxTaskRun.objects.get(schedule_name="tick").status, "READY")


@override_settings(TIME_ZONE="UTC")
class CrontabTests(SimpleTestCase):
    def at(self, *parts):
        return datetime(*parts, tzinfo=UTC)

    def test_every_three_hours(self):
        self.assertEqual(crontab(minute=0, hour="*/3").next_after(self.at(2026, 11, 6, 10, 30)), self.at(2026, 11, 6, 12, 0))

    def test_strictly_after_the_given_moment(self):
        self.assertEqual(crontab(minute=0).next_after(self.at(2026, 11, 6, 10, 0)), self.at(2026, 11, 6, 11, 0))

    def test_weekdays_skip_the_weekend(self):
        friday = self.at(2026, 11, 6, 10, 0)
        self.assertEqual(crontab(minute=30, hour=9, day_of_week="mon-fri").next_after(friday), self.at(2026, 11, 9, 9, 30))

    def test_day_of_month_and_month_of_year(self):
        spec = crontab(minute=0, hour=0, day_of_month=1, month_of_year="jan")
        self.assertEqual(spec.next_after(self.at(2026, 11, 6, 10, 0)), self.at(2027, 1, 1, 0, 0))

    def test_sunday_is_both_0_and_7(self):
        self.assertEqual(crontab(day_of_week=7).fields[2], {0})
        self.assertEqual(crontab(day_of_week="sun").fields[2], {0})

    @override_settings(TIME_ZONE="Africa/Tripoli")
    def test_cron_follows_the_project_time_zone(self):
        self.assertEqual(crontab(minute=0, hour=3).next_after(self.at(2026, 11, 6, 0, 30)), self.at(2026, 11, 6, 1, 0))

    def test_a_celery_crontab_is_read_through_its_expanded_fields(self):
        try:
            from celery.schedules import crontab as celery_crontab
        except ImportError:
            self.skipTest("celery is not installed")
        moment = self.at(2026, 11, 6, 10, 30)
        converted = as_schedule(celery_crontab(minute=0, hour="*/3"))
        self.assertEqual(converted.next_after(moment), crontab(minute=0, hour="*/3").next_after(moment))
        self.assertEqual(as_schedule(timedelta(minutes=15)), interval(900.0))

    def test_bad_specs_fail_with_the_entry_named(self):
        for spec in ({"minute": 60}, {"hour": "5-2"}, {"day_of_month": 0}, {"minute": "*/0"}):
            with self.assertRaises(ValueError):
                crontab(**spec)
        with self.assertRaisesRegex(ValueError, "'nightly'"):
            parse_schedule({"nightly": {"schedule": 5}})
        with self.assertRaisesRegex(ValueError, "'nightly'"):
            parse_schedule({"nightly": {"task": "t", "schedule": -1}})

    def test_the_system_check_reports_a_bad_schedule(self):
        with override_settings(DLUX_TASK_SCHEDULE={"x": {"task": "t", "schedule": "often"}}):
            self.assertEqual([e.id for e in check_task_schedule()], ["dlux.E102"])
        self.assertEqual(check_task_schedule(), [])


class SettingsTests(SimpleTestCase):
    def test_dlux_settings_schedules_djangolux_on_the_worker_only(self):
        from dlux.utils.settings import DLUX_BUILTIN_TASK_SCHEDULE, dlux_settings

        scope = {}
        dlux_settings(scope)
        own = scope["DLUX_TASK_SCHEDULE"]
        self.assertEqual(set(own), set(DLUX_BUILTIN_TASK_SCHEDULE))
        self.assertEqual(own["dlux-ocr-background"]["options"]["priority"], -9)
        parse_schedule(own)
        self.assertNotIn("DLUX_TASK_BACKEND", scope)
        # Kept as an (empty) dict for projects that still add Celery beat entries to it.
        self.assertEqual(scope["CELERY_BEAT_SCHEDULE"], {})
        if django.VERSION >= (6, 0):
            self.assertEqual(scope["TASKS"]["default"]["BACKEND"], "dlux.taskrunner.backend.DatabaseBackend")

    def test_project_entries_and_tasks_setting_are_kept(self):
        from dlux.utils.settings import dlux_settings

        mine = {"refresh": {"task": "crm.tasks.refresh", "schedule": crontab(minute=0, hour="*/3")}}
        scope = {"DLUX_TASK_SCHEDULE": dict(mine)}
        dlux_settings(scope)
        self.assertIn("refresh", scope["DLUX_TASK_SCHEDULE"])
        self.assertIn("dlux-state-tick", scope["DLUX_TASK_SCHEDULE"])
        # A project's own Celery beat entries stay; DjangoLux's never reach Celery,
        # even when a project copied them there.
        project_beat = {
            "crm-refresh": {"task": "crm.tasks.refresh", "schedule": 60},
            "dlux-state-tick": {"task": "dlux.tasks.dlux_state_tick", "schedule": 5.0},
        }
        scope = {"CELERY_BEAT_SCHEDULE": dict(project_beat)}
        dlux_settings(scope)
        self.assertEqual(scope["CELERY_BEAT_SCHEDULE"], {"crm-refresh": project_beat["crm-refresh"]})
        own_tasks = {"default": {"BACKEND": "django.tasks.backends.immediate.ImmediateBackend"}}
        scope = {"TASKS": own_tasks}
        dlux_settings(scope)
        self.assertIs(scope["TASKS"], own_tasks)


class PruneTests(TaskRunnerTestCase):
    def finished(self, status, days, **fields):
        return DluxTaskRun.objects.create(task_name="t", status=status,
                                          finished_at=timezone.now() - timedelta(days=days), **fields)

    def test_finished_runs_are_pruned_after_their_retention(self):
        old_ok, new_ok = self.finished("SUCCESSFUL", 2), self.finished("SUCCESSFUL", 0)
        failed_recently, failed_long_ago = self.finished("FAILED", 2), self.finished("FAILED", 8)
        schedule_row = self.finished("SUCCESSFUL", 30, schedule_name="tick")
        live_worker("gone", heartbeat_at=timezone.now() - timedelta(days=2))
        self.assertEqual(queue.prune(), 2)
        self.assertEqual(set(DluxTaskRun.objects.values_list("pk", flat=True)),
                         {new_ok.pk, failed_recently.pk, schedule_row.pk})
        self.assertFalse(DluxTaskWorker.objects.filter(id="gone").exists())
        self.assertFalse(DluxTaskRun.objects.filter(pk__in=[old_ok.pk, failed_long_ago.pk]).exists())


class ExclusionTests(TaskRunnerTestCase):
    def test_the_queue_is_neither_backed_up_nor_replaced_by_a_restore(self):
        from dlux.backup import get_system_backup_models
        from dlux.backup.restore import _models_in_scope

        for models in (get_system_backup_models(), get_system_backup_models(include_system_data=False),
                       _models_in_scope({"system_data_included": True})):
            self.assertNotIn(DluxTaskRun, models)
            self.assertNotIn(DluxTaskWorker, models)

    @DLUX
    def test_a_restore_run_by_the_worker_keeps_its_own_queue_row(self):
        from dlux.backup import dispatch_system_restore, run_system_backup

        User = get_user_model()
        SystemBackup = apps.get_model("dlux", "SystemBackup")
        SystemRestore = apps.get_model("dlux", "SystemRestore")
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            User.objects.create_superuser("root", "root@example.com", "rootpass123")
            backup = SystemBackup.objects.create(requested_by_username="root")
            run_system_backup(backup.pk)
            backup.refresh_from_db()
            self.assertEqual(backup.status, SystemBackup.STATUS_COMPLETED, backup.error)
            User.objects.create_user("intruder", "i@example.com", "intruderpass")
            bystander = DluxTaskRun.objects.create(task_name="tests.taskrunner.record", args=["later"],
                                                   run_after=timezone.now() + timedelta(hours=1))
            live_worker()
            restore = SystemRestore.objects.create(requested_by_username="root", backup_file_path=backup.file_path)
            self.assertTrue(dispatch_system_restore(restore))
            self.assertEqual(burst(), 1)
            restore.refresh_from_db()
            self.assertEqual(restore.status, SystemRestore.STATUS_COMPLETED, restore.error)
            self.assertFalse(User.objects.filter(username="intruder").exists())
            own = DluxTaskRun.objects.get(task_name="dlux.tasks.restore_system_backup")
            self.assertEqual((own.status, own.sealed_arguments), ("SUCCESSFUL", ""))
            self.assertTrue(DluxTaskRun.objects.filter(pk=bystander.pk, status="READY").exists())

    def test_reports_permissions_and_the_activity_log_leave_the_queue_out(self):
        from dlux.forms.permissions import get_assignable_permissions_queryset
        from dlux.reports.eligibility import is_report_eligible_model
        from dlux.utils.activity_log import LOG_NEVER_LOGGED_MODEL_KEYS

        for model in (DluxTaskRun, DluxTaskWorker):
            self.assertFalse(is_report_eligible_model(model))
            self.assertIn(model._meta.label_lower, LOG_NEVER_LOGGED_MODEL_KEYS)
        self.assertFalse(get_assignable_permissions_queryset().filter(
            content_type__app_label="dlux", content_type__model__in=["dluxtaskrun", "dluxtaskworker"]).exists())


class DoctorAndOptionsTests(TaskRunnerTestCase):
    def finding(self):
        from dlux import doctor

        return doctor._check_task_worker(None)

    def test_doctor_task_worker(self):
        finding = self.finding()
        self.assertEqual(finding.status, "warning")
        self.assertIn("check --fix", finding.remedy)
        live_worker(version="1.16.0b1")
        self.assertEqual(self.finding().status, "ok")
        DluxTaskRun.objects.create(task_name="t", status="FAILED", finished_at=timezone.now())
        self.assertEqual(self.finding().status, "warning")

    def test_doctor_warns_while_the_project_still_uses_celery(self):
        from dlux import doctor

        with override_settings(CELERY_BEAT_SCHEDULE={}, CELERY_BROKER_URL=""), \
                mock.patch.dict(os.environ, {"DJANGO_SETTINGS_MODULE": "dlux.tests.settings"}):
            self.assertEqual(doctor._check_project_celery(None).status, "ok")
        project_beat = {"crm-refresh": {"task": "crm.tasks.refresh", "schedule": 60}}
        with override_settings(CELERY_BEAT_SCHEDULE=project_beat, CELERY_BROKER_URL="redis://redis:6379/2"):
            finding = doctor._check_project_celery(None)
        self.assertEqual(finding.status, "warning")
        self.assertIn("crm-refresh", finding.detail)
        self.assertIn("CELERY_BROKER_URL", finding.detail)
        self.assertIn("dlux.taskrunner.task", finding.remedy)

    def test_the_options_tasks_row_reads_worker_heartbeats(self):
        from dlux.views import options

        service = options._get_tasks_service()
        self.assertEqual((service["state"], service["note_key"]), ("offline", "service_task_worker_offline"))
        live_worker()
        record.enqueue(1)
        service = options._get_tasks_service()
        self.assertEqual((service["state"], service["note_context"]["count"], service["note_context"]["ready"]),
                         ("online", 1, 1))


@DLUX
class DjangoTasksBackendTests(TaskRunnerTestCase):
    def setUp(self):
        super().setUp()
        if django.VERSION < (6, 0):
            self.skipTest("django.tasks needs Django 6.0")
        override = override_settings(TASKS={"default": {"BACKEND": "dlux.taskrunner.backend.DatabaseBackend"}})
        override.enable()
        self.addCleanup(override.disable)

    def test_a_django_task_runs_on_the_worker_and_reports_its_result(self):
        from dlux.tests.django_task_samples import add, attempt_number

        result = add.enqueue(2, 3)
        self.assertEqual(result.status, "READY")
        context_result = attempt_number.enqueue()
        self.assertEqual(burst(), 2)
        finished = add.get_result(result.id)
        self.assertEqual((finished.status, finished.return_value), ("SUCCESSFUL", 5))
        self.assertEqual(attempt_number.get_result(context_result.id).return_value, 1)

    def test_priority_and_run_after_reach_the_queue(self):
        from dlux.tests.django_task_samples import add

        later = timezone.now() + timedelta(hours=1)
        result = add.using(priority=7, run_after=later).enqueue(1, 1)
        run = DluxTaskRun.objects.get(pk=result.id)
        self.assertEqual((run.priority, run.run_after), (7, later))
        self.assertEqual(burst(), 0)
