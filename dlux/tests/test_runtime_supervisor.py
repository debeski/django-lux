from dlux.tests.harness import setup_test_environment

setup_test_environment()

import io
import json
import os
import tempfile
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings

from dlux.updater import supervisor


class VersionOrderingTests(SimpleTestCase):
    def test_is_newer_orders_versions_numerically(self):
        self.assertTrue(supervisor._is_newer("1.5.11", "1.5.8"))
        self.assertFalse(supervisor._is_newer("1.5.8", "1.5.11"))
        self.assertFalse(supervisor._is_newer("1.6.0", "1.6.0"))
        self.assertTrue(supervisor._is_newer("1.6.0", ""))
        self.assertFalse(supervisor._is_newer("", "1.6.0"))


class ResolveReleaseTests(SimpleTestCase):
    def _volume(self, version):
        root = Path(tempfile.mkdtemp())
        (root / "releases" / version).mkdir(parents=True)
        (root / "state").mkdir(parents=True)
        (root / "state" / "active.json").write_text(
            json.dumps({"version": version, "source": "volume"}), encoding="utf-8"
        )
        return root

    def test_older_pinned_release_does_not_shadow_a_newer_baked_image(self):
        root = self._volume("1.5.8")
        # The exact production failure: image baked 1.5.11, volume pinned 1.5.8.
        self.assertIsNone(supervisor.resolve_release(root, baked="1.5.11"))

    def test_newer_pinned_release_still_shadows_an_older_baked_image(self):
        root = self._volume("1.6.0")
        resolved = supervisor.resolve_release(root, baked="1.5.11")
        self.assertEqual(resolved, (root / "releases" / "1.6.0").resolve())

    def test_equal_version_uses_the_baked_image(self):
        root = self._volume("1.5.11")
        self.assertIsNone(supervisor.resolve_release(root, baked="1.5.11"))

    def test_missing_state_falls_back_to_baked(self):
        root = Path(tempfile.mkdtemp())
        (root / "state").mkdir(parents=True)
        self.assertIsNone(supervisor.resolve_release(root, baked="1.5.11"))


class DluxReconcileCommandTests(SimpleTestCase):
    """The pre-migration, DB-free pointer reconcile that keeps a stale pinned
    release from wedging the boot chain behind a maintenance screen."""

    def _runtime(self, pinned):
        root = Path(tempfile.mkdtemp())
        (root / "releases" / pinned).mkdir(parents=True)
        (root / "state").mkdir(parents=True)
        (root / "state" / "active.json").write_text(
            json.dumps({"version": pinned, "source": "volume", "generation": 0}), encoding="utf-8"
        )
        (root / "state" / "generation").write_text("0\n", encoding="utf-8")
        return root

    def _reconcile(self, root, baked):
        with override_settings(DLUX_UPDATE_RUNTIME_ROOT=str(root)), \
                mock.patch.dict(os.environ, {"DLUX_BAKED_VERSION": baked}):
            call_command("dlux_reconcile", stdout=io.StringIO(), stderr=io.StringIO())
        return json.loads((root / "state" / "active.json").read_text(encoding="utf-8"))

    def test_stale_pinned_release_is_reset_to_baked(self):
        active = self._reconcile(self._runtime("1.5.8"), baked="1.5.11")
        self.assertEqual(active["version"], "1.5.11")
        self.assertEqual(active["source"], "image")

    def test_newer_pinned_release_is_preserved(self):
        active = self._reconcile(self._runtime("1.6.0"), baked="1.5.11")
        self.assertEqual(active["version"], "1.6.0")
        self.assertEqual(active["source"], "volume")

    def test_missing_pointer_is_a_noop(self):
        root = Path(tempfile.mkdtemp())
        (root / "state").mkdir(parents=True)
        with override_settings(DLUX_UPDATE_RUNTIME_ROOT=str(root)), \
                mock.patch.dict(os.environ, {"DLUX_BAKED_VERSION": "1.5.11"}):
            call_command("dlux_reconcile", stdout=io.StringIO(), stderr=io.StringIO())
        self.assertFalse((root / "state" / "active.json").exists())
