"""Server-side OpenWeather adapter and shared, bounded weather cache."""
import base64
import hashlib
import json
import math
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, build_opener

from django.conf import settings
from django.core.cache import cache

from .system.weather import normalize_locations, normalize_weather_config


class WeatherUnavailable(Exception):
    pass


def get_weather_config():
    from .utils.config import get_system_config
    return normalize_weather_config((get_system_config().get('extra_config') or {}).get('weather'))


def _fernet():
    from cryptography.fernet import Fernet
    digest = hashlib.sha256(('dlux-weather:' + settings.SECRET_KEY).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_api_key(value):
    return _fernet().encrypt(value.encode()).decode()


def api_key(config):
    from cryptography.fernet import InvalidToken
    try:
        return _fernet().decrypt(config['encrypted_api_key'].encode()).decode()
    except (InvalidToken, ValueError, UnicodeError):
        return ''


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _request(path, key, **params):
    if not key:
        raise WeatherUnavailable('credentials')
    url = 'https://api.openweathermap.org/' + path + '?' + urlencode({**params, 'appid': key})
    try:
        with build_opener(_NoRedirect).open(url, timeout=4) as response:
            body = response.read(131073)
        if len(body) > 131072:
            raise WeatherUnavailable('response')
        return json.loads(body)
    except HTTPError as exc:
        raise WeatherUnavailable('credentials' if exc.code in (401, 403) else 'provider') from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise WeatherUnavailable('provider') from None


def search_locations(query, key):
    data = _request('geo/1.0/direct', key, q=query, limit=5)
    try:
        return normalize_locations([
            dict(name=', '.join(str(row[k]) for k in ('name', 'state', 'country') if row.get(k)), lat=row['lat'], lon=row['lon'])
            for row in data
        ])
    except (KeyError, TypeError, ValueError, AttributeError):
        raise WeatherUnavailable('response') from None


def _reading(config, location, language):
    data = _request('data/2.5/weather', api_key(config), lat=location['lat'], lon=location['lon'],
                    units=config['units'], lang=language)
    try:
        temperature = float(data['main']['temp'])
        feels_like = float(data['main']['feels_like'])
        observed = int(data['dt'])
        condition = data['weather'][0]
        code = int(condition['id'])
        if not all(math.isfinite(x) for x in (temperature, feels_like)) or observed <= 0:
            raise ValueError
        night = str(condition.get('icon', '')).endswith('n')
        icon = ('cloud-lightning-rain' if code < 300 else 'cloud-drizzle' if code < 400 else
                'cloud-rain' if code < 600 else 'snow' if code < 700 else 'cloud-fog2' if code < 800 else
                ('moon-stars' if night else 'sun') if code == 800 else 'cloud')
        return dict(temperature=round(temperature), feels_like=round(feels_like),
                    description=str(condition['description'])[:160], icon=icon, observed_at=observed,
                    fetched_at=int(time.time()), location=location['name'], location_id=location['id'],
                    unit='°F' if config['units'] == 'imperial' else '°C')
    except (KeyError, TypeError, ValueError, IndexError, OverflowError):
        raise WeatherUnavailable('response') from None


def current_weather(config, location, language):
    # A key change must not reuse a previous credential's failure backoff.
    digest = hashlib.sha256(json.dumps([location, config['units'], language, config['encrypted_api_key']], sort_keys=True).encode()).hexdigest()
    key = 'dlux:weather:' + digest
    saved = cache.get(key)
    now = time.time()
    if saved and now - saved['fetched_at'] < 900:
        return {**saved, 'stale': now - saved['observed_at'] > 7200}
    if not cache.add(key + ':refresh', True, 30):
        if saved:
            return {**saved, 'stale': True}
        raise WeatherUnavailable('retry')
    try:
        reading = _reading(config, location, language)
        cache.set(key, reading, 86400)
        return {**reading, 'stale': now - reading['observed_at'] > 7200}
    except WeatherUnavailable:
        if saved:
            return {**saved, 'stale': True}
        raise
