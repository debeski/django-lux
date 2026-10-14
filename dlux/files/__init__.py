"""Document files: accepted file types, page conversion and (later) history and wiring.

A *file type* says which uploads a document field takes, how to recognise one by
its content, and how to turn it into PDF pages. PDF and common image formats are
built in; a project adds its own with `register_file_type()`.
"""

from dataclasses import dataclass, field
from typing import Callable, Optional

DEFAULT_ACCEPT = ('pdf', 'image')


@dataclass(frozen=True)
class FileType:
    name: str
    extensions: tuple
    mime_types: tuple = ()
    sniff: Optional[Callable[[bytes], bool]] = None
    to_pdf: Optional[Callable[[bytes], bytes]] = None
    label_key: str = ''
    label: str = ''
    max_bytes: Optional[int] = field(default=None)


_registry = {}


def register_file_type(name, *, extensions, mime_types=(), sniff=None, to_pdf=None, label_key='', label='', max_bytes=None):
    """Register (or replace) an accepted file kind.

    `sniff(data)` must confirm the content really is this kind; the extension alone
    is never trusted. `to_pdf(data)` returns PDF bytes for the page assembler; a kind
    without it can be validated and stored but not assembled into a PDF.
    """
    extensions = tuple(ext.lower() if ext.startswith('.') else f'.{ext.lower()}' for ext in extensions)
    if not name or not extensions:
        raise ValueError('register_file_type needs a name and at least one extension.')
    _registry[name] = FileType(
        name=name, extensions=extensions, mime_types=tuple(mime_types), sniff=sniff, to_pdf=to_pdf,
        label_key=label_key, label=label or name.upper(), max_bytes=max_bytes,
    )
    return _registry[name]


def get_file_type(name):
    try:
        return _registry[name]
    except KeyError:
        raise LookupError(f'Unknown file type {name!r}; register it with dlux.files.register_file_type().') from None


def file_types(accept=None):
    names = DEFAULT_ACCEPT if accept is None else accept
    return [get_file_type(name) for name in names]


def accept_attribute(accept=None):
    """The `accept` value for a file input taking these kinds."""
    values = []
    for file_type in file_types(accept):
        values.extend(file_type.mime_types)
        values.extend(file_type.extensions)
    return ','.join(dict.fromkeys(values))


def _message(key, default, **values):
    from dlux.translations import get_strings

    return str(get_strings().get(key, default)).format(**values)


def _extension(filename):
    import os

    return os.path.splitext(filename or '')[1].lower()


def detect_file_type(data, filename='', accept=None):
    """Return the `FileType` this content is, or raise `ValueError` with a translated reason.

    With a filename, its extension must belong to an accepted kind and the content
    must match that kind. Without one, the content alone decides.
    """
    candidates = file_types(accept)
    extension = _extension(filename)
    if filename:
        candidates = [file_type for file_type in candidates if extension in file_type.extensions]
        if not candidates:
            allowed = ', '.join(ext for file_type in file_types(accept) for ext in file_type.extensions)
            raise ValueError(_message('files_type_not_allowed', 'This file type is not accepted. Allowed: {allowed}.', allowed=allowed))
    for file_type in candidates:
        if file_type.max_bytes and len(data) > file_type.max_bytes:
            raise ValueError(_message('files_too_large', 'The file is larger than the allowed size.'))
        if file_type.sniff is None or file_type.sniff(data):
            return file_type
    raise ValueError(_message('files_content_mismatch', 'The file is damaged or is not what its name says.'))


def read_upload(upload, limit=None):
    data = upload.read(limit + 1 if limit else -1)
    if limit and len(data) > limit:
        raise ValueError(_message('files_too_large', 'The file is larger than the allowed size.'))
    return data


def validate_upload(upload, accept=None, limit=None):
    """Form-friendly check of an uploaded file; raises `django.core.exceptions.ValidationError`."""
    from django.core.exceptions import ValidationError

    try:
        data = read_upload(upload, limit)
        file_type = detect_file_type(data, getattr(upload, 'name', ''), accept)
    except ValueError as exc:
        raise ValidationError(str(exc), code='invalid_file') from exc
    finally:
        if hasattr(upload, 'seek'):
            upload.seek(0)
    return file_type


def to_pdf_bytes(data, filename='', accept=None):
    """Validate content and return it as PDF bytes (images become pages)."""
    file_type = detect_file_type(data, filename, accept)
    if file_type.to_pdf is None:
        raise ValueError(_message('files_not_pages', 'This file type cannot be turned into PDF pages.'))
    return file_type.to_pdf(data)


from .types import register_builtin_types  # noqa: E402

register_builtin_types()
