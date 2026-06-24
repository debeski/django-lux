import hashlib
import logging

from django.apps import apps
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
    dispatch_system_backup,
    dispatch_system_restore,
    read_dlb_metadata,
    get_system_backup_storage_prefix,
    run_system_backup,
    run_system_restore,
)
from ..guards import require_current_password
from ..notifications import notify
from ..translations import get_strings
from ..utils import get_system_config

logger = logging.getLogger('dlux')

DLB_UPLOAD_MAX_MB_DEFAULT = 512


def _require_superuser(request):
    user = getattr(request, 'user', None)
    if not user or not getattr(user, 'is_superuser', False):
        raise PermissionDenied


def _system_backup_model():
    return apps.get_model('dlux', 'SystemBackup')


def _system_restore_model():
    return apps.get_model('dlux', 'SystemRestore')


def _recent_system_backups():
    return list(_system_backup_model().objects.all()[:20])


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
        ))
        for backup in backups
    )
    return hashlib.sha256(rendered_state.encode('utf-8')).hexdigest()


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
    SystemRestore = _system_restore_model()
    backups = _recent_system_backups()
    return render(request, 'dlux/backup/manage.html', {
        'DLUX_STRINGS': get_strings(),
        'backups': backups,
        'backup_revision': _system_backup_revision(backups),
        'restores': SystemRestore.objects.all()[:10],
        'orphan_files': _orphan_dlb_files(),
        'backup_config': get_system_config().get('backup_config', {}),
    })


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
    SystemBackup = _system_backup_model()
    backup = SystemBackup.objects.create(
        requested_by_username=request.user.get_username(),
        passphrase_required=bool(passphrase),
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
    return JsonResponse({
        'revision': _system_backup_revision(backups),
        'active': any(backup.status in {'pending', 'running'} for backup in backups),
        'items': [
            {
                'token': backup.token,
                'status': backup.status,
                'progress_percent': backup.progress_percent,
                'progress_message': backup.progress_message,
            }
            for backup in backups
        ],
        'html': render_to_string(
            'dlux/backup/_backup_rows.html',
            {'backups': backups, 'DLUX_STRINGS': get_strings()},
            request=request,
        ),
    })


@login_required
@never_cache
def system_backup_status_view(request, token):
    backup = _get_backup_or_404(request, token)
    SystemBackup = type(backup)
    payload = {
        'status': backup.status,
        'file_size': backup.file_size,
        'rows': backup.row_count,
        'files': backup.file_count,
        'progress_percent': backup.progress_percent,
        'progress_message': backup.progress_message,
        'error': backup.error[:200] if backup.status == SystemBackup.STATUS_FAILED else '',
    }
    if backup.status == SystemBackup.STATUS_COMPLETED:
        payload['download_url'] = reverse('system_backup_download', args=[backup.token])
    return JsonResponse(payload)


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
        notify.error(s.get('sysbackup_upload_invalid'), request=request, action='backup_upload_invalid', category='backup')
        return redirect('system_backup_page')
    max_mb = DLB_UPLOAD_MAX_MB_DEFAULT
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
def system_restore_status_view(request, token):
    _require_superuser(request)
    restore = _system_restore_model().objects.filter(token=token).first()
    if restore is None:
        raise Http404
    return JsonResponse({
        'status': restore.status,
        'report': restore.report or {},
        'error': restore.error[:300] if restore.error else '',
    })
