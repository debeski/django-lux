"""A cached singleton row never outlives the row in the database.

A save made while the cache was down could neither refresh nor drop the cached
row, so once the cache answered again the pre-save row was served for 24 hours.
"""

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from contextlib import contextmanager
from unittest import mock

from django.core.cache import cache
from django.db import transaction
from django.test import TestCase, TransactionTestCase

from dlux.resilient_cache import CacheUnavailable


@contextmanager
def cache_outage():
    """Every cache operation fails as a paused Redis does behind the breaker."""
    def down(*args, **kwargs):
        raise CacheUnavailable('cache is down')

    with mock.patch.object(cache, 'get', side_effect=down), \
            mock.patch.object(cache, 'set', side_effect=down), \
            mock.patch.object(cache, 'delete', side_effect=down):
        yield


def _settings():
    from dlux.models import SystemSettings

    return SystemSettings


class SaveDuringCacheOutageTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        SystemSettings = _settings()
        row = SystemSettings.load()
        row.home_url = '/before/'
        row.save()
        self.assertEqual(SystemSettings.cached().home_url, '/before/')

    def test_a_save_during_an_outage_is_served_once_the_cache_answers_again(self):
        SystemSettings = _settings()
        with cache_outage():
            row = SystemSettings.load()
            row.home_url = '/after/'
            row.save()
            self.assertEqual(SystemSettings.load().home_url, '/after/')

        # The cache came back with the row it held before the outage.
        self.assertEqual(cache.get(SystemSettings.entry_key())['fields']['home_url'], '/before/')
        self.assertEqual(SystemSettings.load().home_url, '/after/')
        self.assertEqual(SystemSettings.cached().home_url, '/after/', 'the stale entry was replaced')

    def test_an_older_save_written_to_the_cache_last_is_not_served(self):
        """Two saves race: the earlier one's cache write lands after the later one's."""
        SystemSettings = _settings()
        first = SystemSettings.load()
        first.home_url = '/first/'
        first.save()
        stale_payload = cache.get(SystemSettings.entry_key())

        second = SystemSettings.load()
        second.home_url = '/second/'
        second.save()
        cache.set(SystemSettings.entry_key(), stale_payload)

        self.assertEqual(SystemSettings.load().home_url, '/second/')

    def test_an_unchanged_row_is_served_from_the_cache(self):
        SystemSettings = _settings()
        SystemSettings.load()
        with mock.patch.object(SystemSettings.objects, 'get_or_create', side_effect=AssertionError('read the row')):
            self.assertEqual(SystemSettings.load().home_url, '/before/')

    def test_update_fields_saves_change_the_revision(self):
        SystemSettings = _settings()
        before = SystemSettings.objects.get(pk=1).cache_revision
        row = SystemSettings.load()
        with cache_outage():
            row.home_url = '/partial/'
            row.save(update_fields=['home_url'])
        self.assertNotEqual(SystemSettings.objects.get(pk=1).cache_revision, before)
        self.assertEqual(SystemSettings.load().home_url, '/partial/')


class RolledBackSaveTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def test_a_rolled_back_save_is_not_served_from_the_cache(self):
        SystemSettings = _settings()
        row = SystemSettings.load()
        row.home_url = '/kept/'
        row.save()

        class Abort(Exception):
            pass

        try:
            with transaction.atomic():
                row = SystemSettings.load()
                row.home_url = '/rolled-back/'
                row.save()
                raise Abort
        except Abort:
            pass

        self.assertEqual(cache.get(SystemSettings.entry_key())['fields']['home_url'], '/rolled-back/')
        self.assertEqual(SystemSettings.load().home_url, '/kept/')
