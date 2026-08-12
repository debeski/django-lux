"""Dlux translations.

Facade: `DLUX_STRINGS` and every runtime helper stay importable from
`dlux.translations`, as before the package split.
"""

from .strings import DLUX_STRINGS  # noqa: F401
from .runtime import (  # noqa: F401
    logger,
    MigrationSafeTranslation,
    build_translation_matrix,
    build_translation_matrix_groups,
    discover_translation_languages,
    get_current_language_code,
    get_strings,
    lazy_translator,
    resolve_model_label,
    resolve_translation_key_for_text,
    _build_translation_matrix_row,
    _discover_and_merge_translations,
    _discover_translation_source_layers,
    _enabled_language_codes,
    _normalize_translation_lookup_text,
    _translation_layer_keys,
    _translation_reverse_index,
)

__all__ = ['DLUX_STRINGS'] + [
    'MigrationSafeTranslation',
    'build_translation_matrix',
    'build_translation_matrix_groups',
    'discover_translation_languages',
    'get_current_language_code',
    'get_strings',
    'lazy_translator',
    'resolve_model_label',
    'resolve_translation_key_for_text',
]
