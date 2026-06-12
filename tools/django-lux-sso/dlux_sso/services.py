from dataclasses import dataclass
from urllib.parse import urlparse

from django.conf import settings

from .constants import ROLE_USER


@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    role: str = ""
    reason: str = ""
    policy: object = None


def provider_setting(name, default=None):
    config = getattr(settings, "DLUX_SSO_PROVIDER", {})
    if isinstance(config, dict):
        return config.get(name, default)
    return default


def normalize_redirect_uris(value):
    if not value:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.replace("\r", "\n").split() if item.strip()]
    return [str(item).strip() for item in value if str(item).strip()]


def is_loopback_uri(parsed):
    host = (parsed.hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "::1"} or host.startswith("127.")


def validate_redirect_uri(application, redirect_uri, *, require_https=True, allow_localhost=False):
    registered = normalize_redirect_uris(getattr(application, "redirect_uris", ""))
    if redirect_uri not in registered:
        return False, "redirect_uri_not_registered"

    parsed = urlparse(redirect_uri)
    if not parsed.scheme or not parsed.netloc:
        return False, "redirect_uri_invalid"
    if require_https and parsed.scheme != "https":
        if not (allow_localhost and parsed.scheme == "http" and is_loopback_uri(parsed)):
            return False, "redirect_uri_requires_https"
    return True, ""


def get_policy_for_application(application):
    try:
        return application.dlux_sso_policy
    except AttributeError:
        return None
    except Exception:
        return None


def get_user_client_role(user, policy):
    if not user or not getattr(user, "is_authenticated", False):
        return ""
    if not getattr(user, "is_active", True):
        return ""
    if not policy or not getattr(policy, "is_active", False):
        return ""
    if getattr(policy, "allow_all_authenticated", False):
        return ROLE_USER
    membership = (
        policy.memberships
        .filter(user=user, is_active=True)
        .only("role")
        .first()
    )
    return membership.role if membership else ""


def can_user_authorize_application(user, application, *, redirect_uri=None):
    if not user or not getattr(user, "is_authenticated", False):
        return AuthorizationDecision(False, reason="not_authenticated")
    if not getattr(user, "is_active", True):
        return AuthorizationDecision(False, reason="user_inactive")

    policy = get_policy_for_application(application)
    if not policy:
        return AuthorizationDecision(False, reason="missing_client_policy")
    if not policy.is_active:
        return AuthorizationDecision(False, policy=policy, reason="client_inactive")

    if redirect_uri:
        redirect_ok, reason = validate_redirect_uri(
            application,
            redirect_uri,
            require_https=policy.require_https_redirects,
            allow_localhost=policy.allow_localhost_redirects,
        )
        if not redirect_ok:
            return AuthorizationDecision(False, policy=policy, reason=reason)

    role = get_user_client_role(user, policy)
    if not role:
        return AuthorizationDecision(False, policy=policy, reason="missing_client_role")
    return AuthorizationDecision(True, role=role, policy=policy)


def build_userinfo_claims(user, application):
    decision = can_user_authorize_application(user, application)
    if not decision.allowed:
        return {}

    claims = {
        "sub": str(user.pk),
        "preferred_username": getattr(user, "get_username", lambda: getattr(user, "username", ""))(),
        "email": getattr(user, "email", "") or "",
        "name": user.get_full_name() if hasattr(user, "get_full_name") else "",
        "given_name": getattr(user, "first_name", "") or "",
        "family_name": getattr(user, "last_name", "") or "",
        "dlux_sso_client_id": getattr(application, "client_id", ""),
        "dlux_sso_role": decision.role,
        "dlux_sso": {
            "client_id": getattr(application, "client_id", ""),
            "role": decision.role,
        },
    }
    profile = getattr(user, "profile", None)
    if profile and getattr(profile, "phone", None):
        claims["phone_number"] = profile.phone
    return claims
