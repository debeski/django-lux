from dlux.tests.harness import setup_test_environment

setup_test_environment()

import copy
import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.test import Client, RequestFactory, TestCase, override_settings

from dlux import options
from dlux.models import SystemSettings

User = get_user_model()

# Add this app's tests/templates dir so cards can point at a real template while
# keeping APP_DIRS + context processors intact for the integration render.
_TEMPLATES = copy.deepcopy(settings.TEMPLATES)
_TEMPLATES[0]['DIRS'] = list(_TEMPLATES[0].get('DIRS', [])) + [
    os.path.join(os.path.dirname(__file__), 'templates')
]


class RegisterCardValidationTests(TestCase):
    def setUp(self):
        options.clear_registry()

    def tearDown(self):
        options.clear_registry()

    def test_valid_registration(self):
        options.register_card(id='myapp.card', title='Card', template_name='options_test_card.html')
        self.assertIn('myapp.card', options._REGISTRY)

    def test_rejects_unsafe_id(self):
        for bad in ('bad id', 'bad/id', 'x' * 200, '', 'inject"'):
            with self.assertRaises(ValueError):
                options.register_card(id=bad, title='t', template_name='t.html')

    def test_rejects_bad_title_icon_template_permission(self):
        with self.assertRaises(ValueError):
            options.register_card(id='a.b', title='', template_name='t.html')
        with self.assertRaises(ValueError):
            options.register_card(id='a.b', title='t', template_name='')
        with self.assertRaises(ValueError):
            options.register_card(id='a.b', title='t', template_name='t.html', icon='"><script>')
        with self.assertRaises(ValueError):
            options.register_card(id='a.b', title='t', template_name='t.html', permission=123)
        with self.assertRaises(ValueError):
            options.register_card(id='a.b', title='t', template_name='t.html', context_builder='notcallable')

    def test_callable_title_allowed(self):
        options.register_card(id='a.b', title=lambda r: 'Dynamic', template_name='options_test_card.html')
        self.assertIn('a.b', options._REGISTRY)


class VisibilityGatingTests(TestCase):
    def setUp(self):
        cache.clear()
        options.clear_registry()
        self.factory = RequestFactory()
        self.superuser = User.objects.create_superuser('root', 'r@x.com', 'pw')
        self.regular = User.objects.create_user('joe', 'j@x.com', 'pw')

    def tearDown(self):
        options.clear_registry()

    def _req(self, user):
        req = self.factory.get('/sys/options/')
        req.user = user
        return req

    def test_superuser_only_hidden_from_regular(self):
        options.register_card(id='admin.card', title='A', template_name='options_test_card.html', superuser_only=True)
        self.assertEqual([c['id'] for c in options.get_visible_cards(self._req(self.regular))], [])
        self.assertEqual([c['id'] for c in options.get_visible_cards(self._req(self.superuser))], ['admin.card'])

    def test_permission_gating(self):
        options.register_card(id='perm.card', title='P', template_name='options_test_card.html',
                              permission='auth.view_user')
        self.assertEqual(options.get_visible_cards(self._req(self.regular)), [])
        ct = ContentType.objects.get_for_model(User)
        self.regular.user_permissions.add(Permission.objects.get(codename='view_user', content_type=ct))
        self.regular = User.objects.get(pk=self.regular.pk)  # refresh perm cache
        self.assertEqual([c['id'] for c in options.get_visible_cards(self._req(self.regular))], ['perm.card'])

    def test_anonymous_sees_nothing(self):
        from django.contrib.auth.models import AnonymousUser
        options.register_card(id='a.b', title='A', template_name='options_test_card.html')
        self.assertEqual(options.get_visible_cards(self._req(AnonymousUser())), [])

    def test_visible_predicate_shows_and_hides(self):
        state = {'on': False}
        options.register_card(id='cfg.card', title='Cfg', template_name='options_test_card.html',
                              visible=lambda r: state['on'])
        self.assertEqual(options.get_visible_cards(self._req(self.superuser)), [])
        state['on'] = True
        self.assertEqual([c['id'] for c in options.get_visible_cards(self._req(self.superuser))], ['cfg.card'])

    def test_visible_predicate_fails_closed(self):
        def boom(request):
            raise RuntimeError('config lookup failed')
        options.register_card(id='cfg.card', title='Cfg', template_name='options_test_card.html', visible=boom)
        # A raising predicate hides the card rather than exposing it.
        self.assertEqual(options.get_visible_cards(self._req(self.superuser)), [])

    def test_visible_runs_after_static_gates(self):
        # superuser_only still wins even if visible() would allow it.
        options.register_card(id='cfg.card', title='Cfg', template_name='options_test_card.html',
                              superuser_only=True, visible=lambda r: True)
        self.assertEqual(options.get_visible_cards(self._req(self.regular)), [])

    def test_rejects_non_callable_visible(self):
        with self.assertRaises(ValueError):
            options.register_card(id='a.b', title='t', template_name='t.html', visible='nope')

    def test_sorted_by_order_then_id(self):
        options.register_card(id='z.late', title='Z', template_name='options_test_card.html', order=200)
        options.register_card(id='a.early', title='A', template_name='options_test_card.html', order=10)
        options.register_card(id='b.early', title='B', template_name='options_test_card.html', order=10)
        ids = [c['id'] for c in options.get_visible_cards(self._req(self.superuser))]
        self.assertEqual(ids, ['a.early', 'b.early', 'z.late'])


@override_settings(TEMPLATES=_TEMPLATES)
class RenderSandboxTests(TestCase):
    """Render behaviour exercised through the real Options page (a real request,
    so the standard context processors run exactly as in production)."""

    def setUp(self):
        cache.clear()
        options.clear_registry()
        ss = SystemSettings.load()
        ss.is_configured = True
        ss.save(update_fields=['is_configured'])
        self.user = User.objects.create_superuser('root', 'r@x.com', 'pw12345!')
        self.client = Client()
        self.client.force_login(self.user)

    def tearDown(self):
        options.clear_registry()

    def _page(self):
        return self.client.get('/sys/options/')

    def test_context_builder_output_rendered_and_escaped(self):
        options.register_card(
            id='esc.card', title='Esc', template_name='options_test_card.html',
            context_builder=lambda r: {'greeting': '<script>alert(1)</script>'},
        )
        r = self._page()
        self.assertContains(r, 'data-options-card="esc.card"')
        # Data from the builder is auto-escaped by Django — no raw <script>.
        self.assertContains(r, '&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(r, '<script>alert(1)</script>')

    def test_broken_card_is_skipped_not_fatal(self):
        def boom(request):
            raise RuntimeError('bad builder')
        options.register_card(id='ok.card', title='OK', template_name='options_test_card.html',
                              context_builder=lambda r: {'greeting': 'GOOD-BODY'}, order=1)
        options.register_card(id='bad.card', title='Bad', template_name='options_test_card.html',
                              context_builder=boom, order=2)
        r = self._page()
        # Page renders fine; the good card survives, the exploding one is dropped.
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'GOOD-BODY')
        self.assertNotContains(r, 'data-options-card="bad.card"')

    def test_missing_template_is_skipped(self):
        options.register_card(id='nope.card', title='Nope', template_name='does_not_exist_xyz.html')
        r = self._page()
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, 'data-options-card="nope.card"')

    def test_callable_title_resolved(self):
        options.register_card(id='dyn.card', title=lambda r: 'Resolved-Title', template_name='options_test_card.html',
                              context_builder=lambda r: {'greeting': 'x'})
        self.assertContains(self._page(), 'Resolved-Title')


@override_settings(TEMPLATES=_TEMPLATES)
class OptionsViewIntegrationTests(TestCase):
    def setUp(self):
        cache.clear()
        options.clear_registry()
        ss = SystemSettings.load()
        ss.is_configured = True
        ss.save(update_fields=['is_configured'])
        self.user = User.objects.create_user('joe', 'j@x.com', 'pw12345!')
        self.client = Client()
        self.client.force_login(self.user)

    def tearDown(self):
        options.clear_registry()

    def test_registered_card_appears_on_options_page(self):
        options.register_card(id='myapp.hello', title='Hello Card', template_name='options_test_card.html',
                              context_builder=lambda r: {'greeting': 'HELLO-CARD-BODY'})
        r = self.client.get('/sys/options/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'data-options-card="myapp.hello"')
        self.assertContains(r, 'HELLO-CARD-BODY')

    def test_superuser_only_card_hidden_from_regular_user(self):
        options.register_card(id='admin.only', title='Admin', template_name='options_test_card.html',
                              superuser_only=True, context_builder=lambda r: {'greeting': 'ADMINONLY-SENTINEL-XYZ'})
        r = self.client.get('/sys/options/')
        self.assertNotContains(r, 'data-options-card="admin.only"')
        self.assertNotContains(r, 'ADMINONLY-SENTINEL-XYZ')
