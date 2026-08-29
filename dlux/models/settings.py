"""The SystemSettings singleton and its config-group plumbing."""

from django.db import models
from ..system.constants import DEFAULT_HOME_URL
from ..system.defaults import (
    default_auth_config as _default_auth_config,
    default_backup_config as _default_backup_config,
    default_client_ip_config as _default_client_ip_config,
    default_email_config as _default_email_config,
    default_extra_config as _default_extra_config,
    default_homepage_config as _default_homepage_config,
    default_language_config as _default_language_config,
    default_layout_config as _default_layout_config,
    default_login_config as _default_login_config,
    default_navbar_config as _default_navbar_config,
    default_notification_config as _default_notification_config,
    default_public_root_config as _default_public_root_config,
    default_registration_config as _default_registration_config,
    default_search_config as _default_search_config,
    default_theme_config as _default_theme_config,
    default_titlebar_config as _default_titlebar_config,
    default_typography_config as _default_typography_config,
    default_log_config as _default_log_config,
    default_profile_config as _default_profile_config,
)
from ..system.registry import get_config_defaults, get_flat_config_fields
from ..system.normalizers import (
    homepage_config_legacy_values,
    normalize_homepage_config,
    normalize_search_config,
    search_config_legacy_values,
)

from .base import SingletonModel


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


def default_homepage_config():
    return _default_homepage_config()


def default_client_ip_config():
    return _default_client_ip_config()


def default_notification_config():
    return _default_notification_config()


def default_search_config():
    return _default_search_config()


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
    logo_asset = models.ForeignKey(
        'dlux.ManagedAsset',
        on_delete=models.PROTECT,
        related_name='system_logo_uses',
        null=True,
        blank=True,
        verbose_name="System Logo Asset",
    )
    login_logo_asset = models.ForeignKey(
        'dlux.ManagedAsset',
        on_delete=models.PROTECT,
        related_name='login_logo_uses',
        null=True,
        blank=True,
        verbose_name="Login Logo Asset",
    )
    favicon_asset = models.ForeignKey(
        'dlux.ManagedAsset',
        on_delete=models.PROTECT,
        related_name='favicon_uses',
        null=True,
        blank=True,
        verbose_name="Favicon Asset",
    )
    login_background_asset = models.ForeignKey(
        'dlux.ManagedAsset',
        on_delete=models.PROTECT,
        related_name='login_background_uses',
        null=True,
        blank=True,
        verbose_name="Login Background Asset",
    )
    default_language = models.CharField(max_length=10, default='en', verbose_name="Default Language")
    default_theme = models.CharField(max_length=20, default='light', verbose_name="Default Theme")
    home_url = models.CharField(max_length=255, default=DEFAULT_HOME_URL, verbose_name="Home URL")
    is_configured = models.BooleanField(default=False, verbose_name="Is Configured")
    auth_config = models.JSONField(default=default_auth_config, blank=True, verbose_name="Authentication Configuration")
    email_config = models.JSONField(default=default_email_config, blank=True, verbose_name="Email Configuration")
    registration_config = models.JSONField(default=default_registration_config, blank=True, verbose_name="Registration Configuration")
    public_root_config = models.JSONField(default=default_public_root_config, blank=True, verbose_name="Public Page Configuration")
    homepage_config = models.JSONField(
        default=default_homepage_config,
        db_default=default_homepage_config(),
        blank=True,
        verbose_name="Homepage Configuration",
    )
    client_ip_config = models.JSONField(default=default_client_ip_config, blank=True, verbose_name="Client IP Configuration")
    notification_config = models.JSONField(default=default_notification_config, blank=True, verbose_name="Notification Configuration")
    layout_config = models.JSONField(default=default_layout_config, blank=True, verbose_name="Layout Configuration")
    language_config = models.JSONField(default=default_language_config, blank=True, verbose_name="Language Configuration")
    theme_config = models.JSONField(default=default_theme_config, blank=True, verbose_name="Theme Configuration")
    typography_config = models.JSONField(default=default_typography_config, blank=True, verbose_name="Typography Configuration")
    login_config = models.JSONField(default=default_login_config, blank=True, verbose_name="Login Page Configuration")
    titlebar_config = models.JSONField(default=default_titlebar_config, blank=True, verbose_name="Titlebar Configuration")
    search_config = models.JSONField(
        default=default_search_config,
        db_default=default_search_config(),
        blank=True,
        verbose_name="Search Configuration",
    )
    sidebar_config = models.JSONField(default=dict, blank=True, verbose_name="Sidebar Configuration")
    ribbon_config = models.JSONField(default=dict, db_default={}, blank=True, verbose_name="Ribbon Configuration")
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

    def _legacy_homepage_config(self):
        profile = self.profile_config if isinstance(self.profile_config, dict) else {}
        return normalize_homepage_config({
            'home_url': self.home_url,
            **dict(self.public_root_config or {}),
            'allow_user_home_url': profile.get('allow_user_home_url', False),
        })

    def _sync_homepage_compat(self, homepage):
        self.homepage_config = normalize_homepage_config(homepage)
        legacy = homepage_config_legacy_values(self.homepage_config)
        self.home_url = legacy['home_url']
        self.public_root_config = legacy['public_root_config']
        profile = dict(self.profile_config or {})
        profile['allow_user_home_url'] = legacy['allow_user_home_url']
        self.profile_config = profile

    def _legacy_search_config(self):
        return normalize_search_config(self.titlebar_config or {})

    def _sync_search_compat(self, search):
        self.search_config = normalize_search_config(search)
        titlebar = dict(self.titlebar_config or {})
        titlebar.update(search_config_legacy_values(self.search_config))
        self.titlebar_config = titlebar

    def _sync_compat_configs(self, update_fields):
        requested = set(update_fields or ())
        requested.update(
            _SYSTEM_SETTINGS_FLAT_CONFIG_FIELDS.get(field_name, (field_name, None))[0]
            for field_name in tuple(requested)
        )
        previous = None
        if self.pk and not self._state.adding:
            previous = type(self).objects.filter(pk=self.pk).values(
                'homepage_config', 'home_url', 'public_root_config', 'profile_config',
                'search_config', 'titlebar_config',
            ).first()

        canonical_home = normalize_homepage_config(self.homepage_config)
        legacy_home = self._legacy_homepage_config()
        if 'homepage_config' in requested:
            selected_home = canonical_home
        elif requested.intersection({'home_url', 'public_root_config', 'profile_config'}):
            selected_home = legacy_home
        elif previous:
            old_canonical_home = normalize_homepage_config(previous.get('homepage_config'))
            old_profile = previous.get('profile_config') or {}
            old_legacy_home = normalize_homepage_config({
                'home_url': previous.get('home_url'),
                **dict(previous.get('public_root_config') or {}),
                'allow_user_home_url': old_profile.get('allow_user_home_url', False),
            })
            selected_home = canonical_home if canonical_home != old_canonical_home else legacy_home
            if canonical_home == old_canonical_home and legacy_home == old_legacy_home:
                selected_home = canonical_home
        else:
            selected_home = canonical_home if canonical_home != default_homepage_config() else legacy_home
        self._sync_homepage_compat(selected_home)

        canonical_search = normalize_search_config(self.search_config)
        legacy_search = self._legacy_search_config()
        if 'search_config' in requested:
            selected_search = canonical_search
        elif 'titlebar_config' in requested:
            selected_search = legacy_search
        elif previous:
            old_canonical_search = normalize_search_config(previous.get('search_config'))
            old_legacy_search = normalize_search_config(previous.get('titlebar_config'))
            selected_search = canonical_search if canonical_search != old_canonical_search else legacy_search
            if canonical_search == old_canonical_search and legacy_search == old_legacy_search:
                selected_search = canonical_search
        else:
            selected_search = canonical_search if canonical_search != default_search_config() else legacy_search
        self._sync_search_compat(selected_search)

    def save(self, *args, **kwargs):
        update_fields = kwargs.get('update_fields')
        self._sync_compat_configs(update_fields)
        if update_fields is not None:
            update_fields = list(update_fields)
            requested_storage = {
                _SYSTEM_SETTINGS_FLAT_CONFIG_FIELDS.get(field_name, (field_name, None))[0]
                for field_name in update_fields
            }
            if requested_storage.intersection({'homepage_config', 'home_url', 'public_root_config', 'profile_config'}):
                update_fields.extend(('homepage_config', 'home_url', 'public_root_config', 'profile_config'))
            if requested_storage.intersection({'search_config', 'titlebar_config'}):
                update_fields.extend(('search_config', 'titlebar_config'))
            normalized_update_fields = []
            for field_name in update_fields:
                config_field = _SYSTEM_SETTINGS_FLAT_CONFIG_FIELDS.get(field_name, (field_name, None))[0]
                if config_field not in normalized_update_fields:
                    normalized_update_fields.append(config_field)
            kwargs['update_fields'] = normalized_update_fields
        super().save(*args, **kwargs)


for _flat_name, (_config_field, _config_key) in _SYSTEM_SETTINGS_FLAT_CONFIG_FIELDS.items():
    setattr(SystemSettings, _flat_name, _system_settings_config_property(_config_field, _config_key))


class SystemSettingsSnapshot(models.Model):
    """The settings payload as it stood immediately before an import was applied.

    Applying a config file to a live, populated system is the one operation here
    that can quietly overwrite a lot at once. The Options-page import writes one
    of these first, so "revert" is a real action rather than a promise — the
    payload is a full `export_system_settings_payload()` result, which the same
    importer can feed straight back in.

    Kept deliberately small and append-only: rows are cheap, and an operator
    looking for "what did I import last Tuesday" is better served by history
    than by a single overwritten slot.
    """

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    created_by = models.ForeignKey(
        'auth.User', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='dlux_settings_snapshots',
    )
    reason = models.CharField(max_length=64, default='config_import')
    # The pre-change export payload, verbatim.
    payload = models.JSONField(default=dict, blank=True)
    # What the operator chose to apply, for the audit trail.
    applied_keys = models.JSONField(default=list, blank=True)
    reverted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "System Settings Snapshot"
        verbose_name_plural = "System Settings Snapshots"
        ordering = ('-created_at',)

    def __str__(self):
        return f"Settings snapshot {self.created_at:%Y-%m-%d %H:%M}"
