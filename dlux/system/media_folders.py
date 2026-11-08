"""The `/media/` folder rules behind `dlux.files.media`.

A leaf (it reads settings only), so the settings normalizers can use the rules
without importing the media access view.
"""

from fnmatch import fnmatchcase

from django.conf import settings

#: Served only by the app's own views, never by the proxy.
APP_ONLY_MEDIA = ('dlux_backups/', 'dlux/assets/private/', 'dlux/file_history/')
#: Served to anyone. Keep in step with the public `/media/` routes of the
#: scaffold's `.proxy/Caddyfile` and `.proxy/default.conf.template`.
PUBLIC_MEDIA = ('public/', 'dlux/branding/', 'dlux/assets/image/', 'dlux/assets/font/')
#: The system backup archive format; never a file the proxy hands out.
BACKUP_SUFFIX = '.dlb'
_WILDCARDS = frozenset('*?[')


def listed(name, builtin, setting=None):
    """Is ``name`` under one of the folders, or matched by one of the patterns?

    Compared without regard to case: on a case-insensitive host disk a case
    variant reaches the same file.
    """
    extra = (getattr(settings, setting, ()) or ()) if setting else ()
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


def is_public_media(name):
    """Would ``name`` be served to anyone, by the proxy or by `media_decision`?"""
    return listed(name, PUBLIC_MEDIA, 'DLUX_PUBLIC_MEDIA')


def backup_folder_is_public(folder):
    """Would a backup written into ``folder`` be served to anyone?

    True inside a public folder or a ``DLUX_PUBLIC_MEDIA`` entry: the proxy
    serves the public folders without asking the app, so no check could keep
    a backup there private.
    """
    folder = str(folder or '').strip('/')
    return bool(folder) and any(is_public_media(f'{folder}/backup{suffix}') for suffix in (BACKUP_SUFFIX, '.idx'))
