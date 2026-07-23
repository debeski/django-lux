import json
import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.test import TestCase, override_settings
from django.utils import timezone

from dlux.models import DluxImageUpdate, DluxUpdateState
from dlux.updater.agent_bridge import (
    build_agent_snapshot,
    consume_agent_requests,
    processed_dir,
    publish_agent_results,
    publish_agent_snapshot,
    requests_dir,
    results_dir,
    snapshot_path,
)
from dlux.updater.image_update import trigger_path, write_composer_trigger
from dlux.updater.runtime import RuntimeStore


class AgentBridgeTests(TestCase):
    def test_shared_protocol_command_fixture_is_consumed(self):
        fixture = (
            Path(__file__).parent
            / "fixtures"
            / "agent-protocol-v1"
            / "command.image_update.json"
        )
        request = json.loads(fixture.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(
            DLUX_UPDATE_RUNTIME_ROOT=temp_dir,
            DLUX_INLINE_UPDATES_ENABLED=True,
        ):
            store = RuntimeStore(temp_dir).ensure()
            DluxUpdateState.load()
            self._availability(store)
            path = requests_dir(store) / f"{request['operation_id']}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(request), encoding="utf-8")
            consume_agent_requests(SimpleNamespace(store=store))
            row = DluxImageUpdate.objects.get(control_operation_id=request["operation_id"])
            self.assertEqual(row.backup_mode, "data")

    def _availability(self, store):
        (store.state_dir / "image-available.json").write_text(json.dumps({
            "available": True,
            "images": [{
                "image": "example/project:latest",
                "remote_digest": "sha256:new",
                "local_digest": "sha256:old",
                "update_available": True,
                "version": "9.1.0",
            }],
        }), encoding="utf-8")

    def _request(self, store, operation_id, *, action="dlux.image_update", backup_mode="full"):
        path = requests_dir(store) / f"{operation_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "schema_version": 1,
            "operation_id": operation_id,
            "action": action,
            "actor": {"id": "7", "display": "Fleet Admin"},
            "payload": {"backup_mode": backup_mode},
        }), encoding="utf-8")

    def test_central_request_uses_existing_image_queue_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(
            DLUX_UPDATE_RUNTIME_ROOT=temp_dir,
            DLUX_INLINE_UPDATES_ENABLED=True,
        ):
            store = RuntimeStore(temp_dir).ensure()
            DluxUpdateState.load()
            self._availability(store)
            operation_id = str(uuid.uuid4())
            self._request(store, operation_id)
            service = SimpleNamespace(store=store)

            consume_agent_requests(service)
            consume_agent_requests(service)

            self.assertEqual(DluxImageUpdate.objects.count(), 1)
            row = DluxImageUpdate.objects.get()
            self.assertEqual(str(row.control_operation_id), operation_id)
            self.assertEqual(row.request_source, "control")
            self.assertEqual(row.requested_by_username, "Fleet Admin")
            self.assertEqual(row.backup_mode, "full")
            result = json.loads(
                (results_dir(store) / f"{operation_id}.json").read_text(encoding="utf-8")
            )
            self.assertEqual(result["image_token"], row.token)

    def test_invalid_action_is_rejected_without_creating_an_update(self):
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(
            DLUX_UPDATE_RUNTIME_ROOT=temp_dir,
            DLUX_INLINE_UPDATES_ENABLED=True,
        ):
            store = RuntimeStore(temp_dir).ensure()
            operation_id = str(uuid.uuid4())
            self._request(store, operation_id, action="dlux.backup.restore")

            consume_agent_requests(SimpleNamespace(store=store))

            self.assertFalse(DluxImageUpdate.objects.exists())
            result = json.loads(
                (results_dir(store) / f"{operation_id}.json").read_text(encoding="utf-8")
            )
            self.assertEqual(result["status"], "rejected")

    def test_processed_requests_are_archived_so_later_requests_are_not_starved(self):
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(
            DLUX_UPDATE_RUNTIME_ROOT=temp_dir,
        ):
            store = RuntimeStore(temp_dir).ensure()
            operation_ids = [str(uuid.uuid4()) for _ in range(12)]
            for operation_id in operation_ids:
                self._request(store, operation_id, action="dlux.backup.restore")

            service = SimpleNamespace(store=store)
            self.assertEqual(consume_agent_requests(service), 10)
            self.assertEqual(len(list(requests_dir(store).glob("*.json"))), 2)
            self.assertEqual(consume_agent_requests(service), 2)

            self.assertFalse(list(requests_dir(store).glob("*.json")))
            self.assertEqual(len(list(processed_dir(store).glob("*.json"))), 12)
            self.assertEqual(len(list(results_dir(store).glob("*.json"))), 12)

    def test_central_backup_creation_is_idempotent_and_never_restores(self):
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(
            DLUX_UPDATE_RUNTIME_ROOT=temp_dir,
        ):
            store = RuntimeStore(temp_dir).ensure()
            operation_id = str(uuid.uuid4())
            self._request(
                store,
                operation_id,
                action="dlux.backup.create",
                backup_mode="data",
            )

            def complete(backup_pk):
                from dlux.models import SystemBackup

                backup = SystemBackup.objects.get(pk=backup_pk)
                backup.status = backup.STATUS_COMPLETED
                backup.completed_at = timezone.now()
                backup.save(update_fields=("status", "completed_at"))

            with mock.patch("dlux.backup.run_system_backup", side_effect=complete) as run:
                consume_agent_requests(SimpleNamespace(store=store))
                consume_agent_requests(SimpleNamespace(store=store))
            from dlux.models import SystemBackup

            backup = SystemBackup.objects.get(token=operation_id)
            self.assertFalse(backup.media_included)
            self.assertEqual(run.call_count, 1)
            result = json.loads(
                (results_dir(store) / f"{operation_id}.json").read_text(encoding="utf-8")
            )
            self.assertEqual(result["status"], "completed")

    def test_operation_id_flows_into_composer_trigger_and_terminal_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RuntimeStore(temp_dir).ensure()
            row = DluxImageUpdate.objects.create(
                control_operation_id=uuid.uuid4(),
                request_source="control",
                target_version="9.1.0",
            )
            write_composer_trigger(store, row)
            trigger = json.loads(trigger_path(store).read_text(encoding="utf-8"))
            self.assertEqual(trigger["operation_id"], str(row.control_operation_id))

            row.status = row.STATUS_COMPLETED
            row.is_active = False
            row.save(update_fields=["status", "is_active"])
            publish_agent_results(store)
            result = json.loads(
                (results_dir(store) / f"{row.control_operation_id}.json").read_text(encoding="utf-8")
            )
            self.assertEqual(result["status"], "completed")

    def test_snapshot_is_typed_and_contains_no_environment_values(self):
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(
            DLUX_UPDATE_RUNTIME_ROOT=temp_dir,
            BASE_DIR=Path(temp_dir) / "example-project",
        ):
            store = RuntimeStore(temp_dir).ensure()
            snapshot = build_agent_snapshot(store)
            encoded = json.dumps(snapshot)
            self.assertEqual(snapshot["schema_version"], 1)
            self.assertIn("versions", snapshot)
            self.assertIn("health", snapshot)
            self.assertNotIn("SECRET_KEY", encoded)
            self.assertNotIn("DATABASES", encoded)

            self.assertTrue(publish_agent_snapshot(store, force=True))
            persisted = json.loads(snapshot_path(store).read_text(encoding="utf-8"))
            self.assertEqual(persisted["project"]["environment"], "production")
