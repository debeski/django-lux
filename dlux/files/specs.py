"""Registered document files (pure data): which model fields they are and how they behave.

Kept free of behaviour so the history service and the registry can both read it
without depending on each other.
"""

from dataclasses import dataclass
from typing import Callable, Optional

from . import DEFAULT_ACCEPT


@dataclass(frozen=True)
class DocumentFileSpec:
    model: type
    field_name: str
    accept: tuple = DEFAULT_ACCEPT
    #: ``file_name(document, field_name) -> str``: storage name (under the field's
    #: ``upload_to`` directory unless it contains a ``/``) for the current file.
    file_name: Optional[Callable] = None
    #: ``pdf_metadata(document) -> dict`` of PDF document info (``/Title`` …).
    pdf_metadata: Optional[Callable] = None
    #: ``can_access(request, document, action) -> bool | None``; ``True`` grants,
    #: ``False`` refuses, ``None`` falls back to the standard permission check.
    can_access: Optional[Callable] = None
    #: ``queryset(request, model) -> QuerySet`` the document is looked up in;
    #: defaults to the dynamic modal's scope- and access-filtered set.
    queryset: Optional[Callable] = None
    #: Read the file's text with OCR when OCR is enabled in Options (``False`` opts out).
    ocr: bool = True

    @property
    def key(self):
        return f'{self.model._meta.app_label}.{self.model._meta.model_name}.{self.field_name}'


_specs = {}


def get_document_file(model_or_instance, field_name='pdf_file'):
    meta = model_or_instance._meta
    return _specs.get((meta.label_lower, field_name))


def document_file_fields(model_or_instance):
    label = model_or_instance._meta.label_lower
    return [spec for (model_label, _), spec in _specs.items() if model_label == label]


def registered_document_files():
    return list(_specs.values())
