"""Form wiring for registered document files: the file card and server-side type checks."""

from .registry import get_document_file


class _AcceptedFileValidator:
    """Checks a newly uploaded file against the field's accepted kinds; stored files pass untouched."""

    def __init__(self, accept):
        self.accept = accept

    def __call__(self, value):
        from django.core.files.uploadedfile import UploadedFile

        from dlux.pdf import get_pdf_features

        from . import validate_upload

        if isinstance(value, UploadedFile):
            validate_upload(value, self.accept, limit=get_pdf_features()['max_source_mb'] * 1024 * 1024)

    def __eq__(self, other):
        return isinstance(other, _AcceptedFileValidator) and other.accept == self.accept


class _ActiveContentValidator:
    """Refuses a newly uploaded page, SVG or script on a plain file field; stored files pass untouched."""

    def __call__(self, value):
        from django.core.files.uploadedfile import UploadedFile

        from . import refuse_active_content

        if isinstance(value, UploadedFile):
            refuse_active_content(value)

    def __eq__(self, other):
        return isinstance(other, _ActiveContentValidator)


def _lists_its_own_extensions(model, name):
    """Does the model field choose its accepted extensions itself (``FileExtensionValidator``)?"""
    from django.core.exceptions import FieldDoesNotExist
    from django.core.validators import FileExtensionValidator

    try:
        model_field = model._meta.get_field(name)
    except FieldDoesNotExist:
        return False
    return any(isinstance(validator, FileExtensionValidator) for validator in model_field.validators)


def apply_document_file_fields(form):
    """Give each registered document field on a ModelForm the file card (with Scan) and the type check.

    Every other plain file field refuses uploads a browser would run as a page
    or script (HTML, SVG, JavaScript), unless its model field lists its own
    extensions with ``FileExtensionValidator``. The dynamic modal calls this for
    every form it builds; a project's own form may call it from ``__init__``.
    """
    from django import forms

    from dlux.widgets import DluxFileInput

    from . import accept_attribute

    model = getattr(getattr(form, '_meta', None), 'model', None)
    if model is None:
        return form
    for name, field in form.fields.items():
        spec = get_document_file(model, name)
        if spec is None:
            if (isinstance(field, forms.FileField) and not isinstance(field, forms.ImageField)
                    and not _lists_its_own_extensions(model, name)
                    and _ActiveContentValidator() not in field.validators):
                field.validators.append(_ActiveContentValidator())
            continue
        attrs = dict(getattr(field.widget, 'attrs', {}) or {})
        attrs['accept'] = accept_attribute(spec.accept)
        field.widget = DluxFileInput(attrs=attrs, field_label=str(field.label or ''), show_scan=True)
        validator = _AcceptedFileValidator(spec.accept)
        if validator not in field.validators:
            field.validators.append(validator)
    return form


def document_file_names(instance):
    """``{field_name: current storage name}`` for the registered document fields of an instance."""
    from .registry import document_file_fields

    return {spec.field_name: (getattr(instance, spec.field_name).name or '') for spec in document_file_fields(instance)}


def record_document_file_uploads(instance, previous_names, user=None):
    """After a form save, keep replaced files in history and turn accepted images into PDF."""
    from .history import record_upload

    for field_name, previous in previous_names.items():
        record_upload(instance, previous, field_name=field_name, user=user)
