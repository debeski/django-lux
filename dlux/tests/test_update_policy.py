"""DLUX_UPDATE_POLICY: which update paths a deployment allows, and who refuses."""

import json
import os
import tempfile
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from dlux import doctor
from dlux.models.settings import SystemSettings
from dlux.models.updater import DluxImageUpdate, DluxOpsRun, DluxUpdateRun, DluxUpdateState
from dlux.updater import UpdaterError
from dlux.updater import policy
from dlux.updater.image_update import queue_image_update, trigger_path
from dlux.updater.runtime import RuntimeStore
from dlux.updater.service import UpdateService, get_ops_state, queue_ops_run, queue_run


def write_resident(root, value=None):
    status = {"composer_version": "1.11.0"}
    if value is not None:
        status["update_policy"] = value
    path = Path(root) / "state" / "agent" / "agent-status.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(status), encoding="utf-8")


def write_availability(root):
    store = RuntimeStore(root).ensure()
    (store.state_dir / "image-available.json").write_text(json.dumps({
        "available": True,
        "images": [{
            "image": "example/app:latest",
            "local_digest": "sha256:old",
            "remote_digest": "sha256:new",
            "update_available": True,
            "version": "9.1.0",
        }],
    }), encoding="utf-8")
    return store


class PolicyValueTests(SimpleTestCase):
    def test_empty_means_all_and_unknown_means_none(self):
        self.assertEqual(policy.normalize(""), (policy.ALL, True))
        self.assertEqual(policy.normalize(None), (policy.ALL, True))
        self.assertEqual(policy.normalize(" Inline "), (policy.INLINE, True))
        self.assertEqual(policy.normalize("off"), (policy.NONE, False))

    def test_dlux_settings_reads_the_environment(self):
        from dlux.utils.settings import dlux_settings

        scope = {"BASE_DIR": "/tmp", "INSTALLED_APPS": [], "MIDDLEWARE": [], "TEMPLATES": []}
        with mock.patch.dict(os.environ, {"DLUX_UPDATE_POLICY": " INLINE "}):
            self.assertEqual(dlux_settings(scope)["DLUX_UPDATE_POLICY"], "inline")
        scope = {"BASE_DIR": "/tmp", "INSTALLED_APPS": [], "MIDDLEWARE": [], "TEMPLATES": []}
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DLUX_UPDATE_POLICY", None)
            self.assertEqual(dlux_settings(scope)["DLUX_UPDATE_POLICY"], "all")

    def test_the_stricter_of_web_and_the_resident_pair_applies(self):
        with tempfile.TemporaryDirectory() as root, override_settings(
            DLUX_UPDATE_RUNTIME_ROOT=root, DLUX_UPDATE_POLICY="all",
        ):
            self.assertEqual(policy.effective_policy(), policy.ALL)
            write_resident(root, "none")
            self.assertEqual(policy.effective_policy(), policy.NONE)
            status = policy.status()
            self.assertTrue(status["mismatch"])
            self.assertFalse(status["allows_inline"])
            with override_settings(DLUX_UPDATE_POLICY="none"):
                write_resident(root, "all")
                self.assertEqual(policy.effective_policy(), policy.NONE)

    def test_a_resident_that_does_not_report_leaves_web_alone(self):
        with tempfile.TemporaryDirectory() as root, override_settings(
            DLUX_UPDATE_RUNTIME_ROOT=root, DLUX_UPDATE_POLICY="inline",
        ):
            write_resident(root)
            status = policy.status()
            self.assertEqual(status["policy"], policy.INLINE)
            self.assertFalse(status["mismatch"])
            self.assertTrue(status["resident_unenforced"])


@override_settings(DLUX_INLINE_UPDATES_ENABLED=True)
class QueueRefusalTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        self.store = write_availability(self.root)
        state = DluxUpdateState.load()
        state.worker_seen_at = timezone.now()
        state.latest_version = "1.17.1"
        state.latest_compatible = True
        state.previous_version = "1.16.6"
        state.save()

    def settings(self, value):
        return override_settings(DLUX_UPDATE_RUNTIME_ROOT=self.root, DLUX_UPDATE_POLICY=value)

    def test_image_updates_are_refused_under_inline(self):
        with self.settings("inline"), self.assertRaisesRegex(UpdaterError, "update policy"):
            queue_image_update("root")
        self.assertFalse(DluxImageUpdate.objects.exists())

    def test_image_updates_queue_under_all(self):
        with self.settings("all"):
            self.assertIsNotNone(queue_image_update("root"))

    def test_a_stricter_resident_refuses_the_image_update(self):
        write_resident(self.root, "inline")
        with self.settings("all"), self.assertRaisesRegex(UpdaterError, "update policy"):
            queue_image_update("root")

    def test_inline_updates_queue_under_inline(self):
        with self.settings("inline"):
            run = queue_run(DluxUpdateRun.ACTION_APPLY, "root")
        self.assertEqual(run.target_version, "1.17.1")

    def test_none_refuses_the_inline_update_but_not_check_or_rollback(self):
        with self.settings("none"):
            with self.assertRaisesRegex(UpdaterError, "update policy"):
                queue_run(DluxUpdateRun.ACTION_APPLY, "root")
            check = queue_run(DluxUpdateRun.ACTION_CHECK, "root")
            check.is_active = False
            check.save()
            state = DluxUpdateState.load()
            state.active_run_token = ""
            state.save()
            rollback = queue_run(DluxUpdateRun.ACTION_ROLLBACK, "root")
        self.assertEqual(rollback.target_version, "1.16.6")

    def test_composer_updates_are_refused_and_checks_are_not(self):
        with self.settings("inline"):
            with self.assertRaisesRegex(UpdaterError, "update policy"):
                queue_ops_run("agent-update", username="root")
            self.assertEqual(queue_ops_run("agent-check", username="root").operation, "agent-check")
        self.assertFalse(DluxOpsRun.objects.filter(operation="agent-update").exists())

    def test_the_card_marks_the_composer_update_unavailable(self):
        with self.settings("inline"):
            operations = {item["name"]: item for item in get_ops_state()["operations"]}
        self.assertFalse(operations["agent-update"]["available"])
        self.assertIn("update policy", operations["agent-update"]["unavailable_reason"])
        self.assertTrue(operations["agent-check"]["available"])


@override_settings(DLUX_INLINE_UPDATES_ENABLED=True)
class WorkerRefusalTests(TestCase):
    """A request queued before the policy changed is refused before any hand-off."""

    def test_a_queued_image_update_never_reaches_composer(self):
        with tempfile.TemporaryDirectory() as root:
            store = RuntimeStore(root).ensure()
            row = DluxImageUpdate.objects.create(requested_by_username="root")
            service = UpdateService(store=store)
            with override_settings(DLUX_UPDATE_RUNTIME_ROOT=root, DLUX_UPDATE_POLICY="inline"), \
                    mock.patch.object(service, "_create_backup") as backup:
                service.tick_image_update()
            row.refresh_from_db()
            self.assertEqual(row.status, row.STATUS_FAILED)
            self.assertIn("update policy", row.error)
            backup.assert_not_called()
            self.assertFalse(trigger_path(store).exists())
            self.assertFalse(store.maintenance_file.exists())

    def test_a_queued_inline_update_is_not_handed_off(self):
        with tempfile.TemporaryDirectory() as root:
            store = RuntimeStore(root).ensure()
            run = DluxUpdateRun.objects.create(action=DluxUpdateRun.ACTION_APPLY, target_version="1.17.1")
            service = UpdateService(store=store)
            with override_settings(DLUX_UPDATE_RUNTIME_ROOT=root, DLUX_UPDATE_POLICY="none"), \
                    mock.patch.object(service, "_handoff_to_composer") as handoff:
                with self.assertRaisesRegex(UpdaterError, "update policy"):
                    service._process_apply(run)
            handoff.assert_not_called()


@override_settings(DLUX_INLINE_UPDATES_ENABLED=True)
class ViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.password = "pw-root-1234"
        self.user = User.objects.create_superuser(username="root", email="r@example.com", password=self.password)
        settings_row = SystemSettings.load()
        settings_row.is_configured = True
        settings_row.save()
        state = DluxUpdateState.load()
        state.worker_seen_at = timezone.now()
        state.save()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        write_availability(self._tmp.name)
        self.client = Client()
        self.client.force_login(self.user)

    def test_the_image_view_refuses_with_the_reason(self):
        with override_settings(DLUX_UPDATE_RUNTIME_ROOT=self._tmp.name, DLUX_UPDATE_POLICY="inline"):
            response = self.client.post(reverse("dlux_update_image"), {"current_password": self.password})
        self.assertEqual(response.status_code, 409)
        self.assertIn("update policy", response.json()["error"])

    def test_the_card_state_carries_the_policy_and_keeps_the_versions(self):
        with override_settings(DLUX_UPDATE_RUNTIME_ROOT=self._tmp.name, DLUX_UPDATE_POLICY="inline"):
            state = self.client.get(reverse("dlux_update_state")).json()["state"]
        self.assertEqual(state["update_policy"]["policy"], "inline")
        self.assertFalse(state["update_policy"]["allows_image"])
        self.assertTrue(state["image_update_available"])
        self.assertTrue(state["image_update_target"])


class DoctorTests(SimpleTestCase):
    def finding(self, value, resident=None):
        with tempfile.TemporaryDirectory() as root, override_settings(
            DLUX_UPDATE_RUNTIME_ROOT=root, DLUX_UPDATE_POLICY=value,
        ):
            if resident is not False:
                write_resident(root, resident)
            return doctor._check_update_policy(None)

    def test_a_matching_policy_is_ok(self):
        finding = self.finding("inline", "inline")
        self.assertEqual(finding.status, doctor.OK)
        self.assertIn("Policy inline", finding.detail)

    def test_a_mismatch_warns_with_both_values(self):
        finding = self.finding("all", "none")
        self.assertEqual(finding.status, doctor.WARNING)
        self.assertIn("reads all", finding.detail)
        self.assertIn("enforces none", finding.detail)
        self.assertIn("./start.sh", finding.remedy)
        self.assertNotIn("docker compose", finding.remedy)

    def test_an_unenforced_restriction_warns(self):
        self.assertEqual(self.finding("none", None).status, doctor.WARNING)

    def test_the_default_needs_no_resident_report(self):
        self.assertEqual(self.finding("all", False).status, doctor.OK)

    def test_an_unknown_value_warns(self):
        finding = self.finding("sometimes", "none")
        self.assertEqual(finding.status, doctor.WARNING)
        self.assertIn("unknown value", finding.detail)


class ScaffoldTests(SimpleTestCase):
    def test_web_worker_and_the_resident_pair_read_the_policy(self):
        template = (
            Path(__file__).resolve().parent.parent
            / "scaffold" / "templates" / "project" / "compose.yml.tmpl"
        ).read_text(encoding="utf-8")
        line = 'DLUX_UPDATE_POLICY: "${DLUX_UPDATE_POLICY:-all}"'
        head, _, services = template.partition("\nservices:\n")
        self.assertIn(f"  {line}\n", head)
        for service in ("composer-executor", "composer-agent"):
            body = services.split(f"\n  {service}:\n", 1)[1].split("\n  composer-", 1)[0]
            self.assertIn(f"      {line}\n", body, service)
