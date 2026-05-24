# Fundemental imports
import base64
import logging
import os
import secrets
import string
import time
from io import BytesIO

try:
    import pyotp
except ImportError:
    pyotp = None

try:
    import qrcode
except ImportError:
    qrcode = None

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import check_password, identify_hasher, make_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import DatabaseError
from django.http import JsonResponse
from django.shortcuts import redirect, render, resolve_url
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.utils.http import url_has_allowed_host_and_scheme
from django.urls import reverse
from django.views.decorators.http import require_POST

# Project imports
from ..constants import DEFAULT_HOME_URL
from ..guards import require_current_password
from ..translations import get_strings
from ..trust import (
    TRUSTED_DEVICE_COOKIE_NAME,
    TRUSTED_DEVICE_COOKIE_SALT,
    TRUSTED_DEVICE_MAX_AGE,
    device_label as trust_device_label,
    get_trusted_device_for_login as trust_get_trusted_device_for_login,
    issue_trusted_device,
    sync_session_device_metadata,
    trusted_device_model,
    trusted_device_token_hash,
)
from ..utils import get_client_ip, get_profile_totp_secret, get_system_config, send_microsys_mail, set_profile_totp_state

User = get_user_model()
logger = logging.getLogger('microsys')

TWOFA_IP_VERIFY_LIMIT = int(getattr(settings, 'MICROSYS_2FA_IP_VERIFY_LIMIT', 20))
TWOFA_IP_VERIFY_WINDOW = int(getattr(settings, 'MICROSYS_2FA_IP_VERIFY_WINDOW', 600))
TWOFA_IP_SEND_LIMIT = int(getattr(settings, 'MICROSYS_2FA_IP_SEND_LIMIT', 10))
TWOFA_IP_SEND_WINDOW = int(getattr(settings, 'MICROSYS_2FA_IP_SEND_WINDOW', 3600))
LOGIN_EMAIL_RESEND_COOLDOWN_SECONDS = 120
DEFAULT_OTP_RESEND_COOLDOWN_SECONDS = 60
PRE_2FA_USER_ID_SESSION_KEY = 'pre_2fa_user_id'
PRE_2FA_METHOD_SESSION_KEY = 'pre_2fa_method'
PRE_2FA_EMAIL_SENT_SESSION_KEY = 'pre_2fa_email_sent'
PRE_2FA_EMAIL_AUTO_SENT_SESSION_KEY = 'pre_2fa_email_auto_sent'
PRE_2FA_NEXT_URL_SESSION_KEY = 'pre_2fa_next_url'
PRE_2FA_DEFAULT_REDIRECT_SESSION_KEY = 'pre_2fa_default_redirect'


def _generate_backup_code_values():
    return [''.join(secrets.choice(string.digits) for _ in range(8)) for _ in range(8)]


def _is_hashed_backup_code(value):
    if not isinstance(value, str) or not value:
        return False
    try:
        identify_hasher(value)
        return True
    except Exception:
        return False


def _hash_backup_code_values(codes):
    hashed_codes = []
    for code in codes or []:
        normalized = str(code or '').strip()
        if normalized:
            hashed_codes.append(make_password(normalized))
    return hashed_codes


def _consume_backup_code(profile, raw_code):
    normalized = str(raw_code or '').strip()
    if not normalized:
        return False

    stored_codes = list(profile.backup_codes or [])
    remaining_codes = []
    matched = False
    saw_legacy_value = False

    for stored_code in stored_codes:
        if not isinstance(stored_code, str) or not stored_code:
            continue

        if _is_hashed_backup_code(stored_code):
            if not matched and check_password(normalized, stored_code):
                matched = True
                continue
            remaining_codes.append(stored_code)
            continue

        saw_legacy_value = True
        if not matched and constant_time_compare(normalized, stored_code):
            matched = True
            continue
        remaining_codes.append(make_password(stored_code))

    if matched:
        profile.backup_codes = remaining_codes
        profile.save(update_fields=['backup_codes'])
        return True

    if saw_legacy_value:
        profile.backup_codes = remaining_codes
        profile.save(update_fields=['backup_codes'])

    return False


def _resolve_safe_login_redirect(request):
    session = getattr(request, 'session', None)
    if session is not None:
        next_url = str(session.get(PRE_2FA_NEXT_URL_SESSION_KEY) or '').strip()
        if next_url:
            return next_url
        default_redirect = str(session.get(PRE_2FA_DEFAULT_REDIRECT_SESSION_KEY) or '').strip()
        if default_redirect:
            return default_redirect

    next_url = request.GET.get('next') or request.POST.get('next')
    allowed_hosts = {request.get_host()} if request.get_host() else set()
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts=allowed_hosts,
        require_https=request.is_secure(),
    ):
        return next_url

    try:
        home_url = get_system_config().get('home_url')
    except Exception:
        home_url = None

    if home_url:
        return home_url
    return getattr(settings, 'LOGIN_REDIRECT_URL', DEFAULT_HOME_URL)


def _resolve_totp_issuer_name():
    try:
        config = get_system_config()
    except Exception:
        config = {}

    identity = config.get('identity') if isinstance(config, dict) else {}
    if isinstance(identity, dict):
        issuer_name = str(identity.get('display_name') or '').strip()
        if issuer_name:
            return issuer_name

    if isinstance(config, dict):
        issuer_name = str(config.get('display_name') or config.get('verbose_name') or '').strip()
        if issuer_name:
            return issuer_name

    return 'microSYS'


def _otp_cache_key(user, intent):
    return f"otp_{user.pk}_{intent}"


def _otp_cooldown_key(user, intent):
    return f"otp_cooldown_{user.pk}_{intent}"


def _otp_cooldown_seconds(intent='login'):
    return LOGIN_EMAIL_RESEND_COOLDOWN_SECONDS if intent == 'login' else DEFAULT_OTP_RESEND_COOLDOWN_SECONDS


def _otp_cooldown_scope(intent, recipient_email=None):
    if intent == 'enable_email' and recipient_email:
        return f"{intent}:{str(recipient_email).strip().lower()}"
    return intent


def _otp_cooldown_remaining(user, intent='login', recipient_email=None):
    raw_value = cache.get(_otp_cooldown_key(user, _otp_cooldown_scope(intent, recipient_email)))
    if not raw_value:
        return 0
    if isinstance(raw_value, (int, float)):
        return max(0, int(raw_value - time.time()))
    return _otp_cooldown_seconds(intent)


def _set_otp_cooldown(user, intent='login', recipient_email=None):
    cooldown_seconds = _otp_cooldown_seconds(intent)
    cache.set(
        _otp_cooldown_key(user, _otp_cooldown_scope(intent, recipient_email)),
        time.time() + cooldown_seconds,
        timeout=cooldown_seconds,
    )
    return cooldown_seconds


def _twofa_ip_key(kind, request, intent='login'):
    ip_address = get_client_ip(request) if request else None
    if not ip_address:
        return None
    normalized_intent = str(intent or 'login').replace(':', '_')
    return f"microsys:2fa:{kind}:ip:{ip_address}:{normalized_intent}"


def _increment_cache_counter(key, timeout):
    if not key:
        return 0
    try:
        return cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=timeout)
        return 1


def _twofa_ip_limited(kind, request, intent='login'):
    key = _twofa_ip_key(kind, request, intent)
    if not key:
        return False
    limit = TWOFA_IP_SEND_LIMIT if kind == 'send' else TWOFA_IP_VERIFY_LIMIT
    return int(cache.get(key, 0) or 0) >= limit


def _record_twofa_ip_event(kind, request, intent='login'):
    key = _twofa_ip_key(kind, request, intent)
    timeout = TWOFA_IP_SEND_WINDOW if kind == 'send' else TWOFA_IP_VERIFY_WINDOW
    return _increment_cache_counter(key, timeout)


def _otp_code_matches(data, raw_code):
    normalized = str(raw_code or '')
    if data.get('code_hash'):
        return check_password(normalized, data.get('code_hash'))
    return constant_time_compare(str(data.get('code', '')), normalized)


def _generate_email_otp_code():
    return ''.join(secrets.choice(string.digits) for _ in range(6))


def _email_otp_exists(user, intent='login'):
    return bool(cache.get(_otp_cache_key(user, intent)))


def _trusted_device_model():
    return trusted_device_model()


def _trusted_device_token_hash(raw_token):
    return trusted_device_token_hash(raw_token)


def _device_label(user_agent):
    return trust_device_label(user_agent)


def _sync_session_device_metadata(request, trusted_device=None):
    return sync_session_device_metadata(request, trusted_device=trusted_device)


def _primary_login_methods(profile):
    methods = []
    if getattr(profile, 'is_totp_2fa_enabled', False):
        methods.append('totp')
    if getattr(profile, 'is_email_2fa_enabled', False):
        methods.append('email')
    if getattr(profile, 'is_phone_2fa_enabled', False):
        methods.append('phone')
    return methods


def _default_login_method(profile):
    methods = _primary_login_methods(profile)
    if 'totp' in methods:
        return 'totp'
    if 'email' in methods:
        return 'email'
    if 'phone' in methods:
        return 'phone'
    return 'email'


def _clear_pre_2fa_session_state(request):
    session = getattr(request, 'session', None)
    if session is None:
        return
    for key in (
        PRE_2FA_USER_ID_SESSION_KEY,
        PRE_2FA_METHOD_SESSION_KEY,
        PRE_2FA_EMAIL_SENT_SESSION_KEY,
        PRE_2FA_EMAIL_AUTO_SENT_SESSION_KEY,
        PRE_2FA_NEXT_URL_SESSION_KEY,
        PRE_2FA_DEFAULT_REDIRECT_SESSION_KEY,
    ):
        session.pop(key, None)


def get_trusted_device_for_login(request, user):
    return trust_get_trusted_device_for_login(request, user)


def prepare_login_2fa_challenge(request, user, *, next_url='', default_redirect=''):
    profile = user.profile
    primary_methods = _primary_login_methods(profile)
    default_method = _default_login_method(profile)
    session = request.session
    session[PRE_2FA_USER_ID_SESSION_KEY] = user.pk
    session[PRE_2FA_METHOD_SESSION_KEY] = default_method
    session[PRE_2FA_EMAIL_SENT_SESSION_KEY] = False
    session[PRE_2FA_EMAIL_AUTO_SENT_SESSION_KEY] = False
    session[PRE_2FA_NEXT_URL_SESSION_KEY] = str(next_url or '').strip()
    session[PRE_2FA_DEFAULT_REDIRECT_SESSION_KEY] = str(default_redirect or '').strip()

    auto_sent = False
    if primary_methods == ['email'] and str(user.email or '').strip():
        auto_sent = bool(send_otp(request, user, intent='login'))
        session[PRE_2FA_METHOD_SESSION_KEY] = 'email'
        session[PRE_2FA_EMAIL_SENT_SESSION_KEY] = bool(auto_sent or _email_otp_exists(user, 'login'))
        session[PRE_2FA_EMAIL_AUTO_SENT_SESSION_KEY] = bool(auto_sent)
    session.modified = True
    return auto_sent


def _issue_trusted_device(request, response, user):
    return issue_trusted_device(request, response, user)


def _build_login_challenge_state(request, user):
    s = get_strings()
    profile = user.profile
    session = request.session
    current_method = str(session.get(PRE_2FA_METHOD_SESSION_KEY) or _default_login_method(profile)).strip() or 'email'
    if current_method == 'phone':
        current_method = 'email'
    if current_method == 'backup_code':
        code_length = 8
    else:
        code_length = 6
    return {
        'current_method': current_method,
        'default_method': _default_login_method(profile),
        'email_available': bool(profile.is_email_2fa_enabled),
        'totp_available': bool(profile.is_totp_2fa_enabled),
        'backup_available': bool(profile.backup_codes),
        'email_only': _primary_login_methods(profile) == ['email'],
        'email_sent': bool(session.get(PRE_2FA_EMAIL_SENT_SESSION_KEY) or _email_otp_exists(user, 'login')),
        'email_auto_sent': bool(session.get(PRE_2FA_EMAIL_AUTO_SENT_SESSION_KEY)),
        'email_resend_cooldown_seconds': _otp_cooldown_remaining(user, 'login'),
        'code_length': code_length,
        'trust_device_label': s.get('2fa_trust_device_label'),
        'verify_url': reverse('verify_otp_login'),
        'resend_url': reverse('resend_otp_login'),
    }


# 2FA Helper — Generates and emails a 6-digit OTP code
def send_otp(request, user, intent='login', recipient_email=None):
    """
    Generates a 6-digit OTP, stores it in cache, and sends it via email.
    intent: 'login' or an enable_* flow.
    """
    if _twofa_ip_limited('send', request, intent):
        logger.warning("2FA OTP send rate limited for user pk=%s intent=%s", user.pk, intent)
        return False

    recipient_email = str(recipient_email or user.email or '').strip()
    if _otp_cooldown_remaining(user, intent, recipient_email):
        return False

    if not recipient_email:
        return False

    _record_twofa_ip_event('send', request, intent)

    code = _generate_email_otp_code()
    cache_key = _otp_cache_key(user, intent)
    payload = {'code_hash': make_password(code), 'attempts': 0}
    if intent == 'enable_email':
        payload['email'] = recipient_email
    cache.set(cache_key, payload, timeout=300)
    _set_otp_cooldown(user, intent, recipient_email)

    s = get_strings()
    subject_key = '2fa_login_email_subject' if intent == 'login' else '2fa_setup_email_subject'
    subject = s.get(subject_key)
    body = s.get('2fa_email_body').format(code=code)

    try:
        send_microsys_mail(
            subject,
            body,
            [recipient_email],
            fail_silently=False,
        )
        logger.info("Sent OTP challenge email for user pk=%s intent=%s", user.pk, intent)
        return True
    except Exception:
        logger.exception("Failed to send OTP challenge email for user pk=%s intent=%s", user.pk, intent)
        return False


# 2FA Helper — Verifies an OTP code against the cache
def verify_otp_logic(user, code, intent='login'):
    """
    Verifies the OTP from cache.
    Returns: (True, None) or (False, error_message_key)
    """
    cache_key = _otp_cache_key(user, intent)
    data = cache.get(cache_key)

    if not data:
        return False, '2fa_invalid_code'

    if _otp_code_matches(data, code):
        cache.delete(cache_key)
        return True, None

    attempts = int(data.get('attempts', 0)) + 1
    if attempts >= 3:
        cache.delete(cache_key)
        return False, '2fa_invalid_code'

    data['attempts'] = attempts
    cache.set(cache_key, data, timeout=300)
    return False, '2fa_invalid_code'


# 2FA Config — Returns available 2FA methods based on server environment
def get_2fa_config():
    """Returns available 2FA methods based on system config (DB + MICROSYS_CONFIG)."""
    config = get_system_config()
    return {
        'email': bool(config.get('email_2fa', False)),
        'phone': bool(os.getenv('SMS_BACKEND')),
        'totp': bool(pyotp and qrcode),
    }


def _login_user_methods(user):
    return {
        'email': user.profile.is_email_2fa_enabled,
        'phone': user.profile.is_phone_2fa_enabled,
        'totp': user.profile.is_totp_2fa_enabled,
        'backup': bool(user.profile.backup_codes),
    }


# 2FA View — Handles OTP verification for login and method activation
def verify_otp_view(request, intent='login'):
    """
    Handles OTP verification for Login and Activating specific methods.
    intent: 'login', 'enable', 'enable_email', 'enable_phone', 'enable_totp'
    """
    s = get_strings()
    error_message = None
    user = None
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if intent == 'login':
        user_id = request.session.get(PRE_2FA_USER_ID_SESSION_KEY)
        if not user_id:
            return redirect('login')
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            _clear_pre_2fa_session_state(request)
            return redirect('login')
    else:
        if not request.user.is_authenticated:
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': s.get('err_not_authenticated')}, status=403)
            return redirect('login')
        user = request.user

    user_methods = _login_user_methods(user) if intent == 'login' else {}

    if request.method == 'POST':
        code = request.POST.get('otp_code', '').strip()
        method = str(request.POST.get('method') or '').strip() or (
            request.session.get(PRE_2FA_METHOD_SESSION_KEY, 'email') if intent == 'login' else 'email'
        )
        posted_intent = request.POST.get('intent')
        if posted_intent:
            intent = posted_intent

        if _twofa_ip_limited('verify', request, intent):
            error_msg = s.get('2fa_invalid_code')
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': error_msg}, status=429)
            error_message = error_msg
            return render(request, 'microsys/2fa/verify.html', {
                'intent': intent,
                'error_message': error_message,
                'MS_TRANS': s,
                'user_methods': user_methods,
                'challenge_state': _build_login_challenge_state(request, user) if intent == 'login' else {},
            }, status=429)

        is_valid = False
        error_key = '2fa_invalid_code'
        pending_email = None

        if intent == 'enable_totp' or (intent == 'login' and method == 'totp'):
            totp_secret = get_profile_totp_secret(user.profile)
            if pyotp and totp_secret:
                totp = pyotp.TOTP(totp_secret)
                is_valid = bool(totp.verify(code, valid_window=1))
        elif intent == 'login' and method == 'backup_code':
            is_valid = _consume_backup_code(user.profile, code)
        elif intent == 'login' and method == 'email':
            is_valid, error_key = verify_otp_logic(user, code, intent='login')
        else:
            check_intent = intent
            if intent == 'enable' and method in {'email', 'phone'}:
                check_intent = f'enable_{method}'
            pending_email = None
            if check_intent == 'enable_email':
                pending_data = cache.get(_otp_cache_key(user, check_intent)) or {}
                pending_email = str(pending_data.get('email') or '').strip()
            is_valid, error_key = verify_otp_logic(user, code, intent=check_intent)

        if is_valid:
            if intent == 'login':
                login(request, user)
                _sync_session_device_metadata(request)
                redirect_url = _resolve_safe_login_redirect(request)
                should_trust_device = str(request.POST.get('trust_device') or '').strip().lower() in {'1', 'true', 'on', 'yes'}
                response = JsonResponse({'status': 'success', 'redirect_url': redirect_url}) if is_ajax else redirect(redirect_url)
                if should_trust_device:
                    _issue_trusted_device(request, response, user)
                _clear_pre_2fa_session_state(request)
                return response

            was_2fa_enabled = user.profile.is_2fa_enabled

            if intent == 'enable_email':
                if pending_email:
                    try:
                        validate_email(pending_email)
                    except ValidationError:
                        return JsonResponse({'status': 'error', 'message': s.get('2fa_invalid_email')}, status=400)
                    if user.email != pending_email:
                        user.email = pending_email
                        user.save(update_fields=['email'])
                user.profile.is_email_2fa_enabled = True
                if hasattr(user.profile, 'email_verified_at'):
                    user.profile.email_verified_at = timezone.now()
            elif intent == 'enable_phone':
                user.profile.is_phone_2fa_enabled = True
            elif intent == 'enable_totp':
                set_profile_totp_state(user.profile, enabled=True)

            if intent == 'enable_email' and hasattr(user.profile, 'email_verified_at'):
                user.profile.save(update_fields=['is_email_2fa_enabled', 'email_verified_at'])
            elif intent == 'enable_email':
                user.profile.save(update_fields=['is_email_2fa_enabled'])
            elif intent == 'enable_phone':
                user.profile.save(update_fields=['is_phone_2fa_enabled'])

            response_data = {'status': 'success'}
            if not was_2fa_enabled or not user.profile.backup_codes:
                raw_codes = _generate_backup_code_values()
                user.profile.backup_codes = _hash_backup_code_values(raw_codes)
                user.profile.save(update_fields=['backup_codes'])
                response_data['backup_codes'] = raw_codes

            if is_ajax:
                return JsonResponse(response_data)

            messages.success(request, s.get('2fa_enabled_msg'))
            return redirect('user_profile')

        error_msg = s.get(error_key)
        _record_twofa_ip_event('verify', request, intent)
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': error_msg})
        error_message = error_msg

    return render(request, 'microsys/2fa/verify.html', {
        'intent': intent,
        'error_message': error_message,
        'MS_TRANS': s,
        'user_methods': user_methods,
        'challenge_state': _build_login_challenge_state(request, user) if intent == 'login' else {},
    })


# 2FA Setup — Generates TOTP secret and QR code for authenticator apps
@login_required
@require_POST
def setup_totp(request):
    """Generates secret and QR code."""
    if not pyotp or not qrcode:
        return JsonResponse({'status': 'error', 'message': get_strings().get('err_totp_unavailable')}, status=503)

    profile = request.user.profile
    raw_secret = get_profile_totp_secret(profile)
    if not raw_secret:
        raw_secret = pyotp.random_base32()
        try:
            set_profile_totp_state(profile, raw_secret=raw_secret)
        except DatabaseError:
            logger.exception("Failed to save encrypted TOTP secret for user pk=%s", request.user.pk)
            return JsonResponse({
                'status': 'error',
                'message': get_strings().get('err_unable_save_totp'),
            }, status=500)
        except Exception:
            logger.exception("Failed to persist TOTP secret for user pk=%s", request.user.pk)
            return JsonResponse({
                'status': 'error',
                'message': get_strings().get('2fa_totp_prepare_failed'),
            }, status=500)

    try:
        account_name = str(request.user.email or request.user.get_username() or '').strip()
        totp_uri = pyotp.TOTP(raw_secret).provisioning_uri(
            name=account_name,
            issuer_name=_resolve_totp_issuer_name()
        )

        img = qrcode.make(totp_uri)
        buffered = BytesIO()
        img.save(buffered, format='PNG')
        img_str = base64.b64encode(buffered.getvalue()).decode()
    except Exception:
        logger.exception("Failed to generate TOTP setup payload for user pk=%s", request.user.pk)
        return JsonResponse({
            'status': 'error',
            'message': get_strings().get('2fa_totp_generate_failed'),
        }, status=500)

    return JsonResponse({
        'status': 'success',
        'qr_code': img_str,
        'secret': raw_secret,
    })


# 2FA Setup — Triggers OTP delivery for activating email/phone 2FA
@login_required
@require_POST
def enable_2fa(request):
    """
    Triggers 2FA Setup for Email/Phone.
    Target method specified by POST param 'method' (email/phone).
    """
    s = get_strings()
    method = request.POST.get('method', 'email')
    if method not in {'email', 'phone'}:
        return JsonResponse({'status': 'error', 'message': s.get('err_invalid_method')}, status=400)

    if method == 'email' and request.user.profile.is_email_2fa_enabled:
        return JsonResponse({'status': 'error', 'message': s.get('err_already_enabled')})
    if method == 'phone' and request.user.profile.is_phone_2fa_enabled:
        return JsonResponse({'status': 'error', 'message': s.get('err_already_enabled')})

    recipient_email = None
    if method == 'email':
        recipient_email = str(request.POST.get('email') or request.user.email or '').strip()
        try:
            validate_email(recipient_email)
        except ValidationError:
            return JsonResponse({'status': 'error', 'message': s.get('2fa_invalid_email')}, status=400)

    if send_otp(request, request.user, intent=f'enable_{method}', recipient_email=recipient_email):
        return JsonResponse({'status': 'success'})

    return JsonResponse({'status': 'error', 'message': s.get('err_failed_send_otp')}, status=500)


# 2FA Management — Disables a specific 2FA method and clears its secret
@login_required
@require_POST
def disable_2fa(request):
    """
    Disables a specific 2FA method.
    """
    s = get_strings()
    if failure_response := require_current_password(request):
        return failure_response

    method = request.POST.get('method')
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
    profile = request.user.profile

    if method == 'email':
        profile.is_email_2fa_enabled = False
        update_fields = ['is_email_2fa_enabled']
    elif method == 'phone':
        profile.is_phone_2fa_enabled = False
        update_fields = ['is_phone_2fa_enabled']
    elif method == 'totp':
        set_profile_totp_state(profile, raw_secret='', enabled=False)
        update_fields = []
    else:
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': s.get('err_invalid_method')}, status=400)
        messages.error(request, s.get('err_invalid_method'))
        return redirect('user_profile')

    if update_fields:
        profile.save(update_fields=update_fields)

    if is_ajax:
        return JsonResponse({'status': 'success'})

    messages.success(request, s.get('2fa_disabled_msg'))
    return redirect('user_profile')


# 2FA Helper — Resends OTP code for login or method activation
@require_POST
def resend_otp(request, intent='login'):
    s = get_strings()
    intent = request.POST.get('intent') or intent
    requested_method = str(request.POST.get('method') or '').strip()
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
    user = None

    if intent == 'login':
        user_id = request.session.get(PRE_2FA_USER_ID_SESSION_KEY)
        if user_id:
            try:
                user = User.objects.get(pk=user_id)
            except User.DoesNotExist:
                user = None
    elif request.user.is_authenticated:
        user = request.user

    can_send = bool(user)
    if intent == 'login' and user:
        can_send = bool(getattr(user.profile, 'is_email_2fa_enabled', False))
        if requested_method in {'email', 'totp'}:
            request.session[PRE_2FA_METHOD_SESSION_KEY] = 'email' if requested_method == 'email' else 'totp'
        cooldown_seconds = _otp_cooldown_remaining(user, 'login')
        if requested_method == 'email' and cooldown_seconds:
            if is_ajax:
                return JsonResponse({
                    'status': 'error',
                    'message': s.get('err_unable_send_code'),
                    'cooldown_seconds': cooldown_seconds,
                }, status=400)
            messages.error(request, s.get('err_unable_send_code'))
            return redirect('verify_otp_login')

    if can_send and send_otp(request, user, intent=intent):
        if intent == 'login':
            request.session[PRE_2FA_METHOD_SESSION_KEY] = 'email'
            request.session[PRE_2FA_EMAIL_SENT_SESSION_KEY] = True
            request.session[PRE_2FA_EMAIL_AUTO_SENT_SESSION_KEY] = False
            request.session.modified = True
        cooldown_seconds = _otp_cooldown_remaining(user, intent, str(user.email or '').strip() if user else None)
        if is_ajax:
            return JsonResponse({
                'status': 'success',
                'message': s.get('msg_code_sent'),
                'cooldown_seconds': cooldown_seconds,
                'resent_method': 'email',
            })
        messages.success(request, s.get('msg_code_sent'))
    else:
        cooldown_seconds = _otp_cooldown_remaining(user, intent, str(user.email or '').strip() if user else None) if user else 0
        if is_ajax:
            return JsonResponse({
                'status': 'error',
                'message': s.get('err_unable_send_code'),
                'cooldown_seconds': cooldown_seconds,
            }, status=400)
        messages.error(request, s.get('err_unable_send_code'))

    if intent == 'login':
        return redirect('verify_otp_login')
    return redirect('verify_otp_enable')


# 2FA Management — Generates new backup codes for account recovery
@login_required
@require_POST
def generate_backup_codes(request):
    """Generates 8 new backup codes for the user."""
    if failure_response := require_current_password(request):
        return failure_response

    raw_codes = _generate_backup_code_values()
    request.user.profile.backup_codes = _hash_backup_code_values(raw_codes)
    request.user.profile.save(update_fields=['backup_codes'])
    return JsonResponse({'status': 'success', 'codes': raw_codes})
