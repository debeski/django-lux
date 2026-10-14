"""Built-in file types: PDF, and JPEG/PNG/TIFF/WebP images that become PDF pages."""

from io import BytesIO

IMAGE_FORMATS = {'JPEG', 'PNG', 'TIFF', 'WEBP'}
# Refuse a single frame above this many pixels: ~ an A3 page scanned at 1200 DPI.
MAX_IMAGE_PIXELS = 280_000_000
DEFAULT_DPI = 150


def sniff_pdf(data):
    return b'%PDF-' in data[:1024]


def _open_image(data):
    import warnings

    from PIL import Image

    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        image = Image.open(BytesIO(data))
    if image.format not in IMAGE_FORMATS:
        image.close()
        raise ValueError('Unsupported image format.')
    if image.width * image.height > MAX_IMAGE_PIXELS:
        image.close()
        raise ValueError('Image is too large.')
    return image


def sniff_image(data):
    from PIL import Image

    try:
        with _open_image(data) as image:
            image.verify()
        return True
    except (ValueError, OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        return False


def _frames(image):
    from PIL import ImageSequence

    if image.format == 'TIFF':
        return [frame.copy() for frame in ImageSequence.Iterator(image)]
    image.seek(0)
    return [image.copy()]


def _page_ready(frame):
    """Upright, opaque and in a mode the PDF writer takes."""
    from PIL import Image, ImageOps

    frame = ImageOps.exif_transpose(frame)
    if frame.mode in ('RGBA', 'LA') or (frame.mode == 'P' and 'transparency' in frame.info):
        rgba = frame.convert('RGBA')
        flat = Image.new('RGB', rgba.size, (255, 255, 255))
        flat.paste(rgba, mask=rgba.getchannel('A'))
        return flat
    if frame.mode in ('1', 'L', 'RGB', 'CMYK'):
        return frame
    return frame.convert('RGB')


def _dpi(image):
    dpi = image.info.get('dpi')
    try:
        value = float(dpi[0] if isinstance(dpi, (tuple, list)) else dpi)
    except (TypeError, ValueError, IndexError):
        return DEFAULT_DPI
    return value if 72 <= value <= 1200 else DEFAULT_DPI


# EXIF orientation -> clockwise page rotation for an untouched JPEG; mirrored
# orientations (2, 4, 5, 7) cannot be expressed as /Rotate and are re-drawn losslessly.
_JPEG_ROTATION = {1: 0, 3: 180, 6: 90, 8: 270}
_COLOR_SPACES = {'1': ('/DeviceGray', 1), 'L': ('/DeviceGray', 8), 'RGB': ('/DeviceRGB', 8), 'CMYK': ('/DeviceCMYK', 8)}


def _orientation(image):
    try:
        return image.getexif().get(0x0112, 1) or 1
    except Exception:
        return 1


def _image_stream(width, height, mode, data, *, jpeg):
    from pypdf.generic import DecodedStreamObject, NameObject, NumberObject, StreamObject

    color_space, bits = _COLOR_SPACES[mode]
    if jpeg:
        stream = StreamObject()
        stream.set_data(data)
        stream[NameObject('/Filter')] = NameObject('/DCTDecode')
    else:
        stream = DecodedStreamObject()
        stream.set_data(data)
        stream = stream.flate_encode(level=9)
    stream.update({
        NameObject('/Type'): NameObject('/XObject'),
        NameObject('/Subtype'): NameObject('/Image'),
        NameObject('/Width'): NumberObject(width),
        NameObject('/Height'): NumberObject(height),
        NameObject('/ColorSpace'): NameObject(color_space),
        NameObject('/BitsPerComponent'): NumberObject(bits),
    })
    return stream


def _add_image_page(writer, stream, width, height, dpi, rotate=0):
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    page_w, page_h = width * 72.0 / dpi, height * 72.0 / dpi
    page = writer.add_blank_page(width=page_w, height=page_h)
    content = DecodedStreamObject()
    content.set_data(f'q {page_w:.4f} 0 0 {page_h:.4f} 0 0 cm /Im0 Do Q'.encode())
    page[NameObject('/Resources')] = DictionaryObject({
        NameObject('/XObject'): DictionaryObject({NameObject('/Im0'): writer._add_object(stream)}),
    })
    page[NameObject('/Contents')] = writer._add_object(content.flate_encode())
    if rotate:
        page.rotate(rotate)


def image_to_pdf(data):
    """One PDF page per image (per frame of a multi-page TIFF), sized from the image at its own DPI, without quality loss.

    A JPEG is embedded byte-for-byte (its EXIF orientation becomes the page
    rotation); every other image is stored as Flate-compressed pixels, which is
    lossless. Transparency is flattened onto white.
    """
    from PIL import Image
    from pypdf import PdfWriter

    writer = PdfWriter()
    try:
        with _open_image(data) as image:
            dpi = _dpi(image)
            orientation = _orientation(image)
            if image.format == 'JPEG' and image.mode in ('L', 'RGB') and orientation in _JPEG_ROTATION:
                stream = _image_stream(image.width, image.height, image.mode, data, jpeg=True)
                _add_image_page(writer, stream, image.width, image.height, dpi, _JPEG_ROTATION[orientation])
            else:
                for frame in _frames(image):
                    page = _page_ready(frame)
                    stream = _image_stream(page.width, page.height, page.mode, page.tobytes(), jpeg=False)
                    _add_image_page(writer, stream, page.width, page.height, dpi)
    except (OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError('The image could not be read.') from exc
    output = BytesIO()
    writer.write(output)
    return output.getvalue()
