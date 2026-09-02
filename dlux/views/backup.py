import hashlib
import logging

from django.apps import apps
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from ..backup import (
    backup_retry_policy,
    dispatch_system_backup,
    dispatch_system_restore,
    read_dlb_metadata,
    get_system_backup_storage_prefix,
    reap_stalled_system_backups,
    resume_system_backup,
    run_system_backup,
    run_system_restore,
)
from ..utils.backup_progress import read_restore_progress
from ..guards import require_current_password
from ..notifications import notify
from ..translations import get_strings
from ..utils import get_system_config

logger = logging.getLogger('dlux')

DLB_UPLOAD_MAX_MB_DEFAULT = 512


def _dlb_upload_max_mb():
    """Largest .dlb the upload form accepts, in MB (``DLUX_DLB_UPLOAD_MAX_MB``).

    The reverse proxy body limit (``CADDY_MAX_SIZE`` / ``NGINX_MAX_SIZE``) applies
    first, so raising this alone is not enough.
    """
    try:
        return max(int(getattr(settings, 'DLUX_DLB_UPLOAD_MAX_MB', DLB_UPLOAD_MAX_MB_DEFAULT)), 1)
    except (TypeError, ValueError):
        return DLB_UPLOAD_MAX_MB_DEFAULT


def _require_superuser(request):
    user = getattr(request, 'user', None)
    if not user or not getattr(user, 'is_superuser', False):
        raise PermissionDenied


def _system_backup_model():
    return apps.get_model('dlux', 'SystemBackup')


def _system_restore_model():
    return apps.get_model('dlux', 'SystemRestore')


def _recent_system_backups(*, reap=True):
    """Recent backup rows, after retiring any whose worker is demonstrably gone.

    The reap runs on the read path on purpose: this page (and its poller) is
    where an operator watches a backup, so it is also where a run that died
    without a trace has to stop pretending it is still alive.
    """
    if reap:
        try:
            # allow_inline=False: a retry from here must go to a worker. Building
            # a snapshot inside a status poll would hang the request for as long
            # as the backup takes.
            reap_stalled_system_backups(allow_inline=False)
        except Exception:
            logger.warning('Could not reap stalled system backups', exc_info=True)
    return list(_system_backup_model().objects.all()[:20])


def _recent_system_restores():
    return list(_system_restore_model().objects.all()[:10])


def _stall_seconds(backup):
    """How long a still-active run has gone without reporting anything."""
    if not backup.is_active:
        return 0
    return backup.seconds_since_signal()


def _system_backup_revision(backups):
    """Return a stable marker for fields rendered in the live backup table."""
    rendered_state = '\x1f'.join(
        ':'.join((
            backup.token,
            backup.status,
            str(backup.file_size),
            str(backup.row_count),
            str(backup.file_count),
            str(backup.missing_file_count),
            str(backup.progress_percent),
            backup.progress_message or '',
            '1' if backup.passphrase_required else '0',
            backup.error or '',
            str(backup.attempt_count),
            backup.stage or '',
            # Bucketed so a live run refreshes its "no progress for Nm" warning
            # without the revision churning on every single poll.
            str(_stall_seconds(backup) // 30),
            backup.next_attempt_at.isoformat() if backup.next_attempt_at else '',
        ))
        for backup in backups
    )
    return hashlib.sha256(rendered_state.encode('utf-8')).hexdigest()


def _backup_rows_context(backups):
    policy = backup_retry_policy()
    return {
        'backups': backups,
        'DLUX_STRINGS': get_strings(),
        'backup_policy': policy,
        # Warn well before the row is actually reaped, so a genuinely slow stage
        # is visible as "quiet" rather than silently looking identical to a hang.
        'backup_stall_warn_seconds': max(60, policy['stall_timeout_minutes'] * 60 // 3),
    }


def _posted_passphrase(request):
    return str(request.POST.get('backup_passphrase') or '').strip()


def _orphan_dlb_files():
    """.dlb files present under the backup prefix but unknown to SystemBackup rows
    (manually copied or uploaded files a restore can still consume)."""
    prefix = get_system_backup_storage_prefix()
    try:
        _dirs, files = default_storage.listdir(prefix)
    except Exception:
        return []
    known = set(
        _system_backup_model().objects.exclude(file_path='').values_list('file_path', flat=True)
    )
    active_prefixes = {
        f"system-{token}"
        for token in _system_backup_model().objects.filter(
            status__in=('pending', 'running'),
        ).values_list('token', flat=True)
    }
    orphans = []
    for name in sorted(files):
        if not name.lower().endswith('.dlb'):
            continue
        if any(name.startswith(prefix) for prefix in active_prefixes):
            continue
        path = f'{prefix}/{name}'
        if path in known:
            continue
        try:
            size = default_storage.size(path)
        except Exception:
            size = 0
        orphans.append({'name': name, 'path': path, 'size': size})
    return orphans


@login_required
def system_backup_page(request):
    _require_superuser(request)
    from ..forms.backup import BackupUploadForm

    backups = _recent_system_backups()
    restores = _recent_system_restores()
    context = {
        **_backup_rows_context(backups),
        'backup_revision': _system_backup_revision(backups),
        **_restore_rows_context(restores),
        'restore_revision': _system_restore_revision(restores),
        'orphan_files': _orphan_dlb_files(),
        'backup_config': get_system_config().get('backup_config', {}),
        'backup_upload_form': BackupUploadForm(max_bytes=_dlb_upload_max_mb() * 1024 * 1024),
    }
    context['ribbon'] = _backup_ribbon(request)
    return render(request, 'dlux/backup/manage.html', context)


def _backup_ribbon(request):
    """The page header, as a Ribbon.

    No filterset: this page lists what exists rather than filtering it. Backup
    creation is the page's primary POST form, so the template renders it as a
    separate row under the title/actions band.
    """
    from ..ribbon import build_action, build_ribbon

    strings = get_strings()
    actions = _backup_action_specs(request)
    return build_ribbon(
        None,
        request=request,
        title=strings.get('sysbackup_title', 'Backup & Restore'),
        subtitle=strings.get('sysbackup_subtitle', ''),
        title_icon='bi bi-safe2-fill',
        actions=[
            action
            for action in (build_action(spec, request=request) for spec in actions)
            if action
        ],
        custom_actions_key='route.system_backup_page',
        custom_actions_host='system_backup_page',
    )


def _backup_action_specs(request=None):
    strings = get_strings()
    return [{
        'label': strings.get('sysbackup_back_to_options', 'Back to Options'),
        'icon': 'bi bi-arrow-left',
        'css_class': 'btn btn-outline-secondary rounded-pill dlux-back-link',
        'url': reverse('options_view'),
    }]


system_backup_page.dlux_ribbon_host = True
system_backup_page.dlux_ribbon_actions = _backup_action_specs


@login_required
@require_POST
def system_backup_create_view(request):
    _require_superuser(request)
    s = get_strings()
    passphrase = _posted_passphrase(request)
    confirm = str(request.POST.get('backup_passphrase_confirm') or '').strip()
    if passphrase != confirm:
        return JsonResponse({
            'ok': False,
            'error': s.get('sysbackup_passphrase_mismatch'),
        }, status=400)
    # Admin chooses scope: "data" = fast data-only (no media blobs); anything else = full.
    include_media = str(request.POST.get('backup_scope') or 'full').strip().lower() != 'data'
    SystemBackup = _system_backup_model()
    backup = SystemBackup.objects.create(
        requested_by_username=request.user.get_username(),
        passphrase_required=bool(passphrase),
        media_included=include_media,
    )
    if dispatch_system_backup(backup, passphrase=passphrase):
        queued = True
    else:
        # No live worker: build inline (request blocks; small installs only).
        queued = False
        run_system_backup(backup.pk, passphrase=passphrase)
        backup.refresh_from_db()
    return JsonResponse({
        'ok': True,
        'async': queued,
        'token': backup.token,
        'status': backup.status,
        'status_url': reverse('system_backup_status', args=[backup.token]),
    })


def _get_backup_or_404(request, token):
    _require_superuser(request)
    backup = _system_backup_model().objects.filter(token=token).first()
    if backup is None:
        raise Http404
    return backup


@login_required
@never_cache
def system_backup_list_status_view(request):
    """Return the current backup-table fragment for live background updates."""
    _require_superuser(request)
    backups = _recent_system_backups()
    context = _backup_rows_context(backups)
    return JsonResponse({
        'revision': _system_backup_revision(backups),
        'active': any(backup.is_active for backup in backups),
        'items': [
            {
                'token': backup.token,
                'status': backup.status,
                'progress_percent': backup.progress_percent,
                'progress_message': backup.progress_message,
                'stage': backup.stage,
                'attempt_count': backup.attempt_count,
                'seconds_since_progress': _stall_seconds(backup),
                'stalled': bool(
                    backup.is_active
                    and _stall_seconds(backup) > context['backup_stall_warn_seconds']
                ),
            }
            for backup in backups
        ],
        'html': render_to_string('dlux/backup/_backup_rows.html', context, request=request),
    })


@login_required
@never_cache
def system_backup_status_view(request, token):
    backup = _get_backup_or_404(request, token)
    SystemBackup = type(backup)
    policy = backup_retry_policy()
    payload = {
        'status': backup.status,
        'file_size': backup.file_size,
        'rows': backup.row_count,
        'files': backup.file_count,
        'progress_percent': backup.progress_percent,
        'progress_message': backup.progress_message,
        'stage': backup.stage,
        'attempt_count': backup.attempt_count,
        'max_attempts': policy['max_attempts'],
        'seconds_since_progress': _stall_seconds(backup),
        'next_attempt_at': backup.next_attempt_at.isoformat() if backup.next_attempt_at else '',
        'error': backup.error[:200] if backup.status == SystemBackup.STATUS_FAILED else '',
    }
    if backup.status == SystemBackup.STATUS_COMPLETED:
        payload['download_url'] = reverse('system_backup_download', args=[backup.token])
    return JsonResponse(payload)


@login_required
@require_POST
def system_backup_resume_view(request, token):
    """Run another attempt for a failed backup, on the same history row."""
    backup = _get_backup_or_404(request, token)
    s = get_strings()
    try:
        resume_system_backup(
            backup,
            passphrase=_posted_passphrase(request),
            requested_by=request.user.get_username(),
        )
    except ValueError as exc:
        notify.error(
            s.get('sysbackup_resume_blocked', str(exc)),
            request=request,
            action='backup_resume_blocked',
            category='backup',
        )
        return redirect('system_backup_page')
    notify.success(
        s.get('sysbackup_resume_started', 'Retrying the backup.'),
        request=request,
        action='backup_resume',
        category='backup',
    )
    return redirect('system_backup_page')


@login_required
def system_backup_download_view(request, token):
    backup = _get_backup_or_404(request, token)
    SystemBackup = type(backup)
    if backup.status != SystemBackup.STATUS_COMPLETED or not backup.file_path:
        raise Http404
    if not default_storage.exists(backup.file_path):
        raise Http404
    stamp = timezone.localdate(backup.completed_at).isoformat()
    return FileResponse(
        default_storage.open(backup.file_path, 'rb'),
        as_attachment=True,
        filename=f'dlux-system-backup-{stamp}.dlb',
        content_type='application/octet-stream',
    )


@login_required
@require_POST
def system_backup_delete_view(request, token):
    backup = _get_backup_or_404(request, token)
    if backup.file_path:
        try:
            default_storage.delete(backup.file_path)
        except Exception:
            pass
    backup.delete()
    notify.success(get_strings().get('sysbackup_deleted'), request=request, action='backup_delete', category='backup')
    return redirect('system_backup_page')


@login_required
@require_POST
def system_backup_upload_view(request):
    _require_superuser(request)
    s = get_strings()
    uploaded = request.FILES.get('backup_file')
    if uploaded is None:
        # A file was selected but no complete multipart part arrived, so the body was
        # cut short in transit — almost always the reverse proxy body-size limit.
        notify.error(
            s.get('sysbackup_upload_incomplete'),
            request=request,
            action='backup_upload_incomplete',
            category='backup',
        )
        return redirect('system_backup_page')
    max_mb = _dlb_upload_max_mb()
    if uploaded.size > max_mb * 1024 * 1024:
        notify.error(s.get('sysbackup_upload_too_large'), request=request, action='backup_upload_too_large', category='backup')
        return redirect('system_backup_page')
    try:
        read_dlb_metadata(uploaded)
        uploaded.seek(0)
    except Exception:
        notify.error(s.get('sysbackup_upload_invalid'), request=request, action='backup_upload_invalid', category='backup')
        return redirect('system_backup_page')
    stamp = timezone.now().strftime('%Y%m%d-%H%M%S')
    default_storage.save(f'{get_system_backup_storage_prefix()}/uploaded-{stamp}.dlb', uploaded)
    notify.success(s.get('sysbackup_upload_done'), request=request, action='backup_upload_done', category='backup')
    return redirect('system_backup_page')


def _resolve_restore_source(request):
    """Resolve the POSTed restore source to a storage path inside the backup prefix."""
    token = str(request.POST.get('backup_token') or '').strip()
    if token:
        backup = _system_backup_model().objects.filter(token=token).first()
        if backup and backup.file_path:
            return backup.file_path
        return None
    filename = str(request.POST.get('backup_file_name') or '').strip()
    # The filename must be a bare name inside the backup prefix — no path traversal.
    if not filename or '/' in filename or '\\' in filename or not filename.lower().endswith('.dlb'):
        return None
    path = f'{get_system_backup_storage_prefix()}/{filename}'
    return path if default_storage.exists(path) else None


@login_required
@require_POST
def system_restore_start_view(request):
    _require_superuser(request)
    s = get_strings()
    if failure := require_current_password(request, redirect_name='system_backup_page'):
        return failure
    if str(request.POST.get('confirm_replace') or '') != 'yes':
        notify.error(s.get('sysrestore_confirm_required'), request=request, action='restore_confirm_required', category='backup')
        return redirect('system_backup_page')
    source_path = _resolve_restore_source(request)
    if not source_path:
        notify.error(s.get('sysrestore_source_missing'), request=request, action='restore_source_missing', category='backup')
        return redirect('system_backup_page')
    SystemRestore = _system_restore_model()
    restore = SystemRestore.objects.create(
        requested_by_username=request.user.get_username(),
        backup_file_path=source_path,
        ignore_version_mismatch=str(request.POST.get('ignore_version_mismatch') or '') == 'yes',
    )
    passphrase = _posted_passphrase(request)
    if not dispatch_system_restore(restore, passphrase=passphrase):
        run_system_restore(restore.pk, passphrase=passphrase)
        restore.refresh_from_db()
    return redirect(f"{reverse('system_backup_page')}?restore={restore.token}")


@login_required
@never_cache
def system_restore_status_view(request, token):
    _require_superuser(request)
    restore = _system_restore_model().objects.filter(token=token).first()
    if restore is None:
        raise Http404
    progress = read_restore_progress(restore)
    return JsonResponse({
        'status': restore.status,
        'report': restore.report or {},
        'error': restore.error[:300] if restore.error else '',
        'progress_percent': 100 if restore.status == 'completed' else progress['progress_percent'],
        'progress_message': progress['progress_message'],
        'stage': progress['stage'],
        'seconds_since_progress': restore.seconds_since_signal() if restore.is_active else 0,
    })


def _attach_restore_progress(restores):
    """Overlay each row with its live progress before rendering or hashing.

    A running restore's fine-grained progress lives in the cache mirror, not the
    row, because the database phase runs inside one transaction — so both the
    template and the revision hash must read through this, never the raw field.
    """
    for restore in restores:
        restore.live_progress = read_restore_progress(restore)
    return restores


def _restore_rows_context(restores):
    return {
        'restores': _attach_restore_progress(restores),
        'DLUX_STRINGS': get_strings(),
    }


def _system_restore_revision(restores):
    """Stable marker for every field rendered in the live restore table."""
    rendered_state = '\x1f'.join(
        ':'.join((
            restore.token,
            restore.status,
            str(restore.live_progress['progress_percent']),
            restore.live_progress['progress_message'],
            restore.live_progress['stage'],
            restore.error or '',
            # Bucketed so an active run refreshes its elapsed marker without the
            # revision churning on every poll.
            str(restore.seconds_since_signal() // 30 if restore.is_active else 0),
        ))
        for restore in _attach_restore_progress(restores)
    )
    return hashlib.sha256(rendered_state.encode('utf-8')).hexdigest()


@login_required
@never_cache
def system_restore_list_status_view(request):
    """Return the current restore-table fragment for live background updates."""
    _require_superuser(request)
    restores = _recent_system_restores()
    return JsonResponse({
        'revision': _system_restore_revision(restores),
        'active': any(restore.is_active for restore in restores),
        'html': render_to_string(
            'dlux/backup/_restore_rows.html',
            _restore_rows_context(restores),
            request=request,
        ),
    })
