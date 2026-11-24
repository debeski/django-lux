"""Long or unbounded work kept off web's request threads."""
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings


class ApiStatusProbeTests(TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_no_url_means_no_row(self):
        from dlux.utils.api_status import cached_api_status

        self.assertIsNone(cached_api_status())

    @override_settings(DLUX_API_STATUS_URL="http://api.internal/health")
    def test_web_never_opens_the_connection_and_queues_the_worker(self):
        from dlux.utils.api_status import cached_api_status

        with mock.patch("urllib.request.urlopen") as urlopen, \
                mock.patch("dlux.taskrunner.worker_alive", return_value=True), \
                mock.patch("dlux.taskrunner.enqueue") as enqueue:
            first = cached_api_status()
            second = cached_api_status()
        urlopen.assert_not_called()
        self.assertEqual(first["state"], "unknown")
        self.assertEqual(first["note_key"], "service_api_pending")
        self.assertEqual(second["state"], "unknown")
        enqueue.assert_called_once_with("dlux.tasks.api_status_probe")

    @override_settings(DLUX_API_STATUS_URL="http://api.internal/health", DEBUG=False)
    def test_without_a_worker_it_says_so(self):
        from dlux.utils.api_status import cached_api_status

        with mock.patch("urllib.request.urlopen") as urlopen, \
                mock.patch("dlux.taskrunner.worker_alive", return_value=False):
            status = cached_api_status()
        urlopen.assert_not_called()
        self.assertEqual(status["note_key"], "service_api_no_worker")

    @override_settings(DLUX_API_STATUS_URL="http://api.internal/health")
    def test_the_worker_result_is_what_options_shows(self):
        from dlux.jobs import api_status_probe
        from dlux.utils.api_status import cached_api_status

        response = mock.MagicMock(status=200)
        response.__enter__.return_value = response
        with mock.patch("urllib.request.urlopen", return_value=response):
            api_status_probe.call()
        with mock.patch("urllib.request.urlopen") as urlopen, \
                mock.patch("dlux.taskrunner.enqueue") as enqueue:
            status = cached_api_status()
        urlopen.assert_not_called()
        enqueue.assert_not_called()
        self.assertEqual(status["state"], "online")

    def test_a_changed_url_does_not_reuse_the_old_answer(self):
        from dlux.utils import api_status

        cache.set(api_status.CACHE_KEY, {"state": "online", "url": "http://old/", "checked_at": 9e12})
        with override_settings(DLUX_API_STATUS_URL="http://new/"), \
                mock.patch("dlux.taskrunner.worker_alive", return_value=True), \
                mock.patch("dlux.taskrunner.enqueue"):
            self.assertEqual(api_status.cached_api_status()["state"], "unknown")
