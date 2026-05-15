from django.apps import apps
from django.conf import settings
from types import SimpleNamespace
from unittest.mock import mock_open, patch

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
            'microsys.middleware.MicrosysMiddleware',
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
from django.contrib.messages import constants as messages
from django.core.cache import cache
from microsys import __version__, get_version
from microsys.constants import DEFAULT_TABLE_DENSITY
from microsys.utils import (
    get_system_config, is_staff, is_superuser, get_client_ip,
    log_user_action, is_scope_enabled, _normalize_asset_url,
    get_secret, microsys_settings, _build_generic_detail_context,
    get_user_management_tier_state, get_user_management_tier_state_for_user,
    is_central_staff, is_global_staff, user_can_view_user_directory,
    get_profile_totp_secret, set_profile_totp_state,
)

User = get_user_model()


class UtilsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

    def test_is_staff(self):
        """Test is_staff utility function."""
        self.assertFalse(is_staff(self.user))
        self.user.is_staff = True
        self.user.save()
        self.assertTrue(is_staff(self.user))

    def test_is_superuser(self):
        """Test is_superuser utility function."""
        self.assertFalse(is_superuser(self.user))
        self.user.is_superuser = True
        self.user.save()
        self.assertTrue(is_superuser(self.user))

    def test_get_client_ip_with_x_forwarded_for(self):
        """Test get_client_ip with X-Forwarded-For header."""
        request = self.factory.get('/')
        request.META['HTTP_X_FORWARDED_FOR'] = '192.168.1.1, 10.0.0.1'
        ip = get_client_ip(request)
        self.assertEqual(ip, '192.168.1.1')

    def test_get_client_ip_with_remote_addr(self):
        """Test get_client_ip with REMOTE_ADDR."""
        request = self.factory.get('/')
        request.META['REMOTE_ADDR'] = '192.168.1.2'
        ip = get_client_ip(request)
        self.assertEqual(ip, '192.168.1.2')

    def test_get_client_ip_without_headers(self):
        """Test get_client_ip without IP headers."""
        request = self.factory.get('/')
        request.META.pop('REMOTE_ADDR', None)
        ip = get_client_ip(request)
        self.assertIsNone(ip)

    def test_microsys_settings_adds_locale_and_message_defaults(self):
        scope = {
            'INSTALLED_APPS': ['django.contrib.admin'],
            'MIDDLEWARE': [
                'django.contrib.sessions.middleware.SessionMiddleware',
                'django.middleware.common.CommonMiddleware',
                'django.contrib.auth.middleware.AuthenticationMiddleware',
            ],
            'TEMPLATES': [
                {
                    'OPTIONS': {
                        'context_processors': [],
                    },
                }
            ],
            'MESSAGE_TAGS': {
                messages.INFO: 'info-custom',
            },
        }

        microsys_settings(scope)

        self.assertEqual(scope['INSTALLED_APPS'][:5], [
            'microsys',
            'crispy_forms',
            'crispy_bootstrap5',
            'django_filters',
            'django_tables2',
        ])
        self.assertIn('microsys.context_processors.microsys_context', scope['TEMPLATES'][0]['OPTIONS']['context_processors'])
        self.assertEqual(
            scope['MIDDLEWARE'].index('django.middleware.locale.LocaleMiddleware'),
            scope['MIDDLEWARE'].index('django.middleware.common.CommonMiddleware') - 1,
        )
        self.assertEqual(
            scope['MIDDLEWARE'].index('microsys.middleware.MicrosysMiddleware'),
            scope['MIDDLEWARE'].index('django.contrib.auth.middleware.AuthenticationMiddleware') + 1,
        )
        self.assertEqual(scope['MESSAGE_TAGS'][messages.ERROR], 'danger')
        self.assertEqual(scope['MESSAGE_TAGS'][messages.INFO], 'info-custom')

    def test_microsys_settings_preserves_existing_scalar_defaults(self):
        scope = {
            'INSTALLED_APPS': [],
            'MIDDLEWARE': [],
            'TEMPLATES': [],
            'USE_I18N': False,
            'USE_TZ': False,
            'DEFAULT_CHARSET': 'latin-1',
            'FORMAT_MODULE_PATH': ['project.formats'],
        }

        microsys_settings(scope)

        self.assertFalse(scope['USE_I18N'])
        self.assertFalse(scope['USE_TZ'])
        self.assertEqual(scope['DEFAULT_CHARSET'], 'latin-1')
        self.assertEqual(scope['FORMAT_MODULE_PATH'], ['project.formats', 'microsys.formats'])

    def test_get_secret_reads_docker_secret_first(self):
        with patch('builtins.open', mock_open(read_data='super-secret\n')):
            secret = get_secret('db_password', 'DB_PASSWORD')

        self.assertEqual(secret, 'super-secret')

    def test_get_secret_falls_back_to_environment_variable(self):
        with patch('builtins.open', side_effect=OSError), patch.dict('os.environ', {'DB_PASSWORD': 'env-secret'}, clear=False):
            secret = get_secret('db_password', 'DB_PASSWORD')

        self.assertEqual(secret, 'env-secret')

    def test_get_secret_returns_none_when_missing_everywhere(self):
        with patch('builtins.open', side_effect=OSError), patch.dict('os.environ', {}, clear=True):
            secret = get_secret('db_password', 'DB_PASSWORD')

        self.assertIsNone(secret)

    def test_version_helpers_read_from_version_file(self):
        from pathlib import Path

        expected = Path(__file__).resolve().parents[1].joinpath('VERSION').read_text(encoding='utf-8').strip()

        self.assertEqual(get_version(), expected)
        self.assertEqual(__version__, expected)

    def test_set_profile_totp_state_persists_secret_without_full_model_save(self):
        profile = self.user.profile
        original_picture_name = profile.profile_picture.name or ''

        set_profile_totp_state(profile, raw_secret='JBSWY3DPEHPK3PXP', enabled=True)

        profile.refresh_from_db()
        self.assertTrue(profile.is_totp_2fa_enabled)
        self.assertNotEqual(profile.totp_secret, 'JBSWY3DPEHPK3PXP')
        self.assertEqual(get_profile_totp_secret(profile), 'JBSWY3DPEHPK3PXP')
        self.assertEqual(profile.profile_picture.name or '', original_picture_name)

    def test_set_profile_totp_state_can_clear_secret(self):
        profile = self.user.profile
        set_profile_totp_state(profile, raw_secret='JBSWY3DPEHPK3PXP', enabled=True)

        set_profile_totp_state(profile, raw_secret='', enabled=False)

        profile.refresh_from_db()
        self.assertFalse(profile.is_totp_2fa_enabled)
        self.assertEqual(profile.totp_secret, '')
        self.assertEqual(get_profile_totp_secret(profile), '')

    def test_log_user_action(self):
        """Test log_user_action utility function."""
        from microsys.models import UserActivityLog
        
        request = self.factory.get('/')
        request.user = self.user
        request.META['HTTP_USER_AGENT'] = 'TestAgent'
        request.META['REMOTE_ADDR'] = '127.0.0.1'
        
        log_user_action(request, 'CREATE', model_name='TestModel', object_id=1)
        
        log = UserActivityLog.objects.filter(
            created_by=self.user,
            action='CREATE',
            model_name='TestModel'
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.object_id, 1)

    def test_log_user_action_with_instance(self):
        """Test log_user_action with model instance."""
        from microsys.models import UserActivityLog
        
        request = self.factory.get('/')
        request.user = self.user
        request.META['HTTP_USER_AGENT'] = 'TestAgent'
        request.META['REMOTE_ADDR'] = '127.0.0.1'
        
        log_user_action(request, 'UPDATE', instance=self.user)
        
        log = UserActivityLog.objects.filter(
            created_by=self.user,
            action='UPDATE'
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.object_id, self.user.pk)

    def test_log_user_action_with_details(self):
        """Test log_user_action with details dict."""
        from microsys.models import UserActivityLog
        
        request = self.factory.get('/')
        request.user = self.user
        request.META['HTTP_USER_AGENT'] = 'TestAgent'
        request.META['REMOTE_ADDR'] = '127.0.0.1'
        
        details = {'field1': 'old', 'field2': 'new'}
        log_user_action(request, 'UPDATE', model_name='TestModel', details=details)
        
        log = UserActivityLog.objects.filter(
            created_by=self.user,
            action='UPDATE'
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.details, details)

    def test_get_system_config_default(self):
        """Test get_system_config returns default config."""
        config = get_system_config()
        self.assertIn('system_names', config)
        self.assertIn('identity', config)
        self.assertIn('default_language', config)
        self.assertIn('default_theme', config)
        self.assertIn('allow_user_language_override', config)
        self.assertIn('default_table_density', config)
        self.assertIn('languages', config)
        self.assertEqual(config['default_language'], 'en')
        self.assertEqual(config['identity']['display_name'], 'microSYS')
        self.assertTrue(config['allow_user_language_override'])
        self.assertEqual(config['default_table_density'], DEFAULT_TABLE_DENSITY)

    def test_get_system_config_with_settings_override(self):
        """Test get_system_config with MICROSYS_CONFIG override."""
        with override_settings(MICROSYS_CONFIG={
            'system_names': {'en': 'Test System', 'ar': 'نظام الاختبار'},
            'default_language': 'ar',
            'default_theme': 'dark',
            'default_table_density': 'roomy',
        }):
            config = get_system_config()
            self.assertEqual(config['system_names']['en'], 'Test System')
            self.assertEqual(config['identity']['display_name'], 'نظام الاختبار')
            self.assertEqual(config['default_language'], 'ar')
            self.assertEqual(config['default_theme'], 'dark')
            self.assertEqual(config['default_table_density'], 'roomy')

    def test_get_system_config_rejects_unknown_default_theme(self):
        fake_settings = type('FakeSettings', (), {
            'system_names': {},
            'logo': '',
            'favicon': '',
            'home_url': '',
            'default_language': '',
            'default_theme': '',
            'languages': {},
            'translations_override': {},
            'sidebar_config': {},
            'is_configured': False,
        })()

        with patch('microsys.models.SystemSettings.load', return_value=fake_settings), override_settings(MICROSYS_CONFIG={'default_theme': 'missing-theme'}):
            config = get_system_config()

        self.assertEqual(config['default_theme'], 'light')

    def test_get_system_config_rejects_unknown_default_table_density(self):
        fake_settings = type('FakeSettings', (), {
            'system_names': {},
            'logo': '',
            'favicon': '',
            'home_url': '',
            'default_language': '',
            'default_theme': '',
            'default_table_density': 'invalid-density',
            'languages': {},
            'translations_override': {},
            'sidebar_config': {},
            'is_configured': False,
        })()

        with patch('microsys.models.SystemSettings.load', return_value=fake_settings), override_settings(MICROSYS_CONFIG={'default_table_density': 'missing-density'}):
            config = get_system_config()

        self.assertEqual(config['default_table_density'], DEFAULT_TABLE_DENSITY)

    def test_get_system_config_preserves_sidebar_behavior_flags(self):
        with override_settings(MICROSYS_CONFIG={
            'sidebar': {
                'entries': [],
                'enable_reorder': False,
                'show_toolbar': False,
            }
        }):
            config = get_system_config()

        self.assertFalse(config['sidebar']['enable_reorder'])
        self.assertFalse(config['sidebar']['show_toolbar'])

    @override_settings(MICROSYS_CONFIG={
        'sidebar': {
            'entries': [
                {
                    'kind': 'item',
                    'id': 'options_view',
                    'url_name': 'options_view',
                    'label': 'Options',
                    'icon': 'bi-gear',
                    'group_key': 'microsys',
                }
            ],
        },
        'titlebar': {
            'show_title': False,
        },
    })
    def test_get_system_config_preserves_sidebar_entries_and_titlebar_show_title(self):
        config = get_system_config()

        self.assertEqual(len(config['sidebar']['entries']), 1)
        self.assertEqual(config['sidebar']['entries'][0]['url_name'], 'options_view')
        self.assertFalse(config['titlebar']['show_title'])

    def test_get_system_config_with_database_override(self):
        """Test get_system_config with database override."""
        from microsys.models import SystemSettings
        
        settings = SystemSettings.load()
        settings.system_names = {'en': 'DB System', 'ar': 'نظام قاعدة البيانات'}
        settings.default_language = 'ar'
        settings.save()
        
        config = get_system_config()
        self.assertEqual(config['identity']['display_name'], 'نظام قاعدة البيانات')
        self.assertEqual(config['default_language'], 'ar')

    @override_settings(MICROSYS_CONFIG={
        'translations': {
            'fr': {
                'app_microsys': 'Systeme',
            },
        },
    })
    def test_translation_languages_do_not_auto_enable_language_catalog(self):
        config = get_system_config()

        self.assertNotIn('fr', config['languages'])
        self.assertNotIn('fr', config['localization']['languages'])

    def test_translation_matrix_uses_enabled_languages_and_preserves_override_only_layer(self):
        from microsys.translations import build_translation_matrix

        rows = build_translation_matrix(
            {'en': {'name': 'English'}, 'fr': {'name': 'Francais'}},
            {'fr': {'app_microsys': 'Systeme personnalise'}},
        )
        app_row = next(row for row in rows if row['key'] == 'app_microsys')
        fr_cell = next(cell for cell in app_row['cells'] if cell['language'] == 'fr')

        self.assertEqual(fr_cell['value'], 'Systeme personnalise')
        self.assertEqual(fr_cell['source'], 'override')

    def test_translation_matrix_groups_core_and_project_override_keys(self):
        from microsys.translations import build_translation_matrix_groups

        with self.settings(MICROSYS_CONFIG={
            'translations': {'en': {'project_only_key': 'Project only'}},
        }):
            groups = build_translation_matrix_groups(
                {'en': {'name': 'English'}},
                {'en': {'runtime_only_key': 'Runtime only'}},
            )

        group_ids = [group['id'] for group in groups]
        self.assertIn('microsys', group_ids)
        self.assertIn('project', group_ids)
        self.assertIn('runtime', group_ids)
        microsys_group = next(group for group in groups if group['id'] == 'microsys')
        self.assertTrue(any(row['key'] == 'app_microsys' for row in microsys_group['rows']))

    @override_settings(MICROSYS_CONFIG={
        'default_language': 'en',
        'translations': {
            'ar': {
                'label_systemsettings_public_root': 'الوصول العام للجذر',
                'label_public_root': 'الجذر العام',
            }
        },
    })
    def test_generic_detail_context_uses_translated_model_field_label(self):
        from microsys.models import SystemSettings

        self.user.profile.preferences = {'language': 'ar'}
        self.user.profile.save(update_fields=['preferences'])

        request = self.factory.get('/')
        request.user = self.user

        instance = SystemSettings(public_root=True)
        fields = _build_generic_detail_context(instance, request=request)
        labels = {field['label']: field['value'] for field in fields}

        self.assertIn('الوصول العام للجذر', labels)

    def test_is_scope_enabled(self):
        """Test is_scope_enabled utility function."""
        from microsys.models import ScopeSettings
        
        # Default should be False
        self.assertFalse(is_scope_enabled())
        
        # Enable scopes
        scope_settings = ScopeSettings.load()
        scope_settings.is_enabled = True
        scope_settings.save()
        
        self.assertTrue(is_scope_enabled())

    def test_staff_without_profile_fails_closed_for_staff_tiers(self):
        user = User.objects.create_user(
            username='missingprofile',
            email='missingprofile@example.com',
            password='missingpass123',
            is_staff=True,
        )
        Profile = apps.get_model('microsys', 'Profile')
        Profile.all_objects.filter(user=user).delete()
        user = User.objects.get(pk=user.pk)

        self.assertFalse(is_central_staff(user))
        self.assertFalse(is_global_staff(user))
        self.assertFalse(user_can_view_user_directory(user))

    def test_get_user_management_tier_state_classifies_core_tiers(self):
        self.assertEqual(
            get_user_management_tier_state(
                is_superuser=True,
                is_staff=True,
                scope=None,
                permission_codenames={'manage_scopes'},
            )['tier_key'],
            'superuser',
        )
        self.assertEqual(
            get_user_management_tier_state(
                is_superuser=False,
                is_staff=True,
                scope=None,
                permission_codenames={'manage_scopes'},
            )['tier_key'],
            'global_staff',
        )
        self.assertEqual(
            get_user_management_tier_state(
                is_superuser=False,
                is_staff=True,
                scope=None,
                permission_codenames=set(),
            )['tier_key'],
            'central_staff',
        )
        self.assertEqual(
            get_user_management_tier_state(
                is_superuser=False,
                is_staff=True,
                scope=SimpleNamespace(name='Finance'),
                permission_codenames=set(),
            )['tier_key'],
            'scoped_staff',
        )
        self.assertEqual(
            get_user_management_tier_state(
                is_superuser=False,
                is_staff=False,
                scope=None,
                permission_codenames={'manage_staff'},
            )['tier_key'],
            'regular_user',
        )

    def test_get_user_management_tier_state_emits_expected_warnings(self):
        scoped_conflict = get_user_management_tier_state(
            is_superuser=False,
            is_staff=True,
            scope=SimpleNamespace(name='Finance'),
            permission_codenames={'manage_scopes'},
        )
        self.assertEqual(scoped_conflict['tier_key'], 'scoped_staff')
        self.assertEqual(
            [warning['key'] for warning in scoped_conflict['warnings']],
            ['scoped_manage_scopes_conflict'],
        )

        no_staff_warning = get_user_management_tier_state(
            is_superuser=False,
            is_staff=False,
            scope=None,
            permission_codenames={'manage_staff'},
        )
        self.assertEqual(
            [warning['key'] for warning in no_staff_warning['warnings']],
            ['needs_staff'],
        )

    def test_get_user_management_tier_state_for_user_reads_effective_permissions(self):
        content_type = apps.get_model('contenttypes', 'ContentType').objects.get(app_label='microsys', model='profile')
        manage_scopes = apps.get_model('auth', 'Permission').objects.get(
            content_type=content_type,
            codename='manage_scopes',
        )
        user = User.objects.create_user(
            username='globaltier',
            email='globaltier@example.com',
            password='globaltierpass123',
            is_staff=True,
        )
        user.user_permissions.add(manage_scopes)

        state = get_user_management_tier_state_for_user(user)

        self.assertEqual(state['tier_key'], 'global_staff')

    def test_normalize_asset_url_with_absolute_url(self):
        """Test _normalize_asset_url with absolute URL."""
        url = _normalize_asset_url('http://example.com/image.png')
        self.assertEqual(url, 'http://example.com/image.png')
        
        url = _normalize_asset_url('https://example.com/image.png')
        self.assertEqual(url, 'https://example.com/image.png')

    def test_normalize_asset_url_with_relative_path(self):
        """Test _normalize_asset_url with relative path."""
        url = _normalize_asset_url('media/image.png')
        self.assertEqual(url, '/media/media/image.png')

    def test_normalize_asset_url_with_leading_slash(self):
        """Test _normalize_asset_url with leading slash."""
        url = _normalize_asset_url('/media/image.png')
        self.assertEqual(url, '/media/image.png')

    def test_normalize_asset_url_with_empty_value(self):
        """Test _normalize_asset_url with empty value."""
        url = _normalize_asset_url('')
        self.assertEqual(url, '')
        
        url = _normalize_asset_url(None)
        self.assertIsNone(url)

    def test_normalize_asset_url_with_media_url_setting(self):
        """Test _normalize_asset_url respects MEDIA_URL setting."""
        with override_settings(MEDIA_URL='/custom-media/'):
            url = _normalize_asset_url('image.png')
            self.assertEqual(url, '/custom-media/image.png')

    def test_discover_section_models(self):
        """Test discover_section_models function."""
        from microsys.utils import discover_section_models
        
        # Test with no app_name (should search all apps)
        models = discover_section_models(app_name=None, include_children=False)
        self.assertIsInstance(models, list)

    def test_resolve_model_by_name(self):
        """Test resolve_model_by_name function."""
        from microsys.utils import resolve_model_by_name
        
        # Test with valid model name
        model = resolve_model_by_name('User')
        self.assertIsNotNone(model)
        
        # Test with invalid model name
        model = resolve_model_by_name('InvalidModel')
        self.assertIsNone(model)

    def test_resolve_form_class_for_model(self):
        """Test resolve_form_class_for_model function."""
        from microsys.utils import resolve_form_class_for_model
        
        # Test with User model
        form_class = resolve_form_class_for_model(User)
        self.assertIsNotNone(form_class)

    def test_get_model_classes(self):
        """Test get_model_classes function."""
        from microsys.utils import get_model_classes
        
        # Test with User model
        classes = get_model_classes('User', app_label='auth')
        self.assertIn('form_class', classes)
        self.assertIn('table_class', classes)
        self.assertIn('filter_class', classes)

    def test_collect_related_objects(self):
        """Test collect_related_objects function."""
        from microsys.utils import collect_related_objects
        
        # Test with User instance
        related = collect_related_objects(self.user)
        self.assertIsInstance(related, dict)

    def test_has_related_records(self):
        """Test has_related_records function."""
        from microsys.utils import has_related_records
        
        # Test with User instance (should have profile)
        has_related = has_related_records(self.user)
        self.assertTrue(has_related)

    def test_setup_filter_helper(self):
        """Test setup_filter_helper function."""
        from microsys.utils import setup_filter_helper
        from django_filters import FilterSet
        
        # Create a simple filter
        class TestFilter(FilterSet):
            class Meta:
                model = User
                fields = ['username']
        
        request = self.factory.get('/')
        filter_obj = TestFilter(request.GET or None, queryset=User.objects.all())
        
        # Should not raise error
        setup_filter_helper(filter_obj, request)
        username_field = filter_obj.form.fields['username']
        self.assertEqual(username_field.label, '')
        self.assertTrue(username_field.widget.attrs.get('placeholder'))

    def test_set_field_attrs_preserves_labels_by_default(self):
        from django import forms
        from microsys.utils import set_field_attrs

        class TestForm(forms.Form):
            name = forms.CharField(label='Name')
            status = forms.ChoiceField(
                label='Status',
                choices=[('', '---------'), ('active', 'Active')],
                required=False,
            )
            is_active = forms.BooleanField(label='Is Active', required=False)

        form = TestForm()

        set_field_attrs(form)

        self.assertEqual(form.fields['name'].label, 'Name')
        self.assertIsNone(form.fields['name'].widget.attrs.get('placeholder'))
        self.assertEqual(form.fields['status'].label, 'Status')
        self.assertEqual(list(form.fields['status'].choices)[0][1], '---------')
        self.assertEqual(form.fields['is_active'].label, 'Is Active')

    def test_set_field_attrs_inline_labels_uses_placeholders_when_supported(self):
        from django import forms
        from microsys.utils import set_field_attrs

        class TestForm(forms.Form):
            name = forms.CharField(label='Name')
            status = forms.ChoiceField(
                label='Status',
                choices=[('', '---------'), ('active', 'Active')],
                required=False,
            )
            is_active = forms.BooleanField(label='Is Active', required=False)

        form = TestForm()

        set_field_attrs(form, inline_labels=True)

        self.assertEqual(form.fields['name'].label, '')
        self.assertEqual(form.fields['name'].widget.attrs.get('placeholder'), 'Name')
        self.assertEqual(form.fields['status'].label, '')
        self.assertEqual(list(form.fields['status'].choices)[0][1], 'Status')
        self.assertEqual(form.fields['is_active'].label, 'Is Active')
        self.assertIsNone(form.fields['is_active'].widget.attrs.get('placeholder'))

    def test_setup_filter_helper_can_disable_inline_labels(self):
        from microsys.utils import setup_filter_helper
        from django_filters import FilterSet

        class TestFilter(FilterSet):
            class Meta:
                model = User
                fields = ['username']

        request = self.factory.get('/')
        filter_obj = TestFilter(request.GET or None, queryset=User.objects.all())

        setup_filter_helper(filter_obj, request, inline_labels=False)

        username_field = filter_obj.form.fields['username']
        self.assertNotEqual(username_field.label, '')
        self.assertIsNone(username_field.widget.attrs.get('placeholder'))

    def test_has_submit_button(self):
        """Test has_submit_button function."""
        from microsys.utils import has_submit_button
        from django import forms
        from crispy_forms.helper import FormHelper
        from crispy_forms.layout import HTML, Layout
        
        # Create a form with submit button
        class TestForm(forms.Form):
            name = forms.CharField()
        
        form = TestForm()
        self.assertFalse(has_submit_button(form))

        form.helper = FormHelper()
        form.helper.layout = Layout(HTML("<button type='submit' class='btn btn-primary'>Save</button>"))
        self.assertTrue(has_submit_button(form))
