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

    def test_page_renders_native_layout_fields_and_polling_contract(self):
        self.client.force_login(self.admin)
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(
            DLUX_UPDATE_RUNTIME_ROOT=temp_dir
        ):
            RuntimeStore(temp_dir).ensure()
            response = self.client.get(reverse("control_panel"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "dlux/panel/css/main.css")
        self.assertContains(response, 'class="dlux-form dlux-control-form"')
        self.assertContains(response, "data-control-link")
        self.assertContains(response, "data-control-link-badge")
        self.assertContains(response, "dlux-control-card--status")
        self.assertContains(response, "HTTPS required")

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
            self.assertContains(
                self.client.get(reverse("control_panel")),
                "data-control-link-pending",
            )

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
            response = self.client.post(reverse("control_panel_connect"), {
                "control_url": "http://panel.example.org",
                "pairing_token": "abcd.longsecret",
            }, follow=True)
            self.assertFalse(DluxControlLinkRequest.objects.exists())
            self.assertIsNone(control_link.read_enroll_request(store))
            self.assertContains(response, "Enter a valid https:// control panel URL.")
            self.assertEqual(
                response.context["dlux_flash_notifications"][0]["level"],
                "error",
            )

    def test_accepted_pairing_uses_native_flash_when_legacy_bridge_is_disabled(self):
        self.client.force_login(self.admin)
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(
            DLUX_UPDATE_RUNTIME_ROOT=temp_dir
        ):
            RuntimeStore(temp_dir).ensure()
            response = self.client.post(reverse("control_panel_connect"), {
                "control_url": "https://panel.example.org",
                "pairing_token": "abcd.longsecret",
            }, follow=True)

            self.assertContains(response, "Pairing requested. The agent will connect shortly.")
            self.assertEqual(
                response.context["dlux_flash_notifications"][0]["level"],
                "success",
            )
            self.assertTrue(DluxControlLinkRequest.objects.exists())

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


class AgentComposerVersionTests(TestCase):
    """The resident composer-agent reports its own version. DLUX prefers the new
    `composer_version` field, falling back to legacy `agent_version` for agents
    that predate the split (composer < 1.2.5)."""

    def _state_for(self, temp_dir, status):
        store = RuntimeStore(temp_dir).ensure()
        agent_dir = store.state_dir / "agent"
        agent_dir.mkdir(parents=True, exist_ok=True)
        (agent_dir / "agent-status.json").write_text(json.dumps(status), encoding="utf-8")
        return control_link.control_link_state(store)

    def test_prefers_composer_version_field(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state = self._state_for(temp_dir, {
                "schema_version": 1, "enrolled": True,
                "agent_version": "0.9.0", "composer_version": "1.2.5",
            })
            self.assertEqual(state["composer_version"], "1.2.5")
            self.assertEqual(state["agent_version"], "0.9.0")

    def test_falls_back_to_agent_version_for_older_agents(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state = self._state_for(temp_dir, {
                "schema_version": 1, "enrolled": True, "agent_version": "1.2.4",
            })
            self.assertEqual(state["composer_version"], "1.2.4")

    def test_empty_when_neither_is_reported(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state = self._state_for(temp_dir, {"schema_version": 1, "enrolled": True})
            self.assertEqual(state["composer_version"], "")

    def test_diagnostics_card_shows_both_deployer_and_agent_versions(self):
        from unittest import mock

        admin = User.objects.create_superuser("v-admin", "v@example.com", "pw12345!x")
        settings = SystemSettings.load()
        settings.is_configured = True
        settings.save()
        client = Client()
        client.force_login(admin)
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(
            DLUX_UPDATE_RUNTIME_ROOT=temp_dir
        ), mock.patch.dict(os.environ, {"COMPOSER_VERSION": "1.2.5-deployer"}):
            store = RuntimeStore(temp_dir).ensure()
            agent_dir = store.state_dir / "agent"
            agent_dir.mkdir(parents=True, exist_ok=True)
            (agent_dir / "agent-status.json").write_text(
                json.dumps({"schema_version": 1, "enrolled": True, "composer_version": "1.2.5-agent"}),
                encoding="utf-8",
            )
            response = client.get(reverse("options_view"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Composer (deployer)")
        self.assertContains(response, "1.2.5-deployer")
        self.assertContains(response, "Composer (agent)")
        self.assertContains(response, "1.2.5-agent")


class ControlLinkDisconnectTests(TestCase):
    """A previously-connected panel that drops must be distinguishable from a
    never-configured one, and must alert superadmins once."""

    def _write_status(self, store, **fields):
        agent = store.state_dir / "agent"
        agent.mkdir(parents=True, exist_ok=True)
        (agent / "agent-status.json").write_text(
            json.dumps({"schema_version": 1, **fields}), encoding="utf-8"
        )

    def test_connection_status_distinguishes_the_four_states(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = RuntimeStore(tmp).ensure()
            self.assertEqual(control_link.control_link_state(store)["connection_status"], "unconfigured")

            self._write_status(store, enrolled=True, control_url="https://panel.example")
            self.assertEqual(control_link.control_link_state(store)["connection_status"], "connected")

            self._write_status(store, enrolled=True, revoked=True, control_url="https://panel.example")
            state = control_link.control_link_state(store)
            self.assertEqual(state["connection_status"], "disconnected")
            self.assertTrue(state["revoked"])
            self.assertEqual(state["control_url"], "https://panel.example")

            self._write_status(store, enrolled=False, control_url="https://panel.example")
            self.assertEqual(control_link.control_link_state(store)["connection_status"], "disconnected")

    def test_worker_alerts_once_per_disconnect_and_rearms_on_reconnect(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = RuntimeStore(tmp).ensure()
            service = UpdateService(store=store)
            calls = []
            service._notify_admins_control_link_disconnected = lambda url, revoked: calls.append((url, revoked))

            service._detect_control_link_disconnect({"enrolled": True, "control_url": "https://panel.example"})
            self.assertEqual(calls, [])  # connected — arms, no alert

            service._detect_control_link_disconnect(
                {"enrolled": True, "revoked": True, "control_url": "https://panel.example"}
            )
            self.assertEqual(calls, [("https://panel.example", True)])  # revoked — one alert

            service._detect_control_link_disconnect({"enrolled": False, "control_url": "https://panel.example"})
            self.assertEqual(len(calls), 1)  # still down — no repeat

            service._detect_control_link_disconnect({"enrolled": True, "control_url": "https://panel.example"})
            service._detect_control_link_disconnect({"enrolled": False, "control_url": "https://panel.example"})
            self.assertEqual(len(calls), 2)  # reconnect then drop — alerts again

    def test_no_alert_when_already_disconnected_on_first_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = RuntimeStore(tmp).ensure()
            service = UpdateService(store=store)
            calls = []
            service._notify_admins_control_link_disconnected = lambda url, revoked: calls.append(1)
            # Worker's first-ever tick already finds it revoked — no witnessed transition.
            service._detect_control_link_disconnect(
                {"enrolled": False, "revoked": True, "control_url": "https://panel.example"}
            )
            self.assertEqual(calls, [])

    def test_disconnect_notification_reaches_superadmins(self):
        from dlux.models import DluxNotification

        User.objects.create_superuser("cl-admin", "cl@example.com", "pw12345!x")
        with tempfile.TemporaryDirectory() as tmp:
            store = RuntimeStore(tmp).ensure()
            UpdateService(store=store)._notify_admins_control_link_disconnected("https://panel.example", True)
            note = DluxNotification.objects.filter(action="control_link_disconnected").first()
            self.assertIsNotNone(note)
            self.assertIn("panel.example", note.message)
