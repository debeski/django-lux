"""Backup and restore history as DluxTables: pagination, row actions, live refresh."""

import html
import json
import re

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.apps import apps
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from dlux.views.backup_tables import system_backup_row_actions

User = get_user_model()


def _rows(markup, attribute):
    return re.findall(rf'<tr [^>]*{attribute}=', markup)


def _actions(markup, token):
    match = re.search(rf'data-backup-token="{re.escape(token)}"[^>]*data-dlux-actions="([^"]*)"', markup)
    return json.loads(html.unescape(match.group(1)))


class BackupTablePageTests(TestCase):
    def setUp(self):
        SystemSettings = apps.get_model('dlux', 'SystemSettings')
        settings_obj = SystemSettings.load()
        settings_obj.is_configured = True
        settings_obj.save(update_fields=['is_configured'])
        User.objects.create_superuser('boss', 'boss@example.com', 'bosspass123')
        self.client = Client()
        self.client.login(username='boss', password='bosspass123')
        self.SystemBackup = apps.get_model('dlux', 'SystemBackup')
        self.SystemRestore = apps.get_model('dlux', 'SystemRestore')

    def _backups(self, count, **fields):
        return [
            self.SystemBackup.objects.create(requested_by_username='boss', status='completed', **fields)
            for _ in range(count)
        ]

    def test_backups_page_by_ten_and_restores_by_five(self):
        self._backups(12)
        for _ in range(7):
            self.SystemRestore.objects.create(requested_by_username='boss', backup_file_path='x.dlb', status='completed')
        page = self.client.get(reverse('system_backup_page')).content.decode()
        self.assertEqual(len(_rows(page, 'data-system-backup-row')), 10)
        self.assertEqual(len(_rows(page, 'data-system-restore-row')), 5)
        self.assertNotIn('dlux-table-page-size', page, 'a fixed page size offers no picker')
        self.assertIn('dlux-table-pagination', page)
        second = self.client.get(reverse('system_backup_page'), {'backups-page': 2, 'restores-page': 2}).content.decode()
        self.assertEqual(len(_rows(second, 'data-system-backup-row')), 2)
        self.assertEqual(len(_rows(second, 'data-system-restore-row')), 2)

    def test_no_template_comment_leaks_onto_the_page(self):
        # A `{# #}` comment ends at the line break; the multi-line one showed as text.
        self._backups(1)
        page = self.client.get(reverse('system_backup_page')).content.decode()
        self.assertNotIn('SystemBackupTable', page)
        self.assertNotIn('{#', page)

    def test_the_restore_table_offers_no_density_picker(self):
        self.SystemRestore.objects.create(requested_by_username='boss', backup_file_path='x.dlb', status='completed')
        self._backups(1)
        page = self.client.get(reverse('system_backup_page')).content.decode()
        restore_part = page[page.index('id="sysrestore-table-body"'):]
        backup_part = page[page.index('id="sysbackup-table-body"'):page.index('id="sysrestore-table-body"')]
        self.assertNotIn('data-dlux-table-density-inline', restore_part)
        self.assertIn('data-dlux-table-density="dense"', restore_part)
        self.assertIn('data-dlux-table-density-inline', backup_part, 'the backup history keeps its picker')

    def test_the_page_size_cannot_be_raised_from_the_query(self):
        self._backups(12)
        page = self.client.get(reverse('system_backup_page'), {'backups-per_page': 50}).content.decode()
        self.assertEqual(len(_rows(page, 'data-system-backup-row')), 10)

    def test_the_poller_rerenders_the_page_the_operator_is_on(self):
        backups = self._backups(12)
        payload = self.client.get(reverse('system_backup_list_status'), {'backups-page': 2}).json()
        oldest_two = {backup.token for backup in backups[:2]}
        self.assertEqual({item['token'] for item in payload['items']}, oldest_two)
        self.assertEqual(len(_rows(payload['html'], 'data-system-backup-row')), 2)
        # Pagination links stay relative, so they resolve against the page, not the poller.
        self.assertIn('href="?backups-page=1"', payload['html'])

    def test_the_restore_poller_pages_too(self):
        for _ in range(7):
            self.SystemRestore.objects.create(requested_by_username='boss', backup_file_path='x.dlb', status='completed')
        payload = self.client.get(reverse('system_restore_list_status'), {'restores-page': 2}).json()
        self.assertEqual(len(_rows(payload['html'], 'data-system-restore-row')), 2)

    def test_rows_carry_actions_not_buttons(self):
        (backup,) = self._backups(1)
        page = self.client.get(reverse('system_backup_page')).content.decode()
        self.assertNotIn('sysbackup-details-open', page)
        self.assertIn('data-dlux-context="true"', page)
        events = [action.get('event') or action.get('type') for action in _actions(page, backup.token)]
        self.assertEqual(events, ['dlux:backup:details', 'url', 'dlux:backup:restore', 'divider', 'dlux:backup:delete'])

    def test_the_column_layout_adds_the_three_dot_trigger(self):
        SystemSettings = apps.get_model('dlux', 'SystemSettings')
        settings_obj = SystemSettings.load()
        layout = dict(settings_obj.layout_config or {})
        layout['row_actions_style'] = 'column'
        settings_obj.layout_config = layout
        settings_obj.save()
        self._backups(1)
        page = self.client.get(reverse('system_backup_page')).content.decode()
        self.assertIn('dlux-row-actions-trigger', page)
        self.assertNotIn('data-dlux-context="true"', page)


class BackupRowActionTests(TestCase):
    def setUp(self):
        self.SystemBackup = apps.get_model('dlux', 'SystemBackup')

    def _names(self, backup):
        return [action.get('event') or action.get('type') for action in system_backup_row_actions(backup)]

    @override_settings(USE_TZ=True, TIME_ZONE='Africa/Tripoli')
    def test_action_labels_use_the_local_time_the_table_shows(self):
        backup = self.SystemBackup.objects.create(requested_by_username='x', status='completed')
        expected = timezone.localtime(backup.created_at).strftime('%Y-%m-%d %H:%M')
        details = system_backup_row_actions(backup)[0]
        self.assertEqual(details['data']['label'], expected)
        self.assertNotEqual(expected, backup.created_at.strftime('%Y-%m-%d %H:%M'), 'the zone must differ from UTC here')

    def test_a_running_backup_offers_cancel_and_never_delete(self):
        running = self.SystemBackup.objects.create(requested_by_username='x', status='running')
        self.assertEqual(self._names(running), ['dlux:backup:details', 'divider', 'dlux:backup:cancel'])

    def test_a_failed_backup_offers_retry_with_its_passphrase_need(self):
        failed = self.SystemBackup.objects.create(requested_by_username='x', status='failed', encryption='passphrase')
        actions = system_backup_row_actions(failed)
        resume = next(action for action in actions if action.get('event') == 'dlux:backup:resume')
        self.assertTrue(resume['data']['needsPassphrase'])
        self.assertIn('dlux:backup:delete', self._names(failed))

    def test_an_incremental_backup_downloads_its_chain(self):
        increment = self.SystemBackup.objects.create(
            requested_by_username='x', status='completed', kind=self.SystemBackup.KIND_INCREMENTAL,
        )
        download = next(action for action in system_backup_row_actions(increment) if action.get('type') == 'url')
        self.assertEqual(download['url'], reverse('system_backup_chain_download', args=[increment.token]))

    def test_deleting_a_chain_base_warns_only_when_later_backups_exist(self):
        base = self.SystemBackup.objects.create(
            requested_by_username='x', status='completed', index_root='abc', sequence=0,
        )
        base.chain_id = base.token
        base.save(update_fields=['chain_id'])

        def delete_data():
            return next(a for a in system_backup_row_actions(base) if a.get('event') == 'dlux:backup:delete')['data']

        self.assertNotIn('chainConfirm', delete_data())
        self.SystemBackup.objects.create(
            requested_by_username='x', status='completed', kind=self.SystemBackup.KIND_INCREMENTAL,
            chain_id=base.token, sequence=1,
        )
        # Judged on the server: the later backup may be on another page.
        self.assertIn('chainConfirm', delete_data())
