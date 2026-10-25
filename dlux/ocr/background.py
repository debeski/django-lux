"""Bounded catch-up scans for registered document files, driven by Celery Beat."""

import time
from datetime import timedelta
from uuid import uuid4

from django.core.cache import cache
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from . import RETRY_DELAYS, automatic_model_allowed, config
from .client import service_health
from .service import schedule

STATE_KEY = 'dlux:ocr:background:state'
LOCK_KEY = 'dlux:ocr:background:lock'


def tick():
    options = config()
    if not options['enabled'] or not options['background_enabled']:
        return {'state': 'disabled', 'queued': 0}
    token = uuid4().hex
    if not cache.add(LOCK_KEY, token, 120):
        return {'state': 'busy', 'queued': 0}
    try:
        state = cache.get(STATE_KEY) or {}
        now = timezone.now()
        if now.timestamp() - state.get('last_run', 0) < options['background_interval']:
            return {'state': 'waiting', 'queued': 0}
        from django.contrib.contenttypes.models import ContentType
        from dlux.files.specs import registered_document_files
        from dlux.models import FileText

        specs = sorted((spec for spec in registered_document_files()
                        if spec.ocr and automatic_model_allowed(spec.model, options)), key=lambda spec: spec.key)
        queued = scanned = 0
        status = 'idle'
        cutoff = now - timedelta(seconds=options['timeout'] + 120)
        pending_cutoff = now - timedelta(seconds=max(options['timeout'] + 120, max(RETRY_DELAYS) + 120))
        active = FileText.all_objects.filter(deleted_at__isnull=True).filter(
            Q(status='pending', updated_at__gte=pending_cutoff) | Q(status='running', started_at__gte=cutoff),
        ).count()
        capacity = min(options['background_batch_size'], max(0, options['background_queue_limit'] - active))
        if capacity == 0:
            status = 'paused_queue'
        elif specs and not service_health(refresh=True):
            status = 'paused_service'
        elif specs:
            cursors = state.setdefault('cursors', {})
            index = state.get('index', 0) % len(specs)
            deadline = time.monotonic() + 10
            for offset in range(min(len(specs), 32)):
                spec = specs[(index + offset) % len(specs)]
                state['index'] = (index + offset + 1) % len(specs)
                model = spec.model
                manager = getattr(model, 'all_objects', model._default_manager)
                finished = FileText.all_objects.filter(
                    content_type=ContentType.objects.get_for_model(model), object_id=OuterRef('pk'),
                    field_name=spec.field_name, is_current=True, deleted_at__isnull=True,
                    status__in=['done', 'failed', 'skipped'],
                )
                documents = manager.exclude(**{spec.field_name: ''}).exclude(**{spec.field_name + '__isnull': True})
                if hasattr(model, 'deleted_at'):
                    documents = documents.filter(deleted_at__isnull=True)
                documents = documents.annotate(_ocr_finished=Exists(finished)).filter(_ocr_finished=False)
                batch = list(documents.filter(pk__gt=cursors.get(spec.key, 0)).order_by('pk')[:max(50, capacity)])
                if not batch:
                    cursors[spec.key] = 0
                for document in batch:
                    if queued >= capacity or scanned >= 100 or time.monotonic() >= deadline:
                        break
                    _, sent = schedule(document, spec.field_name, source='backfill')
                    queued += int(sent)
                    scanned += 1
                    cursors[spec.key] = document.pk
                if queued >= capacity or scanned >= 100 or time.monotonic() >= deadline:
                    break
            status = 'queued' if queued else 'idle'
        state.update(last_run=now.timestamp(), state=status, queued=queued, scanned=scanned)
        cache.set(STATE_KEY, state, timeout=None)
        return {'state': status, 'queued': queued, 'scanned': scanned}
    finally:
        if cache.get(LOCK_KEY) == token:
            cache.delete(LOCK_KEY)
