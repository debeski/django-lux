from django.apps import apps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models.deletion import ProtectedError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.decorators.http import require_POST

from ..assets import collect_asset_usages
from ..notifications import notify
from ..ribbon import Ribbon, build_ribbon_tabs
from ..translations import get_strings


ASSET_TABS = ('images', 'fonts')


def _require_superuser(request):
    if not getattr(request.user, 'is_superuser', False):
        raise PermissionDenied


def _active_tab(request):
    requested = str(request.GET.get('asset_tab') or '').strip()
    return requested if requested in ASSET_TABS else 'images'


def _manager_ribbon(request, active_tab, counts):
    strings = get_strings()
    tabs = build_ribbon_tabs({
        'param': 'asset_tab',
        'default': active_tab,
        'items': [
            {'key': 'images', 'label': strings.get('asset_tab_images', 'Images'), 'icon': 'bi bi-images'},
            {'key': 'fonts', 'label': strings.get('asset_tab_fonts', 'Fonts'), 'icon': 'bi bi-fonts'},
        ],
    }, request=request, counts=counts, locked=True)
    base_url = reverse('manage_assets')
    for tab in tabs:
        tab.url = f'{base_url}{tab.url}'
    return Ribbon(strips=[tabs], layout='compact', style='accent', show_title=False, strings=strings)


def _manager_context(request, active_tab, *, image_form=None, font_form=None):
    from ..forms.assets import ManagedFontUploadForm, ManagedImageUploadForm

    Asset = apps.get_model('dlux', 'ManagedAsset')
    FontFamily = apps.get_model('dlux', 'ManagedFontFamily')
    images = list(Asset.objects.select_related('created_by').filter(kind='image'))
    for asset in images:
        asset.usage_report = collect_asset_usages(asset)
    managed_fonts = list(FontFamily.objects.prefetch_related('variants__asset').all())
    return {
        'active_tab': active_tab,
        'ribbon': _manager_ribbon(request, active_tab, {
            'images': len(images),
            'fonts': len(managed_fonts),
        }),
        'image_form': image_form or ManagedImageUploadForm(),
        'font_form': font_form or ManagedFontUploadForm(),
        'images': images,
        'managed_fonts': managed_fonts,
        'image_action_url': f"{reverse('manage_assets')}?asset_tab=images",
        'font_action_url': f"{reverse('manage_assets')}?asset_tab=fonts",
    }


def _manager_html(request, active_tab, **forms):
    return render_to_string(
        'dlux/assets/manager.html',
        _manager_context(request, active_tab, **forms),
        request=request,
    )


def _asset_payload(asset):
    return {
        'id': asset.pk,
        'title': asset.title,
        'url': asset.url,
        'kind': asset.kind,
    }


def _first_form_error(form):
    for errors in form.errors.values():
        if errors:
            return str(errors[0])
    return get_strings().get('asset_upload_failed', 'The file could not be uploaded.')


@login_required
@require_POST
def managed_image_picker_upload(request):
    _require_superuser(request)
    from ..forms.assets import ManagedImageUploadForm

    form = ManagedImageUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        return JsonResponse({'success': False, 'error': _first_form_error(form)}, status=400)
    assets, _created = form.save(user=request.user)
    return JsonResponse({
        'success': True,
        'assets': [_asset_payload(asset) for asset in assets],
    })


@login_required
def asset_manager_page(request):
    _require_superuser(request)
    from ..forms.assets import ManagedFontUploadForm, ManagedImageUploadForm

    active_tab = _active_tab(request)
    form_class = ManagedFontUploadForm if active_tab == 'fonts' else ManagedImageUploadForm
    form = form_class(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        strings = get_strings()
        if active_tab == 'fonts':
            asset, _created, font = form.save(user=request.user)
            template = strings.get('asset_font_registered', 'Font “{font}” registered with “{asset}”.')
            message = template.format(font=font.label, asset=asset.title)
        else:
            assets, created = form.save(user=request.user)
            first = assets[0]
            if len(assets) > 1:
                template = strings.get('assets_uploaded', '{count} files uploaded ({created} new).')
                message = template.format(count=len(assets), created=created)
            elif created:
                message = strings.get('asset_uploaded', 'File “{asset}” uploaded.').format(asset=first.title)
            else:
                message = strings.get('asset_reused', 'Existing file “{asset}” reused.').format(asset=first.title)
        notify.success(message, request=request, action='managed_asset_upload', category='assets')
        payload = [_asset_payload(asset) for asset in (assets if active_tab == 'images' else [asset])]
        return JsonResponse({'success': True, 'reload_current': True, 'assets': payload})
    forms = {'font_form': form} if active_tab == 'fonts' else {'image_form': form}
    html = _manager_html(request, active_tab, **forms)
    response = {'html': html}
    if request.method == 'POST':
        response['error'] = _first_form_error(form)
    return JsonResponse(response, status=400 if request.method == 'POST' else 200)


@login_required
@require_POST
def asset_manager_rename(request, pk):
    _require_superuser(request)
    Asset = apps.get_model('dlux', 'ManagedAsset')
    asset = get_object_or_404(Asset, pk=pk, kind='image')
    title = str(request.POST.get('title') or '').strip()
    if not title:
        return JsonResponse({'success': False, 'error': get_strings().get(
            'asset_name_required', 'Enter a name for this image.')}, status=400)
    if len(title) > Asset._meta.get_field('title').max_length:
        return JsonResponse({'success': False, 'error': get_strings().get(
            'asset_name_too_long', 'The image name is too long.')}, status=400)
    asset.title = title
    asset.save(update_fields=['title', 'updated_at'])
    return JsonResponse({'success': True, 'title': asset.title})


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

# Answers `{'html': ...}`, so it is a modal endpoint rather than a page —
# what a ribbon button must open as a dynamic modal, not navigate to.
asset_manager_page.dlux_modal = True
