"""Weather configuration: import-safe defaults and validation."""
import math

PLACEMENTS = ('titlebar', 'user_hub', 'floating', 'embed')
DISPLAYS = ('icon', 'temperature', 'combined', 'full')
# 1.10.0b1 called the full display 'text' (condition text alone).
LEGACY_DISPLAYS = {'text': 'full'}
CORNERS = ('bottom-end', 'bottom-start', 'top-end', 'top-start')


def default_weather_config():
    return dict(enabled=False, provider='openweather', placement='titlebar',
                display='combined', units='metric', corner='bottom-end',
                locations=[], default_location='', encrypted_api_key='')


def normalize_locations(value):
    if not isinstance(value, list) or len(value) > 10:
        raise ValueError('Choose up to ten locations.')
    result = []
    seen = set()
    for item in value:
        if not isinstance(item, dict):
            raise ValueError('Invalid location.')
        try:
            lat, lon = float(item['lat']), float(item['lon'])
        except (KeyError, TypeError, ValueError, OverflowError):
            raise ValueError('Invalid coordinates.') from None
        if not math.isfinite(lat) or not math.isfinite(lon) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError('Invalid coordinates.')
        name = str(item.get('name') or '').strip()[:120]
        if not name:
            raise ValueError('A location needs a name.')
        key = f'{lat:.5f},{lon:.5f}'
        if key not in seen:
            result.append(dict(id=key, name=name, lat=round(lat, 5), lon=round(lon, 5)))
            seen.add(key)
    return result


def normalize_weather_config(value):
    cfg = value if isinstance(value, dict) else {}
    result = default_weather_config()
    result['enabled'] = cfg.get('enabled') in (True, 1, 'true', 'on')
    if cfg.get('display') in LEGACY_DISPLAYS:
        cfg = {**cfg, 'display': LEGACY_DISPLAYS[cfg['display']]}
    for key, choices in (('placement', PLACEMENTS), ('display', DISPLAYS),
                         ('units', ('metric', 'imperial')), ('corner', CORNERS)):
        if cfg.get(key) in choices:
            result[key] = cfg[key]
    try:
        result['locations'] = normalize_locations(cfg.get('locations', []))
    except ValueError:
        pass
    ids = [location['id'] for location in result['locations']]
    result['default_location'] = cfg.get('default_location') if cfg.get('default_location') in ids else next(iter(ids), '')
    if isinstance(cfg.get('encrypted_api_key'), str):
        result['encrypted_api_key'] = cfg['encrypted_api_key'][:2048]
    return result


def portable_extra_config(value):
    """Keep project namespaces intact while excluding the weather credential."""
    result = dict(value) if isinstance(value, dict) else {}
    if 'weather' in result:
        result['weather'] = normalize_weather_config(result['weather'])
        result['weather'].pop('encrypted_api_key', None)
    return result
