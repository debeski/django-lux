"""Internal OCR HTTP API for DjangoLux (dlux.ocr): ``python -m dlux.ocr.serve``.

Runs as the stack's ``ocr`` service on the project image, like ``smtp-relay``;
no Django is loaded.

POST /v1/ocr   raw PDF or image bytes in the body; optional query mode=auto|ocr
               and max_pages=N. Returns markdown, text and per-page JSON.
GET  /health   engine name and version.

DjangoLux OCR settings drive each request (mode, threads). Models load on
the first OCR request, so an idle container stays small while OCR is off.

The service has no authentication: it is reachable only on the Compose
internal network and publishes no ports.
"""

import json
import logging
import os
import signal
import tempfile
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import engine as engines

SERVICE_VERSION = '1.0.0'
MAX_BYTES = int(os.environ.get('OCR_MAX_BYTES', str(64 * 1024 * 1024)))
MAX_PAGES = int(os.environ.get('OCR_MAX_PAGES', '500'))
QUEUE_WAIT = float(os.environ.get('OCR_QUEUE_WAIT', '20'))
WORKERS = max(1, int(os.environ.get('OCR_WORKERS', '1')))
MAX_CONNECTIONS = WORKERS + max(1, int(os.environ.get('OCR_QUEUE_SIZE', '2')))
READ_TIMEOUT = max(0.1, float(os.environ.get('OCR_READ_TIMEOUT', '30')))
DEFAULT_THREADS = int(os.environ.get('OCR_THREADS', '2'))
MAX_THREADS = max(1, int(os.environ.get('OCR_MAX_THREADS', str(os.cpu_count() or 4))))
MODES = {'auto', 'ocr'}
SIGNATURES = (
    (b'%PDF-', 'pdf'),
    (b'\x89PNG\r\n\x1a\n', 'png'),
    (b'\xff\xd8\xff', 'jpeg'),
    (b'II*\x00', 'tiff'),
    (b'MM\x00*', 'tiff'),
    (b'BM', 'bmp'),
)

log = logging.getLogger('ocr')
ENGINE = None
UNAVAILABLE = {}
SLOTS = threading.BoundedSemaphore(WORKERS)


class OCRHTTPServer(ThreadingHTTPServer):
    request_queue_size = 64

    def __init__(self, address, handler):
        super().__init__(address, handler)
        self._connections = threading.BoundedSemaphore(MAX_CONNECTIONS)

    def process_request(self, request, address):
        if not self._connections.acquire(blocking=False):
            body = b'{"error":"The OCR engine is busy."}'
            response = (b'HTTP/1.1 503 Service Unavailable\r\nConnection: close\r\n'
                        b'Content-Type: application/json\r\nRetry-After: 30\r\nContent-Length: '
                        + str(len(body)).encode('ascii') + b'\r\n\r\n' + body)
            try:
                request.settimeout(READ_TIMEOUT)
                request.sendall(response)
            except OSError:
                pass
            finally:
                self.shutdown_request(request)
            return
        try:
            request.settimeout(READ_TIMEOUT)
            super().process_request(request, address)
        except BaseException:
            self._connections.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self._connections.release()


def detect_kind(head):
    if head[:4] == b'RIFF' and head[8:12] == b'WEBP':
        return 'webp'
    for signature, kind in SIGNATURES:
        if head.startswith(signature):
            return kind
    return None


def summarize(result, kind, started, queued_ms, threads):
    pages = result['pages']
    confidences = [line['conf'] for page in pages for line in page['lines']]
    page_ms = [page['timings'].get('total_ms', 0.0) for page in pages]
    return {
        'engine': ENGINE.name,
        'engine_version': ENGINE.version,
        'model_version': ENGINE.model_version,
        'service_version': SERVICE_VERSION,
        'input_kind': kind,
        'threads': threads,
        'page_count': len(pages),
        'markdown': '\n\n'.join(page['markdown'] for page in pages if page['markdown']),
        'text': '\n\n'.join(page['text'] for page in pages if page['text']),
        'mean_confidence': round(sum(confidences) / len(confidences), 4) if confidences else None,
        'failed_pages': [page['index'] for page in pages if page['source'] == 'error'],
        'pages': pages,
        'timings': {
            'queue_ms': queued_ms,
            'total_ms': round((time.monotonic() - started) * 1000, 1),
            'pages_ms': round(sum(page_ms), 1),
            'per_page_ms': round(sum(page_ms) / len(page_ms), 1) if page_ms else 0.0,
        },
    }


class Handler(BaseHTTPRequestHandler):
    server_version = 'dlux-ocr/' + SERVICE_VERSION
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):
        log.info('%s %s', self.address_string(), fmt % args)

    def reply(self, status, payload, headers=None):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.close_connection = True
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Connection', 'close')
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            log.debug('OCR client disconnected before reading its response.')

    def error(self, status, message, headers=None):
        self.reply(status, {'error': message}, headers)

    def do_GET(self):
        if urlparse(self.path).path != '/health':
            return self.error(HTTPStatus.NOT_FOUND, 'Not found.')
        if ENGINE is None:
            return self.reply(HTTPStatus.SERVICE_UNAVAILABLE, {'status': 'unavailable', 'error': UNAVAILABLE.get('reason', '')})
        self.reply(HTTPStatus.OK, {
            'status': 'ok', 'engine': ENGINE.name, 'engine_version': ENGINE.version,
            'model_version': ENGINE.model_version, 'service_version': SERVICE_VERSION,
            'workers': WORKERS, 'max_threads': MAX_THREADS, 'max_bytes': MAX_BYTES, 'max_pages': MAX_PAGES,
        })

    def do_POST(self):
        url = urlparse(self.path)
        if url.path != '/v1/ocr':
            return self.error(HTTPStatus.NOT_FOUND, 'Not found.')
        if ENGINE is None:
            return self.error(HTTPStatus.SERVICE_UNAVAILABLE, UNAVAILABLE.get('reason', 'The OCR engine is not available.'))
        if self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length', [])) != 1:
            return self.error(HTTPStatus.BAD_REQUEST, 'Send one Content-Length header without Transfer-Encoding.')
        query = parse_qs(url.query)
        mode = query.get('mode', ['auto'])[0]
        if mode not in MODES:
            return self.error(HTTPStatus.BAD_REQUEST, f'mode must be one of {sorted(MODES)}.')
        try:
            max_pages = min(max(int(query.get('max_pages', [MAX_PAGES])[0]), 1), MAX_PAGES)
            threads = min(max(int(query.get('threads', [DEFAULT_THREADS])[0]), 1), MAX_THREADS)
            length = int(self.headers.get('Content-Length', ''))
        except ValueError:
            return self.error(HTTPStatus.BAD_REQUEST, 'Content-Length, max_pages and threads must be integers.')
        if length <= 0:
            return self.error(HTTPStatus.BAD_REQUEST, 'The request body is empty.')
        if length > MAX_BYTES:
            self.close_connection = True
            return self.error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, f'The file exceeds {MAX_BYTES} bytes.')
        started = time.monotonic()
        if not SLOTS.acquire(timeout=QUEUE_WAIT):
            return self.error(HTTPStatus.SERVICE_UNAVAILABLE, 'The OCR engine is busy.', {'Retry-After': '30'})
        try:
            queued_ms = round((time.monotonic() - started) * 1000, 1)
            try:
                body = self.rfile.read(length)
            except TimeoutError:
                return self.error(HTTPStatus.REQUEST_TIMEOUT, 'The file upload timed out.')
            if len(body) != length:
                return self.error(HTTPStatus.BAD_REQUEST, 'The file upload is incomplete.')
            kind = detect_kind(body[:16])
            if kind is None:
                return self.error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, 'Send a PDF, PNG, JPEG, TIFF, BMP or WebP file.')
            with tempfile.NamedTemporaryFile(suffix='.' + kind) as handle:
                handle.write(body)
                handle.flush()
                result = ENGINE.convert(handle.name, mode=mode, max_pages=max_pages, threads=threads)
        except engines.EngineError as exc:
            return self.error(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc))
        except Exception:
            log.exception('OCR failed')
            return self.error(HTTPStatus.INTERNAL_SERVER_ERROR, 'The OCR engine failed on this file.')
        finally:
            SLOTS.release()
        self.reply(HTTPStatus.OK, summarize(result, kind, started, queued_ms, threads))


def main():
    global ENGINE
    logging.basicConfig(level=os.environ.get('OCR_LOG_LEVEL', 'INFO'), format='%(asctime)s %(levelname)s %(name)s %(message)s')
    try:
        ENGINE = engines.load()
    except ImportError as exc:
        UNAVAILABLE['reason'] = (
            f'The OCR engine is not installed in this image ({exc.name or exc}). Install django-lux[ocr] '
            'and rebuild the project image (python -m dlux.ocr.fetch_models downloads the models at build time).'
        )
        log.error('%s', UNAVAILABLE['reason'])
    else:
        log.info('%s %s (models %s) ready; models load on first use', ENGINE.name, ENGINE.version, ENGINE.model_version)
    server = OCRHTTPServer(('0.0.0.0', int(os.environ.get('OCR_PORT', '8080'))), Handler)
    server.daemon_threads = True
    # PID 1 ignores SIGTERM by default; without this `docker stop` waits out its timeout and kills.
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown, daemon=True).start())
    server.serve_forever()
    server.server_close()


if __name__ == '__main__':
    main()
