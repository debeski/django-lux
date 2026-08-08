# Fundemental imports
import logging

from django.apps import apps
from django.contrib.auth import logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.contrib.sessions.models import Session
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

# Project imports
from django.utils.module_loading import import_string
from ..guards import require_current_password
from ..notifications import notify
from ..trust import (
    current_session_trusted_device,
    enforce_single_active_session,
    issue_trusted_device,
    revoke_linked_session_trust,
    sync_session_device_metadata,
    terminate_other_user_sessions,
    trusted_device_for_session,
)
from ..session_history import flag_sessions_revoked, hash_session_key, mark_presence_sessions_ended
from ..reports import (
    exclude_log_noise,
    filter_report_eligible_activity,
    is_report_eligible_activity_model_name,
    log_report_key,
)
from ..utils import (
    get_system_config,
    get_user_scope,
    get_user_management_tier_state_for_user,
    is_scope_enabled,
    log_audit_event,
    log_user_action,
    normalize_activity_log_model_key,
    resolve_user_theme_preference,
)
from ..translations import get_strings
from .twofa import get_2fa_config

logger = logging.getLogger('dlux')

_PROFILE_SYSTEM_ACTIONS = {"login", "logout"}
_PROFILE_RECENT_ACTIVITY_LIMIT = 5
_PROFILE_SYSTEM_INTERACTION_LIMIT = 5


def _is_profile_system_interaction(log_entry):
    action_key = normalize_activity_log_model_key(getattr(log_entry, "action", ""))
    if action_key in _PROFILE_SYSTEM_ACTIONS:
        return True
    return not is_report_eligible_activity_model_name(log_report_key(log_entry))


def _parse_session_datetime(value):
    try:
        parsed = timezone.datetime.fromisoformat(str(value or ''))
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
        return parsed
    except (TypeError, ValueError):
        return None


def _device_label(user_agent):
    user_agent = str(user_agent or '').strip()
    lowered = user_agent.lower()
    if not user_agent:
        return 'Unknown device'

    if 'edg/' in lowered or 'edge/' in lowered:
        browser = 'Edge'
    elif 'firefox/' in lowered:
        browser = 'Firefox'
    elif 'chrome/' in lowered or 'chromium/' in lowered:
        browser = 'Chrome'
    elif 'safari/' in lowered:
        browser = 'Safari'
    else:
        browser = 'Browser'

    if 'android' in lowered:
        platform = 'Android'
    elif 'iphone' in lowered or 'ipad' in lowered:
        platform = 'iOS'
    elif 'windows' in lowered:
        platform = 'Windows'
    elif 'mac os' in lowered or 'macintosh' in lowered:
        platform = 'macOS'
    elif 'linux' in lowered:
        platform = 'Linux'
    else:
        platform = 'device'

    return f'{browser} on {platform}'


def _session_device_metadata_from_request(request):
    return sync_session_device_metadata(request)


def _profile_sessions_for_user(user, current_session_key=None, current_session_data=None, current_expire_date=None):
    sessions = []
    now = timezone.now()
    user_id = str(user.pk)
    has_current_session = False
    trusted_devices = apps.get_model('dlux', 'TrustedDevice').objects.filter(
        user=user,
        revoked_at__isnull=True,
        trusted_until__gt=now,
    )
    trusted_by_id = {device.pk: device for device in trusted_devices}
    trusted_by_session_key = {device.session_key: device for device in trusted_devices if device.session_key}
    PresenceSession = apps.get_model('dlux', 'UserPresenceSession')
    presence_by_session_hash = {
        item.session_key_hash: item
        for item in PresenceSession.objects.filter(user=user)
    }

    for session in Session.objects.filter(expire_date__gt=now).order_by('-expire_date'):
        try:
            data = session.get_decoded()
        except Exception:
            continue

        if str(data.get('_auth_user_id') or '') != user_id:
            continue

        if current_session_key and session.session_key == current_session_key and isinstance(current_session_data, dict):
            metadata = current_session_data.get('dlux_device') if isinstance(current_session_data.get('dlux_device'), dict) else {}
        else:
            metadata = data.get('dlux_device') if isinstance(data.get('dlux_device'), dict) else {}
        presence_session = presence_by_session_hash.get(hash_session_key(session.session_key))
        observed_user_agents = presence_session.user_agents if presence_session is not None and isinstance(presence_session.user_agents, list) else []
        observed_ips = presence_session.ip_addresses if presence_session is not None and isinstance(presence_session.ip_addresses, list) else []
        user_agent = metadata.get('user_agent') or (observed_user_agents[0] if observed_user_agents else '')
        last_seen = _parse_session_datetime(metadata.get('last_seen'))
        first_seen = _parse_session_datetime(metadata.get('first_seen'))
        if presence_session is not None:
            last_seen = last_seen or presence_session.last_seen_at
            first_seen = first_seen or presence_session.first_seen_at
        trusted_device = None
        trusted_device_id = metadata.get('trusted_device_id')
        if trusted_device_id is not None:
            try:
                trusted_device = trusted_by_id.get(int(trusted_device_id))
            except (TypeError, ValueError):
                trusted_device = None
        if trusted_device is None:
            trusted_device = trusted_by_session_key.get(session.session_key)

        is_current = bool(current_session_key and session.session_key == current_session_key)
        has_current_session = has_current_session or is_current

        sessions.append({
            'session_key': session.session_key,
            'is_current': is_current,
            'device_label': _device_label(user_agent),
            'user_agent': user_agent,
            'ip_address': metadata.get('ip_address') or (observed_ips[0] if observed_ips else ''),
            'first_seen': first_seen,
            'last_seen': last_seen,
            'expire_date': session.expire_date,
            'is_trusted': trusted_device is not None,
            'trusted_until': trusted_device.trusted_until if trusted_device is not None else None,
            'estimated_seconds': presence_session.estimated_seconds if presence_session is not None else 0,
            'request_count': presence_session.request_count if presence_session is not None else 0,
        })

    if current_session_key and not has_current_session:
        metadata = current_session_data.get('dlux_device') if isinstance(current_session_data, dict) and isinstance(current_session_data.get('dlux_device'), dict) else {}
        user_agent = metadata.get('user_agent') or ''
        trusted_device = None
        trusted_device_id = metadata.get('trusted_device_id')
        if trusted_device_id is not None:
            try:
                trusted_device = trusted_by_id.get(int(trusted_device_id))
            except (TypeError, ValueError):
                trusted_device = None
        if trusted_device is None:
            trusted_device = trusted_by_session_key.get(current_session_key)
        presence_session = presence_by_session_hash.get(hash_session_key(current_session_key))
        observed_user_agents = presence_session.user_agents if presence_session is not None and isinstance(presence_session.user_agents, list) else []
        observed_ips = presence_session.ip_addresses if presence_session is not None and isinstance(presence_session.ip_addresses, list) else []
        user_agent = user_agent or (observed_user_agents[0] if observed_user_agents else '')
        sessions.append({
            'session_key': current_session_key,
            'is_current': True,
            'device_label': _device_label(user_agent),
            'user_agent': user_agent,
            'ip_address': metadata.get('ip_address') or (observed_ips[0] if observed_ips else ''),
            'first_seen': _parse_session_datetime(metadata.get('first_seen')) or (presence_session.first_seen_at if presence_session is not None else None),
            'last_seen': _parse_session_datetime(metadata.get('last_seen')) or (presence_session.last_seen_at if presence_session is not None else None) or now,
            'expire_date': current_expire_date or now,
            'is_trusted': trusted_device is not None,
            'trusted_until': trusted_device.trusted_until if trusted_device is not None else None,
            'estimated_seconds': presence_session.estimated_seconds if presence_session is not None else 0,
            'request_count': presence_session.request_count if presence_session is not None else 0,
        })

    sessions = sorted(sessions, key=lambda item: (not item['is_current'], -(item['last_seen'] or item['expire_date']).timestamp()))
    current_is_trusted = any(item['is_current'] and item['is_trusted'] for item in sessions)
    for item in sessions:
        item['is_revoke_protected'] = bool(item['is_trusted'] and not item['is_current'] and not current_is_trusted)
        item['can_revoke'] = bool(not item['is_current'] and not item['is_revoke_protected'])
    return sessions


# Profile View — Displays user profile with stats, activity timeline, and password change
@login_required
def user_profile(request):
    CustomPasswordChangeForm = import_string('dlux.forms.CustomPasswordChangeForm')
    user = request.user
    
    # Use dynamic form
    password_form = CustomPasswordChangeForm(user)
    
    if request.method == 'POST':
        password_form = CustomPasswordChangeForm(user, request.POST)
        if password_form.is_valid():
            sign_out_other_sessions = bool(
                password_form.cleaned_data.get('sign_out_other_sessions')
                and not get_system_config().get('prevent_multiple_active_sessions', False)
            )
            password_form.save()
            profile = getattr(user, 'profile', None)
            preferences = getattr(profile, 'preferences', {}) if profile is not None else {}
            if isinstance(preferences, dict) and preferences.get('force_password_change'):
                updated_preferences = dict(preferences)
                updated_preferences.pop('force_password_change', None)
                profile.preferences = updated_preferences
                profile.save(update_fields=['preferences'])
            log_audit_event(request, 'password_change', "PASSWORD_CHANGE", instance=user, model_name="password")
            sessions_ended = 0
            if sign_out_other_sessions:
                sessions_ended = terminate_other_user_sessions(
                    user,
                    keep_session_key=request.session.session_key,
                    reason='signed_out_remotely',
                )
            update_session_auth_hash(request, password_form.user)
            s = get_strings()
            message_key = 'msg_password_changed_sessions_ended' if sessions_ended else 'msg_password_changed'
            default_message = (
                'Password changed and all other signed-in devices were signed out.'
                if sessions_ended else
                'Password changed successfully!'
            )
            notify.success(
                s.get(message_key, default_message),
                request=request,
                action='password_changed',
                category='security',
                metadata={'message_key': message_key, 'sessions_ended': sessions_ended},
            )
            return redirect('user_profile')
        else:
            logger.warning("Password change validation failed for user pk=%s", user.pk)

    # --- Profile Stats & Activity ---
    UserActivityLog = apps.get_model('dlux', 'ActivityLog')
    # Drop operational tracking noise (presence/device churn) up front so it never
    # surfaces in either Recent Activity or System Interactions.
    user_activity_qs = exclude_log_noise(UserActivityLog.objects.filter(created_by=user))
    project_activity_qs = filter_report_eligible_activity(user_activity_qs)
    for system_action in _PROFILE_SYSTEM_ACTIONS:
        project_activity_qs = project_activity_qs.exclude(action__iexact=system_action)
    
    # 1. Stats
    total_actions = project_activity_qs.count()
    docs_created = project_activity_qs.filter(action='CREATE').count()
    total_edits = project_activity_qs.filter(action='UPDATE').count()
    total_downloads = project_activity_qs.filter(action__in=['DOWNLOAD', 'EXPORT']).count()
    
    # 2. Activity Feeds
    # Project/section activity stays in Recent Activity; Dlux operational logs
    # stay in System Interactions.
    recent_activity = []
    system_interactions = []
    all_user_logs = user_activity_qs.order_by('-created_at')[:200]

    for log in all_user_logs:
        if _is_profile_system_interaction(log):
            if len(system_interactions) < _PROFILE_SYSTEM_INTERACTION_LIMIT:
                system_interactions.append(log)
        else:
            if len(recent_activity) < _PROFILE_RECENT_ACTIVITY_LIMIT:
                recent_activity.append(log)
        if (
            len(system_interactions) >= _PROFILE_SYSTEM_INTERACTION_LIMIT
            and len(recent_activity) >= _PROFILE_RECENT_ACTIVITY_LIMIT
        ):
            break

    # 3. Completeness & Health
    completeness = 0
    if user.first_name and user.last_name:
        completeness += 25
    if user.email:
        completeness += 25
        
    # Check profile fields safely
    user_phone = None
    user_pic = None
    if hasattr(user, 'profile'):
        user_phone = user.profile.phone
        user_pic = user.profile.profile_picture
        if user.profile.is_2fa_enabled: # Count 2FA as one item (replacing Pic or adding as bonus?)
             # Let's say we have 4 criteria: Name, Email, Phone, 2FA (Pic is optional/bonus or we restart scale)
             # User requested "only one [2fa method] should count".
             pass 

    # Re-evaluating completeness based on user feedback to include 2FA appropriately
    # Let's do 5 items x 20%: Name, Email, Phone, Picture, 2FA
    completeness = 0
    if user.first_name and user.last_name: completeness += 20
    if user.email: completeness += 20
    if hasattr(user, 'profile'):
        if user.profile.phone: completeness += 20
        if user.profile.profile_picture: completeness += 20
        if user.profile.is_2fa_enabled: completeness += 20
        
    # 4. Health
    account_health = 'good' if user.is_active and user.profile.is_2fa_enabled else 'attention'

    # 5. Missing Definitions
    profile = getattr(user, 'profile', None)
    joined_date = user.date_joined
    last_login_date = user.last_login

    stats = {
        'total_actions': total_actions,
        'docs_created': docs_created,
        'total_edits': total_edits,
        'total_downloads': total_downloads,
        'completeness': completeness, # Passed to template even if not used in cards, used in progress bar
        'health': account_health,     # Used in Health section
    }

    _session_device_metadata_from_request(request)
    profile_preferences = getattr(profile, 'preferences', {}) if profile is not None else {}

    profile_config = get_system_config().get('profile_config') or {}

    context = {
        'profile_config': profile_config,
        'profile_show_completion': profile_config.get('show_completion_widget', True),
        'profile_show_devices': profile_config.get('show_session_device_cards', True),
        'profile_show_activity': profile_config.get('show_activity_feed', True),
        'profile_security_nudges': profile_config.get('security_nudges', 'subtle'),
        'user': request.user, # Ensure user is passed if template uses it directly
        'profile': profile,
        'password_form': password_form,
        'force_password_change_required': bool(
            isinstance(profile_preferences, dict)
            and profile_preferences.get('force_password_change')
        ),
        'stats': stats,
        'recent_activity': recent_activity,
        'system_interactions': system_interactions,
        'total_actions': total_actions, # If used
        'joined_date': joined_date,     # If used
        'last_login_date': last_login_date, # If used
        'role': 'Admin' if request.user.is_staff else 'User',
        'current_user_management_tier': get_user_management_tier_state_for_user(request.user),
        'config_2fa': get_2fa_config(), # Inject 2FA availability
        'active_sessions': _profile_sessions_for_user(
            request.user,
            request.session.session_key,
            dict(request.session.items()),
            request.session.get_expiry_date(),
        ),
    }

    return render(request, 'dlux/users/profile.html', context)


@login_required
@require_POST
def revoke_profile_session(request, session_key):
    if failure_response := require_current_password(request):
        return failure_response

    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
    target_session = get_object_or_404(Session, session_key=session_key)
    try:
        decoded = target_session.get_decoded()
    except Exception:
        decoded = {}

    if str(decoded.get('_auth_user_id') or '') != str(request.user.pk):
        message = get_strings().get('session_revoke_denied', 'That session does not belong to your account.')
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': message}, status=403)
        notify.error(
            message,
            request=request,
            action='session_revoke_denied',
            category='security',
            metadata={'message_key': 'session_revoke_denied'},
        )
        return redirect('user_profile')

    is_current_session = session_key == request.session.session_key
    metadata = decoded.get('dlux_device') if isinstance(decoded.get('dlux_device'), dict) else {}
    trusted_device_id = metadata.get('trusted_device_id')
    target_trusted_device = trusted_device_for_session(request.user, session_key, decoded)
    if target_trusted_device is not None and current_session_trusted_device(request) is None:
        message = get_strings().get('session_revoke_trusted_denied')
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': message}, status=403)
        notify.error(
            message,
            request=request,
            action='session_revoke_trusted_denied',
            category='security',
            metadata={'message_key': 'session_revoke_trusted_denied'},
        )
        return redirect('user_profile')

    target_session.delete()
    mark_presence_sessions_ended([session_key], revoked=True)
    if not is_current_session:
        # The other browser will get a "signed out remotely" interstitial next visit.
        flag_sessions_revoked([session_key], reason='signed_out_remotely')
    trusted_device_ids = []
    if trusted_device_id is not None:
        try:
            trusted_device_ids.append(int(trusted_device_id))
        except (TypeError, ValueError):
            pass
    revoke_linked_session_trust(request.user, [session_key], trusted_device_ids=trusted_device_ids)
    log_audit_event(request, 'session_revoke', "SESSION_REVOKE", instance=request.user, model_name="session", number=session_key[:8])

    success_message = get_strings().get('session_revoked_success', 'Session signed out.')
    if is_ajax:
        redirect_name = 'login' if is_current_session else 'user_profile'
        if is_current_session:
            logout(request)
        return JsonResponse({
            'status': 'success',
            'message': success_message,
            'redirect_url': reverse(redirect_name),
        })

    notify.success(
        success_message,
        request=request,
        action='session_revoked',
        category='security',
        metadata={'message_key': 'session_revoked_success'},
    )
    if is_current_session:
        logout(request)
        return redirect('login')
    return redirect('user_profile')


@login_required
@require_POST
def trust_current_device(request):
    if failure_response := require_current_password(request):
        return failure_response

    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
    trusted_device = current_session_trusted_device(request)
    success_message = get_strings().get('trusted_device_added_success')

    if is_ajax:
        response = JsonResponse({
            'status': 'success',
            'message': success_message,
            'redirect_url': reverse('user_profile'),
        })
    else:
        notify.success(
            success_message,
            request=request,
            action='trusted_device_added',
            category='security',
            metadata={'message_key': 'trusted_device_added_success'},
        )
        response = redirect('user_profile')

    if trusted_device is None:
        trusted_device = issue_trusted_device(request, response, request.user)
        log_audit_event(request, 'trusted_device_change', "TRUSTED_DEVICE", instance=request.user, model_name="trusted device")
    else:
        sync_session_device_metadata(request, trusted_device=trusted_device)
        enforce_single_active_session(request, request.user)

    return response


@login_required
def initial_user_setup(request):
    """First-login *Initial User Setup* modal (dlux dynamic modal).

    Lets the user pick theme / language / fonts (and an optional home override) up front —
    writing to ``Profile.preferences`` — instead of digging into Options later, then marks the
    profile configured. GET returns the modal fragment; POST saves + returns ``{success: True}``
    so the dynamic-modal JS closes and refreshes. A ``skip`` field just marks it configured.
    Which fields appear is governed by the admin's ``profile_config.onboarding_options`` and the
    matching ``allow_user_*_override`` flags.
    """
    from ..utils import get_system_config, get_effective_allowed_themes
    from ..themes import get_theme_options
    from ..fonts import get_available_fonts
    from ..discovery import build_user_home_url_options

    Profile = apps.get_model('dlux', 'Profile')
    profile, _ = Profile.all_objects.get_or_create(user=request.user)
    config = get_system_config()
    profile_config = config.get('profile_config') or {}
    onboarding_options = profile_config.get('onboarding_options') or {}
    s = get_strings()

    allow_theme = bool(onboarding_options.get('theme') and config.get('allow_user_theme_override', True))
    allow_language = bool(onboarding_options.get('language') and config.get('allow_user_language_override', True))
    allow_fonts = bool(onboarding_options.get('fonts') and config.get('allow_user_font_override', True))
    allow_home = bool(profile_config.get('allow_user_home_url'))

    if request.method == 'POST':
        if not request.POST.get('skip'):
            prefs = dict(profile.preferences if isinstance(profile.preferences, dict) else {})
            if allow_theme:
                theme = request.POST.get('theme')
                if theme in set(get_effective_allowed_themes(config)):
                    prefs['theme'] = theme
            if allow_language:
                lang = request.POST.get('language')
                if lang in (config.get('languages') or {}):
                    prefs['language'] = lang
            if allow_fonts:
                font = request.POST.get('font')
                allowed_font_slugs = set(config.get('allowed_fonts') or [f['slug'] for f in get_available_fonts()])
                if font in allowed_font_slugs:
                    prefs['font'] = font
            if allow_home:
                home = (request.POST.get('user_home_url') or '').strip()
                valid_home = {o['value'] for o in build_user_home_url_options(request.user)}
                if home and home in valid_home:
                    prefs['user_home_url'] = home
                else:
                    prefs.pop('user_home_url', None)
            profile.preferences = prefs
        profile.is_configured = True
        # Onboarding is the user's own preference selection — don't log it or fire a
        # "profile updated" notification (the preferences-only skip in signals doesn't catch
        # this two-field save).
        profile.skip_signal_logging = True
        profile.save(update_fields=['preferences', 'is_configured'])
        # refresh_parent makes the dynamic modal reload the page (dismissing the modal and
        # applying the new theme/language immediately) instead of re-opening itself.
        return JsonResponse({'success': True, 'refresh_parent': True})

    prefs = profile.preferences if isinstance(profile.preferences, dict) else {}
    resolved_prefs = resolve_user_theme_preference(
        prefs,
        config,
        scope=get_user_scope(request.user),
        scopes_enabled=is_scope_enabled(),
    )
    allowed_font_slugs = set(config.get('allowed_fonts') or [])
    context = {
        'allow_theme': allow_theme,
        'allow_language': allow_language,
        'allow_fonts': allow_fonts,
        'allow_home': allow_home,
        'theme_options': get_theme_options(s, config.get('allowed_themes')),
        'language_options': config.get('languages') or {},
        'font_options': [f for f in get_available_fonts() if not allowed_font_slugs or f['slug'] in allowed_font_slugs],
        'current_theme': resolved_prefs.get('theme') or config.get('default_theme'),
        'current_language': prefs.get('language') or config.get('default_language'),
        'current_font': prefs.get('font') or '',
        'current_home': prefs.get('user_home_url') or '',
        'home_url_options': build_user_home_url_options(request.user) if allow_home else [],
        'DLUX_STRINGS': s,
    }
    # The dlux dynamic modal fetches via AJAX and expects {html: ...}; a direct browser GET
    # gets the rendered fragment.
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        from django.template.loader import render_to_string
        return JsonResponse({'html': render_to_string('dlux/includes/initial_user_setup.html', context, request=request)})
    return render(request, 'dlux/includes/initial_user_setup.html', context)
