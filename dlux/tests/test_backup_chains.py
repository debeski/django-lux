"""Incremental backup chains: deltas, sidecars, chain restore, rotation."""

import io
import json
import shutil
import tempfile
import zipfile

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from datetime import timedelta
from unittest import mock

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.storage import default_storage
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from dlux.backup import (
    apply_backup_retention,
    decrypt_dlb_to_tempfile,
    incremental_backup_row,
    open_chain_head,
    run_scheduled_system_backup,
    run_system_backup,
    run_system_restore,
)
from dlux.backup.chain import index_root, read_index_sidecar
from dlux.system.defaults import default_backup_config
from dlux.system.normalizers import normalize_backup_config

User = get_user_model()


class ChainTestCase(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.media = override_settings(MEDIA_ROOT=self.media_root)
        self.media.enable()
        self.SystemBackup = apps.get_model('dlux', 'SystemBackup')
        self.SystemRestore = apps.get_model('dlux', 'SystemRestore')
        self.ActivityLog = apps.get_model('dlux', 'ActivityLog')

    def tearDown(self):
        self.media.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def _config(self, **overrides):
        SystemSettings = apps.get_model('dlux', 'SystemSettings')
        settings_obj = SystemSettings.load()
        settings_obj.is_configured = True
        settings_obj.backup_config = normalize_backup_config({**default_backup_config(), **overrides})
        settings_obj.save()

    def _full(self, **fields):
        backup = self.SystemBackup.objects.create(requested_by_username='root', **fields)
        run_system_backup(backup.pk, passphrase=fields.get('_passphrase'))
        backup.refresh_from_db()
        self.assertEqual(backup.status, 'completed', backup.error)
        return backup

    def _increment(self, passphrase=None):
        head, reason = open_chain_head()
        self.assertIsNotNone(head, reason)
        backup = incremental_backup_row(head, requested_by='root', trigger='manual')
        run_system_backup(backup.pk, passphrase=passphrase)
        backup.refresh_from_db()
        return backup

    def _archive(self, backup, passphrase=None):
        with default_storage.open(backup.file_path, 'rb') as fh:
            _meta, tmp = decrypt_dlb_to_tempfile(fh, passphrase=passphrase)
        return zipfile.ZipFile(tmp)

    def _restore(self, backup, passphrase=None):
        restore = self.SystemRestore.objects.create(requested_by_username='root', backup_file_path=backup.file_path)
        run_system_restore(restore.pk, passphrase=passphrase)
        restore.refresh_from_db()
        return restore


class IncrementalContentTests(ChainTestCase):
    def test_full_backup_is_a_chain_base_with_a_matching_sidecar(self):
        User.objects.create_user('alice', password='x')
        base = self._full()
        self.assertEqual((base.kind, base.sequence, base.chain_id), ('full', 0, base.token))
        self.assertTrue(base.index_root and base.migration_digest)
        index = read_index_sidecar(base.index_path)
        self.assertEqual(index_root(index), base.index_root)
        self.assertIn('auth.user', index['models'])
        with self._archive(base) as zf:
            self.assertEqual(json.loads(zf.read('index.json')), index)

    def test_increment_holds_only_changes_and_deletions(self):
        alice = User.objects.create_user('alice', password='x')
        bob = User.objects.create_user('bob', password='x')
        for i in range(30):
            self.ActivityLog.objects.create(created_by=alice, action='CREATE', model_name=f'T{i}')
        base = self._full()

        bob.first_name = 'Robert'
        bob.save()
        User.objects.create_user('carol', password='x')
        self.ActivityLog.objects.filter(model_name='T0').delete()
        inc = self._increment()

        self.assertEqual((inc.status, inc.kind, inc.sequence, inc.chain_id), ('completed', 'incremental', 1, base.token))
        with self._archive(inc) as zf:
            manifest = json.loads(zf.read('manifest.json'))
            users = {item['fields']['username'] for item in json.loads(zf.read('data/auth/user.json'))}
            deleted = json.loads(zf.read('deleted/dlux/activitylog.json'))
            logs = json.loads(zf.read('data/dlux/activitylog.json'))
        self.assertEqual(users, {'bob', 'carol'})
        self.assertEqual(len(deleted), 1)
        # Only the base backup's own EXPORT entry is new; no CREATE row changed.
        self.assertEqual([item['fields']['action'] for item in logs], ['EXPORT'])
        self.assertEqual(manifest['chain']['parent_root'], base.index_root)
        self.assertLess(inc.row_count, base.row_count)
        log_entry = next(item for item in manifest['models'] if item['model'] == 'dlux.activitylog')
        self.assertEqual((log_entry['count'], log_entry['deleted']), (1, 1))

    def test_unchanged_media_is_not_copied_again(self):
        from django.core.files.base import ContentFile

        worker = User.objects.create_user('worker', password='x')
        worker.profile.profile_picture.save('a.png', ContentFile(b'png-a'), save=True)
        base = self._full()
        self.assertEqual(base.file_count, 1)
        User.objects.create_user('other', password='x')
        inc = self._increment()
        self.assertEqual(inc.file_count, 0)
        worker.profile.profile_picture.save('b.png', ContentFile(b'png-b'), save=True)
        inc2 = self._increment()
        self.assertEqual(inc2.file_count, 1)


class ChainRestoreTests(ChainTestCase):
    def _state(self):
        return {
            'users': sorted(User.objects.values_list('username', 'first_name')),
            'logs': sorted(self.ActivityLog.objects.exclude(action__in=['EXPORT', 'RESTORE']).values_list('model_name', flat=True)),
            'groups': sorted(Group.objects.values_list('name', flat=True)),
            'memberships': sorted(
                (user.username, group.name) for user in User.objects.all() for group in user.groups.all()
            ),
        }

    def test_restoring_any_member_reproduces_that_point(self):
        alice = User.objects.create_user('alice', password='x')
        editors = Group.objects.create(name='editors')
        readers = Group.objects.create(name='readers')
        alice.groups.add(editors)
        self.ActivityLog.objects.create(created_by=alice, action='CREATE', model_name='one')
        base = self._full()
        at_base = self._state()

        alice.first_name = 'Alice'
        alice.save()
        alice.groups.add(readers)
        bob = User.objects.create_user('bob', password='x')
        bob.groups.add(editors)
        self.ActivityLog.objects.create(created_by=bob, action='CREATE', model_name='two')
        inc1 = self._increment()
        at_inc1 = self._state()

        bob.delete()
        editors.delete()
        self.ActivityLog.objects.filter(model_name='one').delete()
        self.ActivityLog.objects.create(created_by=alice, action='CREATE', model_name='three')
        inc2 = self._increment()
        at_inc2 = self._state()
        self.assertEqual(inc2.sequence, 2)

        User.objects.create_user('intruder', password='x')
        Group.objects.create(name='later')

        for member, expected in ((inc2, at_inc2), (inc1, at_inc1), (base, at_base)):
            restore = self._restore(member)
            self.assertEqual(restore.status, 'completed', restore.error)
            self.assertEqual(restore.report['chain_members'], member.sequence + 1)
            self.assertEqual(self._state(), expected, f'restoring member {member.sequence}')

    def test_missing_middle_member_fails_before_touching_data(self):
        alice = User.objects.create_user('alice', password='x')
        self._full()
        alice.first_name = 'A'
        alice.save()
        inc1 = self._increment()
        alice.first_name = 'B'
        alice.save()
        inc2 = self._increment()
        default_storage.delete(inc1.file_path)
        User.objects.create_user('kept', password='x')

        restore = self._restore(inc2)
        self.assertEqual(restore.status, 'failed')
        self.assertIn('member 1', restore.error)
        self.assertTrue(User.objects.filter(username='kept').exists())

    def test_foreign_member_with_the_right_sequence_is_rejected(self):
        alice = User.objects.create_user('alice', password='x')
        self._full()
        alice.first_name = 'A'
        alice.save()
        inc1 = self._increment()
        alice.first_name = 'B'
        alice.save()
        inc2 = self._increment()
        # Replace member 1 with a copy of member 2's bytes under member 1's name.
        with default_storage.open(inc2.file_path, 'rb') as fh:
            data = fh.read()
        default_storage.delete(inc1.file_path)
        default_storage.save(inc1.file_path, io.BytesIO(data))
        restore = self._restore(inc2)
        self.assertEqual(restore.status, 'failed')
        self.assertIn('chain', restore.error.lower())

    def test_passphrase_chain_keeps_one_passphrase(self):
        User.objects.create_user('alice', password='x')
        base = self.SystemBackup.objects.create(
            requested_by_username='root', encryption='passphrase', passphrase_required=True,
        )
        run_system_backup(base.pk, passphrase='chain-pass')
        base.refresh_from_db()
        self.assertEqual(base.status, 'completed', base.error)

        User.objects.create_user('bob', password='x')
        wrong = self._increment(passphrase='other-pass')
        self.assertEqual(wrong.status, 'failed')
        self.assertIn('Wrong passphrase', wrong.error)
        wrong.delete()

        right = self._increment(passphrase='chain-pass')
        self.assertEqual(right.status, 'completed', right.error)
        self.assertEqual(right.encryption, 'passphrase')
        restore = self._restore(right, passphrase='chain-pass')
        self.assertEqual(restore.status, 'completed', restore.error)
        self.assertTrue(User.objects.filter(username='bob').exists())


class ChainPolicyTests(ChainTestCase):
    def test_no_chain_without_an_indexed_full_backup(self):
        self.assertEqual(open_chain_head(), (None, 'no_base'))

    def test_chain_closes_on_schema_change_length_and_age(self):
        self._config(max_chain_length=1, full_every_days=7)
        base = self._full()
        self.assertEqual(open_chain_head()[0], base)

        with mock.patch('dlux.backup.chain.migration_digest', return_value='other'):
            self.assertEqual(open_chain_head(), (None, 'schema_changed'))

        self._increment()
        self.assertEqual(open_chain_head(), (None, 'chain_full'))

        self._config(max_chain_length=24, full_every_days=7)
        self.SystemBackup.objects.filter(pk=base.pk).update(completed_at=timezone.now() - timedelta(days=8))
        self.assertEqual(open_chain_head(), (None, 'base_too_old'))

    def test_scheduled_runs_continue_the_chain_when_enabled(self):
        self._config(scheduled_enabled=True, schedule_interval_hours=1, incremental_enabled=True)
        first = run_scheduled_system_backup()
        self.assertEqual((first.kind, first.status), ('full', 'completed'))
        self.SystemBackup.objects.filter(pk=first.pk).update(created_at=timezone.now() - timedelta(hours=2))
        second = run_scheduled_system_backup()
        self.assertEqual((second.kind, second.status, second.parent_id), ('incremental', 'completed', first.pk))

    def test_retention_removes_whole_chains(self):
        self._config(max_backups_to_keep=1)
        old_base = self._full()
        User.objects.create_user('x1', password='x')
        old_inc = self._increment()
        files = [old_base.file_path, old_base.index_path, old_inc.file_path, old_inc.index_path]
        new_base = self._full()
        apply_backup_retention(protected_pk=new_base.pk)
        self.assertEqual(list(self.SystemBackup.objects.values_list('pk', flat=True)), [new_base.pk])
        self.assertFalse(any(default_storage.exists(path) for path in files))


class ChainViewTests(ChainTestCase):
    def setUp(self):
        super().setUp()
        self._config()
        User.objects.create_superuser('boss', 'b@example.com', 'bosspass123')
        self.client = Client()
        self.client.login(username='boss', password='bosspass123')

    def test_incremental_needs_a_chain(self):
        response = self.client.post(reverse('system_backup_create'), {'backup_kind': 'incremental'})
        self.assertEqual(response.status_code, 400)

    def test_incremental_create_inherits_the_chain(self):
        base = self._full(media_included=False, encryption='none')
        with mock.patch('dlux.views.backup.dispatch_system_backup', return_value=True):
            response = self.client.post(reverse('system_backup_create'), {
                'backup_kind': 'incremental', 'backup_encryption': 'server_key', 'backup_scope': 'full',
            })
        self.assertEqual(response.status_code, 200)
        row = self.SystemBackup.objects.get(token=response.json()['token'])
        self.assertEqual(
            (row.kind, row.parent_id, row.media_included, row.encryption),
            ('incremental', base.pk, False, 'none'),
        )

    def test_deleting_a_member_deletes_the_later_ones(self):
        base = self._full()
        User.objects.create_user('a', password='x')
        inc1 = self._increment()
        User.objects.create_user('b', password='x')
        inc2 = self._increment()
        self.client.post(reverse('system_backup_delete', args=[inc1.token]))
        self.assertEqual(list(self.SystemBackup.objects.values_list('pk', flat=True)), [base.pk])
        self.assertFalse(default_storage.exists(inc2.index_path))

    def test_chain_download_bundles_every_member(self):
        base = self._full()
        User.objects.create_user('a', password='x')
        inc = self._increment()
        response = self.client.get(reverse('system_backup_chain_download', args=[inc.token]))
        self.assertEqual(response.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(b''.join(response.streaming_content))) as zf:
            self.assertEqual(
                sorted(zf.namelist()),
                sorted(path.rsplit('/', 1)[-1] for path in (base.file_path, inc.file_path)),
            )

    def test_page_and_poll_report_the_open_chain(self):
        self._full()
        page = self.client.get(reverse('system_backup_page')).content.decode()
        self.assertIn('value="incremental">', page.replace(' disabled', ' DISABLED'))
        chain = self.client.get(reverse('system_backup_list_status')).json()['chain']
        self.assertEqual((chain['available'], chain['next_sequence']), (True, 1))
