from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from ..reports import (
    build_backup_zip,
    build_reports_overview,
    build_reports_overview_xlsx,
    normalize_report_window,
)
from ..translations import get_strings
from ..utils import user_can_download_backup, user_can_view_reports


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
    return render(request, "microsys/reports/overview.html", {
        "MS_TRANS": get_strings(),
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
    filename = f"microsys-reports-{window}-{timezone.localdate().isoformat()}.xlsx"
    response = HttpResponse(
        content,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
def reports_backup_zip_view(request):
    if not user_can_download_backup(request.user):
        raise PermissionDenied
    content, _manifest = build_backup_zip(request)
    filename = f"microsys-backup-{timezone.localdate().isoformat()}.zip"
    response = HttpResponse(content, content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
