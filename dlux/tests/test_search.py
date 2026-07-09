from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from dlux.search import get_component_index, run_search, search_components
from dlux.system.normalizers import normalize_titlebar_config

User = get_user_model()


def _configure_system(**titlebar):
    from dlux.models import SystemSettings

    SystemSettings.objects.all().delete()
    cache.clear()
    ss = SystemSettings.load()
    ss.is_configured = True
    if titlebar:
        ss.titlebar_config = {**(ss.titlebar_config or {}), **titlebar}
    ss.save()
    cache.clear()
    return ss


class TitlebarSearchConfigTests(TestCase):
    def test_defaults(self):
        cfg = normalize_titlebar_config({})
        self.assertEqual(cfg['global_search_mode'], 'icon')
        self.assertFalse(cfg['global_search_include_data'])

    def test_invalid_mode_falls_back(self):
        self.assertEqual(normalize_titlebar_config({'global_search_mode': 'nope'})['global_search_mode'], 'icon')
        self.assertEqual(normalize_titlebar_config({'global_search_mode': 'always'})['global_search_mode'], 'always')

    def test_include_data_coerced_bool(self):
        self.assertTrue(normalize_titlebar_config({'global_search_include_data': 1})['global_search_include_data'])


class ComponentIndexTests(TestCase):
    def setUp(self):
        _configure_system()

    def test_index_has_settings_and_pages(self):
        index = get_component_index('en')
        types = {entry['type'] for entry in index}
        self.assertIn('setting', types)
        self.assertIn('page', types)

    def test_settings_entries_are_step_deeplinked_modals(self):
        index = get_component_index('en')
        settings_entries = [entry for entry in index if entry['type'] == 'setting']
        self.assertEqual(len(settings_entries), 12)
        for entry in settings_entries:
            self.assertEqual(entry['mode'], 'modal')
            self.assertIn('?step=', entry['url'])
            self.assertIn('SystemSettings', entry['url'])

    def test_security_section_maps_to_step_2(self):
        index = get_component_index('en')
        security = next(e for e in index if e['type'] == 'setting' and 'Security' in e['label'])
        self.assertIn('?step=2', security['url'])

    def test_index_includes_options_cards(self):
        index = get_component_index('en')
        option_urls = [e['url'] for e in index if e['type'] == 'option']
        self.assertTrue(option_urls)
        self.assertTrue(all('/sys/options/#dlux-option-' in url for url in option_urls))
        labels = {e['label'] for e in index if e['type'] == 'option'}
        self.assertIn('Color Theme', labels)


class ArabicLocalizationTests(TestCase):
    def setUp(self):
        _configure_system()
        self.superuser = User.objects.create_superuser('root', 'r@x.com', 'pw12345!')

    def test_arabic_index_labels_are_translated(self):
        index = get_component_index('ar')
        setting_labels = [e['label'] for e in index if e['type'] == 'setting']
        # Access & Security in Arabic — the index must not be English.
        self.assertIn('الوصول والأمان', setting_labels)

    def test_arabic_query_matches_arabic_labels(self):
        results = search_components(self.superuser, 'الأمان', lang_code='ar')
        self.assertTrue(any(r['type'] == 'setting' and 'أمان' in r['label'] for r in results))

    def test_endpoint_uses_user_language_over_accept_language_header(self):
        # The reported bug: an English browser (Accept-Language: en) on an
        # Arabic-configured account got English results, because Django's
        # LocaleMiddleware runs before auth and set LANGUAGE_CODE='en'.
        # DluxMiddleware must re-activate the profile language after auth.
        profile = self.superuser.profile
        profile.preferences = {**(profile.preferences or {}), 'language': 'ar'}
        profile.save()
        cache.clear()
        client = Client()
        client.force_login(self.superuser)
        payload = client.get('/search/?q=الأمان', HTTP_ACCEPT_LANGUAGE='en-US,en;q=0.9').json()
        setting = next((g for g in payload['groups'] if g['type'] == 'setting'), None)
        self.assertIsNotNone(setting)
        self.assertTrue(any('أمان' in item['label'] for item in setting['items']))

    def test_middleware_reactivates_profile_language(self):
        # DluxMiddleware sets request.LANGUAGE_CODE + activates translation to the
        # Dlux-resolved language, so any page render agrees with the UI language.
        from django.utils import translation
        from dlux.middleware import DluxMiddleware
        from django.test import RequestFactory

        profile = self.superuser.profile
        profile.preferences = {**(profile.preferences or {}), 'language': 'ar'}
        profile.save()
        cache.clear()
        request = RequestFactory().get('/', HTTP_ACCEPT_LANGUAGE='en')
        request.user = self.superuser

        class _DummySession(dict):
            pass
        request.session = _DummySession()

        DluxMiddleware(lambda r: None)._activate_display_language(request)
        try:
            self.assertEqual(request.LANGUAGE_CODE, 'ar')
            self.assertEqual(translation.get_language(), 'ar')
        finally:
            translation.deactivate()


class SearchRankingAndPermissionTests(TestCase):
    def setUp(self):
        _configure_system()
        self.superuser = User.objects.create_superuser('boss', 'boss@x.com', 'pw12345!')
        self.plain = User.objects.create_user('joe', 'joe@x.com', 'pw12345!')

    def test_short_query_returns_nothing(self):
        self.assertEqual(search_components(self.superuser, 'a'), [])

    def test_superuser_finds_settings_sections(self):
        groups = run_search(self.superuser, 'security', lang_code='en')
        setting = next((g for g in groups if g['type'] == 'setting'), None)
        self.assertIsNotNone(setting)
        self.assertTrue(any('Security' in item['label'] for item in setting['items']))

    def test_non_superuser_gets_no_settings(self):
        groups = run_search(self.plain, 'security', lang_code='en')
        self.assertFalse(any(g['type'] == 'setting' for g in groups))

    def test_keyword_hint_matches_field_level_term(self):
        # 'inactivity' is a keyword of the Security section (a field, not a section name).
        results = search_components(self.superuser, 'inactivity', lang_code='en')
        self.assertTrue(any(r['type'] == 'setting' and 'Security' in r['label'] for r in results))

    def test_exact_prefix_outranks_substring(self):
        results = search_components(self.superuser, 'back', lang_code='en')
        # 'Backups' (prefix) should appear before any entry merely containing 'back'.
        labels = [r['label'] for r in results]
        self.assertTrue(labels)
        self.assertTrue(labels[0].lower().startswith('back'))


class DataProviderTests(TestCase):
    def setUp(self):
        _configure_system(global_search_include_data=True)
        self.superuser = User.objects.create_superuser('alice_admin', 'a@x.com', 'pw12345!')

    def test_data_search_finds_user_records(self):
        from dlux.search import search_data
        results = search_data(self.superuser, 'alice_admin')
        self.assertTrue(any('alice_admin' in item['label'] for item in results))

    def test_data_search_respects_view_permission(self):
        from dlux.search import search_data
        nobody = User.objects.create_user('bob', 'b@x.com', 'pw12345!')
        # A plain user without auth.view_user must not surface other user records.
        results = search_data(nobody, 'alice_admin')
        self.assertFalse(any('alice_admin' in item['label'] for item in results))


class SearchEndpointTests(TestCase):
    def setUp(self):
        _configure_system(global_search_mode='icon', global_search_include_data=True)
        self.superuser = User.objects.create_superuser('root_admin', 'r@x.com', 'pw12345!')
        self.client = Client()

    def test_requires_login(self):
        response = self.client.get('/search/?q=security')
        self.assertIn(response.status_code, (302, 301))

    def test_returns_grouped_json(self):
        self.client.force_login(self.superuser)
        response = self.client.get('/search/?q=security')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn('groups', payload)
        self.assertTrue(any(g['type'] == 'setting' for g in payload['groups']))

    def test_data_gated_on_param_and_setting(self):
        self.client.force_login(self.superuser)
        # With ?data=1 and the setting on → data group present.
        with_data = self.client.get('/search/?q=root_admin&data=1').json()['groups']
        self.assertTrue(any(g['type'] == 'data' for g in with_data))
        # Without ?data=1 → no data group even though the setting is on.
        without = self.client.get('/search/?q=root_admin').json()['groups']
        self.assertFalse(any(g['type'] == 'data' for g in without))

    def test_disabled_mode_returns_disabled(self):
        _configure_system(global_search_mode='disabled')
        self.client.force_login(self.superuser)
        payload = self.client.get('/search/?q=security').json()
        self.assertEqual(payload['groups'], [])
        self.assertTrue(payload.get('disabled'))
