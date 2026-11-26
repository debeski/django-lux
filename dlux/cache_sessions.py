"""Cache-backed sessions that survive a cache outage.

Django's cache ``SessionStore.load()`` reads every error from the cache as a
missing session: it drops the session key, and ``SessionMiddleware`` then
deletes the browser's cookie. While Redis does not answer, any request a
signed-in user makes, a panel's poll included, would sign them out for good.

This engine raises :class:`~dlux.resilient_cache.CacheUnavailable` instead, so
``dlux.cache_outage.CacheOutageMiddleware`` answers the request with its 503,
the cookie is left alone, and the session is still there when the cache answers
again. Any other error, such as a key the backend refuses, still starts an empty
session, as Django's does.

``dlux_settings()`` points ``SESSION_ENGINE = "django.contrib.sessions.backends.cache"``
here when the session cache is one of the fail-fast Redis caches.
"""

from django.contrib.sessions.backends.cache import SessionStore as DjangoCacheSessionStore

from .resilient_cache import CacheUnavailable, is_cache_outage


def _outage(exc):
    """The error to raise for ``exc``, or ``None`` when it is not a cache outage."""
    if isinstance(exc, CacheUnavailable):
        return exc
    if is_cache_outage(exc):
        return CacheUnavailable(f"The session cache did not answer: {exc}")
    return None


class SessionStore(DjangoCacheSessionStore):
    def load(self):
        try:
            session_data = self._cache.get(self.cache_key)
        except Exception as exc:
            outage = _outage(exc)
            if outage is exc:
                raise
            if outage is not None:
                raise outage from exc
            session_data = None
        if session_data is not None:
            return session_data
        self._session_key = None
        return {}

    async def aload(self):
        try:
            session_data = await self._cache.aget(await self.acache_key())
        except Exception as exc:
            outage = _outage(exc)
            if outage is exc:
                raise
            if outage is not None:
                raise outage from exc
            session_data = None
        if session_data is not None:
            return session_data
        self._session_key = None
        return {}
