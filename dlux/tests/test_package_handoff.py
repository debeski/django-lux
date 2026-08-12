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
from tempfile import TemporaryDirectory
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, override_settings

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
        from dlux.updater.service import runtime_volume_problem

        with override_settings(DLUX_UPDATE_RUNTIME_ROOT=root):
            return runtime_volume_problem()

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
            "runtime_volume_problem() if updates_enabled() else",
            inspect.getsource(service.serialize_state),
        )


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
