"""Generic model reader — the security boundary of this package.

Any authenticated user can call these with an arbitrary ``app_label`` /
``model_name``, so authorization is enforced here rather than by the URL: the
model permission is checked (:func:`_can_view_model`), the queryset is narrowed
to the caller's scope (:func:`_visible_queryset`), and sensitive fields are
stripped from the serialized output (:func:`_is_sensitive_api_field`).

Read those three together before changing any one of them.
"""
from datetime import date, datetime

from django.apps import apps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import FieldDoesNotExist
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from ..utils import (
    get_user_scope,
    is_global_staff,
    is_scope_enabled,
    user_has_model_permission,
)

def _can_view_model(user, model):
    """Check if user has permission to view the model."""
    return user_has_model_permission(user, model, "view")

def _has_scope_field(model):
    try:
        model._meta.get_field("scope")
    except FieldDoesNotExist:
        return False
    return True

def _scope_filter_queryset(user, queryset):
    """Apply Dlux scope boundaries to generic API querysets."""
    if not is_scope_enabled():
        return queryset
    if getattr(user, "is_superuser", False) or is_global_staff(user):
        return queryset
    if not _has_scope_field(queryset.model):
        return queryset
    user_scope = get_user_scope(user)
    if user_scope is None:
        return queryset.none()
    return queryset.filter(scope=user_scope)

def _visible_queryset(user, model):
    return _scope_filter_queryset(user, model._default_manager.all())

def _is_sensitive_api_field(field_name):
    lowered = (field_name or "").lower()
    sensitive_markers = (
        "password",
        "secret",
        "token",
        "otp",
        "backup_code",
        "session_key",
        "api_key",
        "private_key",
        "email_config",
    )
    return lowered in {"id", "pk"} or any(marker in lowered for marker in sensitive_markers)

def _serialize_instance(instance, depth=0):
    """Serialize model instance to a dictionary for autofill."""
    if depth > 1:
        return {}
    
    data = {}

    for field in instance._meta.get_fields():
        if field.auto_created and not field.concrete:
             continue

        if not field.concrete:
            continue

        try:
            field_name = field.name
            
            # Skip sensitive or system fields
            if _is_sensitive_api_field(field_name) or field.auto_created:
                continue
                
            value = getattr(instance, field_name)
            
            # Handle different field types
            if value is None:
                data[field_name] = ""
            
            elif field.is_relation:
                # For ForeignKey, return the PK
                if field.many_to_one:
                     # If value is None handled above
                     data[field_name] = value.pk
                elif field.one_to_one:
                     # Forward OneToOne (e.g. Employee.user -> User)
                     if value:
                         data[field_name] = value.pk
            
            elif isinstance(value, (datetime, date)):
                 data[field_name] = value.isoformat()
                 
            elif field.get_internal_type() in ['FileField', 'ImageField']:
                # Skip files for autofill
                continue
                
            else:
                data[field_name] = value
        except Exception:
            continue
            
    # Include metadata
    data['_pk'] = instance.pk if instance.pk else ''
    return data

@login_required
def get_last_entry(request, app_label, model_name):
    try:
        model = apps.get_model(app_label, model_name)
    except LookupError:
        return JsonResponse({'error': 'Model not found'}, status=404)

    if not _can_view_model(request.user, model):
        return JsonResponse({'error': 'Permission denied'}, status=403)
        
    qs = _visible_queryset(request.user, model).order_by('-pk')
    before_id = request.GET.get('before_id')
    if before_id:
        try:
            qs = qs.filter(pk__lt=int(before_id))
        except ValueError:
            pass
            
    instance = qs.first()
    if not instance:
        return JsonResponse({'error': 'No record found'}, status=404)
        
    return JsonResponse(_serialize_instance(instance))

@login_required
def get_model_details(request, app_label, model_name, pk):
    """
    Fetch a specific model instance by PK.
    Pass pk='empty_schema' to get an empty structure (for clearing forms).
    """
    try:
        model = apps.get_model(app_label, model_name)
    except LookupError:
        return JsonResponse({'error': 'Model not found'}, status=404)

    if not _can_view_model(request.user, model):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    if pk == 'empty_schema':
        # Create empty instance
        instance = model()
        # Create OneToOne relations too? (To get their fields)
        # This is hard because we don't know which ones exist or matter.
        # But `_serialize_instance` iterates fields.
        # getattr(instance, reverse_one_to_one) will likely be None or Error.
        # So we might miss clearing profile fields.
        # Use a workaround: Iterate fields and set empty string if not found.
        data = _serialize_instance(instance)
        # Manually ensure we return None/Empty for all fields?
        # _serialize_instance handles None -> "".
        return JsonResponse(data)

    instance = get_object_or_404(_visible_queryset(request.user, model), pk=pk)
    return JsonResponse(_serialize_instance(instance))
