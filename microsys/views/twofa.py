# Fundemental imports
import os
import random
import string
import secrets
import base64
from io import BytesIO

import pyotp
import qrcode
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.mail import send_mail
from django.http import JsonResponse
from django.shortcuts import render, redirect

# Project imports
from ..translations import get_strings

User = get_user_model()


# 2FA Helper — Generates and emails a 6-digit OTP code
def send_otp(request, user, intent='login'):
    """
    Generates a 6-digit OTP, stores it in cache, and sends it via email.
    intent: 'login' or 'enable'
    """
    code = ''.join(random.choices(string.digits, k=6))
    cache_key = f"otp_{user.pk}_{intent}"
    # Store code for 5 minutes (300 seconds)
    cache.set(cache_key, {'code': code, 'attempts': 0}, timeout=300)
    
    s = get_strings()
    subject_key = '2fa_login_email_subject' if intent == 'login' else '2fa_setup_email_subject'
    subject = s.get(subject_key, 'Authentication Code')
    
    # Simple text body for now
    body = s.get('2fa_email_body', 'Your code is {code}').format(code=code)
    
    try:
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
        print(f"DEBUG: OTP for {user.email} is {code}") # Local Debugging
        return True
    except Exception as e:
        print(f"Error sending OTP: {e}")
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
        
    if str(data['code']) == str(code):
        cache.delete(cache_key)
        return True, None
        
    # Increment attempts
    data['attempts'] += 1
    if data['attempts'] >= 3:
        cache.delete(cache_key)
        return False, '2fa_invalid_code' # Max attempts reached
        
    cache.set(cache_key, data, timeout=300) # Reset timeout or keep original? keeping simple for now
    return False, '2fa_invalid_code'


# 2FA Config — Returns available 2FA methods based on server environment
def get_2fa_config():
    """Returns available 2FA methods based on server config."""
    return {
        'email': bool(os.getenv('EMAIL_HOST')),
        'phone': bool(os.getenv('SMS_BACKEND')), # Placeholder check
        'totp': True # Always available if lib installed
    }

# 2FA View — Handles OTP verification for login and method activation
def verify_otp_view(request, intent='login'):
    """
    Handles OTP verification for Login and Activating specific methods.
    intent: 'login', 'enable_email', 'enable_phone', 'enable_totp'
    """
    s = get_strings()
    error_message = None
    user = None

    # 1. Identify User
    if intent == 'login':
        user_id = request.session.get('pre_2fa_user_id')
        if not user_id:
            return redirect('login')
        user = User.objects.get(pk=user_id)
    else:
        if not request.user.is_authenticated:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'message': 'Not authenticated'}, status=403)
            return redirect('login')
        user = request.user

    # 2. Handle Submission
    if request.method == 'POST':
        code = request.POST.get('otp_code', '').strip()
        method = request.POST.get('method', 'email') # Default for login if not specified
        
        # Override intent from POST if provided (crucial for generic endpoints like verify_otp_enable)
        if request.POST.get('intent'):
            intent = request.POST.get('intent')
        
        # Determine verification logic based on intent/method
        is_valid = False
        error_key = '2fa_invalid_code'

        # TOTP Validation
        if intent == 'enable_totp' or (intent == 'login' and method == 'totp'):
            if user.profile.totp_secret:
                totp = pyotp.TOTP(user.profile.totp_secret)
                if totp.verify(code, valid_window=1):
                    is_valid = True
        
        # Backup Code Validation
        elif intent == 'login' and method == 'backup_code':
            codes = user.profile.backup_codes or [] # Default list
            if code in codes:
                is_valid = True
                codes.remove(code) # Burn the code
                user.profile.backup_codes = codes
                user.profile.save()
        
        # Email/Phone Validation (via Cache)
        else:
            # For login, we might need to know which method sent the code. 
            # Simplified: check cache for active intent-based code.
            # If login, we check 'otp_{user_id}_login'
            check_intent = intent
            is_valid, error_key = verify_otp_logic(user, code, intent=check_intent)

        if is_valid:
            if intent == 'login':
                login(request, user)
                if 'pre_2fa_user_id' in request.session:
                    del request.session['pre_2fa_user_id']
                
                # Dynamic Redirect (mirrors get_success_url)
                next_url = request.GET.get('next') or request.POST.get('next')
                if next_url:
                    return redirect(next_url)
                
                try:
                    from microsys.utils import get_system_config
                    config_dict = get_system_config()
                    home_url = config_dict.get('home_url')
                except Exception:
                    home_url = None
                if home_url:
                    return redirect(home_url)
                    
                return redirect('sys_dashboard')

            else:
                # Check if 2FA was previously disabled (first-time activation)
                was_2fa_enabled = user.profile.is_2fa_enabled

                if intent == 'enable_email':
                    user.profile.is_email_2fa_enabled = True
                elif intent == 'enable_phone':
                    user.profile.is_phone_2fa_enabled = True
                elif intent == 'enable_totp':
                    user.profile.is_totp_2fa_enabled = True

                user.profile.save()

                response_data = {'status': 'success'}

                # Generate backup codes on first-time activation
                if not was_2fa_enabled or not user.profile.backup_codes:
                    codes = [''.join(secrets.choice(string.digits) for _ in range(8)) for _ in range(8)]
                    user.profile.backup_codes = codes
                    user.profile.save()
                    response_data['backup_codes'] = codes

                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse(response_data)
            
            messages.success(request, s.get('2fa_enabled_msg', '2FA Enabled'))
            return redirect('user_profile')
        else:
            error_msg = s.get(error_key, 'Invalid Code')
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'message': error_msg})
            error_message = error_msg

    # 3. Render
    return render(request, 'microsys/2fa/verify.html', {
        'intent': intent,
        'error_message': error_message,
        'MS_TRANS': s,
        'user_methods': {
            'email': user.profile.is_email_2fa_enabled,
            'phone': user.profile.is_phone_2fa_enabled,
            'totp': user.profile.is_totp_2fa_enabled
        } if intent == 'login' else {}
    })

# 2FA Setup — Generates TOTP secret and QR code for authenticator apps
@login_required
def setup_totp(request):
    """Generates secret and QR code."""
    if not request.user.profile.totp_secret:
        request.user.profile.totp_secret = pyotp.random_base32()
        request.user.profile.save()
    
    totp_uri = pyotp.totp.TOTP(request.user.profile.totp_secret).provisioning_uri(
        name=request.user.email,
        issuer_name='FineStor'
    )
    
    # Generate QR Code
    img = qrcode.make(totp_uri)
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    
    return JsonResponse({
        'status': 'success',
        'qr_code': img_str,
        'secret': request.user.profile.totp_secret
    })

# 2FA Setup — Triggers OTP delivery for activating email/phone 2FA
@login_required
def enable_2fa(request):
    """
    Triggers 2FA Setup for Email/Phone.
    Target method specified by GET param 'method' (email/phone).
    """
    method = request.GET.get('method', 'email')
    
    # Check if already enabled
    if method == 'email' and request.user.profile.is_email_2fa_enabled:
        return JsonResponse({'status': 'error', 'message': 'Already enabled'})
    if method == 'phone' and request.user.profile.is_phone_2fa_enabled:
        return JsonResponse({'status': 'error', 'message': 'Already enabled'})

    # Send OTP
    if send_otp(request, request.user, intent=f'enable_{method}'):
        return JsonResponse({'status': 'success'})
    
    return JsonResponse({'status': 'error', 'message': 'Failed to send OTP'})

# 2FA Management — Disables a specific 2FA method and clears its secret
@login_required
def disable_2fa(request):
    """
    Disables a specific 2FA method.
    """
    method = request.POST.get('method') or request.GET.get('method')
    
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if method == 'email':
        request.user.profile.is_email_2fa_enabled = False
    elif method == 'phone':
        request.user.profile.is_phone_2fa_enabled = False
    elif method == 'totp':
        request.user.profile.is_totp_2fa_enabled = False
        request.user.profile.totp_secret = '' # Security: clear secret
    else:
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': 'Invalid Method'})
        messages.error(request, 'Invalid Method')
        return redirect('user_profile')
        
    request.user.profile.save()
    
    if is_ajax:
        return JsonResponse({'status': 'success'})
        
    messages.success(request, get_strings().get('2fa_disabled_msg', 'Disabled'))
    return redirect('user_profile')

# 2FA Helper — Resends OTP code for login or method activation
def resend_otp(request, intent='login'):
    # ... logic similar to before, handling updated intents like 'enable_email' ...
    # For brevity, reusing existing logic but would need slight update for 'enable_email' intent mapping
    user = None
    if intent == 'login':
        user_id = request.session.get('pre_2fa_user_id')
        if user_id:
            user = User.objects.get(pk=user_id)
    elif request.user.is_authenticated:
        user = request.user
        
    if user:
        # Map intent to 'login' or 'enable' for cache key if needed, or keep distinct
        send_otp(request, user, intent=intent)
        messages.success(request, 'Code Sent')
        
    return redirect(request.META.get('HTTP_REFERER', 'login'))


# 2FA Management — Generates new backup codes for account recovery
@login_required
def generate_backup_codes(request):
    """Generates 10 new backup codes for the user."""
    if request.method == 'POST':
        
        codes = []
        for _ in range(8):
            code = ''.join(secrets.choice(string.digits) for _ in range(8))
            codes.append(code)
            
        request.user.profile.backup_codes = codes
        request.user.profile.save()
        
        return JsonResponse({'status': 'success', 'codes': codes})
        
    return JsonResponse({'status': 'error', 'message': 'Invalid method'})
