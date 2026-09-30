from dlux.tests.harness import setup_test_environment

setup_test_environment()

from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from dlux.views import options

User = get_user_model()
AJAX = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}


def _fake_app(replies=None, raise_exc=None):
    control = mock.Mock()
    if raise_exc is not None:
        control.ping.side_effect = raise_exc
    else:
        control.ping.return_value = replies or []
    return SimpleNamespace(control=control)


def _fake_celery():
    return SimpleNamespace(__version__='5.3.0')


def _configured():
    from dlux.models import SystemSettings
    SystemSettings.objects.all().delete()
    cache.clear()
    ss = SystemSettings.load()
    ss.is_configured = True
    ss.save()
    cache.clear()


@override_settings(CELERY_BROKER_URL='redis://localhost:6379/0')
class CeleryHealthServiceTests(TestCase):
    def setUp(self):
        cache.delete(options.CELERY_HEALTH_RESULT_KEY)

    def test_page_load_never_probes_and_shows_unknown(self):
        app = _fake_app(replies=[{'w1': {}}])
        with mock.patch.object(options, 'celery', _fake_celery()), \
             mock.patch.object(options, '_get_celery_app', return_value=app):
            svc = options._get_celery_service(probe=False)
        self.assertEqual(svc['state'], 'unknown')
        self.assertEqual(svc['badge_class'], 'bg-secondary')
        app.control.ping.assert_not_called()

    def test_on_demand_probe_online_persists_and_survives_reload(self):
        app = _fake_app(replies=[{'w1': {}}, {'w2': {}}])
        with mock.patch.object(options, 'celery', _fake_celery()), \
             mock.patch.object(options, '_get_celery_app', return_value=app):
            svc = options._get_celery_service(probe=True)
            self.assertEqual(svc['state'], 'online')
            app.control.ping.assert_called_once()

        # The result sticks: a later page load reads the store WITHOUT re-pinging.
        app2 = _fake_app(raise_exc=RuntimeError('must not ping on page load'))
        with mock.patch.object(options, 'celery', _fake_celery()), \
             mock.patch.object(options, '_get_celery_app', return_value=app2):
            svc2 = options._get_celery_service(probe=False)
        self.assertEqual(svc2['state'], 'online')
        app2.control.ping.assert_not_called()

    def test_on_demand_probe_offline_when_ping_raises(self):
        app = _fake_app(raise_exc=RuntimeError('broker down'))
        with mock.patch.object(options, 'celery', _fake_celery()), \
             mock.patch.object(options, '_get_celery_app', return_value=app):
            svc = options._get_celery_service(probe=True)
        self.assertEqual(svc['state'], 'offline')

    def test_on_demand_probe_offline_when_zero_workers(self):
        app = _fake_app(replies=[])
        with mock.patch.object(options, 'celery', _fake_celery()), \
             mock.patch.object(options, '_get_celery_app', return_value=app):
            svc = options._get_celery_service(probe=True)
        self.assertEqual(svc['state'], 'offline')


@override_settings(CELERY_BROKER_URL='redis://localhost:6379/0')
class CeleryHealthEndpointTests(TestCase):
    def setUp(self):
        _configured()
        cache.delete(options.CELERY_HEALTH_RESULT_KEY)
        self.url = reverse('celery_health_check')

    def test_non_staff_forbidden(self):
        User.objects.create_user('bob', password='pw12345!x')
        client = Client()
        client.login(username='bob', password='pw12345!x')
        resp = client.post(self.url, **AJAX)
        self.assertEqual(resp.status_code, 403)

    def test_get_not_allowed(self):
        su = User.objects.create_superuser('admin', 'a@a.com', 'pw12345!x')
        client = Client()
        client.force_login(su)
        resp = client.get(self.url, **AJAX)
        self.assertEqual(resp.status_code, 405)

    def test_superuser_probe_returns_status_and_persists(self):
        su = User.objects.create_superuser('admin', 'a@a.com', 'pw12345!x')
        client = Client()
        client.force_login(su)
        app = _fake_app(replies=[{'w1': {}}])
        with mock.patch.object(options, 'celery', _fake_celery()), \
             mock.patch.object(options, '_get_celery_app', return_value=app):
            resp = client.post(self.url, **AJAX)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['service']['state'], 'online')
        self.assertEqual(data['service']['badge_class'], 'bg-success')
        # Persisted for subsequent page loads.
        self.assertEqual(options._load_celery_probe_result(), (True, 1, ''))


class CeleryNotConfiguredTests(TestCase):
    """Celery is part of every Dlux stack, so its absence is a fault, not a hidden row."""

    def unconfigured(self):
        return override_settings(CELERY_BROKER_URL='', CELERY_RESULT_BACKEND='')

    def test_a_project_without_celery_settings_is_reported_offline(self):
        with self.unconfigured(), mock.patch.object(options.apps, 'is_installed', return_value=False):
            svc = options._get_celery_service()
        self.assertEqual((svc['state'], svc['note_key']), ('offline', 'service_celery_not_configured'))
        self.assertIn('will not run', svc['note'])

    def test_the_options_page_shows_the_tasks_row_with_the_reason(self):
        su = User.objects.create_superuser('admin', 'a@a.com', 'pw12345!x')
        client = Client()
        client.force_login(su)
        with self.unconfigured(), mock.patch.object(options.apps, 'is_installed', return_value=False):
            html = client.get(reverse('options_view')).content.decode()
        self.assertIn('data-dlux-celery-health', html)
        self.assertIn('Celery is not configured', html)

    def test_the_recheck_endpoint_answers_instead_of_404(self):
        su = User.objects.create_superuser('admin', 'a@a.com', 'pw12345!x')
        client = Client()
        client.force_login(su)
        with self.unconfigured(), mock.patch.object(options.apps, 'is_installed', return_value=False):
            resp = client.post(reverse('celery_health_check'), **AJAX)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['service']['state'], 'offline')

    def test_the_message_is_translated(self):
        from dlux.translations import get_strings
        for language in ('en', 'ar'):
            self.assertTrue(get_strings(language).get('service_celery_not_configured'), language)
