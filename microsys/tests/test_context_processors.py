from django.conf import settings

if not settings.configured:
    settings.configure(
        SECRET_KEY='microsys-test-key',
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
            'microsys',
        ],
        MIDDLEWARE=[
            'django.contrib.sessions.middleware.SessionMiddleware',
            'django.contrib.auth.middleware.AuthenticationMiddleware',
            'microsys.middleware.ActivityLogMiddleware',
        ],
        ROOT_URLCONF='microsys.urls',
        TEMPLATES=[
            {
                'BACKEND': 'django.template.backends.django.DjangoTemplates',
                'APP_DIRS': True,
                'OPTIONS': {
                    'context_processors': [
                        'django.template.context_processors.request',
                        'django.contrib.auth.context_processors.auth',
                        'django.contrib.messages.context_processors.messages',
                        'microsys.context_processors.microsys_context',
                    ],
                },
            }
        ],
        DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}},
        STATIC_URL='/static/',
        MEDIA_URL='/media/',
        DEFAULT_AUTO_FIELD='django.db.models.BigAutoField',
        USE_TZ=True,
        CRISPY_ALLOWED_TEMPLATE_PACKS='bootstrap5',
        CRISPY_TEMPLATE_PACK='bootstrap5',
    )

    import django
    django.setup()

from django.test import TestCase, RequestFactory, override_settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from microsys.context_processors import microsys_context

User = get_user_model()


class ContextProcessorsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

    def test_microsys_context_returns_dict(self):
        """Test that microsys_context returns a dictionary."""
        request = self.factory.get('/')
        context = microsys_context(request)
        self.assertIsInstance(context, dict)

    def test_microsys_context_includes_system_config(self):
        """Test that microsys_context includes system config."""
        request = self.factory.get('/')
        context = microsys_context(request)
        self.assertIn('config', context)

    def test_microsys_context_includes_user_info(self):
        """Test that microsys_context includes user information."""
        request = self.factory.get('/')
        request.user = self.user
        context = microsys_context(request)
        self.assertIn('user', context)

    def test_microsys_context_includes_sidebar_config(self):
        """Test that microsys_context includes sidebar configuration."""
        request = self.factory.get('/')
        context = microsys_context(request)
        self.assertIn('sidebar', context)

    def test_microsys_context_includes_languages(self):
        """Test that microsys_context includes languages."""
        request = self.factory.get('/')
        context = microsys_context(request)
        self.assertIn('languages', context)

    def test_microsys_context_includes_translations(self):
        """Test that microsys_context includes translations."""
        request = self.factory.get('/')
        context = microsys_context(request)
        self.assertIn('translations', context)

    def test_microsys_context_config_has_required_keys(self):
        """Test that system config has required keys."""
        request = self.factory.get('/')
        context = microsys_context(request)
        config = context['config']
        
        required_keys = [
            'name', 'name_en', 'logo', 'login_logo', 'favicon',
            'home_url', 'default_language', 'default_theme',
            'languages', 'is_configured'
        ]
        
        for key in required_keys:
            self.assertIn(key, config)

    def test_microsys_context_with_authenticated_user(self):
        """Test microsys_context with authenticated user."""
        request = self.factory.get('/')
        request.user = self.user
        context = microsys_context(request)
        
        self.assertEqual(context['user'], self.user)

    def test_microsys_context_with_anonymous_user(self):
        """Test microsys_context with anonymous user."""
        from django.contrib.auth.models import AnonymousUser
        request = self.factory.get('/')
        request.user = AnonymousUser()
        context = microsys_context(request)
        
        self.assertIsInstance(context['user'], AnonymousUser)

    def test_microsys_context_with_custom_config(self):
        """Test microsys_context with custom MICROSYS_CONFIG."""
        with override_settings(MICROSYS_CONFIG={
            'name': 'Custom System',
            'default_language': 'ar',
            'default_theme': 'dark'
        }):
            request = self.factory.get('/')
            context = microsys_context(request)
            config = context['config']
            
            self.assertEqual(config['name'], 'Custom System')
            self.assertEqual(config['default_language'], 'ar')
            self.assertEqual(config['default_theme'], 'dark')

    def test_microsys_context_sidebar_entries(self):
        """Test that sidebar config includes entries."""
        request = self.factory.get('/')
        context = microsys_context(request)
        sidebar = context['sidebar']
        
        self.assertIn('entries', sidebar)
        self.assertIsInstance(sidebar['entries'], list)

    def test_microsys_context_languages_structure(self):
        """Test that languages have proper structure."""
        request = self.factory.get('/')
        context = microsys_context(request)
        languages = context['config']['languages']
        
        self.assertIsInstance(languages, dict)
        # Should have at least 'en' and 'ar'
        self.assertIn('en', languages)
        self.assertIn('ar', languages)

    def test_microsys_context_theme_options(self):
        """Test that theme options are available."""
        request = self.factory.get('/')
        context = microsys_context(request)
        config = context['config']
        
        self.assertIn('default_theme', config)
        self.assertIn(config['default_theme'], ['light', 'dark', 'blue', 'gold', 'green', 'red'])

    def test_microsys_context_home_url(self):
        """Test that home_url is properly set."""
        request = self.factory.get('/')
        context = microsys_context(request)
        config = context['config']
        
        self.assertIn('home_url', config)
        self.assertIsInstance(config['home_url'], str)

    def test_microsys_context_is_configured_flag(self):
        """Test that is_configured flag is boolean."""
        request = self.factory.get('/')
        context = microsys_context(request)
        config = context['config']
        
        self.assertIn('is_configured', config)
        self.assertIsInstance(config['is_configured'], bool)

    def test_microsys_context_with_database_override(self):
        """Test microsys_context with database settings override."""
        from microsys.models import SystemSettings
        
        settings = SystemSettings.load()
        settings.name = 'DB Override System'
        settings.is_configured = True
        settings.save()
        
        request = self.factory.get('/')
        context = microsys_context(request)
        config = context['config']
        
        self.assertEqual(config['name'], 'DB Override System')
        self.assertTrue(config['is_configured'])

    def test_microsys_context_media_urls(self):
        """Test that media URLs are properly formatted."""
        request = self.factory.get('/')
        context = microsys_context(request)
        config = context['config']
        
        # Check that media URLs are absolute
        if 'logo_url' in config and config['logo_url']:
            self.assertTrue(config['logo_url'].startswith('/') or config['logo_url'].startswith('http'))
        
        if 'favicon_url' in config and config['favicon_url']:
            self.assertTrue(config['favicon_url'].startswith('/') or config['favicon_url'].startswith('http'))
