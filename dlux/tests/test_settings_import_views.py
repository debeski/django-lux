"""End-to-end behaviour of the Options-page config import.

The change-set logic is unit tested in test_settings_diff.py. These cover the
parts that only exist once a request, a database and a session are involved:
permissions, that nothing is written until apply, that the snapshot is real,
and that revert puts back what was there.
"""
import json

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from dlux.models import SystemSettings, SystemSettingsSnapshot
from dlux.utils import export_system_settings_payload

User = get_user_model()


def _upload(settings_dict, name='config.json'):
    payload = {'format': 'django-lux.system-settings', 'dlux_version': '1.8.0',
               'settings': settings_dict}
    return SimpleUploadedFile(
        name, json.dumps(payload).encode('utf-8'), content_type='application/json')


class SettingsImportViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_superuser('admin', 'a@example.com', 'pw')
        self.plain = User.objects.create_user('plain', 'p@example.com', 'pw')
        s = SystemSettings.load()
        s.is_configured = True
        s.home_url = '/current/'
        s.save()
        self.preview_url = reverse('system_settings_import_preview')
        self.apply_url = reverse('system_settings_import_apply')
        self.revert_url = reverse('system_settings_import_revert')
        self.review_url = reverse('system_settings_import_review')

    # --- permissions -----------------------------------------------------
    def test_a_non_superuser_cannot_preview(self):
        self.client.force_login(self.plain)
        response = self.client.post(self.preview_url, {'config_file': _upload({'home_url': '/x/'})})
        self.assertEqual(response.status_code, 403)

    def test_a_non_superuser_cannot_apply(self):
        self.client.force_login(self.plain)
        self.assertEqual(self.client.post(self.apply_url, {'apply': ['home_url']}).status_code, 403)

    def test_get_is_rejected(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.preview_url).status_code, 405)

    # --- preview ---------------------------------------------------------
    def test_preview_reports_the_change_without_writing_anything(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.preview_url, {'config_file': _upload({'home_url': '/from-file/'})})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['ok'])
        self.assertEqual(body['change_count'], 1)
        # Preview parks the change set and returns the address the dynamic modal
        # should fetch; the markup comes from that second request.
        self.assertEqual(body['review_url'], self.review_url)
        review = self.client.get(self.review_url).json()
        self.assertIn('/from-file/', review['html'])
        self.assertEqual(
            SystemSettings.load().home_url, '/current/',
            'preview must not touch the live settings',
        )

    def test_preview_rejects_a_non_json_file(self):
        self.client.force_login(self.admin)
        bad = SimpleUploadedFile('c.json', b'not json at all', content_type='application/json')
        response = self.client.post(self.preview_url, {'config_file': bad})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['ok'])

    def test_preview_rejects_a_missing_file(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(self.preview_url, {}).status_code, 400)

    def test_preview_checkboxes_start_unticked(self):
        """The safe default on a populated system is to keep what is there."""
        self.client.force_login(self.admin)
        self.client.post(self.preview_url, {'config_file': _upload({'home_url': '/from-file/'})})
        html = self.client.get(self.review_url).json()['html']
        self.assertIn('name="apply"', html)
        self.assertNotIn('checked', html)


    def test_the_review_endpoint_answers_json_for_the_dynamic_modal(self):
        """The modal parses the response and injects `data.html`.

        Returning a bare HTML document made it fail with a JSON parse error and
        fall back to rendering inside the options card, which wrecked the page.
        """
        self.client.force_login(self.admin)
        self.client.post(self.preview_url, {'config_file': _upload({'home_url': '/from-file/'})})
        response = self.client.get(self.review_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertIn('html', response.json())

    def test_the_review_endpoint_is_graceful_when_nothing_is_pending(self):
        self.client.force_login(self.admin)
        body = self.client.get(self.review_url).json()
        self.assertIn('html', body, 'it must still answer the modal, not blow up')

    def test_a_non_superuser_cannot_read_the_review(self):
        self.client.force_login(self.plain)
        self.assertEqual(self.client.get(self.review_url).status_code, 403)

    # --- apply -----------------------------------------------------------
    def test_apply_writes_only_the_ticked_change(self):
        self.client.force_login(self.admin)
        self.client.post(self.preview_url, {'config_file': _upload({
            'home_url': '/from-file/', 'footer_text': 'from file',
        })})
        response = self.client.post(self.apply_url, {'apply': ['home_url']})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        reloaded = SystemSettings.load()
        self.assertEqual(reloaded.home_url, '/from-file/')
        self.assertNotEqual(
            reloaded.footer_text, 'from file',
            'an unticked change must not be applied',
        )

    def test_apply_without_a_preview_is_refused(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.apply_url, {'apply': ['home_url']})
        self.assertEqual(response.status_code, 400)

    def test_apply_with_nothing_ticked_is_refused(self):
        self.client.force_login(self.admin)
        self.client.post(self.preview_url, {'config_file': _upload({'home_url': '/from-file/'})})
        self.assertEqual(self.client.post(self.apply_url, {}).status_code, 400)

    def test_apply_cannot_be_talked_into_a_value_that_was_never_reviewed(self):
        """The change set is re-read from the session, not from the post."""
        self.client.force_login(self.admin)
        self.client.post(self.preview_url, {'config_file': _upload({'home_url': '/from-file/'})})
        self.client.post(self.apply_url, {'apply': ['footer_text']})
        self.assertEqual(SystemSettings.load().home_url, '/current/')

    def test_apply_records_a_snapshot_of_what_it_replaced(self):
        self.client.force_login(self.admin)
        self.client.post(self.preview_url, {'config_file': _upload({'home_url': '/from-file/'})})
        self.client.post(self.apply_url, {'apply': ['home_url']})

        snapshot = SystemSettingsSnapshot.objects.get()
        self.assertEqual(snapshot.applied_keys, ['home_url'])
        self.assertEqual(snapshot.created_by, self.admin)
        self.assertEqual(
            snapshot.payload['settings']['home_url'], '/current/',
            'the snapshot must hold the value that was replaced',
        )

    # --- revert ----------------------------------------------------------
    def test_revert_restores_the_previous_value(self):
        self.client.force_login(self.admin)
        self.client.post(self.preview_url, {'config_file': _upload({'home_url': '/from-file/'})})
        self.client.post(self.apply_url, {'apply': ['home_url']})
        self.assertEqual(SystemSettings.load().home_url, '/from-file/')

        response = self.client.post(self.revert_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(SystemSettings.load().home_url, '/current/')

    def test_revert_marks_the_snapshot_so_it_is_not_reused(self):
        self.client.force_login(self.admin)
        self.client.post(self.preview_url, {'config_file': _upload({'home_url': '/from-file/'})})
        self.client.post(self.apply_url, {'apply': ['home_url']})
        self.client.post(self.revert_url)

        self.assertIsNotNone(SystemSettingsSnapshot.objects.get().reverted_at)
        self.assertEqual(
            self.client.post(self.revert_url).status_code, 400,
            'a spent snapshot must not be reverted twice',
        )

    def test_revert_with_no_snapshot_is_refused(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(self.revert_url).status_code, 400)
