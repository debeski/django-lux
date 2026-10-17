import shutil
import tempfile
from io import BytesIO, StringIO
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    PdfReader = PdfWriter = None

from dlux.files.history import (
    archive_previous, next_version_number, record_upload, save_new_version, versions_for,
)
from dlux.files.registry import register_document_file, unregister_document_file
from dlux.models import FileVersion, Scope
from dlux.tests.document_files_app.models import LegacyFileVersion, Paper


def pdf_bytes(pages=1, width=100):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=width, height=200)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class MediaMixin:
    def setUp(self):
        super().setUp()
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, True)
        override = override_settings(MEDIA_ROOT=self.media)
        override.enable()
        self.addCleanup(override.disable)
        self.user = get_user_model().objects.create_user('history-user')

    def paper(self, data=None, **fields):
        paper = Paper.objects.create(title=fields.pop('title', 'Annual report'), **fields)
        if data is not None:
            paper.pdf_file.save('original.pdf', ContentFile(data))
        return paper


@skipUnless(PdfReader, 'Install django-lux[pdf] to test file history.')
class HistoryServiceTests(MediaMixin, TestCase):
    def setUp(self):
        super().setUp()
        register_document_file(Paper, 'pdf_file', pdf_metadata=lambda doc: {'/Title': doc.title, '/Author': 'Records'})
        self.addCleanup(unregister_document_file, Paper, 'pdf_file')

    def test_editor_save_keeps_the_previous_file_byte_for_byte(self):
        original = pdf_bytes(2)
        paper = self.paper(original)
        before = paper.pdf_file.name
        saved, pages = save_new_version(paper, pdf_bytes(1), user=self.user)
        version = versions_for(paper).get()
        self.assertEqual((version.version_number, version.action_type, version.page_count), (1, 'edit', 2))
        self.assertEqual(version.archived_file.read(), original)
        self.assertEqual((version.active_name_before, version.active_name_after), (before, saved))
        self.assertEqual(version.created_by, self.user)
        paper.refresh_from_db()
        self.assertEqual(paper.pdf_file.name, saved)
        self.assertNotEqual(saved, before)
        self.assertEqual(paper.pdf_file.storage.open(before).read(), original)
        reader = PdfReader(paper.pdf_file.open('rb'))
        self.assertEqual((len(reader.pages), reader.metadata['/Title'], reader.metadata['/Author']), (1, 'Annual report', 'Records'))
        self.assertEqual(pages, 1)

    def test_history_rows_follow_the_document_scope_not_the_actor(self):
        scope = Scope.objects.create(name='Branch')
        paper = self.paper(pdf_bytes(), scope=scope)
        save_new_version(paper, pdf_bytes(), user=self.user)
        self.assertEqual(versions_for(paper).get().scope, scope)

    def test_form_upload_and_clear_are_recorded(self):
        original = pdf_bytes(3)
        paper = self.paper(original)
        previous = paper.pdf_file.name
        paper.pdf_file.save('replacement.pdf', ContentFile(pdf_bytes(1)))
        record_upload(paper, previous, user=self.user)
        replaced = versions_for(paper).get()
        self.assertEqual((replaced.action_type, replaced.archived_file.read()), ('replace', original))
        paper.refresh_from_db()
        self.assertEqual(PdfReader(paper.pdf_file.open('rb')).metadata['/Title'], 'Annual report')

        previous = paper.pdf_file.name
        paper.pdf_file = None
        paper.save()
        record_upload(paper, previous, user=self.user)
        cleared = versions_for(paper).first()
        self.assertEqual((cleared.version_number, cleared.action_type, cleared.active_name_after), (2, 'clear', ''))
        self.assertIsNone(record_upload(paper, '', user=self.user))

    def test_missing_original_refuses_and_writes_nothing(self):
        paper = self.paper(pdf_bytes())
        paper.pdf_file.storage.delete(paper.pdf_file.name)
        with self.assertRaisesRegex(ValueError, 'missing'):
            save_new_version(paper, pdf_bytes())
        self.assertFalse(FileVersion.all_objects.exists())

    def test_version_numbers_count_soft_deleted_rows(self):
        paper = self.paper(pdf_bytes())
        archive_previous(paper, paper.pdf_file.name)
        versions_for(paper).get().delete()
        self.assertEqual(next_version_number(paper), 2)

    def test_soft_delete_and_restore_carry_the_history(self):
        paper = self.paper(pdf_bytes())
        save_new_version(paper, pdf_bytes())
        save_new_version(paper, pdf_bytes())
        earlier = FileVersion.all_objects.get(version_number=1)
        earlier.delete()
        paper.delete()
        later = FileVersion.all_objects.get(version_number=2)
        self.assertEqual(later.deleted_at, paper.deleted_at)
        paper.restore()
        self.assertEqual(list(versions_for(paper).values_list('version_number', flat=True)), [2])

        Paper.all_objects.filter(pk=paper.pk).delete()
        self.assertFalse(versions_for(paper).exists())
        Paper.all_objects.filter(pk=paper.pk).restore()
        self.assertEqual(list(versions_for(paper).values_list('version_number', flat=True)), [2])

    def test_unregistered_models_are_not_touched(self):
        unregister_document_file(Paper, 'pdf_file')
        paper = self.paper(pdf_bytes())
        archive_previous(paper, paper.pdf_file.name)
        paper.delete()
        self.assertIsNone(FileVersion.all_objects.get().deleted_at)


@skipUnless(PdfReader, 'Install django-lux[pdf] to test file history.')
class AdoptHistoryCommandTests(MediaMixin, TestCase):
    def legacy(self, paper, version, **fields):
        row = LegacyFileVersion(
            content_type=ContentType.objects.get_for_model(Paper), object_id=paper.pk, document_model='Paper',
            version_number=version, action_type=fields.pop('action_type', 'edit'), page_count=2,
            active_name_before=f'papers/v{version}.pdf', active_name_after='papers/current.pdf',
            metadata={'number': '7'}, created_by=self.user, updated_by=self.user, **fields,
        )
        row.archived_file.save(f'v{version}.pdf', ContentFile(pdf_bytes(2)), save=False)
        row.save()
        return row

    def run_command(self, *args):
        out = StringIO()
        call_command('dlux_adopt_file_history', 'document_files_app.LegacyFileVersion', *args, stdout=out)
        return out.getvalue()

    def test_dry_run_apply_rerun_and_verify(self):
        scope = Scope.objects.create(name='Branch')
        paper = self.paper(pdf_bytes())
        first = self.legacy(paper, 1, scope=scope)
        second = self.legacy(paper, 2, action_type='replace')
        LegacyFileVersion.all_objects.filter(pk=second.pk).update(deleted_at=first.created_at, deleted_by=self.user)

        self.assertIn('2 to copy', self.run_command())
        self.assertFalse(FileVersion.all_objects.exists())

        self.assertIn('Copied 2 rows', self.run_command('--apply'))
        copy = FileVersion.all_objects.get(version_number=1)
        first.refresh_from_db()
        for name in ('content_type_id', 'object_id', 'field_name', 'action_type', 'page_count', 'metadata', 'scope_id',
                     'created_at', 'updated_at', 'created_by_id', 'active_name_before', 'active_name_after'):
            self.assertEqual(getattr(copy, name), getattr(first, name), name)
        self.assertEqual(copy.archived_file.name, first.archived_file.name)
        self.assertEqual(FileVersion.all_objects.get(version_number=2).deleted_by, self.user)
        self.assertEqual(LegacyFileVersion.all_objects.count(), 2)

        output = self.run_command('--apply', '--verify')
        self.assertIn('2 already adopted', output)
        self.assertIn('Verified 2 rows', output)

    def test_conflicts_stop_before_writing(self):
        paper = self.paper(pdf_bytes())
        self.legacy(paper, 1)
        self.legacy(paper, 2)
        archive_previous(paper, paper.pdf_file.name)
        with self.assertRaisesRegex(CommandError, 'Conflicting'):
            self.run_command('--apply')
        self.assertEqual(FileVersion.all_objects.count(), 1)

    def test_verify_reports_a_missing_archived_file(self):
        paper = self.paper(pdf_bytes())
        row = self.legacy(paper, 1)
        self.run_command('--apply')
        row.archived_file.storage.delete(row.archived_file.name)
        with self.assertRaisesRegex(CommandError, 'Verification failed'):
            self.run_command('--verify')

    def test_models_without_history_fields_are_refused(self):
        with self.assertRaisesRegex(CommandError, 'lacks the history fields'):
            call_command('dlux_adopt_file_history', 'document_files_app.Paper', stdout=StringIO())
