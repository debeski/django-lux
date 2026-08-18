"""Abstract bases and custom fields every Dlux model builds on."""

from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.cache import cache
from ..system.constants import TABLE_DENSITY_VALUES
from ..managers import ScopedManager

from ._shared import logger


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
        try:
            obj = cache.get(cls.__name__)
        except Exception:
            # A corrupt or incompatible cache entry (e.g. a pickle written by an
            # older code revision after a dev hot-reload or a deploy that changed
            # this model) must never bubble up: callers such as get_system_config()
            # would then silently treat the system as unconfigured and bounce users
            # into the setup wizard. Drop the poisoned key and rebuild from the DB.
            logger.warning(
                "Discarding unreadable cache entry for singleton %s; rebuilding from DB.",
                cls.__name__,
                exc_info=True,
            )
            try:
                cache.delete(cls.__name__)
            except Exception:
                pass
            obj = None

        if obj is not None:
            # Check if object still exists in DB to prevent stale cache after DB wipes
            try:
                if not cls.objects.filter(pk=obj.pk).exists():
                    obj = None
            except Exception:
                obj = None

        if obj is not None:
            # Guard against a STALE-but-readable pickle written by an older model
            # revision — a dev hot-reload, or a deploy/migration that ADDED fields
            # (e.g. auth_config, notification_config). Such a pickle unpickles fine
            # (so the poisoned-key guard above never fires) but is missing the new
            # field attributes, so get_system_config()'s hasattr() guards silently
            # serve their DEFAULTS — the "settings reset, then return afterwards"
            # symptom. If any current concrete field is absent, rebuild from the DB.
            try:
                expected = {f.attname for f in cls._meta.concrete_fields}
                if not expected.issubset(vars(obj)):
                    logger.warning(
                        "Discarding stale cache entry for singleton %s (missing fields %s); rebuilding from DB.",
                        cls.__name__,
                        sorted(expected.difference(vars(obj))),
                    )
                    cache.delete(cls.__name__)
                    obj = None
            except Exception:
                try:
                    cache.delete(cls.__name__)
                except Exception:
                    pass
                obj = None

        if not obj:
            obj, created = cls.objects.get_or_create(pk=1)
            if created:
                # Seed from codebase DLUX_CONFIG if available
                config = getattr(settings, 'DLUX_CONFIG', {})
                try:
                    from ..utils.config import expand_system_config_groups

                    config = expand_system_config_groups(config)
                except Exception:
                    if not isinstance(config, dict):
                        config = {}
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
                if hasattr(obj, 'homepage_config') and isinstance(config.get('homepage_config'), dict):
                    obj.homepage_config = config.get('homepage_config')
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
                if hasattr(obj, 'search_config') and isinstance(config.get('search_config'), dict):
                    obj.search_config = config.get('search_config')
                if hasattr(obj, 'navbar_config') and isinstance(config.get('navbar'), dict):
                    obj.navbar_config = config.get('navbar')
                if hasattr(obj, 'notification_config'):
                    notifications = config.get('notifications', config.get('notification_config', None))
                    if isinstance(notifications, dict):
                        obj.notification_config = notifications
                if hasattr(obj, 'backup_config'):
                    backup = config.get('backup_config', config.get('backup'))
                    if isinstance(backup, dict):
                        obj.backup_config = backup
                if hasattr(obj, 'auth_config'):
                    auth = dict(obj.auth_config or {})
                    for auth_key in ('email_2fa', 'forgot_password_enabled', 'prevent_multiple_active_sessions', 'login_lockout_enabled', 'enforce_strong_passwords', 'purge_session_on_exit', 'inactivity_timeout_enabled'):
                        if auth_key in config:
                            auth[auth_key] = bool(config.get(auth_key))
                    for auth_key in (
                        'login_lockout_threshold',
                        'login_lockout_window_minutes',
                        'login_lockout_duration_minutes',
                        'strong_password_min_length',
                        'inactivity_timeout_minutes',
                    ):
                        if auth_key in config:
                            try:
                                auth[auth_key] = int(config.get(auth_key))
                            except (TypeError, ValueError):
                                pass
                    obj.auth_config = auth
                if hasattr(obj, 'public_root') and 'public_root' in config:
                    obj.public_root = bool(config.get('public_root'))
                if hasattr(obj, 'public_root_split_enabled') and 'public_root_split_enabled' in config:
                    obj.public_root_split_enabled = bool(config.get('public_root_split_enabled'))
                if hasattr(obj, 'public_root_url') and 'public_root_url' in config:
                    obj.public_root_url = str(config.get('public_root_url') or '').strip()
                if hasattr(obj, 'public_root_theme') and 'public_root_theme' in config:
                    obj.public_root_theme = str(config.get('public_root_theme') or '').strip()
                if hasattr(obj, 'public_root_title') and 'public_root_title' in config:
                    obj.public_root_title = str(config.get('public_root_title') or '').strip()
                if hasattr(obj, 'public_root_meta_description') and 'public_root_meta_description' in config:
                    obj.public_root_meta_description = str(config.get('public_root_meta_description') or '').strip()
                if hasattr(obj, 'show_titlebar_on_public') and 'show_titlebar_on_public' in config:
                    obj.show_titlebar_on_public = bool(config.get('show_titlebar_on_public'))
                if hasattr(obj, 'show_sidebar_on_public') and 'show_sidebar_on_public' in config:
                    obj.show_sidebar_on_public = bool(config.get('show_sidebar_on_public'))
                if hasattr(obj, 'public_registration_enabled') and 'public_registration_enabled' in config:
                    obj.public_registration_enabled = bool(config.get('public_registration_enabled'))
                if hasattr(obj, 'registration_activation_mode') and config.get('registration_activation_mode'):
                    obj.registration_activation_mode = config.get('registration_activation_mode')
                if hasattr(obj, 'registration_throttle_enabled') and 'registration_throttle_enabled' in config:
                    obj.registration_throttle_enabled = bool(config.get('registration_throttle_enabled'))
                if hasattr(obj, 'honeypot_enabled') and 'honeypot_enabled' in config:
                    obj.honeypot_enabled = bool(config.get('honeypot_enabled'))
                for _reg_url_key in ('privacy_policy_url', 'terms_url', 'privacy_notice_text'):
                    if hasattr(obj, _reg_url_key) and _reg_url_key in config:
                        setattr(obj, _reg_url_key, str(config.get(_reg_url_key) or '').strip())
                if hasattr(obj, 'registration_require_consent') and 'registration_require_consent' in config:
                    obj.registration_require_consent = bool(config.get('registration_require_consent'))
                if hasattr(obj, 'default_form_density') and config.get('default_form_density') in TABLE_DENSITY_VALUES:
                    obj.default_form_density = config.get('default_form_density')
                if hasattr(obj, 'default_modal_size') and 'default_modal_size' in config:
                    obj.default_modal_size = config.get('default_modal_size')
                if hasattr(obj, 'sticky_table_headers') and 'sticky_table_headers' in config:
                    obj.sticky_table_headers = bool(config.get('sticky_table_headers'))
                if hasattr(obj, 'resizable_table_columns') and 'resizable_table_columns' in config:
                    obj.resizable_table_columns = bool(config.get('resizable_table_columns'))
                if hasattr(obj, 'zebra_striping') and 'zebra_striping' in config:
                    obj.zebra_striping = bool(config.get('zebra_striping'))
                if hasattr(obj, 'show_audit_fields') and 'show_audit_fields' in config:
                    obj.show_audit_fields = bool(config.get('show_audit_fields'))
                if hasattr(obj, 'show_soft_deleted') and 'show_soft_deleted' in config:
                    obj.show_soft_deleted = bool(config.get('show_soft_deleted'))
                if hasattr(obj, 'allowed_fonts') and isinstance(config.get('allowed_fonts'), (list, tuple, set)):
                    obj.allowed_fonts = list(config.get('allowed_fonts'))
                if hasattr(obj, 'default_fonts') and isinstance(config.get('default_fonts'), dict):
                    obj.default_fonts = config.get('default_fonts')
                if hasattr(obj, 'allow_user_font_override') and 'allow_user_font_override' in config:
                    obj.allow_user_font_override = bool(config.get('allow_user_font_override'))
                obj.save()
            try:
                cache.set(cls.__name__, obj, timeout=86400)
            except Exception:
                logger.warning("Failed to cache singleton %s; serving DB value uncached.", cls.__name__, exc_info=True)
        return obj

    def refresh_cache(self):
         try:
             cache.set(self.__class__.__name__, self, timeout=86400)
         except Exception:
             logger.warning("Failed to refresh cache for singleton %s.", self.__class__.__name__, exc_info=True)
         if self.__class__.__name__ == 'SystemSettings':
             try:
                 from ..context_processors import clear_sidebar_cache
                 clear_sidebar_cache()
             except Exception:
                 pass


class ScopeForeignKey(models.ForeignKey):
    """
    ForeignKey that hides itself from ModelForms when scopes are disabled.
    Keeps schema identical to a normal ForeignKey.
    """

    def formfield(self, **kwargs):
        # Always return a real form field.
        # Visibility is managed globally by dlux.patches.
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
    scope = ScopeForeignKey('dlux.Scope', on_delete=models.PROTECT, null=True, blank=True, verbose_name="Scope")

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
        from ..middleware import get_current_user
        user = get_current_user()
        if user and hasattr(user, 'is_authenticated') and user.is_authenticated:
            if not self.pk:
                if not self.created_by_id:
                    self.created_by = user
                # Auto-set scope from user's profile if not explicitly set
                if not self.scope_id and hasattr(user, 'profile') and user.profile.scope_id:
                    from ..utils import is_scope_enabled
                    if is_scope_enabled():
                        self.scope_id = user.profile.scope_id
            self.updated_by = user
        super().save(*args, **kwargs)

    def delete(self, using=None, keep_parents=False):
        """Override: ALL deletes become soft-deletes. Actor auto-detected."""
        from ..middleware import get_current_user
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

    def validate_unique(self, exclude=None):
        """Uniqueness must ignore soft-deleted rows even while a superadmin is in
        the "show soft-deleted" review mode — otherwise a deleted row could
        falsely block reusing its unique value."""
        from ..managers import force_hide_deleted
        with force_hide_deleted():
            super().validate_unique(exclude=exclude)


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
                    from dlux.utils import get_system_config
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
