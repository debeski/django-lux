from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.utils import timezone

try:
    from mozilla_django_oidc.auth import OIDCAuthenticationBackend
except ImportError:  # pragma: no cover - client dependency is optional outside this package.
    class OIDCAuthenticationBackend:
        def verify_claims(self, claims):
            raise PermissionDenied("mozilla-django-oidc is required by django-lux-sso-client")

from .models import SSOIdentity
from .roles import apply_role_mapping, extract_role, get_client_config, is_role_allowed


class DluxSSOAuthenticationBackend(OIDCAuthenticationBackend):
    """OIDC backend that links users by issuer + subject and maps portable roles."""

    def verify_claims(self, claims):
        parent_ok = True
        if hasattr(super(), "verify_claims"):
            parent_ok = super().verify_claims(claims)
        role = extract_role(claims)
        return bool(parent_ok and is_role_allowed(role))

    def filter_users_by_claims(self, claims):
        issuer = get_client_config().get("issuer") or getattr(settings, "OIDC_OP_ISSUER", "")
        subject = claims.get("sub")
        if not issuer or not subject:
            return self.UserModel.objects.none()
        identity = SSOIdentity.objects.filter(issuer=issuer, subject=subject).select_related("user").first()
        if not identity:
            return self.UserModel.objects.none()
        return self.UserModel.objects.filter(pk=identity.user_id, is_active=True)

    @property
    def UserModel(self):
        return get_user_model()

    def create_user(self, claims):
        config = get_client_config()
        role = extract_role(claims)
        if not config.get("auto_create", True) or not is_role_allowed(role, config):
            raise PermissionDenied("This SSO account is not allowed to access this client.")

        username = self._claim_username(claims)
        user = self.UserModel(username=self._unique_username(username))
        self._sync_user_fields(user, claims, role, config)
        user.set_unusable_password()
        user.save()
        self._sync_identity(user, claims, role, config)
        return user

    def update_user(self, user, claims):
        config = get_client_config()
        role = extract_role(claims)
        if not is_role_allowed(role, config):
            raise PermissionDenied("This SSO account is not allowed to access this client.")
        self._sync_user_fields(user, claims, role, config)
        user.save()
        self._sync_identity(user, claims, role, config)
        return user

    def _claim_username(self, claims):
        return (
            claims.get("preferred_username")
            or claims.get("email")
            or f"sso-{claims.get('sub', '')}"
        ).split("@")[0][:150] or "sso-user"

    def _unique_username(self, username):
        base = username[:140]
        candidate = base
        index = 1
        while self.UserModel.objects.filter(username=candidate).exists():
            suffix = f"-{index}"
            candidate = f"{base[:150 - len(suffix)]}{suffix}"
            index += 1
        return candidate

    def _sync_user_fields(self, user, claims, role, config):
        if config.get("sync_user_fields", True):
            user.email = claims.get("email", "") or user.email
            user.first_name = claims.get("given_name", "") or user.first_name
            user.last_name = claims.get("family_name", "") or user.last_name
        apply_role_mapping(user, role, config)

    def _sync_identity(self, user, claims, role, config):
        issuer = config.get("issuer") or getattr(settings, "OIDC_OP_ISSUER", "")
        subject = claims.get("sub")
        if not issuer or not subject:
            raise PermissionDenied("SSO claims must include issuer configuration and subject.")
        SSOIdentity.objects.update_or_create(
            issuer=issuer,
            subject=subject,
            defaults={
                "user": user,
                "role": role,
                "claims": claims,
                "last_login_at": timezone.now(),
            },
        )

