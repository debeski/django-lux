# Fundemental imports
import logging

from django.apps import apps
from django.contrib import messages
from django.contrib.auth import logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.sessions.models import Session
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

# Project imports
from django.utils.module_loading import import_string
from ..guards import require_current_password
from ..utils import log_user_action
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
    now = timezone.now().isoformat()
    existing = request.session.get('microsys_device')
    if not isinstance(existing, dict):
        existing = {}
    metadata = {
        'user_agent': request.META.get('HTTP_USER_AGENT', '')[:500],
        'ip_address': request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', '')).split(',')[0].strip(),
        'first_seen': existing.get('first_seen') or now,
        'last_seen': now,
    }
    request.session['microsys_device'] = metadata
    request.session.modified = True
    return metadata


def _profile_sessions_for_user(user, current_session_key=None, current_session_data=None, current_expire_date=None):
    sessions = []
    now = timezone.now()
    user_id = str(user.pk)
    has_current_session = False

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
        user_agent = metadata.get('user_agent') or ''
        last_seen = _parse_session_datetime(metadata.get('last_seen'))
        first_seen = _parse_session_datetime(metadata.get('first_seen'))

        is_current = bool(current_session_key and session.session_key == current_session_key)
        has_current_session = has_current_session or is_current

        sessions.append({
            'session_key': session.session_key,
            'is_current': is_current,
            'device_label': _device_label(user_agent),
            'user_agent': user_agent,
            'ip_address': metadata.get('ip_address') or '',
            'first_seen': first_seen,
            'last_seen': last_seen,
            'expire_date': session.expire_date,
        })

    if current_session_key and not has_current_session:
        metadata = current_session_data.get('microsys_device') if isinstance(current_session_data, dict) and isinstance(current_session_data.get('microsys_device'), dict) else {}
        user_agent = metadata.get('user_agent') or ''
        sessions.append({
            'session_key': current_session_key,
            'is_current': True,
            'device_label': _device_label(user_agent),
            'user_agent': user_agent,
            'ip_address': metadata.get('ip_address') or '',
            'first_seen': _parse_session_datetime(metadata.get('first_seen')),
            'last_seen': _parse_session_datetime(metadata.get('last_seen')) or now,
            'expire_date': current_expire_date or now,
        })

    return sorted(sessions, key=lambda item: (not item['is_current'], -(item['last_seen'] or item['expire_date']).timestamp()))


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

    target_session = get_object_or_404(Session, session_key=session_key)
    try:
        decoded = target_session.get_decoded()
    except Exception:
        decoded = {}

    if str(decoded.get('_auth_user_id') or '') != str(request.user.pk):
        messages.error(
            request,
            get_strings().get('session_revoke_denied', 'That session does not belong to your account.'),
            fail_silently=True,
        )
        return redirect('user_profile')

    is_current_session = session_key == request.session.session_key
    target_session.delete()
    log_user_action(request, "DELETE", instance=request.user, model_name="session", number=session_key[:8])

    messages.success(
        request,
        get_strings().get('session_revoked_success', 'Session signed out.'),
        fail_silently=True,
    )
    if is_current_session:
        logout(request)
        return redirect('login')
    return redirect('user_profile')
