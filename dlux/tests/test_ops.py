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
            ["agent-update", "check-fix-apply", "service-recreate", "service-restart"],
        )

    def test_the_read_only_operations_are_the_two_checks(self):
        self.assertEqual(
            sorted(n for n, spec in ops.OPERATIONS.items() if not spec["changes_deployment"]),
            ["agent-check", "check", "logs-tail", "services"],
            "the deployment check carries the repair preview; a separate preview "
            "operation is not offered, and asking whether the resident Composer "
            "has an update must never need a password",
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

    def _finished_apply(self, status):
        run = DluxOpsRun.objects.create(operation="check-fix-apply", requested_by_username="root")
        run.finish(status, result={
            "findings": [{"level": "ok", "name": "maintenance-page", "message": "Served from the runtime volume."}],
            "repairs": [{"name": "fix:maintenance-page", "files": [], "diff": "", "note": "Migrated."}],
        })
        run.save()
        return run

    def test_a_completed_apply_consumes_the_preview_and_becomes_the_check(self):
        self._completed_preview()
        applied = self._finished_apply(DluxOpsRun.STATUS_COMPLETED)
        state = get_ops_state()
        self.assertFalse(state["has_preview"], "what the preview showed is on disk now")
        self.assertEqual(state["check"]["token"], applied.token, "the panel shows the result, not the old preview")
        self.assertEqual([r["diff"] for r in state["check"]["repairs"]], [""], "nothing left to apply")
        with self.assertRaises(UpdaterError):
            self._queue("check-fix-apply")
        self._completed_preview()
        self.assertTrue(get_ops_state()["has_preview"], "a new check makes a new preview")

    def test_a_failed_apply_leaves_the_preview_to_retry(self):
        preview = self._completed_preview()
        self._finished_apply(DluxOpsRun.STATUS_FAILED)
        state = get_ops_state()
        self.assertTrue(state["has_preview"])
        self.assertEqual(state["check"]["token"], preview.token)

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

    def test_the_beta_that_introduced_an_operation_may_run_it(self):
        # PEP 440 orders 1.5.2b1 below 1.5.2, so a floor written as the release
        # refuses its own beta — which is what a rig running the published beta
        # hit: every operation unavailable on the Composer that implements them.
        for name, spec in ops.OPERATIONS.items():
            floor = spec["min_composer"]
            later = ".".join(floor.split(".")[:2]) + ".9"
            for version in (floor, later):
                allowed, reason = ops.supports(name, version)
                self.assertTrue(allowed, f"{name} refused on Composer {version}: {reason}")
        self.assertFalse(ops.supports("check", "1.5.1")[0], "the release before it is still too old")

    def test_an_old_agent_is_told_the_one_command_that_gets_it_current(self):
        # The agent rows are where a deployment on an older Composer lands, and
        # "update the Composer agent first" is what those rows do — so on them
        # it is circular. Found by putting a rig back on 1.5.1.
        for name in ("agent-check", "agent-update"):
            allowed, reason = ops.supports(name, "1.5.1")
            self.assertFalse(allowed)
            self.assertIn("./start.sh agent update", reason)
        _allowed, reason = ops.supports("check", "1.5.1")
        self.assertNotIn("./start.sh", reason, "the deployment check is not the update path")

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
        # Ordered the way PEP 440 orders it, not by string: 1.5.2b1 is newer
        # than 1.5.1 and older than 1.5.2, and it satisfies a floor written as
        # the beta that introduced the operation.
        self.assertTrue(ops.supports("check", "1.5.2b1")[0])
        self.assertFalse(ops.supports("check", "1.5.2a1")[0], "an earlier prerelease is still too old")
        self.assertFalse(ops.supports("check", "1.5.1")[0])

    def test_the_composer_update_gets_a_longer_budget(self):
        self.assertGreater(ops.timeout_for("agent-update"), ops.timeout_for("check"))


class ComposerBehindTests(SimpleTestCase):
    """DjangoLux may be updated before its Composer; the card has to say so."""

    def _package(self, composer_spec):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        requires = {"services": {"composer": composer_spec}} if composer_spec else {}
        with open(f"{tmp.name}/release-manifest.json", "w", encoding="utf-8") as handle:
            json.dump({"version": "9.9.9", "requires": requires}, handle)
        return tmp.name

    def test_the_floor_is_read_from_the_running_release(self):
        with open(ops.Path(ops.__file__).resolve().parents[1] / "release-manifest.json", encoding="utf-8") as handle:
            declared = json.load(handle)["requires"]["services"]["composer"]
        self.assertEqual(ops.required_composer(), declared.removeprefix(">="))
        self.assertEqual(ops.required_composer(self._package(">=1.5.3b1")), "1.5.3b1")
        for spec in ("", "==1.5.3", ">=1.5,<2"):
            with self.subTest(spec=spec):
                self.assertEqual(ops.required_composer(self._package(spec)), "")

    def test_a_resident_too_old_for_the_card_is_sent_to_the_host(self):
        behind = ops.composer_behind("1.5.1", self._package(">=1.5.3b1"))
        self.assertEqual(behind, {"version": "1.5.1", "required": "1.5.3b1", "ops_blocked": True})

    def test_a_resident_the_card_can_still_update_is_sent_to_the_card(self):
        # 1.5.2 answers every operation, including the agent update, so the host
        # commands would send an administrator to a shell for no reason.
        behind = ops.composer_behind("1.5.2", self._package(">=1.5.3b1"))
        self.assertEqual(behind, {"version": "1.5.2", "required": "1.5.3b1", "ops_blocked": False})

    def test_an_operation_floor_counts_without_a_release_floor(self):
        behind = ops.composer_behind("1.5.1", self._package(""))
        self.assertEqual(behind["required"], "1.5.2b1")
        self.assertTrue(behind["ops_blocked"])

    def test_a_current_or_unknown_resident_says_nothing(self):
        package = self._package(">=1.5.3b1")
        for value in ("1.5.3b1", "1.5.3", "1.6.0", "", None, "not-a-version"):
            with self.subTest(value=value):
                self.assertIsNone(ops.composer_behind(value, package))

    def test_the_card_renders_the_notice(self):
        from pathlib import Path

        root = Path(ops.__file__).resolve().parents[1]
        template = (root / "templates/dlux/system/options.html").read_text(encoding="utf-8")
        script = (root / "static/dlux/system/js/ops.js").read_text(encoding="utf-8")
        self.assertIn("data-dlux-ops-composer-notice", template)
        for key in ("dlux_ops_composer_behind_host", "dlux_ops_composer_behind_card"):
            self.assertIn(key, template)
        for name in ("labelComposerBehindHost", "labelComposerBehindCard", "state.composer_behind"):
            self.assertIn(name, script)


@override_settings(DLUX_INLINE_UPDATES_ENABLED=True)
class RowStateTests(TestCase):
    """What the two rows in the Updates card read, and when they read nothing.

    Each row keeps its own last answer: running the Composer check must not blank
    what the deployment check found, and a resident pair that was just replaced
    must not still claim to be "up to date" on the strength of a check taken
    before the replacement.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        RuntimeStore(self._tmp.name).ensure()

    def _completed(self, operation, result, *, minutes_ago=0):
        run = DluxOpsRun.objects.create(operation=operation, status=DluxOpsRun.STATUS_COMPLETED,
                                        is_active=False, result=result)
        when = timezone.now() - timedelta(minutes=minutes_ago)
        DluxOpsRun.objects.filter(pk=run.pk).update(created_at=when, completed_at=when)
        return DluxOpsRun.objects.get(pk=run.pk)

    def _state(self):
        with override_settings(DLUX_UPDATE_RUNTIME_ROOT=self._tmp.name):
            return get_ops_state()

    def test_a_deployment_that_was_never_checked_reports_nothing(self):
        state = self._state()
        self.assertIsNone(state["check"])
        self.assertFalse(state["resident"]["checked"])
        self.assertFalse(state["resident"]["update_available"])

    def test_the_composer_check_reaches_the_row(self):
        self._completed("agent-check", {"resident": {
            "version": "1.5.2", "published_version": "1.6.0", "channel": "stable",
            "checked": True, "update_available": True,
        }})
        resident = self._state()["resident"]
        self.assertTrue(resident["update_available"])
        self.assertEqual(resident["published_version"], "1.6.0")
        self.assertTrue(resident["checked_at"])

    def test_a_composer_check_does_not_blank_the_deployment_row(self):
        self._completed("check", {"findings": [{"level": "ok", "name": "docker", "message": "up"}]},
                        minutes_ago=5)
        self._completed("agent-check", {"resident": {"checked": True, "version": "1.5.2"}})
        state = self._state()
        self.assertEqual(state["run"]["operation"], "agent-check", "the newest run is the Composer check")
        self.assertEqual(state["check"]["operation"], "check")
        self.assertEqual(state["check"]["summary"]["ok"], 1)

    def test_an_update_since_the_check_makes_the_row_ask_again(self):
        self._completed("agent-check", {"resident": {
            "version": "1.5.2", "checked": True, "update_available": True,
        }}, minutes_ago=5)
        self._completed("agent-update", {"exit_code": 0})
        resident = self._state()["resident"]
        self.assertFalse(resident["checked"], "the pair was replaced; what it is now is unknown")
        self.assertFalse(resident["update_available"])

    def test_a_result_without_a_resident_block_is_not_a_check(self):
        # A 1.5.2 agent answers `agent-check`; an older one would answer with a
        # refusal, and the row must not read that as "up to date".
        self._completed("agent-check", {"findings": []})
        self.assertFalse(self._state()["resident"]["checked"])

    def test_an_unreadable_registry_gives_the_row_a_reason_to_show(self):
        self._completed("agent-check", {
            "findings": [{"status": "warn", "message": "Could not read the registry version."}],
            "resident": {"checked": False, "update_available": False},
        })
        resident = self._state()["resident"]
        self.assertFalse(resident["checked"])
        self.assertEqual(resident["detail"], "Could not read the registry version.")

    def test_the_card_has_the_states_a_check_can_end_in(self):
        from pathlib import Path
        root = Path(ops.__file__).resolve().parents[1]
        card = (root / "templates/dlux/system/options.html").read_text(encoding="utf-8")
        panel = (root / "templates/dlux/system/operations_panel.html").read_text(encoding="utf-8")
        card_script = (root / "static/dlux/system/js/ops.js").read_text(encoding="utf-8")
        panel_script = (root / "static/dlux/system/js/operations_panel.js").read_text(encoding="utf-8")
        self.assertIn("data-label-composer-unknown", card)
        for name in ("TONE_GLYPH", "labelComposerUnknown"):
            self.assertIn(name, card_script)
        for hook in ("data-dlux-ops-panel-norepair", "data-dlux-ops-panel-apply", "data-label-no-repair"):
            self.assertIn(hook, panel)
        for name in ("labelNoRepair", "repairsOf", "has_preview"):
            self.assertIn(name, panel_script)

    def test_the_run_carries_the_resident_block_to_the_browser(self):
        run = self._completed("agent-check", {"resident": {"checked": True, "update_available": False}})
        self.assertEqual(serialize_ops_run(run)["resident"], {"checked": True, "update_available": False})


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
        self.assertEqual(state["composer_behind"]["version"], "1.5.0")
        self.assertTrue(state["composer_behind"]["ops_blocked"])


class PanelOperationTests(SimpleTestCase):
    """The Operations panel's service operations: validated arguments only."""

    def test_service_names_are_validated_and_lines_clamped(self):
        self.assertEqual(ops.normalize_params("service-restart", {"service": "web"}), {"service": "web"})
        self.assertEqual(ops.normalize_params("logs-tail", {"service": "celery", "lines": "99999"}),
                         {"service": "celery", "lines": ops.LOG_LINES_MAX})
        self.assertEqual(ops.normalize_params("logs-tail", {"service": "web", "lines": "x"})["lines"],
                         ops.LOG_LINES_DEFAULT)
        self.assertEqual(ops.normalize_params("logs-tail", {"service": ""}), {"lines": ops.LOG_LINES_DEFAULT},
                         "no service means every service")
        with self.assertRaises(UpdaterError):
            ops.normalize_params("logs-tail", {"service": "web;id"})
        self.assertEqual(ops.normalize_params("check", {"service": "web"}), {}, "check takes no arguments")
        for bad in ("", "web;rm -rf /", "../db", "a" * 65, "ويب"):
            with self.subTest(service=bad), self.assertRaises(UpdaterError):
                ops.normalize_params("service-recreate", {"service": bad})

    def test_panel_operations_never_mark_the_deployment_behind(self):
        # A Composer that predates the panel just disables its buttons.
        self.assertIsNone(ops.composer_behind("1.6.1"))
        allowed, reason = ops.supports("service-restart", "1.6.1")
        self.assertFalse(allowed)
        self.assertIn("1.7.0b2", reason)
        self.assertFalse(ops.supports("logs-tail", "1.7.0b2")[0], "all-services logs arrived in 1.7.0b3")
        self.assertTrue(ops.supports("logs-tail", "1.7.0b3")[0])

    def test_restart_and_recreate_change_the_deployment_logs_do_not(self):
        self.assertTrue(ops.OPERATIONS["service-restart"]["changes_deployment"])
        self.assertTrue(ops.OPERATIONS["service-recreate"]["changes_deployment"])
        self.assertFalse(ops.OPERATIONS["logs-tail"]["changes_deployment"])
        self.assertFalse(ops.OPERATIONS["services"]["changes_deployment"])


class OperationLabelTests(TestCase):
    def test_every_operation_label_is_translated(self):
        from dlux.translations import DLUX_STRINGS
        self.assertEqual(set(ops.OPERATION_LABEL_KEYS), set(ops.OPERATIONS))
        for key in ops.OPERATION_LABEL_KEYS.values():
            self.assertIn(key, DLUX_STRINGS["en"], key)
            self.assertIn(key, DLUX_STRINGS["ar"], key)
        with mock.patch("dlux.translations.runtime.get_current_language_code", return_value="ar"):
            labels = {op["name"]: op["label"] for op in get_ops_state()["operations"]}
        self.assertEqual(labels["service-restart"], DLUX_STRINGS["ar"]["dlux_ops_op_restart"])


class PanelRunLifecycleTests(OpsRunLifecycleTests):
    def test_arguments_travel_with_the_request_and_results_come_back(self):
        with override_settings(DLUX_UPDATE_RUNTIME_ROOT=self._tmp.name), \
                mock.patch("dlux.updater.ops.resident_composer_version", return_value="1.7.0b3"):
            run = queue_ops_run("logs-tail", username="root", params={"service": "web", "lines": "50"})
        self.assertEqual(run.params, {"service": "web", "lines": 50})
        tick_ops_run(self.service)
        request = json.loads(ops.request_path(self.store).read_text(encoding="utf-8"))
        self.assertEqual((request["service"], request["lines"]), ("web", 50))
        ops.ack_path(self.store).write_text(json.dumps({"token": run.token, "exit_code": 0, "error": ""}), encoding="utf-8")
        ops.result_path(self.store).write_text(json.dumps({
            "token": run.token, "operation": "logs-tail", "exit_code": 0, "logs": "hello\n", "findings": [],
        }), encoding="utf-8")
        tick_ops_run(self.service)
        run.refresh_from_db()
        payload = serialize_ops_run(run)
        self.assertEqual(payload["logs"], "hello\n")
        self.assertEqual(payload["params"], {"service": "web", "lines": 50})
        # The panel reads logs from their own slot, so a later run cannot hide them.
        with mock.patch("dlux.updater.ops.resident_composer_version", return_value="1.7.0b3"):
            later = queue_ops_run("services", username="root")
        state = get_ops_state()
        self.assertEqual(state["run"]["token"], later.token)
        self.assertEqual(state["logs"]["logs"], "hello\n")


@override_settings(DLUX_INLINE_UPDATES_ENABLED=True)
class PanelViewTests(FixApplyViewTests):
    def test_the_panel_renders_for_a_superuser_only(self):
        client = Client()
        client.force_login(self.superuser)
        payload = client.get(reverse("dlux_operations_panel")).json()
        self.assertIn("data-dlux-ops-panel", payload["html"])
        self.assertIn("operations_panel.js", payload["html"])
        staff = get_user_model().objects.create_user(username="staff", password="pw-staff-1234", is_staff=True)
        client.force_login(staff)
        self.assertIn(client.get(reverse("dlux_operations_panel")).status_code, (302, 403, 404))

    def test_restarting_a_service_needs_the_password_and_a_valid_name(self):
        with mock.patch("dlux.updater.ops.resident_composer_version", return_value="1.7.0b2"):
            self.assertNotEqual(self._post({"operation": "service-restart", "service": "web"}).status_code, 200)
            refused = self._post({"operation": "service-restart", "service": "web;id", "current_password": self.password})
            self.assertEqual(refused.status_code, 409)
            response = self._post({"operation": "service-restart", "service": "web", "current_password": self.password})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["run"]["params"], {"service": "web"})

    def test_reading_logs_needs_no_password(self):
        with mock.patch("dlux.updater.ops.resident_composer_version", return_value="1.7.0b3"):
            response = self._post({"operation": "logs-tail", "service": "web", "lines": "20"})
        self.assertEqual(response.status_code, 200)


class OperationsPlacementTests(SimpleTestCase):
    """Checking and repairing the deployment moved from the Updates card to the panel."""

    def test_the_updates_card_keeps_only_the_composer_row(self):
        from pathlib import Path

        template = (Path(ops.__file__).resolve().parents[1] / "templates" / "dlux" / "system" / "options.html").read_text(encoding="utf-8")
        self.assertNotIn('data-dlux-ops-check="check"', template)
        self.assertNotIn("dluxOpsResultModal", template)
        self.assertIn('data-dlux-ops-check="agent-check"', template)
        self.assertIn("{% url 'dlux_operations_panel' %}", template)
