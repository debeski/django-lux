"""Which files get read, when, and where the text is kept.

``connect_model()`` (called by ``register_document_file``) listens to saves;
``schedule()`` makes the row for the file the document holds now and queues
it; ``run()`` is the worker side. Rows are keyed by file SHA-256, so an
unchanged file is never read twice.
"""

import hashlib
import logging
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from . import RETRY_DELAYS, automatic_model_allowed, config
from .client import OCRRejected, OCRUnavailable, call_service

log = logging.getLogger('dlux')

# Redis transport: lower runs first; tasks sent without a priority run at 0.
PRIORITY = {'manual': 0, 'auto': 6, 'backfill': 9}
ACTIVE_STATUSES = ('pending', 'running')


def ocr_specs(model_or_instance):
    """The registered document files of a model that take part in OCR."""
    from dlux.files.specs import document_file_fields

    return [spec for spec in document_file_fields(model_or_instance) if spec.ocr]


def ocr_spec(model_or_instance, field_name):
    from dlux.files.specs import get_document_file

    spec = get_document_file(model_or_instance, field_name)
    return spec if spec is not None and spec.ocr else None


def file_sha256(file_field):
    digest = hashlib.sha256()
    with file_field.storage.open(file_field.name, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _active_file(document, field_name):
    file_field = getattr(document, field_name, None)
    if not file_field or not file_field.name or not file_field.storage.exists(file_field.name):
        return None
    return file_field


def _rows(document, field_name):
    from django.contrib.contenttypes.models import ContentType

    from dlux.models import FileText

    content_type = ContentType.objects.get_for_model(document.__class__)
    return content_type, FileText.all_objects.filter(content_type=content_type, object_id=document.pk, field_name=field_name)


def current_result(document, field_name='pdf_file'):
    return _rows(document, field_name)[1].filter(is_current=True, deleted_at__isnull=True).first()


def invalidate_changed_file(document, field_name):
    rows = _rows(document, field_name)[1].filter(is_current=True)
    if not rows.exists():
        return
    file_field = _active_file(document, field_name)
    if file_field is None or file_field.size > config()['max_file_mb'] * 1024 * 1024:
        rows.update(is_current=False)
    else:
        rows.exclude(file_sha256=file_sha256(file_field)).update(is_current=False)


def _stale(result):
    """A running row whose worker died, or a queued row whose message was lost."""
    reference = result.started_at if result.status == 'running' else result.updated_at
    grace = config()['timeout'] + 120
    if result.status == 'pending':
        grace = max(grace, max(RETRY_DELAYS) + 120)
    return reference is None or reference < timezone.now() - timedelta(seconds=grace)


def schedule(document, field_name='pdf_file', *, source='auto', user=None, force=False, enqueue=True):
    """Make the row for the document's current file current, and queue OCR when needed.

    ``force`` (Run OCR) re-reads a finished or failed file. Returns
    ``(row, queued)``; ``row`` is None when OCR is off, the field opted out or
    there is no file.
    """
    from dlux.models import FileVersion

    if not config()['enabled'] or ocr_spec(document, field_name) is None or getattr(document, 'deleted_at', None):
        return None, False
    if source != 'manual' and not automatic_model_allowed(document):
        return None, False
    content_type, rows = _rows(document, field_name)
    file_field = _active_file(document, field_name)
    if file_field is None:
        rows.filter(is_current=True).update(is_current=False)
        return None, False
    if file_field.size > config()['max_file_mb'] * 1024 * 1024:
        rows.filter(is_current=True).update(is_current=False)
        log.info('OCR skipped for %s #%s: file exceeds the OCR size limit.', document.__class__.__name__, document.pk)
        return None, False
    digest = file_sha256(file_field)
    version = FileVersion.all_objects.filter(
        content_type=content_type, object_id=document.pk, field_name=field_name, active_name_after=file_field.name,
    ).order_by('-version_number').first()
    keys = {'content_type': content_type, 'object_id': document.pk, 'field_name': field_name, 'file_sha256': digest}
    defaults = {
        'document_model': document.__class__.__name__, 'scope_id': getattr(document, 'scope_id', None),
        'file_name': file_field.name, 'file_version': version, 'source': source, 'requested_by': user,
    }
    with transaction.atomic():
        current_name = document.__class__._base_manager.select_for_update().filter(pk=document.pk).values_list(field_name, flat=True).first()
        if current_name != file_field.name:
            return None, False
        try:
            with transaction.atomic():
                result, created = rows.get_or_create(**keys, defaults=defaults)
        except IntegrityError:
            result, created = rows.get(**keys), False
        result = rows.select_for_update().get(pk=result.pk)
        rows.filter(is_current=True).exclude(pk=result.pk).update(is_current=False)
        queue = created
        if not created:
            busy = result.status in ACTIVE_STATUSES and not _stale(result)
            queue = (force and not busy) or (result.status in ACTIVE_STATUSES and _stale(result))
            if source == 'manual' and force and result.source != 'manual' and result.status == 'pending' and not automatic_model_allowed(document):
                queue = True
            result.is_current = True
            result.file_name = file_field.name
            result.file_version = version or result.file_version
            if result.deleted_at:
                result.deleted_at = None
                result.deleted_by = None
            if queue:
                result.status, result.source, result.requested_by, result.error = 'pending', source, user, ''
            result.save()
        if queue and enqueue:
            send_task(result)
    return result, queue


def _queue(result_id, priority):
    """Send ``dlux.tasks.ocr_file`` by name, so this module never imports the task module."""
    from celery import current_app

    current_app.send_task('dlux.tasks.ocr_file', args=(result_id,), priority=priority)


def send_task(result):
    def send():
        try:
            _queue(result.pk, PRIORITY.get(result.source, 6))
        except Exception:
            log.warning('Could not queue OCR for file text %s; it stays queued for the backfill.', result.pk, exc_info=True)

    transaction.on_commit(send)


def run(result_id):
    """Read one row's file. Raises ``OCRUnavailable`` when the caller should retry later."""
    from dlux.models import FileText

    with transaction.atomic():
        result = FileText.all_objects.select_for_update().filter(pk=result_id).first()
        if result is None or result.status == 'done' or (result.status == 'running' and not _stale(result)):
            return result
        if not config()['enabled']:
            raise OCRUnavailable('OCR is disabled; queued work will retry after it is enabled.')
        document = result.document
        if document is not None and result.source != 'manual' and not automatic_model_allowed(document):
            from dlux.translations import get_strings
            return _finish(result, 'skipped', error=get_strings().get('ocr_automatic_model_excluded', 'Automatic OCR is disabled for this model.'))
        alive = document is not None and not getattr(document, 'deleted_at', None)
        file_field = _active_file(document, result.field_name) if alive else None
        if file_field is None:
            return _finish(result, 'skipped', error='The document or its file no longer exists.')
        result.status, result.started_at, result.error = 'running', timezone.now(), ''
        result.attempts += 1
        result.save(update_fields=['status', 'started_at', 'error', 'attempts', 'updated_at'])
    with file_field.storage.open(file_field.name, 'rb') as handle:
        content = handle.read()
    if hashlib.sha256(content).hexdigest() != result.file_sha256:
        return _finish(result, 'skipped', error='The file changed before OCR ran; the new file has its own result.')
    try:
        payload = call_service(content)
    except OCRUnavailable as exc:
        _finish(result, 'pending', error=str(exc))
        raise
    except OCRRejected as exc:
        return _finish(result, 'failed', error=str(exc))
    return _store(result, payload)


def give_up(result_id, error):
    from dlux.models import FileText

    result = FileText.all_objects.filter(pk=result_id).first()
    if result is not None and result.status != 'done':
        _finish(result, 'failed', error=error)


def _finish(result, status, error=''):
    result.status, result.error = status, error[:2000]
    result.finished_at = timezone.now() if status != 'pending' else None
    result.save(update_fields=['status', 'error', 'finished_at', 'updated_at'])
    return result


def _store(result, payload):
    timings = payload.get('timings') or {}
    result.engine = str(payload.get('engine') or '')[:64]
    result.engine_version = str(payload.get('engine_version') or '')[:64]
    result.model_version = str(payload.get('model_version') or '')[:64]
    result.markdown = payload.get('markdown') or ''
    result.text = payload.get('text') or ''
    result.pages = payload.get('pages') or []
    result.page_count = int(payload.get('page_count') or len(result.pages))
    result.mean_confidence = payload.get('mean_confidence')
    result.timings = timings
    result.duration_ms = int(timings.get('total_ms') or 0)
    failed = payload.get('failed_pages') or []
    result.error = f'Pages that could not be read: {", ".join(str(index + 1) for index in failed)}' if failed else ''
    result.status = 'done'
    result.finished_at = timezone.now()
    result.save(update_fields=[
        'engine', 'engine_version', 'model_version', 'markdown', 'text', 'pages',
        'page_count', 'mean_confidence', 'timings', 'duration_ms', 'error',
        'status', 'finished_at', 'updated_at',
    ])
    return result


def document_saved(sender, instance, created=False, raw=False, update_fields=None, **kwargs):
    """post_save: queue automatic OCR for each OCR field after the surrounding transaction commits."""
    if raw or not ocr_specs(sender):
        return
    fields = [spec.field_name for spec in ocr_specs(sender)
              if update_fields is None or spec.field_name in update_fields]
    if not fields:
        return
    model, pk = instance.__class__, instance.pk

    def scheduled():
        manager = getattr(model, 'all_objects', model._default_manager)
        try:
            document = manager.filter(pk=pk).first()
            for field_name in fields if document is not None else ():
                options = config()
                if options['enabled'] and options['auto_on_save'] and automatic_model_allowed(document, options):
                    schedule(document, field_name, source='auto')
                else:
                    invalidate_changed_file(document, field_name)
        except Exception:
            log.warning('Automatic OCR scheduling failed for %s #%s.', model.__name__, pk, exc_info=True)

    transaction.on_commit(scheduled)


def connect():
    """Wire OCR into saves and search; called once from ``DluxConfig.ready()``."""
    from django.db.models.signals import post_save

    from dlux.utils.arabic import register_model_text_search

    post_save.connect(document_saved, dispatch_uid='dlux.ocr.document_saved', weak=False)
    register_model_text_search(text_search_q)


def text_search_q(model, term):
    """The model-text search hook: OCR matches for models with OCR files, else None."""
    return search_q(model, term) if ocr_specs(model) else None


def search_q(model, term):
    """``Q`` matching ``model`` rows whose current OCR text contains ``term`` (Arabic-variant aware).

    Empty (matches nothing) when OCR search is off or the model has no OCR field.
    """
    from django.contrib.contenttypes.models import ContentType
    from django.db.models import Exists, OuterRef, Q

    from dlux.models import FileText
    from dlux.utils.arabic import arabic_search_pattern

    pattern = arabic_search_pattern(term)
    fields = [spec.field_name for spec in ocr_specs(model)]
    if not pattern or not fields or not config()['search']:
        return Q(pk__in=[])
    matches = FileText.all_objects.filter(
        content_type=ContentType.objects.get_for_model(model), object_id=OuterRef('pk'), field_name__in=fields,
        is_current=True, status='done', deleted_at__isnull=True, text__iregex=pattern,
    )
    return Q(Exists(matches))
