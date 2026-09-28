"""Why a correct password can still leave you on the login page.

Authentication and *remembering* it are separate steps: the password is checked,
the session row is written, `Set-Cookie` goes out — and the browser then throws
the cookie away because it cannot store it for this page. The POST returns its
redirect, the next request arrives anonymous, and the user is back at the login
form with no error, because as far as Django is concerned nothing failed.

Two settings cause it, both correct in production and both fatal on a host they
were not written for:

* ``SESSION_COOKIE_SECURE`` with a page served over plain HTTP, and
* ``SESSION_COOKIE_DOMAIN`` naming a domain this request did not come from.

A deployment reached over its real hostname and TLS never sees either. A stack
opened on ``localhost`` sees both, and the only symptom is a login form that
keeps coming back. So the login page says so.
"""

from __future__ import annotations

from django.conf import settings


def _host(request):
    try:
        return (request.get_host() or "").split(":")[0].lower()
    except Exception:
        # get_host() raises on a host outside ALLOWED_HOSTS; that is a different
        # misconfiguration with its own error page, and not this one to report.
        return ""


def _https_behind_unconfigured_proxy(request):
    """True when a proxy says the browser is on HTTPS but Django was not told to listen.

    With TLS ended at Caddy or nginx, Django sees plain HTTP and ``is_secure()``
    stays False until ``SECURE_PROXY_SSL_HEADER`` is set. The browser is still on
    HTTPS and keeps the Secure cookie, so login works and there is nothing to
    report here; ``dlux_doctor`` names the missing setting. When the setting *is*
    configured, ``is_secure()`` already reads the proxy's answer and is trusted.
    """
    if getattr(settings, "SECURE_PROXY_SSL_HEADER", None):
        return False
    proto = request.META.get("HTTP_X_FORWARDED_PROTO", "")
    return proto.split(",")[0].strip().lower() == "https"


def session_cookie_problem(request, strings=None):
    """A sentence explaining why login cannot persist here, or ``""``.

    ``strings`` is the localized string map, so the message follows the site's
    language; the defaults are used when a project has not translated it.
    """
    strings = strings or {}

    if (
        getattr(settings, "SESSION_COOKIE_SECURE", False)
        and not request.is_secure()
        and not _https_behind_unconfigured_proxy(request)
    ):
        return strings.get(
            "login_cookie_insecure",
            "Signing in cannot be completed: the session cookie is marked Secure, "
            "but this page was served over HTTP, so the browser discards it. Open "
            "the site over HTTPS, or set DEBUG_STATUS=True for local access.",
        )

    domain = (getattr(settings, "SESSION_COOKIE_DOMAIN", "") or "").lstrip(".").lower()
    host = _host(request)
    if domain and host and host != domain and not host.endswith("." + domain):
        template = strings.get(
            "login_cookie_domain",
            "Signing in cannot be completed: the session cookie is scoped to "
            "{domain}, but this page is served from {host}, so the browser "
            "discards it. Open the site at {domain}.",
        )
        return template.replace("{domain}", domain).replace("{host}", host)

    return ""
