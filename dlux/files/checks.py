"""System check: registered document files need ``pypdf`` (the ``pdf`` extra)."""

from importlib.util import find_spec

from django.core.checks import Warning, register

from .specs import registered_document_files


@register()
def check_document_files_have_pypdf(app_configs=None, **kwargs):
    specs = registered_document_files()
    if not specs or find_spec("pypdf") is not None:
        return []
    fields = ", ".join(sorted(f"{spec.model._meta.label}.{spec.field_name}" for spec in specs))
    return [
        Warning(
            f"Document files are registered ({fields}), but pypdf is not installed, so every "
            "upload or replacement of one of their files fails.",
            hint="Install the pdf extra: django-lux[pdf] (generated projects pin django-lux[updater,ocr,pdf]).",
            id="dlux.W103",
        )
    ]
