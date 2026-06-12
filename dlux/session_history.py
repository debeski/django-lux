import hashlib
import secrets
from datetime import timedelta

from django.apps import apps
from django.core.signing import BadSignature
from django.utils import timezone

from .utils import get_client_ip


DEVICE_ID_COOKIE_NAME = 'dlux_device_id'
DEVICE_ID_COOKIE_SALT = 'dlux.device_identity'
DEVICE_ID_MAX_AGE = 365 * 24 * 60 * 60
PRESENCE_UPDATE_INTERVAL_SECONDS = 60
PRESENCE_MAX_DELTA_SECONDS = 15 * 60
OBSERVED_VALUE_LIMIT = 20


def hash_token(value):
    return hashlib.sha256(str(value or '').encode('utf-8')).hexdigest()


def hash_session_key(session_key):
    return hash_token(session_key)


# ── Force sign-out signalling ────────────────────────────────────────────────
# When a session is ended by someone/something other than its own browser (single
# active-session eviction, or a remote "sign out this device"), we can't push to the
# evicted browser — it only comes back on its next request carrying the now-dead session
# cookie. We leave a short-lived flag, keyed by the hashed session key, so that next
# request can show a "you were signed out" interstitial instead of a silent redirect.
SESSION_REVOKED_CACHE_PREFIX = 'dlux:session_revoked:'


def _session_revoked_ttl():
    from django.conf import settings
    try:
        return int(getattr(settings, 'SESSION_COOKIE_AGE', None) or 1209600)
    except (TypeError, ValueError):
        return 1209600


def flag_sessions_revoked(session_keys, reason='ended'):
    """Mark one or more *raw* session keys as force-revoked so the affected browsers get
    a 'signed out' interstitial on their next visit."""
    keys = [key for key in (session_keys or []) if key]
    if not keys:
        return
    try:
        from django.core.cache import cache
    except Exception:
        return
    ttl = _session_revoked_ttl()
    for key in keys:
        try:
            cache.set(SESSION_REVOKED_CACHE_PREFIX + hash_session_key(key), str(reason or 'ended'), ttl)
        except Exception:
            # Best-effort UX only — never let it block sign-out/eviction.
            pass


def get_session_revoked_reason(raw_session_key):
    if not raw_session_key:
        return None
    try:
        from django.core.cache import cache
        return cache.get(SESSION_REVOKED_CACHE_PREFIX + hash_session_key(raw_session_key))
    except Exception:
        return None


def clear_session_revoked_flag(raw_session_key):
    if not raw_session_key:
        return
    try:
        from django.core.cache import cache
        cache.delete(SESSION_REVOKED_CACHE_PREFIX + hash_session_key(raw_session_key))
    except Exception:
        pass


def _model(name):
    return apps.get_model('dlux', name)


def _append_observed(values, value, *, limit=OBSERVED_VALUE_LIMIT):
    observed = list(values or []) if isinstance(values, list) else []
    value = str(value or '').strip()
    if not value:
        return observed[:limit]
    observed = [item for item in observed if item != value]
    observed.insert(0, value)
    return observed[:limit]


def browser_name(user_agent):
    lowered = str(user_agent or '').lower()
    if 'edg/' in lowered or 'edge/' in lowered:
        return 'Edge'
    if 'firefox/' in lowered:
        return 'Firefox'
    if 'chrome/' in lowered or 'chromium/' in lowered:
        return 'Chrome'
    if 'safari/' in lowered:
        return 'Safari'
    return 'Browser' if lowered else ''


def os_name(user_agent):
    lowered = str(user_agent or '').lower()
    if 'android' in lowered:
        return 'Android'
    if 'iphone' in lowered or 'ipad' in lowered:
        return 'iOS'
    if 'windows' in lowered:
        return 'Windows'
    if 'mac os' in lowered or 'macintosh' in lowered:
        return 'macOS'
    if 'linux' in lowered:
        return 'Linux'
    return ''


def plain_device_label(user_agent):
    browser = browser_name(user_agent) or 'Browser'
    platform = os_name(user_agent) or 'Device'
    return f'{browser} on {platform}'


def _coerce_aware(value):
    if not value:
        return None
    if isinstance(value, timezone.datetime):
        parsed = value
    else:
        try:
            parsed = timezone.datetime.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def get_or_create_device_token(request):
    if not request:
        return '', False
    try:
        raw_token = request.get_signed_cookie(
            DEVICE_ID_COOKIE_NAME,
            salt=DEVICE_ID_COOKIE_SALT,
        )
    except (KeyError, BadSignature):
        raw_token = ''
    raw_token = str(raw_token or '').strip()
    if raw_token:
        return raw_token, False
    return secrets.token_urlsafe(32), True


def set_device_identity_cookie(response, raw_token, request=None):
    raw_token = str(raw_token or '').strip()
    if not response or not raw_token:
        return response
    response.set_signed_cookie(
        DEVICE_ID_COOKIE_NAME,
        raw_token,
        salt=DEVICE_ID_COOKIE_SALT,
        max_age=DEVICE_ID_MAX_AGE,
        httponly=True,
        secure=bool(request and request.is_secure()),
        samesite='Lax',
    )
    return response


def _sync_session_metadata(request, *, ip_address, user_agent, trusted_device=None, now=None):
    session = getattr(request, 'session', None)
    if session is None:
        return {}
    if not getattr(session, 'session_key', None):
        session.save()
    now = now or timezone.now()
    existing = session.get('dlux_device')
    if not isinstance(existing, dict):
        existing = {}
    metadata = {
        'user_agent': str(user_agent or existing.get('user_agent') or '')[:500],
        'ip_address': str(ip_address or existing.get('ip_address') or '').strip(),
        'first_seen': existing.get('first_seen') or now.isoformat(),
        'last_seen': now.isoformat(),
    }
    if trusted_device is not None:
        metadata['trusted_device_id'] = trusted_device.pk
        metadata['trusted_until'] = trusted_device.trusted_until.isoformat()
    elif existing.get('trusted_device_id'):
        metadata['trusted_device_id'] = existing.get('trusted_device_id')
        metadata['trusted_until'] = existing.get('trusted_until')
    session['dlux_device'] = metadata
    session.modified = True
    return metadata


def remember_request_presence(request, *, trusted_device=None, force=False):
    user = getattr(request, 'user', None)
    session = getattr(request, 'session', None)
    if not user or not getattr(user, 'is_authenticated', False) or session is None:
        return {}
    if not getattr(session, 'session_key', None):
        session.save()
    session_key = getattr(session, 'session_key', None)
    if not session_key:
        return {}

    now = timezone.now()
    existing = session.get('dlux_device')
    if not isinstance(existing, dict):
        existing = {}
    raw_token = getattr(request, '_dlux_device_identity_token', '')
    cookie_needs_set = bool(getattr(request, '_dlux_device_identity_cookie_needs_set', False))
    if not raw_token:
        raw_token, cookie_needs_set = get_or_create_device_token(request)
        request._dlux_device_identity_token = raw_token
        request._dlux_device_identity_cookie_needs_set = cookie_needs_set

    previous_seen = _coerce_aware(existing.get('last_seen'))
    if not force and previous_seen and (now - previous_seen).total_seconds() < PRESENCE_UPDATE_INTERVAL_SECONDS:
        return {
            'known_device': None,
            'presence_session': None,
            'device_token': raw_token,
            'device_cookie_needs_set': cookie_needs_set,
        }

    ip_address = str(get_client_ip(request) or '').strip()
    user_agent = str(getattr(request, 'META', {}).get('HTTP_USER_AGENT') or '').strip()[:500]
    metadata = _sync_session_metadata(
        request,
        ip_address=ip_address,
        user_agent=user_agent,
        trusted_device=trusted_device,
        now=now,
    )

    known_device = None
    presence_session = None
    device_hash = hash_token(raw_token)
    label = plain_device_label(user_agent)
    browser = browser_name(user_agent)
    platform = os_name(user_agent)

    try:
        KnownDevice = _model('UserKnownDevice')
        PresenceSession = _model('UserPresenceSession')
        known_device, _ = KnownDevice.objects.get_or_create(
            user=user,
            device_hash=device_hash,
            defaults={
                'device_label': label,
                'first_seen_at': now,
                'last_seen_at': now,
            },
        )
        known_device.device_label = label or known_device.device_label
        known_device.last_seen_at = now
        known_device.ip_addresses = _append_observed(known_device.ip_addresses, ip_address)
        known_device.user_agents = _append_observed(known_device.user_agents, user_agent, limit=8)
        known_device.browser_names = _append_observed(known_device.browser_names, browser, limit=8)
        known_device.os_names = _append_observed(known_device.os_names, platform, limit=8)
        if trusted_device is not None:
            known_device.trusted_device = trusted_device
        known_device.save(update_fields=[
            'device_label',
            'trusted_device',
            'ip_addresses',
            'user_agents',
            'browser_names',
            'os_names',
            'last_seen_at',
            'updated_at',
        ])

        session_hash = hash_session_key(session_key)
        presence_session, _ = PresenceSession.objects.get_or_create(
            user=user,
            session_key_hash=session_hash,
            defaults={
                'known_device': known_device,
                'device_label': label,
                'first_seen_at': now,
                'last_seen_at': now,
            },
        )
        delta = 0
        if presence_session.last_seen_at:
            delta = max(0, int((now - presence_session.last_seen_at).total_seconds()))
        presence_session.known_device = known_device
        presence_session.device_label = label or presence_session.device_label
        presence_session.last_seen_at = now
        presence_session.ended_at = None
        presence_session.ip_addresses = _append_observed(presence_session.ip_addresses, ip_address)
        presence_session.user_agents = _append_observed(presence_session.user_agents, user_agent, limit=8)
        presence_session.browser_names = _append_observed(presence_session.browser_names, browser, limit=8)
        presence_session.os_names = _append_observed(presence_session.os_names, platform, limit=8)
        presence_session.request_count = int(presence_session.request_count or 0) + 1
        if delta:
            presence_session.estimated_seconds = int(presence_session.estimated_seconds or 0) + min(delta, PRESENCE_MAX_DELTA_SECONDS)
        presence_session.save(update_fields=[
            'known_device',
            'device_label',
            'ip_addresses',
            'user_agents',
            'browser_names',
            'os_names',
            'last_seen_at',
            'estimated_seconds',
            'request_count',
            'ended_at',
            'updated_at',
        ])
    except Exception:
        # Presence history must never block auth, requests, or setup flows.
        pass

    return {
        'metadata': metadata,
        'known_device': known_device,
        'presence_session': presence_session,
        'device_token': raw_token,
        'device_cookie_needs_set': cookie_needs_set,
    }


def attach_presence_cookie(response, request):
    raw_token = getattr(request, '_dlux_device_identity_token', '')
    needs_set = bool(getattr(request, '_dlux_device_identity_cookie_needs_set', False))
    if needs_set and raw_token:
        set_device_identity_cookie(response, raw_token, request=request)
        request._dlux_device_identity_cookie_needs_set = False
    return response


def link_current_known_device_to_trusted_device(request, trusted_device):
    if trusted_device is None:
        return None
    result = remember_request_presence(request, trusted_device=trusted_device, force=True)
    known_device = result.get('known_device')
    if known_device is not None:
        try:
            trusted_device.session_key = getattr(getattr(request, 'session', None), 'session_key', '') or trusted_device.session_key
            trusted_device.device_label = known_device.device_label or trusted_device.device_label
            trusted_device.ip_address = (known_device.ip_addresses or [None])[0]
            trusted_device.user_agent = (known_device.user_agents or [''])[0]
            trusted_device.last_used_at = timezone.now()
            trusted_device.save(update_fields=['session_key', 'device_label', 'ip_address', 'user_agent', 'last_used_at'])
        except Exception:
            pass
    return known_device


def mark_presence_sessions_ended(session_keys, *, revoked=False):
    keys = [key for key in (session_keys or []) if key]
    if not keys:
        return 0
    now = timezone.now()
    hashes = [hash_session_key(key) for key in keys]
    updates = {'ended_at': now}
    if revoked:
        updates['revoked_at'] = now
    try:
        return _model('UserPresenceSession').objects.filter(session_key_hash__in=hashes).update(**updates)
    except Exception:
        return 0
