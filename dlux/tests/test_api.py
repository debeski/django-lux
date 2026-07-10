from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.core.exceptions import FieldDoesNotExist
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.core.cache import cache
import json
from types import SimpleNamespace
from unittest.mock import patch

from dlux.api import _scope_filter_queryset, _serialize_instance
from dlux.models import Section, SystemSettings

User = get_user_model()


class _FakeMeta:
    app_label = "fake"
    model_name = "record"

    def __init__(self, has_scope=True, fields=None):
        self.has_scope = has_scope
        self._fields = fields or []

    def get_field(self, name):
        if name == "scope" and self.has_scope:
            return object()
        raise FieldDoesNotExist(name)

    def get_fields(self):
        return self._fields


class _FakeModel:
    def __init__(self, has_scope=True):
        self._meta = _FakeMeta(has_scope=has_scope)


class _FakeQuerySet:
    def __init__(self, model):
        self.model = model
        self.filtered_scope = None
        self.none_called = False

    def filter(self, **kwargs):
        clone = _FakeQuerySet(self.model)
        clone.filtered_scope = kwargs.get("scope")
        return clone

    def none(self):
        clone = _FakeQuerySet(self.model)
        clone.none_called = True
        return clone


class _FakeField:
    concrete = True
    auto_created = False
    is_relation = False

    def __init__(self, name):
        self.name = name

    def get_internal_type(self):
        return "CharField"


class APIHelperSecurityTests(TestCase):
    def _user(self, scope=None, *, superuser=False, global_staff=False):
        permissions = {"dlux.manage_scopes"} if global_staff else set()
        return SimpleNamespace(
            is_authenticated=True,
            is_superuser=superuser,
            is_staff=global_staff,
            profile=SimpleNamespace(scope=scope),
            has_perm=lambda perm: perm in permissions,
        )

    @patch("dlux.api.is_scope_enabled", return_value=True)
    def test_scope_filter_limits_scoped_model_to_user_scope(self, _scope_enabled):
        user_scope = object()
        qs = _FakeQuerySet(_FakeModel(has_scope=True))

        filtered = _scope_filter_queryset(self._user(scope=user_scope), qs)

        self.assertIs(filtered.filtered_scope, user_scope)
        self.assertFalse(filtered.none_called)

    @patch("dlux.api.is_scope_enabled", return_value=True)
    def test_scope_filter_fails_closed_for_scopeless_user_on_scoped_model(self, _scope_enabled):
        qs = _FakeQuerySet(_FakeModel(has_scope=True))

        filtered = _scope_filter_queryset(self._user(scope=None), qs)

        self.assertTrue(filtered.none_called)

    @patch("dlux.api.is_scope_enabled", return_value=True)
    def test_scope_filter_allows_global_staff(self, _scope_enabled):
        qs = _FakeQuerySet(_FakeModel(has_scope=True))

        filtered = _scope_filter_queryset(self._user(global_staff=True), qs)

        self.assertIs(filtered, qs)

    def test_serializer_skips_secret_like_fields(self):
        instance = SimpleNamespace(
            _meta=_FakeMeta(fields=[
                _FakeField("name"),
                _FakeField("api_token"),
                _FakeField("smtp_password"),
                _FakeField("email_config"),
            ]),
            pk=1,
            name="Visible",
            api_token="secret-token",
            smtp_password="secret-password",
            email_config={"mode": "encrypted_db"},
        )

        data = _serialize_instance(instance)

        self.assertEqual(data["name"], "Visible")
        self.assertNotIn("api_token", data)
        self.assertNotIn("smtp_password", data)
        self.assertNotIn("email_config", data)


class APIEndpointsTests(TestCase):
    def setUp(self):
        cache.clear()
        settings_obj = SystemSettings.load()
        settings_obj.is_configured = True
        settings_obj.save(update_fields=['is_configured'])
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')

    def test_get_last_entry_requires_login(self):
        """Test that get_last_entry requires authentication."""
        self.client.logout()
        response = self.client.get(
            reverse('api_get_last_entry', args=['dlux', 'SystemSettings'])
        )
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_get_last_entry_requires_permission(self):
        """Test that get_last_entry requires view permission."""
        # Create a user without permissions
        regular_user = User.objects.create_user(
            username='user2',
            email='user2@example.com',
            password='userpass123'
        )
        self.client.logout()
        self.client.login(username='user2', password='userpass123')
        
        response = self.client.get(
            reverse('api_get_last_entry', args=['dlux', 'SystemSettings'])
        )
        self.assertEqual(response.status_code, 403)  # Permission denied

    def test_get_last_entry_with_permission(self):
        """Test get_last_entry with proper permissions."""
        ct = ContentType.objects.get_for_model(User)
        perm = Permission.objects.get(codename='view_user', content_type=ct)
        self.user.user_permissions.add(perm)
        
        response = self.client.get(
            reverse('api_get_last_entry', args=['auth', 'User'])
        )
        self.assertIn(response.status_code, [200, 404])  # 200 if exists, 404 if no entries

    def test_get_model_details_requires_login(self):
        """Test that get_model_details requires authentication."""
        self.client.logout()
        response = self.client.get(
            reverse('api_get_empty_schema', args=['dlux', 'SystemSettings'])
        )
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_get_model_details_empty_schema(self):
        """Test get_model_details with empty_schema."""
        settings_ct = ContentType.objects.get_for_model(SystemSettings)
        perm = Permission.objects.get(codename='view_systemsettings', content_type=settings_ct)
        self.user.user_permissions.add(perm)

        response = self.client.get(
            reverse('api_get_empty_schema', args=['dlux', 'SystemSettings'])
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('_pk', data)

    def test_get_model_details_invalid_model(self):
        """Test get_model_details with invalid model."""
        response = self.client.get(
            reverse('api_get_model_details', args=['invalid', 'InvalidModel', '1'])
        )
        self.assertEqual(response.status_code, 404)

    def test_get_model_details_no_longer_expands_reverse_one_to_one_fields(self):
        ct = ContentType.objects.get_for_model(User)
        perm = Permission.objects.get(codename='view_user', content_type=ct)
        self.user.user_permissions.add(perm)
        self.user.profile.phone = '5551234'
        self.user.profile.save(update_fields=['phone'])

        response = self.client.get(
            reverse('api_get_model_details', args=['auth', 'User', self.user.pk])
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertNotIn('phone', data)

    def test_update_preferences_requires_login(self):
        """Test that update_preferences requires authentication."""
        self.client.logout()
        response = self.client.post(
            reverse('update_preferences'),
            {'theme': 'dark'},
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_update_preferences_post(self):
        """Test update_preferences with POST."""
        response = self.client.post(
            reverse('update_preferences'),
            json.dumps({'theme': 'dark', 'language': 'en', 'table_density': 'dense', 'table_page_size': 50}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')
        
        # Verify preference was saved
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.preferences.get('theme'), 'dark')
        self.assertEqual(self.user.profile.preferences.get('table_density'), 'dense')
        self.assertEqual(self.user.profile.preferences.get('table_page_size'), 50)

    def test_update_preferences_rejects_invalid_table_page_size(self):
        self.user.profile.preferences = {'table_page_size': 20}
        self.user.profile.save(update_fields=['preferences'])

        response = self.client.post(
            reverse('update_preferences'),
            json.dumps({'table_page_size': 15}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        self.user.profile.refresh_from_db()
        self.assertNotIn('table_page_size', self.user.profile.preferences)

    def test_update_preferences_with_form_data(self):
        """Test update_preferences with form data (not JSON)."""
        response = self.client.post(
            reverse('update_preferences'),
            {'theme': 'light', 'sidebar_collapsed': 'true'}
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')

    def test_update_preferences_rejects_disallowed_theme(self):
        settings_obj = SystemSettings.load()
        settings_obj.allowed_themes = ['dark']
        settings_obj.default_theme = 'dark'
        settings_obj.save()

        response = self.client.post(
            reverse('update_preferences'),
            json.dumps({'theme': 'retro'}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        self.user.profile.refresh_from_db()
        self.assertNotIn('theme', self.user.profile.preferences)

    def test_update_preferences_rejects_theme_when_override_disabled(self):
        settings_obj = SystemSettings.load()
        settings_obj.allowed_themes = ['dark', 'retro']
        settings_obj.default_theme = 'dark'
        settings_obj.allow_user_theme_override = False
        settings_obj.save()

        response = self.client.post(
            reverse('update_preferences'),
            json.dumps({'theme': 'retro'}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        self.user.profile.refresh_from_db()
        self.assertNotIn('theme', self.user.profile.preferences)

    def test_update_preferences_rejects_language_when_override_disabled(self):
        settings_obj = SystemSettings.load()
        settings_obj.allow_user_language_override = False
        settings_obj.save()

        response = self.client.post(
            reverse('update_preferences'),
            json.dumps({'language': 'ar'}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        self.user.profile.refresh_from_db()
        self.assertNotIn('language', self.user.profile.preferences)

    def test_update_preferences_validates_sidebar_density(self):
        response = self.client.post(
            reverse('update_preferences'),
            json.dumps({'sidebar_density': 'invalid'}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        self.user.profile.refresh_from_db()
        self.assertNotIn('sidebar_density', self.user.profile.preferences)

    def test_update_preferences_rejects_sidebar_density_when_override_disabled(self):
        settings_obj = SystemSettings.load()
        settings_obj.sidebar_config = {
            'entries': [],
            'allow_user_density': False,
            'density': 'roomy',
        }
        settings_obj.save()

        response = self.client.post(
            reverse('update_preferences'),
            json.dumps({'sidebar_density': 'dense'}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        self.user.profile.refresh_from_db()
        self.assertNotIn('sidebar_density', self.user.profile.preferences)

    def test_update_preferences_validates_navbar_mode_against_system_gate(self):
        settings_obj = SystemSettings.load()
        settings_obj.navbar_config = {
            'enabled': True,
            'default_mode': 'hierarchy',
            'allow_user_mode_override': True,
            'hierarchy': {'nodes': []},
        }
        settings_obj.save()

        response = self.client.post(
            reverse('update_preferences'),
            json.dumps({'navbar_mode': 'history'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.preferences['navbar_mode'], 'history')

        settings_obj.navbar_config['allow_user_mode_override'] = False
        settings_obj.save(update_fields=['navbar_config'])
        response = self.client.post(
            reverse('update_preferences'),
            json.dumps({'navbar_mode': 'invalid'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.user.profile.refresh_from_db()
        self.assertNotIn('navbar_mode', self.user.profile.preferences)

    def test_update_preferences_rejects_sidebar_collapsed_when_locked_expanded(self):
        settings_obj = SystemSettings.load()
        settings_obj.sidebar_config = {
            'entries': [],
            'collapse_mode': 'locked_expanded',
        }
        settings_obj.save()

        response = self.client.post(
            reverse('update_preferences'),
            json.dumps({'sidebar_collapsed': True}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        self.user.profile.refresh_from_db()
        self.assertNotIn('sidebar_collapsed', self.user.profile.preferences)

    def test_update_preferences_invalid_method(self):
        """Test update_preferences with invalid method."""
        response = self.client.get(reverse('update_preferences'))
        self.assertEqual(response.status_code, 405)  # Method not allowed

    def test_update_preferences_returns_sanitized_error_payload(self):
        with patch('dlux.api.get_system_config', side_effect=RuntimeError('secret backend failure')):
            response = self.client.post(
                reverse('update_preferences'),
                json.dumps({'theme': 'dark'}),
                content_type='application/json'
            )

        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'error')
        self.assertNotIn('secret backend failure', data['message'])

    def test_reset_preferences_requires_login(self):
        """Test that reset_preferences requires authentication."""
        self.client.logout()
        response = self.client.post(reverse('reset_preferences'))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_reset_preferences_post(self):
        """Test reset_preferences with POST."""
        # Set some preferences first
        self.user.profile.preferences = {'theme': 'dark', 'language': 'en', 'table_density': 'roomy'}
        self.user.profile.save()
        
        response = self.client.post(reverse('reset_preferences'))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        
        # Verify preferences were cleared
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.preferences, {})

    def test_reset_preferences_clears_session(self):
        """Test that reset_preferences clears session keys."""
        # Set session keys
        session = self.client.session
        session['django_language'] = 'ar'
        session['sidebarCollapsed'] = True
        session.save()
        
        response = self.client.post(reverse('reset_preferences'))
        self.assertEqual(response.status_code, 200)
        
        # Verify session keys were cleared
        session = self.client.session
        self.assertNotIn('django_language', session)
        self.assertNotIn('sidebarCollapsed', session)

    def test_reset_preferences_invalid_method(self):
        """Test reset_preferences with invalid method."""
        response = self.client.get(reverse('reset_preferences'))
        self.assertEqual(response.status_code, 400)  # Bad request

    def test_reset_preferences_returns_sanitized_error_payload(self):
        with patch('dlux.api.log_user_action', side_effect=RuntimeError('sensitive failure')):
            response = self.client.post(reverse('reset_preferences'))

        self.assertEqual(response.status_code, 500)
        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertNotIn('sensitive failure', data['error'])


class AppPreferencesTests(TestCase):
    """The reserved `app` namespace + size cap + targeted patch endpoint."""

    def setUp(self):
        cache.clear()
        ss = SystemSettings.load()
        ss.is_configured = True
        ss.save(update_fields=['is_configured'])
        self.user = User.objects.create_user('appuser', 'app@example.com', 'pw12345!')
        self.client = Client()
        self.client.login(username='appuser', password='pw12345!')

    def _prefs(self):
        self.user.profile.refresh_from_db()
        return self.user.profile.preferences

    # --- main endpoint: app namespace pass-through + merge -----------------
    def test_app_namespace_is_stored_opaquely(self):
        payload = {'app': {'proj.dashboard.v1': {'order': [3, 1, 2], 'hidden': ['x']}}}
        r = self.client.post(reverse('update_preferences'), json.dumps(payload), content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self._prefs()['app']['proj.dashboard.v1'], {'order': [3, 1, 2], 'hidden': ['x']})

    def test_app_namespace_merges_and_preserves_siblings(self):
        self.client.post(reverse('update_preferences'),
                         json.dumps({'app': {'a': {'v': 1}}}), content_type='application/json')
        self.client.post(reverse('update_preferences'),
                         json.dumps({'app': {'b': {'v': 2}}}), content_type='application/json')
        app = self._prefs()['app']
        self.assertEqual(app, {'a': {'v': 1}, 'b': {'v': 2}})

    def test_app_namespace_does_not_touch_dlux_keys(self):
        self.client.post(reverse('update_preferences'),
                         json.dumps({'theme': 'dark'}), content_type='application/json')
        self.client.post(reverse('update_preferences'),
                         json.dumps({'app': {'a': {'v': 1}}}), content_type='application/json')
        prefs = self._prefs()
        self.assertEqual(prefs.get('theme'), 'dark')
        self.assertEqual(prefs['app']['a'], {'v': 1})

    def test_app_namespace_none_clears_entry(self):
        self.client.post(reverse('update_preferences'),
                         json.dumps({'app': {'a': {'v': 1}}}), content_type='application/json')
        self.client.post(reverse('update_preferences'),
                         json.dumps({'app': {'a': None}}), content_type='application/json')
        self.assertNotIn('app', self._prefs())

    # --- size cap ----------------------------------------------------------
    def test_oversized_payload_is_rejected_with_413(self):
        with self.settings(DLUX_MAX_PREFERENCES_BYTES=2048):
            blob = 'x' * 4096
            r = self.client.post(reverse('update_preferences'),
                                 json.dumps({'app': {'big': blob}}), content_type='application/json')
        self.assertEqual(r.status_code, 413)
        self.assertNotIn('app', self._prefs())  # nothing persisted

    # --- targeted patch endpoint ------------------------------------------
    def test_patch_endpoint_sets_single_namespace(self):
        url = reverse('update_app_preference', kwargs={'namespace': 'proj.dash'})
        r = self.client.post(url, json.dumps({'order': [1, 2]}), content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['value'], {'order': [1, 2]})
        self.assertEqual(self._prefs()['app']['proj.dash'], {'order': [1, 2]})

    def test_patch_endpoint_isolates_other_namespaces_and_dlux_keys(self):
        self.client.post(reverse('update_preferences'),
                         json.dumps({'theme': 'dark', 'app': {'keep': {'v': 1}}}),
                         content_type='application/json')
        url = reverse('update_app_preference', kwargs={'namespace': 'proj.dash'})
        self.client.post(url, json.dumps({'order': [9]}), content_type='application/json')
        prefs = self._prefs()
        self.assertEqual(prefs['theme'], 'dark')
        self.assertEqual(prefs['app']['keep'], {'v': 1})
        self.assertEqual(prefs['app']['proj.dash'], {'order': [9]})

    def test_patch_endpoint_null_body_clears_namespace(self):
        url = reverse('update_app_preference', kwargs={'namespace': 'proj.dash'})
        self.client.post(url, json.dumps({'order': [1]}), content_type='application/json')
        r = self.client.post(url, 'null', content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertNotIn('app', self._prefs())

    def test_patch_endpoint_enforces_size_cap(self):
        url = reverse('update_app_preference', kwargs={'namespace': 'big'})
        with self.settings(DLUX_MAX_PREFERENCES_BYTES=2048):
            r = self.client.post(url, json.dumps({'blob': 'x' * 4096}), content_type='application/json')
        self.assertEqual(r.status_code, 413)

    def test_patch_endpoint_requires_login_and_post(self):
        url = reverse('update_app_preference', kwargs={'namespace': 'proj.dash'})
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.post(url, 'null', content_type='application/json').status_code, 302)
