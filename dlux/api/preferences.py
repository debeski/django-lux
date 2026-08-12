"""Per-user preference endpoints.

These write ``Profile.preferences`` for the calling user only, under a total
size ceiling (:func:`_max_preferences_bytes`). App-owned namespaces are merged
rather than replaced, so two tabs writing different namespaces cannot clobber
each other.
"""
import json

from django.apps import apps
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from ._shared import logger
from ..system.constants import (
    DEFAULT_MAX_PREFERENCES_BYTES,
    FORM_DENSITY_VALUES,
    MODAL_SIZE_VALUES,
    NAVBAR_MODE_VALUES,
    PREFERENCES_APP_NAMESPACE,
    PREFERENCES_APP_NAMESPACE_MAXLEN,
    SIDEBAR_DENSITY_VALUES,
    TABLE_DENSITY_VALUES,
    TABLE_PAGE_SIZE_VALUES,
)
from ..utils import (
    get_effective_allowed_themes,
    get_system_config,
    log_user_action,
    normalize_navbar_config,
    normalize_sidebar_behavior,
)

def _max_preferences_bytes():
    """Resolved size ceiling for the whole Profile.preferences blob."""
    try:
        return max(int(getattr(settings, 'DLUX_MAX_PREFERENCES_BYTES', DEFAULT_MAX_PREFERENCES_BYTES)), 1024)
    except (TypeError, ValueError):
        return DEFAULT_MAX_PREFERENCES_BYTES

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
    from ..dialogs import get_dismissible_dialogs, reset_dismissible_dialogs

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
