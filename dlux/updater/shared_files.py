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

import json
import os
import secrets
from pathlib import Path

# The supervisor runs before any release is importable, so the reader lives there.
from .supervisor import RefusedFile, read_bounded  # noqa: F401

SHARED_DIR_MODE = 0o775
SHARED_FILE_MODE = 0o664
#: The ceiling for one state document (pointer, ack, status, request) on the volume.
MAX_STATE_BYTES = 65536


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


def read_text(path, limit=MAX_STATE_BYTES):
    """``read_bounded`` decoded as UTF-8 (a decoding error is a ``ValueError``)."""
    return read_bounded(path, limit).decode("utf-8")


def load_json(path, limit=MAX_STATE_BYTES):
    """The JSON value in ``path`` through ``read_bounded``.

    Raises ``OSError`` when the file is missing, unreadable or refused, and
    ``ValueError`` when it is not JSON (a document nested too deep included), the
    same two families ``json.loads(path.read_text())`` raised.
    """
    data = read_bounded(path, limit)
    try:
        return json.loads(data.decode("utf-8"))
    except RecursionError as exc:
        raise ValueError("The document is nested too deeply.") from exc
