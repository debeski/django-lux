"""DjangoLux states intent; Composer executes.

Since 1.8.0 an inline package update is handed to Composer instead of being
performed in-container. These tests pin the hand-off contract — the file
Composer's executor watches — and the escape hatch that restores the legacy path
for a deployment whose Composer predates the `dlux.package_update` action.

The in-container executor is not removed here. A deployed `compose.yml` is
project-owned and names `dlux_update_worker`, `dlux_reconcile` and the supervisor
in a `restart: always`, `org.dlux.restart: protected` service; deleting any of
them in the release a box upgrades *into* would produce a protected crash loop.
Removal is 1.9.0 — see docs/updater-consolidation.md.
"""
from dlux.tests.harness import setup_test_environment

setup_test_environment()

import json
import os
from datetime import timedelta
from tempfile import TemporaryDirectory
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from dlux.updater import package_request
from dlux.updater.runtime import RuntimeStore
from dlux.updater.service import composer_executes_updates


class ExecutorSelectionTests(SimpleTestCase):
    def test_composer_is_the_default(self):
        self.assertTrue(composer_executes_updates())

    @override_settings(DLUX_UPDATE_EXECUTOR="inline")
    def test_the_legacy_path_can_still_be_selected(self):
        self.assertFalse(composer_executes_updates())

    @override_settings(DLUX_UPDATE_EXECUTOR="")
    def test_an_empty_value_falls_back_to_composer(self):
        self.assertTrue(composer_executes_updates())

    @override_settings(DLUX_UPDATE_EXECUTOR="COMPOSER")
    def test_the_value_is_case_insensitive(self):
        self.assertTrue(composer_executes_updates())


class RequestFileTests(SimpleTestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.store = RuntimeStore(Path(self._tmp.name) / "runtime").ensure()
        self.addCleanup(self._tmp.cleanup)

    def _payload(self):
        return json.loads(package_request.trigger_path(self.store).read_text(encoding="utf-8"))

    def test_the_request_carries_the_agent_action_fields(self):
        """Local file and control-panel command must carry identical fields."""
        package_request.write_request(
            self.store, mode="apply", target_version="1.8.0", backup_mode="full", token="tok-1"
        )

        payload = self._payload()
        self.assertEqual(payload["token"], "tok-1")
        self.assertEqual(
            payload["payload"],
            {"mode": "apply", "target_version": "1.8.0", "backup_mode": "full"},
        )
        self.assertIn("requested_at", payload)

    def test_a_rollback_request_names_no_version(self):
        package_request.write_request(self.store, mode="rollback", token="tok-2")

        self.assertEqual(self._payload()["payload"]["mode"], "rollback")
        self.assertEqual(self._payload()["payload"]["target_version"], "")

    def test_an_unknown_mode_is_refused(self):
        from dlux.updater import UpdaterError

        with self.assertRaises(UpdaterError):
            package_request.write_request(self.store, mode="destroy")
        self.assertFalse(package_request.trigger_path(self.store).exists())

    def test_the_request_is_written_atomically(self):
        package_request.write_request(self.store, mode="apply", token="tok-3")

        leftovers = [p.name for p in self.store.state_dir.iterdir() if p.name.startswith(".")]
        self.assertEqual(leftovers, [])

    def test_an_operation_id_is_carried_through_when_present(self):
        package_request.write_request(self.store, mode="apply", token="t", operation_id="op-9")
        self.assertEqual(self._payload()["operation_id"], "op-9")

    def test_no_operation_id_key_for_a_local_request(self):
        package_request.write_request(self.store, mode="apply", token="t")
        self.assertNotIn("operation_id", self._payload())


class HandoffTests(TestCase):
    """The run itself, not just `write_request`.

    Every field of the request file was pinned below, and the hand-off still
    could not write one: it read `control_operation_id` off the run — a field
    that lives on DluxImageUpdate — so an apply died with AttributeError after
    "Started apply request." and before Composer was told anything. Drive the
    real path, from a queued run to the file on the volume.
    """

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.store = RuntimeStore(Path(self._tmp.name) / "runtime").ensure()
        self.addCleanup(self._tmp.cleanup)

    def _run_model(self):
        from django.apps import apps

        return apps.get_model("dlux", "DluxUpdateRun")

    def _state(self):
        from django.apps import apps

        return apps.get_model("dlux", "DluxUpdateState").load()

    def _queue(self, action, *, target_version="1.8.8", backup_mode="data"):
        Run = self._run_model()
        run = Run.objects.create(
            action=action,
            status=Run.STATUS_QUEUED,
            is_active=True,
            target_version=target_version,
            backup_mode=backup_mode,
        )
        state = self._state()
        state.active_run_token = run.token
        state.save(update_fields=["active_run_token"])
        return run

    def _ack(self, token, exit_code=0):
        package_request.ack_path(self.store).write_text(
            json.dumps({"token": token, "exit_code": exit_code}), encoding="utf-8"
        )

    def _composer_status(self, payload):
        from dlux.updater.image_update import status_path

        status_path(self.store).write_text(json.dumps(payload), encoding="utf-8")

    def _service(self):
        from dlux.updater.service import UpdateService

        return UpdateService(store=self.store)

    def _payload(self):
        return json.loads(package_request.trigger_path(self.store).read_text(encoding="utf-8"))

    def test_an_apply_run_reaches_composer(self):
        Run = self._run_model()
        queued = self._queue(Run.ACTION_APPLY)

        run = self._service().process_next()

        self.assertEqual(run.pk, queued.pk)
        self.assertEqual(run.status, Run.STATUS_APPLYING, run.error)
        payload = self._payload()
        self.assertEqual(payload["token"], run.token)
        self.assertEqual(payload["payload"]["mode"], package_request.APPLY)
        self.assertEqual(payload["payload"]["target_version"], "1.8.8")
        self.assertEqual(payload["payload"]["backup_mode"], "data")
        self.assertNotIn("operation_id", payload, "a package run is local; it has no control operation")

    def test_a_rollback_run_reaches_composer_without_a_version(self):
        Run = self._run_model()
        self._queue(Run.ACTION_ROLLBACK, target_version="1.8.7")

        run = self._service().process_next()

        self.assertEqual(run.status, Run.STATUS_APPLYING, run.error)
        self.assertEqual(self._payload()["payload"]["mode"], package_request.ROLLBACK)
        self.assertEqual(self._payload()["payload"]["target_version"], "")

    def test_composers_progress_is_not_overwritten_while_it_executes(self):
        """That file is the only progress the modal has once web restarts."""
        Run = self._run_model()
        self._queue(Run.ACTION_APPLY)
        self._composer_status({"status": "running", "kind": "package", "message": "staging"})

        self._service().process_next()

        self.assertEqual(package_request.composer_progress(self.store)["message"], "staging")

    def test_the_run_fails_cleanly_while_composer_still_holds_one(self):
        Run = self._run_model()
        package_request.write_request(self.store, mode=package_request.APPLY, token="tok-held")
        self._queue(Run.ACTION_APPLY)

        run = self._service().process_next()

        self.assertEqual(run.status, Run.STATUS_FAILED)
        self.assertIn("already performing", run.error)
        self.assertEqual(self._payload()["token"], "tok-held", "the held request is untouched")


class HandoffCompletionTests(TestCase):
    """Somebody has to end the run Composer executed.

    The hand-off ends at the request file; nothing in the web/worker process can
    see what Composer did next. Until the ack was read back, a handed-off run
    stayed `is_active` for ever — and `queue_run` refuses to queue anything while
    one is active, so a single update wedged the deployment permanently.
    """

    def setUp(self):
        self._tmp = TemporaryDirectory()
        root = Path(self._tmp.name)
        self.store = RuntimeStore(root / "runtime").ensure()
        # Completing a hand-off collects the now-active release's static files,
        # which shells out through the project's manage.py.
        self.base_dir = root / "project"
        self.base_dir.mkdir()
        (self.base_dir / "manage.py").write_text("# generated\n", encoding="utf-8")
        self.addCleanup(self._tmp.cleanup)

    def _models(self):
        from django.apps import apps

        return apps.get_model("dlux", "DluxUpdateRun"), apps.get_model("dlux", "DluxUpdateState")

    def _service(self):
        from dlux.updater.service import UpdateService

        class _Completed:
            returncode = 0
            stdout = ""
            stderr = ""

        return UpdateService(store=self.store, command_runner=lambda *a, **k: _Completed())

    def _tick(self):
        with override_settings(BASE_DIR=self.base_dir):
            return self._service().tick_package_update()

    def _applying_run(self, *, started_at=None):
        Run, State = self._models()
        run = Run.objects.create(
            action=Run.ACTION_APPLY,
            status=Run.STATUS_APPLYING,
            is_active=True,
            target_version="1.8.8",
            started_at=started_at or timezone.now(),
        )
        state = State.load()
        state.active_run_token = run.token
        state.save(update_fields=["active_run_token"])
        return run

    def _ack(self, token, exit_code=0):
        package_request.ack_path(self.store).write_text(
            json.dumps({"token": token, "exit_code": exit_code}), encoding="utf-8"
        )

    def _composer_status(self, payload):
        from dlux.updater.image_update import status_path

        status_path(self.store).write_text(json.dumps(payload), encoding="utf-8")

    def test_an_applied_release_completes_the_run(self):
        Run, State = self._models()
        run = self._applying_run()
        self._ack(run.token, 0)

        finished = self._tick()

        finished.refresh_from_db()
        self.assertEqual(finished.status, Run.STATUS_COMPLETED)
        self.assertFalse(finished.is_active)
        self.assertEqual(State.load().active_run_token, "", "the next update must be queueable")

    def test_a_run_stays_open_until_composer_acknowledges_it(self):
        Run, _State = self._models()
        run = self._applying_run()

        self.assertIsNone(self._tick())

        run.refresh_from_db()
        self.assertEqual(run.status, Run.STATUS_APPLYING)
        self.assertTrue(run.is_active)

    def test_an_ack_for_another_token_is_not_this_run(self):
        Run, _State = self._models()
        run = self._applying_run()
        self._ack("some-older-token", 0)

        self.assertIsNone(self._tick())
        run.refresh_from_db()
        self.assertEqual(run.status, Run.STATUS_APPLYING)

    def test_a_rolled_back_update_is_reported_as_rolled_back(self):
        Run, _State = self._models()
        run = self._applying_run()
        self._ack(run.token, 1)
        self._composer_status({
            "kind": "package", "ok": False, "rolled_back": True,
            "message": "Health check failed. Rolled back to 1.8.6.",
        })

        finished = self._tick()

        finished.refresh_from_db()
        self.assertEqual(finished.status, Run.STATUS_ROLLED_BACK)
        self.assertIn("Rolled back", finished.error)

    def test_needs_a_human_is_carried_through(self):
        """Composer's exit 3: the rollback was not healthy either."""
        Run, _State = self._models()
        run = self._applying_run()
        self._ack(run.token, 3)

        finished = self._tick()

        finished.refresh_from_db()
        self.assertEqual(finished.status, Run.STATUS_FAILED)
        self.assertIn("needs an operator", finished.error)

    def test_a_hand_off_composer_never_acknowledged_is_eventually_failed(self):
        from dlux.updater.service import PACKAGE_HANDOFF_TIMEOUT

        Run, State = self._models()
        run = self._applying_run(
            started_at=timezone.now() - PACKAGE_HANDOFF_TIMEOUT - timedelta(minutes=1)
        )

        finished = self._tick()

        finished.refresh_from_db()
        self.assertEqual(finished.status, Run.STATUS_FAILED)
        self.assertIn("did not acknowledge", finished.error)
        self.assertEqual(State.load().active_run_token, "")

    def test_nothing_happens_without_an_active_run(self):
        self.assertIsNone(self._tick())


class PendingTokenTests(SimpleTestCase):
    """A second swap must not start while Composer is mid-flight on the first."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.store = RuntimeStore(Path(self._tmp.name) / "runtime").ensure()
        self.addCleanup(self._tmp.cleanup)

    def test_no_request_means_nothing_pending(self):
        self.assertEqual(package_request.pending_token(self.store), "")

    def test_an_unacknowledged_request_is_pending(self):
        package_request.write_request(self.store, mode="apply", token="tok-1")
        self.assertEqual(package_request.pending_token(self.store), "tok-1")

    def test_an_acknowledged_request_is_not_pending(self):
        package_request.write_request(self.store, mode="apply", token="tok-1")
        package_request.ack_path(self.store).write_text(
            json.dumps({"token": "tok-1", "exit_code": 0}), encoding="utf-8")

        self.assertEqual(package_request.pending_token(self.store), "")

    def test_an_ack_for_an_older_token_leaves_the_new_one_pending(self):
        package_request.ack_path(self.store).write_text(
            json.dumps({"token": "old", "exit_code": 0}), encoding="utf-8")
        package_request.write_request(self.store, mode="apply", token="new")

        self.assertEqual(package_request.pending_token(self.store), "new")

    def test_an_unreadable_request_is_not_treated_as_pending(self):
        """A corrupt file must not wedge every future update."""
        package_request.trigger_path(self.store).write_text("{not json", encoding="utf-8")
        self.assertEqual(package_request.pending_token(self.store), "")

    def test_a_failed_ack_still_clears_pending(self):
        """Composer failing is not the same as Composer still working."""
        package_request.write_request(self.store, mode="apply", token="tok-1")
        package_request.ack_path(self.store).write_text(
            json.dumps({"token": "tok-1", "exit_code": 3}), encoding="utf-8")

        self.assertEqual(package_request.pending_token(self.store), "")
        self.assertEqual(package_request.read_ack(self.store)["exit_code"], 3)


class AvailabilityTests(SimpleTestCase):
    """DjangoLux reads what Composer published; it never reaches PyPI itself."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.store = RuntimeStore(Path(self._tmp.name) / "runtime").ensure()
        self.addCleanup(self._tmp.cleanup)

    def _publish(self, payload):
        package_request.availability_path(self.store).write_text(
            json.dumps(payload), encoding="utf-8")

    def test_nothing_published_reads_as_unknown_not_up_to_date(self):
        """The distinction the UI must not blur: unknown != up to date."""
        self.assertEqual(package_request.read_availability(self.store), {})

    def test_a_published_report_is_returned(self):
        self._publish({"available": True, "version": "1.9.0", "inline_safe": True})
        report = package_request.read_availability(self.store)

        self.assertTrue(report["available"])
        self.assertEqual(report["version"], "1.9.0")

    def test_an_error_report_is_surfaced_not_swallowed(self):
        """A failed check must not look like 'no update available'."""
        self._publish({"available": False, "version": "", "error": "attestation invalid"})

        self.assertEqual(
            package_request.read_availability(self.store)["error"], "attestation invalid")

    def test_a_corrupt_report_reads_as_unknown(self):
        package_request.availability_path(self.store).write_text("{not json", encoding="utf-8")
        self.assertEqual(package_request.read_availability(self.store), {})

    def test_a_release_requiring_an_image_rebuild_is_reported_as_such(self):
        self._publish({
            "available": True, "version": "2.0.0", "inline_safe": False,
            "reason": "DjangoLux 2.0.0 requires a project image rebuild.",
        })
        report = package_request.read_availability(self.store)

        self.assertFalse(report["inline_safe"])
        self.assertIn("image rebuild", report["reason"])


class WithoutComposerTests(SimpleTestCase):
    """DjangoLux runs fine without Composer; it only loses inline updates.

    Composer is required *for updates* from 1.8.0, not for DjangoLux to work. A
    laptop checkout, a bare `runserver`, or any deployment that never enabled
    inline updates must be unaffected — no crash, no volume, no network.
    """

    def test_inline_updates_are_off_unless_explicitly_enabled(self):
        """The default: nothing about the updater engages at all."""
        from dlux.updater.service import updates_enabled

        with override_settings():
            del settings.DLUX_INLINE_UPDATES_ENABLED
            self.assertFalse(updates_enabled())

    @override_settings(DLUX_UPDATE_RUNTIME_ROOT="/nonexistent/dlux-runtime")
    def test_reading_an_absent_runtime_volume_never_raises(self):
        """The panel reads these on a stack that has no volume at all."""
        self.assertEqual(package_request.read_availability(), {})
        self.assertEqual(package_request.read_ack(), {})
        self.assertEqual(package_request.pending_token(), "")
        self.assertEqual(package_request.composer_progress(), {})

    @override_settings(DLUX_INLINE_UPDATES_ENABLED=False)
    def test_queueing_is_refused_with_a_message_not_a_crash(self):
        from dlux.updater import UpdaterError
        from dlux.updater.service import queue_daily_check_if_due, queue_run

        with self.assertRaises(UpdaterError):
            queue_run("check")
        self.assertIsNone(queue_daily_check_if_due())

    @override_settings(DLUX_UPDATE_RUNTIME_ROOT="/nonexistent/dlux-runtime")
    def test_an_unusable_runtime_volume_is_a_named_error(self):
        """Not a raw OSError from inside mkdir — this is a configuration problem."""
        from dlux.updater import UpdaterError
        from dlux.updater.service import runtime_store

        with self.assertRaises(UpdaterError) as caught:
            runtime_store()
        self.assertIn("DLUX_INLINE_UPDATES_ENABLED", str(caught.exception))


class UnusableRuntimeVolumeTests(SimpleTestCase):
    """Updates on, but the volume backing them is not writable.

    The worst available outcome is the one to prevent: offering the button,
    accepting the click, and leaving the run at "queued" forever because nothing
    can drain it. The failure must be visible before anyone clicks.
    """

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        # Build an unwritable parent rather than assuming /opt is one: as root
        # (CI containers) it is writable, and the test would silently invert.
        self.locked = Path(self._tmp.name) / "locked"
        self.locked.mkdir()
        os.chmod(self.locked, 0o500)
        self.addCleanup(os.chmod, self.locked, 0o700)
        self.unwritable = str(self.locked / "runtime")

    def _problem(self, root):
        from dlux.updater.service import local_runtime_volume_problem

        with override_settings(DLUX_UPDATE_RUNTIME_ROOT=root):
            return local_runtime_volume_problem()

    def test_a_writable_path_reports_no_problem(self):
        self.assertEqual(self._problem(f"{self._tmp.name}/runtime"), "")

    def test_an_unwritable_root_is_reported(self):
        """The laptop case: the default /opt path is not writable without root."""
        if os.geteuid() == 0:
            self.skipTest("root can write anywhere; the probe cannot be exercised")
        self.assertIn("not writable", self._problem(self.unwritable))

    def test_the_probe_creates_nothing(self):
        """It runs on every panel render; it must not have side effects."""
        from pathlib import Path

        root = Path(self._tmp.name) / "runtime"
        self._problem(str(root))
        self.assertFalse(root.exists())

    def test_the_panel_reports_updates_unavailable_with_the_reason(self):
        from dlux.updater.service import inline_updates_available

        if os.geteuid() == 0:
            self.skipTest("root can write anywhere; the probe cannot be exercised")
        with override_settings(DLUX_INLINE_UPDATES_ENABLED=True,
                               DLUX_UPDATE_RUNTIME_ROOT=self.unwritable):
            self.assertFalse(inline_updates_available())

    def test_a_disabled_deployment_is_unavailable_without_blaming_the_volume(self):
        """Nothing is wrong there — updates are simply off, so say only that."""
        import inspect

        from dlux.updater import service

        with override_settings(DLUX_INLINE_UPDATES_ENABLED=False,
                               DLUX_UPDATE_RUNTIME_ROOT=self.unwritable):
            self.assertFalse(service.updates_enabled())
            self.assertFalse(service.inline_updates_available())
        # The reason is computed only when updates are switched on, so a disabled
        # deployment never shows a volume complaint it cannot act on.
        self.assertIn(
            "runtime_volume_problem(state) if updates_enabled() else",
            inspect.getsource(service.serialize_state),
        )


class RuntimeVolumeAuthorityTests(TestCase):
    """Whoever writes the runtime volume decides whether updates can run.

    Celery owns the write loop since 1.8.0 and web mounts the same volume
    read-only, so web probing its own mount answered a question nobody asked and
    disabled the panel — and refused a manual check — on a healthy deployment.
    Web reads the writer's recorded verdict instead.
    """

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.locked = Path(self._tmp.name) / "locked"
        self.locked.mkdir()
        os.chmod(self.locked, 0o500)
        self.addCleanup(os.chmod, self.locked, 0o700)
        self.unwritable = str(self.locked / "runtime")
        self.writable = f"{self._tmp.name}/runtime"

    def _read_only_web(self):
        return override_settings(
            DLUX_INLINE_UPDATES_ENABLED=True, DLUX_UPDATE_RUNTIME_ROOT=self.unwritable
        )

    def test_the_workers_verdict_beats_this_process_mount(self):
        from dlux.updater.service import get_ui_state, record_worker_volume_report

        if os.geteuid() == 0:
            self.skipTest("root can write anywhere; the probe cannot be exercised")
        record_worker_volume_report()
        with self._read_only_web():
            state = get_ui_state()
        self.assertEqual(state["unavailable_reason"], "")
        self.assertTrue(state["enabled"])

    def test_a_read_only_web_mount_no_longer_refuses_queueing(self):
        from dlux.updater.service import queue_run, record_worker_volume_report

        if os.geteuid() == 0:
            self.skipTest("root can write anywhere; the probe cannot be exercised")
        record_worker_volume_report()
        with self._read_only_web():
            run = queue_run("check", username="tester")
        self.assertEqual(run.action, "check")
        self.assertEqual(run.status, "queued")

    def test_the_workers_problem_is_what_the_panel_reports(self):
        from dlux.updater.service import get_ui_state, record_worker_volume_report

        record_worker_volume_report("The runtime volume at /opt/dlux-runtime is not writable.")
        with override_settings(DLUX_INLINE_UPDATES_ENABLED=True,
                               DLUX_UPDATE_RUNTIME_ROOT=self.writable):
            state = get_ui_state()
        self.assertIn("not writable", state["unavailable_reason"])
        self.assertFalse(state["enabled"])

    def test_without_a_report_the_local_probe_still_stands_in(self):
        """A laptop, a fresh install, a single-process deployment."""
        from dlux.updater.service import runtime_volume_problem

        if os.geteuid() == 0:
            self.skipTest("root can write anywhere; the probe cannot be exercised")
        with self._read_only_web():
            self.assertIn("not writable", runtime_volume_problem())

    def test_a_worker_that_went_quiet_refuses_the_queue(self):
        """Nothing would drain the run — the original guard's real concern."""
        from datetime import timedelta

        from django.utils import timezone

        from dlux.models import DluxUpdateState
        from dlux.updater import UpdaterError
        from dlux.updater.service import get_ui_state, queue_run, record_worker_volume_report

        record_worker_volume_report()
        DluxUpdateState.objects.filter(pk=1).update(
            worker_seen_at=timezone.now() - timedelta(hours=1)
        )
        with override_settings(DLUX_INLINE_UPDATES_ENABLED=True,
                               DLUX_UPDATE_RUNTIME_ROOT=self.writable):
            self.assertTrue(get_ui_state()["worker_stale"])
            with self.assertRaises(UpdaterError) as caught:
                queue_run("check")
        self.assertIn("has not reported", str(caught.exception))

    def test_the_report_is_not_rewritten_on_every_tick(self):
        """The state tick fires every few seconds; this is one row."""
        from dlux.updater.service import record_worker_volume_report

        first = record_worker_volume_report()
        stamp = first.worker_seen_at
        second = record_worker_volume_report()
        self.assertEqual(second.worker_seen_at, stamp)

    def test_a_changed_verdict_is_written_immediately(self):
        from dlux.updater.service import record_worker_volume_report, worker_volume_report

        record_worker_volume_report()
        record_worker_volume_report("volume gone")
        self.assertEqual(worker_volume_report()["problem"], "volume gone")


class ProgressTests(SimpleTestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.store = RuntimeStore(Path(self._tmp.name) / "runtime").ensure()
        self.addCleanup(self._tmp.cleanup)

    def _status(self, payload):
        from dlux.updater.image_update import status_path

        status_path(self.store).write_text(json.dumps(payload), encoding="utf-8")

    def test_package_progress_is_returned(self):
        self._status({"status": "running", "kind": "package", "message": "staging"})
        self.assertEqual(package_request.composer_progress(self.store)["message"], "staging")

    def test_an_image_deploys_progress_is_not_mistaken_for_a_package_update(self):
        self._status({"status": "running", "kind": "image"})
        self.assertEqual(package_request.composer_progress(self.store), {})

    def test_an_untagged_status_is_accepted(self):
        """Older Composer builds do not stamp a kind."""
        self._status({"status": "running"})
        self.assertEqual(package_request.composer_progress(self.store)["status"], "running")


class HandoffCollectsStaticTests(TestCase):
    """Nothing collected the new release's static files on a Composer stack.

    The inline path collects them as one of its own steps; `_process_apply`
    returns at the hand-off long before reaching it. So every Composer-executed
    deployment — the default since 1.8.0 — kept serving the previous release's
    CSS and JS against the new release's templates, with no error to explain it.
    """

    def setUp(self):
        self._tmp = TemporaryDirectory()
        root = Path(self._tmp.name)
        self.store = RuntimeStore(root / "runtime").ensure()
        # `_run_manage` shells out through the project's manage.py.
        self.base_dir = root / "project"
        self.base_dir.mkdir()
        (self.base_dir / "manage.py").write_text("# generated\n", encoding="utf-8")
        self.commands = []
        self.addCleanup(self._tmp.cleanup)

    def _models(self):
        from django.apps import apps

        return apps.get_model("dlux", "DluxUpdateRun"), apps.get_model("dlux", "DluxUpdateState")

    def _runner(self, returncode=0):
        class _Completed:
            def __init__(self):
                self.returncode = returncode
                self.stdout = "42 static files copied."
                self.stderr = ""

        def run(command, **kwargs):
            self.commands.append((list(command), kwargs.get("env") or {}))
            return _Completed()

        return run

    def _service(self, returncode=0):
        from dlux.updater.service import UpdateService

        return UpdateService(store=self.store, command_runner=self._runner(returncode))

    def _applying_run(self):
        Run, State = self._models()
        run = Run.objects.create(
            action=Run.ACTION_APPLY,
            status=Run.STATUS_APPLYING,
            is_active=True,
            target_version="1.8.11",
            started_at=timezone.now(),
        )
        state = State.load()
        state.active_run_token = run.token
        state.save(update_fields=["active_run_token"])
        return run

    def _ack(self, token, exit_code=0):
        package_request.ack_path(self.store).write_text(
            json.dumps({"token": token, "exit_code": exit_code}), encoding="utf-8"
        )

    def _collectstatic_calls(self):
        return [
            (command, env) for command, env in self.commands
            if "collectstatic" in command
        ]

    def test_an_applied_release_has_its_static_collected(self):
        run = self._applying_run()
        self._ack(run.token, 0)

        with override_settings(BASE_DIR=self.base_dir):
            finished = self._service().tick_package_update()

        calls = self._collectstatic_calls()
        self.assertEqual(len(calls), 1, "the release Composer applied was never collected")
        command, _env = calls[0]
        self.assertIn("--noinput", command)
        self.assertIn("--clear", command)
        finished.refresh_from_db()
        self.assertTrue(finished.report.get("static_collected"))

    def test_the_collected_release_is_the_one_on_the_volume(self):
        """Collecting from the baked image would write a *different* version's
        CSS and JS into the shared volume than the templates being served."""
        run = self._applying_run()
        self._ack(run.token, 0)
        release = Path(self.store.release_path("1.8.11"))
        release.mkdir(parents=True, exist_ok=True)
        self.store.write_active("1.8.11", source="volume", generation=self.store.read_generation() + 1)

        with override_settings(BASE_DIR=self.base_dir):
            self._service().tick_package_update()

        _command, env = self._collectstatic_calls()[0]
        self.assertIn(str(release), env.get("PYTHONPATH", ""))

    def test_a_rollback_collects_the_release_it_returned_to(self):
        Run, _State = self._models()
        run = self._applying_run()
        run.action = Run.ACTION_ROLLBACK
        run.save(update_fields=["action"])
        self._ack(run.token, 0)

        with override_settings(BASE_DIR=self.base_dir):
            self._service().tick_package_update()

        self.assertEqual(len(self._collectstatic_calls()), 1)

    def test_a_failed_apply_still_collects_what_composer_left_active(self):
        """Composer rolls a bad release back itself; the volume then holds the
        previous release's code and the new release's static."""
        run = self._applying_run()
        self._ack(run.token, 1)

        with override_settings(BASE_DIR=self.base_dir):
            self._service().tick_package_update()

        self.assertEqual(len(self._collectstatic_calls()), 1)

    def test_a_failed_collect_is_named_and_never_hidden(self):
        run = self._applying_run()
        self._ack(run.token, 0)

        Run, _State = self._models()
        with override_settings(BASE_DIR=self.base_dir):
            with self.assertLogs("dlux", level="WARNING") as captured:
                finished = self._service(returncode=1).tick_package_update()
        self.assertIn("collect static files", "\n".join(captured.output))

        finished.refresh_from_db()
        # The release really is active — Composer swapped and health-checked it —
        # so the run completes, but the mismatch is recorded rather than swallowed.
        self.assertEqual(finished.status, Run.STATUS_COMPLETED)
        self.assertFalse(finished.report.get("static_collected"))
        self.assertIn("collectstatic", finished.progress_log)

    def test_nothing_is_collected_without_an_acknowledgement(self):
        self._applying_run()

        with override_settings(BASE_DIR=self.base_dir):
            self.assertIsNone(self._service().tick_package_update())

        self.assertEqual(self._collectstatic_calls(), [])
