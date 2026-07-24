import json
import os
import stat
import tempfile

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from dlux.models import DluxControlLinkRequest, SystemSettings
from dlux.updater import control_link
from dlux.updater.runtime import RuntimeStore
from dlux.updater.service import UpdateService

User = get_user_model()


class ControlLinkTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", "admin@example.com", "pw12345!x")
        self.user = User.objects.create_user("bob", "bob@example.com", "pw12345!x")
        self.client = Client()
        settings = SystemSettings.load()
        settings.is_configured = True
        settings.save()

    def test_non_superuser_is_forbidden(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("control_panel")).status_code, 403)

    def test_pairing_is_queued_by_web_then_published_by_the_worker(self):
        self.client.force_login(self.admin)
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(
            DLUX_UPDATE_RUNTIME_ROOT=temp_dir
        ):
            store = RuntimeStore(temp_dir).ensure()

            self.assertEqual(self.client.get(reverse("control_panel")).status_code, 200)

            resp = self.client.post(reverse("control_panel_connect"), {
                "control_url": "https://panel.example.org",
                "pairing_token": "abcd.longsecret",
            })
            self.assertEqual(resp.status_code, 302)

            # The web tier only records intent; the bridge is still untouched.
            self.assertIsNone(control_link.read_enroll_request(store))
            row = DluxControlLinkRequest.objects.get()
            self.assertEqual(row.action, DluxControlLinkRequest.ACTION_ENROLL)
            self.assertEqual(row.control_url, "https://panel.example.org")

            # The tile reports pending immediately, before the worker runs.
            status = self.client.get(reverse("control_panel_status")).json()["link"]
            self.assertTrue(status["pending"])
            self.assertEqual(status["pending_operation_id"], str(row.operation_id))

            # The worker publishes it and consumes the row.
            self.assertEqual(UpdateService(store=store).tick_control_link(), 1)
            request = control_link.read_enroll_request(store)
            self.assertEqual(request["control_url"], "https://panel.example.org")
            self.assertEqual(request["pairing_code"], "abcd.longsecret")
            self.assertEqual(request["operation_id"], str(row.operation_id))
            self.assertFalse(DluxControlLinkRequest.objects.exists())

            # Agent enrolls and confirms that operation.
            (store.state_dir / "agent").mkdir(parents=True, exist_ok=True)
            (store.state_dir / "agent" / "agent-status.json").write_text(json.dumps({
                "schema_version": 1, "enrolled": True, "control_url": "https://panel.example.org",
                "agent_id": "agent-1", "last_enroll": {"operation_id": request["operation_id"], "state": "ok"},
            }))

            status = self.client.get(reverse("control_panel_status")).json()["link"]
            self.assertTrue(status["enrolled"])
            self.assertFalse(status["pending"])

            # Cleanup of the confirmed request belongs to the worker, not the
            # read-only web tier.
            self.assertIsNotNone(control_link.read_enroll_request(store))
            UpdateService(store=store).tick_control_link()
            self.assertIsNone(control_link.read_enroll_request(store))

    def test_pairing_survives_a_read_only_runtime_mount(self):
        """The web tier mounts the runtime volume read-only, so the connect view
        must never write it. Regression: it used to write the bridge inline and
        raised PermissionError/OSError on every real deployment."""
        self.client.force_login(self.admin)
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(
            DLUX_UPDATE_RUNTIME_ROOT=temp_dir
        ):
            store = RuntimeStore(temp_dir).ensure()
            read_only = stat.S_IRUSR | stat.S_IXUSR
            os.chmod(store.state_dir, read_only)
            os.chmod(store.root, read_only)
            try:
                resp = self.client.post(reverse("control_panel_connect"), {
                    "control_url": "https://panel.example.org",
                    "pairing_token": "abcd.longsecret",
                })
            finally:
                os.chmod(store.root, 0o755)
                os.chmod(store.state_dir, 0o755)

            self.assertEqual(resp.status_code, 302)
            self.assertEqual(DluxControlLinkRequest.objects.count(), 1)

    def test_worker_records_a_bridge_failure_and_drops_the_token(self):
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(
            DLUX_UPDATE_RUNTIME_ROOT=temp_dir
        ):
            store = RuntimeStore(temp_dir).ensure()
            control_link.queue_enroll_request("https://panel.example.org", "abcd.longsecret")
            read_only = stat.S_IRUSR | stat.S_IXUSR
            os.chmod(store.state_dir, read_only)
            os.chmod(store.root, read_only)
            try:
                self.assertEqual(UpdateService(store=store).tick_control_link(), 0)
            finally:
                os.chmod(store.root, 0o755)
                os.chmod(store.state_dir, 0o755)

            row = DluxControlLinkRequest.objects.get()
            self.assertTrue(row.error)
            self.assertEqual(row.pairing_token, "")

    def test_invalid_url_is_rejected_without_queueing(self):
        self.client.force_login(self.admin)
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(
            DLUX_UPDATE_RUNTIME_ROOT=temp_dir
        ):
            store = RuntimeStore(temp_dir).ensure()
            self.client.post(reverse("control_panel_connect"), {
                "control_url": "ftp://nope",
                "pairing_token": "abcd.longsecret",
            })
            self.assertFalse(DluxControlLinkRequest.objects.exists())
            self.assertIsNone(control_link.read_enroll_request(store))

    def test_cancel_queues_removal_and_the_worker_clears_the_bridge(self):
        self.client.force_login(self.admin)
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(
            DLUX_UPDATE_RUNTIME_ROOT=temp_dir
        ):
            store = RuntimeStore(temp_dir).ensure()
            control_link.write_enroll_request(store, "https://panel.example.org", "abcd.longsecret")
            self.assertIsNotNone(control_link.read_enroll_request(store))

            self.client.post(reverse("control_panel_cancel"))
            self.assertEqual(
                DluxControlLinkRequest.objects.get().action,
                DluxControlLinkRequest.ACTION_CANCEL,
            )

            UpdateService(store=store).tick_control_link()
            self.assertIsNone(control_link.read_enroll_request(store))
            self.assertFalse(DluxControlLinkRequest.objects.exists())

    def test_newest_submission_replaces_an_unapplied_one(self):
        self.client.force_login(self.admin)
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(
            DLUX_UPDATE_RUNTIME_ROOT=temp_dir
        ):
            for token in ("first.secret", "second.secret"):
                self.client.post(reverse("control_panel_connect"), {
                    "control_url": "https://panel.example.org",
                    "pairing_token": token,
                })
            row = DluxControlLinkRequest.objects.get()
            self.assertEqual(row.pairing_token, "second.secret")
