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
        DEFAULT_AUTO_FIELD='django.db.models.BigAutoField',
        USE_TZ=True,
        CRISPY_ALLOWED_TEMPLATE_PACKS='bootstrap5',
        CRISPY_TEMPLATE_PACK='bootstrap5',
    )

    import django

    django.setup()

from django.test import Client, RequestFactory, SimpleTestCase, override_settings
from django.template import Context, Template
from django.urls import clear_url_caches
from django.core.files.uploadedfile import SimpleUploadedFile
from types import SimpleNamespace
from unittest.mock import call, patch
import json

from microsys.constants import DEFAULT_HOME_URL, DEFAULT_TABLE_DENSITY, LEGACY_HOME_URL
from microsys.forms import SystemSettingsForm
from microsys.models import SystemSettings
from microsys.themes import get_theme_names
from microsys.utils import (
    decrypt_email_secret,
    export_system_settings_payload,
    get_microsys_email_config,
    get_system_config,
    normalize_system_settings_import_payload,
)


class MicrosysDefaultRouteTests(SimpleTestCase):
    @override_settings(MICROSYS_CONFIG={})
    def test_system_config_defaults_home_url_to_profile(self):
        self.assertEqual(get_system_config().get('home_url'), DEFAULT_HOME_URL)

    def test_unconfigured_root_url_redirects_to_system_setup(self):
        response = Client().get('/')

        self.assertRedirects(
            response,
            '/sys/setup/',
            fetch_redirect_response=False,
        )

    @override_settings(MICROSYS_CONFIG={'is_configured': True})
    def test_configured_root_url_redirects_to_login(self):
        response = Client().get('/')

        self.assertRedirects(
            response,
            '/accounts/login/',
            fetch_redirect_response=False,
        )

    @override_settings(ROOT_URLCONF='microsys.tests.urls_with_root_index')
    def test_unconfigured_existing_project_root_redirects_to_system_setup(self):
        clear_url_caches()
        response = Client().get('/')

        self.assertRedirects(
            response,
            '/sys/setup/',
            fetch_redirect_response=False,
        )

    @override_settings(ROOT_URLCONF='microsys.tests.urls_with_root_index', MICROSYS_CONFIG={'is_configured': True})
    def test_configured_existing_project_root_view_is_not_hijacked(self):
        clear_url_caches()
        response = Client().get('/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'project index')

    @override_settings(ROOT_URLCONF='microsys.tests.urls_with_prefix_mount')
    def test_prefix_mount_does_not_hijack_project_root(self):
        clear_url_caches()
        response = Client().get('/')

        self.assertEqual(response.status_code, 404)

    @override_settings(MICROSYS_CONFIG={})
    def test_setup_form_replaces_legacy_sys_home_url_for_unconfigured_instance(self):
        form = SystemSettingsForm(
            instance=SystemSettings(home_url=LEGACY_HOME_URL, is_configured=False),
        )

        self.assertEqual(form.initial['home_url'], DEFAULT_HOME_URL)

    @override_settings(MICROSYS_CONFIG={
        'default_theme': 'neon',
        'default_table_density': 'roomy',
        'sidebar': {
            'entries': [],
            'enable_reorder': False,
            'show_toolbar': False,
        },
    })
    def test_setup_form_surfaces_neon_and_sidebar_behavior_flags(self):
        form = SystemSettingsForm(
            instance=SystemSettings(default_theme='neon', is_configured=False),
        )

        theme_choices = [value for value, _label in form.fields['default_theme'].choices]

        self.assertIn('neon', theme_choices)
        self.assertEqual(theme_choices, list(get_theme_names()))
        self.assertEqual(form.initial['default_theme'], 'neon')
        self.assertEqual(form.initial['default_table_density'], 'roomy')
        self.assertFalse(form.initial['sidebar_enable_reorder'])
        self.assertFalse(form.initial['sidebar_enable_toolbar'])

    @override_settings(MICROSYS_CONFIG={
        'default_theme': 'retro',
        'allowed_themes': ['retro', 'dark'],
        'allow_user_theme_override': False,
        'allow_user_language_override': False,
        'sidebar': {
            'entries': [],
            'show_icons': False,
            'density': 'roomy',
            'allow_user_density': False,
            'collapse_mode': 'icons',
        },
        'titlebar': {
            'show_logo': False,
            'show_home_button': False,
            'home_shape': 'square',
            'title_align': 'center',
            'title_size': 'lg',
            'height': 'roomy',
            'surface': 'glass',
        },
    })
    def test_setup_form_surfaces_allowed_themes_sidebar_and_titlebar_defaults(self):
        form = SystemSettingsForm(
            instance=SystemSettings(default_theme='retro', is_configured=False),
        )

        self.assertEqual(form.initial['allowed_themes'], ['retro', 'dark'])
        self.assertFalse(form.initial['allow_user_theme_override'])
        self.assertFalse(form.initial['allow_user_language_override'])
        self.assertFalse(form.initial['sidebar_show_icons'])
        self.assertEqual(form.initial['sidebar_density'], 'roomy')
        self.assertFalse(form.initial['sidebar_allow_user_density'])
        self.assertEqual(form.initial['sidebar_collapse_mode'], 'hidden')
        self.assertFalse(form.initial['titlebar_show_logo'])
        self.assertFalse(form.initial['titlebar_show_home_button'])
        self.assertEqual(form.initial['titlebar_home_shape'], 'square')
        self.assertEqual(form.initial['titlebar_title_align'], 'center')
        self.assertEqual(form.initial['titlebar_title_size'], 'lg')
        self.assertEqual(form.initial['titlebar_height'], 'roomy')
        self.assertEqual(form.initial['titlebar_surface'], 'glass')

    @override_settings(MICROSYS_CONFIG={
        'titlebar': {
            'show_title': False,
        },
    })
    def test_setup_form_surfaces_titlebar_toggle_widgets_and_step_four(self):
        request = RequestFactory().get('/sys/modals/microsys/systemsettings/1/?step=3')
        form = SystemSettingsForm(
            instance=SystemSettings(is_configured=False),
            request=request,
        )

        self.assertTrue(form.single_step_mode)
        self.assertEqual(form.single_step_index, 3)
        self.assertFalse(form.initial['titlebar_show_title'])
        self.assertIn('data-ms-selector-variant="toggle"', str(form['default_table_density']))
        self.assertIn('lang-option', str(form['default_table_density']))
        self.assertIn('data-ms-selector-variant="toggle"', str(form['sidebar_density']))
        self.assertIn('ms-choice-option', str(form['sidebar_collapse_mode']))
        self.assertIn('lang-option', str(form['sidebar_collapse_mode']))
        self.assertIn('ms-choice-option', str(form['titlebar_title_align']))
        self.assertIn('data-ms-selector-variant="toggle"', str(form['titlebar_title_align']))
        self.assertIn('ms-choice-option', str(form['titlebar_surface']))
        self.assertIn('<select', str(form['home_url_discovered']))
        self.assertNotIn('data-ms-selector-search', str(form['home_url_discovered']))

    def test_setup_theme_picker_keeps_allow_checkboxes_separate_from_default_selector(self):
        form = SystemSettingsForm(
            instance=SystemSettings(is_configured=False),
            mode='setup',
        )

        self.assertIn('data-setup-theme-choice="light"', form.theme_picker_html)
        self.assertIn('data-setup-theme-allowed="light"', form.theme_picker_html)
        self.assertIn('ms-theme-settings-option__checkbox', form.theme_picker_html)

    @override_settings(MICROSYS_CONFIG={'system_names': {'en': 'Demo System', 'ar': 'نظام تجريبي'}})
    def test_setup_identity_step_renders_language_keyed_system_names(self):
        form = SystemSettingsForm(
            instance=SystemSettings(is_configured=False),
            mode='setup',
        )

        html = Template('{% load crispy_forms_tags %}{% crispy form %}').render(Context({'form': form}))

        self.assertIn('data-system-names-editor', html)
        self.assertIn('data-system-name-row data-language-code="en"', html)
        self.assertIn('value="Demo System"', html)
        self.assertIn('data-language-catalog-editor', html)
        self.assertIn('data-translation-group-tab="microsys"', html)
        self.assertNotIn('data-setup-language-picker', html)

    def test_setup_form_import_file_overrides_posted_setup_values_on_initial_import(self):
        """On initial import (JS populated, flag not set), import overrides posted defaults."""
        payload = {
            'format': 'django-microsys.system-settings',
            'version': 1,
            'settings': {
                'system_names': {'en': 'Imported System', 'fr': 'Systeme Importe'},
                'languages': {'fr': {'name': 'Francais', 'dir': 'ltr', 'flag': 'FR'}},
                'default_language': 'fr',
                'default_theme': 'dark',
                'allowed_themes': ['dark'],
                'translations_override': {'fr': {'app_microsys': 'Systeme'}},
                'home_url': '/imported/',
                'default_table_density': 'dense',
                'sidebar_config': {'entries': [], 'density': 'dense', 'collapse_mode': 'hidden'},
                'titlebar_config': {'show_title': False, 'title_align': 'center'},
            },
        }
        import_file = SimpleUploadedFile(
            'microsys-system-settings.json',
            json.dumps(payload).encode('utf-8'),
            content_type='application/json',
        )
        form = SystemSettingsForm(
            data={
                'system_names': '{"en": "Posted"}',
                'home_url': '/',
                'default_language': 'en',
                'default_theme': 'light',
                'allowed_themes': ['light'],
                'default_table_density': 'balanced',
                'languages': '{}',
                'translations_override': '{}',
                'sidebar_config': '{"entries":[]}',
            },
            files={'settings_import_file': import_file},
            instance=SystemSettings(is_configured=False),
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['system_names']['en'], 'Imported System')
        self.assertIn('fr', form.cleaned_data['languages'])
        self.assertEqual(form.cleaned_data['default_language'], 'fr')
        self.assertEqual(form.cleaned_data['default_theme'], 'dark')
        self.assertEqual(form.cleaned_data['home_url'], '/imported/')
        self.assertEqual(form.cleaned_data['sidebar_config']['density'], 'dense')
        self.assertFalse(form.cleaned_data['titlebar_config']['show_title'])

    def test_setup_form_import_restores_email_config_and_sidebar_enabled_flag(self):
        payload = {
            'format': 'django-microsys.system-settings',
            'version': 1,
            'settings': {
                'system_names': {'en': 'Imported System'},
                'default_language': 'en',
                'default_theme': 'light',
                'allowed_themes': ['light'],
                'default_table_density': 'balanced',
                'languages': {'en': {'name': 'English', 'dir': 'ltr', 'flag': 'EN'}},
                'translations_override': {},
                'home_url': '/',
                'email_config': {
                    'mode': 'encrypted_db',
                    'host': 'smtp.example.com',
                    'port': 587,
                    'use_tls': True,
                    'username': 'mailer@example.com',
                    'default_from_email': 'security@example.com',
                    'password_configured': True,
                },
                'sidebar_config': {'enabled': False, 'entries': [], 'density': 'dense'},
            },
        }
        import_file = SimpleUploadedFile(
            'microsys-system-settings.json',
            json.dumps(payload).encode('utf-8'),
            content_type='application/json',
        )
        form = SystemSettingsForm(
            data={
                'system_names': '{"en": "Posted"}',
                'home_url': '/',
                'default_language': 'en',
                'default_theme': 'light',
                'allowed_themes': ['light'],
                'default_table_density': 'balanced',
                'languages': '{}',
                'translations_override': '{}',
                'sidebar_config': '{"entries":[]}',
            },
            files={'settings_import_file': import_file},
            instance=SystemSettings(is_configured=False),
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['email_config']['mode'], 'encrypted_db')
        self.assertEqual(form.cleaned_data['email_config']['host'], 'smtp.example.com')
        self.assertFalse(form.cleaned_data['email_config']['password_configured'])
        self.assertFalse(form.cleaned_data['sidebar_config']['enabled'])
        self.assertFalse(form.cleaned_data['sidebar_enable_toolbar'])

    def test_setup_form_import_does_not_override_when_processed_flag_set(self):
        """When import is marked as processed, user edits are preserved and import is skipped."""
        payload = {
            'format': 'django-microsys.system-settings',
            'version': 1,
            'settings': {
                'system_names': {'en': 'Imported System'},
                'default_language': 'fr',
                'default_theme': 'dark',
            },
        }
        import_file = SimpleUploadedFile(
            'microsys-system-settings.json',
            json.dumps(payload).encode('utf-8'),
            content_type='application/json',
        )
        form = SystemSettingsForm(
            data={
                'system_names': '{"en": "User Edited"}',
                'default_language': 'en',
                'default_theme': 'light',
                'allowed_themes': ['light'],
                'default_table_density': 'balanced',
                'languages': '{}',
                'translations_override': '{}',
                'sidebar_config': '{"entries":[]}',
                'settings_import_processed': 'true',
            },
            files={'settings_import_file': import_file},
            instance=SystemSettings(is_configured=False),
        )

        self.assertTrue(form.is_valid(), form.errors)
        # User edits should be preserved, not overridden by import
        self.assertEqual(form.cleaned_data['system_names']['en'], 'User Edited')
        self.assertEqual(form.cleaned_data['default_language'], 'en')
        self.assertEqual(form.cleaned_data['default_theme'], 'light')

    def test_crispy_setup_render_uses_custom_toggle_markup_for_choice_fields(self):
        form = SystemSettingsForm(
            instance=SystemSettings(is_configured=False),
            mode='setup',
        )

        html = Template('{% load crispy_forms_tags %}{% crispy form %}').render(Context({'form': form}))

        self.assertIn('ms-choice-selector--toggle', html)
        self.assertIn('id="id_default_table_density"', html)
        self.assertIn('id="id_titlebar_title_align"', html)
        self.assertNotIn('<fieldset aria-describedby="id_default_table_density_helptext">', html)
        self.assertNotIn('<fieldset> <legend', html)

    def test_setup_form_rejects_empty_allowed_themes(self):
        form = SystemSettingsForm(
            data={
                'system_names': '{"en": "System", "ar": "System"}',
                'home_url': '/',
                'default_language': 'en',
                'default_theme': 'light',
                'default_table_density': 'balanced',
                'languages': '{}',
                'translations_override': '{}',
                'sidebar_config': '{"entries":[]}',
            },
            instance=SystemSettings(is_configured=False),
        )

        self.assertFalse(form.is_valid())
        self.assertIn('allowed_themes', form.errors)

    def test_setup_form_rejects_default_theme_outside_allowlist(self):
        form = SystemSettingsForm(
            data={
                'system_names': '{"en": "System", "ar": "System"}',
                'home_url': '/',
                'default_language': 'en',
                'default_theme': 'light',
                'allowed_themes': ['dark'],
                'default_table_density': 'balanced',
                'languages': '{}',
                'translations_override': '{}',
                'sidebar_config': '{"entries":[]}',
            },
            instance=SystemSettings(is_configured=False),
        )

        self.assertFalse(form.is_valid())
        self.assertIn('default_theme', form.errors)

    def test_setup_form_saves_encrypted_db_email_secret_without_plaintext(self):
        form = SystemSettingsForm(
            data={
                'system_names': '{"en": "System", "ar": "System"}',
                'home_url': '/',
                'default_language': 'en',
                'default_theme': 'light',
                'allowed_themes': ['light'],
                'default_table_density': 'balanced',
                'languages': '{}',
                'translations_override': '{}',
                'email_2fa': 'on',
                'email_config_mode': 'encrypted_db',
                'email_config_host': 'smtp.example.com',
                'email_config_port': '587',
                'email_config_use_tls': 'on',
                'email_config_username': 'mailer@example.com',
                'email_config_password': 'app-secret-pass',
                'email_config_default_from_email': 'security@example.com',
                'sidebar_config': '{"entries":[]}',
            },
            instance=SystemSettings(is_configured=False),
        )

        self.assertTrue(form.is_valid(), form.errors)
        email_config = form.cleaned_data['email_config']
        self.assertEqual(email_config['mode'], 'encrypted_db')
        self.assertTrue(email_config['encrypted_password'])
        self.assertNotEqual(email_config['encrypted_password'], 'app-secret-pass')
        self.assertEqual(decrypt_email_secret(email_config['encrypted_password']), 'app-secret-pass')

    def test_system_settings_export_redacts_email_secret_and_preserves_sidebar_enabled(self):
        settings_obj = SystemSettings(
            system_names={'en': 'Export System'},
            default_language='en',
            default_theme='light',
            allowed_themes=['light'],
            email_config={
                'mode': 'encrypted_db',
                'host': 'smtp.example.com',
                'port': 587,
                'use_tls': True,
                'username': 'mailer@example.com',
                'default_from_email': 'security@example.com',
                'encrypted_password': 'ciphertext-value',
                'password_configured': True,
            },
            sidebar_config={'enabled': False, 'entries': []},
        )

        payload = export_system_settings_payload(settings_obj)
        email_config = payload['settings']['email_config']

        self.assertNotIn('encrypted_password', email_config)
        self.assertTrue(email_config['password_configured'])
        self.assertEqual(email_config['mode'], 'encrypted_db')
        self.assertFalse(payload['settings']['sidebar_config']['enabled'])

        imported = normalize_system_settings_import_payload(payload)
        self.assertNotIn('encrypted_password', imported['email_config'])
        self.assertTrue(imported['email_config']['password_configured'])

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
        EMAIL_HOST='settings-smtp.example.com',
        EMAIL_PORT=2525,
        EMAIL_USE_TLS=False,
        EMAIL_HOST_USER='settings-user',
        EMAIL_HOST_PASSWORD='env-secret',
        DEFAULT_FROM_EMAIL='settings@example.com',
    )
    @patch('microsys.models.SystemSettings.load')
    def test_env_email_mode_uses_ui_hints_with_env_secret(self, mock_load):
        mock_load.return_value = SimpleNamespace(email_config={
            'mode': 'env',
            'host': 'ui-smtp.example.com',
            'port': 587,
            'use_tls': True,
            'use_ssl': False,
            'username': 'ui-user',
            'default_from_email': 'ui@example.com',
        })
        email_config = get_microsys_email_config(include_secret=True)

        self.assertEqual(email_config['mode'], 'env')
        self.assertEqual(email_config['host'], 'ui-smtp.example.com')
        self.assertEqual(email_config['port'], 587)
        self.assertTrue(email_config['use_tls'])
        self.assertEqual(email_config['username'], 'ui-user')
        self.assertEqual(email_config['from_email'], 'ui@example.com')
        self.assertEqual(email_config['password'], 'env-secret')

    @override_settings(MICROSYS_CONFIG={'default_table_density': 'invalid-choice'})
    def test_setup_form_falls_back_to_balanced_table_density(self):
        form = SystemSettingsForm(
            instance=SystemSettings(default_table_density='invalid-choice', is_configured=False),
        )

        self.assertEqual(form.initial['default_table_density'], DEFAULT_TABLE_DENSITY)

    @override_settings(MICROSYS_CONFIG={'default_language': 'ar'})
    @patch('microsys.discovery.discover_sidebar_catalog')
    def test_setup_form_provides_sidebar_builder_with_language_catalog_and_english_fallback(self, mock_discover_sidebar_catalog):
        mock_discover_sidebar_catalog.side_effect = [
            [{'id': 'demo:list', 'url_name': 'demo:list', 'label': 'القائمة', 'group_label': 'التجريبي'}],
            [{'id': 'demo:list', 'url_name': 'demo:list', 'label': 'القائمة', 'group_label': 'التجريبي'}],
            [{'id': 'demo:list', 'url_name': 'demo:list', 'label': 'List', 'group_label': 'Demo'}],
        ]

        form = SystemSettingsForm(
            instance=SystemSettings(default_language='ar', is_configured=False),
        )

        self.assertEqual(
            mock_discover_sidebar_catalog.call_args_list,
            [
                call(lang_code='ar', include_system_items=False),
                call(lang_code='ar', include_system_items=True),
                call(lang_code='en', include_system_items=True),
            ],
        )
        self.assertIn('ms-sidebar-catalog-fallback-data', form.sidebar_builder_html)
        self.assertIn('Demo', form.sidebar_builder_html)

    @override_settings(MICROSYS_CONFIG={}, MEDIA_URL='')
    def test_uploaded_branding_urls_fall_back_to_absolute_media_paths(self):
        fake_settings = SimpleNamespace(
            system_names={},
            logo=SimpleNamespace(url='microsys/branding/logo.png'),
            favicon=SimpleNamespace(url='microsys/branding/favicon.ico'),
            home_url='',
            default_language='en',
            default_theme='light',
            languages={},
            translations_override={},
            sidebar_config={},
            is_configured=True,
        )

        with patch('microsys.models.SystemSettings.load', return_value=fake_settings):
            config = get_system_config()

        self.assertEqual(config['logo_url'], '/media/microsys/branding/logo.png')
        self.assertEqual(config['login_logo_url'], '/media/microsys/branding/logo.png')
        self.assertEqual(config['favicon_url'], '/media/microsys/branding/favicon.ico')

    @override_settings(MICROSYS_CONFIG={
        'default_theme': 'neon',
        'allowed_themes': ['missing-theme'],
        'sidebar': {
            'entries': [],
            'show_icons': False,
            'collapse_mode': 'icons',
        },
    })
    def test_system_config_normalizes_allowed_themes_and_sidebar_collapse(self):
        config = get_system_config()

        self.assertEqual(config['default_theme'], 'neon')
        self.assertEqual(config['allowed_themes'], list(get_theme_names()))
        self.assertFalse(config['sidebar']['show_icons'])
        self.assertEqual(config['sidebar']['collapse_mode'], 'hidden')
