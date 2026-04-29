# Fundemental imports
import base64
import logging
import os
import random
import secrets
import string
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
from django.core.mail import send_mail
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.crypto import constant_time_compare
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

# Project imports
from ..constants import DEFAULT_HOME_URL
from ..translations import get_strings
from ..utils import get_system_config

User = get_user_model()
logger = logging.getLogger('microsys')


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


# 2FA Helper — Generates and emails a 6-digit OTP code
def send_otp(request, user, intent='login'):
    """
    Generates a 6-digit OTP, stores it in cache, and sends it via email.
    intent: 'login' or an enable_* flow.
    """
    code = ''.join(random.choices(string.digits, k=6))
    cache_key = f"otp_{user.pk}_{intent}"
    cache.set(cache_key, {'code': code, 'attempts': 0}, timeout=300)

    s = get_strings()
    subject_key = '2fa_login_email_subject' if intent == 'login' else '2fa_setup_email_subject'
    subject = s.get(subject_key, 'Authentication Code')
    body = s.get('2fa_email_body', 'Your code is {code}').format(code=code)

    try:
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
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
    cache_key = f"otp_{user.pk}_{intent}"
    data = cache.get(cache_key)

    if not data:
        return False, '2fa_invalid_code'

    if constant_time_compare(str(data.get('code', '')), str(code)):
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


# 2FA View — Handles OTP verification for login and method activation
def verify_otp_view(request, intent='login'):
    """
    Handles OTP verification for Login and Activating specific methods.
    intent: 'login', 'enable', 'enable_email', 'enable_phone', 'enable_totp'
    """
    s = get_strings()
    error_message = None
    user = None

    if intent == 'login':
        user_id = request.session.get('pre_2fa_user_id')
        if not user_id:
            return redirect('login')
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            request.session.pop('pre_2fa_user_id', None)
            return redirect('login')
    else:
        if not request.user.is_authenticated:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'message': 'Not authenticated'}, status=403)
            return redirect('login')
        user = request.user

    if request.method == 'POST':
        code = request.POST.get('otp_code', '').strip()
        method = request.POST.get('method', 'email')
        posted_intent = request.POST.get('intent')
        if posted_intent:
            intent = posted_intent

        is_valid = False
        error_key = '2fa_invalid_code'

        if intent == 'enable_totp' or (intent == 'login' and method == 'totp'):
            if pyotp and user.profile.totp_secret:
                totp = pyotp.TOTP(user.profile.totp_secret)
                is_valid = bool(totp.verify(code, valid_window=1))
        elif intent == 'login' and method == 'backup_code':
            is_valid = _consume_backup_code(user.profile, code)
        else:
            check_intent = intent
            if intent == 'enable' and method in {'email', 'phone'}:
                check_intent = f'enable_{method}'
            is_valid, error_key = verify_otp_logic(user, code, intent=check_intent)

        if is_valid:
            if intent == 'login':
                login(request, user)
                request.session.pop('pre_2fa_user_id', None)
                return redirect(_resolve_safe_login_redirect(request))

            was_2fa_enabled = user.profile.is_2fa_enabled

            if intent == 'enable_email':
                user.profile.is_email_2fa_enabled = True
            elif intent == 'enable_phone':
                user.profile.is_phone_2fa_enabled = True
            elif intent == 'enable_totp':
                user.profile.is_totp_2fa_enabled = True

            user.profile.save()

            response_data = {'status': 'success'}
            if not was_2fa_enabled or not user.profile.backup_codes:
                raw_codes = _generate_backup_code_values()
                user.profile.backup_codes = _hash_backup_code_values(raw_codes)
                user.profile.save(update_fields=['backup_codes'])
                response_data['backup_codes'] = raw_codes

            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse(response_data)

            messages.success(request, s.get('2fa_enabled_msg', '2FA Enabled'))
            return redirect('user_profile')

        error_msg = s.get(error_key, 'Invalid Code')
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'message': error_msg})
        error_message = error_msg

    return render(request, 'microsys/2fa/verify.html', {
        'intent': intent,
        'error_message': error_message,
        'MS_TRANS': s,
        'user_methods': {
            'email': user.profile.is_email_2fa_enabled,
            'phone': user.profile.is_phone_2fa_enabled,
            'totp': user.profile.is_totp_2fa_enabled,
        } if intent == 'login' else {},
    })


# 2FA Setup — Generates TOTP secret and QR code for authenticator apps
@login_required
@require_POST
def setup_totp(request):
    """Generates secret and QR code."""
    if not pyotp or not qrcode:
        return JsonResponse({'status': 'error', 'message': 'TOTP is unavailable'}, status=503)

    profile = request.user.profile
    if not profile.totp_secret:
        profile.totp_secret = pyotp.random_base32()
        profile.save(update_fields=['totp_secret'])

    totp_uri = pyotp.totp.TOTP(profile.totp_secret).provisioning_uri(
        name=request.user.email,
        issuer_name=_resolve_totp_issuer_name()
    )

    img = qrcode.make(totp_uri)
    buffered = BytesIO()
    img.save(buffered, format='PNG')
    img_str = base64.b64encode(buffered.getvalue()).decode()

    return JsonResponse({
        'status': 'success',
        'qr_code': img_str,
        'secret': profile.totp_secret,
    })


# 2FA Setup — Triggers OTP delivery for activating email/phone 2FA
@login_required
@require_POST
def enable_2fa(request):
    """
    Triggers 2FA Setup for Email/Phone.
    Target method specified by POST param 'method' (email/phone).
    """
    method = request.POST.get('method', 'email')
    if method not in {'email', 'phone'}:
        return JsonResponse({'status': 'error', 'message': 'Invalid Method'}, status=400)

    if method == 'email' and request.user.profile.is_email_2fa_enabled:
        return JsonResponse({'status': 'error', 'message': 'Already enabled'})
    if method == 'phone' and request.user.profile.is_phone_2fa_enabled:
        return JsonResponse({'status': 'error', 'message': 'Already enabled'})

    if send_otp(request, request.user, intent=f'enable_{method}'):
        return JsonResponse({'status': 'success'})

    return JsonResponse({'status': 'error', 'message': 'Failed to send OTP'}, status=500)


# 2FA Management — Disables a specific 2FA method and clears its secret
@login_required
@require_POST
def disable_2fa(request):
    """
    Disables a specific 2FA method.
    """
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
        profile.is_totp_2fa_enabled = False
        profile.totp_secret = ''
        update_fields = ['is_totp_2fa_enabled', 'totp_secret']
    else:
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': 'Invalid Method'}, status=400)
        messages.error(request, 'Invalid Method')
        return redirect('user_profile')

    profile.save(update_fields=update_fields)

    if is_ajax:
        return JsonResponse({'status': 'success'})

    messages.success(request, get_strings().get('2fa_disabled_msg', 'Disabled'))
    return redirect('user_profile')


# 2FA Helper — Resends OTP code for login or method activation
@require_POST
def resend_otp(request, intent='login'):
    intent = request.POST.get('intent') or intent
    user = None

    if intent == 'login':
        user_id = request.session.get('pre_2fa_user_id')
        if user_id:
            try:
                user = User.objects.get(pk=user_id)
            except User.DoesNotExist:
                user = None
    elif request.user.is_authenticated:
        user = request.user

    if user and send_otp(request, user, intent=intent):
        messages.success(request, 'Code Sent')
    else:
        messages.error(request, 'Unable to send code')

    if intent == 'login':
        return redirect('verify_otp_login')
    return redirect('verify_otp_enable')


# 2FA Management — Generates new backup codes for account recovery
@login_required
@require_POST
def generate_backup_codes(request):
    """Generates 8 new backup codes for the user."""
    raw_codes = _generate_backup_code_values()
    request.user.profile.backup_codes = _hash_backup_code_values(raw_codes)
    request.user.profile.save(update_fields=['backup_codes'])
    return JsonResponse({'status': 'success', 'codes': raw_codes})
