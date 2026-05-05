from django.apps import apps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import FieldDoesNotExist
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
import json
from datetime import date, datetime
import logging
# Project imports
from .constants import SIDEBAR_DENSITY_VALUES, TABLE_DENSITY_VALUES, TABLE_PAGE_SIZE_VALUES
from .utils import (
    get_effective_allowed_themes,
    get_system_config,
    get_user_scope,
    is_global_staff,
    is_scope_enabled,
    log_user_action,
    normalize_sidebar_behavior,
    user_has_model_permission,
)

logger = logging.getLogger('microsys')

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
    """Apply Microsys scope boundaries to generic API querysets."""
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
            system_config = get_system_config()
            allowed_themes = set(get_effective_allowed_themes(system_config))
            sidebar_config = normalize_sidebar_behavior(system_config.get('sidebar', {}))
            
            language_preview_requested = bool(data.get('__language_preview'))

            for key, value in data.items():
                if key != 'csrfmiddlewaretoken':
                    if key == '__language_preview':
                        continue
                    if key == 'theme':
                        if not system_config.get('allow_user_theme_override', True):
                            prefs.pop('theme', None)
                            continue
                        if value not in allowed_themes:
                            prefs.pop('theme', None)
                            continue
                    if key == 'language':
                        available_languages = system_config.get('languages', {}) or {}
                        if value not in available_languages:
                            prefs.pop('language', None)
                            request.session.pop('lang', None)
                            request.session.pop('django_language', None)
                            request.session.pop('ms_force_language_preview', None)
                            continue
                        if language_preview_requested and request.user.is_superuser:
                            request.session['lang'] = value
                            request.session['django_language'] = value
                            request.session['ms_force_language_preview'] = True
                            continue
                        if not system_config.get('allow_user_language_override', True):
                            prefs.pop('language', None)
                            request.session.pop('lang', None)
                            request.session.pop('django_language', None)
                            request.session.pop('ms_force_language_preview', None)
                            continue
                        request.session['lang'] = value
                        request.session['django_language'] = value
                        request.session.pop('ms_force_language_preview', None)
                    if key == 'table_density':
                        if value not in TABLE_DENSITY_VALUES:
                            prefs.pop('table_density', None)
                            continue
                    if key == 'sidebar_density':
                        if not sidebar_config.get('allow_user_density', True):
                            prefs.pop('sidebar_density', None)
                            continue
                        if value not in SIDEBAR_DENSITY_VALUES:
                            prefs.pop('sidebar_density', None)
                            continue
                    if key == 'table_page_size':
                        try:
                            coerced_value = int(value)
                        except (TypeError, ValueError):
                            prefs.pop('table_page_size', None)
                            continue
                        if coerced_value not in TABLE_PAGE_SIZE_VALUES:
                            prefs.pop('table_page_size', None)
                            continue
                        value = coerced_value
                    if key == 'sidebar_collapsed' and sidebar_config.get('collapse_mode') == 'locked_expanded':
                        prefs.pop('sidebar_collapsed', None)
                        request.session['sidebarCollapsed'] = False
                        continue
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
            
            logger.debug("Preferences updated for user pk=%s", request.user.pk)
            return JsonResponse({'status': 'success', 'preferences': profile.preferences})
        except Exception:
            logger.exception("Failed to update preferences for user pk=%s", request.user.pk)
            return JsonResponse({'status': 'error', 'message': 'Unable to update preferences.'}, status=400)
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
        except Exception:
            logger.exception("Failed to reset preferences for user pk=%s", request.user.pk)
            return JsonResponse({'success': False, 'error': 'Unable to reset preferences.'}, status=500)
    
    return JsonResponse({'success': False}, status=400)
