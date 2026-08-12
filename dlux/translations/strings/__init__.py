"""Bundled interface strings, one module per language."""

from .ar import STRINGS as ARABIC
from .en import STRINGS as ENGLISH

DLUX_STRINGS = {
    'ar': ARABIC,
    'en': ENGLISH,
}

__all__ = ['DLUX_STRINGS', 'ARABIC', 'ENGLISH']
