from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, RequestFactory, TestCase, override_settings

from dlux.system.constants import (
    SETUP_STEP_COUNT,
    SETUP_STEP_EMAIL,
    SETUP_STEP_HOMEPAGE,
    SETUP_STEP_LAYOUT,
    SETUP_STEP_SEARCH,
    SETUP_STEP_SECURITY,
)
from dlux.search import get_component_index, run_search, search_components
from dlux.system.normalizers import normalize_search_config, normalize_titlebar_config
from dlux.utils import get_system_config

User = get_user_model()


def _configure_system(search_config=None, **titlebar):
    from dlux.models import SystemSettings

    SystemSettings.objects.all().delete()
    cache.clear()
    ss = SystemSettings.load()
    ss.is_configured = True
    if titlebar:
        ss.titlebar_config = {**(ss.titlebar_config or {}), **titlebar}
    if search_config is not None:
        ss.search_config = search_config
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

    def test_canonical_search_config_accepts_legacy_keys(self):
        cfg = normalize_search_config({
            'global_search_mode': 'disabled',
            'global_search_include_data': True,
        })
        self.assertFalse(cfg['enabled'])
        self.assertEqual(cfg['display_mode'], 'icon')
        self.assertTrue(cfg['include_data'])


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
        self.assertEqual(len(settings_entries), SETUP_STEP_COUNT)
        for entry in settings_entries:
            self.assertEqual(entry['mode'], 'modal')
            self.assertIn('?step=', entry['url'])
            self.assertIn('SystemSettings', entry['url'])

    def test_security_section_maps_to_step_2(self):
        index = get_component_index('en')
        security = next(e for e in index if e['type'] == 'setting' and 'Security' in e['label'])
        self.assertIn(f'?step={SETUP_STEP_SECURITY}', security['url'])

    def test_layout_section_maps_to_its_wizard_step(self):
        index = get_component_index('en')
        layout = next(e for e in index if e['type'] == 'setting' and e['label'] == 'Layout')
        self.assertIn(f'?step={SETUP_STEP_LAYOUT}', layout['url'])

    def test_email_section_deeplinks_to_its_own_step(self):
        index = get_component_index('en')
        email = next(e for e in index if e['type'] == 'setting' and e['label'] == 'Email')
        self.assertIn(f'?step={SETUP_STEP_EMAIL}', email['url'])

    def test_homepage_and_search_have_dedicated_steps(self):
        index = get_component_index('en')
        homepage = next(e for e in index if e['type'] == 'setting' and e['label'] == 'Homepage')
        search = next(e for e in index if e['type'] == 'setting' and e['label'] == 'Global Search')
        self.assertIn(f'?step={SETUP_STEP_HOMEPAGE}', homepage['url'])
        self.assertIn(f'?step={SETUP_STEP_SEARCH}', search['url'])

    def test_index_includes_options_cards(self):
        index = get_component_index('en')
        option_urls = [e['url'] for e in index if e['type'] == 'option']
        self.assertTrue(option_urls)
        self.assertTrue(all('/sys/options/#dlux-option-' in url for url in option_urls))
        labels = {e['label'] for e in index if e['type'] == 'option'}
        self.assertIn('Color Theme', labels)


class AppCardSearchTests(TestCase):
    """App cards are resolved per request, outside the cached component index."""

    def setUp(self):
        from dlux import options

        _configure_system()
        self.factory = RequestFactory()
        self.superuser = User.objects.create_superuser('boss', 'boss@x.com', 'pw12345!')
        self.plain = User.objects.create_user('joe', 'joe@x.com', 'pw12345!')
        options.register_card(
            id='probe.widget',
            title=lambda request: 'Widget Bridge',
            template_name='options_test_card.html',
            search_keywords=('gadget', 'أداة'),
        )
        options.register_card(
            id='probe.secret',
            title='Secret Widget',
            template_name='options_test_card.html',
            superuser_only=True,
        )
        self.addCleanup(options.unregister_card, 'probe.widget')
        self.addCleanup(options.unregister_card, 'probe.secret')

    def _labels(self, user, query):
        request = self.factory.get('/')
        request.user = user
        results = search_components(user, query, lang_code='en', request=request)
        return [r['label'] for r in results]

    def test_card_is_found_by_title_and_deeplinks_to_its_id(self):
        request = self.factory.get('/')
        request.user = self.superuser
        results = search_components(self.superuser, 'widget bridge', lang_code='en', request=request)
        entry = next(r for r in results if r['label'] == 'Widget Bridge')
        self.assertEqual(entry['type'], 'option')
        self.assertEqual(entry['url'], '/sys/options/#dlux-option-probe.widget')

    def test_search_keywords_match(self):
        self.assertIn('Widget Bridge', self._labels(self.superuser, 'gadget'))
        self.assertIn('Widget Bridge', self._labels(self.superuser, 'أداة'))

    def test_superuser_only_card_is_hidden_from_others(self):
        self.assertIn('Secret Widget', self._labels(self.superuser, 'secret'))
        self.assertNotIn('Secret Widget', self._labels(self.plain, 'secret'))
        self.assertIn('Widget Bridge', self._labels(self.plain, 'gadget'))

    def test_no_request_yields_no_app_cards(self):
        self.assertEqual(search_components(self.superuser, 'gadget', lang_code='en'), [])


class ArabicLocalizationTests(TestCase):
    def setUp(self):
        _configure_system()
        self.superuser = User.objects.create_superuser('root', 'r@x.com', 'pw12345!')

    @staticmethod
    def _setting_at_step(index, step):
        return next(
            entry
            for entry in index
            if entry['type'] == 'setting' and entry['url'].endswith(f'?step={step}')
        )

    def test_arabic_index_labels_are_translated(self):
        arabic = self._setting_at_step(get_component_index('ar'), 2)
        english = self._setting_at_step(get_component_index('en'), 2)

        self.assertNotEqual(arabic['label'], english['label'])

    def test_arabic_theme_and_layout_labels_are_distinct_and_step_deep_linked(self):
        index = get_component_index('ar')
        themes = self._setting_at_step(index, 8)
        layout = self._setting_at_step(index, 9)

        self.assertNotEqual(themes['label'], layout['label'])
        self.assertTrue(themes['label'])
        self.assertTrue(layout['label'])

    def test_arabic_query_matches_arabic_labels(self):
        security = self._setting_at_step(get_component_index('ar'), 2)
        results = search_components(self.superuser, security['label'], lang_code='ar')
        self.assertTrue(any(r['type'] == 'setting' and r['url'] == security['url'] for r in results))

    def test_endpoint_uses_user_language_over_accept_language_header(self):
        # The reported bug: an English browser (Accept-Language: en) on an
        # Arabic-configured account got English results, because Django's
        # LocaleMiddleware runs before auth and set LANGUAGE_CODE='en'.
        # DluxMiddleware must re-activate the profile language after auth.
        profile = self.superuser.profile
        profile.preferences = {**(profile.preferences or {}), 'language': 'ar'}
        profile.save()
        cache.clear()
        security = self._setting_at_step(get_component_index('ar'), 2)
        client = Client()
        client.force_login(self.superuser)
        payload = client.get(
            '/search/',
            {'q': security['label']},
            HTTP_ACCEPT_LANGUAGE='en-US,en;q=0.9',
        ).json()
        setting = next((g for g in payload['groups'] if g['type'] == 'setting'), None)
        self.assertIsNotNone(setting)
        self.assertTrue(any(item['url'] == security['url'] for item in setting['items']))

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
        _configure_system(search_config={'enabled': False, 'display_mode': 'icon', 'include_data': False})
        self.client.force_login(self.superuser)
        payload = self.client.get('/search/?q=security').json()
        self.assertEqual(payload['groups'], [])
        self.assertTrue(payload.get('disabled'))


class SearchActivationWiringTests(TestCase):
    """The click path from a result to the thing it names.

    The failure these cover: settings results were dead on click. The dropdown
    dispatched `dlux:dynamic_modal:open` on `document`, while the modal helper
    listened on `document.body` — and an event dispatched on `document` never
    reaches body, because bubbling only travels child → parent. No modal, no
    request, no error.
    """

    def setUp(self):
        _configure_system()

    @staticmethod
    def _asset(*parts):
        from pathlib import Path

        import dlux

        return (Path(dlux.__file__).parent.joinpath('static', 'dlux', *parts)).read_text(encoding='utf-8')

    def test_modal_listener_and_dispatcher_share_a_target(self):
        helper = self._asset('helpers', 'dynamic_modal', 'js', 'main.js')
        search = self._asset('search', 'js', 'main.js')
        # The listener must be on document so it also catches events bubbling up
        # from an element, which is how table row actions reach it.
        self.assertIn("document.addEventListener('dlux:dynamic_modal:open'", helper)
        self.assertNotIn("document.body.addEventListener('dlux:dynamic_modal:open'", helper)
        # The dispatcher bubbles from body, so it lands on either binding.
        self.assertIn("document.body.dispatchEvent(new CustomEvent('dlux:dynamic_modal:open'", search)
        self.assertIn('bubbles: true', search)

    def test_settings_results_carry_a_fallback_target(self):
        index = get_component_index('en')
        settings_entries = [entry for entry in index if entry['type'] == 'setting']
        self.assertTrue(settings_entries)
        for entry in settings_entries:
            self.assertTrue(entry['fallback_url'].endswith('#dlux-option-admin-panel'), entry)

    def test_fallback_url_survives_the_public_key_filter(self):
        superuser = User.objects.create_superuser('root', 'r@x.com', 'pw12345!')
        self.client.force_login(superuser)
        groups = self.client.get('/search/?q=security').json()['groups']
        settings_group = next(g for g in groups if g['type'] == 'setting')
        item = settings_group['items'][0]
        self.assertIn('fallback_url', item)
        self.assertTrue(item['fallback_url'])

    def test_admin_panel_is_addressable_without_becoming_reorderable(self):
        from pathlib import Path

        import dlux

        template = (
            Path(dlux.__file__).parent / 'templates' / 'dlux' / 'system' / 'options.html'
        ).read_text(encoding='utf-8')
        self.assertIn('dlux-admin-panel-card" data-options-deeplink="admin-panel"', template)
        # data-options-card is what drag-reordering keys off, so the admin panel
        # must NOT gain it just to be deep-linkable.
        self.assertNotIn('dlux-admin-panel-card" data-options-card=', template)

    def test_options_deep_link_reveals_its_tab_and_survives_repeat_clicks(self):
        options_js = self._asset('system', 'js', 'options.js')
        # The deep link resolves either hook.
        self.assertIn('data-options-deeplink="', options_js)
        # It activates the pane that holds the target instead of scrolling to a
        # hidden card, which is what "goes to Options but not the tab" was.
        self.assertIn('optionsTabs.activate(index)', options_js)
        # A second result while already on Options only changes the hash.
        self.assertIn("window.addEventListener('hashchange', focusHashCard)", options_js)


class OptionCardVisibilityTests(TestCase):
    """Only cards this configuration actually renders may be offered.

    The failure these cover: OPTIONS_CARDS is a static catalogue, so the index
    advertised every card unconditionally. A single-language install still
    returned a Language result whose deep link landed on Options and highlighted
    nothing, because the card is never rendered.
    """

    def setUp(self):
        _configure_system()
        self.config = get_system_config()

    def _slugs(self, **overrides):
        from dlux.search import _visible_option_slugs

        return _visible_option_slugs({**self.config, **overrides})

    def test_single_language_hides_the_language_card(self):
        localization = {**(self.config.get('localization') or {}), 'languages': {'en': 'English'}}
        visible, _remap = self._slugs(localization=localization)
        self.assertNotIn('language', visible)
        self.assertNotIn('theme-language', visible)

    def test_language_override_off_hides_it_even_with_two_languages(self):
        localization = {
            **(self.config.get('localization') or {}),
            'languages': {'en': 'English', 'ar': 'Arabic'},
            'allow_user_language_override': False,
        }
        visible, _remap = self._slugs(localization=localization)
        self.assertNotIn('language', visible)

    def test_single_theme_hides_the_standalone_theme_card(self):
        """The merged card still renders for the language half alone, matching
        the template, so only the standalone 'theme' slug disappears."""
        visible, remap = self._slugs(allowed_themes=['light'])
        self.assertNotIn('theme', visible)
        self.assertIsNone(remap.get('theme'))
        self.assertEqual(remap.get('language'), 'theme-language')

    def test_no_theme_and_no_language_hides_the_pair_entirely(self):
        localization = {**(self.config.get('localization') or {}), 'languages': {'en': 'English'}}
        visible, remap = self._slugs(allowed_themes=['light'], localization=localization)
        self.assertNotIn('theme', visible)
        self.assertNotIn('language', visible)
        self.assertNotIn('theme-language', visible)
        self.assertEqual(remap, {})

    def test_merged_theme_language_card_remaps_both_slugs(self):
        """Below the split thresholds the page renders one combined card."""
        appearance = {**(self.config.get('appearance') or {}), 'options_style': 'cards'}
        visible, remap = self._slugs(allowed_themes=['light', 'dark'], appearance=appearance)
        self.assertIn('theme-language', visible)
        self.assertEqual(remap.get('theme'), 'theme-language')
        self.assertEqual(remap.get('language'), 'theme-language')

    def test_tabs_layout_splits_them_into_their_own_cards(self):
        appearance = {**(self.config.get('appearance') or {}), 'options_style': 'tabs'}
        visible, remap = self._slugs(allowed_themes=['light', 'dark'], appearance=appearance)
        self.assertIn('theme', visible)
        self.assertIn('language', visible)
        self.assertNotIn('theme-language', visible)
        self.assertEqual(remap, {})

    def test_landing_page_follows_allow_user_home_url(self):
        off, _ = self._slugs(profile_config={'allow_user_home_url': False})
        self.assertNotIn('landing-page', off)
        on, _ = self._slugs(profile_config={'allow_user_home_url': True})
        self.assertIn('landing-page', on)

    def test_sidebar_density_follows_the_sidebar_being_enabled(self):
        off, _ = self._slugs(sidebar={'enabled': False})
        self.assertNotIn('sidebar-density', off)

    def test_index_drops_the_language_result_for_a_single_language_install(self):
        from unittest import mock

        single = {
            **self.config,
            'localization': {
                **(self.config.get('localization') or {}),
                'languages': {'en': 'English'},
            },
        }
        cache.clear()
        with mock.patch('dlux.utils.get_system_config', return_value=single):
            labels = {e['label'] for e in get_component_index('en') if e['type'] == 'option'}
        self.assertNotIn('Language', labels)
        # Unconditional cards are untouched.
        self.assertIn('Accessibility', labels)

    def test_every_indexed_option_points_at_a_renderable_card(self):
        from dlux.search import _visible_option_slugs

        visible, _remap = _visible_option_slugs(get_system_config())
        for entry in get_component_index('en'):
            if entry['type'] != 'option':
                continue
            slug = entry['url'].split('#dlux-option-')[-1]
            self.assertIn(slug, visible, entry['url'])
