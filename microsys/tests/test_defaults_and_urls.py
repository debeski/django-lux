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
from pathlib import Path
import json
import re

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

    def test_setup_identity_step_uses_microsys_file_widget_for_import_logo_and_favicon(self):
        form = SystemSettingsForm(
            instance=SystemSettings(is_configured=False),
            mode='setup',
        )

        html = Template('{% load crispy_forms_tags %}{% crispy form %}').render(Context({'form': form}))

        self.assertEqual(html.count('data-archive-file-widget'), 3)
        self.assertIn('data-settings-import-file="true"', html)
        self.assertIn('id="id_settings_import_file"', html)
        self.assertIn('id="id_logo"', html)
        self.assertIn('id="id_favicon"', html)

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
                    'transport': 'direct',
                    'secret_storage': 'encrypted_db',
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
        self.assertEqual(form.cleaned_data['email_config']['transport'], 'direct')
        self.assertEqual(form.cleaned_data['email_config']['secret_storage'], 'encrypted_db')
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

    def test_crispy_setup_render_uses_shared_toggle_cards_for_boolean_settings_except_email_switches(self):
        form = SystemSettingsForm(
            instance=SystemSettings(is_configured=False),
            mode='setup',
        )

        html = Template('{% load crispy_forms_tags %}{% crispy form %}').render(Context({'form': form}))

        self.assertIn("data-ms-settings-toggle-field='allow_user_language_override'", html)
        self.assertIn("data-ms-settings-toggle-field='public_root'", html)
        self.assertIn("data-ms-settings-toggle-field='sidebar_enabled'", html)
        self.assertIn("data-ms-settings-toggle-field='sidebar_enable_toolbar'", html)
        self.assertIn("data-ms-settings-toggle-field='allow_user_theme_override'", html)
        self.assertIn("data-ms-settings-toggle-field='titlebar_show_title'", html)
        self.assertIn("data-ms-email-toggle-field='email_config_use_tls'", html)
        self.assertIn("data-ms-email-toggle-field='email_config_use_ssl'", html)
        self.assertNotIn("data-ms-settings-toggle-field='email_config_use_tls'", html)
        self.assertNotIn("data-ms-settings-toggle-field='email_config_use_ssl'", html)
        self.assertIn('data-ms-settings-toggle-field=\'allow_user_language_override\'', html)
        self.assertIn('class="row mb-3"', html)
        self.assertIn('class="row g-3 mb-3"', html)
        self.assertIn('data-ms-settings-toggle-field=\'titlebar_show_home_button\'', html)

    def test_setup_form_hides_public_registration_dependents_until_enabled(self):
        form = SystemSettingsForm(
            instance=SystemSettings(is_configured=False, public_registration_enabled=False),
            mode='setup',
        )

        html = Template('{% load crispy_forms_tags %}{% crispy form %}').render(Context({'form': form}))

        self.assertIn('ms-public-registration-dependent d-none', html)
        self.assertIn('data-public-registration-dependent="true"', html)
        self.assertIn('aria-hidden="true"', html)
        self.assertIn('data-ms-settings-toggle-field=\'public_registration_enabled\'', html)
        self.assertIn('class="col-lg-12" > <div class=\'ms-settings-toggle-field', html)

    def test_setup_form_shows_public_registration_dependents_when_enabled(self):
        form = SystemSettingsForm(
            instance=SystemSettings(is_configured=False, public_registration_enabled=True),
            mode='setup',
        )

        html = Template('{% load crispy_forms_tags %}{% crispy form %}').render(Context({'form': form}))
        dependent_class_start = html.index('ms-public-registration-dependent')
        dependent_class_end = html.index('>', dependent_class_start)

        self.assertNotIn('d-none', html[dependent_class_start:dependent_class_end])
        self.assertIn('aria-hidden="false"', html[dependent_class_start:dependent_class_end])
        self.assertIn('class="col-lg-6 ms-public-registration-dependent"', html)

    @override_settings(MICROSYS_CONFIG={})
    def test_setup_wizard_actions_align_to_direction_end_in_ltr(self):
        form = SystemSettingsForm(
            instance=SystemSettings(is_configured=False),
            mode='setup',
        )

        html = Template('{% load crispy_forms_tags %}{% crispy form %}').render(Context({'form': form}))

        self.assertIn('ms-setup-wizard-actions', html)
        self.assertIn("dir='ltr'", html)
        self.assertIn('justify-content-end', html)
        self.assertNotIn('justify-content-between align-items-center gap-2 mt-4', html)

    @override_settings(MICROSYS_CONFIG={'default_language': 'ar'})
    def test_setup_wizard_actions_align_to_direction_end_in_rtl(self):
        form = SystemSettingsForm(
            instance=SystemSettings(is_configured=False, default_language='ar'),
            mode='setup',
        )

        html = Template('{% load crispy_forms_tags %}{% crispy form %}').render(Context({'form': form}))

        self.assertIn('ms-setup-wizard-actions', html)
        self.assertIn("dir='rtl'", html)
        self.assertIn('justify-content-end', html)
        self.assertNotIn('justify-content-between align-items-center gap-2 mt-4', html)

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
                'email_config_transport': 'direct',
                'email_config_secret_storage': 'encrypted_db',
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
        self.assertEqual(email_config['transport'], 'direct')
        self.assertEqual(email_config['secret_storage'], 'encrypted_db')
        self.assertTrue(email_config['encrypted_password'])
        self.assertNotEqual(email_config['encrypted_password'], 'app-secret-pass')
        self.assertEqual(decrypt_email_secret(email_config['encrypted_password']), 'app-secret-pass')

    def test_setup_form_saves_direct_smtp_with_encrypted_db_secret_axes(self):
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
                'email_config_transport': 'direct',
                'email_config_secret_storage': 'encrypted_db',
                'email_config_host': 'smtp.example.com',
                'email_config_port': '465',
                'email_config_use_ssl': 'on',
                'email_config_username': 'mailer@example.com',
                'email_config_password': 'direct-secret',
                'email_config_default_from_email': 'security@example.com',
                'sidebar_config': '{"entries":[]}',
            },
            instance=SystemSettings(is_configured=False),
        )

        self.assertTrue(form.is_valid(), form.errors)
        email_config = form.cleaned_data['email_config']
        self.assertEqual(email_config['transport'], 'direct')
        self.assertEqual(email_config['secret_storage'], 'encrypted_db')
        self.assertTrue(email_config['use_ssl'])
        self.assertFalse(email_config['use_tls'])
        self.assertEqual(decrypt_email_secret(email_config['encrypted_password']), 'direct-secret')

    def test_setup_form_saves_relay_upstream_email_secret_without_plaintext(self):
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
                'email_config_transport': 'relay',
                'email_config_secret_storage': 'encrypted_db',
                'email_config_host': 'smtp.gmail.com',
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
        self.assertEqual(email_config['transport'], 'relay')
        self.assertEqual(email_config['secret_storage'], 'encrypted_db')
        self.assertEqual(email_config['host'], 'smtp.gmail.com')
        self.assertEqual(email_config['port'], 587)
        self.assertTrue(email_config['use_tls'])
        self.assertFalse(email_config['use_ssl'])
        self.assertEqual(email_config['username'], 'mailer@example.com')
        self.assertTrue(email_config['encrypted_password'])
        self.assertNotEqual(email_config['encrypted_password'], 'app-secret-pass')
        self.assertEqual(decrypt_email_secret(email_config['encrypted_password']), 'app-secret-pass')
        self.assertTrue(email_config['password_configured'])

    def test_setup_form_hides_email_password_field_for_env_secret_storage(self):
        form = SystemSettingsForm(
            instance=SystemSettings(is_configured=False, email_config={
                'transport': 'relay',
                'secret_storage': 'env',
                'host': 'smtp.example.com',
                'port': 587,
                'default_from_email': 'security@example.com',
            }),
            mode='setup',
        )

        html = Template('{% load crispy_forms_tags %}{% crispy form %}').render(Context({'form': form}))

        self.assertIn('ms-email-config-password-field d-none', html)

    def test_setup_form_shows_email_password_field_for_encrypted_db_secret_storage(self):
        form = SystemSettingsForm(
            instance=SystemSettings(is_configured=False, email_config={
                'transport': 'relay',
                'secret_storage': 'encrypted_db',
                'host': 'smtp.example.com',
                'port': 587,
                'default_from_email': 'security@example.com',
            }),
            mode='setup',
        )

        html = Template('{% load crispy_forms_tags %}{% crispy form %}').render(Context({'form': form}))
        password_class_start = html.index('ms-email-config-password-field')
        password_class_end = html.index('>', password_class_start)

        self.assertNotIn('d-none', html[password_class_start:password_class_end])

    def test_system_setup_js_toggles_email_password_and_previews_default_language(self):
        script = Path(__file__).resolve().parents[1] / 'static' / 'microsys' / 'main' / 'js' / 'system_setup.js'
        contents = script.read_text(encoding='utf-8')

        self.assertIn('ms-email-config-password-field', contents)
        self.assertIn("secretStorageInput.value === 'encrypted_db'", contents)
        self.assertIn('previewSetupDefaultLanguage', contents)
        self.assertIn('window.setLanguage(normalizedLanguage, { previewOnly: true })', contents)
        self.assertIn("input.matches('[data-language-default]')", contents)
        self.assertIn('#id_sidebar_enable_toolbar, #id_sidebar_enabled', contents)
        self.assertIn('data-public-registration-dependent', contents)
        self.assertIn("setNamedFieldDisabled(form, 'registration_activation_mode', !enabled)", contents)
        self.assertIn("setNamedFieldDisabled(form, 'registration_throttle_enabled', !enabled)", contents)

    def test_wizard_helper_reveals_server_hidden_steps(self):
        script = Path(__file__).resolve().parents[1] / 'static' / 'microsys' / 'helpers' / 'wizard' / 'js' / 'main.js'
        contents = script.read_text(encoding='utf-8')

        self.assertIn("step.classList.toggle('d-none', !isActive);", contents)
        self.assertIn("step.style.display = isActive ? '' : 'none';", contents)
        self.assertIn("step.setAttribute('aria-hidden', isActive ? 'false' : 'true');", contents)

    def test_user_hub_css_clamps_mobile_dropdown_to_viewport(self):
        stylesheet = Path(__file__).resolve().parents[1] / 'static' / 'microsys' / 'users' / 'css' / 'user_hub.css'
        contents = stylesheet.read_text(encoding='utf-8')

        self.assertIn('width: min(var(--ms-dropdown-width), calc(100vw - (var(--ms-dropdown-edge-gap) * 2)))', contents)
        self.assertIn('@media (max-width: 575.98px)', contents)
        self.assertIn('position: fixed', contents)
        self.assertIn('inset-inline: var(--ms-dropdown-edge-gap)', contents)
        self.assertIn('overflow-y: auto', contents)
        self.assertIn('flex-wrap: wrap;', contents)
        self.assertIn('justify-content: center;', contents)
        self.assertIn('width: auto;', contents)

    def test_selector_css_adds_vertical_padding_for_toggle_card_grids(self):
        stylesheet = Path(__file__).resolve().parents[1] / 'static' / 'microsys' / 'main' / 'css' / 'selectors.css'
        contents = stylesheet.read_text(encoding='utf-8')

        self.assertIn('.ms-choice-selector--toggle .ms-choice-selector__options {', contents)
        self.assertIn('padding-block: 0.8rem;', contents)
        self.assertIn('align-self: stretch;', contents)

    def test_system_setup_css_makes_shared_toggle_cards_reflow_inside_narrow_columns(self):
        stylesheet = Path(__file__).resolve().parents[1] / 'static' / 'microsys' / 'main' / 'css' / 'system_setup.css'
        contents = stylesheet.read_text(encoding='utf-8')

        self.assertIn('.ms-settings-toggle-field {', contents)
        self.assertIn('container-type: inline-size;', contents)
        self.assertIn('.ms-settings-toggle-field__content {', contents)
        self.assertIn('.ms-settings-toggle-field__control {', contents)
        self.assertIn('.ms-settings-toggle-field__control.form-switch {', contents)
        self.assertIn('.ms-settings-toggle-field__input.form-check-input {', contents)
        self.assertIn('padding-inline-start: 0;', contents)
        self.assertIn('margin: 0;', contents)
        self.assertIn('float: none;', contents)
        self.assertIn('position: static;', contents)
        self.assertIn('overflow-wrap: break-word;', contents)
        self.assertIn('word-break: normal;', contents)
        self.assertNotIn('overflow-wrap: anywhere;', contents)
        self.assertIn('@container (max-width: 14rem)', contents)
        self.assertIn('flex-direction: column;', contents)
        self.assertIn('justify-content: flex-end;', contents)

    def test_shared_toggle_helper_uses_neutral_switch_wrapper(self):
        form = SystemSettingsForm(
            instance=SystemSettings(is_configured=False),
            mode='setup',
        )

        html = Template('{% load crispy_forms_tags %}{% crispy form %}').render(Context({'form': form}))

        self.assertIn("ms-settings-toggle-field__control form-switch", html)
        self.assertIn("form-check-input ms-settings-toggle-field__input", html)
        self.assertNotIn("ms-settings-toggle-field__control form-check form-switch", html)

    def test_setup_email_tls_ssl_use_dedicated_email_toggle_markup(self):
        form = SystemSettingsForm(
            instance=SystemSettings(is_configured=False),
            mode='setup',
        )

        html = Template('{% load crispy_forms_tags %}{% crispy form %}').render(Context({'form': form}))

        self.assertIn("data-ms-email-toggle-field='email_config_use_tls'", html)
        self.assertIn("data-ms-email-toggle-field='email_config_use_ssl'", html)
        self.assertIn('ms-email-toggle-field__input', html)

    def test_system_setup_css_defines_dedicated_email_toggle_layout(self):
        stylesheet = Path(__file__).resolve().parents[1] / 'static' / 'microsys' / 'main' / 'css' / 'system_setup.css'
        contents = stylesheet.read_text(encoding='utf-8')

        self.assertIn('.ms-email-toggle-field {', contents)
        self.assertIn('.ms-email-toggle-field__row {', contents)
        self.assertIn('.ms-email-toggle-field__label {', contents)
        self.assertIn('.ms-email-toggle-field__input.form-check-input {', contents)

    def test_options_template_uses_external_assets_and_draggable_cards(self):
        template_path = Path(__file__).resolve().parents[1] / 'templates' / 'microsys' / 'includes' / 'options.html'
        contents = template_path.read_text(encoding='utf-8')

        self.assertIn("microsys/main/css/options.css", contents)
        self.assertIn("microsys/main/js/options.js", contents)
        self.assertIn('id="msOptionsGrid"', contents)
        self.assertIn('data-options-card="system-info"', contents)
        self.assertIn('data-options-card="autofill"', contents)
        self.assertIn('data-options-card="reset-defaults"', contents)
        self.assertIn('data-options-card-handle', contents)
        self.assertIn('bi-arrow-left-right', contents)
        self.assertNotIn('bi-grip-vertical', contents)
        self.assertIn('id="autofillToggle"', contents)
        self.assertIn('id="btnResetInit"', contents)
        self.assertIn('id="resetActions"', contents)
        self.assertNotIn('<style nonce=', contents)
        self.assertNotIn('<script nonce=', contents)

    def test_options_assets_define_shared_card_system_and_reorder_logic(self):
        css_path = Path(__file__).resolve().parents[1] / 'static' / 'microsys' / 'main' / 'css' / 'options.css'
        js_path = Path(__file__).resolve().parents[1] / 'static' / 'microsys' / 'main' / 'js' / 'options.js'

        css_contents = css_path.read_text(encoding='utf-8')
        js_contents = js_path.read_text(encoding='utf-8')

        self.assertIn('.ms-options-panel {', css_contents)
        self.assertIn('.ms-options-card {', css_contents)
        self.assertIn('.ms-options-card-handle {', css_contents)
        self.assertIn('.ms-options-card--wide {', css_contents)
        self.assertIn('--ms-options-grid-gap: 1.35rem;', css_contents)
        self.assertIn('position: relative;', css_contents)
        self.assertIn('0 16px 30px -28px rgba(15, 23, 42, 0.28);', css_contents)
        self.assertIn('inset-block: 1rem;', css_contents)
        self.assertIn('width: 3px;', css_contents)
        self.assertIn('.ms-options-card.is-drag-over-before::after,', css_contents)
        self.assertIn('.ms-options-card.is-drag-over-after::after {', css_contents)
        self.assertIn('inset-inline-start: calc((var(--ms-options-grid-gap) / -2) - 1.5px);', css_contents)
        self.assertIn('inset-inline-end: calc((var(--ms-options-grid-gap) / -2) - 1.5px);', css_contents)
        self.assertIn('pointer-events: none;', css_contents)
        self.assertIn('.ms-options-system-info-table .table {', css_contents)
        self.assertIn('--bs-table-bg: transparent;', css_contents)
        self.assertIn('.ms-options-system-info-table .progress {', css_contents)
        self.assertIn('OPTIONS_ORDER_STORAGE_KEY', js_contents)
        self.assertIn('data-options-card-handle', js_contents)
        self.assertIn('persistCardOrder(grid, storageKey)', js_contents)
        self.assertIn('function shouldInsertBefore(targetCard, event)', js_contents)
        self.assertIn("const direction = window.getComputedStyle(targetCard).direction || document.documentElement.dir || 'ltr';", js_contents)
        self.assertIn('return event.clientX < midpoint;', js_contents)

    def test_setup_form_render_does_not_emit_inline_style_attributes(self):
        form = SystemSettingsForm(
            instance=SystemSettings(is_configured=False),
            mode='setup',
        )

        html = Template('{% load crispy_forms_tags %}{% crispy form %}').render(Context({'form': form}))

        self.assertNotIn(' style=', html)

    def test_templates_do_not_embed_inline_style_blocks_or_executable_inline_scripts(self):
        templates_root = Path(__file__).resolve().parents[1] / 'templates'
        inline_script_pattern = re.compile(
            r'<script\b(?![^>]*\bsrc=)(?![^>]*\btype=(["\'])application/json\1)[^>]*>',
            re.IGNORECASE,
        )
        violations = []

        for path in sorted(templates_root.rglob('*.html')):
            contents = path.read_text(encoding='utf-8')
            if re.search(r'<style\b', contents, re.IGNORECASE):
                violations.append(f'{path.relative_to(templates_root)}:style-block')
            if inline_script_pattern.search(contents):
                violations.append(f'{path.relative_to(templates_root)}:inline-script')

        self.assertEqual(violations, [])

    def test_template_html_emitters_do_not_hardcode_inline_css_or_js(self):
        repo_root = Path(__file__).resolve().parents[2]
        emitter_paths = [
            repo_root / 'microsys' / 'forms.py',
            repo_root / 'microsys' / 'widgets.py',
        ]
        inline_script_pattern = re.compile(
            r'<script\b(?![^>]*\bsrc=)(?![^>]*\btype=(["\'])application/json\1)[^>]*>',
            re.IGNORECASE,
        )

        for path in emitter_paths:
            contents = path.read_text(encoding='utf-8')
            self.assertNotIn('style=', contents, str(path))
            self.assertNotIn('<style', contents, str(path))
            self.assertIsNone(inline_script_pattern.search(contents), str(path))

    def test_templates_do_not_use_inline_style_attributes(self):
        templates_root = Path(__file__).resolve().parents[1] / 'templates'
        violations = []

        for path in sorted(templates_root.rglob('*.html')):
            for lineno, line in enumerate(path.read_text(encoding='utf-8').splitlines(), start=1):
                if 'style=' in line:
                    violations.append(f'{path.relative_to(templates_root)}:{lineno}')

        self.assertEqual(violations, [])

    def test_system_settings_export_redacts_email_secret_and_preserves_sidebar_enabled(self):
        settings_obj = SystemSettings(
            system_names={'en': 'Export System'},
            default_language='en',
            default_theme='light',
            allowed_themes=['light'],
            email_config={
                'transport': 'direct',
                'secret_storage': 'encrypted_db',
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
        self.assertEqual(email_config['transport'], 'direct')
        self.assertEqual(email_config['secret_storage'], 'encrypted_db')
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
            'transport': 'direct',
            'secret_storage': 'env',
            'host': 'ui-smtp.example.com',
            'port': 587,
            'use_tls': True,
            'use_ssl': False,
            'username': 'ui-user',
            'default_from_email': 'ui@example.com',
        })
        email_config = get_microsys_email_config(include_secret=True)

        self.assertEqual(email_config['transport'], 'direct')
        self.assertEqual(email_config['secret_storage'], 'env')
        self.assertEqual(email_config['host'], 'ui-smtp.example.com')
        self.assertEqual(email_config['port'], 587)
        self.assertTrue(email_config['use_tls'])
        self.assertEqual(email_config['username'], 'ui-user')
        self.assertEqual(email_config['from_email'], 'ui@example.com')
        self.assertEqual(email_config['password'], 'env-secret')

    @patch('microsys.models.SystemSettings.load')
    def test_relay_email_mode_sends_to_internal_relay_without_auth_or_tls(self, mock_load):
        mock_load.return_value = SimpleNamespace(email_config={
            'transport': 'relay',
            'secret_storage': 'encrypted_db',
            'host': 'smtp.gmail.com',
            'port': 587,
            'use_tls': True,
            'use_ssl': False,
            'username': 'mailer@example.com',
            'default_from_email': 'security@example.com',
            'encrypted_password': 'ciphertext-value',
            'password_configured': True,
        })

        email_config = get_microsys_email_config(include_secret=True)

        self.assertEqual(email_config['transport'], 'relay')
        self.assertEqual(email_config['secret_storage'], 'encrypted_db')
        self.assertEqual(email_config['host'], 'smtp-relay')
        self.assertEqual(email_config['port'], 1025)
        self.assertFalse(email_config['use_tls'])
        self.assertFalse(email_config['use_ssl'])
        self.assertEqual(email_config['username'], '')
        self.assertEqual(email_config['password'], '')
        self.assertFalse(email_config['password_configured'])
        self.assertEqual(email_config['from_email'], 'security@example.com')

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
