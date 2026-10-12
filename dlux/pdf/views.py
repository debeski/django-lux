"""Modal editor transport with a project-supplied persistence adapter."""

import json
import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.views import View

from . import get_pdf_features
from .assembly import assemble_pdf
from dlux.widgets import DluxFileInput

logger = logging.getLogger(__name__)


class PdfSourceInput(DluxFileInput):
    allow_multiple_selected = True


class PdfEditorView(LoginRequiredMixin, View):
    adapter = None

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not get_pdf_features()['editing_enabled']:
            return JsonResponse({'error': 'PDF editing is disabled.'}, status=403)
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        document = self.adapter.lookup(request, kwargs, lock=False)
        context = self.adapter.context(request, document, kwargs)
        context.update(document=document, revision=self.adapter.revision(document), pdf_features=get_pdf_features())
        context['source_input'] = PdfSourceInput(attrs={'id': 'dlux-pdf-file-input', 'accept': 'application/pdf,.pdf', 'multiple': True}).render('pdf_sources', None)
        return JsonResponse({'html': render_to_string('dlux/pdf/editor.html', context, request=request)})

    def post(self, request, *args, **kwargs):
        with transaction.atomic():
            document = self.adapter.lookup(request, kwargs, lock=True)
            if request.POST.get('revision') != self.adapter.revision(document):
                return JsonResponse({'error': 'This document has changed. Reopen it before saving.'}, status=409)
            try:
                manifest = json.loads(request.POST.get('manifest', '[]'))
                limits = get_pdf_features()
                data = assemble_pdf(manifest, lambda source: self.adapter.read_source(request, document, source), max_pages=limits['max_pages'], max_source_bytes=limits['max_source_mb'] * 1024 * 1024)
                with transaction.atomic():
                    self.adapter.save(request, document, data)
            except Exception as exc:
                logger.warning('PDF editing failed; database changes rolled back.', exc_info=True)
                return JsonResponse({'error': str(exc), 'success': False}, status=400)
        return JsonResponse({'success': True, 'refresh_parent': True})
