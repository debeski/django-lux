"""HTTP endpoints for document files."""

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_POST


@login_required
@require_POST
def convert_to_pdf(request):
    """Turn one uploaded image (or other convertible kind) into PDF pages for the page editor.

    Nothing is stored. The same conversion runs again on save, so the editor's
    preview and the saved document always agree.
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


convert_to_pdf.dlux_exclude = True
