from django.conf import settings
from django.db import models


class SSOIdentity(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sso_identities")
    issuer = models.URLField()
    subject = models.CharField(max_length=255)
    role = models.CharField(max_length=20, blank=True)
    claims = models.JSONField(default=dict, blank=True)
    last_login_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("issuer", "subject")
        verbose_name = "SSO identity"
        verbose_name_plural = "SSO identities"

    def __str__(self):
        return f"{self.issuer}:{self.subject}"

