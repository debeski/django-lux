"""The client strings table served as a cached script, and the per-request
``ScopeSettings`` memo.

Every ``base.html`` page used to embed the whole merged table with Django's
``json_script``, which writes each Arabic character as a six-byte escape: most of
an Arabic page was its strings. Pages now name ``/sys/api/strings/<lang>.<version>.js``.
"""

import json
import re

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.template import Context, Template
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from dlux.middleware import _thread_locals
from dlux.models import Profile, Scope, ScopeSettings, SystemSettings
from dlux.translations import get_strings
from dlux.translations.runtime import client_strings_version
from dlux.utils import get_scope_settings, is_scope_enabled

SCRIPT_URL = re.compile(r'<script src="(/sys/api/strings/(\w+)\.([0-9a-f]{16})\.js)" nonce="([^"]*)"></script>')


def _configure(**fields):
    # SystemSettings.load() is served from the cache, which outlives a test's
    # rolled-back transaction.
    cache.clear()
    record = SystemSettings.load()
    record.is_configured = True
    for name, value in fields.items():
        setattr(record, name, value)
    record.save()


def _table(response):
    body = b''.join(response.streaming_content) if response.streaming else response.content
    text = body.decode('utf-8')
    match = re.fullmatch(r'window\.DLUX_STRINGS=JSON\.parse\((.*)\);\n', text, re.S)
    assert match, text[:200]
    return json.loads(json.loads(match.group(1))), text


class StringsScriptPageTests(TestCase):
    def setUp(self):
        _configure()

    def _page(self, language):
        session = self.client.session
        session['lang'] = language
        session.save()
        return self.client.get(reverse('login')).content.decode('utf-8')

    def test_page_names_the_script_instead_of_embedding_the_table(self):
        for language in ('en', 'ar'):
            with self.subTest(language=language):
                html = self._page(language)
                self.assertNotIn('dlux-strings-data', html)
                match = SCRIPT_URL.search(html)
                self.assertIsNotNone(match)
                self.assertEqual(match.group(2), language)
                self.assertEqual(match.group(3), client_strings_version(language, {}))
                # It runs before base_head.js, which every other script relies on.
                self.assertLess(html.index(match.group(1)), html.index('dlux/base/js/base_head.js'))

    def test_arabic_page_no_longer_carries_the_table(self):
        html = self._page('ar')
        # A string only scripts use, so only the table would carry it.
        self.assertNotIn(get_strings('ar')['assist_bar_legend'], html)
        self.assertLess(len(html.encode('utf-8')), 100_000)


class StringsScriptEndpointTests(TestCase):
    def setUp(self):
        _configure()

    def _url(self, language, version=None):
        version = version or client_strings_version(language, {})
        return reverse('dlux_strings', kwargs={'lang': language, 'version': version})

    def test_anyone_gets_the_table_with_immutable_caching(self):
        response = self.client.get(self._url('ar'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/javascript; charset=utf-8')
        self.assertEqual(response['Cache-Control'], 'public, max-age=31536000, immutable')
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        self.assertNotIn('Cookie', response.get('Vary', ''))
        self.assertFalse(response.cookies)
        table, text = _table(response)
        self.assertEqual(table, get_strings('ar', overrides={}))
        # UTF-8 text, not \\uXXXX escapes.
        self.assertIn(get_strings('ar')['login'], text)
        self.assertNotIn('\\u06', text)

    def test_stale_version_gets_current_table_without_long_caching(self):
        response = self.client.get(self._url('en', version='0' * 16))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'no-cache')
        self.assertEqual(_table(response)[0], get_strings('en', overrides={}))

    def test_unknown_language_is_not_found(self):
        self.assertEqual(self.client.get(self._url('xx')).status_code, 404)

    def test_served_before_setup_and_to_signed_in_users(self):
        _configure(is_configured=False)
        self.assertEqual(self.client.get(self._url('en')).status_code, 200)
        user = get_user_model().objects.create_user('reader', 'r@example.com', 'pw')
        self.client.force_login(user)
        self.assertEqual(self.client.get(self._url('en')).status_code, 200)

    def test_an_override_changes_the_version_and_the_table(self):
        before = client_strings_version('en', {})
        _configure(translations_override={'en': {'login': 'Enter the archive'}})
        session = self.client.session
        session['lang'] = 'en'
        session.save()
        html = self.client.get(reverse('login')).content.decode('utf-8')
        version = SCRIPT_URL.search(html).group(3)
        self.assertNotEqual(version, before)
        response = self.client.get(self._url('en', version))
        self.assertEqual(response['Cache-Control'], 'public, max-age=31536000, immutable')
        self.assertEqual(_table(response)[0]['login'], 'Enter the archive')
        # The other language's table, and so its version, is untouched.
        self.assertEqual(
            client_strings_version('ar', {'en': {'login': 'Enter the archive'}}),
            client_strings_version('ar', {}),
        )


class JsonScriptUtf8Tests(TestCase):
    def test_keeps_text_as_utf8_and_escapes_markup(self):
        rendered = Template('{% load dlux_tags %}{{ value|json_script_utf8:"data" }}').render(
            Context({'value': {'k': 'سجل </script><b>&'}})
        )
        self.assertTrue(rendered.startswith('<script id="data" type="application/json">'))
        self.assertIn('سجل', rendered)
        self.assertNotIn('</script><b>', rendered)
        self.assertIn('\\u003C/script\\u003E\\u003Cb\\u003E\\u0026', rendered)
        payload = rendered.split('>', 1)[1].rsplit('</script>', 1)[0]
        self.assertEqual(json.loads(payload), {'k': 'سجل </script><b>&'})


class ScopeSettingsMemoTests(TestCase):
    def setUp(self):
        ScopeSettings.objects.update_or_create(pk=1, defaults={'is_enabled': True})
        self.scope = Scope.objects.create(name='North')
        self.user = get_user_model().objects.create_user('clerk', 'c@example.com', 'pw')
        profile = self.user.profile
        profile.scope = self.scope
        profile.save()
        self.request = RequestFactory().get('/')
        self.request.user = self.user
        _thread_locals.request = self.request
        _thread_locals.user = self.user

    def tearDown(self):
        for name in ('request', 'user'):
            if hasattr(_thread_locals, name):
                delattr(_thread_locals, name)

    def test_scoped_querysets_read_the_row_once_per_request(self):
        with CaptureQueriesContext(connection) as queries:
            for _ in range(16):
                list(Profile.objects.all())
            self.assertTrue(is_scope_enabled())
        reads = [q for q in queries.captured_queries if 'dlux_scopesettings' in q['sql']]
        self.assertEqual(len(reads), 1)

    def test_saving_the_row_drops_the_memo(self):
        self.assertTrue(is_scope_enabled())
        row = ScopeSettings.load()
        row.is_enabled = False
        row.save()
        self.assertFalse(is_scope_enabled())

    def test_without_a_request_every_call_reads_the_row(self):
        del _thread_locals.request
        with CaptureQueriesContext(connection) as queries:
            get_scope_settings()
            get_scope_settings()
        self.assertEqual(sum('dlux_scopesettings' in q['sql'] for q in queries.captured_queries), 2)
