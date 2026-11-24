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


class RelayGreetingCacheTests(TestCase):
    def setUp(self):
        from dlux.utils import mail

        mail._relay_answers.clear()
        self.addCleanup(mail._relay_answers.clear)

    def test_the_settings_form_reuses_a_recent_answer(self):
        from dlux.utils import internal_smtp_relay_greeting, mail

        key = ("relay-cache.test", 2525)
        with mock.patch.object(mail, "_smtp_relay_greeting", return_value="dlux smtp relay ready") as probe:
            first = internal_smtp_relay_greeting(*key, max_age=10)
            second = internal_smtp_relay_greeting(*key, max_age=10)
        self.assertEqual(first, "dlux smtp relay ready")
        self.assertEqual(second, first)
        self.assertEqual(probe.call_count, 1)

    def test_a_negative_answer_is_reused_and_expires(self):
        from dlux.utils import internal_smtp_relay_greeting, mail

        key = ("relay-cache.test", 2526)
        with mock.patch.object(mail, "_smtp_relay_greeting", return_value=None) as probe:
            self.assertIsNone(internal_smtp_relay_greeting(*key, max_age=10))
            self.assertIsNone(internal_smtp_relay_greeting(*key, max_age=10))
            self.assertEqual(probe.call_count, 1)
            mail._relay_answers[key] = (mail.time.monotonic() - 11, None)
            self.assertIsNone(internal_smtp_relay_greeting(*key, max_age=10))
            self.assertEqual(probe.call_count, 2)

    def test_callers_without_max_age_always_probe(self):
        from dlux.utils import internal_smtp_relay_greeting, mail

        key = ("relay-cache.test", 2527)
        with mock.patch.object(mail, "_smtp_relay_greeting", return_value="220 ready") as probe:
            internal_smtp_relay_greeting(*key)
            internal_smtp_relay_greeting(*key)
        self.assertEqual(probe.call_count, 2)

    def test_the_form_asks_with_a_max_age(self):
        from dlux.forms.system_settings import SystemSettingsForm
        from dlux.utils.mail import DLUX_SMTP_RELAY_GREETING_MAX_AGE

        with mock.patch("dlux.utils.internal_smtp_relay_greeting", return_value=None) as probe:
            SystemSettingsForm()
        probe.assert_called_with(max_age=DLUX_SMTP_RELAY_GREETING_MAX_AGE)
