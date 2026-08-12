"""Global app system-config writes.

Separate from :mod:`dlux.api.preferences` on purpose: that module writes the
caller's own profile, this one writes project-wide state and is **superuser
only**. Keeping them apart makes the differing authorization gate visible
instead of buried among per-user handlers.
"""
import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from ._shared import _SAFE_NAMESPACE, logger
from ..options import AppSystemConfigError, write_app_system_config
from ..system.constants import PREFERENCES_APP_NAMESPACE_MAXLEN

@login_required
@require_POST
def update_app_system_config(request, namespace):
    """Set (or clear) one app-owned GLOBAL system-config namespace.

    Writes only ``SystemSettings.extra_config['app'][<namespace>]`` — Dlux-owned
    config and every other namespace are left untouched. This is global,
    project-wide state, so it is **superuser-only**, POST + CSRF, size-capped,
    audit-logged, and cache-refreshed (via ``SystemSettings.save``). The body is
    the namespace's new value (opaque JSON); an empty/``null`` body clears it.

    Deliberately *not* a general settings mutator: it can never reach Dlux's own
    settings fields or other ``extra_config`` keys, so it cannot be used to
    tamper with security-relevant configuration.
    """
    # Firm gate: global config is superuser-only. Non-superusers get 403 even
    # though they passed @login_required.
    if not request.user.is_superuser:
        return JsonResponse({'status': 'error', 'message': 'Superuser required.'}, status=403)

    namespace = str(namespace or '').strip()
    if not namespace or len(namespace) > PREFERENCES_APP_NAMESPACE_MAXLEN or not _SAFE_NAMESPACE.match(namespace):
        return JsonResponse({'status': 'error', 'message': 'Invalid namespace.'}, status=400)

    try:
        if request.content_type == 'application/json':
            body = json.loads(request.body or b'null')
        else:
            raw = request.POST.get('value')
            body = json.loads(raw) if raw not in (None, '') else None
    except (TypeError, ValueError):
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON body.'}, status=400)

    try:
        stored_value = write_app_system_config(namespace, body, request=request)
        return JsonResponse({
            'status': 'success',
            'namespace': namespace,
            'value': stored_value,
        })
    except AppSystemConfigError as exc:
        return JsonResponse({'status': 'error', 'message': exc.message}, status=exc.status_code)
    except Exception:
        logger.exception("Failed to update app system-config '%s' by user pk=%s", namespace, request.user.pk)
        return JsonResponse({'status': 'error', 'message': 'Unable to update system config.'}, status=400)
