# Imports of the required python modules and libraries
######################################################
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.cache import cache
from django.core.files.base import ContentFile
from .managers import ScopedManager
import io
from PIL import Image


class Scope(models.Model):
    name = models.CharField(max_length=100, verbose_name="النطاق")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Scope"
        verbose_name_plural = "Scopes"


class ScopeSettings(models.Model):
    is_enabled = models.BooleanField(default=False, verbose_name="تفعيل النطاقات")

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
        return "إعدادات النطاق"


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
        if not obj:
            obj, created = cls.objects.get_or_create(pk=1)
            if created:
                # Seed from codebase MICROSYS_CONFIG if available
                config = getattr(settings, 'MICROSYS_CONFIG', {})
                if 'name' in config:
                    obj.name = config.get('name')
                if 'name_ar' in config:
                    obj.name = config.get('name_ar') or obj.name
                if 'default_language' in config:
                    obj.default_language = config.get('default_language')
                if 'default_theme' in config:
                    obj.default_theme = config.get('default_theme')
                if 'name_en' in config:
                    obj.name_en = config.get('name_en')
                if 'home_url' in config:
                    obj.home_url = config.get('home_url') or obj.home_url
                if hasattr(obj, 'languages') and isinstance(config.get('languages'), dict):
                    obj.languages = config.get('languages')
                if hasattr(obj, 'translations_override') and isinstance(config.get('translations'), dict):
                    obj.translations_override = config.get('translations')
                if hasattr(obj, 'sidebar_config') and isinstance(config.get('sidebar'), dict):
                    obj.sidebar_config = config.get('sidebar')
                obj.save()
            cache.set(cls.__name__, obj, timeout=86400)
        return obj

    def refresh_cache(self):
         cache.set(self.__class__.__name__, self, timeout=86400)


class SystemSettings(SingletonModel):
    name = models.CharField(max_length=255, default='', verbose_name="اسم النظام (عربي)")
    name_en = models.CharField(max_length=255, blank=True, null=True, verbose_name="اسم النظام (إنجليزي)")
    logo = models.ImageField(upload_to='microsys/branding/', null=True, blank=True, verbose_name="شعار النظام (Logo)")
    favicon = models.ImageField(upload_to='microsys/branding/', null=True, blank=True, verbose_name="أيقونة الموقع (Favicon)")
    default_language = models.CharField(max_length=10, default='en', verbose_name="اللغة الافتراضية")
    default_theme = models.CharField(max_length=20, default='light', verbose_name="المظهر الافتراضي")
    home_url = models.CharField(max_length=255, default='/sys/', verbose_name="الرابط الرئيسي")
    is_configured = models.BooleanField(default=False, verbose_name="تم الضبط")
    languages = models.JSONField(default=dict, blank=True, verbose_name="اللغات المتوفرة")
    translations_override = models.JSONField(default=dict, blank=True, verbose_name="تجاوز الترجمات")
    sidebar_config = models.JSONField(default=dict, blank=True, verbose_name="إعدادات الشريط الجانبي")

    class Meta:
        verbose_name = "System Settings"
        verbose_name_plural = "System Settings"

    def __str__(self):
        return "إعدادات النظام العامة"


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
    scope = ScopeForeignKey('microsys.Scope', on_delete=models.PROTECT, null=True, blank=True, verbose_name="النطاق")

    # Timestamps (auto-managed)
    created_at = models.DateTimeField(auto_now_add=True, editable=False, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, editable=False, verbose_name="تاريخ التعديل")

    # Audit trail (auto-populated via save() override)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, related_name='+',
        on_delete=models.SET_NULL, editable=False, verbose_name="أنشئ بواسطة"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, related_name='+',
        on_delete=models.SET_NULL, editable=False, verbose_name="عدّل بواسطة"
    )

    # Soft-delete
    deleted_at = models.DateTimeField(null=True, blank=True, editable=False, verbose_name="تاريخ الحذف")
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, related_name='+',
        on_delete=models.SET_NULL, editable=False, verbose_name="حذف بواسطة"
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
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile', verbose_name="المستخدم")
    phone = models.CharField(max_length=15, blank=True, null=True, verbose_name="رقم الهاتف")
    profile_picture = models.ImageField(upload_to='profile_pictures/', null=True, blank=True)
    # deleted_at is inherited from ScopedModel
    preferences = models.JSONField(default=dict, blank=True, verbose_name="تفضيلات المستخدم")
    
    # 2FA Fields
    is_email_2fa_enabled = models.BooleanField(default=False, verbose_name="2FA via Email")
    is_phone_2fa_enabled = models.BooleanField(default=False, verbose_name="2FA via Phone")
    is_totp_2fa_enabled = models.BooleanField(default=False, verbose_name="2FA via App")
    totp_secret = models.CharField(max_length=32, blank=True, null=True, verbose_name="TOTP Secret")
    backup_codes = models.JSONField(default=list, blank=True, verbose_name="Backup Codes")

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
        ]


class UserActivityLog(ScopedModel):
    """
    Activity log model. Uses inherited ScopedModel fields:
    - created_by → the user who performed the action (was 'user')
    - created_at → when the action occurred (was 'timestamp')
    """
    # created_by (inherited) → replaces old 'user' field
    # created_at (inherited) → replaces old 'timestamp' field
    action = models.CharField(max_length=50, verbose_name="العملية")
    model_name = models.CharField(max_length=100, blank=True, null=True, verbose_name="القسم")
    object_id = models.IntegerField(blank=True, null=True, verbose_name="ID")
    number = models.CharField(max_length=50, null=True, blank=True, verbose_name="المستند")
    ip_address = models.GenericIPAddressField(blank=True, null=True, verbose_name="عنوان IP")
    user_agent = models.TextField(blank=True, null=True, verbose_name="agent")
    details = models.JSONField(default=dict, blank=True, null=True, verbose_name="التفاصيل")

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
        if not scope and user and hasattr(user, 'profile'):
            scope = user.profile.scope

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
            try:
                target_model = None
                if '.' in self.model_name:
                    try:
                        target_model = apps.get_model(self.model_name)
                    except LookupError:
                        pass
                if not target_model:
                    import unicodedata
                    def normalize(s):
                        return unicodedata.normalize('NFKD', s).casefold() if s else ""
                    log_model_norm = normalize(self.model_name)
                    for model in apps.get_models():
                        if normalize(model._meta.verbose_name) == log_model_norm or \
                           normalize(model._meta.object_name) == log_model_norm:
                            target_model = model
                            break
                if target_model:
                    try:
                        related_object = target_model.objects.get(pk=self.object_id)
                    except target_model.DoesNotExist:
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
