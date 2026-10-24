"""Read the text of existing registered document files, in batches; safe to stop and rerun."""

import json
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'OCR existing registered document files in batches. Files already read are skipped, so it is safe to stop and rerun.'

    def add_arguments(self, parser):
        parser.add_argument('--files', default='', help='Comma-separated app_label.model.field keys (default: every OCR file).')
        parser.add_argument('--batch-size', type=int, default=50)
        parser.add_argument('--limit', type=int, default=0, help='Stop after this many documents in this run (0: no limit).')
        parser.add_argument('--enqueue', action='store_true', help='Queue the files on Celery at backfill priority instead of reading them here.')
        parser.add_argument('--retry-failed', action='store_true', help='Read files whose last OCR failed again.')
        parser.add_argument('--restart', action='store_true', help='Ignore the saved position and start from the first document.')
        parser.add_argument('--state-file', default='', help='Checkpoint file (default: <BASE_DIR>/logs/dlux-ocr-backfill.json).')
        parser.add_argument('--wait', type=int, default=60, help='Seconds to wait for a busy or unavailable service before each retry.')
        parser.add_argument('--max-waits', type=int, default=10, help='Stop (resumable) after this many waits for one file.')
        parser.add_argument('--dry-run', action='store_true', help='Only count documents and finished texts.')

    def handle(self, *args, **options):
        from dlux.files.specs import registered_document_files
        from dlux.ocr import enabled

        if not enabled():
            raise CommandError('OCR is disabled. Turn it on in System Settings > Extra Features, and start the ocr service.')
        specs = {spec.key: spec for spec in registered_document_files() if spec.ocr}
        wanted = [key.strip() for key in options['files'].split(',') if key.strip()] or sorted(specs)
        unknown = sorted(set(wanted) - set(specs))
        if unknown:
            raise CommandError(f'Not registered for OCR: {", ".join(unknown)}. Known: {", ".join(sorted(specs)) or "none"}')
        state_path = Path(options['state_file'] or Path(settings.BASE_DIR) / 'logs' / 'dlux-ocr-backfill.json')
        state = {} if options['restart'] or not state_path.exists() else json.loads(state_path.read_text())
        totals = {'queued': 0, 'read': 0, 'skipped': 0, 'failed': 0}
        processed = 0
        for key in wanted:
            spec = specs[key]
            manager = getattr(spec.model, 'all_objects', spec.model._default_manager)
            documents = manager.exclude(**{spec.field_name: ''}).exclude(**{f'{spec.field_name}__isnull': True}).order_by('pk')
            if hasattr(spec.model, 'deleted_at'):
                documents = documents.filter(deleted_at__isnull=True)
            if options['dry_run']:
                self._report_counts(key, spec, documents)
                continue
            after = state.get(key, 0)
            while True:
                batch = list(documents.filter(pk__gt=after)[:options['batch_size']])
                if not batch:
                    break
                for document in batch:
                    if options['limit'] and processed >= options['limit']:
                        self._save(state_path, state)
                        self._summary(totals, stopped=True)
                        return
                    totals[self._process(document, spec.field_name, options)] += 1
                    processed += 1
                    after = state[key] = document.pk
                    self._save(state_path, state)
                self.stdout.write(f'{key}: up to #{after} ({processed} documents this run)')
        self._summary(totals, stopped=False)

    def _process(self, document, field_name, options):
        from dlux.ocr.client import OCRUnavailable
        from dlux.ocr.service import run, schedule, send_task

        result, queued = schedule(document, field_name, source='backfill', enqueue=options['enqueue'])
        if result is None:
            return 'skipped'
        if not queued and options['retry_failed'] and result.status in ('failed', 'skipped'):
            result.status, result.source, result.error = 'pending', 'backfill', ''
            result.save(update_fields=['status', 'source', 'error', 'updated_at'])
            queued = True
            if options['enqueue']:
                send_task(result)
        if not queued:
            return 'skipped'
        if options['enqueue']:
            return 'queued'
        for attempt in range(options['max_waits'] + 1):
            try:
                result = run(result.pk)
                break
            except OCRUnavailable as exc:
                if attempt == options['max_waits']:
                    raise CommandError(f'{exc}. Stopped at {document._meta.label} #{document.pk}; rerun to resume.')
                self.stderr.write(f'{exc}; waiting {options["wait"]} s')
                time.sleep(options['wait'])
        if result.status == 'done':
            self.stdout.write(f'  {document._meta.label} #{document.pk}: {result.page_count} pages in {result.duration_ms} ms')
            return 'read'
        self.stderr.write(f'  {document._meta.label} #{document.pk}: {result.status} {result.error}')
        return 'failed'

    def _report_counts(self, key, spec, documents):
        from django.contrib.contenttypes.models import ContentType

        from dlux.models import FileText

        done = FileText.all_objects.filter(
            content_type=ContentType.objects.get_for_model(spec.model), object_id__in=documents.values('pk'),
            field_name=spec.field_name, is_current=True, status='done', deleted_at__isnull=True,
        ).count()
        self.stdout.write(f'{key}: {documents.count()} documents with a file, {done} with current OCR text')

    def _save(self, path, state):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2))

    def _summary(self, totals, stopped):
        summary = ', '.join(f'{name} {count}' for name, count in totals.items())
        self.stdout.write(self.style.SUCCESS(f'{"Stopped at --limit" if stopped else "Done"}: {summary}'))
