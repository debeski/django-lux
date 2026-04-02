from django.apps import apps
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.core.exceptions import PermissionDenied
import json
from datetime import date, datetime
import logging
# Project imports
from .utils import log_user_action

def _can_view_model(user, app_label, model_name):
    """Check if user has permission to view the model."""
    perm = f"{app_label}.view_{model_name}"
    return user.has_perm(perm)

def _serialize_instance(instance, depth=0):
    """Serialize model instance to a dictionary for autofill."""
    if depth > 1: return {} # Prevent infinite recursion
    
    data = {}
    
    # Iterate over model fields
    # Iterate over model fields
    for field in instance._meta.get_fields():
        if field.auto_created and not field.concrete:
             # Handle Reverse OneToOne (e.g. user.profile)
             if field.one_to_one and field.related_model:
                 try:
                     # Check if instance is unsaved (empty_schema mode)
                     if instance.pk is None:
                         # Instantiate empty related model to discover fields
                         related_obj = field.related_model()
                     else:
                         # Access related object via accessor
                         # Note: field.name on Relation usually works, but get_accessor_name is safer
                         # We stick to what worked for pk=1 (field.name or getattr logic)
                         accessor_name = field.get_accessor_name() if hasattr(field, 'get_accessor_name') else field.name
                         related_obj = getattr(instance, accessor_name, None)

                     if related_obj:
                         # Merge related data (e.g. profile.phone)
                         related_data = _serialize_instance(related_obj, depth=depth+1)
                         for k, v in related_data.items():
                             if k not in data and k != '_pk':
                                 data[k] = v
                 except Exception as e:
                     # print(f"Autofill serialization error for {field}: {e}")
                     pass
             continue

        if not field.concrete: continue

        try:
            field_name = field.name
            
            # Skip sensitive or system fields
            if field_name in ['password', 'id', 'pk'] or field.auto_created:
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
        except Exception as e:
            # print(f"Autofill main serialization error for {field.name}: {e}")
            continue
            
    # Include metadata
    data['_pk'] = instance.pk if instance.pk else ''
    return data

@login_required
def get_last_entry(request, app_label, model_name):
    # ... (same as before) ...
    if not _can_view_model(request.user, app_label, model_name):
        return JsonResponse({'error': 'Permission denied'}, status=403)
        
    try:
        model = apps.get_model(app_label, model_name)
    except LookupError:
        return JsonResponse({'error': 'Model not found'}, status=404)
        
    qs = model.objects.all().order_by('-pk')
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
    if not _can_view_model(request.user, app_label, model_name):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    try:
        model = apps.get_model(app_label, model_name)
    except LookupError:
        return JsonResponse({'error': 'Model not found'}, status=404)
    
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

    instance = get_object_or_404(model, pk=pk)
    return JsonResponse(_serialize_instance(instance))

# Preferences API — Updates user preferences (theme, sidebar, language, etc.)
@login_required
def update_preferences(request):
    if request.method == "POST":
        try:
             # Support both JSON body and Form data
            if request.content_type == 'application/json':
                data = json.loads(request.body)
            else:
                data = request.POST

            # 1. Get or create profile
            Profile = apps.get_model('microsys', 'Profile')
            profile, created = Profile.all_objects.get_or_create(user=request.user)

            # 2. Get existing prefs safely
            current_prefs = profile.preferences
            if not isinstance(current_prefs, dict):
                if isinstance(current_prefs, str) and current_prefs.strip():
                    try:
                        current_prefs = json.loads(current_prefs)
                    except:
                        current_prefs = {}
                else:
                    current_prefs = {}
            
            # Start with a clean dict for merging
            prefs = dict(current_prefs)
            
            # 3. Update with new data
            logger = logging.getLogger('microsys')
            
            for key, value in data.items():
                if key != 'csrfmiddlewaretoken':
                    prefs[key] = value
                    
                    # Sync sidebar state to session for server-side consistency
                    if key == 'sidebar_collapsed':
                         val = value
                         if isinstance(val, str):
                             val = val.lower() == 'true'
                         request.session['sidebarCollapsed'] = val

            # 4. Save
            profile.preferences = prefs
            profile.save(update_fields=['preferences'])
            request.session.modified = True
            
            logger.debug(f"Preferences updated for {request.user.username}: {prefs}")
            return JsonResponse({'status': 'success', 'preferences': profile.preferences})
        except Exception as e:
            error_msg = f"Error updating preferences for {request.user.username}: {str(e)}"
            logging.getLogger('microsys').error(error_msg)
            return JsonResponse({'status': 'error', 'message': error_msg}, status=400)
    return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)

# Preferences API — Resets all user preferences to defaults
@login_required
def reset_preferences(request):
    """
    Reset all user preferences to default.
    Clears Profile.preferences and session keys.
    """
    if request.method == "POST":
        try:
            # 1. Clear Profile preferences
            Profile = apps.get_model('microsys', 'Profile')
            profile, created = Profile.all_objects.get_or_create(user=request.user)
            profile.preferences = {}
            profile.save()
            
            # 2. Clear Session keys related to preferences
            session_keys_to_clear = ['django_language', 'sidebarCollapsed', 'enable_prefill']
            for key in session_keys_to_clear:
                if key in request.session:
                    del request.session[key]
            
            # Log action
            log_user_action(request, "RESET", instance=request.user, model_name="preferences")
            
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    
    return JsonResponse({'success': False}, status=400)
