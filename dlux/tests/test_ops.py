"""The Operations card: one named operation, handed to Composer, answered once.

Dlux holds no Docker authority, so every one of these asserts the same shape as
the update handoff: a typed request carrying the run's token, a result read back
only under that token, and a refusal for anything that is not a named operation.
"""

import json
import tempfile
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from dlux.models.settings import SystemSettings
from dlux.models.updater import DluxOpsRun, DluxUpdateState
from dlux.updater import UpdaterError, ops
from dlux.updater.runtime import RuntimeStore
from dlux.updater.service import (
    get_ops_state, queue_ops_run, serialize_ops_run, tick_ops_run,
)


class OperationTableTests(SimpleTestCase):
    def test_only_named_operations_are_accepted(self):
        self.assertEqual(ops.normalize_operation("CHECK"), "check")
        for value in ("", None, "shell", "check --fix", "restart"):
            with self.subTest(value=value), self.assertRaises(UpdaterError):
                ops.normalize_operation(value)

    def test_every_operation_declares_its_composer_floor_and_blast_radius(self):
        for name, spec in ops.OPERATIONS.items():
            with self.subTest(operation=name):
                self.assertTrue(spec["min_composer"])
                self.assertIn("changes_deployment", spec)
                self.assertTrue(spec["label"])

    def test_the_write_operations_are_the_apply_and_the_composer_update(self):
        self.assertEqual(
            sorted(n for n, spec in ops.OPERATIONS.items() if spec["changes_deployment"]),
            ["agent-update", "check-fix-apply"],
        )

    def test_the_check_is_the_only_read_only_operation(self):
        self.assertEqual(
            sorted(n for n, spec in ops.OPERATIONS.items() if not spec["changes_deployment"]),
            ["check"],
            "the check carries the repair preview; a separate preview operation is not offered",
        )

    def test_only_the_apply_needs_a_preview(self):
        self.assertEqual(
            [n for n, spec in ops.OPERATIONS.items() if spec["needs_preview"]],
            ["check-fix-apply"],
        )

    def test_a_digest_must_look_like_one(self):
        self.assertEqual(ops.normalize_digest("A" * 64), "a" * 64)
        for bad in ("", None, "z" * 64, "abc", "../etc/passwd", "a" * 63):
            with self.subTest(bad=bad), self.assertRaises(UpdaterError):
                ops.normalize_digest(bad)

    def test_a_result_is_only_this_runs_result(self):
        with tempfile.TemporaryDirectory() as root:
            store = RuntimeStore(root).ensure()
            ops.result_path(store).write_text(json.dumps({"token": "older", "findings": [{}]}), encoding="utf-8")
            self.assertEqual(ops.read_result(store, token="mine"), {})
            self.assertEqual(ops.read_result(store, token="older")["token"], "older")

    def test_the_summary_counts_by_level(self):
        summary = ops.summarize({"findings": [
            {"level": "ok"}, {"level": "warn"}, {"level": "fail"}, {"level": "fail"}, "not a finding",
        ]})
        self.assertEqual(summary, {"total": 4, "ok": 1, "warn": 1, "fail": 2})


@override_settings(DLUX_INLINE_UPDATES_ENABLED=True)
class OpsRunLifecycleTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = RuntimeStore(self._tmp.name).ensure()
        self.service = mock.Mock(store=self.store)
        state = DluxUpdateState.load()
        state.worker_seen_at = timezone.now()
        state.save()

    def _queue(self):
        with override_settings(DLUX_UPDATE_RUNTIME_ROOT=self._tmp.name):
            return queue_ops_run("check", username="root")

    def _answer(self, token, *, findings=None, exit_code=0, error=""):
        ops.ack_path(self.store).write_text(
            json.dumps({"token": token, "exit_code": exit_code, "error": error}), encoding="utf-8")
        ops.result_path(self.store).write_text(json.dumps({
            "token": token, "operation": "check", "exit_code": exit_code,
            "composer_version": "1.5.0",
            "findings": findings if findings is not None else [
                {"level": "ok", "name": "docker", "message": "Docker daemon reachable."},
            ],
        }), encoding="utf-8")

    def test_the_first_tick_hands_the_request_over(self):
        run = self._queue()
        self.assertEqual(run.status, DluxOpsRun.STATUS_QUEUED)
        tick_ops_run(self.service)
        run.refresh_from_db()
        request = json.loads(ops.request_path(self.store).read_text(encoding="utf-8"))
        self.assertEqual(request["token"], run.token)
        self.assertEqual(request["operation"], "check")
        self.assertEqual(run.status, DluxOpsRun.STATUS_RUNNING)

    def test_the_answer_finishes_the_run_with_its_findings(self):
        run = self._queue()
        tick_ops_run(self.service)
        self._answer(run.token, findings=[
            {"level": "fail", "name": "resident-commands", "message": "flat command", "fix": "check --fix"},
        ])
        tick_ops_run(self.service)
        run.refresh_from_db()
        self.assertEqual(run.status, DluxOpsRun.STATUS_COMPLETED)
        self.assertFalse(run.is_active)
        self.assertEqual(run.result["findings"][0]["name"], "resident-commands")

    def test_a_check_that_finds_problems_is_still_a_successful_run(self):
        # `check` exits non-zero when the DEPLOYMENT has a problem. That is a
        # finding to render, not an operation that failed.
        run = self._queue()
        tick_ops_run(self.service)
        self._answer(run.token, exit_code=1, findings=[{"level": "fail", "name": "topology", "message": "no composer"}])
        tick_ops_run(self.service)
        run.refresh_from_db()
        self.assertEqual(run.status, DluxOpsRun.STATUS_COMPLETED)
        self.assertEqual(serialize_ops_run(run)["summary"]["fail"], 1)

    def test_a_refusal_from_composer_fails_the_run(self):
        run = self._queue()
        tick_ops_run(self.service)
        self._answer(run.token, exit_code=2, error="Unknown operation.")
        tick_ops_run(self.service)
        run.refresh_from_db()
        self.assertEqual(run.status, DluxOpsRun.STATUS_FAILED)
        self.assertIn("Unknown operation", run.error)

    def test_another_runs_answer_is_not_read_as_this_ones(self):
        run = self._queue()
        tick_ops_run(self.service)
        self._answer("some-other-run")
        tick_ops_run(self.service)
        run.refresh_from_db()
        self.assertEqual(run.status, DluxOpsRun.STATUS_RUNNING, "a foreign ack must not finish this run")

    def test_an_older_composer_that_never_answers_says_so(self):
        run = self._queue()
        tick_ops_run(self.service)
        DluxOpsRun.objects.filter(pk=run.pk).update(
            requested_at=timezone.now() - timedelta(seconds=ops.REQUEST_TIMEOUT_SECONDS + 1))
        tick_ops_run(self.service)
        run.refresh_from_db()
        self.assertEqual(run.status, DluxOpsRun.STATUS_FAILED)
        self.assertIn(ops.OPERATIONS["check"]["min_composer"], run.error)

    def test_a_second_operation_is_refused_while_one_is_running(self):
        self._queue()
        with self.assertRaises(UpdaterError):
            self._queue()

    def test_a_finished_operation_frees_the_panel(self):
        run = self._queue()
        tick_ops_run(self.service)
        self._answer(run.token)
        tick_ops_run(self.service)
        self.assertIsNotNone(self._queue())

    def test_the_card_state_names_the_operations_and_the_last_run(self):
        run = self._queue()
        state = get_ops_state()
        self.assertEqual([o["name"] for o in state["operations"]], list(ops.OPERATIONS))
        self.assertEqual(state["run"]["token"], run.token)
        self.assertEqual(state["run"]["status"], DluxOpsRun.STATUS_QUEUED)


@override_settings(DLUX_INLINE_UPDATES_ENABLED=True)
class OpsViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.superuser = User.objects.create_superuser(
            username="root", email="root@example.com", password="pw-root-1234")
        self.staff = User.objects.create_user(
            username="staff", email="staff@example.com", password="pw-staff-1234", is_staff=True)
        settings_row = SystemSettings.load()
        settings_row.is_configured = True
        settings_row.save()
        state = DluxUpdateState.load()
        state.worker_seen_at = timezone.now()
        state.save()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        RuntimeStore(self._tmp.name).ensure()
        self.run_url = reverse("dlux_ops_run")
        self.state_url = reverse("dlux_ops_state")

    def _client(self, user):
        client = Client()
        client.force_login(user)
        return client

    def test_a_superuser_queues_an_operation_on_a_read_only_mount(self):
        # Web writes nothing: the worker hands the request over.
        erofs = OSError(30, "Read-only file system")
        with override_settings(DLUX_UPDATE_RUNTIME_ROOT=self._tmp.name), \
                mock.patch("dlux.updater.channel._atomic_json", side_effect=erofs):
            response = self._client(self.superuser).post(self.run_url, {"operation": "check"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["run"]["operation"], "check")
        self.assertEqual(DluxOpsRun.objects.count(), 1)

    def test_an_unknown_operation_is_refused(self):
        with override_settings(DLUX_UPDATE_RUNTIME_ROOT=self._tmp.name):
            response = self._client(self.superuser).post(self.run_url, {"operation": "rm -rf /"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(DluxOpsRun.objects.count(), 0)

    def test_a_non_superuser_can_neither_run_nor_read(self):
        client = self._client(self.staff)
        with override_settings(DLUX_UPDATE_RUNTIME_ROOT=self._tmp.name):
            self.assertIn(client.post(self.run_url, {"operation": "check"}).status_code, (302, 403, 404))
            self.assertIn(client.get(self.state_url).status_code, (302, 403, 404))
        self.assertEqual(DluxOpsRun.objects.count(), 0)

    def test_get_is_not_a_mutation(self):
        with override_settings(DLUX_UPDATE_RUNTIME_ROOT=self._tmp.name):
            self.assertEqual(self._client(self.superuser).get(self.run_url).status_code, 405)

    def test_the_state_endpoint_serves_the_card(self):
        with override_settings(DLUX_UPDATE_RUNTIME_ROOT=self._tmp.name):
            client = self._client(self.superuser)
            client.post(self.run_url, {"operation": "check"})
            payload = client.get(self.state_url).json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["run"]["status"], DluxOpsRun.STATUS_QUEUED)
        self.assertIn("check", [o["name"] for o in payload["operations"]])

    def test_running_an_operation_is_audited(self):
        with override_settings(DLUX_UPDATE_RUNTIME_ROOT=self._tmp.name), \
                mock.patch("dlux.views.updater.log_audit_event") as audit:
            self._client(self.superuser).post(self.run_url, {"operation": "check"})
        self.assertEqual(audit.call_args[0][2], "DLUX_OPS_RUN")


@override_settings(DLUX_INLINE_UPDATES_ENABLED=True)
class FixApplyGuardTests(TestCase):
    """An apply may only write the repair a preview showed, after a password."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = RuntimeStore(self._tmp.name).ensure()
        self.service = mock.Mock(store=self.store)
        state = DluxUpdateState.load()
        state.worker_seen_at = timezone.now()
        state.save()
        self.digest = "a1" * 32

    def _completed_preview(self, digest=None):
        run = DluxOpsRun.objects.create(operation="check", requested_by_username="root")
        run.finish(DluxOpsRun.STATUS_COMPLETED, result={
            "repairs": [{"name": "resident-block", "diff": "--- a\n+++ b\n", "files": ["compose.yml"]}],
            ops.DIGEST_FIELD: self.digest if digest is None else digest,
        })
        run.save()
        return run

    def _queue(self, operation):
        with override_settings(DLUX_UPDATE_RUNTIME_ROOT=self._tmp.name):
            return queue_ops_run(operation, username="root")

    def test_an_apply_without_a_preview_is_refused_before_composer_hears_of_it(self):
        with self.assertRaises(UpdaterError):
            self._queue("check-fix-apply")
        self.assertFalse(ops.request_path(self.store).exists())

    def test_a_preview_with_an_unusable_digest_does_not_count(self):
        self._completed_preview(digest="not-a-digest")
        with self.assertRaises(UpdaterError):
            self._queue("check-fix-apply")

    def test_the_request_carries_the_previews_digest(self):
        self._completed_preview()
        run = self._queue("check-fix-apply")
        tick_ops_run(self.service)
        request = json.loads(ops.request_path(self.store).read_text(encoding="utf-8"))
        self.assertEqual(request["operation"], "check-fix-apply")
        self.assertEqual(request[ops.DIGEST_FIELD], self.digest)
        self.assertEqual(request["token"], run.token)

    def test_a_check_request_never_carries_a_digest(self):
        DluxOpsRun.objects.all().delete()
        self._queue("check")
        tick_ops_run(self.service)
        request = json.loads(ops.request_path(self.store).read_text(encoding="utf-8"))
        self.assertNotIn(ops.DIGEST_FIELD, request)

    def test_the_card_reports_whether_a_preview_is_available(self):
        self.assertFalse(get_ops_state()["has_preview"])
        self._completed_preview()
        self.assertTrue(get_ops_state()["has_preview"])

    def test_a_previews_repairs_reach_the_card(self):
        run = self._completed_preview()
        serialized = serialize_ops_run(run)
        self.assertEqual(serialized["repairs"][0]["name"], "resident-block")
        self.assertIn("+++ b", serialized["repairs"][0]["diff"])


@override_settings(DLUX_INLINE_UPDATES_ENABLED=True)
class FixApplyViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.password = "pw-root-1234"
        self.superuser = User.objects.create_superuser(
            username="root", email="root@example.com", password=self.password)
        settings_row = SystemSettings.load()
        settings_row.is_configured = True
        settings_row.save()
        state = DluxUpdateState.load()
        state.worker_seen_at = timezone.now()
        state.save()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        RuntimeStore(self._tmp.name).ensure()
        self.url = reverse("dlux_ops_run")
        preview = DluxOpsRun.objects.create(operation="check")
        preview.finish(DluxOpsRun.STATUS_COMPLETED, result={ops.DIGEST_FIELD: "b2" * 32, "repairs": []})
        preview.save()

    def _post(self, data):
        client = Client()
        client.force_login(self.superuser)
        with override_settings(DLUX_UPDATE_RUNTIME_ROOT=self._tmp.name):
            return client.post(self.url, data)

    def test_an_apply_without_the_password_is_refused(self):
        response = self._post({"operation": "check-fix-apply"})
        self.assertNotEqual(response.status_code, 200)
        self.assertFalse(DluxOpsRun.objects.filter(operation="check-fix-apply").exists())

    def test_an_apply_with_the_wrong_password_is_refused(self):
        response = self._post({"operation": "check-fix-apply", "current_password": "not-it"})
        self.assertNotEqual(response.status_code, 200)
        self.assertFalse(DluxOpsRun.objects.filter(operation="check-fix-apply").exists())

    def test_an_apply_with_the_password_is_queued(self):
        response = self._post({"operation": "check-fix-apply", "current_password": self.password})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["run"]["operation"], "check-fix-apply")

    def test_a_check_needs_no_password(self):
        response = self._post({"operation": "check"})
        self.assertEqual(response.status_code, 200)

    def test_updating_the_resident_composer_needs_the_password(self):
        self.assertNotEqual(self._post({"operation": "agent-update"}).status_code, 200)
        self.assertFalse(DluxOpsRun.objects.filter(operation="agent-update").exists())
        response = self._post({"operation": "agent-update", "current_password": self.password})
        self.assertEqual(response.status_code, 200)


class ComposerVersionGateTests(SimpleTestCase):
    """An operation the resident Composer cannot perform is not offered."""

    def test_an_older_resident_blocks_the_operation(self):
        allowed, reason = ops.supports("check", "1.5.0")
        self.assertFalse(allowed)
        self.assertIn("1.5.2", reason)
        self.assertIn("1.5.0", reason)

    def test_the_required_version_is_allowed(self):
        self.assertEqual(ops.supports("check", "1.5.2"), (True, ""))
        self.assertEqual(ops.supports("check", "1.6.0")[0], True)

    def test_an_unknown_version_is_not_a_refusal(self):
        # The agent may predate the status file; the run's own timeout still
        # names the floor, and refusing here would block a working deployment.
        for value in ("", None, "not-a-version"):
            with self.subTest(value=value):
                self.assertTrue(ops.supports("check", value)[0])

    def test_a_prerelease_resident_counts_as_its_own_version(self):
        self.assertFalse(ops.supports("check", "1.5.2b1")[0])

    def test_the_composer_update_gets_a_longer_budget(self):
        self.assertGreater(ops.timeout_for("agent-update"), ops.timeout_for("check"))


@override_settings(DLUX_INLINE_UPDATES_ENABLED=True)
class GatedQueueTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        RuntimeStore(self._tmp.name).ensure()
        state = DluxUpdateState.load()
        state.worker_seen_at = timezone.now()
        state.save()

    def test_an_operation_the_resident_cannot_do_is_refused_before_it_is_queued(self):
        with override_settings(DLUX_UPDATE_RUNTIME_ROOT=self._tmp.name), \
                mock.patch("dlux.updater.ops.resident_composer_version", return_value="1.5.0"):
            with self.assertRaises(UpdaterError):
                queue_ops_run("check", username="root")
        self.assertEqual(DluxOpsRun.objects.count(), 0)

    def test_the_card_marks_it_unavailable_with_the_reason(self):
        with override_settings(DLUX_UPDATE_RUNTIME_ROOT=self._tmp.name), \
                mock.patch("dlux.updater.ops.resident_composer_version", return_value="1.5.0"):
            state = get_ops_state()
        self.assertEqual(state["composer_version"], "1.5.0")
        self.assertTrue(all(not o["available"] for o in state["operations"]))
        self.assertIn("1.5.2", state["operations"][0]["unavailable_reason"])
