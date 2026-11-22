"""Writes on the runtime volume that the app and Composer share.

The worker and composer-agent both create and replace files under
``/opt/dlux-runtime``. The agent runs as uid 0 with no capabilities, so it gets
no permission override: it can only write into a directory through the
directory's group bits once the app runs as uid 10001 with group 0. Every
directory and file DjangoLux creates there is therefore group-writable,
whatever the process umask is, and temporary names carry the pid so a leftover
temporary file from another process can never block this one.

No Django import: the entrypoint permission gate and Composer's mirror of this
contract read the same constants.
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

SHARED_DIR_MODE = 0o775
SHARED_FILE_MODE = 0o664


def _set_mode(path, mode):
    """Best effort: only the owner may chmod, and an older root-owned entry is
    fixed by Composer's permission repair rather than here."""
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def ensure_dir(path):
    """Create ``path`` and any missing parents with group write."""
    path = Path(path)
    missing = []
    probe = path
    while not probe.exists() and probe != probe.parent:
        missing.append(probe)
        probe = probe.parent
    path.mkdir(parents=True, exist_ok=True)
    for created in reversed(missing):
        _set_mode(created, SHARED_DIR_MODE)
    return path


def _temporary_name(path):
    return path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")


def write_bytes(path, data, *, fsync=False):
    """Replace ``path`` atomically with ``data``; the result is group-writable."""
    path = Path(path)
    ensure_dir(path.parent)
    temporary = _temporary_name(path)
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, SHARED_FILE_MODE)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            os.fchmod(stream.fileno(), SHARED_FILE_MODE)
            stream.write(data)
            stream.flush()
            if fsync:
                os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise
    return path


def write_text(path, text, *, fsync=False):
    return write_bytes(path, str(text).encode("utf-8"), fsync=fsync)
