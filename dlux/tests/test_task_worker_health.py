"""The Options page Tasks row and its recheck endpoint read the dlux worker's heartbeats."""

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from dlux.models import DluxTaskWorker

User = get_user_model()
AJAX = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}


def _configured():
    from dlux.models import SystemSettings
    SystemSettings.objects.all().delete()
    cache.clear()
    ss = SystemSettings.load()
    ss.is_configured = True
    ss.save()
    cache.clear()


class TaskWorkerHealthEndpointTests(TestCase):
    def setUp(self):
        _configured()
        self.url = reverse('task_worker_health')

    def superuser_client(self):
        client = Client()
        client.force_login(User.objects.create_superuser('admin', 'a@a.com', 'pw12345!x'))
        return client

    def test_non_staff_forbidden(self):
        User.objects.create_user('bob', password='pw12345!x')
        client = Client()
        client.login(username='bob', password='pw12345!x')
        self.assertEqual(client.post(self.url, **AJAX).status_code, 403)

    def test_get_not_allowed(self):
        self.assertEqual(self.superuser_client().get(self.url, **AJAX).status_code, 405)

    def test_no_heartbeat_is_offline_and_a_live_worker_is_online(self):
        client = self.superuser_client()
        data = client.post(self.url, **AJAX).json()
        self.assertEqual((data['status'], data['service']['state']), ('ok', 'offline'))
        DluxTaskWorker.objects.create(id='w1', heartbeat_at=timezone.now())
        data = client.post(self.url, **AJAX).json()
        self.assertEqual((data['service']['state'], data['service']['badge_class'], data['service']['detail']),
                         ('online', 'bg-success', 'dlux_worker'))

    def test_the_options_page_shows_the_tasks_row(self):
        html = self.superuser_client().get(reverse('options_view')).content.decode()
        self.assertIn('data-dlux-task-health', html)
        self.assertIn(reverse('task_worker_health'), html)
        self.assertNotIn('celery-health', html)

    def test_the_messages_are_translated(self):
        from dlux.translations import get_strings
        for language in ('en', 'ar'):
            strings = get_strings(language)
            for key in ('service_task_worker_offline', 'service_task_workers_online',
                        'service_task_recheck', 'service_task_check_failed'):
                self.assertTrue(strings.get(key), (language, key))
