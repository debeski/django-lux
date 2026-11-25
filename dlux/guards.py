from django.contrib.auth import update_session_auth_hash
from django.http import JsonResponse
from django.shortcuts import redirect

from .notifications import notify
from .translations import get_strings


def check_own_password(request, raw_password, user=None):
    """``user.check_password()`` for the signed-in user that keeps them signed in.

    A correct password whose hasher has since raised its work factor (Django
    6.1.3 moved PBKDF2 from 1.2M to 1.5M iterations) is re-hashed and saved by
    ``check_password``. That changes the session auth hash, so this session was
    signed out on its next request. When the check re-hashed the request's own
    user, refresh the session the way Django's password change views do.
    """
    user = user if user is not None else request.user
    before = user.password
    matched = user.check_password(raw_password)
    keep_session_after_rehash(request, user, before)
    return matched


def keep_session_after_rehash(request, user, previous_hash):
    """Refresh this session's auth hash when ``user`` is its user and the stored
    hash changed since ``previous_hash`` (a re-hash during a password check)."""
    if request is None or user is None or user.password == previous_hash:
        return
    session_user = getattr(request, 'user', None)
    if getattr(session_user, 'pk', None) is not None and session_user.pk == user.pk:
        update_session_auth_hash(request, user)


def require_current_password(request, redirect_name='user_profile', field_name='current_password'):
    """
    Enforce current-password confirmation for a POST action.

    Usage:
        if failure_response := require_current_password(request):
            return failure_response
    """
    current_password = str(request.POST.get(field_name) or '')
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
    s = get_strings()

    if not current_password:
        message = s.get('current_password_required', 'Please enter your current password.')
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': message}, status=400)
        notify.error(
            message,
            request=request,
            action='current_password_required',
            category='security',
            metadata={'message_key': 'current_password_required'},
        )
        return redirect(redirect_name)

    if not check_own_password(request, current_password):
        message = s.get('current_password_incorrect', 'Current password is incorrect.')
        try:
            from .utils import log_audit_event
            log_audit_event(request, 'permission_denied', "PERMISSION_DENIED",
                            instance=request.user, model_name="password")
        except Exception:
            pass
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': message}, status=400)
        notify.error(
            message,
            request=request,
            action='current_password_incorrect',
            category='security',
            metadata={'message_key': 'current_password_incorrect'},
        )
        return redirect(redirect_name)

    return None
