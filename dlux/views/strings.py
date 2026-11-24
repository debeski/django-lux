"""The client strings table as a cacheable script.

``base.html`` names ``/sys/api/strings/<lang>.<version>.js`` instead of embedding
the whole table in every page. The version is a digest of everything the table
is built from, so the URL changes whenever the table does and the response can
be cached for good.
"""

from django.http import Http404, HttpResponse
from django.views.decorators.http import require_http_methods

from ..translations.runtime import (
    client_strings_script,
    client_strings_version,
    config_translation_overrides,
    get_strings,
)
from ..utils import get_system_config

IMMUTABLE = 'public, max-age=31536000, immutable'


def _served_languages(config):
    localization = config.get('localization') or {}
    languages = localization.get('languages') or config.get('languages') or {}
    default_lang = localization.get('default_language') or config.get('default_language') or 'en'
    return {*languages, default_lang}


@require_http_methods(["GET", "HEAD"])
def strings_script(request, lang, version):
    """Anyone may fetch it: every page, the sign-in page included, already
    carried the same table inline."""
    config = get_system_config()
    if lang not in _served_languages(config):
        raise Http404
    overrides = config_translation_overrides(config)
    response = HttpResponse(
        client_strings_script(get_strings(lang, overrides=overrides)),
        content_type='text/javascript; charset=utf-8',
    )
    # A stale version still gets the current table, but only for this load:
    # caching it under the old URL would pin the wrong strings for a year.
    current = client_strings_version(lang, overrides)
    response['Cache-Control'] = IMMUTABLE if version == current else 'no-cache'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
