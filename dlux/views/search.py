"""Global search view.

The JSON endpoint behind the titlebar search dropdown. It lived in
`dlux/views/options.py` (then `general.py`) until 1.8.0, where it was the one
member with no relation to the system-options page that module serves. The
search engine itself is `dlux.search`; this is the thin HTTP layer over it.
"""
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse

from ..search import run_search
from ..translations import get_current_language_code
from ..utils import get_system_config, normalize_search_config


@login_required
def global_search_view(request):
    """JSON endpoint for the titlebar global search. Returns grouped,
    permission-filtered results for the given ``q``. Respects ``search_config``
    (disabled → no results) and only searches data when
    both its ``include_data`` setting is on and the client asks
    for it (``?data=1``)."""
    config = get_system_config()
    search = normalize_search_config(
        config.get('search_config') or config.get('titlebar_config') or config.get('titlebar') or {}
    )
    if not search['enabled']:
        return JsonResponse({'groups': [], 'disabled': True})

    query = (request.GET.get('q') or '').strip()
    include_data = bool(search['include_data']) and \
        request.GET.get('data') in ('1', 'true', 'yes')
    # Resolve the actual display language the way the rest of Dlux does (session
    # preview / user preference / session / config) — NOT request.LANGUAGE_CODE,
    # which Dlux does not populate; otherwise results are always English and an
    # Arabic query never matches.
    lang_code = get_current_language_code(request)

    groups = run_search(request.user, query, include_data=include_data, lang_code=lang_code,
                        request=request)
    return JsonResponse({'groups': groups, 'query': query, 'include_data': include_data})
