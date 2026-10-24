"""OCR text for registered document files (dlux.ocr), with the ocr service mocked."""

import json
import shutil
import tempfile
from io import BytesIO, StringIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from dlux import ocr
from dlux.files.registry import register_document_file, unregister_document_file
from dlux.models import FileText, SystemSettings
from dlux.ocr import service
from dlux.tests.document_files_app.models import Paper

PDF = b'%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n'


def payload(text='قرار وزير الاقتصاد والتجارة', pages=1):
    return {
        'engine': 'indra-ocr', 'engine_version': '1.1.2', 'model_version': 'v1.1.0', 'service_version': '1.0.0',
        'page_count': pages, 'markdown': f'## {text}', 'text': text, 'mean_confidence': 0.84, 'failed_pages': [],
        'pages': [{'index': i, 'source': 'ocr', 'markdown': f'## {text}', 'text': text,
                   'lines': [{'box': [1, 2, 30, 12], 'text': text, 'conf': 0.84}], 'blocks': [],
                   'rotation': 0, 'skew': 0.0, 'note': '', 'timings': {'total_ms': 250.0}} for i in range(pages)],
        'timings': {'queue_ms': 0.0, 'total_ms': 312.4, 'pages_ms': 250.0 * pages, 'per_page_ms': 250.0},
    }


class FakeResponse:
    def __init__(self, data):
        self.data = json.dumps(data).encode()

    def read(self):
        return self.data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def http_error(code, message):
    return HTTPError('http://ocr:8080/v1/ocr', code, 'error', {}, BytesIO(json.dumps({'error': message}).encode()))


def configure(**values):
    record = SystemSettings.load()
    record.is_configured = True
    extra = dict(record.extra_config or {})
    extra['ocr'] = {**ocr.DEFAULTS, 'enabled': True, **values}
    record.extra_config = extra
    record.save()
    cache.clear()


class OCRTestCase(TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, True)
        media = override_settings(MEDIA_ROOT=self.media)
        media.enable()
        self.addCleanup(media.disable)
        register_document_file(Paper, 'pdf_file')
        self.addCleanup(unregister_document_file, Paper, 'pdf_file')
        configure()
        send = patch('dlux.ocr.service._queue')
        self.apply_async = send.start()
        self.addCleanup(send.stop)

    def paper(self, content=PDF, title='Annual report'):
        with self.captureOnCommitCallbacks(execute=True):
            paper = Paper.objects.create(title=title)
            if content is not None:
                paper.pdf_file.save('scan.pdf', ContentFile(content))
        return paper

    def rows(self, paper):
        return FileText.all_objects.filter(content_type=ContentType.objects.get_for_model(Paper), object_id=paper.pk)

    def read(self, row, data=None):
        with patch('dlux.ocr.client._opener.open', return_value=FakeResponse(data or payload())) as opened:
            service.run(row.pk)
        row.refresh_from_db()
        return opened


class ConfigTests(OCRTestCase):
    def test_options_win_then_environment_strings_then_defaults(self):
        record = SystemSettings.load()
        record.extra_config = {**(record.extra_config or {}), 'ocr': {}}
        record.save()
        cache.clear()
        self.assertEqual(ocr.config(), ocr.DEFAULTS)
        env = {'OCR_ENABLED': 'true', 'OCR_URL': 'http://ocr-env:8080', 'OCR_THREADS': '3', 'OCR_MODE': 'bogus'}
        with patch.dict('os.environ', env):
            self.assertEqual({k: ocr.config()[k] for k in ('enabled', 'service_url', 'threads', 'mode')},
                             {'enabled': True, 'service_url': 'http://ocr-env:8080', 'threads': 3, 'mode': 'auto'})
            configure(enabled=False, service_url='http://ocr:8080', threads=1, mode='ocr')
            self.assertEqual({k: ocr.config()[k] for k in ('enabled', 'service_url', 'threads', 'mode')},
                             {'enabled': False, 'service_url': 'http://ocr:8080', 'threads': 1, 'mode': 'ocr'})

    def test_invalid_stored_values_fall_back(self):
        configure(enabled='yes', mode='fast', timeout=-5, threads=99, service_url='file:///etc/passwd')
        values = ocr.config()
        self.assertEqual((values['mode'], values['timeout'], values['threads'], values['service_url']),
                         ('auto', 900, 2, 'http://ocr:8080'))


class SchedulingTests(OCRTestCase):
    def test_saved_file_is_queued_once_per_hash_at_automatic_priority(self):
        paper = self.paper()
        row = self.rows(paper).get()
        self.assertEqual((row.status, row.source, row.is_current, row.document_model), ('pending', 'auto', True, 'Paper'))
        self.apply_async.assert_called_once_with(row.pk, service.PRIORITY['auto'])
        with self.captureOnCommitCallbacks(execute=True):
            paper.title = 'Metadata only'
            paper.save()
        self.assertEqual((self.rows(paper).count(), self.apply_async.call_count), (1, 1))

    def test_replaced_file_gets_a_new_current_row(self):
        paper = self.paper()
        first = self.rows(paper).get()
        with self.captureOnCommitCallbacks(execute=True):
            paper.pdf_file.save('other.pdf', ContentFile(PDF + b'%changed'))
        first.refresh_from_db()
        self.assertFalse(first.is_current)
        self.assertNotEqual(service.current_result(paper).pk, first.pk)

    def test_opt_out_disabled_and_automatic_off_create_nothing(self):
        unregister_document_file(Paper, 'pdf_file')
        register_document_file(Paper, 'pdf_file', ocr=False)
        self.assertFalse(self.rows(self.paper()).exists())
        register_document_file(Paper, 'pdf_file')
        configure(enabled=False)
        self.assertFalse(self.rows(self.paper()).exists())
        configure(auto_on_save=False)
        paper = self.paper()
        self.assertFalse(self.rows(paper).exists())
        with self.captureOnCommitCallbacks(execute=True):
            self.assertTrue(service.schedule(paper, source='manual', force=True)[1])
        self.apply_async.assert_called_once()

    def test_saves_survive_a_broker_outage(self):
        self.apply_async.side_effect = ConnectionError('redis down')
        self.assertEqual(self.rows(self.paper()).get().status, 'pending')


class RunTests(OCRTestCase):
    def test_run_stores_text_engine_timings_and_sends_options(self):
        configure(mode='ocr', threads=4)
        row = self.rows(self.paper()).get()
        opened = self.read(row, payload(pages=2))
        request = opened.call_args.args[0]
        self.assertIn('mode=ocr', request.full_url)
        self.assertIn('threads=4', request.full_url)
        self.assertEqual((row.status, row.engine, row.page_count, row.duration_ms), ('done', 'indra-ocr', 2, 312))
        self.assertEqual(row.text, 'قرار وزير الاقتصاد والتجارة')

    def test_busy_or_down_service_retries_and_rejection_is_final(self):
        row = self.rows(self.paper()).get()
        for error in (http_error(503, 'busy'), URLError(ConnectionRefusedError())):
            with patch('dlux.ocr.client._opener.open', side_effect=error), self.assertRaises(ocr.client.OCRUnavailable):
                service.run(row.pk)
            row.refresh_from_db()
            self.assertEqual(row.status, 'pending')
        with patch('dlux.ocr.client._opener.open', side_effect=http_error(422, 'cannot open the PDF')):
            service.run(row.pk)
        row.refresh_from_db()
        self.assertEqual((row.status, row.error), ('failed', 'cannot open the PDF'))

    def test_changed_or_deleted_file_is_skipped_without_calling_the_service(self):
        paper = self.paper()
        row = self.rows(paper).get()
        FileText.all_objects.filter(pk=row.pk).update(file_sha256='0' * 64)
        with patch('dlux.ocr.client._opener.open') as opened:
            service.run(row.pk)
        opened.assert_not_called()
        row.refresh_from_db()
        self.assertEqual(row.status, 'skipped')

    def test_task_retries_with_growing_delay_then_gives_up(self):
        from dlux.tasks import OCR_RETRY_DELAYS, ocr_file

        row = self.rows(self.paper()).get()
        with patch('dlux.ocr.service.run', side_effect=ocr.client.OCRUnavailable('down')), \
                patch.object(ocr_file, 'retry', side_effect=RuntimeError('retry')) as retry, self.assertRaises(RuntimeError):
            ocr_file.apply(args=(row.pk,), throw=True)
        self.assertEqual(retry.call_args.kwargs['countdown'], OCR_RETRY_DELAYS[0])
        with patch('dlux.ocr.service.run', side_effect=ocr.client.OCRUnavailable('down')):
            ocr_file.apply(args=(row.pk,), retries=ocr_file.max_retries, throw=True)
        row.refresh_from_db()
        self.assertIn('gave up', row.error)


class ViewTests(OCRTestCase):
    def setUp(self):
        super().setUp()
        self.paper_obj = self.paper()
        self.read(self.rows(self.paper_obj).get())
        self.url = reverse('dlux_document_file_text', kwargs={
            'app_label': 'document_files_app', 'model_name': 'paper', 'pk': self.paper_obj.pk, 'field_name': 'pdf_file'})

    def login(self, *codenames):
        user = get_user_model().objects.create_user('-'.join(codenames) or 'nobody', password='x')
        user.user_permissions.add(*Permission.objects.filter(content_type__app_label='document_files_app', codename__in=codenames))
        self.client.force_login(user)
        return user

    def test_view_permission_reads_text_change_permission_runs_it(self):
        self.login('view_paper')
        html = self.client.get(self.url).json()['html']
        self.assertIn('قرار وزير الاقتصاد والتجارة', html)
        self.assertIn('dir="auto"', html)
        self.assertNotIn('data-dlux-ocr-run', html)
        self.assertNotIn('<script', html)
        self.assertEqual(self.client.post(self.url).status_code, 403)
        self.client.logout()
        self.login()
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_run_ocr_requeues_at_manual_priority_once(self):
        user = self.login('view_paper', 'change_paper')
        self.apply_async.reset_mock()
        with self.captureOnCommitCallbacks(execute=True):
            data = self.client.post(self.url).json()
        self.assertEqual((data['status'], data['active']), ('pending', True))
        row = service.current_result(self.paper_obj)
        self.assertEqual((row.source, row.requested_by), ('manual', user))
        self.apply_async.assert_called_once_with(row.pk, service.PRIORITY['manual'])
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(self.url)
        self.assertEqual(self.apply_async.call_count, 1)

    def test_disabled_ocr_refuses_runs_but_keeps_text_readable(self):
        self.login('view_paper', 'change_paper')
        configure(enabled=False)
        self.assertEqual(self.client.post(self.url).status_code, 409)
        self.assertIn('قرار وزير', self.client.get(self.url).json()['html'])

    def test_viewer_offers_the_text_button_only_for_ocr_fields(self):
        from dlux.ocr.views import viewer_context as _text_context

        self.assertTrue(_text_context(self.paper_obj, 'pdf_file')['text_url'])
        unregister_document_file(Paper, 'pdf_file')
        register_document_file(Paper, 'pdf_file', ocr=False)
        self.assertEqual(_text_context(self.paper_obj, 'pdf_file')['text_url'], '')


class SearchTests(OCRTestCase):
    def test_arabic_search_q_with_model_matches_current_ocr_text(self):
        from dlux.search import search_data
        from dlux.utils import arabic_search_q

        matched = self.paper(title='First')
        self.read(self.rows(matched).get())
        self.paper(PDF + b'%other', title='Second')
        rows = Paper.objects.all()
        self.assertEqual(list(rows.filter(arabic_search_q('الأقتصاد', ['title'], model=Paper))), [matched])
        self.assertFalse(rows.filter(arabic_search_q('الاقتصاد', ['title'])).exists())
        configure(search=False)
        self.assertFalse(rows.filter(arabic_search_q('الاقتصاد', ['title'], model=Paper)).exists())
        configure()
        admin = get_user_model().objects.create_superuser('search-admin', password='x')
        with patch('dlux.search._searchable_models', return_value=[Paper]):
            self.assertEqual([hit['label'] for hit in search_data(admin, 'الاقتصاد')], ['First'])
        from dlux.search import _searchable_models
        from dlux.utils.activity_log import is_model_loggable

        self.assertFalse(is_model_loggable('dlux.filetext'))
        self.assertNotIn(FileText, _searchable_models(admin))


class SettingsFormTests(OCRTestCase):
    def test_extra_features_saves_ocr_options_and_keeps_project_config(self):
        from dlux.forms.ocr import apply_ocr

        record = SystemSettings.load()
        record.extra_config = {**(record.extra_config or {}), 'app': {'project': {'keep': 1}}}
        form = type('Form', (), {'single_step_mode': False, 'single_step_index': 0, 'cleaned_data': {
            'ocr_enabled': True, 'ocr_auto_on_save': False, 'ocr_search': True, 'ocr_mode': 'ocr',
            'ocr_service_url': 'http://ocr:8081', 'ocr_timeout': 300, 'ocr_max_file_mb': 20, 'ocr_threads': 3}})()
        apply_ocr(form, record)
        self.assertEqual(record.extra_config['app'], {'project': {'keep': 1}})
        self.assertEqual(record.extra_config['ocr'], {'enabled': True, 'auto_on_save': False, 'search': True,
                         'service_url': 'http://ocr:8081', 'mode': 'ocr', 'timeout': 300, 'max_file_mb': 20, 'threads': 3})

    def test_system_settings_form_renders_the_ocr_section(self):
        from dlux.forms.system_settings import SystemSettingsForm

        form = SystemSettingsForm(instance=SystemSettings.load())
        self.assertTrue(form.initial['ocr_enabled'])
        self.assertEqual(form.initial['ocr_service_url'], 'http://ocr:8080')
        self.assertFalse(form.fields['ocr_service_url'].clean('http://ocr:8080') is None)
        with self.assertRaises(Exception):
            form.fields['ocr_service_url'].clean('file:///etc/passwd')


class CommandTests(OCRTestCase):
    def setUp(self):
        super().setUp()
        configure(enabled=False)
        self.papers = [self.paper(PDF + str(i).encode(), title=f'P{i}') for i in range(3)]
        configure()
        self.state = Path(self.media) / 'state.json'

    def backfill(self, *args):
        out = StringIO()
        with self.captureOnCommitCallbacks(execute=True):
            call_command('dlux_ocr_backfill', '--state-file', str(self.state), '--batch-size', '2', '--wait', '0',
                         *args, stdout=out, stderr=StringIO())
        return out.getvalue()

    def test_backfill_reads_in_batches_resumes_and_skips_unchanged_files(self):
        with patch('dlux.ocr.client._opener.open', side_effect=lambda *a, **k: FakeResponse(payload())) as opened:
            self.backfill('--limit', '2')
            self.assertEqual(opened.call_count, 2)
            self.assertEqual(json.loads(self.state.read_text()), {'document_files_app.paper.pdf_file': self.papers[1].pk})
            self.backfill()
            self.backfill('--restart')
            self.assertEqual(opened.call_count, 3)
        self.assertEqual(FileText.all_objects.filter(status='done', source='backfill').count(), 3)
        self.apply_async.assert_not_called()

    def test_backfill_enqueue_and_resumable_stop(self):
        self.backfill('--enqueue')
        self.assertTrue(all(c.args[1] == service.PRIORITY['backfill'] for c in self.apply_async.call_args_list))
        FileText.all_objects.update(status='failed')
        with patch('dlux.ocr.client._opener.open', side_effect=URLError(ConnectionRefusedError())), \
                self.assertRaisesMessage(CommandError, 'rerun to resume'):
            self.backfill('--restart', '--retry-failed', '--max-waits', '1')
        configure(enabled=False)
        with self.assertRaisesMessage(CommandError, 'OCR is disabled'):
            self.backfill()

    def test_adopt_copies_project_rows_idempotently(self):
        from dlux.tests.document_files_app.models import LegacyFileText

        paper = self.papers[0]
        content_type = ContentType.objects.get_for_model(Paper)
        LegacyFileText.all_objects.create(
            content_type=content_type, object_id=paper.pk, document_model='Paper', file_name=paper.pdf_file.name,
            file_sha256='a' * 64, status='done', text='نص قديم', markdown='## نص قديم', engine='indra-ocr',
            engine_version='1.1.2', page_count=1, pages=[{'index': 0}], timings={'total_ms': 10.0}, duration_ms=10,
        )
        label = 'document_files_app.LegacyFileText'
        out = StringIO()
        call_command('dlux_adopt_ocr_text', label, stdout=out)
        self.assertIn('1 to copy', out.getvalue())
        self.assertFalse(FileText.all_objects.filter(file_sha256='a' * 64).exists())
        call_command('dlux_adopt_ocr_text', label, '--apply', stdout=StringIO())
        copy = FileText.all_objects.get(file_sha256='a' * 64)
        self.assertEqual((copy.object_id, copy.text, copy.status, copy.page_count), (paper.pk, 'نص قديم', 'done', 1))
        out = StringIO()
        call_command('dlux_adopt_ocr_text', label, '--apply', stdout=out)
        self.assertIn('1 already adopted', out.getvalue())
        FileText.all_objects.filter(pk=copy.pk).update(text='changed')
        with self.assertRaisesMessage(CommandError, 'Conflicting'):
            call_command('dlux_adopt_ocr_text', label, stdout=StringIO())


class ContractTests(TestCase):
    def test_ocr_is_an_optional_internal_restart_safe_lifecycle_service(self):
        from dlux.contracts.stack import diff_attachments, load_contract

        contract = load_contract()
        spec = contract['services']['ocr']
        self.assertEqual((spec['networks'], spec['restart'], spec['optional']), (['internal'], 'safe', True))
        self.assertIn('ocr', contract['invariants']['internal_only_services'])
        self.assertIn('ocr', contract['invariants']['restart']['lifecycle'])
        attachments = {name: set(s['networks']) for name, s in contract['services'].items() if name != 'ocr'}
        self.assertEqual(diff_attachments(contract, attachments), [])
        attachments['ocr'] = {'internal', 'egress'}
        self.assertTrue(diff_attachments(contract, attachments))

    def test_scaffold_runs_ocr_and_allow_lists_it(self):
        from dlux.scaffold import __file__ as scaffold_init

        template = (Path(scaffold_init).parent / 'templates' / 'project' / 'compose.yml.tmpl').read_text()
        self.assertIn('image: ${OCR_IMAGE:-debeski/dlux-ocr:latest}', template)
        self.assertEqual(template.count('COMPOSER_AGENT_RESTART_SERVICES: "web,celery,smtp-relay,caddy,ocr"'), 2)
        launcher = (Path(scaffold_init).parent / 'templates' / 'project' / 'start.ps1.tmpl').read_bytes()
        self.assertTrue(all(byte < 128 for byte in launcher))
