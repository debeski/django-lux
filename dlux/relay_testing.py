"""A stand-in for the Composer agent, so project tests can exercise relay calls.

    with FakeAgent(state_dir, {'finance.cbl_page': lambda params, secret: '<html>...</html>'}) as agent:
        agent.step()                      # publishes capabilities and the public key
        ticket = relay.submit('finance.cbl_page', store=store)
        agent.step()                      # answers it
        assert relay.wait(ticket, store=store)

It reads and writes the same files the real agent does and opens sealed secrets with
its own key, so it fails the same way the real thing would on a malformed request.
Its handlers are plain callables; nothing here touches the network.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .relay import ALGORITHM, KDF_INFO, SCHEMA_VERSION, _atomic_json, relay_root


class FakeAgent:
    def __init__(self, state, handlers, *, operations=None, unapproved=(), problems=()):
        """``state`` is the runtime ``state`` directory or a ``RuntimeStore``."""
        self.root = relay_root(state) if hasattr(state, "state_dir") else Path(state) / "relay"
        self.handlers = dict(handlers)
        self.operations = operations or {name: {"response": "text", "auth": False, "params": []} for name in self.handlers}
        self.unapproved, self.problems = list(unapproved), list(problems)
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

        self._private = X25519PrivateKey.generate()
        self._public = self._private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self.key_id = hashlib.sha256(self._public).hexdigest()[:16]
        self.seen = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def _open(self, envelope, operation_id, operation):
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey
        from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF

        epk = base64.b64decode(envelope["epk"], validate=True)
        shared = self._private.exchange(X25519PublicKey.from_public_bytes(epk))
        key = HKDF(algorithm=hashes.SHA256(), length=32, salt=epk + self._public, info=KDF_INFO).derive(shared)
        return ChaCha20Poly1305(key).decrypt(
            base64.b64decode(envelope["nonce"], validate=True),
            base64.b64decode(envelope["ct"], validate=True),
            f"{operation_id}\0{operation}".encode(),
        ).decode("utf-8")

    def publish(self):
        now = datetime.now(timezone.utc).isoformat()
        _atomic_json(self.root / "public-key.json", {
            "schema_version": SCHEMA_VERSION, "algorithm": ALGORITHM, "key_id": self.key_id,
            "public_key": base64.b64encode(self._public).decode("ascii"), "published_at": now,
        })
        _atomic_json(self.root / "capabilities.json", {
            "schema_version": SCHEMA_VERSION, "composer": "fake", "algorithm": ALGORITHM, "key_id": self.key_id,
            "operations": self.operations, "unapproved": self.unapproved, "problems": self.problems, "updated_at": now,
        })

    def step(self):
        """Publish, then answer every waiting request. Returns how many it answered."""
        self.publish()
        (self.root / "requests").mkdir(parents=True, exist_ok=True)
        (self.root / "results").mkdir(parents=True, exist_ok=True)
        answered = 0
        for path in sorted((self.root / "requests").glob("*.json")):
            raw = path.read_bytes()
            request = json.loads(raw)
            operation_id, operation = request["operation_id"], request["op"]
            payload = {"schema_version": SCHEMA_VERSION, "operation_id": operation_id,
                       "request_digest": hashlib.sha256(raw).hexdigest(),
                       "completed_at": datetime.now(timezone.utc).isoformat()}
            try:
                secret = self._open(request["sealed"], operation_id, operation) if request.get("sealed") else None
                self.seen.append({"op": operation, "params": request.get("params", {}), "secret": secret})
                payload.update(status="ok", data=self.handlers[operation](request.get("params", {}), secret))
            except KeyError:
                payload.update(status="rejected", error="unsupported", detail="no such operation")
            except Exception as failure:  # noqa: BLE001 - a handler may raise its own error code
                payload.update(status="error", error=getattr(failure, "code", "provider"), detail=str(failure)[:200])
            _atomic_json(self.root / "results" / f"{operation_id}.json", payload)
            path.unlink()
            answered += 1
        return answered
