"""The .dlb container: key derivation, Fernet streaming, read/write/decrypt."""

import base64
import hashlib
import json
import secrets
import struct
import tempfile
from django.conf import settings


DLB_MAGIC = b"DLB1"


DLB_FORMAT_VERSION = 1


_CHUNK_SIZE = 32 * 1024 * 1024


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


def write_dlb_container(zip_fileobj, dest, metadata, *, passphrase=None, on_chunk=None):
    """Wrap an already-built backup zip stream into an encrypted .dlb container."""
    salt_hex = secrets.token_bytes(16).hex()
    has_passphrase = bool(_clean_passphrase(passphrase))
    encryption = {
        "scheme": "fernet-chunked",
        "kdf": "pbkdf2-sha256",
        "salt": salt_hex,
        "iterations": _PASSWORD_KDF_ITERATIONS,
        "key_source": "passphrase" if has_passphrase else "django-secret-key",
        "passphrase_required": has_passphrase,
    }
    metadata = dict(metadata or {})
    metadata.setdefault("format", DLB_FORMAT_VERSION)
    metadata.setdefault("kind", "dlux-system-backup")
    metadata["encryption"] = encryption
    payload = json.dumps(metadata, ensure_ascii=False).encode("utf-8")
    dest.write(DLB_MAGIC)
    dest.write(struct.pack(">I", len(payload)))
    dest.write(payload)
    _encrypt_stream(
        zip_fileobj, dest, salt_hex,
        encryption=encryption,
        passphrase=passphrase,
        on_chunk=on_chunk,
    )
    return metadata


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
