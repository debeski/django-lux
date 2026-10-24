"""OCR text for registered document files.

Settings live in Options > System Settings > Extra Features
(``SystemSettings.extra_config['ocr']``). ``OCR_*`` environment strings only
fill options that were never saved there; built-in defaults fill the rest.
The engine runs from the project image in the stack's ``ocr`` service, reachable
only on the internal network. Everything here tolerates that service being
off, missing or down: a document save never fails because of OCR.
"""

import os
import ipaddress
import re
from urllib.parse import urlsplit

CONFIG_KEY = 'ocr'
SERVICE_NAME = 'ocr'
MODES = ('auto', 'ocr')
DEFAULTS = {
    'enabled': False,
    'auto_on_save': True,
    'search': True,
    'service_url': 'http://ocr:8080',
    'mode': 'auto',
    'timeout': 900,
    'max_file_mb': 64,
    'threads': 2,
}
ENV_FALLBACKS = {
    'enabled': 'OCR_ENABLED',
    'auto_on_save': 'OCR_AUTO_ON_SAVE',
    'search': 'OCR_SEARCH',
    'service_url': 'OCR_URL',
    'mode': 'OCR_MODE',
    'timeout': 'OCR_TIMEOUT',
    'max_file_mb': 'OCR_MAX_FILE_MB',
    'threads': 'OCR_THREADS',
}
LIMITS = {'timeout': (30, 7200), 'max_file_mb': (1, 512), 'threads': (1, 16)}
_TRUE = ('true', '1', 'yes', 'on')
_FALSE = ('false', '0', 'no', 'off')


def valid_service_url(value):
    """Only an internal service name or private LAN address; never public egress."""
    if not isinstance(value, str):
        return False
    try:
        url = urlsplit(value.strip())
        host = url.hostname or ''
        if url.scheme not in ('http', 'https') or url.username or url.password or url.query or url.fragment or url.path not in ('', '/'):
            return False
        if url.port is not None and not 1 <= url.port <= 65535:
            return False
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            return host.lower() != 'localhost' and bool(re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_-]*', host))
        return address.is_private and not (address.is_loopback or address.is_link_local or address.is_unspecified or address.is_multicast)
    except ValueError:
        return False


def merge(values, raw):
    """Overlay the valid entries of ``raw`` on ``values``; anything invalid is ignored."""
    raw = raw if isinstance(raw, dict) else {}
    for name in ('enabled', 'auto_on_save', 'search'):
        if isinstance(raw.get(name), bool):
            values[name] = raw[name]
    for name, (low, high) in LIMITS.items():
        value = raw.get(name)
        if isinstance(value, int) and not isinstance(value, bool) and low <= value <= high:
            values[name] = value
    if raw.get('mode') in MODES:
        values['mode'] = raw['mode']
    url = raw.get('service_url')
    if valid_service_url(url):
        values['service_url'] = url.strip().rstrip('/')
    return values


def _environment():
    raw = {}
    for name, variable in ENV_FALLBACKS.items():
        value = (os.environ.get(variable) or '').strip()
        if not value:
            continue
        default = DEFAULTS[name]
        if isinstance(default, bool):
            if value.lower() in _TRUE + _FALSE:
                raw[name] = value.lower() in _TRUE
        elif isinstance(default, int):
            if value.isdecimal():
                raw[name] = int(value)
        else:
            raw[name] = value
    return raw


def fallbacks():
    """Built-in defaults overlaid with any ``OCR_*`` environment strings."""
    return merge(dict(DEFAULTS), _environment())


def normalize_ocr_config(stored):
    """The stored ``extra_config['ocr']`` dict as a complete, valid config."""
    return merge(fallbacks(), stored)


def config():
    from dlux.utils.config import get_system_config

    extra = get_system_config().get('extra_config') or {}
    return normalize_ocr_config(extra.get(CONFIG_KEY) if isinstance(extra, dict) else None)


def enabled():
    return config()['enabled']
