"""Which releases this deployment is willing to install.

Stable is the default and excludes every prerelease. Beta is a persistent,
explicit opt-in that additionally admits ``bN``/``rcN`` releases — it is a
*widening* of eligibility, never a relaxation of verification: digest,
attestation, manifest and migration checks are identical on both channels.

Three processes need the same answer and none of them can be the sole owner:

* the Options UI runs on ``web``, which mounts the runtime volume read-only;
* the Celery worker owns the write side of that volume;
* Composer resolves the actual candidate and never touches the database.

So the database column is where the administrator's choice is recorded, and
``state/channel-policy.json`` on the runtime volume is the published mirror
Composer reads. Celery is the only writer of that file. Anything that cannot
write it — the web container, and Composer's host CLI — submits a request that
Celery applies and acknowledges, exactly as package and image updates already do.

Failure modes are deliberate: a missing policy file reads as *stable*, because a
deployment that has never opted in must never be handed a prerelease; a
malformed one reads as stable too but reports the error, so beta cannot be
activated by corrupting a file.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from django.utils import timezone

from . import UpdaterError
from .runtime import state_dir


STABLE = "stable"
BETA = "beta"
CHANNELS = (STABLE, BETA)

#: Bump only for an incompatible shape change. An older updater that meets a
#: newer schema refuses beta rather than guessing at fields it cannot read.
POLICY_SCHEMA_VERSION = 1

POLICY_FILENAME = "channel-policy.json"
REQUEST_FILENAME = "channel-request.json"
ACK_FILENAME = f"{REQUEST_FILENAME}.ack"


def normalize_channel(value):
    """Coerce free text to a known channel, or raise. Never guesses beta."""
    text = str(value or "").strip().lower()
    if text not in CHANNELS:
        raise UpdaterError(
            f"'{value}' is not a DjangoLux release channel; expected one of: "
            + ", ".join(CHANNELS)
            + "."
        )
    return text


def prereleases_allowed(channel):
    """The single place that turns a channel name into an eligibility rule."""
    return str(channel or "").strip().lower() == BETA


def policy_path(store=None):
    return state_dir(store) / POLICY_FILENAME


def request_path(store=None):
    return state_dir(store) / REQUEST_FILENAME


def ack_path(store=None):
    return state_dir(store) / ACK_FILENAME


def read_policy(store=None):
    """The published policy as ``(channel, error)``.

    ``error`` is non-empty when the file exists but cannot be trusted. The
    channel is *always* a usable value, and is ``stable`` whenever there is any
    doubt — callers act on the channel and surface the error, rather than having
    to handle an exception on a read that happens on every update check.
    """
    path = policy_path(store)
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        # Never published, or a deployment that predates channels. Stable.
        return STABLE, ""
    except OSError as exc:
        return STABLE, f"The release channel policy could not be read ({exc.strerror or exc})."
    try:
        data = json.loads(raw)
    except ValueError:
        return STABLE, "The release channel policy is not valid JSON."
    if not isinstance(data, dict):
        return STABLE, "The release channel policy is not an object."
    schema = data.get("schema_version")
    if type(schema) is not int or schema < 1:
        return STABLE, "The release channel policy has an invalid schema version."
    if schema > POLICY_SCHEMA_VERSION:
        return STABLE, (
            f"The release channel policy uses schema {schema}, which this DjangoLux "
            "release does not understand; staying on the stable channel."
        )
    channel = str(data.get("channel") or "").strip().lower()
    if channel not in CHANNELS:
        return STABLE, "The release channel policy names an unknown channel."
    return channel, ""


def publish_policy(store, channel, *, source="", token=""):
    """Write the policy file atomically. Celery only — ``store`` is required.

    Passing an ensured store is the whole guard: the read-only web mount cannot
    produce one, so this cannot be called from a process that has no business
    writing it.
    """
    if store is None:
        raise UpdaterError("Publishing the release channel policy requires the runtime store.")
    channel = normalize_channel(channel)
    payload = {
        "schema_version": POLICY_SCHEMA_VERSION,
        "channel": channel,
        "published_at": timezone.now().isoformat(),
    }
    if source:
        payload["source"] = str(source)[:200]
    if token:
        payload["token"] = str(token)[:64]
    _atomic_json(policy_path(store), payload)
    return payload


def write_request(channel, *, store=None, requested_by="", token=""):
    """Ask the worker to change the channel. Written by web, or by Composer.

    Mirrors ``package_request.write_request``: a token the applier echoes into
    an ack, so a caller can tell "not picked up yet" from "applied" from
    "refused", instead of watching a value that may never change.
    """
    channel = normalize_channel(channel)
    token = str(token or uuid.uuid4())
    payload = {
        "schema_version": POLICY_SCHEMA_VERSION,
        "token": token,
        "channel": channel,
        "requested_at": timezone.now().isoformat(),
        "requested_by": str(requested_by or "")[:150],
    }
    _atomic_json(request_path(store), payload)
    return payload


def read_request(store=None):
    return _read_json(request_path(store))


def read_ack(store=None):
    return _read_json(ack_path(store))


def write_ack(store, *, token, channel, applied=True, error=""):
    if store is None:
        raise UpdaterError("Acknowledging a channel request requires the runtime store.")
    payload = {
        "schema_version": POLICY_SCHEMA_VERSION,
        "token": str(token or "")[:64],
        "channel": str(channel or ""),
        "applied": bool(applied),
        "acknowledged_at": timezone.now().isoformat(),
    }
    if error:
        payload["error"] = str(error)[:1000]
    _atomic_json(ack_path(store), payload)
    return payload


def pending_request(store=None):
    """The channel of a request the worker has not acknowledged yet, or ``''``."""
    request = read_request(store)
    token = str(request.get("token") or "").strip()
    if not token:
        return ""
    if str(read_ack(store).get("token") or "").strip() == token:
        return ""
    channel = str(request.get("channel") or "").strip().lower()
    return channel if channel in CHANNELS else ""


def clear_request(store=None):
    """Drop a request file that is no longer relevant. Missing is success."""
    try:
        os.unlink(request_path(store))
    except FileNotFoundError:
        pass
    except OSError:
        pass


def _read_json(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path
