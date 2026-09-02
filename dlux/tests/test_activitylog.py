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
        # The strip is the Ribbon's now, but the regression it guards is the same.
        counts = {tab.key: tab.count for tab in response.context['ribbon'].tabs}

        # Both exceed 1 — the bug capped every non-empty badge at exactly 1.
        self.assertEqual(counts.get('user'), 4)
        self.assertEqual(counts.get('system'), 2)

    def test_badges_count_the_whole_list_not_the_active_tab(self):
        """Counting through the active tab would make every badge read that
        tab's total — which is what the strip's build-time guard prevents."""
        self._make_logs('user', 4)
        self._make_logs('system', 2)

        response = self.client.get(reverse('user_activity_log'), {'category': 'system'})
        counts = {tab.key: tab.count for tab in response.context['ribbon'].tabs}
        self.assertEqual(counts.get('user'), 4)
        self.assertEqual(counts.get('system'), 2)


class ActivityLogRibbonTests(TestCase):
    """The page's filter band is dlux's own Ribbon.

    This is the first dlux screen with a real advanced panel, so it is where the
    derivation, the preserved tab key and the panel's server-rendered open state
    are exercised against a live page rather than a synthetic FilterSet.
    """

    def setUp(self):
        self.admin = User.objects.create_superuser('admin', 'admin@example.com', 'pw')
        self.client = Client()
        self.client.force_login(self.admin)
        settings = SystemSettings.load()
        settings.is_configured = True
        settings.save()
        self.url = reverse('user_activity_log')

    def test_the_band_is_the_ribbon(self):
        html = self.client.get(self.url).content.decode()
        self.assertIn('dlux-ribbon-header', html)
        self.assertIn('dlux-ribbon-filter', html)
        # The hand-rolled heading it replaces must not linger alongside it.
        self.assertNotIn('page-title', html)

    def test_the_page_is_the_shared_list_arrangement(self):
        """First screen on `dlux/list_page.html`: wrapper, no card, modal outside."""
        html = self.client.get(self.url).content.decode()

        self.assertIn('dlux-list-page', html)
        self.assertIn('dlux-table-shell', html)
        self.assertNotIn('dlux-table-card', html)
        self.assertLess(html.index('dlux-ribbon-header'), html.index('dlux-table-shell'))
        # The detail modal comes from `list_modals`, outside the list wrapper.
        self.assertGreater(
            html.index('id="activityLogDetailModal"'),
            html.index('dlux-table-shell'),
        )
        self.assertIn('activitylog/js/main.js', html)

    def test_search_and_year_lead_the_row_and_the_dates_do_not(self):
        html = self.client.get(self.url).content.decode()
        primary = html[html.index('row g-2 align-items-start mb-0'):html.index('id="dlux-ribbon-advanced"')]
        self.assertIn('name="keyword"', primary)
        self.assertIn('name="year"', primary)
        self.assertNotIn('name="created_at__gte"', primary)

    def test_the_date_range_is_in_the_advanced_panel(self):
        html = self.client.get(self.url).content.decode()
        panel = html[html.index('id="dlux-ribbon-advanced"'):]
        self.assertIn('name="created_at__gte"', panel)
        self.assertIn('name="created_at__lte"', panel)

    def test_the_panel_opens_when_an_advanced_filter_is_set(self):
        closed = self.client.get(self.url).content.decode()
        self.assertIn('<div class="collapse m-0" id="dlux-ribbon-advanced"', closed)
        opened = self.client.get(self.url, {'created_at__gte': '2026-01-01'}).content.decode()
        self.assertIn('<div class="collapse show m-0" id="dlux-ribbon-advanced"', opened)

    def test_the_category_tab_survives_a_filter_submit(self):
        """The tabs live in the query string and the ribbon is a GET form, so
        without the hidden input the first filter drops the reader to tab one."""
        html = self.client.get(self.url, {'category': 'system'}).content.decode()
        self.assertIn('<input type="hidden" name="category" value="system">', html)

    def test_switching_tabs_keeps_the_filter(self):
        """The links used to be a bare `?category=<key>`, which dropped every
        other parameter and silently cleared the filter just applied."""
        html = self.client.get(self.url, {'category': 'system', 'keyword': 'x'}).content.decode()
        self.assertIn('?category=user&amp;keyword=x', html)

    def test_switching_tabs_drops_the_page(self):
        """Page 4 of one category is rarely a valid page of another. Scoped to
        the tab links: the table's own pagination legitimately carries `page`."""
        import re

        html = self.client.get(self.url, {'category': 'system', 'page': '3'}).content.decode()
        tab_links = re.findall(r'href="(\?[^"]*)" role="tab"', html)
        self.assertTrue(tab_links, 'no category tabs rendered')
        for link in tab_links:
            self.assertNotIn('page=3', link)

    def test_the_ribbon_script_is_loaded(self):
        """This template overrode `{% block scripts %}` without `block.super`,
        so it used to load none of `list_base`'s assets."""
        html = self.client.get(self.url).content.decode()
        self.assertIn('dlux/ribbon/js/ribbon.js', html)
