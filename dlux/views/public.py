"""Views for anonymous pages built on ``dlux/public_base.html``."""

from django.http import Http404, HttpResponse
from django.views.decorators.http import require_http_methods

from ..fonts import font_stylesheet_css, get_font_by_slug
from ..page_styles import page_stylesheet_css, page_stylesheet_version
from ..system.normalizers import normalize_allowed_fonts
from ..utils import get_system_config


@require_http_methods(["GET", "HEAD"])
def font_stylesheet(request, slug):
    """One font System Settings allows, as a same-origin stylesheet.

    ``public_base.html`` links it for the one font a public page uses. Anyone may fetch it: it names a font and its
    files, nothing else.
    """
    if slug not in normalize_allowed_fonts(get_system_config().get('allowed_fonts')):
        raise Http404
    font = get_font_by_slug(slug)
    css = font_stylesheet_css(font) if font else None
    if css is None:
        raise Http404
    response = HttpResponse(css, content_type='text/css; charset=utf-8')
    response['Cache-Control'] = 'public, max-age=3600'
    return response


@require_http_methods(["GET", "HEAD"])
def page_stylesheet(request, version):
    """The registry stylesheet ``base.html`` links (``dlux/page_styles.py``).

    Anyone may fetch it: the sign-in page links it too, and it names fonts,
    their files and theme colours, nothing else. The version is a digest of the
    content, so the current URL is cached for good and a stale one is not.
    """
    css = page_stylesheet_css()
    response = HttpResponse(css, content_type='text/css; charset=utf-8')
    current = page_stylesheet_version(css)
    response['Cache-Control'] = 'public, max-age=31536000, immutable' if version == current else 'no-cache'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
