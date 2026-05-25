import hashlib
import secrets
from datetime import timedelta

from django.apps import apps
from django.contrib.sessions.models import Session
from django.core.signing import BadSignature
from django.db.models import Q
from django.utils import timezone

from .translations import get_strings
from .utils import get_system_config
from .session_history import (
    attach_presence_cookie,
    link_current_known_device_to_trusted_device,
    mark_presence_sessions_ended,
    remember_request_presence,
)


TRUSTED_DEVICE_COOKIE_NAME = 'microsys_trusted_device'
TRUSTED_DEVICE_COOKIE_SALT = 'microsys.trusted_device'
TRUSTED_DEVICE_MAX_AGE = 30 * 24 * 60 * 60


def trusted_device_model():
    return apps.get_model('microsys', 'TrustedDevice')


def trusted_device_token_hash(raw_token):
    return hashlib.sha256(str(raw_token or '').encode('utf-8')).hexdigest()


def device_label(user_agent):
    s = get_strings()
    user_agent = str(user_agent or '').strip()
    lowered = user_agent.lower()
    if not user_agent:
        return s.get('device_unknown')
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
        platform = s.get('device_platform_generic')
    return s.get('device_label_pattern').format(browser=browser, platform=platform)


def get_trusted_device_for_login(request, user):
    if not request or not user:
        return None
    try:
        raw_token = request.get_signed_cookie(
            TRUSTED_DEVICE_COOKIE_NAME,
            salt=TRUSTED_DEVICE_COOKIE_SALT,
        )
    except (KeyError, BadSignature):
        return None
    if not raw_token:
        return None
    return trusted_device_model().objects.filter(
        user=user,
        token_hash=trusted_device_token_hash(raw_token),
        revoked_at__isnull=True,
        trusted_until__gt=timezone.now(),
    ).first()


def sync_session_device_metadata(request, trusted_device=None):
    result = remember_request_presence(request, trusted_device=trusted_device, force=True)
    metadata = result.get('metadata') or {}
    if trusted_device is not None:
        link_current_known_device_to_trusted_device(request, trusted_device)
    return metadata


def trusted_device_for_session(user, session_key, session_data=None):
    if not user or not session_key:
        return None
    now = timezone.now()
    metadata = {}
    if isinstance(session_data, dict):
        metadata = session_data.get('microsys_device') if isinstance(session_data.get('microsys_device'), dict) else {}
    devices = trusted_device_model().objects.filter(
        user=user,
        revoked_at__isnull=True,
        trusted_until__gt=now,
    )
    trusted_device_id = metadata.get('trusted_device_id')
    if trusted_device_id is not None:
        try:
            by_id = devices.filter(pk=int(trusted_device_id)).first()
        except (TypeError, ValueError):
            by_id = None
        if by_id is not None:
            return by_id
    return devices.filter(session_key=session_key).first()


def current_session_trusted_device(request):
    user = getattr(request, 'user', None)
    if not user or not getattr(user, 'is_authenticated', False):
        return None
    session = getattr(request, 'session', None)
    if session is None:
        return None
    return trusted_device_for_session(user, getattr(session, 'session_key', None), dict(session.items()))


def revoke_linked_session_trust(user, session_keys, trusted_device_ids=None, exclude_trusted_device_id=None):
    session_keys = [key for key in (session_keys or []) if key]
    trusted_device_ids = [pk for pk in (trusted_device_ids or []) if pk]
    devices = trusted_device_model().objects.filter(user=user, revoked_at__isnull=True)
    if exclude_trusted_device_id:
        devices = devices.exclude(pk=exclude_trusted_device_id)
    criteria = Q()
    if trusted_device_ids and session_keys:
        criteria = Q(pk__in=trusted_device_ids) | Q(session_key__in=session_keys)
    elif trusted_device_ids:
        criteria = Q(pk__in=trusted_device_ids)
    elif session_keys:
        criteria = Q(session_key__in=session_keys)
    else:
        return 0
    return devices.filter(criteria).update(revoked_at=timezone.now())


def revoke_other_user_sessions(user, keep_session_key=None, keep_trusted_device_id=None):
    now = timezone.now()
    target_keys = []
    trusted_ids = []
    user_id = str(user.pk)
    for session in Session.objects.filter(expire_date__gt=now):
        if keep_session_key and session.session_key == keep_session_key:
            continue
        try:
            data = session.get_decoded()
        except Exception:
            continue
        if str(data.get('_auth_user_id') or '') != user_id:
            continue
        target_keys.append(session.session_key)
        metadata = data.get('microsys_device') if isinstance(data.get('microsys_device'), dict) else {}
        trusted_device_id = metadata.get('trusted_device_id')
        if trusted_device_id is not None:
            try:
                trusted_ids.append(int(trusted_device_id))
            except (TypeError, ValueError):
                pass
    if target_keys:
        Session.objects.filter(session_key__in=target_keys).delete()
        mark_presence_sessions_ended(target_keys, revoked=True)
    revoke_linked_session_trust(
        user,
        target_keys,
        trusted_device_ids=trusted_ids,
        exclude_trusted_device_id=keep_trusted_device_id,
    )
    return len(target_keys)


def enforce_single_active_trusted_session(request, user, trusted_device):
    if not trusted_device:
        return 0
    if not bool(get_system_config().get('prevent_multiple_active_sessions', False)):
        return 0
    return revoke_other_user_sessions(
        user,
        keep_session_key=getattr(getattr(request, 'session', None), 'session_key', None),
        keep_trusted_device_id=trusted_device.pk,
    )


def issue_trusted_device(request, response, user):
    raw_token = secrets.token_urlsafe(32)
    trusted_device = trusted_device_model().objects.create(
        user=user,
        token_hash=trusted_device_token_hash(raw_token),
        trusted_until=timezone.now() + timedelta(days=30),
    )
    sync_session_device_metadata(request, trusted_device=trusted_device)
    link_current_known_device_to_trusted_device(request, trusted_device)
    response.set_signed_cookie(
        TRUSTED_DEVICE_COOKIE_NAME,
        raw_token,
        salt=TRUSTED_DEVICE_COOKIE_SALT,
        max_age=TRUSTED_DEVICE_MAX_AGE,
        httponly=True,
        secure=request.is_secure(),
        samesite='Lax',
    )
    attach_presence_cookie(response, request)
    enforce_single_active_trusted_session(request, user, trusted_device)
    return trusted_device
