from io import BytesIO
from unittest import skipUnless

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from PIL import Image

try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    PdfReader = PdfWriter = None

from dlux.files import (
    accept_attribute, detect_file_type, get_file_type, register_file_type, to_pdf_bytes, validate_upload,
)
from dlux.files.types import DEFAULT_DPI


def image_bytes(fmt, size=(300, 150), mode='RGB', dpi=None, frames=1, exif_orientation=None):
    image = Image.new(mode, size, 'red' if mode != 'RGBA' else (255, 0, 0, 0))
    output = BytesIO()
    kwargs = {}
    if dpi:
        kwargs['dpi'] = (dpi, dpi)
    if frames > 1:
        kwargs.update(save_all=True, append_images=[Image.new(mode, (size[1], size[0]), 'blue') for _ in range(frames - 1)])
    if exif_orientation:
        exif = Image.Exif()
        exif[0x0112] = exif_orientation
        kwargs['exif'] = exif
    image.save(output, format=fmt, **kwargs)
    return output.getvalue()


def pdf_bytes(sizes):
    writer = PdfWriter()
    for width, height in sizes:
        writer.add_blank_page(width=width, height=height)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def page_sizes(data):
    pages = PdfReader(BytesIO(data)).pages
    return [(round(float(page.mediabox.width)), round(float(page.mediabox.height)), page.rotation) for page in pages]


class FileTypeRegistryTests(SimpleTestCase):
    def test_builtin_kinds_and_accept_attribute(self):
        self.assertEqual(get_file_type('pdf').extensions, ('.pdf',))
        self.assertEqual(get_file_type('image').extensions, ('.jpg', '.jpeg', '.png', '.tif', '.tiff', '.webp'))
        attribute = accept_attribute()
        for value in ('application/pdf', '.pdf', 'image/webp', '.tiff'):
            self.assertIn(value, attribute)
        self.assertEqual(accept_attribute(('pdf',)), 'application/pdf,.pdf')

    def test_content_decides_not_the_name(self):
        self.assertEqual(detect_file_type(pdf_bytes([(100, 100)]), 'scan.pdf').name, 'pdf')
        for fmt, name in (('JPEG', 'a.jpg'), ('JPEG', 'a.jpeg'), ('PNG', 'a.png'), ('TIFF', 'a.tif'), ('TIFF', 'a.tiff'), ('WEBP', 'a.webp')):
            with self.subTest(name=name):
                self.assertEqual(detect_file_type(image_bytes(fmt), name).name, 'image')
        with self.assertRaisesRegex(ValueError, 'damaged'):
            detect_file_type(image_bytes('PNG'), 'renamed.pdf')
        with self.assertRaisesRegex(ValueError, 'damaged'):
            detect_file_type(pdf_bytes([(100, 100)]), 'renamed.png')
        with self.assertRaisesRegex(ValueError, 'damaged'):
            detect_file_type(b'not an image at all', 'broken.jpg')
        with self.assertRaisesRegex(ValueError, 'not accepted'):
            detect_file_type(b'GIF89a', 'animation.gif')
        with self.assertRaisesRegex(ValueError, 'not accepted'):
            detect_file_type(image_bytes('PNG'), 'photo.png', accept=('pdf',))

    def test_validate_upload_raises_validation_error_and_rewinds(self):
        upload = SimpleUploadedFile('photo.png', image_bytes('PNG'))
        self.assertEqual(validate_upload(upload).name, 'image')
        self.assertEqual(upload.read(4), b'\x89PNG')
        with self.assertRaises(ValidationError):
            validate_upload(SimpleUploadedFile('fake.pdf', b'hello'))
        with self.assertRaises(ValidationError):
            validate_upload(SimpleUploadedFile('big.png', image_bytes('PNG')), limit=10)

    def test_projects_register_their_own_kinds(self):
        register_file_type('text', extensions=['txt'], sniff=lambda data: data.isascii(), label='Text')
        self.addCleanup(lambda: __import__('dlux.files', fromlist=['_registry'])._registry.pop('text'))
        self.assertEqual(detect_file_type(b'plain', 'notes.TXT', accept=('text',)).name, 'text')
        with self.assertRaisesRegex(ValueError, 'cannot be turned into PDF'):
            to_pdf_bytes(b'plain', 'notes.txt', accept=('text',))
        with self.assertRaises(LookupError):
            get_file_type('missing')


@skipUnless(PdfReader, 'Install django-lux[pdf] to test page conversion.')
class ImagePageTests(SimpleTestCase):
    def test_each_format_becomes_a_page_at_its_own_size(self):
        for fmt in ('JPEG', 'PNG', 'TIFF', 'WEBP'):
            with self.subTest(fmt=fmt):
                data = to_pdf_bytes(image_bytes(fmt, size=(300, 150), dpi=150), f'a.{fmt.lower()}')
                self.assertEqual(page_sizes(data), [(144, 72, 0)])

    def test_missing_or_absurd_dpi_falls_back(self):
        width = round(300 / DEFAULT_DPI * 72)
        self.assertEqual(page_sizes(to_pdf_bytes(image_bytes('PNG'), 'a.png'))[0][0], width)
        self.assertEqual(page_sizes(to_pdf_bytes(image_bytes('PNG', dpi=5000), 'a.png'))[0][0], width)

    def test_multipage_tiff_gives_one_page_per_frame(self):
        self.assertEqual(len(page_sizes(to_pdf_bytes(image_bytes('TIFF', frames=3), 'scan.tiff'))), 3)

    def test_exif_orientation_and_transparency_are_applied(self):
        upright = page_sizes(to_pdf_bytes(image_bytes('JPEG', size=(300, 150), dpi=72, exif_orientation=6), 'phone.jpg'))
        self.assertEqual(upright, [(150, 300, 0)])
        self.assertEqual(len(page_sizes(to_pdf_bytes(image_bytes('PNG', mode='RGBA'), 'logo.png'))), 1)

    def test_decompression_bombs_are_refused(self):
        from unittest.mock import patch

        with patch('dlux.files.types.MAX_IMAGE_PIXELS', 100):
            with self.assertRaises(ValueError):
                to_pdf_bytes(image_bytes('PNG'), 'huge.png')


@skipUnless(PdfReader, 'Install django-lux[pdf] to test optional PDF assembly.')
class AssemblyPageOptionTests(SimpleTestCase):
    def assemble(self, manifest, sources, **kwargs):
        from dlux.pdf.assembly import assemble_pdf

        return assemble_pdf(manifest, sources.__getitem__, **kwargs)

    def test_images_join_pdf_pages_when_accepted(self):
        sources = {'current': pdf_bytes([(100, 200)]), 'upload_0': image_bytes('PNG', dpi=72)}
        output = self.assemble([{'source': 'current', 'page': 1}, {'source': 'upload_0', 'page': 1}], sources, accept=('pdf', 'image'))
        self.assertEqual(page_sizes(output), [(100, 200, 0), (300, 150, 0)])
        with self.assertRaises(ValueError):
            self.assemble([{'source': 'upload_0', 'page': 1}], sources)

    def test_rotation_is_recorded_per_page(self):
        output = self.assemble([{'source': 'current', 'page': 1, 'rotate': 90}], {'current': pdf_bytes([(100, 200)])})
        self.assertEqual(page_sizes(output), [(100, 200, 90)])

    def test_fit_to_a4_keeps_orientation_and_proportions(self):
        sources = {'current': pdf_bytes([(842, 1191), (400, 100)])}
        output = self.assemble([
            {'source': 'current', 'page': 1, 'fit': 'a4'},
            {'source': 'current', 'page': 2, 'fit': 'a4'},
            {'source': 'current', 'page': 2, 'fit': 'a4', 'rotate': 90},
        ], sources)
        self.assertEqual(page_sizes(output), [(595, 842, 0), (842, 595, 0), (595, 842, 0)])

    def test_invalid_page_options_are_rejected(self):
        for item in ({'rotate': 45}, {'rotate': True}, {'fit': 'letter'}):
            with self.subTest(item=item), self.assertRaises(ValueError):
                self.assemble([{'source': 'current', 'page': 1, **item}], {'current': pdf_bytes([(100, 100)])})
