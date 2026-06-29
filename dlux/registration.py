import hashlib
import logging
import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.text import slugify

from .system.constants import REGISTRATION_ACTIVATION_AUTO_LOGIN
from .models import PublicRegistration
from .utils import build_config_groups, get_client_ip, get_email_service_status, get_system_config, send_dlux_mail


logger = logging.getLogger('dlux')

REGISTRATION_TOKEN_TTL_SECONDS = 24 * 60 * 60
REGISTRATION_THROTTLE_SECONDS = 60 * 60
REGISTRATION_IP_LIMIT = 10
REGISTRATION_EMAIL_LIMIT = 3


def normalize_registration_email(email):
    return str(email or '').strip().lower()


def public_registration_config():
    config = get_system_config()
    return {
        'enabled': bool(config.get('public_registration_enabled', False)),
        'activation_mode': config.get('registration_activation_mode') or REGISTRATION_ACTIVATION_AUTO_LOGIN,
        'throttle_enabled': bool(config.get('registration_throttle_enabled', True)),
        'honeypot_enabled': bool(config.get('honeypot_enabled', True)),
    }


def public_registration_available():
    config = public_registration_config()
    email_status = get_email_service_status()
    return bool(config['enabled'] and email_status.get('available'))


def _hashed_key(value):
    return hashlib.sha256(str(value).encode('utf-8')).hexdigest()


def _increment_throttle(key, timeout):
    count = cache.get(key, 0)
    if count:
        cache.incr(key)
        return count + 1
    cache.set(key, 1, timeout=timeout)
    return 1


def registration_throttle_allows(request, email):
    config = public_registration_config()
    if not config['throttle_enabled']:
        return True

    ip = get_client_ip(request) or 'unknown'
    email_key = _hashed_key(normalize_registration_email(email))
    ip_count = _increment_throttle(f'dlux:registration:ip:{ip}', REGISTRATION_THROTTLE_SECONDS)
    email_count = _increment_throttle(f'dlux:registration:email:{email_key}', REGISTRATION_THROTTLE_SECONDS)
    return ip_count <= REGISTRATION_IP_LIMIT and email_count <= REGISTRATION_EMAIL_LIMIT


def generate_registration_username(email):
    User = get_user_model()
    local_part = normalize_registration_email(email).split('@', 1)[0]
    base = slugify(local_part).replace('-', '_')[:24] or 'user'
    username = base
    while User._default_manager.filter(username__iexact=username).exists():
        username = f"{base}_{secrets.token_hex(3)}"
    return username


def existing_registration_email(email):
    User = get_user_model()
    normalized = normalize_registration_email(email)
    return User._default_manager.filter(email__iexact=normalized).exists()


def create_inactive_registration_user(form, request):
    config = public_registration_config()
    email = normalize_registration_email(form.cleaned_data['email'])
    User = get_user_model()
    user = User(
        username=generate_registration_username(email),
        email=email,
        first_name=form.cleaned_data.get('first_name', ''),
        last_name=form.cleaned_data.get('last_name', ''),
        is_active=False,
    )
    user.set_password(form.cleaned_data['password1'])
    user._dlux_public_registration = True
    user.save()
    registration, token = PublicRegistration.create_for_user(
        user=user,
        email=email,
        activation_mode=config['activation_mode'],
        ip_address=get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        ttl_seconds=getattr(settings, 'DLUX_REGISTRATION_TOKEN_TTL_SECONDS', REGISTRATION_TOKEN_TTL_SECONDS),
    )
    return registration, token


def send_registration_verification_email(request, registration, token):
    verify_url = request.build_absolute_uri(reverse('register_verify', args=[token]))
    subject = "Verify your account"
    system_config = get_system_config()
    identity = build_config_groups(system_config).get('identity', {})
    context = {
        'registration': registration,
        'verify_url': verify_url,
        'system_name': identity.get('display_name') or 'DjangoLux',
    }
    text_body = render_to_string('registration/email/verify_registration.txt', context)
    try:
        send_dlux_mail(
            subject,
            text_body,
            [registration.email],
            fail_silently=False,
        )
    except Exception:
        logger.exception("Public registration verification email failed for registration id %s", registration.pk)
        return False
    return True
