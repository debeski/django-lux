"""ScanLink installer distribution.

Ported from project-archive, where it lived as app code. ScanLink works with any
correctly configured dlux project, so the manifest, the download gate and the
publish flow belong in the package rather than in one project.

Three endpoints:

* ``scanlink/update.json`` — what the tray app polls. Public shape, login-gated,
  and it advertises the highest *parsed* version among active rows so lexical
  ordering can never rank ``0.9`` above ``0.10``.
* ``scanlink/download/<pk>/`` — the only way to the bytes. Installers are stored
  as protected managed assets (off MEDIA_URL by design), so this view is the
  permission gate, not a convenience.
* ``scanlink/releases/upload/`` — superuser-only publish from the settings modal.

Every one of them refuses to do anything while the ScanLink integration is off.
"""
import os

from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from ..models import ScanLinkRelease
from ..system.constants import SETUP_STEP_EXTRAS
from ..translations import get_strings
from ..utils import scanlink_enabled


def _strings():
    try:
        return get_strings()
    except Exception:
        return {}


def _parse_version_key(value):
    """Sort key for a dotted version, tolerant of junk.

    ``0.10.0`` must outrank ``0.9.0``; a string compare gets that backwards, and
    a release that never appears is worse than one that sorts oddly, so an
    unparsable segment becomes 0 rather than raising.
    """
    parts = []
    for chunk in str(value or '').split('.'):
        digits = ''.join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


@login_required
def scanlink_update_manifest(request):
    """Latest active installer per architecture."""
    if not scanlink_enabled():
        return JsonResponse({'latest_version': None, 'downloads': {}, 'sha256': {}})

    active = list(
        ScanLinkRelease.objects.filter(is_active=True).select_related('asset')
    )
    downloads = {}
    sha256 = {}
    latest_version = None
    latest_key = None

    for arch, _label in ScanLinkRelease.ARCH_CHOICES:
        candidates = [r for r in active if r.arch == arch and r.asset_id and r.asset.file]
        if not candidates:
            continue
        best = max(candidates, key=lambda r: _parse_version_key(r.version))
        downloads[arch] = reverse('scanlink_download', args=[best.pk])
        sha256[arch] = best.sha256
        best_key = _parse_version_key(best.version)
        if latest_key is None or best_key > latest_key:
            latest_key = best_key
            latest_version = best.version

    return JsonResponse({
        'latest_version': latest_version,
        'downloads': downloads,
        'sha256': sha256,
    })


@login_required
def scanlink_download(request, pk):
    """Serve an installer to a logged-in user.

    The bytes sit under the protected asset prefix, which generated deployments
    deny at the proxy, so this is the only route to them and the permission check
    has to stay in Django.
    """
    if not scanlink_enabled():
        raise Http404("ScanLink is not enabled on this system.")

    release = get_object_or_404(
        ScanLinkRelease.objects.select_related('asset'), pk=pk, is_active=True,
    )
    stored = getattr(release.asset, 'file', None)
    if not stored or not stored.name:
        raise Http404("No installer file is attached to this release.")

    response = FileResponse(
        stored.open('rb'),
        as_attachment=True,
        filename=os.path.basename(stored.name),
        content_type='application/octet-stream',
    )
    if release.sha256:
        response['X-Content-SHA256'] = release.sha256
    return response


@require_POST
@user_passes_test(lambda user: user.is_superuser)
def scanlink_toggle(request):
    """Flip the ScanLink switch immediately, without waiting for a form save.

    Managing installers is gated on the integration being on, so the save-then-
    reopen-the-step dance stood between an operator and the thing they came to
    do. This writes the same key the settings form writes, so a later Save of the
    Extra Features step agrees with it rather than fighting it.

    Copy-then-set: `extra_config` also holds every downstream project's config
    under `app`, so this must never rebuild the dict.
    """
    from ..models import SystemSettings

    enabled = str(request.POST.get('enabled', '')).strip().lower() in {'1', 'true', 'on', 'yes'}
    record = SystemSettings.load()
    extra_config = dict(record.extra_config or {})
    scanlink = dict(extra_config.get('scanlink') or {}) if isinstance(extra_config.get('scanlink'), dict) else {}
    scanlink['enabled'] = enabled
    extra_config['scanlink'] = scanlink
    record.extra_config = extra_config
    record.save()
    return JsonResponse({'ok': True, 'enabled': enabled})


@user_passes_test(lambda user: user.is_superuser)
def scanlink_releases_modal(request):
    """Publish form plus the current releases, for the dynamic modal.

    The modal fetches this URL and injects `data.html`, so the response must be
    JSON — returning a bare document makes it fail with a parse error and fall
    back to rendering inline.
    """
    from django.template.loader import render_to_string
    from ..forms.scanlink import ScanLinkReleaseForm

    html = render_to_string('dlux/system/scanlink_releases.html', {
        'form': ScanLinkReleaseForm(),
        'releases': ScanLinkRelease.objects.select_related('asset').all()[:20],
        'enabled': scanlink_enabled(),
        'upload_url': reverse('scanlink_release_upload'),
        'settings_step_url': f"{reverse('modal_manager', args=['dlux', 'SystemSettings', 1])}?step={SETUP_STEP_EXTRAS}",
        'DLUX_STRINGS': _strings(),
    }, request=request)
    return JsonResponse({'html': html})


@require_POST
@user_passes_test(lambda user: user.is_superuser)
def scanlink_release_upload(request):
    """Publish an installer from the Extra Features settings modal."""
    from ..forms.scanlink import ScanLinkReleaseForm
    from ..notifications import notify

    s = _strings()
    if not scanlink_enabled():
        return JsonResponse(
            {'ok': False, 'message': s.get(
                'scanlink_disabled_message',
                'ScanLink is switched off. Enable it under Extra Features first.',
            )},
            status=400,
        )

    form = ScanLinkReleaseForm(request.POST, request.FILES, user=request.user)
    if not form.is_valid():
        details = []
        for field, errors in form.errors.items():
            label = form.fields[field].label if field in form.fields else ''
            details.extend(f"{label}: {error}" if label else str(error) for error in errors)
        return JsonResponse(
            {'ok': False, 'message': '; '.join(details) or s.get(
                'scanlink_release_failed', 'Could not publish the release.')},
            status=400,
        )

    release = form.save()
    notify.success(
        s.get('scanlink_release_published', 'Published ScanLink {version} ({arch}).').format(
            version=release.version, arch=release.arch,
        ),
        request=request, flash=True, persist=False,
    )
    return JsonResponse({'ok': True, 'pk': release.pk})


# POST-only card actions: dlux route discovery would otherwise offer these as
# navigable pages in the sidebar catalog and global search, under humanized
# English route names no translation can reach.
scanlink_release_upload.sidebar_exclude = True
scanlink_download.sidebar_exclude = True
scanlink_update_manifest.sidebar_exclude = True
scanlink_releases_modal.sidebar_exclude = True
scanlink_toggle.sidebar_exclude = True
