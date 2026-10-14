"""Declaring document files: `register_document_file()` and its soft-delete wiring."""

from . import DEFAULT_ACCEPT, get_file_type
from .specs import DocumentFileSpec, _specs, document_file_fields, get_document_file, registered_document_files  # noqa: F401


def register_document_file(model, field_name='pdf_file', *, accept=DEFAULT_ACCEPT, file_name=None, pdf_metadata=None,
                           can_access=None, queryset=None):
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
        pdf_metadata=pdf_metadata, can_access=can_access, queryset=queryset,
    )
    _specs[(model._meta.label_lower, field_name)] = spec
    _connect_history(model)
    return spec


def unregister_document_file(model, field_name='pdf_file'):
    """Remove a registration (tests and reloads)."""
    _specs.pop((model._meta.label_lower, field_name), None)
    if not document_file_fields(model):
        _disconnect_history(model)


def _connect_history(model):
    """Soft delete/restore of a document carries its file history (one connection per model)."""
    from dlux.models.soft_delete_signals import restored, soft_deleted

    from .history import cascade_restore, cascade_soft_delete

    uid = f'dlux.files:{model._meta.label_lower}'
    soft_deleted.connect(
        lambda sender, pks, deleted_at, deleted_by_id, **kwargs: cascade_soft_delete(sender, pks, deleted_at, deleted_by_id),
        sender=model, dispatch_uid=uid, weak=False,
    )
    restored.connect(
        lambda sender, deleted_at_by_pk, **kwargs: cascade_restore(sender, deleted_at_by_pk),
        sender=model, dispatch_uid=uid, weak=False,
    )


def _disconnect_history(model):
    from dlux.models.soft_delete_signals import restored, soft_deleted

    uid = f'dlux.files:{model._meta.label_lower}'
    soft_deleted.disconnect(sender=model, dispatch_uid=uid)
    restored.disconnect(sender=model, dispatch_uid=uid)
