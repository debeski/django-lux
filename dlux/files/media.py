"""Who may fetch a stored file straight from the proxy.

The generated proxy serves `/media/` with its own file server, which is fast but
knows nothing about users. Before it serves anything outside the public folders
it asks `media_access` (Caddy `forward_auth`, nginx `auth_request`), so the
proxy never hands a stored file to someone the app itself would refuse.

Decisions, in order:

- folders only the app serves (backups, protected assets, file history) and
  ``DLUX_APP_ONLY_MEDIA`` are refused to everyone; their own views serve them
  after their checks;
- public folders (branding, managed images and fonts, ``public/``) and
  ``DLUX_PUBLIC_MEDIA`` are served to anyone;
- a registered document file follows its document: anyone gets it when the
  registration's ``public`` rule passes, otherwise the user must reach the
  document in its scoped queryset and pass its ``view`` access check;
- everything else needs a signed-in user.

A project entry is a folder (``products/``) or, when it has a wildcard, a file
pattern matched one folder level per ``/`` (``publication/*.png``).
"""

import posixpath
from fnmatch import fnmatchcase
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
_WILDCARDS = frozenset('*?[')


def _listed(name, builtin, setting):
    """Is ``name`` under one of the folders, or matched by one of the patterns?

    Compared without regard to case: on a case-insensitive host disk a case
    variant reaches the same file.
    """
    extra = getattr(settings, setting, ()) or ()
    if isinstance(extra, str):
        extra = (extra,)
    key = name.casefold()
    parts = key.split('/')
    for entry in (*builtin, *extra):
        entry = str(entry or '').strip('/').casefold()
        if not entry:
            continue
        if _WILDCARDS.isdisjoint(entry):
            if (key + '/').startswith(entry + '/'):
                return True
            continue
        pattern = entry.split('/')
        if len(pattern) == len(parts) and all(map(fnmatchcase, parts, pattern)):
            return True
    return False


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

    signed_in = request.user.is_authenticated
    matched = False
    for spec in registered_document_files():
        if not (signed_in or spec.public):
            # Signed out, only a public rule can grant: skip the lookup.
            continue
        model, field = spec.model, spec.field_name
        if not model._base_manager.filter(**{f'{field}__iexact': name}).exists():
            continue
        matched = True
        if spec.public:
            # Unscoped and the same for every reader: signing in must not hide a public file.
            candidates = model._base_manager.filter(**{field: name})
            if hasattr(model, 'deleted_at'):
                candidates = candidates.filter(deleted_at__isnull=True)
            for document in candidates[:_DOCUMENT_CANDIDATES]:
                if spec.public(document):
                    return True
        if not signed_in:
            continue
        queryset = spec.queryset(request, model) if spec.queryset else _scope_filtered_modal_queryset(model, request.user)
        for document in queryset.filter(**{field: name})[:_DOCUMENT_CANDIDATES]:
            if can_access(request, spec, document, 'view'):
                return True
    return False if matched else None


def media_decision(request, name):
    """May ``request`` fetch the stored file ``name`` from the proxy?"""
    if _listed(name, APP_ONLY_MEDIA, 'DLUX_APP_ONLY_MEDIA'):
        return False
    if _listed(name, PUBLIC_MEDIA, 'DLUX_PUBLIC_MEDIA'):
        return True
    decision = _document_decision(request, name)
    return request.user.is_authenticated if decision is None else decision


@require_safe
def media_access(request):
    """204 when the proxy may serve the forwarded `/media/` file, 403 when not."""
    name = media_name(request.META.get(FORWARDED_URI, ''))
    allowed = name is not None and media_decision(request, name)
    response = HttpResponse(status=204 if allowed else 403)
    response['Cache-Control'] = 'no-store'
    return response
