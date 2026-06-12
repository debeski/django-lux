try:
    from oauth2_provider.oauth2_validators import OAuth2Validator
except ImportError:  # pragma: no cover - provider dependency is optional outside this package.
    OAuth2Validator = object

from .services import build_userinfo_claims


class DluxOIDCValidator(OAuth2Validator):
    """OIDC validator that emits portable per-client role claims only."""

    def get_additional_claims(self, request):
        claims = {}
        if hasattr(super(), "get_additional_claims"):
            claims.update(super().get_additional_claims(request) or {})

        user = getattr(request, "user", None)
        application = getattr(request, "client", None)
        if user and application:
            claims.update(build_userinfo_claims(user, application))
        return claims

