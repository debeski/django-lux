from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from dlux.models import ActivityLog
from dlux.ribbon import RibbonTab, RibbonTabs, build_ribbon_tabs

User = get_user_model()


def _request(query=None):
    return RequestFactory().get('/logs/', query or {})


class TabSourceTests(TestCase):
    """A strip is built from sources, so one list can split more than one way."""

    def test_a_field_with_choices_gives_one_tab_each(self):
        tabs = build_ribbon_tabs(
            {'param': 'category', 'sources': [{'type': 'field', 'field': 'category'}]},
            model=ActivityLog, request=_request(), strings={},
        )
        keys = [tab.key for tab in tabs]
        self.assertEqual(keys, [str(v) for v, _l in ActivityLog._meta.get_field('category').choices])

    def test_a_field_tab_carries_its_own_lookup(self):
        tabs = build_ribbon_tabs(
            {'sources': [{'type': 'field', 'field': 'category'}]},
            model=ActivityLog, request=_request(), strings={},
        )
        self.assertEqual(tabs.items[0].lookup, {'category': tabs.items[0].key})

    def test_an_all_tab_has_no_key_and_no_lookup(self):
        tabs = build_ribbon_tabs(
            {'sources': [{'type': 'all'}, {'type': 'field', 'field': 'category'}]},
            model=ActivityLog, request=_request(), strings={'ui_all': 'All'},
        )
        self.assertTrue(tabs.items[0].is_all)
        self.assertIsNone(tabs.items[0].lookup)
        self.assertEqual(tabs.items[0].label, 'All')

    def test_a_flag_source_shows_the_rows_where_it_is_true(self):
        tabs = build_ribbon_tabs(
            {'sources': [{'type': 'flag', 'field': 'is_superuser'}]},
            model=User, request=_request(), strings={},
        )
        self.assertEqual(tabs.items[0].key, 'is_superuser')
        self.assertEqual(tabs.items[0].lookup, {'is_superuser': True})

    def test_one_strip_mixes_a_relation_and_flags(self):
        """The case that shaped the design: a field populating the tabs
        alongside booleans, all in one strip."""
        from django.contrib.auth.models import Group

        Group.objects.create(name='Editors')
        tabs = build_ribbon_tabs(
            {
                'param': 'tab',
                'sources': [
                    {'type': 'all'},
                    {'type': 'field', 'field': 'groups'},
                    {'type': 'flag', 'field': 'is_superuser', 'label': 'Superusers'},
                    {'type': 'flag', 'field': 'is_active', 'label': 'Active'},
                ],
            },
            model=User, request=_request(), strings={'ui_all': 'All'},
        )
        labels = [t.label for t in tabs]
        self.assertEqual(labels[0], 'All')
        self.assertIn('Editors', labels)
        self.assertIn('Superusers', labels)
        self.assertIn('Active', labels)
        # Every tab answers to a distinct URL.
        self.assertEqual(len({t.key for t in tabs}), len(tabs.items))

    def test_mixed_sources_keep_their_own_lookups(self):
        """A flag narrows to True while a field narrows to its value — the two
        must not be conflated just because they share a strip."""
        from django.contrib.auth.models import Group

        group = Group.objects.create(name='Editors')
        tabs = build_ribbon_tabs(
            {'param': 'tab', 'sources': [
                {'type': 'field', 'field': 'groups'},
                {'type': 'flag', 'field': 'is_superuser'},
            ]},
            model=User, request=_request(), strings={},
        )
        by_key = {t.key: t.lookup for t in tabs}
        self.assertEqual(by_key[str(group.pk)], {'groups': group.pk})
        self.assertEqual(by_key['is_superuser'], {'is_superuser': True})

    def test_a_relation_makes_one_tab_per_row(self):
        from django.contrib.auth.models import Group

        Group.objects.create(name='Warehouse A')
        Group.objects.create(name='Warehouse B')
        tabs = build_ribbon_tabs(
            {'sources': [{'type': 'field', 'field': 'groups'}]},
            model=User, request=_request(), strings={},
        )
        self.assertEqual(sorted(t.label for t in tabs), ['Warehouse A', 'Warehouse B'])

    def test_a_plain_field_is_refused_with_a_reason(self):
        with self.assertRaises(ValueError) as caught:
            build_ribbon_tabs(
                {'sources': [{'type': 'field', 'field': 'username'}]},
                model=User, request=_request(), strings={},
            )
        self.assertIn('neither choices nor a relation', str(caught.exception))

    def test_duplicate_keys_fail_loudly(self):
        """Two tabs answering to one URL means the second is unreachable."""
        with self.assertRaises(ValueError) as caught:
            build_ribbon_tabs(
                {'sources': [
                    {'type': 'flag', 'field': 'is_active'},
                    {'type': 'flag', 'field': 'is_active'},
                ]},
                model=User, request=_request(), strings={},
            )
        self.assertIn('duplicate key', str(caught.exception))

    def test_a_view_can_hand_the_items_in(self):
        """The escape hatch: a strip no source expresses."""
        tabs = build_ribbon_tabs(
            {'param': 'model', 'items': [
                {'key': 'fiscalyear', 'label': 'Fiscal Years'},
                RibbonTab(key='warehouse', label='Warehouses'),
            ]},
            request=_request(), strings={},
        )
        self.assertEqual([t.label for t in tabs], ['Fiscal Years', 'Warehouses'])


class ActiveTabTests(TestCase):
    def _tabs(self, query):
        return build_ribbon_tabs(
            {'param': 'category', 'sources': [{'type': 'all'}, {'type': 'field', 'field': 'category'}]},
            model=ActivityLog, request=_request(query), strings={'ui_all': 'All'},
        )

    def test_the_requested_tab_is_active(self):
        key = ActivityLog._meta.get_field('category').choices[0][0]
        tabs = self._tabs({'category': key})
        self.assertEqual(tabs.active, str(key))
        self.assertTrue(tabs.active_tab.active)

    def test_an_unknown_value_falls_back_to_all(self):
        """A stale bookmark should show everything, not an empty page."""
        self.assertEqual(self._tabs({'category': 'nonsense'}).active, '')

    def test_no_value_means_all(self):
        self.assertEqual(self._tabs({}).active, '')


class TabUrlTests(TestCase):
    def _tabs(self, query):
        return build_ribbon_tabs(
            {'param': 'category', 'sources': [{'type': 'all'}, {'type': 'field', 'field': 'category'}]},
            model=ActivityLog, request=_request(query), strings={'ui_all': 'All'},
        )

    def test_a_tab_keeps_the_filters_it_was_reached_with(self):
        """A tab is not a filter, so switching one must not clear the other."""
        tabs = self._tabs({'keyword': 'ali'})
        for tab in tabs:
            self.assertIn('keyword=ali', tab.url)

    def test_a_tab_drops_the_page(self):
        tabs = self._tabs({'page': '4'})
        for tab in tabs:
            self.assertNotIn('page=4', tab.url)

    def test_the_all_tab_removes_the_param(self):
        key = str(ActivityLog._meta.get_field('category').choices[0][0])
        tabs = self._tabs({'category': key})
        self.assertNotIn('category=', tabs.items[0].url)

    def test_drop_clears_a_dependent_key(self):
        """A sub-tab is meaningless once its parent changes."""
        tabs = build_ribbon_tabs(
            {'param': 'category', 'drop': ('zone',),
             'sources': [{'type': 'field', 'field': 'category'}]},
            model=ActivityLog, request=_request({'zone': '3'}), strings={},
        )
        self.assertNotIn('zone=3', tabs.items[0].url)


class NarrowTests(TestCase):
    """The strip knows its own lookup, so a view gets the filtering for free."""

    def setUp(self):
        self.admin = User.objects.create_superuser('root', 'r@e.com', 'pw')
        for category, n in (('user', 2), ('system', 3)):
            for i in range(n):
                ActivityLog.objects.create(created_by=self.admin, action='t',
                                           category=category, model_name=f'M{i}')

    def _tabs(self, query):
        return build_ribbon_tabs(
            {'param': 'category', 'sources': [{'type': 'all'}, {'type': 'field', 'field': 'category'}]},
            model=ActivityLog, request=_request(query), strings={'ui_all': 'All'},
        )

    def test_the_active_tab_narrows_the_queryset(self):
        self.assertEqual(self._tabs({'category': 'system'}).narrow(ActivityLog.objects.all()).count(), 3)
        self.assertEqual(self._tabs({'category': 'user'}).narrow(ActivityLog.objects.all()).count(), 2)

    def test_all_narrows_nothing(self):
        self.assertEqual(self._tabs({}).narrow(ActivityLog.objects.all()).count(), 5)

    def test_a_flag_tab_narrows_to_true(self):
        User.objects.create_user('plain', password='x')
        tabs = build_ribbon_tabs(
            {'param': 'tab', 'sources': [{'type': 'flag', 'field': 'is_superuser'}]},
            model=User, request=_request({'tab': 'is_superuser'}), strings={},
        )
        self.assertEqual(tabs.narrow(User.objects.all()).count(), 1)


class ChildStripScopeTests(TestCase):
    def setUp(self):
        from django.contrib.auth.models import Group
        from django.core.cache import cache

        from dlux.models import SystemSettings

        cache.clear()
        settings = SystemSettings.load()
        settings.is_configured = True
        settings.ribbon_config = {}
        settings.save()

        self.editors = Group.objects.create(name='Editors')
        self.reviewers = Group.objects.create(name='Reviewers')
        self.live = User.objects.create_user('live', 'l@x.com', 'pw', is_active=True)
        self.gone = User.objects.create_user('gone', 'g@x.com', 'pw', is_active=False)
        self.live.groups.add(self.editors)
        self.gone.groups.add(self.reviewers)

    def _view(self, query, *, ribbon_tabs, model=User):
        from django.views.generic import ListView

        from dlux.ribbon import RibbonMixin

        cls = type('View', (RibbonMixin, ListView), {
            'model': model,
            'ribbon_tabs': ribbon_tabs,
        })
        view = cls()
        view.request = _request(query)
        return view

    def _state_strip(self):
        return {
            'param': 'state',
            'sources': [
                {'type': 'static', 'key': 'live', 'label': 'Live',
                 'lookup': {'is_active': True}},
                {'type': 'static', 'key': 'gone', 'label': 'Gone',
                 'lookup': {'is_active': False}},
            ],
        }

    def _group_child_strip(self):
        return {
            'param': 'group',
            'relation': 'child',
            'sources': [{'type': 'all'}, {'type': 'field', 'field': 'groups'}],
        }

    def test_a_child_strip_shows_only_tabs_with_rows_under_the_active_parent(self):
        view = self._view(
            {'state': 'live'},
            ribbon_tabs=[self._state_strip(), self._group_child_strip()],
        )

        child = view.visible_ribbon_strips()[1]

        self.assertEqual([tab.key for tab in child], ['', str(self.editors.pk)])

    def test_a_stale_child_value_does_not_empty_the_parent_tab(self):
        view = self._view(
            {'state': 'live', 'group': str(self.reviewers.pk)},
            ribbon_tabs=[self._state_strip(), self._group_child_strip()],
        )

        child = view.visible_ribbon_strips()[1]

        self.assertEqual(child.active, '')
        self.assertEqual(list(view.get_queryset()), [self.live])

    def test_a_child_default_scoped_out_by_the_parent_falls_back(self):
        child_config = self._group_child_strip()
        child_config['default'] = str(self.reviewers.pk)
        view = self._view(
            {'state': 'live'},
            ribbon_tabs=[self._state_strip(), child_config],
        )

        child = view.visible_ribbon_strips()[1]

        self.assertEqual(child.active, '')

    def test_a_child_strip_with_no_specific_tabs_under_the_parent_drops_out(self):
        no_group = User.objects.create_user('no-group', 'n@x.com', 'pw', is_active=True)
        view = self._view(
            {'state': 'solo'},
            ribbon_tabs=[
                {
                    'param': 'state',
                    'sources': [
                        {'type': 'static', 'key': 'solo', 'label': 'Solo',
                         'lookup': {'pk': no_group.pk}},
                    ],
                },
                self._group_child_strip(),
            ],
        )

        self.assertEqual([strip.param for strip in view.visible_ribbon_strips()], ['state'])

    def test_an_admin_made_child_strip_is_scoped_to_the_declared_parent(self):
        from dlux.models import SystemSettings

        settings = SystemSettings.load()
        settings.ribbon_config = {
            'auth.User': {'extra_strips': [self._group_child_strip()]},
        }
        settings.save()

        view = self._view({'state': 'gone'}, ribbon_tabs=self._state_strip())

        child = view.visible_ribbon_strips()[1]
        self.assertEqual([tab.key for tab in child], ['', str(self.reviewers.pk)])

    def test_child_choice_tabs_are_scoped_to_the_active_parent(self):
        ActivityLog.objects.create(
            created_by=self.live, action='t', category=ActivityLog.CATEGORY_USER,
            model_key='parties', model_name='Parties',
        )
        ActivityLog.objects.create(
            created_by=self.gone, action='t', category=ActivityLog.CATEGORY_SYSTEM,
            model_key='assets', model_name='Assets',
        )
        view = self._view(
            {'subject': 'parties'},
            ribbon_tabs=[
                {
                    'param': 'subject',
                    'sources': [
                        {'type': 'static', 'key': 'parties', 'label': 'Parties',
                         'lookup': {'model_key': 'parties'}},
                        {'type': 'static', 'key': 'assets', 'label': 'Assets',
                         'lookup': {'model_key': 'assets'}},
                    ],
                },
                {
                    'param': 'category',
                    'relation': 'child',
                    'sources': [{'type': 'all'}, {'type': 'field', 'field': 'category'}],
                },
            ],
            model=ActivityLog,
        )

        child = view.visible_ribbon_strips()[1]
        self.assertEqual([tab.key for tab in child], ['', ActivityLog.CATEGORY_USER])


class CountTests(TestCase):
    def test_counts_are_attached_when_the_view_supplies_them(self):
        tabs = build_ribbon_tabs(
            {'param': 'category', 'sources': [{'type': 'field', 'field': 'category'}]},
            model=ActivityLog, request=_request(), strings={},
            counts={'user': 7},
        )
        by_key = {t.key: t.count for t in tabs}
        self.assertEqual(by_key.get('user'), 7)

    def test_a_tab_with_no_rows_reads_zero(self):
        """Supplying counts means badges are wanted; a missing badge is an
        absence the reader has to interpret, while 0 is a fact."""
        tabs = build_ribbon_tabs(
            {'param': 'category', 'sources': [{'type': 'field', 'field': 'category'}]},
            model=ActivityLog, request=_request(), strings={},
            counts={'user': 7},
        )
        by_key = {t.key: t.count for t in tabs}
        self.assertEqual(by_key.get('system'), 0)

    def test_no_counts_means_no_badges(self):
        tabs = build_ribbon_tabs(
            {'param': 'category', 'sources': [{'type': 'field', 'field': 'category'}]},
            model=ActivityLog, request=_request(), strings={},
        )
        self.assertTrue(all(t.count is None for t in tabs))


class TabSeparatorTests(TestCase):
    """One rule, under the title.

    The title says what the page is; the tabs and the filters both say which
    records. So the boundary is under the heading — with the rule below the
    strip instead, the tabs read as an appendage of the filter row and nothing
    divided them from the title at all.
    """

    def _rules(self):
        import re
        from pathlib import Path as P

        css = (P(__file__).resolve().parents[1]
               / 'static' / 'dlux' / 'ribbon' / 'css' / 'ribbon.css').read_text()

        def block(selector):
            """The declarations of the rule `selector` belongs to.

            Found by selector rather than by the literal text up to the brace:
            a selector may be grouped with others on the same rule, and reading
            the block only when it happens to be alone made these fail on a
            grouping that changed nothing about what they assert.
            """
            at = css.index(selector)
            body = css[css.index('{', at) + 1:]
            return body[:body.index('}')]

        return {
            'tabs': block('.dlux-ribbon-header-row + .dlux-ribbon-strips'),
            'filters_after_tabs': block('.dlux-ribbon-strips + .dlux-ribbon-filter'),
            # The filter block carries the rule by default; the adjacency rule
            # above only takes it away again when a strip precedes it.
            'filters_default': block('\n.dlux-ribbon-filter {'),
        }

    def test_the_strip_carries_the_rule(self):
        self.assertIn('border-block-start: 1px', self._rules()['tabs'])

    def test_the_filters_are_not_divided_from_the_tabs(self):
        """Two rules in one header would split a zone that is one thing."""
        self.assertIn('border-block-start: 0', self._rules()['filters_after_tabs'])

    def test_a_page_without_tabs_still_divides_title_from_filters(self):
        self.assertIn('border-block-start: 1px', self._rules()['filters_default'])

    def test_the_strip_is_not_flush_against_the_title(self):
        rules = self._rules()['tabs']
        self.assertIn('margin-block-start', rules)
        self.assertIn('padding-block-start', rules)


class ConfiguredTabsTests(TestCase):
    """A strip drawn in Settings reaches the page without a developer."""

    def setUp(self):
        from django.core.cache import cache

        from dlux.models import SystemSettings

        # `SystemSettings.load()` is cached and `save()` refreshes that cache,
        # so production always sees a saved change. The cache is not rolled back
        # with the test transaction, though, so one test's stored strip would
        # otherwise be read by the next.
        cache.clear()
        self.settings = SystemSettings.load()
        self.settings.is_configured = True
        self.settings.save()

    def _store(self, config):
        self.settings.ribbon_config = config
        self.settings.save()

    def test_a_stored_strip_is_found_for_its_model(self):
        from dlux.ribbon import configured_tabs_for

        self._store({'dlux.ActivityLog': {'extra_strips': [{
            'param': 'category',
            'sources': [{'type': 'field', 'field': 'category'}],
        }]}})
        found = configured_tabs_for(ActivityLog)
        self.assertEqual(found['param'], 'category')
        self.assertEqual(found['sources'][0]['field'], 'category')

    def test_another_model_gets_nothing(self):
        from dlux.ribbon import configured_tabs_for

        self._store({'dlux.ActivityLog': {'extra_strips': [{'sources': [{'type': 'all'}]}]}})
        self.assertIsNone(configured_tabs_for(User))

    def test_a_malformed_strip_is_dropped_not_raised(self):
        """This JSON is edited by a builder, imported, and hand-patched. A bad
        strip must fall out here rather than raise on a list page."""
        from dlux.ribbon import configured_tabs_for

        self._store({
            'dlux.ActivityLog': {'extra_strips': [
                {'sources': [{'type': 'nonsense'}, {'type': 'flag'}]},
            ]},
        })
        self.assertIsNone(configured_tabs_for(ActivityLog))

    def test_a_declared_strip_wins_over_a_stored_one(self):
        """A setting quietly overriding a developer's declaration is the kind of
        surprise that costs an hour to find."""
        from dlux.ribbon import RibbonMixin

        self._store({'dlux.ActivityLog': {'extra_strips': [
            {'param': 'stored', 'sources': [{'type': 'all'}]},
        ]}})

        class View(RibbonMixin):
            model = ActivityLog
            ribbon_tabs_fixed = {'param': 'declared', 'sources': [{'type': 'all'}]}

            def __init__(self):
                self.request = _request()

        self.assertEqual(View().get_ribbon_tabs().param, 'declared')

    def test_a_view_with_no_declaration_uses_the_stored_strip(self):
        from dlux.ribbon import RibbonMixin

        self._store({'dlux.ActivityLog': {'extra_strips': [{
            'param': 'stored', 'sources': [{'type': 'field', 'field': 'category'}],
        }]}})

        class View(RibbonMixin):
            model = ActivityLog

            def __init__(self):
                self.request = _request()

        self.assertEqual(View().get_ribbon_tabs().param, 'stored')

    def test_unreadable_settings_leave_the_page_renderable(self):
        """No strip is a worse page; an exception is a broken one."""
        from unittest.mock import patch

        from dlux.ribbon import configured_tabs_for

        with patch('dlux.models.SystemSettings.load', side_effect=RuntimeError('mid-migration')):
            self.assertIsNone(configured_tabs_for(ActivityLog))

    def test_custom_actions_are_scoped_to_the_ribbon_host(self):
        from dlux.ribbon import configured_custom_actions_for

        self._store({'dlux.ActivityLog': {'custom_actions': {
            '*': [{'id': 'global', 'label': 'Global', 'url': '/global/'}],
            'logs:list': [{'id': 'logs', 'label': 'Logs', 'url': '/logs/'}],
            'logs:other': [{'id': 'other', 'label': 'Other', 'url': '/other/'}],
        }}})
        actions = configured_custom_actions_for(ActivityLog, 'logs:list')
        self.assertEqual([action['id'] for action in actions], ['global', 'logs'])

    def test_custom_actions_render_after_developer_actions(self):
        from types import SimpleNamespace

        from dlux.ribbon import RibbonMixin, build_action

        self._store({'dlux.ActivityLog': {'custom_actions': {
            'logs:list': [{'id': 'custom', 'labels': {'en': 'Custom'}, 'url': '/custom/'}],
        }}})

        class View(RibbonMixin):
            model = ActivityLog

            def __init__(self):
                self.request = _request()
                self.request.resolver_match = SimpleNamespace(view_name='logs:list')

            def get_ribbon_actions(self):
                return [build_action({'label': 'Developer', 'url': '/developer/'}, request=self.request)]

        ribbon = View().get_ribbon()
        self.assertEqual([action.label for action in ribbon.actions], ['Developer', 'Custom'])

    def test_custom_action_permission_is_enforced_on_render(self):
        from types import SimpleNamespace

        from dlux.ribbon import RibbonMixin

        self._store({'dlux.ActivityLog': {'custom_actions': {
            'logs:list': [{
                'id': 'restricted',
                'label': 'Restricted',
                'url': '/restricted/',
                'permission': 'dlux.view_activitylog',
            }],
        }}})

        class View(RibbonMixin):
            model = ActivityLog

            def __init__(self):
                self.request = _request()
                self.request.resolver_match = SimpleNamespace(view_name='logs:list')
                self.request.user = SimpleNamespace(has_perm=lambda perm: False)

        self.assertEqual(View().get_ribbon().actions, [])


class TabCatalogTests(TestCase):
    """Two guards: a host must be a view that renders a ribbon, and only fields
    that can actually become tabs are listed."""

    def _catalog(self):
        from dlux.ribbon.catalog import ribbon_tab_catalog

        return {entry['key']: entry for entry in ribbon_tab_catalog()}

    def _user_host(self):
        return next(
            entry for entry in self._catalog().values()
            if entry['model_key'] == 'auth.User'
        )

    def test_only_views_that_host_a_ribbon_are_offered(self):
        """Reading the model registry instead offered every table in the
        project — sessions, permissions, log entries — none of which have a
        page, let alone a ribbon."""
        from django.apps import apps as django_apps

        catalog = self._catalog()
        self.assertIn('manage_users', catalog)
        self.assertEqual(catalog['manage_users']['model_key'], 'auth.User')
        self.assertLess(len(catalog), len(django_apps.get_models()))
        model_keys = {entry['model_key'] for entry in catalog.values()}
        for absent in ('auth.Permission', 'sessions.Session', 'dlux.SystemSettings',
                       'contenttypes.ContentType', 'dlux.UserPresenceSession'):
            self.assertNotIn(absent, model_keys)

    def test_a_view_that_locks_its_tabs_is_listed_without_structural_actions(self):
        """It used to be dropped from the catalog entirely, which left the page
        with no presence in Settings at all. Now it is offered so its tabs can be
        reordered and renamed; extra strips are withheld because the primary
        strip is fixed by code.
        """
        from dlux.ribbon.catalog import ribbon_view_models

        views = ribbon_view_models()
        self.assertTrue(views['dlux.ActivityLog'][1], 'activity log locks its tabs')
        entry = self._catalog().get('user_activity_log')
        self.assertIsNotNone(entry, 'a locked ribbon host still belongs in the catalog')
        self.assertTrue(entry['locked'])
        self.assertIn('strips', entry)

    def test_dynamically_built_fixed_strips_are_serialized(self):
        """Activity Log builds its category strip from permissions and counts.
        The builder still needs that final strip; treating it as raw config made
        the fixed badge show without the strip itself.
        """
        from dlux.ribbon.catalog import ribbon_tab_catalog

        request = _request()
        request.user = User.objects.create_superuser('root', 'root@example.com', 'pw')
        catalog = {entry['key']: entry for entry in ribbon_tab_catalog(request=request)}
        entry = catalog['user_activity_log']
        self.assertEqual([strip['param'] for strip in entry['strips']], ['category'])
        self.assertTrue(entry['strips'][0]['tabs'])

    def test_audit_relations_are_not_offered_as_tabs(self):
        """dlux stamps these on every scoped model; each would draw one tab per
        user, and they are bookkeeping rather than a dimension anyone lists by."""
        fields = {f['name'] for f in self._user_host()['fields']}
        for noise in ('created_by', 'updated_by', 'deleted_by', 'user_permissions'):
            self.assertNotIn(noise, fields)

    def test_a_broken_urlconf_does_not_take_settings_down(self):
        from unittest.mock import patch

        from dlux.ribbon.catalog import ribbon_view_models

        with patch('dlux.ribbon.catalog.get_resolver', side_effect=RuntimeError('boom')):
            self.assertEqual(ribbon_view_models(), {})

    def test_a_choices_field_is_classified_as_a_field_source(self):
        """Tested on the classifier: the only model in dlux's own catalog is
        `auth.User`, which has no choices field of its own."""
        from dlux.ribbon.catalog import _source_kind

        self.assertEqual(_source_kind(ActivityLog._meta.get_field('category')), 'field')

    def test_a_boolean_is_offered_as_a_flag_source(self):
        fields = {f['name']: f['kind'] for f in self._user_host()['fields']}
        self.assertEqual(fields.get('is_superuser'), 'flag')

    def test_a_free_text_field_is_not_offered(self):
        """Offering it would let an operator draw a strip that raises on render."""
        fields = {f['name'] for f in self._user_host()['fields']}
        self.assertNotIn('username', fields)

    def test_a_ribbon_host_without_declared_strips_is_kept(self):
        entry = self._catalog()['manage_users']
        self.assertEqual(entry['route_name'], 'manage_users')
        self.assertEqual(entry['strips'], [])

    def test_explicit_function_ribbon_hosts_are_kept(self):
        catalog = self._catalog()
        self.assertEqual(catalog['reports_overview']['model_key'], 'route.reports_overview')
        self.assertEqual(catalog['system_backup_page']['model_key'], 'route.system_backup_page')
        self.assertTrue(catalog['reports_overview']['locked'])
        self.assertTrue(catalog['system_backup_page']['locked'])

    def test_catalog_marks_developer_actions_as_locked(self):
        entry = self._catalog()['manage_users']
        self.assertTrue(entry['actions_locked'])
        self.assertTrue(entry['actions_dynamic'])


class RibbonDestinationCatalogTests(TestCase):
    def _catalog(self):
        from dlux.ribbon.catalog import ribbon_destination_catalog

        return {entry['id']: entry for entry in ribbon_destination_catalog()}

    def test_page_form_and_modal_destinations_are_catalogued(self):
        catalog = self._catalog()
        self.assertEqual(catalog['manage_users']['kind'], 'page')
        self.assertTrue(catalog['manage_users']['is_system'])

    def test_only_pages_an_admin_can_navigate_to_are_offered(self):
        """The catalog walks the URLconf itself, so it must apply the discovery
        profile by hand — a raw walk offers every named route.

        Before this, the destination dropdown listed sign-up and session pages,
        settings import/export endpoints, backup and restore starters, and
        `global_search`, which answers with JSON. None of them are somewhere a
        ribbon button can meaningfully send a reader.
        """
        catalog = self._catalog()

        for route_name in (
            'register',
            'session_ended',
            'global_search',
            'system_settings_export',
            'system_restore_start',
            'reports_backup_start',
        ):
            self.assertNotIn(route_name, catalog, route_name)

        # What dlux owns out of the hidden group: the configurable system pages the
        # sidebar offers, every dynamic-modal manager, and the named managers worth
        # opening from a button. All of it reads as System in the picker; a project's
        # own destinations never do.
        from dlux.discovery.meta import CONFIGURABLE_SYSTEM_ROUTE_NAMES

        offered_system = {name for name, entry in catalog.items() if entry['is_system']}
        self.assertTrue(
            (set(CONFIGURABLE_SYSTEM_ROUTE_NAMES) & set(catalog)).issubset(offered_system))
        self.assertTrue(all(':' not in name for name in offered_system))
        self.assertIn('manage_users', catalog)
        self.assertIn('reports_overview', catalog)

    def test_a_json_answering_manager_is_a_modal_destination_not_a_page(self):
        """Group, Scope and Asset management answer `{"html": ...}`; they are not
        pages. Offered as pages, a button pointing at one navigated to raw JSON —
        and they are modals, so they are destinations without being sidebar
        material."""
        catalog = self._catalog()
        from dlux.discovery.meta import CONFIGURABLE_SYSTEM_ROUTE_NAMES

        for route_name in ('manage_groups', 'manage_scopes', 'manage_assets'):
            entry = catalog[route_name]
            self.assertEqual(entry['kind'], 'modal', route_name)
            # Opened as a dynamic modal, not navigated to.
            self.assertIn('attrs', entry['action_spec'], route_name)
            self.assertTrue(entry['is_system'], route_name)
            self.assertNotIn(route_name, CONFIGURABLE_SYSTEM_ROUTE_NAMES, route_name)

    def test_a_modal_manager_dlux_owns_is_labelled_system_like_its_pages(self):
        """`modal_user` is dlux's, so it reads as System — it used to sit among the
        project's own destinations while User Management hid behind the toggle."""
        catalog = self._catalog()
        self.assertTrue(catalog['modal_user']['is_system'])
        # And it says what it is rather than a humanised route name.
        self.assertNotEqual(catalog['modal_user']['label'], 'Modal User')

    def test_a_view_may_opt_out_of_navigation_yet_stay_a_destination(self):
        """`sidebar_exclude = True` means every profile, which took the ScanLink
        releases modal out of the destination picker too. Naming the navigation
        profiles keeps it out of those and available here."""
        from dlux.views.scanlink import scanlink_releases_modal

        excluded = set(scanlink_releases_modal.dlux_exclude)
        self.assertIn('sidebar', excluded)
        self.assertIn('navbar', excluded)
        self.assertNotIn('ribbon_destination', excluded)

    def test_dynamic_modal_managers_are_offered_whoever_registered_them(self):
        """They land in the hidden `dlux` group by grouping accident, and a button
        opening one is exactly the point — dlux's own included."""
        catalog = self._catalog()
        self.assertEqual(catalog['modal_user']['kind'], 'modal')
        self.assertEqual(catalog['modal_user']['group_key'], 'dlux')

    def test_context_bound_routes_are_left_out(self):
        catalog = self._catalog()
        self.assertNotIn('user_detail_modal', catalog)
        self.assertNotIn('modal_user_edit', catalog)

    def test_mutating_page_endpoints_are_left_out(self):
        catalog = self._catalog()
        self.assertNotIn('dlux_data_reset_execute', catalog)

    def test_modal_destination_carries_a_renderable_action_spec(self):
        # Exercised directly: dlux ships no namespaced modal of its own, and its own
        # modals are no longer offered as destinations.
        from dlux.ribbon.catalog import _destination_action_spec

        spec = _destination_action_spec(
            {'url_name': 'shop:order_manager', 'url': '/shop/orders/manage/',
             'label': 'Orders', 'icon': 'bi-box', 'permissions': []},
            'modal',
        )
        self.assertEqual(spec['attrs']['data-dynamic-modal'], '/shop/orders/manage/')
        self.assertEqual(spec['destination']['kind'], 'modal')


class RibbonStepTests(TestCase):
    """The ribbon has its own settings step: it outgrew a section in Layout once
    it gained a builder, which is why the sidebar and navbar have theirs."""

    def _form_html(self):
        from django.template import Context, Template

        from dlux.forms.system_settings import SystemSettingsForm
        from dlux.models import SystemSettings

        form = SystemSettingsForm(instance=SystemSettings(is_configured=False), mode='setup')
        return Template('{% load crispy_forms_tags %}{% crispy form %}').render(Context({'form': form}))

    def test_the_step_exists_and_is_counted(self):
        from dlux.system.constants import SETUP_STEP_COUNT, SETUP_STEP_RIBBON, SETUP_STEPS

        # It used to be pinned to the last position because it was appended
        # there. What matters is that it is a step like any other.
        self.assertIn('ribbon', [slug for slug, _icon, _keywords in SETUP_STEPS])
        self.assertIn(SETUP_STEP_RIBBON, range(SETUP_STEP_COUNT))

    def test_the_step_carries_the_builder_and_its_field(self):
        html = self._form_html()
        self.assertIn('data-ribbon-builder', html)
        self.assertIn('name="ribbon_config"', html)
        self.assertIn('data-destinations=', html)

    def test_the_config_is_normalised_on_the_way_in(self):
        """The failure belongs in the editor that caused it, not on a list page
        days later."""
        from dlux.forms.system_settings import SystemSettingsForm
        from dlux.models import SystemSettings

        form = SystemSettingsForm(instance=SystemSettings(is_configured=False), mode='modal')
        form.cleaned_data = {'ribbon_config': {
            'dlux.ActivityLog': {'extra_strips': [
                {'sources': [{'type': 'field', 'field': 'category'}]},
            ]},
            'broken': {'extra_strips': [{'sources': [{'type': 'nope'}]}]},
        }}
        cleaned = form.clean_ribbon_config()
        self.assertIn('dlux.ActivityLog', cleaned)
        self.assertNotIn('broken', cleaned)

    def test_the_config_travels_with_the_other_settings(self):
        from dlux.system.constants import SYSTEM_SETTINGS_EXPORT_FIELDS

        self.assertIn('ribbon_config', SYSTEM_SETTINGS_EXPORT_FIELDS)

    def test_the_registry_knows_the_field(self):
        """Every `*_config` JSON field needs a schema group, a default and a
        normalizer, or import and bootstrap skip it."""
        from dlux.system.registry import (
            build_default_system_config, get_config_default_factory, get_config_normalizers,
        )

        self.assertIn('ribbon_config', build_default_system_config())
        self.assertTrue(callable(get_config_default_factory('ribbon_config')))
        self.assertTrue(callable(get_config_normalizers()['ribbon_config']))


class SourceScopeTests(TestCase):
    """A strip is often a split *within* a scope, not over the whole table."""

    def test_a_source_lookup_rides_on_every_tab_it_makes(self):
        from django.contrib.auth.models import Group

        group = Group.objects.create(name='Warehouse A')
        tabs = build_ribbon_tabs({
            'param': 'group',
            'sources': [
                {'type': 'all', 'lookup': {'is_active': True}},
                {'type': 'field', 'field': 'groups', 'lookup': {'is_active': True}},
                {'type': 'static', 'key': 'retired', 'label': 'Retired',
                 'lookup': {'is_active': False}},
            ],
        }, model=User, request=_request(), strings={'ui_all': 'All'})
        by_key = {tab.key: tab.lookup for tab in tabs.items}
        self.assertEqual(by_key[''], {'is_active': True})
        self.assertEqual(by_key['retired'], {'is_active': False})
        self.assertEqual(by_key[str(group.pk)], {'is_active': True, 'groups': group.pk})

    def test_a_tab_may_escape_the_scope_its_neighbours_share(self):
        """The reason the scope cannot just live in the view's get_queryset():
        narrowing is additive, so a tab that must step outside the scope — the
        retired one — could never do it from there."""
        tabs = build_ribbon_tabs({
            'param': 'group',
            'sources': [
                {'type': 'all', 'lookup': {'is_active': True}},
                {'type': 'static', 'key': 'retired', 'label': 'Retired',
                 'lookup': {'is_active': False}},
            ],
        }, model=User, request=_request({'group': 'retired'}), strings={'ui_all': 'All'})
        self.assertEqual(tabs.active, 'retired')
        self.assertEqual(tabs.active_tab.lookup, {'is_active': False})

    def test_a_tab_keeps_its_own_value_when_the_scope_names_the_same_key(self):
        """The tab is the more specific statement, so it wins the merge."""
        tabs = build_ribbon_tabs({
            'param': 'flag',
            'sources': [{'type': 'flag', 'field': 'is_active', 'value': False,
                         'lookup': {'is_active': True}}],
        }, model=User, request=_request(), strings={})
        self.assertEqual(tabs.items[0].lookup, {'is_active': False})

    def test_a_relation_queryset_may_be_built_from_the_request(self):
        """Which rows this reader may pick from is not knowable at import."""
        from django.contrib.auth.models import Group

        Group.objects.create(name='Visible')
        Group.objects.create(name='Hidden')
        seen = []

        def scoped(request):
            seen.append(request)
            return Group.objects.filter(name='Visible')

        request = _request()
        tabs = build_ribbon_tabs({
            'param': 'group',
            'sources': [{'type': 'field', 'field': 'groups', 'queryset': scoped}],
        }, model=User, request=request, strings={})
        self.assertEqual(seen, [request], 'the callable must be given the request')
        self.assertEqual([tab.label for tab in tabs.items], ['Visible'])


class QLookupTests(TestCase):
    """Some conditions are an OR, and no dict can say one."""

    def test_a_tab_may_narrow_by_a_q_object(self):
        from django.db.models import Q

        User.objects.create_user('live', 'l@x.com', 'pw', is_active=True)
        staff = User.objects.create_user('staff', 's@x.com', 'pw', is_active=False)
        staff.is_staff = True
        staff.save(update_fields=['is_staff'])

        tabs = build_ribbon_tabs({
            'param': 'state',
            'default': 'reachable',
            'sources': [{'type': 'static', 'key': 'reachable', 'label': 'Reachable',
                         'lookup': Q(is_active=True) | Q(is_staff=True)}],
        }, model=User, request=_request(), strings={})
        names = set(tabs.narrow(User.objects.all()).values_list('username', flat=True))
        self.assertEqual(names, {'live', 'staff'})

    def test_a_dict_lookup_still_works(self):
        User.objects.create_user('live', 'l@x.com', 'pw', is_active=True)
        User.objects.create_user('gone', 'g@x.com', 'pw', is_active=False)

        tabs = build_ribbon_tabs({
            'param': 'state',
            'default': 'live',
            'sources': [{'type': 'static', 'key': 'live', 'label': 'Live',
                         'lookup': {'is_active': True}}],
        }, model=User, request=_request(), strings={})
        self.assertEqual(
            list(tabs.narrow(User.objects.all()).values_list('username', flat=True)), ['live']
        )


class TraversalTests(TestCase):
    """A strip often splits by something one step away from the listed model."""

    def test_a_source_may_follow_a_relation_path(self):
        """Balances split by the warehouse their *zone* belongs to: the tabs come
        from Warehouse, but the lookup has to read `zone__warehouse`."""
        from django.contrib.auth.models import Group, Permission

        permission = Permission.objects.filter(codename='add_group').first()
        group = Group.objects.create(name='Editors')
        group.permissions.add(permission)
        user = User.objects.create_user('member', 'm@x.com', 'pw')
        user.groups.add(group)

        tabs = build_ribbon_tabs({
            'param': 'permission',
            'sources': [{'type': 'field', 'field': 'groups__permissions',
                         'queryset': lambda request: Permission.objects.filter(
                             pk=permission.pk)}],
        }, model=User, request=_request(), strings={})
        self.assertEqual([tab.key for tab in tabs.items], [str(permission.pk)])
        self.assertEqual(tabs.items[0].lookup, {'groups__permissions': permission.pk})

    def test_the_path_narrows_the_queryset(self):
        from django.contrib.auth.models import Group

        group = Group.objects.create(name='Editors')
        member = User.objects.create_user('member', 'm@x.com', 'pw')
        member.groups.add(group)
        User.objects.create_user('outsider', 'o@x.com', 'pw')

        tabs = build_ribbon_tabs({
            'param': 'group',
            'default': str(group.pk),
            'sources': [{'type': 'field', 'field': 'groups'}],
        }, model=User, request=_request(), strings={})
        self.assertEqual(
            list(tabs.narrow(User.objects.all()).values_list('username', flat=True)),
            ['member'],
        )

    def test_a_non_relation_in_the_middle_of_a_path_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            build_ribbon_tabs({
                'param': 'x',
                'sources': [{'type': 'field', 'field': 'username__groups'}],
            }, model=User, request=_request(), strings={})
        self.assertIn('not a relation', str(caught.exception))


class SourceIconTests(TestCase):
    """One source makes many tabs, so an icon can be per value or shared."""

    def test_icons_maps_a_value_to_its_own_icon(self):
        tabs = build_ribbon_tabs({
            'param': 'cat',
            'sources': [{'type': 'field', 'field': 'category',
                         'icons': {'user': 'bi bi-person', 'system': 'bi bi-gear'}}],
        }, model=ActivityLog, request=_request(), strings={})
        by_key = {tab.key: tab.icon for tab in tabs.items}
        self.assertEqual(by_key.get('user'), 'bi bi-person')
        self.assertEqual(by_key.get('system'), 'bi bi-gear')

    def test_a_bare_icon_covers_every_tab_the_source_makes(self):
        """The builder offers an icon input on a field source; it used to be
        accepted and then dropped, so setting it did nothing at all."""
        tabs = build_ribbon_tabs({
            'param': 'cat',
            'sources': [{'type': 'field', 'field': 'category', 'icon': 'bi bi-tag'}],
        }, model=ActivityLog, request=_request(), strings={})
        self.assertTrue(tabs.items)
        self.assertTrue(all(tab.icon == 'bi bi-tag' for tab in tabs.items))

    def test_a_per_value_icon_beats_the_shared_one(self):
        tabs = build_ribbon_tabs({
            'param': 'cat',
            'sources': [{'type': 'field', 'field': 'category', 'icon': 'bi bi-tag',
                         'icons': {'user': 'bi bi-person'}}],
        }, model=ActivityLog, request=_request(), strings={})
        by_key = {tab.key: tab.icon for tab in tabs.items}
        self.assertEqual(by_key.get('user'), 'bi bi-person')
        others = [v for k, v in by_key.items() if k != 'user']
        self.assertTrue(others and all(v == 'bi bi-tag' for v in others))


class CatalogTests(TestCase):
    """What Settings offers, and what it must never choke on."""

    def _catalog(self):
        from dlux.ribbon.catalog import ribbon_tab_catalog

        return {entry['key']: entry for entry in ribbon_tab_catalog(request=_request())}

    def test_the_catalog_is_json_serialisable(self):
        """It is embedded in the Ribbon step as a data attribute. A declared
        strip may carry a callable queryset or a `Q` lookup — neither survives
        JSON, and serialising one used to take down the whole settings step
        rather than the one source that could not be represented.
        """
        import json

        from dlux.ribbon.catalog import ribbon_tab_catalog

        json.dumps(ribbon_tab_catalog(request=_request()))

    def test_a_locked_model_is_listed_so_its_tabs_can_be_re_dressed(self):
        """It used to be dropped, which left it no presence in Settings at all."""
        from dlux.ribbon.catalog import ribbon_tab_catalog

        entries = ribbon_tab_catalog(request=_request())
        self.assertTrue(entries, 'the catalog should not be empty')
        for entry in entries:
            self.assertIn('locked', entry)
            self.assertIn('strips', entry)

    def test_a_model_splitting_more_than_one_way_offers_every_strip(self):
        """Reading only the first left the pages that split more than one way —
        the ones the builder most needs to reach — with nothing to show."""
        from dlux.ribbon.catalog import _declared_strips

        strips = _declared_strips(
            [
                {'param': 'a', 'sources': [{'type': 'all'}]},
                {'param': 'b', 'relation': 'child', 'sources': [{'type': 'all'}]},
                {'param': 'c', 'relation': 'axis', 'sources': [{'type': 'all'}]},
            ],
            ActivityLog, _request(),
        )
        self.assertEqual([s['param'] for s in strips], ['a', 'b', 'c'])
        self.assertEqual([s['relation'] for s in strips], ['primary', 'child', 'axis'])


class OverlayTests(TestCase):
    """Re-dressing a built strip, which is what makes a code-only strip editable.

    The point of applying this to the *built* tabs is that it cannot care how
    they were declared — a `Q` lookup, a request-scoped queryset, hand-fed items.
    None of it touches a lookup, so none of it can change what a tab means.
    """

    def _tabs(self, overlay, *, locked=False, config=None):
        return build_ribbon_tabs(
            config or {
                'param': 'cat',
                'sources': [{'type': 'field', 'field': 'category'}],
            },
            model=ActivityLog, request=_request(), strings={},
            overlay=overlay, locked=locked,
        )

    def test_a_tab_can_be_renamed(self):
        tabs = self._tabs({'labels': {'user': 'People'}})
        self.assertEqual({t.key: str(t.label) for t in tabs.items}.get('user'), 'People')

    def test_a_tab_can_be_renamed_per_language(self):
        """A rename is a name in a language, like every other name in Settings.
        A language left blank keeps the declared label rather than blanking it."""
        tabs = self._tabs({'labels': {'user': {'en': 'People', 'ar': ''}}})
        self.assertEqual({t.key: str(t.label) for t in tabs.items}.get('user'), 'People')

    def test_a_tab_can_be_re_iconed(self):
        tabs = self._tabs({'icons': {'user': 'bi bi-person'}})
        self.assertEqual({t.key: t.icon for t in tabs.items}.get('user'), 'bi bi-person')

    def test_a_tab_can_be_hidden(self):
        before = [t.key for t in self._tabs(None).items]
        self.assertIn('user', before)
        after = [t.key for t in self._tabs({'hidden': ['user']}).items]
        self.assertNotIn('user', after)
        self.assertEqual(len(after), len(before) - 1)

    def test_tabs_can_be_reordered(self):
        keys = [t.key for t in self._tabs(None).items]
        reversed_keys = list(reversed(keys))
        tabs = self._tabs({'order': reversed_keys})
        self.assertEqual([t.key for t in tabs.items], reversed_keys)

    def test_a_tab_the_order_forgot_keeps_its_place_rather_than_vanishing(self):
        """A strip that gains a tab in code must not disappear from view because
        an order saved months ago never mentioned it."""
        keys = [t.key for t in self._tabs(None).items]
        tabs = self._tabs({'order': [keys[-1]]})
        self.assertEqual([t.key for t in tabs.items], [keys[-1]] + keys[:-1])

    def test_a_locked_strip_takes_the_cosmetic_half_only(self):
        """Which tabs exist is the developer's call on a fixed strip; how they
        read is not — that distinction is what stops `fixed` meaning invisible."""
        tabs = self._tabs({'labels': {'user': 'People'}, 'hidden': ['user']}, locked=True)
        by_key = {t.key: str(t.label) for t in tabs.items}
        self.assertIn('user', by_key, 'a locked strip must keep its tabs')
        self.assertEqual(by_key['user'], 'People')

    def test_an_overlay_never_touches_a_lookup(self):
        """The safety property the whole design rests on."""
        plain = {t.key: t.lookup for t in self._tabs(None).items}
        dressed = {
            t.key: t.lookup
            for t in self._tabs({'labels': {'user': 'People'}, 'order': ['system']}).items
        }
        self.assertEqual(plain, dressed)

    def test_it_re_dresses_a_strip_no_settings_json_could_build(self):
        """A `Q` lookup cannot be stored, so this strip can never be rebuilt
        from Settings — and before the overlay that put the whole model out of reach."""
        from django.db.models import Q

        config = {
            'param': 'state',
            'default': 'live',
            'sources': [
                {'type': 'static', 'key': 'live', 'label': 'Live',
                 'lookup': Q(is_active=True) | Q(is_staff=True)},
                {'type': 'static', 'key': 'gone', 'label': 'Gone',
                 'lookup': {'is_active': False}},
            ],
        }
        tabs = build_ribbon_tabs(
            config, model=User, request=_request(), strings={},
            overlay={'order': ['gone', 'live'], 'labels': {'gone': 'Retired'}},
        )
        self.assertEqual([t.key for t in tabs.items], ['gone', 'live'])
        self.assertEqual(str(tabs.items[0].label), 'Retired')
        self.assertEqual(tabs.items[1].lookup, config['sources'][0]['lookup'])

    def test_hiding_the_default_tab_falls_back_instead_of_raising(self):
        """Hiding a tab is an ordinary thing to do in Settings; a list page is
        the wrong place to find out it was the default."""
        tabs = build_ribbon_tabs(
            {'param': 'state', 'default': 'gone',
             'sources': [
                 {'type': 'static', 'key': 'live', 'label': 'Live', 'lookup': {'is_active': True}},
                 {'type': 'static', 'key': 'gone', 'label': 'Gone', 'lookup': {'is_active': False}},
             ]},
            model=User, request=_request(), strings={},
            overlay={'hidden': ['gone']},
        )
        self.assertEqual([t.key for t in tabs.items], ['live'])
        self.assertEqual(tabs.active, 'live')


class StripPrecedenceTests(TestCase):
    """Where a strip comes from, and who is allowed to change it.

      `ribbon_tabs`        the starting point; an administrator may re-dress it,
                           switch it off, and append extra strips
      `ribbon_tabs_fixed`  locked in code; the builder keeps structural changes off
      neither              whatever Settings holds, if anything

    The short name belongs to the adjustable one because that is the ordinary
    case: locking a strip is the exception and reads as one.
    """

    def setUp(self):
        from django.core.cache import cache

        from dlux.models import SystemSettings

        # `SystemSettings.load()` is cached and `save()` refreshes that cache,
        # so production always sees a saved change. The cache is not rolled back
        # with the test transaction, though, so one test's stored strip would
        # otherwise be read by the next.
        cache.clear()
        self.settings = SystemSettings.load()
        self.settings.is_configured = True
        self.settings.save()

    def _store(self, config):
        self.settings.ribbon_config = config
        self.settings.save()

    def _view(self, **attrs):
        from dlux.ribbon import RibbonMixin

        cls = type('View', (RibbonMixin,), {'model': ActivityLog, **attrs})
        view = cls()
        view.request = _request()
        return view

    def test_a_declared_strip_is_used_when_settings_hold_nothing(self):
        view = self._view(ribbon_tabs={'param': 'declared', 'sources': [{'type': 'all'}]})
        self.assertEqual(view.get_ribbon_tabs().param, 'declared')

    def test_an_extra_strip_does_not_replace_the_declared_strip(self):
        """Admin-made strips are extra rows, not replacements for declared ones."""
        self._store({'dlux.ActivityLog': {'extra_strips': [
            {'param': 'edited', 'sources': [{'type': 'all'}]},
        ]}})
        view = self._view(ribbon_tabs={'param': 'declared', 'sources': [{'type': 'all'}]})
        self.assertEqual([strip.param for strip in view.get_ribbon_strips()], ['declared', 'edited'])

    def test_a_fixed_strip_ignores_extra_strips(self):
        """`ribbon_tabs_fixed` says the developer decided; Settings does not override."""
        self._store({'dlux.ActivityLog': {'extra_strips': [
            {'param': 'edited', 'sources': [{'type': 'all'}]},
        ]}})
        view = self._view(
            ribbon_tabs_fixed={'param': 'fixed', 'sources': [{'type': 'all'}]},
            ribbon_tabs={'param': 'declared', 'sources': [{'type': 'all'}]},
        )
        self.assertEqual(view.get_ribbon_tabs().param, 'fixed')

    def test_removing_an_extra_strip_falls_back_to_the_declared_strip(self):
        view = self._view(ribbon_tabs={'param': 'declared', 'sources': [{'type': 'all'}]})
        self._store({'dlux.ActivityLog': {'extra_strips': [
            {'param': 'edited', 'sources': [{'type': 'all'}]},
        ]}})
        self.assertEqual([strip.param for strip in view.get_ribbon_strips()], ['declared', 'edited'])
        self._store({})
        self.assertEqual(self._view(
            ribbon_tabs={'param': 'declared', 'sources': [{'type': 'all'}]}
        ).get_ribbon_tabs().param, 'declared')

    def test_switching_a_strip_off_beats_the_declared_one(self):
        """Otherwise the switch would do nothing on the pages that have tabs —
        which is every page an operator would want to switch off."""
        view = self._view(ribbon_tabs={'param': 'declared', 'sources': [{'type': 'all'}]})
        self.assertIsNotNone(view.get_ribbon_tabs())
        self._store({'dlux.ActivityLog': {'strips': [{'param': 'declared', 'enabled': False}]}})
        self.assertIsNone(self._view(
            ribbon_tabs={'param': 'declared', 'sources': [{'type': 'all'}]}
        ).get_ribbon_tabs())

    def test_off_survives_the_normalizer_despite_having_no_sources(self):
        """A sourceless strip is normally dropped as an empty bar. Dropping this
        one would restore the strip it was saved to suppress."""
        from dlux.system.normalizers import normalize_ribbon_config

        cleaned = normalize_ribbon_config({
            'dlux.ActivityLog': {'strips': [{'param': 'category', 'enabled': False}]},
        })
        self.assertEqual(cleaned['dlux.ActivityLog']['strips'][0].get('enabled'), False)
        self.assertEqual(normalize_ribbon_config({'dlux.ActivityLog': {'strips': [{'sources': []}]}}), {})

    def test_the_direct_single_strip_shape_is_dropped(self):
        from dlux.system.normalizers import normalize_ribbon_config

        self.assertEqual(normalize_ribbon_config({
            'dlux.ActivityLog': {'param': 'kind', 'sources': [{'type': 'all'}]},
        }), {})

    def test_declared_strip_entries_need_a_param_or_index(self):
        from dlux.system.normalizers import normalize_ribbon_config

        self.assertEqual(normalize_ribbon_config({
            'dlux.ActivityLog': {'strips': [{'enabled': False}]},
        }), {})

    def test_declared_and_extra_strips_are_kept_separately(self):
        """A list can split more than one way at once."""
        from dlux.system.normalizers import normalize_ribbon_config

        cleaned = normalize_ribbon_config({
            'dlux.ActivityLog': {
                'strips': [
                    {'param': 'category', 'labels': {'a': 'A'}},
                ],
                'extra_strips': [
                    {'param': 'kind', 'sources': [{'type': 'all'}]},
                ],
            },
        })
        self.assertEqual(cleaned['dlux.ActivityLog']['strips'][0]['labels'], {'a': 'A'})
        self.assertEqual(cleaned['dlux.ActivityLog']['extra_strips'][0]['param'], 'kind')

    def test_custom_actions_are_kept_by_host(self):
        from dlux.system.normalizers import normalize_ribbon_config

        cleaned = normalize_ribbon_config({
            'dlux.ActivityLog': {'custom_actions': {
                'logs:list': [{
                    'id': 'print',
                    'labels': {'en': 'Print', 'ar': 'طباعة'},
                    'icon': 'bi bi-printer',
                    'url': '/logs/print/',
                    'permission': 'dlux.view_activitylog',
                }],
            }},
        })
        action = cleaned['dlux.ActivityLog']['custom_actions']['logs:list'][0]
        self.assertEqual(action['labels']['en'], 'Print')
        self.assertEqual(action['url'], '/logs/print/')

    def test_custom_actions_reject_raw_html_and_external_urls(self):
        from dlux.system.normalizers import normalize_ribbon_config

        cleaned = normalize_ribbon_config({
            'dlux.ActivityLog': {'custom_actions': {
                'logs:list': [
                    {'id': 'html', 'label': 'Bad', 'html': '<script></script>', 'url': '/ok/'},
                    {'id': 'external', 'label': 'Bad', 'url': 'https://example.com/'},
                    {'id': 'ok', 'label': 'OK', 'attrs': {'data-dynamic-modal': '/modal/'}},
                ],
            }},
        })
        actions = cleaned['dlux.ActivityLog']['custom_actions']['logs:list']
        self.assertEqual([action['id'] for action in actions], ['ok'])

    def test_custom_action_destination_normalizes_to_a_modal_button(self):
        from dlux.system.normalizers import normalize_ribbon_config

        cleaned = normalize_ribbon_config({
            'dlux.ActivityLog': {'custom_actions': {
                'logs:list': [{
                    'id': 'users',
                    'label': 'Users',
                    'destination': {
                        'kind': 'modal',
                        'route_name': 'modal_user',
                        'url': '/sys/modals/users/',
                        'label': 'Users',
                        'permissions': ['auth.add_user'],
                    },
                }],
            }},
        })
        action = cleaned['dlux.ActivityLog']['custom_actions']['logs:list'][0]
        self.assertEqual(action['attrs']['data-dynamic-modal'], '/sys/modals/users/')
        self.assertEqual(action['permissions'], ['auth.add_user'])

    def test_extra_strip_relation_is_kept(self):
        from dlux.system.normalizers import normalize_ribbon_config

        cleaned = normalize_ribbon_config({
            'dlux.ActivityLog': {'extra_strips': [
                {'param': 'kind', 'relation': 'axis', 'sources': [{'type': 'all'}]},
            ]},
        })
        self.assertEqual(cleaned['dlux.ActivityLog']['extra_strips'][0]['relation'], 'axis')

    def test_removing_a_declared_strip_leaves_extra_strips(self):
        self._store({'dlux.ActivityLog': {
            'strips': [{'param': 'declared', 'enabled': False}],
            'extra_strips': [{'param': 'extra', 'sources': [{'type': 'all'}]}],
        }})
        view = self._view(ribbon_tabs={'param': 'declared', 'sources': [{'type': 'all'}]})
        strips = view.get_ribbon_strips()
        self.assertEqual([strip.param for strip in strips], ['extra'])
        self.assertEqual(view.get_ribbon_tabs().param, 'extra')

    def test_a_locked_strip_cannot_be_switched_off(self):
        """The builder does not offer removal for locked strips, so a hand-patched
        record must not disarm a strip the page needs."""
        self._store({'dlux.ActivityLog': {'strips': [{'param': 'fixed', 'enabled': False}]}})
        view = self._view(ribbon_tabs_fixed={'param': 'fixed', 'sources': [{'type': 'all'}]})
        self.assertEqual(view.get_ribbon_tabs().param, 'fixed')

    def test_switching_back_on_restores_the_declared_strip(self):
        """On with nothing drawn stores nothing, so the page returns to code."""
        self._store({'dlux.ActivityLog': {'strips': []}})
        view = self._view(ribbon_tabs={'param': 'declared', 'sources': [{'type': 'all'}]})
        self.assertEqual(view.get_ribbon_tabs().param, 'declared')

    def test_an_unlocked_declared_view_can_receive_extra_strips(self):
        """A normal declaration must not close the door the way a fixed one does."""
        from dlux.ribbon.catalog import ribbon_view_models

        for key, (_model, locked, _declared) in ribbon_view_models().items():
            if key == 'auth.User':
                self.assertFalse(locked)

    def test_the_catalog_carries_declared_strips_for_the_builder(self):
        from dlux.ribbon.catalog import ribbon_tab_catalog

        for entry in ribbon_tab_catalog():
            self.assertIn('strips', entry)
