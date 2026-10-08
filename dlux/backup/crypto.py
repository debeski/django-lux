"""The .dlb container: key derivation, Fernet streaming, read/write/decrypt."""

import base64
import hashlib
import io
import json
import queue
import secrets
import shutil
import struct
import tempfile
import threading
from django.conf import settings


DLB_MAGIC = b"DLB1"


DLB_FORMAT_VERSION = 1


_CHUNK_SIZE = 32 * 1024 * 1024


# Frames written by the streaming writer. Smaller than ``_CHUNK_SIZE`` so the
# encrypting thread starts early and two in-flight frames bound memory; readers
# take any frame length from its prefix.
_STREAM_CHUNK_SIZE = 8 * 1024 * 1024


ENCRYPTION_PASSPHRASE = "passphrase"
ENCRYPTION_SERVER_KEY = "server_key"
ENCRYPTION_NONE = "none"
ENCRYPTION_MODES = (ENCRYPTION_PASSPHRASE, ENCRYPTION_SERVER_KEY, ENCRYPTION_NONE)


SCHEME_NONE = "none"


_PASSWORD_KDF_ITERATIONS = 390_000


def _clean_passphrase(passphrase):
    value = "" if passphrase is None else str(passphrase)
    return value.strip()


def _django_secret_key_seed():
    return str(getattr(settings, "SECRET_KEY", "") or "dlux-backup-secret-dev-key")


def _derive_backup_key(salt_hex, *, encryption=None, passphrase=None):
    salt = bytes.fromhex(salt_hex)
    encryption = encryption or {}
    kdf = encryption.get("kdf")
    key_source = encryption.get("key_source")

    # Backward-compatible reader for early unreleased DLB1 files. Only Django
    # SECRET_KEY is used for this legacy key source.
    if kdf == "sha256-salt-seed":
        return hashlib.sha256(salt + _django_secret_key_seed().encode("utf-8")).digest()

    if key_source == "passphrase":
        seed = _clean_passphrase(passphrase)
        if not seed:
            raise ValueError("Backup passphrase is required")
    else:
        seed = _django_secret_key_seed()

    iterations = int(encryption.get("iterations") or _PASSWORD_KDF_ITERATIONS)
    return hashlib.pbkdf2_hmac("sha256", seed.encode("utf-8"), salt, iterations, dklen=32)


def _backup_fernet(salt_hex, *, encryption=None, passphrase=None):
    from cryptography.fernet import Fernet

    digest = _derive_backup_key(salt_hex, encryption=encryption, passphrase=passphrase)
    return Fernet(base64.urlsafe_b64encode(digest))


def _encrypt_stream(src, dest, salt_hex, *, encryption, passphrase=None, on_chunk=None):
    fernet = _backup_fernet(salt_hex, encryption=encryption, passphrase=passphrase)
    written = 0
    while True:
        chunk = src.read(_CHUNK_SIZE)
        if not chunk:
            break
        token = fernet.encrypt(chunk)
        dest.write(struct.pack(">Q", len(token)))
        dest.write(token)
        written += len(chunk)
        if on_chunk:
            on_chunk(written)


def _decrypt_stream(src, dest, salt_hex, *, encryption, passphrase=None, on_chunk=None):
    fernet = _backup_fernet(salt_hex, encryption=encryption, passphrase=passphrase)
    consumed = 0
    while True:
        header = src.read(8)
        if not header:
            break
        if len(header) != 8:
            raise ValueError("Truncated backup container")
        (length,) = struct.unpack(">Q", header)
        token = src.read(length)
        if len(token) != length:
            raise ValueError("Truncated backup container")
        dest.write(fernet.decrypt(token))
        consumed += len(header) + length
        if on_chunk:
            on_chunk(consumed)


def _encryption_block(*, passphrase=None, encrypt=True):
    if not encrypt:
        return {"scheme": SCHEME_NONE, "key_source": "none", "passphrase_required": False}
    has_passphrase = bool(_clean_passphrase(passphrase))
    return {
        "scheme": "fernet-chunked",
        "kdf": "pbkdf2-sha256",
        "salt": secrets.token_bytes(16).hex(),
        "iterations": _PASSWORD_KDF_ITERATIONS,
        "key_source": "passphrase" if has_passphrase else "django-secret-key",
        "passphrase_required": has_passphrase,
    }


class DlbPayloadWriter:
    """Write-only stream that encrypts the inner ZIP while it is being built.

    ``zipfile`` writes into this object; full frames are handed to one worker
    thread that encrypts them (OpenSSL releases the GIL) and appends them, in
    order, to a temporary payload file. Serialization and encryption therefore
    overlap instead of running as two passes over the whole archive. The header
    is written last by ``finish()``, once the row and file counts are known.

    ``seek`` is unsupported on purpose: ``zipfile`` then writes data descriptors
    and never rewinds into bytes that may already be encrypted.
    """

    def __init__(self, *, passphrase=None, encrypt=True, on_chunk=None, chunk_size=_STREAM_CHUNK_SIZE):
        self.encryption = _encryption_block(passphrase=passphrase, encrypt=encrypt)
        self._fernet = None
        if encrypt:
            self._fernet = _backup_fernet(
                self.encryption["salt"], encryption=self.encryption, passphrase=passphrase,
            )
        self._payload = tempfile.TemporaryFile()
        self._buffer = bytearray()
        self._chunk_size = chunk_size
        self._position = 0
        self._processed = 0
        self._on_chunk = on_chunk
        self._error = None
        self._closed = False
        self._queue = queue.Queue(maxsize=2)
        self._thread = threading.Thread(target=self._drain, name="dlb-encrypt", daemon=True)
        self._thread.start()

    def _drain(self):
        while True:
            chunk = self._queue.get()
            if chunk is None:
                return
            if self._error is not None:
                continue
            try:
                if self._fernet is None:
                    self._payload.write(chunk)
                else:
                    token = self._fernet.encrypt(bytes(chunk))
                    self._payload.write(struct.pack(">Q", len(token)))
                    self._payload.write(token)
                self._processed += len(chunk)
            except Exception as exc:
                self._error = exc

    def _submit(self, chunk):
        if self._error is not None:
            raise self._error
        self._queue.put(chunk)
        if self._on_chunk:
            self._on_chunk(self._position)

    def writable(self):
        return True

    def seekable(self):
        return False

    def seek(self, *args):
        raise io.UnsupportedOperation("seek")

    def tell(self):
        return self._position

    def write(self, data):
        if self._closed:
            raise ValueError("write to a finished backup payload")
        self._buffer += data
        self._position += len(data)
        while len(self._buffer) >= self._chunk_size:
            chunk = bytes(self._buffer[:self._chunk_size])
            del self._buffer[:self._chunk_size]
            self._submit(chunk)
        return len(data)

    def flush(self):
        pass

    @property
    def size(self):
        """Plaintext bytes written so far (the inner ZIP's size once finished)."""
        return self._position

    def _close_worker(self):
        if self._closed:
            return
        self._closed = True
        if self._buffer and self._error is None:
            self._queue.put(bytes(self._buffer))
            self._buffer.clear()
        self._queue.put(None)
        self._thread.join()

    def finish(self, dest, metadata):
        """Write header + payload into ``dest``; returns the header metadata."""
        self._close_worker()
        if self._error is not None:
            raise self._error
        metadata = dict(metadata or {})
        metadata.setdefault("format", DLB_FORMAT_VERSION)
        metadata.setdefault("kind", "dlux-system-backup")
        metadata["encryption"] = self.encryption
        metadata["passphrase_required"] = bool(self.encryption.get("passphrase_required"))
        payload = json.dumps(metadata, ensure_ascii=False).encode("utf-8")
        dest.write(DLB_MAGIC)
        dest.write(struct.pack(">I", len(payload)))
        dest.write(payload)
        self._payload.seek(0)
        shutil.copyfileobj(self._payload, dest, 4 * 1024 * 1024)
        self._payload.close()
        return metadata

    def abort(self):
        self._close_worker()
        self._payload.close()

    def close(self):
        self.abort()


def write_dlb_container(zip_fileobj, dest, metadata, *, passphrase=None, on_chunk=None, encrypt=True):
    """Wrap an already-built backup zip stream into a .dlb container."""
    writer = DlbPayloadWriter(passphrase=passphrase, encrypt=encrypt, chunk_size=_CHUNK_SIZE)
    try:
        while True:
            chunk = zip_fileobj.read(_CHUNK_SIZE)
            if not chunk:
                break
            writer.write(chunk)
            if on_chunk:
                on_chunk(writer.size)
        return writer.finish(dest, metadata)
    except BaseException:
        writer.abort()
        raise


def _copy_plain_payload(src, dest, *, on_chunk=None):
    consumed = 0
    while True:
        chunk = src.read(_CHUNK_SIZE)
        if not chunk:
            break
        dest.write(chunk)
        consumed += len(chunk)
        if on_chunk:
            on_chunk(consumed)


def read_dlb_metadata(fileobj):
    """Read and return the cleartext metadata header; leaves the stream at the payload."""
    magic = fileobj.read(len(DLB_MAGIC))
    if magic != DLB_MAGIC:
        raise ValueError("Not a Dlux backup (.dlb) file")
    (length,) = struct.unpack(">I", fileobj.read(4))
    if length <= 0 or length > 10 * 1024 * 1024:
        raise ValueError("Corrupt backup metadata header")
    metadata = json.loads(fileobj.read(length).decode("utf-8"))
    if metadata.get("kind") != "dlux-system-backup":
        raise ValueError("Unsupported backup kind")
    return metadata


def decrypt_dlb_to_tempfile(fileobj, *, passphrase=None, on_chunk=None):
    """Decrypt an .dlb stream (positioned anywhere) into a temp zip file.

    Returns ``(metadata, tempfile)`` with the temp file positioned at 0.
    The caller owns closing the temp file. ``on_chunk`` receives the number of
    encrypted bytes consumed so far, so a caller that knows the container size
    can report progress across what is the longest phase of a large restore.
    """
    fileobj.seek(0)
    metadata = read_dlb_metadata(fileobj)
    encryption = metadata.get("encryption") or {}
    if encryption.get("scheme") == SCHEME_NONE:
        tmp = tempfile.TemporaryFile()
        try:
            _copy_plain_payload(fileobj, tmp, on_chunk=on_chunk)
        except Exception:
            tmp.close()
            raise
        tmp.seek(0)
        return metadata, tmp
    salt_hex = str(encryption.get("salt") or "")
    if not salt_hex:
        raise ValueError("Backup metadata is missing encryption parameters")
    tmp = tempfile.TemporaryFile()
    try:
        _decrypt_stream(
            fileobj, tmp, salt_hex,
            encryption=encryption,
            passphrase=passphrase,
            on_chunk=on_chunk,
        )
    except Exception:
        tmp.close()
        raise
    tmp.seek(0)
    return metadata, tmp
