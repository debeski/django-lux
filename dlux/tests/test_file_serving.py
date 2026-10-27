"""serve_file: ranges for the PDF viewer, and revalidation instead of re-download."""

import tempfile

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.http import Http404
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase

from dlux.files.serving import parse_range, serve_file

PAYLOAD = bytes(range(256)) * 40  # 10240 bytes


class _StoredFile:
    """The parts of a FieldFile that serve_file uses."""

    def __init__(self, storage, name):
        self.storage = storage
        self.name = name


class ServeFileTests(SimpleTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.storage = FileSystemStorage(location=self.tmp.name)
        self.file = _StoredFile(self.storage, self.storage.save('scans/decree 7.pdf', ContentFile(PAYLOAD)))
        self.factory = RequestFactory()

    def tearDown(self):
        self.tmp.cleanup()

    def serve(self, **headers):
        return serve_file(self.factory.get('/source/', **headers), self.file)

    def body(self, response):
        return b''.join(response.streaming_content)

    def test_full_response_advertises_ranges_and_validators(self):
        response = self.serve()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.body(response), PAYLOAD)
        self.assertEqual(response['Accept-Ranges'], 'bytes')
        self.assertEqual(response['Cache-Control'], 'private, no-cache')
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response['ETag'].startswith('"'))
        self.assertIn('Last-Modified', response)
        self.assertEqual(response['Content-Disposition'], 'inline; filename="decree 7.pdf"')

    def test_matching_etag_revalidates_without_a_body(self):
        etag = self.serve()['ETag']
        response = self.serve(HTTP_IF_NONE_MATCH=etag)
        self.assertEqual(response.status_code, 304)
        self.assertEqual(response['ETag'], etag)

    def test_a_replaced_file_gets_a_new_etag(self):
        etag = self.serve()['ETag']
        self.storage.delete(self.file.name)
        self.storage.save(self.file.name, ContentFile(PAYLOAD + b'more'))
        self.assertNotEqual(self.serve()['ETag'], etag)
        self.assertEqual(self.serve(HTTP_IF_NONE_MATCH=etag).status_code, 200)

    def test_single_ranges_return_exact_bytes(self):
        for header, start, end in (
            ('bytes=0-99', 0, 99),
            ('bytes=10000-', 10000, 10239),
            ('bytes=-40', 10200, 10239),
            ('bytes=10200-99999', 10200, 10239),
        ):
            with self.subTest(header=header):
                response = self.serve(HTTP_RANGE=header)
                self.assertEqual(response.status_code, 206)
                self.assertEqual(self.body(response), PAYLOAD[start:end + 1])
                self.assertEqual(response['Content-Range'], f'bytes {start}-{end}/{len(PAYLOAD)}')
                self.assertEqual(response['Content-Length'], str(end - start + 1))
                self.assertEqual(response['Content-Type'], 'application/pdf')
                self.assertEqual(response['Accept-Ranges'], 'bytes')

    def test_unsatisfiable_range_is_416(self):
        for header in ('bytes=10240-', 'bytes=500-100', 'bytes=-0'):
            with self.subTest(header=header):
                response = self.serve(HTTP_RANGE=header)
                self.assertEqual(response.status_code, 416)
                self.assertEqual(response['Content-Range'], f'bytes */{len(PAYLOAD)}')

    def test_stale_if_range_and_unsupported_ranges_fall_back_to_the_whole_file(self):
        for headers in (
            {'HTTP_RANGE': 'bytes=0-9', 'HTTP_IF_RANGE': '"an-old-etag"'},
            {'HTTP_RANGE': 'bytes=0-9,20-29'},
            {'HTTP_RANGE': 'items=0-9'},
        ):
            with self.subTest(headers=headers):
                response = self.serve(**headers)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(self.body(response), PAYLOAD)

    def test_matching_if_range_honours_the_range(self):
        etag = self.serve()['ETag']
        response = self.serve(HTTP_RANGE='bytes=0-9', HTTP_IF_RANGE=etag)
        self.assertEqual(response.status_code, 206)
        self.assertEqual(self.body(response), PAYLOAD[:10])

    def test_attachment_disposition_survives_a_range(self):
        response = serve_file(self.factory.get('/', HTTP_RANGE='bytes=0-9'), self.file, as_attachment=True)
        self.assertEqual(response['Content-Disposition'], 'attachment; filename="decree 7.pdf"')

    def test_missing_file_is_404(self):
        for file_field in (None, _StoredFile(self.storage, ''), _StoredFile(self.storage, 'nope.pdf')):
            with self.subTest(file_field=file_field):
                with self.assertRaises(Http404):
                    serve_file(self.factory.get('/'), file_field)

    def test_parse_range_edges(self):
        self.assertEqual(parse_range('bytes=0-0', 10), (0, 0))
        self.assertEqual(parse_range('bytes=-20', 10), (0, 9))
        self.assertIsNone(parse_range('bytes=-', 10))
        self.assertIsNone(parse_range('', 10))
        self.assertFalse(parse_range('bytes=10-', 10))


class ViewerLoadsTheFileOnceTests(SimpleTestCase):
    def test_the_fallback_frame_is_not_loaded_up_front(self):
        html = render_to_string('dlux/pdf/viewer.html', {
            'source_url': '/source/', 'worker_url': '/worker.js', 'pdf_features': {}, 'DLUX_STRINGS': {},
        })
        self.assertIn('data-pdf-fallback', html)
        self.assertNotIn('src="/source/', html)
