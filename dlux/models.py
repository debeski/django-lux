# Imports of the required python modules and libraries
######################################################
import logging
from django.apps import apps
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.core.cache import cache
from django.core.files.base import ContentFile
from .system.constants import (
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
    TABLE_DENSITY_VALUES,
)
from .managers import ScopedManager
from .system.defaults import (
    default_auth_config as _default_auth_config,
    default_backup_config as _default_backup_config,
    default_client_ip_config as _default_client_ip_config,
    default_email_config as _default_email_config,
    default_extra_config as _default_extra_config,
    default_language_config as _default_language_config,
    default_layout_config as _default_layout_config,
    default_login_config as _default_login_config,
    default_navbar_config as _default_navbar_config,
    default_notification_config as _default_notification_config,
    default_public_root_config as _default_public_root_config,
    default_registration_config as _default_registration_config,
    default_theme_config as _default_theme_config,
    default_titlebar_config as _default_titlebar_config,
    default_typography_config as _default_typography_config,
    default_log_config as _default_log_config,
    default_profile_config as _default_profile_config,
)
from .system.registry import get_config_defaults, get_flat_config_fields
import hashlib
import io
import secrets
from datetime import timedelta
from PIL import Image

logger = logging.getLogger('dlux')


def default_allowed_fonts():
    return _default_typography_config()['allowed_fonts']


def default_allowed_themes():
    return _default_theme_config()['allowed_themes']


def default_titlebar_config():
    return _default_titlebar_config()


def default_navbar_config():
    return _default_navbar_config()


def default_auth_config():
    """Authentication & session-security policy, consolidated into one JSON field."""
    return _default_auth_config()


def default_backup_config():
    return _default_backup_config()


def default_email_config():
    return _default_email_config()


def default_registration_config():
    return _default_registration_config()


def default_public_root_config():
    return _default_public_root_config()


def default_client_ip_config():
    return _default_client_ip_config()


def default_notification_config():
    return _default_notification_config()


def default_layout_config():
    return _default_layout_config()


def default_language_config():
    return _default_language_config()


def default_theme_config():
    return _default_theme_config()


def default_typography_config():
    return _default_typography_config()


def default_login_config():
    return _default_login_config()


def default_extra_config():
    return _default_extra_config()


def default_log_config():
    return _default_log_config()


def default_profile_config():
    return _default_profile_config()


class Scope(models.Model):
    name = models.CharField(max_length=100, verbose_name="Scope")
    description = models.TextField(blank=True, null=True, verbose_name="Description")
    is_public_registration_default = models.BooleanField(
        default=False,
        db_default=False,
        verbose_name="Default for Public Registration",
    )

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


class GroupProfile(models.Model):
    """
    Metadata sidecar for a Django auth ``Group`` used as a reusable permission
    PRESET. The Group itself owns the name + permissions bundle (and therefore
    feeds ``user.has_perm`` via native group inheritance); this model only adds
    the description, optional scope binding, active flag, and audit trail that
    the native Group lacks. Purely additive — a Group without a profile still
    works as a plain preset.
    """
    group = models.OneToOneField(
        'auth.Group', on_delete=models.CASCADE, related_name='dlux_profile',
        verbose_name="Group",
    )
    description = models.CharField(max_length=255, blank=True, verbose_name="Description")
    # A preset may be global (scope NULL) or bound to a single Scope. Plain FK
    # (not ScopeForeignKey) so a preset's scope is chosen explicitly on the
    # preset form rather than auto-derived from the acting admin's own scope.
    scope = models.ForeignKey(
        'dlux.Scope', on_delete=models.PROTECT, null=True, blank=True,
        related_name='group_presets', verbose_name="Scope",
    )
    is_active = models.BooleanField(default=True, verbose_name="Active")
    is_public_registration_default = models.BooleanField(
        default=False,
        db_default=False,
        verbose_name="Default for Public Registration",
    )
    created_at = models.DateTimeField(auto_now_add=True, editable=False, verbose_name="Created At")
    updated_at = models.DateTimeField(auto_now=True, editable=False, verbose_name="Updated At")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, related_name='+',
        on_delete=models.SET_NULL, editable=False, verbose_name="Created By",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, related_name='+',
        on_delete=models.SET_NULL, editable=False, verbose_name="Updated By",
    )

    class Meta:
        verbose_name = "Group Preset"
        verbose_name_plural = "Group Presets"
        default_permissions = ()
        # Host the manage_groups permission on this NEW model (not the existing
        # Profile) so it ships inside CreateModel.options — keeping the release
        # migration inline-safe (no AlterModelOptions). Codename resolves as
        # `dlux.manage_groups` either way (both models are in the dlux app).
        permissions = [
            ("manage_groups", "Can manage permission groups"),
        ]

    def __str__(self):
        return self.group.name


class GroupMembership(models.Model):
    """
    Audit/history record of a user's membership in a permission-preset Group.
    Django's implicit ``user_groups`` M2M carries no timestamp or actor; this
    parallel row records WHO assigned the user to WHICH preset and WHEN, and
    backs the "users assigned to groups" view. The Group's ``user_set`` stays
    the source of truth for permission resolution — this table is kept in sync
    by ``dlux.utils.users.set_user_group_presets``.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='group_memberships', verbose_name="User",
    )
    group = models.ForeignKey(
        'auth.Group', on_delete=models.CASCADE,
        related_name='dlux_memberships', verbose_name="Group",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, related_name='+',
        on_delete=models.SET_NULL, verbose_name="Assigned By",
    )
    assigned_at = models.DateTimeField(auto_now_add=True, verbose_name="Assigned At")

    class Meta:
        verbose_name = "Group Membership"
        verbose_name_plural = "Group Memberships"
        default_permissions = ()
        unique_together = ('user', 'group')
        ordering = ['-assigned_at']

    def __str__(self):
        return f"{self.user} → {self.group}"


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
                    from .utils.config import expand_system_config_groups

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
                    for auth_key in ('email_2fa', 'prevent_multiple_active_sessions', 'login_lockout_enabled', 'enforce_strong_passwords', 'purge_session_on_exit', 'inactivity_timeout_enabled'):
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
                if hasattr(obj, 'zebra_striping') and 'zebra_striping' in config:
                    obj.zebra_striping = bool(config.get('zebra_striping'))
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
                 from .context_processors import clear_sidebar_cache
                 clear_sidebar_cache()
             except Exception:
                 pass


_SYSTEM_SETTINGS_CONFIG_DEFAULTS = get_config_defaults()

_SYSTEM_SETTINGS_FLAT_CONFIG_FIELDS = get_flat_config_fields()


def _system_settings_config_get(instance, config_field, key):
    config = getattr(instance, config_field, None)
    if not isinstance(config, dict):
        config = {}
    default_factory = _SYSTEM_SETTINGS_CONFIG_DEFAULTS.get(config_field, dict)
    defaults = default_factory()
    return config.get(key, defaults.get(key))


def _system_settings_config_set(instance, config_field, key, value):
    config = getattr(instance, config_field, None)
    if not isinstance(config, dict):
        config = {}
    config = dict(config)
    config[key] = value
    setattr(instance, config_field, config)


def _system_settings_config_property(config_field, key):
    return property(
        lambda self: _system_settings_config_get(self, config_field, key),
        lambda self, value: _system_settings_config_set(self, config_field, key, value),
    )


class SystemSettings(SingletonModel):
    system_names = models.JSONField(default=dict, blank=True, verbose_name="System Names by Language")
    logo = models.ImageField(upload_to='dlux/branding/', null=True, blank=True, verbose_name="System Logo (Logo)")
    favicon = models.ImageField(upload_to='dlux/branding/', null=True, blank=True, verbose_name="Site Icon (Favicon)")
    default_language = models.CharField(max_length=10, default='en', verbose_name="Default Language")
    default_theme = models.CharField(max_length=20, default='light', verbose_name="Default Theme")
    home_url = models.CharField(max_length=255, default=DEFAULT_HOME_URL, verbose_name="Home URL")
    is_configured = models.BooleanField(default=False, verbose_name="Is Configured")
    auth_config = models.JSONField(default=default_auth_config, blank=True, verbose_name="Authentication Configuration")
    email_config = models.JSONField(default=default_email_config, blank=True, verbose_name="Email Configuration")
    registration_config = models.JSONField(default=default_registration_config, blank=True, verbose_name="Registration Configuration")
    public_root_config = models.JSONField(default=default_public_root_config, blank=True, verbose_name="Public Root Configuration")
    client_ip_config = models.JSONField(default=default_client_ip_config, blank=True, verbose_name="Client IP Configuration")
    notification_config = models.JSONField(default=default_notification_config, blank=True, verbose_name="Notification Configuration")
    layout_config = models.JSONField(default=default_layout_config, blank=True, verbose_name="Layout Configuration")
    language_config = models.JSONField(default=default_language_config, blank=True, verbose_name="Language Configuration")
    theme_config = models.JSONField(default=default_theme_config, blank=True, verbose_name="Theme Configuration")
    typography_config = models.JSONField(default=default_typography_config, blank=True, verbose_name="Typography Configuration")
    login_config = models.JSONField(default=default_login_config, blank=True, verbose_name="Login Page Configuration")
    titlebar_config = models.JSONField(default=default_titlebar_config, blank=True, verbose_name="Titlebar Configuration")
    sidebar_config = models.JSONField(default=dict, blank=True, verbose_name="Sidebar Configuration")
    navbar_config = models.JSONField(default=default_navbar_config, blank=True, verbose_name="Nav Bar Configuration")
    log_config = models.JSONField(default=default_log_config, blank=True, verbose_name="Logging Configuration")
    profile_config = models.JSONField(default=default_profile_config, blank=True, verbose_name="Profile Page Configuration")
    backup_config = models.JSONField(default=default_backup_config, blank=True, verbose_name="Backup Configuration")
    extra_config = models.JSONField(default=default_extra_config, blank=True, verbose_name="Extra Configuration")

    class Meta:
        verbose_name = "System Settings"
        verbose_name_plural = "System Settings"

    def __str__(self):
        return "System Settings"

    def save(self, *args, **kwargs):
        update_fields = kwargs.get('update_fields')
        if update_fields is not None:
            normalized_update_fields = []
            for field_name in update_fields:
                config_field = _SYSTEM_SETTINGS_FLAT_CONFIG_FIELDS.get(field_name, (field_name, None))[0]
                if config_field not in normalized_update_fields:
                    normalized_update_fields.append(config_field)
            kwargs['update_fields'] = normalized_update_fields
        super().save(*args, **kwargs)


for _flat_name, (_config_field, _config_key) in _SYSTEM_SETTINGS_FLAT_CONFIG_FIELDS.items():
    setattr(SystemSettings, _flat_name, _system_settings_config_property(_config_field, _config_key))


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


class DluxNotification(ScopedModel):
    """Durable user-facing notification event."""

    LEVEL_INFO = 'info'
    LEVEL_SUCCESS = 'success'
    LEVEL_WARNING = 'warning'
    LEVEL_ERROR = 'error'
    LEVEL_CHOICES = (
        (LEVEL_INFO, 'Info'),
        (LEVEL_SUCCESS, 'Success'),
        (LEVEL_WARNING, 'Warning'),
        (LEVEL_ERROR, 'Error'),
    )

    AUDIENCE_ACTOR = 'actor'
    AUDIENCE_WATCHERS = 'watchers'
    AUDIENCE_USERS = 'users'
    AUDIENCE_BROADCAST = 'broadcast'
    AUDIENCE_CHOICES = (
        (AUDIENCE_ACTOR, 'Actor'),
        (AUDIENCE_WATCHERS, 'Watchers'),
        (AUDIENCE_USERS, 'Specific Users'),
        (AUDIENCE_BROADCAST, 'Broadcast'),
    )

    title = models.CharField(max_length=180, blank=True, verbose_name="Title")
    message = models.TextField(verbose_name="Message")
    level = models.CharField(max_length=16, choices=LEVEL_CHOICES, default=LEVEL_INFO, db_index=True, verbose_name="Level")
    category = models.CharField(max_length=64, default='general', db_index=True, verbose_name="Category")
    source = models.CharField(max_length=64, default='manual', db_index=True, verbose_name="Source")
    action = models.CharField(max_length=64, blank=True, db_index=True, verbose_name="Action")
    source_model = models.CharField(max_length=120, blank=True, verbose_name="Source Model")
    source_model_key = models.CharField(max_length=120, blank=True, db_index=True, verbose_name="Source Model Key")
    source_object_id = models.CharField(max_length=64, blank=True, db_index=True, verbose_name="Source Object ID")
    source_label = models.CharField(max_length=255, blank=True, verbose_name="Source Label")
    target_url = models.CharField(max_length=512, blank=True, verbose_name="Target URL")
    request_path = models.CharField(max_length=512, blank=True, verbose_name="Request Path")
    audience_type = models.CharField(max_length=24, choices=AUDIENCE_CHOICES, default=AUDIENCE_ACTOR, verbose_name="Audience Type")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="Metadata")
    expires_at = models.DateTimeField(blank=True, null=True, db_index=True, verbose_name="Expires At")

    class Meta:
        verbose_name = "Dlux Notification"
        verbose_name_plural = "Dlux Notifications"
        default_permissions = ()
        indexes = [
            models.Index(fields=['created_at'], name='dlux_notif_created_idx'),
            models.Index(fields=['scope', 'created_at'], name='dlux_notif_scope_created_idx'),
            models.Index(fields=['level', 'created_at'], name='dlux_notif_level_created_idx'),
            models.Index(fields=['source_model_key', 'created_at'], name='dlux_notif_model_created_idx'),
            models.Index(fields=['action', 'created_at'], name='dlux_notif_action_created_idx'),
        ]
        permissions = [
            ('view_notification', 'View notifications'),
            ('manage_notifications', 'Manage notification rules and watches'),
        ]

    def __str__(self):
        return self.title or self.message[:80]


class DluxNotificationState(models.Model):
    """Per-user state for a notification."""

    notification = models.ForeignKey(
        'dlux.DluxNotification',
        related_name='states',
        on_delete=models.CASCADE,
        verbose_name="Notification",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='dlux_notification_states',
        on_delete=models.CASCADE,
        verbose_name="User",
    )
    read_at = models.DateTimeField(blank=True, null=True, db_index=True, verbose_name="Read At")
    dismissed_at = models.DateTimeField(blank=True, null=True, db_index=True, verbose_name="Dismissed At")
    emailed_at = models.DateTimeField(blank=True, null=True, verbose_name="Emailed At")
    email_status = models.CharField(max_length=32, blank=True, verbose_name="Email Status")
    email_error = models.TextField(blank=True, verbose_name="Email Error")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated At")

    class Meta:
        verbose_name = "Dlux Notification State"
        verbose_name_plural = "Dlux Notification States"
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(fields=['notification', 'user'], name='dlux_notif_state_user_uniq'),
        ]
        indexes = [
            models.Index(fields=['user', 'read_at'], name='dlux_ns_read_idx'),
            models.Index(fields=['user', 'dismissed_at'], name='dlux_ns_dismiss_idx'),
            models.Index(fields=['user', 'created_at'], name='dlux_ns_created_idx'),
        ]

    def __str__(self):
        return f"{self.user} / {self.notification_id}"


class DluxNotificationRule(ScopedModel):
    """Admin-configured routing rule for notification events."""

    name = models.CharField(max_length=120, verbose_name="Name")
    enabled = models.BooleanField(default=True, db_index=True, verbose_name="Enabled")
    priority = models.IntegerField(default=100, db_index=True, verbose_name="Priority")
    match_config = models.JSONField(default=dict, blank=True, verbose_name="Match Configuration")
    delivery_config = models.JSONField(default=dict, blank=True, verbose_name="Delivery Configuration")
    stop_processing = models.BooleanField(default=False, verbose_name="Stop Processing")

    class Meta:
        verbose_name = "Dlux Notification Rule"
        verbose_name_plural = "Dlux Notification Rules"
        default_permissions = ()
        ordering = ['priority', 'name']
        indexes = [
            models.Index(fields=['enabled', 'priority'], name='dlux_notif_rule_enabled_idx'),
            models.Index(fields=['scope', 'priority'], name='dlux_notif_rule_scope_idx'),
        ]

    def __str__(self):
        return self.name


class DluxNotificationWatch(ScopedModel):
    """Model-level notification watch for a user and optional scope."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='dlux_notification_watches',
        on_delete=models.CASCADE,
        verbose_name="User",
    )
    model_key = models.CharField(max_length=120, db_index=True, verbose_name="Model Key")
    enabled = models.BooleanField(default=True, db_index=True, verbose_name="Enabled")
    email_enabled = models.BooleanField(default=False, verbose_name="Email Enabled")

    class Meta:
        verbose_name = "Dlux Notification Watch"
        verbose_name_plural = "Dlux Notification Watches"
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(fields=['user', 'scope', 'model_key'], name='dlux_nw_user_scope_model'),
        ]
        indexes = [
            models.Index(fields=['model_key', 'enabled'], name='dlux_nw_model_idx'),
            models.Index(fields=['scope', 'model_key'], name='dlux_nw_scope_model_idx'),
        ]

    def __str__(self):
        return f"{self.user} watches {self.model_key}"


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
            ("view_reports", "Can view reports"),
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
            from .utils import set_user_group_presets
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


def generate_report_backup_token():
    return secrets.token_urlsafe(32)


class ReportBackup(models.Model):
    """A requested reports backup zip build (background via Celery when available).

    State is kept in the DB so the requesting web process and the worker only
    need a shared database + shared default storage to hand off the result.
    """

    STATUS_PENDING = 'pending'
    STATUS_RUNNING = 'running'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_RUNNING, 'Running'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_FAILED, 'Failed'),
    ]

    token = models.CharField(
        max_length=64,
        unique=True,
        default=generate_report_backup_token,
        editable=False,
        verbose_name="Token",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='dlux_report_backups',
        verbose_name="User",
    )
    window = models.CharField(max_length=10, default='all', verbose_name="Window")
    status = models.CharField(
        max_length=12,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
        verbose_name="Status",
    )
    file_path = models.CharField(max_length=512, blank=True, verbose_name="File Path")
    file_size = models.BigIntegerField(default=0, verbose_name="File Size")
    model_count = models.PositiveIntegerField(default=0, verbose_name="Model Count")
    file_count = models.PositiveIntegerField(default=0, verbose_name="File Count")
    missing_file_count = models.PositiveIntegerField(default=0, verbose_name="Missing File Count")
    progress_percent = models.PositiveSmallIntegerField(
        default=0,
        db_default=0,
        verbose_name="Progress Percent",
    )
    progress_message = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_default="",
        verbose_name="Progress Message",
    )
    error = models.TextField(blank=True, verbose_name="Error")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    started_at = models.DateTimeField(blank=True, null=True, verbose_name="Started At")
    completed_at = models.DateTimeField(blank=True, null=True, verbose_name="Completed At")

    class Meta:
        verbose_name = "Report Backup"
        verbose_name_plural = "Report Backups"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user} backup ({self.window}, {self.status})"


class SystemBackup(models.Model):
    """A full encrypted system snapshot (.dlb) — separate from the reports backup.

    Stores the requesting username as plain text (no user FK): a restore wipes
    and replaces the user table inside one transaction, so these bookkeeping
    rows must not reference it.
    """

    STATUS_PENDING = 'pending'
    STATUS_RUNNING = 'running'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_RUNNING, 'Running'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_FAILED, 'Failed'),
    ]
    TRIGGER_MANUAL = 'manual'
    TRIGGER_SCHEDULED = 'scheduled'
    TRIGGER_UPDATE = 'update'
    TRIGGER_CHOICES = [
        (TRIGGER_MANUAL, 'Manual'),
        (TRIGGER_SCHEDULED, 'Scheduled'),
        (TRIGGER_UPDATE, 'DjangoLux update'),
    ]

    token = models.CharField(
        max_length=64,
        unique=True,
        default=generate_report_backup_token,
        editable=False,
        verbose_name="Token",
    )
    requested_by_username = models.CharField(max_length=150, blank=True, verbose_name="Requested By")
    trigger = models.CharField(
        max_length=12,
        choices=TRIGGER_CHOICES,
        default=TRIGGER_MANUAL,
        # db_default keeps a persistent database-level default so a *previous*
        # release's code (which has no `trigger` field) can still INSERT a
        # SystemBackup row after this migration is applied — e.g. the updater's
        # pre-update backup step running under the old code after a rollback.
        # A plain Python `default` alone is dropped from the column by Django and
        # would make those inserts violate the NOT NULL constraint.
        db_default=TRIGGER_MANUAL,
        db_index=True,
        verbose_name="Trigger",
    )
    status = models.CharField(
        max_length=12,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
        verbose_name="Status",
    )
    # Whether this snapshot includes uploaded media blobs. False = a fast data-only
    # backup (database + migration state only). The runner reads this off the row so
    # the choice survives a Celery handoff (the task only receives the pk). db_default
    # keeps it insert-safe for any code that doesn't set it.
    media_included = models.BooleanField(default=True, db_default=True, verbose_name="Media Included")
    file_path = models.CharField(max_length=512, blank=True, verbose_name="File Path")
    file_size = models.BigIntegerField(default=0, verbose_name="File Size")
    model_count = models.PositiveIntegerField(default=0, verbose_name="Model Count")
    row_count = models.PositiveIntegerField(default=0, verbose_name="Row Count")
    file_count = models.PositiveIntegerField(default=0, verbose_name="File Count")
    missing_file_count = models.PositiveIntegerField(default=0, verbose_name="Missing File Count")
    progress_percent = models.PositiveSmallIntegerField(
        default=0,
        db_default=0,
        verbose_name="Progress Percent",
    )
    progress_message = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_default="",
        verbose_name="Progress Message",
    )
    passphrase_required = models.BooleanField(default=False, verbose_name="Passphrase Required")
    error = models.TextField(blank=True, verbose_name="Error")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    started_at = models.DateTimeField(blank=True, null=True, verbose_name="Started At")
    completed_at = models.DateTimeField(blank=True, null=True, verbose_name="Completed At")

    class Meta:
        verbose_name = "System Backup"
        verbose_name_plural = "System Backups"
        ordering = ['-created_at']

    def __str__(self):
        return f"system backup {self.token[:8]} ({self.status})"


class SystemRestore(models.Model):
    """A full-replace restore run from an .dlb file (same no-user-FK rule as SystemBackup)."""

    STATUS_PENDING = 'pending'
    STATUS_RUNNING = 'running'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_RUNNING, 'Running'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_FAILED, 'Failed'),
    ]

    token = models.CharField(
        max_length=64,
        unique=True,
        default=generate_report_backup_token,
        editable=False,
        verbose_name="Token",
    )
    requested_by_username = models.CharField(max_length=150, blank=True, verbose_name="Requested By")
    backup_file_path = models.CharField(max_length=512, verbose_name="Backup File Path")
    ignore_version_mismatch = models.BooleanField(default=False, verbose_name="Ignore Version Mismatch")
    status = models.CharField(
        max_length=12,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
        verbose_name="Status",
    )
    report = models.JSONField(default=dict, blank=True, verbose_name="Report")
    error = models.TextField(blank=True, verbose_name="Error")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    started_at = models.DateTimeField(blank=True, null=True, verbose_name="Started At")
    completed_at = models.DateTimeField(blank=True, null=True, verbose_name="Completed At")

    class Meta:
        verbose_name = "System Restore"
        verbose_name_plural = "System Restores"
        ordering = ['-created_at']

    def __str__(self):
        return f"system restore {self.token[:8]} ({self.status})"


class DluxUpdateState(models.Model):
    """Singleton mirror of the active runtime release and last verified update."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    baked_version = models.CharField(max_length=32, blank=True, verbose_name="Baked Version")
    active_version = models.CharField(max_length=32, blank=True, verbose_name="Active Version")
    active_wheel_url = models.TextField(blank=True, verbose_name="Active Wheel URL")
    active_wheel_sha256 = models.CharField(max_length=64, blank=True, verbose_name="Active Wheel SHA256")
    active_manifest = models.JSONField(default=dict, blank=True, verbose_name="Active Manifest")
    previous_version = models.CharField(max_length=32, blank=True, verbose_name="Previous Version")
    previous_wheel_url = models.TextField(blank=True, verbose_name="Previous Wheel URL")
    previous_wheel_sha256 = models.CharField(max_length=64, blank=True, verbose_name="Previous Wheel SHA256")
    previous_manifest = models.JSONField(default=dict, blank=True, verbose_name="Previous Manifest")
    latest_version = models.CharField(max_length=32, blank=True, verbose_name="Latest Version")
    latest_wheel_url = models.TextField(blank=True, verbose_name="Latest Wheel URL")
    latest_wheel_sha256 = models.CharField(max_length=64, blank=True, verbose_name="Latest Wheel SHA256")
    latest_manifest = models.JSONField(default=dict, blank=True, verbose_name="Latest Manifest")
    latest_compatible = models.BooleanField(default=False, verbose_name="Latest Compatible")
    latest_reason = models.TextField(blank=True, verbose_name="Latest Compatibility Reason")
    last_checked_at = models.DateTimeField(blank=True, null=True, verbose_name="Last Checked At")
    last_check_error = models.TextField(blank=True, verbose_name="Last Check Error")
    generation = models.PositiveBigIntegerField(default=0, verbose_name="Runtime Generation")
    degraded = models.BooleanField(default=False, verbose_name="Runtime Degraded")
    degraded_reason = models.TextField(blank=True, verbose_name="Runtime Degraded Reason")
    active_run_token = models.CharField(max_length=64, blank=True, db_index=True, verbose_name="Active Run Token")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated At")

    class Meta:
        verbose_name = "Dlux Update State"
        verbose_name_plural = "Dlux Update State"

    @classmethod
    def load(cls):
        from . import __version__
        from .updater import get_baked_version

        obj, _created = cls.objects.get_or_create(
            pk=1,
            defaults={
                'baked_version': get_baked_version(),
                'active_version': __version__,
            },
        )
        return obj

    def save(self, *args, **kwargs):
        self.pk = 1
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        return None

    def __str__(self):
        return f"Dlux updater ({self.active_version or self.baked_version or 'unknown'})"


class DluxUpdateRun(models.Model):
    """Durable check/apply/rollback request consumed by the isolated update worker."""

    ACTION_CHECK = 'check'
    ACTION_APPLY = 'apply'
    ACTION_ROLLBACK = 'rollback'
    ACTION_CHOICES = [
        (ACTION_CHECK, 'Check'),
        (ACTION_APPLY, 'Apply'),
        (ACTION_ROLLBACK, 'Rollback'),
    ]

    BACKUP_FULL = 'full'
    BACKUP_DATA = 'data'
    BACKUP_SKIP = 'skip'
    BACKUP_MODE_CHOICES = [
        (BACKUP_FULL, 'Full (database + media)'),
        (BACKUP_DATA, 'Quick (data only)'),
        (BACKUP_SKIP, 'Skip backup'),
    ]

    STATUS_QUEUED = 'queued'
    STATUS_CHECKING = 'checking'
    STATUS_DOWNLOADING = 'downloading'
    STATUS_VERIFYING = 'verifying'
    STATUS_STAGING = 'staging'
    STATUS_PREFLIGHT = 'preflight'
    STATUS_BACKING_UP = 'backing_up'
    STATUS_MAINTENANCE = 'maintenance'
    STATUS_MIGRATING = 'migrating'
    STATUS_COLLECTING_STATIC = 'collecting_static'
    STATUS_SWITCHING = 'switching'
    STATUS_RESTARTING = 'restarting'
    STATUS_VERIFYING_HEALTH = 'verifying_health'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    STATUS_ROLLED_BACK = 'rolled_back'
    STATUS_CHOICES = [
        (STATUS_QUEUED, 'Queued'),
        (STATUS_CHECKING, 'Checking'),
        (STATUS_DOWNLOADING, 'Downloading'),
        (STATUS_VERIFYING, 'Verifying'),
        (STATUS_STAGING, 'Staging'),
        (STATUS_PREFLIGHT, 'Preflight'),
        (STATUS_BACKING_UP, 'Backing Up'),
        (STATUS_MAINTENANCE, 'Maintenance'),
        (STATUS_MIGRATING, 'Migrating'),
        (STATUS_COLLECTING_STATIC, 'Collecting Static'),
        (STATUS_SWITCHING, 'Switching'),
        (STATUS_RESTARTING, 'Restarting'),
        (STATUS_VERIFYING_HEALTH, 'Verifying Health'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_ROLLED_BACK, 'Rolled Back'),
    ]

    token = models.CharField(
        max_length=64,
        unique=True,
        default=generate_report_backup_token,
        editable=False,
        verbose_name="Token",
    )
    action = models.CharField(max_length=16, choices=ACTION_CHOICES, db_index=True, verbose_name="Action")
    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default=STATUS_QUEUED,
        db_index=True,
        verbose_name="Status",
    )
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="Active")
    source_version = models.CharField(max_length=32, blank=True, verbose_name="Source Version")
    target_version = models.CharField(max_length=32, blank=True, verbose_name="Target Version")
    requested_by_username = models.CharField(max_length=150, blank=True, verbose_name="Requested By")
    manifest = models.JSONField(default=dict, blank=True, verbose_name="Verified Manifest")
    wheel_url = models.TextField(blank=True, verbose_name="Wheel URL")
    wheel_sha256 = models.CharField(max_length=64, blank=True, verbose_name="Wheel SHA256")
    # Operator's pre-update backup choice, read by the worker off the row (the run is
    # processed asynchronously). db_default keeps it insert-safe for older code.
    backup_mode = models.CharField(
        max_length=8,
        choices=BACKUP_MODE_CHOICES,
        default=BACKUP_DATA,
        db_default=BACKUP_DATA,
        verbose_name="Backup Mode",
    )
    backup_token = models.CharField(max_length=64, blank=True, verbose_name="Backup Token")
    progress_log = models.TextField(blank=True, verbose_name="Progress Log")
    report = models.JSONField(default=dict, blank=True, verbose_name="Report")
    error = models.TextField(blank=True, verbose_name="Error")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    started_at = models.DateTimeField(blank=True, null=True, verbose_name="Started At")
    completed_at = models.DateTimeField(blank=True, null=True, verbose_name="Completed At")

    class Meta:
        verbose_name = "Dlux Update Run"
        verbose_name_plural = "Dlux Update Runs"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['is_active', 'created_at'], name='dlux_update_active_idx'),
        ]

    def append_log(self, message):
        line = str(message or '').replace('\x00', '').strip()
        if not line:
            return
        combined = f"{self.progress_log}\n{line}".strip()
        self.progress_log = combined[-65536:]

    def finish(self, status, *, error='', report=None):
        self.status = status
        self.is_active = False
        self.completed_at = timezone.now()
        self.error = str(error or '')[:4000]
        if report is not None:
            self.report = report

    def __str__(self):
        return f"Dlux {self.action} {self.target_version or self.source_version} ({self.status})"


class DluxImageUpdate(models.Model):
    """Image-level (full container) update request, executed by the external
    composer-updater rather than the inline wheel worker.

    Deliberately SEPARATE from DluxUpdateRun so the battle-tested inline update
    worker/recovery state machine is never disturbed. Lifecycle is driven by
    ``UpdateService.tick_image_update()`` from the same worker loop: pending →
    backing_up → awaiting_recreate → (composer recreates this container) →
    completed/failed, finalized by reading composer's ``deploy-status.json``.
    Backup-mode values intentionally mirror ``DluxUpdateRun`` so the shared
    ``_create_backup`` helper can be reused unchanged.
    """

    BACKUP_FULL = 'full'
    BACKUP_DATA = 'data'
    BACKUP_SKIP = 'skip'
    BACKUP_MODE_CHOICES = [
        (BACKUP_FULL, 'Full (database + media)'),
        (BACKUP_DATA, 'Quick (data only)'),
        (BACKUP_SKIP, 'Skip backup'),
    ]

    STATUS_PENDING = 'pending'
    STATUS_BACKING_UP = 'backing_up'
    STATUS_AWAITING_RECREATE = 'awaiting_recreate'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_BACKING_UP, 'Backing Up'),
        (STATUS_AWAITING_RECREATE, 'Awaiting Recreate'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_FAILED, 'Failed'),
    ]
    TERMINAL_STATUSES = frozenset({STATUS_COMPLETED, STATUS_FAILED})

    token = models.CharField(
        max_length=64,
        unique=True,
        default=generate_report_backup_token,
        editable=False,
        verbose_name="Token",
    )
    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
        verbose_name="Status",
    )
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="Active")
    source_version = models.CharField(max_length=32, blank=True, verbose_name="Source Version")
    target_version = models.CharField(max_length=32, blank=True, verbose_name="Target Version")
    requested_by_username = models.CharField(max_length=150, blank=True, verbose_name="Requested By")
    backup_mode = models.CharField(
        max_length=8,
        choices=BACKUP_MODE_CHOICES,
        default=BACKUP_DATA,
        db_default=BACKUP_DATA,
        verbose_name="Backup Mode",
    )
    backup_token = models.CharField(max_length=64, blank=True, verbose_name="Backup Token")
    progress_log = models.TextField(blank=True, verbose_name="Progress Log")
    error = models.TextField(blank=True, verbose_name="Error")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    handoff_at = models.DateTimeField(blank=True, null=True, verbose_name="Handoff At")
    completed_at = models.DateTimeField(blank=True, null=True, verbose_name="Completed At")

    class Meta:
        verbose_name = "Dlux Image Update"
        verbose_name_plural = "Dlux Image Updates"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['is_active', 'created_at'], name='dlux_image_active_idx'),
        ]

    def append_log(self, message):
        line = str(message or '').replace('\x00', '').strip()
        if not line:
            return
        combined = f"{self.progress_log}\n{line}".strip()
        self.progress_log = combined[-65536:]

    def __str__(self):
        return f"Dlux image update {self.target_version or ''} ({self.status})"


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


class ActivityLog(ScopedModel):
    """
    Activity log model — the single source of truth for all logs (user/system/audit).
    Uses inherited ScopedModel fields:
    - created_by → the user who performed the action (was 'user')
    - created_at → when the action occurred (was 'timestamp')

    Renamed from ``UserActivityLog`` (the "User" prefix is obsolete now that this stores
    system and audit entries too). ``UserActivityLog`` remains a module alias for
    backward-compatible imports.
    """
    CATEGORY_USER = 'user'
    CATEGORY_SYSTEM = 'system'
    CATEGORY_AUDIT = 'audit'
    CATEGORY_CHOICES = (
        (CATEGORY_USER, "User"),
        (CATEGORY_SYSTEM, "System"),
        (CATEGORY_AUDIT, "Audit"),
    )

    # created_by (inherited) → replaces old 'user' field
    # created_at (inherited) → replaces old 'timestamp' field
    action = models.CharField(max_length=50, verbose_name="Action")
    # Log category: 'user' (project work / dev-invoked), 'system' (dlux-internal), or
    # 'audit' (security events). Derived at log time by resolve_log_category(); audit rows
    # are privileged (append-only, never auto-pruned by default).
    category = models.CharField(
        max_length=10, choices=CATEGORY_CHOICES, default=CATEGORY_USER,
        verbose_name="Category",
    )
    # Human-readable label (the model's translated verbose name at log time). Used for
    # display. NOTE: this is locale-dependent, so never key reports/grouping off it.
    model_name = models.CharField(max_length=100, blank=True, null=True, verbose_name="Model Name")
    # Stable, locale-independent identity ("app_label.model_name", e.g. "documents.decree").
    # This is what reports/eligibility should group and resolve on. Null for legacy rows
    # and for non-model events (login, password, session, ...).
    model_key = models.CharField(max_length=100, blank=True, null=True, db_index=True, verbose_name="Model Key")
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

    def save(self, *args, **kwargs):
        # Audit entries are append-only: block in-app mutation of an existing audit row.
        # (Inserts have no pk yet and are allowed.) Bulk QuerySet.update() bypasses this by
        # design; app code must not target audit rows for updates.
        if self.pk and self.category == self.CATEGORY_AUDIT:
            raise ValueError("Audit activity-log entries are immutable and cannot be modified.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Audit entries cannot be deleted through the app (never auto-pruned by default).
        # Bulk QuerySet.delete() bypasses this; the prune command excludes audit explicitly.
        if self.category == self.CATEGORY_AUDIT:
            return None
        return super().delete(*args, **kwargs)

    class Meta:
        verbose_name = "Activity Log"
        verbose_name_plural = "Activity Logs"
        default_permissions = ()
        indexes = [
            models.Index(fields=['created_at'], name='dlux_ual_created_idx'),
            models.Index(fields=['scope', 'created_at'], name='dlux_ual_scope_created_idx'),
            models.Index(fields=['created_by', 'created_at'], name='dlux_ual_actor_created_idx'),
            models.Index(fields=['model_key', 'created_at'], name='dlux_ual_model_created_idx'),
            models.Index(fields=['action', 'created_at'], name='dlux_ual_action_created_idx'),
            models.Index(fields=['category', 'created_at'], name='dlux_ual_cat_created_idx'),
        ]
        permissions = [
            ("view_activitylog", "View activity log"),
        ]

    @classmethod
    def safe_log(cls, user, action, model_name=None, object_id=None, number=None, details=None, ip_address=None, user_agent=None, scope=None, model_key=None, category=None):
        """
        Log an action only if a duplicate entry hasn't been created in the last 2 seconds.

        ``category`` is the log type ('user'/'system'/'audit'); when omitted it is derived
        from (action, model_key, model_name) via resolve_log_category. It is NOT part of the
        dedupe key — it is a pure function of fields already in the key.
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

        if category is None:
            from .utils.activity_log import resolve_log_category
            category = resolve_log_category(action, model_key=model_key, model_name=model_name)

        return cls.objects.create(
            created_by=user,
            action=action,
            category=category,
            model_name=model_name,
            model_key=(str(model_key).strip().lower() or None) if model_key else None,
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
        if (self.model_key or self.model_name) and self.object_id:
            from .utils import resolve_model_by_name
            try:
                target_model = resolve_model_by_name(self.model_key or self.model_name)
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


# Backward-compatible alias: the model was renamed UserActivityLog -> ActivityLog.
# Keeps `from dlux.models import UserActivityLog` and dlux.models.UserActivityLog.* working.
# NOTE: apps.get_model('dlux', 'ActivityLog') does NOT follow this alias — those string
# lookups were updated to 'ActivityLog'.
UserActivityLog = ActivityLog


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


class Section(models.Model):
    """Dummy Model for section permissions."""
    class Meta:
        managed = False
        default_permissions = ()
        permissions = [
            ("view_sections", "View sections"),
            ("manage_sections", "Manage sections"),
        ]
