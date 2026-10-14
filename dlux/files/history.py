"""Saving document files with history: the previous file is always kept byte-for-byte.

Every write goes to a new storage name; nothing is overwritten. Database rows
are written inside the caller's transaction, but storage writes cannot be rolled
back, so a failure leaves at worst an unreferenced new file, never a lost one.
"""

import os
from io import BytesIO

from django.core.files.base import ContentFile

from .specs import get_document_file


def _messages(key, default):
    from dlux.translations import get_strings

    return str(get_strings().get(key, default))


def _content_type(document):
    from django.contrib.contenttypes.models import ContentType

    return ContentType.objects.get_for_model(document.__class__)


def versions_for(document, field_name='pdf_file'):
    """History rows for one document field, newest first (soft-deleted rows excluded)."""
    from dlux.models import FileVersion

    return FileVersion.all_objects.filter(
        content_type=_content_type(document), object_id=document.pk, field_name=field_name, deleted_at__isnull=True,
    ).order_by('-version_number')


def next_version_number(document, field_name='pdf_file'):
    from dlux.models import FileVersion

    latest = (
        FileVersion.all_objects.filter(content_type=_content_type(document), object_id=document.pk, field_name=field_name)
        .order_by('-version_number').values_list('version_number', flat=True).first()
    )
    return (latest or 0) + 1


def default_pdf_metadata(document):
    return {'/Title': str(document), '/Subject': document._meta.verbose_name.title()}


def write_pdf_metadata(pdf_bytes, document, field_name='pdf_file'):
    """Return ``(pdf bytes with document info, page count)``; existing info keys are kept unless replaced.

    The output is cleaned up losslessly (`optimize_pdf_writer`), so every save stores a compact file.
    """
    from pypdf import PdfReader, PdfWriter

    spec = get_document_file(document, field_name)
    metadata = (spec.pdf_metadata if spec and spec.pdf_metadata else default_pdf_metadata)(document)
    reader = PdfReader(BytesIO(pdf_bytes))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    info = {str(key): str(value) for key, value in (reader.metadata or {}).items() if value is not None}
    info.update({key: str(value) for key, value in metadata.items() if value is not None})
    writer.add_metadata(info)
    from dlux.pdf.assembly import optimize_pdf_writer

    optimize_pdf_writer(writer)
    output = BytesIO()
    writer.write(output)
    return output.getvalue(), len(reader.pages)


def target_name(document, field_name='pdf_file'):
    """Storage name the current file should have (the storage adds a suffix if taken)."""
    spec = get_document_file(document, field_name)
    file_field = getattr(document, field_name)
    if spec and spec.file_name:
        name = spec.file_name(document, field_name)
        if '/' in name:
            return name
        return file_field.field.generate_filename(document, name)
    return file_field.field.generate_filename(document, f'{document._meta.model_name}_{document.pk}.pdf')


def _page_count(data):
    try:
        from pypdf import PdfReader

        return len(PdfReader(BytesIO(data)).pages)
    except Exception:
        return 0


def archive_previous(document, previous_name, *, field_name='pdf_file', user=None, action_type='replace', active_name_after=''):
    """Copy the file at `previous_name` into a new history row. Returns the row, or ``None`` without a previous file."""
    from dlux.models import FileVersion

    if not previous_name:
        return None
    storage = getattr(document, field_name).storage
    if not storage.exists(previous_name):
        raise ValueError(_messages('files_original_missing', 'The original file is missing; restore it before replacing it.'))
    with storage.open(previous_name, 'rb') as stream:
        data = stream.read()
    version = FileVersion(
        content_type=_content_type(document), object_id=document.pk, document_model=document.__class__.__name__,
        field_name=field_name, version_number=next_version_number(document, field_name), action_type=action_type,
        active_name_before=previous_name, active_name_after=active_name_after, page_count=_page_count(data),
        scope_id=getattr(document, 'scope_id', None),
        metadata={'title': str(document)},
    )
    version.archived_file.save(os.path.basename(previous_name), ContentFile(data), save=False)
    if user is not None and getattr(user, 'is_authenticated', False):
        version.created_by = version.updated_by = user
    version.save()
    if version.scope_id != getattr(document, 'scope_id', None):
        # ScopedModel.save() fills an empty scope from the acting user; history follows the document.
        FileVersion.all_objects.filter(pk=version.pk).update(scope_id=getattr(document, 'scope_id', None))
    return version


def _store(document, field_name, data, user, extra_update=()):
    file_field = getattr(document, field_name)
    saved = file_field.storage.save(target_name(document, field_name), ContentFile(data), max_length=file_field.field.max_length)
    file_field.name = saved
    update_fields = [file_field.field.attname, *extra_update]
    if hasattr(document, 'updated_at'):
        update_fields.append('updated_at')
    if user is not None and getattr(user, 'is_authenticated', False) and hasattr(document, 'updated_by'):
        document.updated_by = user
        update_fields.append('updated_by')
    document.save(update_fields=update_fields)
    return saved


def save_new_version(document, pdf_bytes, *, field_name='pdf_file', user=None, action_type='edit'):
    """Make `pdf_bytes` the document's current file and keep the previous one in history.

    Used by the page editor. Returns ``(new storage name, page count)``.
    """
    previous = getattr(document, field_name).name or ''
    data, page_count = write_pdf_metadata(pdf_bytes, document, field_name)
    version = archive_previous(document, previous, field_name=field_name, user=user, action_type=action_type)
    saved = _store(document, field_name, data, user)
    if version:
        version.active_name_after = saved
        version.save(update_fields=['active_name_after'])
    return saved, page_count


def record_upload(document, previous_name, *, field_name='pdf_file', user=None):
    """After a form saved a new upload (or cleared the field), keep the replaced file and tidy the new one.

    The replaced file goes to history (``replace``, or ``clear`` when the field is
    now empty). A new PDF gets the document's metadata and its target name; an
    accepted image is converted into that PDF and the uploaded image removed.
    """
    file_field = getattr(document, field_name)
    current = file_field.name or ''
    if current == previous_name:
        return None
    version = archive_previous(
        document, previous_name, field_name=field_name, user=user,
        action_type='replace' if current else 'clear', active_name_after=current,
    )
    if current and file_field.storage.exists(current):
        from . import detect_file_type, to_pdf_bytes

        with file_field.storage.open(current, 'rb') as stream:
            data = stream.read()
        spec = get_document_file(document, field_name)
        accept = spec.accept if spec else ('pdf',)
        try:
            kind = detect_file_type(data, current, accept)
        except ValueError:
            return version
        if kind.name != 'pdf':
            if kind.to_pdf is None:
                return version
            # An accepted image becomes the document's PDF; the uploaded image is not kept (D3).
            data = to_pdf_bytes(data, current, accept)
        data, _ = write_pdf_metadata(data, document, field_name)
        saved = _store(document, field_name, data, user)
        if kind.name != 'pdf':
            file_field.storage.delete(current)
        if version:
            version.active_name_after = saved
            version.save(update_fields=['active_name_after'])
    return version


def cascade_soft_delete(model, pks, deleted_at, deleted_by_id):
    """Soft-delete the history of soft-deleted documents with the same time and actor."""
    from dlux.models import FileVersion

    if not pks:
        return 0
    from django.contrib.contenttypes.models import ContentType

    return FileVersion.all_objects.filter(
        content_type=ContentType.objects.get_for_model(model), object_id__in=list(pks), deleted_at__isnull=True,
    ).update(deleted_at=deleted_at, deleted_by_id=deleted_by_id)


def cascade_restore(model, deleted_at_by_pk):
    """Restore the history rows deleted together with each restored document (matched on ``deleted_at``)."""
    from django.contrib.contenttypes.models import ContentType

    from dlux.models import FileVersion

    content_type = ContentType.objects.get_for_model(model)
    restored = 0
    for pk, deleted_at in deleted_at_by_pk.items():
        if deleted_at is None:
            continue
        restored += FileVersion.all_objects.filter(
            content_type=content_type, object_id=pk, deleted_at=deleted_at,
        ).update(deleted_at=None, deleted_by=None)
    return restored

