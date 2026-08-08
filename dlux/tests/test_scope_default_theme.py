from types import SimpleNamespace

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import RequestFactory, TestCase
from django.urls import reverse

from dlux.context_processors import dlux_context
from dlux.forms import ScopeForm
from dlux.models import Scope, ScopeSettings, SystemSettings
from dlux.utils import resolve_user_theme_preference


class ScopeDefaultThemeTests(TestCase):
    def setUp(self):
        cache.clear()
        settings_obj = SystemSettings.load()
        settings_obj.is_configured = True
        settings_obj.default_theme = 'light'
        settings_obj.allowed_themes = ['light', 'dark', 'retro']
        settings_obj.allow_user_theme_override = True
        settings_obj.save()
        scope_settings = ScopeSettings.load()
        scope_settings.is_enabled = True
        scope_settings.save()

    def test_scope_model_inherits_system_theme_by_default(self):
        scope = Scope.objects.create(name='Unspecified')

        self.assertEqual(scope.default_theme, '')

    def test_scope_form_offers_only_allowed_themes_and_defaults_to_system_theme(self):
        form = ScopeForm()

        self.assertEqual(
            [value for value, _label in form.fields['default_theme'].choices],
            ['light', 'dark', 'retro'],
        )
        self.assertEqual(form.initial['default_theme'], 'light')

    def test_scope_form_saves_selected_default_theme(self):
        form = ScopeForm({
            'name': 'Dark Scope',
            'description': '',
            'default_theme': 'dark',
        })

        self.assertTrue(form.is_valid(), form.errors)
        scope = form.save()
        self.assertEqual(scope.default_theme, 'dark')

    def test_scope_creation_endpoint_saves_selected_default_theme(self):
        admin = get_user_model().objects.create_superuser('scope-admin', password='pw')
        self.client.force_login(admin)

        form_response = self.client.get(reverse('get_scope_form'))

        self.assertEqual(form_response.status_code, 200)
        self.assertIn('id_default_theme', form_response.json()['html'])

        response = self.client.post(reverse('save_scope'), {
            'name': 'Endpoint Scope',
            'description': '',
            'default_theme': 'retro',
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        self.assertEqual(
            Scope.objects.get(name='Endpoint Scope').default_theme,
            'retro',
        )

    def test_scope_form_rejects_theme_outside_allowed_list(self):
        form = ScopeForm({
            'name': 'Invalid Scope',
            'description': '',
            'default_theme': 'neon',
        })

        self.assertFalse(form.is_valid())
        self.assertIn('default_theme', form.errors)

    def test_scope_form_hides_theme_when_scopes_are_disabled_and_preserves_edit(self):
        scope = Scope.objects.create(name='Existing', default_theme='dark')
        scope_settings = ScopeSettings.load()
        scope_settings.is_enabled = False
        scope_settings.save()

        form = ScopeForm({'name': 'Renamed', 'description': ''}, instance=scope)

        self.assertNotIn('default_theme', form.fields)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        scope.refresh_from_db()
        self.assertEqual(scope.default_theme, 'dark')

    def test_scope_form_hides_theme_when_only_one_theme_is_allowed(self):
        settings_obj = SystemSettings.load()
        settings_obj.default_theme = 'dark'
        settings_obj.allowed_themes = ['dark']
        settings_obj.save()

        form = ScopeForm()

        self.assertNotIn('default_theme', form.fields)

    def test_scope_default_is_used_only_without_valid_personal_preference(self):
        config = {
            'default_theme': 'light',
            'allowed_themes': ['light', 'dark', 'retro'],
            'allow_user_theme_override': True,
        }
        scope = SimpleNamespace(default_theme='dark')

        inherited = resolve_user_theme_preference(
            {}, config, scope=scope, scopes_enabled=True,
        )
        personalized = resolve_user_theme_preference(
            {'theme': 'retro'}, config, scope=scope, scopes_enabled=True,
        )

        self.assertEqual(inherited['theme'], 'dark')
        self.assertEqual(personalized['theme'], 'retro')

    def test_scope_default_is_ignored_when_disabled_or_no_longer_allowed(self):
        config = {
            'default_theme': 'light',
            'allowed_themes': ['light', 'dark'],
            'allow_user_theme_override': True,
        }

        disabled = resolve_user_theme_preference(
            {}, config, scope=SimpleNamespace(default_theme='dark'), scopes_enabled=False,
        )
        invalid = resolve_user_theme_preference(
            {}, config, scope=SimpleNamespace(default_theme='retro'), scopes_enabled=True,
        )

        self.assertEqual(disabled['theme'], 'light')
        self.assertEqual(invalid['theme'], 'light')

    def test_context_injects_scope_default_without_persisting_it_as_user_choice(self):
        scope = Scope.objects.create(name='Dark Scope', default_theme='dark')
        user = get_user_model().objects.create_user('scoped-theme-user', password='pw')
        user.profile.scope = scope
        user.profile.preferences = {}
        user.profile.save(update_fields=['scope', 'preferences'])
        request = RequestFactory().get('/')
        request.user = user
        request.session = {}

        context = dlux_context(request)

        self.assertEqual(context['user_preferences']['theme'], 'dark')
        user.profile.refresh_from_db()
        self.assertNotIn('theme', user.profile.preferences)

    def test_initial_user_setup_selects_the_scope_default(self):
        scope = Scope.objects.create(name='Onboarding Scope', default_theme='dark')
        user = get_user_model().objects.create_user('scope-onboarding-user', password='pw')
        user.profile.scope = scope
        user.profile.preferences = {}
        user.profile.save(update_fields=['scope', 'preferences'])
        self.client.force_login(user)

        response = self.client.get(reverse('initial_user_setup'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['current_theme'], 'dark')
