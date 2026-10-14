"""Which model fields are document files, and how each one behaves."""

from dataclasses import dataclass
from typing import Callable, Optional

from . import DEFAULT_ACCEPT, get_file_type


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

    @property
    def key(self):
        return f'{self.model._meta.app_label}.{self.model._meta.model_name}.{self.field_name}'


_specs = {}


def register_document_file(model, field_name='pdf_file', *, accept=DEFAULT_ACCEPT, file_name=None, pdf_metadata=None, can_access=None):
    """Declare ``model.field_name`` a document file.

    One call connects the file card, the viewer, the page editor, file history,
    downloads and Scan for that field. Call it once, from the app's
    ``dlux_options.py`` or ``AppConfig.ready()``.
    """
    from django.db import models as django_models

    field = model._meta.get_field(field_name)
    if not isinstance(field, django_models.FileField):
        raise TypeError(f'{model.__name__}.{field_name} is not a FileField.')
    for name in accept:
        get_file_type(name)
    spec = DocumentFileSpec(
        model=model, field_name=field_name, accept=tuple(accept), file_name=file_name,
        pdf_metadata=pdf_metadata, can_access=can_access,
    )
    _specs[(model._meta.label_lower, field_name)] = spec
    return spec


def get_document_file(model_or_instance, field_name='pdf_file'):
    meta = model_or_instance._meta
    return _specs.get((meta.label_lower, field_name))


def document_file_fields(model_or_instance):
    label = model_or_instance._meta.label_lower
    return [spec for (model_label, _), spec in _specs.items() if model_label == label]


def registered_document_files():
    return list(_specs.values())


def unregister_document_file(model, field_name='pdf_file'):
    """Remove a registration (tests and reloads)."""
    _specs.pop((model._meta.label_lower, field_name), None)
