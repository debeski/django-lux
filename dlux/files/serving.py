"""Serve a stored file with range and revalidation support.

Callers keep their own access checks; this only turns an already-authorised
file into a response. A viewer such as pdf.js asks for byte ranges when the
server allows them, so it can draw the first page before a large scan has
finished downloading, and a reopened record revalidates with a 304 instead of
downloading the file again.
"""

import hashlib
import mimetypes
import os
import re

from django.http import FileResponse, Http404, HttpResponse, StreamingHttpResponse
from django.utils.cache import get_conditional_response
from django.utils.http import content_disposition_header, http_date, quote_etag

CHUNK_SIZE = 64 * 1024
# Private: these files sit behind a login. no-cache: revalidate every time, so a
# replaced file is never shown stale, but an unchanged one costs a 304.
CACHE_CONTROL = 'private, no-cache'
_RANGE = re.compile(r'^bytes=(\d*)-(\d*)$')


def _file_state(file_field):
    storage, name = file_field.storage, file_field.name
    size = storage.size(name)
    try:
        modified = storage.get_modified_time(name).timestamp()
    except (NotImplementedError, AttributeError, OSError):
        modified = None
    digest = hashlib.sha256(f'{name}:{size}:{modified}'.encode()).hexdigest()[:32]
    return size, modified, quote_etag(digest)


def parse_range(header, size):
    """`(start, end)` inclusive for a single satisfiable range, None to serve the
    whole file, or False when the range cannot be satisfied."""
    match = _RANGE.match((header or '').strip())
    if not match:
        return None
    first, last = match.groups()
    if not first and not last:
        return None
    if not first:
        suffix = int(last)
        if suffix == 0:
            return False
        return max(size - suffix, 0), size - 1
    start = int(first)
    end = min(int(last), size - 1) if last else size - 1
    if start >= size or start > end:
        return False
    return start, end


def _chunks(handle, remaining):
    try:
        while remaining > 0:
            data = handle.read(min(CHUNK_SIZE, remaining))
            if not data:
                break
            remaining -= len(data)
            yield data
    finally:
        handle.close()


def serve_file(request, file_field, *, content_type=None, as_attachment=False, filename=None):
    """Respond with `file_field`: 200, 206 for one byte range, 304, or 416."""
    if not file_field or not file_field.name or not file_field.storage.exists(file_field.name):
        raise Http404('No file is attached.')
    filename = filename or os.path.basename(file_field.name)
    size, modified, etag = _file_state(file_field)

    def finish(response):
        response['ETag'] = etag
        if modified is not None:
            response['Last-Modified'] = http_date(modified)
        response['Cache-Control'] = CACHE_CONTROL
        response['Accept-Ranges'] = 'bytes'
        return response

    conditional = get_conditional_response(request, etag=etag, last_modified=modified)
    if conditional is not None:
        return finish(conditional)

    requested = request.META.get('HTTP_RANGE')
    if_range = request.META.get('HTTP_IF_RANGE')
    if requested and (not if_range or if_range.strip() == etag):
        span = parse_range(requested, size)
        if span is False:
            response = HttpResponse(status=416)
            response['Content-Range'] = f'bytes */{size}'
            return finish(response)
        if span is not None:
            start, end = span
            handle = file_field.storage.open(file_field.name, 'rb')
            handle.seek(start)
            response = StreamingHttpResponse(
                _chunks(handle, end - start + 1), status=206,
                content_type=content_type or mimetypes.guess_type(filename)[0] or 'application/octet-stream',
            )
            response['Content-Length'] = str(end - start + 1)
            response['Content-Range'] = f'bytes {start}-{end}/{size}'
            response['Content-Disposition'] = content_disposition_header(as_attachment, filename)
            return finish(response)

    response = FileResponse(
        file_field.storage.open(file_field.name, 'rb'), as_attachment=as_attachment, filename=filename,
    )
    if content_type:
        response['Content-Type'] = content_type
    return finish(response)
