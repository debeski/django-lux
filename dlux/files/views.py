"""HTTP endpoints for document files: conversion, source/download, page editor and history."""

import hashlib
import json
import os

from django.apps import apps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.decorators.http import require_POST

from .registry import get_document_file

VIEW_ACTIONS = ('view', 'download', 'history')


@login_required
@require_POST
def convert_to_pdf(request):
    """Turn one uploaded image (or other convertible kind) into PDF pages for the page editor.

    Nothing is stored; the editor uploads the returned pages as a PDF source.
    """
    from dlux.pdf import get_pdf_features

    from . import convertible_types, read_upload, to_pdf_bytes

    upload = request.FILES.get('file')
    if upload is None:
        return JsonResponse({'error': 'Choose a file to add.'}, status=400)
    limit = get_pdf_features()['max_source_mb'] * 1024 * 1024
    try:
        data = read_upload(upload, limit)
        pdf = to_pdf_bytes(data, upload.name, accept=convertible_types())
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    return HttpResponse(pdf, content_type='application/pdf')


def document_revision(document):
    """A string that changes whenever any stored value of the document changes."""
    values = {field.attname: str(getattr(document, field.attname)) for field in document._meta.concrete_fields}
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def _route_kwargs(document, field_name):
    return {
        'app_label': document._meta.app_label, 'model_name': document._meta.model_name,
        'pk': document.pk, 'field_name': field_name,
    }


def document_file_urls(document, field_name='pdf_file'):
    kwargs = _route_kwargs(document, field_name)
    return {
        'source_url': reverse('dlux_document_file_source', kwargs=kwargs),
        'download_url': reverse('dlux_document_file_download', kwargs=kwargs),
        'edit_url': reverse('dlux_document_file_edit', kwargs=kwargs),
        'history_url': reverse('dlux_document_file_history', kwargs=kwargs),
    }


def can_access(request, spec, document, action):
    decision = spec.can_access(request, document, action) if spec.can_access else None
    if decision is not None:
        return bool(decision)
    meta = document._meta
    codename = 'change' if action == 'edit' else 'view'
    return request.user.has_perm(f'{meta.app_label}.{codename}_{meta.model_name}')


def document_file_context(request, document, field_name='pdf_file'):
    """Context for `dlux/pdf/viewer.html` (and the editor) of a registered document file."""
    from dlux.pdf import get_pdf_features

    spec = get_document_file(document, field_name)
    file_field = getattr(document, field_name)
    urls = document_file_urls(document, field_name)
    features = get_pdf_features()
    if not can_access(request, spec, document, 'history'):
        features = {**features, 'history_enabled': False}
    has_file = bool(file_field and file_field.name)
    return {
        **urls,
        'source_url': urls['source_url'] if has_file else '',
        'download_url': urls['download_url'] if has_file else '',
        'file_name': os.path.basename(file_field.name) if has_file else '',
        'can_edit': can_access(request, spec, document, 'edit'),
        'pdf_features': features,
        'document': document,
    }


def resolve_document(request, app_label, model_name, pk, field_name, action, lock=False):
    """The registered document the user may act on, or 404/403."""
    from dlux.views.sections import _scope_filtered_modal_queryset

    try:
        model = apps.get_model(app_label, model_name)
    except LookupError:
        raise Http404('Unknown document type.') from None
    spec = get_document_file(model, field_name)
    if spec is None:
        raise Http404('This field is not a document file.')
    queryset = spec.queryset(request, model) if spec.queryset else _scope_filtered_modal_queryset(model, request.user)
    if lock:
        queryset = queryset.select_for_update()
    document = get_object_or_404(queryset, pk=pk)
    if not can_access(request, spec, document, action):
        raise PermissionDenied
    return spec, document


def _file_response(request, file_field, *, as_attachment):
    from .serving import serve_file

    return serve_file(request, file_field, as_attachment=as_attachment)


@login_required
def document_file_source(request, app_label, model_name, pk, field_name):
    _, document = resolve_document(request, app_label, model_name, pk, field_name, 'view')
    return _file_response(request, getattr(document, field_name), as_attachment=False)


@login_required
def document_file_download(request, app_label, model_name, pk, field_name):
    _, document = resolve_document(request, app_label, model_name, pk, field_name, 'download')
    return _file_response(request, getattr(document, field_name), as_attachment=True)


class DocumentFileAdapter:
    """`PdfEditorView` adapter for any registered document file."""

    revision = staticmethod(document_revision)

    def __init__(self, field_name):
        self.field_name = field_name

    def lookup(self, request, keys, lock=False):
        return resolve_document(request, keys['app_label'], keys['model_name'], keys['pk'], keys['field_name'], 'edit', lock=lock)[1]

    def context(self, request, document, keys):
        context = document_file_context(request, document, keys['field_name'])
        context['history_url'] += '?return_to=' + context['edit_url']
        return context

    def read_source(self, request, document, source):
        from dlux.pdf import get_pdf_features

        from . import read_upload

        limit = get_pdf_features()['max_source_mb'] * 1024 * 1024
        if source == 'current':
            file_field = getattr(document, self.field_name)
            if not file_field.name:
                raise ValueError('The current record has no file.')
            with file_field.open('rb') as stream:
                return stream.read(limit + 1)
        upload = request.FILES.get(source)
        if upload is None:
            raise ValueError('A selected upload is missing.')
        return read_upload(upload, limit)

    def save(self, request, document, data):
        from .history import save_new_version

        save_new_version(document, data, field_name=self.field_name, user=request.user)


@login_required
def document_file_edit(request, app_label, model_name, pk, field_name):
    from dlux.pdf.views import PdfEditorView

    spec, _ = resolve_document(request, app_label, model_name, pk, field_name, 'edit')
    view = PdfEditorView.as_view(adapter=DocumentFileAdapter(field_name), accept=spec.accept)
    return view(request, app_label=app_label, model_name=model_name, pk=pk, field_name=field_name)


@login_required
def document_file_history(request, app_label, model_name, pk, field_name):
    from dlux.pdf import get_pdf_features

    from .history import versions_for

    if not get_pdf_features()['history_enabled']:
        raise PermissionDenied
    _, document = resolve_document(request, app_label, model_name, pk, field_name, 'history')
    versions = list(versions_for(document, field_name).select_related('created_by'))
    kwargs = _route_kwargs(document, field_name)
    for version in versions:
        version.file_name = os.path.basename(version.archived_file.name)
        version.download_url = reverse('dlux_document_file_version', kwargs={**kwargs, 'version': version.version_number})
    edit_url = reverse('dlux_document_file_edit', kwargs=kwargs)
    spec = get_document_file(document, field_name)
    return_url = edit_url if (
        request.GET.get('return_to') == edit_url and get_pdf_features()['editing_enabled']
        and can_access(request, spec, document, 'edit')
    ) else ''
    html = render_to_string('dlux/pdf/history.html', {
        'document': document, 'versions': versions, 'is_modal': True, 'history_return_url': return_url,
    }, request=request)
    return JsonResponse({'html': html})


@login_required
def document_file_version(request, app_label, model_name, pk, field_name, version):
    from dlux.pdf import get_pdf_features

    from .history import versions_for

    if not get_pdf_features()['history_enabled']:
        raise PermissionDenied
    _, document = resolve_document(request, app_label, model_name, pk, field_name, 'history')
    row = get_object_or_404(versions_for(document, field_name), version_number=version)
    return _file_response(request, row.archived_file, as_attachment=True)


for _view in (convert_to_pdf, document_file_source, document_file_download, document_file_edit,
              document_file_history, document_file_version):
    _view.dlux_exclude = True
