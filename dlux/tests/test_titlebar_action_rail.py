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


ACTIONS = [
    {'kind': 'search', 'key': 'search', 'label': 'Search', 'icon': 'bi-search'},
    {'kind': 'theme', 'key': 'theme', 'label': 'Theme', 'icon': 'bi-circle-half'},
    {'kind': 'language', 'key': 'language', 'label': 'Language', 'icon': 'bi-translate'},
    {'kind': 'notifications', 'key': 'notifications', 'label': 'Notifications', 'icon': 'bi-bell-fill'},
    {'kind': 'link', 'key': 'home', 'label': 'Home', 'icon': 'bi-house-fill', 'url': '/'},
    {'kind': 'link', 'key': 'settings', 'label': 'Options', 'icon': 'bi-gear-fill', 'url': '/o/'},
    {'kind': 'logout', 'key': 'auth', 'label': 'Logout', 'url': '/out/'},
]


def _titlebar(actions=ACTIONS, **titlebar_overrides):
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
        'titlebar_actions': list(actions),
        'search': {'enabled': True, 'display_mode': 'icon'},
        'dlux_notifications_enabled': True,
        'dlux_notification_config': {'drawer': {'badge_enabled': True}},
        'dlux_notifications': [],
        'languages': {'en': {}, 'ar': {}},
        'CURRENT_LANG': 'en',
        'CURRENT_DIR': 'ltr',
        'DLUX_THEMES': [],
        'DLUX_THEME_NAMES': [],
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

    def test_selector_is_disabled_until_its_layout_is_chosen(self):
        layout_source = _read(
            Path(__file__).resolve().parents[1], 'forms', 'system_settings_groups', 'layout.py'
        )
        setup_js = _read(STATIC, 'setup', 'js', 'main.js')

        self.assertIn('dlux-titlebar-actions-layout-dependent', layout_source)
        self.assertIn('dlux-dependent-settings', layout_source)
        self.assertIn("form.querySelectorAll('.dlux-titlebar-actions-layout-dependent')", setup_js)
        self.assertIn('setDependentFieldEnabled(\n                        node,\n                        titlebarActions,', setup_js)

    def test_setting_sits_under_the_style_it_depends_on(self):
        layout_source = _read(
            Path(__file__).resolve().parents[1], 'forms', 'system_settings_groups', 'layout.py'
        )

        self.assertLess(
            layout_source.index("Field('titlebar_user_hub_style')"),
            layout_source.index("Field('titlebar_actions_layout')"),
        )

    def test_setting_is_a_dlux_selector_beside_the_user_hub_style(self):
        form_source = _read(Path(__file__).resolve().parents[1], 'forms', 'system_settings.py')
        layout_source = _read(
            Path(__file__).resolve().parents[1], 'forms', 'system_settings_groups', 'layout.py'
        )

        self.assertIn("titlebar_actions_layout = forms.ChoiceField(", form_source)
        self.assertIn("self.fields['titlebar_actions_layout'],", form_source)
        self.assertIn("'actions_layout': cleaned.get('titlebar_actions_layout'", form_source)
        self.assertIn("Field('titlebar_actions_layout')", layout_source)


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
        scattered = _titlebar(user_hub_style='titlebar_actions')
        grouped = _titlebar(
            user_hub_style='titlebar_actions',
            actions_layout=TITLEBAR_ACTIONS_LAYOUT_GROUPED,
        )

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

    def test_membership_is_decided_server_side_not_by_hiding_a_second_group(self):
        context_processors = _read(
            Path(__file__).resolve().parents[1], 'context_processors.py'
        )
        titlebar = _titlebar()

        # There used to be two groups, one hidden by CSS — which rendered a second
        # notification bell that grouping would have lifted into view. The layout
        # now decides which actions exist, and one group renders them.
        self.assertEqual(titlebar.count('data-titlebar-actions-group='), 1)
        self.assertIn('TITLEBAR_DROPDOWN_ACTION_KEYS', context_processors)
        self.assertEqual(titlebar.count('data-dlux-notifications-toggle'), 1)
        # The unread badge mirrored onto the caret is the one that is actually on
        # the bar, not whichever copy comes first in the document.
        self.assertIn("node.querySelector('[data-dlux-notifications-badge]')", self.js)
        self.assertNotIn("document.querySelector('[data-dlux-notifications-badge]')", self.js)

    def test_grouping_moves_nodes_so_panels_travel_with_their_toggles(self):
        self.assertIn('rail.appendChild(node)', self.js)
        self.assertIn('placeholder.parentNode.insertBefore(node, placeholder.nextSibling)', self.js)

    def test_the_layout_setting_only_applies_to_the_layout_it_names(self):
        # The selector is "Titlebar Action Layout". The Dropdown style keeps its
        # shortcuts in the hub card, so it has nothing to group by choice.
        self.assertIn(
            "titlebar.dataset.titlebarUserHubStyle === 'titlebar_actions'\n"
            "                && titlebar.dataset.titlebarActionsLayout === 'grouped'",
            self.js,
        )

    def test_narrow_screens_group_either_layout_regardless_of_the_setting(self):
        self.assertIn("const MOBILE_QUERY = '(max-width: 575.98px)';", self.js)
        self.assertIn('if (mobile.matches) {\n                return true;\n            }', self.js)
        # ...and the fit fallback still catches a scattered row that cannot leave
        # the title a readable minimum.
        self.assertIn('return byChoice || !scatteredFits();', self.js)

    def test_dropdown_layout_is_never_seeded_as_grouped(self):
        grouped_dropdown = _titlebar(actions_layout=TITLEBAR_ACTIONS_LAYOUT_GROUPED)
        grouped_actions = _titlebar(
            actions_layout=TITLEBAR_ACTIONS_LAYOUT_GROUPED,
            user_hub_style='titlebar_actions',
        )

        self.assertIn('data-titlebar-actions-grouped="false"', grouped_dropdown)
        self.assertIn('data-titlebar-actions-grouped="true"', grouped_actions)

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
        self.assertIn(
            "attributeFilter: ['data-titlebar-actions-layout', 'data-titlebar-user-hub-style']",
            self.js,
        )

    def test_rail_and_user_hub_are_mutually_exclusive(self):
        hub = _read(STATIC, 'titlebar', 'js', 'user_hub.js')

        self.assertIn("new CustomEvent('dlux:user-hub-toggled'", hub)
        self.assertIn("document.addEventListener('dlux:user-hub-toggled'", self.js)
        # Clicks landing inside the rail are not "outside": the notification panel
        # and the search box live there, and closing would unmount them mid-use.
        self.assertIn('element.contains(event.target)', self.js)

    def test_rail_wraps_rather_than_scrolls(self):
        # An action parked off the edge of a scroller is an action nobody finds —
        # the logout button was the one that went missing. The rail takes the width
        # its actions need and wraps onto another line where that will not fit.
        css = _read(STATIC, 'titlebar', 'css', 'main.css')
        block = css.split('.dlux-titlebar-rail {')[1].split('}')[0]

        self.assertIn('width: max-content;', block)
        self.assertIn('flex-wrap: wrap;', block)
        self.assertIn('justify-content: space-evenly;', block)
        self.assertNotIn('overflow', block)
        self.assertNotIn('is-scrollable', css)
        self.assertNotIn('is-scrollable', self.js)

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
        self.assertIn(
            '.titlebar:not([data-titlebar-actions-grouped="true"]) .dlux-titlebar-rail-toggle {\n'
            '    display: none;\n'
            '}',
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
        self.assertEqual(js.count('renderTitlebarActionsOrderBuilder(builder, form);'), 4)
        self.assertIn('list.insertBefore(dragged, before ? item : item.nextSibling);', js)

    def test_drop_affordances_are_styled(self):
        css = _read(STATIC, 'setup', 'css', 'main.css')

        self.assertIn('.dlux-titlebar-action-order-item.is-dragging {', css)
        self.assertIn('.dlux-titlebar-action-order-item.is-drop-before {', css)
        self.assertIn('.dlux-titlebar-action-order-item.is-drop-after {', css)
        self.assertIn('cursor: grab;', css)


class TitlebarActionsOrderIsOneListTests(TestCase):
    def test_the_setup_js_order_matches_the_python_one_exactly(self):
        """The JS copy is not merely a display detail: a key missing from it is
        dropped by normalizeTitlebarActionsOrder and then *saved* stripped, which
        removed the theme cycle from the titlebar after a reorder."""
        import re

        from dlux.system.constants import TITLEBAR_ACTIONS_ORDER

        js = _read(STATIC, 'setup', 'js', 'main.js')
        block = js.split('const TITLEBAR_ACTIONS_DEFAULT_ORDER = [')[1].split(']')[0]
        js_order = re.findall(r"'([a-z_]+)'", block)

        self.assertEqual(js_order, list(TITLEBAR_ACTIONS_ORDER))


class TitlebarActionParityTests(TestCase):
    """Search, theme and language must behave as ordinary actions. They were
    hardcoded outside the action group for a long time, and every one of these is
    a way that leaked back out."""

    def setUp(self):
        self.css = _read(STATIC, 'titlebar', 'css', 'main.css')

    def test_they_carry_no_margin_the_other_actions_lack(self):
        # Outside the group they were loose siblings with no flex gap, so each
        # carried its own margin. Inside it those stack on the gap — a wider space
        # between exactly these three and nothing else.
        self.assertIn(
            '.titlebar__actions .dlux-titlebar-lang-cycle,\n'
            '.titlebar__actions .dlux-titlebar-theme-cycle,\n'
            '.titlebar__actions .dlux-global-search {\n'
            '    margin-inline: 0;\n'
            '}',
            self.css,
        )

    def test_every_action_is_tagged_with_the_styles_that_offer_it(self):
        html = _titlebar()

        self.assertIn('data-titlebar-action-scope=', html)
        self.assertIn(
            '.titlebar[data-titlebar-user-hub-style="dropdown"] [data-titlebar-action-scope="titlebar_actions"]',
            self.css,
        )
        # The rail is outside the titlebar, so it needs the style mirrored to it.
        js = _read(STATIC, 'titlebar', 'js', 'action_rail.js')
        self.assertIn("'data-titlebar-user-hub-style',", js)

    def test_both_sets_render_so_the_settings_page_can_preview_a_style_change(self):
        context_processors = _read(
            Path(__file__).resolve().parents[1], 'context_processors.py'
        )

        # Filtering server-side would mean the titlebar disagreed with the form
        # until a round trip — the mismatch that made choosing a style confusing.
        self.assertIn("action['scope'] = (", context_processors)
        self.assertNotIn('if key in TITLEBAR_DROPDOWN_ACTION_KEYS\n', context_processors)

    def test_opening_search_never_moves_the_title_or_leaves_a_hole(self):
        # In flow the field's width pushed the brand aside; collapsing the toggle
        # left a gap where the button had been, which in the rail sat among the
        # other actions.
        self.assertIn(
            '.titlebar__actions .dlux-global-search[data-global-search-mode]'
            '.dlux-global-search--open .dlux-global-search__toggle,',
            self.css,
        )
        self.assertIn(
            '.dlux-titlebar-rail .dlux-global-search[data-global-search-mode]'
            '.dlux-global-search--open .dlux-global-search__toggle {',
            self.css,
        )
        desktop = self.css.split('@media (min-width: 768px) {')[1].split('\n}')[0]
        self.assertIn('.dlux-global-search__box', desktop)
        self.assertIn('position: absolute;', desktop)


class TitlebarActionChromeTests(TestCase):
    def setUp(self):
        self.css = _read(STATIC, 'titlebar', 'css', 'main.css')
        self.markup = _titlebar()

    def test_the_caret_is_an_ordinary_titlebar_button(self):
        # It carries the shared class, so it inherits the size, surface and the
        # configured shape exactly like every other action.
        self.assertIn('dlux-titlebar-btn dlux-titlebar-action dlux-titlebar-rail-toggle', self.markup)
        # ...which means hiding it has to out-specify the shared button rule.
        self.assertIn(
            '.titlebar:not([data-titlebar-actions-grouped="true"]) .dlux-titlebar-rail-toggle {',
            self.css,
        )

    def test_the_search_toggle_is_an_ordinary_titlebar_button(self):
        self.assertIn('dlux-titlebar-btn dlux-titlebar-action dlux-global-search__toggle', self.markup)

    def test_the_action_group_is_not_a_scroll_container(self):
        # It clipped the absolutely-positioned search field and notification panel,
        # which stopped search opening at all outside the rail. Overflow is what
        # grouping is for; the rail is the thing that scrolls.
        block = self.css.split('.titlebar__actions {')[1].split('}')[0]
        self.assertNotIn('overflow', block)

    def test_the_constants_cluster_is_spaced_off_the_actions(self):
        block = self.css.split('.titlebar__side--end {')[1].split('}')[0]
        self.assertIn('gap: 0.5rem;', block)

    def test_rail_panels_hang_off_the_rail_itself(self):
        # Nothing clips them any more, so they anchor to the rail rather than to
        # viewport coordinates a script has to keep in step.
        self.assertIn('.dlux-titlebar-rail .dlux-notifications__panel,', self.css)
        self.assertIn('inset-block-start: calc(100% + 0.5rem);', self.css)
        self.assertNotIn('--dlux-titlebar-rail-panel-', self.css)


class TitlebarActionsOrderResetTests(TestCase):
    def test_the_builder_offers_a_reset_to_defaults(self):
        from dlux.forms import build_titlebar_actions_order_builder

        html = str(build_titlebar_actions_order_builder(['auth', 'home'], {}))

        self.assertIn('data-titlebar-actions-order-reset', html)
        self.assertIn('bi-arrow-counterclockwise', html)

    def test_reset_restores_the_default_order_through_the_usual_path(self):
        js = _read(STATIC, 'setup', 'js', 'main.js')

        self.assertIn("event.target.closest('[data-titlebar-actions-order-reset]')", js)
        self.assertIn('TITLEBAR_ACTIONS_DEFAULT_ORDER.forEach((key) => {', js)
        # A reset must re-render, re-preview and persist exactly like a move does.
        self.assertEqual(js.count('renderTitlebarActionsOrderBuilder(builder, form);'), 4)


class GlobalSearchDismissalTests(TestCase):
    def setUp(self):
        self.js = _read(STATIC, 'search', 'js', 'main.js')

    def test_the_toggle_closes_what_it_opened(self):
        self.assertIn("if (root.classList.contains('dlux-global-search--open')) {", self.js)
        self.assertIn('closeBox();', self.js)

    def test_dismissal_clears_the_query(self):
        # It used to collapse only when already empty, so a half-typed search came
        # back the next time anyone opened it.
        self.assertNotIn('collapseIfEmpty', self.js)
        block = self.js.split('function closeBox() {')[1].split('}')[0]
        self.assertIn("input.value = '';", block)
        self.assertIn("lastQuery = '';", block)
        self.assertIn('closeResults();', block)
