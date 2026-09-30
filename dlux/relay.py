"""Ask the Composer agent to make outbound calls for the project.

In a generated stack only ``composer-agent`` can reach the internet; ``web`` and
``celery`` cannot. Code that needs something from the outside world asks the agent
for a *named operation* through the runtime volume:

    celery  -> state/relay/requests/<uuid>.json
    agent   -> state/relay/results/<uuid>.json      (web and celery may read it)

Only ``celery`` may write: ``web`` mounts the volume read-only, so a web request
that needs a call queues a Celery task, exactly as any other slow work. A request
names an operation and its parameters, never a URL. The operation is either built
into Composer or declared by the project in ``relay/operations.json`` and approved
with ``composer relay approve``; see ``docs/outbound-requests.md``.

A secret (an API key) is sealed to a public key that only the agent holds, so it is
never on the volume in the clear.

    from dlux import relay
    data = relay.fetch('finance.cbl_page', secret=None, timeout=20)   # in a Celery task
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import uuid
from collections import namedtuple
from datetime import datetime, timedelta
from pathlib import Path

from django.utils import timezone

from django.conf import settings

from .updater.runtime import RuntimeStore, state_dir

SCHEMA_VERSION = 1
ALGORITHM = "x25519-hkdf-sha256-chacha20poly1305"
KDF_INFO = b"composer-relay-v1"
MAX_REQUEST_BYTES = 64 * 1024
DEFAULT_TTL = 60
POLL_SECONDS = 0.25
#: The agent republishes ``capabilities.json`` about once a minute; a document much
#: older than that means no agent is answering.
CAPABILITIES_MAX_AGE = 300

Ticket = namedtuple("Ticket", "id digest op")


class RelayError(Exception):
    """A relay call did not produce data. ``code`` is stable; ``detail`` is for people."""

    def __init__(self, code, detail=""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


def relay_root(store=None):
    return state_dir(store) / "relay"


def _read_json(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def capabilities(store=None):
    """What the agent says it can do, or ``{}`` when no agent is answering."""
    document = _read_json(relay_root(store) / "capabilities.json")
    if document.get("schema_version") != SCHEMA_VERSION:
        return {}
    try:
        age = (timezone.now() - datetime.fromisoformat(str(document.get("updated_at")))).total_seconds()
    except (ValueError, TypeError):
        return {}
    return document if age <= CAPABILITIES_MAX_AGE else {}


def available(operation, store=None):
    return operation in (capabilities(store).get("operations") or {})


def status(store=None):
    """A summary for the deployment views: is the relay answering, and what is on offer."""
    document = capabilities(store)
    return {
        "answering": bool(document),
        "composer": document.get("composer", ""),
        "operations": sorted((document.get("operations") or {})),
        "unapproved": list(document.get("unapproved") or []),
        "problems": list(document.get("problems") or []),
    }


def _why_unavailable(operation, document):
    if not document:
        return RelayError(
            "agent",
            "The Composer agent is not answering. It needs a Composer with the egress relay "
            "(1.6.0b1 or newer): run `./start.sh self update` then `./start.sh agent update`.",
        )
    if operation in (document.get("unapproved") or []):
        return RelayError("unapproved", f"{operation} is declared but not approved: run `composer relay approve` and redeploy relay/operations.lock.")
    for problem in document.get("problems") or []:
        if problem.get("name") == operation:
            return RelayError("invalid", f"{operation} is not valid: {problem.get('reason', '')}")
    return RelayError("unsupported", f"The agent offers no operation named {operation}.")


def seal(secret, operation_id, operation, public_key_document):
    """Seal ``secret`` to the agent's public key, bound to this request and operation."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    if public_key_document.get("algorithm") != ALGORITHM:
        raise RelayError("agent", "The agent seals with an algorithm this DjangoLux does not know.")
    recipient = base64.b64decode(public_key_document["public_key"], validate=True)
    ephemeral = X25519PrivateKey.generate()
    epk = ephemeral.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    shared = ephemeral.exchange(X25519PublicKey.from_public_bytes(recipient))
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=epk + recipient, info=KDF_INFO).derive(shared)
    nonce = os.urandom(12)
    ciphertext = ChaCha20Poly1305(key).encrypt(nonce, str(secret).encode("utf-8"), f"{operation_id}\0{operation}".encode())
    encode = lambda raw: base64.b64encode(raw).decode("ascii")
    return {"key_id": public_key_document["key_id"], "epk": encode(epk), "nonce": encode(nonce), "ct": encode(ciphertext)}


def submit(operation, params=None, *, secret=None, ttl=DEFAULT_TTL, store=None):
    """Write one request and return its ``Ticket``. Celery only: ``store`` is required.

    Refuses at once, with the reason, when the agent does not offer the operation,
    rather than leaving a request nobody will answer.
    """
    if store is None:
        raise RelayError("writer", "Only the Celery worker may write relay requests; queue a task from web.")
    document = capabilities(store)
    if operation not in (document.get("operations") or {}):
        raise _why_unavailable(operation, document)
    operation_id = str(uuid.uuid4())
    now = timezone.now()
    request = {
        "schema_version": SCHEMA_VERSION,
        "operation_id": operation_id,
        "op": operation,
        "params": dict(params or {}),
        "sealed": None,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=min(int(ttl), 120))).isoformat(),
    }
    if secret:
        key = _read_json(relay_root(store) / "public-key.json")
        if not key:
            raise RelayError("agent", "The agent has not published a relay key yet.")
        request["sealed"] = seal(secret, operation_id, operation, key)
    body = (json.dumps(request, sort_keys=True) + "\n").encode("utf-8")
    if len(body) > MAX_REQUEST_BYTES:
        raise RelayError("invalid", "The request is larger than the relay accepts.")
    path = relay_root(store) / "requests" / f"{operation_id}.json"
    try:
        _atomic_json(path, request)
    except OSError as exc:
        raise RelayError("writer", "This process cannot write to the runtime volume: run the call in a Celery task.") from exc
    return Ticket(operation_id, hashlib.sha256(path.read_bytes()).hexdigest(), operation)


def read_result(ticket, store=None):
    """The result for ``ticket``, or ``{}`` while unanswered.

    A result whose ``request_digest`` is not the one written is ignored, so a stale
    or misdirected document is never read as this request's answer.
    """
    result = _read_json(relay_root(store) / "results" / f"{ticket.id}.json")
    if not result or result.get("operation_id") != ticket.id:
        return {}
    if result.get("request_digest") not in (ticket.digest, ""):
        return {}
    return result


def wait(ticket, timeout=15, store=None, *, sleep=time.sleep, clock=time.monotonic):
    """Wait for the answer and return its data; raise ``RelayError`` with the agent's code."""
    deadline = clock() + timeout
    while True:
        result = read_result(ticket, store)
        if result:
            if store is not None:
                try:
                    (relay_root(store) / "results" / f"{ticket.id}.json").unlink(missing_ok=True)
                except OSError:
                    pass  # the agent sweeps results after five minutes
            if result.get("status") == "ok":
                return result.get("data")
            raise RelayError(str(result.get("error") or "provider"), str(result.get("detail") or ""))
        if clock() >= deadline:
            raise RelayError("timeout", "The agent did not answer in time. Is composer-agent running and up to date?")
        sleep(POLL_SECONDS)


def _writable_store():
    """The runtime volume, or a ``writer`` error where it cannot be written (web mounts it read-only).

    Built from ``updater.runtime`` rather than ``updater.service.runtime_store``: that module
    reaches back into tasks, and this one must stay a leaf (tests/test_import_graph.py).
    """
    root = getattr(settings, "DLUX_UPDATE_RUNTIME_ROOT", "/opt/dlux-runtime")
    try:
        return RuntimeStore(root).ensure()
    except OSError as exc:
        raise RelayError("writer", "The runtime volume is not writable here: run the call in a Celery task.") from exc


def fetch(operation, params=None, *, secret=None, timeout=15, ttl=DEFAULT_TTL, store=None):
    """Ask the agent and wait for the data. For a Celery task or management command."""
    if store is None:
        store = _writable_store()
    return wait(submit(operation, params, secret=secret, ttl=ttl, store=store), timeout, store)
