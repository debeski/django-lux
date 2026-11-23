"""The app's view of its mounted data, and the files it shares with Composer.

DjangoLux images move to a fixed non-root uid (10001) with group 0, and reach
data written while the stack ran as root through group bits. The entrypoint gate
must stop a container whose data is not ready, and every file the app creates on
the runtime volume must stay usable by composer-agent (uid 0, no capabilities).
"""
from dlux.tests.harness import setup_test_environment

setup_test_environment()

import io
import json
import os
import stat
import tempfile
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase

from dlux import doctor, mount_access
from dlux.contracts import runtime as runtime_contract
from dlux.updater import shared_files
from dlux.updater.runtime import RuntimeStore

TEMPLATES = Path(__file__).resolve().parents[1] / "scaffold" / "templates" / "project"


def _st(uid, gid, mode, kind=stat.S_IFDIR):
    return os.stat_result((kind | mode, 0, 0, 1, uid, gid, 0, 0, 0, 0))


class AllowedTests(SimpleTestCase):
    def test_root_needs_no_bits(self):
        self.assertTrue(mount_access.allowed(_st(5, 5, 0o000), 0, {0}, 7))

    def test_owner_group_and_other_bits_are_checked_in_order(self):
        directory = _st(0, 0, 0o755)
        self.assertFalse(mount_access.allowed(directory, 10001, {0}, 7))
        self.assertTrue(mount_access.allowed(_st(0, 0, 0o775), 10001, {0}, 7))
        self.assertTrue(mount_access.allowed(_st(10001, 5, 0o700), 10001, {0}, 7))
        # The owner's own bits win even when the group would allow more.
        self.assertFalse(mount_access.allowed(_st(10001, 0, 0o577), 10001, {0}, 2))

    def test_a_private_root_file_is_unreadable_to_the_app(self):
        self.assertFalse(mount_access.allowed(_st(0, 0, 0o600, stat.S_IFREG), 10001, {0}, 4))
        self.assertTrue(mount_access.allowed(_st(0, 0, 0o640, stat.S_IFREG), 10001, {0}, 4))


class MountinfoTests(SimpleTestCase):
    def test_mounts_below_the_app_roots_with_their_read_only_flag(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as handle:
            handle.write(
                "1 0 8:1 / / rw,relatime - ext4 /dev/root rw\n"
                "2 1 8:1 /src /app rw,relatime - ext4 /dev/root rw\n"
                "3 1 8:1 /m /app/media rw,relatime - ext4 /dev/root rw\n"
                "4 1 8:1 /i /app/imports ro,relatime - ext4 /dev/root rw\n"
                "5 1 8:1 /r /opt/dlux-runtime ro,relatime - ext4 /dev/root rw\n"
                "6 1 8:1 /s /app/scan\\040releases rw,relatime - ext4 /dev/root rw\n"
                "7 1 8:1 /h /etc/hosts rw,relatime - ext4 /dev/root rw\n"
            )
        self.addCleanup(os.unlink, handle.name)

        found = mount_access.mounts(handle.name)

        self.assertEqual(found, {
            "/app/media": False,
            "/app/imports": True,
            "/opt/dlux-runtime": True,
            "/app/scan releases": False,
        })


class TreeTests(SimpleTestCase):
    """A tree owned by the test runner, judged for a uid that only shares its group."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(self._cleanup)
        self.mountinfo = self.root / "mountinfo"
        self.uid = os.geteuid() + 1 if os.geteuid() else 10001
        self.groups = {os.getegid()}
        roots = mock.patch.object(mount_access, "MOUNT_ROOTS", (str(self.root),))
        roots.start()
        self.addCleanup(roots.stop)

    def _cleanup(self):
        for path, dirs, _files in os.walk(self.root):
            for name in dirs:
                entry = os.path.join(path, name)
                if not os.path.islink(entry):
                    os.chmod(entry, 0o755)
        import shutil

        shutil.rmtree(self.root, ignore_errors=True)

    def _mount(self, name, read_only=False):
        path = self.root / name
        path.mkdir()
        with self.mountinfo.open("a") as stream:
            stream.write(f"9 1 8:1 /x {path} {'ro' if read_only else 'rw'} - ext4 /dev/root rw\n")
        return path

    def _problems(self, **kwargs):
        return list(mount_access.problems(self.uid, self.groups, mountinfo=str(self.mountinfo), **kwargs))

    def test_root_owned_style_tree_needs_group_write_on_directories_only(self):
        media = self._mount("media")
        (media / "decree").mkdir()
        (media / "decree" / "a.pdf").write_text("x")
        os.chmod(media / "decree" / "a.pdf", 0o644)
        os.chmod(media / "decree", 0o755)
        os.chmod(media, 0o755)

        found = {item["path"]: item["needs"] for item in self._problems()}

        self.assertEqual(found, {str(media): "rwx", str(media / "decree"): "rwx"})

        os.chmod(media, 0o775)
        os.chmod(media / "decree", 0o775)
        self.assertEqual(self._problems(), [])

    def test_files_under_a_logs_mount_must_be_writable(self):
        logs = self._mount("logs")
        os.chmod(logs, 0o775)
        (logs / "django.log").write_text("")
        os.chmod(logs / "django.log", 0o644)

        self.assertEqual([item["needs"] for item in self._problems()], ["rw"])

    def test_a_read_only_mount_only_needs_reading(self):
        runtime = self._mount("runtime", read_only=True)
        (runtime / "state").mkdir()
        os.chmod(runtime / "state", 0o755)
        (runtime / "state" / "deploy-status.json").write_text("{}")
        os.chmod(runtime / "state" / "deploy-status.json", 0o600)
        os.chmod(runtime, 0o755)

        found = self._problems()

        self.assertEqual([(Path(item["path"]).name, item["needs"]) for item in found],
                         [("deploy-status.json", "r")])

    def test_the_runtime_volume_needs_write_only_at_the_top_and_in_state(self):
        runtime = self._mount("runtime")
        package = runtime / "releases" / "1.16.2" / "dlux"
        package.mkdir(parents=True)
        (package / "x.py").write_text("")
        state = runtime / "state"
        (state / "relay").mkdir(parents=True)
        (state / "image-available.json").write_text("{}")
        (state / "deploy-status.json").write_text("{}")
        for path in (package, package.parent, state / "relay"):
            os.chmod(path, 0o755)
        os.chmod(package / "x.py", 0o644)
        os.chmod(state / "image-available.json", 0o644)
        os.chmod(state / "deploy-status.json", 0o600)
        for path in (runtime, runtime / "releases", state):
            os.chmod(path, 0o775)

        with mock.patch.dict(os.environ, {"DLUX_UPDATE_RUNTIME_ROOT": str(runtime)}):
            found = sorted((Path(item["path"]).name, item["needs"]) for item in self._problems())

        # A state file is replaced by a rename into its directory, never written
        # in place, so a root-written 0644 file is fine and a 0600 one needs read.
        self.assertEqual(found, [("deploy-status.json", "r"), ("relay", "rwx")])

    def test_symlinks_are_not_followed_or_reported(self):
        media = self._mount("media")
        os.chmod(media, 0o775)
        os.symlink("/etc", media / "link")

        self.assertEqual(self._problems(), [])

    def test_the_gate_looks_two_levels_deep(self):
        media = self._mount("media")
        deep = media / "a" / "b" / "c"
        deep.mkdir(parents=True)
        for path in (media, media / "a", media / "a" / "b"):
            os.chmod(path, 0o775)
        os.chmod(deep, 0o755)

        self.assertEqual(self._problems(max_depth=mount_access.GATE_DEPTH), [])
        self.assertEqual([item["path"] for item in self._problems()], [str(deep)])

    def test_gate_refuses_with_exit_78_and_names_the_path(self):
        media = self._mount("media")
        os.chmod(media, 0o755)
        out = io.StringIO()
        with mock.patch.object(mount_access, "current_identity", return_value=(self.uid, self.groups)):
            status = mount_access.gate(out=out, mountinfo=str(self.mountinfo))

        self.assertEqual(status, mount_access.GATE_EXIT)
        self.assertIn(str(media), out.getvalue())
        self.assertIn("check --fix", out.getvalue())

    def test_gate_passes_ready_data_and_skips_root(self):
        media = self._mount("media")
        os.chmod(media, 0o775)
        with mock.patch.object(mount_access, "current_identity", return_value=(self.uid, self.groups)):
            self.assertEqual(mount_access.gate(out=io.StringIO(), mountinfo=str(self.mountinfo)), 0)
        os.chmod(media, 0o700)
        with mock.patch.object(mount_access, "current_identity", return_value=(0, {0})):
            self.assertEqual(mount_access.gate(out=io.StringIO(), mountinfo=str(self.mountinfo)), 0)

    def test_report_as_root_judges_the_app_identity(self):
        self._mount("media")
        with mock.patch.object(mount_access, "current_identity", return_value=(0, {0})):
            result = mount_access.report(mountinfo=str(self.mountinfo))

        self.assertTrue(result["running_as_root"])
        self.assertEqual((result["uid"], result["gid"]), (10001, 0))


class SharedFilesTests(SimpleTestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.root, ignore_errors=True))
        self.old_umask = os.umask(0o022)
        self.addCleanup(os.umask, self.old_umask)

    def test_files_and_new_directories_are_group_writable_whatever_the_umask(self):
        target = self.root / "state" / "agent" / "results" / "op.json"

        shared_files.write_text(target, "{}\n")

        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o664)
        for directory in (self.root / "state", self.root / "state" / "agent", target.parent):
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o775)
        self.assertEqual(target.read_text(), "{}\n")

    def test_existing_directories_keep_their_mode(self):
        existing = self.root / "state"
        existing.mkdir(mode=0o755)
        os.chmod(existing, 0o755)

        shared_files.write_text(existing / "a.json", "1")

        self.assertEqual(stat.S_IMODE(existing.stat().st_mode), 0o755)

    def test_a_leftover_fixed_name_temporary_file_does_not_block(self):
        target = self.root / "active.json"
        leftover = self.root / ".active.json.tmp"
        leftover.write_text("stale")
        os.chmod(leftover, 0o444)

        shared_files.write_text(target, "fresh")

        self.assertEqual(target.read_text(), "fresh")
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), [".active.json.tmp", "active.json"])

    def test_runtime_store_writes_through_the_shared_helper(self):
        store = RuntimeStore(self.root).ensure()

        self.assertEqual(stat.S_IMODE(store.generation_file.stat().st_mode), 0o664)
        for directory in (store.releases, store.staging, store.downloads, store.failed, store.state_dir):
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o775)


class ContractTests(SimpleTestCase):
    def test_code_and_runtime_contract_agree_on_identity_and_modes(self):
        permissions = runtime_contract.load_contract()["permissions"]

        self.assertEqual(permissions["app_uid"], mount_access.APP_UID)
        self.assertEqual(permissions["app_gid"], mount_access.APP_GID)
        self.assertEqual(int(permissions["directory_mode"], 8), shared_files.SHARED_DIR_MODE)
        self.assertEqual(int(permissions["file_mode"], 8), shared_files.SHARED_FILE_MODE)

    def test_the_entrypoint_sets_the_umask_and_gates_before_waiting_for_the_database(self):
        text = (TEMPLATES / "entrypoint.sh.tmpl").read_text(encoding="utf-8")

        umask = text.index("\numask 0002\n")
        gate = text.index("\npython -m dlux.mount_access gate\n")
        self.assertLess(umask, gate)
        self.assertLess(gate, text.index("until nc -z"))

    def test_the_doctor_runs_the_check(self):
        ids = [check_id for check_id, *_rest in doctor._REGISTRY]
        self.assertIn("storage.mount_access", ids)

    def test_the_doctor_reports_root_readiness_as_informational(self):
        sample = [{"path": "/app/media", "kind": "dir", "owner": "0:0", "mode": "0755", "needs": "rwx"}]
        result = {"running_as_root": True, "uid": 10001, "gid": 0, "mounts": ["/app/media"],
                  "problems": 1, "sample": sample}
        with mock.patch.object(mount_access, "report", return_value=result):
            finding = doctor._check_mount_access(doctor.Context())

        self.assertEqual(finding.status, doctor.SKIPPED)
        self.assertIn("/app/media", finding.detail)

    def test_the_doctor_fails_when_the_running_uid_cannot_use_its_data(self):
        result = {"running_as_root": False, "uid": 10001, "gid": 0, "mounts": ["/app/media"],
                  "problems": 3, "sample": []}
        with mock.patch.object(mount_access, "report", return_value=result):
            finding = doctor._check_mount_access(doctor.Context())

        self.assertEqual(finding.status, doctor.ERROR)
        self.assertIn("check --fix", finding.remedy)


if __name__ == "__main__":
    import unittest

    unittest.main()
