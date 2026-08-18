"""Options-page config import: review a change set, then apply what was ticked.

Distinct from the first-launch import in `system_setup_view`, and deliberately
so. That one fills an empty form — take everything, nothing to lose. This one
runs against a populated, live system, so it inverts the defaults:

* upload only ever *describes* the difference; nothing is written;
* the operator ticks each change they want, and unticked means keep current;
* a key absent from the file is left alone, never reset to a default;
* applying writes a `SystemSettingsSnapshot` first, so revert is a real action.

Three views: preview (parse + diff), apply (snapshot + write), revert.
"""
import json

from django.apps import apps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape
from django.views.decorators.http import require_POST

from ..notifications import notify
from ..system.settings_diff import build_change_set, selected_settings
from ..translations import get_current_language_code, get_strings
from ..utils import (
    apply_system_settings_import,
    export_system_settings_payload,
    normalize_system_settings_import_payload,
)

# A config export is small. Anything much larger is not one, and parsing it
# would only waste memory before failing.
MAX_IMPORT_BYTES = 2 * 1024 * 1024

# Session key holding the pending change set. Keeping it server-side means the
# diff the operator approved is the diff that applies — a client that re-posts
# a doctored payload cannot smuggle in values that were never reviewed.
PENDING_KEY = 'dlux_settings_import_pending'


def _require_superuser(request):
    if not request.user.is_superuser:
        raise PermissionDenied


def _current_settings():
    SystemSettings = apps.get_model('dlux', 'SystemSettings')
    instance = SystemSettings.load()
    return instance, export_system_settings_payload(instance)


@login_required
@require_POST
def settings_import_preview_view(request):
    """Parse an uploaded config file and return the change set for review."""
    _require_superuser(request)
    strings = get_strings(get_current_language_code(request))

    upload = request.FILES.get('config_file')
    if upload is None:
        return JsonResponse(
            {'ok': False, 'message': strings.get(
                'settings_import_no_file', 'Choose a configuration file to import.')},
            status=400,
        )
    if upload.size > MAX_IMPORT_BYTES:
        return JsonResponse(
            {'ok': False, 'message': strings.get(
                'settings_import_too_large', 'That file is too large to be a settings export.')},
            status=400,
        )

    try:
        payload = json.loads(upload.read().decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse(
            {'ok': False, 'message': strings.get(
                'settings_import_invalid_json', 'That file is not valid JSON.')},
            status=400,
        )

    try:
        incoming = normalize_system_settings_import_payload(payload)
    except ValueError as exc:
        return JsonResponse({'ok': False, 'message': str(exc)}, status=400)

    _, current = _current_settings()
    source = {
        'dlux_version': payload.get('dlux_version') if isinstance(payload, dict) else None,
        'format': payload.get('format') if isinstance(payload, dict) else None,
        'filename': upload.name,
    }
    change_set = build_change_set(current['settings'], incoming, source=source)
    # Resolve the group headings here rather than reaching into DLUX_STRINGS
    # from the template, which would need a lookup filter that does not exist.
    for group in change_set['groups']:
        group['label'] = strings.get(group['label_key'], group['key'].title())

    # Held server-side; the apply step re-reads it rather than trusting the post.
    request.session[PENDING_KEY] = change_set
    request.session.modified = True

    # The dynamic modal is URL-driven: it fetches a URL and injects the
    # response. So preview only parks the change set and hands back the address
    # to open — it does not return the markup itself.
    return JsonResponse({
        'ok': True,
        'review_url': reverse('system_settings_import_review'),
        'change_count': change_set['change_count'],
        'unknown_keys': change_set['unknown_keys'],
    })


@login_required
def settings_import_review_view(request):
    """Render the pending change set. Fetched by the dynamic modal.

    GET on purpose: the modal issues a plain GET and expects JSON with an
    `html` key. Nothing is written here — the change set was parked by the preview POST, and this only
    reads it back.
    """
    _require_superuser(request)
    strings = get_strings(get_current_language_code(request))

    change_set = request.session.get(PENDING_KEY)
    if not change_set:
        expired = escape(strings.get(
            'settings_import_expired', 'That review has expired. Upload the file again.'))
        return JsonResponse({'html': f'<p class="text-muted mb-0">{expired}</p>'})

    # The dynamic modal parses the response as JSON and injects `html` — the
    # same contract the other `/sys/.../manage/` modal endpoints use. Returning
    # a bare HTML document makes it fail with a JSON parse error.
    return JsonResponse({'html': render_to_string(
        'dlux/system/settings_import_review.html',
        {
            'change_set': change_set,
            'DLUX_STRINGS': strings,
            'apply_url': reverse('system_settings_import_apply'),
        },
        request=request,
    )})


@login_required
@require_POST
def settings_import_apply_view(request):
    """Apply the ticked changes, after snapshotting what they replace."""
    _require_superuser(request)
    strings = get_strings(get_current_language_code(request))

    change_set = request.session.get(PENDING_KEY)
    if not change_set:
        return JsonResponse(
            {'ok': False, 'message': strings.get(
                'settings_import_expired', 'That review has expired. Upload the file again.')},
            status=400,
        )

    selections = request.POST.getlist('apply')
    instance, current = _current_settings()
    chosen = selected_settings(change_set, selections, current['settings'])
    if not chosen:
        return JsonResponse(
            {'ok': False, 'message': strings.get(
                'settings_import_nothing_selected', 'Select at least one change to apply.')},
            status=400,
        )

    Snapshot = apps.get_model('dlux', 'SystemSettingsSnapshot')
    with transaction.atomic():
        # Snapshot first: taken inside the transaction so a failed apply cannot
        # leave a snapshot claiming a change that never happened.
        Snapshot.objects.create(
            created_by=request.user if request.user.is_authenticated else None,
            reason='config_import',
            payload=current,
            applied_keys=sorted(chosen),
        )
        apply_system_settings_import(
            instance,
            chosen,
            mark_configured=False,      # already configured; this is an edit
            preserve_email_secret=True,  # exports redact it; never blank it out
        )

    request.session.pop(PENDING_KEY, None)
    request.session.modified = True

    notify.success(
        strings.get('settings_import_applied', 'Configuration import applied.'),
        request=request, action='settings_import_apply', category='system',
        metadata={'fields': sorted(chosen)},
    )
    return JsonResponse({'ok': True, 'applied': sorted(chosen)})


@login_required
@require_POST
def settings_import_revert_view(request):
    """Restore the settings captured by a snapshot."""
    _require_superuser(request)
    strings = get_strings(get_current_language_code(request))

    Snapshot = apps.get_model('dlux', 'SystemSettingsSnapshot')
    snapshot = Snapshot.objects.filter(reverted_at__isnull=True).order_by('-created_at').first()
    if snapshot is None:
        return JsonResponse(
            {'ok': False, 'message': strings.get(
                'settings_import_nothing_to_revert', 'There is no import to revert.')},
            status=400,
        )

    instance, _ = _current_settings()
    with transaction.atomic():
        apply_system_settings_import(
            instance, snapshot.payload,
            mark_configured=False, preserve_email_secret=True,
        )
        snapshot.reverted_at = timezone.now()
        snapshot.save(update_fields=['reverted_at'])

    notify.success(
        strings.get('settings_import_reverted', 'Configuration restored from the snapshot.'),
        request=request, action='settings_import_revert', category='system',
    )
    return JsonResponse({'ok': True})
