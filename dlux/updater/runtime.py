from __future__ import annotations

import json
import os
import re
from pathlib import Path

from django.conf import settings

from packaging.version import InvalidVersion, Version

from . import UpdaterError
from . import shared_files


_VERSION_DIR_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")


def state_dir(store=None):
    """The runtime state directory, WITHOUT creating it.

    Readers run on the web container, which mounts the runtime volume
    read-only — they must never mkdir or ensure. Writers (the worker) pass their
    own ensured ``store`` instead.

    It lives here, beside the rest of the volume layout, because every file
    protocol on that volume needs it: image updates, package updates and the
    channel policy. Homing it in any one of them makes the other two import that
    protocol to find a path.
    """
    if store is not None:
        return store.state_dir
    root = Path(getattr(settings, "DLUX_UPDATE_RUNTIME_ROOT", "/opt/dlux-runtime")).expanduser()
    return root / "state"


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
            shared_files.ensure_dir(path)
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

    def staged_versions(self):
        """Releases staged on the volume, oldest first, ordered by version.

        Mirrors Composer's view of the same directory — it is the process that
        activates them, and a rollback target read in string order would put
        1.8.10 below 1.8.9.
        """
        if not self.releases.is_dir():
            return []
        found = []
        for entry in self.releases.iterdir():
            if not entry.is_dir():
                continue
            try:
                found.append((Version(entry.name), entry.name))
            except InvalidVersion:
                continue
        return [name for _version, name in sorted(found)]

    def stage_path(self, token):
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", str(token or ""))[:80]
        if not safe:
            raise UpdaterError("The update run token is invalid.")
        return self.staging / safe

    def read_active(self, baked_version):
        """What the supervisor serves: the volume release ``active.json`` names, or
        the baked image package.

        A volume release whose image floor this image does not meet is not served;
        the result is then the baked package, with ``held`` naming the release and
        why. ``active.json`` is left as it is, so restoring an image that meets
        the floor serves the release again.
        """
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
            from .supervisor import _is_newer, image_floor_problem

            problem = image_floor_problem(path, baked_version) if _is_newer(version, baked_version) else ""
            if problem:
                # The supervisor serves the baked package on this image, so that
                # is what is active; `held` keeps the release the pointer names.
                return {**fallback, "held": {"version": version, "reason": problem}}
            return {
                "version": version,
                "source": "volume",
                "path": str(path),
                "generation": int(payload.get("generation") or self.read_generation()),
            }
        except Exception as exc:
            raise UpdaterError("The active DjangoLux runtime state is invalid.") from exc

    def recorded_version(self):
        """The version active.json names, or None when it is absent or unreadable.

        ``read_active`` reports the baked version for an image activation, so a
        stale ``version`` left in the file is only visible here. Composer reads
        the field literally.
        """
        try:
            payload = json.loads(self.active_file.read_text(encoding="utf-8"))
            return self.normalize_version(payload.get("version"))
        except Exception:
            return None

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
    def _atomic_text(path, text):
        shared_files.write_text(path, text)
