"""The runtime-volume contract must describe the code, not an aspiration.

`runtime_contract.json` is a cross-repo interface: Composer writes the volume
this file describes, and the supervisor reads it. A contract that drifts from
`RuntimeStore` is worse than none, because both sides would trust it.

These tests assert the document against DjangoLux's own implementation. The
matching assertion on Composer's side lives in its `test_dlux_runtime.py`.
"""
from dlux.tests.harness import setup_test_environment

setup_test_environment()

import importlib
import json
from pathlib import Path

from django.core.management import call_command
from django.test import SimpleTestCase
from io import StringIO

from dlux import __version__
from dlux.contracts import runtime as runtime_contract
from dlux.updater.runtime import RuntimeStore


class ContractShapeTests(SimpleTestCase):
    def setUp(self):
        self.contract = runtime_contract.load_contract()

    def test_the_contract_is_stamped_with_the_running_version(self):
        """Never stored in the file — a consumer must see the release it asked."""
        raw = json.loads(runtime_contract.CONTRACT_PATH.read_text(encoding="utf-8"))

        self.assertNotIn("dlux_version", raw)
        self.assertEqual(self.contract["dlux_version"], __version__)

    # The contract names directories as they appear on disk; RuntimeStore exposes
    # one of them under a python-friendlier attribute.
    ATTRIBUTE_FOR = {"state": "state_dir"}

    def test_every_directory_it_names_exists_on_runtimestore(self):
        store = RuntimeStore("/tmp/dlux-runtime-contract-check")

        for name in self.contract["directories"]:
            with self.subTest(directory=name):
                attribute = self.ATTRIBUTE_FOR.get(name, name)
                self.assertTrue(
                    hasattr(store, attribute),
                    f"contract names directory '{name}' that RuntimeStore does not have",
                )
                self.assertEqual(
                    getattr(store, attribute).name, name,
                    f"RuntimeStore.{attribute} is not the on-disk directory '{name}'",
                )

    def test_runtimestore_has_no_directory_the_contract_omits(self):
        """Drift in the other direction: a new directory must be documented."""
        documented = set(self.contract["directories"])
        on_disk = {"releases", "staging", "downloads", "failed", "state"}

        self.assertEqual(
            on_disk - documented, set(),
            "RuntimeStore creates a directory the contract does not describe",
        )

    def test_active_json_keys_match_what_runtimestore_writes(self):
        expected = set(self.contract["active_json"]["required_keys"])

        # write_active() builds exactly this payload.
        self.assertEqual(expected, {"version", "source", "path", "generation"})

    def test_source_values_match_the_implementation(self):
        self.assertEqual(
            set(self.contract["active_json"]["source_values"]), {"image", "volume"}
        )

    def test_the_state_file_table_names_a_writer_for_every_file(self):
        for filename, spec in self.contract["state_files"].items():
            with self.subTest(filename=filename):
                self.assertIn(spec.get("writer"), {"dlux", "composer", "both"})

    def test_intent_files_are_written_by_dlux_and_acked_by_composer(self):
        """The direction of the protocol, pinned so a refactor cannot invert it."""
        self.assertEqual(runtime_contract.writer_of(self.contract,
                                                    "image-update-request.json"), "dlux")
        self.assertEqual(runtime_contract.writer_of(self.contract,
                                                    "package-update-request.json"), "dlux")
        self.assertEqual(runtime_contract.writer_of(self.contract,
                                                    "package-update-request.json.ack"), "composer")
        self.assertEqual(runtime_contract.writer_of(self.contract, "active.json"), "composer")

    def test_the_protocol_filenames_match_the_code(self):
        from dlux.updater import image_update

        files = set(self.contract["state_files"])
        self.assertIn(image_update.TRIGGER_FILENAME, files)
        self.assertIn(image_update.ACK_FILENAME, files)
        self.assertIn(image_update.STATUS_FILENAME, files)
        self.assertIn(image_update.AVAILABILITY_FILENAME, files)


class ContractLocationTests(SimpleTestCase):
    """Where the contracts live, and that publishing them still works.

    There is no alias at the old `dlux.stack_contract` / `dlux.runtime_contract`
    paths: nothing imported them — not Composer, not any project — so a second
    canonical path was never earned.
    """

    def test_the_old_module_paths_are_gone(self):
        for name in ('dlux.stack_contract', 'dlux.runtime_contract'):
            with self.subTest(module=name):
                with self.assertRaises(ImportError):
                    importlib.import_module(name)

    def test_each_contract_json_sits_beside_its_module(self):
        from dlux.contracts import runtime, stack

        for module, name in ((runtime, 'runtime.json'), (stack, 'stack.json')):
            with self.subTest(contract=name):
                self.assertTrue(module.CONTRACT_PATH.is_file())
                self.assertEqual(module.CONTRACT_PATH.name, name)
                self.assertEqual(module.CONTRACT_PATH.parent.name, 'contracts')

    def test_the_management_commands_still_publish_them(self):
        """The cross-repo interface — Composer execs these, not the module."""
        for command, key in (('dlux_runtime_contract', 'directories'),
                             ('dlux_stack_contract', 'services')):
            with self.subTest(command=command):
                out = StringIO()
                call_command(command, stdout=out)
                self.assertIn(key, json.loads(out.getvalue()))


class DiffTests(SimpleTestCase):
    def setUp(self):
        self.contract = runtime_contract.load_contract()

    def test_a_complete_layout_reports_no_drift(self):
        self.assertEqual(
            runtime_contract.diff_layout(
                self.contract, ["releases", "staging", "downloads", "failed", "state"]
            ),
            [],
        )

    def test_a_missing_required_directory_is_drift(self):
        drift = runtime_contract.diff_layout(self.contract, ["staging", "state"])

        self.assertEqual(len(drift), 1)
        self.assertIn("releases", drift[0])

    def test_extra_directories_are_not_drift(self):
        self.assertEqual(
            runtime_contract.diff_layout(self.contract, ["releases", "state", "project-extra"]), []
        )

    def test_an_absent_pointer_is_valid(self):
        """No active.json means the image release is in force."""
        self.assertEqual(runtime_contract.diff_active(self.contract, {}), [])

    def test_a_valid_volume_pointer_reports_no_drift(self):
        active = {"version": "1.8.0", "source": "volume",
                  "path": "/opt/dlux-runtime/releases/1.8.0", "generation": 3}
        self.assertEqual(runtime_contract.diff_active(self.contract, active), [])

    def test_an_invalid_pointer_is_reported_per_rule(self):
        cases = {
            "unknown source": {"version": "1.8.0", "source": "nfs", "path": "", "generation": 1},
            "volume without a path": {"version": "1.8.0", "source": "volume",
                                      "path": "", "generation": 1},
            "image with a path": {"version": "1.8.0", "source": "image",
                                  "path": "/opt/x", "generation": 1},
            "negative generation": {"version": "1.8.0", "source": "image",
                                    "path": "", "generation": -1},
            "missing key": {"source": "image", "path": "", "generation": 1},
        }
        for label, active in cases.items():
            with self.subTest(case=label):
                self.assertTrue(runtime_contract.diff_active(self.contract, active))


class ManagementCommandTests(SimpleTestCase):
    def test_the_command_prints_the_stamped_contract(self):
        """Composer execs this to fetch the contract for the running release."""
        out = StringIO()
        call_command("dlux_runtime_contract", stdout=out)

        payload = json.loads(out.getvalue())
        self.assertEqual(payload["dlux_version"], __version__)
        self.assertEqual(payload["schema_version"], 1)
        self.assertIn("releases", payload["directories"])
