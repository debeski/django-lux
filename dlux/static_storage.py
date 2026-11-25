"""Static file URLs that change with every release.

A generated stack's proxy serves ``/static/`` with ``Cache-Control: public,
max-age=31536000, immutable``. A plain ``{% static %}`` URL never changes, so a
browser kept a project's old script for a year after an upgrade (found upgrading
Trademarks to DjangoLux 1.16.5). ``dlux_settings()`` swaps Django's default
static storage for ``VersionedStaticFilesStorage``, whose URLs carry
``?v=<DjangoLux version>-<project version>``: a DjangoLux update or a project
release gives every static URL a new address.
"""
import os
from functools import lru_cache
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.staticfiles.storage import StaticFilesStorage


@lru_cache(maxsize=1)
def release_revision():
    """``<DjangoLux version>-<project version>``, or the DjangoLux version alone
    when the project has no ``release-manifest.json``. Read once per process: both
    versions only change with a restart (inline update or image rebuild)."""
    from . import __version__ as dlux_version
    from .utils.settings import get_project_version

    project_version = get_project_version()
    return f"{dlux_version}-{project_version}" if project_version else str(dlux_version)


def static_revision(path):
    """The ``v`` value for ``path``. In DEBUG the source file's modification time
    is added, so mounted development assets refresh without a release."""
    revision = release_revision()
    if settings.DEBUG and path:
        try:
            from django.contrib.staticfiles import finders

            source = finders.find(path)
            if source:
                revision = f"{revision}-{os.stat(source).st_mtime_ns:x}"
        except (OSError, TypeError, ValueError):
            pass
    return revision


def with_revision(url, path):
    """``url`` with ``v=<revision>`` added, unless it already carries a ``v``."""
    query = urlsplit(url).query
    if any(part == 'v' or part.startswith('v=') for part in query.split('&') if part):
        return url
    separator = '&' if '?' in url else '?'
    return f"{url}{separator}v={static_revision(path)}"


class VersionedStaticFilesStorage(StaticFilesStorage):
    """Django's ``StaticFilesStorage`` with ``?v=<release>`` on every URL."""

    def url(self, name):
        url = super().url(name)
        return with_revision(url, name) if name else url
