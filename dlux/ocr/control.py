"""Start or stop the stack's ``ocr`` service when the Extra Features switch changes.

The request is the Operations panel's: a ``service-start``/``service-stop``
operation queued for Composer and audited as ``DLUX_OPS_RUN``. The caller has
already confirmed the current password. Nothing here blocks saving the setting:
when Composer is too old, unreachable or busy, the reason is reported and the
Operations panel remains the way to act on the service.
"""

import logging

from django.core.cache import cache

from . import SERVICE_NAME

log = logging.getLogger('dlux')
NOTE_CACHE_KEY = 'dlux:ocr:service-note'
OPERATIONS = ('service-start', 'service-stop')


def operation_for(enabled):
    return 'service-start' if enabled else 'service-stop'


def request_service(request, operation):
    """Queue ``operation`` for the ocr service; returns the run, or None with a note kept for the section."""
    from dlux.notifications import notify
    from dlux.translations import get_strings
    from dlux.updater import UpdaterError
    from dlux.updater.service import queue_ops_run
    from dlux.utils import log_audit_event

    strings = get_strings()
    user = getattr(request, 'user', None)
    try:
        run = queue_ops_run(operation, username=user.get_username() if user else '', params={'service': SERVICE_NAME})
    except (UpdaterError, Exception) as exc:
        reason = str(exc) if isinstance(exc, UpdaterError) else exc.__class__.__name__
        if not isinstance(exc, UpdaterError):
            log.warning('Could not queue %s for the ocr service.', operation, exc_info=True)
        key = 'ocr_service_start_unavailable' if operation == 'service-start' else 'ocr_service_stop_unavailable'
        fallback = ('Saved. The ocr service could not be started from here: {reason} Use the Operations panel.'
                    if operation == 'service-start' else
                    'Saved. The ocr service could not be stopped from here: {reason} Use the Operations panel.')
        message = strings.get(key, fallback).format(reason=reason)
        cache.set(NOTE_CACHE_KEY, {'operation': operation, 'message': message}, 86400)
        notify.warning(message, request=request, action='ocr_service_unavailable', category='system')
        return None
    cache.delete(NOTE_CACHE_KEY)
    log_audit_event(
        request, 'dlux_ops_run', 'DLUX_OPS_RUN', model_name='DjangoLux operations',
        details={'operation': run.operation, 'token': run.token, **(run.params or {})},
    )
    key = 'ocr_service_start_requested' if operation == 'service-start' else 'ocr_service_stop_requested'
    fallback = 'Starting the ocr service through Composer.' if operation == 'service-start' else 'Stopping the ocr service through Composer.'
    notify.info(strings.get(key, fallback), request=request, action='ocr_service_requested', category='system')
    return run


def service_status():
    """``{'state', 'operation', 'message'}`` for the latest switch-driven request, or None."""
    from dlux.models import DluxOpsRun

    note = cache.get(NOTE_CACHE_KEY)
    if note:
        # Set when the last request could not be queued; a queued request clears it.
        return {'state': 'unavailable', 'operation': note.get('operation', ''), 'message': note.get('message', '')}
    run = DluxOpsRun.objects.filter(operation__in=OPERATIONS, params__service=SERVICE_NAME).order_by('-created_at', '-pk').first()
    if run is None:
        return None
    return {'state': run.status, 'operation': run.operation, 'message': run.error or ''}


def settings_saved(sender, instance, raw=False, **kwargs):
    """post_save on SystemSettings: send the service request a changed Enable OCR switch asked for, once per save."""
    pending = getattr(instance, '_dlux_ocr_service_request', None)
    if raw or not pending:
        return
    instance._dlux_ocr_service_request = None
    request, operation = pending
    from django.db import transaction

    transaction.on_commit(lambda: request_service(request, operation))
