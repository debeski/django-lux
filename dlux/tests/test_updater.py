import json
import os
from datetime import timedelta
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
from unittest import mock
import zipfile

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db import close_old_connections, connection
from django.test import Client, SimpleTestCase, TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.urls import reverse
from django.utils import timezone

from dlux import __version__
from dlux.models import (
    ActivityLog,
    DluxImageUpdate,
    DluxUpdateRun,
    DluxUpdateState,
    SystemBackup,
    SystemSettings,
)
from dlux.scaffold import ScaffoldError, enable_updater
from dlux.updater import UpdaterError
from dlux.updater.manifest import (
    ReleaseCandidate,
    _validated_https_url,
    assess_wheel,
    download_wheel,
    select_latest_candidate,
    validate_local_release_manifest,
    validate_release_manifest,
    verify_pypi_attestation,
)
from dlux.updater.runtime import RuntimeStore
from dlux.updater.image_update import (
    ack_path,
    app_version,
    image_update_metadata,
    queue_image_update,
    read_composer_ack,
    read_deploy_status,
    status_path,
)
from dlux.updater.health import runtime_probe_token
from dlux.updater.release_check import (
    _changed_migrations,
    _previous_release_tag,
    validate_inline_migrations,
)
from dlux.updater.service import (
    UpdateService,
    _sanitize,
    queue_daily_check_if_due,
    queue_run,
)


def _newer_version(base=__version__):
    """Return a version string strictly greater than ``base`` (patch +1).

    Lets version-sensitive updater tests model a volume release that is newer
    than the baked ``__version__`` without hardcoding a literal that collides
    with the package version on each release bump.
    """
    parts = base.split(".")
    try:
        parts[-1] = str(int(parts[-1]) + 1)
    except (ValueError, IndexError):
        return f"{base}.1"
    return ".".join(parts)


NEWER_VERSION = _newer_version()


class FakeResponse:
    def __init__(self, payload, url="https://files.pythonhosted.org/package.whl", headers=None):
        self.payload = payload
        self.url = url
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        return self.payload if size < 0 else self.payload[:size]

    def geturl(self):
        return self.url


def release_manifest(version="1.2.3", **overrides):
    manifest = {
        "schema_version": 1,
        "version": version,
        "inline_safe": True,
        "minimum_updater_schema": 1,
        "migration_policy": "backward_compatible",
        "summary": "Safe updater test release",
        "release_url": f"https://github.com/debeski/django-lux/releases/tag/v{version}",
    }
    manifest.update(overrides)
    return manifest


def make_wheel(path, version="1.2.3", *, manifest=None, requires=(), requires_python=">=3.11"):
    manifest = manifest or release_manifest(version)
    metadata = [
        "Metadata-Version: 2.1",
        "Name: django-lux",
        f"Version: {version}",
        f"Requires-Python: {requires_python}",
    ]
    metadata.extend(f"Requires-Dist: {requirement}" for requirement in requires)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("dlux/release-manifest.json", json.dumps(manifest))
        archive.writestr(
            f"django_lux-{version}.dist-info/METADATA",
            "\n".join(metadata) + "\n",
        )
    return path


class StateOnlyMigrationGateTests(SimpleTestCase):
    """The `SeparateDatabaseAndState` allowance in the inline-safety gate.

    No shipped migration uses it right now — 0018 did until it was folded into
    0016, where the choice became part of CreateModel and the field alteration
    disappeared. RELEASING.md still documents the pattern for the next genuinely
    column-free field change, so it is tested directly rather than left as
    untested capability waiting for its first user.
    """

    @staticmethod
    def _op(source):
        import ast
        return ast.parse(source, mode='eval').body

    def test_an_empty_database_operations_list_is_safe(self):
        from dlux.updater.release_check import _separate_state_is_safe
        self.assertTrue(_separate_state_is_safe(self._op(
            "migrations.SeparateDatabaseAndState("
            "database_operations=[], state_operations=[migrations.AlterField()])"
        )))

    def test_a_populated_database_operations_list_is_not_safe(self):
        from dlux.updater.release_check import _separate_state_is_safe
        self.assertFalse(_separate_state_is_safe(self._op(
            "migrations.SeparateDatabaseAndState("
            "database_operations=[migrations.RunSQL('SELECT 1')], state_operations=[])"
        )))

    def test_omitting_database_operations_is_not_safe(self):
        """Absent is not empty: Django would then run the state ops for real."""
        from dlux.updater.release_check import _separate_state_is_safe
        self.assertFalse(_separate_state_is_safe(self._op(
            "migrations.SeparateDatabaseAndState(state_operations=[migrations.AlterField()])"
        )))

    def test_the_positional_form_is_read_too(self):
        from dlux.updater.release_check import _separate_state_is_safe
        self.assertTrue(_separate_state_is_safe(self._op(
            "migrations.SeparateDatabaseAndState([], [migrations.AlterField()])"
        )))
        self.assertFalse(_separate_state_is_safe(self._op(
            "migrations.SeparateDatabaseAndState([migrations.RunSQL('SELECT 1')], [])"
        )))


class ManifestTests(TestCase):
    def test_manifest_schema_and_version_are_enforced(self):
        self.assertEqual(validate_release_manifest(release_manifest(), "1.2.3")["version"], "1.2.3")
        with self.assertRaises(UpdaterError):
            validate_release_manifest(release_manifest(schema_version=2), "1.2.3")
        with self.assertRaises(UpdaterError):
            validate_release_manifest(release_manifest(version="1.2.4"), "1.2.3")

    def test_latest_candidate_excludes_prerelease_yanked_and_platform_wheels(self):
        def item(filename, *, yanked=False):
            return {
                "filename": filename,
                "url": f"https://files.pythonhosted.org/{filename}",
                "hashes": {"sha256": "a" * 64},
                "yanked": yanked,
                "requires-python": ">=3.11",
            }

        index = {"files": [
            item("django_lux-1.2.2-py3-none-any.whl"),
            item("django_lux-1.3.0rc1-py3-none-any.whl"),
            item("django_lux-1.2.4-py3-none-any.whl", yanked=True),
            item("django_lux-1.2.5-cp313-cp313-manylinux_2_17_x86_64.whl"),
            item("django_lux-1.2.3-py3-none-any.whl"),
        ]}
        candidate = select_latest_candidate(index, "1.2.1")
        self.assertEqual(candidate.version, "1.2.3")
        self.assertEqual(candidate.requires_python, ">=3.11")

    def test_download_rejects_hash_mismatch_and_redirect_host(self):
        payload = b"not-a-wheel"
        candidate = ReleaseCandidate("1.2.3", "django_lux-1.2.3-py3-none-any.whl", "https://files.pythonhosted.org/a.whl", "0" * 64)
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(UpdaterError):
                download_wheel(candidate, Path(temp_dir) / "a.whl", opener=lambda *a, **k: FakeResponse(payload))
        with self.assertRaises(UpdaterError):
            _validated_https_url("https://evil.example/django_lux.whl")

    def test_attestation_requires_official_repository_and_workflow(self):
        candidate = ReleaseCandidate("1.2.3", "django_lux-1.2.3-py3-none-any.whl", "https://files.pythonhosted.org/a.whl", "a" * 64)
        runner = mock.Mock(return_value=SimpleNamespace(returncode=0, stdout="", stderr=""))

        def opener(request, timeout=0):
            provenance = {"attestation_bundles": [{"publisher": {
                "kind": "GitHub",
                "repository": "debeski/django-lux",
                "workflow": "release.yml",
            }}]}
            return FakeResponse(json.dumps(provenance).encode(), "https://pypi.org/integrity/x")

        present = mock.patch(
            "dlux.updater.manifest.importlib.util.find_spec",
            return_value=SimpleNamespace(),
        )
        with present:
            self.assertTrue(verify_pypi_attestation(candidate, runner=runner, opener=opener))
        command = runner.call_args.args[0]
        self.assertEqual(command[:3], [sys.executable, "-m", "pypi_attestations"])

        def wrong_opener(request, timeout=0):
            provenance = {"attestation_bundles": [{"publisher": {
                "kind": "GitHub", "repository": "fork/django-lux", "workflow": "release.yml",
            }}]}
            return FakeResponse(json.dumps(provenance).encode(), "https://pypi.org/integrity/x")

        with present, self.assertRaises(UpdaterError):
            verify_pypi_attestation(candidate, runner=runner, opener=wrong_opener)

        with mock.patch("dlux.updater.manifest.importlib.util.find_spec", return_value=None):
            with self.assertRaisesMessage(UpdaterError, "attestation verification is unavailable"):
                verify_pypi_attestation(candidate, runner=runner, opener=opener)

    def test_assessment_rejects_dependency_python_and_manifest_changes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            wheel = make_wheel(
                Path(temp_dir) / "candidate.whl",
                requires=("definitely-not-installed-dlux-test>=1",),
                requires_python=">=99",
            )
            candidate = ReleaseCandidate("1.2.3", wheel.name, "https://files.pythonhosted.org/a.whl", "a" * 64)
            assessment = assess_wheel(candidate, wheel)
            self.assertFalse(assessment["compatible"])
            self.assertTrue(assessment["reason"].startswith("Project image rebuild required."))
            self.assertIn("Required dependency", assessment["reason"])
            self.assertIn("requires Python", assessment["reason"])

            unsafe = make_wheel(
                Path(temp_dir) / "unsafe.whl",
                manifest=release_manifest(inline_safe=False, migration_policy="image_rebuild"),
            )
            self.assertFalse(assess_wheel(candidate, unsafe)["compatible"])

    def test_sanitized_logs_redact_secrets_and_are_bounded(self):
        raw = (
            "password=plain token: abc "
            '"secret": "quoted value" Authorization: Bearer bearer-value '
            "--password cli-value DJANGO_SECRET_KEY=env-value\n"
        )
        sanitized_values = _sanitize(raw, limit=1000)
        for secret in ("plain", "abc", "quoted value", "bearer-value", "cli-value", "env-value"):
            self.assertNotIn(secret, sanitized_values)
        sanitized = _sanitize(raw + ("x" * 5000), limit=100)
        self.assertLessEqual(len(sanitized), 100)

    def test_release_gate_allows_only_compatible_migration_operations(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            safe = Path(temp_dir) / "0004_safe.py"
            safe.write_text(
                "from django.db import migrations, models\n"
                "class Migration(migrations.Migration):\n"
                "    operations = [\n"
                "        migrations.CreateModel(name='Safe', fields=[]),\n"
                "        migrations.AddField(model_name='safe', name='note', field=models.TextField(null=True)),\n"
                "        migrations.AddIndex(model_name='safe', index=models.Index(fields=['note'], name='safe_note_idx')),\n"
                "    ]\n",
                encoding="utf-8",
            )
            with mock.patch("dlux.updater.release_check._changed_migrations", return_value=[safe]):
                self.assertTrue(validate_inline_migrations("v1.2.2"))
            unsafe = Path(temp_dir) / "0005_unsafe.py"
            unsafe.write_text(
                "from django.db import migrations\n"
                "class Migration(migrations.Migration):\n"
                "    operations = [migrations.RemoveField(model_name='safe', name='note')]\n",
                encoding="utf-8",
            )
            with mock.patch("dlux.updater.release_check._changed_migrations", return_value=[unsafe]):
                with self.assertRaises(RuntimeError):
                    validate_inline_migrations("v1.2.2")

    def test_release_gate_requires_database_default_for_not_null_add_field(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            python_default = Path(temp_dir) / "0004_python_default.py"
            python_default.write_text(
                "from django.db import migrations, models\n"
                "class Migration(migrations.Migration):\n"
                "    operations = [migrations.AddField("
                "model_name='thing', name='kind', field=models.CharField(default='manual', max_length=12))]\n",
                encoding="utf-8",
            )
            with mock.patch("dlux.updater.release_check._changed_migrations", return_value=[python_default]):
                with self.assertRaisesRegex(RuntimeError, "db_default"):
                    validate_inline_migrations("v1.2.6")

            database_default = Path(temp_dir) / "0004_database_default.py"
            database_default.write_text(
                "from django.db import migrations, models\n"
                "class Migration(migrations.Migration):\n"
                "    operations = [migrations.AddField("
                "model_name='thing', name='kind', field=models.CharField("
                "default='manual', db_default='manual', max_length=12))]\n",
                encoding="utf-8",
            )
            with mock.patch("dlux.updater.release_check._changed_migrations", return_value=[database_default]):
                self.assertTrue(validate_inline_migrations("v1.2.6"))

    def test_release_gate_includes_worktree_and_untracked_migrations(self):
        results = [
            SimpleNamespace(stdout="dlux/migrations/0004_tracked.py\n"),
            SimpleNamespace(stdout="dlux/migrations/0005_untracked.py\n"),
        ]
        with mock.patch("dlux.updater.release_check.subprocess.run", side_effect=results) as run:
            paths = _changed_migrations("v1.2.1")
        self.assertEqual(paths, [
            Path("dlux/migrations/0004_tracked.py"),
            Path("dlux/migrations/0005_untracked.py"),
        ])
        self.assertEqual(run.call_args_list[0].args[0][3], "v1.2.1")
        self.assertIn("--others", run.call_args_list[1].args[0])

    def test_local_migrations_honor_manifest_inline_safe_claim(self):
        """Guard the SHIPPING release, not just the validator's mechanics.

        If ``dlux/release-manifest.json`` advertises ``inline_safe: true`` then
        the migrations this release actually adds (tracked-since-the-previous-tag
        plus any untracked worktree migration) must pass the inline-migration
        validator. This catches the exact class of mistake where a new migration
        introduces an operation outside the ``CreateModel``/``AddField``/
        ``AddIndex`` allowlist — e.g. an ``AlterModelOptions`` emitted by adding a
        permission to an *existing* model — while the manifest still claims the
        update is inline-safe. It mirrors what the CI release gate
        (``release_check.main``) enforces at tag time, but runs on every suite so
        the flag can never silently drift from the code.

        Skips gracefully where git history is unavailable (e.g. an installed
        wheel with no repository or previous tag), since there is nothing to diff.
        """
        manifest = validate_local_release_manifest()
        if not manifest["inline_safe"]:
            self.skipTest("Release declares inline_safe=False; no inline guarantee to verify.")
        try:
            base_tag = _previous_release_tag(f"v{manifest['version']}")
        except (RuntimeError, subprocess.SubprocessError, FileNotFoundError) as exc:
            self.skipTest(f"No previous release tag available for comparison: {exc}")
        try:
            self.assertTrue(validate_inline_migrations(base_tag))
        except RuntimeError as exc:
            self.fail(
                "release-manifest.json declares inline_safe=True but the migrations "
                f"added since {base_tag} are NOT inline-safe:\n{exc}"
            )


class RuntimeStoreTests(TestCase):
    def test_wheel_download_path_preserves_the_canonical_pip_filename(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RuntimeStore(temp_dir).ensure()
            filename = f"django_lux-{NEWER_VERSION}-py3-none-any.whl"
            candidate = ReleaseCandidate(
                NEWER_VERSION,
                filename,
                f"https://files.pythonhosted.org/{filename}",
                "a" * 64,
            )
            wheel = store.wheel_path(candidate)
            self.assertEqual(wheel.name, filename)
            self.assertEqual(wheel.parent.name, "a" * 64)
            self.assertEqual(wheel.parent.parent, store.downloads)

            runner = mock.Mock(return_value=SimpleNamespace(returncode=0, stdout="", stderr=""))
            RuntimeStore.install_wheel(wheel, Path(temp_dir) / "target", runner=runner)
            install_command = runner.call_args.args[0]
            self.assertEqual(Path(install_command[-1]).name, filename)

    def test_wheel_staging_failure_keeps_bounded_redacted_pip_detail(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            wheel = Path(temp_dir) / f"django_lux-{NEWER_VERSION}-py3-none-any.whl"
            runner = mock.Mock(return_value=SimpleNamespace(
                returncode=1,
                stdout="",
                stderr="Looking in indexes: https://user:password@example.test/simple\n"
                       "ERROR: Invalid wheel filename\n",
            ))
            with self.assertRaisesMessage(UpdaterError, "ERROR: Invalid wheel filename") as raised:
                RuntimeStore.install_wheel(wheel, Path(temp_dir) / "target", runner=runner)
            self.assertNotIn("user:password", str(raised.exception))

    def test_baked_fallback_atomic_switch_corrupt_state_and_rollback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RuntimeStore(temp_dir).ensure()
            self.assertEqual(store.read_active("1.2.2")["source"], "image")
            release = store.release_path("1.2.3")
            release.mkdir()
            generation = store.bump_generation()
            store.write_active("1.2.3", source="volume", generation=generation)
            self.assertEqual(store.read_active("1.2.2")["path"], str(release))
            store.write_active("1.2.2", source="image", generation=store.bump_generation())
            self.assertEqual(store.read_active("1.2.2")["version"], "1.2.2")
            store.active_file.write_text("{broken", encoding="utf-8")
            with self.assertRaises(UpdaterError):
                store.read_active("1.2.2")
            store.write_heartbeat()
            store.invalidate_heartbeat()
            self.assertEqual(store.heartbeat_file.read_text(encoding="utf-8"), "0\n")

    def test_supervisor_uses_release_and_restarts_on_generation(self):
        from dlux.scaffold import _render_template

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runtime = root / "runtime"
            release = runtime / "releases" / "1.2.3"
            state = runtime / "state"
            release.mkdir(parents=True)
            state.mkdir()
            (state / "active.json").write_text(json.dumps({
                "version": "1.2.3", "source": "volume", "generation": 0,
            }), encoding="utf-8")
            (state / "generation").write_text("0\n", encoding="utf-8")
            supervisor = root / "supervisor.py"
            from dlux.updater import supervisor as _supervisor_module
            supervisor.write_text(
                Path(_supervisor_module.__file__).read_text(encoding="utf-8"), encoding="utf-8"
            )
            child = root / "child.py"
            log = root / "launches.txt"
            child.write_text(
                "import json,os,signal,time,pathlib\n"
                "payload={'pythonpath':os.environ.get('PYTHONPATH',''),"
                "'baked':os.environ.get('DLUX_BAKED_VERSION','')}\n"
                f"pathlib.Path({str(log)!r}).open('a').write(json.dumps(payload)+'\\n')\n"
                "def stop(*args):\n    raise SystemExit(0)\n"
                "signal.signal(signal.SIGTERM, stop)\n"
                "time.sleep(30)\n",
                encoding="utf-8",
            )
            # Pin DLUX_BAKED_VERSION explicitly so the assertion is deterministic
            # and independent of the installed-package metadata (importlib.metadata),
            # which can lag the source/manifest version on a source checkout. The
            # supervisor's runtime_environment() keeps an already-set value, so this
            # is exactly what the child should report back as "baked". Kept below the
            # 1.2.3 volume release so the version gate activates it.
            expected_baked = "1.0.0"
            supervisor_env = {**os.environ, "DLUX_BAKED_VERSION": expected_baked}
            process = subprocess.Popen([
                sys.executable, str(supervisor), "--runtime-root", str(runtime),
                "--poll-seconds", "0.1", "--grace-seconds", "2", "--",
                sys.executable, str(child),
            ], env=supervisor_env)
            deadline = time.monotonic() + 5
            while (not log.exists() or len(log.read_text().splitlines()) < 1) and time.monotonic() < deadline:
                time.sleep(0.05)
            (state / "generation").write_text("1\n", encoding="utf-8")
            deadline = time.monotonic() + 5
            while (not log.exists() or len(log.read_text().splitlines()) < 2) and time.monotonic() < deadline:
                time.sleep(0.05)
            process.terminate()
            process.wait(timeout=5)
            launches = [json.loads(line) for line in log.read_text().splitlines()]
            self.assertGreaterEqual(len(launches), 2)
            self.assertTrue(all(str(release) in item["pythonpath"] for item in launches[:2]))
            self.assertTrue(all(item["baked"] == expected_baked for item in launches[:2]))

    def test_reconcile_preserves_image_baked_version_while_volume_release_is_active(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RuntimeStore(temp_dir).ensure()
            store.release_path("1.2.3").mkdir()
            store.write_active("1.2.3", source="volume", generation=0)
            state = DluxUpdateState.load()
            state.baked_version = "1.2.2"
            state.active_version = "1.2.3"
            state.save()
            service = UpdateService(store=store)
            with mock.patch("dlux.__version__", "1.2.3"), mock.patch(
                "dlux.updater.service.get_baked_version", return_value="1.2.2"
            ):
                reconciled = service.reconcile()
            self.assertEqual(reconciled.baked_version, "1.2.2")
            self.assertEqual(reconciled.active_version, "1.2.3")

    def test_the_state_tick_reconciles_a_row_left_behind_by_an_upgrade(self):
        """The 1.8.0 regression: nothing called reconcile() any more.

        `dlux-updater` reconciled at startup; the Celery tick that replaced it
        did not, so a row written before an image upgrade kept naming the old
        versions — and kept offering a rollback to a release that is gone.
        """
        from dlux.updater import service as service_module

        with tempfile.TemporaryDirectory() as temp_dir:
            store = RuntimeStore(temp_dir).ensure()
            store.release_path("1.7.0").mkdir()
            store.write_active("1.7.0", source="volume", generation=0)
            state = DluxUpdateState.load()
            state.baked_version = "1.5.10"
            state.active_version = "1.7.0"
            state.previous_version = "1.6.1"
            state.latest_version = "1.7.0"
            state.latest_compatible = True
            state.save()
            service = UpdateService(store=store)
            with mock.patch.object(service_module, "_PROCESS_RECONCILED", False), mock.patch(
                "dlux.updater.service.get_baked_version", return_value="1.8.4"
            ):
                reconciled = service_module.reconcile_state_if_due(service)
            self.assertEqual(reconciled.baked_version, "1.8.4")
            self.assertEqual(reconciled.active_version, "1.8.4")
            self.assertEqual(reconciled.previous_version, "")
            self.assertEqual(reconciled.latest_version, "")
            self.assertFalse(reconciled.latest_compatible)

    def test_reconcile_does_not_run_on_every_tick(self):
        """It reads the volume and writes the row; the tick fires every few seconds."""
        from dlux.updater import service as service_module

        with tempfile.TemporaryDirectory() as temp_dir:
            store = RuntimeStore(temp_dir).ensure()
            state = DluxUpdateState.load()
            state.baked_version = "1.8.4"
            state.active_version = "1.8.4"
            state.save()
            service = UpdateService(store=store)
            with mock.patch.object(service_module, "_PROCESS_RECONCILED", True), mock.patch(
                "dlux.updater.service.get_baked_version", return_value="1.8.4"
            ), mock.patch.object(service, "reconcile") as reconcile:
                self.assertIsNone(service_module.reconcile_state_if_due(service))
            reconcile.assert_not_called()

    def test_a_swapped_image_reconciles_without_a_worker_restart(self):
        from dlux.updater import service as service_module

        with tempfile.TemporaryDirectory() as temp_dir:
            store = RuntimeStore(temp_dir).ensure()
            state = DluxUpdateState.load()
            state.baked_version = "1.8.4"
            state.active_version = "1.8.4"
            state.save()
            service = UpdateService(store=store)
            with mock.patch.object(service_module, "_PROCESS_RECONCILED", True), mock.patch(
                "dlux.updater.service.get_baked_version", return_value="1.8.6"
            ):
                reconciled = service_module.reconcile_state_if_due(service)
            self.assertEqual(reconciled.baked_version, "1.8.6")

    def test_a_failing_reconcile_never_takes_the_tick_down(self):
        from dlux.updater import service as service_module

        with tempfile.TemporaryDirectory() as temp_dir:
            service = UpdateService(store=RuntimeStore(temp_dir).ensure())
            with mock.patch.object(service_module, "_PROCESS_RECONCILED", False), mock.patch.object(
                service, "reconcile", side_effect=OSError("volume gone")
            ):
                self.assertIsNone(service_module.reconcile_state_if_due(service))

    def test_newer_rebuilt_image_supersedes_older_volume_pointer(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RuntimeStore(temp_dir).ensure()
            store.release_path("1.2.3").mkdir()
            store.write_active("1.2.3", source="volume", generation=0)
            state = DluxUpdateState.load()
            state.baked_version = "1.2.2"
            state.active_version = "1.2.3"
            state.active_wheel_url = "https://files.pythonhosted.org/old.whl"
            state.active_wheel_sha256 = "a" * 64
            state.active_manifest = release_manifest()
            state.previous_version = "1.2.2"
            state.latest_version = "1.2.4"
            state.latest_compatible = True
            state.save()
            service = UpdateService(store=store)
            with mock.patch("dlux.__version__", "1.2.3"), mock.patch(
                "dlux.updater.service.get_baked_version", return_value="1.3.0"
            ):
                reconciled = service.reconcile()
            active = store.read_active("1.3.0")
            self.assertEqual(active["source"], "image")
            self.assertEqual(active["version"], "1.3.0")
            self.assertEqual(reconciled.baked_version, "1.3.0")
            self.assertEqual(reconciled.active_version, "1.3.0")
            self.assertEqual(reconciled.previous_version, "")
            self.assertEqual(reconciled.latest_version, "")
            self.assertTrue(service.restart_worker)

    def test_newer_rebuilt_image_supersedes_stale_baked_database_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RuntimeStore(temp_dir).ensure()
            state = DluxUpdateState.load()
            state.baked_version = "1.2.2"
            state.active_version = "1.2.2"
            state.latest_version = "1.2.3"
            state.latest_wheel_url = "https://files.pythonhosted.org/old.whl"
            state.latest_wheel_sha256 = "a" * 64
            state.latest_manifest = release_manifest()
            state.latest_compatible = True
            state.save()
            store.set_maintenance(True, token="failed-update")
            store.set_degraded("failed health check")
            state.degraded = True
            state.degraded_reason = "failed health check"
            state.save(update_fields=["degraded", "degraded_reason"])
            service = UpdateService(store=store)
            with mock.patch(
                "dlux.updater.service.get_baked_version",
                return_value="1.2.4",
            ), mock.patch("dlux.updater.service.download_wheel") as download:
                reconciled = service.reconcile()
            active = store.read_active("1.2.4")
            self.assertEqual(active["source"], "image")
            self.assertEqual(active["version"], "1.2.4")
            self.assertEqual(reconciled.baked_version, "1.2.4")
            self.assertEqual(reconciled.active_version, "1.2.4")
            self.assertEqual(reconciled.previous_version, "")
            self.assertEqual(reconciled.latest_version, "")
            self.assertFalse(reconciled.degraded)
            self.assertFalse(store.maintenance_file.exists())
            self.assertFalse(store.degraded_file.exists())
            download.assert_not_called()

    def test_unreconstructable_active_reverts_to_baked_instead_of_degrading(self):
        # active_version is newer than baked but was never a downloadable wheel
        # (image/mount activation) and no volume release exists on disk — e.g. a
        # backward image move, or a wiped runtime volume. reconcile must revert to
        # the baked image and clear degraded instead of chasing a wheel that never
        # existed and wedging the runtime permanently.
        state = DluxUpdateState.load()
        state.active_version = NEWER_VERSION
        state.active_wheel_url = ""
        state.active_wheel_sha256 = ""
        state.degraded = True
        state.degraded_reason = "previous reconcile failed"
        state.save()
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RuntimeStore(temp_dir).ensure()
            store.set_degraded("previous reconcile failed")
            with mock.patch("dlux.updater.service.download_wheel") as download:
                reconciled = UpdateService(store=store).reconcile()
            download.assert_not_called()
            active = store.read_active(__version__)
            self.assertEqual(active["source"], "image")
            self.assertEqual(active["version"], __version__)
            self.assertEqual(reconciled.active_version, __version__)
            self.assertEqual(reconciled.active_wheel_url, "")
            self.assertFalse(reconciled.degraded)
            self.assertEqual(reconciled.degraded_reason, "")
            self.assertFalse(store.degraded_file.exists())
            self.assertTrue(UpdateService(store=store).restart_worker is False)

    def test_reconcile_clears_stuck_degraded_once_back_on_baked(self):
        # A transient degrade (e.g. a one-off health-probe failure) must not wedge
        # the runtime once it is healthily serving the baked image (active == baked).
        state = DluxUpdateState.load()
        state.active_version = __version__
        state.degraded = True
        state.degraded_reason = "transient health probe failure"
        state.save()
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RuntimeStore(temp_dir).ensure()
            store.set_degraded("transient health probe failure")
            reconciled = UpdateService(store=store).reconcile()
            self.assertEqual(reconciled.active_version, __version__)
            self.assertFalse(reconciled.degraded)
            self.assertEqual(reconciled.degraded_reason, "")
            self.assertFalse(store.degraded_file.exists())

    def test_reconcile_lowers_orphaned_maintenance_flag_when_healthy_on_baked(self):
        # The production outage: a failed/interrupted update converged the app back
        # onto the healthy baked image but left state/maintenance raised, so the site
        # stayed 503'd behind the update screen with nothing running (and compose
        # down/up couldn't clear it — the flag lives in the runtime volume). reconcile
        # must lower the orphaned flag once the runtime is demonstrably healthy on
        # baked and no run/image update still owns it.
        state = DluxUpdateState.load()
        state.active_version = __version__
        state.active_run_token = ""
        state.save()
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RuntimeStore(temp_dir).ensure()
            store.set_maintenance(True, token="failed-update")
            self.assertTrue(store.maintenance_file.exists())
            reconciled = UpdateService(store=store).reconcile()
            self.assertEqual(reconciled.active_version, __version__)
            self.assertFalse(
                store.maintenance_file.exists(),
                "reconcile must lower an orphaned maintenance flag on a healthy baked runtime",
            )

    def test_reconcile_keeps_maintenance_flag_while_a_run_owns_it(self):
        # The safety net must never race an update that is legitimately mid-flight:
        # while a run still owns the flag (active_run_token set), reconcile leaves it.
        state = DluxUpdateState.load()
        state.active_version = __version__
        state.active_run_token = "in-flight-token"
        state.save()
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RuntimeStore(temp_dir).ensure()
            store.set_maintenance(True, token="in-flight-token")
            UpdateService(store=store).reconcile()
            self.assertTrue(
                store.maintenance_file.exists(),
                "reconcile must not lower a maintenance flag a run still owns",
            )

    def test_supervisor_bakes_version_from_running_code_manifest(self):
        # The supervisor must derive DLUX_BAKED_VERSION from dlux.__version__ (the
        # running code's manifest) so bind-mounted source checkouts — where the
        # installed-package metadata is absent or stale — bake the correct version.
        # importlib.metadata remains only as a fallback.
        from dlux.updater import supervisor as _supervisor_module

        source = Path(_supervisor_module.__file__).read_text(encoding="utf-8")
        self.assertIn("def baked_version", source)
        self.assertIn("from dlux import __version__", source)
        self.assertLess(
            source.index("from dlux import __version__"),
            source.index('importlib.metadata.version("django-lux")'),
        )


class ManageRuntimeReleaseTests(TestCase):
    """Every management command — collectstatic above all — must import the same
    runtime-active DjangoLux release the web process serves templates from, no
    matter how manage.py is launched. Otherwise collectstatic writes one
    version's static against another version's templates (unstyled pages, dead
    JS). manage.py resolves the release itself, before Django loads."""

    def _project(self, temp_dir, *, source, version="9.9.9"):
        """Render manage.py + supervisor into a temp project with a fake release
        whose only content is a sentinel package, so an import proves which path
        was activated without needing Django installed into the release."""
        from dlux.scaffold import _render_template

        root = Path(temp_dir)
        # manage.py imports the supervisor from the installed dlux package
        # (dlux.updater.supervisor), so no project-local supervisor file is needed.
        (root / "manage.py").write_text(
            _render_template(
                "project/manage.py.tmpl",
                {"dlux_version": "0.0.0", "project_name": "demo", "generated_date": "2026-01-01",
                 "config_package": "config"},
            ),
            encoding="utf-8",
        )
        runtime = root / "runtime"
        release = runtime / "releases" / version
        (release / "sentinel_release_pkg").mkdir(parents=True)
        (release / "sentinel_release_pkg" / "__init__.py").write_text("MARKER = 'release'\n", encoding="utf-8")
        (runtime / "state").mkdir(parents=True)
        (runtime / "state" / "active.json").write_text(
            json.dumps({"version": version, "source": source, "generation": 0}), encoding="utf-8"
        )
        return root, runtime, release

    def _run(self, root, runtime):
        script = (
            "import manage; manage._activate_runtime_release()\n"
            "try:\n"
            "    import sentinel_release_pkg as p; print('RELEASE:' + p.__file__)\n"
            "except ImportError:\n"
            "    print('BAKED')\n"
        )
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(root),
            capture_output=True,
            text=True,
            env={**os.environ, "DLUX_UPDATE_RUNTIME_ROOT": str(runtime),
                 "PYTHONPATH": os.pathsep.join([str(root), os.environ.get("PYTHONPATH", "")]).rstrip(os.pathsep)},
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return completed.stdout.strip()

    def test_volume_release_is_activated(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root, runtime, release = self._project(temp_dir, source="volume")
            output = self._run(root, runtime)
            self.assertTrue(output.startswith("RELEASE:"), output)
            self.assertIn(str(release), output)

    def test_image_source_uses_the_baked_package(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root, runtime, _ = self._project(temp_dir, source="image")
            self.assertEqual(self._run(root, runtime), "BAKED")

    def test_missing_runtime_state_falls_back_to_baked(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root, runtime, _ = self._project(temp_dir, source="volume")
            (runtime / "state" / "active.json").unlink()
            self.assertEqual(self._run(root, runtime), "BAKED")

    def test_manage_template_activates_before_importing_django(self):
        from dlux.scaffold import _render_template

        rendered = _render_template(
            "project/manage.py.tmpl",
            {"dlux_version": "1.0.0", "project_name": "demo", "generated_date": "2026-01-01",
             "config_package": "config"},
        )
        self.assertIn("_activate_runtime_release()", rendered)
        self.assertIn("from dlux.updater.supervisor import baked_version, resolve_release", rendered)
        # Resolution must precede the Django import, or the baked package is
        # already bound by the time the release is added to the path.
        self.assertLess(
            rendered.index("_activate_runtime_release()"),
            rendered.index("execute_from_command_line"),
        )


class AppVersionSourceTests(TestCase):
    """The Updates card must still report a version for a project that keeps its
    version only in release-manifest.json (no root VERSION file)."""

    def test_manifest_is_used_when_no_setting_or_version_file_exists(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "release-manifest.json").write_text(
                json.dumps({"schema_version": 1, "version": "0.1.3"}), encoding="utf-8"
            )
            with override_settings(BASE_DIR=root, DLUX_APP_VERSION=""):
                self.assertEqual(app_version(), "0.1.3")

    def test_version_file_still_wins_over_the_manifest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "VERSION").write_text("2.0.0\n", encoding="utf-8")
            (root / "release-manifest.json").write_text(
                json.dumps({"schema_version": 1, "version": "0.1.3"}), encoding="utf-8"
            )
            with override_settings(BASE_DIR=root, DLUX_APP_VERSION=""):
                self.assertEqual(app_version(), "2.0.0")

    def test_explicit_setting_wins_over_both(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "VERSION").write_text("2.0.0\n", encoding="utf-8")
            with override_settings(BASE_DIR=root, DLUX_APP_VERSION="9.9.9"):
                self.assertEqual(app_version(), "9.9.9")

    def test_missing_everything_returns_empty(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(BASE_DIR=Path(temp_dir), DLUX_APP_VERSION=""):
                self.assertEqual(app_version(), "")


class ImageAvailabilityMetadataTests(TestCase):
    @staticmethod
    def _write_availability(store, image):
        payload = {
            "available": True,
            "images": [{
                "image": "example/app:latest",
                "local_digest": "sha256:old",
                "remote_digest": "sha256:1234567890abcdef",
                "update_available": True,
                **image,
            }],
        }
        (store.state_dir / "image-available.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

    def test_manifest_version_and_notes_are_optional_display_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RuntimeStore(temp_dir).ensure()
            self._write_availability(store, {
                "version": "1.4.12",
                "manifest": {
                    "schema_version": 1,
                    "version": "2026.7",
                    "summary": "Project release",
                    "highlights": ["New report", "Faster imports"],
                },
            })

            metadata = image_update_metadata(store)

        self.assertTrue(metadata["available"])
        self.assertEqual(metadata["target"], "v2026.7")
        self.assertEqual(metadata["runtime_target"], "v1.4.12")
        self.assertEqual(metadata["manifest"]["highlights"], ["New report", "Faster imports"])

    def test_manifest_baked_dlux_version_is_display_metadata(self):
        """The candidate image's baked DjangoLux version reaches the review dialog
        without disturbing the target the completion check compares against."""
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RuntimeStore(temp_dir).ensure()
            self._write_availability(store, {
                "version": "1.4.12",
                "manifest": {
                    "schema_version": 1,
                    "version": "0.1.2",
                    "baked_dlux_version": "1.5.3",
                },
            })

            metadata = image_update_metadata(store)

        self.assertEqual(metadata["manifest"]["baked_dlux_version"], "1.5.3")
        self.assertEqual(metadata["target"], "v0.1.2")
        self.assertEqual(metadata["runtime_target"], "v1.4.12")

    def test_manifest_without_baked_dlux_version_omits_it(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RuntimeStore(temp_dir).ensure()
            self._write_availability(store, {
                "version": "1.4.12",
                "manifest": {"schema_version": 1, "version": "0.1.2"},
            })

            metadata = image_update_metadata(store)

        self.assertNotIn("baked_dlux_version", metadata["manifest"])

    def test_invalid_manifest_falls_back_to_version_then_digest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RuntimeStore(temp_dir).ensure()
            self._write_availability(store, {
                "version": "1.4.12",
                "manifest": {"schema_version": 2, "version": "ignored"},
            })
            version_metadata = image_update_metadata(store)
            self._write_availability(store, {})
            digest_metadata = image_update_metadata(store)

        self.assertEqual(version_metadata["target"], "v1.4.12")
        self.assertEqual(version_metadata["manifest"], {})
        self.assertEqual(digest_metadata["target"], "sha256:1234567890ab")
        self.assertEqual(digest_metadata["runtime_target"], "sha256:1234567890ab")


@override_settings(DLUX_INLINE_UPDATES_ENABLED=True)
class UpdateAdmissionTests(TestCase):
    @staticmethod
    def _write_availability(root):
        store = RuntimeStore(root).ensure()
        (store.state_dir / "image-available.json").write_text(
            json.dumps({
                "available": True,
                "images": [{
                    "image": "example/app:latest",
                    "local_digest": "sha256:old",
                    "remote_digest": "sha256:new",
                    "update_available": True,
                    "version": "9.1.0",
                }],
            }),
            encoding="utf-8",
        )

    def setUp(self):
        DluxUpdateState.load()

    def test_image_update_rejects_an_active_inline_run(self):
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(
            DLUX_UPDATE_RUNTIME_ROOT=temp_dir,
        ):
            self._write_availability(temp_dir)
            queue_run(DluxUpdateRun.ACTION_CHECK, "inline-admin")

            with self.assertRaisesRegex(UpdaterError, "inline DjangoLux update"):
                queue_image_update("image-admin")

        self.assertFalse(DluxImageUpdate.objects.exists())

    def test_inline_run_rejects_an_active_image_update(self):
        DluxImageUpdate.objects.create(requested_by_username="image-admin")

        with self.assertRaisesRegex(UpdaterError, "image update"):
            queue_run(DluxUpdateRun.ACTION_CHECK, "inline-admin")

        self.assertFalse(DluxUpdateRun.objects.exists())

    def test_second_image_update_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(
            DLUX_UPDATE_RUNTIME_ROOT=temp_dir,
        ):
            self._write_availability(temp_dir)
            first = queue_image_update("first-admin")

            with self.assertRaisesRegex(UpdaterError, "image update"):
                queue_image_update("second-admin")

        self.assertEqual(DluxImageUpdate.objects.get(), first)

    def test_terminal_image_update_does_not_block_inline_admission(self):
        DluxImageUpdate.objects.create(
            status=DluxImageUpdate.STATUS_COMPLETED,
            is_active=False,
            requested_by_username="image-admin",
        )

        run = queue_run(DluxUpdateRun.ACTION_CHECK, "inline-admin")

        self.assertTrue(run.is_active)

    def test_previous_release_insert_uses_agent_field_database_defaults(self):
        table = connection.ops.quote_name(DluxImageUpdate._meta.db_table)
        now = timezone.now()
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {table} (
                    token, status, is_active, source_version, target_version,
                    requested_by_username, backup_mode, backup_token, progress_log,
                    error, created_at, handoff_at, completed_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    "legacy-image-token",
                    DluxImageUpdate.STATUS_PENDING,
                    True,
                    "1.4.15",
                    "1.5.0",
                    "legacy-admin",
                    DluxImageUpdate.BACKUP_DATA,
                    "",
                    "",
                    "",
                    now,
                    None,
                    None,
                ],
            )

        row = DluxImageUpdate.objects.get(token="legacy-image-token")
        self.assertIsNone(row.control_operation_id)
        self.assertEqual(row.request_source, "local")


@override_settings(DLUX_INLINE_UPDATES_ENABLED=True)
class UpdateAdmissionConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(
            DLUX_UPDATE_RUNTIME_ROOT=self.temp_dir.name,
        )
        self.settings_override.enable()
        DluxUpdateState.load()
        UpdateAdmissionTests._write_availability(self.temp_dir.name)

    def tearDown(self):
        self.settings_override.disable()
        self.temp_dir.cleanup()

    @staticmethod
    def _run_concurrently(*operations):
        barrier = threading.Barrier(len(operations))
        outcomes = []

        def submit(operation):
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                operation()
                outcomes.append("accepted")
            except UpdaterError:
                outcomes.append("rejected")
            except Exception as exc:
                outcomes.append(exc)
            finally:
                close_old_connections()

        threads = [threading.Thread(target=submit, args=(operation,)) for operation in operations]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        return outcomes

    @skipUnlessDBFeature("has_select_for_update")
    def test_state_row_lock_serializes_two_image_requests(self):
        outcomes = self._run_concurrently(
            lambda: queue_image_update("first-admin"),
            lambda: queue_image_update("second-admin"),
        )

        self.assertCountEqual(outcomes, ["accepted", "rejected"])
        self.assertEqual(DluxImageUpdate.objects.count(), 1)

    @skipUnlessDBFeature("has_select_for_update")
    def test_state_row_lock_serializes_inline_and_image_requests(self):
        outcomes = self._run_concurrently(
            lambda: queue_run(DluxUpdateRun.ACTION_CHECK, "inline-admin"),
            lambda: queue_image_update("image-admin"),
        )

        self.assertCountEqual(outcomes, ["accepted", "rejected"])
        self.assertEqual(DluxUpdateRun.objects.count() + DluxImageUpdate.objects.count(), 1)


class ImageUpdateHandoffTests(TestCase):
    def _awaiting_row(self):
        return DluxImageUpdate.objects.create(
            status=DluxImageUpdate.STATUS_AWAITING_RECREATE,
            handoff_at=timezone.now() - timedelta(seconds=5),
            target_version="",
        )

    @staticmethod
    def _write_ack(store, row, exit_code, *, token=None):
        payload = {
            "token": token if token is not None else row.token,
            "exit_code": exit_code,
            "finished_at": timezone.now().isoformat(),
        }
        ack_path(store).write_text(json.dumps(payload) + "\n", encoding="utf-8")

    def test_failed_token_matched_ack_clears_maintenance_without_status_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RuntimeStore(temp_dir).ensure()
            row = self._awaiting_row()
            store.set_maintenance(True, token=row.token)
            self._write_ack(store, row, 1)

            UpdateService(store=store)._finalize_image_update(row)

            row.refresh_from_db()
            self.assertEqual(row.status, row.STATUS_FAILED)
            self.assertFalse(row.is_active)
            self.assertIn("exited with status 1", row.error)
            self.assertFalse(store.maintenance_file.exists())
            self.assertEqual(read_composer_ack(store)["token"], row.token)

    def test_successful_token_matched_ack_completes_without_status_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RuntimeStore(temp_dir).ensure()
            row = self._awaiting_row()
            store.set_maintenance(True, token=row.token)
            self._write_ack(store, row, 0)

            UpdateService(store=store)._finalize_image_update(row)

            row.refresh_from_db()
            self.assertEqual(row.status, row.STATUS_COMPLETED)
            self.assertFalse(row.is_active)
            self.assertFalse(store.maintenance_file.exists())

    def test_ack_for_an_older_request_cannot_finalize_current_handoff(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RuntimeStore(temp_dir).ensure()
            row = self._awaiting_row()
            store.set_maintenance(True, token=row.token)
            self._write_ack(store, row, 1, token="older-request")

            UpdateService(store=store)._finalize_image_update(row)

            row.refresh_from_db()
            self.assertEqual(row.status, row.STATUS_AWAITING_RECREATE)
            self.assertTrue(row.is_active)
            self.assertTrue(store.maintenance_file.exists())

    def test_fresh_failed_status_clears_maintenance_with_detailed_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RuntimeStore(temp_dir).ensure()
            row = self._awaiting_row()
            store.set_maintenance(True, token=row.token)
            status_path(store).write_text(
                json.dumps({
                    "status": "failed",
                    "updated_at": timezone.now().isoformat(),
                    "request_token": row.token,
                    "error": "Composer could not create its runtime override.",
                }) + "\n",
                encoding="utf-8",
            )

            UpdateService(store=store)._finalize_image_update(row)

            row.refresh_from_db()
            self.assertEqual(row.status, row.STATUS_FAILED)
            self.assertEqual(row.error, "Composer could not create its runtime override.")
            self.assertFalse(store.maintenance_file.exists())

    def test_undated_status_cannot_finalize_a_new_handoff(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RuntimeStore(temp_dir).ensure()
            row = self._awaiting_row()
            store.set_maintenance(True, token=row.token)
            status_path(store).write_text(
                json.dumps({"status": "failed", "error": "stale failure"}) + "\n",
                encoding="utf-8",
            )

            UpdateService(store=store)._finalize_image_update(row)

            row.refresh_from_db()
            self.assertEqual(row.status, row.STATUS_AWAITING_RECREATE)
            self.assertTrue(row.is_active)
            self.assertTrue(store.maintenance_file.exists())

    def test_unacknowledged_handoff_fails_before_full_deploy_timeout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RuntimeStore(temp_dir).ensure()
            row = self._awaiting_row()
            row.handoff_at = timezone.now() - timedelta(seconds=121)
            row.save(update_fields=["handoff_at"])
            store.set_maintenance(True, token=row.token)

            UpdateService(store=store)._finalize_image_update(row)

            row.refresh_from_db()
            self.assertEqual(row.status, row.STATUS_FAILED)
            self.assertIn("did not acknowledge", row.error)
            self.assertFalse(store.maintenance_file.exists())


class AutoUpdateCheckSchedulingTests(TestCase):
    """The background daily check is driven both by the isolated worker loop and,
    reliably, by a Celery-beat task. Both funnel through queue_daily_check_if_due,
    which must gate on enablement, an in-flight run, and the persisted interval."""

    def setUp(self):
        DluxUpdateState.load()

    def _checks(self):
        return DluxUpdateRun.objects.filter(action=DluxUpdateRun.ACTION_CHECK)

    @override_settings(DLUX_INLINE_UPDATES_ENABLED=False)
    def test_disabled_never_queues(self):
        self.assertIsNone(queue_daily_check_if_due())
        self.assertEqual(self._checks().count(), 0)

    @override_settings(DLUX_INLINE_UPDATES_ENABLED=True)
    def test_first_run_queues_a_check(self):
        run = queue_daily_check_if_due()
        self.assertIsNotNone(run)
        self.assertEqual(run.action, DluxUpdateRun.ACTION_CHECK)
        self.assertEqual(run.requested_by_username, "system")
        self.assertEqual(self._checks().count(), 1)

    @override_settings(DLUX_INLINE_UPDATES_ENABLED=True, DLUX_UPDATE_CHECK_INTERVAL=86400)
    def test_recent_check_is_not_re_queued(self):
        state = DluxUpdateState.load()
        state.last_checked_at = timezone.now() - timedelta(hours=1)
        state.save()
        self.assertIsNone(queue_daily_check_if_due())
        self.assertEqual(self._checks().count(), 0)

    @override_settings(DLUX_INLINE_UPDATES_ENABLED=True, DLUX_UPDATE_CHECK_INTERVAL=86400)
    def test_stale_check_is_re_queued(self):
        state = DluxUpdateState.load()
        state.last_checked_at = timezone.now() - timedelta(days=2)
        state.save()
        self.assertIsNotNone(queue_daily_check_if_due())
        self.assertEqual(self._checks().count(), 1)

    @override_settings(DLUX_INLINE_UPDATES_ENABLED=True)
    def test_active_run_blocks_a_new_check(self):
        state = DluxUpdateState.load()
        state.active_run_token = "busy-token"
        state.save()
        self.assertIsNone(queue_daily_check_if_due())
        self.assertEqual(self._checks().count(), 0)

    def test_beat_schedule_registers_the_update_check(self):
        from dlux.utils.settings import dlux_settings

        scope = {}
        dlux_settings(scope)
        entry = scope["CELERY_BEAT_SCHEDULE"]["dlux-update-check"]
        self.assertEqual(entry["task"], "dlux.tasks.dlux_update_check")
        self.assertGreater(entry["schedule"], 0)

    @override_settings(DLUX_INLINE_UPDATES_ENABLED=True)
    def test_beat_task_enqueues_a_check(self):
        from dlux.tasks import dlux_update_check_task

        if dlux_update_check_task is None:
            self.skipTest("Celery is not installed in this environment.")
        dlux_update_check_task()
        self.assertEqual(self._checks().count(), 1)


@override_settings(DLUX_INLINE_UPDATES_ENABLED=True)
class UpdaterApiTests(TestCase):
    def setUp(self):
        self.password = "super-password-123"
        self.user = get_user_model().objects.create_superuser(
            username="updater-admin", email="admin@example.com", password=self.password,
        )
        self.client = Client()
        self.client.login(username=self.user.username, password=self.password)
        system_settings = SystemSettings.load()
        system_settings.is_configured = True
        system_settings.save()
        DluxUpdateState.load()

    def test_previous_apply_failure_flags_failed_version_until_it_succeeds(self):
        from dlux.updater.service import previous_apply_failure
        Run = DluxUpdateRun
        self.assertIsNone(previous_apply_failure("1.4.7"))
        Run.objects.create(
            action=Run.ACTION_APPLY, target_version="1.4.7",
            status=Run.STATUS_ROLLED_BACK, error="health check failed",
        )
        failure = previous_apply_failure("1.4.7")
        self.assertIsNotNone(failure)
        self.assertEqual(failure["version"], "1.4.7")
        self.assertEqual(failure["status"], "rolled_back")
        self.assertIn("health check", failure["error"])
        # A later successful apply of the same version clears the warning.
        Run.objects.create(action=Run.ACTION_APPLY, target_version="1.4.7", status=Run.STATUS_COMPLETED)
        self.assertIsNone(previous_apply_failure("1.4.7"))
        # An unrelated version is unaffected.
        self.assertIsNone(previous_apply_failure("1.4.9"))

    def test_state_endpoint_surfaces_latest_version_failure(self):
        state = DluxUpdateState.load()
        state.latest_version = "1.4.7"
        state.save()
        DluxUpdateRun.objects.create(
            action=DluxUpdateRun.ACTION_APPLY, target_version="1.4.7",
            status=DluxUpdateRun.STATUS_ROLLED_BACK, error="health check failed",
        )
        response = self.client.get(reverse("dlux_update_state"))
        self.assertEqual(response.status_code, 200)
        failure = json.loads(response.content)["state"]["latest_version_failure"]
        self.assertIsNotNone(failure)
        self.assertEqual(failure["version"], "1.4.7")

    @mock.patch("dlux.views.updater.image_update_metadata")
    def test_state_endpoint_surfaces_optional_project_image_manifest(self, metadata):
        metadata.return_value = {
            "available": True,
            "target": "v2026.7",
            "runtime_target": "v1.4.12",
            "reason": "A new application image is available.",
            "manifest": {
                "schema_version": 1,
                "version": "2026.7",
                "highlights": ["New report"],
            },
        }

        response = self.client.get(reverse("dlux_update_state"))

        self.assertEqual(response.status_code, 200)
        state = response.json()["state"]
        self.assertEqual(state["image_update_target"], "v2026.7")
        self.assertEqual(state["image_update_manifest"]["highlights"], ["New report"])

    def test_skip_endpoint_adds_removes_and_clears_offered_latest(self):
        state = DluxUpdateState.load()
        state.active_version = "1.4.6"
        state.latest_version = "1.4.7"
        state.latest_compatible = True
        state.save()
        # Skip the currently-offered version.
        resp = self.client.post(reverse("dlux_update_skip"), {"version": "1.4.7"})
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.content)["state"]
        self.assertEqual(body["skipped_versions"], ["1.4.7"])
        self.assertEqual(body["latest_version"], "1.4.6")  # no longer offered
        self.assertFalse(body["latest_compatible"])
        # Un-skip.
        resp = self.client.post(reverse("dlux_update_skip"), {"version": "1.4.7", "unskip": "true"})
        self.assertEqual(json.loads(resp.content)["state"]["skipped_versions"], [])

    def test_skip_endpoint_requires_superuser(self):
        other = get_user_model().objects.create_user(username="plain", password="pw12345678")
        client = Client()
        client.force_login(other)
        self.assertEqual(
            client.post(reverse("dlux_update_skip"), {"version": "1.4.7"}).status_code, 403
        )

    def test_check_excludes_skipped_versions(self):
        from dlux.updater.manifest import select_latest_candidate

        def wheel(v):
            return {
                "filename": f"django_lux-{v}-py3-none-any.whl",
                "hashes": {"sha256": "a" * 64},
                "url": f"https://files.pythonhosted.org/packages/x/django_lux-{v}-py3-none-any.whl",
                "requires-python": "",
            }
        index = {"files": [wheel("1.4.7"), wheel("1.4.8")]}
        self.assertEqual(select_latest_candidate(index, "1.4.6").version, "1.4.8")
        self.assertEqual(
            select_latest_candidate(index, "1.4.6", skip_versions=["1.4.8"]).version, "1.4.7"
        )
        self.assertIsNone(
            select_latest_candidate(index, "1.4.6", skip_versions=["1.4.7", "v1.4.8"])
        )

    def test_selection_jumps_directly_over_an_image_required_release(self):
        # Selection returns the single highest candidate, so a box on 1.6.8 is
        # offered 1.7.1 directly even when the image-required 1.7.0 sits between
        # them (whether or not 1.7.0 was skipped). This is exactly why the
        # per-wheel inline floor below is required.
        def wheel(v):
            return {
                "filename": f"django_lux-{v}-py3-none-any.whl",
                "hashes": {"sha256": "a" * 64},
                "url": f"https://files.pythonhosted.org/packages/x/django_lux-{v}-py3-none-any.whl",
                "requires-python": "",
            }
        index = {"files": [wheel("1.7.0"), wheel("1.7.1")]}
        self.assertEqual(select_latest_candidate(index, "1.6.8").version, "1.7.1")
        self.assertEqual(
            select_latest_candidate(index, "1.6.8", skip_versions=["1.7.0"]).version, "1.7.1"
        )

    def test_runtime_health_requires_internal_probe_and_reports_version(self):
        self.assertEqual(Client().get(reverse("dlux_update_runtime_health")).status_code, 404)
        from django.conf import settings

        response = Client().get(
            reverse("dlux_update_runtime_health"),
            HTTP_X_DLUX_UPDATER_PROBE=runtime_probe_token(settings.SECRET_KEY),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["version"], __version__)

    def test_health_verification_retries_until_celery_worker_and_version_are_ready(self):
        # Pass an explicit temp store (like every other updater test) so construction
        # never depends on the default /opt/dlux-runtime path existing/being writable.
        service = UpdateService(store=RuntimeStore(tempfile.mkdtemp()).ensure(), command_runner=mock.Mock(side_effect=[
            SimpleNamespace(returncode=1, stdout="", stderr="No nodes replied"),
            SimpleNamespace(returncode=0, stdout="celery@worker: OK\n    pong", stderr=""),
            SimpleNamespace(returncode=1, stdout="", stderr="old version"),
            SimpleNamespace(returncode=0, stdout="celery@worker: OK\n    pong", stderr=""),
            SimpleNamespace(returncode=0, stdout="", stderr=""),
        ]))
        url_responses = [
            FakeResponse(b"ok", url="http://web:8000/health/"),
            FakeResponse(json.dumps({"version": NEWER_VERSION}).encode("utf-8"), url="http://web:8000/sys/api/dlux-update/runtime-health/"),
        ]
        with mock.patch("dlux.updater.service.urllib.request.urlopen", side_effect=url_responses), \
             mock.patch("dlux.updater.service.time.sleep"):
            service._verify_health(NEWER_VERSION, os.environ.copy())

        self.assertEqual(service.command_runner.call_count, 5)

    def test_mutations_are_superuser_only_and_csrf_protected(self):
        regular = get_user_model().objects.create_user(username="regular", password="regular-pass-123")
        other = Client()
        other.login(username=regular.username, password="regular-pass-123")
        self.assertEqual(other.post(reverse("dlux_update_check")).status_code, 403)

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.login(username=self.user.username, password=self.password)
        self.assertEqual(csrf_client.post(reverse("dlux_update_check")).status_code, 403)

    def test_manual_check_is_queued_and_recent_result_is_cached(self):
        response = self.client.post(reverse("dlux_update_check"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["run"]["action"], "check")
        self.assertTrue(ActivityLog.objects.filter(action="DLUX_UPDATE_CHECK").exists())
        run = DluxUpdateRun.objects.get(token=response.json()["run"]["token"])
        run.finish(run.STATUS_COMPLETED)
        run.save()
        state = DluxUpdateState.load()
        state.active_run_token = ""
        state.last_checked_at = timezone.now()
        state.save()
        cached = self.client.post(reverse("dlux_update_check"))
        self.assertTrue(cached.json()["cached"])
        self.assertIsNone(cached.json()["run"])

    def test_apply_and_rollback_require_current_password(self):
        state = DluxUpdateState.load()
        state.latest_version = "1.2.3"
        state.latest_compatible = True
        state.previous_version = "1.2.1"
        state.save()
        bad = self.client.post(
            reverse("dlux_update_apply"),
            {"current_password": "wrong"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(bad.status_code, 400)
        good = self.client.post(
            reverse("dlux_update_apply"),
            {"current_password": self.password},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(good.status_code, 200)
        self.assertEqual(good.json()["run"]["target_version"], "1.2.3")

    def test_singleton_lock_serializes_operations(self):
        queue_run(DluxUpdateRun.ACTION_CHECK, self.user.username)
        with self.assertRaises(UpdaterError):
            queue_run(DluxUpdateRun.ACTION_CHECK, self.user.username)

    def test_system_info_renders_superuser_controls_and_global_staff_read_only_state(self):
        response = self.client.get(reverse("options_view"))
        self.assertContains(response, "data-dlux-updater")
        self.assertContains(response, "data-dlux-update-check>")
        self.assertContains(response, "data-dlux-update-recheck")
        self.assertContains(response, "Re-check for newer release")
        self.assertContains(response, "dluxUpdateReviewModal")
        self.assertContains(response, "data-dlux-update-progress-panel")
        self.assertContains(response, 'name="current_password" autocomplete="off"')

        global_staff = get_user_model().objects.create_user(
            username="global-updater-reader",
            password="global-reader-pass-123",
            is_staff=True,
        )
        permission = Permission.objects.get(
            content_type=ContentType.objects.get(app_label="dlux", model="profile"),
            codename="manage_scopes",
        )
        global_staff.user_permissions.add(permission)
        staff_client = Client()
        staff_client.login(username=global_staff.username, password="global-reader-pass-123")
        state_response = staff_client.get(reverse("dlux_update_state"))
        self.assertEqual(state_response.status_code, 200)
        self.assertFalse(state_response.json()["state"]["can_manage"])
        options_response = staff_client.get(reverse("options_view"))
        self.assertContains(options_response, "data-dlux-updater")
        self.assertNotContains(options_response, "data-dlux-update-check>")
        self.assertNotContains(options_response, "data-dlux-update-recheck")
        script = Path(__file__).resolve().parents[1] / "static" / "dlux" / "system" / "js" / "updater.js"
        contents = script.read_text(encoding="utf-8")
        self.assertIn("if (payload.state?.can_manage)", contents)
        self.assertIn("pollReadOnlyState", contents)
        self.assertIn("const PROGRESS", contents)
        self.assertIn("showProgress(run)", contents)
        self.assertIn("run.token === trackedRunToken", contents)
        self.assertIn("modalRecheckButton", contents)
        self.assertIn("reopenReviewAfterCheck", contents)
        self.assertIn("state.image_update_manifest || null", contents)
        self.assertIn("allowSummaryFallback", contents)
        # The Check button spins via the shared loading-button helper and a
        # successful run shows a green "Finish" affordance (the old misleading
        # "Update completed" root-status line was removed).
        self.assertIn("startCheckSpinner(button)", contents)
        self.assertIn("root.dataset.labelFinish", contents)
        self.assertNotIn("setRootStatus(message, 5000)", contents)
        self.assertNotIn("modal.hide()", contents)

    # Exercises the in-container PyPI check, kept until 1.9.0; the 1.8.0 default
    # reads what Composer published instead.
    @override_settings(DLUX_UPDATE_EXECUTOR="inline")
    @mock.patch("dlux.updater.service.assess_wheel")
    @mock.patch("dlux.updater.service.verify_pypi_attestation")
    @mock.patch("dlux.updater.service.download_wheel")
    @mock.patch("dlux.updater.service.select_latest_candidate")
    @mock.patch("dlux.updater.service.fetch_simple_index", return_value={"files": []})
    def test_check_run_persists_verified_candidate(self, _fetch, select, download, verify, assess):
        candidate = ReleaseCandidate(
            "1.2.3", "django_lux-1.2.3-py3-none-any.whl",
            "https://files.pythonhosted.org/a.whl", "a" * 64,
        )
        select.return_value = candidate
        download.return_value = Path("candidate.whl")
        assess.return_value = {
            "compatible": True,
            "reason": "",
            "manifest": release_manifest(),
        }
        run = queue_run(DluxUpdateRun.ACTION_CHECK, self.user.username)
        with tempfile.TemporaryDirectory() as temp_dir:
            UpdateService(store=RuntimeStore(temp_dir).ensure()).process_next()
        run.refresh_from_db()
        state = DluxUpdateState.load()
        self.assertEqual(run.status, run.STATUS_COMPLETED)
        self.assertEqual(state.latest_version, "1.2.3")
        self.assertTrue(state.latest_compatible)
        verify.assert_called_once_with(candidate)

    def _publish_availability(self, store, payload):
        from dlux.updater import package_request

        package_request.availability_path(store).write_text(
            json.dumps(payload), encoding="utf-8")

    def _run_composer_check(self, payload=None):
        """Drain one CHECK run on the 1.8.0 default path."""
        run = queue_run(DluxUpdateRun.ACTION_CHECK, self.user.username)
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RuntimeStore(temp_dir).ensure()
            if payload is not None:
                self._publish_availability(store, payload)
            UpdateService(store=store).process_next()
        run.refresh_from_db()
        return run, DluxUpdateState.load()

    def test_the_default_check_reaches_no_network_at_all(self):
        """1.8.0 reads Composer's report; PyPI is Composer's problem now."""
        with mock.patch("dlux.updater.service.fetch_simple_index") as fetch:
            run, _state = self._run_composer_check({
                "available": True, "version": NEWER_VERSION, "inline_safe": True, "reason": "",
            })

        fetch.assert_not_called()
        self.assertEqual(run.status, run.STATUS_COMPLETED)

    def test_an_available_inline_safe_release_is_offered(self):
        _run, state = self._run_composer_check({
            "available": True, "version": NEWER_VERSION, "inline_safe": True, "reason": "",
        })

        self.assertEqual(state.latest_version, NEWER_VERSION)
        self.assertTrue(state.latest_compatible)
        self.assertEqual(state.last_check_error, "")

    def test_nothing_published_is_reported_as_unknown_not_up_to_date(self):
        """The dangerous failure: silently telling an operator they are current."""
        _run, state = self._run_composer_check(None)

        self.assertFalse(state.latest_compatible)
        self.assertIn("has not reported", state.last_check_error)
        self.assertIsNotNone(state.last_checked_at)

    def test_a_composer_side_failure_surfaces_as_a_check_error(self):
        _run, state = self._run_composer_check({
            "available": False, "version": "", "inline_safe": False,
            "error": "The wheel's PyPI Trusted Publisher attestation is invalid.",
        })

        self.assertFalse(state.latest_compatible)
        self.assertIn("attestation is invalid", state.last_check_error)

    def test_a_release_needing_an_image_rebuild_is_not_offered_inline(self):
        _run, state = self._run_composer_check({
            "available": True, "version": NEWER_VERSION, "inline_safe": False,
            "reason": f"DjangoLux {NEWER_VERSION} requires a project image rebuild.",
        })

        self.assertEqual(state.latest_version, NEWER_VERSION)
        self.assertFalse(state.latest_compatible)
        self.assertIn("image rebuild", state.latest_reason)

    def test_a_skipped_version_is_not_offered_again(self):
        state = DluxUpdateState.load()
        state.skipped_versions = [NEWER_VERSION]
        state.save()

        _run, state = self._run_composer_check({
            "available": True, "version": NEWER_VERSION, "inline_safe": True, "reason": "",
        })

        self.assertFalse(state.latest_compatible)
        self.assertIn("skipped", state.latest_reason)

    def test_an_older_published_version_leaves_the_deployment_up_to_date(self):
        _run, state = self._run_composer_check({
            "available": True, "version": "0.0.1", "inline_safe": True, "reason": "",
        })

        self.assertFalse(state.latest_compatible)
        self.assertIn("up to date", state.latest_reason)

    def test_queueing_is_refused_when_the_runtime_volume_is_unusable(self):
        """Otherwise the run sits at 'queued' forever — nothing can drain it."""
        import os
        import stat

        if os.geteuid() == 0:
            self.skipTest("root can write anywhere; the probe cannot be exercised")
        with tempfile.TemporaryDirectory() as temp_dir:
            locked = Path(temp_dir) / "locked"
            locked.mkdir()
            os.chmod(locked, stat.S_IRUSR | stat.S_IXUSR)
            try:
                with override_settings(DLUX_UPDATE_RUNTIME_ROOT=str(locked / "runtime")):
                    with self.assertRaisesRegex(UpdaterError, "not writable"):
                        queue_run(DluxUpdateRun.ACTION_CHECK, self.user.username)
            finally:
                # Restore before TemporaryDirectory tries to remove the tree.
                os.chmod(locked, 0o700)

            self.assertEqual(DluxUpdateRun.objects.count(), 0)

    def test_status_contract_contains_full_apply_pipeline(self):
        expected = [
            "queued", "downloading", "verifying", "staging", "preflight", "backing_up",
            "maintenance", "migrating", "collecting_static", "switching", "restarting",
            "verifying_health", "completed", "failed", "rolled_back",
        ]
        available = {value for value, _label in DluxUpdateRun.STATUS_CHOICES}
        self.assertTrue(set(expected).issubset(available))

    @mock.patch("dlux.updater.service.download_wheel", side_effect=UpdaterError("PyPI unavailable"))
    def test_empty_volume_reconstruction_failure_stays_degraded_and_preserves_record(self, _download):
        # Active version must be strictly newer than the baked __version__ so the
        # empty-volume path tries (and fails) to reconstruct from the wheel rather
        # than falling back to the baked image.
        state = DluxUpdateState.load()
        state.active_version = NEWER_VERSION
        state.active_wheel_url = f"https://files.pythonhosted.org/django_lux-{NEWER_VERSION}-py3-none-any.whl"
        state.active_wheel_sha256 = "a" * 64
        state.save()
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RuntimeStore(temp_dir).ensure()
            reconciled = UpdateService(store=store).reconcile()
            self.assertTrue(reconciled.degraded)
            self.assertEqual(reconciled.active_version, NEWER_VERSION)
            self.assertTrue(store.degraded_file.exists())
            with mock.patch.dict(os.environ, {"DLUX_UPDATE_RUNTIME_ROOT": temp_dir}):
                from dlux.updater.health import main as updater_health

                self.assertEqual(updater_health(), 1)

    def _apply_with_mocks(self, temp_dir, *, health_effect=None, manage_effect=None):
        state = DluxUpdateState.load()
        candidate = ReleaseCandidate(
            NEWER_VERSION, f"django_lux-{NEWER_VERSION}-py3-none-any.whl",
            f"https://files.pythonhosted.org/django_lux-{NEWER_VERSION}-py3-none-any.whl", "a" * 64,
        )
        manifest = release_manifest(version=NEWER_VERSION)
        state.latest_version = candidate.version
        state.latest_wheel_url = candidate.url
        state.latest_wheel_sha256 = candidate.sha256
        state.latest_manifest = manifest
        state.latest_compatible = True
        state.save()
        run = queue_run(DluxUpdateRun.ACTION_APPLY, self.user.username)
        store = RuntimeStore(temp_dir).ensure()
        service = UpdateService(store=store)

        def install(_wheel, target, **kwargs):
            Path(target).mkdir(parents=True)
            return Path(target)

        with mock.patch("dlux.updater.service.fetch_simple_index", return_value={}), \
             mock.patch("dlux.updater.service.select_latest_candidate", return_value=candidate), \
             mock.patch("dlux.updater.service.download_wheel", return_value=Path("candidate.whl")), \
             mock.patch("dlux.updater.service.verify_pypi_attestation"), \
             mock.patch("dlux.updater.service.assess_wheel", return_value={
                 "compatible": True, "reason": "", "manifest": manifest,
             }), \
             mock.patch.object(RuntimeStore, "install_wheel", side_effect=install), \
             mock.patch.object(service, "_create_backup", return_value=SimpleNamespace(token="backup-token")), \
             mock.patch.object(service, "_run_manage", side_effect=manage_effect), \
             mock.patch.object(service, "_verify_health", side_effect=health_effect):
            service.process_next()
        run.refresh_from_db()
        state.refresh_from_db()
        return run, state, store

    # Exercises the in-container executor, kept until 1.9.0 behind this setting;
    # the 1.8.0 default hands the operation to Composer instead.
    @override_settings(DLUX_UPDATE_EXECUTOR="inline")
    def test_safe_apply_switches_release_and_preserves_previous(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run, state, store = self._apply_with_mocks(temp_dir)
            self.assertEqual(run.status, run.STATUS_COMPLETED)
            self.assertEqual(state.active_version, NEWER_VERSION)
            self.assertEqual(state.previous_version, __version__)
            self.assertEqual(store.read_active(__version__)["version"], NEWER_VERSION)
            self.assertFalse(store.maintenance_file.exists())

    # Exercises the in-container executor, kept until 1.9.0 behind this setting;
    # the 1.8.0 default hands the operation to Composer instead.
    @override_settings(DLUX_UPDATE_EXECUTOR="inline")
    def test_successful_apply_notifies_admins(self):
        from django.core.cache import cache
        from dlux.models import DluxNotification, DluxNotificationState
        # Fresh config cache so notifications resolve to the enabled default
        # (a prior test in the suite may have cached a disabled config).
        cache.clear()
        # A second superuser + a regular user: only the superusers get notified.
        admin2 = get_user_model().objects.create_superuser(
            username="admin2", email="a2@example.com", password="admin2-pass-123",
        )
        regular = get_user_model().objects.create_user(username="reg-upd", password="reg-pass-123")
        with tempfile.TemporaryDirectory() as temp_dir:
            run, state, store = self._apply_with_mocks(temp_dir)
            self.assertEqual(run.status, run.STATUS_COMPLETED)
        note = DluxNotification.objects.filter(action="dlux_update_applied").order_by("-id").first()
        self.assertIsNotNone(note, "an app-updated notification should be created")
        self.assertIn(NEWER_VERSION, note.message)
        notified = set(
            DluxNotificationState.objects.filter(notification=note).values_list("user_id", flat=True)
        )
        self.assertIn(self.user.id, notified)
        self.assertIn(admin2.id, notified)
        self.assertNotIn(regular.id, notified)

    # Exercises the in-container executor, kept until 1.9.0 behind this setting;
    # the 1.8.0 default hands the operation to Composer instead.
    @override_settings(DLUX_UPDATE_EXECUTOR="inline")
    def test_post_switch_health_failure_automatically_restores_previous(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run, state, store = self._apply_with_mocks(
                temp_dir,
                health_effect=[UpdaterError("candidate unhealthy"), None],
            )
            self.assertEqual(run.status, run.STATUS_ROLLED_BACK)
            self.assertEqual(state.active_version, __version__)
            self.assertEqual(store.read_active(__version__)["version"], __version__)
            self.assertTrue(store.release_path(NEWER_VERSION).is_dir())

    def test_required_update_backup_is_marked_as_update_trigger(self):
        run = DluxUpdateRun.objects.create(
            action=DluxUpdateRun.ACTION_APPLY,
            requested_by_username=self.user.username,
        )
        service = UpdateService(store=RuntimeStore(tempfile.mkdtemp()).ensure())

        def complete_backup(pk):
            SystemBackup.objects.filter(pk=pk).update(status=SystemBackup.STATUS_COMPLETED)

        with mock.patch('dlux.backup.run_system_backup', side_effect=complete_backup):
            backup = service._create_backup(run)

        self.assertEqual(backup.trigger, SystemBackup.TRIGGER_UPDATE)
        self.assertEqual(backup.requested_by_username, self.user.username)
        # Default mode is quick/data-only (no media copy) so a quick update is fast;
        # the runner reads this off the row, so it survives a Celery handoff.
        self.assertFalse(backup.media_included)

    def test_create_backup_honors_backup_mode_skip_quick_full(self):
        service = UpdateService(store=RuntimeStore(tempfile.mkdtemp()).ensure())

        def complete_backup(pk):
            SystemBackup.objects.filter(pk=pk).update(status=SystemBackup.STATUS_COMPLETED)

        with mock.patch('dlux.backup.run_system_backup', side_effect=complete_backup):
            skip_run = DluxUpdateRun.objects.create(
                action=DluxUpdateRun.ACTION_APPLY, backup_mode=DluxUpdateRun.BACKUP_SKIP,
            )
            self.assertIsNone(service._create_backup(skip_run))
            self.assertFalse(SystemBackup.objects.exists())

            quick_run = DluxUpdateRun.objects.create(
                action=DluxUpdateRun.ACTION_APPLY, backup_mode=DluxUpdateRun.BACKUP_DATA,
            )
            quick = service._create_backup(quick_run)
            self.assertFalse(quick.media_included)

            full_run = DluxUpdateRun.objects.create(
                action=DluxUpdateRun.ACTION_APPLY, backup_mode=DluxUpdateRun.BACKUP_FULL,
            )
            full = service._create_backup(full_run)
            self.assertTrue(full.media_included)

    def test_apply_view_persists_backup_mode_choice(self):
        state = DluxUpdateState.load()
        state.latest_version = NEWER_VERSION
        state.latest_compatible = True
        state.save()
        with mock.patch('dlux.views.updater.require_current_password', return_value=None):
            response = self.client.post(reverse('dlux_update_apply'), {'backup_mode': 'skip'})
        self.assertEqual(response.status_code, 200)
        run = DluxUpdateRun.objects.get(token=response.json()['run']['token'])
        self.assertEqual(run.backup_mode, DluxUpdateRun.BACKUP_SKIP)

    def test_failed_preflight_never_switches_active_release(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run, state, store = self._apply_with_mocks(
                temp_dir,
                manage_effect=UpdaterError("preflight failed"),
            )
            self.assertEqual(run.status, run.STATUS_FAILED)
            self.assertEqual(state.active_version, __version__)
            self.assertEqual(store.read_active(__version__)["source"], "image")

    def test_interrupted_pre_switch_run_restores_static_and_clears_maintenance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RuntimeStore(temp_dir).ensure()
            store.set_maintenance(True, token="interrupted")
            run = queue_run(DluxUpdateRun.ACTION_CHECK, self.user.username)
            run.status = run.STATUS_MIGRATING
            run.save(update_fields=["status"])
            service = UpdateService(store=store)
            with mock.patch.object(service, "_run_manage") as run_manage:
                recovered = service.recover_interrupted_run()
            recovered.refresh_from_db()
            state = DluxUpdateState.load()
            self.assertEqual(recovered.status, run.STATUS_FAILED)
            self.assertFalse(recovered.is_active)
            self.assertTrue(recovered.report["interrupted"])
            self.assertEqual(state.active_run_token, "")
            self.assertFalse(state.degraded)
            self.assertFalse(store.maintenance_file.exists())
            run_manage.assert_called_once()

    def test_interrupted_post_switch_apply_restores_source_pointer(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RuntimeStore(temp_dir).ensure()
            store.release_path(NEWER_VERSION).mkdir()
            store.write_active(NEWER_VERSION, source="volume", generation=1)
            store.set_generation(1)
            store.set_maintenance(True, token="interrupted")
            state = DluxUpdateState.load()
            state.active_version = NEWER_VERSION
            state.active_wheel_url = "https://files.pythonhosted.org/new.whl"
            state.active_wheel_sha256 = "a" * 64
            state.active_manifest = release_manifest()
            state.previous_version = __version__
            state.generation = 1
            state.save()
            run = DluxUpdateRun.objects.create(
                action=DluxUpdateRun.ACTION_APPLY,
                status=DluxUpdateRun.STATUS_VERIFYING_HEALTH,
                source_version=__version__,
                target_version=NEWER_VERSION,
                report={"pointer_switched": True},
            )
            state.active_run_token = run.token
            state.save(update_fields=["active_run_token", "updated_at"])
            service = UpdateService(store=store)
            with mock.patch.object(service, "_run_manage"):
                recovered = service.recover_interrupted_run()
            recovered.refresh_from_db()
            state.refresh_from_db()
            self.assertEqual(recovered.status, run.STATUS_ROLLED_BACK)
            self.assertTrue(recovered.report["pointer_recovered"])
            self.assertEqual(state.active_version, __version__)
            self.assertEqual(state.previous_version, NEWER_VERSION)
            self.assertEqual(store.read_active(__version__)["source"], "image")
            self.assertFalse(store.maintenance_file.exists())
            self.assertTrue(service.restart_worker)

    def test_interrupted_run_recovery_failure_remains_in_maintenance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RuntimeStore(temp_dir).ensure()
            store.set_maintenance(True, token="interrupted")
            run = DluxUpdateRun.objects.create(
                action=DluxUpdateRun.ACTION_APPLY,
                status=DluxUpdateRun.STATUS_MIGRATING,
                source_version=__version__,
                target_version=NEWER_VERSION,
            )
            state = DluxUpdateState.load()
            state.active_run_token = run.token
            state.save(update_fields=["active_run_token", "updated_at"])
            service = UpdateService(store=store)
            with mock.patch.object(
                service,
                "_run_manage",
                side_effect=UpdaterError("static recovery failed"),
            ):
                recovered = service.recover_interrupted_run()
            recovered.refresh_from_db()
            state = DluxUpdateState.load()
            self.assertEqual(recovered.status, run.STATUS_FAILED)
            self.assertTrue(recovered.report["recovery_failed"])
            self.assertTrue(state.degraded)
            self.assertTrue(store.degraded_file.exists())
            self.assertTrue(store.maintenance_file.exists())

    # Exercises the in-container executor, kept until 1.9.0 behind this setting;
    # the 1.8.0 default hands the operation to Composer instead.
    @override_settings(DLUX_UPDATE_EXECUTOR="inline")
    def test_manual_rollback_swaps_active_and_previous_without_reversing_migrations(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RuntimeStore(temp_dir).ensure()
            # The volume-resident active version must differ from (be newer than) the
            # baked __version__ we roll back to, so the rollback target resolves to the
            # baked "image" source.
            store.release_path(NEWER_VERSION).mkdir()
            store.write_active(NEWER_VERSION, source="volume", generation=0)
            state = DluxUpdateState.load()
            state.active_version = NEWER_VERSION
            state.active_wheel_url = "https://files.pythonhosted.org/new.whl"
            state.active_wheel_sha256 = "a" * 64
            state.active_manifest = release_manifest()
            state.previous_version = __version__
            state.save()
            run = queue_run(DluxUpdateRun.ACTION_ROLLBACK, self.user.username)
            service = UpdateService(store=store)
            with mock.patch.object(service, "_create_backup", return_value=SimpleNamespace(token="backup-token")), \
                 mock.patch.object(service, "_run_manage"), \
                 mock.patch.object(service, "_verify_health"):
                service.process_next()
            run.refresh_from_db()
            state.refresh_from_db()
            self.assertEqual(run.status, run.STATUS_COMPLETED)
            self.assertEqual(state.active_version, __version__)
            self.assertEqual(state.previous_version, NEWER_VERSION)
            self.assertEqual(store.read_active(__version__)["source"], "image")

    # Exercises the in-container executor, kept until 1.9.0 behind this setting;
    # the 1.8.0 default hands the operation to Composer instead.
    @override_settings(DLUX_UPDATE_EXECUTOR="inline")
    def test_manual_rollback_recovery_failure_marks_runtime_degraded(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RuntimeStore(temp_dir).ensure()
            store.release_path(NEWER_VERSION).mkdir()
            store.write_active(NEWER_VERSION, source="volume", generation=0)
            state = DluxUpdateState.load()
            state.active_version = NEWER_VERSION
            state.active_wheel_url = "https://files.pythonhosted.org/new.whl"
            state.active_wheel_sha256 = "a" * 64
            state.active_manifest = release_manifest()
            state.previous_version = __version__
            state.save()
            run = queue_run(DluxUpdateRun.ACTION_ROLLBACK, self.user.username)
            service = UpdateService(store=store)
            manage_effects = [
                None,
                None,
                UpdaterError("target static collection failed"),
                UpdaterError("current static recovery failed"),
            ]
            with mock.patch.object(service, "_create_backup", return_value=SimpleNamespace(token="backup-token")), \
                 mock.patch.object(service, "_run_manage", side_effect=manage_effects), \
                 mock.patch.object(service, "_verify_health"):
                service.process_next()
            run.refresh_from_db()
            state.refresh_from_db()
            self.assertEqual(run.status, run.STATUS_FAILED)
            self.assertTrue(run.report["recovery_failed"])
            self.assertTrue(state.degraded)
            self.assertTrue(store.degraded_file.exists())
            self.assertTrue(store.maintenance_file.exists())
            reconciled = UpdateService(store=store).reconcile()
            self.assertTrue(reconciled.degraded)
            self.assertTrue(store.degraded_file.exists())

    # Exercises the in-container executor, kept until 1.9.0 behind this setting;
    # the 1.8.0 default hands the operation to Composer instead.
    @override_settings(DLUX_UPDATE_EXECUTOR="inline")
    def test_manual_rollback_target_failure_with_successful_recovery_is_not_degraded(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RuntimeStore(temp_dir).ensure()
            store.release_path(NEWER_VERSION).mkdir()
            store.write_active(NEWER_VERSION, source="volume", generation=0)
            state = DluxUpdateState.load()
            state.active_version = NEWER_VERSION
            state.active_wheel_url = "https://files.pythonhosted.org/new.whl"
            state.active_wheel_sha256 = "a" * 64
            state.active_manifest = release_manifest()
            state.previous_version = __version__
            state.save()
            run = queue_run(DluxUpdateRun.ACTION_ROLLBACK, self.user.username)
            service = UpdateService(store=store)
            with mock.patch.object(service, "_create_backup", return_value=SimpleNamespace(token="backup-token")), \
                 mock.patch.object(service, "_run_manage"), \
                 mock.patch.object(
                     service,
                     "_verify_health",
                     side_effect=[UpdaterError("rollback target unhealthy"), None],
                 ):
                service.process_next()
            run.refresh_from_db()
            state.refresh_from_db()
            self.assertEqual(run.status, run.STATUS_FAILED)
            self.assertTrue(run.report["pointer_recovered"])
            self.assertEqual(state.active_version, NEWER_VERSION)
            self.assertFalse(state.degraded)
            self.assertFalse(store.maintenance_file.exists())


class BootstrapTests(TestCase):
    def _legacy_project(self, root):
        (root / "config").mkdir(parents=True)
        (root / ".nginx").mkdir()
        (root / "manage.py").write_text(
            '# Generated with django-lux 1.2.1.\n'
            'import os\nos.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")\n',
            encoding="utf-8",
        )
        (root / "config" / "settings.py").write_text("INSTALLED_APPS = []\n", encoding="utf-8")
        (root / "config" / "urls.py").write_text("urlpatterns = []\n", encoding="utf-8")
        (root / "requirements.txt").write_text("django-lux==1.2.1\ncelery\n", encoding="utf-8")
        (root / "compose.yml").write_text('''name: demo
x-environment:
  &de
  DEBUG_STATUS: "${DEBUG_STATUS:-False}"
services:
  db:
    image: postgres:17
  redis:
    image: redis:7
  smtp-relay:
    image: ${WEB_IMAGE:-demo:latest}
  nginx:
    image: nginx:latest
    volumes:
      - ./media/:/app/media:ro
  web:
    image: ${WEB_IMAGE:-demo:latest}
    command: >
      bash -c ' if [ "$$DEBUG_STATUS" = "True" ]; then
          python manage.py runserver 0.0.0.0:8000
      else
          gunicorn -c gunicorn.py config.wsgi:application
      fi'
    entrypoint: ["/app/entrypoint.sh"]
    post_start:
      - command: python manage.py migrator
    volumes:
      - ./imports/:/app/imports:ro
    healthcheck:
      test: [ "CMD", "python", "manage.py", "check" ]
    depends_on:
      smtp-relay:
        condition: service_healthy
  celery:
    image: ${WEB_IMAGE:-demo:latest}
    command: ["python", "-m", "celery", "-A", "config", "worker", "-B", "--loglevel=info"]
    volumes:
      - ./logs/:/app/logs:rw
    depends_on:
      redis:
        condition: service_healthy
volumes:
  static:

networks:
  demo_internal:
    internal: true
''', encoding="utf-8")
        (root / "compose.dev.yml").write_text('''name: demo
services:
  smtp-relay:
    build: .
  nginx:
    ports: []
  web:
    build: .
    volumes:
      - ./logs/:/app/logs:rw
  celery:
    build: .
    volumes:
      - ./logs/:/app/logs:rw
'''.rstrip(), encoding="utf-8")
        (root / ".nginx" / "nginx.conf").write_text('''server {
    client_max_body_size 5M;
    location / {
        proxy_pass http://web:8000;
    }
    location /health {
        proxy_pass http://web:8000/health/;
    }
}
''', encoding="utf-8")

    def test_bootstrap_dry_run_apply_and_reapply(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._legacy_project(root)
            dry = enable_updater(root)
            self.assertFalse(dry["applied"])
            self.assertIn("compose.yml", dry["files"])
            self.assertIn(".nginx/maintenance.html", dry["files"])
            self.assertNotIn(UPDATER_COMPOSE_START := "# DjangoLux updater start", (root / "compose.yml").read_text())
            completed = SimpleNamespace(returncode=0, stdout="ok", stderr="")
            runner = mock.Mock(return_value=completed)
            with mock.patch("dlux.scaffold.legacy.shutil.which", return_value="/usr/bin/docker"):
                applied = enable_updater(root, apply=True, command_runner=runner)
            self.assertTrue(applied["applied"])
            self.assertIn(UPDATER_COMPOSE_START, (root / "compose.yml").read_text())
            self.assertEqual((root / "requirements.txt").read_text().splitlines()[0], f"django-lux[updater]=={__version__}")
            self.assertFalse((root / "tools" / "dlux_runtime_supervisor.py").exists())
            maintenance = (root / ".nginx" / "maintenance.html").read_text(encoding="utf-8")
            nginx = (root / ".nginx" / "nginx.conf").read_text(encoding="utf-8")
            self.assertIn('var statusUrl = "/_update/status.json"', maintenance)
            self.assertIn("alias /opt/dlux-runtime/state/deploy-status.json;", nginx)
            self.assertIn("alias /opt/dlux-runtime/state/deploy-log.txt;", nginx)
            self.assertTrue(Path(applied["backup_root"], "compose.yml").exists())
            self.assertIn(mock.call(
                ["docker", "compose", "config"], cwd=str(root.resolve()), check=False,
                capture_output=True, text=True,
            ), runner.mock_calls)
            with mock.patch("dlux.scaffold.legacy.shutil.which", return_value="/usr/bin/docker"):
                reapplied = enable_updater(root, apply=True, command_runner=runner)
            self.assertEqual(reapplied["files"], [])

    def test_bootstrap_refuses_non_generated_or_custom_layout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._legacy_project(root)
            (root / "manage.py").write_text('os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")\n', encoding="utf-8")
            with self.assertRaises(ScaffoldError):
                enable_updater(root)


class InlineDoctorPreflightTests(TestCase):
    """The inline apply/rollback preflight runs a dlux wiring check against the
    target release. It must be scoped to the wiring groups and never abort the
    update: at preflight the target's migrations are unapplied and its static is
    uncollected, so the full doctor would exit non-zero on that expected state."""

    def setUp(self):
        DluxUpdateState.load()

    def _service_and_run(self, temp_dir, returncode):
        import types

        calls = []

        def runner(cmd, **kwargs):
            calls.append(cmd)
            return types.SimpleNamespace(returncode=returncode, stdout="", stderr="pending migrations")

        store = RuntimeStore(temp_dir).ensure()
        service = UpdateService(store=store, command_runner=runner)
        service._manage_py = lambda: Path(temp_dir) / "manage.py"
        run = DluxUpdateRun.objects.create(
            action=DluxUpdateRun.ACTION_APPLY,
            status=DluxUpdateRun.STATUS_PREFLIGHT,
            requested_by_username="inline-admin",
            token="preflight-run",
        )
        return service, run, calls

    def test_preflight_is_scoped_to_wiring_groups_and_uses_dlux_doctor(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service, run, calls = self._service_and_run(temp_dir, returncode=0)
            service._doctor_preflight({"PYTHONPATH": "x"}, run)
            cmd = calls[-1]
            self.assertIn("dlux_doctor", cmd)
            self.assertEqual(cmd.count("--group"), 2)
            self.assertIn("settings", cmd)
            self.assertIn("urls", cmd)
            self.assertNotIn("dlux_check", cmd)

    def test_preflight_does_not_abort_when_the_doctor_exits_non_zero(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service, run, _ = self._service_and_run(temp_dir, returncode=1)
            # Must not raise: expected pending-migration/uncollected-static state
            # at preflight would otherwise abort every inline update.
            service._doctor_preflight({"PYTHONPATH": "x"}, run)

    def test_required_command_still_aborts_on_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service, run, _ = self._service_and_run(temp_dir, returncode=1)
            with self.assertRaises(UpdaterError):
                service._run_manage(["check"], {"PYTHONPATH": "x"}, run)


class InlineProgressMirrorTests(TestCase):
    """During inline maintenance the proxy 503s web, so the run's own status API
    is unreachable and the modal froze. The worker must mirror each phase to the
    proxy-served deploy-status.json / deploy-log.txt, which survive maintenance."""

    def setUp(self):
        DluxUpdateState.load()

    def _run(self, action=None):
        action = action or DluxUpdateRun.ACTION_APPLY
        return DluxUpdateRun.objects.create(
            action=action,
            status=DluxUpdateRun.STATUS_QUEUED,
            requested_by_username="inline-admin",
            token=f"run-{action}",
        )

    def test_transition_mirrors_phase_to_the_shared_volume(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RuntimeStore(temp_dir).ensure()
            service = UpdateService(store=store)
            run = self._run()
            service._transition(run, DluxUpdateRun.STATUS_MAINTENANCE, "Entering maintenance mode.")

            doc = read_deploy_status(store)
            self.assertEqual(doc["kind"], "inline")
            self.assertEqual(doc["status"], "maintenance")
            self.assertEqual(doc["run_token"], run.token)
            self.assertEqual(doc["action"], DluxUpdateRun.ACTION_APPLY)
            log = (store.state_dir / "deploy-log.txt").read_text(encoding="utf-8")
            self.assertIn("Entering maintenance mode.", log)

    def test_each_maintenance_phase_is_published(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RuntimeStore(temp_dir).ensure()
            service = UpdateService(store=store)
            run = self._run()
            for status in (
                DluxUpdateRun.STATUS_MAINTENANCE,
                DluxUpdateRun.STATUS_MIGRATING,
                DluxUpdateRun.STATUS_COLLECTING_STATIC,
                DluxUpdateRun.STATUS_SWITCHING,
                DluxUpdateRun.STATUS_VERIFYING_HEALTH,
            ):
                service._transition(run, status, f"phase {status}")
                self.assertEqual(read_deploy_status(store)["status"], status)

    def test_complete_publishes_the_terminal_phase(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RuntimeStore(temp_dir).ensure()
            service = UpdateService(store=store)
            run = self._run()
            run.append_log("DjangoLux 9.9.9 is active and healthy.")
            service._complete(run, report={"active_version": "9.9.9"})

            doc = read_deploy_status(store)
            self.assertEqual(doc["status"], DluxUpdateRun.STATUS_COMPLETED)
            self.assertEqual(doc["kind"], "inline")
            log = (store.state_dir / "deploy-log.txt").read_text(encoding="utf-8")
            self.assertIn("active and healthy", log)

    def test_failure_during_maintenance_is_published(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RuntimeStore(temp_dir).ensure()
            service = UpdateService(store=store)
            run = self._run()
            run.status = DluxUpdateRun.STATUS_MIGRATING
            run.save(update_fields=["status"])
            service._handle_failure(run, RuntimeError("migration blew up"))

            doc = read_deploy_status(store)
            self.assertEqual(doc["status"], DluxUpdateRun.STATUS_FAILED)
            self.assertEqual(doc["kind"], "inline")
            self.assertTrue(doc["error"])

    def test_check_runs_do_not_mirror(self):
        """A background check must never touch the shared progress file — it is
        not a user-visible maintenance operation and would confuse the modal."""
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RuntimeStore(temp_dir).ensure()
            service = UpdateService(store=store)
            run = self._run(action=DluxUpdateRun.ACTION_CHECK)
            service._transition(run, DluxUpdateRun.STATUS_VERIFYING, "verifying")
            self.assertFalse(status_path(store).exists())

    def test_mirror_failure_never_derails_the_transition(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RuntimeStore(temp_dir).ensure()
            service = UpdateService(store=store)
            run = self._run()
            with mock.patch("dlux.updater.image_update.write_deploy_status", side_effect=OSError("disk full")):
                service._transition(run, DluxUpdateRun.STATUS_SWITCHING, "switching")
            run.refresh_from_db()
            self.assertEqual(run.status, DluxUpdateRun.STATUS_SWITCHING)


class InlineRollForwardTests(TestCase):
    """When the latest release advances between the check and the apply, the
    updater re-verifies the new release in place and rolls forward if it's
    inline-safe — instead of dead-ending — while stopping clearly if it isn't and
    keeping the tampered-artifact hard stop for a re-published same-version wheel."""

    def _state(self):
        state = DluxUpdateState.load()
        state.baked_version = "1.2.2"
        state.active_version = "1.2.2"
        state.latest_version = "1.2.3"
        state.latest_wheel_url = "https://files.pythonhosted.org/x.whl"
        state.latest_wheel_sha256 = "a" * 64
        state.latest_manifest = release_manifest()
        state.latest_compatible = True
        state.save()
        return state

    def _run(self):
        return DluxUpdateRun.objects.create(
            action=DluxUpdateRun.ACTION_APPLY, source_version="1.2.2", target_version="1.2.3"
        )

    def _candidate(self, version, sha="b" * 64, url="https://files.pythonhosted.org/y.whl"):
        return ReleaseCandidate(version, f"django_lux-{version}-py3-none-any.whl", url, sha)

    def _patches(self, tmp, candidate, *, compatible=True):
        return (
            mock.patch("dlux.updater.service.fetch_simple_index", return_value={}),
            mock.patch("dlux.updater.service.select_latest_candidate", return_value=candidate),
            mock.patch("dlux.updater.service.download_wheel", return_value=Path(tmp) / "w.whl"),
            mock.patch("dlux.updater.service.verify_pypi_attestation", return_value=True),
            mock.patch(
                "dlux.updater.service.assess_wheel",
                return_value={"compatible": compatible, "manifest": release_manifest("1.2.4"), "reason": "ok" if compatible else "needs an image update"},
            ),
        )

    def test_rolls_forward_to_a_newer_inline_safe_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = UpdateService(store=RuntimeStore(tmp).ensure())
            state, run = self._state(), self._run()
            p = self._patches(tmp, self._candidate("1.2.4"))
            with p[0], p[1], p[2], p[3], p[4]:
                result = service._verified_latest_candidate(state, run)
            self.assertEqual(result.version, "1.2.4")
            self.assertEqual(DluxUpdateState.load().latest_version, "1.2.4")
            run.refresh_from_db()
            self.assertIn("1.2.3", run.progress_log)
            self.assertIn("1.2.4", run.progress_log)

    def test_stops_clearly_when_the_newer_release_is_not_inline_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = UpdateService(store=RuntimeStore(tmp).ensure())
            state, run = self._state(), self._run()
            p = self._patches(tmp, self._candidate("1.2.4"), compatible=False)
            with p[0], p[1], p[2], p[3], p[4]:
                with self.assertRaises(UpdaterError) as ctx:
                    service._verified_latest_candidate(state, run)
            self.assertIn("inline-safe", str(ctx.exception))

    def test_same_version_tampered_artifact_still_hard_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = UpdateService(store=RuntimeStore(tmp).ensure())
            state, run = self._state(), self._run()
            tampered = self._candidate("1.2.3", sha="c" * 64)  # same version, different sha
            with mock.patch("dlux.updater.service.fetch_simple_index", return_value={}), \
                 mock.patch("dlux.updater.service.select_latest_candidate", return_value=tampered):
                with self.assertRaises(UpdaterError) as ctx:
                    service._verified_latest_candidate(state, run)
            self.assertIn("metadata changed", str(ctx.exception))


class InlineFloorTests(SimpleTestCase):
    def _floor_wheel(self, path, *, version="1.7.1", baseline="1.7.0"):
        return make_wheel(
            path, version=version,
            manifest=release_manifest(version=version, image_baseline=baseline),
        )

    def test_manifest_normalizes_and_validates_image_baseline(self):
        self.assertEqual(
            validate_release_manifest(release_manifest(image_baseline="1.7.0"), "1.2.3")["image_baseline"],
            "1.7.0",
        )
        self.assertNotIn(
            "image_baseline",
            validate_release_manifest(release_manifest(image_baseline="  "), "1.2.3"),
        )
        with self.assertRaisesMessage(UpdaterError, "invalid image baseline"):
            validate_release_manifest(release_manifest(image_baseline="not-a-version"), "1.2.3")

    def test_inline_floor_blocks_a_box_below_the_baseline(self):
        with tempfile.TemporaryDirectory() as temp_dir, \
                mock.patch("dlux.updater.manifest._check_dependency_contract", return_value=[]), \
                mock.patch("dlux.updater.manifest._check_dependencies", return_value=[]):
            wheel = self._floor_wheel(Path(temp_dir) / "candidate.whl")
            candidate = ReleaseCandidate("1.7.1", wheel.name, "https://files.pythonhosted.org/a.whl", "a" * 64)

            blocked = assess_wheel(candidate, wheel, baked_version="1.6.8")
            self.assertFalse(blocked["compatible"])
            self.assertIn("needs the v1.7.0 project image", blocked["reason"])

    def test_inline_floor_allows_a_box_at_or_above_the_baseline(self):
        with tempfile.TemporaryDirectory() as temp_dir, \
                mock.patch("dlux.updater.manifest._check_dependency_contract", return_value=[]), \
                mock.patch("dlux.updater.manifest._check_dependencies", return_value=[]):
            wheel = self._floor_wheel(Path(temp_dir) / "candidate.whl")
            candidate = ReleaseCandidate("1.7.1", wheel.name, "https://files.pythonhosted.org/a.whl", "a" * 64)

            for baked in ("1.7.0", "1.7.0.1", "1.8.0"):
                assessment = assess_wheel(candidate, wheel, baked_version=baked)
                self.assertTrue(assessment["compatible"], f"baked {baked} should clear the floor")

    def test_inline_floor_fails_closed_when_image_version_is_unknown(self):
        with tempfile.TemporaryDirectory() as temp_dir, \
                mock.patch("dlux.updater.manifest._check_dependency_contract", return_value=[]), \
                mock.patch("dlux.updater.manifest._check_dependencies", return_value=[]):
            wheel = self._floor_wheel(Path(temp_dir) / "candidate.whl")
            candidate = ReleaseCandidate("1.7.1", wheel.name, "https://files.pythonhosted.org/a.whl", "a" * 64)

            for baked in (None, "", "garbage"):
                self.assertFalse(assess_wheel(candidate, wheel, baked_version=baked)["compatible"])

    def test_release_without_baseline_is_unaffected(self):
        with tempfile.TemporaryDirectory() as temp_dir, \
                mock.patch("dlux.updater.manifest._check_dependency_contract", return_value=[]), \
                mock.patch("dlux.updater.manifest._check_dependencies", return_value=[]):
            wheel = make_wheel(Path(temp_dir) / "candidate.whl", version="1.7.1",
                               manifest=release_manifest(version="1.7.1"))
            candidate = ReleaseCandidate("1.7.1", wheel.name, "https://files.pythonhosted.org/a.whl", "a" * 64)

            assessment = assess_wheel(candidate, wheel, baked_version="1.6.8")
            self.assertTrue(assessment["compatible"])
