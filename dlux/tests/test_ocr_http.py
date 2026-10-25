import json
import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection, RemoteDisconnected
from unittest import TestCase
from unittest.mock import patch

from dlux.ocr import serve


PDF = b'%PDF-1.4\n%%EOF\n'


class Engine:
    name = 'test'
    version = '1'
    model_version = '1'

    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.release.set()
        self.lock = threading.Lock()
        self.active = self.peak = self.calls = 0
        self.options = []

    def convert(self, path, **options):
        with self.lock:
            self.active += 1
            self.calls += 1
            self.peak = max(self.peak, self.active)
            self.options.append(options)
        self.started.set()
        try:
            if not self.release.wait(3):
                raise RuntimeError('Test did not release the engine')
            return {'pages': [{'index': 0, 'source': 'ocr', 'text': 'Read text',
                               'markdown': 'Read text', 'lines': [], 'timings': {}}]}
        finally:
            with self.lock:
                self.active -= 1


class OCRHTTPTests(TestCase):
    def setUp(self):
        self.engine = Engine()
        self.patchers = [patch.object(serve, name, value) for name, value in {
            'ENGINE': self.engine, 'MAX_CONNECTIONS': 2, 'READ_TIMEOUT': 0.2,
            'QUEUE_WAIT': 0.05, 'SLOTS': threading.BoundedSemaphore(1),
        }.items()]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.server = serve.OCRHTTPServer(('127.0.0.1', 0), serve.Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)

    def close(self):
        self.engine.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def request(self, body=PDF, path='/v1/ocr', headers=None):
        connection = HTTPConnection(*self.server.server_address, timeout=3)
        try:
            connection.request('POST', path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def raw(self, message, *, eof=False):
        with socket.create_connection(self.server.server_address, timeout=2) as connection:
            connection.sendall(message)
            if eof:
                connection.shutdown(socket.SHUT_WR)
            response = b''
            while True:
                try:
                    chunk = connection.recv(65536)
                except ConnectionResetError:
                    if not response:
                        raise
                    break
                if not chunk:
                    break
                response += chunk
        return int(response.split(b' ', 2)[1]), response

    def test_real_http_response_and_option_limits(self):
        status, data = self.request(path='/v1/ocr?max_pages=999999&threads=999999')
        self.assertEqual(status, 200)
        self.assertEqual(data['text'], 'Read text')
        self.assertEqual(self.engine.options[-1]['max_pages'], serve.MAX_PAGES)
        self.assertEqual(self.engine.options[-1]['threads'], serve.MAX_THREADS)

    def test_oversized_invalid_and_ambiguous_uploads_never_reach_engine(self):
        with patch.object(serve, 'MAX_BYTES', 10):
            self.assertEqual(self.request()[0], 413)
        self.assertEqual(self.request(b'<html>')[0], 415)
        self.assertEqual(self.request(path='/v1/ocr?threads=bad')[0], 400)
        self.assertEqual(self.raw(b'POST /v1/ocr HTTP/1.1\r\nHost: ocr\r\nContent-Length: 1\r\nContent-Length: 2\r\n\r\n')[0], 400)
        self.assertEqual(self.raw(b'POST /v1/ocr HTTP/1.1\r\nHost: ocr\r\nTransfer-Encoding: chunked\r\n\r\n')[0], 400)
        self.assertEqual(self.engine.calls, 0)
        self.assertEqual(self.request()[0], 200)

    def test_partial_and_stalled_uploads_release_the_worker(self):
        headers = b'POST /v1/ocr HTTP/1.1\r\nHost: ocr\r\nContent-Length: 100\r\n\r\n'
        self.assertEqual(self.raw(headers + b'%PDF-', eof=True)[0], 400)
        self.assertEqual(self.raw(headers + b'%PDF-')[0], 408)
        self.assertEqual(self.request()[0], 200)
        self.assertEqual(self.engine.calls, 1)

    def test_busy_request_is_rejected_before_upload_is_buffered(self):
        self.engine.release.clear()
        with ThreadPoolExecutor(max_workers=1) as executor:
            first = executor.submit(self.request)
            self.assertTrue(self.engine.started.wait(1))
            try:
                status, response = self.raw(b'POST /v1/ocr HTTP/1.1\r\nHost: ocr\r\nContent-Length: 100000\r\n\r\n')
                self.assertEqual(status, 503)
                self.assertIn(b'Retry-After: 30', response)
            finally:
                self.engine.release.set()
            self.assertEqual(first.result()[0], 200)
        self.assertEqual(self.engine.peak, 1)

    def test_connection_limit_rejects_overflow_and_recovers(self):
        self.server._connections = threading.BoundedSemaphore(1)
        self.engine.release.clear()
        with ThreadPoolExecutor(max_workers=1) as executor:
            first = executor.submit(self.request)
            self.assertTrue(self.engine.started.wait(1))
            try:
                self.assertEqual(self.raw(b'GET /health HTTP/1.1\r\nHost: ocr\r\n\r\n')[0], 503)
            finally:
                self.engine.release.set()
            self.assertEqual(first.result()[0], 200)
        self.assertEqual(self.request()[0], 200)

    def test_concurrent_requests_respect_engine_limit(self):
        def request_or_rejection(_):
            try:
                return self.request()[0]
            except (BrokenPipeError, ConnectionResetError, RemoteDisconnected):
                return 'closed'

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(request_or_rejection, range(24)))
        self.assertTrue(set(results) <= {200, 503, 'closed'}, results)
        self.assertIn(200, results)
        self.assertEqual(self.engine.peak, 1)
        self.assertEqual(self.request()[0], 200)
