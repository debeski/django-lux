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


def image_to_pdf(data):
    """One PDF page per image (per frame of a multi-page TIFF), sized from the image at its own DPI."""
    from PIL import Image

    try:
        with _open_image(data) as image:
            dpi = _dpi(image)
            pages = [_page_ready(frame) for frame in _frames(image)]
    except (OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError('The image could not be read.') from exc
    output = BytesIO()
    pages[0].save(output, format='PDF', save_all=True, append_images=pages[1:], resolution=dpi)
    return output.getvalue()


def register_builtin_types():
    from . import register_file_type

    register_file_type(
        'pdf', extensions=['.pdf'], mime_types=['application/pdf'], sniff=sniff_pdf, to_pdf=lambda data: data,
        label_key='files_type_pdf', label='PDF',
    )
    register_file_type(
        'image', extensions=['.jpg', '.jpeg', '.png', '.tif', '.tiff', '.webp'],
        mime_types=['image/jpeg', 'image/png', 'image/tiff', 'image/webp'], sniff=sniff_image, to_pdf=image_to_pdf,
        label_key='files_type_image', label='Image',
    )
