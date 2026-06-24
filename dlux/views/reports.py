import tempfile
from datetime import timedelta

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
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
    can_download_backup = user_can_download_backup(request.user)
    active_backup = latest_completed_backup = None
    if can_download_backup:
        active_backup, latest_completed_backup = _report_backup_page_state(request.user)
    return render(request, "dlux/reports/overview.html", {
        "DLUX_STRINGS": get_strings(),
        "overview": overview,
        "window": window,
        "can_download_backup": can_download_backup,
        "active_report_backup": active_backup,
        "latest_completed_report_backup": latest_completed_backup,
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


def _report_backup_page_state(user):
    """Return the durable active/latest backup state shown on the reports page."""
    ReportBackup = apps.get_model("dlux", "ReportBackup")
    active_statuses = (ReportBackup.STATUS_PENDING, ReportBackup.STATUS_RUNNING)
    stale_cutoff = timezone.now() - timedelta(hours=24)
    stale_backups = list(ReportBackup.objects.filter(
        user=user,
        status__in=active_statuses,
        created_at__lt=stale_cutoff,
    ))
    if stale_backups:
        error = "Backup did not finish within 24 hours."
        now = timezone.now()
        ReportBackup.objects.filter(pk__in=[backup.pk for backup in stale_backups]).update(
            status=ReportBackup.STATUS_FAILED,
            completed_at=now,
            error=error,
        )
        from ..backup_progress import finish_backup_progress
        for backup in stale_backups:
            backup.status = ReportBackup.STATUS_FAILED
            backup.completed_at = now
            backup.error = error
            finish_backup_progress(backup, success=False, error=error)
    active = ReportBackup.objects.filter(
        user=user,
        status__in=active_statuses,
    ).order_by("created_at").first()
    latest_completed = ReportBackup.objects.filter(
        user=user,
        status=ReportBackup.STATUS_COMPLETED,
    ).exclude(file_path="").order_by("-completed_at", "-created_at").first()
    return active, latest_completed


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
    with transaction.atomic():
        get_user_model()._default_manager.select_for_update().get(pk=request.user.pk)
        active, _latest = _report_backup_page_state(request.user)
        if active is not None:
            return JsonResponse({
                "ok": True,
                "async": True,
                "reused": True,
                "token": active.token,
                "status_url": reverse("reports_backup_status", args=[active.token]),
            })
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
@never_cache
def reports_backup_status_view(request, token):
    backup = _get_own_backup_or_404(request, token)
    ReportBackup = type(backup)
    payload = {
        "status": backup.status,
        "window": backup.window,
        "file_size": backup.file_size,
        "model_count": backup.model_count,
        "file_count": backup.file_count,
        "missing_file_count": backup.missing_file_count,
        "progress_percent": backup.progress_percent,
        "progress_message": backup.progress_message,
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
