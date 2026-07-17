from datetime import timedelta

from django.apps import apps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_protect

from .. import __version__
from ..guards import require_current_password
from ..updater import UpdaterError
from ..updater.health import runtime_probe_token
from ..updater.image_update import (
    active_image_update,
    image_status_summary,
    image_update_available,
    queue_image_update,
    serialize_image_update,
)
from ..updater.service import get_ui_state, previous_apply_failure, queue_run, serialize_run, updates_enabled
from ..utils import is_global_staff, log_audit_event


def _require_diagnostics_access(request):
    user = getattr(request, "user", None)
    if not user or not (getattr(user, "is_superuser", False) or is_global_staff(user)):
        raise PermissionDenied


def _require_superuser(request):
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_superuser", False):
        raise PermissionDenied


def _run_model():
    return apps.get_model("dlux", "DluxUpdateRun")


def _queue_response(run, *, cached=False):
    return JsonResponse({
        "ok": True,
        "cached": cached,
        "run": serialize_run(run) if run else None,
        "state": get_ui_state(),
        "state_url": reverse("dlux_update_state"),
        "run_url": reverse("dlux_update_run", args=[run.token]) if run else "",
    })


@require_GET
def dlux_update_runtime_health(request):
    import hmac
    from django.conf import settings

    supplied = str(request.headers.get("X-Dlux-Updater-Probe") or "")
    expected = runtime_probe_token(settings.SECRET_KEY)
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise Http404
    return JsonResponse({"ok": True, "version": __version__})


@login_required
@require_GET
def dlux_update_state_view(request):
    _require_diagnostics_access(request)
    state = get_ui_state()
    state["can_manage"] = bool(request.user.is_superuser and state["enabled"])
    latest_run = _run_model().objects.order_by("-created_at").first()
    # Image-level (full container) update availability + any in-flight run.
    # Registry-driven: composer publishes availability; we just read it.
    available, target, reason = image_update_available()
    active_image = active_image_update()
    state["image_update_available"] = available
    state["image_update_target"] = target
    state["image_update_reason"] = reason if available else ""
    # Application-image facts for the Updates card (app version, running/published
    # digest, last update + registry check time).
    state["image"] = image_status_summary()
    # Re-apply guard: if the latest available wheel version already failed a
    # previous apply, the review modal warns and requires an explicit ack.
    state["latest_version_failure"] = previous_apply_failure(state.get("latest_version"))
    return JsonResponse({
        "ok": True,
        "state": state,
        "run": serialize_run(latest_run) if latest_run else None,
        "image_update": serialize_image_update(active_image, include_log=True),
    })


@login_required
@require_GET
def dlux_update_run_view(request, token):
    _require_superuser(request)
    run = _run_model().objects.filter(token=token).first()
    if run is None:
        raise Http404
    return JsonResponse({"ok": True, "run": serialize_run(run, include_log=True)})


@login_required
@csrf_protect
@require_POST
def dlux_update_check_view(request):
    _require_superuser(request)
    if not updates_enabled():
        return JsonResponse({"ok": False, "error": "Inline DjangoLux updates are disabled."}, status=409)
    State = apps.get_model("dlux", "DluxUpdateState")
    state = State.load()
    # Short anti-spam debounce: a manual check queues a real PyPI index fetch, so
    # collapse rapid repeat clicks onto the most recent result. Kept brief (10s) so
    # an operator who just published a release can re-check almost immediately.
    if (
        not state.active_run_token
        and state.last_checked_at
        and timezone.now() - state.last_checked_at < timedelta(seconds=10)
    ):
        return _queue_response(None, cached=True)
    try:
        run = queue_run(_run_model().ACTION_CHECK, request.user.get_username())
    except UpdaterError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=409)
    log_audit_event(
        request,
        "dlux_update_check",
        "DLUX_UPDATE_CHECK",
        model_name="DjangoLux updater",
        details={"run_token": run.token},
    )
    return _queue_response(run)


@login_required
@csrf_protect
@require_POST
def dlux_update_skip_view(request):
    """Permanently skip (or un-skip) a version so the update check never offers it.
    Superuser-only; audited. The skip list is a state preference, so this works
    even when inline apply itself is disabled."""
    _require_superuser(request)
    version = str(request.POST.get("version") or "").strip()
    if not version:
        return JsonResponse({"ok": False, "error": "No version specified."}, status=400)
    unskip = str(request.POST.get("unskip") or "").strip().lower() in ("1", "true", "yes", "on")
    from ..updater.service import set_version_skipped
    state = set_version_skipped(version, skipped=not unskip)
    log_audit_event(
        request,
        "dlux_update_unskip" if unskip else "dlux_update_skip",
        "DLUX_UPDATE_SKIP",
        model_name="DjangoLux updater",
        details={"version": version, "unskip": unskip},
    )
    return JsonResponse({"ok": True, "state": state})


def _password_guard(request):
    failure = require_current_password(request, field_name="current_password")
    return failure


@login_required
@csrf_protect
@require_POST
def dlux_update_apply_view(request):
    _require_superuser(request)
    if failure := _password_guard(request):
        return failure
    backup_mode = str(request.POST.get("backup_mode") or "").strip().lower()
    try:
        run = queue_run(_run_model().ACTION_APPLY, request.user.get_username(), backup_mode=backup_mode)
    except UpdaterError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=409)
    log_audit_event(
        request,
        "dlux_update_apply",
        "DLUX_UPDATE_APPLY",
        model_name="DjangoLux updater",
        details={"run_token": run.token, "target_version": run.target_version, "backup_mode": run.backup_mode},
    )
    return _queue_response(run)


@login_required
@csrf_protect
@require_POST
def dlux_update_image_view(request):
    """Queue an image-level update. Executed by the external composer-updater;
    dlux backs up, enters maintenance, hands off, and finalizes."""
    _require_superuser(request)
    if failure := _password_guard(request):
        return failure
    backup_mode = str(request.POST.get("backup_mode") or "").strip().lower()
    try:
        row = queue_image_update(request.user.get_username(), backup_mode=backup_mode)
    except UpdaterError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=409)
    log_audit_event(
        request,
        "dlux_update_image",
        "DLUX_UPDATE_IMAGE",
        model_name="DjangoLux updater",
        details={"image_token": row.token, "target_version": row.target_version, "backup_mode": row.backup_mode},
    )
    return JsonResponse({
        "ok": True,
        "image_update": serialize_image_update(row, include_log=True),
        "state_url": reverse("dlux_update_state"),
    })


@login_required
@csrf_protect
@require_POST
def dlux_update_rollback_view(request):
    _require_superuser(request)
    if failure := _password_guard(request):
        return failure
    try:
        run = queue_run(_run_model().ACTION_ROLLBACK, request.user.get_username())
    except UpdaterError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=409)
    log_audit_event(
        request,
        "dlux_update_rollback",
        "DLUX_UPDATE_ROLLBACK",
        model_name="DjangoLux updater",
        details={"run_token": run.token, "target_version": run.target_version},
    )
    return _queue_response(run)
