"""Views for anonymous pages built on ``dlux/public_base.html``."""

from django.http import Http404, HttpResponse
from django.views.decorators.http import require_http_methods

from ..fonts import font_stylesheet_css, get_font_by_slug
from ..system.normalizers import normalize_allowed_fonts
from ..utils import get_system_config


@require_http_methods(["GET", "HEAD"])
def font_stylesheet(request, slug):
    """One font System Settings allows, as a same-origin stylesheet.

    ``base.html`` writes these rules inline; pages under a policy that allows no
    inline style link this instead. Anyone may fetch it: it names a font and its
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
