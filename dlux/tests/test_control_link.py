import json
import tempfile

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from dlux.models import SystemSettings
from dlux.updater import control_link
from dlux.updater.runtime import RuntimeStore

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

    def test_pairing_writes_bridge_request_and_status_reports_connected(self):
        self.client.force_login(self.admin)
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(
            DLUX_UPDATE_RUNTIME_ROOT=temp_dir
        ):
            store = RuntimeStore(temp_dir).ensure()

            # Page renders when unpaired.
            self.assertEqual(self.client.get(reverse("control_panel")).status_code, 200)

            # Connect: writes an enroll request onto the bridge.
            resp = self.client.post(reverse("control_panel_connect"), {
                "control_url": "https://panel.example.org",
                "pairing_token": "abcd.longsecret",
            })
            self.assertEqual(resp.status_code, 302)
            request = control_link.read_enroll_request(store)
            self.assertEqual(request["control_url"], "https://panel.example.org")
            self.assertEqual(request["pairing_code"], "abcd.longsecret")

            # Simulate the agent enrolling and reporting success for that operation.
            (store.state_dir / "agent").mkdir(parents=True, exist_ok=True)
            (store.state_dir / "agent" / "agent-status.json").write_text(json.dumps({
                "schema_version": 1, "enrolled": True, "control_url": "https://panel.example.org",
                "agent_id": "agent-1", "last_enroll": {"operation_id": request["operation_id"], "state": "ok"},
            }))

            status = self.client.get(reverse("control_panel_status")).json()["link"]
            self.assertTrue(status["enrolled"])
            self.assertFalse(status["pending"])
            # The successful request was auto-cleared.
            self.assertIsNone(control_link.read_enroll_request(store))

    def test_invalid_url_is_rejected_without_writing_a_request(self):
        self.client.force_login(self.admin)
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(
            DLUX_UPDATE_RUNTIME_ROOT=temp_dir
        ):
            store = RuntimeStore(temp_dir).ensure()
            self.client.post(reverse("control_panel_connect"), {
                "control_url": "ftp://nope",
                "pairing_token": "abcd.longsecret",
            })
            self.assertIsNone(control_link.read_enroll_request(store))

    def test_cancel_clears_pending_request(self):
        self.client.force_login(self.admin)
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(
            DLUX_UPDATE_RUNTIME_ROOT=temp_dir
        ):
            store = RuntimeStore(temp_dir).ensure()
            control_link.write_enroll_request(store, "https://panel.example.org", "abcd.longsecret")
            self.assertIsNotNone(control_link.read_enroll_request(store))
            self.client.post(reverse("control_panel_cancel"))
            self.assertIsNone(control_link.read_enroll_request(store))
