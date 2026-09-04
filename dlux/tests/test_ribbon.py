from django.urls import reverse
import json
from pathlib import Path
from types import SimpleNamespace

from dlux.tests.harness import setup_test_environment

setup_test_environment()

import django_filters
from django.contrib.auth import get_user_model
from django.template import Context, Template
from django.test import Client, TestCase

from dlux.models import SystemSettings
from dlux.ribbon import KIND_RANGE, KIND_SEARCH, RibbonMixin, build_ribbon, split_range_suffix
from dlux.system.constants import SYSTEM_SETTINGS_EXPORT_FIELDS
from dlux.system.normalizers import normalize_layout_config
from dlux.utils.config import get_system_config
from dlux.utils.import_export import apply_system_settings_import

User = get_user_model()

DEFAULT_LAYOUT = {
    'ribbon_layout': 'default',
    'ribbon_style': 'accent',
    'ribbon_title': True,
    'ribbon_advanced_trigger': 'button',
}


class UserFilterSet(django_filters.FilterSet):
    """Deliberately declared in an order that exercises every derivation rule:
    a search field that is not first, a promoted `year`, a complete date range,
    and a half-range with no sibling."""

    is_staff = django_filters.BooleanFilter(field_name='is_staff')
    keyword = django_filters.CharFilter(field_name='username', lookup_expr='icontains')
    date_joined__gte = django_filters.DateFilter(field_name='date_joined', lookup_expr='gte')
    date_joined__lte = django_filters.DateFilter(field_name='date_joined', lookup_expr='lte')
    year = django_filters.NumberFilter(field_name='date_joined__year')
    last_login__gte = django_filters.DateFilter(field_name='last_login', lookup_expr='gte')

    class Meta:
        model = User
        fields = []


def _ribbon(data=None, layout=None, strings=None, **kwargs):
    filterset = UserFilterSet(data if data is not None else {})
    merged = dict(DEFAULT_LAYOUT)
    merged.update(layout or {})
    return build_ribbon(filterset, layout=merged, strings=strings or {}, **kwargs)


class RibbonDerivationTests(TestCase):
    """A view that declares only a filterset_class must get a correct ribbon."""

    def test_search_leads_the_primary_row(self):
        ribbon = _ribbon()
        self.assertEqual(ribbon.primary[0].name, 'keyword')
        self.assertEqual(ribbon.primary[0].kind, KIND_SEARCH)

    def test_year_is_promoted_beside_the_search(self):
        names = [slot.name for slot in _ribbon().primary]
        self.assertEqual(names, ['keyword', 'year'])

    def test_everything_else_goes_to_the_advanced_panel(self):
        advanced = _ribbon().advanced
        self.assertIn('is_staff', [slot.name for slot in advanced])
        self.assertNotIn('keyword', [slot.name for slot in advanced])

    def test_declaration_order_is_kept_in_the_advanced_panel(self):
        # is_staff is declared before the date fields and must stay there.
        names = [slot.name for slot in _ribbon().advanced]
        self.assertEqual(names[0], 'is_staff')

    def test_gte_lte_pair_collapses_into_one_range_slot(self):
        ranges = [s for s in _ribbon().advanced if s.kind == KIND_RANGE]
        self.assertEqual(len(ranges), 1)
        self.assertEqual(ranges[0].names, ('date_joined__gte', 'date_joined__lte'))

    def test_half_range_label_keeps_the_from_sense_without_the_lookup_sentence(self):
        slots = {s.names[0]: s for s in _ribbon().advanced}
        label = slots['last_login__gte'].label
        self.assertEqual(label, 'Last Login (From)')
        self.assertNotIn('greater than', label.lower())

    def test_half_range_stays_a_plain_field(self):
        """A `_gte` with no `_lte` sibling is still a real filter. Dropping it
        would silently stop a filter the user set from being offered."""
        slots = {s.name: s for s in _ribbon().advanced}
        self.assertIn('last_login__gte', slots)
        self.assertNotEqual(slots['last_login__gte'].kind, KIND_RANGE)

    def test_every_filter_is_placed_exactly_once(self):
        ribbon = _ribbon()
        placed = ribbon.field_names()
        self.assertEqual(sorted(placed), sorted(ribbon.form.fields))
        self.assertEqual(len(placed), len(set(placed)))

    def test_split_range_suffix_recognises_both_spellings(self):
        self.assertEqual(split_range_suffix('date__gte'), ('date', 'from'))
        self.assertEqual(split_range_suffix('date_lte'), ('date', 'to'))
        self.assertEqual(split_range_suffix('plain'), (None, None))

    def test_no_filterset_yields_a_ribbon_with_only_chrome(self):
        ribbon = build_ribbon(None, layout=DEFAULT_LAYOUT, strings={}, title='Assets')
        self.assertEqual(ribbon.title, 'Assets')
        self.assertEqual(ribbon.primary, [])
        self.assertFalse(ribbon.has_advanced)

    def test_advanced_panel_opens_when_an_advanced_filter_is_active(self):
        self.assertFalse(_ribbon().advanced_active)
        self.assertTrue(_ribbon({'is_staff': 'true'}).advanced_active)

    def test_a_primary_filter_does_not_force_the_panel_open(self):
        self.assertFalse(_ribbon({'keyword': 'ali'}).advanced_active)


class RibbonLabelTests(TestCase):
    """django_filters auto-generates a label from the lookup when a filter
    declares none. Those labels are unusable on a control, so the translation
    chain has to win and the fallback has to be the field name."""

    def _labels(self, strings=None):
        ribbon = build_ribbon(UserFilterSet({}), layout=DEFAULT_LAYOUT, strings=strings or {})
        slots = list(ribbon.primary) + list(ribbon.advanced)
        return {slot.names[0]: slot.label for slot in slots}

    def test_unresolvable_auto_label_is_not_shown(self):
        """`year` filters on `date_joined__year`, which django_filters cannot
        resolve — it labels the field '[invalid name]'."""
        self.assertEqual(self._labels()['year'], 'Year')

    def test_range_never_uses_the_lookup_sentence(self):
        label = self._labels()['date_joined__gte']
        self.assertEqual(label, 'Date Joined')
        self.assertNotIn('greater than', label.lower())

    def test_filter_namespace_is_in_the_chain(self):
        """dlux already keeps filter labels under `filter_<name>`; a project
        that translated its filters for the old helper needs no new strings."""
        self.assertEqual(self._labels({'filter_year': 'Season'})['year'], 'Season')

    def test_model_specific_key_wins_over_generic(self):
        labels = self._labels({'label_year': 'Generic', 'label_user_year': 'Specific'})
        self.assertEqual(labels['year'], 'Specific')

    def test_model_verbose_name_is_used_when_it_is_meaningful(self):
        self.assertEqual(self._labels()['is_staff'], 'Staff status')


class RibbonOverrideTests(TestCase):
    """Each override must work on its own — a view should never have to
    specify all of them to correct one."""

    def test_primary_override_alone(self):
        ribbon = _ribbon(primary=['is_staff'])
        self.assertEqual([s.name for s in ribbon.primary], ['is_staff'])
        self.assertIn('keyword', [s.name for s in ribbon.advanced])

    def test_advanced_override_alone(self):
        ribbon = _ribbon(advanced=['is_staff'])
        self.assertEqual([s.name for s in ribbon.advanced], ['is_staff'])

    def test_unknown_name_is_skipped_not_raised(self):
        """A filter renamed out from under a view degrades to a missing control,
        not a 500 on the list page."""
        ribbon = _ribbon(primary=['keyword', 'renamed_away'])
        self.assertEqual([s.name for s in ribbon.primary], ['keyword'])

    def test_title_and_actions_pass_through(self):
        from dlux.ribbon import RibbonAction

        ribbon = _ribbon(title='Users', actions=[RibbonAction(url='/add/', label='Add')])
        self.assertEqual(ribbon.title, 'Users')
        self.assertEqual(ribbon.actions[0].url, '/add/')

    def test_subtitle_can_be_computed_per_request(self):
        class View(RibbonMixin):
            request = SimpleNamespace(GET={}, resolver_match=None)

            def get_ribbon_filterset(self):
                return None

            def get_ribbon_subtitle(self):
                return 'Translated subtitle'

            def get_custom_ribbon_actions(self):
                return []

            def visible_ribbon_strips(self):
                return []

        self.assertEqual(View().get_ribbon().subtitle, 'Translated subtitle')


class RibbonActionPermissionTests(TestCase):
    def test_action_is_dropped_when_the_user_lacks_the_permission(self):
        from types import SimpleNamespace

        from dlux.ribbon import build_action

        denied = SimpleNamespace(user=SimpleNamespace(has_perm=lambda perm: False))
        allowed = SimpleNamespace(user=SimpleNamespace(has_perm=lambda perm: True))
        spec = {'url': '/add/', 'label': 'Add', 'permission': 'auth.add_user'}
        self.assertIsNone(build_action(spec, request=denied))
        self.assertIsNotNone(build_action(spec, request=allowed))

    def test_action_without_permission_needs_no_request(self):
        from dlux.ribbon import build_action

        self.assertIsNotNone(build_action({'url': '/add/'}, request=None))

    def test_action_permission_lists_are_supported(self):
        from types import SimpleNamespace

        from dlux.ribbon import build_action

        denied = SimpleNamespace(user=SimpleNamespace(
            is_authenticated=True,
            is_superuser=False,
            has_perm=lambda perm: False,
        ))
        allowed = SimpleNamespace(user=SimpleNamespace(
            is_authenticated=True,
            is_superuser=False,
            has_perm=lambda perm: perm == 'auth.add_user',
        ))
        spec = {'url': '/add/', 'label': 'Add', 'permissions': ['auth.add_user']}
        self.assertIsNone(build_action(spec, request=denied))
        self.assertIsNotNone(build_action(spec, request=allowed))


class RibbonActiveFilterTests(TestCase):
    """The Clear control reflects filter state, not table presentation state —
    the same contract `advanced_filter_helper` was fixed to honour in v1.8.2."""

    def _ribbon_for(self, query):
        from django.test import RequestFactory

        request = RequestFactory().get('/users/', query)
        return build_ribbon(
            UserFilterSet(request.GET), request=request,
            layout=DEFAULT_LAYOUT, strings={},
        )

    def test_no_query_means_no_active_filter(self):
        self.assertFalse(self._ribbon_for({}).has_active_filters)

    def test_a_real_filter_activates_it(self):
        self.assertTrue(self._ribbon_for({'keyword': 'ali'}).has_active_filters)

    def test_pagination_and_sorting_do_not_activate_it(self):
        for query in ({'page': '3'}, {'per_page': '50'}, {'sort': 'username'}):
            self.assertFalse(
                self._ribbon_for(query).has_active_filters,
                f'{query} must not read as a filter',
            )

    def test_an_unknown_query_key_does_not_activate_it(self):
        self.assertFalse(self._ribbon_for({'utm_source': 'x'}).has_active_filters)

    def test_clear_keeps_presentation_but_drops_filters_and_page(self):
        ribbon = self._ribbon_for({'keyword': 'ali', 'per_page': '50', 'sort': 'username', 'page': '3'})
        self.assertIn('per_page=50', ribbon.clear_url)
        self.assertIn('sort=username', ribbon.clear_url)
        self.assertNotIn('keyword', ribbon.clear_url)
        self.assertNotIn('page=3', ribbon.clear_url)

    def test_clear_renders_only_when_a_filter_is_active(self):
        def html(query):
            return Template('{% load dlux_tags %}{% dlux_ribbon ribbon %}').render(
                Context({'ribbon': self._ribbon_for(query), 'request': None}))

        self.assertNotIn('dlux-filter-clear', html({'per_page': '50'}))
        self.assertIn('dlux-filter-clear', html({'keyword': 'ali'}))


class EmptyChoiceLabelTests(TestCase):
    """A dropdown's empty option must name the field, not read "---------".

    The field and its widget hold choices separately. `ModelChoiceField` gives
    its widget a live iterator, so setting `empty_label` reaches the markup on
    its own; a plain `ChoiceField` gives it a snapshot list, so it does not.
    Asserting on `field.choices` alone passes while the page still renders
    "---------", so these assert the **widget**, which is what renders.
    """

    def _form(self):
        import django_filters
        from django.contrib.auth.models import Group

        class F(django_filters.FilterSet):
            # One of each: model-backed, plain choices, and choices assigned
            # after construction the way a generated year filter does it.
            group = django_filters.ModelChoiceFilter(queryset=Group.objects.all())
            kind = django_filters.ChoiceFilter(choices=[('a', 'A'), ('b', 'B')])
            year = django_filters.ChoiceFilter(choices=[])

            class Meta:
                model = User
                fields = []

        filterset = F({})
        filterset.form.fields['year'].choices = [('2026', '2026')]
        return filterset.form

    def test_every_select_names_its_field_in_the_empty_option(self):
        from dlux.utils.crud import set_field_attrs

        form = self._form()
        set_field_attrs(form, None, inline_labels=True)
        for name in ('group', 'kind', 'year'):
            rendered = list(form.fields[name].widget.choices)[0][1]
            self.assertNotIn('---', str(rendered), f'{name} still renders a bare placeholder')
            self.assertTrue(str(rendered).strip(), f'{name} has an empty first option')

    def test_the_widget_agrees_with_the_field(self):
        from dlux.utils.crud import set_field_attrs

        form = self._form()
        set_field_attrs(form, None, inline_labels=True)
        for name in ('group', 'kind', 'year'):
            self.assertEqual(
                list(form.fields[name].choices)[0][1],
                list(form.fields[name].widget.choices)[0][1],
                f'{name}: the widget renders something the field does not say',
            )

    def test_choices_assigned_after_construction_are_still_synced(self):
        """The year filter is built empty and filled from the data, which is the
        case that used to leave the widget holding a stale list."""
        from dlux.utils.crud import set_field_attrs

        form = self._form()
        set_field_attrs(form, None, inline_labels=True)
        values = [value for value, _label in form.fields['year'].widget.choices]
        self.assertIn('2026', values)


class RibbonPreservedKeyTests(TestCase):
    """A list split by tabs carries its tab in the query string. The ribbon is a
    GET form, so without carrying that key a filter submit — or a Clear — drops
    the reader back to the first tab."""

    def _ribbon(self, query, preserve_keys=('kind',)):
        from django.test import RequestFactory

        request = RequestFactory().get('/parties/', query)
        return build_ribbon(
            UserFilterSet(request.GET), request=request, layout=DEFAULT_LAYOUT,
            strings={}, preserve_keys=preserve_keys,
        )

    def test_the_tab_key_is_resubmitted_as_a_hidden_input(self):
        ribbon = self._ribbon({'kind': 'employee', 'keyword': 'ali'})
        self.assertIn(('kind', 'employee'), ribbon.hidden)

    def test_the_tab_key_survives_a_clear(self):
        ribbon = self._ribbon({'kind': 'employee', 'keyword': 'ali'})
        self.assertIn('kind=employee', ribbon.clear_url)
        self.assertNotIn('keyword', ribbon.clear_url)

    def test_presentation_keys_are_carried_too(self):
        ribbon = self._ribbon({'sort': 'name', 'per_page': '50'})
        carried = dict(ribbon.hidden)
        self.assertEqual(carried.get('sort'), 'name')
        self.assertEqual(carried.get('per_page'), '50')

    def test_page_is_never_carried(self):
        """Applying a filter changes what the list holds, so the old page
        number is meaningless — and would show an empty page."""
        ribbon = self._ribbon({'kind': 'employee', 'page': '7'})
        self.assertNotIn('page', dict(ribbon.hidden))
        self.assertNotIn('page=7', ribbon.clear_url)

    def test_a_filter_is_never_carried_as_hidden(self):
        """Carrying a filter would make it impossible to clear from the form."""
        ribbon = self._ribbon({'keyword': 'ali', 'kind': 'employee'})
        self.assertNotIn('keyword', dict(ribbon.hidden))

    def test_nothing_is_carried_without_preserve_keys(self):
        ribbon = self._ribbon({'kind': 'employee'}, preserve_keys=())
        self.assertNotIn('kind', dict(ribbon.hidden))
        self.assertNotIn('kind', ribbon.clear_url)

    def test_hidden_inputs_render(self):
        ribbon = self._ribbon({'kind': 'employee'})
        html = Template('{% load dlux_tags %}{% dlux_ribbon ribbon %}').render(
            Context({'ribbon': ribbon, 'request': None}))
        self.assertIn('<input type="hidden" name="kind" value="employee">', html)


class RibbonFieldNormalisationTests(TestCase):
    """The ribbon must apply the same field normalisation the filter helpers do,
    or its inputs lose their Bootstrap styling, RTL direction and datepicker."""

    def test_normalisation_does_not_eat_the_derived_labels(self):
        """`set_field_attrs` blanks a select's label into its empty choice, so
        it has to run after derivation, not before."""
        slots = {s.names[0]: s for s in _ribbon().advanced}
        self.assertEqual(slots['is_staff'].label, 'Staff status')

    def test_widgets_get_bootstrap_classes(self):
        ribbon = _ribbon()
        self.assertIn('form-control', ribbon.form.fields['keyword'].widget.attrs['class'])
        self.assertIn('form-select', ribbon.form.fields['is_staff'].widget.attrs['class'])

    def test_date_fields_get_the_shared_datepicker_hook(self):
        ribbon = _ribbon()
        for name in ('date_joined__gte', 'date_joined__lte'):
            self.assertIn('dlux-datepicker', ribbon.form.fields[name].widget.attrs['class'])

    def test_fields_carry_a_direction(self):
        self.assertIn('dir', _ribbon().form.fields['keyword'].widget.attrs)


class RibbonActionIdentityTests(TestCase):
    """A ribbon button is its destination.

    Two buttons opening the same modal or linking to the same URL are the same
    button however they were declared, so only one is drawn — and an
    administrator's edits to a code-declared button hang off that identity rather
    than its position in `ribbon_actions`, which a view is free to reorder.
    """

    def _action(self, **kwargs):
        from dlux.ribbon import RibbonAction

        return RibbonAction(**kwargs)

    def test_the_key_is_the_endpoint_whichever_attribute_carries_it(self):
        """dlux's own manager buttons open a modal from `data-url` through their own
        handler rather than the dynamic-modal contract. Keying on the attribute
        called them different buttons from an administrator's `data-dynamic-modal`
        one — which is the very pair that ends up duplicated."""
        from dlux.ribbon.build import action_destination_key

        modal = self._action(label='Add', attrs={'data-dynamic-modal': '/groups/manage/'})
        data_url = self._action(label='Groups', attrs={'data-url': '/groups/manage/'})
        link = self._action(label='Groups', url='/groups/manage/')
        html_only = self._action(label='Raw')

        self.assertEqual(action_destination_key(modal), 'dest:/groups/manage/')
        self.assertEqual(action_destination_key(data_url), 'dest:/groups/manage/')
        self.assertEqual(action_destination_key(link), 'dest:/groups/manage/')
        self.assertEqual(action_destination_key(html_only), '')

    def test_one_button_per_destination_whoever_declared_it(self):
        from dlux.ribbon.build import _dedupe_actions_by_destination

        first = self._action(label="View's own", url='/groups/manage/')
        duplicate = self._action(label='Added by an admin', url='/groups/manage/')
        modal = self._action(label='Users', attrs={'data-dynamic-modal': '/modal/user/'})
        same_modal = self._action(label='Users again', attrs={'data-dynamic-modal': '/modal/user/'})
        other = self._action(label='Reports', url='/reports/')

        kept = _dedupe_actions_by_destination([first, duplicate, modal, same_modal, other])

        # Code before configuration: the first declaration of a destination wins.
        self.assertEqual([action.label for action in kept], ["View's own", 'Users', 'Reports'])

    def test_buttons_with_no_destination_are_never_merged(self):
        """Two raw-html actions are not the same action; they just say nothing."""
        from dlux.ribbon.build import _dedupe_actions_by_destination

        kept = _dedupe_actions_by_destination([
            self._action(label='One'), self._action(label='Two'),
        ])

        self.assertEqual([action.label for action in kept], ['One', 'Two'])

    def test_an_overlay_removes_renames_and_re_icons_a_declared_button(self):
        from dlux.ribbon.build import _apply_action_overlays

        actions = [
            self._action(label='Add User', icon='bi-plus', attrs={'data-dynamic-modal': '/modal/user/'}),
            self._action(label='Reports', icon='bi-graph-up', url='/reports/'),
            self._action(label='Groups', url='/groups/'),
        ]
        overlays = {
            'dest:/modal/user/': {'enabled': False},
            'dest:/reports/': {'labels': {'en': 'Statistics'}, 'icon': 'bi-bar-chart'},
        }

        kept = _apply_action_overlays(actions, overlays)

        self.assertEqual([action.label for action in kept], ['Statistics', 'Groups'])
        self.assertEqual(kept[0].icon, 'bi-bar-chart')

    def test_an_overlay_never_edits_the_action_a_view_handed_over(self):
        """A view may return the same RibbonAction instance on every request, so an
        overlay that mutated it would leak into the next reader's page."""
        from dlux.ribbon.build import _apply_action_overlays

        original = self._action(label='Reports', url='/reports/')

        kept = _apply_action_overlays([original], {'dest:/reports/': {'labels': {'en': 'Stats'}}})

        self.assertEqual(kept[0].label, 'Stats')
        self.assertEqual(original.label, 'Reports')

    def test_restoring_a_button_is_the_absence_of_an_overlay(self):
        from dlux.system.normalizers import _normalize_ribbon_action_overlays

        self.assertEqual(_normalize_ribbon_action_overlays({'dest:/x/': {}}), {})
        self.assertEqual(
            _normalize_ribbon_action_overlays({'dest:/x/': {'enabled': False}}),
            {'dest:/x/': {'enabled': False}},
        )
        # `enabled: True` is the default, so it is not worth storing either.
        self.assertEqual(_normalize_ribbon_action_overlays({'dest:/x/': {'enabled': True}}), {})
        self.assertEqual(_normalize_ribbon_action_overlays('nonsense'), {})


class RibbonBuilderDeclaredActionAssetTests(TestCase):
    """The builder treats a code-declared button the way it treats a declared strip."""

    BUILDER_JS = (
        Path(__file__).resolve().parent.parent
        / 'static' / 'dlux' / 'ribbon' / 'js' / 'ribbon_builder.js'
    )

    def test_declared_buttons_are_selectable_editable_and_restorable(self):
        js = self.BUILDER_JS.read_text()

        self.assertIn('const actionOverlayState = {};', js)
        self.assertIn('function actionOverlayFor(modelKey, key)', js)
        self.assertIn('function actionOverlayDirty(overlay)', js)
        self.assertIn('function dropActionOverlay(modelKey, key)', js)
        self.assertIn("const type = locked ? 'declared-action' : 'action';", js)
        self.assertIn("id: 'restore-action'", js)
        # Restore is dropping the overlay, exactly as it is for a declared strip.
        self.assertIn('dropActionOverlay(selected.modelKey, selected.key);', js)
        self.assertIn('overlay.enabled = false;', js)
        # A button with no destination cannot be addressed, so it stays fixed.
        self.assertIn("const overlayKey = locked ? String(action.key || '') : '';", js)
        self.assertIn('if (locked && !overlayKey) {', js)

    def test_the_builder_shows_one_button_per_destination(self):
        js = self.BUILDER_JS.read_text()

        self.assertIn('function customActionDestinationKey(action)', js)
        self.assertIn('const seenDestinations = new Set();', js)
        self.assertIn('function withoutDuplicates(action, key)', js)

    def test_an_overlay_carrying_only_an_icon_keeps_the_developers_name(self):
        """`firstLabel` always answers with something, so asking it whether a rename
        exists reported the placeholder as the name and overwrote the real one."""
        js = self.BUILDER_JS.read_text()

        self.assertIn('function overrideLabel(labels)', js)
        self.assertIn("(overlay && overrideLabel(overlay.labels)) || action.label", js)
        self.assertNotIn("(overlay && firstLabel(overlay.labels, ''))", js)

    def test_a_submit_buttons_endpoint_is_its_formaction(self):
        """The Reports buttons post the page's own form; where they post it is
        their destination just as much as an href is."""
        from dlux.ribbon.build import action_destination_key
        from dlux.ribbon import RibbonAction

        action = RibbonAction(label='Print', type='submit', attrs={
            'form': 'general-report-form', 'formaction': '/reports/print/',
        })

        self.assertEqual(action_destination_key(action), 'dest:/reports/print/')

    def test_a_function_host_can_declare_its_buttons_for_the_builder(self):
        """A function page builds its ribbon inline, so there is no instance to
        ask — it names its buttons on the function instead. Without this the
        builder listed Reports as a ribbon host carrying no buttons at all."""
        from dlux.ribbon.catalog import _declared_function_actions

        def host(request):
            return None

        host.dlux_ribbon_actions = [
            {'label': 'Print', 'attrs': {'formaction': '/reports/print/'}},
        ]
        summaries = _declared_function_actions(host, None)
        self.assertEqual([s['label'] for s in summaries], ['Print'])
        self.assertEqual(summaries[0]['key'], 'dest:/reports/print/')

        # A callable form, for buttons that depend on the request.
        host.dlux_ribbon_actions = lambda request: [{'label': 'Export', 'url': '/x/'}]
        self.assertEqual(
            [s['label'] for s in _declared_function_actions(host, None)], ['Export'])

        # And a host that declares nothing is simply a host with no buttons.
        del host.dlux_ribbon_actions
        self.assertEqual(_declared_function_actions(host, None), [])

    def test_reports_declares_the_buttons_its_page_draws(self):
        """One spec list for the renameable buttons, so what an administrator
        renames is what the page shows."""
        from dlux.views.reports import (
            _reports_action_specs, _reports_catalog_actions, reports_overview_view,
        )

        self.assertIs(reports_overview_view.dlux_ribbon_actions, _reports_catalog_actions)
        specs = _reports_action_specs()
        self.assertEqual(len(specs), 2)
        self.assertTrue(all(spec['attrs'].get('formaction') for spec in specs))

    def test_backup_declares_the_back_button_its_page_draws(self):
        """Backup is a function host too, so the builder needs an explicit action
        catalog just like Reports."""
        from dlux.ribbon.catalog import _declared_function_actions
        from dlux.views.backup import _backup_action_specs, system_backup_page

        self.assertIs(system_backup_page.dlux_ribbon_actions, _backup_action_specs)
        specs = _backup_action_specs()
        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0]['url'], reverse('options_view'))

        summaries = _declared_function_actions(system_backup_page, None)
        self.assertEqual([summary['label'] for summary in summaries], ['Back to Options'])
        self.assertEqual(summaries[0]['key'], f"dest:{reverse('options_view')}")

    def test_the_backup_control_is_listed_for_removal_but_never_drawn_from_the_catalog(self):
        """It is rendered markup, so the catalog carries a stand-in for it. That
        stand-in must not reach the page: sharing one list put it ahead of the real
        markup, the duplicate check dropped the markup, and the page drew an empty
        button where the backup control had been."""
        from dlux.views.reports import _reports_action_specs, _reports_catalog_actions

        catalog = _reports_catalog_actions()
        page = _reports_action_specs()

        self.assertEqual(len(catalog), 3)
        self.assertEqual(len(page), 2)
        stand_in = catalog[-1]
        self.assertEqual(stand_in['kind'], 'html')
        self.assertEqual(stand_in['attrs']['data-start-url'], reverse('reports_backup_start'))
        self.assertNotIn(stand_in, page)

    def test_a_composite_control_is_identified_by_the_job_it_starts(self):
        from dlux.ribbon.build import action_destination_key
        from dlux.ribbon import RibbonAction

        action = RibbonAction(html='<div>widget</div>', attrs={'data-start-url': '/start/'})

        self.assertEqual(action_destination_key(action), 'dest:/start/')

    def test_building_the_catalog_never_writes(self):
        """Asking a view for its buttons runs the view's own code, which reads and
        — through a settings singleton it happens to touch — can write. A catalog
        describes what exists; building one must not change anything."""
        source = (
            Path(__file__).resolve().parent.parent / 'ribbon' / 'catalog.py'
        ).read_text()
        built = source[source.index('def _view_built_actions('):source.index('def _host_actions(')]
        self.assertIn('with transaction.atomic():', built)
        self.assertIn('transaction.set_rollback(True)', built)

    def test_the_catalog_gives_each_declared_button_its_destination(self):
        from dlux.ribbon.catalog import _action_summary

        modal = _action_summary({'label': 'Users', 'attrs': {'data-dynamic-modal': '/m/'}}, 0)
        link = _action_summary({'label': 'Reports', 'url': '/reports/'}, 1)
        raw = _action_summary({'html': '<b>x</b>'}, 2)

        self.assertEqual(modal['key'], 'dest:/m/')
        self.assertEqual(link['key'], 'dest:/reports/')
        self.assertEqual(raw['key'], '')


class RibbonActionRenderingTests(TestCase):
    """The commonest dlux list action opens a dynamic modal and has no href, so
    the ribbon must render a button — not force the page back to raw HTML."""

    def _html(self, action):
        from dlux.ribbon import build_action

        ribbon = _ribbon(actions=[build_action(action) if isinstance(action, dict) else action])
        return Template('{% load dlux_tags %}{% dlux_ribbon ribbon %}').render(
            Context({'ribbon': ribbon, 'request': None})
        )

    def test_action_with_a_url_renders_a_link(self):
        from dlux.ribbon import RibbonAction

        html = self._html(RibbonAction(url='/add/', label='Add'))
        self.assertIn('<a href="/add/"', html)

    def test_action_without_a_url_renders_a_button(self):
        from dlux.ribbon import RibbonAction

        html = self._html(RibbonAction(label='Add', attrs={'data-dynamic-modal': '/modal/user/'}))
        self.assertIn('<button type="button"', html)
        self.assertNotIn('<a href=', html)
        self.assertIn('data-dynamic-modal="/modal/user/"', html)

    def test_a_missing_url_never_becomes_an_empty_href(self):
        """An `<a>` with no href is not focusable and does nothing on click."""
        from dlux.ribbon import build_action

        action = build_action({'label': 'Add', 'url': None})
        self.assertFalse(action.is_link)

    def test_raw_html_action_still_passes_through(self):
        html = self._html({'html': '<span id="custom-action"></span>'})
        self.assertIn('<span id="custom-action"></span>', html)

    def test_title_icon_renders_only_when_given(self):
        ribbon = _ribbon(title='Users', title_icon='bi bi-people')
        html = Template('{% load dlux_tags %}{% dlux_ribbon ribbon %}').render(
            Context({'ribbon': ribbon, 'request': None}))
        self.assertIn('<span class="dlux-ribbon-icon"><i class="bi bi-people"></i></span>', html)
        plain = Template('{% load dlux_tags %}{% dlux_ribbon ribbon %}').render(
            Context({'ribbon': _ribbon(title='Users'), 'request': None}))
        self.assertIn('Users', plain)
        self.assertNotIn('<i class=""', plain)


class RibbonLayoutTests(TestCase):
    """The band mirrors the list header this replaces: title and actions share
    one row, and the filters sit on the row beneath it."""

    def _html(self, layout=None, **kwargs):
        from dlux.ribbon import RibbonAction

        ribbon = _ribbon(layout=layout, title='Users',
                         actions=[RibbonAction(label='Add')], **kwargs)
        return Template('{% load dlux_tags %}{% dlux_ribbon ribbon %}').render(
            Context({'ribbon': ribbon, 'request': None}))

    def test_actions_sit_on_the_title_row_not_under_the_filters(self):
        html = self._html()
        header = html.index('dlux-ribbon-header-row')
        actions = html.index('dlux-ribbon-actions')
        filters = html.index('dlux-ribbon-filter no-print')
        self.assertLess(header, actions, 'actions must be inside the header row')
        self.assertLess(actions, filters, 'actions must come before the filters')

    def test_the_search_control_is_the_pill_chip_pair(self):
        """The chip group is shared with the filter helper — the ribbon must
        reuse it, not render a plain labelled button in its place."""
        html = self._html()
        self.assertIn('dlux-filter-chip dlux-filter-submit rounded-pill', html)
        self.assertIn('d-flex w-100 dlux-filter-controls', html)

    def test_the_advanced_toggle_is_a_chip_but_not_the_helpers_toggle(self):
        """It takes the chip look, but never `dlux-filter-toggle`: the helper's
        script binds panel state to that class, and two scripts restoring one
        panel from two localStorage keys fight each other."""
        html = self._html()
        self.assertIn('dlux-filter-chip dlux-ribbon-toggle', html)
        self.assertNotIn('dlux-filter-toggle', html)

    def test_the_form_reuses_the_filter_class_but_not_its_autosubmit_hook(self):
        """`form_fields.css` and all seven themes style filter rows through
        `.dlux-filter`, so the ribbon shares the class; the helper's autosubmit
        keys off the data attribute, so sharing it cannot double-submit."""
        html = self._html()
        self.assertIn('dlux-form dlux-filter dlux-ribbon', html)
        self.assertIn('data-dlux-ribbon-autosubmit="true"', html)
        self.assertNotIn('data-dlux-filter-autosubmit', html)

    def test_filters_and_controls_share_one_bootstrap_row(self):
        """The controls and the toggle are columns of the same `row` as the
        fields — the CSS makes only that first row nowrap."""
        html = self._html()
        first_row = html.index('row g-2 align-items-start mb-0')
        panel = html.index('id="dlux-ribbon-advanced"')
        row = html[first_row:panel]
        self.assertIn('form-group col-auto flex-fill', row)
        self.assertIn('col-sm-12 col-md-2 col-lg-auto', row)
        self.assertIn('dlux-filter-controls', row)
        self.assertIn('col-sm-12 col-md-3 col-lg-auto', row)

    def test_search_field_is_not_given_two_placeholders(self):
        ribbon = _ribbon(strings={'search_placeholder': 'Find'})
        html = Template('{% load dlux_tags %}{% dlux_ribbon ribbon %}').render(
            Context({'ribbon': ribbon, 'request': None}))
        search = html[html.index('name="keyword"') - 40:html.index('name="keyword"') + 200]
        self.assertEqual(search.count('placeholder='), 1)
        self.assertIn('placeholder="Find"', search)


class RibbonLayoutVersusStyleTests(TestCase):
    """Layout is the arrangement; style is the look. They must not leak into
    each other — a new skin should never have to know where the actions sit."""

    def _html(self, layout=None, **kw):
        from dlux.ribbon import RibbonAction

        ribbon = _ribbon(layout=layout, title='Users',
                         actions=[RibbonAction(label='Add')], **kw)
        return Template('{% load dlux_tags %}{% dlux_ribbon ribbon %}').render(
            Context({'ribbon': ribbon, 'request': None}))

    def test_each_style_is_a_skin_class_on_every_layout(self):
        for layout in ('default', 'stacked', 'compact'):
            for style in ('accent', 'panel', 'flat'):
                html = self._html({'ribbon_layout': layout, 'ribbon_style': style})
                self.assertIn(f'dlux-ribbon-layout-{layout}', html)
                self.assertIn(f'dlux-ribbon-skin-{style}', html)

    def test_compact_has_no_title_whatever_the_toggle_says(self):
        html = self._html({'ribbon_layout': 'compact', 'ribbon_title': True})
        self.assertNotIn('<h1>', html)

    def test_compact_keeps_its_actions_in_the_filter_row(self):
        html = self._html({'ribbon_layout': 'compact'})
        self.assertIn('dlux-ribbon-actions-inline', html)
        self.assertNotIn('dlux-ribbon-actions-below', html)

    def test_stacked_puts_actions_below(self):
        self.assertIn('dlux-ribbon-actions-below', self._html({'ribbon_layout': 'stacked'}))

    def test_default_puts_actions_on_the_title_row(self):
        html = self._html({'ribbon_layout': 'default'})
        self.assertNotIn('dlux-ribbon-actions-below', html)
        self.assertLess(html.index('dlux-ribbon-actions'),
                        html.index('row g-2 align-items-start mb-0'))

    def test_each_layout_places_the_actions_exactly_one_way(self):
        """Layout alone decides placement. A second setting for it was removed
        because its only live value rendered exactly what `stacked` renders."""
        placements = {
            layout: (
                'inline' if 'dlux-ribbon-actions-inline' in self._html({'ribbon_layout': layout})
                else 'below' if 'dlux-ribbon-actions-below' in self._html({'ribbon_layout': layout})
                else 'title-row'
            )
            for layout in ('default', 'stacked', 'compact')
        }
        self.assertEqual(placements,
                         {'default': 'title-row', 'stacked': 'below', 'compact': 'inline'})

    def test_no_layout_renders_the_same_band_as_another(self):
        """Two layouts producing identical markup means one of them is dead."""
        rendered = {layout: self._html({'ribbon_layout': layout}).replace(
            f'dlux-ribbon-layout-{layout}', 'X')
            for layout in ('default', 'stacked', 'compact')}
        self.assertEqual(len(set(rendered.values())), 3)

    def test_default_layout_is_unchanged_by_the_split(self):
        """Renaming the setting must not have altered what `default` renders."""
        html = self._html({'ribbon_layout': 'default'})
        self.assertIn('dlux-ribbon-header-row', html)
        self.assertIn('<h1>', html)
        first_row = html.index('row g-2 align-items-start mb-0')
        self.assertLess(html.index('dlux-ribbon-actions'), first_row)


class RibbonChromeHookTests(TestCase):
    """The ribbon must hang off the chrome hooks dlux already has, not
    hand-rolled equivalents, or every theme and every appearance setting has to
    be taught about it separately."""

    def _html(self, layout=None):
        ribbon = _ribbon(layout=layout, title='Users')
        return Template('{% load dlux_tags %}{% dlux_ribbon ribbon %}').render(
            Context({'ribbon': ribbon, 'request': None}))

    def test_every_layout_is_a_card_surface(self):
        """`base/css/card_edges.css` keys off this attribute, so without it the
        Card edges setting has no effect on the ribbon at any style."""
        for layout in ('default', 'stacked', 'compact'):
            self.assertIn('data-dlux-card-surface', self._html({'ribbon_layout': layout}))

    def test_panel_carries_the_shared_theme_class(self):
        """All seven themes restyle `.glass-profile`. Without it the panel skin
        keeps its light-mode surface on the dark themes."""
        self.assertIn('glass-profile', self._html({'ribbon_style': 'panel'}))

    def test_other_styles_do_not_claim_the_glass_class(self):
        for style in ('accent', 'flat'):
            self.assertNotIn('glass-profile', self._html({'ribbon_style': style}))

    def test_panel_surface_is_not_hardcoded_to_a_light_colour(self):
        """A literal white mix is what broke the dark themes."""
        css = (Path(__file__).resolve().parents[1]
               / 'static' / 'dlux' / 'ribbon' / 'css' / 'ribbon.css').read_text()
        glass = css[css.index('.dlux-ribbon-skin-panel {'):]
        glass = glass[:glass.index('}')]
        self.assertNotIn('rgba(255, 255, 255', glass)

    def _ribbon_css(self):
        return (Path(__file__).resolve().parents[1]
                / 'static' / 'dlux' / 'ribbon' / 'css' / 'ribbon.css').read_text()

    def test_the_action_row_wraps_instead_of_crushing_its_buttons(self):
        """On a phone the row kept every action on one line: buttons were squeezed
        below their own labels until they read as circles, and the ones that still
        would not fit hung outside the ribbon card and off the screen."""
        css = self._ribbon_css()
        actions = css[css.index('\n.dlux-ribbon-actions {'):]
        actions = actions[:actions.index('}')]
        self.assertIn('flex-wrap: wrap;', actions)
        self.assertNotIn('flex-wrap: nowrap;', actions)

        button = css[css.index('\n.dlux-ribbon-actions .btn {'):]
        button = button[:button.index('}')]
        # A button is as wide as its label; shrinking it is what made it a circle.
        self.assertIn('flex: 0 0 auto;', button)

    def test_the_title_stops_sharing_a_line_with_the_actions_on_a_phone(self):
        """399.98px was too late — every common phone is 390-430px wide, so the
        actions kept whatever column was left beside a 14rem title floor."""
        css = self._ribbon_css()
        self.assertIn('@media (max-width: 575.98px) {', css)
        block = css[css.rindex('@media (max-width: 575.98px) {'):]
        block = block[:block.index('\n}')]
        self.assertIn('.dlux-ribbon-header-row', block)
        self.assertIn('grid-template-columns: minmax(0, 1fr);', block)
        self.assertNotIn('@media (max-width: 399.98px)', css)

    def test_skins_defer_to_the_shared_edge_radius_variable(self):
        css = self._ribbon_css()
        for skin in ('accent', 'panel'):
            block = css[css.index(f'.dlux-ribbon-skin-{skin} {{'):]
            block = block[:block.index('}')]
            self.assertIn('--dlux-ribbon-edge-radius', block)

    def _card_edge_radii(self):
        """(curved, normal) in rem, as `card_edges.css` declares them."""
        import re

        css = (Path(__file__).resolve().parents[1]
               / 'static' / 'dlux' / 'base' / 'css' / 'card_edges.css').read_text()
        normal_block = css[css.index('body[data-dlux-card-edges="normal"]'):]
        normal = float(re.search(r'--dlux-card-edge-radius:\s*([\d.]+)rem', normal_block).group(1))
        curved = float(re.search(r'--dlux-card-edge-radius:\s*([\d.]+)rem',
                                 css[:css.index('body[data-dlux-card-edges="normal"]')]).group(1))
        return curved, normal

    def test_card_edges_defines_both_states(self):
        """Defining only `normal` made the setting invisible: Bootstrap's own
        card radius is already 0.375rem, so curved rendered identically."""
        curved, normal = self._card_edge_radii()
        self.assertGreater(curved, normal,
                           f'curved ({curved}rem) must be rounder than normal ({normal}rem)')

    def test_card_edges_matches_the_table_edge_pair(self):
        """The two settings should read as one system, not two conventions."""
        import re

        tables = (Path(__file__).resolve().parents[1]
                  / 'static' / 'dlux' / 'tables' / 'css' / 'main.css').read_text()
        table_normal_block = tables[tables.index('body[data-dlux-table-edges="normal"]'):]
        table_normal = float(re.search(r'--dlux-table-edge-radius:\s*([\d.]+)rem', table_normal_block).group(1))
        table_curved = float(re.search(r'--dlux-table-edge-radius:\s*([\d.]+)rem', tables).group(1))
        self.assertEqual(self._card_edge_radii(), (table_curved, table_normal))

    def test_card_children_inherit_the_corner(self):
        """A child with its own opaque background repaints the corner square.

        Every theme except the light/colour palettes gives `.card-body` a solid
        background with `!important`, so a card that measured as rounded still
        looked square on them — the radius was right and invisible. The first
        child must take the top corners and the last the bottom ones.
        """
        css = (Path(__file__).resolve().parents[1]
               / 'static' / 'dlux' / 'base' / 'css' / 'card_edges.css').read_text()
        self.assertIn(':first-child', css)
        self.assertIn(':last-child', css)
        for prop in ('border-start-start-radius', 'border-start-end-radius',
                     'border-end-start-radius', 'border-end-end-radius'):
            self.assertIn(f'{prop}: inherit', css, f'{prop} is not inherited')

    def test_only_card_sections_use_the_generic_child_corner_rule(self):
        """Rounding any first/last child also caught a `.list-group` sitting at
        a card's edge, leaving its last row curved along the bottom and square
        along the top. Bootstrap already rounds a card's list-group from
        `--bs-card-inner-border-radius`, which this file sets."""
        rules = self._card_edges_rules()
        generic_rules = rules[
            rules.index('body :where('):rules.rindex('body[data-dlux-card-edges="half_rounded"]')
        ]
        self.assertNotIn('> :first-child', generic_rules)
        self.assertNotIn('> :last-child', generic_rules)
        for section in ('.card-body', '.card-header', '.card-footer'):
            self.assertIn(section, generic_rules)
        self.assertNotIn('.list-group', generic_rules)

    def test_half_rounded_repairs_the_bottom_list_group_corner(self):
        rules = self._card_edges_rules()
        half = rules[rules.index('body[data-dlux-card-edges="half_rounded"]'):]
        self.assertIn('.list-group:last-child', half)
        self.assertIn('.list-group-item:last-child', half)
        self.assertIn('--dlux-card-edge-bottom-radius', half)

    def _card_edges_rules(self):
        """`card_edges.css` with comments stripped.

        The prose explains what the rules deliberately avoid, so asserting
        against the raw file matches the explanation rather than the CSS.
        """
        import re

        css = (Path(__file__).resolve().parents[1]
               / 'static' / 'dlux' / 'base' / 'css' / 'card_edges.css').read_text()
        return re.sub(r'/\*.*?\*/', '', css, flags=re.S)

    def test_card_children_use_logical_corners(self):
        """Physical corners would put the rounding on the wrong side in RTL."""
        rules = self._card_edges_rules()
        child_rules = rules[rules.index('border-start-start-radius'):]
        for physical in ('border-top-left-radius', 'border-top-right-radius',
                         'border-bottom-left-radius', 'border-bottom-right-radius'):
            self.assertNotIn(physical, child_rules)

    def test_alerts_are_a_card_surface(self):
        """An alert is a panel; it looked wrong keeping a fixed corner beside
        cards that changed shape."""
        rules = self._card_edges_rules()
        self.assertIn('.alert,', rules)

    def test_no_page_pins_a_table_shell_radius(self):
        """`.dlux-table-shell` follows Table edges through
        `--dlux-table-edge-radius`. A page-level rule outranks that selector and
        pins every table on the page to one shape whatever the setting says."""
        import re

        root = Path(__file__).resolve().parents[1] / 'static' / 'dlux'
        offenders = []
        for css_file in root.rglob('*.css'):
            if css_file.name == 'main.css' and css_file.parent.name == 'tables':
                continue  # the shell's own rule, which reads the variable
            body = re.sub(r'/\*.*?\*/', '', css_file.read_text(), flags=re.S)
            for match in re.finditer(r'([^{}]*)\{([^}]*)\}', body):
                # `:not(.dlux-table-shell)` excludes the shell rather than
                # styling it, so strip those before deciding it matches.
                selector = re.sub(r':not\([^)]*\)', '', match.group(1))
                if '.dlux-table-shell' not in selector:
                    continue
                uses_edge_contract = any(
                    token in match.group(2)
                    for token in ('--dlux-table-edge-radius', '--dlux-table-edge-shape')
                )
                if 'border-radius' in match.group(2) and not uses_edge_contract:
                    offenders.append(f'{css_file.name}: {selector.strip()[:60]}')
        self.assertEqual(offenders, [])

    def test_inner_panels_follow_the_card_edge_setting(self):
        """A panel sitting inside a card looks wrong keeping its own corner
        while the card changes shape around it."""
        css = (Path(__file__).resolve().parents[1]
               / 'static' / 'dlux' / 'users' / 'css' / 'profile.css').read_text()
        block = css[css.index('.profile-session-row {'):]
        block = block[:block.index('}')]
        self.assertIn('var(--dlux-card-edge-shape', block)

    def test_a_progress_meter_opts_out_rather_than_cohering(self):
        """A card-sized radius on an 8px-tall track swallows the bar, so the
        completeness meter keeps its own proportions and says so explicitly."""
        html = (Path(__file__).resolve().parents[1]
                / 'templates' / 'dlux' / 'users' / 'profile.html').read_text()
        self.assertIn('class="completeness-container" data-dlux-card-edges-ignore', html)
        css = (Path(__file__).resolve().parents[1]
               / 'static' / 'dlux' / 'users' / 'css' / 'profile.css').read_text()
        for name in ('.completeness-container {', '.progress-custom {'):
            block = css[css.index(name):]
            block = block[:block.index('}')]
            self.assertNotIn('--dlux-card-edge-radius', block)
            self.assertNotIn('--dlux-card-edge-shape', block)

    def test_panel_surface_uses_a_theme_token_not_a_darkening_mix(self):
        """Mixing the body background toward the emphasis colour made a grey
        slab on the light and colour palettes, which do not restyle
        `glass-profile` and so never got a replacement surface."""
        css = self._ribbon_css()
        block = css[css.index('.dlux-ribbon-skin-panel {'):]
        block = block[:block.index('}')]
        background = [l for l in block.splitlines() if 'background' in l]
        self.assertTrue(background, 'the panel skin sets no background')
        self.assertNotIn('emphasis-color', background[0])
        self.assertIn('--bs-card-bg', background[0])

    def test_the_shape_applies_in_every_state(self):
        """The rule must not be scoped to one selector, or another state leaves
        every card at whatever Bootstrap gave it."""
        css = (Path(__file__).resolve().parents[1]
               / 'static' / 'dlux' / 'base' / 'css' / 'card_edges.css').read_text()
        selector = css[:css.index('--bs-card-border-radius')].rsplit('}', 1)[-1]
        self.assertNotIn('data-dlux-card-edges="normal"', selector,
                         'the radius rule is still gated on the normal setting')
        self.assertNotIn('data-dlux-card-edges="half_rounded"', selector,
                         'the radius rule is gated on the half-rounded setting')
        self.assertIn('border-radius: var(--dlux-card-edge-shape)', css)

    def test_half_rounded_is_square_on_top_and_curved_on_bottom(self):
        card_css = (Path(__file__).resolve().parents[1]
                    / 'static' / 'dlux' / 'base' / 'css' / 'card_edges.css').read_text()
        table_css = (Path(__file__).resolve().parents[1]
                     / 'static' / 'dlux' / 'tables' / 'css' / 'main.css').read_text()
        for css, prefix in ((card_css, 'card'), (table_css, 'table')):
            block = css[css.index(f'body[data-dlux-{prefix}-edges="half_rounded"]'):]
            block = block[:block.index('}')]
            self.assertIn(f'--dlux-{prefix}-edge-top-radius: 0;', block)
            self.assertIn(f'--dlux-{prefix}-edge-bottom-radius: 1.35rem;', block)
            self.assertIn(f'--dlux-{prefix}-edge-shape: 0 0 1.35rem 1.35rem;', block)

    def test_ribbon_uses_the_shared_card_shape(self):
        css = self._ribbon_css()
        self.assertIn('--dlux-ribbon-edge-shape: var(--dlux-card-edge-shape', css)
        for skin in ('accent', 'panel'):
            block = css[css.index(f'.dlux-ribbon-skin-{skin} {{'):]
            block = block[:block.index('}')]
            self.assertIn('border-radius: var(--dlux-ribbon-edge-shape', block)

    def test_curved_is_never_flatter_than_normal(self):
        """The ribbon skins read the same variable, so their fallback must not
        invert the setting either."""
        import re

        css = self._ribbon_css()
        match = re.search(r'--dlux-ribbon-edge-radius:\s*var\(--dlux-card-edge-radius,\s*([\d.]+)rem\)', css)
        self.assertIsNotNone(match, 'the curved fallback is not declared as a rem value')
        _curved, normal = self._card_edge_radii()
        self.assertGreater(float(match.group(1)), normal)

    def test_no_skin_hardcodes_a_radius_that_ignores_the_setting(self):
        """Flat is the one exception — it has no panel, so it has no corners."""
        css = self._ribbon_css()
        for skin in ('accent', 'panel'):
            block = css[css.index(f'.dlux-ribbon-skin-{skin} {{'):]
            block = block[:block.index('}')]
            for line in block.splitlines():
                if 'border-radius' in line:
                    self.assertIn('var(', line, f'{skin} pins its radius: {line.strip()}')


class LayoutStepOrderTests(TestCase):
    """The Layout step follows a house convention: sections in reading order,
    and within each section toggles first, then selectors, then fields, then
    builders. Pinned here because it is an editorial decision that a later edit
    would otherwise undo silently."""

    def _html(self):
        from dlux.forms.system_settings import SystemSettingsForm

        return Template('{% load crispy_forms_tags %}{% crispy form %}').render(
            Context({'form': SystemSettingsForm(
                instance=SystemSettings(is_configured=False), mode='setup')}))

    def _positions(self, html, names):
        out = {}
        for name in names:
            for needle in (f'name="{name}"', f"name='{name}'"):
                index = html.find(needle)
                if index != -1:
                    out[name] = index
                    break
            else:
                self.fail(f'{name} is not rendered at all')
        return out

    def _headings(self, html):
        """The rendered `<h6>` section headings, in document order.

        Matching on the heading markup rather than the bare words matters: the
        page also embeds every translation string as JSON, so a plain substring
        search finds those copies first.
        """
        import re

        return [(m.start(), re.sub(r'<[^>]+>', '', m.group(1)).strip())
                for m in re.finditer(r'<h6[^>]*>(.*?)</h6>', html, re.S)]

    def _step(self, html, first_heading, next_heading):
        headings = self._headings(html)
        start = next(i for i, name in headings if name == first_heading)
        end = next((i for i, name in headings if i > start and name == next_heading), len(html))
        return html[start:end]

    def _panel(self, html, slug):
        """One wizard panel, sliced by its position rather than by guessing
        which heading follows it.

        Slicing between two named headings assumed both the names and the order
        of the steps; renaming one section and moving Ribbon ahead of Components
        broke every test that used it, none of which was about either.
        """
        from dlux.system.constants import SETUP_STEP_INDEX

        panels = html.split('wizard-step')[1:]
        return panels[SETUP_STEP_INDEX[slug]]

    def _layout_step(self, html):
        return self._panel(html, 'layout')

    def _ribbon_step(self, html):
        return self._panel(html, 'ribbon')

    def test_section_order(self):
        """The ribbon has its own step now — it outgrew a section in Layout once
        it gained a builder, which is why the sidebar and navbar have theirs."""
        html = self._html()
        self.assertEqual(
            [name for _i, name in self._headings(self._layout_step(html))],
            ['Tables', 'Forms', 'Modals', 'Options Page'],
        )
        self.assertEqual(
            [name for _i, name in self._headings(self._ribbon_step(html))],
            ['List Page Ribbon', 'Tab Strips'],
        )

    def test_record_visibility_moved_to_access_and_security(self):
        headings = self._headings(self._html())
        order = [name for _i, name in headings]
        self.assertIn('Record Visibility', order)
        self.assertLess(order.index('Access & Security'), order.index('Record Visibility'))
        self.assertLess(order.index('Record Visibility'), order.index('List Page Ribbon'))

    def test_ribbon_section_puts_the_toggle_before_the_selectors(self):
        pos = self._positions(self._ribbon_step(self._html()),
                              ['ribbon_title', 'ribbon_style', 'ribbon_layout',
                               'ribbon_advanced_trigger'])
        self.assertLess(pos['ribbon_title'], pos['ribbon_style'])
        self.assertLess(pos['ribbon_style'], pos['ribbon_layout'])
        self.assertLess(pos['ribbon_layout'], pos['ribbon_advanced_trigger'])

    def test_tables_section_puts_toggles_first_then_density(self):
        pos = self._positions(self._layout_step(self._html()),
                              ['sticky_table_headers', 'resizable_table_columns',
                               'zebra_striping', 'default_table_density',
                               'row_actions_style'])
        for toggle in ('sticky_table_headers', 'resizable_table_columns', 'zebra_striping'):
            self.assertLess(pos[toggle], pos['default_table_density'],
                            f'{toggle} must precede the selectors')
        self.assertLess(pos['default_table_density'], pos['row_actions_style'])

    def test_edge_shape_lives_with_the_theme_not_the_components(self):
        """Edge shape is a surface decision and reaches far past tables — the
        ribbon, profile panels and list groups all read it — so it is asked for
        beside the palette, and before every builder that previews in it."""
        html = self._html()
        appearance = self._panel(html, 'appearance')
        self.assertIn('name="table_edges"', appearance)
        self.assertIn('name="card_edges"', appearance)

        components = self._layout_step(html)
        self.assertNotIn('name="table_edges"', components)
        self.assertNotIn('name="card_edges"', components)

    def test_the_builder_sits_in_the_ribbon_step(self):
        step = self._ribbon_step(self._html())
        self.assertIn('data-ribbon-builder', step)
        self.assertIn('name="ribbon_config"', step)

    def test_record_visibility_is_not_in_the_layout_step(self):
        step = self._layout_step(self._html())
        self.assertNotIn('show_audit_fields', step)
        self.assertNotIn('show_soft_deleted', step)

    def test_headings_are_matched_as_markup_not_bare_words(self):
        """Guards the helper itself. The page embeds the whole translation
        catalogue as JSON, so the bare words appear long before the Layout step
        and a plain substring search reads the sections in the wrong order."""
        html = self._html()
        bare = html.index('List Page Ribbon')
        heading = next(i for i, name in self._headings(html) if name == 'List Page Ribbon')
        self.assertLess(bare, heading,
                        'a bare search must land on the JSON copy, not the heading')
        self.assertEqual([n for _i, n in self._headings(html)].count('List Page Ribbon'), 1)


class RibbonSettingsOptionMetaTests(TestCase):
    """Every choice needs an entry in the widget's `option_meta`. A key that no
    longer matches its value renders with no icon and no description, so the
    option shows its bare value twice over."""

    SELECTOR_FIELDS = (
        'ribbon_layout', 'ribbon_style', 'ribbon_advanced_trigger',
        'notification_flash_position', 'notification_flash_size',
        'notification_flash_text_size', 'notification_auto_update',
    )

    def test_every_choice_has_matching_option_meta(self):
        from dlux.forms.system_settings import SystemSettingsForm

        form = SystemSettingsForm(instance=SystemSettings(is_configured=False), mode='modal')
        for name in self.SELECTOR_FIELDS:
            meta = getattr(form.fields[name].widget, 'option_meta', None) or {}
            values = {value for value, _label in form.fields[name].choices}
            self.assertEqual(
                values, set(meta),
                f'{name}: option_meta keys {sorted(meta)} do not match choices {sorted(values)}',
            )
            for value, entry in meta.items():
                # Size selectors use a letter instead of an icon, matching
                # `titlebar_title_size`; either is a usable surface.
                self.assertTrue(
                    entry.get('icon') or entry.get('surface_label'),
                    f'{name}={value} has neither an icon nor a surface label',
                )
                self.assertTrue(entry.get('description'), f'{name}={value} has no description')

    def test_selector_fields_are_not_plain_dropdowns(self):
        """A bare `Select` renders as an OS dropdown, which is what these were
        before; the dlux selector is the house control for a choice field."""
        from dlux.forms.system_settings import SystemSettingsForm
        from dlux.widgets import DluxChoiceSelectorWidget

        form = SystemSettingsForm(instance=SystemSettings(is_configured=False), mode='modal')
        for name in self.SELECTOR_FIELDS:
            self.assertIsInstance(form.fields[name].widget, DluxChoiceSelectorWidget, name)


class NotificationStepOrderTests(TestCase):
    """The Notifications section follows the same house order as Layout:
    toggles, then selectors, then fields."""

    def test_order(self):
        from dlux.forms.system_settings import SystemSettingsForm

        html = Template('{% load crispy_forms_tags %}{% crispy form %}').render(
            Context({'form': SystemSettingsForm(
                instance=SystemSettings(is_configured=False), mode='setup')}))

        def pos(name):
            for quote in ('"', "'"):
                index = html.find(f'id={quote}id_{name}{quote}')
                if index != -1:
                    return index
            self.fail(f'{name} is not rendered')

        toggles = ['notification_flash_enabled', 'notification_drawer_enabled',
                   'notification_badge_enabled', 'notification_bridge_enabled',
                   'notification_auto_crud_enabled', 'notification_auto_create',
                   'notification_auto_delete', 'notification_email_enabled',
                   'notification_email_default']
        selectors = ['notification_flash_position', 'notification_flash_size',
                     'notification_flash_text_size', 'notification_auto_update']
        fields = ['notification_flash_timeout_ms', 'notification_flash_max_visible']

        self.assertLess(max(pos(n) for n in toggles), min(pos(n) for n in selectors))
        self.assertLess(max(pos(n) for n in selectors), min(pos(n) for n in fields))


class RibbonSettingsTests(TestCase):
    """The layout keys must survive the real save path and reach the runtime
    config — the same pipeline contract as options_style and row_actions_style."""

    def test_defaults(self):
        cfg = normalize_layout_config({})
        for key, value in DEFAULT_LAYOUT.items():
            self.assertEqual(cfg[key], value)

    def test_invalid_values_fall_back(self):
        cfg = normalize_layout_config({
            'ribbon_layout': 'nope',
            'ribbon_style': 'nope',
            'ribbon_advanced_trigger': 'nope',
        })
        self.assertEqual(cfg['ribbon_layout'], 'default')
        self.assertEqual(cfg['ribbon_style'], 'accent')
        self.assertEqual(cfg['ribbon_advanced_trigger'], 'button')

    def test_valid_values_are_kept(self):
        cfg = normalize_layout_config({
            'ribbon_layout': 'compact',
            'ribbon_advanced_trigger': 'always',
            'ribbon_title': False,
        })
        self.assertEqual(cfg['ribbon_layout'], 'compact')
        self.assertEqual(cfg['ribbon_advanced_trigger'], 'always')
        self.assertFalse(cfg['ribbon_title'])

    def test_keys_are_exportable(self):
        for key in DEFAULT_LAYOUT:
            self.assertIn(key, SYSTEM_SETTINGS_EXPORT_FIELDS)

    def test_import_routes_into_layout_config_and_runtime(self):
        settings = SystemSettings.load()
        settings.is_configured = True
        settings.save()
        apply_system_settings_import(
            settings,
            {'ribbon_layout': 'stacked', 'ribbon_style': 'panel'},
            mark_configured=False,
        )
        reloaded = SystemSettings.load()
        self.assertEqual(reloaded.layout_config.get('ribbon_layout'), 'stacked')
        self.assertEqual(get_system_config().get('ribbon_layout'), 'stacked')
        self.assertEqual(get_system_config().get('ribbon_style'), 'panel')

    def test_title_off_survives_a_reload(self):
        """False is a real stored choice, not an absent one — a runtime path
        that tests truthiness would silently turn the title back on."""
        settings = SystemSettings.load()
        settings.is_configured = True
        settings.save()
        apply_system_settings_import(settings, {'ribbon_title': False}, mark_configured=False)
        self.assertFalse(SystemSettings.load().layout_config.get('ribbon_title'))
        # The runtime layer is where a truthiness test would lose it: the stored
        # JSON keeps False, but the override loop would skip the key and the
        # default (True) would win.
        self.assertIs(get_system_config().get('ribbon_title'), False)


class RibbonHeadingLayoutTests(TestCase):
    """The heading mirrors the reports hero: an icon tile, then the title and
    subtitle sharing one column beside it, then the actions.

    The icon used to sit inline inside the `h1`, which locked it against the
    title and left the subtitle nowhere sensible to go.
    """

    def _html(self, **kw):
        ribbon = _ribbon(title='Users', title_icon='bi bi-people', **kw)
        return Template('{% load dlux_tags %}{% dlux_ribbon ribbon %}').render(
            Context({'ribbon': ribbon, 'request': None}))

    def test_the_icon_is_its_own_tile_not_a_glyph_in_the_title(self):
        html = self._html()
        self.assertIn('<span class="dlux-ribbon-icon">', html)
        h1 = html[html.index('<h1>'):html.index('</h1>')]
        self.assertNotIn('<i ', h1)

    def test_the_title_and_subtitle_share_a_column(self):
        html = self._html(subtitle='Everything the system recorded.')
        copy = html[html.index('dlux-ribbon-copy'):html.index('dlux-ribbon-actions')]
        self.assertIn('<h1>', copy)
        self.assertIn('<p>', copy)

    def test_no_icon_means_no_empty_tile(self):
        ribbon = _ribbon(title='Users')
        html = Template('{% load dlux_tags %}{% dlux_ribbon ribbon %}').render(
            Context({'ribbon': ribbon, 'request': None}))
        self.assertNotIn('dlux-ribbon-icon', html)

    def test_heading_spacing_is_the_house_measure(self):
        """These are the reports hero's values, which the ribbon replaced — it
        is now the only implementation, so they are pinned here rather than
        compared against a second copy."""
        import re

        css = (Path(__file__).resolve().parents[1]
               / 'static' / 'dlux' / 'ribbon' / 'css' / 'ribbon.css').read_text()

        def decl(selector, prop):
            block = css[css.index(selector):]
            block = block[:block.index('}')]
            match = re.search(rf'(?<![\w-]){prop}:\s*([^;]+);', block)
            return match.group(1).strip() if match else None

        self.assertEqual(decl('.dlux-ribbon-header-row {', 'gap'), '1.5rem')
        self.assertEqual(decl('.dlux-ribbon-heading {', 'gap'), '1rem')
        self.assertEqual(decl('.dlux-ribbon-actions {', 'gap'), '.75rem')
        for prop, value in (('width', '3rem'), ('height', '3rem'),
                            ('border-radius', '1rem'), ('font-size', '1.35rem')):
            self.assertEqual(decl('.dlux-ribbon-icon {', prop), value)

    def test_the_heading_column_has_a_floor(self):
        """A bare `max-content` actions column never yields, so a wide action
        can crush the title into a column barely wider than one word."""
        import re

        css = (Path(__file__).resolve().parents[1]
               / 'static' / 'dlux' / 'ribbon' / 'css' / 'ribbon.css').read_text()
        block = css[css.index('.dlux-ribbon-header-row {'):]
        block = block[:block.index('}')]
        cols = re.search(r'grid-template-columns:\s*([^;]+);', block).group(1)
        self.assertIn('minmax(min(100%', cols, 'the heading has no floor')
        self.assertIn('minmax(0, max-content)', cols, 'the actions cannot yield')

    def test_backup_does_not_double_the_page_padding(self):
        html = (Path(__file__).resolve().parents[1]
                / 'templates' / 'dlux' / 'backup' / 'manage.html').read_text()
        self.assertIn('<div class="dlux-backup-page">', html)
        self.assertNotIn('container-fluid py-3', html)

    def test_the_backup_hero_it_replaced_is_gone(self):
        css = (Path(__file__).resolve().parents[1]
               / 'static' / 'dlux' / 'backup' / 'css' / 'manage.css').read_text()
        self.assertNotIn('.dlux-backup-hero', css)
        # The create control moved to a partial and still needs its styling.
        self.assertIn('.dlux-backup-create-row', css)
        self.assertIn('.dlux-backup-create-form', css)

    def test_reports_does_not_double_the_page_padding(self):
        """The shared content column already pads the page. The reports wrapper
        added a second helping, so its ribbon sat 12px further in and 16px
        further down than the same band on every other page."""
        html = (Path(__file__).resolve().parents[1]
                / 'templates' / 'dlux' / 'reports' / 'overview.html').read_text()
        self.assertIn('<div class="dlux-reports-page">', html)
        self.assertNotIn('container-fluid py-3', html)

    def test_the_reports_grid_owns_the_gap_under_its_ribbon(self):
        """A grid parent with a `gap` must not also collect the child's margin,
        or the header drifts away from its content."""
        css = (Path(__file__).resolve().parents[1]
               / 'static' / 'dlux' / 'reports' / 'css' / 'overview.css').read_text()
        block = css[css.index('.dlux-reports-page > .dlux-ribbon-header {'):]
        block = block[:block.index('}')]
        self.assertIn('margin-block-end: 0', block)

    def test_the_reports_hero_it_replaced_is_gone(self):
        """Leaving the old rules behind would mean two headers to keep in step,
        which is what the migration was for."""
        css = (Path(__file__).resolve().parents[1]
               / 'static' / 'dlux' / 'reports' / 'css' / 'overview.css').read_text()
        self.assertNotIn('.dlux-report-hero', css)
        self.assertNotIn('.dlux-report-exports', css)
        # The backup control moved to a partial and still needs its styling.
        self.assertIn('.dlux-report-backup-action', css)


class ManagementScreenNamingTests(TestCase):
    """`manage_<plural>` for the route, and the template name says whether it is
    a page or a fragment. Asserted so the distinction stays load-bearing."""

    def test_every_management_route_is_named_manage_something(self):
        from django.urls import reverse

        for name in ('manage_users', 'manage_scopes', 'manage_groups',
                     'manage_sections', 'manage_assets'):
            self.assertTrue(reverse(name), name)

    def test_pages_extend_a_base_and_partials_do_not(self):
        root = Path(__file__).resolve().parents[1] / 'templates' / 'dlux'
        for rel in ('users/manage_users.html', 'sections/manage_sections.html'):
            self.assertIn('{% extends', (root / rel).read_text(), f'{rel} is not a page')
        for rel in ('groups/_group_manager.html', 'scopes/_scope_manager.html'):
            body = (root / rel).read_text()
            self.assertNotIn('{% extends', body, f'{rel} is a page, not a fragment')

    def test_fragments_carry_the_underscore_prefix(self):
        root = Path(__file__).resolve().parents[1] / 'templates' / 'dlux'
        for rel in ('groups/_group_manager.html', 'scopes/_scope_manager.html'):
            self.assertTrue((root / rel).exists(), f'{rel} is missing')
            self.assertTrue(Path(rel).name.startswith('_'))


class ManagerModalRibbonTests(TestCase):
    """The group and scope managers are modal bodies, not pages, and were the
    last two dlux screens hand-rolling a title/action row."""

    def setUp(self):
        from django.contrib.auth import get_user_model

        self.admin = get_user_model().objects.create_superuser('root', 'r@e.com', 'pw')
        settings = SystemSettings.load()
        settings.is_configured = True
        settings.save()
        self.client.force_login(self.admin)

    def _body(self, route):
        import json

        from django.urls import reverse

        response = self.client.get(reverse(route))
        self.assertEqual(response.status_code, 200, route)
        return json.loads(response.content)['html']

    def test_both_managers_use_the_ribbon(self):
        for route in ('manage_groups', 'manage_scopes'):
            html = self._body(route)
            self.assertIn('dlux-ribbon-header', html, route)

    def test_the_managers_honour_the_configured_style(self):
        """A modal is not an excuse to ignore the administrator's choice."""
        settings = SystemSettings.load()
        layout = dict(settings.layout_config or {})
        layout['ribbon_style'] = 'accent'
        settings.layout_config = layout
        settings.save()
        for route in ('manage_groups', 'manage_scopes'):
            self.assertIn('dlux-ribbon-skin-accent', self._body(route), route)

    def test_the_scope_manager_is_translated(self):
        """Its title and button were hardcoded Arabic with no English at all."""
        html = self._body('manage_scopes')
        self.assertIn('Manage Scopes', html)
        self.assertIn('Add New Scope', html)

    def test_no_hardcoded_arabic_left_in_either_template(self):
        root = Path(__file__).resolve().parents[1] / 'templates' / 'dlux'
        for rel in ('scopes/_scope_manager.html', 'groups/_group_manager.html'):
            body = (root / rel).read_text()
            arabic = [ch for ch in body if '\u0600' <= ch <= '\u06ff']
            self.assertEqual(arabic, [], f'{rel} still carries literal Arabic')


class RibbonBuilderIconPickerTests(TestCase):
    """The inspector borrows the shared icon picker field rather than owning a grid.

    Two implementations of this existed. `dlux/helpers/icon_picker.html` is a
    self-contained field with a trigger and a collapsed body, bound to a named form
    field; the builders each had a second copy rendered inline and always open. The
    inline one rebuilt ~600 buttons on every render of the inspector, which is what
    made the Ribbon step drag, and inside a popover it filled the panel instead of
    dropping over it. The Sidebar and Ribbon builders now borrow the shared field.
    """

    BUILDER_JS = (
        Path(__file__).resolve().parent.parent
        / 'static' / 'dlux' / 'ribbon' / 'js' / 'ribbon_builder.js'
    )

    def test_the_builder_borrows_the_shared_picker_and_owns_no_grid(self):
        source = self.BUILDER_JS.read_text()
        self.assertIn("data-icon-field=\"ribbon_builder_entry_icon\"", source)
        self.assertIn('data-ribbon-icon-picker-holder', source)
        # No second implementation left behind.
        self.assertNotIn('function renderIconChoices', source)
        self.assertNotIn('ICON_SUGGESTIONS', source)
        self.assertNotIn('dlux-builder-icon-suggestions', source)

    def test_the_picker_is_server_rendered_once_and_parked(self):
        template = (
            Path(__file__).resolve().parent.parent
            / 'templates' / 'dlux' / 'setup' / 'ribbon_builder.html'
        ).read_text()
        self.assertIn("data-ribbon-icon-picker-holder", template)
        self.assertIn("field_name='ribbon_builder_entry_icon'", template)
        # `inline=False` is the collapsed-body form, which drops over the panel
        # instead of filling it.
        self.assertIn('inline=False', template)
        # The picker reports a pick by writing to the field its `field_name` names;
        # with no such field the pick goes nowhere.
        self.assertIn(
            'name="ribbon_builder_entry_icon" data-dlux-unsaved-ignore data-ribbon-icon-value',
            template,
        )

    def test_the_grid_opens_upward_when_there_is_no_room_below(self):
        """Near the bottom of a scrollable modal the grid would open past the edge
        that clips it, where it can be neither clicked nor scrolled to."""
        js = (
            Path(__file__).resolve().parent.parent
            / 'static' / 'dlux' / 'helpers' / 'icon_picker' / 'js' / 'main.js'
        ).read_text()

        self.assertIn('function placeBody()', js)
        # Room is the box that actually clips the grid, not the viewport: inside a
        # modal there is screen below it and none inside it.
        self.assertIn('function visibleBounds(element)', js)
        self.assertIn("overflowY === 'auto' || overflowY === 'scroll' || overflowY === 'hidden'", js)
        self.assertIn("body.classList.add('dlux-builder-icon-picker--above');", js)
        # Placed after the grid is built, so its height is the one being placed.
        self.assertLess(js.index('placeBody();'), js.index('search.focus();'))
        self.assertLess(js.index('renderSuggestions();\n'), js.index('placeBody();'))
        # And reset on close, or the next open inherits the last direction.
        self.assertIn("if (body) body.classList.remove('dlux-builder-icon-picker--above');", js)

        css = (
            Path(__file__).resolve().parent.parent
            / 'static' / 'dlux' / 'helpers' / 'icon_picker' / 'css' / 'main.css'
        ).read_text()
        self.assertIn('.dlux-builder-icon-picker--popover.dlux-builder-icon-picker--above', css)
        self.assertIn('inset-block-end: calc(100% + 0.45rem);', css)

    def test_an_icon_can_be_cleared_where_empty_is_a_real_answer(self):
        """A ribbon tab with no override keeps the icon the page already gives it, so
        clearing the box has to mean cleared. Both emptying it and Reset used to write
        the default straight back, leaving a bad icon name as the only way out."""
        js = (
            Path(__file__).resolve().parent.parent
            / 'static' / 'dlux' / 'helpers' / 'icon_picker' / 'js' / 'main.js'
        ).read_text()
        self.assertIn("const allowEmpty = picker.getAttribute('data-icon-allow-empty') === 'true';", js)
        self.assertIn("const value = raw || (allowEmpty ? '' : defaultIcon);", js)
        self.assertIn("apply(allowEmpty ? '' : defaultIcon)", js)

        template = (
            Path(__file__).resolve().parent.parent
            / 'templates' / 'dlux' / 'setup' / 'ribbon_builder.html'
        ).read_text()
        self.assertIn('allow_empty=True', template)
        # And the builder must not put an icon back on the way in.
        builder = self.BUILDER_JS.read_text()
        self.assertIn("const value = String(icon || '').trim();", builder)
        self.assertNotIn("String(icon || '').trim() || 'bi-tag'", builder)

    def test_a_removed_strip_can_still_be_restored(self):
        """Its tabs go inert when it is off, so they cannot carry the way back."""
        builder = self.BUILDER_JS.read_text()
        remove = builder[builder.index('function removeStripOf('):builder.index('function restoreStripOf(')]
        # Removing a declared strip keeps it selected, so Restore is already on screen.
        self.assertIn("selected = {\n                    type: 'strip',", remove)
        self.assertNotIn('selected = null;\n            commit();', remove)
        # And an off strip advertises the caption as the route back.
        self.assertIn("kind.classList.add('is-off');", builder)
        self.assertIn("t('removed_strip', 'removed')", builder)

        css = (
            Path(__file__).resolve().parent.parent
            / 'static' / 'dlux' / 'ribbon' / 'css' / 'ribbon.css'
        ).read_text()
        self.assertIn('.dlux-ribbon-builder__preview-kind.is-off', css)

    def test_a_pick_reaches_the_builder(self):
        source = self.BUILDER_JS.read_text()
        self.assertIn("refs.iconValue.addEventListener('input'", source)
        self.assertIn('iconTarget(String(refs.iconValue.value', source)
        # The borrowed node goes back to its holder so the next render can re-mount it.
        self.assertIn('refs.iconPickerHolder.appendChild(refs.iconPicker);', source)


class RibbonBuilderDoesNotDirtyTheFormTests(TestCase):
    """Opening the Ribbon step must not make an untouched form look edited.

    The builder writes `ribbon_config` as JSON, and so does the server — but not
    the same JSON: the server emits `{"labels": ..., "param": ...}` with a space
    after each separator, while `JSON.stringify` emits `param` first and no
    spaces. Same data, different bytes. The unsaved guard compares bytes, so a
    rewrite at init reads as an edit and prompts on every close.

    This stayed invisible while `ribbon_config` was empty, because both sides
    render `{}` identically; it appeared the moment a real strip was saved.

    A static check because the behaviour is JavaScript: what matters is that no
    commit happens on the way in, and every commit sits in an event handler.
    """

    def _source(self):
        return (
            Path(__file__).resolve().parent.parent
            / 'static' / 'dlux' / 'ribbon' / 'js' / 'ribbon_builder.js'
        ).read_text()

    def test_the_builder_does_not_write_the_field_on_open(self):
        source = self._source()
        self.assertNotIn(
            'renderAll();\n        commit();', source,
            'committing at init rewrites an untouched field and dirties the form',
        )


class RibbonSettingsFormTests(TestCase):
    """A setting nobody can reach is not a setting.

    These fields are declared with `HiddenInput` like their siblings, and are
    only made visible by binding a `DluxChoiceSelectorWidget`. Forgetting that
    bind leaves them in the POST and in `layout_config` — every pipeline test
    still passes — while the Layout step shows nothing at all.
    """

    def _form(self):
        from dlux.forms.system_settings import SystemSettingsForm

        return SystemSettingsForm(instance=SystemSettings(is_configured=False), mode='modal')

    def test_choice_fields_are_not_left_as_hidden_inputs(self):
        from dlux.widgets import DluxChoiceSelectorWidget

        form = self._form()
        for name in ('ribbon_layout', 'ribbon_style', 'ribbon_advanced_trigger'):
            self.assertIsInstance(
                form.fields[name].widget,
                DluxChoiceSelectorWidget,
                f'{name} renders as a hidden input, so it is invisible in Settings',
            )

    def test_every_choice_renders_as_a_selectable_option(self):
        html = Template('{% load crispy_forms_tags %}{% crispy form %}').render(
            Context({'form': self._form()}))
        expected = {
            'ribbon_layout': ('default', 'stacked', 'compact'),
            'ribbon_style': ('accent', 'panel', 'flat'),
            'ribbon_advanced_trigger': ('button', 'always', 'off'),
        }
        for name, values in expected.items():
            for value in values:
                self.assertIn(
                    f'name="{name}" type="radio" value="{value}"', html,
                    f'{name}={value} is not offered in the Layout step',
                )

    def test_the_title_toggle_is_reachable_too(self):
        html = Template('{% load crispy_forms_tags %}{% crispy form %}').render(
            Context({'form': self._form()}))
        self.assertIn("id='id_ribbon_title'", html.replace('"', "'"))

    def test_fields_sit_in_the_layout_step(self):
        """They must be in the Layout step's own field list, not merely present
        somewhere in the form."""
        from dlux.system.settings_diff import GROUPS

        layout = next(fields for key, _label, fields in GROUPS if key == 'layout')
        for name in ('ribbon_layout', 'ribbon_style', 'ribbon_title',
                     'ribbon_advanced_trigger'):
            self.assertIn(name, layout)


class RibbonRenderingTests(TestCase):
    """Every style must fill every region it is configured to show."""

    def _render(self, layout=None, **kwargs):
        ribbon = _ribbon(layout=layout, title='Users', **kwargs)
        return Template(
            '{% load dlux_tags %}{% dlux_ribbon ribbon %}'
        ).render(Context({'ribbon': ribbon, 'request': None}))

    def test_the_separator_selector_matches_the_strips_wrapper(self):
        """The rule under the title is drawn by an adjacent-sibling selector, and
        nothing complains when one stops matching — the heading just goes flush
        against the tabs. It broke exactly that way when strips gained a wrapper,
        so the stylesheet is checked against the class the template gives it.
        """
        import re
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        strips = (root / 'templates' / 'dlux' / 'ribbon' / '_strips.html').read_text()
        wrappers = set()
        for classes in re.findall(r'class="([^"]*dlux-ribbon-strips[^"]*)"', strips):
            wrappers.update(classes.split())
        self.assertTrue(wrappers, '_strips.html no longer has a strips wrapper')

        css = (root / 'static' / 'dlux' / 'ribbon' / 'css' / 'ribbon.css').read_text()
        for pattern, what in (
            (r'\.dlux-ribbon-header-row \+ \.([\w-]+)', 'the separator under the title'),
            (r'\.([\w-]+) \+ \.dlux-ribbon-filter', 'the gap above the filter row'),
        ):
            targets = set(re.findall(pattern, css))
            self.assertTrue(
                targets.intersection(wrappers),
                '{} does not reach {}'.format(what, sorted(wrappers)),
            )

    def test_each_style_renders_its_own_variant(self):
        for style in ('default', 'stacked', 'compact'):
            html = self._render({'ribbon_layout': style})
            self.assertIn(f'dlux-ribbon-layout-{style}', html)

    def test_every_style_renders_the_filters(self):
        for style in ('default', 'stacked', 'compact'):
            html = self._render({'ribbon_layout': style})
            self.assertIn('name="keyword"', html)
            self.assertIn('name="is_staff"', html)

    def test_title_toggle(self):
        self.assertIn('<h1>', self._render({'ribbon_title': True}))
        self.assertNotIn('<h1>', self._render({'ribbon_title': False}))

    def test_advanced_trigger_off_hides_the_panel_and_its_fields(self):
        html = self._render({'ribbon_advanced_trigger': 'off'})
        self.assertNotIn('dlux-ribbon-advanced', html)
        self.assertNotIn('name="is_staff"', html)

    def test_advanced_trigger_always_opens_the_panel_without_a_toggle(self):
        html = self._render({'ribbon_advanced_trigger': 'always'})
        self.assertIn('dlux-ribbon-advanced', html)
        self.assertNotIn('dlux-ribbon-toggle', html)

    def test_advanced_trigger_button_renders_a_collapsed_panel(self):
        html = self._render({'ribbon_advanced_trigger': 'button'})
        self.assertIn('dlux-ribbon-toggle', html)
        self.assertIn('collapse', html)

    def test_range_renders_both_ends(self):
        html = self._render({'ribbon_advanced_trigger': 'always'})
        self.assertIn('name="date_joined__gte"', html)
        self.assertIn('name="date_joined__lte"', html)

    def test_tag_renders_nothing_without_a_ribbon(self):
        html = Template('{% load dlux_tags %}{% dlux_ribbon %}').render(Context({}))
        self.assertEqual(html.strip(), '')


class AdvancedFilterHelperUnchangedTests(TestCase):
    """Five projects still call the old helper. It must behave exactly as it
    did until it is removed in v1.9.0."""

    def test_helper_is_still_exported_and_builds_a_layout(self):
        from dlux.utils import advanced_filter_helper

        # The helper assigns onto `form.helper` and returns nothing.
        filterset = UserFilterSet({})
        advanced_filter_helper(filterset, config={'fields': ['keyword']})
        helper = filterset.form.helper
        self.assertEqual(helper.form_method, 'get')
        self.assertIn('dlux-filter', helper.form_class)
        self.assertEqual(helper.attrs.get('data-dlux-filter-autosubmit'), 'true')

    def test_helper_and_ribbon_do_not_share_a_js_hook(self):
        """Both scripts can be on the same page; if they targeted the same
        form, a select change would submit it twice."""
        from dlux.utils import advanced_filter_helper

        filterset = UserFilterSet({})
        advanced_filter_helper(filterset, config={'fields': ['keyword']})
        self.assertNotIn('dlux-ribbon', filterset.form.helper.form_class)
        rendered = Template('{% load dlux_tags %}{% dlux_ribbon ribbon %}').render(
            Context({'ribbon': _ribbon(), 'request': None})
        )
        self.assertNotIn('data-dlux-filter-autosubmit', rendered)
        self.assertNotIn('dlux-filter-toggle', rendered)


class BuilderSplitFieldTests(TestCase):
    """A strip an operator draws must say which field it splits on.

    This is the whole point of a strip. Without it the builder wrote
    `sources: [{type: 'all'}]` — a strip whose only tab is "All", with nothing to
    order, rename or hide — and offered no way to say otherwise, for existing
    pages and brand-new ones alike. It rendered as an empty preview with a note
    promising tabs that could never arrive.
    """

    BUILDER_JS = (
        Path(__file__).resolve().parent.parent
        / 'static' / 'dlux' / 'ribbon' / 'js' / 'ribbon_builder.js'
    )
    BUILDER_HTML = (
        Path(__file__).resolve().parent.parent
        / 'templates' / 'dlux' / 'setup' / 'ribbon_builder.html'
    )

    def test_the_add_bar_asks_which_field_to_split_on(self):
        markup = self.BUILDER_HTML.read_text()
        self.assertIn('data-ribbon-new-field', markup)

    def test_the_add_bar_asks_how_the_extra_strip_relates(self):
        markup = self.BUILDER_HTML.read_text()
        self.assertIn('data-ribbon-new-relation', markup)

    def test_an_admin_made_strip_can_change_its_split_field(self):
        markup = self.BUILDER_HTML.read_text()
        self.assertIn('data-strip-field', markup)
        self.assertIn("querySelector('[data-strip-field]')", self.BUILDER_JS.read_text())

    def test_a_new_strip_is_not_built_from_an_all_source_alone(self):
        source = self.BUILDER_JS.read_text()
        self.assertNotIn(
            "= [{ type: 'all' }];", source,
            'a strip whose only source is "all" has no tabs to draw',
        )
        self.assertIn('sourcesFor(', source)

    def test_an_all_only_strip_really_does_have_nothing_to_split(self):
        """Why the above matters, proven against the tab builder itself."""
        from django.contrib.auth.models import User

        from dlux.ribbon.tabs import build_ribbon_tabs

        all_only = list(build_ribbon_tabs(
            model=User, config={'param': 'p', 'sources': [{'type': 'all'}]}))
        with_split = list(build_ribbon_tabs(
            model=User,
            config={'param': 'p',
                    'sources': [{'type': 'all'}, {'type': 'flag', 'field': 'is_active'}]}))

        self.assertEqual(len(all_only), 1)
        self.assertGreater(len(with_split), len(all_only))

    def test_the_all_tab_leads_a_drawn_strip(self):
        """Without it a reader has no way back to the unfiltered list."""
        source = self.BUILDER_JS.read_text()
        body = source[source.index('function sourcesFor'):source.index('function splitFieldOf')]
        # The line that builds the real strip, not the no-field early return —
        # measuring the whole slice found that one first and passed either way.
        built = next(line for line in body.splitlines() if 'field.kind' in line)
        self.assertLess(built.index("type: 'all'"), built.index('field.kind'))


class BuilderTabPreviewTests(TestCase):
    """A strip drawn in Settings has to show the tabs it will draw.

    Without them an extra strip could choose its criteria but rendered no tabs,
    so there was nothing to reorder, rename or hide. Only the server can produce
    that preview, because a strip over a relation is one tab per row.
    """

    def setUp(self):
        from django.contrib.auth import get_user_model

        from dlux.models import SystemSettings

        # Otherwise every request is caught by the initial-setup gate and
        # answered with a redirect, whatever the endpoint would have said.
        SystemSettings.objects.all().delete()
        settings_row = SystemSettings.load()
        settings_row.is_configured = True
        settings_row.save()

        self.url = reverse('ribbon_tabs_preview')
        User = get_user_model()
        self.admin = User.objects.create_superuser('ribbon-admin', 'a@example.com', 'pw')
        self.plain = User.objects.create_user('ribbon-plain', 'b@example.com', 'pw')

    def _post(self, payload, user=None):
        client = Client()
        client.force_login(user or self.admin)
        return client.post(self.url, data=json.dumps(payload),
                           content_type='application/json')

    def test_it_draws_the_tabs_a_flag_source_would_produce(self):
        response = self._post({
            'model': 'auth.User', 'param': 'is_active',
            'sources': [{'type': 'all'}, {'type': 'flag', 'field': 'is_active'}],
        })
        self.assertEqual(response.status_code, 200)
        tabs = response.json()['tabs']
        self.assertGreater(len(tabs), 1)
        self.assertEqual(tabs[0]['key'], '')

    def test_an_all_only_strip_previews_as_the_single_tab_it_is(self):
        response = self._post({
            'model': 'auth.User', 'param': 'p', 'sources': [{'type': 'all'}],
        })
        self.assertEqual(len(response.json()['tabs']), 1)

    def test_it_refuses_a_model_the_builder_does_not_offer(self):
        """Otherwise it would enumerate rows of any table by name."""
        response = self._post({'model': 'auth.Permission', 'sources': [{'type': 'all'}]})
        self.assertEqual(response.status_code, 404)

    def test_it_refuses_a_reader_who_cannot_edit_settings(self):
        response = self._post({'model': 'auth.User', 'sources': [{'type': 'all'}]},
                              user=self.plain)
        self.assertEqual(response.status_code, 403)

    def test_a_broken_strip_is_a_400_not_a_500(self):
        """The operator is mid-edit; a half-built strip is normal here."""
        response = self._post({
            'model': 'auth.User', 'param': 'p',
            'sources': [{'type': 'no-such-source-type'}],
        })
        self.assertEqual(response.status_code, 400)


class BuilderExtraStripTests(TestCase):
    """Declared strips and admin-made strips are different rows."""

    BUILDER_JS = (
        Path(__file__).resolve().parent.parent
        / 'static' / 'dlux' / 'ribbon' / 'js' / 'ribbon_builder.js'
    )

    def test_the_picker_is_only_for_admin_made_strips(self):
        source = self.BUILDER_JS.read_text()
        self.assertIn("if (picker && strip.origin === 'extra') {", source)
        self.assertNotIn('if (picker && !locked) {', source)

    def test_existing_strips_do_not_block_adding_extra_strips(self):
        source = self.BUILDER_JS.read_text()
        body = source[source.index('function setupAddStripControls'):source.index('function addCustomAction')]
        self.assertNotIn('stripsOf(model.key).length', body)
        self.assertIn('model.locked || !model.fields.length', body)

    def test_the_builder_writes_extra_strips_separately(self):
        source = self.BUILDER_JS.read_text()
        self.assertIn('modelEntry.extra_strips = extra;', source)
        self.assertIn('readExtraStrips', source)

    def test_the_builder_preserves_custom_actions(self):
        source = self.BUILDER_JS.read_text()
        self.assertIn('readCustomActions', source)
        self.assertIn('modelEntry.custom_actions = customOut;', source)

    def test_predefined_and_extra_strips_have_separate_hosts(self):
        template = (
            Path(__file__).resolve().parent.parent
            / 'templates' / 'dlux' / 'setup' / 'ribbon_builder.html'
        ).read_text()
        self.assertIn('data-model-declared-strips', template)
        self.assertIn('data-model-extra-strips', template)

    def test_add_strip_controls_are_inside_each_ribbon_host(self):
        template = (
            Path(__file__).resolve().parent.parent
            / 'templates' / 'dlux' / 'setup' / 'ribbon_builder.html'
        ).read_text()
        self.assertIn('data-model-add-strip', template)
        self.assertNotIn('data-ribbon-model aria-label', template)

    def test_the_hand_rolled_inspector_templates_are_gone(self):
        template = (
            Path(__file__).resolve().parent.parent
            / 'templates' / 'dlux' / 'setup' / 'ribbon_builder.html'
        ).read_text()
        self.assertIn('data-ribbon-action-template', template)
        # The shell renders both inspectors now.
        self.assertNotIn('data-ribbon-action-inspector-template', template)
        self.assertNotIn('data-ribbon-inspector-template', template)
        self.assertNotIn('data-ribbon-clear-selection', template)
        self.assertNotIn('data-model-inspector', template)
        self.assertNotIn('data-ribbon-label-inputs', template)
        self.assertNotIn('data-ribbon-shown', template)
        # Per-strip Remove/Restore moved into the inspector's action row.
        self.assertNotIn('data-strip-tools', template)

    def test_one_builder_level_shell_hosts_every_inspector(self):
        template = (
            Path(__file__).resolve().parent.parent
            / 'templates' / 'dlux' / 'setup' / 'ribbon_builder.html'
        ).read_text()
        self.assertIn('data-ribbon-inspector-shell', template)
        # The host sits outside the per-model template, which is re-cloned on every
        # render — a shell created inside it would be rebuilt (and re-bound) each time.
        model_template = template[
            template.index('<template data-ribbon-model-template>'):
            template.index('<template data-ribbon-strip-row-template>')
        ]
        self.assertNotIn('data-ribbon-inspector-shell', model_template)
        # Add strip and Add button stay where they were.
        self.assertIn('data-model-add-strip', model_template)
        self.assertIn('data-model-add-action', model_template)

    def test_tab_inspector_is_driven_by_the_shell_adapter(self):
        source = self.BUILDER_JS.read_text()
        self.assertIn('window.DluxInspectorShell.create(refs.inspectorShell', source)
        self.assertIn("presentation: 'popover'", source)
        # The ribbon has no builder-level toolbar, so the actions ride in the panel.
        self.assertIn("actionsPlacement: 'panel'", source)
        self.assertIn('dismissOnOutsideClick: true', source)
        self.assertNotIn('function renderTabInspector', source)
        self.assertNotIn('function renderActionInspector', source)
        self.assertNotIn('function renderLanguageInputs', source)
        strip_renderer = source[
            source.index('function renderStripRow'):
            source.index('function renderActionPill')
        ]
        self.assertNotIn('renderTabInspector', strip_renderer)

    def test_extra_strip_rows_pass_the_strip_to_the_renderer(self):
        source = self.BUILDER_JS.read_text()
        self.assertIn('renderStripRow(model.key, strip, extraHost || declaredHost, model.locked)', source)
        self.assertNotIn('renderStripRow(model.key, extraHost || declaredHost, model.locked)', source)

    def test_admin_made_strips_say_remove_not_restore(self):
        source = self.BUILDER_JS.read_text()
        self.assertIn("strip.origin === 'declared'", source)
        # Both live in the inspector's action row now and act on the strip that owns
        # the selected entry; only a declared strip offers Restore.
        actions = source[source.index('function stripActions('):source.index('function iconField(')]
        self.assertIn("id: 'restore-strip'", actions)
        self.assertIn("id: 'remove-strip'", actions)
        self.assertIn("if (found.strip.origin === 'declared') {", actions)
        self.assertLess(actions.index("id: 'restore-strip'"), actions.index("id: 'remove-strip'"))
        self.assertIn("t('restore_strip', 'Restore')", actions)
        self.assertIn("t('remove_strip', 'Remove')", actions)

    def test_a_strip_with_no_tabs_is_still_reachable(self):
        """Remove/Restore moved into the inspector, which opens on a selected entry.

        A strip whose split produces no tabs has no pill to select, so without a
        strip-level selection an admin could never remove one they mis-created.
        """
        source = self.BUILDER_JS.read_text()
        self.assertIn("type: 'strip',", source)
        self.assertIn('function selectedStrip()', source)
        template = (
            Path(__file__).resolve().parent.parent
            / 'templates' / 'dlux' / 'setup' / 'ribbon_builder.html'
        ).read_text()
        self.assertIn('<button type="button" class="dlux-ribbon-builder__preview-kind" data-strip-kind>', template)


class BuilderCriteriaLabelTests(TestCase):
    """The picker must show the criteria a strip is actually split on.

    A declared strip's catalog entry carried its param, relation, label and
    tabs but not what it split on, so the picker had nothing to select and the
    browser fell back to whichever field sorted first — a confident label for
    the wrong answer, on every page that already had tabs.
    """

    BUILDER_JS = (
        Path(__file__).resolve().parent.parent
        / 'static' / 'dlux' / 'ribbon' / 'js' / 'ribbon_builder.js'
    )

    def test_a_declared_strip_reports_the_field_it_splits_on(self):
        from django.contrib.auth.models import User

        from dlux.ribbon.catalog import _declared_strips

        strips = _declared_strips(
            {'param': 'is_active',
             'sources': [{'type': 'all'}, {'type': 'flag', 'field': 'is_active'}]},
            User, None)
        self.assertEqual(strips[0]['field'], 'is_active')

    def test_a_strip_that_splits_on_no_field_reports_none(self):
        """A static-only strip is not describable by the dropdown, and says so."""
        from django.contrib.auth.models import User

        from dlux.ribbon import RibbonTab, RibbonTabs
        from dlux.ribbon.catalog import _declared_strips

        strips = _declared_strips(
            {'param': 'state',
             'sources': [{'type': 'static', 'key': 'a', 'label': 'A'}]},
            User, None)
        self.assertEqual(strips[0]['field'], '')

        strips = _declared_strips(
            RibbonTabs(param='status', items=[RibbonTab(key='open', label='Open')]),
            User, None)
        self.assertEqual(strips[0]['param'], 'status')
        self.assertEqual(strips[0]['tabs'][0]['key'], 'open')

    def test_only_the_first_field_source_is_reported(self):
        """One dropdown cannot describe a strip mixing several splits."""
        from django.contrib.auth.models import User

        from dlux.ribbon.catalog import _declared_strips

        strips = _declared_strips(
            {'param': 'p',
             'sources': [{'type': 'flag', 'field': 'is_staff'},
                         {'type': 'flag', 'field': 'is_active'}]},
            User, None)
        self.assertEqual(strips[0]['field'], 'is_staff')

    def test_declared_strips_do_not_use_the_picker_as_a_criteria_control(self):
        source = self.BUILDER_JS.read_text()
        self.assertNotIn("(strip.field || '')", source)
        self.assertIn("strip.origin === 'extra'", source)

    def test_an_unmatched_criteria_is_described_not_guessed(self):
        source = self.BUILDER_JS.read_text()
        self.assertIn("t('split_none', 'Not split by a field')", source)
        self.assertIn("t('split_custom', 'Currently: ')", source)


class RibbonCatalogFailuresAreVisibleTests(TestCase):
    """An empty builder in production looked identical to a project with no ribbon
    hosts: nothing in the server log, nothing in the browser console."""

    def test_blanking_the_catalog_is_logged(self):
        from unittest.mock import patch

        from dlux.ribbon.catalog import _ribbon_view_hosts

        with patch('dlux.ribbon.catalog.get_resolver', side_effect=RuntimeError('boom')):
            with self.assertLogs('dlux', level='WARNING') as captured:
                self.assertEqual(_ribbon_view_hosts(), [])
        self.assertIn('no ribbon hosts', '\n'.join(captured.output))

    def test_unwalkable_urlconf_is_logged(self):
        from unittest.mock import patch

        from dlux.ribbon.catalog import _ribbon_view_hosts

        with patch('dlux.ribbon.catalog._iter_named_patterns', side_effect=ImportError('nope')):
            with self.assertLogs('dlux', level='WARNING') as captured:
                self.assertEqual(_ribbon_view_hosts(), [])
        self.assertIn('named URL patterns', '\n'.join(captured.output))

    def test_blanking_the_destination_catalog_is_logged(self):
        from unittest.mock import patch

        from dlux.ribbon.catalog import ribbon_destination_catalog

        with patch('dlux.discovery.discover_routes', side_effect=RuntimeError('boom')):
            with self.assertLogs('dlux', level='WARNING') as captured:
                self.assertEqual(ribbon_destination_catalog(), [])
        self.assertIn('no destinations', '\n'.join(captured.output))

    def test_client_side_parse_failure_is_reported(self):
        from pathlib import Path

        js = (Path(__file__).resolve().parents[1]
              / 'static' / 'dlux' / 'ribbon' / 'js' / 'ribbon_builder.js').read_text(encoding='utf-8')

        self.assertIn('function parse(value, fallback, name)', js)
        self.assertIn('could not parse its ${name} payload', js)
        for attr in ('catalog', 'destinations', 'strings', 'languages', 'config'):
            self.assertIn(f"parse(root.dataset.{attr}, ", js)
            self.assertIn(f", '{attr}');", js)
