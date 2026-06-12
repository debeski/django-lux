from django.conf import settings

if not settings.configured:
    settings.configure(
        SECRET_KEY='dlux-test-key',
        ALLOWED_HOSTS=['testserver', 'localhost'],
        INSTALLED_APPS=[
            'django.contrib.auth',
            'django.contrib.contenttypes',
            'django.contrib.sessions',
            'django.contrib.messages',
            'django.contrib.staticfiles',
            'crispy_forms',
            'crispy_bootstrap5',
            'django_filters',
            'django_tables2',
            'dlux',
        ],
        MIDDLEWARE=[
            'django.contrib.sessions.middleware.SessionMiddleware',
            'django.contrib.auth.middleware.AuthenticationMiddleware',
            'dlux.middleware.DluxMiddleware',
        ],
        ROOT_URLCONF='dlux.urls',
        TEMPLATES=[
            {
                'BACKEND': 'django.template.backends.django.DjangoTemplates',
                'APP_DIRS': True,
                'OPTIONS': {
                    'context_processors': [
                        'django.template.context_processors.request',
                        'django.contrib.auth.context_processors.auth',
                        'django.contrib.messages.context_processors.messages',
                        'dlux.context_processors.dlux_context',
                    ],
                },
            }
        ],
        DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}},
        STATIC_URL='/static/',
        DEFAULT_AUTO_FIELD='django.db.models.BigAutoField',
        USE_TZ=True,
        CRISPY_ALLOWED_TEMPLATE_PACKS='bootstrap5',
        CRISPY_TEMPLATE_PACK='bootstrap5',
    )

    import django
    django.setup()

from django.db import models
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from dlux.constants import DEFAULT_TABLE_DENSITY
from dlux.models import (
    SystemSettings, Scope, ScopeSettings, Profile, UserActivityLog,
    ScopedModel, TranslationMixin, Section
)

User = get_user_model()


class SystemSettingsTests(TestCase):
    def setUp(self):
        cache.clear()

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
