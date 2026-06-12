import tempfile

from django.apps import apps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..reports import (
    build_reports_overview,
    build_reports_overview_xlsx,
    dispatch_report_backup,
    normalize_backup_window,
    normalize_report_window,
    write_backup_zip,
)
from ..translations import get_strings
from ..utils import log_user_action, user_can_download_backup, user_can_view_reports


@login_required
def reports_overview_view(request):
    if not user_can_view_reports(request.user):
        raise PermissionDenied
    window = normalize_report_window(request.GET.get("window"))
    overview = build_reports_overview(
        request.user,
        window=window,
        filters={
            "q": request.GET.get("q"),
            "model": request.GET.get("model"),
            "action": request.GET.get("action"),
        },
    )
    return render(request, "dlux/reports/overview.html", {
        "DLUX_STRINGS": get_strings(),
        "overview": overview,
        "window": window,
        "can_download_backup": user_can_download_backup(request.user),
    })


@login_required
def reports_overview_xlsx_view(request):
    if not user_can_view_reports(request.user):
        raise PermissionDenied
    window = normalize_report_window(request.GET.get("window"))
    overview = build_reports_overview(
        request.user,
        window=window,
        filters={
            "q": request.GET.get("q"),
            "model": request.GET.get("model"),
            "action": request.GET.get("action"),
        },
    )
    content = build_reports_overview_xlsx(overview)
    filename = f"dlux-reports-{window}-{timezone.localdate().isoformat()}.xlsx"
    response = HttpResponse(
        content,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _backup_filename(window, when=None):
    stamp = timezone.localdate(when).isoformat()
    return f"dlux-backup-{window}-{stamp}.zip"


@login_required
def reports_backup_zip_view(request):
    """Synchronous, window-aware backup download (fallback when Celery is absent).

    Streams the zip from a temp file instead of building it in RAM; large 'all'
    backups may still exceed reverse-proxy timeouts, which is why the UI prefers
    the background flow below.
    """
    if not user_can_download_backup(request.user):
        raise PermissionDenied
    window = normalize_backup_window(request.GET.get("window"))
    tmp = tempfile.TemporaryFile()
    try:
        manifest = write_backup_zip(request.user, tmp, window=window)
    except Exception:
        tmp.close()
        raise
    log_user_action(
        request,
        "EXPORT",
        model_name="Dlux Reports Backup",
        details={
            "window": window,
            "models": len(manifest["models"]),
            "files": len(manifest["files"]),
        },
    )
    tmp.seek(0)
    return FileResponse(
        tmp,
        as_attachment=True,
        filename=_backup_filename(window),
        content_type="application/zip",
    )


@login_required
@require_POST
def reports_backup_start_view(request):
    """Start a backup build. Queues it on Celery when a live worker is reachable;
    otherwise tells the client to use the synchronous download URL."""
    if not user_can_download_backup(request.user):
        raise PermissionDenied
    window = normalize_backup_window(request.POST.get("window"))
    ReportBackup = apps.get_model("dlux", "ReportBackup")
    backup = ReportBackup.objects.create(user=request.user, window=window)
    if dispatch_report_backup(backup):
        return JsonResponse({
            "ok": True,
            "async": True,
            "token": backup.token,
            "status_url": reverse("reports_backup_status", args=[backup.token]),
        })
    backup.delete()
    return JsonResponse({
        "ok": True,
        "async": False,
        "download_url": f"{reverse('reports_backup_zip')}?window={window}",
    })


def _get_own_backup_or_404(request, token):
    if not user_can_download_backup(request.user):
        raise PermissionDenied
    ReportBackup = apps.get_model("dlux", "ReportBackup")
    backup = ReportBackup.objects.filter(token=token, user=request.user).first()
    if backup is None:
        raise Http404
    return backup


@login_required
def reports_backup_status_view(request, token):
    backup = _get_own_backup_or_404(request, token)
    ReportBackup = type(backup)
    payload = {
        "status": backup.status,
        "window": backup.window,
        "file_size": backup.file_size,
        "error": backup.error[:200] if backup.status == ReportBackup.STATUS_FAILED else "",
    }
    if backup.status == ReportBackup.STATUS_COMPLETED:
        payload["download_url"] = reverse("reports_backup_download", args=[backup.token])
    return JsonResponse(payload)


@login_required
def reports_backup_download_view(request, token):
    backup = _get_own_backup_or_404(request, token)
    ReportBackup = type(backup)
    if backup.status != ReportBackup.STATUS_COMPLETED or not backup.file_path:
        raise Http404
    if not default_storage.exists(backup.file_path):
        raise Http404
    return FileResponse(
        default_storage.open(backup.file_path, "rb"),
        as_attachment=True,
        filename=_backup_filename(backup.window, backup.completed_at),
        content_type="application/zip",
    )
