"""Long requests run by the task worker (``DluxJob`` rows).

A view checks its permissions and inputs, then calls ``start_job(kind, user,
params)``. With a live worker the row is queued as ``dlux.tasks.run_job`` and
the browser polls ``sys/api/jobs/<token>/``; without one the view keeps its
synchronous path. A job's file is downloaded from
``sys/api/jobs/<token>/download/`` by the user who started it, while that user
still passes the kind's permission check.
"""

import logging
import tempfile
from datetime import timedelta
from types import SimpleNamespace

from django.apps import apps
from django.core.files import File
from django.core.files.storage import default_storage
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

logger = logging.getLogger('dlux')

TASK_NAME = 'dlux.tasks.run_job'
KEEP_COMPLETED_PER_KIND = 3
KEEP_FOR = timedelta(days=1)
KEEP_FAILED_FOR = timedelta(days=7)

KIND_REPORTS_XLSX = 'reports_xlsx'
KIND_DATA_RESET = 'data_reset'


def _job_model():
    return apps.get_model('dlux', 'DluxJob')


def _storage_dir():
    from .reports.archive import get_backup_storage_prefix

    return f'{get_backup_storage_prefix()}/jobs'


def _can_view_reports(user):
    from .utils import user_can_view_reports

    return user_can_view_reports(user)


def _is_superuser(user):
    return bool(getattr(user, 'is_superuser', False))


def _run_reports_xlsx(job, progress):
    from .reports import build_reports_overview
    from .reports.export import build_model_entries_xlsx

    params = job.params or {}
    window = params.get('window')
    overview = build_reports_overview(job.user, window=window, filters=params.get('filters') or {})
    content = build_model_entries_xlsx(
        job.user,
        overview,
        progress_callback=lambda percent, message: progress(5 + int(percent * 0.9), message),
    )
    stamp = timezone.localdate().isoformat()
    _store_file(job, content, f'dlux-entries-{overview["criteria"]["window"]}-{stamp}.xlsx', '.xlsx')
    from .utils import log_user_action

    log_user_action(
        _job_request(job),
        'EXPORT',
        model_name='Dlux Reports Backup',
        details={'kind': 'model_entries', 'window': overview['criteria']['window'],
                 'models': overview['selected_model_count']},
    )
    return {'models': overview['selected_model_count']}


def _run_data_reset(job, progress):
    from .admin_actions.data_reset import run_data_reset

    params = job.params or {}
    return run_data_reset(
        job.user,
        params.get('models') or [],
        delete_media=bool(params.get('delete_media')),
        mode=params.get('mode'),
        request=_job_request(job),
        language=params.get('language') or None,
        progress_callback=progress,
    )


# kind -> (runner, permission check, download content type)
KINDS = {
    KIND_REPORTS_XLSX: (
        _run_reports_xlsx, _can_view_reports,
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    ),
    KIND_DATA_RESET: (_run_data_reset, _is_superuser, ''),
}


def user_may_use(job, user):
    entry = KINDS.get(job.kind)
    return entry is not None and job.user_id == getattr(user, 'pk', None) and entry[1](user)


def request_context(request):
    """What a worker needs to write audit rows as if from ``request``."""
    from .translations import get_current_language_code
    from .utils.config import get_client_ip

    meta = getattr(request, 'META', {}) or {}
    return {
        'ip': get_client_ip(request) or '',
        'user_agent': str(meta.get('HTTP_USER_AGENT', ''))[:500],
        'language': get_current_language_code(request) or '',
    }


def _job_request(job):
    """A stand-in request for audit rows written by the worker."""
    params = job.params or {}
    return SimpleNamespace(
        user=job.user,
        META={'REMOTE_ADDR': params.get('ip') or '', 'HTTP_USER_AGENT': params.get('user_agent') or ''},
        path='',
        method='POST',
    )


def _store_file(job, content, file_name, suffix):
    with tempfile.TemporaryFile() as tmp:
        tmp.write(content)
        size = tmp.tell()
        tmp.seek(0)
        job.file_path = default_storage.save(f'{_storage_dir()}/{job.token}{suffix}', File(tmp))
    job.file_name = file_name
    job.file_size = size


def worker_available():
    from .taskrunner import worker_alive

    return worker_alive()


def start_job(kind, user, params):
    """Create a job and queue it on the worker. Returns the job, or None without a worker.

    The caller has already checked the user's permission for ``kind``.
    """
    if kind not in KINDS:
        raise ValueError(f'Unknown job kind: {kind}')
    if not worker_available():
        return None
    from .taskrunner import enqueue

    DluxJob = _job_model()
    _prune(user, kind)
    with transaction.atomic():
        job = DluxJob.objects.create(kind=kind, user=user, params=params or {})
        enqueue(TASK_NAME, args=[job.pk])
    return job


def set_progress(job, percent, message=''):
    percent = max(0, min(100, int(percent)))
    job.progress_percent = percent
    job.progress_message = str(message or '')[:255]
    _job_model().objects.filter(pk=job.pk).update(
        progress_percent=job.progress_percent, progress_message=job.progress_message,
    )


def run_job(job_pk):
    """Run one queued job. The worker's task body; safe to call twice."""
    DluxJob = _job_model()
    claimed = DluxJob.objects.filter(pk=job_pk, status=DluxJob.STATUS_PENDING).update(
        status=DluxJob.STATUS_RUNNING, started_at=timezone.now(),
    )
    if not claimed:
        return None
    job = DluxJob.objects.select_related('user').get(pk=job_pk)
    runner, allowed, _content_type = KINDS.get(job.kind, (None, None, ''))
    try:
        if runner is None:
            raise ValueError(f'Unknown job kind: {job.kind}')
        if not allowed(job.user):
            raise PermissionError('The user who started this job no longer has permission for it.')
        result = runner(job, lambda percent, message='': set_progress(job, percent, message))
    except Exception as exc:
        logger.exception('Background job %s (%s) failed.', job.pk, job.kind)
        _fail(job, str(exc))
        return job
    job.result = result or {}
    job.status = DluxJob.STATUS_COMPLETED
    job.progress_percent = 100
    job.completed_at = timezone.now()
    job.error = ''
    job.save(update_fields=[
        'result', 'status', 'progress_percent', 'completed_at', 'error',
        'file_path', 'file_name', 'file_size',
    ])
    return job


def _fail(job, error):
    DluxJob = type(job)
    job.status = DluxJob.STATUS_FAILED
    job.error = str(error or '')[:2000]
    job.completed_at = timezone.now()
    job.save(update_fields=['status', 'error', 'completed_at'])


def job_lost(job_pk):
    """``on_lost`` for ``run_job``: the worker died mid-run, so say so at once."""
    DluxJob = _job_model()
    job = DluxJob.objects.filter(pk=job_pk, status__in=[DluxJob.STATUS_PENDING, DluxJob.STATUS_RUNNING]).first()
    if job is not None:
        _fail(job, 'The task worker stopped before this job finished.')


def payload(job):
    """The status JSON the browser polls."""
    DluxJob = type(job)
    data = {
        'token': job.token,
        'kind': job.kind,
        'status': job.status,
        'progress_percent': job.progress_percent,
        'progress_message': job.progress_message,
        'error': job.error[:300] if job.status == DluxJob.STATUS_FAILED else '',
        'result': job.result if job.status == DluxJob.STATUS_COMPLETED else {},
    }
    if job.status == DluxJob.STATUS_COMPLETED and job.file_path:
        data['download_url'] = reverse('dlux_job_download', args=[job.token])
        data['file_name'] = job.file_name
        data['file_size'] = job.file_size
    return data


def start_payload(job):
    return {
        'ok': True,
        'async': True,
        'token': job.token,
        'status_url': reverse('dlux_job_status', args=[job.token]),
    }


def _delete_file(job):
    if job.file_path:
        try:
            default_storage.delete(job.file_path)
        except Exception:
            logger.warning('Could not delete job file %s.', job.file_path, exc_info=True)


def _prune(user, kind):
    """Keep a user's last few finished jobs of a kind, for a day; failures for a week."""
    DluxJob = _job_model()
    now = timezone.now()
    finished = DluxJob.objects.filter(user=user, kind=kind, status=DluxJob.STATUS_COMPLETED).order_by('-created_at')
    stale = list(finished[KEEP_COMPLETED_PER_KIND:]) + list(finished.filter(created_at__lt=now - KEEP_FOR))
    stale += list(DluxJob.objects.filter(
        user=user, kind=kind, status=DluxJob.STATUS_FAILED, created_at__lt=now - KEEP_FAILED_FOR,
    ))
    seen = set()
    for job in stale:
        if job.pk in seen:
            continue
        seen.add(job.pk)
        _delete_file(job)
        job.delete()


def open_file(job):
    """The job's file for download, or None when it is gone."""
    if not job.file_path or not default_storage.exists(job.file_path):
        return None
    return default_storage.open(job.file_path, 'rb')


def content_type(job):
    entry = KINDS.get(job.kind)
    return (entry[2] if entry else '') or 'application/octet-stream'


__all__ = [
    'KINDS', 'KIND_DATA_RESET', 'KIND_REPORTS_XLSX', 'TASK_NAME', 'content_type', 'job_lost',
    'open_file', 'payload', 'request_context', 'run_job', 'set_progress', 'start_job',
    'start_payload', 'user_may_use', 'worker_available',
]
