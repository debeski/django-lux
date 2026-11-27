"""The 503 a request gets when it failed because the cache did not answer.

Kept apart from ``dlux.resilient_cache``, which the sidebar and search import,
because the page reads the translations.
"""

import logging
import sys

from django.core.signals import got_request_exception
from django.http import HttpResponse, JsonResponse
from django.utils.html import escape

from .resilient_cache import RETRY_AFTER_SECONDS, is_cache_outage

logger = logging.getLogger("dlux.cache")


def _mark_outage(sender, request=None, **kwargs):
    if request is not None and is_cache_outage(sys.exc_info()[1]):
        try:
            request._dlux_cache_outage = True
        except Exception:
            pass


got_request_exception.connect(_mark_outage, dispatch_uid="dlux.cache_outage.mark_outage")


def outage_response(
    request,
    *,
    title_key="cache_unavailable_title",
    title="Temporarily unavailable",
    message_key="cache_unavailable_message",
    message=(
        "The service that keeps sign-ins and sessions is not responding. Try again "
        "in a minute; if it keeps happening, tell your administrator."
    ),
    retry_after=RETRY_AFTER_SECONDS,
    strings=None,
):
    """A 503 saying a service the page needs does not answer.

    Built without templates, the database or the session: those may be what is
    down. JSON for ``XMLHttpRequest`` and ``Accept: application/json``.
    ``strings`` skips the language lookup, which reads System Settings and the
    signed-in user's profile, for a page served while the database is away.
    """
    offline = strings is not None
    if not offline:
        try:
            from .translations import get_strings

            strings = get_strings()
        except Exception:
            try:
                from .translations.strings.en import STRINGS as strings
            except Exception:
                strings = {}
    title = strings.get(title_key) or title
    message = strings.get(message_key) or message
    retry_after = str(int(retry_after))
    wants_json = (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or "application/json" in request.headers.get("accept", "")
    )
    if wants_json:
        response = JsonResponse({"success": False, "error": message}, status=503)
    else:
        lang = "en"
        try:
            if offline:
                from django.conf import settings

                lang = str(getattr(settings, "LANGUAGE_CODE", "en") or "en").split("-")[0]
            else:
                from .translations import get_current_language_code

                lang = (get_current_language_code(request) or "en").split("-")[0]
        except Exception:
            pass
        direction = "rtl" if lang.startswith(("ar", "fa", "he", "ur")) else "ltr"
        response = HttpResponse(
            f'<!doctype html><html lang="{escape(lang)}" dir="{direction}"><head>'
            f'<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{escape(title)}</title></head><body><main><h1>{escape(title)}</h1>"
            f"<p>{escape(message)}</p></main></body></html>",
            status=503,
            content_type="text/html; charset=utf-8",
        )
    response["Retry-After"] = retry_after
    response["Cache-Control"] = "no-store"
    # Middleware inside this one never sees the replacement response.
    response["X-Content-Type-Options"] = "nosniff"
    response["X-Frame-Options"] = "DENY"
    return response


class CacheOutageMiddleware:
    """Answer 503 instead of 500 when a request failed because the cache is down.

    It sits just outside the session middleware. A view's error reaches ``process_exception``;
    an error in an inner middleware, such as the session middleware saving the
    session, is already a 500 response by the time it gets here, so the request
    is marked by a ``got_request_exception`` receiver and the 500 is replaced.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if getattr(request, "_dlux_cache_outage", False) and getattr(response, "status_code", 0) == 500:
            return outage_response(request)
        return response

    def process_exception(self, request, exception):
        if not is_cache_outage(exception):
            return None
        logger.warning("%s %s failed because the cache did not answer: %s", request.method, request.path, exception)
        return outage_response(request)
