import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from .constants import ROLE_CHOICES, ROLE_VALUES, ROLE_ADMIN


class SSOClientPolicy(models.Model):
    application = models.OneToOneField(
        "oauth2_provider.Application",
        on_delete=models.CASCADE,
        related_name="dlux_sso_policy",
    )
    slug = models.SlugField(unique=True)
    display_name = models.CharField(max_length=160)
    is_active = models.BooleanField(default=True)
    allow_all_authenticated = models.BooleanField(
        default=False,
        help_text="If enabled, any active authenticated provider user receives the 'user' role for this client.",
    )
    require_pkce = models.BooleanField(default=True)
    require_https_redirects = models.BooleanField(default=True)
    allow_localhost_redirects = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "SSO client policy"
        verbose_name_plural = "SSO client policies"

    def __str__(self):
        return self.display_name or str(self.application)


class SSOClientMembership(models.Model):
    policy = models.ForeignKey(SSOClientPolicy, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sso_client_memberships")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_USER)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("policy", "user")
        verbose_name = "SSO client membership"
        verbose_name_plural = "SSO client memberships"

    def clean(self):
        if self.role not in ROLE_VALUES:
            raise ValueError(f"Unsupported SSO role: {self.role}")

    def __str__(self):
        return f"{self.user} -> {self.policy} ({self.role})"


class SSOAdminInvitation(models.Model):
    policy = models.ForeignKey(SSOClientPolicy, on_delete=models.CASCADE, related_name="admin_invitations")
    email = models.EmailField()
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_ADMIN)
    token_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("policy", "email", "token_hash")
        verbose_name = "SSO admin invitation"
        verbose_name_plural = "SSO admin invitations"

    @staticmethod
    def hash_token(token):
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @classmethod
    def create_invitation(cls, *, policy, email, created_by=None, role=ROLE_ADMIN, expires_at=None):
        token = secrets.token_urlsafe(32)
        invitation = cls.objects.create(
            policy=policy,
            email=email,
            role=role,
            token_hash=cls.hash_token(token),
            expires_at=expires_at or timezone.now() + timedelta(days=7),
            created_by=created_by,
        )
        return invitation, token

    @property
    def is_usable(self):
        return not self.accepted_at and self.expires_at > timezone.now()

    def __str__(self):
        return f"{self.email} -> {self.policy}"


class SSOAuditEvent(models.Model):
    event_type = models.CharField(max_length=80)
    policy = models.ForeignKey(SSOClientPolicy, null=True, blank=True, on_delete=models.SET_NULL)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    client_id = models.CharField(max_length=255, blank=True)
    role = models.CharField(max_length=20, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "SSO audit event"
        verbose_name_plural = "SSO audit events"

    def __str__(self):
        return f"{self.event_type} {self.client_id}".strip()


class SSOSessionState(models.Model):
    policy = models.ForeignKey(SSOClientPolicy, null=True, blank=True, on_delete=models.SET_NULL)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sso_sessions")
    token_identifier = models.CharField(max_length=255, unique=True)
    role = models.CharField(max_length=20, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "SSO session"
        verbose_name_plural = "SSO sessions"

    @property
    def is_revoked(self):
        return bool(self.revoked_at)

    def revoke(self):
        if not self.revoked_at:
            self.revoked_at = timezone.now()
            self.save(update_fields=["revoked_at"])

    def __str__(self):
        return f"{self.user} {self.policy} {self.token_identifier}"

