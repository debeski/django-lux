"""Backward-compatibility shim for the public ``dlux.constants`` import surface.

The canonical definitions now live in :mod:`dlux.system.constants`. This module
re-exports every public constant so existing downstream imports
(``from dlux.constants import DEFAULT_TABLE_PAGE_SIZE``) keep working.

New code should import from :mod:`dlux.system` / :mod:`dlux.system.constants`
directly; this alias exists only to preserve the released public API.
"""

from .system import constants as _constants
from .system.constants import *  # noqa: F401,F403

__all__ = list(_constants.__all__)
