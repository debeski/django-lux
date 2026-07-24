from urllib.parse import urlparse

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET, require_POST

from ..notifications import notify
from ..translations import get_strings
from ..updater import control_link
from ..updater.service import runtime_store


def _require_superuser(request):
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_superuser", False):
        raise PermissionDenied


def _store_or_none():
    try:
        return runtime_store()
    except Exception:
        return None


def _valid_control_url(url):
    parsed = urlparse(url or "")
    if not parsed.netloc:
        return False
    if parsed.scheme == "https":
        return True
    return parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}


def _state():
    store = _store_or_none()
    if store is None:
        return {"bridge_available": False, "enrolled": False, "pending": False,
                "control_url": "", "last_enroll": {}, "agent_status_present": False}
    return control_link.control_link_state(store)


@login_required
@require_GET
def control_panel_page(request):
    _require_superuser(request)
    return render(request, "dlux/control_link.html", {"link": _state()})


@login_required
@require_GET
def control_panel_status_view(request):
    _require_superuser(request)
    return JsonResponse({"ok": True, "link": _state()})


@login_required
@csrf_protect
@require_POST
def control_panel_connect_view(request):
    _require_superuser(request)
    strings = get_strings()
    control_url = (request.POST.get("control_url") or "").strip()
    pairing_token = (request.POST.get("pairing_token") or "").strip()
    store = _store_or_none()

    if store is None:
        notify.error(
            strings.get("control_link_bridge_unavailable",
                        "The agent runtime bridge is unavailable on this host."),
            request=request,
            action="control_panel_pair",
            category="control_panel",
            persist=False,
            flash=True,
        )
    elif not _valid_control_url(control_url):
        notify.error(
            strings.get("control_link_bad_url",
                        "Enter a valid https:// control panel URL."),
            request=request,
            action="control_panel_pair",
            category="control_panel",
            persist=False,
            flash=True,
        )
    elif not pairing_token:
        notify.error(
            strings.get("control_link_missing_token",
                        "Paste the one-use pairing token from the control panel."),
            request=request,
            action="control_panel_pair",
            category="control_panel",
            persist=False,
            flash=True,
        )
    else:
        # The web tier cannot write the agent bridge (read-only runtime mount);
        # the update worker publishes this on its next tick.
        control_link.queue_enroll_request(control_url, pairing_token)
        notify.success(
            strings.get("control_link_requested",
                        "Pairing requested. The agent will connect shortly."),
            request=request,
            action="control_panel_pair",
            category="control_panel",
            persist=False,
            flash=True,
        )
    return redirect(reverse("control_panel"))


@login_required
@csrf_protect
@require_POST
def control_panel_cancel_view(request):
    _require_superuser(request)
    control_link.queue_cancel_request()
    notify.success(
        get_strings().get("control_link_cancelled", "Pending pairing request cleared."),
        request=request,
        action="control_panel_pair_cancel",
        category="control_panel",
        persist=False,
        flash=True,
    )
    return redirect(reverse("control_panel"))
