"""Standard-library process supervisor for the shared DjangoLux runtime volume."""

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import signal
import subprocess
import time


def runtime_environment(root):
    env = os.environ.copy()
    if not env.get("DLUX_BAKED_VERSION"):
        try:
            env["DLUX_BAKED_VERSION"] = importlib.metadata.version("django-lux")
        except importlib.metadata.PackageNotFoundError:
            pass
    active_file = root / "state" / "active.json"
    try:
        payload = json.loads(active_file.read_text(encoding="utf-8"))
        version = str(payload.get("version") or "").strip()
        source = payload.get("source")
        release = (root / "releases" / version).resolve()
        release.relative_to((root / "releases").resolve())
        if source == "volume" and release.is_dir():
            current = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = f"{release}{os.pathsep}{current}" if current else str(release)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        # Missing or corrupt runtime state deliberately falls back to the image package.
        pass
    return env


def generation(root):
    try:
        return max(0, int((root / "state" / "generation").read_text(encoding="utf-8").strip()))
    except (OSError, ValueError):
        return 0


def signal_group(process, sig):
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, sig)
    except ProcessLookupError:
        pass


def stop_child(process, grace_seconds):
    signal_group(process, signal.SIGTERM)
    deadline = time.monotonic() + grace_seconds
    while process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.1)
    if process.poll() is None:
        signal_group(process, signal.SIGKILL)
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
            signal_group(child, forwarded_signal)
            return stop_child(child, max(1.0, args.grace_seconds))
        if restart_requested:
            continue
        return_code = child.poll()
        if return_code is not None:
            return return_code


if __name__ == "__main__":
    raise SystemExit(main())
