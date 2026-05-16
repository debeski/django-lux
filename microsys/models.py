# Imports of the required python modules and libraries
######################################################
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.core.cache import cache
from django.core.files.base import ContentFile
from .constants import (
    DEFAULT_HOME_URL,
    DEFAULT_TABLE_DENSITY,
    REGISTRATION_ACTIVATION_AUTO_LOGIN,
    REGISTRATION_ACTIVATION_CHOICES,
    REGISTRATION_STATUS_ACTIVATED,
    REGISTRATION_STATUS_CHOICES,
    REGISTRATION_STATUS_EXPIRED,
    REGISTRATION_STATUS_PENDING_APPROVAL,
    REGISTRATION_STATUS_PENDING_EMAIL,
    REGISTRATION_STATUS_REJECTED,
    TABLE_DENSITY_CHOICES,
    TABLE_DENSITY_VALUES,
)
from .managers import ScopedManager
import hashlib
import io
import secrets
from datetime import timedelta
from PIL import Image


def default_allowed_fonts():
    from .fonts import get_builtin_fonts
    return [f['slug'] for f in get_builtin_fonts()]


def default_allowed_themes():
    from .themes import get_theme_names
    return list(get_theme_names())


def default_titlebar_config():
    return {
        'show_title': True,
        'show_logo': True,
        'show_home_button': True,
        'hide_on_public_unauthenticated_index': False,
        'home_shape': 'circle',
        'title_align': 'start',
        'title_size': 'md',
        'height': 'balanced',
        'surface': 'default',
    }


class Scope(models.Model):
    name = models.CharField(max_length=100, verbose_name="Scope")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Scope"
        verbose_name_plural = "Scopes"


class ScopeSettings(models.Model):
    is_enabled = models.BooleanField(default=False, verbose_name="Enable Scopes")
    auto_create_user_scope = models.BooleanField(default=False, verbose_name="Auto-create scope for each user")

    class Meta:
        verbose_name = "Scope Settings"
        verbose_name_plural = "Scope Settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super(ScopeSettings, self).save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Scope Settings"


class SingletonModel(models.Model):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
        self.refresh_cache()

    def delete(self, *args, **kwargs):
        pass

    @classmethod
    def load(cls):
        obj = cache.get(cls.__name__)
        if obj:
            # Check if object still exists in DB to prevent stale cache after DB wipes
            if not cls.objects.filter(pk=obj.pk).exists():
                obj = None
        
        if not obj:
            obj, created = cls.objects.get_or_create(pk=1)
            if created:
                # Seed from codebase MICROSYS_CONFIG if available
                config = getattr(settings, 'MICROSYS_CONFIG', {})
                if hasattr(obj, 'system_names') and isinstance(config.get('system_names'), dict):
                    obj.system_names = config.get('system_names')
                if 'default_language' in config:
                    obj.default_language = config.get('default_language')
                if 'default_theme' in config:
                    obj.default_theme = config.get('default_theme')
                if hasattr(obj, 'default_table_density') and config.get('default_table_density') in TABLE_DENSITY_VALUES:
                    obj.default_table_density = config.get('default_table_density')
                if 'home_url' in config:
                    obj.home_url = config.get('home_url') or obj.home_url
                if hasattr(obj, 'languages') and isinstance(config.get('languages'), dict):
                    obj.languages = config.get('languages')
                if hasattr(obj, 'translations_override') and isinstance(config.get('translations'), dict):
                    obj.translations_override = config.get('translations')
                if hasattr(obj, 'sidebar_config') and isinstance(config.get('sidebar'), dict):
                    obj.sidebar_config = config.get('sidebar')
                if hasattr(obj, 'email_config') and isinstance(config.get('email_config'), dict):
                    obj.email_config = config.get('email_config')
                if hasattr(obj, 'allowed_themes') and isinstance(config.get('allowed_themes'), (list, tuple, set)):
                    obj.allowed_themes = list(config.get('allowed_themes'))
                if hasattr(obj, 'allow_user_theme_override') and 'allow_user_theme_override' in config:
                    obj.allow_user_theme_override = bool(config.get('allow_user_theme_override'))
                if hasattr(obj, 'allow_user_language_override') and 'allow_user_language_override' in config:
                    obj.allow_user_language_override = bool(config.get('allow_user_language_override'))
                if hasattr(obj, 'titlebar_config') and isinstance(config.get('titlebar'), dict):
                    obj.titlebar_config = config.get('titlebar')
                if hasattr(obj, 'email_2fa') and 'email_2fa' in config:
                    obj.email_2fa = bool(config.get('email_2fa'))
                if hasattr(obj, 'public_root') and 'public_root' in config:
                    obj.public_root = bool(config.get('public_root'))
                if hasattr(obj, 'public_root_split_enabled') and 'public_root_split_enabled' in config:
                    obj.public_root_split_enabled = bool(config.get('public_root_split_enabled'))
                if hasattr(obj, 'public_root_url') and 'public_root_url' in config:
                    obj.public_root_url = str(config.get('public_root_url') or '').strip()
                if hasattr(obj, 'public_registration_enabled') and 'public_registration_enabled' in config:
                    obj.public_registration_enabled = bool(config.get('public_registration_enabled'))
                if hasattr(obj, 'registration_activation_mode') and config.get('registration_activation_mode'):
                    obj.registration_activation_mode = config.get('registration_activation_mode')
                if hasattr(obj, 'registration_throttle_enabled') and 'registration_throttle_enabled' in config:
                    obj.registration_throttle_enabled = bool(config.get('registration_throttle_enabled'))
                if hasattr(obj, 'allowed_fonts') and isinstance(config.get('allowed_fonts'), (list, tuple, set)):
                    obj.allowed_fonts = list(config.get('allowed_fonts'))
                if hasattr(obj, 'default_fonts') and isinstance(config.get('default_fonts'), dict):
                    obj.default_fonts = config.get('default_fonts')
                if hasattr(obj, 'allow_user_font_override') and 'allow_user_font_override' in config:
                    obj.allow_user_font_override = bool(config.get('allow_user_font_override'))
                obj.save()
            cache.set(cls.__name__, obj, timeout=86400)
        return obj

    def refresh_cache(self):
         cache.set(self.__class__.__name__, self, timeout=86400)


class SystemSettings(SingletonModel):
    system_names = models.JSONField(default=dict, blank=True, verbose_name="System Names by Language")
    logo = models.ImageField(upload_to='microsys/branding/', null=True, blank=True, verbose_name="System Logo (Logo)")
    favicon = models.ImageField(upload_to='microsys/branding/', null=True, blank=True, verbose_name="Site Icon (Favicon)")
    default_language = models.CharField(max_length=10, default='en', verbose_name="Default Language")
    default_theme = models.CharField(max_length=20, default='light', verbose_name="Default Theme")
    default_table_density = models.CharField(
        max_length=20,
        default=DEFAULT_TABLE_DENSITY,
        choices=TABLE_DENSITY_CHOICES,
        verbose_name="Default Table Density",
    )
    allowed_themes = models.JSONField(default=default_allowed_themes, blank=True, verbose_name="Allowed Themes")
    allow_user_theme_override = models.BooleanField(default=True, verbose_name="Allow User Theme Override")
    allowed_fonts = models.JSONField(default=default_allowed_fonts, blank=True, verbose_name="Allowed Fonts")
    default_fonts = models.JSONField(default=dict, blank=True, verbose_name="Default Fonts by Language")
    allow_user_font_override = models.BooleanField(default=True, verbose_name="Allow User Font Override")
    allow_user_language_override = models.BooleanField(default=True, verbose_name="Allow User Language Override")
    home_url = models.CharField(max_length=255, default=DEFAULT_HOME_URL, verbose_name="Home URL")
    is_configured = models.BooleanField(default=False, verbose_name="Is Configured")
    email_2fa = models.BooleanField(default=False, verbose_name="Enable Email 2FA")
    client_ip_config = models.JSONField(default=dict, blank=True, verbose_name="Client IP Configuration")
    public_root = models.BooleanField(default=False, verbose_name="Public Root Access")
    public_root_split_enabled = models.BooleanField(default=False, verbose_name="Separate Public Root From Home")
    public_root_url = models.CharField(max_length=255, default='', blank=True, verbose_name="Public Root URL")
    public_registration_enabled = models.BooleanField(default=False, verbose_name="Enable Public Registration")
    registration_activation_mode = models.CharField(
        max_length=32,
        choices=REGISTRATION_ACTIVATION_CHOICES,
        default=REGISTRATION_ACTIVATION_AUTO_LOGIN,
        verbose_name="Registration Activation Mode",
    )
    registration_throttle_enabled = models.BooleanField(default=True, verbose_name="Enable Registration Throttles")
    email_config = models.JSONField(default=dict, blank=True, verbose_name="Email Configuration")
    languages = models.JSONField(default=dict, blank=True, verbose_name="Available Languages")
    translations_override = models.JSONField(default=dict, blank=True, verbose_name="Translations Override")
    sidebar_config = models.JSONField(default=dict, blank=True, verbose_name="Sidebar Configuration")
    titlebar_config = models.JSONField(default=default_titlebar_config, blank=True, verbose_name="Titlebar Configuration")

    class Meta:
        verbose_name = "System Settings"
        verbose_name_plural = "System Settings"

    def __str__(self):
        return "System Settings"


class ScopeForeignKey(models.ForeignKey):
    """
    ForeignKey that hides itself from ModelForms when scopes are disabled.
    Keeps schema identical to a normal ForeignKey.
    """

    def formfield(self, **kwargs):
        # Always return a real form field.
        # Visibility is managed globally by microsys.patches.
        return super().formfield(**kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        # Treat as a normal ForeignKey in migrations to avoid churn.
        path = "django.db.models.ForeignKey"
        return name, path, args, kwargs


class ScopedModel(models.Model):
    """
    Abstract base class for models that should be isolated by Scope.
    Provides built-in audit trail (timestamps + actor tracking) and soft-delete.
    All audit fields are editable=False — auto-excluded from ModelForms.
    """
    scope = ScopeForeignKey('microsys.Scope', on_delete=models.PROTECT, null=True, blank=True, verbose_name="Scope")

    # Timestamps (auto-managed)
    created_at = models.DateTimeField(auto_now_add=True, editable=False, verbose_name="Created At")
    updated_at = models.DateTimeField(auto_now=True, editable=False, verbose_name="Updated At")

    # Audit trail (auto-populated via save() override)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, related_name='+',
        on_delete=models.SET_NULL, editable=False, verbose_name="Created By"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, related_name='+',
        on_delete=models.SET_NULL, editable=False, verbose_name="Updated By"
    )

    # Soft-delete
    deleted_at = models.DateTimeField(null=True, blank=True, editable=False, verbose_name="Deleted At")
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, related_name='+',
        on_delete=models.SET_NULL, editable=False, verbose_name="Deleted By"
    )

    objects = ScopedManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        """Auto-populate created_by/updated_by and scope from thread-local user."""
        from .middleware import get_current_user
        user = get_current_user()
        if user and hasattr(user, 'is_authenticated') and user.is_authenticated:
            if not self.pk:
                if not self.created_by_id:
                    self.created_by = user
                # Auto-set scope from user's profile if not explicitly set
                if not self.scope_id and hasattr(user, 'profile') and user.profile.scope_id:
                    from .utils import is_scope_enabled
                    if is_scope_enabled():
                        self.scope_id = user.profile.scope_id
            self.updated_by = user
        super().save(*args, **kwargs)

    def delete(self, using=None, keep_parents=False):
        """Override: ALL deletes become soft-deletes. Actor auto-detected."""
        from .middleware import get_current_user
        self.deleted_at = timezone.now()
        user = get_current_user()
        if user and hasattr(user, 'is_authenticated') and user.is_authenticated:
            self.deleted_by = user
        self.save(update_fields=['deleted_at', 'deleted_by'])

    def soft_delete(self):
        """Explicit soft-delete (delegates to overridden delete)."""
        self.delete()

    def restore(self):
        """Undo soft-delete."""
        self.deleted_at = None
        self.deleted_by = None
        self.save(update_fields=['deleted_at', 'deleted_by'])

    def hard_delete(self, using=None, keep_parents=False):
        """Permanently remove from database (escape hatch)."""
        super().delete(using=using, keep_parents=keep_parents)


class Profile(ScopedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile', verbose_name="User")
    phone = models.CharField(max_length=15, blank=True, null=True, verbose_name="Phone Number")
    profile_picture = models.ImageField(upload_to='profile_pictures/', null=True, blank=True)
    # deleted_at is inherited from ScopedModel
    preferences = models.JSONField(default=dict, blank=True, verbose_name="User Preferences")
    
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
            from .utils import encrypt_totp_secret
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
        ]


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


class PublicRegistration(models.Model):
    microsys_auto_create_user_profile = False

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
        self.save(update_fields=['status', 'approved_at', 'approved_by', 'updated_at'])

    def reject(self, actor):
        self.status = REGISTRATION_STATUS_REJECTED
        self.rejected_at = timezone.now()
        self.rejected_by = actor
        self.token_hash = ''
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        self.save(update_fields=['status', 'rejected_at', 'rejected_by', 'token_hash', 'updated_at'])


class UserActivityLog(ScopedModel):
    """
    Activity log model. Uses inherited ScopedModel fields:
    - created_by → the user who performed the action (was 'user')
    - created_at → when the action occurred (was 'timestamp')
    """
    # created_by (inherited) → replaces old 'user' field
    # created_at (inherited) → replaces old 'timestamp' field
    action = models.CharField(max_length=50, verbose_name="Action")
    model_name = models.CharField(max_length=100, blank=True, null=True, verbose_name="Model Name")
    object_id = models.IntegerField(blank=True, null=True, verbose_name="Object ID")
    number = models.CharField(max_length=50, null=True, blank=True, verbose_name="Document Number")
    ip_address = models.GenericIPAddressField(blank=True, null=True, verbose_name="IP Address")
    user_agent = models.TextField(blank=True, null=True, verbose_name="User Agent")
    details = models.JSONField(default=dict, blank=True, null=True, verbose_name="Details")

    # Backward-compat properties for templates and tables
    @property
    def user(self):
        """Alias for created_by (backward compat)."""
        return self.created_by

    @property
    def timestamp(self):
        """Alias for created_at (backward compat)."""
        return self.created_at

    def __str__(self):
        return f"{self.created_by} {self.action} {self.model_name or 'General'} at {self.created_at}"

    class Meta:
        verbose_name = "Activity Log"
        verbose_name_plural = "Activity Logs"
        default_permissions = ()
        permissions = [
            ("view_activitylog", "View activity log"),
        ]

    @classmethod
    def safe_log(cls, user, action, model_name=None, object_id=None, number=None, details=None, ip_address=None, user_agent=None, scope=None):
        """
        Log an action only if a duplicate entry hasn't been created in the last 2 seconds.
        """
        from django.utils.timezone import now
        from datetime import timedelta
        
        # Debounce window
        time_threshold = now() - timedelta(seconds=2)
        
        # Check for duplicates
        duplicate = cls.objects.filter(
            created_by=user,
            action=action,
            model_name=model_name,
            object_id=object_id,
            created_at__gte=time_threshold
        )
        
        if details:
             duplicate = duplicate.filter(details=details)
             
        if duplicate.exists():
            return None

        # Automatically use actor's scope if not provided
        if not scope and user:
            from .utils import get_user_scope
            scope = get_user_scope(user)

        return cls.objects.create(
            created_by=user,
            action=action,
            model_name=model_name,
            object_id=object_id,
            number=number,
            details=details or {},
            ip_address=ip_address,
            user_agent=user_agent,
            scope=scope,
        )

    def get_modal_context(self):
        """Auto-resolve related object for dynamic modal detail view."""
        related_object = None
        if self.model_name and self.object_id:
            from .utils import resolve_model_by_name
            try:
                target_model = resolve_model_by_name(self.model_name)
                if target_model:
                    try:
                        related_object = target_model._default_manager.get(pk=self.object_id)
                    except (target_model.DoesNotExist, ValueError, TypeError):
                        pass
            except Exception:
                pass
        return {
            'related_object': related_object,
            'related_object_model': related_object._meta.verbose_name if related_object else (self.model_name or "-"),
        }

class TranslationMixin:
    """
    Mixin for zero-boilerplate database content translation.
    Usage example:
        class Product(TranslationMixin, models.Model):
            translated_fields = ['name', 'description']
            name_en = models.CharField(...)
            name_ar = models.CharField(...)
        
        # In template: {{ product.t_name }} prints 'Sample' or 'عينة' magically.
    """
    def __getattr__(self, name):
        """
        Intercepts field access. If name starts with 't_' and the base field is translated,
        it fetches the correct variant based on the thread's language.
        """
        if name.startswith('t_'):
            base_field = name[2:]
            translated_fields = getattr(self.__class__, 'translated_fields', [])
            
            if base_field in translated_fields:
                from django.utils.translation import get_language
                lang = get_language() or 'en'
                
                # Try fetching localized version
                try:
                    val = self.__getattribute__(f"{base_field}_{lang}")
                    if val is not None and val != "":
                        return val
                except AttributeError:
                    pass
                
                # Check default language (fallback 1)
                try:
                    from microsys.utils import get_system_config
                    default_lang = get_system_config().get('default_language', 'en')
                    val = self.__getattribute__(f"{base_field}_{default_lang}")
                    if val is not None and val != "":
                        return val
                except AttributeError:
                    pass
                
                # Fallback to English (fallback 2)
                try:
                    val = self.__getattribute__(f"{base_field}_en")
                    if val is not None and val != "":
                        return val
                except AttributeError:
                    pass

                # Fallback to base (fallback 3)
                try:
                    val = self.__getattribute__(base_field)
                    if val is not None:
                        return val
                except AttributeError:
                    return ""
                    
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")


class Section(models.Model):
    """Dummy Model for section permissions."""
    class Meta:
        managed = False
        default_permissions = ()
        permissions = [
            ("view_sections", "View sections"),
            ("manage_sections", "Manage sections"),
        ]
