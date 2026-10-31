"""Who may fetch a stored file straight from the proxy.

The generated proxy serves `/media/` with its own file server, which is fast but
knows nothing about users. Before it serves anything outside the public folders
it asks `media_access` (Caddy `forward_auth`, nginx `auth_request`), so the
proxy never hands a stored file to someone the app itself would refuse.

Decisions, in order:

- folders only the app serves (backups, protected assets, file history) are
  refused to everyone; their own views serve them after their checks;
- public folders (branding, managed images and fonts, ``public/`` and
  ``DLUX_PUBLIC_MEDIA``) are served to anyone;
- everything else needs a signed-in user;
- a registered document file follows its document: the user must reach the
  document in its scoped queryset and pass its ``view`` access check.
"""

import posixpath
from urllib.parse import unquote, urlsplit

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.http import require_safe

#: Served only by the app's own views, never by the proxy.
APP_ONLY_MEDIA = ('dlux_backups/', 'dlux/assets/private/', 'dlux/file_history/')
#: Served to anyone. Keep in step with the public `/media/` routes of the
#: scaffold's `.proxy/Caddyfile` and `.proxy/default.conf.template`.
PUBLIC_MEDIA = ('public/', 'dlux/branding/', 'dlux/assets/image/', 'dlux/assets/font/')
#: Set by the proxy on its sub-request (both templates overwrite any client value).
FORWARDED_URI = 'HTTP_X_FORWARDED_URI'
#: Documents checked per registered field for one requested name.
_DOCUMENT_CANDIDATES = 5


def _prefixes(builtin, setting):
    extra = getattr(settings, setting, ()) or ()
    if isinstance(extra, str):
        extra = (extra,)
    return tuple(
        prefix.strip('/').casefold() + '/'
        for prefix in (*builtin, *extra)
        if str(prefix or '').strip('/')
    )


def media_name(uri):
    """The storage name a forwarded ``/media/…`` URI points at, or None.

    Decoded once and normalised the way the proxy's file server resolves it, so
    an encoded or dotted variant names the same file it would serve. Anything
    outside `MEDIA_URL`, or climbing out of it, is None.
    """
    path = urlsplit(uri or '').path
    media_url = urlsplit(settings.MEDIA_URL or '/media/').path or '/media/'
    if not media_url.endswith('/'):
        media_url += '/'
    if not path.startswith(media_url):
        return None
    raw = unquote(path[len(media_url):])
    if not raw or '\x00' in raw or '\\' in raw:
        return None
    name = posixpath.normpath(raw)
    if name in ('.', '..') or name.startswith(('/', '../')):
        return None
    return name


def _document_decision(request, name):
    """True or False when ``name`` is a registered document file, else None.

    Matched without regard to case: on a case-insensitive host disk a case
    variant reaches the same file, so it must not slip past its document.
    """
    from dlux.views.sections import _scope_filtered_modal_queryset

    from .specs import registered_document_files
    from .views import can_access

    matched = False
    for spec in registered_document_files():
        model, field = spec.model, spec.field_name
        if not model._base_manager.filter(**{f'{field}__iexact': name}).exists():
            continue
        matched = True
        queryset = spec.queryset(request, model) if spec.queryset else _scope_filtered_modal_queryset(model, request.user)
        for document in queryset.filter(**{field: name})[:_DOCUMENT_CANDIDATES]:
            if can_access(request, spec, document, 'view'):
                return True
    return False if matched else None


def media_decision(request, name):
    """May ``request`` fetch the stored file ``name`` from the proxy?"""
    key = name.casefold() + '/'
    if key.startswith(_prefixes(APP_ONLY_MEDIA, 'DLUX_APP_ONLY_MEDIA')):
        return False
    if key.startswith(_prefixes(PUBLIC_MEDIA, 'DLUX_PUBLIC_MEDIA')):
        return True
    if not request.user.is_authenticated:
        return False
    decision = _document_decision(request, name)
    return True if decision is None else decision


@require_safe
def media_access(request):
    """204 when the proxy may serve the forwarded `/media/` file, 403 when not."""
    name = media_name(request.META.get(FORWARDED_URI, ''))
    allowed = name is not None and media_decision(request, name)
    response = HttpResponse(status=204 if allowed else 403)
    response['Cache-Control'] = 'no-store'
    return response
