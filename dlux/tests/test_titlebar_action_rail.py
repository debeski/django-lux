from pathlib import Path

from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase

from dlux.system.constants import (
    TITLEBAR_ACTIONS_LAYOUT_GROUPED,
    TITLEBAR_ACTIONS_LAYOUT_SCATTERED,
)
from dlux.utils import default_titlebar_config, normalize_titlebar_config

STATIC = Path(__file__).resolve().parents[1] / 'static' / 'dlux'
TEMPLATES = Path(__file__).resolve().parents[1] / 'templates' / 'dlux'


def _read(*parts):
    return Path(*parts).read_text(encoding='utf-8')


class _RailUser:
    is_authenticated = True
    username = 'railtester'
    scope = None

    def get_full_name(self):
        return 'Rail Tester'


def _titlebar(**titlebar_overrides):
    request = RequestFactory().get('/')
    request.user = _RailUser()
    config = default_titlebar_config()
    config.update(titlebar_overrides)
    return render_to_string('dlux/titlebar/main.html', {
        'request': request,
        'user': request.user,
        'sidebar_enabled': True,
        'sidebar': {'collapse_mode': 'icons'},
        'titlebar': config,
        'DLUX_STRINGS': {},
        'APP_CONFIG': {},
    })


class TitlebarActionsLayoutSettingTests(TestCase):
    def test_scattered_is_the_default_so_existing_installs_do_not_move(self):
        self.assertEqual(
            default_titlebar_config()['actions_layout'],
            TITLEBAR_ACTIONS_LAYOUT_SCATTERED,
        )

    def test_normalizer_keeps_known_values_and_falls_back_otherwise(self):
        self.assertEqual(
            normalize_titlebar_config({'actions_layout': TITLEBAR_ACTIONS_LAYOUT_GROUPED})['actions_layout'],
            TITLEBAR_ACTIONS_LAYOUT_GROUPED,
        )
        self.assertEqual(
            normalize_titlebar_config({'actions_layout': 'sideways'})['actions_layout'],
            TITLEBAR_ACTIONS_LAYOUT_SCATTERED,
        )
        self.assertEqual(
            normalize_titlebar_config({})['actions_layout'],
            TITLEBAR_ACTIONS_LAYOUT_SCATTERED,
        )

    def test_setting_is_a_dlux_selector_beside_the_user_hub_style(self):
        form_source = _read(Path(__file__).resolve().parents[1], 'forms', 'system_settings.py')
        layout_source = _read(
            Path(__file__).resolve().parents[1], 'forms', 'system_settings_groups', 'layout.py'
        )

        self.assertIn("titlebar_actions_layout = forms.ChoiceField(", form_source)
        self.assertIn("self.fields['titlebar_actions_layout'],", form_source)
        self.assertIn("'actions_layout': cleaned.get('titlebar_actions_layout'", form_source)
        self.assertIn("Div(Field('titlebar_actions_layout'), css_class='col-lg-12')", layout_source)
        self.assertLess(
            layout_source.index("Field('titlebar_actions_layout')"),
            layout_source.index("Field('titlebar_user_hub_style')"),
        )


class TitlebarActionRailMarkupTests(TestCase):
    def test_caret_sits_before_the_user_hub_trigger(self):
        html = _titlebar()

        self.assertIn('data-dlux-titlebar-rail-toggle', html)
        self.assertLess(
            html.index('data-dlux-titlebar-rail-toggle'),
            html.index('id="dlux-user-dropdown-trigger"'),
        )

    def test_home_and_the_hub_trigger_are_not_in_the_same_group_as_the_rest(self):
        html = _titlebar()

        # Home stays in the action group (it is never grouped away); the caret and
        # the hub trigger form the constants cluster that closes the end side.
        constants = html.split('class="titlebar__constants"')[1]
        self.assertIn('data-dlux-titlebar-rail-toggle', constants)
        self.assertIn('id="dlux-user-dropdown-trigger"', constants)
        self.assertNotIn('data-titlebar-home', constants)

    def test_layout_and_effective_state_both_ride_on_the_titlebar(self):
        scattered = _titlebar()
        grouped = _titlebar(actions_layout=TITLEBAR_ACTIONS_LAYOUT_GROUPED)

        self.assertIn('data-titlebar-actions-layout="scattered"', scattered)
        self.assertIn('data-titlebar-actions-grouped="false"', scattered)
        # Seeded server-side so a configured caret does not flash its actions
        # onto the bar before the script runs.
        self.assertIn('data-titlebar-actions-layout="grouped"', grouped)
        self.assertIn('data-titlebar-actions-grouped="true"', grouped)

    def test_rail_renders_empty_and_outside_the_bar(self):
        html = _titlebar()

        self.assertIn('id="dlux-titlebar-rail"', html)
        # Outside `.titlebar`: the bar is a stacking context and its Glass surface
        # sets a backdrop-filter, either of which would box in the rail's panels.
        self.assertLess(html.index('class="titlebar shadow-sm'), html.index('id="dlux-titlebar-rail"'))
        rail = html.split('id="dlux-titlebar-rail"')[1].split('</div>')[0]
        self.assertNotIn('<button', rail)
        self.assertNotIn('<a ', rail)

    def test_base_loads_the_rail_script_after_the_hub_it_coordinates_with(self):
        base = _read(TEMPLATES, 'base.html')

        self.assertIn("dlux_static 'dlux/titlebar/js/action_rail.js'", base)
        self.assertLess(
            base.index('dlux/titlebar/js/user_hub.js'),
            base.index('dlux/titlebar/js/action_rail.js'),
        )


class TitlebarActionRailBehaviourTests(TestCase):
    def setUp(self):
        self.js = _read(STATIC, 'titlebar', 'js', 'action_rail.js')

    def test_home_the_caret_and_the_hub_trigger_never_group(self):
        for selector in (
            "'.dlux-titlebar-home'",
            "'[data-titlebar-home]'",
            "'[data-titlebar-action-key=\"home\"]'",
            "'.dlux-user-trigger'",
            "'.dlux-titlebar-rail-toggle'",
        ):
            self.assertIn(selector, self.js)

    def test_only_the_active_action_group_is_collected(self):
        # Both groups always render and CSS hides the unused one, second notification
        # bell included. Lifting a child out of the hidden group would show it.
        self.assertIn("child.dataset.titlebarActionsGroup !== activeGroup", self.js)
        self.assertIn("titlebar.dataset.titlebarUserHubStyle === 'titlebar_actions'", self.js)
        # And the unread badge mirrored onto the caret is that group's, not
        # whichever copy comes first in the document.
        self.assertIn("node.querySelector('[data-dlux-notifications-badge]')", self.js)
        self.assertNotIn("document.querySelector('[data-dlux-notifications-badge]')", self.js)

    def test_grouping_moves_nodes_so_panels_travel_with_their_toggles(self):
        self.assertIn('rail.appendChild(node)', self.js)
        self.assertIn('placeholder.parentNode.insertBefore(node, placeholder.nextSibling)', self.js)

    def test_grouped_when_configured_or_on_mobile_or_when_it_cannot_fit(self):
        self.assertIn("titlebar.dataset.titlebarActionsLayout === 'grouped'", self.js)
        self.assertIn("const MOBILE_QUERY = '(max-width: 575.98px)';", self.js)
        self.assertIn('|| !scatteredFits();', self.js)

    def test_fit_decision_cannot_depend_on_its_own_outcome(self):
        # A grouped node sits in a closed rail and measures 0, and a wrapper that
        # holds one measures differently once it leaves — either would flap.
        self.assertIn('node.__dluxNaturalWidth = width;', self.js)
        self.assertIn('if (!grouped) {', self.js)
        self.assertIn('items.some(function (item) { return node.contains(item); })', self.js)

    def test_titlebar_appearance_attributes_are_mirrored_onto_the_rail(self):
        for attribute in (
            'data-titlebar-buttons-shape',
            'data-titlebar-home-shape',
            'data-titlebar-show-home',
            'data-titlebar-show-language-switcher',
        ):
            self.assertIn(f"'{attribute}'", self.js)
        self.assertIn('new MutationObserver(mirror).observe(titlebar', self.js)
        # System Settings previews the selector on the live titlebar.
        self.assertIn("attributeFilter: ['data-titlebar-actions-layout']", self.js)

    def test_rail_and_user_hub_are_mutually_exclusive(self):
        hub = _read(STATIC, 'titlebar', 'js', 'user_hub.js')

        self.assertIn("new CustomEvent('dlux:user-hub-toggled'", hub)
        self.assertIn("document.addEventListener('dlux:user-hub-toggled'", self.js)
        # Clicks landing inside the rail are not "outside": the notification panel
        # and the search box live there, and closing would unmount them mid-use.
        self.assertIn('element.contains(event.target)', self.js)

    def test_rail_scrolls_once_the_actions_stop_fitting(self):
        # The Titlebar Actions layout hands the rail every configured button, which
        # overflows a narrow phone; spilling them out of reach is what the scattered
        # bar already did wrong.
        self.assertIn("rail.classList.toggle('is-scrollable', rail.scrollWidth > rail.clientWidth + 1)", self.js)
        self.assertIn("rail.style.setProperty(\n                '--dlux-titlebar-rail-panel-top'", self.js)

    def test_grouped_bell_hands_its_unread_state_to_the_caret(self):
        css = _read(STATIC, 'titlebar', 'css', 'main.css')

        self.assertIn("'[data-dlux-notifications-badge]'", self.js)
        self.assertIn("rail.toggle.setAttribute('data-dlux-rail-alert'", self.js)
        self.assertIn('.dlux-titlebar-rail-toggle[data-dlux-rail-alert="true"]::after {', css)

    def test_tutorial_opens_the_rail_for_the_steps_it_walks(self):
        tutorial = _read(STATIC, 'tutorial', 'js', 'main.js')

        self.assertIn('window.__dluxTitlebarRail', self.js)
        self.assertIn('const actionRail = window.__dluxTitlebarRail;', tutorial)
        # Every exit path puts it back.
        self.assertEqual(tutorial.count('releaseRail();'), 5)


class TitlebarActionRailStyleTests(TestCase):
    def setUp(self):
        self.css = _read(STATIC, 'titlebar', 'css', 'main.css')

    def test_caret_only_shows_once_the_actions_are_actually_grouped(self):
        self.assertIn('.dlux-titlebar-rail-toggle {\n    display: none;', self.css)
        self.assertIn(
            '.titlebar[data-titlebar-actions-grouped="true"] .dlux-titlebar-rail-toggle {',
            self.css,
        )

    def test_actions_are_spread_equally_inside_the_rail(self):
        rail = self.css.split('.dlux-titlebar-rail {')[1].split('}')[0]
        self.assertIn('justify-content: space-evenly;', rail)

    def test_panels_open_downward_from_the_rail_not_over_the_caret(self):
        self.assertIn('.dlux-titlebar-rail .dlux-notifications,\n.dlux-titlebar-rail .dlux-global-search {', self.css)
        self.assertIn('position: static;', self.css)
        self.assertIn('.dlux-titlebar-rail .dlux-notifications__panel,', self.css)
        self.assertIn(
            '.dlux-titlebar-rail .dlux-global-search[data-global-search-mode] .dlux-global-search__results {',
            self.css,
        )
        self.assertIn('inset-block-start: calc(100% + 0.5rem);', self.css)
        self.assertIn('inset-block-start: calc(100% + 3.15rem);', self.css)

    def test_scrolling_rail_stops_spreading_and_frees_its_panels(self):
        # space-evenly inside a scroll container parks the leading action before the
        # scrollable start, where it cannot be reached.
        self.assertIn('.dlux-titlebar-rail.is-scrollable {', self.css)
        scrollable = self.css.split('.dlux-titlebar-rail.is-scrollable {')[1].split('}')[0]
        self.assertIn('justify-content: flex-start;', scrollable)
        self.assertIn('overflow-x: auto;', scrollable)

        # A scroll container clips on both axes, so the panels anchor to the viewport
        # under the rail's measured bottom instead of hanging off the rail.
        self.assertIn(
            '.dlux-titlebar-rail.is-scrollable .dlux-notifications__panel,',
            self.css,
        )
        self.assertIn('var(--dlux-titlebar-rail-panel-top', self.css)

    def test_button_styles_reach_the_grouped_actions(self):
        self.assertIn(':is(.titlebar, .dlux-titlebar-rail) .dlux-titlebar-btn {', self.css)
        self.assertIn(
            ':is(.titlebar, .dlux-titlebar-rail)[data-titlebar-show-home="false"] .dlux-titlebar-home',
            self.css,
        )
        self.assertIn(
            ':is(.titlebar, .dlux-titlebar-rail)[data-titlebar-show-language-switcher="false"]'
            ' .dlux-titlebar-lang-cycle',
            self.css,
        )
        # The sidebar toggle never groups; its shape rule stays titlebar-only.
        self.assertIn('.titlebar[data-titlebar-buttons-shape="square"] .sidebar-toggle', self.css)

        for theme in ('dark', 'gothic', 'retro', 'neon', 'prism', 'aether'):
            theme_css = _read(STATIC, 'themes', 'css', f'{theme}.css')
            self.assertIn(':is(.titlebar, .dlux-titlebar-rail) .dlux-titlebar-btn {', theme_css)

    def test_titlebar_actions_layout_hides_the_hub_trigger_by_name(self):
        # It used to ride inside the dropdown action group, which that layout hides
        # wholesale; it stands on its own now.
        self.assertIn(
            '.titlebar[data-titlebar-user-hub-style="titlebar_actions"] .dlux-user-trigger {',
            self.css,
        )

    def test_narrow_screens_enforce_the_small_title_and_a_tighter_logo(self):
        mobile = self.css.split('@media (max-width: 575.98px) {')[-1]
        self.assertIn('.titlebar[data-title-size] .titlebar__title {', mobile)
        self.assertIn('.titlebar__logo {', mobile)
        self.assertIn('.dlux-titlebar-rail {', mobile)


class TitlebarActionsOrderBuilderTests(TestCase):
    def test_handle_is_a_real_drag_source(self):
        from dlux.forms import build_titlebar_actions_order_builder

        html = str(build_titlebar_actions_order_builder([], {}))

        self.assertIn('data-titlebar-action-order-handle', html)
        self.assertIn("draggable='true'", html)
        # The buttons stay: drag is the pointer path, they are the keyboard one.
        self.assertIn("data-titlebar-action-move='-1'", html)
        self.assertIn("data-titlebar-action-move='1'", html)

    def test_drag_reorder_is_bound_and_writes_through_the_same_path_as_the_buttons(self):
        js = _read(STATIC, 'setup', 'js', 'main.js')

        for event in ('dragstart', 'dragover', 'dragleave', 'drop', 'dragend'):
            self.assertIn(f"list.addEventListener('{event}'", js)
        # A drop must persist exactly like a button move does.
        self.assertEqual(js.count('renderTitlebarActionsOrderBuilder(builder, form);'), 3)
        self.assertIn('list.insertBefore(dragged, before ? item : item.nextSibling);', js)

    def test_drop_affordances_are_styled(self):
        css = _read(STATIC, 'setup', 'css', 'main.css')

        self.assertIn('.dlux-titlebar-action-order-item.is-dragging {', css)
        self.assertIn('.dlux-titlebar-action-order-item.is-drop-before {', css)
        self.assertIn('.dlux-titlebar-action-order-item.is-drop-after {', css)
        self.assertIn('cursor: grab;', css)
