from io import BytesIO

from django.test import RequestFactory, SimpleTestCase, TestCase
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from unittest.mock import patch
from django.template.loader import render_to_string
from unittest import skipUnless
try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    PdfReader = PdfWriter = None

from dlux.pdf.assembly import assemble_pdf
from dlux.pdf import get_pdf_features
from dlux.pdf.views import PdfEditorView


class PdfIntegrationTests(SimpleTestCase):
    def test_options_defaults_disable_flags_and_bound_limits(self):
        with patch('dlux.utils.get_app_system_config',return_value={}):
            self.assertEqual(get_pdf_features()['max_source_mb'],100)
            self.assertTrue(get_pdf_features()['editing_enabled'])
        with patch('dlux.utils.get_app_system_config',return_value={'editing_enabled':False,'max_pages':-1,'max_source_mb':900}):
            values = get_pdf_features()
            self.assertFalse(values['editing_enabled'])
            self.assertEqual(values['max_pages'],1)
            self.assertEqual(values['max_source_mb'],500)
        with patch('dlux.utils.get_app_system_config',return_value={'max_pages':'invalid'}):
            self.assertEqual(get_pdf_features()['max_pages'],500)

    def test_viewer_uses_explicit_context_without_a_model_field_contract(self):
        html = render_to_string('dlux/pdf/viewer.html',{'source_url':'/protected/opaque/','file_name':'custom.pdf','download_url':'/download/opaque/','pdf_features':{'editing_enabled':False,'history_enabled':False}})
        self.assertIn('data-pdf-url="/protected/opaque/"',html)
        self.assertIn('data-file-name="custom.pdf"',html)
        self.assertNotIn('data-dynamic-modal=',html)


def source_pdf(widths):
    writer = PdfWriter()
    for width in widths:
        writer.add_blank_page(width=width, height=200)
    stream = BytesIO()
    writer.write(stream)
    return stream.getvalue()


@skipUnless(PdfReader, 'Install django-lux[pdf] to test optional PDF assembly.')
class PdfAssemblyTests(SimpleTestCase):
    def test_reorder_remove_append_and_read_each_source_once(self):
        sources = {'current': source_pdf([100, 120, 140]), 'upload_0': source_pdf([180])}
        calls = []
        def read(key):
            calls.append(key)
            return sources[key]
        output = assemble_pdf([{'source': 'current', 'page': 3}, {'source': 'current', 'page': 1}, {'source': 'upload_0', 'page': 1}], read)
        self.assertEqual([float(page.mediabox.width) for page in PdfReader(BytesIO(output)).pages], [140, 100, 180])
        self.assertEqual(calls, ['current', 'upload_0'])

    def test_malformed_manifest_and_page_numbers_are_rejected(self):
        for value in ({}, [], [None], [{'source': 'current', 'page': True}], [{'source': 'current', 'page': '1'}], [{'source': 'current', 'page': 0}], [{'source': 'current', 'page': 2}]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                assemble_pdf(value, lambda key: source_pdf([100]))

    def test_page_and_total_source_limits(self):
        with self.assertRaises(ValueError):
            assemble_pdf([{'source': 'current', 'page':1}]*2, lambda key: source_pdf([100]), max_pages=1)
        with self.assertRaises(ValueError):
            assemble_pdf([{'source':'current','page':1}], lambda key: source_pdf([100]), max_source_bytes=10)

    def test_encrypted_pdf_is_rejected_without_prompting(self):
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=200)
        writer.encrypt('secret')
        stream = BytesIO()
        writer.write(stream)
        with self.assertRaisesRegex(ValueError, 'Encrypted'):
            assemble_pdf([{'source':'current','page':1}], lambda key: stream.getvalue())


class PdfTransportTests(TestCase):
    def setUp(self):
        from unittest.mock import Mock

        self.factory = RequestFactory()
        self.user = get_user_model().objects.create_user(username='pdf-transport')
        self.adapter = Mock()
        self.adapter.lookup.return_value = self.user
        self.adapter.revision.return_value = 'revision-1'
        self.view = PdfEditorView.as_view(adapter=self.adapter)
        self.features = patch('dlux.pdf.views.get_pdf_features', return_value={
            'editing_enabled': True, 'history_enabled': True,
            'max_pages': 5, 'max_source_mb': 1,
        })
        self.features.start()
        self.addCleanup(self.features.stop)

    def request(self, **data):
        request = self.factory.post('/pdf/edit/', {'revision': 'revision-1', 'manifest': '[]', **data})
        request.user = self.user
        return request

    def test_anonymous_and_disabled_editing_never_reach_adapter(self):
        request = self.request()
        request.user = AnonymousUser()
        self.assertEqual(self.view(request).status_code, 302)
        with patch('dlux.pdf.views.get_pdf_features', return_value={'editing_enabled': False}):
            self.assertEqual(self.view(self.request()).status_code, 403)
        self.adapter.lookup.assert_not_called()

    def test_authorization_denial_and_revision_conflict_never_save(self):
        self.adapter.lookup.side_effect = PermissionDenied
        with self.assertRaises(PermissionDenied):
            self.view(self.request())
        self.adapter.lookup.side_effect = None
        response = self.view(self.request(revision='stale'))
        self.assertEqual(response.status_code, 409)
        self.adapter.save.assert_not_called()

    def test_save_exception_rolls_back_adapter_database_writes(self):
        def fail_save(request, document, data):
            document.username = 'changed-by-failed-save'
            document.save(update_fields=['username'])
            raise ValueError('Storage failed')

        self.adapter.save.side_effect = fail_save
        with patch('dlux.pdf.views.assemble_pdf', return_value=b'pdf'):
            response = self.view(self.request())
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'pdf-transport')

    def test_success_uses_locked_lookup_and_configured_assembly_limits(self):
        import json

        request = self.request()
        with patch('dlux.pdf.views.assemble_pdf', return_value=b'pdf') as assemble:
            response = self.view(request)
        self.assertEqual(json.loads(response.content), {'success': True, 'refresh_parent': True})
        self.adapter.lookup.assert_called_once_with(request, {}, lock=True)
        self.assertEqual(assemble.call_args.kwargs, {'max_pages': 5, 'max_source_bytes': 1024 * 1024})
        self.adapter.save.assert_called_once()
