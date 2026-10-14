"""Bounded PDF assembly independent of any project's document models."""

from io import BytesIO

ROTATIONS = (0, 90, 180, 270)
FIT_CHOICES = (None, 'a4')
A4_POINTS = (595.276, 841.89)


def _page_choice(item):
    if not isinstance(item, dict):
        raise ValueError('Invalid page selection.')
    source, page = item.get('source'), item.get('page')
    rotate, fit = item.get('rotate', 0), item.get('fit')
    if not isinstance(source, str) or not source or isinstance(page, bool) or not isinstance(page, int) or page < 1:
        raise ValueError('Invalid page selection.')
    if isinstance(rotate, bool) or rotate not in ROTATIONS or fit not in FIT_CHOICES:
        raise ValueError('Invalid page selection.')
    return source, page, rotate, fit


def _add_fitted_to_a4(writer, source_page, rotate):
    """Append an A4 sheet (portrait or landscape following the page) with the page scaled to fit and centred."""
    from pypdf import PdfWriter, Transformation

    scratch = PdfWriter()
    page = scratch.add_page(source_page)
    if rotate:
        page.rotate(rotate)
    page.transfer_rotation_to_content()
    box = page.mediabox
    width, height = float(box.width), float(box.height)
    sheet_w, sheet_h = A4_POINTS if height >= width else A4_POINTS[::-1]
    scale = min(sheet_w / width, sheet_h / height)
    offset_x = (sheet_w - width * scale) / 2 - float(box.left) * scale
    offset_y = (sheet_h - height * scale) / 2 - float(box.bottom) * scale
    sheet = writer.add_blank_page(width=sheet_w, height=sheet_h)
    sheet.merge_transformed_page(page, Transformation().scale(scale, scale).translate(offset_x, offset_y))


def assemble_pdf(manifest, read_source, *, max_pages=500, max_source_bytes=30 * 1024 * 1024, accept=('pdf',)):
    """Build one PDF from `manifest` pages.

    Each item names a `source`, a one-based `page`, and optionally `rotate`
    (0/90/180/270, clockwise) and `fit` (`"a4"`). `read_source(key)` returns the
    source's bytes; any kind in `accept` that has a page converter is turned into
    PDF pages first, so an image is a one-page source.
    """
    from pypdf import PdfReader, PdfWriter

    from dlux.files import to_pdf_bytes

    if not isinstance(manifest, list) or not manifest or len(manifest) > max_pages:
        raise ValueError('Select between 1 and %s pages.' % max_pages)
    writer = PdfWriter()
    readers = {}
    total = 0
    for item in manifest:
        source, page_number, rotate, fit = _page_choice(item)
        if source not in readers:
            data = read_source(source)
            total += len(data)
            if total > max_source_bytes:
                raise ValueError('Selected PDF sources exceed the upload limit.')
            reader = PdfReader(BytesIO(to_pdf_bytes(data, accept=accept)))
            if reader.is_encrypted:
                raise ValueError('Encrypted PDFs cannot be edited.')
            readers[source] = reader
        reader = readers[source]
        if page_number > len(reader.pages):
            raise ValueError('Selected page is outside the PDF page range.')
        if fit == 'a4':
            _add_fitted_to_a4(writer, reader.pages[page_number - 1], rotate)
        else:
            page = writer.add_page(reader.pages[page_number - 1])
            if rotate:
                page.rotate(rotate)
    result = BytesIO()
    writer.write(result)
    return result.getvalue()
