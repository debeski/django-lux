"""Can the app process use the data mounted into its container?

DjangoLux images run as uid ``APP_UID`` with primary group ``APP_GID`` (root),
and reach existing data through group bits. Data written while the stack ran as
root is ``root:root`` with directories at 0755, so a directory the app must
create or delete files in needs group write first. Composer's ``check --fix``
grants it; nothing here changes a file.

Two uses, sharing one rule:

- ``python -m dlux.mount_access gate`` from the entrypoint: a quick look at the
  top two levels of each mount, run only when the process is not root. Anything
  the app cannot use stops the container with exit 78 and names the path, so a
  stack whose data was never prepared fails at boot instead of failing uploads.
- ``report()`` from the ``storage.mount_access`` doctor check: the whole tree,
  judged for the running process, or for ``APP_UID``/``APP_GID`` while the app
  still runs as root.

What the app needs, per entry, on a read-write mount: directories readable,
writable and searchable; files readable; files under a ``logs`` mount also
writable (the project log handler appends and rotates). On the runtime volume
the app writes only into its top-level directories and the ``state/`` tree, and
replaces a file there by renaming a new one over it (``dlux.updater.shared_files``),
so every file there needs only reading; installed releases below ``releases/``
are only read. On a read-only mount only reading is needed. Symlinks are never
followed.

Dependency-free (no Django) so the entrypoint can run it before Django starts.
"""
from __future__ import annotations

import json
import os
import stat
import sys

APP_UID = 10001
APP_GID = 0

# Where the generated stack mounts data into app containers. Mounts below
# these roots are found from /proc/self/mountinfo, so a project's own mounts
# (Archive's ./scanlink_releases) are checked too.
MOUNT_ROOTS = ("/app", "/opt/dlux-runtime")
DEFAULT_PATHS = ("/app/media", "/app/logs", "/app/staticfiles", "/opt/dlux-runtime")

GATE_DEPTH = 2
GATE_EXIT = 78
REPORT_LIMIT = 20

READ, WRITE, SEARCH = 4, 2, 1
FIX_HINT = (
    "Run ./start.sh check --fix (Composer's app-permissions fix) to grant group access; "
    "see docs/deployment-configuration.md#file-permissions."
)


def _unescape(field):
    return (
        field.replace("\\040", " ").replace("\\011", "\t")
        .replace("\\012", "\n").replace("\\134", "\\")
    )


def mounts(mountinfo="/proc/self/mountinfo"):
    """``{mount point: read_only}`` for mounts at or below ``MOUNT_ROOTS``."""
    found = {}
    try:
        with open(mountinfo, encoding="utf-8") as stream:
            lines = stream.read().splitlines()
    except OSError:
        return found
    for line in lines:
        fields = line.split()
        if len(fields) < 6:
            continue
        point = _unescape(fields[4])
        if not any(point == root or point.startswith(root + "/") for root in MOUNT_ROOTS):
            continue
        if point == "/app":
            continue  # a development stack mounts the source tree here
        found[point] = "ro" in fields[5].split(",")
    return found


def targets(extra=(), mountinfo="/proc/self/mountinfo"):
    """``[(path, read_only)]``: discovered mounts, else the generated stack's paths."""
    table = mounts(mountinfo)
    if not table:
        table = {path: False for path in DEFAULT_PATHS if os.path.exists(path)}
    for path in extra:
        path = os.path.abspath(str(path))
        if path not in table and os.path.exists(path):
            table[path] = False
    return sorted(table.items())


def allowed(st, uid, groups, want):
    """Whether ``uid``/``groups`` get the ``want`` bits on an entry (no ACLs)."""
    if uid == 0:
        return True
    if st.st_uid == uid:
        bits = (st.st_mode >> 6) & 7
    elif st.st_gid in groups:
        bits = (st.st_mode >> 3) & 7
    else:
        bits = st.st_mode & 7
    return bits & want == want


def runtime_root():
    return os.path.abspath(os.environ.get("DLUX_UPDATE_RUNTIME_ROOT") or "/opt/dlux-runtime")


def role_of(root):
    """``runtime``, ``logs`` or ``data``: what the app does with a mount."""
    if os.path.abspath(root) == runtime_root():
        return "runtime"
    if os.path.basename(root.rstrip("/")) == "logs":
        return "logs"
    return "data"


def needs(is_dir, role, read_only, parts=()):
    """The bits the app needs on one entry; ``parts`` is its path below the mount root."""
    if read_only:
        return READ | SEARCH if is_dir else READ
    if role == "runtime":
        if is_dir:
            writes = len(parts) <= 1 or parts[:1] == ("state",)
            return READ | WRITE | SEARCH if writes else READ | SEARCH
        return READ
    if is_dir:
        return READ | WRITE | SEARCH
    return READ | WRITE if role == "logs" else READ


def _describe(want):
    return "".join(letter for bit, letter in ((READ, "r"), (WRITE, "w"), (SEARCH, "x")) if want & bit)


def _walk(root, max_depth):
    """Yield ``(path, lstat)`` for ``root`` and everything below, to ``max_depth``."""
    try:
        yield root, os.lstat(root)
    except OSError:
        return
    stack = [(root, 0)]
    while stack:
        directory, depth = stack.pop()
        if max_depth is not None and depth >= max_depth:
            continue
        try:
            entries = list(os.scandir(directory))
        except OSError:
            continue
        for entry in entries:
            try:
                st = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            yield entry.path, st
            if stat.S_ISDIR(st.st_mode):
                stack.append((entry.path, depth + 1))


def problems(uid, groups, *, max_depth=None, extra=(), mountinfo="/proc/self/mountinfo"):
    """Yield one dict per entry the identity cannot use the way the app needs."""
    groups = frozenset(groups)
    for root, read_only in targets(extra, mountinfo):
        role = role_of(root)
        for path, st in _walk(root, max_depth):
            if stat.S_ISLNK(st.st_mode):
                continue
            relative = os.path.relpath(path, root)
            parts = () if relative == "." else tuple(relative.split(os.sep))
            want = needs(stat.S_ISDIR(st.st_mode), role, read_only, parts)
            if allowed(st, uid, groups, want):
                continue
            yield {
                "path": path,
                "kind": "dir" if stat.S_ISDIR(st.st_mode) else "file",
                "owner": f"{st.st_uid}:{st.st_gid}",
                "mode": f"{stat.S_IMODE(st.st_mode):04o}",
                "needs": _describe(want),
                "mount_read_only": read_only,
            }


def current_identity():
    return os.geteuid(), {os.getegid(), *os.getgroups()}


def report(*, extra=(), mountinfo="/proc/self/mountinfo", limit=REPORT_LIMIT):
    """Full-tree summary for the running process, or for the app identity as root."""
    uid, groups = current_identity()
    as_root = uid == 0
    if as_root:
        uid, groups = APP_UID, {APP_GID}
    count, sample = 0, []
    for problem in problems(uid, groups, extra=extra, mountinfo=mountinfo):
        count += 1
        if len(sample) < limit:
            sample.append(problem)
    return {
        "running_as_root": as_root,
        "uid": uid,
        "gid": APP_GID if as_root else os.getegid(),
        "mounts": [path for path, _ro in targets(extra, mountinfo)],
        "problems": count,
        "sample": sample,
    }


def gate(*, out=sys.stderr, mountinfo="/proc/self/mountinfo"):
    """Exit status for the entrypoint: 0 when usable or root, ``GATE_EXIT`` otherwise."""
    uid, groups = current_identity()
    if uid == 0:
        return 0
    found = []
    for problem in problems(uid, groups, max_depth=GATE_DEPTH, mountinfo=mountinfo):
        found.append(problem)
        if len(found) >= REPORT_LIMIT:
            break
    if not found:
        return 0
    print(
        f"dlux: this container runs as uid {uid} (gid {os.getegid()}) and cannot use data it needs:",
        file=out,
    )
    for problem in found:
        print(
            f"  {problem['path']} ({problem['kind']}, owner {problem['owner']}, mode {problem['mode']}): "
            f"needs {problem['needs']}",
            file=out,
        )
    print(f"dlux: refusing to start. {FIX_HINT}", file=out)
    return GATE_EXIT


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    command = argv[0] if argv else "gate"
    if command == "gate":
        return gate()
    if command == "report":
        print(json.dumps(report(), indent=2, sort_keys=True))
        return 0
    print("usage: python -m dlux.mount_access [gate|report]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
