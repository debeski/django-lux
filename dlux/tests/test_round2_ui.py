"""Break-it round 2 UI findings (R2-052, R2-091, R2-092, R2-094, R2-110, R2-111,
R2-115, R2-129). The ScanLink client half (R2-053, R2-116, R2-117) runs in
``fixtures/scanlink/scenarios.mjs``; the browser half in ``tests-e2e``."""

from pathlib import Path
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template import Context, Template
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse

from dlux import middleware
from dlux.forms.system_settings_groups.shared import PreservedValueMixin
from dlux.models import SystemSettings
from dlux.system.normalizers import normalize_scanlink_origin, normalize_scanlink_sites
from dlux.utils.config import normalize_system_names, resolve_system_name
from dlux.utils.import_export import SettingsImportError, read_system_settings_import
from dlux.widgets import DluxFileInput

DLUX = Path(__file__).resolve().parents[1]
User = get_user_model()


class _ArabicRequest:
    """Puts an Arabic request in the thread local the strings table reads."""

    def __enter__(self):
        request = RequestFactory().get('/')
        request.user = AnonymousUser()
        request.session = {'lang': 'ar'}
        self._previous = getattr(middleware._thread_locals, 'request', None)
        middleware._thread_locals.request = request
        return request

    def __exit__(self, *exc):
        if self._previous is None:
            if hasattr(middleware._thread_locals, 'request'):
                del middleware._thread_locals.request
        else:
            middleware._thread_locals.request = self._previous


def _enable_scanlink():
    record = SystemSettings.load()
    record.extra_config = {**(record.extra_config or {}), 'scanlink': {'enabled': True}}
    record.save()


class ScanButtonMessagesTests(TestCase):
    """R2-052: widgets render without context processors, so the Scan button's
    data-scan-* attributes were always their English defaults."""

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        _enable_scanlink()

    def test_the_scan_button_carries_the_arabic_messages(self):
        with _ArabicRequest():
            html = DluxFileInput(show_scan=True).render('pdf_file', None, attrs={'id': 'id_pdf_file'})
        from dlux.translations.strings.ar import STRINGS as AR
        self.assertIn(f'data-scan-preparing="{AR["scan_preparing_label"]}"', html)
        self.assertIn(f'data-scan-lost="{AR["scan_lost_message"]}"', html)
        self.assertNotIn('Preparing scan', html)
        self.assertNotIn('Choose Allow in the ScanLink window', html)

    def test_without_a_strings_table_no_english_attributes_are_rendered(self):
        html = render_to_string('dlux/helpers/scanlink/scan_messages.html', {})
        self.assertNotIn('data-scan-', html)


class ScanLinkOriginTests(SimpleTestCase):
    """R2-115 (DjangoLux half): hosts that read as another site are refused, and
    non-ASCII hosts are compared in their IDNA form, as ScanLink does."""

    def test_invisible_and_bidi_characters_and_trailing_dots_are_refused(self):
        for value in ('https://arch\u202eive.example', 'https://a\u200bb.example',
                      'https://ex\u2066ample.org', 'https://example.org.'):
            with self.subTest(value=repr(value)):
                self.assertIsNone(normalize_scanlink_origin(value))

    def test_non_ascii_hosts_are_stored_as_idna(self):
        self.assertEqual(normalize_scanlink_origin('https://аpple.example'), 'https://xn--pple-43d.example')
        self.assertEqual(normalize_scanlink_origin('https://bücher.example:8443'), 'https://xn--bcher-kva.example:8443')
        self.assertEqual(normalize_scanlink_sites(['https://crm.example', 'https://crm\u202e.example']), ['https://crm.example'])


class SystemNameControlTests(SimpleTestCase):
    """R2-092: bidi controls reversed the titlebar and every page title."""

    def test_bidi_and_control_characters_are_stripped(self):
        names = normalize_system_names({'ar': 'نظام\u202e<svg>', 'en': ' Sys\u2066tem\u2069\x07 '})
        self.assertEqual(names, {'ar': 'نظام<svg>', 'en': 'System'})
        self.assertEqual(resolve_system_name({'en': 'A\u202eB'}, 'en'), 'AB')


class SettingsImportFileTests(TestCase):
    """R2-094: malformed settings files returned a 500."""

    MALFORMED = {
        'deep': b'[' * 200000,
        'infinity': b'{"email_config": {"port": Infinity}}',
        'nan': b'{"login_config": {"lockout_threshold": NaN}}',
        'overflow': b'{"email_config": {"port": 1e400}}',
        'not_utf8': b'\xff\xfe{}',
        'not_object': b'[]',
    }

    def test_the_reader_refuses_every_malformed_file(self):
        for name, raw in self.MALFORMED.items():
            with self.subTest(name=name):
                with self.assertRaises(SettingsImportError):
                    read_system_settings_import(raw)
        with self.assertRaises(SettingsImportError) as caught:
            read_system_settings_import(b' ' * (2 * 1024 * 1024 + 1))
        self.assertEqual(caught.exception.code, 'too_large')

    def test_a_byte_order_mark_is_accepted(self):
        payload, normalized = read_system_settings_import('\ufeff{"home_url": "/bom/"}'.encode('utf-8'))
        self.assertEqual(payload, {'home_url': '/bom/'})
        self.assertEqual(normalized.get('home_url'), '/bom/')

    def test_the_options_preview_answers_400_with_the_translated_message(self):
        cache.clear()
        record = SystemSettings.load()
        record.is_configured = True
        record.save()
        admin = User.objects.create_superuser('import-admin', 'i@example.test', 'pw-long-enough-1')
        self.client.force_login(admin)
        for name, raw in self.MALFORMED.items():
            with self.subTest(name=name):
                upload = SimpleUploadedFile('config.json', raw, content_type='application/json')
                response = self.client.post(reverse('system_settings_import_preview'), {'config_file': upload})
                self.assertEqual(response.status_code, 400)
                self.assertFalse(response.json()['ok'])

    def test_the_setup_wizard_reports_a_form_error(self):
        for name, raw in self.MALFORMED.items():
            with self.subTest(name=name):
                errors = []
                form = SimpleNamespace(
                    cleaned_data={'settings_import_file': SimpleUploadedFile('setup.json', raw)},
                    add_error=lambda field, message: errors.append((field, message)),
                )
                self.assertEqual(PreservedValueMixin._read_imported_settings(form), {})
                self.assertEqual([field for field, _ in errors], ['settings_import_file'])


class BackupPageTests(SimpleTestCase):
    def test_the_create_button_names_both_kinds(self):
        """R2-129: the label switches with the Type select (backup/js/manage.js)."""
        html = (DLUX / 'templates/dlux/backup/_create_action.html').read_text(encoding='utf-8')
        self.assertIn('data-label-incremental="{{ DLUX_STRINGS.sysbackup_create_incremental', html)
        self.assertIn('data-sysbackup-create-label', html)
        script = (DLUX / 'static/dlux/backup/js/manage.js').read_text(encoding='utf-8')
        self.assertIn('createBtn.dataset.labelIncremental', script)

    def test_light_badges_keep_dark_ink_in_every_theme(self):
        """R2-111: the dark theme turns .text-dark white, which left white text on
        the cyan "Data only" badge (1.96:1). text-bg-* sets its own ink."""
        for name in ('backup/cells/_backup_trigger.html', 'backup/cells/_backup_status.html'):
            html = (DLUX / 'templates/dlux' / name).read_text(encoding='utf-8')
            self.assertNotIn('bg-info text-dark', html, name)
            self.assertNotIn('bg-warning text-dark', html, name)
        self.assertIn('badge text-bg-info', (DLUX / 'templates/dlux/backup/cells/_backup_trigger.html').read_text(encoding='utf-8'))


class ArabicStringsTests(TestCase):
    """R2-110: strings that stayed English on Arabic deployments."""

    def test_crud_notifications_are_translated(self):
        from dlux.notifications import _crud_message

        record = type('Record', (), {'_meta': SimpleNamespace(verbose_name='قرار'), '__str__': lambda self: '99001'})()
        with _ArabicRequest():
            self.assertEqual(_crud_message(record, 'create'), 'تمت إضافة قرار: 99001')
            self.assertEqual(_crud_message(record, 'delete'), 'تم حذف قرار: 99001')
            self.assertEqual(_crud_message(record, 'update', {'title': {}}), 'تم تعديل قرار: 99001 (title)')
        self.assertEqual(_crud_message(record, 'create'), 'Created قرار: 99001')

    def test_device_labels_are_translated(self):
        from dlux.views.profile import _device_label

        with _ArabicRequest():
            self.assertEqual(_device_label(''), 'جهاز غير معروف')
            self.assertEqual(_device_label('Mozilla/5.0 (Macintosh) Chrome/120'), 'Chrome على macOS')
        self.assertEqual(_device_label('Mozilla/5.0 (Macintosh) Chrome/120'), 'Chrome on macOS')

    def test_audit_column_headers_are_translated(self):
        template = Template('{% load dlux_translation %}{{ header|dlux_column_label }}')
        with _ArabicRequest():
            self.assertEqual(template.render(Context({'header': 'Updated By'})), 'آخر تعديل بواسطة')
            self.assertEqual(template.render(Context({'header': 'Updated at'})), 'تاريخ آخر تعديل')
            self.assertEqual(template.render(Context({'header': 'Decree Number'})), 'Decree Number')

    def test_djangos_blank_choice_label_is_translated(self):
        from django.db.models.utils import get_blank_choice_label

        with _ArabicRequest():
            self.assertEqual(str(get_blank_choice_label()), '- اختر خياراً -')

    def test_modal_close_buttons_are_labelled_through_the_strings_table(self):
        found = []
        for path in (DLUX / 'templates').rglob('*.html'):
            if 'aria-label="Close"' in path.read_text(encoding='utf-8'):
                found.append(path.relative_to(DLUX).as_posix())
        self.assertEqual(found, [])


class ProfileActivityTests(SimpleTestCase):
    """R2-091: a structured detail printed its raw dict and widened the card."""

    def test_structured_details_are_summarised(self):
        from dlux.templatetags.dlux_translation import format_log_details

        html = str(format_log_details({'criteria': {'builder': '1', 'custom_end': '2026-01-01', 'x': 1},
                                       'note': 'n' * 120}))
        self.assertIn('criteria: 3 fields', html)
        self.assertNotIn('custom_end', html)
        self.assertIn('n' * 40 + '…', html)
        self.assertNotIn('n' * 41, html)

    def test_theme_toggle_is_not_rendered_in_a_zero_width_sidebar(self):
        css = (DLUX / 'static/dlux/sidebar/css/main.css').read_text(encoding='utf-8')
        self.assertIn('.sidebar.collapsed .sidebar-toolbar {\n        display: none;', css)
        self.assertIn('[data-sidebar-collapse-mode="hidden"].collapsed .sidebar-toolbar', css)
