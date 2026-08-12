"""Notification endpoints.

Read and dismiss the caller's own notifications. Every query is bound to
``request.user`` — no path here reads another user's rows.
"""
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

@login_required
@never_cache
def notifications_list(request):
    from ..notifications import get_notification_context

    try:
        limit = int(request.GET.get('limit') or 20)
    except (TypeError, ValueError):
        limit = 20
    limit = max(1, min(limit, 50))
    context = get_notification_context(request, limit=limit)
    return JsonResponse({
        'enabled': context.get('enabled', False),
        'items': context.get('items', []),
        'unread_count': context.get('unread_count', 0),
        'unread_level': context.get('unread_level', ''),
        'section_counts': context.get('section_counts', {}),
    })

@login_required
@require_POST
def notification_mark_read(request, pk):
    from ..notifications import mark_notification_read, serialize_notification_state

    try:
        state = mark_notification_read(request.user, pk)
    except Exception:
        return JsonResponse({'success': False, 'error': 'Notification not found'}, status=404)
    return JsonResponse({'success': True, 'item': serialize_notification_state(state, request=request)})

@login_required
@require_POST
def notification_dismiss(request, pk):
    from ..notifications import NotificationLockedError, dismiss_notification

    try:
        dismiss_notification(request.user, pk)
    except NotificationLockedError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=409)
    except Exception:
        return JsonResponse({'success': False, 'error': 'Notification not found'}, status=404)
    return JsonResponse({'success': True})

@login_required
@require_POST
def notifications_mark_all_read(request):
    from ..notifications import mark_all_notifications_read

    count = mark_all_notifications_read(request.user)
    return JsonResponse({'success': True, 'updated': count, 'unread_count': 0})

@login_required
@require_POST
def notifications_clear_all(request):
    from ..notifications import clear_all_notifications

    count = clear_all_notifications(request.user)
    return JsonResponse({'success': True, 'updated': count, 'unread_count': 0})
