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
        DEFAULT_AUTO_FIELD='django.db.models.BigAutoField',
        USE_TZ=True,
        CRISPY_ALLOWED_TEMPLATE_PACKS='bootstrap5',
        CRISPY_TEMPLATE_PACK='bootstrap5',
    )

    import django

    django.setup()

from django.contrib.auth.models import AnonymousUser
from django.test import Client, RequestFactory, SimpleTestCase, override_settings
from django.template import Context, Template
from django.urls import clear_url_caches
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from types import SimpleNamespace
from unittest.mock import call, patch
from pathlib import Path
from io import StringIO
import json
import re
import tempfile

from microsys.constants import DEFAULT_HOME_URL, DEFAULT_TABLE_DENSITY, LEGACY_HOME_URL
from microsys.context_processors import microsys_context
from microsys.forms import SystemSettingsForm
from microsys.models import SystemSettings
from microsys.themes import get_theme_names
from microsys.utils import (
    decrypt_email_secret,
    export_system_settings_payload,
    get_microsys_email_config,
    get_system_config,
    normalize_navbar_config,
    normalize_system_settings_import_payload,
    normalize_titlebar_config,
    seed_navbar_config_from_sidebar,
)
from microsys.navbar import build_navbar_hierarchy_crumbs


class MicrosysDefaultRouteTests(SimpleTestCase):
    databases = {'default'}

    def setUp(self):
        cache.clear()
        SystemSettings._default_manager.all().delete()
        super().setUp()

    @override_settings(MICROSYS_CONFIG={})
    def test_system_config_defaults_home_url_to_profile(self):
        self.assertEqual(get_system_config().get('home_url'), DEFAULT_HOME_URL)

    def test_microsys_settings_status_does_not_create_singleton(self):
        out = StringIO()

        call_command('microsys_settings', 'status', stdout=out)

        self.assertIn('SystemSettings singleton: missing', out.getvalue())
        self.assertFalse(SystemSettings._default_manager.filter(pk=1).exists())

    def test_microsys_settings_unconfigure_preserves_settings(self):
        instance = SystemSettings.load()
        instance.is_configured = True
        instance.home_url = '/sys/profile/'
        instance.sidebar_config = {'enabled': False, 'entries': []}
        instance.save()

        call_command('microsys_settings', 'unconfigure', stdout=StringIO())

        instance.refresh_from_db()
        self.assertFalse(instance.is_configured)
        self.assertEqual(instance.home_url, '/sys/profile/')
        self.assertFalse(instance.sidebar_config['enabled'])

    def test_microsys_settings_delete_requires_yes_and_removes_singleton(self):
        SystemSettings.load()

        with self.assertRaises(CommandError):
            call_command('microsys_settings', 'delete', stdout=StringIO())

        self.assertTrue(SystemSettings._default_manager.filter(pk=1).exists())
        call_command('microsys_settings', 'delete', '--yes', stdout=StringIO())
        self.assertFalse(SystemSettings._default_manager.filter(pk=1).exists())

    def test_microsys_settings_reset_recreates_unconfigured_defaults(self):
        instance = SystemSettings.load()
        instance.is_configured = True
        instance.home_url = '/custom/'
        instance.save()

        call_command('microsys_settings', 'reset', '--yes', stdout=StringIO())

        instance = SystemSettings._default_manager.get(pk=1)
        self.assertFalse(instance.is_configured)
        self.assertEqual(instance.home_url, DEFAULT_HOME_URL)

    def test_microsys_settings_export_import_roundtrip(self):
        instance = SystemSettings.load()
        instance.is_configured = True
        instance.system_names = {'en': 'Exported'}
        instance.home_url = '/sys/profile/'
        instance.allowed_fonts = ['cairo']
        instance.default_fonts = {'en': 'cairo'}
        instance.sidebar_config = {'enabled': False, 'entries': []}
        instance.navbar_config = {'enabled': True, 'default_mode': 'history', 'hierarchy': {'nodes': []}}
        instance.save()

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'config.json'
            call_command('microsys_settings', 'export', '--output', str(path), stdout=StringIO())
            call_command('microsys_settings', 'delete', '--yes', stdout=StringIO())
            call_command('microsys_settings', 'import', '--input', str(path), stdout=StringIO())

        instance = SystemSettings._default_manager.get(pk=1)
        self.assertTrue(instance.is_configured)
        self.assertEqual(instance.system_names['en'], 'Exported')
        self.assertEqual(instance.home_url, '/sys/profile/')
        self.assertEqual(instance.allowed_fonts, ['cairo'])
        self.assertEqual(instance.default_fonts, {'en': 'cairo'})
        self.assertFalse(instance.sidebar_config['enabled'])
        self.assertTrue(instance.navbar_config['enabled'])

    def test_navbar_config_normalizes_defaults_and_nested_manual_labels(self):
        normalized = normalize_navbar_config({
            'enabled': True,
            'default_mode': 'invalid',
            'allow_user_mode_override': False,
            'hierarchy': {
                'nodes': [{
                    'kind': 'manual',
                    'id': 'documents',
                    'labels': {'en': 'Documents', '': 'Ignored'},
                    'children': [{'kind': 'route', 'id': 'documents:list', 'url_name': 'documents:list'}],
                }],
            },
        })

        self.assertTrue(normalized['enabled'])
        self.assertEqual(normalized['default_mode'], 'hierarchy')
        self.assertFalse(normalized['allow_user_mode_override'])
        self.assertEqual(normalized['hierarchy']['nodes'][0]['labels'], {'en': 'Documents'})
        self.assertEqual(normalized['hierarchy']['nodes'][0]['children'][0]['url_name'], 'documents:list')

    def test_system_settings_import_accepts_runtime_config_aliases(self):
        imported = normalize_system_settings_import_payload({
            'translations': {'en': {'custom_key': 'Custom'}},
            'sidebar': {'enabled': False, 'entries': [{'kind': 'item', 'id': 'archive:index'}]},
            'navbar': {'enabled': True, 'default_mode': 'history', 'hierarchy': {'nodes': []}},
            'titlebar': {'show_title': False, 'logo_treatment': 'plate', 'logo_treatment_shape': 'pill'},
            'prevent_multiple_active_sessions': 'true',
        })

        self.assertEqual(imported['translations_override']['en']['custom_key'], 'Custom')
        self.assertFalse(imported['sidebar_config']['enabled'])
        self.assertEqual(imported['sidebar_config']['entries'][0]['id'], 'archive:index')
        self.assertTrue(imported['navbar_config']['enabled'])
        self.assertFalse(imported['titlebar_config']['show_title'])
        self.assertEqual(imported['titlebar_config']['logo_treatment'], 'plate')
        self.assertEqual(imported['titlebar_config']['logo_treatment_shape'], 'pill')
        self.assertTrue(imported['prevent_multiple_active_sessions'])

    def test_titlebar_logo_treatment_normalizes_defaults_and_invalid_values(self):
        defaults = normalize_titlebar_config({})
        invalid = normalize_titlebar_config({
            'logo_treatment': 'flash',
            'logo_treatment_shape': 'hexagon',
        })

        self.assertEqual(defaults['logo_treatment'], 'none')
        self.assertEqual(defaults['logo_treatment_shape'], 'soft')
        self.assertEqual(invalid['logo_treatment'], 'none')
        self.assertEqual(invalid['logo_treatment_shape'], 'soft')

    def test_navbar_seed_from_sidebar_only_when_enabled_and_empty(self):
        seeded = seed_navbar_config_from_sidebar(
            {'enabled': True, 'hierarchy': {'nodes': []}},
            {
                'enabled': True,
                'entries': [{
                    'kind': 'group',
                    'id': 'archive',
                    'label': 'Archive',
                    'items': [{
                        'kind': 'item',
                        'id': 'archive:decree_list',
                        'url_name': 'archive:decree_list',
                        'label': 'Decrees',
                    }],
                }],
            },
            lang_code='en',
        )

        archive = seeded['hierarchy']['nodes'][0]
        self.assertEqual(archive['kind'], 'manual')
        self.assertEqual(archive['labels'], {'en': 'Archive'})
        self.assertEqual(archive['children'][0]['kind'], 'route')
        self.assertEqual(archive['children'][0]['url_name'], 'archive:decree_list')

        preserved = seed_navbar_config_from_sidebar(
            {
                'enabled': True,
                'hierarchy': {'nodes': [{'kind': 'manual', 'id': 'kept', 'children': []}]},
            },
            {'entries': []},
        )
        self.assertEqual(preserved['hierarchy']['nodes'][0]['id'], 'kept')

    def test_navbar_hierarchy_runtime_crumbs_win_over_static_route_tree(self):
        request = RequestFactory().get('/documents/record/')
        request.resolver_match = SimpleNamespace(view_name='documents:list', url_name='list')
        config = {
            'enabled': True,
            'hierarchy': {
                'nodes': [{
                    'kind': 'manual',
                    'id': 'static',
                    'labels': {'en': 'Static'},
                    'children': [{'kind': 'route', 'id': 'documents:list', 'url_name': 'documents:list'}],
                }],
            },
        }

        with patch('microsys.navbar.discover_sidebar_catalog', return_value=[]):
            crumbs = build_navbar_hierarchy_crumbs(
                request,
                config,
                'en',
                {'navbar_root': 'Root', 'documents': 'Documents'},
                runtime_crumbs=[
                    {'label_key': 'documents', 'url': '/documents/'},
                    {'label': 'Record 7', 'url': '/documents/7/'},
                ],
            )

        self.assertEqual([crumb['label'] for crumb in crumbs], ['Root', 'Documents', 'Record 7'])
        self.assertTrue(crumbs[1]['clickable'])

    def test_navbar_hierarchy_resolves_manual_group_and_route_label_fallback(self):
        request = RequestFactory().get('/documents/')
        request.resolver_match = SimpleNamespace(view_name='documents:list', url_name='list')
        config = {
            'enabled': True,
            'hierarchy': {
                'nodes': [{
                    'kind': 'manual',
                    'id': 'library',
                    'labels': {'en': 'Library'},
                    'children': [{'kind': 'route', 'id': 'documents:list', 'url_name': 'documents:list'}],
                }],
            },
        }
        catalog = [{'url_name': 'documents:list', 'label': 'Documents', 'url': '/documents/'}]

        with patch('microsys.navbar.discover_sidebar_catalog', return_value=catalog):
            crumbs = build_navbar_hierarchy_crumbs(request, config, 'en', {'navbar_root': 'Root'})

        self.assertEqual([crumb['label'] for crumb in crumbs], ['Root', 'Library', 'Documents'])
        self.assertFalse(crumbs[1]['clickable'])
        self.assertTrue(crumbs[2]['clickable'])

    def test_navbar_hierarchy_keeps_manual_url_ancestor_clickable_for_current_route(self):
        request = RequestFactory().get('/archive/decrees/')
        request.resolver_match = SimpleNamespace(view_name='archive:decree_list', url_name='decree_list')
        config = {
            'enabled': True,
            'hierarchy': {
                'nodes': [{
                    'kind': 'manual',
                    'id': 'archive',
                    'labels': {'en': 'Archive'},
                    'url': '/archive/',
                    'children': [{'kind': 'route', 'id': 'decree_list', 'url_name': 'decree_list'}],
                }],
            },
        }
        catalog = [{'url_name': 'decree_list', 'label': 'Decrees', 'url': '/archive/decrees/'}]

        with patch('microsys.navbar.discover_sidebar_catalog', return_value=catalog):
            crumbs = build_navbar_hierarchy_crumbs(request, config, 'en', {'navbar_root': 'Root'})

        self.assertEqual([crumb['label'] for crumb in crumbs], ['Root', 'Archive', 'Decrees'])
        self.assertTrue(crumbs[1]['clickable'])
        self.assertEqual(crumbs[1]['url'], '/archive/')

    def test_navbar_hierarchy_keeps_root_level_manual_index_url_clickable(self):
        request = RequestFactory().get('/archive/decrees/')
        request.resolver_match = SimpleNamespace(view_name='archive:decree_list', url_name='decree_list')
        config = {
            'enabled': True,
            'hierarchy': {
                'nodes': [{
                    'kind': 'manual',
                    'id': 'archive-index',
                    'labels': {'en': 'Index'},
                    'url': '/archive/',
                    'children': [{'kind': 'route', 'id': 'decree_list', 'url_name': 'decree_list'}],
                }],
            },
        }
        catalog = [{'url_name': 'decree_list', 'label': 'Decrees', 'url': '/archive/decrees/'}]

        with patch('microsys.navbar.discover_sidebar_catalog', return_value=catalog):
            crumbs = build_navbar_hierarchy_crumbs(request, config, 'en', {'navbar_root': 'Root'})

        self.assertEqual([crumb['label'] for crumb in crumbs], ['Root', 'Index', 'Decrees'])
        self.assertTrue(crumbs[1]['clickable'])
        self.assertEqual(crumbs[1]['url'], '/archive/')

    def test_navbar_hierarchy_keeps_discovered_index_route_clickable_when_label_is_specific(self):
        request = RequestFactory().get('/archive/decrees/')
        request.resolver_match = SimpleNamespace(view_name='archive:decree_list', url_name='decree_list')
        config = {
            'enabled': True,
            'hierarchy': {
                'nodes': [{
                    'kind': 'route',
                    'id': 'archive:index',
                    'url_name': 'archive:index',
                    'labels': {'en': 'Archive'},
                    'children': [{
                        'kind': 'route',
                        'id': 'archive:decree_list',
                        'url_name': 'archive:decree_list',
                    }],
                }],
            },
        }
        catalog = [
            {'url_name': 'archive:index', 'label': 'Archive Index', 'url': '/archive/'},
            {'url_name': 'archive:decree_list', 'label': 'Decree List', 'url': '/archive/decrees/'},
        ]

        with patch('microsys.navbar.discover_sidebar_catalog', return_value=catalog):
            crumbs = build_navbar_hierarchy_crumbs(request, config, 'en', {'navbar_root': 'Root'})

        self.assertEqual([crumb['label'] for crumb in crumbs], ['Root', 'Archive', 'Decree List'])
        self.assertTrue(crumbs[1]['clickable'])
        self.assertEqual(crumbs[1]['url'], '/archive/')

    def test_navbar_hierarchy_does_not_match_app_index_node_for_project_root(self):
        request = RequestFactory().get('/')
        request.resolver_match = SimpleNamespace(view_name='index', url_name='index')
        config = {
            'enabled': True,
            'hierarchy': {
                'nodes': [{
                    'kind': 'route',
                    'id': 'archive:index',
                    'url_name': 'archive:index',
                    'labels': {'en': 'Archive'},
                    'children': [],
                }],
            },
        }
        catalog = [
            {'url_name': 'index', 'label': 'Home', 'url': '/'},
            {'url_name': 'archive:index', 'label': 'Archive', 'url': '/archive/'},
        ]

        with patch('microsys.navbar.discover_sidebar_catalog', return_value=catalog):
            crumbs = build_navbar_hierarchy_crumbs(request, config, 'en', {'navbar_root': 'Root'})

        self.assertEqual([crumb['label'] for crumb in crumbs], ['Root', 'Home'])
        self.assertFalse(crumbs[1]['clickable'])

    def test_navbar_hierarchy_wraps_microsys_routes_in_system_group(self):
        request = RequestFactory().get('/sys/options/')
        request.resolver_match = SimpleNamespace(view_name='microsys:options_view', url_name='options_view')
        catalog = [{
            'url_name': 'options_view',
            'label': 'Application Options',
            'url': '/sys/options/',
            'group_key': 'microsys',
        }]

        with patch('microsys.navbar.discover_sidebar_catalog', return_value=catalog):
            crumbs = build_navbar_hierarchy_crumbs(
                request,
                {'enabled': True, 'hierarchy': {'nodes': []}},
                'en',
                {'navbar_root': 'Root', 'navbar_system': 'System'},
            )

        self.assertEqual([crumb['label'] for crumb in crumbs], ['Root', 'System', 'Application Options'])
        self.assertFalse(crumbs[1]['clickable'])
        self.assertTrue(crumbs[2]['clickable'])

    def test_navbar_frontend_uses_language_aware_history_and_hides_system_routes_from_builder(self):
        navbar_js = Path('microsys/static/microsys/main/js/navbar.js').read_text(encoding='utf-8')
        setup_js = Path('microsys/static/microsys/main/js/system_setup.js').read_text(encoding='utf-8')

        self.assertIn("const HISTORY_KEY = 'microsys.navbar.history.v1';", navbar_js)
        self.assertIn('labels[language] = label;', navbar_js)
        self.assertIn('labelsByPath[normalizedPath(entry.path)]', navbar_js)
        self.assertIn('trail.replaceChildren(fragment);', navbar_js)
        self.assertIn('!entry.is_system', setup_js)
        self.assertNotIn('crumb.clickable && crumb.url && !isCurrent', navbar_js)

    def test_unconfigured_root_url_redirects_to_system_setup(self):
        response = Client().get('/')

        self.assertRedirects(
            response,
            '/sys/setup/',
            fetch_redirect_response=False,
        )

    @override_settings(MICROSYS_CONFIG={'is_configured': True, 'home_url': '/dashboard/', 'public_root': True})
    def test_configured_root_url_redirects_to_home_url(self):
        response = Client().get('/')

        self.assertRedirects(
            response,
            '/dashboard/',
            fetch_redirect_response=False,
        )

    @override_settings(MICROSYS_CONFIG={'is_configured': True, 'home_url': '/dashboard/', 'public_root': False})
    def test_configured_root_url_redirects_anonymous_to_login(self):
        response = Client().get('/')

        self.assertRedirects(
            response,
            '/accounts/login/',
            fetch_redirect_response=False,
        )

    @override_settings(ROOT_URLCONF='microsys.tests.urls_with_root_index')
    def test_unconfigured_existing_project_root_respects_dev_view(self):
        clear_url_caches()
        response = Client().get('/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'project index')

    @override_settings(ROOT_URLCONF='microsys.tests.urls_with_root_index', MICROSYS_CONFIG={'is_configured': True})
    def test_configured_existing_project_root_view_is_not_hijacked(self):
        clear_url_caches()
        response = Client().get('/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'project index')

    @override_settings(ROOT_URLCONF='microsys.tests.urls_with_prefix_mount', MICROSYS_CONFIG={'is_configured': True, 'home_url': '/dashboard/', 'public_root': True})
    def test_prefix_mount_still_redirects_unclaimed_root(self):
        clear_url_caches()
        response = Client().get('/')

        self.assertRedirects(
            response,
            '/dashboard/',
            fetch_redirect_response=False,
        )

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
        'public_root_split_enabled': True,
        'public_root_url': '/public-landing/',
        'titlebar': {
            'show_logo': False,
            'show_home_button': False,
            'hide_on_public_unauthenticated_index': True,
            'home_shape': 'square',
            'title_align': 'center',
            'title_size': 'lg',
            'height': 'roomy',
            'surface': 'glass',
            'logo_treatment': 'plate',
            'logo_treatment_shape': 'pill',
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
        self.assertTrue(form.initial['public_root_split_enabled'])
        self.assertEqual(form.initial['public_root_url'], '/public-landing/')
        self.assertTrue(form.initial['titlebar_hide_on_public_unauthenticated_index'])
        self.assertEqual(form.initial['titlebar_home_shape'], 'square')
        self.assertEqual(form.initial['titlebar_title_align'], 'center')
        self.assertEqual(form.initial['titlebar_title_size'], 'lg')
        self.assertEqual(form.initial['titlebar_height'], 'roomy')
        self.assertEqual(form.initial['titlebar_surface'], 'glass')
        self.assertEqual(form.initial['titlebar_logo_treatment'], 'plate')
        self.assertEqual(form.initial['titlebar_logo_treatment_shape'], 'pill')

    @override_settings(MICROSYS_CONFIG={
        'titlebar': {
            'show_title': False,
        },
    })
    def test_setup_form_surfaces_titlebar_toggle_widgets_and_step_three(self):
        request = RequestFactory().get('/sys/modals/microsys/systemsettings/1/?step=2')
        form = SystemSettingsForm(
            instance=SystemSettings(is_configured=False),
            request=request,
        )

        self.assertTrue(form.single_step_mode)
        self.assertEqual(form.single_step_index, 2)
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
        self.assertIn('<select', str(form['public_root_url_discovered']))
        self.assertNotIn('data-ms-selector-search', str(form['home_url_discovered']))

    def test_setup_theme_picker_keeps_allow_checkboxes_separate_from_default_selector(self):
        form = SystemSettingsForm(
            instance=SystemSettings(is_configured=False),
            mode='setup',
        )

        self.assertIn('data-setup-theme-choice="light"', form.theme_picker_html)
        self.assertIn('data-setup-theme-preview-url="/static/microsys/themes/css/light.css?v=20260523c"', form.theme_picker_html)
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
        self.assertIn('data-settings-import-finish', html)
        self.assertIn('Finish setup from imported config', html)
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
                'allowed_fonts': ['cairo'],
                'default_fonts': {'fr': 'cairo'},
                'allow_user_font_override': False,
                'translations_override': {'fr': {'app_microsys': 'Systeme'}},
                'home_url': '/imported/',
                'public_root': True,
                'public_root_split_enabled': True,
                'public_root_url': '/public-imported/',
                'default_table_density': 'dense',
                'sidebar_config': {'entries': [], 'density': 'dense', 'collapse_mode': 'hidden'},
                'titlebar_config': {
                    'show_title': False,
                    'hide_on_public_unauthenticated_index': True,
                    'title_align': 'center',
                    'logo_treatment': 'halo',
                    'logo_treatment_shape': 'square',
                },
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
        self.assertEqual(form.cleaned_data['allowed_fonts'], ['cairo'])
        self.assertEqual(form.cleaned_data['default_fonts'], {'fr': 'cairo'})
        self.assertFalse(form.cleaned_data['allow_user_font_override'])
        self.assertEqual(form.cleaned_data['home_url'], '/imported/')
        self.assertTrue(form.cleaned_data['public_root_split_enabled'])
        self.assertEqual(form.cleaned_data['public_root_url'], '/public-imported/')
        self.assertEqual(form.cleaned_data['sidebar_config']['density'], 'dense')
        self.assertFalse(form.cleaned_data['titlebar_config']['show_title'])
        self.assertTrue(form.cleaned_data['titlebar_config']['hide_on_public_unauthenticated_index'])
        self.assertEqual(form.cleaned_data['titlebar_config']['logo_treatment'], 'halo')
        self.assertEqual(form.cleaned_data['titlebar_config']['logo_treatment_shape'], 'square')

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
        self.assertTrue(form.cleaned_data['sidebar_enable_toolbar'])

    def test_setup_form_import_restores_login_config_and_registration_mode(self):
        payload = {
            'format': 'django-microsys.system-settings',
            'version': 1,
            'settings': {
                'system_names': {'en': 'Imported System', 'ar': 'نظام'},
                'default_language': 'ar',
                'default_theme': 'light',
                'allowed_themes': ['light'],
                'default_table_density': 'balanced',
                'languages': {
                    'en': {'name': 'English', 'dir': 'ltr', 'flag': 'EN'},
                    'ar': {'name': 'العربية', 'dir': 'rtl', 'flag': 'AR'},
                },
                'translations_override': {},
                'home_url': '/',
                'registration_activation_mode': 'verified_pending_approval',
                'login_config': {
                    'style': 'fullpage',
                    'show_logo': False,
                    'banner_color': '#123456',
                    'logo_treatment': 'plate',
                    'logo_treatment_shape': 'circle',
                    'hero_message': {'en': 'Welcome', 'ar': 'مرحبا'},
                },
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
        login_config = form.cleaned_data['login_config']
        self.assertEqual(login_config['style'], 'fullpage')
        self.assertFalse(login_config['show_logo'])
        self.assertEqual(login_config['banner_color'], '#123456')
        self.assertEqual(login_config['logo_treatment'], 'plate')
        self.assertEqual(login_config['hero_message'].get('en'), 'Welcome')
        self.assertEqual(form.cleaned_data['registration_activation_mode'], 'verified_pending_approval')
        self.assertEqual(form.cleaned_data['default_language'], 'ar')

    def test_setup_import_normalizer_accepts_legacy_login_alias(self):
        imported = normalize_system_settings_import_payload({
            'system_names': {'en': 'Legacy System'},
            'default_language': 'ar',
            'registration_activation_mode': 'verified_pending_approval',
            'login': {
                'style': 'minimal',
                'show_logo': False,
                'banner_color': '#223344',
                'logo_treatment': 'halo',
                'logo_treatment_shape': 'pill',
                'hero_message': {'en': 'Legacy welcome'},
            },
        })

        self.assertEqual(imported['default_language'], 'ar')
        self.assertEqual(imported['registration_activation_mode'], 'verified_pending_approval')
        self.assertEqual(imported['login_config']['style'], 'minimal')
        self.assertFalse(imported['login_config']['show_logo'])
        self.assertEqual(imported['login_config']['banner_color'], '#223344')
        self.assertEqual(imported['login_config']['logo_treatment'], 'halo')
        self.assertEqual(imported['login_config']['logo_treatment_shape'], 'pill')

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', DEBUG=True)
    def test_setup_form_processed_import_keeps_client_applied_login_language_and_registration(self):
        form = SystemSettingsForm(
            data={
                'settings_import_processed': 'true',
                'system_names': json.dumps({'en': 'Imported System', 'ar': 'نظام'}),
                'home_url': '/',
                'default_language': 'ar',
                'default_theme': 'light',
                'allowed_themes': ['light'],
                'default_table_density': 'balanced',
                'languages': json.dumps({
                    'en': {'name': 'English', 'dir': 'ltr', 'flag': 'EN'},
                    'ar': {'name': 'العربية', 'dir': 'rtl', 'flag': 'AR'},
                }),
                'translations_override': '{}',
                'public_registration_enabled': 'on',
                'registration_activation_mode': 'verified_pending_approval',
                'registration_throttle_enabled': 'on',
                'email_config_transport': 'direct',
                'email_config_secret_storage': 'env',
                'email_config_host': '',
                'email_config_port': '587',
                'email_config_use_tls': 'on',
                'email_config_username': '',
                'email_config_default_from_email': '',
                'sidebar_config': '{"entries":[]}',
                'login_style': 'fullpage',
                'login_banner_color': '#123456',
                'login_logo_treatment': 'plate',
                'login_logo_treatment_shape': 'pill',
                'login_hero_message_en': 'Welcome',
                'login_hero_message_ar': 'مرحبا',
            },
            instance=SystemSettings(is_configured=False),
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['default_language'], 'ar')
        self.assertTrue(form.cleaned_data['public_registration_enabled'])
        self.assertEqual(form.cleaned_data['registration_activation_mode'], 'verified_pending_approval')
        login_config = form.cleaned_data['login_config']
        self.assertEqual(login_config['style'], 'fullpage')
        self.assertEqual(login_config['banner_color'], '#123456')
        self.assertEqual(login_config['logo_treatment'], 'plate')
        self.assertEqual(login_config['logo_treatment_shape'], 'pill')
        self.assertEqual(login_config['hero_message']['ar'], 'مرحبا')

    def test_setup_form_processed_import_requires_selected_encrypted_db_smtp_password(self):
        form = SystemSettingsForm(
            data={
                'settings_import_processed': 'true',
                'system_names': '{"en": "Imported System"}',
                'home_url': '/',
                'default_language': 'en',
                'default_theme': 'light',
                'allowed_themes': ['light'],
                'default_table_density': 'balanced',
                'languages': '{"en": {"name": "English", "dir": "ltr", "flag": "EN"}}',
                'translations_override': '{}',
                'public_registration_enabled': 'on',
                'registration_activation_mode': 'verified_pending_approval',
                'registration_throttle_enabled': 'on',
                'email_config_transport': 'direct',
                'email_config_secret_storage': 'encrypted_db',
                'email_config_host': 'smtp.example.com',
                'email_config_port': '587',
                'email_config_use_tls': 'on',
                'email_config_username': 'mailer@example.com',
                'email_config_default_from_email': 'security@example.com',
                'email_config': json.dumps({
                    'transport': 'direct',
                    'secret_storage': 'encrypted_db',
                    'host': 'smtp.example.com',
                    'port': 587,
                    'use_tls': True,
                    'username': 'mailer@example.com',
                    'default_from_email': 'security@example.com',
                }),
                'sidebar_config': '{"entries":[]}',
            },
            instance=SystemSettings(is_configured=False),
        )

        self.assertFalse(form.is_valid())
        self.assertIn('email_config', form.errors)
        self.assertEqual(form.cleaned_data['default_language'], 'en')
        self.assertEqual(form.cleaned_data['registration_activation_mode'], 'verified_pending_approval')

    def test_setup_form_keeps_sidebar_child_settings_when_sidebar_is_disabled(self):
        form = SystemSettingsForm(
            data={
                'system_names': '{"en": "Demo"}',
                'home_url': '/',
                'default_language': 'en',
                'default_theme': 'light',
                'allowed_themes': ['light'],
                'default_table_density': 'balanced',
                'languages': '{"en": {"name": "English", "dir": "ltr", "flag": "EN"}}',
                'translations_override': '{}',
                'sidebar_config': json.dumps({
                    'enabled': False,
                    'home_url_name': None,
                    'entries': [],
                    'enable_reorder': True,
                    'show_toolbar': True,
                    'show_icons': True,
                    'density': 'roomy',
                    'allow_user_density': True,
                    'collapse_mode': 'icons',
                }),
            },
            instance=SystemSettings(is_configured=False),
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(form.cleaned_data['sidebar_config']['enabled'])
        self.assertTrue(form.cleaned_data['sidebar_config']['enable_reorder'])
        self.assertTrue(form.cleaned_data['sidebar_config']['show_toolbar'])
        self.assertTrue(form.cleaned_data['sidebar_config']['show_icons'])
        self.assertEqual(form.cleaned_data['sidebar_config']['density'], 'roomy')
        self.assertTrue(form.cleaned_data['sidebar_config']['allow_user_density'])
        self.assertEqual(form.cleaned_data['sidebar_config']['collapse_mode'], 'icons')
        self.assertTrue(form.cleaned_data['sidebar_enable_reorder'])
        self.assertTrue(form.cleaned_data['sidebar_enable_toolbar'])
        self.assertTrue(form.cleaned_data['sidebar_show_icons'])
        self.assertTrue(form.cleaned_data['sidebar_allow_user_density'])
        self.assertEqual(form.cleaned_data['sidebar_collapse_mode'], 'icons')

    def test_setup_form_saves_navbar_config_and_manual_hierarchy_nodes(self):
        form = SystemSettingsForm(
            data={
                'system_names': '{"en": "Demo"}',
                'home_url': '/',
                'default_language': 'en',
                'default_theme': 'light',
                'allowed_themes': ['light'],
                'default_table_density': 'balanced',
                'languages': '{"en": {"name": "English", "dir": "ltr", "flag": "EN"}}',
                'translations_override': '{}',
                'sidebar_config': '{"entries":[]}',
                'navbar_enabled': 'on',
                'navbar_default_mode': 'history',
                'navbar_allow_user_mode_override': 'on',
                'navbar_config': json.dumps({
                    'enabled': False,
                    'default_mode': 'hierarchy',
                    'allow_user_mode_override': False,
                    'hierarchy': {
                        'nodes': [{
                            'kind': 'manual',
                            'id': 'areas',
                            'labels': {'en': 'Areas'},
                            'children': [],
                        }],
                    },
                }),
            },
            instance=SystemSettings(is_configured=False),
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.cleaned_data['navbar_config']['enabled'])
        self.assertEqual(form.cleaned_data['navbar_config']['default_mode'], 'history')
        self.assertTrue(form.cleaned_data['navbar_config']['allow_user_mode_override'])
        self.assertEqual(form.cleaned_data['navbar_config']['hierarchy']['nodes'][0]['labels']['en'], 'Areas')

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
        self.assertIn('id="id_titlebar_logo_treatment"', html)
        self.assertIn('id="id_titlebar_logo_treatment_shape"', html)
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
        self.assertIn("data-ms-settings-toggle-field='public_root_split_enabled'", html)
        self.assertIn("data-ms-settings-toggle-field='titlebar_hide_on_public_unauthenticated_index'", html)
        self.assertIn("data-ms-email-toggle-field='email_config_use_tls'", html)
        self.assertIn("data-ms-email-toggle-field='email_config_use_ssl'", html)
        self.assertNotIn("data-ms-settings-toggle-field='email_config_use_tls'", html)
        self.assertNotIn("data-ms-settings-toggle-field='email_config_use_ssl'", html)
        self.assertIn('data-ms-settings-toggle-field=\'allow_user_language_override\'', html)
        self.assertIn('class="row mb-3"', html)
        self.assertIn('class="row g-3 mb-3"', html)
        self.assertIn('data-ms-settings-toggle-field=\'titlebar_show_home_button\'', html)
        self.assertIn('data-ms-settings-toggle-field=\'titlebar_hide_on_public_unauthenticated_index\'', html)
        self.assertIn('data-public-root-dependent="true"', html)
        self.assertIn('data-public-root-split-dependent="true"', html)

    def test_setup_form_hides_public_root_split_dependents_until_enabled(self):
        form = SystemSettingsForm(
            instance=SystemSettings(
                is_configured=False,
                public_root=False,
                public_root_split_enabled=False,
            ),
            mode='setup',
        )

        html = Template('{% load crispy_forms_tags %}{% crispy form %}').render(Context({'form': form}))

        self.assertIn('ms-public-root-dependent', html)
        self.assertIn('ms-public-root-split-dependent', html)
        self.assertIn('d-none', html)
        self.assertIn('data-public-root-dependent="true"', html)
        self.assertIn('data-public-root-split-dependent="true"', html)

    @override_settings(MICROSYS_CONFIG={
        'public_root': True,
        'public_root_split_enabled': True,
        'public_root_url': '/public-landing/',
    })
    def test_setup_form_shows_public_root_split_dependents_when_enabled(self):
        form = SystemSettingsForm(
            instance=SystemSettings(is_configured=False),
            mode='setup',
        )

        html = Template('{% load crispy_forms_tags %}{% crispy form %}').render(Context({'form': form}))
        dependent_class_start = html.index('ms-public-root-split-dependent')
        dependent_class_end = html.index('>', dependent_class_start)

        self.assertIn('data-ms-settings-toggle-field=\'public_root_split_enabled\'', html)
        self.assertIn('ms-public-root-split-dependent', html)
        self.assertNotIn('d-none', html[dependent_class_start:dependent_class_end])

    def test_setup_form_uses_translated_step_three_public_root_labels(self):
        translated_strings = {
            'access_security_settings_title': 'Security Custom',
            'root_home_settings_title': 'Routing Custom',
            'form_sys_public_root_split_enabled': 'Split Custom',
            'help_sys_public_root_split_enabled': 'Split help custom.',
            'form_sys_public_root_url': 'Anon Root Custom',
            'form_sys_public_root_url_discovered': 'Anon Root Pick Custom',
            'help_sys_public_root_url': 'Anon root help custom.',
            'help_sys_public_root_url_discovered': 'Anon root discovered help custom.',
        }

        with patch('microsys.forms.get_strings', return_value=translated_strings):
            form = SystemSettingsForm(
                instance=SystemSettings(is_configured=False),
                mode='setup',
            )

        html = Template('{% load crispy_forms_tags %}{% crispy form %}').render(Context({'form': form}))

        self.assertIn('Security Custom', html)
        self.assertIn('Routing Custom', html)
        self.assertIn('Split Custom', html)
        self.assertIn('Split help custom.', html)
        self.assertIn('Anon Root Custom', html)
        self.assertIn('Anon Root Pick Custom', html)
        self.assertIn('Anon root help custom.', html)
        self.assertIn('Anon root discovered help custom.', html)

    def test_setup_form_preserves_root_destinations_when_conditional_fields_are_omitted(self):
        form = SystemSettingsForm(
            data={
                'system_names': '{"en": "System", "ar": "System"}',
                'default_language': 'en',
                'default_theme': 'light',
                'allowed_themes': ['light'],
                'default_table_density': 'balanced',
                'languages': '{}',
                'translations_override': '{}',
                'public_root': 'on',
                'sidebar_config': '{"entries":[]}',
            },
            instance=SystemSettings(
                is_configured=True,
                home_url='/dashboard/',
                public_root=True,
                public_root_split_enabled=True,
                public_root_url='/anonymous-landing/',
            ),
        )

        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save(commit=False)
        self.assertEqual(saved.home_url, '/dashboard/')
        self.assertFalse(saved.public_root_split_enabled)
        self.assertEqual(saved.public_root_url, '/anonymous-landing/')

    def test_setup_form_saves_active_public_root_split_destinations(self):
        form = SystemSettingsForm(
            data={
                'system_names': '{"en": "System", "ar": "System"}',
                'home_url': '/dashboard/',
                'default_language': 'en',
                'default_theme': 'light',
                'allowed_themes': ['light'],
                'default_table_density': 'balanced',
                'languages': '{}',
                'translations_override': '{}',
                'public_root': 'on',
                'public_root_split_enabled': 'on',
                'public_root_url': '/anonymous-landing/',
                'sidebar_config': '{"entries":[]}',
            },
            instance=SystemSettings(is_configured=True),
        )

        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save(commit=False)
        self.assertEqual(saved.home_url, '/dashboard/')
        self.assertTrue(saved.public_root)
        self.assertTrue(saved.public_root_split_enabled)
        self.assertEqual(saved.public_root_url, '/anonymous-landing/')

    def test_public_root_setup_js_uses_single_form_scoped_controller(self):
        script = (
            Path(__file__).resolve().parents[1]
            / 'static'
            / 'microsys'
            / 'main'
            / 'js'
            / 'system_setup.js'
        ).read_text(encoding='utf-8')

        self.assertIn("target.name !== 'public_root'", script)
        self.assertIn("splitToggle.checked = false", script)
        self.assertIn("setNamedFieldDisabled(form, 'public_root_split_enabled'", script)
        self.assertNotIn("#id_public_root, #id_public_root_split_enabled", script)

    @override_settings(MICROSYS_CONFIG={
        'is_configured': True,
        'public_root': True,
        'home_url': '/public-home/',
        'titlebar': {'hide_on_public_unauthenticated_index': True},
    })
    def test_context_marks_anonymous_public_home_for_titlebar_hide(self):
        request = RequestFactory().get('/public-home/')
        request.user = AnonymousUser()
        request.session = {}
        request.resolver_match = SimpleNamespace(url_name='public_home')

        context = microsys_context(request)

        self.assertTrue(context['hide_titlebar_for_public_index'])

    @override_settings(MICROSYS_CONFIG={
        'is_configured': True,
        'public_root': True,
        'home_url': '/public-home/',
        'titlebar': {'hide_on_public_unauthenticated_index': True},
    })
    def test_base_template_hides_titlebar_for_anonymous_public_home_when_enabled(self):
        request = RequestFactory().get('/public-home/')
        request.user = AnonymousUser()
        request.session = {}
        request.resolver_match = SimpleNamespace(url_name='public_home')

        context = {'request': request, **microsys_context(request)}
        html = Template("{% extends 'microsys/base.html' %}{% block content %}Public{% endblock %}").render(Context(context))

        self.assertTrue(context['hide_titlebar_for_public_index'])
        self.assertNotIn('class="titlebar shadow-sm no-print"', html)

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
        instance = form.save(commit=False)
        self.assertEqual(decrypt_email_secret(instance.email_config['encrypted_password']), 'app-secret-pass')

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

    @override_settings(
        DEFAULT_FROM_EMAIL='deployer@example.com',
        EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
    )
    @patch.dict('os.environ', {
        'SMTP_RELAY_HOST': 'smtp.gmail.com',
        'SMTP_RELAY_PORT': '587',
    }, clear=False)
    def test_setup_form_accepts_relay_env_mode_with_upstream_env_hints(self):
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
                'email_config_secret_storage': 'env',
                'email_config_host': '',
                'email_config_port': '587',
                'email_config_username': '',
                'email_config_default_from_email': '',
                'sidebar_config': '{"entries":[]}',
            },
            instance=SystemSettings(is_configured=False),
        )

        self.assertTrue(form.is_valid(), form.errors)

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
        self.assertIn("alert alert-info small' data-autoclose='false'", html)

    def test_setup_form_renders_client_ip_config_controls(self):
        form = SystemSettingsForm(
            instance=SystemSettings(is_configured=False),
            mode='setup',
        )

        html = Template('{% load crispy_forms_tags %}{% crispy form %}').render(Context({'form': form}))

        self.assertIn('data-client-ip-mode-input="true"', html)
        self.assertIn('data-client-ip-hops="true"', html)
        self.assertIn('data-client-ip-custom-header="true"', html)
        self.assertIn('client_ip_trusted_proxy_hops', html)
        self.assertIn('client_ip_custom_header', html)
        self.assertIn('id_prevent_multiple_active_sessions', html)

    def test_setup_form_saves_client_ip_config_as_single_json_field(self):
        form = SystemSettingsForm(
            data={
                'home_url': DEFAULT_HOME_URL,
                'default_language': 'en',
                'default_theme': 'light',
                'allowed_themes': ['light'],
                'default_table_density': DEFAULT_TABLE_DENSITY,
                'client_ip_mode': 'custom',
                'client_ip_trusted_proxy_hops': '3',
                'client_ip_custom_header': 'CF-Connecting-IP',
            },
            instance=SystemSettings(is_configured=False),
            mode='setup',
        )

        self.assertTrue(form.is_valid(), form.errors)
        instance = form.save(commit=False)

        self.assertEqual(instance.client_ip_config['mode'], 'custom')
        self.assertEqual(instance.client_ip_config['trusted_proxy_hops'], 3)
        self.assertEqual(instance.client_ip_config['custom_header'], 'HTTP_CF_CONNECTING_IP')

    def test_system_setup_js_toggles_email_password_and_previews_default_language(self):
        script = Path(__file__).resolve().parents[1] / 'static' / 'microsys' / 'main' / 'js' / 'system_setup.js'
        contents = script.read_text(encoding='utf-8')

        self.assertIn('ms-email-config-password-field', contents)
        self.assertIn("secretStorageInput.value === 'encrypted_db'", contents)
        self.assertIn('previewSetupDefaultLanguage', contents)
        self.assertIn('window.setLanguage(normalizedLanguage, { previewOnly: true })', contents)
        self.assertNotIn('window.setLanguage(normalizedLanguage, { previewOnly: true, reload: false })', contents)
        self.assertIn('rehydrateSetupLanguageEditors(form)', contents)
        self.assertIn('restoreImportedEmailPasswordNotice(form);', contents)
        self.assertGreaterEqual(contents.count('restoreImportedEmailPasswordNotice(form);'), 2)
        self.assertIn('function restoreImportedEmailPasswordNotice(form) {', contents)
        self.assertIn('sessionStorage.removeItem(getSetupStateKey(form));', contents)
        self.assertIn("notice.setAttribute('data-autoclose', 'false');", contents)
        self.assertIn("form.dataset.suppressSetupLanguagePreview = 'true';", contents)
        self.assertNotIn('form.dataset.msWizardInitialStep = String(state.currentStep);', contents)
        self.assertIn('window.__msGetWizardInitialStep = function (container) {', contents)
        self.assertIn('if (stepHasValidationError(steps[index])) {', contents)
        self.assertIn('return index;', contents)
        self.assertIn("input.matches('[data-language-default]')", contents)
        self.assertIn('#id_sidebar_enable_toolbar, #id_sidebar_enabled', contents)
        self.assertIn('function syncSidebarBehaviorConfig(form) {', contents)
        self.assertIn('const hiddenInput = form.querySelector(\'input[name="sidebar_config"]\');', contents)
        self.assertIn('nextConfig.show_toolbar = readBooleanField(form, \'#id_sidebar_enable_toolbar\', true);', contents)
        self.assertIn('syncSidebarBehaviorConfig(form);', contents)
        self.assertIn('function seedNavbarConfigFromSidebar(form) {', contents)
        self.assertIn("shell.classList.contains('mode-setup')", contents)
        self.assertIn('navbarHierarchyHasNodes(navbarConfig)', contents)
        self.assertIn("toolbarToggle.disabled = !available;", contents)
        self.assertIn("'sidebar_enable_toolbar',\n                    'sidebar_show_icons'", contents)
        self.assertNotIn('toolbarToggle.checked = false;', contents)
        self.assertIn('data-public-registration-dependent', contents)
        self.assertIn('function setImportedSetupFinishVisible(form, visible)', contents)
        self.assertIn("t('system_setup_import_loaded'", contents)
        self.assertIn("t('system_setup_import_needs_email_password'", contents)
        self.assertIn("function syncSetupLanguagePickers(form) {", contents)
        self.assertIn("option.classList.toggle('is-active', isActive);", contents)
        self.assertIn("input.addEventListener('change', syncActive);", contents)
        self.assertIn("Object.prototype.hasOwnProperty.call(settings, 'registration_activation_mode')", contents)
        self.assertIn("function setupRequiresEmailPassword(form)", contents)
        self.assertIn("setupRequiresEmailPassword(form) && !emailConfig.encrypted_password", contents)
        self.assertIn("getNamedFieldValue(form, 'email_config_secret_storage') !== 'encrypted_db'", contents)
        self.assertNotIn("emailConfig.password_configured === true", contents)
        self.assertNotIn("const needsEncryptedDbPassword = emailConfig.secret_storage === 'encrypted_db'", contents)
        self.assertIn("form.dataset.suppressSetupLanguagePreview = 'true';", contents)
        self.assertIn("if (form.dataset.suppressSetupLanguagePreview === 'true')", contents)
        self.assertIn('window.__msPrepareWizardContainer = function (container) {', contents)
        self.assertIn('scan(document);', contents)
        self.assertNotIn('ms-setup-language-switch-pending', contents)
        self.assertNotIn('function setupDefaultLanguageWillSwitch(language) {', contents)
        self.assertIn('previewSetupDefaultLanguage(form, settings.default_language);', contents)
        self.assertIn("'allow_user_font_override'", contents)
        self.assertIn('applyImportedFontSettings(form, settings);', contents)
        self.assertIn("hiddenInput.addEventListener('change', () => {", contents)
        self.assertIn('function applyImportedSidebarSettings(form, sidebar) {', contents)
        self.assertIn("builder.dispatchEvent(new CustomEvent('microsys:sidebar-config-imported'", contents)
        self.assertIn("builder.addEventListener('microsys:sidebar-config-imported'", contents)
        self.assertIn('const sidebarSource = settings.sidebar_config || settings.sidebar;', contents)
        self.assertIn('const translationOverrides = settings.translations_override || settings.translations;', contents)
        self.assertIn('const navbarSource = settings.navbar_config || settings.navbar;', contents)
        self.assertIn('const titlebarSource = settings.titlebar_config || settings.titlebar;', contents)
        self.assertIn("setNamedFieldValue(form, 'titlebar_logo_treatment', titlebar.logo_treatment || 'none');", contents)
        self.assertIn("setNamedFieldValue(form, 'titlebar_logo_treatment_shape', titlebar.logo_treatment_shape || 'soft');", contents)
        self.assertIn("setNamedFieldReadonly(form, 'titlebar_logo_treatment_shape', !showLogoToggle.checked || logoTreatment !== 'plate');", contents)
        self.assertIn("setNamedFieldDisabled(form, 'registration_activation_mode', !enabled)", contents)
        self.assertIn("setNamedFieldDisabled(form, 'registration_throttle_enabled', !enabled)", contents)
        self.assertIn("'prevent_multiple_active_sessions'", contents)
        self.assertIn('initClientIpOptions', contents)
        self.assertIn('data-client-ip-mode-input', contents)
        self.assertIn("setNamedFieldDisabled(form, 'client_ip_trusted_proxy_hops', !showHops)", contents)
        self.assertIn("setNamedFieldDisabled(form, 'client_ip_custom_header', !showCustomHeader)", contents)
        self.assertIn('function initSystemSetupStepValidation(root) {', contents)
        self.assertIn('function updateSetupStepValidationState(form) {', contents)
        self.assertIn('return !field.checkValidity();', contents)
        self.assertIn("step.classList.toggle('ms-setup-step-has-error', hasError);", contents)
        self.assertIn("navItem.classList.toggle('has-validation-error', hasError);", contents)
        self.assertIn("bullet.textContent = hasError ? '!' : bullet.dataset.msStepNumber;", contents)
        self.assertIn("form.addEventListener('invalid', syncSoon, true);", contents)
        self.assertIn('persistSetupFormState(form);', contents)
        self.assertIn("form.querySelectorAll('.ms-btn-submit').forEach((button) => {", contents)
        self.assertIn('initSystemSetupStepValidation(root);', contents)

    def test_wizard_helper_reveals_server_hidden_steps(self):
        script = Path(__file__).resolve().parents[1] / 'static' / 'microsys' / 'helpers' / 'wizard' / 'js' / 'main.js'
        contents = script.read_text(encoding='utf-8')

        self.assertIn("step.classList.toggle('d-none', !isActive);", contents)
        self.assertIn("step.style.display = isActive ? '' : 'none';", contents)
        self.assertIn("step.setAttribute('aria-hidden', isActive ? 'false' : 'true');", contents)
        self.assertIn("button.classList.toggle('d-none', !isVisible);", contents)
        self.assertIn("button.style.display = isVisible ? '' : 'none';", contents)
        self.assertIn("button.setAttribute('aria-hidden', isVisible ? 'false' : 'true');", contents)
        self.assertIn('function prepareWizardContainer(container) {', contents)
        self.assertIn("typeof window.__msPrepareWizardContainer !== 'function'", contents)
        self.assertIn('prepareWizardContainer(container);', contents)
        self.assertLess(
            contents.index('prepareWizardContainer(container);'),
            contents.index("container.dataset.msWizardBound = 'true';"),
        )
        self.assertIn("container.querySelectorAll('[data-ms-wizard-step-target]')", contents)
        self.assertIn("item.classList.toggle('is-active', isActive);", contents)
        self.assertIn("item.classList.toggle('is-complete', isComplete);", contents)
        self.assertIn("item.setAttribute('aria-current', isActive ? 'step' : 'false');", contents)
        self.assertIn("container.dispatchEvent(new CustomEvent('ms:wizard-step-change'", contents)

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

    def test_tutorial_uses_modal_user_trigger_on_manage_users(self):
        script = Path(__file__).resolve().parents[1] / 'static' / 'microsys' / 'tutorial' / 'js' / 'main.js'
        contents = script.read_text(encoding='utf-8')

        self.assertIn("button[data-dynamic-modal]", contents)
        self.assertNotIn('a[href*="create_user"]', contents)

    def test_permissions_css_hardens_staff_tier_preview_for_light_and_dark_themes(self):
        stylesheet = Path(__file__).resolve().parents[1] / 'static' / 'microsys' / 'users' / 'css' / 'permissions.css'
        contents = stylesheet.read_text(encoding='utf-8')

        self.assertIn('.ms-staff-tier-preview .badge.bg-primary {', contents)
        self.assertIn('linear-gradient(135deg, #1d4ed8 0%, #2563eb 55%, #3b82f6 100%)', contents)
        self.assertIn(':root.theme-dark .ms-staff-tier-preview,', contents)
        self.assertIn(':root.theme-gothic .ms-staff-tier-preview,', contents)
        self.assertIn(':root.theme-neon .ms-staff-tier-preview,', contents)
        self.assertIn(':root.theme-retro .ms-staff-tier-preview,', contents)
        self.assertIn(':root.theme-prism .ms-staff-tier-preview {', contents)

    def test_tables_css_hardens_staff_tier_badges_for_manage_users(self):
        stylesheet = Path(__file__).resolve().parents[1] / 'static' / 'microsys' / 'main' / 'css' / 'tables.css'
        contents = stylesheet.read_text(encoding='utf-8')

        self.assertIn('.ms-staff-tier-badge--global_staff {', contents)
        self.assertIn('linear-gradient(135deg, #1d4ed8 0%, #2563eb 55%, #3b82f6 100%)', contents)
        self.assertIn('.ms-staff-tier-badge--delegate {', contents)

    def test_user_detail_modal_uses_shared_staff_tier_badge_classes(self):
        template_path = Path(__file__).resolve().parents[1] / 'templates' / 'microsys' / 'users' / 'user_detail_modal.html'
        contents = template_path.read_text(encoding='utf-8')

        self.assertIn('ms-staff-tier-badge--{{ target_user_management_tier.tier_key }}', contents)
        self.assertIn('ms-staff-tier-badge--delegate', contents)
        self.assertNotIn('badge {{ target_user_management_tier.badge_classes }}', contents)

    def test_main_css_forces_readable_primary_badge_text(self):
        stylesheet = Path(__file__).resolve().parents[1] / 'static' / 'microsys' / 'main' / 'css' / 'main.css'
        contents = stylesheet.read_text(encoding='utf-8')

        self.assertIn('.badge.bg-primary,', contents)
        self.assertIn('.text-bg-primary,', contents)
        self.assertIn('.badge.text-bg-primary {', contents)
        self.assertIn('color: #fff !important;', contents)

    def test_titlebar_login_round_uses_shared_shape_and_theme_selectors(self):
        static_root = Path(__file__).resolve().parents[1] / 'static' / 'microsys'
        titlebar_css = (static_root / 'main' / 'css' / 'titlebar.css').read_text(encoding='utf-8')

        self.assertIn('.titlebar .ms-login-round {', titlebar_css)
        self.assertIn('.titlebar[data-titlebar-home-shape="square"] .ms-login-round {', titlebar_css)
        self.assertIn('.titlebar[data-titlebar-home-shape="squircle"] .ms-login-round {', titlebar_css)
        self.assertIn('.titlebar .ms-login-round:hover,', titlebar_css)
        self.assertIn('.titlebar .ms-login-round:focus-visible {', titlebar_css)
        self.assertIn('.titlebar[data-titlebar-logo-treatment="plate"] .titlebar__logo {', titlebar_css)
        self.assertIn('.titlebar[data-titlebar-logo-treatment="halo"] .titlebar__logo {', titlebar_css)
        self.assertIn('.titlebar[data-titlebar-logo-treatment="contrast"] .titlebar__logo {', titlebar_css)
        self.assertIn('.titlebar[data-titlebar-logo-treatment="plate"][data-titlebar-logo-treatment-shape="pill"] .titlebar__logo {', titlebar_css)
        titlebar_template = Path(__file__).resolve().parents[1] / 'templates' / 'microsys' / 'includes' / 'titlebar.html'
        titlebar_markup = titlebar_template.read_text(encoding='utf-8')
        self.assertIn('data-titlebar-logo-treatment="{{ titlebar.logo_treatment|default:\'none\' }}"', titlebar_markup)
        self.assertIn('data-titlebar-logo-treatment-shape="{{ titlebar.logo_treatment_shape|default:\'soft\' }}"', titlebar_markup)

        for theme_name in ('dark', 'gothic', 'retro', 'neon', 'prism', 'aether'):
            theme_css = (static_root / 'themes' / 'css' / f'{theme_name}.css').read_text(encoding='utf-8')
            self.assertIn('.titlebar .ms-login-round {', theme_css)
            self.assertIn('.titlebar .ms-login-round:hover,', theme_css)
            self.assertIn('.titlebar .ms-login-round:focus-visible {', theme_css)
            self.assertIn('.titlebar[data-titlebar-logo-treatment="plate"] .titlebar__logo {', theme_css)

    def test_neon_theme_excludes_options_panels_from_generic_option_section_overlays(self):
        stylesheet = Path(__file__).resolve().parents[1] / 'static' / 'microsys' / 'themes' / 'css' / 'neon.css'
        contents = stylesheet.read_text(encoding='utf-8')

        self.assertIn('.option-section:not(.ms-options-panel):not([class*="text-bg-"]):not([class*="bg-"]),', contents)
        self.assertIn('.option-section:not(.ms-options-panel)::before,', contents)
        self.assertIn('.option-section:not(.ms-options-panel):hover::before,', contents)
        self.assertIn('.option-section:not(.ms-options-panel),', contents)
        self.assertIn('.option-section:not(.ms-options-panel) > *,', contents)

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
        self.assertIn('.ms-setup-step-nav {', contents)
        self.assertIn('grid-template-columns: repeat(7, minmax(6.2rem, 1fr));', contents)
        self.assertIn('.ms-setup-step-nav__item.is-active {', contents)
        self.assertIn('.ms-setup-step-nav__item.is-complete {', contents)
        self.assertIn('backdrop-filter: blur(14px);', contents)

    def test_system_setup_css_defines_step_validation_warning_state(self):
        stylesheet = Path(__file__).resolve().parents[1] / 'static' / 'microsys' / 'main' / 'css' / 'system_setup.css'
        contents = stylesheet.read_text(encoding='utf-8')

        self.assertIn('.ms-setup-step-nav__item.has-validation-error {', contents)
        self.assertIn('.ms-setup-step-nav__item.has-validation-error .ms-setup-step-nav__bullet {', contents)
        self.assertIn('.ms-system-settings-shell.mode-setup .wizard-step.ms-setup-step-has-error {', contents)
        self.assertIn('border-color: rgba(245, 158, 11, 0.72);', contents)
        self.assertIn('background: #f59e0b;', contents)
        self.assertNotIn('ms-setup-language-switch-pending', contents)
        self.assertNotIn('visibility: hidden;', contents)

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

    def test_shared_switch_css_uses_pointer_for_enabled_toggle_inputs(self):
        stylesheet = Path(__file__).resolve().parents[1] / 'static' / 'microsys' / 'main' / 'css' / 'main.css'
        contents = stylesheet.read_text(encoding='utf-8')

        self.assertIn('.form-switch .form-check-input:not(:disabled) {', contents)
        self.assertIn('cursor: pointer;', contents)

    def test_options_template_uses_external_assets_and_draggable_cards(self):
        template_path = Path(__file__).resolve().parents[1] / 'templates' / 'microsys' / 'includes' / 'options.html'
        contents = template_path.read_text(encoding='utf-8')

        self.assertIn("microsys/main/css/options.css", contents)
        self.assertIn("?v=20260525a", contents)
        self.assertIn("microsys/main/js/options.js", contents)
        self.assertIn('{{ server_time_backend_display }}', contents)
        self.assertIn('id="msOptionsGrid"', contents)
        self.assertIn('data-options-card="system-info"', contents)
        self.assertIn('data-options-card="autofill"', contents)
        self.assertIn('data-options-card="reset-defaults"', contents)
        self.assertIn('data-options-card-handle', contents)
        self.assertIn('bi-grip-vertical', contents)
        self.assertNotIn('bi-arrow-left-right', contents)
        self.assertIn('id="autofillToggle"', contents)
        self.assertIn('name="autofill_enabled"', contents)
        self.assertIn('name="accessibility_high_contrast"', contents)
        self.assertIn('id="btnResetInit"', contents)
        self.assertIn('id="resetActions"', contents)
        self.assertNotIn('<style nonce=', contents)
        self.assertNotIn('<script nonce=', contents)
        self.assertIn('MS_TRANS.system_settings_security', contents)
        self.assertNotIn("default:'Access & Security'", contents)

    def test_base_template_versions_shared_main_stylesheet(self):
        template_path = Path(__file__).resolve().parents[1] / 'templates' / 'microsys' / 'base.html'
        contents = template_path.read_text(encoding='utf-8')

        self.assertIn("microsys/main/css/main.css", contents)
        self.assertIn("?v=20260607d", contents)
        self.assertIn("microsys/main/css/system_setup.css", contents)
        self.assertIn("?v=20260610a", contents)
        self.assertIn("microsys/main/js/system_setup.js", contents)
        self.assertIn("microsys/helpers/wizard/js/main.js", contents)
        self.assertLess(
            contents.index("microsys/main/js/system_setup.js"),
            contents.index("microsys/helpers/wizard/js/main.js"),
        )
        self.assertGreaterEqual(contents.count("?v=20260610a"), 3)
        self.assertIn("microsys/main/js/navbar.js", contents)
        self.assertIn("microsys/main/css/navbar.css", contents)
        self.assertIn("{% static theme.css_path %}?v=20260528c", contents)
        self.assertIn("microsys/main/css/template_cleanup.css", contents)
        self.assertIn("?v=20260529a", contents)

    def test_theme_preview_surfaces_include_aether_and_light_mono(self):
        css_path = Path(__file__).resolve().parents[1] / 'static' / 'microsys' / 'main' / 'css' / 'template_cleanup.css'
        contents = css_path.read_text(encoding='utf-8')

        self.assertIn('.ms-theme-preview--mono', contents)
        self.assertIn('#ffffff 0%', contents)
        self.assertIn('#f4f6f8 48%', contents)
        self.assertIn('#cbd5df 49%', contents)
        self.assertIn('#94a3b8 100%', contents)
        self.assertNotIn('#475569 39%', contents)
        self.assertNotIn('#0f172a 100%', contents)
        self.assertIn('.ms-theme-preview--prism', contents)
        self.assertIn('.ms-theme-preview--aether', contents)
        self.assertIn('#a8ffe4', contents)

    def test_prism_and_aether_theme_owned_file_field_and_logo_overrides(self):
        static_root = Path(__file__).resolve().parents[1] / 'static' / 'microsys'

        for theme_name in ('prism', 'aether'):
            contents = (static_root / 'themes' / 'css' / f'{theme_name}.css').read_text(encoding='utf-8')
            self.assertIn(f':root.theme-{theme_name} .archive-file-card {{', contents)
            self.assertIn(f':root.theme-{theme_name} .archive-file-field.is-dragover .archive-file-card,', contents)
            self.assertIn(f':root.theme-{theme_name} .archive-file-tool-upload {{', contents)
            self.assertIn(f':root.theme-{theme_name} .archive-file-tool-scan {{', contents)
            self.assertIn(f':root.theme-{theme_name} .archive-file-tool-clear {{', contents)
            self.assertIn(f':root.theme-{theme_name} .archive-file-meta {{', contents)
            self.assertIn(f':root.theme-{theme_name} .titlebar[data-titlebar-logo-treatment="plate"] .titlebar__logo {{', contents)
            self.assertIn(f':root.theme-{theme_name} .titlebar[data-titlebar-logo-treatment="halo"] .titlebar__logo {{', contents)
            self.assertIn(f':root.theme-{theme_name} .titlebar[data-titlebar-logo-treatment="contrast"] .titlebar__logo {{', contents)

    def test_options_theme_system_settings_tiles_include_aether(self):
        css_path = Path(__file__).resolve().parents[1] / 'static' / 'microsys' / 'main' / 'css' / 'options.css'
        contents = css_path.read_text(encoding='utf-8')

        self.assertIn(':root.theme-aether .ms-system-settings-actions .ms-system-settings-tile,', contents)
        self.assertIn(':root.theme-aether .ms-system-settings-tile-icon,', contents)
        self.assertIn(':root.theme-aether .ms-system-settings-actions .ms-system-settings-tile i,', contents)
        self.assertIn(':root.theme-aether .ms-system-settings-actions .ms-system-settings-tile:hover,', contents)
        self.assertIn(':root.theme-aether .ms-system-settings-actions .ms-system-settings-tile:focus-visible,', contents)
        self.assertIn(':root.theme-aether .ms-system-settings-actions .ms-system-settings-action--secondary,', contents)

    def test_verify_template_uses_versioned_auto_verify_script_and_trust_device_checkbox(self):
        template_path = Path(__file__).resolve().parents[1] / 'templates' / 'microsys' / '2fa' / 'verify.html'
        css_path = Path(__file__).resolve().parents[1] / 'static' / 'microsys' / 'users' / 'css' / 'login.css'
        script_path = Path(__file__).resolve().parents[1] / 'static' / 'microsys' / 'users' / 'js' / 'twofa_verify.js'
        contents = template_path.read_text(encoding='utf-8')
        stylesheet = css_path.read_text(encoding='utf-8')
        script = script_path.read_text(encoding='utf-8')

        self.assertIn("microsys/users/css/login.css", contents)
        self.assertIn("?v=20260515e", contents)
        self.assertIn("microsys/users/js/twofa_verify.js", contents)
        self.assertIn("?v=20260515e", contents)
        self.assertIn('id="usePrimaryMethodBtn"', contents)
        self.assertIn('name="trust_device"', contents)
        self.assertIn('ms-twofa-login-state', contents)
        self.assertIn('MS_TRANS.2fa_trust_device_label', contents)
        self.assertIn('MS_TRANS.login_logo_alt', contents)
        self.assertNotIn('2fa_backup_instruction|default', contents)
        self.assertNotIn('2fa_email_request_instruction|default', contents)
        self.assertNotIn('2fa_send_email_code|default', contents)
        self.assertNotIn('2fa_return_to_default|default', contents)
        self.assertIn('form.requestSubmit', script)
        self.assertIn('updateModeActions', script)
        self.assertIn('inputEl.readOnly = disabled;', script)
        self.assertNotIn('inputEl.disabled = disabled;', script)
        self.assertIn("new URLSearchParams({ method: 'email' })", script)
        self.assertNotIn('Return to default method', script)
        self.assertNotIn('Unable to send code', script)
        self.assertIn('.ms-twofa-inline-alert', stylesheet)
        self.assertIn('.ms-twofa-trust-field', stylesheet)

    def test_recent_2fa_and_client_ip_surfaces_do_not_use_hardcoded_translation_fallbacks(self):
        project_root = Path(__file__).resolve().parents[1]
        forms_contents = (project_root / 'forms.py').read_text(encoding='utf-8')
        profile_contents = (project_root / 'templates' / 'microsys' / 'users' / 'profile.html').read_text(encoding='utf-8')
        translation_contents = (project_root / 'translations.py').read_text(encoding='utf-8')

        self.assertNotIn("s.get('form_sys_client_ip_mode', 'Client IP source')", forms_contents)
        self.assertNotIn("s.get('client_ip_settings_title', 'Client IP Resolution')", forms_contents)
        self.assertNotIn("s.get('client_ip_settings_desc', 'Microsys uses this setting", forms_contents)
        self.assertNotIn('MS_TRANS.trusted_device_badge|default', profile_contents)
        self.assertNotIn('MS_TRANS.trusted_until|default', profile_contents)
        self.assertIn("'form_sys_client_ip_mode':", translation_contents)
        self.assertIn("'client_ip_settings_title':", translation_contents)
        self.assertIn("'2fa_trust_device_label':", translation_contents)
        self.assertIn("'trusted_device_badge':", translation_contents)

    def test_dynamic_modal_template_uses_nonce_on_external_loader(self):
        template_path = Path(__file__).resolve().parents[1] / 'templates' / 'microsys' / 'helpers' / 'dynamic_modal.html'
        script_path = Path(__file__).resolve().parents[1] / 'static' / 'microsys' / 'helpers' / 'dynamic_modal' / 'js' / 'main.js'
        contents = template_path.read_text(encoding='utf-8')
        script = script_path.read_text(encoding='utf-8')

        self.assertIn("microsys/helpers/dynamic_modal/js/main.js", contents)
        self.assertIn("?v=20260525e", contents)
        self.assertIn('nonce="{{ request.csp_nonce }}"', contents)
        self.assertIn("'Accept': 'application/json'", script)
        self.assertIn("dynamic-modal-loading-shell", script)
        self.assertIn("dynamic-modal-overlay", script)
        self.assertIn("hasUsablePreviousFallback", script)
        self.assertIn("Node.ELEMENT_NODE", script)
        self.assertIn("skeletonBlock", script)
        self.assertIn("hasPreviousFallback", script)
        self.assertIn("Request failed with HTTP ${res.status}", script)

    def test_setup_editor_templates_use_ids_not_post_names_for_js_controls(self):
        templates_root = Path(__file__).resolve().parents[1] / 'templates' / 'microsys' / 'includes'

        language_editor = (templates_root / 'language_catalog_editor.html').read_text(encoding='utf-8')
        system_names_editor = (templates_root / 'system_names_editor.html').read_text(encoding='utf-8')
        translation_editor = (templates_root / 'translation_matrix_editor.html').read_text(encoding='utf-8')
        sidebar_builder = (templates_root / 'sidebar_builder.html').read_text(encoding='utf-8')
        setup_script = (
            Path(__file__).resolve().parents[1]
            / 'static'
            / 'microsys'
            / 'main'
            / 'js'
            / 'system_setup.js'
        ).read_text(encoding='utf-8')

        self.assertIn('id="ms-language-code-input"', language_editor)
        self.assertIn('id="ms-language-name-input"', language_editor)
        self.assertIn('id="ms-language-dir-input"', language_editor)
        self.assertIn('id="ms-language-flag-input"', language_editor)
        self.assertIn('id="ms-system-name-', system_names_editor)
        self.assertIn('id="ms-translation-search"', translation_editor)
        self.assertIn('id="ms-translation-status"', translation_editor)
        self.assertIn('id="ms-sidebar-catalog-data-', sidebar_builder)
        self.assertIn('id="ms-sidebar-builder-search-', sidebar_builder)
        self.assertIn('id="sidebarSystemItemsToggle-', sidebar_builder)
        self.assertNotIn('name="ms_', language_editor)
        self.assertNotIn('name="ms_', system_names_editor)
        self.assertNotIn('name="ms_', translation_editor)
        self.assertNotIn('name="ms_', sidebar_builder)
        self.assertNotIn('name="sidebarSystemItemsToggle-', sidebar_builder)
        self.assertNotIn('name="ms_language_default_choice"', setup_script)

    def test_system_settings_render_does_not_submit_js_only_editor_controls(self):
        form = SystemSettingsForm(
            instance=SystemSettings(is_configured=False),
            mode='modal',
        )

        html = Template('{% load crispy_forms_tags %}{% crispy form %}').render(Context({'form': form}))

        self.assertNotIn('name="ms_', html)
        self.assertNotIn('name="sidebarSystemItemsToggle-', html)
        self.assertLess(len(re.findall(r'\sname=', html)), 200)

    def test_options_assets_define_shared_card_system_and_reorder_logic(self):
        css_path = Path(__file__).resolve().parents[1] / 'static' / 'microsys' / 'main' / 'css' / 'options.css'
        js_path = Path(__file__).resolve().parents[1] / 'static' / 'microsys' / 'main' / 'js' / 'options.js'

        css_contents = css_path.read_text(encoding='utf-8')
        js_contents = js_path.read_text(encoding='utf-8')

        self.assertIn('.ms-options-panel {', css_contents)
        self.assertIn('.ms-options-card {', css_contents)
        self.assertIn('.ms-options-card-handle {', css_contents)
        self.assertIn('.ms-options-card-handle:not(:disabled),', css_contents)
        self.assertIn('.ms-options-card-handle .bi {', css_contents)
        self.assertIn('cursor: grab;', css_contents)
        self.assertIn('.ms-options-card-handle:not(:disabled):active,', css_contents)
        self.assertIn('.ms-options-card-handle:active .bi {', css_contents)
        self.assertIn('cursor: grabbing;', css_contents)
        self.assertIn('float: inline-end;', css_contents)
        self.assertNotIn('top: 1rem;', css_contents)
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

    def test_profile_confirmation_script_submits_password_modal_on_enter(self):
        template_path = Path(__file__).resolve().parents[1] / 'templates' / 'microsys' / 'users' / 'profile.html'
        script_path = Path(__file__).resolve().parents[1] / 'static' / 'microsys' / 'users' / 'js' / 'profile_2fa.js'
        template = template_path.read_text(encoding='utf-8')
        script = script_path.read_text(encoding='utf-8')

        self.assertIn("microsys/users/js/profile_2fa.js' %}?v=20260524a", template)
        self.assertIn("passwordInput.addEventListener('keydown', submitOnEnter);", script)
        self.assertIn('profile-session-trust-form', template)
        self.assertIn('MS_TRANS.msg_confirm_trust_current_device', template)
        self.assertIn('MS_TRANS.session_revoke_trusted_denied', template)
        self.assertIn('function confirmSessionTrust(form)', script)
        self.assertIn("passwordInput.addEventListener('input', clearPasswordError);", script)
        self.assertIn("if (event.key !== 'Enter') return;", script)
        self.assertIn('confirmCurrentModal();', script)
        self.assertIn('.then(parseJsonResponse)', script)
        self.assertIn("window.location.assign(data.redirect_url || window.location.href);", script)

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
            rel_path = path.relative_to(templates_root).as_posix()
            if re.search(r'<style\b', contents, re.IGNORECASE) and rel_path != 'microsys/base.html':
                violations.append(f'{rel_path}:style-block')
            if inline_script_pattern.search(contents):
                violations.append(f'{rel_path}:inline-script')

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
            allowed_fonts=['cairo'],
            default_fonts={'en': 'cairo'},
            allow_user_font_override=False,
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
            navbar_config={'enabled': True, 'default_mode': 'history', 'hierarchy': {'nodes': []}},
            prevent_multiple_active_sessions=True,
        )

        payload = export_system_settings_payload(settings_obj)
        email_config = payload['settings']['email_config']

        self.assertNotIn('encrypted_password', email_config)
        self.assertTrue(email_config['password_configured'])
        self.assertEqual(email_config['transport'], 'direct')
        self.assertEqual(email_config['secret_storage'], 'encrypted_db')
        self.assertFalse(payload['settings']['sidebar_config']['enabled'])
        self.assertTrue(payload['settings']['navbar_config']['enabled'])
        self.assertEqual(payload['settings']['navbar_config']['default_mode'], 'history')
        self.assertEqual(payload['settings']['allowed_fonts'], ['cairo'])
        self.assertEqual(payload['settings']['default_fonts'], {'en': 'cairo'})
        self.assertFalse(payload['settings']['allow_user_font_override'])
        self.assertTrue(payload['settings']['prevent_multiple_active_sessions'])

        imported = normalize_system_settings_import_payload(payload)
        self.assertNotIn('encrypted_password', imported['email_config'])
        self.assertTrue(imported['email_config']['password_configured'])
        self.assertEqual(imported['allowed_fonts'], ['cairo'])
        self.assertEqual(imported['default_fonts'], {'en': 'cairo'})
        self.assertFalse(imported['allow_user_font_override'])
        self.assertTrue(imported['prevent_multiple_active_sessions'])

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

    def test_system_setup_js_keeps_last_allowed_theme_postable(self):
        script = Path(__file__).resolve().parents[1] / 'static' / 'microsys' / 'main' / 'js' / 'system_setup.js'
        contents = script.read_text(encoding='utf-8')

        self.assertNotIn('checkbox.disabled = checkbox.checked && resolvedAllowedThemes.length === 1;', contents)
        self.assertIn("if (checkbox.checked && getAllowedThemes().length === 1)", contents)
        self.assertIn("checkbox.setAttribute('aria-disabled', isLocked ? 'true' : 'false');", contents)
        self.assertIn("preview: true,", contents)
        self.assertIn("option.getAttribute('data-setup-theme-preview-url')", contents)

    def test_theme_runtime_fades_explicit_switches_and_honors_reduced_motion(self):
        assets_root = Path(__file__).resolve().parents[1] / 'static' / 'microsys'
        theme_script = (assets_root / 'themes' / 'js' / 'main.js').read_text(encoding='utf-8')
        main_css = (assets_root / 'main' / 'css' / 'main.css').read_text(encoding='utf-8')
        sidebar_css = (assets_root / 'sidebar' / 'css' / 'main.css').read_text(encoding='utf-8')

        self.assertIn('function fadeThemeSwitch(resolvedTheme)', theme_script)
        self.assertIn("root.classList.contains('accessibility-no-animations')", theme_script)
        self.assertIn("window.matchMedia('(prefers-reduced-motion: reduce)')", theme_script)
        self.assertIn("root.classList.add('ms-theme-switching-covered')", theme_script)
        self.assertIn(':root.ms-theme-switching body::after {', main_css)
        self.assertIn(':root.ms-theme-switching.ms-theme-switching-covered body::after {', main_css)
        self.assertIn('@media (prefers-reduced-motion: reduce) {', main_css)
        self.assertIn(':root.ms-theme-switching .sidebar .list-group-item,', sidebar_css)
        self.assertIn(':root.ms-theme-switching .sidebar .accordion-button i {', sidebar_css)
        self.assertIn('transition: none !important;', sidebar_css)

    def test_sidebar_collapsed_icons_only_hides_group_label_flex_space(self):
        sidebar_css = (
            Path(__file__).resolve().parents[1]
            / 'static'
            / 'microsys'
            / 'sidebar'
            / 'css'
            / 'main.css'
        ).read_text(encoding='utf-8')

        self.assertIn('.sidebar.collapsed .accordion-button span {', sidebar_css)
        self.assertIn('flex: 0 0 0;', sidebar_css)
        self.assertIn('overflow: hidden;', sidebar_css)
        self.assertIn('.sidebar.collapsed .accordion-button.sidebar-folder-button span {', sidebar_css)
        self.assertIn('transition: none !important;', sidebar_css)
        self.assertIn('inset-inline-start: -9999px;', sidebar_css)
        self.assertIn('.sidebar.collapsed .accordion-header {', sidebar_css)
        self.assertIn('.sidebar.collapsed .accordion-button.sidebar-folder-button,', sidebar_css)
        self.assertIn('.sidebar.collapsed .accordion-button.sidebar-folder-button i {', sidebar_css)
        self.assertIn('min-width: var(--sidebar-icon-width);', sidebar_css)

    def test_sidebar_folder_buttons_do_not_use_redundant_flex_grow_classes(self):
        templates_root = Path(__file__).resolve().parents[1] / 'templates' / 'microsys' / 'sidebar'
        tree_template = (templates_root / 'tree.html').read_text(encoding='utf-8')
        extra_groups_template = (templates_root / 'extra_groups.html').read_text(encoding='utf-8')

        self.assertNotIn('accordion-button sidebar-folder-button flex-grow-1', tree_template)
        self.assertNotIn('accordion-button sidebar-folder-button flex-grow-1', extra_groups_template)
        self.assertNotIn('<span class="flex-grow-1 text-start">', tree_template)
        self.assertNotIn('<span class="flex-grow-1 text-start">', extra_groups_template)
        self.assertIn('<span class="text-start">', tree_template)
        self.assertIn('<span class="text-start">', extra_groups_template)

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
