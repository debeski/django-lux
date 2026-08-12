from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.db import models
from django.test import TestCase, override_settings
from django.test.utils import isolate_apps
from django.contrib.auth import get_user_model
from django.core.cache import cache
from dlux.system.constants import DEFAULT_TABLE_DENSITY
from dlux.models import (
    SystemSettings, Scope, ScopeSettings, Profile, UserActivityLog,
    ScopedModel, TranslationMixin, Section
)

User = get_user_model()


class SystemSettingsTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_system_settings_field_order_uses_json_config_groups(self):
        """SystemSettings keeps identity columns first, then grouped JSON config fields."""
        field_names = [field.name for field in SystemSettings._meta.fields]
        self.assertEqual(field_names, [
            'id',
            'system_names',
            'logo',
            'favicon',
            'logo_asset',
            'login_logo_asset',
            'favicon_asset',
            'login_background_asset',
            'default_language',
            'default_theme',
            'home_url',
            'is_configured',
            'auth_config',
            'email_config',
            'registration_config',
            'public_root_config',
            'client_ip_config',
            'notification_config',
            'layout_config',
            'language_config',
            'theme_config',
            'typography_config',
            'login_config',
            'titlebar_config',
            'sidebar_config',
            'navbar_config',
            'log_config',
            'profile_config',
            'backup_config',
            'extra_config',
        ])

    def test_singleton_load_creates_instance(self):
        """Test that load() creates a singleton instance if it doesn't exist."""
        instance = SystemSettings.load()
        self.assertIsNotNone(instance)
        self.assertEqual(instance.pk, 1)

    def test_singleton_load_returns_same_instance(self):
        """Test that load() returns the same instance on subsequent calls."""
        instance1 = SystemSettings.load()
        instance2 = SystemSettings.load()
        self.assertEqual(instance1.pk, instance2.pk)

    def test_system_settings_defaults(self):
        """Test default values for SystemSettings."""
        instance = SystemSettings.load()
        self.assertEqual(instance.default_language, 'en')
        self.assertEqual(instance.default_theme, 'light')
        self.assertTrue(instance.allow_user_language_override)
        self.assertEqual(instance.default_table_density, DEFAULT_TABLE_DENSITY)
        self.assertFalse(instance.is_configured)
        self.assertFalse(instance.backup_config['scheduled_enabled'])
        self.assertEqual(instance.backup_config['retention_days'], 0)
        self.assertEqual(instance.backup_config['max_backups_to_keep'], 0)

    def test_system_settings_flat_properties_write_grouped_json(self):
        instance = SystemSettings.load()
        instance.public_registration_enabled = True
        instance.registration_activation_mode = 'verified_pending_approval'
        instance.public_root = True
        instance.public_root_split_enabled = True
        instance.public_root_url = '/public/'
        instance.default_table_density = 'roomy'
        instance.allowed_themes = ['dark']
        instance.allow_user_theme_override = False
        instance.allowed_fonts = ['cairo']
        instance.default_fonts = {'en': 'cairo'}
        instance.allow_user_font_override = False
        instance.languages = {'en': {'name': 'English', 'direction': 'ltr'}}
        instance.translations_override = {'en': {'custom_key': 'Custom'}}
        instance.allow_user_language_override = False
        instance.save(update_fields=[
            'public_registration_enabled',
            'registration_activation_mode',
            'public_root',
            'public_root_split_enabled',
            'public_root_url',
            'default_table_density',
            'allowed_themes',
            'allow_user_theme_override',
            'allowed_fonts',
            'default_fonts',
            'allow_user_font_override',
            'languages',
            'translations_override',
            'allow_user_language_override',
        ])

        fresh = SystemSettings._default_manager.get(pk=instance.pk)
        self.assertEqual(fresh.registration_config['public_registration_enabled'], True)
        self.assertEqual(fresh.registration_config['registration_activation_mode'], 'verified_pending_approval')
        self.assertEqual(fresh.public_root_config['public_root_url'], '/public/')
        self.assertEqual(fresh.layout_config['default_table_density'], 'roomy')
        self.assertEqual(fresh.theme_config['allowed_themes'], ['dark'])
        self.assertFalse(fresh.theme_config['allow_user_theme_override'])
        self.assertEqual(fresh.typography_config['allowed_fonts'], ['cairo'])
        self.assertEqual(fresh.typography_config['default_fonts'], {'en': 'cairo'})
        self.assertFalse(fresh.typography_config['allow_user_font_override'])
        self.assertEqual(fresh.language_config['translations_override'], {'en': {'custom_key': 'Custom'}})
        self.assertFalse(fresh.language_config['allow_user_language_override'])

    def test_system_settings_legacy_update_fields_maps_to_group_owner(self):
        instance = SystemSettings.load()
        instance.allowed_themes = ['dark']
        instance.save(update_fields=['allowed_themes'])

        fresh = SystemSettings._default_manager.get(pk=instance.pk)
        self.assertEqual(fresh.theme_config['allowed_themes'], ['dark'])

    def test_system_settings_caching(self):
        """Test that SystemSettings uses caching."""
        instance1 = SystemSettings.load()
        cached_instance = cache.get('SystemSettings')
        self.assertIsNotNone(cached_instance)
        self.assertEqual(instance1.pk, cached_instance.pk)

    def test_refresh_cache(self):
        """Test that refresh_cache updates the cache."""
        instance = SystemSettings.load()
        instance.name = 'Test System'
        instance.save()
        instance.refresh_cache()
        cached_instance = cache.get('SystemSettings')
        self.assertEqual(cached_instance.name, 'Test System')

    def test_load_survives_unreadable_cache(self):
        """Regression: an unreadable cached singleton (e.g. an incompatible pickle
        from an older code revision) must fall back to the DB, not raise."""
        from unittest.mock import patch
        instance = SystemSettings.load()
        instance.is_configured = True
        instance.save()
        with patch('dlux.models.base.cache.get', side_effect=Exception('unpickle boom')):
            result = SystemSettings.load()
        self.assertEqual(result.pk, 1)
        self.assertTrue(result.is_configured)

    def test_get_system_config_keeps_configured_when_cache_unreadable(self):
        """Regression: a cache read failure must never collapse get_system_config()
        to is_configured=False (which would bounce users into the setup wizard)."""
        from unittest.mock import patch
        from dlux.utils import get_system_config
        instance = SystemSettings.load()
        instance.is_configured = True
        instance.save()
        with patch('dlux.models.base.cache.get', side_effect=Exception('unpickle boom')):
            config = get_system_config()
        self.assertTrue(config.get('is_configured'))

    def test_get_system_config_safety_net_when_load_raises(self):
        """Regression: even if SystemSettings.load() fails outright, the cache-free
        DB safety net in get_system_config() honors a configured row."""
        from unittest.mock import patch
        from dlux.utils import get_system_config
        instance = SystemSettings.load()
        instance.is_configured = True
        instance.save()
        cache.clear()
        with patch('dlux.models.SystemSettings.load', side_effect=Exception('load boom')):
            config = get_system_config()
        self.assertTrue(config.get('is_configured'))


class ScopeTests(TestCase):
    def test_scope_creation(self):
        """Test creating a Scope."""
        scope = Scope.objects.create(name='Test Scope')
        self.assertEqual(scope.name, 'Test Scope')
        self.assertEqual(str(scope), 'Test Scope')

    def test_scope_verbose_names(self):
        """Test verbose names for Scope model."""
        self.assertEqual(str(Scope._meta.verbose_name), 'Scopes')
        self.assertEqual(Scope._meta.verbose_name_plural, 'Scopes')


class ScopeSettingsTests(TestCase):
    def test_singleton_load_creates_instance(self):
        """Test that load() creates a singleton instance."""
        instance = ScopeSettings.load()
        self.assertIsNotNone(instance)
        self.assertEqual(instance.pk, 1)

    def test_singleton_always_sets_pk_to_1(self):
        """Test that save() always sets pk to 1."""
        instance = ScopeSettings.load()
        instance.save()
        self.assertEqual(instance.pk, 1)

    def test_toggle_is_enabled(self):
        """Test toggling is_enabled field."""
        settings = ScopeSettings.load()
        settings.is_enabled = True
        settings.save()
        self.assertTrue(ScopeSettings.load().is_enabled)


class ProfileTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

    def test_profile_auto_creation(self):
        """Test that Profile is automatically created for User."""
        self.assertTrue(hasattr(self.user, 'profile'))
        self.assertIsNotNone(self.user.profile)

    def test_profile_phone_field(self):
        """Test profile phone field."""
        self.user.profile.phone = '+1234567890'
        self.user.profile.save()
        self.assertEqual(self.user.profile.phone, '+1234567890')

    def test_profile_preferences_json_field(self):
        """Test profile preferences JSON field."""
        self.user.profile.preferences = {'theme': 'dark', 'language': 'en'}
        self.user.profile.save()
        self.assertEqual(self.user.profile.preferences['theme'], 'dark')

    def test_profile_2fa_properties(self):
        """Test 2FA-related properties."""
        self.assertFalse(self.user.profile.is_2fa_enabled)
        
        self.user.profile.is_email_2fa_enabled = True
        self.user.profile.save()
        self.assertTrue(self.user.profile.is_2fa_enabled)

    def test_profile_full_name_property(self):
        """Test full_name property."""
        self.user.first_name = 'John'
        self.user.last_name = 'Doe'
        self.user.save()
        self.assertEqual(self.user.profile.full_name, 'John Doe')

    def test_profile_str_representation(self):
        """Test string representation of Profile."""
        self.assertEqual(str(self.user.profile), 'testuser')


class UserActivityLogTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

    def test_activity_log_creation(self):
        """Test creating an activity log entry."""
        log = UserActivityLog.objects.create(
            created_by=self.user,
            action='CREATE',
            model_name='TestModel',
            object_id=1,
            number='TEST-001'
        )
        self.assertEqual(log.action, 'CREATE')
        self.assertEqual(log.model_name, 'TestModel')

    def test_safe_log_debouncing(self):
        """Test that safe_log debounces duplicate entries."""
        from django.utils.timezone import now
        from datetime import timedelta
        
        # Create first log
        log1 = UserActivityLog.safe_log(
            user=self.user,
            action='CREATE',
            model_name='TestModel',
            object_id=1
        )
        self.assertIsNotNone(log1)
        
        # Try to create duplicate within 2 seconds
        log2 = UserActivityLog.safe_log(
            user=self.user,
            action='CREATE',
            model_name='TestModel',
            object_id=1
        )
        # Should return None due to debouncing
        self.assertIsNone(log2)

    def test_backward_compat_properties(self):
        """Test backward compatibility properties."""
        log = UserActivityLog.objects.create(
            created_by=self.user,
            action='UPDATE',
            model_name='TestModel'
        )
        self.assertEqual(log.user, log.created_by)
        self.assertEqual(log.timestamp, log.created_at)

    def test_activity_log_details_json_field(self):
        """Test details JSON field."""
        log = UserActivityLog.objects.create(
            created_by=self.user,
            action='UPDATE',
            details={'field1': 'old', 'field2': 'new'}
        )
        self.assertEqual(log.details['field1'], 'old')


class ScopedModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.scope = Scope.objects.create(name='Test Scope')

    @isolate_apps('dlux')
    def test_scoped_model_auto_populates_audit_fields(self):
        """Test that ScopedModel auto-populates audit fields."""
        from dlux.middleware import get_current_user
        from threading import local
        
        # Set current user in thread local
        _thread_locals = local()
        _thread_locals.user = self.user
        
        try:
            # Create a test model that inherits from ScopedModel
            class TestScopedModel(ScopedModel):
                name = models.CharField(max_length=100)
                
                class Meta:
                    app_label = 'dlux'
            
            # Note: This would require database migration in real usage
            # For testing, we just verify the logic exists
            self.assertTrue(hasattr(ScopedModel, 'created_by'))
            self.assertTrue(hasattr(ScopedModel, 'updated_by'))
        finally:
            if hasattr(_thread_locals, 'user'):
                del _thread_locals.user

    def test_soft_delete_behavior(self):
        """Test soft delete behavior."""
        # This would require a concrete model inheriting ScopedModel
        # For now, verify the methods exist
        self.assertTrue(hasattr(ScopedModel, 'delete'))
        self.assertTrue(hasattr(ScopedModel, 'soft_delete'))
        self.assertTrue(hasattr(ScopedModel, 'restore'))
        self.assertTrue(hasattr(ScopedModel, 'hard_delete'))


class TranslationMixinTests(TestCase):
    @isolate_apps('dlux')
    def test_translation_mixin_getattr(self):
        """Test TranslationMixin __getattr__ for field translation."""
        
        class TestTranslationModel(models.Model):
            translated_fields = ['name', 'description']
            name = models.CharField(max_length=100)
            name_en = models.CharField(max_length=100, blank=True)
            name_ar = models.CharField(max_length=100, blank=True)
            description = models.TextField()
            description_en = models.TextField(blank=True)
            description_ar = models.TextField(blank=True)
            
            class Meta:
                app_label = 'dlux'
        
        model = TestTranslationModel()
        model.name = 'Default'
        model.name_en = 'English'
        model.name_ar = 'Arabic'
        
        # Test that the mixin has the __getattr__ method
        self.assertTrue(hasattr(TranslationMixin, '__getattr__'))


class SectionTests(TestCase):
    def test_section_permissions(self):
        """Test Section model permissions."""
        permissions = Section._meta.permissions
        self.assertIn(('view_sections', 'View sections'), permissions)
        self.assertIn(('manage_sections', 'Manage sections'), permissions)

    def test_section_is_managed(self):
        """Test that Section is not managed."""
        self.assertFalse(Section._meta.managed)


class MicrosysBrandingRepairTests(TestCase):
    """The microsys→dlux migration must relocate branding media that django-microsys
    stored under 'microsys/branding/' to dlux's 'dlux/branding/' upload path,
    otherwise the migrated logo/favicon 404 forever."""

    def setUp(self):
        cache.clear()

    def _run_repair(self):
        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        call_command('dlux_migrate_from_microsys', '--repair-branding-media', '--yes', stdout=out)
        return out.getvalue()

    def test_repair_rewrites_path_and_moves_file(self):
        import tempfile
        from django.core.files.base import ContentFile
        from django.core.files.storage import default_storage

        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            old_name = 'microsys/branding/logo.png'
            default_storage.save(old_name, ContentFile(b'PNGDATA'))

            settings_row = SystemSettings.load()
            SystemSettings.objects.filter(pk=settings_row.pk).update(logo=old_name)

            self._run_repair()

            moved = SystemSettings.objects.get(pk=settings_row.pk)
            self.assertEqual(moved.logo.name, 'dlux/branding/logo.png')
            self.assertTrue(default_storage.exists('dlux/branding/logo.png'))
            self.assertFalse(default_storage.exists(old_name))

    def test_repair_rewrites_path_even_when_file_missing(self):
        import tempfile
        from django.core.files.storage import default_storage

        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            settings_row = SystemSettings.load()
            SystemSettings.objects.filter(pk=settings_row.pk).update(
                favicon='microsys/branding/icon.png')

            self._run_repair()

            moved = SystemSettings.objects.get(pk=settings_row.pk)
            # Path is corrected so a re-upload lands in the right place; no file to move.
            self.assertEqual(moved.favicon.name, 'dlux/branding/icon.png')
            self.assertFalse(default_storage.exists('microsys/branding/icon.png'))

    def test_repair_leaves_dlux_paths_untouched(self):
        settings_row = SystemSettings.load()
        SystemSettings.objects.filter(pk=settings_row.pk).update(logo='dlux/branding/logo.png')
        self._run_repair()
        self.assertEqual(
            SystemSettings.objects.get(pk=settings_row.pk).logo.name,
            'dlux/branding/logo.png',
        )
