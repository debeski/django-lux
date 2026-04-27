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
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.cache import cache
from microsys.context_processors import microsys_context
from microsys.themes import get_theme_names

User = get_user_model()


class ContextProcessorsTests(TestCase):
    def setUp(self):
        from django.contrib.auth.models import AnonymousUser

        cache.clear()
        self.factory = RequestFactory()
        raw_get = self.factory.get

        def get_with_context(*args, **kwargs):
            request = raw_get(*args, **kwargs)
            request.session = {}
            request.user = AnonymousUser()
            return request

        self.factory.get = get_with_context
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
            'system_names', 'identity', 'localization', 'security', 'navigation', 'appearance', 'personalization',
            'logo', 'login_logo', 'favicon',
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
            'system_names': {'en': 'Custom System', 'ar': 'نظام مخصص'},
            'default_language': 'ar',
            'default_theme': 'dark'
        }):
            request = self.factory.get('/')
            context = microsys_context(request)
            config = context['config']
            
            self.assertEqual(config['identity']['display_name'], 'نظام مخصص')
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
        theme_names = list(get_theme_names())
        
        self.assertIn('default_theme', config)
        self.assertIn(config['default_theme'], theme_names)
        self.assertEqual(context['MICROSYS_THEME_NAMES'], theme_names)
        self.assertEqual([theme['slug'] for theme in context['MICROSYS_THEMES']], theme_names)

    def test_microsys_context_includes_table_density_defaults(self):
        request = self.factory.get('/')
        context = microsys_context(request)

        self.assertIn('default_table_density', context['config'])
        self.assertEqual(context['user_preferences']['table_density'], context['config']['default_table_density'])

    def test_microsys_context_filters_theme_options_to_allowed_list(self):
        from microsys.models import SystemSettings

        settings_obj = SystemSettings.load()
        settings_obj.default_theme = 'dark'
        settings_obj.allowed_themes = ['dark', 'retro']
        settings_obj.allow_user_theme_override = True
        settings_obj.save()

        request = self.factory.get('/')
        request.user = self.user
        self.user.profile.preferences = {'theme': 'retro'}
        self.user.profile.save(update_fields=['preferences'])

        context = microsys_context(request)

        self.assertEqual(context['MICROSYS_THEME_NAMES'], ['dark', 'retro'])
        self.assertEqual([theme['slug'] for theme in context['MICROSYS_THEMES']], ['dark', 'retro'])
        self.assertEqual(context['user_preferences']['theme'], 'retro')

    def test_microsys_context_falls_back_from_disallowed_theme_and_locked_sidebar(self):
        from microsys.models import SystemSettings

        settings_obj = SystemSettings.load()
        settings_obj.default_theme = 'dark'
        settings_obj.allowed_themes = ['dark']
        settings_obj.allow_user_theme_override = False
        settings_obj.sidebar_config = {
            'entries': [],
            'density': 'roomy',
            'allow_user_density': False,
            'collapse_mode': 'locked_expanded',
        }
        settings_obj.save()

        request = self.factory.get('/')
        request.user = self.user
        request.session['sidebarCollapsed'] = True
        self.user.profile.preferences = {
            'theme': 'retro',
            'sidebar_density': 'dense',
            'sidebar_collapsed': True,
        }
        self.user.profile.save(update_fields=['preferences'])

        context = microsys_context(request)

        self.assertEqual(context['user_preferences']['theme'], 'dark')
        self.assertEqual(context['user_preferences']['sidebar_density'], 'roomy')
        self.assertFalse(context['sidebar_collapsed'])
        self.assertEqual(context['sidebar_density'], 'roomy')
        self.assertEqual(context['sidebar']['collapse_mode'], 'locked_expanded')
        self.assertEqual(context['titlebar']['home_shape'], 'circle')

    def test_microsys_context_hides_sidebar_toolbar_when_no_live_tools_exist(self):
        from microsys.models import SystemSettings

        settings_obj = SystemSettings.load()
        settings_obj.default_theme = 'dark'
        settings_obj.allowed_themes = ['dark']
        settings_obj.allow_user_theme_override = False
        settings_obj.sidebar_config = {
            'entries': [],
            'show_toolbar': True,
            'enable_reorder': False,
            'allow_user_density': False,
        }
        settings_obj.save()

        request = self.factory.get('/')
        request.user = self.user

        with patch('microsys.context_processors.has_section_models', return_value=False):
            context = microsys_context(request)

        self.assertFalse(context['sidebar_theme_picker_enabled'])
        self.assertFalse(context['sidebar_density_picker_enabled'])
        self.assertFalse(context['sidebar_reorder_enabled'])
        self.assertFalse(context['sidebar_toolbar_enabled'])

    def test_microsys_context_keeps_sidebar_toolbar_when_any_live_tool_exists(self):
        from microsys.models import SystemSettings

        settings_obj = SystemSettings.load()
        settings_obj.default_theme = 'dark'
        settings_obj.allowed_themes = ['dark']
        settings_obj.allow_user_theme_override = False
        settings_obj.sidebar_config = {
            'entries': [],
            'show_toolbar': True,
            'enable_reorder': False,
            'allow_user_density': True,
        }
        settings_obj.save()

        request = self.factory.get('/')
        request.user = self.user

        with patch('microsys.context_processors.has_section_models', return_value=False):
            context = microsys_context(request)

        self.assertTrue(context['sidebar_density_picker_enabled'])
        self.assertTrue(context['sidebar_toolbar_enabled'])

    def test_microsys_context_falls_back_to_default_language_when_override_disabled(self):
        from microsys.models import SystemSettings

        settings_obj = SystemSettings.load()
        settings_obj.default_language = 'en'
        settings_obj.allow_user_language_override = False
        settings_obj.save()

        request = self.factory.get('/')
        request.user = self.user
        request.session['lang'] = 'ar'
        self.user.profile.preferences = {'language': 'ar'}
        self.user.profile.save(update_fields=['preferences'])

        context = microsys_context(request)

        self.assertEqual(context['CURRENT_LANG'], 'en')
        self.assertFalse(context['language_picker_enabled'])
        self.assertNotIn('language', context['user_preferences'])

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
        settings.system_names = {'en': 'DB Override System'}
        settings.is_configured = True
        settings.save()
        
        request = self.factory.get('/')
        context = microsys_context(request)
        config = context['config']
        
        self.assertEqual(config['identity']['display_name'], 'DB Override System')
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
