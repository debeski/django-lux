"""Dlux notification pipeline.

Public usage:
    from dlux.notifications import notify
    notify.success("Saved.")
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, field

from django.apps import apps
from django.contrib.messages import get_messages
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models import Q
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from .middleware import get_current_request, get_current_user
from .system.normalizers import normalize_notification_config


FLASH_SESSION_KEY = '_dlux_notification_flash_queue'
VALID_LEVELS = {'info', 'success', 'warning', 'error'}
BOOTSTRAP_LEVELS = {
    'info': 'info',
    'success': 'success',
    'warning': 'warning',
    'error': 'danger',
}


class NotificationLockedError(ValueError):
    """Raised when an active lifecycle notification cannot be dismissed."""


@dataclass
class NotificationEvent:
    message: str
    level: str = 'info'
    title: str = ''
    category: str = 'general'
    source: str = 'manual'
    action: str = ''
    obj: object | None = None
    request: object | None = None
    user: object | None = None
    scope: object | None = None
    target_url: str = ''
    request_path: str = ''
    metadata: dict = field(default_factory=dict)
    to: object | None = None
    recipients: object | None = None
    flash: bool | None = None
    persist: bool | None = None
    email: bool | None = None
    audience_type: str = ''
    expires_at: object | None = None


def _normalize_level(level):
    normalized = str(level or 'info').strip().lower()
    if normalized == 'danger':
        normalized = 'error'
    return normalized if normalized in VALID_LEVELS else 'info'


def _safe_user(user=None, request=None):
    candidate = user or get_current_user() or getattr(request, 'user', None)
    if candidate and getattr(candidate, 'is_authenticated', False):
        return candidate
    return None


def _safe_request(request=None):
    return request or get_current_request()


def _get_config():
    try:
        from .utils import get_system_config

        config = get_system_config()
    except Exception:
        config = {}
    return normalize_notification_config(
        config.get('notifications', config.get('notification_config', {}))
        if isinstance(config, dict)
        else {}
    )


def _get_user_scope(user):
    if not user:
        return None
    try:
        from .utils import get_user_scope

        return get_user_scope(user)
    except Exception:
        profile = getattr(user, 'profile', None)
        return getattr(profile, 'scope', None)


def _infer_scope(scope=None, obj=None, user=None):
    if scope is not None:
        return scope
    obj_scope = getattr(obj, 'scope', None)
    if obj_scope is not None:
        return obj_scope
    return _get_user_scope(user)


def _obj_metadata(obj):
    if obj is None:
        return {}
    meta = getattr(obj, '_meta', None)
    if not meta:
        return {'source_label': str(obj)}
    try:
        pk = getattr(obj, 'pk', '')
    except Exception:
        pk = ''
    return {
        'source_model': str(meta.verbose_name),
        'source_model_key': meta.label_lower,
        'source_object_id': str(pk or ''),
        'source_label': str(obj),
    }


def _default_target_url(request):
    if request is None:
        return ''
    try:
        return request.get_full_path()
    except Exception:
        return getattr(request, 'path', '') or ''


def _expiry_from_config(config):
    days = int(config.get('retention', {}).get('default_expiry_days') or 0)
    if days <= 0:
        return None
    return timezone.now() + timezone.timedelta(days=days)


def _json_cache_key(payload):
    try:
        raw = json.dumps(payload, sort_keys=True, default=str)
    except TypeError:
        raw = str(payload)
    return hashlib.sha1(raw.encode('utf-8')).hexdigest()


def _translated_string(key, fallback='', request=None):
    key = str(key or '').strip()
    if not key:
        return fallback
    try:
        from .translations import get_current_language_code, get_strings

        strings = get_strings(get_current_language_code(request))
        return strings.get(key, fallback or key)
    except Exception:
        return fallback or key


def _translation_key_for_text(text):
    try:
        from .translations import resolve_translation_key_for_text

        return resolve_translation_key_for_text(text)
    except Exception:
        return ''


def _localized_metadata_value(metadata, field, fallback='', request=None):
    if not isinstance(metadata, dict):
        metadata = {}
    key = metadata.get(f'{field}_key')
    if field == 'message' and not key:
        key = metadata.get('translation_key')
    if not key:
        key = _translation_key_for_text(fallback)
    return _translated_string(key, fallback, request=request) if key else fallback


def _should_dedupe(event):
    actor_id = getattr(event.user, 'pk', None)
    obj_meta = _obj_metadata(event.obj)
    key = _json_cache_key({
        'actor': actor_id,
        'level': event.level,
        'source': event.source,
        'action': event.action,
        'model': obj_meta.get('source_model_key', ''),
        'object': obj_meta.get('source_object_id', ''),
        'message': event.message,
        'metadata': event.metadata,
    })
    cache_key = f'dlux:notification:dedupe:{key}'
    if cache.get(cache_key):
        return True
    cache.set(cache_key, True, timeout=2)
    return False


def _coerce_user_list(value):
    User = get_user_model()
    if value is None:
        return []
    if isinstance(value, str):
        return []
    if not isinstance(value, Iterable):
        value = [value]
    users = []
    user_ids = []
    for item in value:
        if not item:
            continue
        if getattr(item, 'is_authenticated', False):
            users.append(item)
        else:
            try:
                user_ids.append(int(item))
            except (TypeError, ValueError):
                continue
    if user_ids:
        users.extend(User.objects.filter(pk__in=user_ids, is_active=True))
    seen = set()
    unique = []
    for user in users:
        pk = getattr(user, 'pk', None)
        if pk and pk not in seen:
            seen.add(pk)
            unique.append(user)
    return unique


def _watcher_users(model_key, scope=None, *, email_only=False):
    if not model_key:
        return []
    DluxNotificationWatch = apps.get_model('dlux', 'DluxNotificationWatch')
    qs = DluxNotificationWatch.objects.filter(enabled=True, model_key=model_key)
    if scope is not None:
        qs = qs.filter(Q(scope__isnull=True) | Q(scope=scope))
    else:
        qs = qs.filter(scope__isnull=True)
    if email_only:
        qs = qs.filter(email_enabled=True)
    return [watch.user for watch in qs.select_related('user') if getattr(watch.user, 'is_active', False)]


def _staff_users(scope=None):
    User = get_user_model()
    qs = User.objects.filter(is_active=True, is_staff=True)
    if scope is not None:
        try:
            qs = qs.filter(Q(profile__scope=scope) | Q(is_superuser=True)).distinct()
        except Exception:
            pass
    return list(qs)


def _broadcast_users(scope=None):
    User = get_user_model()
    qs = User.objects.filter(is_active=True)
    if scope is not None:
        try:
            qs = qs.filter(Q(profile__scope=scope) | Q(is_superuser=True)).distinct()
        except Exception:
            pass
    return list(qs)


def _rule_value_matches(expected, actual):
    if expected in (None, '', [], ()):
        return True
    if isinstance(expected, (list, tuple, set)):
        return str(actual or '') in {str(item) for item in expected}
    return str(expected) == str(actual or '')


def _rule_matches(rule, event, obj_meta):
    match = rule.match_config if isinstance(rule.match_config, dict) else {}
    checks = {
        'level': event.level,
        'category': event.category,
        'source': event.source,
        'action': event.action,
        'model': obj_meta.get('source_model_key', ''),
        'source_model_key': obj_meta.get('source_model_key', ''),
    }
    for key, actual in checks.items():
        if key in match and not _rule_value_matches(match.get(key), actual):
            return False
    return True


def _base_delivery(event, config):
    automatic = config.get('automatic', {})
    action = str(event.action or '').lower()
    is_auto = event.source in {'scoped_model', 'generic_crud', 'context_menu'}
    actor_flash_actions = set(automatic.get('actor_flash_actions') or [])
    explicit_audience = bool(event.recipients)
    if isinstance(event.to, str):
        explicit_audience = explicit_audience or event.to.strip().lower() in {'watchers', 'staff', 'broadcast', 'users'}
    elif isinstance(event.to, (list, tuple, set)):
        explicit_audience = explicit_audience or bool(event.to)
    if event.persist is None:
        persist = bool(event.user or explicit_audience)
    else:
        persist = bool(event.persist)
    if event.flash is None:
        flash = bool(
            event.level in {'error', 'warning'}
            or not is_auto
            or action in actor_flash_actions
        )
    else:
        flash = bool(event.flash)
    if event.email is None:
        email = bool(config.get('email', {}).get('default', False))
    else:
        email = bool(event.email)
    return {
        'persist': persist,
        'flash': flash,
        'badge': True,
        'email': email,
        'to': event.to,
        'recipients': event.recipients,
        'audience_type': event.audience_type or '',
        'expires_at': event.expires_at,
    }


def _apply_rules(event, config, scope, obj_meta):
    delivery = _base_delivery(event, config)
    DluxNotificationRule = apps.get_model('dlux', 'DluxNotificationRule')
    rules = DluxNotificationRule.objects.filter(enabled=True)
    if scope is not None:
        rules = rules.filter(Q(scope__isnull=True) | Q(scope=scope))
    else:
        rules = rules.filter(scope__isnull=True)
    for rule in rules.order_by('priority', 'name'):
        if not _rule_matches(rule, event, obj_meta):
            continue
        rule_delivery = rule.delivery_config if isinstance(rule.delivery_config, dict) else {}
        for key in ('persist', 'flash', 'badge', 'email'):
            if key in rule_delivery:
                delivery[key] = bool(rule_delivery.get(key))
        for key in ('to', 'recipients', 'audience_type', 'expires_at'):
            if key in rule_delivery:
                delivery[key] = rule_delivery.get(key)
        expiry_days = rule_delivery.get('expiry_days')
        if expiry_days is not None:
            try:
                days = int(expiry_days)
            except (TypeError, ValueError):
                days = 0
            delivery['expires_at'] = timezone.now() + timezone.timedelta(days=days) if days > 0 else None
        if rule.stop_processing:
            break
    return delivery


def _resolve_recipients(event, delivery, scope, obj_meta):
    recipients = []
    explicit = _coerce_user_list(delivery.get('recipients'))
    if explicit:
        recipients.extend(explicit)

    to_value = delivery.get('to')
    if to_value is None:
        to_value = 'actor+watchers' if event.source in {'scoped_model', 'generic_crud', 'context_menu'} else 'actor'
    if isinstance(to_value, str):
        tokens = {token.strip().lower() for token in to_value.replace(',', '+').split('+') if token.strip()}
    elif isinstance(to_value, (list, tuple, set)):
        tokens = {str(token).strip().lower() for token in to_value if str(token).strip()}
    else:
        tokens = set()

    actor = event.user
    if 'actor' in tokens and actor:
        recipients.append(actor)
    if 'watchers' in tokens:
        recipients.extend(_watcher_users(obj_meta.get('source_model_key'), scope))
    if 'staff' in tokens:
        recipients.extend(_staff_users(scope))
    if 'broadcast' in tokens or delivery.get('audience_type') == 'broadcast':
        recipients.extend(_broadcast_users(scope))

    seen = set()
    unique = []
    for user in recipients:
        pk = getattr(user, 'pk', None)
        if pk and getattr(user, 'is_active', True) and pk not in seen:
            seen.add(pk)
            unique.append(user)
    return unique


def _flash_payload(event, obj_meta, notification=None):
    metadata = event.metadata if isinstance(event.metadata, dict) else {}
    return {
        'id': getattr(notification, 'pk', None),
        'title': event.title,
        'message': event.message,
        'title_key': metadata.get('title_key', ''),
        'message_key': metadata.get('message_key', metadata.get('translation_key', '')),
        'level': event.level,
        'tags': BOOTSTRAP_LEVELS.get(event.level, 'info'),
        'category': event.category,
        'source': event.source,
        'action': event.action,
        'source_model': obj_meta.get('source_model', ''),
        'source_model_key': obj_meta.get('source_model_key', ''),
        'source_object_id': obj_meta.get('source_object_id', ''),
        'source_label': obj_meta.get('source_label', ''),
        'target_url': event.target_url,
    }


def queue_flash_notification(request, payload):
    if request is None or not hasattr(request, 'session'):
        return
    queue = request.session.get(FLASH_SESSION_KEY, [])
    if not isinstance(queue, list):
        queue = []
    queue.append(dict(payload or {}))
    request.session[FLASH_SESSION_KEY] = queue[-20:]
    request.session.modified = True


def get_flash_notifications(request):
    """Drain Dlux flash notices and, if enabled, legacy Django messages."""
    config = _get_config()
    if not config.get('enabled', True):
        return []
    items = []
    if request is not None and hasattr(request, 'session'):
        queued = request.session.pop(FLASH_SESSION_KEY, [])
        if isinstance(queued, list):
            items.extend(queued)
        request.session.modified = True

    if config.get('bridge', {}).get('django_messages_enabled', False) and request is not None:
        try:
            for message in get_messages(request):
                tag = str(getattr(message, 'tags', '') or 'info').split()[0] or 'info'
                level = 'error' if tag in {'error', 'danger'} else tag
                if level not in VALID_LEVELS:
                    level = 'info'
                items.append({
                    'message': str(message),
                    'level': level,
                    'tags': BOOTSTRAP_LEVELS.get(level, tag),
                    'source': 'django_messages',
                    'category': 'legacy',
                })
        except Exception:
            pass

    max_visible = config.get('flash', {}).get('max_visible', 3)
    localized = []
    for item in items[:max_visible]:
        if not isinstance(item, dict):
            continue
        payload = dict(item)
        payload['title'] = _localized_metadata_value(payload, 'title', payload.get('title', ''), request=request)
        payload['message'] = _localized_metadata_value(payload, 'message', payload.get('message', ''), request=request)
        localized.append(payload)
    return localized


def _create_notification(event, scope, obj_meta, delivery, config):
    DluxNotification = apps.get_model('dlux', 'DluxNotification')
    expires_at = delivery.get('expires_at') or _expiry_from_config(config)
    notification = DluxNotification.objects.create(
        title=event.title[:180],
        message=event.message,
        level=event.level,
        category=event.category or 'general',
        source=event.source or 'manual',
        action=(event.action or '')[:64],
        source_model=obj_meta.get('source_model', '')[:120],
        source_model_key=obj_meta.get('source_model_key', '')[:120],
        source_object_id=obj_meta.get('source_object_id', '')[:64],
        source_label=obj_meta.get('source_label', '')[:255],
        target_url=(event.target_url or '')[:512],
        request_path=(event.request_path or '')[:512],
        audience_type=(delivery.get('audience_type') or event.audience_type or 'actor')[:24],
        metadata=event.metadata if isinstance(event.metadata, dict) else {},
        scope=scope,
        expires_at=expires_at,
        created_by=event.user,
        updated_by=event.user,
    )
    return notification


def _create_states(notification, recipients):
    DluxNotificationState = apps.get_model('dlux', 'DluxNotificationState')
    states = []
    for user in recipients:
        state, _created = DluxNotificationState.objects.get_or_create(
            notification=notification,
            user=user,
        )
        states.append(state)
    return states


def _send_notification_email(notification, states):
    if not states:
        return
    try:
        from .utils import get_email_service_status, send_dlux_mail

        if not get_email_service_status().get('available'):
            return
        recipients = [
            state.user.email
            for state in states
            if getattr(state.user, 'email', '')
        ]
        if not recipients:
            return
        subject = notification.title or notification.message[:80]
        body = notification.message
        send_dlux_mail(subject, body, recipients, fail_silently=True)
        now = timezone.now()
        for state in states:
            state.emailed_at = now
            state.email_status = 'sent'
            state.save(update_fields=['emailed_at', 'email_status', 'updated_at'])
    except Exception as exc:
        for state in states:
            state.email_status = 'failed'
            state.email_error = str(exc)[:2000]
            state.save(update_fields=['email_status', 'email_error', 'updated_at'])


def emit_notification_event(event):
    """Internal pipeline entrypoint. Accepts a dict or NotificationEvent."""
    if isinstance(event, dict):
        event = NotificationEvent(**event)
    if not isinstance(event, NotificationEvent):
        raise TypeError("emit_notification_event() expects a NotificationEvent or dict.")

    event.message = str(event.message or '').strip()
    if not event.message:
        return None
    if not _get_config().get('enabled', True):
        return None
    event.level = _normalize_level(event.level)
    event.request = _safe_request(event.request)
    event.user = _safe_user(event.user, event.request)
    event.scope = _infer_scope(event.scope, event.obj, event.user)
    if not event.target_url:
        event.target_url = _default_target_url(event.request)
    if not event.request_path and event.request is not None:
        event.request_path = getattr(event.request, 'path', '') or ''
    event.metadata = event.metadata if isinstance(event.metadata, dict) else {}

    if _should_dedupe(event):
        return None

    config = _get_config()
    obj_meta = _obj_metadata(event.obj)
    try:
        delivery = _apply_rules(event, config, event.scope, obj_meta)
        recipients = _resolve_recipients(event, delivery, event.scope, obj_meta)
    except Exception:
        if event.flash is not False and config.get('flash', {}).get('enabled', True):
            queue_flash_notification(event.request, _flash_payload(event, obj_meta, None))
        return None

    notification = None
    states = []
    should_persist = bool(delivery.get('persist') or delivery.get('email'))
    if should_persist:
        try:
            notification = _create_notification(event, event.scope, obj_meta, delivery, config)
            if recipients:
                states = _create_states(notification, recipients)
        except Exception:
            notification = None
            states = []

    if delivery.get('flash') and config.get('flash', {}).get('enabled', True):
        queue_flash_notification(event.request, _flash_payload(event, obj_meta, notification))

    if delivery.get('email') and config.get('email', {}).get('enabled', False):
        _send_notification_email(notification, states)

    return notification


def _notify(
    message='',
    *,
    level='info',
    obj=None,
    action=None,
    category='general',
    request=None,
    user=None,
    scope=None,
    target_url=None,
    metadata=None,
    title='',
    message_key='',
    title_key='',
    to=None,
    recipients=None,
    flash=None,
    persist=None,
    email=None,
    audience_type='',
    expires_at=None,
    source='manual',
    **options,
):
    metadata = dict(metadata or {})
    if message_key:
        metadata.setdefault('message_key', message_key)
        if not message:
            message = _translated_string(message_key, message_key, request=request)
    if title_key:
        metadata.setdefault('title_key', title_key)
        if not title:
            title = _translated_string(title_key, title_key, request=request)
    if options:
        metadata = {**metadata, **options}
    event = NotificationEvent(
        message=message,
        level=level,
        title=title or '',
        category=category or 'general',
        source=source or 'manual',
        action=action or '',
        obj=obj,
        request=request,
        user=user,
        scope=scope,
        target_url=target_url or '',
        metadata=metadata,
        to=to,
        recipients=recipients,
        flash=flash,
        persist=persist,
        email=email,
        audience_type=audience_type,
        expires_at=expires_at,
    )
    return emit_notification_event(event)


def _level_helper(level):
    def helper(message='', **kwargs):
        return _notify(message, level=level, **kwargs)

    return helper


class _NotifyProxy:
    def __call__(self, message='', **kwargs):
        return _notify(message, **kwargs)

    info = staticmethod(_level_helper('info'))
    success = staticmethod(_level_helper('success'))
    warning = staticmethod(_level_helper('warning'))
    error = staticmethod(_level_helper('error'))


notify = _NotifyProxy()


def _model_notification_policy(model):
    policy = getattr(model, 'dlux_notify', None)
    if policy is False:
        return None
    config = _get_config()
    automatic = dict(config.get('automatic', {}))
    if isinstance(policy, dict):
        automatic.update(policy)
    return automatic


def _model_flash_override(policy, action):
    flash_actions = policy.get('flash')
    if isinstance(flash_actions, (list, tuple, set)):
        return action in {str(item).lower() for item in flash_actions}
    if isinstance(flash_actions, bool):
        return flash_actions
    return None


def _update_summary(details):
    if not isinstance(details, dict) or not details:
        return ''
    names = [str(name) for name in details.keys() if str(name)]
    if not names:
        return ''
    if len(names) <= 3:
        return ', '.join(names)
    return ', '.join(names[:3]) + f" +{len(names) - 3}"


def _crud_message(instance, action, details=None):
    model_label = str(getattr(instance._meta, 'verbose_name', instance.__class__.__name__))
    object_label = str(instance)
    if action == 'create':
        return f"Created {model_label}: {object_label}"
    if action == 'delete':
        return f"Deleted {model_label}: {object_label}"
    summary = _update_summary(details)
    if summary:
        return f"Updated {model_label}: {object_label} ({summary})"
    return f"Updated {model_label}: {object_label}"


def notify_model_event(instance, action, *, details=None, activity_log=None, request=None, user=None):
    """Emit an automatic notification for a model CRUD event."""
    if instance is None:
        return None
    action = str(action or '').strip().lower()
    if action not in {'create', 'update', 'delete'}:
        return None

    policy = _model_notification_policy(instance.__class__)
    if not policy or not policy.get('scoped_model_crud', True):
        return None
    if action == 'create' and not policy.get('create', True):
        return None
    if action == 'delete' and not policy.get('delete', True):
        return None
    if action == 'update':
        update_mode = policy.get('update', 'summary')
        if update_mode == 'off':
            return None
        if update_mode == 'summary' and not details:
            return None

    obj_meta = _obj_metadata(instance)
    metadata = {
        'model_key': obj_meta.get('source_model_key', ''),
        'object_id': obj_meta.get('source_object_id', ''),
        'activity_log_id': getattr(activity_log, 'pk', None),
        'details': details or {},
        'route': getattr(instance, '_dlux_notify_route', ''),
        'surface': getattr(instance, '_dlux_notify_surface', ''),
    }
    explicit_flash = getattr(instance, '_dlux_notify_flash', None)
    flash_override = bool(explicit_flash) if explicit_flash is not None else _model_flash_override(policy, action)
    return _notify(
        _crud_message(instance, action, details=details),
        level='success' if action in {'create', 'delete'} else 'info',
        obj=instance,
        action=action,
        category='crud',
        source=getattr(instance, '_dlux_notify_source', '') or 'scoped_model',
        request=request,
        user=user,
        metadata=metadata,
        to='actor+watchers' if policy.get('watchable', True) else 'actor',
        flash=flash_override,
    )


def serialize_notification_state(state, request=None):
    notification = state.notification
    metadata = notification.metadata or {}
    return {
        'id': notification.pk,
        'state_id': state.pk,
        'title': _localized_metadata_value(metadata, 'title', notification.title, request=request),
        'message': _localized_metadata_value(metadata, 'message', notification.message, request=request),
        'level': notification.level,
        'tags': BOOTSTRAP_LEVELS.get(notification.level, 'info'),
        'category': notification.category,
        'source': notification.source,
        'action': notification.action,
        'source_model': notification.source_model,
        'source_model_key': notification.source_model_key,
        'source_object_id': notification.source_object_id,
        'source_label': notification.source_label,
        'target_url': notification.target_url,
        'metadata': metadata,
        'created_at': notification.created_at.isoformat() if notification.created_at else '',
        'read': bool(state.read_at),
        'dismissed': bool(state.dismissed_at),
        'read_at': state.read_at.isoformat() if state.read_at else '',
    }


def get_notification_context(request, limit=None):
    user = getattr(request, 'user', None)
    config = _get_config()
    if not (user and getattr(user, 'is_authenticated', False)):
        return {
            'enabled': False,
            'items': [],
            'unread_count': 0,
            'unread_level': '',
            'config': config,
        }
    if not config.get('enabled', True):
        return {
            'enabled': False,
            'items': [],
            'unread_count': 0,
            'unread_level': '',
            'config': config,
        }
    if not config.get('drawer', {}).get('enabled', True):
        return {
            'enabled': False,
            'items': [],
            'unread_count': 0,
            'unread_level': '',
            'config': config,
        }
    DluxNotificationState = apps.get_model('dlux', 'DluxNotificationState')
    now = timezone.now()
    qs = DluxNotificationState.objects.select_related('notification').filter(
        user=user,
        dismissed_at__isnull=True,
    ).filter(
        Q(notification__expires_at__isnull=True) | Q(notification__expires_at__gt=now)
    ).order_by('-notification__created_at')
    unread_qs = qs.filter(read_at__isnull=True)
    unread_count = unread_qs.count()
    unread_level = ''
    latest_unread = unread_qs.first()
    if latest_unread:
        unread_level = latest_unread.notification.level
    if limit is None:
        limit = config.get('drawer', {}).get('preview_limit', 8)
    return {
        'enabled': True,
        'items': [serialize_notification_state(state, request=request) for state in qs[:limit]],
        'unread_count': unread_count,
        'unread_level': unread_level,
        'config': config,
    }


def mark_notification_read(user, notification_id):
    DluxNotificationState = apps.get_model('dlux', 'DluxNotificationState')
    state = DluxNotificationState.objects.select_related('notification').get(
        notification_id=notification_id,
        user=user,
    )
    if not state.read_at:
        state.read_at = timezone.now()
        state.save(update_fields=['read_at', 'updated_at'])
    return state


def dismiss_notification(user, notification_id):
    DluxNotificationState = apps.get_model('dlux', 'DluxNotificationState')
    state = DluxNotificationState.objects.select_related('notification').get(
        notification_id=notification_id,
        user=user,
    )
    if bool((state.notification.metadata or {}).get('locked')):
        raise NotificationLockedError('Active notification cannot be dismissed.')
    now = timezone.now()
    update_fields = ['dismissed_at', 'updated_at']
    state.dismissed_at = now
    if not state.read_at:
        state.read_at = now
        update_fields.append('read_at')
    state.save(update_fields=update_fields)
    return state


def mark_all_notifications_read(user):
    DluxNotificationState = apps.get_model('dlux', 'DluxNotificationState')
    now = timezone.now()
    return DluxNotificationState.objects.filter(
        user=user,
        read_at__isnull=True,
        dismissed_at__isnull=True,
    ).update(read_at=now, updated_at=now)


def clear_all_notifications(user):
    """Dismiss read notification states for a user, leaving unread items visible."""
    DluxNotificationState = apps.get_model('dlux', 'DluxNotificationState')
    now = timezone.now()
    candidates = DluxNotificationState.objects.select_related('notification').filter(
        user=user,
        dismissed_at__isnull=True,
        read_at__isnull=False,
    )
    dismissible_ids = [
        state.pk
        for state in candidates
        if not bool((state.notification.metadata or {}).get('locked'))
    ]
    return DluxNotificationState.objects.filter(pk__in=dismissible_ids).update(
        read_at=now,
        dismissed_at=now,
        updated_at=now,
    )


def notification_detail_url(notification):
    try:
        return reverse('notifications_list') + f'?id={notification.pk}'
    except NoReverseMatch:
        return ''
