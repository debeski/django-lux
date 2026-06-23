"""Isolated, volume-backed DjangoLux update runtime."""

import os

from packaging.version import InvalidVersion, Version

UPDATER_SCHEMA_VERSION = 1


class UpdaterError(RuntimeError):
    """A safe, user-displayable updater failure."""


def get_baked_version():
    """Return the immutable image version captured before runtime activation."""
    from dlux import __version__

    raw = str(os.getenv("DLUX_BAKED_VERSION") or __version__).strip()
    try:
        return str(Version(raw))
    except InvalidVersion:
        return str(__version__)
