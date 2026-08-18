"""Interrupted-backup detection, retry, and resume.

The failure these cover: a full ``.dlb`` build whose worker disappears mid-run
never reaches its own failure path, so before this the row stayed ``running``
forever — no error, no file, a frozen percentage, and (for scheduled runs) a
permanent block on the next backup.
"""

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from datetime import timedelta
from unittest import mock

from django.apps import apps
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from dlux.backup import (
    backup_retry_policy,
    dispatch_due_backup_retries,
    fail_system_backup,
    reap_stalled_system_backups,
    resume_system_backup,
    retry_countdown_for,
    run_scheduled_system_backup,
    run_system_backup,
)
from dlux.system.defaults import default_backup_config
from dlux.system.normalizers import normalize_backup_config

User = get_user_model()


class BackupRecoveryTestCase(TestCase):
    def setUp(self):
        self.SystemSettings = apps.get_model('dlux', 'SystemSettings')
        self.SystemBackup = apps.get_model('dlux', 'SystemBackup')
        self.settings_obj = self.SystemSettings.load()
        self.settings_obj.is_configured = True
        self.settings_obj.save(update_fields=['is_configured'])

    def _save_config(self, **overrides):
        self.settings_obj.backup_config = normalize_backup_config({
            **default_backup_config(),
            **overrides,
        })
        self.settings_obj.save(update_fields=['backup_config'])

    def _running(self, *, quiet_minutes=0, **kwargs):
        """A backup row that last reported progress ``quiet_minutes`` ago."""
        stamp = timezone.now() - timedelta(minutes=quiet_minutes)
        backup = self.SystemBackup.objects.create(
            requested_by_username=kwargs.pop('requested_by_username', 'boss'),
            **kwargs,
        )
        self.SystemBackup.objects.filter(pk=backup.pk).update(
            status=self.SystemBackup.STATUS_RUNNING,
            started_at=stamp,
            heartbeat_at=stamp,
            attempt_count=kwargs.get('attempt_count', 1) or 1,
            progress_percent=66,
            stage=self.SystemBackup.STAGE_MODELS,
        )
        backup.refresh_from_db()
        return backup

    def _with_worker(self):
        """Pretend a Celery worker is reachable — automatic retries need one."""
        return mock.patch('dlux.backup.retry.system_backup_celery_available', return_value=True)


class StallReaperTests(BackupRecoveryTestCase):
    def test_manual_backup_abandoned_by_its_worker_is_reaped(self):
        # The original bug: only scheduled runs were ever checked, so a manual
        # backup whose worker died stayed 'running' with no error forever.
        self._save_config(stall_timeout_minutes=30, auto_retry_enabled=False)
        ghost = self._running(quiet_minutes=45, trigger=self.SystemBackup.TRIGGER_MANUAL)

        reaped, _requeued = reap_stalled_system_backups()

        ghost.refresh_from_db()
        self.assertEqual(reaped, 1)
        self.assertEqual(ghost.status, self.SystemBackup.STATUS_FAILED)
        self.assertIn('66%', ghost.error)
        self.assertIsNotNone(ghost.completed_at)

    def test_a_run_that_is_still_reporting_is_left_alone(self):
        self._save_config(stall_timeout_minutes=30)
        healthy = self._running(quiet_minutes=2, trigger=self.SystemBackup.TRIGGER_MANUAL)

        reaped, _requeued = reap_stalled_system_backups()

        healthy.refresh_from_db()
        self.assertEqual(reaped, 0)
        self.assertEqual(healthy.status, self.SystemBackup.STATUS_RUNNING)

    def test_pending_row_waiting_on_its_scheduled_retry_is_not_reaped(self):
        self._save_config(stall_timeout_minutes=5)
        backup = self._running(quiet_minutes=60)
        self.SystemBackup.objects.filter(pk=backup.pk).update(
            status=self.SystemBackup.STATUS_PENDING,
            next_attempt_at=timezone.now() + timedelta(minutes=10),
        )

        reaped, _requeued = reap_stalled_system_backups()

        backup.refresh_from_db()
        self.assertEqual(reaped, 0)
        self.assertEqual(backup.status, self.SystemBackup.STATUS_PENDING)

    def test_a_ghost_no_longer_blocks_the_next_scheduled_backup(self):
        self._save_config(scheduled_enabled=True, schedule_interval_hours=1,
                          stall_timeout_minutes=15, auto_retry_enabled=False)
        ghost = self._running(quiet_minutes=90, trigger=self.SystemBackup.TRIGGER_SCHEDULED)
        self.SystemBackup.objects.filter(pk=ghost.pk).update(
            created_at=timezone.now() - timedelta(hours=3),
        )

        with mock.patch(
            'dlux.backup.dispatch.run_system_backup',
            side_effect=lambda pk, **kw: self.SystemBackup.objects.get(pk=pk),
        ) as runner:
            created = run_scheduled_system_backup()

        ghost.refresh_from_db()
        self.assertEqual(ghost.status, self.SystemBackup.STATUS_FAILED)
        self.assertTrue(runner.called)
        self.assertNotEqual(created.pk, ghost.pk)


class AutomaticRetryTests(BackupRecoveryTestCase):
    def test_failure_arms_a_delayed_retry_within_the_attempt_budget(self):
        self._save_config(auto_retry_enabled=True, max_attempts=3, retry_delay_minutes=5)
        backup = self._running(quiet_minutes=0)

        with self._with_worker():
            countdown = fail_system_backup(backup, 'storage went away')

        backup.refresh_from_db()
        self.assertEqual(countdown, 300)
        self.assertEqual(backup.status, self.SystemBackup.STATUS_PENDING)
        self.assertIsNotNone(backup.next_attempt_at)
        self.assertEqual(retry_countdown_for(backup.pk, now=backup.next_attempt_at), 0)

    def test_last_attempt_is_terminal(self):
        self._save_config(auto_retry_enabled=True, max_attempts=2, retry_delay_minutes=5)
        backup = self._running()
        self.SystemBackup.objects.filter(pk=backup.pk).update(attempt_count=2)
        backup.refresh_from_db()

        with self._with_worker():
            countdown = fail_system_backup(backup, 'still broken')

        backup.refresh_from_db()
        self.assertIsNone(countdown)
        self.assertEqual(backup.status, self.SystemBackup.STATUS_FAILED)
        self.assertIsNone(backup.next_attempt_at)

    def test_passphrase_backups_are_never_retried_without_the_passphrase(self):
        # Re-running one blind would silently encrypt with the Django secret key
        # instead of the passphrase the operator chose.
        self._save_config(auto_retry_enabled=True, max_attempts=3)
        backup = self._running(passphrase_required=True)

        with self._with_worker():
            self.assertIsNone(fail_system_backup(backup, 'worker died'))
        backup.refresh_from_db()
        self.assertEqual(backup.status, self.SystemBackup.STATUS_FAILED)

        # ...but the Celery task, which still holds the passphrase, may arm one.
        backup.status = self.SystemBackup.STATUS_RUNNING
        backup.save(update_fields=['status'])
        self.assertEqual(
            fail_system_backup(backup, 'worker died', passphrase_in_hand=True),
            backup_retry_policy()['retry_delay_minutes'] * 60,
        )

    def test_no_retry_is_promised_when_there_is_no_worker_to_run_it(self):
        # Without a background worker the only executor is the request that just
        # failed, so arming a delayed attempt would strand the row as pending.
        self._save_config(auto_retry_enabled=True, max_attempts=3)
        backup = self._running()

        with mock.patch('dlux.backup.retry.system_backup_celery_available', return_value=False):
            self.assertIsNone(fail_system_backup(backup, 'inline build failed'))

        backup.refresh_from_db()
        self.assertEqual(backup.status, self.SystemBackup.STATUS_FAILED)
        self.assertIsNone(backup.next_attempt_at)

    def test_due_retry_sweep_starts_one_run_and_skips_passphrase_rows(self):
        self._save_config(auto_retry_enabled=True, max_attempts=3, retry_delay_minutes=0)
        due = self.SystemBackup.objects.create(requested_by_username='boss')
        self.SystemBackup.objects.filter(pk=due.pk).update(
            next_attempt_at=timezone.now() - timedelta(minutes=1),
        )
        protected = self.SystemBackup.objects.create(
            requested_by_username='boss', passphrase_required=True,
        )
        self.SystemBackup.objects.filter(pk=protected.pk).update(
            next_attempt_at=timezone.now() - timedelta(minutes=1),
        )

        with mock.patch('dlux.backup.dispatch.dispatch_system_backup', return_value=False), \
                mock.patch('dlux.backup.dispatch.run_system_backup') as runner:
            started = dispatch_due_backup_retries()

        self.assertEqual(started, 1)
        runner.assert_called_once_with(due.pk)

    def test_auto_retry_can_be_switched_off(self):
        self._save_config(auto_retry_enabled=False, max_attempts=5)
        backup = self._running()

        self.assertIsNone(fail_system_backup(backup, 'nope'))
        backup.refresh_from_db()
        self.assertEqual(backup.status, self.SystemBackup.STATUS_FAILED)

    def test_a_claimed_run_cannot_be_started_twice(self):
        self._save_config()
        backup = self._running(quiet_minutes=0)

        # Already running: a second dispatcher reaching the same row is a no-op.
        with mock.patch('dlux.backup.create.write_system_backup') as writer:
            run_system_backup(backup.pk)

        writer.assert_not_called()


class ResumeTests(BackupRecoveryTestCase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser(
            username='root', email='root@example.com', password='Str0ng-Pass!1',
        )
        self.client = Client()
        self.client.force_login(self.admin)

    def _failed(self, **kwargs):
        backup = self.SystemBackup.objects.create(requested_by_username='root', **kwargs)
        self.SystemBackup.objects.filter(pk=backup.pk).update(
            status=self.SystemBackup.STATUS_FAILED,
            attempt_count=1,
            progress_percent=66,
            error='Backup stopped reporting progress at 66%',
            completed_at=timezone.now(),
        )
        backup.refresh_from_db()
        return backup

    def test_resume_reruns_the_same_row_as_a_new_attempt(self):
        backup = self._failed()

        with mock.patch('dlux.backup.dispatch.dispatch_system_backup', return_value=False), \
                mock.patch('dlux.backup.dispatch.run_system_backup') as runner:
            resume_system_backup(backup, requested_by='root')

        backup.refresh_from_db()
        runner.assert_called_once_with(backup.pk, passphrase=None)
        self.assertEqual(backup.status, self.SystemBackup.STATUS_PENDING)
        self.assertEqual(backup.progress_percent, 0)
        self.assertIsNone(backup.next_attempt_at)

    def test_resume_of_a_protected_backup_requires_the_passphrase(self):
        backup = self._failed(passphrase_required=True)

        with self.assertRaises(ValueError):
            resume_system_backup(backup)

        with mock.patch('dlux.backup.dispatch.dispatch_system_backup', return_value=True) as dispatch:
            resume_system_backup(backup, passphrase='vault-pass')
        dispatch.assert_called_once()
        self.assertEqual(dispatch.call_args.kwargs['passphrase'], 'vault-pass')

    def test_resume_view_dispatches_and_redirects(self):
        backup = self._failed()

        with mock.patch('dlux.views.backup.resume_system_backup') as resume:
            response = self.client.post(reverse('system_backup_resume', args=[backup.token]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('system_backup_page'))
        resume.assert_called_once()

    def test_completed_backups_cannot_be_resumed(self):
        backup = self.SystemBackup.objects.create(requested_by_username='root')
        self.SystemBackup.objects.filter(pk=backup.pk).update(
            status=self.SystemBackup.STATUS_COMPLETED,
        )
        backup.refresh_from_db()

        with self.assertRaises(ValueError):
            resume_system_backup(backup)


class BackupStatusSurfaceTests(BackupRecoveryTestCase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser(
            username='root', email='root@example.com', password='Str0ng-Pass!1',
        )
        self.client = Client()
        self.client.force_login(self.admin)

    def test_list_status_reports_stall_age_and_reaps_ghosts(self):
        self._save_config(stall_timeout_minutes=10, auto_retry_enabled=False)
        ghost = self._running(quiet_minutes=30)

        response = self.client.get(reverse('system_backup_list_status'))

        payload = response.json()
        ghost.refresh_from_db()
        self.assertEqual(ghost.status, self.SystemBackup.STATUS_FAILED)
        self.assertFalse(payload['active'])
        item = next(row for row in payload['items'] if row['token'] == ghost.token)
        self.assertEqual(item['attempt_count'], 1)
        self.assertIn('Retry', payload['html'])

    def test_status_endpoint_exposes_liveness_for_a_live_run(self):
        self._save_config(stall_timeout_minutes=60)
        backup = self._running(quiet_minutes=3)

        payload = self.client.get(
            reverse('system_backup_status', args=[backup.token]),
        ).json()

        self.assertEqual(payload['status'], 'running')
        self.assertEqual(payload['stage'], self.SystemBackup.STAGE_MODELS)
        self.assertGreaterEqual(payload['seconds_since_progress'], 170)
        self.assertEqual(payload['max_attempts'], backup_retry_policy()['max_attempts'])

    def test_running_row_past_the_warning_threshold_is_flagged_in_the_table(self):
        self._save_config(stall_timeout_minutes=60)
        self._running(quiet_minutes=25)

        payload = self.client.get(reverse('system_backup_list_status')).json()

        self.assertTrue(payload['items'][0]['stalled'])
        self.assertIn('dlux-backup-progress--stalled', payload['html'])


class RecoveryPolicyPersistenceTests(BackupRecoveryTestCase):
    def test_policy_round_trips_through_the_import_path(self):
        from dlux.utils.config import get_system_config
        from dlux.utils.import_export import apply_system_settings_import

        apply_system_settings_import(self.settings_obj, {
            'backup_config': {
                'stall_timeout_minutes': 12,
                'auto_retry_enabled': False,
                'max_attempts': 4,
                'retry_delay_minutes': 7,
            },
        })
        self.settings_obj.save()

        stored = self.SystemSettings.load().backup_config
        self.assertEqual(stored['stall_timeout_minutes'], 12)
        self.assertFalse(stored['auto_retry_enabled'])
        self.assertEqual(stored['max_attempts'], 4)
        self.assertEqual(stored['retry_delay_minutes'], 7)
        self.assertEqual(get_system_config()['backup_config']['max_attempts'], 4)
        self.assertEqual(backup_retry_policy()['stall_timeout_minutes'], 12)

    def test_out_of_range_values_are_clamped(self):
        clamped = normalize_backup_config({
            'stall_timeout_minutes': 0,
            'max_attempts': 99,
            'retry_delay_minutes': -3,
        })
        self.assertEqual(clamped['stall_timeout_minutes'], 2)
        self.assertEqual(clamped['max_attempts'], 10)
        self.assertEqual(clamped['retry_delay_minutes'], 0)

    def test_saving_another_settings_step_preserves_the_recovery_policy(self):
        from django.test import RequestFactory

        from dlux.forms import SystemSettingsForm

        self._save_config(stall_timeout_minutes=17, max_attempts=4)
        admin = User.objects.create_superuser(
            username='stepper', email='stepper@example.com', password='Str0ng-Pass!1',
        )
        # A single-step save of an unrelated step must not read the absent backup
        # fields as "operator turned everything back to the defaults".
        request = RequestFactory().post('/?step=0', {'system_name': 'Kept'})
        request.user = admin
        form = SystemSettingsForm(
            data={'system_name': 'Kept', 'system_name_ar': 'Kept'},
            instance=self.SystemSettings.load(),
            request=request,
            mode='modal',
        )
        form.is_valid()

        self.assertEqual(form.cleaned_data['backup_config']['stall_timeout_minutes'], 17)
        self.assertEqual(form.cleaned_data['backup_config']['max_attempts'], 4)


class ProgressReportingTests(BackupRecoveryTestCase):
    def test_streaming_reports_sub_progress_and_refreshes_the_heartbeat(self):
        # A model holding many rows/files used to report nothing between its
        # start and end checkpoints, which is precisely what made a live backup
        # indistinguishable from a dead one.
        from dlux.backup import _BackupReporter

        backup = self._running(quiet_minutes=10)
        reporter = _BackupReporter(backup)
        reporter.HEARTBEAT_INTERVAL_SECONDS = 0
        reporter.NOTIFY_INTERVAL_SECONDS = 10_000

        before = backup.heartbeat_at
        reporter.tick(40, 'Backing up Document - files 120/900...')

        backup.refresh_from_db()
        self.assertGreater(backup.heartbeat_at, before)
        self.assertEqual(backup.progress_percent, 40)
        self.assertIn('120/900', backup.progress_message)

    def test_a_real_run_records_its_attempt_and_finishes_clean(self):
        from django.core.files.storage import default_storage

        backup = self.SystemBackup.objects.create(
            requested_by_username='boss', media_included=False,
        )

        run_system_backup(backup.pk)

        backup.refresh_from_db()
        self.assertEqual(backup.status, self.SystemBackup.STATUS_COMPLETED)
        self.assertEqual(backup.attempt_count, 1)
        self.assertIsNotNone(backup.heartbeat_at)
        self.assertEqual(backup.stage, '')
        self.assertIsNone(backup.next_attempt_at)
        self.assertTrue(default_storage.exists(backup.file_path))
        default_storage.delete(backup.file_path)

    def test_write_system_backup_emits_row_and_file_sub_steps(self):
        import tempfile

        seen = []

        class Recorder:
            def checkpoint(self, percent, message, stage=None):
                seen.append((percent, stage))

            def tick(self, percent, message, stage=None):
                seen.append((percent, stage))

        from dlux.backup import write_system_backup

        with tempfile.TemporaryFile() as dest:
            write_system_backup(dest, reporter=Recorder(), include_media=False)

        stages = {stage for _percent, stage in seen}
        self.assertIn('models', stages)
        self.assertIn('encrypting', stages)
        self.assertTrue(all(0 <= percent <= 99 for percent, _stage in seen))


class BackupPageNavigationTests(TestCase):
    """Backup and restore is a full page, not a modal, so it needs its own way
    back — otherwise the only route to Options is the browser's Back button."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.addCleanup(cache.clear)
        self.admin = get_user_model().objects.create_superuser('navadmin', 'n@example.com', 'pw')
        settings_row = apps.get_model('dlux', 'SystemSettings').load()
        settings_row.is_configured = True
        settings_row.save()
        self.client.force_login(self.admin)

    def test_the_page_links_back_to_options(self):
        response = self.client.get(reverse('system_backup_page'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('options_view'))
        self.assertContains(response, 'dlux-backup-back')

    def test_the_label_is_translated_not_hardcoded(self):
        """Every other page label comes from DLUX_STRINGS; this one must too."""
        from dlux.translations import get_strings
        for language in ('en', 'ar'):
            with self.subTest(language=language):
                self.assertIn('sysbackup_back_to_options', get_strings(language))
