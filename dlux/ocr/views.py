"""The text panel of a registered document file: view its OCR text, run OCR again."""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from . import config
from .service import ACTIVE_STATUSES, current_result, ocr_spec, schedule


def text_url(document, field_name='pdf_file'):
    return reverse('dlux_document_file_text', kwargs={
        'app_label': document._meta.app_label, 'model_name': document._meta.model_name,
        'pk': document.pk, 'field_name': field_name,
    })


def text_available(document, field_name='pdf_file'):
    """Whether the viewer offers the text panel: OCR is on for this field, or text was read before."""
    if ocr_spec(document, field_name) is None:
        return False
    return config()['enabled'] or current_result(document, field_name) is not None


def viewer_context(document, field_name='pdf_file'):
    """``text_url`` for the viewer's Extracted text button, or ``''`` when it is not offered."""
    return {'text_url': text_url(document, field_name) if text_available(document, field_name) else ''}


def panel_context(request, spec, document):
    from dlux.files.views import can_access

    result = current_result(document, spec.field_name)
    enabled = config()['enabled']
    file_field = getattr(document, spec.field_name, None)
    return {
        'document': document,
        'ocr_enabled': enabled,
        'ocr_result': result,
        'ocr_active': bool(result and result.status in ACTIVE_STATUSES),
        'ocr_can_run': enabled and bool(file_field and file_field.name) and can_access(request, spec, document, 'edit'),
        'ocr_url': text_url(document, spec.field_name),
        'ocr_dom_id': f'{document._meta.model_name}-{document.pk}-{spec.field_name}',
    }


def _panel_response(request, spec, document, status=200, message=''):
    context = panel_context(request, spec, document)
    result = context['ocr_result']
    return JsonResponse({
        'status': result.status if result else '',
        'active': context['ocr_active'],
        'message': message,
        'html': render_to_string('dlux/ocr/panel.html', context, request=request),
    }, status=status)


@login_required
@require_http_methods(['GET', 'POST'])
def document_file_text(request, app_label, model_name, pk, field_name):
    """GET: the text panel (view access). POST: Run OCR now (edit access, POST only)."""
    from dlux.files.views import resolve_document
    from dlux.translations import get_strings

    strings = get_strings()
    action = 'edit' if request.method == 'POST' else 'view'
    spec, document = resolve_document(request, app_label, model_name, pk, field_name, action)
    if not spec.ocr:
        return JsonResponse({'error': strings.get('ocr_field_off', 'OCR is off for this file.')}, status=404)
    if request.method == 'GET':
        return _panel_response(request, spec, document)
    if not config()['enabled']:
        return _panel_response(request, spec, document, 409, strings.get('ocr_disabled', 'OCR is not enabled.'))
    file_field = getattr(document, field_name)
    if not file_field or not file_field.name:
        return _panel_response(request, spec, document, 409, strings.get('ocr_no_file', 'There is no file to read.'))
    try:
        result, queued = schedule(document, field_name, source='manual', user=request.user, force=True)
    except Exception:
        import logging

        logging.getLogger('dlux').warning('Run OCR failed for %s #%s.', model_name, pk, exc_info=True)
        result, queued = None, False
    if result is None:
        return _panel_response(request, spec, document, 503, strings.get('ocr_request_failed', 'Could not request OCR.'))
    message = strings.get('ocr_queued_notice', 'The file was queued for OCR.') if queued else \
        strings.get('ocr_already_running', 'OCR is already running for this file.')
    return _panel_response(request, spec, document, message=message)
