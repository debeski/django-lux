"""The General Reports builder: model identities and labels, search, every
period in the user report, and the activity backfill for older records."""

import json
from datetime import timedelta
from io import StringIO
from types import SimpleNamespace
from unittest import mock

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from dlux.reports import REPORT_WINDOWS, build_reports_overview, is_report_eligible_model
from dlux.reports.backfill import backfill_report_activity
from dlux.reports.users import build_user_report
from dlux.tests.document_files_app.models import Paper
from dlux.translations import resolve_model_label

User = get_user_model()


class ReportBuilderTests(TestCase):
    def setUp(self):
        SystemSettings = apps.get_model('dlux', 'SystemSettings')
        settings_obj = SystemSettings.load()
        settings_obj.is_configured = True
        settings_obj.save(update_fields=['is_configured'])
        self.ActivityLog = apps.get_model('dlux', 'ActivityLog')
        self.admin = User.objects.create_superuser('boss', 'boss@example.com', 'pw12345!')
        self.clerk = User.objects.create_user('clerk', first_name='Huda', last_name='Salem', password='x')

    def log(self, action='CREATE', **fields):
        fields.setdefault('created_by', self.clerk)
        return self.ActivityLog.objects.create(action=action, **fields)

    def entry(self, overview, key):
        return next(item for item in overview['available_models'] if item['key'] == key)

    def test_rows_under_a_legacy_name_join_their_models_entry_and_label(self):
        self.log(model_name='Paper', model_key='document_files_app.paper')
        self.log(model_name='paper')
        overview = build_reports_overview(self.admin, window='all')
        keys = [item['key'] for item in overview['available_models']]
        self.assertEqual(keys.count('document_files_app.paper'), 1)
        self.assertNotIn('paper', keys)
        self.assertEqual(self.entry(overview, 'document_files_app.paper')['label'], resolve_model_label(Paper))
        self.assertEqual(overview['models'], [
            {'key': 'document_files_app.paper', 'label': resolve_model_label(Paper), 'count': 2},
        ])
        selected = build_reports_overview(
            self.admin, window='all', filters={'builder': '1', 'models': ['document_files_app.paper'], 'operations': ['CREATE']},
        )
        self.assertEqual(selected['current_total'], 2)

    def test_infrastructure_packages_are_not_reported(self):
        self.assertTrue(is_report_eligible_model(Paper))
        # django-health-check's TestModel is labelled `db`; only its package says what it is.
        with mock.patch.object(type(Paper._meta), 'app_config', new_callable=mock.PropertyMock,
                               return_value=SimpleNamespace(name='health_check.db')):
            self.assertFalse(is_report_eligible_model(Paper))

    def test_search_matches_what_the_page_shows(self):
        self.log(model_name='Paper', model_key='document_files_app.paper', number='77/2026')
        self.log(action='UPDATE', model_name='Paper', model_key='document_files_app.paper', created_by=self.admin)
        for keyword, expected in (
            ('Huda Salem', 1),
            (resolve_model_label(Paper), 2),
            ('77/2026', 1),
            ('no such thing', 0),
        ):
            with self.subTest(keyword=keyword):
                overview = build_reports_overview(self.admin, window='all', filters={'q': keyword})
                self.assertEqual(overview['current_total'], expected)
        create_label = next(item['label'] for item in build_reports_overview(self.admin, window='all')['available_actions']
                            if item['key'] == 'CREATE')
        self.assertEqual(build_reports_overview(self.admin, window='all', filters={'q': create_label})['current_total'], 1)

    def test_the_search_field_suggests_users_models_and_operations(self):
        self.log(model_name='Paper', model_key='document_files_app.paper')
        suggestions = build_reports_overview(self.admin, window='all')['search_suggestions']
        for value in ('clerk', 'Huda Salem', resolve_model_label(Paper)):
            self.assertIn(value, suggestions)
        self.assertEqual(len(suggestions), len({value.casefold() for value in suggestions}))

    def test_the_user_report_builds_every_period_the_page_offers(self):
        self.log(model_name='Paper', model_key='document_files_app.paper')
        today = timezone.localdate().isoformat()
        for window in sorted(REPORT_WINDOWS):
            with self.subTest(window=window):
                report = build_user_report(self.clerk, actor=self.admin, window=window, activity_only=True,
                                           custom_start=today, custom_end=today)
                self.assertEqual(report['summary']['activity_count'], 1)
                self.assertEqual(report['selected_window_stats']['activity_count'], 1)
                self.assertEqual(report['selected_period_tab'], window not in ('week', 'month', 'all'))

    def test_the_user_report_modal_opens_on_a_custom_range(self):
        self.log(model_name='Paper', model_key='document_files_app.paper')
        client = Client()
        client.force_login(self.admin)
        today = timezone.localdate().isoformat()
        response = client.get(
            reverse('user_report_modal', args=[self.clerk.pk]),
            {'window': 'custom', 'custom_start': today, 'custom_end': today},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        html = json.loads(response.content)['html']
        self.assertIn(f'data-dlux-user-report-export-query="window=custom&amp;custom_start={today}&amp;custom_end={today}"', html)
        page = client.get(reverse('reports_overview'), {'window': 'custom', 'custom_start': today, 'custom_end': today})
        self.assertContains(page, f'?window=custom&amp;custom_start={today}&amp;custom_end={today}')


class ReportActivityBackfillTests(TestCase):
    def setUp(self):
        self.ActivityLog = apps.get_model('dlux', 'ActivityLog')
        self.author = User.objects.create_user('author', password='x')
        self.old = Paper.objects.create(title='Old', created_by=self.author)
        self.logged = Paper.objects.create(title='Logged')
        long_ago = timezone.now() - timedelta(days=400)
        Paper.all_objects.filter(pk=self.old.pk).update(created_at=long_ago)
        self.long_ago = Paper.all_objects.get(pk=self.old.pk).created_at
        # Already counted, under a legacy name and no key.
        self.ActivityLog.objects.create(action='CREATE', model_name='Paper', object_id=self.logged.pk)

    def counts(self, **kwargs):
        rows = backfill_report_activity([Paper], **kwargs)
        return rows[0]['missing'], rows[0]['written']

    def test_a_dry_run_writes_nothing(self):
        self.assertEqual(self.counts(), (1, 0))
        self.assertFalse(self.ActivityLog.objects.filter(details__backfilled=True).exists())

    def test_apply_writes_one_create_row_from_the_record_and_is_idempotent(self):
        self.assertEqual(self.counts(apply=True), (1, 1))
        row = self.ActivityLog.objects.get(details__backfilled=True)
        self.assertEqual(
            (row.action, row.model_key, row.object_id, row.created_by_id, row.category, row.created_at),
            ('CREATE', 'document_files_app.paper', self.old.pk, self.author.pk, 'user', self.long_ago),
        )
        self.assertEqual(self.counts(apply=True), (0, 0))

    def test_the_command_reports_and_applies(self):
        out = StringIO()
        call_command('dlux_backfill_report_activity', '--model', 'document_files_app.Paper', stdout=out)
        self.assertIn('document_files_app.paper: 1 missing', out.getvalue())
        call_command('dlux_backfill_report_activity', '--model', 'document_files_app.Paper', '--apply', stdout=out)
        self.assertIn('Wrote 1 CREATE rows.', out.getvalue())
        overview = build_reports_overview(User.objects.create_superuser('root', 'r@example.com', 'pw12345!'), window='all')
        self.assertEqual(overview['current_total'], 2)
