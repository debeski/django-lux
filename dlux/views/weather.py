"""Authenticated weather reads and administrator-only draft city search."""
import json

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from ..weather import (
    SearchNotFound, WeatherPending, WeatherUnavailable, api_key, current_weather, get_weather_config,
    location_search_result, start_location_search,
)


@login_required
@require_GET
@never_cache
def weather_current(request):
    config = get_weather_config()
    if not config['enabled']:
        return JsonResponse({'error': 'disabled'}, status=404)
    selected = request.GET.get('location', config['default_location'])
    location = next((item for item in config['locations'] if item['id'] == selected), None)
    if location is None:
        return JsonResponse({'error': 'location'}, status=400)
    from ..translations import get_current_language_code
    language = get_current_language_code()
    try:
        return JsonResponse(current_weather(config, location, language))
    except WeatherPending:
        # The worker has been asked; the widget tries again shortly.
        return JsonResponse({'status': 'pending'}, status=202)
    except WeatherUnavailable:
        return JsonResponse({'error': 'unavailable'}, status=503)


@login_required
@require_POST
@never_cache
def weather_locations(request):
    if not request.user.is_superuser:
        return JsonResponse({'error': 'forbidden'}, status=403)
    if len(request.body) > 4096:
        return JsonResponse({'error': 'invalid'}, status=400)
    try:
        data = json.loads(request.body)
        query = data.get('query', '').strip()
        key = data.get('api_key', '').strip() or api_key(get_weather_config())
        enabled = data.get('enabled') is True
        if not enabled or not 2 <= len(query) <= 120 or len(key) > 256:
            raise ValueError
    except (ValueError, AttributeError, TypeError):
        return JsonResponse({'error': 'invalid'}, status=400)
    if not cache.add(f'dlux:weather:search:{request.user.pk}', True, 1):
        return JsonResponse({'error': 'retry'}, status=429)
    try:
        started = start_location_search(query, key, request.user.pk)
    except WeatherUnavailable as exc:
        return JsonResponse({'error': str(exc)}, status=502)
    if 'locations' in started:
        return JsonResponse({'locations': started['locations']})
    return JsonResponse({
        'status': 'pending',
        'token': started['token'],
        'result_url': reverse('weather_location_result', args=[started['token']]),
    }, status=202)


@login_required
@require_GET
@never_cache
def weather_location_result(request, token):
    """The answer to a search this administrator started: 202 while the worker runs it."""
    if not request.user.is_superuser:
        return JsonResponse({'error': 'forbidden'}, status=403)
    try:
        locations = location_search_result(token, request.user.pk)
    except SearchNotFound:
        return JsonResponse({'error': 'not_found'}, status=404)
    except WeatherUnavailable as exc:
        return JsonResponse({'error': str(exc)}, status=502)
    if locations is None:
        return JsonResponse({'status': 'pending'}, status=202)
    return JsonResponse({'locations': locations})
