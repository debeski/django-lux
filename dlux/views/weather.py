"""Authenticated weather reads and administrator-only draft city search."""
import json

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from ..weather import WeatherUnavailable, api_key, current_weather, get_weather_config, search_locations


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
        return JsonResponse({'locations': search_locations(query, key)})
    except WeatherUnavailable as exc:
        return JsonResponse({'error': str(exc)}, status=502)
