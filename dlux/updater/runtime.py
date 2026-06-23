from __future__ import annotations

import json
import os
import re
from pathlib import Path

from packaging.version import InvalidVersion, Version

from . import UpdaterError


_VERSION_DIR_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")


class RuntimeStore:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        self.releases = self.root / "releases"
        self.staging = self.root / "staging"
        self.downloads = self.root / "downloads"
        self.failed = self.root / "failed"
        self.state_dir = self.root / "state"
        self.active_file = self.state_dir / "active.json"
        self.generation_file = self.state_dir / "generation"
        self.maintenance_file = self.state_dir / "maintenance"
        self.heartbeat_file = self.state_dir / "updater-heartbeat"
        self.degraded_file = self.state_dir / "degraded"

    def ensure(self):
        for path in (
            self.releases, self.staging, self.downloads, self.failed, self.state_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
        if not self.generation_file.exists():
            self._atomic_text(self.generation_file, "0\n")
        return self

    @staticmethod
    def normalize_version(version):
        raw = str(version or "").strip()
        try:
            normalized = str(Version(raw))
        except InvalidVersion as exc:
            raise UpdaterError("The requested update version is invalid.") from exc
        if not _VERSION_DIR_RE.fullmatch(normalized):
            raise UpdaterError("The requested update version cannot be used as a runtime path.")
        return normalized

    def release_path(self, version):
        return self.releases / self.normalize_version(version)

    def stage_path(self, token):
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", str(token or ""))[:80]
        if not safe:
            raise UpdaterError("The update run token is invalid.")
        return self.staging / safe

    def wheel_path(self, candidate):
        return self.downloads / f"{candidate.sha256}-{candidate.filename}"

    def read_active(self, baked_version):
        fallback = {
            "version": str(baked_version),
            "source": "image",
            "path": "",
            "generation": self.read_generation(),
        }
        if not self.active_file.exists():
            return fallback
        try:
            payload = json.loads(self.active_file.read_text(encoding="utf-8"))
            version = self.normalize_version(payload.get("version"))
            source = payload.get("source")
            if source == "image":
                return {
                    **fallback,
                    "generation": int(payload.get("generation") or self.read_generation()),
                }
            path = self.release_path(version).resolve()
            path.relative_to(self.releases.resolve())
            if source != "volume" or not path.is_dir():
                raise ValueError("missing release directory")
            return {
                "version": version,
                "source": "volume",
                "path": str(path),
                "generation": int(payload.get("generation") or self.read_generation()),
            }
        except Exception as exc:
            raise UpdaterError("The active DjangoLux runtime state is invalid.") from exc

    def write_active(self, version, *, source="volume", generation=None):
        version = self.normalize_version(version)
        if source not in {"image", "volume"}:
            raise UpdaterError("The runtime source is invalid.")
        path = ""
        if source == "volume":
            release = self.release_path(version)
            if not release.is_dir():
                raise UpdaterError("The selected DjangoLux release is not staged.")
            path = str(release)
        generation = self.read_generation() if generation is None else int(generation)
        payload = {
            "version": version,
            "source": source,
            "path": path,
            "generation": generation,
        }
        self._atomic_text(self.active_file, json.dumps(payload, sort_keys=True) + "\n")
        return payload

    def read_generation(self):
        try:
            return max(0, int(self.generation_file.read_text(encoding="utf-8").strip()))
        except (OSError, ValueError):
            return 0

    def bump_generation(self):
        generation = self.read_generation() + 1
        self._atomic_text(self.generation_file, f"{generation}\n")
        return generation

    def set_generation(self, generation):
        generation = max(0, int(generation))
        self._atomic_text(self.generation_file, f"{generation}\n")
        return generation

    def set_maintenance(self, enabled, *, token=""):
        if enabled:
            self._atomic_text(
                self.maintenance_file,
                json.dumps({"token": str(token or "")[:64]}) + "\n",
            )
        elif self.maintenance_file.exists():
            archived = self.failed / f"maintenance-{self.read_generation()}"
            suffix = 1
            while archived.exists():
                suffix += 1
                archived = self.failed / f"maintenance-{self.read_generation()}-{suffix}"
            self.maintenance_file.replace(archived)

    def write_heartbeat(self):
        import time

        self._atomic_text(self.heartbeat_file, f"{time.time():.6f}\n")

    def invalidate_heartbeat(self):
        self._atomic_text(self.heartbeat_file, "0\n")

    def set_degraded(self, message):
        self._atomic_text(self.degraded_file, str(message or "runtime degraded")[:4000] + "\n")

    def clear_degraded(self):
        if not self.degraded_file.exists():
            return
        destination = self.failed / f"degraded-{self.read_generation()}"
        suffix = 1
        while destination.exists():
            suffix += 1
            destination = self.failed / f"degraded-{self.read_generation()}-{suffix}"
        self.degraded_file.replace(destination)

    def activate_stage(self, stage, version):
        stage = Path(stage).resolve()
        stage.relative_to(self.staging.resolve())
        destination = self.release_path(version)
        if destination.exists():
            if not destination.is_dir():
                raise UpdaterError("The target release path is not a directory.")
            return destination
        stage.replace(destination)
        return destination

    def archive_failed_stage(self, stage, token):
        stage = Path(stage)
        if not stage.exists():
            return None
        destination = self.failed / re.sub(r"[^A-Za-z0-9._-]", "_", str(token))[:80]
        suffix = 1
        while destination.exists():
            suffix += 1
            destination = self.failed / f"{token}-{suffix}"
        stage.replace(destination)
        return destination

    @staticmethod
    def python_env_for(path):
        env = os.environ.copy()
        current = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{path}{os.pathsep}{current}" if current else str(path)
        return env

    @staticmethod
    def install_wheel(wheel_path, target, *, runner=None):
        import subprocess
        import sys

        runner = runner or subprocess.run
        target = Path(target)
        if target.exists():
            raise UpdaterError("The update staging directory already exists.")
        target.mkdir(parents=True)
        completed = runner(
            [
                sys.executable, "-m", "pip", "install", "--no-deps", "--no-compile",
                "--target", str(target), str(wheel_path),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if completed.returncode != 0:
            raise UpdaterError("The verified DjangoLux wheel could not be staged.")
        return target

    @staticmethod
    def _atomic_text(path, text):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)
