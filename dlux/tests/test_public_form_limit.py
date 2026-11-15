from dlux.tests.harness import setup_test_environment

setup_test_environment()

import json
import time
from unittest import mock

from django.core.cache import DEFAULT_CACHE_ALIAS, caches
from django.core.cache.backends.base import BaseCache
from django.core.cache.backends.locmem import LocMemCache
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.utils.decorators import method_decorator
from django.views import View

from dlux.utils import ratelimit
from dlux.utils.ratelimit import (
    LIMIT_ADDRESS,
    LIMIT_TOTAL,
    PublicFormLimitResult,
    count_public_form_post,
    public_form_limit,
    rate_limited_response,
)


def _ok(request, *args, **kwargs):
    return HttpResponse('ok')


class _LimitTestCase(TestCase):
    def setUp(self):
        self.cache = caches[DEFAULT_CACHE_ALIAS]
        self.cache.clear()
        self.addCleanup(self.cache.clear)
        self.logger = self.enterContext(mock.patch.object(ratelimit, 'logger'))
        self.factory = RequestFactory()

    def post(self, address='198.51.100.7', **extra):
        return self.factory.post('/form/', {'comment': 'hi'}, REMOTE_ADDR=address, **extra)

    def statuses(self, view, requests):
        return [view(request).status_code for request in requests]

    def limit_keys(self):
        return [key for key in self.cache._cache if ratelimit.CACHE_PREFIX in key]


class PerAddressAndTotalLimitTests(_LimitTestCase):
    def test_per_address_limit_refuses_only_that_sender(self):
        view = public_form_limit('complaint', per_address=3, total=100)(_ok)
        self.assertEqual(self.statuses(view, [self.post() for _ in range(4)]), [200, 200, 200, 429])
        self.assertEqual(view(self.post('198.51.100.8')).status_code, 200)

        result = count_public_form_post(self.post(), 'complaint', per_address=3, total=100)
        self.assertEqual((result.allowed, result.limit), (False, LIMIT_ADDRESS))

    def test_total_limit_refuses_every_sender_once_reached(self):
        view = public_form_limit('review', per_address=10, total=3)(_ok)
        addresses = ['198.51.100.1', '198.51.100.2', '198.51.100.3', '198.51.100.4']
        self.assertEqual(self.statuses(view, [self.post(a) for a in addresses]), [200, 200, 200, 429])

        result = count_public_form_post(self.post('198.51.100.5'), 'review', per_address=10, total=3)
        self.assertEqual((result.allowed, result.limit), (False, LIMIT_TOTAL))

    def test_refused_posts_do_not_spend_the_shared_budget(self):
        view = public_form_limit('review', per_address=1, total=2)(_ok)
        self.assertEqual(self.statuses(view, [self.post('198.51.100.1') for _ in range(5)]), [200, 429, 429, 429, 429])
        self.assertEqual(view(self.post('198.51.100.2')).status_code, 200)
        self.assertEqual(view(self.post('198.51.100.3')).status_code, 429)

    def test_buckets_count_separately(self):
        review = public_form_limit('review', per_address=1)(_ok)
        complaint = public_form_limit('complaint', per_address=1)(_ok)
        self.assertEqual(review(self.post()).status_code, 200)
        self.assertEqual(complaint(self.post()).status_code, 200)
        self.assertEqual(review(self.post()).status_code, 429)

    def test_none_turns_a_limit_off(self):
        view = public_form_limit('open', per_address=None, total=None)(_ok)
        self.assertEqual(set(self.statuses(view, [self.post() for _ in range(20)])), {200})
        self.assertEqual(self.limit_keys(), [])

    def test_only_listed_methods_are_counted(self):
        view = public_form_limit('complaint', per_address=1)(_ok)
        for _ in range(5):
            self.assertEqual(view(self.factory.get('/form/', REMOTE_ADDR='198.51.100.7')).status_code, 200)
        self.assertEqual(self.statuses(view, [self.post(), self.post()]), [200, 429])

    def test_class_based_view_through_method_decorator(self):
        @method_decorator(public_form_limit('contact', per_address=1), name='dispatch')
        class ContactView(View):
            def post(self, request):
                return HttpResponse('sent')

        view = ContactView.as_view()
        self.assertEqual(self.statuses(view, [self.post(), self.post()]), [200, 429])


class ClientAddressTests(_LimitTestCase):
    def test_uses_the_configured_client_ip_resolution(self):
        # Default policy: X-Forwarded-For with one trusted proxy hop.
        view = public_form_limit('complaint', per_address=1)(_ok)
        behind_proxy = [
            self.post('172.18.0.5', HTTP_X_FORWARDED_FOR='203.0.113.5'),
            self.post('172.18.0.5', HTTP_X_FORWARDED_FOR='203.0.113.6'),
            self.post('172.18.0.5', HTTP_X_FORWARDED_FOR='203.0.113.5'),
        ]
        self.assertEqual(self.statuses(view, behind_proxy), [200, 200, 429])

    def test_ipv6_counts_per_slash_64(self):
        view = public_form_limit('complaint', per_address=1)(_ok)
        self.assertEqual(view(self.post('2001:db8:1:2::1')).status_code, 200)
        self.assertEqual(view(self.post('2001:db8:1:2:ffff:ffff:ffff:ffff')).status_code, 429)
        self.assertEqual(view(self.post('2001:db8:1:3::1')).status_code, 200)

    def test_ipv4_mapped_ipv6_counts_as_ipv4(self):
        view = public_form_limit('complaint', per_address=1)(_ok)
        self.assertEqual(view(self.post('198.51.100.9')).status_code, 200)
        self.assertEqual(view(self.post('::ffff:198.51.100.9')).status_code, 429)

    def test_cache_holds_no_raw_address_and_expires_with_the_window(self):
        view = public_form_limit('complaint', per_address=2, total=5, window=60)(_ok)
        view(self.post('198.51.100.77'))
        view(self.post('2001:db8:1:2::77'))
        keys = self.limit_keys()
        self.assertEqual(len(keys), 3)
        for key in keys:
            self.assertRegex(key, r'^:1:dlux:formlimit:complaint:(a:[0-9a-f]{32}|t):\d+$')
            self.assertLessEqual(self.cache._expire_info[key] - time.time(), 60)

    def test_address_digest_is_keyed(self):
        digest = ratelimit._address_digest('198.51.100.7')
        with override_settings(SECRET_KEY='another-secret-key-for-the-digest-test-0123456789'):
            self.assertNotEqual(ratelimit._address_digest('198.51.100.7'), digest)

    def test_logs_never_name_the_address(self):
        view = public_form_limit('complaint', per_address=1)(_ok)
        for _ in range(4):
            view(self.post('198.51.100.66'))
        self.assertEqual(self.logger.warning.call_count, 1)
        self.assertNotIn('198.51.100.66', repr(self.logger.warning.call_args))


class WindowTests(_LimitTestCase):
    def at(self, now):
        return mock.patch.object(ratelimit, 'time', mock.Mock(time=mock.Mock(return_value=now)))

    def test_counters_reset_when_the_window_ends(self):
        view = public_form_limit('complaint', per_address=1, window=60)(_ok)
        with self.at(6000.0):
            self.assertEqual(self.statuses(view, [self.post(), self.post()]), [200, 429])
        with self.at(6059.5):
            self.assertEqual(view(self.post()).status_code, 429)
        with self.at(6060.0):
            self.assertEqual(view(self.post()).status_code, 200)

    def test_retry_after_counts_to_the_window_end(self):
        with self.at(6015.2):
            result = count_public_form_post(self.post(), 'complaint', window=60)
        self.assertEqual(result.retry_after, 45)

    def test_generic_incr_keeps_the_window_ttl(self):
        class GenericIncrCache(LocMemCache):
            incr = BaseCache.incr

        backend = GenericIncrCache('dlux-generic-incr-test', {})
        self.addCleanup(backend.clear)
        for expected in (1, 2, 3):
            self.assertEqual(ratelimit._increment(backend, 'k', 30), expected)
        self.assertLessEqual(backend._expire_info[backend.make_key('k')] - time.time(), 30)


class ResponseTests(_LimitTestCase):
    def refused(self):
        return PublicFormLimitResult(False, LIMIT_ADDRESS, 120)

    def test_default_response_is_translated_text_with_retry_after(self):
        response = rate_limited_response(self.post(), self.refused())
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response['Retry-After'], '120')
        self.assertTrue(response['Content-Type'].startswith('text/plain'))
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(response.content.decode(), 'Too many submissions. Please try again later.')

    def test_default_response_follows_the_request_language(self):
        request = self.post()
        request.session = {'lang': 'ar'}
        response = rate_limited_response(request, self.refused())
        self.assertEqual(response.content.decode(), 'عدد المحاولات كبير. الرجاء المحاولة لاحقاً.')

    def test_script_requests_get_json(self):
        request = self.post(HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        response = rate_limited_response(request, self.refused())
        self.assertEqual(response.status_code, 429)
        self.assertEqual(json.loads(response.content)['status'], 'error')

    def test_on_limited_renders_the_project_response(self):
        seen = {}

        def on_limited(request, result, slug):
            seen.update(result=result, slug=slug)
            return HttpResponse('form with notice', status=429)

        def view(request, slug):
            return HttpResponse(slug)

        limited = public_form_limit('review', per_address=1, on_limited=on_limited)(view)
        self.assertEqual(limited(self.post(), slug='water').status_code, 200)
        response = limited(self.post(), slug='water')
        self.assertEqual((response.status_code, response.content), (429, b'form with notice'))
        self.assertEqual((seen['slug'], seen['result'].limit), ('water', LIMIT_ADDRESS))


class SettingsOverrideTests(_LimitTestCase):
    @override_settings(DLUX_PUBLIC_FORM_LIMITS={'complaint': {'per_address': 1}})
    def test_settings_override_the_code_values(self):
        view = public_form_limit('complaint', per_address=50)(_ok)
        self.assertEqual(self.statuses(view, [self.post(), self.post()]), [200, 429])

    @override_settings(DLUX_PUBLIC_FORM_LIMITS={'complaint': {'per_address': None, 'total': None}})
    def test_settings_can_turn_a_bucket_off(self):
        view = public_form_limit('complaint', per_address=1, total=1)(_ok)
        self.assertEqual(set(self.statuses(view, [self.post() for _ in range(5)])), {200})

    @override_settings(DLUX_PUBLIC_FORM_LIMITS={'complaint': {'per_address': 0, 'window': 'soon'}})
    def test_invalid_override_keeps_the_code_values(self):
        view = public_form_limit('complaint', per_address=2, window=60)(_ok)
        self.assertEqual(self.statuses(view, [self.post() for _ in range(3)]), [200, 200, 429])
        self.assertTrue(self.logger.warning.called)


class FailureTests(_LimitTestCase):
    def test_unreachable_cache_lets_the_post_through(self):
        view = public_form_limit('complaint', per_address=1)(_ok)
        with mock.patch.object(ratelimit, '_increment', side_effect=ConnectionError('redis down')):
            self.assertEqual(self.statuses(view, [self.post(), self.post()]), [200, 200])
        self.assertTrue(self.logger.exception.called)

    def test_invalid_arguments_fail_at_decoration(self):
        for kwargs in (
            {'bucket': 'Has Spaces'},
            {'bucket': ''},
            {'bucket': 'x' * 65},
            {'bucket': 'ok', 'per_address': 0},
            {'bucket': 'ok', 'total': True},
            {'bucket': 'ok', 'window': 0},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                public_form_limit(**kwargs)
