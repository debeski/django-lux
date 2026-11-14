"""The administrator chooses which websites may use ScanLink.

ScanLink lets no website scan until the operator approves it once; the page
then sends the sites listed here, and ScanLink allows them too. The list is
stored in ``extra_config['scanlink']['sites']`` as website origins, exactly as
browsers send them, because ScanLink compares them that way.
"""

from dlux.models import SystemSettings
from dlux.system.normalizers import (
    SCANLINK_MAX_SITES,
    normalize_extra_config,
    normalize_scanlink_origin,
)
from dlux.tests.test_scanlink_gate import ScanLinkTestCase
from dlux.utils import scanlink_sites


def _store(scanlink):
    record = SystemSettings.load()
    extra = dict(record.extra_config or {})
    extra['scanlink'] = scanlink
    record.extra_config = extra
    record.save()


class OriginTests(ScanLinkTestCase):
    def test_addresses_become_origins_as_browsers_send_them(self):
        for value, expected in (
            ('https://crm.example.org', 'https://crm.example.org'),
            (' https://CRM.Example.org/ ', 'https://crm.example.org'),
            ('https://crm.example.org:443', 'https://crm.example.org'),
            ('http://intranet:8080', 'http://intranet:8080'),
        ):
            with self.subTest(value=value):
                self.assertEqual(normalize_scanlink_origin(value), expected)

    def test_anything_but_a_website_origin_is_refused(self):
        for value in ('*', 'https://*.example.org', 'crm.example.org', 'https://crm.example.org/path',
                      'https://user:pw@crm.example.org', 'ftp://crm.example.org', 'null', '', None, 7):
            with self.subTest(value=value):
                self.assertIsNone(normalize_scanlink_origin(value))


class StoredSitesTests(ScanLinkTestCase):
    def test_no_sites_by_default(self):
        self.assertEqual(scanlink_sites(), [])

    def test_stored_sites_are_read_as_origins(self):
        _store({'enabled': True, 'sites': ['https://crm.example.org/', 'https://crm.example.org', 'bad', 'http://b:81']})
        self.assertEqual(scanlink_sites(), ['https://crm.example.org', 'http://b:81'])

    def test_a_corrupt_value_reads_as_no_sites(self):
        _store('not-a-dict')
        self.assertEqual(scanlink_sites(), [])

    def test_normalizing_keeps_the_switch_and_the_project_namespace(self):
        result = normalize_extra_config({
            'app': {'p': 1},
            'scanlink': {'enabled': 'true', 'sites': ['https://a.example', '*']},
        })
        self.assertEqual(result['app'], {'p': 1})
        self.assertEqual(result['scanlink'], {'enabled': True, 'sites': ['https://a.example']})


class SettingsFormTests(ScanLinkTestCase):
    def _form(self, sites, enabled=True):
        from dlux.forms import SystemSettingsForm

        form = SystemSettingsForm(instance=SystemSettings.load())
        form.cleaned_data = {'scanlink_enabled': enabled, 'scanlink_sites': sites}
        return form

    def test_one_address_per_line_is_saved_as_origins(self):
        form = self._form('https://crm.example.org\n\n  https://CRM.example.org/ \nhttp://intranet:8080\n')
        self.assertEqual(form.clean_scanlink_sites(), ['https://crm.example.org', 'http://intranet:8080'])

    def test_a_bad_line_is_named_in_the_error(self):
        from django.core.exceptions import ValidationError

        for value in ('crm.example.org', 'https://*.example.org', '*'):
            with self.subTest(value=value), self.assertRaises(ValidationError) as caught:
                self._form(f'https://ok.example\n{value}').clean_scanlink_sites()
            self.assertIn(value, caught.exception.messages[0])

    def test_too_many_sites_are_refused(self):
        from django.core.exceptions import ValidationError

        lines = '\n'.join(f'https://s{n}.example' for n in range(SCANLINK_MAX_SITES + 1))
        with self.assertRaises(ValidationError):
            self._form(lines).clean_scanlink_sites()

    def test_saving_writes_the_list_beside_the_switch(self):
        record = SystemSettings.load()
        record.extra_config = {'app': {'p': {'keep': 'me'}}, 'scanlink': {'enabled': False}}
        record.save()
        form = self._form('https://crm.example.org')
        form.single_step_mode = False
        form.cleaned_data['scanlink_sites'] = form.clean_scanlink_sites()
        form._apply_extra_features(record)
        self.assertEqual(record.extra_config['scanlink'], {'enabled': True, 'sites': ['https://crm.example.org']})
        self.assertEqual(record.extra_config['app'], {'p': {'keep': 'me'}})

    def test_the_form_shows_the_stored_list_one_per_line(self):
        from dlux.forms import SystemSettingsForm

        _store({'enabled': True, 'sites': ['https://a.example', 'https://b.example']})
        form = SystemSettingsForm(instance=SystemSettings.load())
        self.assertEqual(form.initial['scanlink_sites'], 'https://a.example\nhttps://b.example')


class PageDataTests(ScanLinkTestCase):
    def _page(self):
        from django.contrib.auth import get_user_model

        record = SystemSettings.load()
        record.is_configured = True
        record.save()
        user = get_user_model().objects.create_superuser('scan-admin', 'scan@example.org', 'pw-for-tests-only')
        self.client.force_login(user)
        response = self.client.get('/accounts/profile/')
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_the_list_reaches_every_page_once_as_json_data(self):
        _store({'enabled': True, 'sites': ['https://crm.example.org']})
        html = self._page()
        self.assertEqual(html.count('id="dlux-scanlink-sites"'), 1)
        self.assertIn('<script id="dlux-scanlink-sites" type="application/json">["https://crm.example.org"]</script>', html)

    def test_nothing_is_sent_while_scanlink_is_off(self):
        _store({'enabled': False, 'sites': ['https://crm.example.org']})
        self.assertNotIn('dlux-scanlink-sites', self._page())
