"""Authenticated, CSRF-protected personal table settings; never reads model rows."""

import json

from django.contrib.auth.decorators import login_required
from django.core import signing
from django.db import transaction
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.views.decorators.http import require_http_methods

from .preferences import _coerce_prefs_dict, _prefs_within_cap
from ..translations import get_strings
from ..utils import get_system_config, user_matches_permission_token
from ..utils.user_table_columns import (
    PREFERENCE_KEY, TOKEN_MAX_AGE, TOKEN_SALT, available_columns, personal_overlay,
)


@login_required
@require_http_methods(['GET', 'POST'])
def user_table_columns(request):
    strings = get_strings()
    if not user_matches_permission_token(request.user, '__dlux_authenticated__'):
        return JsonResponse({'success': False}, status=403)
    try:
        size = len(request.body) if request.content_type == 'application/json' else int(request.META.get('CONTENT_LENGTH') or 0)
        if size > 131072:
            return JsonResponse({'success': False}, status=413)
        posted = json.loads(request.body) if request.content_type == 'application/json' else request.POST
        if not hasattr(posted, 'get'):
            raise ValueError
        token = request.GET.get('token') if request.method == 'GET' else posted.get('token')
        catalog = signing.loads(token, salt=TOKEN_SALT, max_age=TOKEN_MAX_AGE)
        if catalog['user'] != str(request.user.pk):
            raise signing.BadSignature('Different user')
    except (signing.BadSignature, TypeError, ValueError, KeyError):
        return JsonResponse({'success': False, 'error': strings['personal_columns_expired']}, status=403)
    config = get_system_config().get('tables_config') or {}
    columns = available_columns(catalog['model'], catalog['columns'], config)
    names = [c['name'] for c in columns]
    if not names:
        return JsonResponse({'success': False}, status=403)
    from ..models import Profile
    profile = Profile.all_objects.filter(user=request.user).first()
    preferences = _coerce_prefs_dict(profile.preferences if profile else {})
    overlay = personal_overlay(preferences, catalog['key'], names)
    error = ''
    if request.method == 'POST':
        try:
            raw = posted.get('preferences', {})
            raw = json.loads(raw) if isinstance(raw, str) else raw
            if not isinstance(raw, dict) or set(raw) - {'order', 'hidden', 'reset'}:
                raise ValueError
            if 'reset' in raw and not isinstance(raw['reset'], bool):
                raise ValueError
            for field in ('order', 'hidden'):
                values = raw.get(field, [])
                if not isinstance(values, list) or any(not isinstance(n, str) or n not in names for n in values):
                    raise ValueError
            if set(raw.get('hidden', [])) == set(names) and not raw.get('reset'):
                raise ValueError
            overlay = personal_overlay({PREFERENCE_KEY: {catalog['key']: raw}}, catalog['key'], names)
            with transaction.atomic():
                profile, _ = Profile.all_objects.get_or_create(user=request.user)
                profile = Profile.all_objects.select_for_update().get(pk=profile.pk)
                preferences = dict(_coerce_prefs_dict(profile.preferences))
                saved = preferences.get(PREFERENCE_KEY)
                saved = dict(saved) if isinstance(saved, dict) else {}
                if raw.get('reset') or (not overlay['hidden'] and overlay['order'] == names):
                    saved.pop(catalog['key'], None)
                else:
                    saved[catalog['key']] = overlay
                if saved:
                    preferences[PREFERENCE_KEY] = saved
                else:
                    preferences.pop(PREFERENCE_KEY, None)
                if not _prefs_within_cap(preferences):
                    return JsonResponse({'success': False}, status=413)
                profile.preferences = preferences
                profile.save(update_fields=['preferences'])
            return JsonResponse({'success': True, 'refresh_parent': True, 'close_modal': True})
        except (TypeError, ValueError):
            error = strings['personal_columns_invalid']
    by_name = {c['name']: c for c in columns}
    rows = [{**by_name[n], 'hidden': n in overlay['hidden']} for n in overlay['order']]
    html = render_to_string('dlux/tables/personal_columns.html', {
        'token': token, 'columns': rows, 'defaults': json.dumps(names),
        'preferences_json': json.dumps(overlay, separators=(',', ':')), 'error': error,
        'has_override': overlay['hidden'] or overlay['order'] != names,
        'DLUX_STRINGS': strings,
    }, request=request)
    return JsonResponse({'html': html, 'success': False}, status=400 if error else 200)
