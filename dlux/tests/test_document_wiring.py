import json
import shutil
import tempfile
from io import BytesIO
from unittest import skipUnless

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template import Context, Template
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from PIL import Image

try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    PdfReader = PdfWriter = None

from dlux.files.forms import apply_document_file_fields, record_document_file_uploads
from dlux.files.registry import register_document_file, unregister_document_file
from dlux.files.views import document_revision
from dlux.models import FileVersion, Scope, ScopeSettings, SystemSettings
from dlux.tests.document_files_app.models import Paper


def pdf_bytes(pages=1):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=100, height=200)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def png_bytes():
    output = BytesIO()
    Image.new('RGB', (144, 72), 'red').save(output, format='PNG', dpi=(72, 72))
    return output.getvalue()


class PaperForm(forms.ModelForm):
    class Meta:
        model = Paper
        fields = ['title', 'pdf_file']


@skipUnless(PdfReader, 'Install django-lux[pdf] to test document files.')
class DocumentFileWiringTests(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, True)
        override = override_settings(MEDIA_ROOT=self.media)
        override.enable()
        self.addCleanup(override.disable)
        settings_obj = SystemSettings.load()
        settings_obj.is_configured = True
        settings_obj.save()
        cache.clear()
        self.addCleanup(cache.clear)
        register_document_file(Paper, 'pdf_file')
        self.addCleanup(unregister_document_file, Paper, 'pdf_file')
        User = get_user_model()
        self.admin = User.objects.create_superuser('files-admin', 'files-admin@example.com', 'pw12345!')
        self.reader = User.objects.create_user('files-reader', password='pw12345!')
        self.reader.user_permissions.add(Permission.objects.get(codename='view_paper'))
        self.paper = Paper.objects.create(title='Annual report')
        self.paper.pdf_file.save('original.pdf', ContentFile(pdf_bytes(2)))

    def url(self, name, **extra):
        kwargs = {'app_label': 'document_files_app', 'model_name': 'paper', 'pk': self.paper.pk, 'field_name': 'pdf_file', **extra}
        return reverse(name, kwargs=kwargs)

    def login(self, user):
        self.client.force_login(user)

    def test_source_and_download_follow_view_permission(self):
        self.login(self.reader)
        source = self.client.get(self.url('dlux_document_file_source'))
        self.assertEqual(source.status_code, 200)
        self.assertIn('inline', source['Content-Disposition'])
        self.assertIn('attachment', self.client.get(self.url('dlux_document_file_download'))['Content-Disposition'])
        self.assertEqual(self.client.get(self.url('dlux_document_file_edit'), HTTP_X_REQUESTED_WITH='XMLHttpRequest').status_code, 403)
        self.login(get_user_model().objects.create_user('nobody'))
        self.assertEqual(self.client.get(self.url('dlux_document_file_source')).status_code, 403)

    def test_unregistered_fields_and_unknown_models_are_not_served(self):
        self.login(self.admin)
        self.assertEqual(self.client.get(self.url('dlux_document_file_source', field_name='title')).status_code, 404)
        self.assertEqual(self.client.get(self.url('dlux_document_file_source', model_name='nothing')).status_code, 404)

    def test_editor_saves_a_new_version_with_page_options(self):
        self.login(self.admin)
        html = self.client.get(self.url('dlux_document_file_edit'), HTTP_X_REQUESTED_WITH='XMLHttpRequest').json()['html']
        self.assertIn('data-accept-extensions=".pdf .jpg .jpeg .png .tif .tiff .webp"', html)
        manifest = [{'source': 'current', 'page': 2, 'rotate': 90}, {'source': 'upload_0', 'page': 1, 'fit': 'a4'}]
        response = self.client.post(self.url('dlux_document_file_edit'), {
            'revision': document_revision(self.paper), 'manifest': json.dumps(manifest),
            'upload_0': SimpleUploadedFile('photo.png', png_bytes()),
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.json(), {'success': True, 'refresh_parent': True})
        self.paper.refresh_from_db()
        pages = PdfReader(self.paper.pdf_file.open('rb')).pages
        self.assertEqual([(round(float(p.mediabox.width)), p.rotation) for p in pages], [(100, 90), (842, 0)])
        version = FileVersion.all_objects.get()
        self.assertEqual((version.version_number, version.page_count, version.created_by), (1, 2, self.admin))

        stale = self.client.post(self.url('dlux_document_file_edit'), {'revision': 'stale', 'manifest': '[]'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(stale.status_code, 409)

    def test_history_lists_and_downloads_versions(self):
        from dlux.files.history import save_new_version

        original = self.paper.pdf_file.read()
        save_new_version(self.paper, pdf_bytes(1), user=self.admin)
        self.login(self.reader)
        html = self.client.get(self.url('dlux_document_file_history'), HTTP_X_REQUESTED_WITH='XMLHttpRequest').json()['html']
        version_url = self.url('dlux_document_file_version', version=1)
        self.assertIn(version_url, html)
        self.assertIn('files-admin', html)
        self.admin.first_name = '<Editor>'
        self.admin.last_name = 'Name'
        self.admin.save(update_fields=['first_name', 'last_name'])
        html = self.client.get(self.url('dlux_document_file_history'), HTTP_X_REQUESTED_WITH='XMLHttpRequest').json()['html']
        self.assertIn('&lt;Editor&gt; Name', html)
        self.assertNotIn('<Editor>', html)
        FileVersion.all_objects.update(created_by=None)
        html = self.client.get(self.url('dlux_document_file_history'), HTTP_X_REQUESTED_WITH='XMLHttpRequest').json()['html']
        self.assertIn('<td>—</td>', html)
        download = self.client.get(version_url)
        self.assertEqual(b''.join(download.streaming_content), original)
        self.assertEqual(self.client.get(self.url('dlux_document_file_version', version=9)).status_code, 404)

    def test_can_access_hook_grants_and_refuses(self):
        outsider = get_user_model().objects.create_user('reviewer-only')
        register_document_file(Paper, 'pdf_file', can_access=lambda request, document, action: action == 'view' and request.user == outsider or (False if request.user.is_superuser else None))
        self.login(outsider)
        self.assertEqual(self.client.get(self.url('dlux_document_file_source')).status_code, 200)
        self.assertEqual(self.client.get(self.url('dlux_document_file_download')).status_code, 403)
        self.login(self.admin)
        self.assertEqual(self.client.get(self.url('dlux_document_file_source')).status_code, 403)

    def test_scope_hides_other_scopes(self):
        ScopeSettings.objects.update_or_create(pk=1, defaults={'is_enabled': True})
        other = Scope.objects.create(name='Other branch')
        mine = Scope.objects.create(name='My branch')
        Paper.all_objects.filter(pk=self.paper.pk).update(scope=other)
        self.reader.profile.scope = mine
        self.reader.profile.save()
        cache.clear()
        self.login(self.reader)
        self.assertEqual(self.client.get(self.url('dlux_document_file_source')).status_code, 404)

    def test_viewer_tag_uses_dlux_routes(self):
        request = RequestFactory().get('/')
        request.user = self.admin
        html = Template("{% load dlux_files %}{% dlux_document_viewer paper %}").render(Context({'request': request, 'paper': self.paper}))
        self.assertIn(f'data-pdf-url="{self.url("dlux_document_file_source")}"', html)
        self.assertIn(self.url('dlux_document_file_edit'), html)

    def test_form_gets_the_file_card_and_type_check(self):
        form = apply_document_file_fields(PaperForm())
        widget = form.fields['pdf_file'].widget
        self.assertEqual(type(widget).__name__, 'DluxFileInput')
        self.assertTrue(widget.show_scan)
        self.assertIn('image/png', widget.attrs['accept'])
        bad = apply_document_file_fields(PaperForm({'title': 'x'}, {'pdf_file': SimpleUploadedFile('fake.pdf', b'hello')}))
        self.assertFalse(bad.is_valid())
        self.assertIn('pdf_file', bad.errors)

    def test_form_uploaded_image_becomes_the_pdf_and_old_file_is_kept(self):
        original = self.paper.pdf_file.read()
        previous = {'pdf_file': self.paper.pdf_file.name}
        form = apply_document_file_fields(PaperForm({'title': 'Annual report'}, {'pdf_file': SimpleUploadedFile('photo.png', png_bytes())}, instance=self.paper))
        self.assertTrue(form.is_valid(), form.errors)
        paper = form.save()
        uploaded_image = paper.pdf_file.name
        record_document_file_uploads(paper, previous, user=self.admin)
        paper.refresh_from_db()
        self.assertTrue(paper.pdf_file.name.endswith('.pdf'))
        self.assertEqual(len(PdfReader(paper.pdf_file.open('rb')).pages), 1)
        self.assertFalse(paper.pdf_file.storage.exists(uploaded_image))
        self.assertEqual(FileVersion.all_objects.get().archived_file.read(), original)

    def test_generic_modal_save_records_history(self):
        self.login(self.admin)
        url = reverse('modal_manager', args=['document_files_app', 'paper', self.paper.pk])
        response = self.client.post(url, {'title': 'Annual report', 'pdf_file': SimpleUploadedFile('new.pdf', pdf_bytes(3))}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertTrue(response.json().get('success'), response.content[:500])
        self.assertEqual(FileVersion.all_objects.get().action_type, 'replace')


class AttachmentForm(forms.ModelForm):
    class Meta:
        model = Paper
        fields = ['title', 'attachment']


class PlainFileFieldUploadTests(TestCase):
    """Break-it R2-001: a plain file field took an HTML or SVG upload that then ran as the site."""

    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, True)
        override = override_settings(MEDIA_ROOT=self.media)
        override.enable()
        self.addCleanup(override.disable)

    def form(self, name, data):
        return apply_document_file_fields(AttachmentForm({'title': 'x'}, {'attachment': SimpleUploadedFile(name, data)}))

    def test_pages_svg_and_scripts_are_refused(self):
        for name, data in (
            ('x.html', b'<html><script>alert(1)</script></html>'),
            ('pic.svg', b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>'),
            ('PIC.SVG', b'<svg/>'),
            ('run.js', b'alert(1)'),
            ('page.xhtml', b'<html/>'),
            ('renamed.txt', b'\xef\xbb\xbf  <!DOCTYPE html><script>alert(1)</script>'),
            ('noext', b'<svg onload="alert(1)"/>'),
            ('drawing.xml', b'<?xml version="1.0"?>\n<svg xmlns="http://www.w3.org/2000/svg"/>'),
        ):
            with self.subTest(name=name):
                form = self.form(name, data)
                self.assertFalse(form.is_valid())
                self.assertIn('active_content', [error.code for error in form.errors.as_data()['attachment']])

    def test_ordinary_files_are_kept(self):
        for name, data in (('notes.txt', b'plain notes'), ('scan.pdf', b'%PDF-1.4'), ('photo.png', png_bytes()),
                           ('feed.xml', b'<?xml version="1.0"?><invoice/>'), ('table.csv', b'a,b\n1,2\n')):
            with self.subTest(name=name):
                form = self.form(name, data)
                self.assertTrue(form.is_valid(), form.errors)

    def test_a_field_that_lists_its_own_extensions_decides_itself(self):
        from django.core.validators import FileExtensionValidator

        field = Paper._meta.get_field('attachment')
        validator = FileExtensionValidator(['svg'])
        field.validators.append(validator)
        self.addCleanup(field.validators.remove, validator)
        self.assertTrue(self.form('logo.svg', b'<svg/>').is_valid())

    def test_the_check_is_added_once(self):
        form = apply_document_file_fields(apply_document_file_fields(AttachmentForm()))
        names = [type(validator).__name__ for validator in form.fields['attachment'].validators]
        self.assertEqual(names.count('_ActiveContentValidator'), 1)
