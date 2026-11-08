"""Who may fetch a stored file straight from the proxy.

The generated proxy serves `/media/` with its own file server, which is fast but
knows nothing about users. Before it serves anything outside the public folders
it asks `media_access` (Caddy `forward_auth`, nginx `auth_request`), so the
proxy never hands a stored file to someone the app itself would refuse.

Decisions, in order:

- folders only the app serves (backups, protected assets, file history),
  ``DLUX_APP_ONLY_MEDIA`` and any ``.dlb`` archive are refused to everyone;
  their own views serve them after their checks;
- public folders (branding, managed images and fonts, ``public/``) and
  ``DLUX_PUBLIC_MEDIA`` are served to anyone;
- a registered document file follows its document: anyone gets it when the
  registration's ``public`` rule passes, otherwise the user must reach the
  document in its scoped queryset and pass its ``view`` access check;
- everything else needs a signed-in user.

Whatever would be granted is refused when it is a backup: a file in the folder
system or report backups are written to now (``backup_config.auto_export_target``
and ``DLUX_CONFIG['reports']['backup_storage_prefix']``, read per request), or
one a backup record names, so moving the folder does not expose older backups.

A project entry is a folder (``products/``) or, when it has a wildcard, a file
pattern matched one folder level per ``/`` (``publication/*.png``).
"""

import posixpath
from urllib.parse import unquote, urlsplit

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.http import require_safe

from dlux.system.media_folders import (  # noqa: F401  re-exported
    APP_ONLY_MEDIA,
    BACKUP_SUFFIX,
    PUBLIC_MEDIA,
    backup_folder_is_public,
    is_public_media,
    listed as _listed,
)

#: Set by the proxy on its sub-request (both templates overwrite any client value).
FORWARDED_URI = 'HTTP_X_FORWARDED_URI'
#: Documents checked per registered field for one requested name.
_DOCUMENT_CANDIDATES = 5


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


def backup_folders():
    """The folders system and report backups are written to now."""
    from dlux.backup.config import get_system_backup_storage_prefix
    from dlux.reports.archive import get_backup_storage_prefix

    return (get_system_backup_storage_prefix(), get_backup_storage_prefix())


def _is_backup(name):
    """Is ``name`` in a backup folder, or a file a backup record names?"""
    from django.db.models import Q

    from dlux.models import ReportBackup, SystemBackup

    if _listed(name, backup_folders()):
        return True
    archives = Q(file_path__iexact=name)
    stem, dot, suffix = name.rpartition('.')
    if dot and suffix.casefold() == 'idx':
        # A member's row-index sidecar sits beside its archive (`SystemBackup.index_path`).
        archives |= Q(file_path__iexact=f'{stem}{BACKUP_SUFFIX}')
    return (
        SystemBackup._base_manager.filter(archives).exists()
        or ReportBackup._base_manager.filter(file_path__iexact=name).exists()
    )


def media_decision(request, name):
    """May ``request`` fetch the stored file ``name`` from the proxy?"""
    if _listed(name, APP_ONLY_MEDIA, 'DLUX_APP_ONLY_MEDIA') or name.casefold().endswith(BACKUP_SUFFIX):
        return False
    if is_public_media(name):
        allowed = True
    else:
        decision = _document_decision(request, name)
        allowed = request.user.is_authenticated if decision is None else decision
    # Looked up only when the answer would be yes, so refusals stay query-free.
    return allowed and not _is_backup(name)


@require_safe
def media_access(request):
    """204 when the proxy may serve the forwarded `/media/` file, 403 when not."""
    name = media_name(request.META.get(FORWARDED_URI, ''))
    allowed = name is not None and media_decision(request, name)
    response = HttpResponse(status=204 if allowed else 403)
    response['Cache-Control'] = 'no-store'
    return response
