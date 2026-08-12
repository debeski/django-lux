from django.apps import apps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models.deletion import ProtectedError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from ..assets import collect_asset_usages
from ..notifications import notify
from ..translations import get_strings


def _require_superuser(request):
    if not getattr(request.user, 'is_superuser', False):
        raise PermissionDenied


def _manager_context(form):
    Asset = apps.get_model('dlux', 'ManagedAsset')
    FontFamily = apps.get_model('dlux', 'ManagedFontFamily')
    assets = list(Asset.objects.select_related('created_by').all())
    for asset in assets:
        asset.usage_report = collect_asset_usages(asset)
    return {
        'form': form,
        'assets': assets,
        'managed_fonts': FontFamily.objects.prefetch_related('variants__asset').all(),
    }


def _manager_html(request, form):
    return render_to_string('dlux/assets/manager.html', _manager_context(form), request=request)


@login_required
def asset_manager_page(request):
    _require_superuser(request)
    from ..forms.assets import ManagedAssetUploadForm

    form = ManagedAssetUploadForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        asset, created, font = form.save(user=request.user)
        strings = get_strings()
        if font:
            template = strings.get('asset_font_registered', 'Font “{font}” registered with “{asset}”.')
            message = template.format(font=font.label, asset=asset.title)
        elif created:
            message = strings.get('asset_uploaded', 'File “{asset}” uploaded.').format(asset=asset.title)
        else:
            message = strings.get('asset_reused', 'Existing file “{asset}” reused.').format(asset=asset.title)
        notify.success(message, request=request, action='managed_asset_upload', category='assets')
        return JsonResponse({'success': True})
    html = _manager_html(request, form)
    return JsonResponse({'html': html}, status=400 if request.method == 'POST' else 200)


@login_required
@require_POST
def asset_manager_delete(request, pk):
    _require_superuser(request)
    Asset = apps.get_model('dlux', 'ManagedAsset')
    asset = get_object_or_404(Asset, pk=pk)
    strings = get_strings()
    usages = collect_asset_usages(asset)
    if usages:
        message = strings.get('asset_delete_in_use', 'File “{asset}” is in use and cannot be deleted.').format(asset=asset.title)
        notify.error(message, request=request, action='managed_asset_delete_blocked', category='assets')
        return JsonResponse({'success': False, 'error': message}, status=409)
    title = asset.title
    try:
        asset.delete()
    except ProtectedError:
        message = strings.get('asset_delete_in_use', 'File “{asset}” is in use and cannot be deleted.').format(asset=title)
        notify.error(message, request=request, action='managed_asset_delete_blocked', category='assets')
        return JsonResponse({'success': False, 'error': message}, status=409)
    else:
        message = strings.get('asset_deleted', 'File “{asset}” deleted.').format(asset=title)
        notify.success(message, request=request, action='managed_asset_delete', category='assets')
        return JsonResponse({'success': True})
