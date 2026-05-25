# Fundemental imports
import logging

from django.apps import apps
from django.contrib import messages
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
from ..trust import (
    current_session_trusted_device,
    enforce_single_active_trusted_session,
    issue_trusted_device,
    revoke_linked_session_trust,
    sync_session_device_metadata,
    trusted_device_for_session,
)
from ..session_history import hash_session_key, mark_presence_sessions_ended
from ..utils import get_user_management_tier_state_for_user, log_user_action
from ..translations import get_strings
from .twofa import get_2fa_config

logger = logging.getLogger('microsys')


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
    trusted_devices = apps.get_model('microsys', 'TrustedDevice').objects.filter(
        user=user,
        revoked_at__isnull=True,
        trusted_until__gt=now,
    )
    trusted_by_id = {device.pk: device for device in trusted_devices}
    trusted_by_session_key = {device.session_key: device for device in trusted_devices if device.session_key}
    PresenceSession = apps.get_model('microsys', 'UserPresenceSession')
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
            metadata = current_session_data.get('microsys_device') if isinstance(current_session_data.get('microsys_device'), dict) else {}
        else:
            metadata = data.get('microsys_device') if isinstance(data.get('microsys_device'), dict) else {}
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
        metadata = current_session_data.get('microsys_device') if isinstance(current_session_data, dict) and isinstance(current_session_data.get('microsys_device'), dict) else {}
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
    CustomPasswordChangeForm = import_string('microsys.forms.CustomPasswordChangeForm')
    user = request.user
    _session_device_metadata_from_request(request)
    
    # Use dynamic form
    password_form = CustomPasswordChangeForm(user)
    
    if request.method == 'POST':
        # ... existing POST logic ...
        password_form = CustomPasswordChangeForm(user, request.POST)
        if password_form.is_valid():
            password_form.save()
            log_user_action(request, "UPDATE", instance=user, model_name="password")
            update_session_auth_hash(request, password_form.user)
            s = get_strings()
            messages.success(
                request,
                s.get('msg_password_changed', 'Password changed successfully!'),
                fail_silently=True,
            )
            return redirect('user_profile')
        else:
            s = get_strings()
            messages.error(
                request,
                s.get('msg_form_error', "There was an error with the submitted data"),
                fail_silently=True,
            )
            logger.warning("Password change validation failed for user pk=%s", user.pk)

    # --- Profile Stats & Activity ---
    UserActivityLog = apps.get_model('microsys', 'UserActivityLog')
    
    # 1. Stats
    total_actions = UserActivityLog.objects.filter(created_by=user).count()
    docs_created = UserActivityLog.objects.filter(created_by=user, action='CREATE').count()
    total_edits = UserActivityLog.objects.filter(created_by=user, action='UPDATE').count()
    total_downloads = UserActivityLog.objects.filter(created_by=user, action__in=['DOWNLOAD', 'EXPORT']).count()
    
    # 2. Activity Feeds
    # Split by app ownership:
    # - `system_interactions`: logs related to microsys app models.
    # - `recent_activity`: logs from all other apps.
    def _normalize_model_name(value):
        return str(value).strip().casefold() if value else ""

    microsys_model_names = set()
    try:
        microsys_app = apps.get_app_config('microsys')
        for model in microsys_app.get_models():
            meta = model._meta
            microsys_model_names.update({
                _normalize_model_name(meta.model_name),
                _normalize_model_name(meta.object_name),
                _normalize_model_name(meta.verbose_name),
                _normalize_model_name(meta.verbose_name_plural),
            })
    except LookupError:
        pass

    # Virtual and legacy labels used by microsys logging helpers/signals.
    microsys_model_names.update({
        "auth",
        "user",
        "profile",
        "scope",
        "scopesettings",
        "useractivitylog",
        "user profile",
        "password",
        "preferences",
        "session",
    })

    def _is_microsys_log(log_entry):
        model_key = _normalize_model_name(log_entry.model_name)
        action_key = _normalize_model_name(log_entry.action)
        if action_key in {"login", "logout"}:
            return True
        if not model_key:
            return False
        if model_key in microsys_model_names:
            return True
        # Support explicit "app_label.ModelName" payloads if logged that way.
        if "." in model_key:
            return model_key.split(".", 1)[0] == "microsys"
        return False

    recent_activity = []
    system_interactions = []
    all_user_logs = UserActivityLog.objects.filter(created_by=user).order_by('-created_at')[:200]

    for log in all_user_logs:
        if _is_microsys_log(log):
            if len(system_interactions) < 5:
                system_interactions.append(log)
        else:
            if len(recent_activity) < 5:
                recent_activity.append(log)
        if len(system_interactions) >= 5 and len(recent_activity) >= 5:
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

    context = {
        'user': request.user, # Ensure user is passed if template uses it directly
        'profile': profile,
        'password_form': password_form,
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

    return render(request, 'microsys/users/profile.html', context)


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
        messages.error(request, message, fail_silently=True)
        return redirect('user_profile')

    is_current_session = session_key == request.session.session_key
    metadata = decoded.get('microsys_device') if isinstance(decoded.get('microsys_device'), dict) else {}
    trusted_device_id = metadata.get('trusted_device_id')
    target_trusted_device = trusted_device_for_session(request.user, session_key, decoded)
    if target_trusted_device is not None and current_session_trusted_device(request) is None:
        message = get_strings().get('session_revoke_trusted_denied')
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': message}, status=403)
        messages.error(request, message, fail_silently=True)
        return redirect('user_profile')

    target_session.delete()
    mark_presence_sessions_ended([session_key], revoked=True)
    trusted_device_ids = []
    if trusted_device_id is not None:
        try:
            trusted_device_ids.append(int(trusted_device_id))
        except (TypeError, ValueError):
            pass
    revoke_linked_session_trust(request.user, [session_key], trusted_device_ids=trusted_device_ids)
    log_user_action(request, "DELETE", instance=request.user, model_name="session", number=session_key[:8])

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

    messages.success(request, success_message, fail_silently=True)
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
        messages.success(request, success_message, fail_silently=True)
        response = redirect('user_profile')

    if trusted_device is None:
        trusted_device = issue_trusted_device(request, response, request.user)
        log_user_action(request, "CREATE", instance=request.user, model_name="trusted device")
    else:
        sync_session_device_metadata(request, trusted_device=trusted_device)
        enforce_single_active_trusted_session(request, request.user, trusted_device)

    return response
