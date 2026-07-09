# Fundemental imports
import json

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.utils.module_loading import import_string
from django.views.decorators.http import require_POST
from django_tables2 import RequestConfig

# Project imports
from ..utils import is_scope_enabled

User = get_user_model()


def _require_superuser(request):
    if not request.user.is_superuser:
        raise PermissionDenied


def _render_scope_manager(request):
    Scope = apps.get_model('dlux', 'Scope')
    ScopeTable = import_string('dlux.tables.ScopeTable')
    table = ScopeTable(Scope.objects.all(), request=request)
    RequestConfig(request).configure(table)
    return render_to_string('dlux/scopes/scope_manager.html', {'table': table}, request=request)


# Scope Management — AJAX modal: returns scope table (superuser only)
@login_required
def manage_scopes(request):
    """
    Returns the initial modal content with the table.
    """
    _require_superuser(request)
    return JsonResponse({'html': _render_scope_manager(request)})

# Scope Management — AJAX: returns add/edit scope form partial
@login_required
def get_scope_form(request, pk=None):
    """
    Returns the Add/Edit form partial.
    """
    _require_superuser(request)
    ScopeForm = import_string('dlux.forms.ScopeForm')
    Scope = apps.get_model('dlux', 'Scope')

    if pk:
        scope = get_object_or_404(Scope, pk=pk)
        form = ScopeForm(instance=scope)
    else:
        form = ScopeForm()
        
    html = render_to_string('dlux/scopes/scope_form.html', {'form': form, 'scope_id': pk}, request=request)
    return JsonResponse({'html': html})

@login_required
def save_scope(request, pk=None):
    """
    Handles form submission. Returns updated table on success, or form with errors on failure.
    """
    _require_superuser(request)
    ScopeForm = import_string('dlux.forms.ScopeForm')
    Scope = apps.get_model('dlux', 'Scope')

    if request.method == "POST":
        if pk:
            scope = get_object_or_404(Scope, pk=pk)
            form = ScopeForm(request.POST, instance=scope)
        else:
            form = ScopeForm(request.POST)

        if form.is_valid():
            form.save()
            return JsonResponse({'success': True, 'html': _render_scope_manager(request)})
        else:
            # Return form with errors
            html = render_to_string('dlux/scopes/scope_form.html', {'form': form, 'scope_id': pk}, request=request)
            return JsonResponse({'success': False, 'html': html})
    
    return JsonResponse({'success': False, 'error': 'Invalid method'})

# Scope Management — Scope deletion endpoint (currently disabled for safety)
@login_required
def delete_scope(request, pk):
    _require_superuser(request)
    return JsonResponse({'success': False, 'error': 'تم تعطيل حذف النطاقات لأسباب أمنية.'})


@login_required
@require_POST
def toggle_scope_public_registration_default(request, pk):
    _require_superuser(request)
    Scope = apps.get_model('dlux', 'Scope')
    scope = get_object_or_404(Scope, pk=pk)
    if scope.is_public_registration_default:
        scope.is_public_registration_default = False
        scope.save(update_fields=['is_public_registration_default'])
    else:
        Scope.objects.filter(is_public_registration_default=True).exclude(pk=scope.pk).update(
            is_public_registration_default=False
        )
        scope.is_public_registration_default = True
        scope.save(update_fields=['is_public_registration_default'])
    return JsonResponse({
        'success': True,
        'is_default': scope.is_public_registration_default,
        'html': _render_scope_manager(request),
    })


@login_required
def scope_detail(request, pk):
    _require_superuser(request)
    Scope = apps.get_model('dlux', 'Scope')
    Profile = apps.get_model('dlux', 'Profile')
    ActivityLog = apps.get_model('dlux', 'ActivityLog')
    GroupProfile = apps.get_model('dlux', 'GroupProfile')
    scope = get_object_or_404(Scope, pk=pk)

    users = User.objects.filter(profile__scope=scope).order_by('username')[:12]
    user_count = User.objects.filter(profile__scope=scope).count()
    group_presets = GroupProfile.objects.filter(scope=scope).select_related('group').order_by('group__name')[:12]
    preset_count = GroupProfile.objects.filter(scope=scope).count()
    activity_count = ActivityLog.all_objects.filter(scope=scope).count()
    recent_activity = ActivityLog.all_objects.filter(scope=scope).order_by('-created_at')[:8]

    data_counts = []
    for model in apps.get_models():
        if not model._meta.managed:
            continue
        if model in {Profile, ActivityLog}:
            continue
        field_names = {field.name for field in model._meta.fields}
        if 'scope' not in field_names:
            continue
        try:
            count = model._default_manager.filter(scope=scope).count()
        except Exception:
            continue
        if count:
            data_counts.append({
                'label': model._meta.verbose_name_plural or model._meta.verbose_name,
                'count': count,
            })
    data_counts = sorted(data_counts, key=lambda item: str(item['label']).lower())[:16]

    html = render_to_string(
        'dlux/scopes/scope_detail.html',
        {
            'scope': scope,
            'users': users,
            'user_count': user_count,
            'preset_count': preset_count,
            'activity_count': activity_count,
            'recent_activity': recent_activity,
            'data_counts': data_counts,
            'group_presets': group_presets,
        },
        request=request,
    )
    return JsonResponse({'html': html})

# Scope Management — Toggles the scope system on/off with safety checks
@login_required
def toggle_scopes(request):
    _require_superuser(request)
    if request.method == "POST":
        ScopeSettings = apps.get_model('dlux', 'ScopeSettings')
        settings = ScopeSettings.load()
        
        # Get explicit target state from POST body (prevents race conditions)
        target_enabled = None
        try:
            body = json.loads(request.body)
            target_enabled = body.get('target_enabled')
        except (json.JSONDecodeError, ValueError):
            pass
        
        # If no explicit state was sent, invert the current state
        if target_enabled is None:
            target_enabled = not settings.is_enabled
        
        # Safety Check: Prevent disabling if users are assigned to scopes
        if settings.is_enabled and not target_enabled:
            if User.objects.filter(profile__scope__isnull=False).exists():
                return JsonResponse({
                    'success': False, 
                    'error': 'لا يمكن تعطيل النطاقات لوجود مستخدمين معينين لنطاقات حالية. يرجى إزالة النطاقات من كافة المستخدمين أولاً.'
                }, status=200)
        
        settings.is_enabled = target_enabled
        settings.save()
        return JsonResponse({'success': True, 'is_enabled': settings.is_enabled})
    return JsonResponse({'success': False}, status=400)


@login_required
def toggle_auto_scopes(request):
    _require_superuser(request)
    if request.method == "POST":
        ScopeSettings = apps.get_model('dlux', 'ScopeSettings')
        settings = ScopeSettings.load()
        
        target_enabled = None
        try:
            body = json.loads(request.body)
            target_enabled = body.get('target_enabled')
        except (json.JSONDecodeError, ValueError):
            pass
        
        if target_enabled is None:
            target_enabled = not getattr(settings, 'auto_create_user_scope', False)
            
        settings.auto_create_user_scope = target_enabled
        settings.save()
        return JsonResponse({'success': True, 'auto_create_user_scope': settings.auto_create_user_scope})
    return JsonResponse({'success': False}, status=400)
