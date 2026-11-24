"""Status and download of a background job, for the user who started it."""

from django.apps import apps
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from ..background_jobs import content_type, open_file, payload, user_may_use


def _own_job_or_404(request, token):
    DluxJob = apps.get_model('dlux', 'DluxJob')
    job = DluxJob.objects.filter(token=token, user=request.user).first()
    if job is None or not user_may_use(job, request.user):
        raise Http404
    return job


@login_required
@require_GET
@never_cache
def dlux_job_status_view(request, token):
    return JsonResponse(payload(_own_job_or_404(request, token)))


@login_required
@require_GET
@never_cache
def dlux_job_download_view(request, token):
    job = _own_job_or_404(request, token)
    if job.status != type(job).STATUS_COMPLETED:
        raise Http404
    handle = open_file(job)
    if handle is None:
        raise Http404
    return FileResponse(handle, as_attachment=True, filename=job.file_name or job.token,
                        content_type=content_type(job))
