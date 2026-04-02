# Fundemental imports
import json

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.utils.module_loading import import_string
from django_tables2 import RequestConfig

# Project imports
from ..utils import is_scope_enabled, is_superuser

User = get_user_model()


# Scope Management — AJAX modal: returns scope table (superuser only)
@login_required
@user_passes_test(is_superuser)
def manage_scopes(request):
    """
    Returns the initial modal content with the table.
    """
    if not is_scope_enabled():
         return JsonResponse({'error': 'Scope management is disabled.'}, status=403)

    Scope = apps.get_model('microsys', 'Scope')
    ScopeTable = import_string('microsys.tables.ScopeTable')
    table = ScopeTable(Scope.objects.all())
    RequestConfig(request, paginate={'per_page': 5}).configure(table)
    
    context = {'table': table}
    html = render_to_string('microsys/scopes/scope_manager.html', context, request=request)
    return JsonResponse({'html': html})

# Scope Management — AJAX: returns add/edit scope form partial
@login_required
@user_passes_test(is_superuser)
def get_scope_form(request, pk=None):
    """
    Returns the Add/Edit form partial.
    """
    ScopeForm = import_string('microsys.forms.ScopeForm')
    Scope = apps.get_model('microsys', 'Scope')

    if pk:
        scope = get_object_or_404(Scope, pk=pk)
        form = ScopeForm(instance=scope)
    else:
        form = ScopeForm()
        
    html = render_to_string('microsys/scopes/scope_form.html', {'form': form, 'scope_id': pk}, request=request)
    return JsonResponse({'html': html})

@login_required
@user_passes_test(is_superuser)
def save_scope(request, pk=None):
    """
    Handles form submission. Returns updated table on success, or form with errors on failure.
    """
    ScopeForm = import_string('microsys.forms.ScopeForm')
    Scope = apps.get_model('microsys', 'Scope')
    ScopeTable = import_string('microsys.tables.ScopeTable')

    if request.method == "POST":
        if pk:
            scope = get_object_or_404(Scope, pk=pk)
            form = ScopeForm(request.POST, instance=scope)
        else:
            form = ScopeForm(request.POST)

        if form.is_valid():
            form.save()
            # Return updated table
            table = ScopeTable(Scope.objects.all())
            RequestConfig(request, paginate={'per_page': 5}).configure(table)
            html = render_to_string('microsys/scopes/scope_manager.html', {'table': table}, request=request)
            return JsonResponse({'success': True, 'html': html})
        else:
            # Return form with errors
            html = render_to_string('microsys/scopes/scope_form.html', {'form': form, 'scope_id': pk}, request=request)
            return JsonResponse({'success': False, 'html': html})
    
    return JsonResponse({'success': False, 'error': 'Invalid method'})

# Scope Management — Scope deletion endpoint (currently disabled for safety)
@login_required
@user_passes_test(is_superuser)
def delete_scope(request, pk):
    return JsonResponse({'success': False, 'error': 'تم تعطيل حذف النطاقات لأسباب أمنية.'})

# Scope Management — Toggles the scope system on/off with safety checks
@login_required
@user_passes_test(is_superuser)
def toggle_scopes(request):
    if request.method == "POST":
        ScopeSettings = apps.get_model('microsys', 'ScopeSettings')
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

