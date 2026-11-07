from dlux.tests.harness import setup_test_environment

setup_test_environment()

import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings

from dlux.updater import supervisor


# A stand-in for a gunicorn master: records "start", and on SIGTERM either
# ignores it or needs SHUTDOWN seconds before it records "stop" and exits.
SERVER = """\
import os, signal, sys, time
events, shutdown = sys.argv[1], sys.argv[2]

def note(event):
    with open(events, "a", encoding="utf-8") as handle:
        handle.write(event + "\\n")

def stop(*_):
    time.sleep(float(shutdown))
    note("stop")
    sys.exit(0)

signal.signal(signal.SIGTERM, signal.SIG_IGN if shutdown == "ignore" else stop)
note("start")
time.sleep(120)
"""

# The generated web command's shape: a compound bash -c, so bash forks the
# server instead of exec'ing it and dies on SIGTERM before the server does.
WRAPPER = 'if true; then echo starting; "$0" "$@"; fi'


def _wait_for(predicate, timeout=15.0):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("timed out waiting for the server")
        time.sleep(0.05)


def _group_exists(pgid):
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    return True


class _ServerTestCase(SimpleTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.server = self.dir / "server.py"
        self.server.write_text(SERVER, encoding="utf-8")
        self.events_file = self.dir / "events"

    def events(self):
        try:
            return self.events_file.read_text(encoding="utf-8").split()
        except FileNotFoundError:
            return []

    def wrapped_server_command(self, shutdown):
        return ["bash", "-c", WRAPPER, sys.executable, str(self.server), str(self.events_file), str(shutdown)]

    def _kill_leftovers(self, pgid):
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass


class StopChildTests(_ServerTestCase):
    def start_wrapped(self, shutdown):
        child = subprocess.Popen(
            self.wrapped_server_command(shutdown), start_new_session=True, stdout=subprocess.DEVNULL
        )
        self.addCleanup(self._kill_leftovers, child.pid)
        _wait_for(lambda: self.events() == ["start"])
        return child

    def test_returns_only_after_a_bash_wrapped_server_exits(self):
        child = self.start_wrapped(shutdown=2)
        began = time.monotonic()
        supervisor.stop_child(child, grace_seconds=30)
        self.assertGreaterEqual(time.monotonic() - began, 1.5)
        self.assertEqual(self.events(), ["start", "stop"])
        self.assertFalse(_group_exists(child.pid))
        self.assertIsNotNone(child.returncode)

    def test_kills_the_group_after_the_grace_period(self):
        child = self.start_wrapped(shutdown="ignore")
        began = time.monotonic()
        supervisor.stop_child(child, grace_seconds=1)
        elapsed = time.monotonic() - began
        self.assertGreaterEqual(elapsed, 1.0)
        self.assertLess(elapsed, 1.0 + supervisor.KILL_WAIT_SECONDS)
        self.assertEqual(self.events(), ["start"])
        self.assertFalse(_group_exists(child.pid))
        self.assertIsNotNone(child.returncode)


class GenerationRestartTests(_ServerTestCase):
    """Drive the supervisor process itself through a generation restart."""

    def test_the_next_generation_starts_only_after_the_old_server_stopped(self):
        state = self.dir / "runtime" / "state"
        state.mkdir(parents=True)
        (state / "generation").write_text("0\n", encoding="utf-8")
        env = dict(os.environ, PYTHONPATH=str(Path(supervisor.__file__).resolve().parents[2]))
        process = subprocess.Popen(
            [
                sys.executable, "-m", "dlux.updater.supervisor",
                "--runtime-root", str(self.dir / "runtime"),
                "--poll-seconds", "0.1", "--grace-seconds", "30",
                "--", *self.wrapped_server_command(shutdown=1.5),
            ],
            env=env,
            stdout=subprocess.DEVNULL,
        )
        self.addCleanup(self._stop_supervisor, process)
        _wait_for(lambda: self.events() == ["start"])

        (state / "generation").write_text("1\n", encoding="utf-8")
        _wait_for(lambda: len(self.events()) >= 3)
        self.assertEqual(self.events()[:3], ["start", "stop", "start"])

        process.send_signal(signal.SIGTERM)
        process.wait(timeout=15)
        self.assertEqual(self.events(), ["start", "stop", "start", "stop"])

    @staticmethod
    def _stop_supervisor(process):
        if process.poll() is not None:
            return
        process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


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
