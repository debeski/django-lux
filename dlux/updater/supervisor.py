"""Standard-library process supervisor for the shared DjangoLux runtime volume.

Shipped inside the ``dlux`` package (not as a project scaffold file) so every fix
travels with dlux itself — an image rebuild or inline update delivers it, with no
per-project file to hand-copy. Invoked as ``python -m dlux.updater.supervisor``.

It runs at the very start of a container, before any volume release is on the
child's ``PYTHONPATH``, and imports only the standard library plus the bundled
release manifest — no Django setup.
"""

import argparse
import errno
import importlib.metadata
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import time


_READ_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_NONBLOCK", 0)
    | getattr(os, "O_CLOEXEC", 0)
)


class RefusedFile(OSError):
    """A runtime-volume entry that is not a regular file within its size cap."""


def _refusal(info, limit):
    if stat.S_ISLNK(info.st_mode):
        return "it is a symbolic link"
    if stat.S_ISFIFO(info.st_mode):
        return "it is a FIFO"
    if stat.S_ISDIR(info.st_mode):
        return "it is a directory"
    if not stat.S_ISREG(info.st_mode):
        return "it is not a regular file"
    if info.st_size > limit:
        return f"it is larger than {limit} bytes"
    return ""


def read_bounded(path, limit):
    """The bytes of regular file ``path``, at most ``limit`` of them.

    Either side of the volume can plant an entry, so the read never blocks (a
    FIFO), never follows a link and never reads past ``limit``. Anything else
    raises ``RefusedFile``; a missing or unreadable file raises its ``OSError``.
    """
    path = Path(path)
    reason = _refusal(os.lstat(path), limit)
    if not reason:
        try:
            descriptor = os.open(path, _READ_FLAGS)
        except OSError as exc:
            if exc.errno != errno.ELOOP:
                raise
            reason = "it is a symbolic link"
        else:
            with os.fdopen(descriptor, "rb") as stream:
                reason = _refusal(os.fstat(stream.fileno()), limit)
                if not reason:
                    data = stream.read(limit + 1)
                    if len(data) <= limit:
                        return data
                    reason = f"it is larger than {limit} bytes"
    raise RefusedFile(f"{path.name} was refused: {reason}.")


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


def parse_image_floor(raw):
    """``(lowest, specifier)`` for a ``requires.baked_image`` value.

    A bare version means ``>=`` that version. A compound PEP 440 specifier
    (``>=1.17.0b1,<2.0``) is kept whole; ``lowest`` is its ``>=`` bound, or "".
    An empty value is ``("", None)``. Raises ``ValueError`` for anything else.
    """
    from packaging.specifiers import InvalidSpecifier, SpecifierSet

    text = str(raw or "").strip()
    if not text:
        return "", None
    if text[0].isdigit():
        text = f">={text}"
    try:
        specifier = SpecifierSet(text, prereleases=True)
    except InvalidSpecifier as exc:
        raise ValueError(f"requires.baked_image {raw!r} is not a version specifier") from exc
    lowest = ""
    for clause in specifier:
        if clause.operator == ">=" and (not lowest or _is_newer(clause.version, lowest)):
            lowest = clause.version
    return lowest, specifier


def _release_floor_text(release):
    try:
        manifest = json.loads((Path(release) / "dlux" / "release-manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return ""
    if not isinstance(manifest, dict):
        return ""
    requires = manifest.get("requires")
    floor = requires.get("baked_image") if isinstance(requires, dict) else None
    return str(floor or manifest.get("image_baseline") or "").strip()


def release_image_floor(release):
    """The oldest baked DjangoLux an image needs to run ``release``, or "".

    Read from the release's own manifest (``requires.baked_image``). A volume
    release carries only DjangoLux; everything it imports comes from the image,
    so a release that needed an image rebuild cannot run on an image older than
    that rebuild.
    """
    try:
        return parse_image_floor(_release_floor_text(release))[0]
    except ValueError:
        return ""


def image_floor_problem(release, baked):
    """Why this image cannot run volume ``release``, or "" when it can.

    An unknown baked version or a release without a floor is not a problem: both
    were served before the floor was enforced. A floor this supervisor cannot
    parse holds the release, so a malformed manifest never runs by accident.
    """
    raw = _release_floor_text(release)
    baked = str(baked or "").strip()
    if not raw or not baked:
        return ""
    name = Path(release).name
    try:
        lowest, specifier = parse_image_floor(raw)
    except ValueError:
        return f"DjangoLux {name} declares an image floor this image cannot read ({raw[:80]})"
    try:
        from packaging.version import InvalidVersion, Version

        if Version(baked) in specifier:
            return ""
    except InvalidVersion:
        return ""
    wanted = f"DjangoLux {lowest} or later" if str(specifier) == f">={lowest}" else f"DjangoLux {specifier}"
    return f"DjangoLux {name} needs a project image with {wanted}, but this image bakes {baked}"


def held_release_outcome(baked, running):
    """What runs while a release is held below its image floor, as a sentence.

    ``running`` is the DjangoLux of the process reporting it. This image's
    supervisor serves the baked package; one that predates the floor check (an
    image baking DjangoLux 1.16 or older) serves the release anyway, and then
    the reporting process runs something newer than the baked package.
    """
    if _is_newer(running, baked):
        return (
            f"This image's supervisor predates the floor check, so DjangoLux {running} "
            "runs on an image below its floor"
        )
    return f"The baked DjangoLux {baked} runs instead"


_REPORTED_FALLBACKS = set()


def _report_fallback(problem, baked):
    """Say once per process, on stderr, that the baked release runs instead."""
    if problem in _REPORTED_FALLBACKS:
        return
    _REPORTED_FALLBACKS.add(problem)
    print(
        f"dlux runtime: {problem}. Serving the baked DjangoLux {baked} instead. "
        "Deploy an image that meets the floor, or roll the runtime back.",
        file=sys.stderr,
        flush=True,
    )


ACTIVE_POINTER_MAX_BYTES = 64 * 1024


def read_active_pointer(root):
    """The ``state/active.json`` object, or ``{}`` when it is missing or unusable.

    Anything other than a JSON object (``null``, a list, a string, an oversized
    or unreadable file) counts as a missing pointer: the baked package is served
    and ``reconcile`` rebuilds the file.
    """
    try:
        payload = json.loads(read_bounded(Path(root) / "state" / "active.json", ACTIVE_POINTER_MAX_BYTES))
    except (OSError, ValueError, RecursionError):
        return {}
    return payload if isinstance(payload, dict) else {}


def runtime_fallback(root, baked=None):
    """Why the active volume release is not served on this image, or "".

    The same decision ``resolve_release`` makes, for readers that report it.
    """
    root = Path(root)
    if baked is None:
        baked = os.environ.get("DLUX_BAKED_VERSION") or baked_version()
    payload = read_active_pointer(root)
    try:
        version = str(payload.get("version") or "").strip()
        release = (root / "releases" / version).resolve()
        release.relative_to((root / "releases").resolve())
        if payload.get("source") == "volume" and release.is_dir() and _is_newer(version, baked):
            return image_floor_problem(release, baked)
    except (OSError, ValueError, TypeError):
        pass
    return ""


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

    Nor does one run on an image older than its ``requires.baked_image`` floor
    (an image rolled back under it): the baked package is served instead, and
    stderr says so once per process.
    """
    root = Path(root)
    if baked is None:
        baked = os.environ.get("DLUX_BAKED_VERSION") or baked_version()
    payload = read_active_pointer(root)
    try:
        version = str(payload.get("version") or "").strip()
        source = payload.get("source")
        release = (root / "releases" / version).resolve()
        release.relative_to((root / "releases").resolve())
        if source == "volume" and release.is_dir() and _is_newer(version, baked):
            problem = image_floor_problem(release, baked)
            if not problem:
                return release
            _report_fallback(problem, baked)
    except (OSError, ValueError, TypeError):
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
        return max(0, int(read_bounded(Path(root) / "state" / "generation", 64).decode("ascii").strip()))
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
    """Stop the child, then its group, and return the direct child's exit code.

    The signal goes to the direct child first, so a server that shuts its own
    workers down (Celery's warm shutdown, gunicorn's graceful stop) does so: a
    signal to the whole group reached Celery's pool children mid-task. Once the
    direct child has exited, whatever is left of its group (a ``bash -c``
    wrapper's server) gets the signal too. Returns only once every process of
    the group has exited, so a restart never starts the next generation while
    the old server still holds its port. The group is SIGKILLed after
    ``grace_seconds``.
    """
    try:
        process.send_signal(sig)
    except (ProcessLookupError, PermissionError):
        pass
    deadline = time.monotonic() + grace_seconds
    forwarded = False
    while _group_running(process):
        if not forwarded and process.poll() is not None:
            signal_group(process, sig)
            forwarded = True
        if time.monotonic() >= deadline:
            signal_group(process, signal.SIGKILL)
            _wait_group(process, KILL_WAIT_SECONDS, 0.05)
            break
        time.sleep(0.1)
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
