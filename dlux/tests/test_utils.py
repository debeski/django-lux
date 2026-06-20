from django.apps import apps
from types import SimpleNamespace
from unittest.mock import mock_open, patch

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.test import TestCase, RequestFactory, override_settings
from django.contrib.auth import get_user_model
from django.contrib.messages import constants as messages
from django.core.cache import cache
from dlux import __version__, get_version
from dlux.constants import DEFAULT_TABLE_DENSITY
from dlux.utils import (
    get_system_config, is_staff, is_superuser, get_client_ip,
    log_user_action, is_scope_enabled, _normalize_asset_url,
    get_secret, dlux_settings, _build_generic_detail_context,
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
        with override_settings(DLUX_CONFIG={'client_ip': {'mode': 'x_forwarded_for', 'trusted_proxy_hops': 1}}):
            request = self.factory.get('/')
            request.META['HTTP_X_FORWARDED_FOR'] = '192.168.1.1, 10.0.0.1'
            request.META['REMOTE_ADDR'] = '10.0.0.1'
            ip = get_client_ip(request)
        self.assertEqual(ip, '192.168.1.1')

    def test_get_client_ip_with_remote_addr(self):
        """Test get_client_ip with REMOTE_ADDR."""
        request = self.factory.get('/')
        request.META['REMOTE_ADDR'] = '192.168.1.2'
        ip = get_client_ip(request)
        self.assertEqual(ip, '192.168.1.2')

    def test_get_client_ip_with_x_real_ip_mode(self):
        with override_settings(DLUX_CONFIG={'client_ip': {'mode': 'x_real_ip'}}):
            request = self.factory.get('/')
            request.META['HTTP_X_REAL_IP'] = '198.51.100.8'
            request.META['REMOTE_ADDR'] = '10.0.0.1'

            ip = get_client_ip(request)

        self.assertEqual(ip, '198.51.100.8')

    def test_get_client_ip_with_custom_header_mode(self):
        with override_settings(DLUX_CONFIG={'client_ip': {'mode': 'custom', 'custom_header': 'CF-Connecting-IP'}}):
            request = self.factory.get('/')
            request.META['HTTP_CF_CONNECTING_IP'] = '203.0.113.40'
            request.META['REMOTE_ADDR'] = '10.0.0.1'

            ip = get_client_ip(request)

        self.assertEqual(ip, '203.0.113.40')

    def test_get_client_ip_without_headers(self):
        """Test get_client_ip without IP headers."""
        request = self.factory.get('/')
        request.META.pop('REMOTE_ADDR', None)
        ip = get_client_ip(request)
        self.assertIsNone(ip)

    def test_dlux_settings_adds_locale_and_message_defaults(self):
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

        dlux_settings(scope)

        self.assertEqual(scope['INSTALLED_APPS'][:5], [
            'dlux',
            'crispy_forms',
            'crispy_bootstrap5',
            'django_filters',
            'django_tables2',
        ])
        self.assertIn('dlux.context_processors.dlux_context', scope['TEMPLATES'][0]['OPTIONS']['context_processors'])
        self.assertEqual(
            scope['MIDDLEWARE'].index('django.middleware.locale.LocaleMiddleware'),
            scope['MIDDLEWARE'].index('django.middleware.common.CommonMiddleware') - 1,
        )
        self.assertEqual(
            scope['MIDDLEWARE'].index('dlux.middleware.DluxMiddleware'),
            scope['MIDDLEWARE'].index('django.contrib.auth.middleware.AuthenticationMiddleware') + 1,
        )
        self.assertEqual(scope['MESSAGE_TAGS'][messages.ERROR], 'danger')
        self.assertEqual(scope['MESSAGE_TAGS'][messages.INFO], 'info-custom')

    def test_dlux_settings_preserves_existing_scalar_defaults(self):
        scope = {
            'INSTALLED_APPS': [],
            'MIDDLEWARE': [],
            'TEMPLATES': [],
            'USE_I18N': False,
            'USE_TZ': False,
            'DEFAULT_CHARSET': 'latin-1',
            'FORMAT_MODULE_PATH': ['project.formats'],
        }

        dlux_settings(scope)

        self.assertFalse(scope['USE_I18N'])
        self.assertFalse(scope['USE_TZ'])
        self.assertEqual(scope['DEFAULT_CHARSET'], 'latin-1')
        self.assertEqual(scope['FORMAT_MODULE_PATH'], ['project.formats', 'dlux.formats'])

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
        from dlux.models import UserActivityLog
        
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
        from dlux.models import UserActivityLog
        
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
        from dlux.models import UserActivityLog
        
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
        self.assertEqual(config['identity']['display_name'], 'DjangoLux')
        self.assertTrue(config['allow_user_language_override'])
        self.assertEqual(config['default_table_density'], DEFAULT_TABLE_DENSITY)

    def test_get_system_config_with_settings_override(self):
        """Test get_system_config with DLUX_CONFIG override."""
        with override_settings(DLUX_CONFIG={
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

    def test_get_system_config_accepts_nested_config_aliases(self):
        from dlux.models import SystemSettings

        SystemSettings.objects.all().delete()
        cache.clear()
        with override_settings(DLUX_CONFIG={
            'default_theme': 'dark',
            'auth_config': {
                'email_2fa': True,
                'prevent_multiple_active_sessions': True,
                'login_lockout_enabled': False,
            },
            'registration_config': {
                'public_registration_enabled': True,
                'registration_activation_mode': 'verified_pending_approval',
                'registration_throttle_enabled': False,
            },
            'public_root_config': {
                'public_root': True,
                'public_root_split_enabled': True,
                'public_root_url': '/public/',
            },
            'layout_config': {'default_table_density': 'dense'},
            'language_config': {
                'translations_override': {'en': {'custom_key': 'Custom'}},
                'allow_user_language_override': False,
            },
            'theme_config': {
                'allowed_themes': ['dark'],
                'allow_user_theme_override': False,
            },
            'typography_config': {
                'allowed_fonts': ['cairo'],
                'default_fonts': {'en': 'cairo'},
                'allow_user_font_override': False,
            },
            'extra_config': {'host_flag': True},
        }):
            config = get_system_config()

        self.assertTrue(config['email_2fa'])
        self.assertTrue(config['prevent_multiple_active_sessions'])
        self.assertFalse(config['login_lockout_enabled'])
        self.assertTrue(config['public_registration_enabled'])
        self.assertEqual(config['registration_activation_mode'], 'verified_pending_approval')
        self.assertFalse(config['registration_throttle_enabled'])
        self.assertTrue(config['public_root'])
        self.assertTrue(config['public_root_split_enabled'])
        self.assertEqual(config['public_root_url'], '/public/')
        self.assertEqual(config['default_table_density'], 'dense')
        self.assertEqual(config['allowed_themes'], ['dark'])
        self.assertFalse(config['allow_user_theme_override'])
        self.assertIn('cairo', config['allowed_fonts'])
        self.assertEqual(config['default_fonts'], {'en': 'cairo'})
        self.assertFalse(config['allow_user_font_override'])
        self.assertFalse(config['allow_user_language_override'])
        self.assertEqual(config['extra_config'], {'host_flag': True})
        self.assertEqual(config['language_config']['translations_override'], {'en': {'custom_key': 'Custom'}})
        self.assertNotIn('app_dlux', config['language_config']['translations_override']['en'])
        self.assertEqual(config['translations']['en']['custom_key'], 'Custom')

    def test_get_system_config_reads_grouped_database_values(self):
        from dlux.models import SystemSettings

        settings_obj = SystemSettings.load()
        settings_obj.is_configured = True
        settings_obj.auth_config = {
            'email_2fa': True,
            'prevent_multiple_active_sessions': True,
            'login_lockout_enabled': False,
        }
        settings_obj.public_root_config = {
            'public_root': True,
            'public_root_split_enabled': True,
            'public_root_url': '/anonymous/',
        }
        settings_obj.layout_config = {'default_table_density': 'roomy'}
        settings_obj.language_config = {
            'languages': {},
            'translations_override': {'en': {'db_key': 'DB'}},
            'allow_user_language_override': False,
        }
        settings_obj.save()

        config = get_system_config()

        self.assertTrue(config['email_2fa'])
        self.assertTrue(config['prevent_multiple_active_sessions'])
        self.assertFalse(config['login_lockout_enabled'])
        self.assertTrue(config['public_root'])
        self.assertTrue(config['public_root_split_enabled'])
        self.assertEqual(config['public_root_url'], '/anonymous/')
        self.assertEqual(config['default_table_density'], 'roomy')
        self.assertFalse(config['allow_user_language_override'])
        self.assertEqual(config['language_config']['translations_override'], {'en': {'db_key': 'DB'}})
        self.assertEqual(config['translations']['en']['db_key'], 'DB')

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

        with patch('dlux.models.SystemSettings.load', return_value=fake_settings), override_settings(DLUX_CONFIG={'default_theme': 'missing-theme'}):
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

        with patch('dlux.models.SystemSettings.load', return_value=fake_settings), override_settings(DLUX_CONFIG={'default_table_density': 'missing-density'}):
            config = get_system_config()

        self.assertEqual(config['default_table_density'], DEFAULT_TABLE_DENSITY)

    def test_get_system_config_preserves_sidebar_behavior_flags(self):
        with override_settings(DLUX_CONFIG={
            'sidebar': {
                'entries': [],
                'enable_reorder': False,
                'show_toolbar': False,
            }
        }):
            config = get_system_config()

        self.assertFalse(config['sidebar']['enable_reorder'])
        self.assertFalse(config['sidebar']['show_toolbar'])

    def test_get_system_config_preserves_disabled_sidebar_child_flags_for_future_restore(self):
        with override_settings(DLUX_CONFIG={
            'sidebar': {
                'enabled': False,
                'entries': [],
                'enable_reorder': True,
                'show_toolbar': True,
                'show_icons': True,
                'density': 'roomy',
                'allow_user_density': True,
                'collapse_mode': 'icons',
            }
        }):
            config = get_system_config()

        self.assertFalse(config['sidebar']['enabled'])
        self.assertTrue(config['sidebar']['enable_reorder'])
        self.assertTrue(config['sidebar']['show_toolbar'])
        self.assertTrue(config['sidebar']['show_icons'])
        self.assertEqual(config['sidebar']['density'], 'roomy')
        self.assertTrue(config['sidebar']['allow_user_density'])
        self.assertEqual(config['sidebar']['collapse_mode'], 'icons')

    @override_settings(DLUX_CONFIG={
        'sidebar': {
            'entries': [
                {
                    'kind': 'item',
                    'id': 'options_view',
                    'url_name': 'options_view',
                    'label': 'Options',
                    'icon': 'bi-gear',
                    'group_key': 'dlux',
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
        from dlux.models import SystemSettings
        
        settings = SystemSettings.load()
        settings.system_names = {'en': 'DB System', 'ar': 'نظام قاعدة البيانات'}
        settings.default_language = 'ar'
        settings.save()
        
        config = get_system_config()
        self.assertEqual(config['identity']['display_name'], 'نظام قاعدة البيانات')
        self.assertEqual(config['default_language'], 'ar')

    @override_settings(DLUX_CONFIG={
        'translations': {
            'fr': {
                'app_dlux': 'Systeme',
            },
        },
    })
    def test_translation_languages_do_not_auto_enable_language_catalog(self):
        config = get_system_config()

        self.assertNotIn('fr', config['languages'])
        self.assertNotIn('fr', config['localization']['languages'])

    def test_translation_matrix_uses_enabled_languages_and_preserves_override_only_layer(self):
        from dlux.translations import build_translation_matrix

        rows = build_translation_matrix(
            {'en': {'name': 'English'}, 'fr': {'name': 'Francais'}},
            {'fr': {'app_dlux': 'Systeme personnalise'}},
        )
        app_row = next(row for row in rows if row['key'] == 'app_dlux')
        fr_cell = next(cell for cell in app_row['cells'] if cell['language'] == 'fr')

        self.assertEqual(fr_cell['value'], 'Systeme personnalise')
        self.assertEqual(fr_cell['source'], 'override')

    def test_lazy_translator_renders_current_language_but_serializes_stably(self):
        from django.db.migrations.serializer import serializer_factory
        from dlux.translations import lazy_translator

        label = lazy_translator('label_name', 'Name')

        with patch('dlux.translations.get_strings', return_value={'label_name': 'الاسم'}):
            self.assertEqual(str(label), 'الاسم')

        serialized, imports = serializer_factory(label).serialize()
        self.assertEqual(serialized, "'Name'")
        self.assertEqual(imports, set())
        self.assertEqual(label, 'Name')

    def test_translation_matrix_groups_core_and_project_override_keys(self):
        from dlux.translations import build_translation_matrix_groups

        with self.settings(DLUX_CONFIG={
            'translations': {'en': {'project_only_key': 'Project only'}},
        }):
            groups = build_translation_matrix_groups(
                {'en': {'name': 'English'}},
                {'en': {'runtime_only_key': 'Runtime only'}},
            )

        group_ids = [group['id'] for group in groups]
        self.assertIn('dlux', group_ids)
        self.assertIn('project', group_ids)
        self.assertIn('runtime', group_ids)
        dlux_group = next(group for group in groups if group['id'] == 'dlux')
        self.assertTrue(any(row['key'] == 'app_dlux' for row in dlux_group['rows']))

    def test_translation_matrix_keeps_discovered_app_keys_in_app_source_group(self):
        from dlux.translations import (
            _discover_and_merge_translations,
            _discover_translation_source_layers,
            build_translation_matrix_groups,
        )

        app_config = SimpleNamespace(
            name='demo_matrix_app',
            label='demo_matrix_app',
            verbose_name='Demo Matrix App',
        )
        app_module = SimpleNamespace(DLUX_STRINGS={
            'en': {'demo_matrix_only_key': 'Demo app value'},
            'ar': {'demo_matrix_only_key': 'قيمة التطبيق'},
        })

        _discover_and_merge_translations.cache_clear()
        _discover_translation_source_layers.cache_clear()
        with patch('dlux.translations.apps.get_app_configs', return_value=[app_config]), \
             patch('dlux.translations.import_module', return_value=app_module):
            groups = build_translation_matrix_groups({'en': {'name': 'English'}})
        _discover_and_merge_translations.cache_clear()
        _discover_translation_source_layers.cache_clear()

        group_ids = [group['id'] for group in groups]
        self.assertIn('demo_matrix_app', group_ids)
        app_group = next(group for group in groups if group['id'] == 'demo_matrix_app')
        self.assertTrue(any(row['key'] == 'demo_matrix_only_key' for row in app_group['rows']))
        dlux_group = next(group for group in groups if group['id'] == 'dlux')
        self.assertFalse(any(row['key'] == 'demo_matrix_only_key' for row in dlux_group['rows']))

    @override_settings(DLUX_CONFIG={
        'default_language': 'en',
        'translations': {
            'ar': {
                'label_systemsettings_public_root': 'الوصول العام للجذر',
                'label_public_root': 'الجذر العام',
            }
        },
    })
    def test_generic_detail_context_uses_translated_model_field_label(self):
        from dlux.models import SystemSettings

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
        from dlux.models import ScopeSettings
        
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
        Profile = apps.get_model('dlux', 'Profile')
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
        content_type = apps.get_model('contenttypes', 'ContentType').objects.get(app_label='dlux', model='profile')
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
        from dlux.utils import discover_section_models
        
        # Test with no app_name (should search all apps)
        models = discover_section_models(app_name=None, include_children=False)
        self.assertIsInstance(models, list)

    def test_resolve_model_by_name(self):
        """Test resolve_model_by_name function."""
        from dlux.utils import resolve_model_by_name
        
        # Test with valid model name
        model = resolve_model_by_name('User')
        self.assertIsNotNone(model)
        
        # Test with invalid model name
        model = resolve_model_by_name('InvalidModel')
        self.assertIsNone(model)

    def test_resolve_form_class_for_model(self):
        """Test resolve_form_class_for_model function."""
        from dlux.utils import resolve_form_class_for_model
        
        # Test with User model
        form_class = resolve_form_class_for_model(User)
        self.assertIsNotNone(form_class)

    def test_get_model_classes(self):
        """Test get_model_classes function."""
        from dlux.utils import get_model_classes
        
        # Test with User model
        classes = get_model_classes('User', app_label='auth')
        self.assertIn('form_class', classes)
        self.assertIn('table_class', classes)
        self.assertIn('filter_class', classes)

    def test_collect_related_objects(self):
        """Test collect_related_objects function."""
        from dlux.utils import collect_related_objects
        
        # Test with User instance
        related = collect_related_objects(self.user)
        self.assertIsInstance(related, dict)

    def test_has_related_records(self):
        """Test has_related_records function."""
        from dlux.utils import has_related_records
        
        # Test with User instance (should have profile)
        has_related = has_related_records(self.user)
        self.assertTrue(has_related)

    def test_setup_filter_helper(self):
        """Test setup_filter_helper function."""
        from dlux.utils import setup_filter_helper
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
        from dlux.utils import set_field_attrs

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
        from dlux.utils import set_field_attrs

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
        from dlux.utils import setup_filter_helper
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
        from dlux.utils import has_submit_button
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

    def test_safe_referer(self):
        """Test _safe_referer to prevent open-redirect vulnerabilities."""
        from dlux.fetcher import _safe_referer
        from django.test import RequestFactory

        factory = RequestFactory()

        # 1. No HTTP_REFERER header -> returns '/'
        request = factory.get('/')
        self.assertEqual(_safe_referer(request), '/')

        # 2. Local HTTP_REFERER matching host -> returns the referer
        request = factory.get('/', HTTP_REFERER='http://testserver/some/path/')
        self.assertEqual(_safe_referer(request), 'http://testserver/some/path/')

        # 3. Local HTTP_REFERER matching ALLOWED_HOSTS -> returns the referer
        with override_settings(ALLOWED_HOSTS=['allowedhost.com', 'testserver']):
            request = factory.get('/', HTTP_REFERER='http://allowedhost.com/some/path/')
            self.assertEqual(_safe_referer(request), 'http://allowedhost.com/some/path/')

        # 4. Untrusted external referer -> returns '/'
        request = factory.get('/', HTTP_REFERER='http://malicious-external-site.com/evil')
        self.assertEqual(_safe_referer(request), '/')

        # 5. Relative referer path -> returns the relative referer path
        request = factory.get('/', HTTP_REFERER='/local/path/')
        self.assertEqual(_safe_referer(request), '/local/path/')
