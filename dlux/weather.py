"""Server-side OpenWeather adapter and shared, bounded weather cache.

In a Dlux-generated stack neither web nor celery has a route to the internet:
only smtp-relay and the Composer agent sit on the egress network. The calls to
OpenWeather run in a Celery task that writes to the shared cache, and web only
reads that cache, so the celery service must be given the egress network
(docs/weather.md). A project without a reachable Celery worker makes the calls in
web instead, where a development server can reach the internet.
"""
import base64
import hashlib
import json
import logging
import math
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, build_opener

from django.conf import settings
from django.core.cache import cache

from .system.weather import normalize_locations, normalize_weather_config

logger = logging.getLogger(__name__)

FRESH_SECONDS = 900             # a reading younger than this is served as is
KEEP_SECONDS = 86400            # a reading older than FRESH may be served, marked stale
STALE_OBSERVATION = 7200        # an observation older than this is stale regardless
BACKOFF_SECONDS = 30            # one refresh per reading per window; failures back off
SEARCH_WAIT_SECONDS = 10        # how long web waits for a worker's city search
WORKER_CHECK_SECONDS = 60       # how long a worker availability answer is reused


class WeatherUnavailable(Exception):
    pass


class WeatherPending(Exception):
    """No reading yet; a worker has been asked for one."""


def get_weather_config():
    from .utils.config import get_system_config
    return normalize_weather_config((get_system_config().get('extra_config') or {}).get('weather'))


def _fernet():
    from cryptography.fernet import Fernet
    digest = hashlib.sha256(('dlux-weather:' + settings.SECRET_KEY).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_api_key(value):
    return _fernet().encrypt(value.encode()).decode()


def decrypt_api_key(value):
    from cryptography.fernet import InvalidToken
    try:
        return _fernet().decrypt(str(value or '').encode()).decode()
    except (InvalidToken, ValueError, UnicodeError):
        return ''


def api_key(config):
    return decrypt_api_key(config['encrypted_api_key'])


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
    except ValueError:
        raise WeatherUnavailable('provider') from None
    except OSError:
        # URLError and TimeoutError are OSErrors: DNS, refused or timed out, so
        # this process has no route to OpenWeather (a stack whose worker is not
        # on the egress network) rather than OpenWeather answering badly.
        raise WeatherUnavailable('network') from None


def search_locations(query, key):
    data = _request('geo/1.0/direct', key, q=query, limit=5)
    try:
        return normalize_locations([
            dict(name=', '.join(str(row[k]) for k in ('name', 'state', 'country') if row.get(k)), lat=row['lat'], lon=row['lon'])
            for row in data
        ])
    except (KeyError, TypeError, ValueError, AttributeError):
        raise WeatherUnavailable('response') from None


def _reading(units, location, language, key):
    data = _request('data/2.5/weather', key, lat=location['lat'], lon=location['lon'],
                    units=units, lang=language)
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
                    unit='°F' if units == 'imperial' else '°C')
    except (KeyError, TypeError, ValueError, IndexError, OverflowError):
        raise WeatherUnavailable('response') from None


def _reading_key(location, units, language, encrypted_api_key):
    # A key change must not reuse a previous credential's reading or backoff.
    digest = hashlib.sha256(json.dumps([location, units, language, encrypted_api_key], sort_keys=True).encode()).hexdigest()
    return 'dlux:weather:' + digest


def _search_key(token):
    return 'dlux:weather:search-result:' + token


def _celery_app():
    """The project's Celery app. Tasks are sent by name, so this module never
    imports ``dlux.tasks`` (which imports this one)."""
    if not getattr(settings, 'CELERY_BROKER_URL', ''):
        return None
    try:
        from celery import current_app
    except Exception:
        return None
    return current_app


def _worker_reachable():
    app = _celery_app()
    if app is None:
        return False
    try:
        with app.connection_for_write() as conn:
            conn.ensure_connection(max_retries=0, timeout=2)
        return bool(app.control.ping(timeout=1.0))
    except Exception:
        return False


def weather_worker_available():
    """Whether a Celery worker can make the calls. Asked once a minute, not per read."""
    cached = cache.get('dlux:weather:worker')
    if cached is not None:
        return cached
    available = _worker_reachable()
    cache.set('dlux:weather:worker', available, WORKER_CHECK_SECONDS)
    return available


def _dispatch(task_name, args):
    """Queue a weather task by name; False when there is no worker to run it."""
    if not weather_worker_available():
        return False
    try:
        _celery_app().send_task(task_name, args=args, retry=False)
        return True
    except Exception:
        logger.exception('Could not queue %s; making the weather call in this process.', task_name)
        return False


def refresh_reading(location, units, language, encrypted_api_key):
    """Fetch one reading into the shared cache. Runs in the Celery worker."""
    key = _reading_key(location, units, language, encrypted_api_key)
    try:
        reading = _reading(units, location, language, decrypt_api_key(encrypted_api_key))
    except WeatherUnavailable as exc:
        cache.set(key + ':error', str(exc), BACKOFF_SECONDS)
        raise
    cache.set(key, reading, KEEP_SECONDS)
    cache.delete(key + ':error')
    return reading


def current_weather(config, location, language):
    """The reading for ``location``: cached, or refreshed through the worker.

    Raises ``WeatherPending`` when there is no reading yet and a worker has been
    asked for one, and ``WeatherUnavailable`` when the last attempt failed.
    """
    args = [location, config['units'], language, config['encrypted_api_key']]
    key = _reading_key(*args)
    saved = cache.get(key)
    now = time.time()
    if saved and now - saved['fetched_at'] < FRESH_SECONDS:
        return {**saved, 'stale': now - saved['observed_at'] > STALE_OBSERVATION}
    if cache.add(key + ':refresh', True, BACKOFF_SECONDS):
        if not _dispatch('dlux.tasks.weather_refresh', args):
            try:
                reading = refresh_reading(*args)
                return {**reading, 'stale': now - reading['observed_at'] > STALE_OBSERVATION}
            except WeatherUnavailable:
                if not saved:
                    raise
        elif not saved:
            raise WeatherPending()
    if saved:
        return {**saved, 'stale': True}
    error = cache.get(key + ':error')
    if error:
        raise WeatherUnavailable(error)
    raise WeatherPending()


def run_search(token, query, encrypted_api_key):
    """A city search, answered into the cache under ``token``. Runs in the worker."""
    try:
        result = {'locations': search_locations(query, decrypt_api_key(encrypted_api_key))}
    except WeatherUnavailable as exc:
        result = {'error': str(exc)}
    cache.set(_search_key(token), result, 60)
    return result


def find_locations(query, key):
    """Search cities for the settings page: through the worker, or here without one.

    Web blocks for at most ``SEARCH_WAIT_SECONDS``; this is an administrator's
    search, one request at a time.
    """
    token = uuid.uuid4().hex
    if not _dispatch('dlux.tasks.weather_search', [token, query, encrypt_api_key(key) if key else '']):
        return search_locations(query, key)
    deadline = time.monotonic() + SEARCH_WAIT_SECONDS
    while time.monotonic() < deadline:
        result = cache.get(_search_key(token))
        if result is not None:
            cache.delete(_search_key(token))
            if 'error' in result:
                raise WeatherUnavailable(result['error'])
            return result['locations']
        time.sleep(0.25)
    raise WeatherUnavailable('worker')
