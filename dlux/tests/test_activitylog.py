from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from dlux.models import ActivityLog, SystemSettings

User = get_user_model()


class ActivityLogTabCountTests(TestCase):
    """Regression for the category-tab badges reading a fixed 1 (or 0)."""

    def setUp(self):
        self.admin = User.objects.create_superuser('admin', 'admin@example.com', 'pw')
        self.client = Client()
        self.client.force_login(self.admin)
        settings = SystemSettings.load()
        settings.is_configured = True
        settings.save()

    def _make_logs(self, category, n):
        for i in range(n):
            ActivityLog.objects.create(
                created_by=self.admin, action='test', category=category,
                model_name=f'Thing{i}',
            )

    def test_tab_badges_report_real_per_category_counts(self):
        # More than one row per category — the bug capped every badge at 1
        # because the queryset's `.order_by('-created_at')` leaked into the
        # values()/annotate() GROUP BY.
        self._make_logs('user', 4)
        self._make_logs('system', 2)

        response = self.client.get(reverse('user_activity_log'))
        self.assertEqual(response.status_code, 200)
        counts = {tab['key']: tab['count'] for tab in response.context['log_category_tabs']}

        # Both exceed 1 — the bug capped every non-empty badge at exactly 1.
        self.assertEqual(counts.get('user'), 4)
        self.assertEqual(counts.get('system'), 2)
