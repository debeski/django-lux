"""Render-cost guards.

Two regressions cost ~10x on the Options page and made every page slower. Both
were invisible to correctness tests — the pages rendered fine, just slowly — so
they are pinned here by cost rather than by output.

1. **Context processors must run once per request.** The `{% dlux_card %}` /
   `{% dlux_option_card %}` family used ``get_template(name).render(ctx, request)``,
   which builds a *new* RequestContext and therefore re-runs every context
   processor. A page with 13 wrapped cards ran `dlux_context` 13 extra times,
   each doing config and font lookups.

2. **The font list must be looked up once per request.** Config normalisation
   calls `get_available_fonts()` from several places, so one page issued ~278
   managed-font queries. On SQLite that is tens of milliseconds; on PostgreSQL it
   is ~800 round trips (the bootstrap savepoint wraps each call in
   BEGIN/SELECT/COMMIT), which is where the multi-second page loads came from.
"""
from dlux.tests.harness import setup_test_environment

setup_test_environment()

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

User = get_user_model()


class RenderCostTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser('costs', 'costs@example.com', 'costpass123')

    def setUp(self):
        from dlux.models import SystemSettings

        settings_row = SystemSettings.load()
        settings_row.is_configured = True
        settings_row.save()
        cache.clear()
        self.client = Client()
        self.client.force_login(self.user)

    def test_context_processors_run_once_per_request(self):
        import dlux.context_processors as context_processors

        with patch.object(
            context_processors, 'dlux_context',
            wraps=context_processors.dlux_context,
        ) as spy:
            response = self.client.get(reverse('options_view'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            spy.call_count, 1,
            f'dlux_context ran {spy.call_count} times for one request. A template '
            'wrapper is building a new RequestContext instead of rendering into '
            'the current one — see _WrapperNode.render in dlux_tags.',
        )

    def test_the_font_list_is_looked_up_once_per_request(self):
        import dlux.fonts as fonts

        with patch.object(fonts, '_build_available_fonts', wraps=fonts._build_available_fonts) as spy:
            response = self.client.get(reverse('options_view'))

        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(
            spy.call_count, 1,
            f'The managed-font query ran {spy.call_count} times in one request. '
            'get_available_fonts() must stay memoised per request — each call is '
            'BEGIN/SELECT/COMMIT, i.e. three round trips on PostgreSQL.',
        )

    @override_settings(DEBUG=True)
    def test_a_page_render_stays_within_a_sane_query_budget(self):
        from django.db import connection, reset_queries

        self.client.get(reverse('options_view'))  # warm caches
        reset_queries()
        response = self.client.get(reverse('options_view'))
        count = len(connection.queries)

        self.assertEqual(response.status_code, 200)
        self.assertLess(
            count, 120,
            f'The Options page issued {count} queries. Before the render-cost fix '
            'it issued well over 800, almost all of them the same font lookup.',
        )


class FontMemoInvalidationTests(TestCase):
    """The memo must never outlive a change to what it caches."""

    def test_a_managed_font_write_is_visible_immediately(self):
        from dlux.fonts import clear_font_cache, get_available_fonts, _build_available_fonts
        from dlux.models import ManagedAsset, ManagedFontFamily, ManagedFontVariant

        clear_font_cache()
        get_available_fonts()  # fill the memo

        family = ManagedFontFamily.objects.create(
            slug='memo-probe', family='MemoProbe', label='Memo Probe')
        asset = ManagedAsset.objects.create(
            title='probe', slug='memo-probe-woff', kind='font',
            file='fonts/memo-probe.woff2', is_active=True)
        ManagedFontVariant.objects.create(font=family, asset=asset, weight=400, style='normal')

        self.assertEqual(
            {f['slug'] for f in get_available_fonts()},
            {f['slug'] for f in _build_available_fonts()},
            'The memo served a stale list after a managed-font write.',
        )

    @override_settings(DLUX_CUSTOM_FONTS=[{
        'slug': 'memo_custom', 'family': 'Memo Custom', 'label': 'Memo Custom',
        'variants': [{'weight': 400, 'path': 'memo/custom.woff2'}],
    }])
    def test_a_settings_override_invalidates_the_memo(self):
        from dlux.fonts import get_available_fonts

        self.assertIn('memo_custom', [f['slug'] for f in get_available_fonts()])
