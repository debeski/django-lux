from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.utils import timezone

from dlux import ocr
from dlux.models import FileText, SystemSettings
from dlux.ocr import background, service
from dlux.tests.document_files_app.models import Paper
from dlux.tests.test_ocr import OCRTestCase, PDF, configure
from django.core.files.base import ContentFile


class BackgroundOCRTests(OCRTestCase):
    def setUp(self):
        super().setUp()
        configure(background_enabled=True, auto_on_save=False)
        health = patch('dlux.ocr.background.service_health', return_value={'status': 'ok'})
        self.health = health.start()
        self.addCleanup(health.stop)

    def tick(self):
        with self.captureOnCommitCallbacks(execute=True):
            return background.tick()

    def due(self):
        state = cache.get(background.STATE_KEY) or {}
        state['last_run'] = 0
        cache.set(background.STATE_KEY, state, timeout=None)

    def test_legacy_files_catch_up_in_batches_and_resume_without_rereading(self):
        papers = [self.paper() for _ in range(3)]
        self.assertEqual(FileText.all_objects.count(), 0)
        configure(background_enabled=True, auto_on_save=False, background_batch_size=1)
        for index, paper in enumerate(papers):
            self.due()
            self.assertEqual(self.tick()['queued'], 1)
            row = service.current_result(paper)
            self.assertEqual(row.source, 'backfill')
            self.read(row)
            self.assertEqual(FileText.all_objects.count(), index + 1)
        self.due()
        with patch('dlux.ocr.service.file_sha256') as hashing:
            self.assertEqual(self.tick()['queued'], 0)
        hashing.assert_not_called()
        self.assertEqual(self.apply_async.call_count, 3)
        self.assertTrue(all(call.args[1] == 9 for call in self.apply_async.call_args_list))

    def test_interval_queue_limit_and_service_health_pause_scans(self):
        first, second = self.paper(), self.paper()
        configure(background_enabled=True, auto_on_save=False, background_queue_limit=1)
        self.assertEqual(self.tick()['queued'], 1)
        self.assertEqual(self.tick()['state'], 'waiting')
        self.due()
        self.assertEqual(self.tick()['state'], 'paused_queue')
        self.read(service.current_result(first))
        self.due()
        self.health.return_value = None
        self.assertEqual(self.tick()['state'], 'paused_service')
        self.assertIsNone(service.current_result(second))
        self.due()
        self.health.return_value = {'status': 'ok'}
        self.assertEqual(self.tick()['queued'], 1)

    def test_disabled_or_locked_scanner_does_no_work(self):
        self.paper()
        configure(background_enabled=False)
        self.assertEqual(self.tick()['state'], 'disabled')
        self.health.assert_not_called()
        configure(background_enabled=True)
        cache.add(background.LOCK_KEY, 'another-worker', 120)
        self.assertEqual(self.tick()['state'], 'busy')
        self.health.assert_not_called()

    def test_excluded_model_has_no_auto_or_catch_up_but_manual_works(self):
        configure(background_enabled=True, automatic_models=[])
        paper = self.paper()
        self.assertIsNone(service.current_result(paper))
        self.assertEqual(self.tick()['queued'], 0)
        self.health.assert_not_called()
        row, queued = service.schedule(paper, source='manual', force=True)
        self.assertTrue(queued)
        self.read(row)
        self.assertEqual(row.status, 'done')

    def test_exclusion_after_queueing_is_enforced_and_manual_can_promote_pending(self):
        configure(background_enabled=True)
        paper = self.paper()
        row = service.current_result(paper)
        configure(background_enabled=True, automatic_models=[])
        with patch('dlux.ocr.service.call_service') as reading:
            service.run(row.pk)
        reading.assert_not_called()
        row.refresh_from_db()
        self.assertEqual(row.status, 'skipped')
        row.status = 'pending'
        row.save()
        promoted, queued = service.schedule(paper, source='manual', force=True)
        self.assertTrue(queued)
        self.assertEqual(promoted.source, 'manual')
        self.assertFalse(service.schedule(paper, source='manual', force=True)[1])
        self.read(promoted)
        self.assertEqual(promoted.status, 'done')

    def test_replaced_excluded_file_invalidates_earlier_text(self):
        configure()
        paper = self.paper()
        old = service.current_result(paper)
        self.read(old)
        configure(automatic_models=[])
        with self.captureOnCommitCallbacks(execute=True):
            paper.pdf_file.save('new.pdf', ContentFile(PDF + b'replacement'))
        old.refresh_from_db()
        self.assertFalse(old.is_current)
        self.assertIsNone(service.current_result(paper))

    def test_stale_pending_work_can_recover_but_failed_files_do_not_loop(self):
        configure()
        paper = self.paper()
        row = service.current_result(paper)
        FileText.all_objects.filter(pk=row.pk).update(updated_at=timezone.now() - timedelta(days=1))
        configure(background_enabled=True)
        self.apply_async.reset_mock()
        self.assertEqual(self.tick()['queued'], 1)
        self.assertEqual(self.apply_async.call_count, 1)
        row.refresh_from_db()
        row.status = 'failed'
        row.save()
        self.due()
        self.assertEqual(self.tick()['queued'], 0)

    def test_settings_defaults_selection_and_saved_controls(self):
        from dlux.forms.ocr import apply_ocr
        from dlux.forms.system_settings import SystemSettingsForm
        record = SystemSettings.load()
        form = SystemSettingsForm(instance=record)
        self.assertIn(Paper._meta.label_lower, form.initial['ocr_automatic_models'])
        form.cleaned_data = {'ocr_enabled': True, 'ocr_background_enabled': True,
                             'ocr_background_interval': 120, 'ocr_background_batch_size': 2,
                             'ocr_background_queue_limit': 4, 'ocr_automatic_models': []}
        apply_ocr(form, record)
        record.save()
        cache.clear()
        options = ocr.config()
        self.assertEqual(options['automatic_models'], [])
        self.assertTrue(options['background_enabled'])
        self.assertEqual(options['background_interval'], 120)
        self.assertEqual(options['background_batch_size'], 2)
        self.assertEqual(options['background_queue_limit'], 4)

    def test_retry_eta_is_not_mistaken_for_a_lost_message(self):
        configure()
        paper = self.paper()
        row = service.current_result(paper)
        FileText.all_objects.filter(pk=row.pk).update(updated_at=timezone.now() - timedelta(minutes=30))
        configure(background_enabled=True)
        self.apply_async.reset_mock()
        self.assertEqual(self.tick()['queued'], 0)
        self.apply_async.assert_not_called()

    def test_scan_snapshot_cannot_make_a_replaced_file_current(self):
        stale = self.paper()
        fresh = Paper.objects.get(pk=stale.pk)
        configure()
        with self.captureOnCommitCallbacks(execute=True):
            fresh.pdf_file.save('replacement.pdf', ContentFile(PDF + b'changed'))
        current = service.current_result(fresh)
        row, queued = service.schedule(stale, source='backfill')
        self.assertIsNone(row)
        self.assertFalse(queued)
        self.assertEqual(service.current_result(fresh).pk, current.pk)

    def test_invalid_selection_fails_closed_and_limits_fall_back(self):
        values = ocr.normalize_ocr_config({'automatic_models': 'all', 'background_batch_size': 0})
        self.assertEqual(values['automatic_models'], [])
        self.assertEqual(values['background_batch_size'], 5)
