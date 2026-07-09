from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.contrib.auth import get_user_model
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

from dlux.system.constants import DEFAULT_HOME_URL, DEFAULT_TABLE_DENSITY, TITLEBAR_ACTIONS_ORDER
from dlux.context_processors import dlux_context
from dlux.forms import SystemSettingsForm
from dlux.models import SystemSettings
from dlux.themes import get_theme_names
from dlux.utils import (
    decrypt_email_secret,
    export_system_settings_payload,
    get_dlux_email_config,
    get_system_config,
    normalize_navbar_config,
    normalize_system_settings_import_payload,
    normalize_titlebar_actions_order,
    normalize_titlebar_config,
    seed_navbar_config_from_sidebar,
)
from dlux.navbar import build_navbar_hierarchy_crumbs

_LEGACY_HOME_URL = '/sys/'


def _assert_versioned_static_asset(testcase, contents, asset_path):
    # An asset is cache-busted either via the {% dlux_static 'path' %} tag (which
    # appends ?v=<DjangoLux version> at render) or a legacy {% static %}?v=DATE ref.
    p = re.escape(asset_path)
    testcase.assertRegex(contents, rf"(dlux_static\s+['\"]{p}['\"]|{p}[^\n]*\?v=)")


class DluxDefaultRouteTests(SimpleTestCase):
    databases = {'default'}

    def setUp(self):
        cache.clear()
        SystemSettings._default_manager.all().delete()
        super().setUp()

    @override_settings(DLUX_CONFIG={})
    def test_system_config_defaults_home_url_to_profile(self):
        self.assertEqual(get_system_config().get('home_url'), DEFAULT_HOME_URL)

    def test_dlux_settings_status_does_not_create_singleton(self):
        out = StringIO()

        call_command('dlux_settings', 'status', stdout=out)

        self.assertIn('SystemSettings singleton: missing', out.getvalue())
        self.assertFalse(SystemSettings._default_manager.filter(pk=1).exists())

    def test_dlux_settings_unconfigure_preserves_settings(self):
        instance = SystemSettings.load()
        instance.is_configured = True
        instance.home_url = '/sys/profile/'
        instance.sidebar_config = {'enabled': False, 'entries': []}
        instance.save()

        call_command('dlux_settings', 'unconfigure', stdout=StringIO())

        instance.refresh_from_db()
        self.assertFalse(instance.is_configured)
        self.assertEqual(instance.home_url, '/sys/profile/')
        self.assertFalse(instance.sidebar_config['enabled'])

    def test_dlux_settings_delete_requires_yes_and_removes_singleton(self):
        SystemSettings.load()

        with self.assertRaises(CommandError):
            call_command('dlux_settings', 'delete', stdout=StringIO())

        self.assertTrue(SystemSettings._default_manager.filter(pk=1).exists())
        call_command('dlux_settings', 'delete', '--yes', stdout=StringIO())
        self.assertFalse(SystemSettings._default_manager.filter(pk=1).exists())

    def test_dlux_settings_reset_recreates_unconfigured_defaults(self):
        instance = SystemSettings.load()
        instance.is_configured = True
        instance.home_url = '/custom/'
        instance.save()

        call_command('dlux_settings', 'reset', '--yes', stdout=StringIO())

        instance = SystemSettings._default_manager.get(pk=1)
        self.assertFalse(instance.is_configured)
        self.assertEqual(instance.home_url, DEFAULT_HOME_URL)

    def test_dlux_settings_export_import_roundtrip(self):
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
            call_command('dlux_settings', 'export', '--output', str(path), stdout=StringIO())
            call_command('dlux_settings', 'delete', '--yes', stdout=StringIO())
            call_command('dlux_settings', 'import', '--input', str(path), stdout=StringIO())

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

    def test_system_settings_import_accepts_grouped_config_aliases(self):
        imported = normalize_system_settings_import_payload({
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
                'public_root_url': '/public-import/',
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
        })

        self.assertTrue(imported['email_2fa'])
        self.assertTrue(imported['prevent_multiple_active_sessions'])
        self.assertFalse(imported['login_lockout_enabled'])
        self.assertTrue(imported['public_registration_enabled'])
        self.assertEqual(imported['registration_activation_mode'], 'verified_pending_approval')
        self.assertFalse(imported['registration_throttle_enabled'])
        self.assertTrue(imported['public_root'])
        self.assertTrue(imported['public_root_split_enabled'])
        self.assertEqual(imported['public_root_url'], '/public-import/')
        self.assertEqual(imported['default_table_density'], 'dense')
        self.assertEqual(imported['translations_override'], {'en': {'custom_key': 'Custom'}})
        self.assertFalse(imported['allow_user_language_override'])
        self.assertEqual(imported['allowed_themes'], ['dark'])
        self.assertFalse(imported['allow_user_theme_override'])
        self.assertEqual(imported['allowed_fonts'], ['cairo'])
        self.assertEqual(imported['default_fonts'], {'en': 'cairo'})
        self.assertFalse(imported['allow_user_font_override'])
        self.assertEqual(imported['extra_config'], {'host_flag': True})

    def test_system_settings_export_remains_flat_after_grouped_storage(self):
        instance = SystemSettings.load()
        instance.public_root = True
        instance.public_root_split_enabled = True
        instance.public_root_url = '/public-export/'
        instance.default_table_density = 'roomy'
        instance.translations_override = {'en': {'custom_key': 'Custom'}}
        instance.allowed_themes = ['dark']
        instance.extra_config = {'host_flag': True}
        instance.save()

        payload = export_system_settings_payload(instance)
        settings_payload = payload['settings']

        self.assertTrue(settings_payload['public_root'])
        self.assertTrue(settings_payload['public_root_split_enabled'])
        self.assertEqual(settings_payload['public_root_url'], '/public-export/')
        self.assertEqual(settings_payload['default_table_density'], 'roomy')
        self.assertEqual(settings_payload['translations_override'], {'en': {'custom_key': 'Custom'}})
        self.assertEqual(settings_payload['allowed_themes'], ['dark'])
        self.assertEqual(settings_payload['extra_config'], {'host_flag': True})
        self.assertNotIn('public_root_config', settings_payload)
        self.assertNotIn('layout_config', settings_payload)
        self.assertNotIn('theme_config', settings_payload)
        self.assertNotIn('language_config', settings_payload)

    def test_system_settings_export_import_preserves_flat_strong_password_toggle(self):
        instance = SystemSettings.load()
        instance.auth_config = {
            'email_2fa': False,
            'prevent_multiple_active_sessions': False,
            'login_lockout_enabled': True,
            'enforce_strong_passwords': True,
        }
        instance.save()

        payload = export_system_settings_payload(instance)
        imported = normalize_system_settings_import_payload(payload)

        self.assertTrue(payload['settings']['enforce_strong_passwords'])
        self.assertTrue(imported['enforce_strong_passwords'])

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

    def test_titlebar_user_hub_style_and_actions_order_normalize(self):
        defaults = normalize_titlebar_config({})
        invalid = normalize_titlebar_config({
            'user_hub_style': 'drawer',
            'actions_order': ['auth', 'unknown', 'home', 'auth'],
        })
        custom = normalize_titlebar_config({
            'user_hub_style': 'titlebar_actions',
            'actions_order': ['auth', 'settings', 'home'],
        })

        self.assertEqual(defaults['user_hub_style'], 'dropdown')
        self.assertEqual(defaults['actions_order'], list(TITLEBAR_ACTIONS_ORDER))
        self.assertEqual(invalid['user_hub_style'], 'dropdown')
        self.assertEqual(invalid['actions_order'][:2], ['auth', 'home'])
        self.assertNotIn('unknown', invalid['actions_order'])
        self.assertEqual(custom['user_hub_style'], 'titlebar_actions')
        self.assertEqual(custom['actions_order'][:3], ['auth', 'settings', 'home'])
        self.assertEqual(
            normalize_titlebar_actions_order(['home', 'home', 'profile'])[:2],
            ['home', 'profile'],
        )

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

        with patch('dlux.navbar.discover_sidebar_catalog', return_value=[]):
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

        with patch('dlux.navbar.discover_sidebar_catalog', return_value=catalog):
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

        with patch('dlux.navbar.discover_sidebar_catalog', return_value=catalog):
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

        with patch('dlux.navbar.discover_sidebar_catalog', return_value=catalog):
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

        with patch('dlux.navbar.discover_sidebar_catalog', return_value=catalog):
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

        with patch('dlux.navbar.discover_sidebar_catalog', return_value=catalog):
            crumbs = build_navbar_hierarchy_crumbs(request, config, 'en', {'navbar_root': 'Root'})

        self.assertEqual([crumb['label'] for crumb in crumbs], ['Root', 'Home'])
        self.assertFalse(crumbs[1]['clickable'])

    def test_navbar_hierarchy_wraps_dlux_routes_in_system_group(self):
        request = RequestFactory().get('/sys/options/')
        request.resolver_match = SimpleNamespace(view_name='dlux:options_view', url_name='options_view')
        catalog = [{
            'url_name': 'options_view',
            'label': 'Application Options',
            'url': '/sys/options/',
            'group_key': 'dlux',
        }]

        with patch('dlux.navbar.discover_sidebar_catalog', return_value=catalog):
            crumbs = build_navbar_hierarchy_crumbs(
                request,
                {'enabled': True, 'hierarchy': {'nodes': []}},
                'en',
                {'navbar_root': 'Root', 'navbar_system': 'System'},
            )

        self.assertEqual([crumb['label'] for crumb in crumbs], ['Root', 'System', 'Application Options'])
        self.assertFalse(crumbs[1]['clickable'])
        self.assertTrue(crumbs[2]['clickable'])

    def test_navbar_hierarchy_infers_dlux_link_parent_for_unplaced_system_route(self):
        request = RequestFactory().get('/sys/backup/')
        request.resolver_match = SimpleNamespace(
            view_name='dlux:system_backup_page',
            url_name='system_backup_page',
        )
        catalog = [
            {
                'url_name': 'options_view',
                'label': 'Application Options',
                'url': '/sys/options/',
                'group_key': 'dlux',
            },
            {
                'url_name': 'system_backup_page',
                'label': 'Backup & Restore',
                'url': '/sys/backup/',
                'group_key': 'dlux',
            },
        ]

        with patch('dlux.navbar.discover_sidebar_catalog', return_value=catalog):
            crumbs = build_navbar_hierarchy_crumbs(
                request,
                {'enabled': True, 'hierarchy': {'nodes': []}},
                'en',
                {'navbar_root': 'Root', 'navbar_system': 'System'},
            )

        self.assertEqual(
            [crumb['label'] for crumb in crumbs],
            ['Root', 'System', 'Application Options', 'Backup & Restore'],
        )
        self.assertFalse(crumbs[1]['clickable'])
        self.assertTrue(crumbs[2]['clickable'])

    def test_navbar_hierarchy_explicit_route_tree_overrides_inferred_dlux_parent(self):
        request = RequestFactory().get('/sys/backup/')
        request.resolver_match = SimpleNamespace(
            view_name='dlux:system_backup_page',
            url_name='system_backup_page',
        )
        config = {
            'enabled': True,
            'hierarchy': {
                'nodes': [{
                    'kind': 'manual',
                    'id': 'maintenance',
                    'labels': {'en': 'Maintenance'},
                    'children': [{
                        'kind': 'route',
                        'id': 'system_backup_page',
                        'url_name': 'system_backup_page',
                    }],
                }],
            },
        }
        catalog = [
            {
                'url_name': 'options_view',
                'label': 'Application Options',
                'url': '/sys/options/',
                'group_key': 'dlux',
            },
            {
                'url_name': 'system_backup_page',
                'label': 'Backup & Restore',
                'url': '/sys/backup/',
                'group_key': 'dlux',
            },
        ]

        with patch('dlux.navbar.discover_sidebar_catalog', return_value=catalog):
            crumbs = build_navbar_hierarchy_crumbs(
                request,
                config,
                'en',
                {'navbar_root': 'Root', 'navbar_system': 'System'},
            )

        self.assertEqual(
            [crumb['label'] for crumb in crumbs],
            ['Root', 'System', 'Maintenance', 'Backup & Restore'],
        )
        self.assertNotIn('Application Options', [crumb['label'] for crumb in crumbs])

    def test_navbar_frontend_uses_language_aware_history_and_allows_system_routes_in_builder(self):
        navbar_js = Path('dlux/static/dlux/main/js/navbar.js').read_text(encoding='utf-8')
        setup_js = Path('dlux/static/dlux/main/js/system_setup.js').read_text(encoding='utf-8')

        self.assertIn("const HISTORY_KEY = 'dlux.navbar.history.v1';", navbar_js)
        self.assertIn('labels[language] = label;', navbar_js)
        self.assertIn('labelsByPath[normalizedPath(entry.path)]', navbar_js)
        self.assertIn('trail.replaceChildren(fragment);', navbar_js)
        self.assertIn("entry.kind === 'item' && entry.url_name", setup_js)
        self.assertNotIn("entry.kind === 'item' && entry.url_name && !entry.is_system", setup_js)
        self.assertNotIn('crumb.clickable && crumb.url && !isCurrent', navbar_js)

    def test_unconfigured_root_url_redirects_anonymous_to_login(self):
        response = Client().get('/')

        self.assertRedirects(
            response,
            '/accounts/login/',
            fetch_redirect_response=False,
        )

    def test_unconfigured_root_url_redirects_superuser_to_system_setup(self):
        user_model = get_user_model()
        user = user_model.objects.create_superuser(
            username='setup-admin',
            email='setup-admin@example.com',
            password='adminpass123',
        )
        client = Client()
        client.force_login(user)

        response = client.get('/')

        self.assertRedirects(
            response,
            '/sys/setup/',
            fetch_redirect_response=False,
        )

    @override_settings(DLUX_CONFIG={'is_configured': True, 'home_url': '/dashboard/', 'public_root': True})
    def test_configured_root_url_redirects_to_home_url(self):
        response = Client().get('/')

        self.assertRedirects(
            response,
            '/dashboard/',
            fetch_redirect_response=False,
        )

    @override_settings(DLUX_CONFIG={'is_configured': True, 'home_url': '/dashboard/', 'public_root': False})
    def test_configured_root_url_redirects_anonymous_to_login(self):
        response = Client().get('/')

        self.assertRedirects(
            response,
            '/accounts/login/',
            fetch_redirect_response=False,
        )

    @override_settings(ROOT_URLCONF='dlux.tests.urls_with_root_index')
    def test_unconfigured_existing_project_root_requires_login_before_dev_view(self):
        clear_url_caches()
        response = Client().get('/')

        self.assertRedirects(
            response,
            '/accounts/login/',
            fetch_redirect_response=False,
        )

    @override_settings(ROOT_URLCONF='dlux.tests.urls_with_root_index', DLUX_CONFIG={'is_configured': True})
    def test_configured_existing_project_root_view_is_not_hijacked(self):
        clear_url_caches()
        response = Client().get('/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'project index')

    @override_settings(ROOT_URLCONF='dlux.tests.urls_with_prefix_mount', DLUX_CONFIG={'is_configured': True, 'home_url': '/dashboard/', 'public_root': True})
    def test_prefix_mount_still_redirects_unclaimed_root(self):
        clear_url_caches()
        response = Client().get('/')

        self.assertRedirects(
            response,
            '/dashboard/',
            fetch_redirect_response=False,
        )

    @override_settings(DLUX_CONFIG={})
    def test_setup_form_replaces_legacy_sys_home_url_for_unconfigured_instance(self):
        form = SystemSettingsForm(
            instance=SystemSettings(home_url=_LEGACY_HOME_URL, is_configured=False),
        )

        self.assertEqual(form.initial['home_url'], DEFAULT_HOME_URL)

    @override_settings(DLUX_CONFIG={
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

    @override_settings(DLUX_CONFIG={
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
            'buttons_shape': 'square',
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
        # Legacy titlebar hide=True migrates (inverted) to show_titlebar_on_public=False.
        self.assertFalse(form.initial['show_titlebar_on_public'])
        self.assertEqual(form.initial['titlebar_home_shape'], 'square')
        self.assertEqual(form.initial['titlebar_title_align'], 'center')
        self.assertEqual(form.initial['titlebar_title_size'], 'lg')
        self.assertEqual(form.initial['titlebar_height'], 'roomy')
        self.assertEqual(form.initial['titlebar_surface'], 'glass')
        self.assertEqual(form.initial['titlebar_logo_treatment'], 'plate')
        self.assertEqual(form.initial['titlebar_logo_treatment_shape'], 'pill')

    @override_settings(DLUX_CONFIG={
        'titlebar': {
            'user_hub_style': 'titlebar_actions',
            'actions_order': ['auth', 'settings', 'home', 'bogus', 'auth'],
        },
    })
    def test_setup_form_surfaces_titlebar_user_hub_style_and_order_builder(self):
        form = SystemSettingsForm(
            instance=SystemSettings(is_configured=False),
        )

        self.assertEqual(form.initial['titlebar_user_hub_style'], 'titlebar_actions')
        self.assertEqual(
            json.loads(form.initial['titlebar_actions_order'])[:3],
            ['auth', 'settings', 'home'],
        )
        self.assertIn('data-titlebar-actions-order-builder', form.titlebar_actions_order_html)
        self.assertIn("data-action-key='auth'", form.titlebar_actions_order_html)
        self.assertIn('id="id_titlebar_user_hub_style"', str(form['titlebar_user_hub_style']))
        self.assertIn('data-dlux-selector-variant="toggle"', str(form['titlebar_user_hub_style']))

    @override_settings(DLUX_CONFIG={
        'titlebar': {
            'show_title': False,
        },
    })
    def test_setup_form_surfaces_titlebar_toggle_widgets_and_step_three(self):
        request = RequestFactory().get('/sys/modals/dlux/systemsettings/1/?step=2')
        form = SystemSettingsForm(
            instance=SystemSettings(is_configured=False),
            request=request,
        )

        self.assertTrue(form.single_step_mode)
        self.assertEqual(form.single_step_index, 2)
        self.assertFalse(form.initial['titlebar_show_title'])
        self.assertIn('data-dlux-selector-variant="toggle"', str(form['default_table_density']))
        self.assertIn('lang-option', str(form['default_table_density']))
        self.assertIn('data-dlux-selector-variant="toggle"', str(form['sidebar_density']))
        self.assertIn('dlux-choice-option', str(form['sidebar_collapse_mode']))
        self.assertIn('lang-option', str(form['sidebar_collapse_mode']))
        self.assertIn('dlux-choice-option', str(form['titlebar_title_align']))
        self.assertIn('data-dlux-selector-variant="toggle"', str(form['titlebar_title_align']))
        self.assertIn('dlux-choice-option', str(form['titlebar_surface']))
        self.assertIn('<select', str(form['home_url_discovered']))
        self.assertIn('<select', str(form['public_root_url_discovered']))
        self.assertNotIn('data-dlux-selector-search', str(form['home_url_discovered']))

    def test_setup_theme_picker_keeps_allow_checkboxes_separate_from_default_selector(self):
        form = SystemSettingsForm(
            instance=SystemSettings(is_configured=False),
            mode='setup',
        )

        self.assertIn('data-setup-theme-choice="light"', form.theme_picker_html)
        self.assertIn(
            'data-setup-theme-preview-url="/static/dlux/themes/css/light.css?v=',
            form.theme_picker_html,
        )
        self.assertIn('data-setup-theme-allow-toggle="light"', form.theme_picker_html)
        self.assertIn('dlux-theme-settings-option__preview', form.theme_picker_html)
        self.assertIn('aria-pressed="true"', form.theme_picker_html)
        self.assertIn('aria-label="Default Theme: Light"', form.theme_picker_html)
        self.assertIn('data-setup-theme-allowed="light"', form.theme_picker_html)
        self.assertIn('data-setup-theme-allowed-control', form.theme_picker_html)
        self.assertIn('dlux-theme-settings-option__checkbox', form.theme_picker_html)
        self.assertNotIn('dlux-choice-option__copy', form.theme_picker_html)
        self.assertNotIn('dlux-choice-option__label', form.theme_picker_html)
        self.assertNotIn('dlux-choice-option__meta', form.theme_picker_html)
        self.assertNotIn('dlux-theme-settings-option__default-indicator', form.theme_picker_html)
        self.assertNotIn('bi-check2-circle', form.theme_picker_html)

    @override_settings(DLUX_CONFIG={'system_names': {'en': 'Demo System', 'ar': 'نظام تجريبي'}})
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
        self.assertIn('data-translation-group-tab="dlux"', html)
        self.assertNotIn('data-setup-language-picker', html)

    def test_setup_identity_step_uses_dlux_file_widget_for_import_logo_and_favicon(self):
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
            'format': 'django-lux.system-settings',
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
                'translations_override': {'fr': {'app_dlux': 'Systeme'}},
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
                    'user_hub_style': 'titlebar_actions',
                    'actions_order': ['auth', 'settings', 'home', 'missing'],
                },
            },
        }
        import_file = SimpleUploadedFile(
            'dlux-system-settings.json',
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
        self.assertEqual(form.cleaned_data['titlebar_config']['user_hub_style'], 'titlebar_actions')
        self.assertEqual(form.cleaned_data['titlebar_config']['actions_order'][:3], ['auth', 'settings', 'home'])
        self.assertNotIn('missing', form.cleaned_data['titlebar_config']['actions_order'])

    def test_setup_form_import_restores_email_config_and_sidebar_enabled_flag(self):
        payload = {
            'format': 'django-lux.system-settings',
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
            'dlux-system-settings.json',
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
            'format': 'django-lux.system-settings',
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
            'dlux-system-settings.json',
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
            'format': 'django-lux.system-settings',
            'version': 1,
            'settings': {
                'system_names': {'en': 'Imported System'},
                'default_language': 'fr',
                'default_theme': 'dark',
            },
        }
        import_file = SimpleUploadedFile(
            'dlux-system-settings.json',
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

        self.assertIn('dlux-choice-selector--toggle', html)
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

        self.assertIn("data-dlux-settings-toggle-field='allow_user_language_override'", html)
        self.assertIn("data-dlux-settings-toggle-field='public_root'", html)
        self.assertIn("data-dlux-settings-toggle-field='sidebar_enabled'", html)
        self.assertIn("data-dlux-settings-toggle-field='sidebar_enable_toolbar'", html)
        self.assertIn("data-dlux-settings-toggle-field='allow_user_theme_override'", html)
        self.assertIn("data-dlux-settings-toggle-field='titlebar_show_title'", html)
        self.assertIn("data-dlux-settings-toggle-field='public_root_split_enabled'", html)
        self.assertIn("data-dlux-settings-toggle-field='show_titlebar_on_public'", html)
        self.assertIn("data-dlux-settings-toggle-field='show_sidebar_on_public'", html)
        self.assertIn("data-dlux-settings-toggle-field='honeypot_enabled'", html)
        self.assertIn("data-dlux-settings-toggle-field='sticky_table_headers'", html)
        self.assertIn("data-dlux-settings-toggle-field='zebra_striping'", html)
        self.assertIn("data-dlux-email-toggle-field='email_config_use_tls'", html)
        self.assertIn("data-dlux-email-toggle-field='email_config_use_ssl'", html)
        self.assertNotIn("data-dlux-settings-toggle-field='email_config_use_tls'", html)
        self.assertNotIn("data-dlux-settings-toggle-field='email_config_use_ssl'", html)
        self.assertIn('data-dlux-settings-toggle-field=\'allow_user_language_override\'', html)
        self.assertIn('class="row mb-3"', html)
        self.assertIn('class="row g-3 mb-3"', html)
        self.assertIn('data-dlux-settings-toggle-field=\'titlebar_show_home_button\'', html)
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

        self.assertIn('dlux-public-root-dependent', html)
        self.assertIn('dlux-public-root-split-dependent', html)
        self.assertIn('d-none', html)
        self.assertIn('data-public-root-dependent="true"', html)
        self.assertIn('data-public-root-split-dependent="true"', html)

    @override_settings(DLUX_CONFIG={
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
        dependent_class_start = html.index('dlux-public-root-split-dependent')
        dependent_class_end = html.index('>', dependent_class_start)

        self.assertIn('data-dlux-settings-toggle-field=\'public_root_split_enabled\'', html)
        self.assertIn('dlux-public-root-split-dependent', html)
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

        with patch('dlux.forms.get_strings', return_value=translated_strings):
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

    def test_form_save_persists_new_layout_and_public_root_keys(self):
        form = SystemSettingsForm(
            data={
                'system_names': '{"en": "System", "ar": "System"}',
                'home_url': '/dashboard/',
                'default_language': 'en',
                'default_theme': 'light',
                'allowed_themes': ['light'],
                'default_table_density': 'balanced',
                'default_form_density': 'dense',
                'default_modal_size': 'compact',
                # sticky/zebra/honeypot omitted on a full form == toggled off
                'languages': '{}',
                'translations_override': '{}',
                'public_root': 'on',
                'public_root_theme': 'dark',
                'public_root_title': 'Welcome',
                'public_root_meta_description': 'Hello there',
                'show_titlebar_on_public': 'on',
                'show_sidebar_on_public': 'on',
                'sidebar_config': '{"entries":[]}',
            },
            instance=SystemSettings(is_configured=True),
        )

        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save(commit=False)
        self.assertEqual(saved.default_form_density, 'dense')
        self.assertEqual(saved.default_modal_size, 'compact')
        self.assertFalse(saved.sticky_table_headers)
        self.assertFalse(saved.zebra_striping)
        self.assertEqual(saved.public_root_theme, 'dark')
        self.assertEqual(saved.public_root_title, 'Welcome')
        self.assertEqual(saved.public_root_meta_description, 'Hello there')
        self.assertTrue(saved.show_titlebar_on_public)
        self.assertTrue(saved.show_sidebar_on_public)
        self.assertFalse(saved.honeypot_enabled)

    def test_single_step_save_preserves_layout_keys_from_other_step(self):
        request = RequestFactory().get('/sys/modals/dlux/systemsettings/1/?step=2')
        form = SystemSettingsForm(
            data={
                'system_names': '{"en": "System", "ar": "System"}',
                'home_url': '/dashboard/',
                'default_language': 'en',
                'default_theme': 'light',
                'allowed_themes': ['light'],
                'languages': '{}',
                'translations_override': '{}',
                'sidebar_config': '{"entries":[]}',
            },
            instance=SystemSettings(
                is_configured=True,
                layout_config={
                    'default_table_density': 'balanced',
                    'default_form_density': 'roomy',
                    'default_modal_size': 'wide',
                    'sticky_table_headers': False,
                    'zebra_striping': False,
                    'footer_enabled': True,
                },
            ),
            request=request,
        )

        self.assertTrue(form.single_step_mode)
        self.assertEqual(form.single_step_index, 2)
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save(commit=False)
        # A Security-step (index 2) save must not wipe Themes-step (index 8) layout keys.
        self.assertEqual(saved.default_form_density, 'roomy')
        self.assertEqual(saved.default_modal_size, 'wide')
        self.assertFalse(saved.sticky_table_headers)
        self.assertFalse(saved.zebra_striping)

    def test_public_root_setup_js_uses_single_form_scoped_controller(self):
        script = (
            Path(__file__).resolve().parents[1]
            / 'static'
            / 'dlux'
            / 'main'
            / 'js'
            / 'system_setup.js'
        ).read_text(encoding='utf-8')

        self.assertIn("target.name !== 'public_root'", script)
        self.assertIn("splitToggle.checked = false", script)
        self.assertIn("setNamedFieldDisabled(form, 'public_root_split_enabled'", script)
        self.assertNotIn("#id_public_root, #id_public_root_split_enabled", script)

    @override_settings(DLUX_CONFIG={
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

        context = dlux_context(request)

        self.assertTrue(context['hide_titlebar_for_public_index'])

    @override_settings(DLUX_CONFIG={
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

        context = {'request': request, **dlux_context(request)}
        html = Template("{% extends 'dlux/base.html' %}{% block content %}Public{% endblock %}").render(Context(context))

        self.assertTrue(context['hide_titlebar_for_public_index'])
        self.assertNotIn('class="titlebar shadow-sm no-print"', html)

    @override_settings(DLUX_CONFIG={
        'is_configured': True,
        'public_root': True,
        'home_url': '/public-home/',
        'public_root_theme': 'dark',
        'public_root_title': 'Public Landing',
        'public_root_meta_description': 'A public landing page.',
        'show_titlebar_on_public': True,
        'show_sidebar_on_public': True,
    })
    def test_context_applies_public_root_overrides_for_anonymous_index(self):
        request = RequestFactory().get('/public-home/')
        request.user = AnonymousUser()
        request.session = {}
        request.resolver_match = SimpleNamespace(url_name='public_home')

        context = dlux_context(request)

        self.assertTrue(context['dlux_is_public_index'])
        # show_titlebar_on_public=True -> titlebar not hidden.
        self.assertFalse(context['hide_titlebar_for_public_index'])
        # show_sidebar_on_public=True -> sidebar rendered for the anonymous visitor.
        self.assertTrue(context['dlux_show_sidebar'])
        # Public theme override forces the configured theme for the visitor.
        self.assertEqual(context['user_preferences'].get('theme'), 'dark')
        self.assertEqual(context['APP_CONFIG']['security']['public_root_title'], 'Public Landing')
        self.assertEqual(
            context['APP_CONFIG']['security']['public_root_meta_description'],
            'A public landing page.',
        )

    def test_setup_form_hides_public_registration_dependents_until_enabled(self):
        form = SystemSettingsForm(
            instance=SystemSettings(is_configured=False, public_registration_enabled=False),
            mode='setup',
        )

        html = Template('{% load crispy_forms_tags %}{% crispy form %}').render(Context({'form': form}))

        self.assertIn('dlux-public-registration-dependent d-none', html)
        self.assertIn('data-public-registration-dependent="true"', html)
        self.assertIn('aria-hidden="true"', html)
        self.assertIn('data-dlux-settings-toggle-field=\'public_registration_enabled\'', html)
        self.assertIn('class="col-lg-12" > <div class=\'dlux-settings-toggle-field', html)

    def test_setup_form_shows_public_registration_dependents_when_enabled(self):
        form = SystemSettingsForm(
            instance=SystemSettings(is_configured=False, public_registration_enabled=True),
            mode='setup',
        )

        html = Template('{% load crispy_forms_tags %}{% crispy form %}').render(Context({'form': form}))
        dependent_class_start = html.index('dlux-public-registration-dependent')
        dependent_class_end = html.index('>', dependent_class_start)

        self.assertNotIn('d-none', html[dependent_class_start:dependent_class_end])
        self.assertIn('aria-hidden="false"', html[dependent_class_start:dependent_class_end])
        self.assertIn('class="col-lg-6 dlux-public-registration-dependent"', html)

    @override_settings(DLUX_CONFIG={})
    def test_setup_wizard_actions_align_to_direction_end_in_ltr(self):
        form = SystemSettingsForm(
            instance=SystemSettings(is_configured=False),
            mode='setup',
        )

        html = Template('{% load crispy_forms_tags %}{% crispy form %}').render(Context({'form': form}))

        self.assertIn('dlux-setup-wizard-actions', html)
        self.assertIn("dir='ltr'", html)
        self.assertIn('justify-content-end', html)
        self.assertNotIn('justify-content-between align-items-center gap-2 mt-4', html)

    @override_settings(DLUX_CONFIG={'default_language': 'ar'})
    def test_setup_wizard_actions_align_to_direction_end_in_rtl(self):
        form = SystemSettingsForm(
            instance=SystemSettings(is_configured=False, default_language='ar'),
            mode='setup',
        )

        html = Template('{% load crispy_forms_tags %}{% crispy form %}').render(Context({'form': form}))

        self.assertIn('dlux-setup-wizard-actions', html)
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

        self.assertIn('dlux-email-config-password-field d-none', html)

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
        password_class_start = html.index('dlux-email-config-password-field')
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

    def test_setup_form_schema_covers_simple_config_field_names(self):
        from dlux.system.registry import get_setting_group

        form = SystemSettingsForm(
            instance=SystemSettings(is_configured=False),
            mode='setup',
        )

        for storage_field in SystemSettingsForm._SCHEMA_SIMPLE_CONFIG_GROUPS:
            for field_schema in get_setting_group(storage_field).fields:
                self.assertIn(field_schema.form_name, form.fields)

    def test_setup_form_schema_packs_simple_config_groups(self):
        from dlux.system.normalizers import normalize_auth_config, normalize_client_ip_config

        form = SystemSettingsForm(
            instance=SystemSettings(is_configured=False),
            mode='setup',
        )
        form.cleaned_data = {
            'email_2fa': True,
            'prevent_multiple_active_sessions': True,
            'login_lockout_enabled': False,
            'enforce_strong_passwords': True,
            'client_ip_mode': 'custom',
            'client_ip_trusted_proxy_hops': 4,
            'client_ip_custom_header': 'CF-Connecting-IP',
        }

        self.assertEqual(
            form._schema_group_from_cleaned('auth_config'),
            normalize_auth_config({
                'email_2fa': True,
                'prevent_multiple_active_sessions': True,
                'login_lockout_enabled': False,
                'enforce_strong_passwords': True,
            }),
        )
        self.assertEqual(
            form._schema_group_from_cleaned('client_ip_config'),
            normalize_client_ip_config({
                'mode': 'custom',
                'trusted_proxy_hops': 4,
                'custom_header': 'CF-Connecting-IP',
            }),
        )

    def test_setup_form_saves_enforce_strong_passwords_to_auth_config(self):
        form = SystemSettingsForm(
            data={
                'home_url': DEFAULT_HOME_URL,
                'default_language': 'en',
                'default_theme': 'light',
                'allowed_themes': ['light'],
                'default_table_density': DEFAULT_TABLE_DENSITY,
                'login_lockout_enabled': 'on',
                'enforce_strong_passwords': 'on',
            },
            instance=SystemSettings(is_configured=False),
            mode='setup',
        )

        self.assertTrue(form.is_valid(), form.errors)
        instance = form.save(commit=False)

        self.assertTrue(instance.auth_config['login_lockout_enabled'])
        self.assertTrue(instance.auth_config['enforce_strong_passwords'])

    def test_system_setup_js_toggles_email_password_and_keeps_default_language_save_only(self):
        script = Path(__file__).resolve().parents[1] / 'static' / 'dlux' / 'main' / 'js' / 'system_setup.js'
        contents = script.read_text(encoding='utf-8')

        self.assertIn('dlux-email-config-password-field', contents)
        self.assertIn("secretStorageInput.value === 'encrypted_db'", contents)
        self.assertNotIn('previewSetupDefaultLanguage', contents)
        self.assertNotIn('__language_preview', contents)
        self.assertNotIn('window.setLanguage', contents)
        self.assertNotIn('function getLockedDefaultLanguage(form) {', contents)
        self.assertNotIn('function enforceDefaultLanguageLock(form) {', contents)
        self.assertNotIn('defaultInput.disabled = true;', contents)
        self.assertNotIn('aria-disabled="true"', contents)
        self.assertIn('function applySetupFormStateValues(form, values, options) {', contents)
        self.assertIn('function finalizeSetupFormStateRestore(root) {', contents)
        self.assertIn('function readSetupWizardCurrentStep(form) {', contents)
        self.assertIn('function rememberSetupWizardStep(form, step) {', contents)
        self.assertIn('state.currentStep = currentStep;', contents)
        self.assertIn('form.dataset.dluxWizardInitialStep = String(Number(state.currentStep));', contents)
        self.assertIn('form.__dluxPendingSetupState = state;', contents)
        self.assertIn('const fieldsByName = new Map();', contents)
        self.assertIn("state.values[name] = fields\n                        .filter((field) => field.checked)\n                        .map((field) => field.value);", contents)
        self.assertIn('if (Array.isArray(value)) {', contents)
        self.assertIn('const allowedValues = value.map((item) => String(item));', contents)
        self.assertIn('field.checked = allowedValues.includes(String(field.value));', contents)
        self.assertIn('const fieldsToDispatch = [];', contents)
        self.assertIn('fieldsToDispatch.forEach(({ field, input, change }) => {', contents)
        self.assertIn('applySetupFormStateValues(form, state.values, { dispatchEvents: true });', contents)
        self.assertIn('syncSetupLanguagePickers(form);', contents)
        self.assertIn('syncTranslationOverrides(form);', contents)
        self.assertIn('applyImmediateSystemSettingsPreview(form);', contents)
        self.assertIn('delete form.__dluxPendingSetupState;', contents)
        self.assertIn('rehydrateSetupLanguageEditors(form)', contents)
        self.assertIn('restoreImportedEmailPasswordNotice(form);', contents)
        self.assertGreaterEqual(contents.count('restoreImportedEmailPasswordNotice(form);'), 2)
        self.assertIn('function restoreImportedEmailPasswordNotice(form) {', contents)
        self.assertIn('sessionStorage.removeItem(getSetupStateKey(form));', contents)
        self.assertIn("notice.setAttribute('data-autoclose', 'false');", contents)
        self.assertNotIn('suppressSetupLanguagePreview', contents)
        self.assertIn('window.__dluxGetWizardInitialStep = function (container) {', contents)
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
        # The setup viewport is a plain flow box; it must NOT measure the titlebar
        # height into a CSS var (that measurement shoved the shell up behind the
        # titlebar on every preview change). The wizard action bar is relocated into
        # the fixed footer instead.
        self.assertIn("function initSetupFooterRelocation(root)", contents)
        self.assertIn("footer.appendChild(actions)", contents)
        self.assertNotIn("getBoundingClientRect().height", contents)
        self.assertNotIn("--dlux-setup-titlebar-offset", contents)
        self.assertNotIn("emailConfig.password_configured === true", contents)
        self.assertNotIn("const needsEncryptedDbPassword = emailConfig.secret_storage === 'encrypted_db'", contents)
        self.assertIn('window.__dluxPrepareWizardContainer = function (container) {', contents)
        self.assertIn('scan(document);', contents)
        self.assertLess(contents.index('restoreSetupFormState(root);'), contents.index('finalizeSetupFormStateRestore(root);'))
        self.assertNotIn('dlux-setup-language-switch-pending', contents)
        self.assertNotIn('function setupDefaultLanguageWillSwitch(language) {', contents)
        self.assertIn("'allow_user_font_override'", contents)
        self.assertIn('applyImportedFontSettings(form, settings);', contents)
        self.assertIn("hiddenInput.addEventListener('change', () => {", contents)
        self.assertIn('function applyImportedSidebarSettings(form, sidebar) {', contents)
        self.assertIn("builder.dispatchEvent(new CustomEvent('dlux:sidebar-config-imported'", contents)
        self.assertIn("builder.addEventListener('dlux:sidebar-config-imported'", contents)
        self.assertIn('const sidebarSource = settings.sidebar_config || settings.sidebar;', contents)
        self.assertIn('const translationOverrides = settings.translations_override || settings.translations;', contents)
        self.assertIn('const navbarSource = settings.navbar_config || settings.navbar;', contents)
        self.assertIn('const titlebarSource = settings.titlebar_config || settings.titlebar;', contents)
        self.assertIn("setNamedFieldValue(form, 'titlebar_user_hub_style', titlebar.user_hub_style === 'titlebar_actions' ? 'titlebar_actions' : 'dropdown');", contents)
        self.assertIn("writeTitlebarActionsOrder(form, titlebar.actions_order || TITLEBAR_ACTIONS_DEFAULT_ORDER);", contents)
        self.assertIn('function normalizeTitlebarActionsOrder(value) {', contents)
        self.assertIn('function initTitlebarActionsOrderBuilder(form) {', contents)
        self.assertIn('titlebar.dataset.titlebarUserHubStyle = userHubStyle ===', contents)
        self.assertIn("document.querySelectorAll('#dlux-user-dropdown-card').forEach((card) => {", contents)
        self.assertIn("setNamedFieldValue(form, 'titlebar_logo_treatment', titlebar.logo_treatment || 'none');", contents)
        self.assertIn("setNamedFieldValue(form, 'titlebar_logo_treatment_shape', titlebar.logo_treatment_shape || 'soft');", contents)
        self.assertIn("setNamedFieldReadonly(form, 'titlebar_logo_treatment_shape', !showPlateShape);", contents)
        self.assertIn("form.querySelectorAll('.dlux-login-logo-treatment-primary').forEach((node) => {", contents)
        self.assertIn("node.classList.toggle('dlux-logo-treatment-primary--wide', !isPlate);", contents)
        self.assertIn("const showPlateShape = showLogo && logoTreatment === 'plate';", contents)
        self.assertIn("node.classList.toggle('dlux-logo-treatment-primary--wide', showLogo && !showPlateShape);", contents)
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
        self.assertIn("step.classList.toggle('dlux-setup-step-has-error', hasError);", contents)
        self.assertIn("navItem.classList.toggle('has-validation-error', hasError);", contents)
        self.assertIn("bullet.textContent = hasError ? '!' : bullet.dataset.dluxStepNumber;", contents)
        self.assertIn("form.addEventListener('invalid', syncSoon, true);", contents)
        self.assertIn('persistSetupFormState(form);', contents)
        self.assertIn("form.querySelectorAll('.dlux-btn-submit').forEach((button) => {", contents)
        self.assertIn('initSystemSetupStepValidation(root);', contents)

    def test_wizard_helper_reveals_server_hidden_steps(self):
        script = Path(__file__).resolve().parents[1] / 'static' / 'dlux' / 'helpers' / 'wizard' / 'js' / 'main.js'
        contents = script.read_text(encoding='utf-8')

        self.assertIn("step.classList.toggle('d-none', !isActive);", contents)
        self.assertIn("step.style.display = isActive ? '' : 'none';", contents)
        self.assertIn("step.setAttribute('aria-hidden', isActive ? 'false' : 'true');", contents)
        self.assertIn("button.classList.toggle('d-none', !isVisible);", contents)
        self.assertIn("button.style.display = isVisible ? '' : 'none';", contents)
        self.assertIn("button.setAttribute('aria-hidden', isVisible ? 'false' : 'true');", contents)
        self.assertIn('function prepareWizardContainer(container) {', contents)
        self.assertIn("typeof window.__dluxPrepareWizardContainer !== 'function'", contents)
        self.assertIn('prepareWizardContainer(container);', contents)
        self.assertLess(
            contents.index('prepareWizardContainer(container);'),
            contents.index("container.dataset.dluxWizardBound = 'true';"),
        )
        self.assertIn("container.querySelectorAll('[data-dlux-wizard-step-target]')", contents)
        self.assertIn("item.classList.toggle('is-active', isActive);", contents)
        self.assertIn("item.classList.toggle('is-complete', isComplete);", contents)
        self.assertIn("item.setAttribute('aria-current', isActive ? 'step' : 'false');", contents)
        self.assertIn("container.dispatchEvent(new CustomEvent('dlux:wizard-step-change'", contents)

    def test_user_hub_css_clamps_mobile_dropdown_to_viewport(self):
        stylesheet = Path(__file__).resolve().parents[1] / 'static' / 'dlux' / 'users' / 'css' / 'user_hub.css'
        contents = stylesheet.read_text(encoding='utf-8')

        self.assertIn('width: min(var(--dlux-dropdown-width), calc(100vw - (var(--dlux-dropdown-edge-gap) * 2)))', contents)
        self.assertIn('@media (max-width: 575.98px)', contents)
        self.assertIn('position: fixed', contents)
        self.assertIn('inset-inline: var(--dlux-dropdown-edge-gap)', contents)
        self.assertIn('overflow-y: auto', contents)
        self.assertIn('flex-wrap: wrap;', contents)
        self.assertIn('justify-content: center;', contents)
        self.assertIn('width: auto;', contents)

    def test_tutorial_uses_modal_user_trigger_on_manage_users(self):
        script = Path(__file__).resolve().parents[1] / 'static' / 'dlux' / 'tutorial' / 'js' / 'main.js'
        contents = script.read_text(encoding='utf-8')

        self.assertIn("button[data-dynamic-modal]", contents)
        self.assertNotIn('a[href*="create_user"]', contents)

    def test_permissions_css_hardens_staff_tier_preview_for_light_and_dark_themes(self):
        stylesheet = Path(__file__).resolve().parents[1] / 'static' / 'dlux' / 'users' / 'css' / 'permissions.css'
        contents = stylesheet.read_text(encoding='utf-8')

        self.assertIn('.dlux-staff-tier-preview .badge.bg-primary {', contents)
        self.assertIn('linear-gradient(135deg, #1d4ed8 0%, #2563eb 55%, #3b82f6 100%)', contents)
        self.assertIn(':root.theme-dark .dlux-staff-tier-preview,', contents)
        self.assertIn(':root.theme-gothic .dlux-staff-tier-preview,', contents)
        self.assertIn(':root.theme-neon .dlux-staff-tier-preview,', contents)
        self.assertIn(':root.theme-retro .dlux-staff-tier-preview,', contents)
        self.assertIn(':root.theme-prism .dlux-staff-tier-preview {', contents)

    def test_tables_css_hardens_staff_tier_badges_for_manage_users(self):
        stylesheet = Path(__file__).resolve().parents[1] / 'static' / 'dlux' / 'main' / 'css' / 'tables.css'
        contents = stylesheet.read_text(encoding='utf-8')

        self.assertIn('.dlux-staff-tier-badge--global_staff {', contents)
        self.assertIn('linear-gradient(135deg, #1d4ed8 0%, #2563eb 55%, #3b82f6 100%)', contents)
        self.assertIn('.dlux-staff-tier-badge--delegate {', contents)

    def test_user_detail_modal_uses_shared_staff_tier_badge_classes(self):
        template_path = Path(__file__).resolve().parents[1] / 'templates' / 'dlux' / 'users' / 'user_detail_modal.html'
        contents = template_path.read_text(encoding='utf-8')

        self.assertIn('dlux-staff-tier-badge--{{ target_user_management_tier.tier_key }}', contents)
        self.assertIn('dlux-staff-tier-badge--delegate', contents)
        self.assertNotIn('badge {{ target_user_management_tier.badge_classes }}', contents)

    def test_main_css_forces_readable_primary_badge_text(self):
        stylesheet = Path(__file__).resolve().parents[1] / 'static' / 'dlux' / 'main' / 'css' / 'main.css'
        contents = stylesheet.read_text(encoding='utf-8')

        self.assertIn('.badge.bg-primary,', contents)
        self.assertIn('.text-bg-primary,', contents)
        self.assertIn('.badge.text-bg-primary {', contents)
        self.assertIn('color: #fff !important;', contents)

    def test_titlebar_login_round_uses_shared_shape_and_theme_selectors(self):
        static_root = Path(__file__).resolve().parents[1] / 'static' / 'dlux'
        titlebar_css = (static_root / 'main' / 'css' / 'titlebar.css').read_text(encoding='utf-8')

        # All titlebar buttons (home/action/login/notification trigger) share the
        # `dlux-titlebar-btn` class, so base appearance + hover are styled once.
        self.assertIn('.titlebar .dlux-titlebar-btn {', titlebar_css)
        self.assertIn('.titlebar .dlux-titlebar-btn:hover,', titlebar_css)
        self.assertIn('.titlebar .dlux-titlebar-btn:focus-visible {', titlebar_css)
        # Shape variants stay per-class (home-shape applies to home/trigger/login, not actions).
        self.assertIn('.titlebar[data-titlebar-home-shape="square"] .dlux-login-round {', titlebar_css)
        self.assertIn('.titlebar[data-titlebar-home-shape="squircle"] .dlux-login-round {', titlebar_css)
        self.assertIn('.titlebar[data-titlebar-logo-treatment="plate"] .titlebar__logo {', titlebar_css)
        self.assertIn('.titlebar[data-titlebar-logo-treatment="halo"] .titlebar__logo {', titlebar_css)
        self.assertIn('.titlebar[data-titlebar-logo-treatment="contrast"] .titlebar__logo {', titlebar_css)
        self.assertIn('.titlebar[data-titlebar-logo-treatment="plate"][data-titlebar-logo-treatment-shape="pill"] .titlebar__logo {', titlebar_css)
        titlebar_template = Path(__file__).resolve().parents[1] / 'templates' / 'dlux' / 'includes' / 'titlebar.html'
        titlebar_markup = titlebar_template.read_text(encoding='utf-8')
        notifications_markup = (Path(__file__).resolve().parents[1] / 'templates' / 'dlux' / 'includes' / 'notifications.html').read_text(encoding='utf-8')
        self.assertIn('data-titlebar-logo-treatment="{{ titlebar.logo_treatment|default:\'none\' }}"', titlebar_markup)
        self.assertIn('data-titlebar-logo-treatment-shape="{{ titlebar.logo_treatment_shape|default:\'soft\' }}"', titlebar_markup)
        self.assertIn('data-titlebar-user-hub-style="{{ titlebar.user_hub_style|default:\'dropdown\' }}"', titlebar_markup)
        self.assertIn('data-titlebar-actions', titlebar_markup)
        self.assertIn('method="POST" action="{{ action.url }}"', titlebar_markup)
        self.assertIn('{% csrf_token %}', titlebar_markup)
        self.assertIn('data-titlebar-action-key="{{ action.key }}"', titlebar_markup)
        self.assertIn('.titlebar__actions--titlebar', titlebar_css)
        self.assertIn('.titlebar[data-titlebar-user-hub-style="titlebar_actions"] .titlebar__actions--dropdown', titlebar_css)
        self.assertIn('.titlebar__actions--titlebar {', titlebar_css)
        titlebar_surfaces_css = (static_root / 'main' / 'css' / 'titlebar_surfaces.css').read_text(encoding='utf-8')
        self.assertIn(':root .titlebar[data-titlebar-surface="muted"] {', titlebar_surfaces_css)
        self.assertIn(':root .titlebar[data-titlebar-surface="glass"] {', titlebar_surfaces_css)
        self.assertIn('background:', titlebar_surfaces_css)
        self.assertIn('!important;', titlebar_surfaces_css)
        self.assertIn('backdrop-filter: blur(16px) saturate(1.2) !important;', titlebar_surfaces_css)
        base_template = Path(__file__).resolve().parents[1] / 'templates' / 'dlux' / 'base.html'
        base_markup = base_template.read_text(encoding='utf-8')
        self.assertIn("user.is_authenticated and titlebar.user_hub_style != 'titlebar_actions'", base_markup)

        # Dark themes override the single shared button class (so the bell / action buttons
        # get the dark treatment too, not just home/login).
        self.assertIn('dlux-titlebar-btn dlux-notifications__trigger', notifications_markup)
        self.assertIn('dlux-titlebar-btn dlux-login-round', titlebar_markup)
        for theme_name in ('dark', 'gothic', 'retro', 'neon', 'prism', 'aether'):
            theme_css = (static_root / 'themes' / 'css' / f'{theme_name}.css').read_text(encoding='utf-8')
            self.assertIn('.titlebar .dlux-titlebar-btn {', theme_css)
            self.assertIn('.titlebar .dlux-titlebar-btn:hover,', theme_css)
            self.assertIn('.titlebar .dlux-titlebar-btn:focus-visible {', theme_css)
            self.assertNotIn('.titlebar .dlux-login-round {', theme_css)
            self.assertIn('.titlebar[data-titlebar-logo-treatment="plate"] .titlebar__logo {', theme_css)

    def test_neon_theme_excludes_options_panels_from_generic_option_section_overlays(self):
        stylesheet = Path(__file__).resolve().parents[1] / 'static' / 'dlux' / 'themes' / 'css' / 'neon.css'
        contents = stylesheet.read_text(encoding='utf-8')

        self.assertIn('.option-section:not(.dlux-options-panel):not([class*="text-bg-"]):not([class*="bg-"]),', contents)
        self.assertIn('.option-section:not(.dlux-options-panel)::before,', contents)
        self.assertIn('.option-section:not(.dlux-options-panel):hover::before,', contents)
        self.assertIn('.option-section:not(.dlux-options-panel),', contents)
        self.assertIn('.option-section:not(.dlux-options-panel) > *,', contents)

    def test_aether_sheen_reverses_at_endpoints_without_a_loop_jump(self):
        stylesheet = Path(__file__).resolve().parents[1] / 'static' / 'dlux' / 'themes' / 'css' / 'aether.css'
        contents = stylesheet.read_text(encoding='utf-8')

        self.assertIn(
            'animation: aetherSheen 12s cubic-bezier(0.4, 0, 0.2, 1) infinite alternate;',
            contents,
        )
        self.assertIn('0%, 18% {\n        background-position: -160% 0, 0 -20%;', contents)
        self.assertIn('100% {\n        background-position: 180% 0, 0 120%;', contents)

    def test_selector_css_adds_vertical_padding_for_toggle_card_grids(self):
        stylesheet = Path(__file__).resolve().parents[1] / 'static' / 'dlux' / 'main' / 'css' / 'selectors.css'
        contents = stylesheet.read_text(encoding='utf-8')

        self.assertIn('.dlux-choice-selector--toggle .dlux-choice-selector__options {', contents)
        self.assertIn('padding-block: 0.8rem;', contents)
        self.assertIn('align-self: stretch;', contents)
        self.assertIn('.dlux-choice-option {\n  display: block;\n  position: relative;', contents)
        self.assertIn('.dlux-choice-option__input {\n  position: absolute;\n  inset: 0;\n  width: 100%;\n  height: 100%;', contents)
        self.assertIn('--dlux-choice-toggle-surface:', contents)
        self.assertIn('background: var(--dlux-choice-toggle-surface);', contents)
        self.assertIn('background: var(--dlux-choice-toggle-surface-hover);', contents)
        self.assertIn('background: var(--dlux-choice-toggle-surface-active);', contents)
        self.assertNotIn('linear-gradient(180deg, rgba(255, 255, 255, 0.99)', contents)

    def test_system_setup_css_makes_shared_toggle_cards_reflow_inside_narrow_columns(self):
        stylesheet = Path(__file__).resolve().parents[1] / 'static' / 'dlux' / 'main' / 'css' / 'system_setup.css'
        contents = stylesheet.read_text(encoding='utf-8')

        self.assertIn('.dlux-settings-toggle-field {', contents)
        self.assertIn('container-type: inline-size was removed', contents)
        self.assertIn('.dlux-settings-toggle-field__content {', contents)
        self.assertIn('.dlux-settings-toggle-field__control {', contents)
        self.assertIn('.dlux-settings-toggle-field__control.form-switch {', contents)
        self.assertIn('.dlux-settings-toggle-field__input.form-check-input {', contents)
        self.assertIn('padding-inline-start: 0;', contents)
        self.assertIn('margin: 0;', contents)
        self.assertIn('float: none;', contents)
        self.assertIn('position: static;', contents)
        self.assertIn('overflow-wrap: break-word;', contents)
        self.assertIn('word-break: normal;', contents)
        self.assertIn('.dlux-logo-treatment-primary.dlux-logo-treatment-primary--wide {', contents)
        self.assertIn('flex: 0 0 100%;', contents)
        self.assertIn('width: 100%;', contents)
        self.assertIn('max-width: 100%;', contents)
        self.assertNotIn('overflow-wrap: anywhere;', contents)
        self.assertIn('@media (max-width: 400px)', contents)
        self.assertIn('flex-direction: column;', contents)
        self.assertIn('justify-content: flex-end;', contents)
        # The setup viewport is a plain flow box (same scaffold as #mainContent),
        # NOT a position:fixed overlay with a JS-measured top offset — that offset
        # collapsed to ~0 on preview changes and shoved the shell up behind the
        # titlebar. No `position: fixed`, no `top`, no measured-offset var.
        self.assertIn('height: calc(100vh - var(--header-height, 60px));', contents)
        self.assertIn('width: 100%;', contents)
        self.assertIn('max-width: none;', contents)
        self.assertNotIn('max-width: 1180px;', contents)
        self.assertNotIn('--dlux-setup-titlebar-offset', contents)
        self.assertNotIn('--dlux-setup-active-titlebar-height', contents)
        self.assertNotIn('position: fixed;', contents)
        self.assertIn('.dlux-setup-step-nav {', contents)
        self.assertIn('grid-template-columns: repeat(7, minmax(6.2rem, 1fr));', contents)
        self.assertIn('.dlux-setup-step-nav__item.is-active {', contents)
        self.assertIn('.dlux-setup-step-nav__item.is-complete {', contents)
        self.assertIn('backdrop-filter: blur(14px);', contents)
        self.assertIn('.dlux-theme-settings-option .dlux-choice-option__surface {', contents)
        self.assertIn('cursor: pointer;', contents)
        self.assertIn('.dlux-theme-settings-option__preview {', contents)
        self.assertIn('appearance: none;', contents)
        self.assertIn('background: transparent !important;', contents)
        self.assertIn('box-shadow: none !important;', contents)
        self.assertIn('justify-content: center;', contents)
        self.assertIn('.dlux-theme-settings-option.is-default .dlux-choice-option__surface {', contents)
        self.assertIn('.dlux-theme-settings-option.is-default .theme-preview.active {', contents)
        self.assertNotIn('.dlux-theme-settings-option .dlux-choice-option__copy', contents)
        self.assertNotIn('dlux-theme-settings-option__default-indicator', contents)

    def test_system_setup_css_defines_step_validation_warning_state(self):
        stylesheet = Path(__file__).resolve().parents[1] / 'static' / 'dlux' / 'main' / 'css' / 'system_setup.css'
        contents = stylesheet.read_text(encoding='utf-8')

        self.assertIn('.dlux-setup-step-nav__item.has-validation-error {', contents)
        self.assertIn('.dlux-setup-step-nav__item.has-validation-error .dlux-setup-step-nav__bullet {', contents)
        self.assertIn('.dlux-system-settings-shell.mode-setup .wizard-step.dlux-setup-step-has-error {', contents)
        self.assertIn('border-color: rgba(245, 158, 11, 0.72);', contents)
        self.assertIn('background: #f59e0b;', contents)
        self.assertNotIn('dlux-setup-language-switch-pending', contents)
        self.assertNotIn('visibility: hidden;', contents)

    def test_shared_toggle_helper_uses_neutral_switch_wrapper(self):
        form = SystemSettingsForm(
            instance=SystemSettings(is_configured=False),
            mode='setup',
        )

        html = Template('{% load crispy_forms_tags %}{% crispy form %}').render(Context({'form': form}))

        self.assertIn("dlux-settings-toggle-field__control form-switch", html)
        self.assertIn("form-check-input dlux-settings-toggle-field__input", html)
        self.assertNotIn("dlux-settings-toggle-field__control form-check form-switch", html)

    def test_logo_treatment_cards_start_full_width_without_plate_shape(self):
        form = SystemSettingsForm(
            instance=SystemSettings(is_configured=False),
            mode='setup',
        )

        html = Template('{% load crispy_forms_tags %}{% crispy form %}').render(Context({'form': form}))

        self.assertIn('dlux-logo-treatment-primary', html)
        self.assertIn('dlux-login-logo-treatment-primary', html)
        self.assertIn('dlux-titlebar-logo-treatment-primary', html)
        self.assertIn('dlux-logo-treatment-primary--wide', html)
        self.assertIn('data-login-plate-shape', html)
        self.assertIn('dlux-titlebar-logo-plate-dependent d-none', html)

    def test_setup_email_tls_ssl_use_dedicated_email_toggle_markup(self):
        form = SystemSettingsForm(
            instance=SystemSettings(is_configured=False),
            mode='setup',
        )

        html = Template('{% load crispy_forms_tags %}{% crispy form %}').render(Context({'form': form}))

        self.assertIn("data-dlux-email-toggle-field='email_config_use_tls'", html)
        self.assertIn("data-dlux-email-toggle-field='email_config_use_ssl'", html)
        self.assertIn('dlux-email-toggle-field__input', html)

    def test_system_setup_css_defines_dedicated_email_toggle_layout(self):
        stylesheet = Path(__file__).resolve().parents[1] / 'static' / 'dlux' / 'main' / 'css' / 'system_setup.css'
        contents = stylesheet.read_text(encoding='utf-8')

        self.assertIn('.dlux-email-toggle-field {', contents)
        self.assertIn('.dlux-email-toggle-field__row {', contents)
        self.assertIn('.dlux-email-toggle-field__label {', contents)
        self.assertIn('.dlux-email-toggle-field__input.form-check-input {', contents)

    def test_shared_switch_css_uses_pointer_for_enabled_toggle_inputs(self):
        stylesheet = Path(__file__).resolve().parents[1] / 'static' / 'dlux' / 'main' / 'css' / 'main.css'
        contents = stylesheet.read_text(encoding='utf-8')

        self.assertIn('.form-switch .form-check-input:not(:disabled) {', contents)
        self.assertIn('cursor: pointer;', contents)

    def test_options_template_uses_external_assets_and_draggable_cards(self):
        template_path = Path(__file__).resolve().parents[1] / 'templates' / 'dlux' / 'includes' / 'options.html'
        contents = template_path.read_text(encoding='utf-8')

        self.assertIn("dlux/main/css/options.css", contents)
        self.assertIn("dlux/main/js/options.js", contents)
        _assert_versioned_static_asset(self, contents, "dlux/main/css/options.css")
        _assert_versioned_static_asset(self, contents, "dlux/main/js/options.js")
        self.assertIn('{{ server_time_backend_display }}', contents)
        self.assertIn('id="dluxOptionsGrid"', contents)
        self.assertIn('dlux-admin-panel-card', contents)
        self.assertIn('dlux-admin-tile--status', contents)
        self.assertIn('data-options-card="autofill"', contents)
        self.assertIn('dlux-options-reset-footer', contents)
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
        self.assertIn('DLUX_STRINGS.system_settings_security', contents)
        self.assertNotIn("default:'Access & Security'", contents)

    def test_base_template_versions_shared_main_stylesheet(self):
        template_path = Path(__file__).resolve().parents[1] / 'templates' / 'dlux' / 'base.html'
        contents = template_path.read_text(encoding='utf-8')

        self.assertIn("dlux/main/css/main.css", contents)
        _assert_versioned_static_asset(self, contents, "dlux/main/css/main.css")
        self.assertIn("dlux/main/css/system_setup.css", contents)
        _assert_versioned_static_asset(self, contents, "dlux/main/css/system_setup.css")
        self.assertIn("dlux_static 'dlux/main/css/system_setup.css'", contents)
        self.assertIn("dlux/main/css/titlebar_surfaces.css", contents)
        _assert_versioned_static_asset(self, contents, "dlux/main/css/titlebar_surfaces.css")
        self.assertLess(
            contents.index("{% dlux_static theme.css_path %}"),
            contents.index("dlux/main/css/titlebar_surfaces.css"),
        )
        self.assertIn("dlux/main/js/system_setup.js", contents)
        _assert_versioned_static_asset(self, contents, "dlux/main/js/system_setup.js")
        self.assertIn("dlux_static 'dlux/main/js/system_setup.js'", contents)
        self.assertIn("dlux_static 'dlux/helpers/prevent_double_submit.js'", contents)
        _assert_versioned_static_asset(self, contents, "dlux/helpers/prevent_double_submit.js")
        self.assertIn("dlux/helpers/wizard/js/main.js", contents)
        self.assertLess(
            contents.index("dlux/main/js/system_setup.js"),
            contents.index("dlux/helpers/wizard/js/main.js"),
        )
        # Every versioned asset now goes through {% dlux_static %} (?v=<version>).
        self.assertGreaterEqual(contents.count("{% dlux_static"), 20)
        self.assertIn("dlux/main/js/navbar.js", contents)
        _assert_versioned_static_asset(self, contents, "dlux/main/js/navbar.js")
        self.assertIn("dlux/main/css/navbar.css", contents)
        _assert_versioned_static_asset(self, contents, "dlux/main/css/navbar.css")
        self.assertIn("{% dlux_static theme.css_path %}", contents)
        self.assertIn("dlux/main/css/template_cleanup.css", contents)
        _assert_versioned_static_asset(self, contents, "dlux/main/css/template_cleanup.css")

    def test_system_setup_hides_sidebar_toggle_but_keeps_titlebar(self):
        titlebar_template = Path(__file__).resolve().parents[1] / 'templates' / 'dlux' / 'includes' / 'titlebar.html'
        setup_template = Path(__file__).resolve().parents[1] / 'templates' / 'dlux' / 'includes' / 'system_setup.html'
        view_source = Path(__file__).resolve().parents[1] / 'views' / 'general.py'

        titlebar_contents = titlebar_template.read_text(encoding='utf-8')
        setup_contents = setup_template.read_text(encoding='utf-8')
        view_contents = view_source.read_text(encoding='utf-8')

        self.assertIn('and not hide_sidebar_toggle', titlebar_contents)
        self.assertIn('id="sidebarToggle"', titlebar_contents)
        self.assertIn("'hide_sidebar_toggle': True,", view_contents)
        self.assertIn("dlux_static 'dlux/main/css/system_setup.css'", setup_contents)
        self.assertLess(
            setup_contents.index('dlux-setup-intro__text'),
            setup_contents.index('dlux-setup-page-logo'),
        )

        stylesheet = Path(__file__).resolve().parents[1] / 'static' / 'dlux' / 'main' / 'css' / 'system_setup.css'
        stylesheet_contents = stylesheet.read_text(encoding='utf-8')
        self.assertIn('text-align: start;', stylesheet_contents)

    def test_double_submit_helper_preserves_named_submitter_values(self):
        script_path = Path(__file__).resolve().parents[1] / 'static' / 'dlux' / 'helpers' / 'prevent_double_submit.js'
        contents = script_path.read_text(encoding='utf-8')

        self.assertIn('const submitBtn = event.submitter ||', contents)
        self.assertIn("form.dataset.dluxSubmitting === 'true'", contents)
        self.assertIn('window.setTimeout(() => {', contents)
        self.assertLess(contents.index('window.setTimeout(() => {'), contents.index('submitBtn.disabled = true'))

    def test_system_setup_language_gate_template_uses_setup_language_choices(self):
        template_path = Path(__file__).resolve().parents[1] / 'templates' / 'dlux' / 'includes' / 'system_setup_language.html'
        contents = template_path.read_text(encoding='utf-8')

        self.assertIn('name="setup_language"', contents)
        self.assertIn('data-setup-language-start="{{ code }}"', contents)
        self.assertIn('dlux-setup-language-choice', contents)
        self.assertIn("dlux_static 'dlux/main/css/system_setup.css'", contents)
        self.assertLess(
            contents.index('dlux-setup-intro__text'),
            contents.index('dlux-setup-page-logo'),
        )

    def test_setup_language_does_not_force_saved_default_language(self):
        request = RequestFactory().get('/sys/setup/')
        request.session = {'dlux_initial_setup_language': 'en'}

        form = SystemSettingsForm(
            data={
                'system_names': '{"en": "System", "ar": "النظام"}',
                'home_url': '/',
                'default_language': 'ar',
                'default_theme': 'light',
                'allowed_themes': ['light'],
                'default_table_density': DEFAULT_TABLE_DENSITY,
                'languages': '{"en": {"name": "English", "dir": "ltr"}, "ar": {"name": "Arabic", "dir": "rtl"}}',
                'translations_override': '{}',
                'sidebar_config': '{"entries":[]}',
                'navbar_config': '{"enabled": false, "hierarchy": {"nodes": []}}',
                'log_config': '{}',
                'profile_config': '{}',
            },
            instance=SystemSettings(is_configured=False),
            request=request,
            mode='setup',
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['default_language'], 'ar')

        html = Template('{% load crispy_forms_tags %}{% crispy form %}').render(Context({'form': form}))
        self.assertNotIn('data-default-language-locked', html)
        self.assertIn('data-language-default value="ar" checked', html)
        self.assertNotIn('disabled aria-disabled="true"', html)

    def test_theme_preview_surfaces_include_aether_and_light_mono(self):
        css_path = Path(__file__).resolve().parents[1] / 'static' / 'dlux' / 'main' / 'css' / 'template_cleanup.css'
        contents = css_path.read_text(encoding='utf-8')

        self.assertIn('.dlux-theme-preview--mono', contents)
        self.assertIn('#ffffff 0%', contents)
        self.assertIn('#f4f6f8 48%', contents)
        self.assertIn('#cbd5df 49%', contents)
        self.assertIn('#94a3b8 100%', contents)
        self.assertNotIn('#475569 39%', contents)
        self.assertNotIn('#0f172a 100%', contents)
        self.assertIn('.dlux-theme-preview--prism', contents)
        self.assertIn('.dlux-theme-preview--aether', contents)
        self.assertIn('#a8ffe4', contents)

    def test_prism_and_aether_theme_owned_file_field_and_logo_overrides(self):
        static_root = Path(__file__).resolve().parents[1] / 'static' / 'dlux'

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
        css_path = Path(__file__).resolve().parents[1] / 'static' / 'dlux' / 'main' / 'css' / 'options.css'
        contents = css_path.read_text(encoding='utf-8')

        self.assertIn(':root.theme-aether .dlux-system-settings-actions .dlux-system-settings-tile,', contents)
        self.assertIn(':root.theme-aether .dlux-system-settings-tile-icon,', contents)
        self.assertIn(':root.theme-aether .dlux-system-settings-actions .dlux-system-settings-tile i,', contents)
        self.assertIn(':root.theme-aether .dlux-system-settings-actions .dlux-system-settings-tile:hover,', contents)
        self.assertIn(':root.theme-aether .dlux-system-settings-actions .dlux-system-settings-tile:focus-visible,', contents)
        self.assertIn(':root.theme-aether .dlux-system-settings-actions .dlux-system-settings-action--secondary,', contents)

    def test_verify_template_uses_versioned_auto_verify_script_and_trust_device_checkbox(self):
        template_path = Path(__file__).resolve().parents[1] / 'templates' / 'dlux' / '2fa' / 'verify.html'
        css_path = Path(__file__).resolve().parents[1] / 'static' / 'dlux' / 'users' / 'css' / 'login.css'
        script_path = Path(__file__).resolve().parents[1] / 'static' / 'dlux' / 'users' / 'js' / 'twofa_verify.js'
        contents = template_path.read_text(encoding='utf-8')
        stylesheet = css_path.read_text(encoding='utf-8')
        script = script_path.read_text(encoding='utf-8')

        self.assertIn("dlux/users/css/login.css", contents)
        self.assertIn("dlux/users/js/twofa_verify.js", contents)
        _assert_versioned_static_asset(self, contents, "dlux/users/css/login.css")
        _assert_versioned_static_asset(self, contents, "dlux/users/js/twofa_verify.js")
        self.assertIn('id="usePrimaryMethodBtn"', contents)
        self.assertIn('name="trust_device"', contents)
        self.assertIn('dlux-twofa-login-state', contents)
        self.assertIn('DLUX_STRINGS.2fa_trust_device_label', contents)
        self.assertIn('DLUX_STRINGS.login_logo_alt', contents)
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
        self.assertIn('.dlux-twofa-inline-alert', stylesheet)
        self.assertIn('.dlux-twofa-trust-field', stylesheet)

    def test_recent_2fa_and_client_ip_surfaces_do_not_use_hardcoded_translation_fallbacks(self):
        project_root = Path(__file__).resolve().parents[1]
        forms_contents = (project_root / 'forms.py').read_text(encoding='utf-8')
        profile_contents = (project_root / 'templates' / 'dlux' / 'users' / 'profile.html').read_text(encoding='utf-8')
        translation_contents = (project_root / 'translations.py').read_text(encoding='utf-8')

        self.assertNotIn("s.get('form_sys_client_ip_mode', 'Client IP source')", forms_contents)
        self.assertNotIn("s.get('client_ip_settings_title', 'Client IP Resolution')", forms_contents)
        self.assertNotIn("s.get('client_ip_settings_desc', 'Dlux uses this setting", forms_contents)
        self.assertNotIn('DLUX_STRINGS.trusted_device_badge|default', profile_contents)
        self.assertNotIn('DLUX_STRINGS.trusted_until|default', profile_contents)
        self.assertIn("'form_sys_client_ip_mode':", translation_contents)
        self.assertIn("'client_ip_settings_title':", translation_contents)
        self.assertIn("'2fa_trust_device_label':", translation_contents)
        self.assertIn("'trusted_device_badge':", translation_contents)

    def test_dynamic_modal_template_uses_nonce_on_external_loader(self):
        template_path = Path(__file__).resolve().parents[1] / 'templates' / 'dlux' / 'helpers' / 'dynamic_modal.html'
        script_path = Path(__file__).resolve().parents[1] / 'static' / 'dlux' / 'helpers' / 'dynamic_modal' / 'js' / 'main.js'
        contents = template_path.read_text(encoding='utf-8')
        script = script_path.read_text(encoding='utf-8')

        self.assertIn("dlux/helpers/dynamic_modal/js/main.js", contents)
        _assert_versioned_static_asset(self, contents, "dlux/helpers/dynamic_modal/js/main.js")
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
        templates_root = Path(__file__).resolve().parents[1] / 'templates' / 'dlux' / 'includes'

        language_editor = (templates_root / 'language_catalog_editor.html').read_text(encoding='utf-8')
        system_names_editor = (templates_root / 'system_names_editor.html').read_text(encoding='utf-8')
        translation_editor = (templates_root / 'translation_matrix_editor.html').read_text(encoding='utf-8')
        sidebar_builder = (templates_root / 'sidebar_builder.html').read_text(encoding='utf-8')
        setup_script = (
            Path(__file__).resolve().parents[1]
            / 'static'
            / 'dlux'
            / 'main'
            / 'js'
            / 'system_setup.js'
        ).read_text(encoding='utf-8')

        self.assertIn('id="dlux-language-code-input"', language_editor)
        self.assertIn('id="dlux-language-name-input"', language_editor)
        self.assertIn('id="dlux-language-dir-input"', language_editor)
        self.assertIn('id="dlux-language-flag-input"', language_editor)
        self.assertIn('id="dlux-system-name-', system_names_editor)
        self.assertIn('id="dlux-translation-search"', translation_editor)
        self.assertIn('id="dlux-translation-status"', translation_editor)
        self.assertIn('id="dlux-sidebar-catalog-data-', sidebar_builder)
        self.assertIn('id="dlux-sidebar-builder-search-', sidebar_builder)
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
        css_path = Path(__file__).resolve().parents[1] / 'static' / 'dlux' / 'main' / 'css' / 'options.css'
        js_path = Path(__file__).resolve().parents[1] / 'static' / 'dlux' / 'main' / 'js' / 'options.js'

        css_contents = css_path.read_text(encoding='utf-8')
        js_contents = js_path.read_text(encoding='utf-8')

        self.assertIn('.dlux-options-panel {', css_contents)
        self.assertIn('.dlux-options-card {', css_contents)
        self.assertIn('.dlux-options-card-handle {', css_contents)
        self.assertIn('.dlux-options-card-handle:not(:disabled),', css_contents)
        self.assertIn('.dlux-options-card-handle .bi {', css_contents)
        self.assertIn('cursor: grab;', css_contents)
        self.assertIn('.dlux-options-card-handle:not(:disabled):active,', css_contents)
        self.assertIn('.dlux-options-card-handle:active .bi {', css_contents)
        self.assertIn('cursor: grabbing;', css_contents)
        self.assertIn('float: inline-end;', css_contents)
        self.assertNotIn('top: 1rem;', css_contents)
        self.assertIn('.dlux-options-card--wide {', css_contents)
        self.assertIn('--dlux-options-grid-gap: 1.35rem;', css_contents)
        self.assertIn('position: relative;', css_contents)
        self.assertIn('0 16px 30px -28px rgba(15, 23, 42, 0.28);', css_contents)
        self.assertIn('inset-block: 1rem;', css_contents)
        self.assertIn('width: 3px;', css_contents)
        self.assertIn('.dlux-options-card.is-drag-over-before::after,', css_contents)
        self.assertIn('.dlux-options-card.is-drag-over-after::after {', css_contents)
        self.assertIn('inset-inline-start: calc((var(--dlux-options-grid-gap) / -2) - 1.5px);', css_contents)
        self.assertIn('inset-inline-end: calc((var(--dlux-options-grid-gap) / -2) - 1.5px);', css_contents)
        self.assertIn('pointer-events: none;', css_contents)
        self.assertIn('.dlux-options-system-info-table .table {', css_contents)
        self.assertIn('--bs-table-bg: transparent;', css_contents)
        self.assertIn('.dlux-options-system-info-table .progress {', css_contents)
        self.assertIn('OPTIONS_ORDER_STORAGE_KEY', js_contents)
        self.assertIn('data-options-card-handle', js_contents)
        self.assertIn('persistCardOrder(grid, storageKey)', js_contents)
        self.assertIn('function shouldInsertBefore(targetCard, event)', js_contents)
        self.assertIn("const direction = window.getComputedStyle(targetCard).direction || document.documentElement.dir || 'ltr';", js_contents)
        self.assertIn('return event.clientX < midpoint;', js_contents)

    def test_profile_confirmation_script_submits_password_modal_on_enter(self):
        template_path = Path(__file__).resolve().parents[1] / 'templates' / 'dlux' / 'users' / 'profile.html'
        script_path = Path(__file__).resolve().parents[1] / 'static' / 'dlux' / 'users' / 'js' / 'profile_2fa.js'
        template = template_path.read_text(encoding='utf-8')
        script = script_path.read_text(encoding='utf-8')

        confirm_js = (Path(__file__).resolve().parents[1] / 'static' / 'dlux' / 'main' / 'js' / 'confirm_password.js').read_text(encoding='utf-8')

        _assert_versioned_static_asset(self, template, "dlux/users/js/profile_2fa.js")
        self.assertIn('profile-session-trust-form', template)
        self.assertIn('DLUX_STRINGS.msg_confirm_trust_current_device', template)
        self.assertIn('DLUX_STRINGS.session_revoke_trusted_denied', template)
        self.assertIn('force_password_change_required', template)
        self.assertIn('data-autoclose="false"', template)
        self.assertIn('data-dlux-open-on-load="true"', template)
        self.assertIn('function confirmSessionTrust(form)', script)
        self.assertIn("resetPasswordModal.dataset.dluxOpenOnLoad === 'true'", script)
        self.assertIn('window.bootstrap.Modal.getOrCreateInstance(resetPasswordModal).show();', script)
        self.assertIn('.then(parseJsonResponse)', script)
        self.assertIn("window.location.assign(data.redirect_url || window.location.href);", script)
        # The confirm-password prompt is now the global dluxConfirmPassword helper;
        # profile_2fa.js's showConfirmation delegates to it, and the enter-to-submit
        # + inline password-error behaviour lives in confirm_password.js.
        self.assertIn('window.dluxConfirmPassword', script)
        self.assertIn('window.dluxConfirmPassword = dluxConfirmPassword', confirm_js)
        self.assertIn("addEventListener('keydown', onKey)", confirm_js)
        self.assertIn("e.key === 'Enter'", confirm_js)
        self.assertIn("addEventListener('input', onInput)", confirm_js)

    def test_global_confirm_password_prompt_wiring(self):
        base = Path(__file__).resolve().parents[1]
        base_html = (base / 'templates' / 'dlux' / 'base.html').read_text(encoding='utf-8')
        options_html = (base / 'templates' / 'dlux' / 'includes' / 'options.html').read_text(encoding='utf-8')
        partial = (base / 'templates' / 'dlux' / 'includes' / 'confirm_password_modal.html').read_text(encoding='utf-8')
        options_js = (base / 'static' / 'dlux' / 'main' / 'js' / 'options.js').read_text(encoding='utf-8')

        # base.html renders the global prompt + loads its script for authenticated users.
        self.assertIn("include 'dlux/includes/confirm_password_modal.html'", base_html)
        self.assertIn('confirm_password.js', base_html)
        # Redesigned admin-style modal (header + warning alert + footer).
        self.assertIn('data-dlux-confirm-modal', partial)
        self.assertIn('modal-header', partial)
        self.assertIn('modal-footer', partial)
        self.assertIn('alert alert-warning', partial)
        # The alert must opt out of the global .alert auto-hide (base_runtime.js),
        # or the modal's description would vanish after ~3s.
        self.assertIn('data-autoclose="false"', partial)
        self.assertIn('data-dlux-confirm-password', partial)
        # Admin force-password drives the global prompt from the chip; no bespoke modal.
        self.assertIn('data-force-pass-change-open', options_html)
        self.assertIn('dlux_force_pass_change_all', options_html)
        self.assertNotIn('data-force-pass-change-modal', options_html)
        self.assertIn('window.dluxConfirmPassword', options_js)

    def test_navbar_current_title_translates_for_reports_and_profile(self):
        # The Nav Bar current-page title (navbar_current_label = last crumb) must
        # resolve the translated title for non-sidebar system pages, not an English
        # humanization of the URL.
        from django.test import RequestFactory
        from django.urls import resolve
        from dlux.navbar import build_navbar_hierarchy_crumbs
        from dlux.translations import get_strings

        factory = RequestFactory()
        navbar_config = {'enabled': True, 'mode': 'hierarchy', 'hierarchy': {'nodes': []}}
        cases = {
            '/sys/reports/': {'en': 'Reports', 'ar': 'التقارير'},
            '/accounts/profile/': {'en': 'Profile', 'ar': 'الملف الشخصي'},
        }
        for path, expected in cases.items():
            for lang, label in expected.items():
                request = factory.get(path)
                request.resolver_match = resolve(path)
                crumbs = build_navbar_hierarchy_crumbs(request, navbar_config, lang, get_strings(lang))
                self.assertEqual(crumbs[-1].get('label'), label, msg=f'{path} [{lang}]')

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
            # base.html: dynamic font-face bridge. system_setup.html: a tiny
            # layout guard that forces the setup shell to a flow box, rendered
            # live from the template so a stale collected system_setup.css cannot
            # reintroduce the position:fixed/measured-top that hid the shell.
            inline_style_allowed = {'dlux/base.html', 'dlux/includes/system_setup.html'}
            if re.search(r'<style\b', contents, re.IGNORECASE) and rel_path not in inline_style_allowed:
                violations.append(f'{rel_path}:style-block')
            if inline_script_pattern.search(contents):
                violations.append(f'{rel_path}:inline-script')

        self.assertEqual(violations, [])

    def test_template_html_emitters_do_not_hardcode_inline_css_or_js(self):
        repo_root = Path(__file__).resolve().parents[2]
        emitter_paths = [
            repo_root / 'dlux' / 'forms.py',
            repo_root / 'dlux' / 'widgets.py',
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
        inline_style_pattern = re.compile(r'(?<![\w:-])style\s*=', re.IGNORECASE)
        violations = []

        for path in sorted(templates_root.rglob('*.html')):
            for lineno, line in enumerate(path.read_text(encoding='utf-8').splitlines(), start=1):
                if inline_style_pattern.search(line):
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
            auth_config={'prevent_multiple_active_sessions': True},
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
    @patch('dlux.models.SystemSettings.load')
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
        email_config = get_dlux_email_config(include_secret=True)

        self.assertEqual(email_config['transport'], 'direct')
        self.assertEqual(email_config['secret_storage'], 'env')
        self.assertEqual(email_config['host'], 'ui-smtp.example.com')
        self.assertEqual(email_config['port'], 587)
        self.assertTrue(email_config['use_tls'])
        self.assertEqual(email_config['username'], 'ui-user')
        self.assertEqual(email_config['from_email'], 'ui@example.com')
        self.assertEqual(email_config['password'], 'env-secret')

    @patch('dlux.models.SystemSettings.load')
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

        email_config = get_dlux_email_config(include_secret=True)

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

    @override_settings(DLUX_CONFIG={'default_table_density': 'invalid-choice'})
    def test_setup_form_falls_back_to_balanced_table_density(self):
        form = SystemSettingsForm(
            instance=SystemSettings(default_table_density='invalid-choice', is_configured=False),
        )

        self.assertEqual(form.initial['default_table_density'], DEFAULT_TABLE_DENSITY)

    @override_settings(DLUX_CONFIG={'default_language': 'ar'})
    @patch('dlux.discovery.discover_sidebar_catalog')
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
        self.assertIn('dlux-sidebar-catalog-fallback-data', form.sidebar_builder_html)
        self.assertIn('Demo', form.sidebar_builder_html)

    def test_system_setup_js_keeps_last_allowed_theme_postable(self):
        script = Path(__file__).resolve().parents[1] / 'static' / 'dlux' / 'main' / 'js' / 'system_setup.js'
        contents = script.read_text(encoding='utf-8')

        self.assertNotIn('checkbox.disabled = checkbox.checked && resolvedAllowedThemes.length === 1;', contents)
        self.assertIn("if (checkbox.checked && getAllowedThemes().length === 1)", contents)
        self.assertIn("checkbox.setAttribute('aria-disabled', isLocked ? 'true' : 'false');", contents)
        self.assertIn("preview: true,", contents)
        self.assertIn("candidate.getAttribute('data-setup-theme-choice') === theme", contents)
        self.assertIn("option ? option.getAttribute('data-setup-theme-preview-url') || '' : ''", contents)
        self.assertIn('const allowToggleContainers = Array.from(picker.querySelectorAll(\'[data-setup-theme-allow-toggle]\'));', contents)
        self.assertIn('function isThemeAllowControlTarget(target) {', contents)
        self.assertIn("target.closest('[data-setup-theme-allowed], [data-setup-theme-allowed-control]')", contents)
        self.assertIn('function isThemeDefaultControlTarget(target) {', contents)
        self.assertIn("target.closest('[data-setup-theme-choice]')", contents)
        self.assertIn('function toggleAllowedThemeFromContainer(container) {', contents)
        self.assertIn('event.stopPropagation();', contents)
        self.assertIn("option.addEventListener('keydown', (event) => {", contents)
        self.assertIn("!['Enter', ' '].includes(event.key)", contents)

    def test_theme_runtime_fades_explicit_switches_and_honors_reduced_motion(self):
        assets_root = Path(__file__).resolve().parents[1] / 'static' / 'dlux'
        theme_script = (assets_root / 'themes' / 'js' / 'main.js').read_text(encoding='utf-8')
        main_css = (assets_root / 'main' / 'css' / 'main.css').read_text(encoding='utf-8')
        sidebar_css = (assets_root / 'sidebar' / 'css' / 'main.css').read_text(encoding='utf-8')

        self.assertIn('function fadeThemeSwitch(resolvedTheme)', theme_script)
        self.assertIn("root.classList.contains('accessibility-no-animations')", theme_script)
        self.assertIn("window.matchMedia('(prefers-reduced-motion: reduce)')", theme_script)
        self.assertIn("root.classList.add('dlux-theme-switching-covered')", theme_script)
        self.assertIn(':root.dlux-theme-switching body::after {', main_css)
        self.assertIn(':root.dlux-theme-switching.dlux-theme-switching-covered body::after {', main_css)
        self.assertIn('@media (prefers-reduced-motion: reduce) {', main_css)
        self.assertIn(':root.dlux-theme-switching .sidebar .list-group-item,', sidebar_css)
        self.assertIn(':root.dlux-theme-switching .sidebar .accordion-button i {', sidebar_css)
        self.assertIn('transition: none !important;', sidebar_css)

    def test_sidebar_collapsed_icons_only_hides_group_label_flex_space(self):
        sidebar_css = (
            Path(__file__).resolve().parents[1]
            / 'static'
            / 'dlux'
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
        templates_root = Path(__file__).resolve().parents[1] / 'templates' / 'dlux' / 'sidebar'
        tree_template = (templates_root / 'tree.html').read_text(encoding='utf-8')
        extra_groups_template = (templates_root / 'extra_groups.html').read_text(encoding='utf-8')

        self.assertNotIn('accordion-button sidebar-folder-button flex-grow-1', tree_template)
        self.assertNotIn('accordion-button sidebar-folder-button flex-grow-1', extra_groups_template)
        self.assertNotIn('<span class="flex-grow-1 text-start">', tree_template)
        self.assertNotIn('<span class="flex-grow-1 text-start">', extra_groups_template)
        self.assertIn('<span class="text-start">', tree_template)
        self.assertIn('<span class="text-start">', extra_groups_template)

    @override_settings(DLUX_CONFIG={}, MEDIA_URL='')
    def test_uploaded_branding_urls_fall_back_to_absolute_media_paths(self):
        fake_settings = SimpleNamespace(
            system_names={},
            logo=SimpleNamespace(url='dlux/branding/logo.png'),
            favicon=SimpleNamespace(url='dlux/branding/favicon.ico'),
            home_url='',
            default_language='en',
            default_theme='light',
            languages={},
            translations_override={},
            sidebar_config={},
            is_configured=True,
        )

        with patch('dlux.models.SystemSettings.load', return_value=fake_settings):
            config = get_system_config()

        self.assertEqual(config['logo_url'], '/media/dlux/branding/logo.png')
        self.assertEqual(config['login_logo_url'], '/media/dlux/branding/logo.png')
        self.assertEqual(config['favicon_url'], '/media/dlux/branding/favicon.ico')

    @override_settings(DLUX_CONFIG={
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
