"""The deployment update policy: which update paths this deployment allows.

``DLUX_UPDATE_POLICY`` (in ``.secrets/.env``) is read by web, the task worker and
the resident Composer pair, and each side refuses what it does not allow:

- ``all``: every update path (the default);
- ``inline``: DjangoLux inline runtime updates only, no application-image or
  Composer updates;
- ``none``: no updates at all.

Checks, rollbacks and the operator's own shell commands stay allowed under every
value. An unknown value counts as ``none``: a typo must never allow more than the
operator meant.

The resident Composer reports the policy it enforces in ``agent-status.json``. The
pair is recreated only by ``./start.sh up`` or ``agent update``, so after an edit
it can still run on the old value; DjangoLux then takes the stricter of the two,
because that is what Composer refuses anyway, and says so.
"""

from __future__ import annotations

import os

from django.conf import settings

from .channel import _read_json
from .runtime import state_dir

ALL = "all"
INLINE = "inline"
NONE = "none"
POLICIES = (ALL, INLINE, NONE)
_RANK = {ALL: 0, INLINE: 1, NONE: 2}

INLINE_UPDATE = "inline"
IMAGE_UPDATE = "image"
COMPOSER_UPDATE = "composer"
_ALLOWED = {
    ALL: {INLINE_UPDATE, IMAGE_UPDATE, COMPOSER_UPDATE},
    INLINE: {INLINE_UPDATE},
    NONE: set(),
}


def normalize(value):
    """``(policy, valid)``: empty means ``all``; anything unknown means ``none``."""
    text = str(value if value is not None else "").strip().lower()
    if not text:
        return ALL, True
    if text in POLICIES:
        return text, True
    return NONE, False


def configured_raw():
    return str(getattr(settings, "DLUX_UPDATE_POLICY", os.getenv("DLUX_UPDATE_POLICY", "")) or "")


def configured_policy():
    return normalize(configured_raw())[0]


def resident_policy(store=None):
    """The policy the resident Composer reports enforcing, or ``""`` when it
    does not report one (no agent, or a Composer older than 1.11.0)."""
    try:
        status = _read_json(state_dir(store) / "agent" / "agent-status.json")
    except Exception:
        return ""
    raw = status.get("update_policy") if isinstance(status, dict) else None
    if raw is None:
        return ""
    return normalize(raw)[0]


def effective_policy(store=None):
    web = configured_policy()
    resident = resident_policy(store)
    if resident and _RANK[resident] > _RANK[web]:
        return resident
    return web


def allows(kind, store=None):
    return kind in _ALLOWED[effective_policy(store)]


def refusal(kind):
    what = {
        INLINE_UPDATE: "Inline DjangoLux updates",
        IMAGE_UPDATE: "Application image updates",
        COMPOSER_UPDATE: "Composer updates",
    }[kind]
    return (
        f"{what} are turned off by this deployment's update policy "
        f"(DLUX_UPDATE_POLICY={effective_policy()}). Deploy from the server instead."
    )


def status(store=None):
    """What the Updates card and the doctor report about the policy."""
    raw = configured_raw()
    web, valid = normalize(raw)
    resident = resident_policy(store)
    effective = effective_policy(store)
    return {
        "policy": effective,
        "configured": web,
        "configured_valid": valid,
        "resident": resident,
        "mismatch": bool(resident) and resident != web,
        # Web restricts, but no Composer says it enforces it: a compromised web
        # could still write the image trigger.
        "resident_unenforced": not resident and effective != ALL,
        "allows_inline": INLINE_UPDATE in _ALLOWED[effective],
        "allows_image": IMAGE_UPDATE in _ALLOWED[effective],
        "allows_composer": COMPOSER_UPDATE in _ALLOWED[effective],
    }
