"""Profiles, devices, presence and public registration."""

from django.apps import apps
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.core.files.base import ContentFile
from ..system.constants import (
    REGISTRATION_ACTIVATION_AUTO_LOGIN,
    REGISTRATION_ACTIVATION_CHOICES,
    REGISTRATION_STATUS_ACTIVATED,
    REGISTRATION_STATUS_CHOICES,
    REGISTRATION_STATUS_EXPIRED,
    REGISTRATION_STATUS_PENDING_APPROVAL,
    REGISTRATION_STATUS_PENDING_EMAIL,
    REGISTRATION_STATUS_REJECTED,
)
import hashlib
import io
import secrets
from datetime import timedelta
from PIL import Image

from ._shared import logger
from .base import ScopedModel
from .scopes import GroupProfile, Scope, ScopeSettings


class Profile(ScopedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile', verbose_name="User")
    phone = models.CharField(max_length=15, blank=True, null=True, verbose_name="Phone Number")
    profile_picture = models.ImageField(upload_to='profile_pictures/', null=True, blank=True)
    # deleted_at is inherited from ScopedModel
    preferences = models.JSONField(default=dict, blank=True, verbose_name="User Preferences")
    # Per-user onboarding flag: set once the user completes/skips the Initial User Setup modal.
    is_configured = models.BooleanField(default=False, verbose_name="Completed Initial User Setup")
    
    # 2FA Fields
    is_email_2fa_enabled = models.BooleanField(default=False, verbose_name="2FA via Email")
    is_phone_2fa_enabled = models.BooleanField(default=False, verbose_name="2FA via Phone")
    is_totp_2fa_enabled = models.BooleanField(default=False, verbose_name="2FA via App")
    totp_secret = models.CharField(max_length=255, blank=True, null=True, verbose_name="TOTP Secret")
    backup_codes = models.JSONField(default=list, blank=True, verbose_name="Backup Codes")
    email_verified_at = models.DateTimeField(blank=True, null=True, verbose_name="Email Verified At")

    @property
    def is_2fa_enabled(self):
        """Returns True if any 2FA method is enabled."""
        return self.is_email_2fa_enabled or self.is_phone_2fa_enabled or self.is_totp_2fa_enabled

    @property
    def full_name(self):
        return f"{self.user.first_name} {self.user.last_name}".strip()

    def __str__(self):
        return self.user.username

    @property
    def profile_pic(self):
        """Standardized property to access profile picture with default fallback."""
        if self.profile_picture:
            return self.profile_picture
        return None

    def save(self, *args, **kwargs):
        """Optimize profile picture: Resize and convert to WebP."""
        if self.totp_secret:
            from ..utils import encrypt_totp_secret
            self.totp_secret = encrypt_totp_secret(self.totp_secret)

        if self.profile_picture and hasattr(self.profile_picture, 'file'):
            try:
                # Normalize extension and check if processing is needed
                ext = self.profile_picture.name.lower().split('.')[-1]
                if ext != 'webp':
                    img = Image.open(self.profile_picture)
                    
                    # Convert to RGB (standard for JPEG/WebP)
                    if img.mode in ('RGBA', 'P'):
                        img = img.convert('RGB')
                    
                    # Resize if larger than 300x300
                    if img.width > 300 or img.height > 300:
                        img.thumbnail((300, 300), Image.Resampling.LANCZOS)
                    
                    # Prepare WebP buffer
                    output = io.BytesIO()
                    img.save(output, format='WEBP', quality=80)
                    output.seek(0)
                    
                    # Construct new filename
                    original_name = self.profile_picture.name.rsplit('.', 1)[0]
                    new_filename = f"{original_name}.webp"
                    
                    # Replace the file content
                    # We wrap in ContentFile and assign to the field
                    # Note: We don't call super() here if we call self.profile_picture.save() with save=True
                    # But if we use save=False, we still need super().save()
                    content = ContentFile(output.read())
                    self.profile_picture.save(new_filename, content, save=False)
            except Exception:
                pass
                
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Profile"
        verbose_name_plural = "Profiles"
        default_permissions = ()
        permissions = [
            ("manage_staff", "Can manage staff"),
            ("manage_scopes", "Can manage scopes and all users"),
            ("view_reports", "Can view reports"),
            ("view_audit_fields", "Can view audit fields (created/updated by/at) in tables and detail views"),
            ("download_backup", "Can download backup"),
        ]


def apply_public_registration_defaults(user):
    """
    Apply admin-marked Scope and Group preset defaults to an activated public
    registration account. Defaults are owned by the Scopes and Groups managers,
    not System Settings.
    """
    if not getattr(user, 'pk', None):
        return

    profile, _created = Profile.all_objects.get_or_create(user=user)
    scope = None

    try:
        if ScopeSettings.load().is_enabled:
            scope = Scope.objects.filter(is_public_registration_default=True).order_by('name', 'pk').first()
            if scope is not None and profile.scope_id != scope.pk:
                profile.scope = scope
                profile.save(update_fields=['scope'])
    except Exception:
        logger.exception("Failed to apply default public-registration scope for user pk=%s", user.pk)

    try:
        Group = apps.get_model('auth', 'Group')
        default_profiles = GroupProfile.objects.filter(
            is_active=True,
            is_public_registration_default=True,
        )
        if scope is not None:
            default_profiles = default_profiles.filter(models.Q(scope__isnull=True) | models.Q(scope=scope))
        else:
            default_profiles = default_profiles.filter(scope__isnull=True)
        groups = Group.objects.filter(dlux_profile__in=default_profiles)
        if groups.exists():
            from ..utils import set_user_group_presets
            set_user_group_presets(user, list(groups), actor=None, manageable_groups=groups)
    except Exception:
        logger.exception("Failed to apply default public-registration group presets for user pk=%s", user.pk)


class TrustedDevice(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='trusted_devices',
        verbose_name="User",
    )
    token_hash = models.CharField(max_length=64, unique=True, verbose_name="Token Hash")
    session_key = models.CharField(max_length=64, blank=True, verbose_name="Session Key")
    device_label = models.CharField(max_length=255, blank=True, verbose_name="Device Label")
    ip_address = models.GenericIPAddressField(blank=True, null=True, verbose_name="IP Address")
    user_agent = models.TextField(blank=True, verbose_name="User Agent")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    last_used_at = models.DateTimeField(auto_now=True, verbose_name="Last Used At")
    trusted_until = models.DateTimeField(verbose_name="Trusted Until")
    revoked_at = models.DateTimeField(blank=True, null=True, verbose_name="Revoked At")

    class Meta:
        verbose_name = "Trusted Device"
        verbose_name_plural = "Trusted Devices"
        ordering = ['-last_used_at']

    def __str__(self):
        return f"{self.user} trusted device"

    @property
    def is_active(self):
        return self.revoked_at is None and self.trusted_until > timezone.now()


class UserKnownDevice(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='dlux_known_devices',
        verbose_name="User",
    )
    device_hash = models.CharField(max_length=64, verbose_name="Device Hash")
    device_label = models.CharField(max_length=255, blank=True, verbose_name="Device Label")
    trusted_device = models.ForeignKey(
        'dlux.TrustedDevice',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='known_device_links',
        verbose_name="Trusted Device",
    )
    ip_addresses = models.JSONField(default=list, blank=True, verbose_name="IP Addresses")
    user_agents = models.JSONField(default=list, blank=True, verbose_name="User Agents")
    browser_names = models.JSONField(default=list, blank=True, verbose_name="Browsers")
    os_names = models.JSONField(default=list, blank=True, verbose_name="Operating Systems")
    first_seen_at = models.DateTimeField(default=timezone.now, verbose_name="First Seen At")
    last_seen_at = models.DateTimeField(default=timezone.now, verbose_name="Last Seen At")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated At")

    class Meta:
        verbose_name = "Known Device"
        verbose_name_plural = "Known Devices"
        ordering = ['-last_seen_at']
        constraints = [
            models.UniqueConstraint(fields=['user', 'device_hash'], name='dlux_unique_known_device'),
        ]
        indexes = [
            models.Index(fields=['user', '-last_seen_at'], name='dlux_known_device_seen_idx'),
        ]

    def __str__(self):
        return f"{self.user} known device"


class UserPresenceSession(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='dlux_presence_sessions',
        verbose_name="User",
    )
    known_device = models.ForeignKey(
        'dlux.UserKnownDevice',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='presence_sessions',
        verbose_name="Known Device",
    )
    session_key_hash = models.CharField(max_length=64, verbose_name="Session Key Hash")
    session_key = models.CharField(max_length=64, blank=True, verbose_name="Session Key")
    device_label = models.CharField(max_length=255, blank=True, verbose_name="Device Label")
    ip_addresses = models.JSONField(default=list, blank=True, verbose_name="IP Addresses")
    user_agents = models.JSONField(default=list, blank=True, verbose_name="User Agents")
    browser_names = models.JSONField(default=list, blank=True, verbose_name="Browsers")
    os_names = models.JSONField(default=list, blank=True, verbose_name="Operating Systems")
    first_seen_at = models.DateTimeField(default=timezone.now, verbose_name="First Seen At")
    last_seen_at = models.DateTimeField(default=timezone.now, verbose_name="Last Seen At")
    estimated_seconds = models.PositiveIntegerField(default=0, verbose_name="Estimated Seconds")
    request_count = models.PositiveIntegerField(default=0, verbose_name="Request Count")
    ended_at = models.DateTimeField(blank=True, null=True, verbose_name="Ended At")
    revoked_at = models.DateTimeField(blank=True, null=True, verbose_name="Revoked At")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated At")

    class Meta:
        verbose_name = "Presence Session"
        verbose_name_plural = "Presence Sessions"
        ordering = ['-last_seen_at']
        constraints = [
            models.UniqueConstraint(fields=['user', 'session_key_hash'], name='dlux_unique_presence_session'),
        ]
        indexes = [
            models.Index(fields=['user', '-last_seen_at'], name='dlux_presence_seen_idx'),
            models.Index(fields=['session_key_hash'], name='dlux_presence_session_idx'),
        ]

    def __str__(self):
        return f"{self.user} presence session"


class PublicRegistration(models.Model):
    dlux_auto_create_user_profile = False

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='public_registration',
        verbose_name="User",
    )
    email = models.EmailField(db_index=True, verbose_name="Email")
    status = models.CharField(
        max_length=32,
        choices=REGISTRATION_STATUS_CHOICES,
        default=REGISTRATION_STATUS_PENDING_EMAIL,
        db_index=True,
        verbose_name="Status",
    )
    activation_mode = models.CharField(
        max_length=32,
        choices=REGISTRATION_ACTIVATION_CHOICES,
        default=REGISTRATION_ACTIVATION_AUTO_LOGIN,
        verbose_name="Activation Mode",
    )
    token_hash = models.CharField(max_length=64, blank=True, verbose_name="Verification Token Hash")
    ip_address = models.GenericIPAddressField(blank=True, null=True, verbose_name="IP Address")
    user_agent = models.TextField(blank=True, verbose_name="User Agent")
    expires_at = models.DateTimeField(verbose_name="Expires At")
    verified_at = models.DateTimeField(blank=True, null=True, verbose_name="Verified At")
    approved_at = models.DateTimeField(blank=True, null=True, verbose_name="Approved At")
    rejected_at = models.DateTimeField(blank=True, null=True, verbose_name="Rejected At")
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        related_name='approved_public_registrations',
        on_delete=models.SET_NULL,
        verbose_name="Approved By",
    )
    rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        related_name='rejected_public_registrations',
        on_delete=models.SET_NULL,
        verbose_name="Rejected By",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated At")

    class Meta:
        verbose_name = "Public Registration"
        verbose_name_plural = "Public Registrations"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.email} ({self.status})"

    @staticmethod
    def hash_token(token):
        return hashlib.sha256(str(token).encode('utf-8')).hexdigest()

    @classmethod
    def create_for_user(cls, user, email, activation_mode, ip_address=None, user_agent='', ttl_seconds=86400):
        token = secrets.token_urlsafe(32)
        registration = cls.objects.create(
            user=user,
            email=email,
            activation_mode=activation_mode,
            token_hash=cls.hash_token(token),
            ip_address=ip_address,
            user_agent=(user_agent or '')[:2000],
            expires_at=timezone.now() + timedelta(seconds=ttl_seconds),
        )
        return registration, token

    def token_matches(self, token):
        if not token or not self.token_hash:
            return False
        return constant_time_compare(self.token_hash, self.hash_token(token))

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    def mark_expired(self):
        if self.status == REGISTRATION_STATUS_PENDING_EMAIL:
            self.status = REGISTRATION_STATUS_EXPIRED
            self.token_hash = ''
            self.user.is_active = False
            self.user.save(update_fields=['is_active'])
            self.save(update_fields=['status', 'token_hash', 'updated_at'])

    def mark_verified(self):
        self.verified_at = timezone.now()
        self.token_hash = ''
        if self.activation_mode == REGISTRATION_ACTIVATION_AUTO_LOGIN:
            self.status = REGISTRATION_STATUS_ACTIVATED
            self.user.is_active = True
            self.user.save(update_fields=['is_active'])
            apply_public_registration_defaults(self.user)
        else:
            self.status = REGISTRATION_STATUS_PENDING_APPROVAL
            self.user.is_active = False
            self.user.save(update_fields=['is_active'])
        self.save(update_fields=['verified_at', 'token_hash', 'status', 'updated_at'])

        profile = getattr(self.user, 'profile', None)
        if profile and not profile.email_verified_at:
            profile.email_verified_at = self.verified_at
            profile.save(update_fields=['email_verified_at'])

    def approve(self, actor):
        self.status = REGISTRATION_STATUS_ACTIVATED
        self.approved_at = timezone.now()
        self.approved_by = actor
        self.user.is_active = True
        self.user.save(update_fields=['is_active'])
        apply_public_registration_defaults(self.user)
        self.save(update_fields=['status', 'approved_at', 'approved_by', 'updated_at'])

    def reject(self, actor):
        self.status = REGISTRATION_STATUS_REJECTED
        self.rejected_at = timezone.now()
        self.rejected_by = actor
        self.token_hash = ''
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        self.save(update_fields=['status', 'rejected_at', 'rejected_by', 'token_hash', 'updated_at'])
