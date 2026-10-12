"""Bounded PDF assembly independent of any project's document models."""

from io import BytesIO


def assemble_pdf(manifest, read_source, *, max_pages=500, max_source_bytes=30 * 1024 * 1024):
    from pypdf import PdfReader, PdfWriter

    if not isinstance(manifest, list) or not manifest or len(manifest) > max_pages:
        raise ValueError('Select between 1 and %s pages.' % max_pages)
    writer = PdfWriter()
    readers = {}
    total = 0
    for item in manifest:
        if not isinstance(item, dict):
            raise ValueError('Invalid page selection.')
        source, page = item.get('source'), item.get('page')
        if not isinstance(source, str) or not source or isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise ValueError('Invalid page selection.')
        if source not in readers:
            data = read_source(source)
            total += len(data)
            if total > max_source_bytes:
                raise ValueError('Selected PDF sources exceed the upload limit.')
            reader = PdfReader(BytesIO(data))
            if reader.is_encrypted:
                raise ValueError('Encrypted PDFs cannot be edited.')
            readers[source] = reader
        reader = readers[source]
        if page > len(reader.pages):
            raise ValueError('Selected page is outside the PDF page range.')
        writer.add_page(reader.pages[page - 1])
    result = BytesIO()
    writer.write(result)
    return result.getvalue()
