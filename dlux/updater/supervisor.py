"""Standard-library process supervisor for the shared DjangoLux runtime volume.

Shipped inside the ``dlux`` package (not as a project scaffold file) so every fix
travels with dlux itself — an image rebuild or inline update delivers it, with no
per-project file to hand-copy. Invoked as ``python -m dlux.updater.supervisor``.

It runs at the very start of a container, before any volume release is on the
child's ``PYTHONPATH``, and imports only the standard library plus the bundled
release manifest — no Django setup.
"""

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import signal
import subprocess
import time


def baked_version():
    """Resolve the immutable image (baked) DjangoLux version.

    Single source of truth: the running code's manifest version (``dlux.__version__``),
    read here *before* any volume release is prepended to the child's PYTHONPATH, so
    it reflects the image package. This works identically for pip-installed images and
    bind-mounted source checkouts (where installed-package metadata is absent or stale).
    Importing ``dlux`` only reads the bundled manifest JSON — no Django setup. Fall back
    to installed-package metadata, then give up gracefully.
    """
    try:
        from dlux import __version__

        version = str(__version__).strip()
        if version:
            return version
    except Exception:
        pass
    try:
        return importlib.metadata.version("django-lux")
    except importlib.metadata.PackageNotFoundError:
        return ""


def _is_newer(candidate, baseline):
    """True if dlux version ``candidate`` is strictly newer than ``baseline``.

    An empty candidate is never newer; an unknown baseline preserves the pinned
    release (prior behavior). Prefers ``packaging`` and falls back to a numeric
    dotted comparison, so 1.5.8 vs 1.5.11 orders correctly.
    """
    candidate = str(candidate or "").strip()
    baseline = str(baseline or "").strip()
    if not candidate:
        return False
    if not baseline:
        return True
    try:
        from packaging.version import Version

        return Version(candidate) > Version(baseline)
    except Exception:
        pass

    def _key(value):
        key = []
        for chunk in value.split("."):
            digits = "".join(char for char in chunk if char.isdigit())
            key.append(int(digits) if digits else 0)
        return key

    try:
        return _key(candidate) > _key(baseline)
    except Exception:
        return True


def resolve_release(root, baked=None):
    """Return the runtime-active volume release directory, or ``None`` to use the
    baked image package.

    Single source of truth for "which DjangoLux is active": consumed both here
    (to build the child ``PYTHONPATH``) and by the project ``manage.py`` (to keep
    every management command — collectstatic above all — on the same release the
    web process serves templates from). Missing/corrupt state falls back to baked.

    A volume release only shadows the baked image when it is STRICTLY NEWER than
    baked. Inline updates ship newer, forward-compatible dlux; an older pinned
    release must never shadow a newer image (an image update supersedes it), or
    the image's app code would run against stale dlux and fail on missing symbols.
    """
    root = Path(root)
    if baked is None:
        baked = os.environ.get("DLUX_BAKED_VERSION") or baked_version()
    active_file = root / "state" / "active.json"
    try:
        payload = json.loads(active_file.read_text(encoding="utf-8"))
        version = str(payload.get("version") or "").strip()
        source = payload.get("source")
        release = (root / "releases" / version).resolve()
        release.relative_to((root / "releases").resolve())
        if source == "volume" and release.is_dir() and _is_newer(version, baked):
            return release
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    return None


def runtime_environment(root):
    env = os.environ.copy()
    baked = env.get("DLUX_BAKED_VERSION") or baked_version()
    if baked and not env.get("DLUX_BAKED_VERSION"):
        env["DLUX_BAKED_VERSION"] = baked
    release = resolve_release(root, baked)
    if release is not None:
        current = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{release}{os.pathsep}{current}" if current else str(release)
    return env


def generation(root):
    try:
        return max(0, int((Path(root) / "state" / "generation").read_text(encoding="utf-8").strip()))
    except (OSError, ValueError):
        return 0


KILL_WAIT_SECONDS = 10.0


def signal_group(process, sig):
    """Signal the child's process group, even after the direct child has exited.

    The group outlives a ``bash -c`` wrapper that dies first, so its server
    grandchild must still receive the signal.
    """
    try:
        os.killpg(process.pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def _reap_group(process):
    """Reap exited members of the child's group once the direct child is reaped.

    As PID 1 the supervisor adopts a grandchild orphaned by the wrapper, and an
    unreaped zombie keeps the group alive. The direct child is reaped first
    through ``Popen`` so its exit status is not lost.
    """
    if process.poll() is None:
        return
    while True:
        try:
            pid, _status = os.waitpid(-process.pid, os.WNOHANG)
        except ChildProcessError:
            return
        if pid == 0:
            return


def _group_running(process):
    _reap_group(process)
    if process.poll() is None:
        return True
    try:
        os.killpg(process.pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    return True


def _wait_group(process, seconds, interval):
    deadline = time.monotonic() + seconds
    while _group_running(process):
        if time.monotonic() >= deadline:
            return False
        time.sleep(interval)
    return True


def stop_child(process, grace_seconds, sig=signal.SIGTERM):
    """Stop the child's whole process group and return the direct child's exit code.

    Returns only once every process of the group has exited, so a restart never
    starts the next generation while the old server still holds its port. The
    group is SIGKILLed after ``grace_seconds``.
    """
    signal_group(process, sig)
    if not _wait_group(process, grace_seconds, 0.1):
        signal_group(process, signal.SIGKILL)
        _wait_group(process, KILL_WAIT_SECONDS, 0.05)
    return process.wait()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", default=os.getenv("DLUX_UPDATE_RUNTIME_ROOT", "/opt/dlux-runtime"))
    parser.add_argument("--grace-seconds", type=float, default=30.0)
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument("--no-watch", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = list(args.command)
    if command and command[0] == "--":
        command.pop(0)
    if not command:
        parser.error("a child command is required after --")

    root = Path(args.runtime_root).resolve()
    stopping = False
    forwarded_signal = signal.SIGTERM
    child = None

    def request_stop(signum, _frame):
        nonlocal stopping, forwarded_signal
        stopping = True
        forwarded_signal = signum
        if child is not None:
            signal_group(child, signum)

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    while True:
        started_generation = generation(root)
        restart_requested = False
        child = subprocess.Popen(
            command,
            env=runtime_environment(root),
            start_new_session=True,
        )
        while child.poll() is None and not stopping:
            time.sleep(max(0.1, min(args.poll_seconds, 10.0)))
            if not args.no_watch and generation(root) != started_generation:
                stop_child(child, max(1.0, args.grace_seconds))
                restart_requested = True
                break
        if stopping:
            return stop_child(child, max(1.0, args.grace_seconds), forwarded_signal)
        if restart_requested:
            continue
        return_code = child.poll()
        if return_code is not None:
            return return_code


if __name__ == "__main__":
    raise SystemExit(main())
