from django.apps import apps
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import FieldDoesNotExist
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache
import json
import re
from datetime import date, datetime
import logging
# Project imports
from .system.constants import (
    DEFAULT_MAX_PREFERENCES_BYTES,
    FORM_DENSITY_VALUES,
    MODAL_SIZE_VALUES,
    NAVBAR_MODE_VALUES,
    PREFERENCES_APP_NAMESPACE,
    PREFERENCES_APP_NAMESPACE_MAXLEN,
    SAFE_NAMESPACE_RE,
    SIDEBAR_DENSITY_VALUES,
    TABLE_DENSITY_VALUES,
    TABLE_PAGE_SIZE_VALUES,
)
from .options import AppSystemConfigError, write_app_system_config
from .utils import (
    get_effective_allowed_themes,
    get_system_config,
    get_user_scope,
    is_global_staff,
    is_scope_enabled,
    log_user_action,
    normalize_navbar_config,
    normalize_sidebar_behavior,
    user_has_model_permission,
)

logger = logging.getLogger('dlux')


def _max_preferences_bytes():
    """Resolved size ceiling for the whole Profile.preferences blob."""
    try:
        return max(int(getattr(settings, 'DLUX_MAX_PREFERENCES_BYTES', DEFAULT_MAX_PREFERENCES_BYTES)), 1024)
    except (TypeError, ValueError):
        return DEFAULT_MAX_PREFERENCES_BYTES


_SAFE_NAMESPACE = re.compile(SAFE_NAMESPACE_RE)


def _coerce_prefs_dict(value):
    """Return a plain dict for a stored preferences value (tolerating legacy str)."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError):
            return {}
    return {}


def _merge_app_namespace(current_app, incoming_app):
    """Shallow-merge an incoming ``app`` namespace dict into the stored one.

    Each top-level key under ``app`` is one app-owned namespace; its value is
    opaque to Dlux. Incoming namespaces overwrite matching ones and leave the
    rest untouched; an explicit ``None`` value clears that namespace. Returns
    the merged dict (possibly empty) or ``None`` when the input isn't usable.
    """
    if not isinstance(incoming_app, dict):
        return current_app if isinstance(current_app, dict) else None
    merged = dict(current_app) if isinstance(current_app, dict) else {}
    for ns_key, ns_value in incoming_app.items():
        ns_key = str(ns_key)[:PREFERENCES_APP_NAMESPACE_MAXLEN]
        if ns_value is None:
            merged.pop(ns_key, None)
        else:
            merged[ns_key] = ns_value
    return merged


def _prefs_within_cap(prefs):
    """True if ``prefs`` serializes to JSON within the configured byte ceiling."""
    try:
        return len(json.dumps(prefs, default=str).encode('utf-8')) <= _max_preferences_bytes()
    except (TypeError, ValueError):
        # Non-serializable payloads are rejected as if oversized.
        return False

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


@login_required
@never_cache
def notifications_list(request):
    from .notifications import get_notification_context

    try:
        limit = int(request.GET.get('limit') or 20)
    except (TypeError, ValueError):
        limit = 20
    limit = max(1, min(limit, 50))
    context = get_notification_context(request, limit=limit)
    return JsonResponse({
        'enabled': context.get('enabled', False),
        'items': context.get('items', []),
        'unread_count': context.get('unread_count', 0),
        'unread_level': context.get('unread_level', ''),
        'section_counts': context.get('section_counts', {}),
    })


@login_required
@require_POST
def notification_mark_read(request, pk):
    from .notifications import mark_notification_read, serialize_notification_state

    try:
        state = mark_notification_read(request.user, pk)
    except Exception:
        return JsonResponse({'success': False, 'error': 'Notification not found'}, status=404)
    return JsonResponse({'success': True, 'item': serialize_notification_state(state, request=request)})


@login_required
@require_POST
def notification_dismiss(request, pk):
    from .notifications import NotificationLockedError, dismiss_notification

    try:
        dismiss_notification(request.user, pk)
    except NotificationLockedError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=409)
    except Exception:
        return JsonResponse({'success': False, 'error': 'Notification not found'}, status=404)
    return JsonResponse({'success': True})


@login_required
@require_POST
def notifications_mark_all_read(request):
    from .notifications import mark_all_notifications_read

    count = mark_all_notifications_read(request.user)
    return JsonResponse({'success': True, 'updated': count, 'unread_count': 0})


@login_required
@require_POST
def notifications_clear_all(request):
    from .notifications import clear_all_notifications

    count = clear_all_notifications(request.user)
    return JsonResponse({'success': True, 'updated': count, 'unread_count': 0})


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
            Profile = apps.get_model('dlux', 'Profile')
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
            navbar_config = normalize_navbar_config(system_config.get('navbar', {}))
            
            language_preview_requested = bool(data.get('__language_preview'))

            for key, value in data.items():
                if key != 'csrfmiddlewaretoken':
                    if key == '__language_preview':
                        continue
                    if key == PREFERENCES_APP_NAMESPACE:
                        # App-owned namespace: opaque pass-through, merged at the
                        # namespace level so different namespaces don't clobber.
                        merged_app = _merge_app_namespace(prefs.get(PREFERENCES_APP_NAMESPACE), value)
                        if merged_app:
                            prefs[PREFERENCES_APP_NAMESPACE] = merged_app
                        else:
                            prefs.pop(PREFERENCES_APP_NAMESPACE, None)
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
                            request.session.pop('dlux_force_language_preview', None)
                            continue
                        if language_preview_requested and request.user.is_superuser:
                            request.session['lang'] = value
                            request.session['django_language'] = value
                            request.session['dlux_force_language_preview'] = True
                            continue
                        if not system_config.get('allow_user_language_override', True):
                            prefs.pop('language', None)
                            request.session.pop('lang', None)
                            request.session.pop('django_language', None)
                            request.session.pop('dlux_force_language_preview', None)
                            continue
                        request.session['lang'] = value
                        request.session['django_language'] = value
                        request.session.pop('dlux_force_language_preview', None)
                    if key == 'table_density':
                        if value not in TABLE_DENSITY_VALUES:
                            prefs.pop('table_density', None)
                            continue
                    if key == 'form_density':
                        if value not in FORM_DENSITY_VALUES:
                            prefs.pop('form_density', None)
                            continue
                    if key == 'modal_size':
                        if value not in MODAL_SIZE_VALUES:
                            prefs.pop('modal_size', None)
                            continue
                    if key == 'sidebar_density':
                        if not sidebar_config.get('allow_user_density', True):
                            prefs.pop('sidebar_density', None)
                            continue
                        if value not in SIDEBAR_DENSITY_VALUES:
                            prefs.pop('sidebar_density', None)
                            continue
                    if key == 'navbar_mode':
                        if (
                            not navbar_config.get('enabled', False)
                            or not navbar_config.get('allow_user_mode_override', True)
                            or value not in NAVBAR_MODE_VALUES
                        ):
                            prefs.pop('navbar_mode', None)
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
                    if key in ('autofill_from_related', 'sticky_forms'):
                        # Assisted-entry switches. Stored as strict bools; the
                        # two features are independent, so neither implies the
                        # other.
                        coerced = value
                        if isinstance(coerced, str):
                            coerced = coerced.strip().lower() in {'1', 'true', 'yes', 'on'}
                        value = bool(coerced)
                    if key == 'skip_unsaved_settings_prompt':
                        # Opt-out for the unsaved-changes prompt. Stored as a
                        # strict bool, and dropped entirely when off so the
                        # preferences blob does not carry dead keys.
                        coerced = value
                        if isinstance(coerced, str):
                            coerced = coerced.strip().lower() in {'1', 'true', 'yes', 'on'}
                        if not bool(coerced):
                            prefs.pop('skip_unsaved_settings_prompt', None)
                            continue
                        value = True
                    if key == 'sidebar_collapsed' and sidebar_config.get('collapse_mode') == 'locked_expanded':
                        prefs.pop('sidebar_collapsed', None)
                        request.session['sidebarCollapsed'] = False
                        continue
                    if key == 'user_home_url':
                        profile_config = system_config.get('profile_config') or {}
                        cleaned_home = str(value or '').strip()
                        if not profile_config.get('allow_user_home_url') or not cleaned_home:
                            prefs.pop('user_home_url', None)
                            continue
                        # Only accept a page the user may actually access (discovered + perm-filtered).
                        from dlux.discovery import build_user_home_url_options
                        if cleaned_home not in {o['value'] for o in build_user_home_url_options(request.user)}:
                            prefs.pop('user_home_url', None)
                            continue
                        value = cleaned_home
                    prefs[key] = value
                    
                    # Sync sidebar state to session for server-side consistency
                    if key == 'sidebar_collapsed':
                         val = value
                         if isinstance(val, str):
                             val = val.lower() == 'true'
                         request.session['sidebarCollapsed'] = val

            # 4. Enforce the overall size ceiling before persisting (the blob is
            # inlined into every page as window.USER_PREFS).
            if not _prefs_within_cap(prefs):
                return JsonResponse(
                    {'status': 'error', 'message': 'Preferences payload too large.'},
                    status=413,
                )

            # 5. Save
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
            Profile = apps.get_model('dlux', 'Profile')
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


@login_required
@require_POST
def reset_dialog_prompts(request):
    """Re-arm every registered dismissible dialog for the current user.

    Deliberately narrower than ``reset_preferences``: it clears only the
    "don't show again" state registered through ``dlux.dialogs``, leaving theme,
    density, language and the rest of the user's preferences alone.

    Routed under ``/sys/api/preferences/`` so the unconfigured-system middleware
    treats it like the other preference endpoints instead of bouncing it to setup.
    """
    from .dialogs import get_dismissible_dialogs, reset_dismissible_dialogs

    try:
        Profile = apps.get_model('dlux', 'Profile')
        profile, _created = Profile.all_objects.get_or_create(user=request.user)
        reset_count = reset_dismissible_dialogs(profile)
        log_user_action(request, "RESET", instance=request.user, model_name="dialog_prompts")
        return JsonResponse({
            'success': True,
            'reset': reset_count,
            'registered': len(get_dismissible_dialogs()),
        })
    except Exception:
        logger.exception("Failed to reset dialog prompts for user pk=%s", request.user.pk)
        return JsonResponse(
            {'success': False, 'error': 'Unable to reset dialog prompts.'}, status=500,
        )


# Preferences API — Targeted, concurrent-safe write to one app-owned namespace.
@login_required
@require_POST
def update_app_preference(request, namespace):
    """Set (or clear) a single app-owned preferences namespace.

    Writes only ``Profile.preferences['app'][<namespace>]`` — Dlux-owned keys and
    every other app namespace are left untouched, so two tabs writing *different*
    namespaces don't clobber each other. The request body is the namespace's new
    value (any JSON) and is stored opaquely; an empty/``null`` body clears it.
    Enforces the same overall size ceiling as the main preferences endpoint.
    """
    namespace = str(namespace or '').strip()
    if not namespace or len(namespace) > PREFERENCES_APP_NAMESPACE_MAXLEN:
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
        Profile = apps.get_model('dlux', 'Profile')
        profile, _created = Profile.all_objects.get_or_create(user=request.user)
        prefs = dict(_coerce_prefs_dict(profile.preferences))

        app_prefs = dict(_coerce_prefs_dict(prefs.get(PREFERENCES_APP_NAMESPACE)))
        if body is None:
            app_prefs.pop(namespace, None)
        else:
            app_prefs[namespace] = body

        if app_prefs:
            prefs[PREFERENCES_APP_NAMESPACE] = app_prefs
        else:
            prefs.pop(PREFERENCES_APP_NAMESPACE, None)

        if not _prefs_within_cap(prefs):
            return JsonResponse(
                {'status': 'error', 'message': 'Preferences payload too large.'},
                status=413,
            )

        profile.preferences = prefs
        profile.save(update_fields=['preferences'])
        return JsonResponse({
            'status': 'success',
            'namespace': namespace,
            'value': app_prefs.get(namespace),
        })
    except Exception:
        logger.exception("Failed to update app preference '%s' for user pk=%s", namespace, request.user.pk)
        return JsonResponse({'status': 'error', 'message': 'Unable to update preference.'}, status=400)


# System Config API — Superuser-only write to one app-owned system-config namespace.
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
