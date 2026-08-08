from pathlib import Path

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, TestCase

from dlux.forms import SystemSettingsForm
from dlux.models import SystemSettings
from dlux.system.constants import (
    DEFAULT_SIDEBAR_TOGGLE_ICON,
    SIDEBAR_TOGGLE_DIRECTIONAL_ICONS,
)
from dlux.system.defaults import default_sidebar_config, default_titlebar_config
from dlux.system.normalizers import normalize_sidebar_behavior, normalize_sidebar_toggle_icon
from dlux.utils.config import get_system_config
from dlux.utils.import_export import apply_system_settings_import


class SidebarToggleIconNormalizerTests(SimpleTestCase):
    def test_default_is_the_plain_list_glyph(self):
        self.assertEqual(default_sidebar_config()['toggle_icon'], 'bi-list')
        self.assertEqual(DEFAULT_SIDEBAR_TOGGLE_ICON, 'bi-list')

    def test_accepts_any_bootstrap_icon_token(self):
        for icon in ('bi-list', 'bi-arrow-bar-left', 'bi-layout-sidebar-inset-reverse', 'bi-x'):
            with self.subTest(icon=icon):
                self.assertEqual(normalize_sidebar_toggle_icon(icon), icon)

    def test_casing_and_padding_are_coerced(self):
        self.assertEqual(normalize_sidebar_toggle_icon('  BI-Arrow-Bar-Left '), 'bi-arrow-bar-left')

    def test_anything_that_is_not_an_icon_token_falls_back(self):
        # The value is rendered into a class attribute, so a hostile or malformed
        # string must never reach the template.
        for value in (
            '',
            None,
            'foo',
            'list',
            'bi-list" onload="alert(1)',
            'bi-list bi-x',
            'bi_list',
            'bi-' + 'a' * 80,
            {'icon': 'bi-list'},
        ):
            with self.subTest(value=value):
                self.assertEqual(normalize_sidebar_toggle_icon(value), DEFAULT_SIDEBAR_TOGGLE_ICON)

    def test_group_normalizer_repairs_a_stored_bad_value(self):
        normalized = normalize_sidebar_behavior({'entries': [], 'toggle_icon': '<script>'})

        self.assertEqual(normalized['toggle_icon'], DEFAULT_SIDEBAR_TOGGLE_ICON)


class SidebarToggleIconPersistenceTests(TestCase):
    """Driven through the real save/import paths, never a direct dict write."""

    def test_survives_import_reload_and_reaches_runtime_config(self):
        settings_row = SystemSettings.load()

        apply_system_settings_import(settings_row, {
            'sidebar_config': {'enabled': True, 'entries': [], 'toggle_icon': 'bi-arrow-bar-left'},
        })

        self.assertEqual(SystemSettings.load().sidebar_config.get('toggle_icon'), 'bi-arrow-bar-left')
        self.assertEqual(get_system_config().get('sidebar', {}).get('toggle_icon'), 'bi-arrow-bar-left')

    def test_import_rejects_a_hostile_value(self):
        settings_row = SystemSettings.load()

        apply_system_settings_import(settings_row, {
            'sidebar_config': {
                'enabled': True,
                'entries': [],
                'toggle_icon': 'bi-x" onerror="alert(1)',
            },
        })

        self.assertEqual(
            SystemSettings.load().sidebar_config.get('toggle_icon'),
            DEFAULT_SIDEBAR_TOGGLE_ICON,
        )

    def test_sidebar_step_save_stores_the_chosen_icon(self):
        request = RequestFactory().get('/sys/modals/dlux/systemsettings/1/?step=5')
        form = SystemSettingsForm(
            data={
                'system_names': '{"en": "System", "ar": "System"}',
                'home_url': '/dashboard/',
                'default_language': 'en',
                'default_theme': 'light',
                'allowed_themes': ['light'],
                'languages': '{}',
                'translations_override': '{}',
                'sidebar_config': '{"enabled":true,"entries":[]}',
                'sidebar_enabled': 'on',
                'sidebar_toggle_icon': 'bi-layout-sidebar-inset-reverse',
            },
            instance=SystemSettings(is_configured=True),
            request=request,
        )

        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save(commit=False)

        self.assertEqual(
            saved.sidebar_config.get('toggle_icon'),
            'bi-layout-sidebar-inset-reverse',
        )

    def test_saving_another_step_does_not_reset_the_icon(self):
        # Trap 2 in docs/adding-system-settings.md: a field absent from a
        # single-step POST must not be written back as its default.
        request = RequestFactory().get('/sys/modals/dlux/systemsettings/1/?step=2')
        form = SystemSettingsForm(
            data={
                'system_names': '{"en": "System", "ar": "System"}',
                'home_url': '/dashboard/',
                'default_language': 'en',
                'default_theme': 'light',
                'allowed_themes': ['light'],
                'languages': '{}',
                'translations_override': '{}',
                'sidebar_config': '{"enabled":true,"entries":[],"toggle_icon":"bi-arrow-bar-left"}',
            },
            instance=SystemSettings(
                is_configured=True,
                sidebar_config={
                    'enabled': True,
                    'entries': [],
                    'toggle_icon': 'bi-arrow-bar-left',
                },
            ),
            request=request,
        )

        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save(commit=False)

        self.assertEqual(saved.sidebar_config.get('toggle_icon'), 'bi-arrow-bar-left')

    def test_form_initial_reflects_the_stored_icon(self):
        form = SystemSettingsForm(
            instance=SystemSettings(
                is_configured=True,
                sidebar_config={'enabled': True, 'entries': [], 'toggle_icon': 'bi-menu-app'},
            ),
        )

        self.assertEqual(form.initial['sidebar_toggle_icon'], 'bi-menu-app')


class SidebarToggleIconRenderTests(TestCase):
    def _titlebar(self, sidebar):
        request = RequestFactory().get('/')
        request.user = _AuthedUser()
        return render_to_string('dlux/includes/titlebar.html', {
            'request': request,
            'user': request.user,
            'sidebar_enabled': True,
            'sidebar': sidebar,
            'titlebar': default_titlebar_config(),
            'DLUX_STRINGS': {},
            'APP_CONFIG': {},
        })

    def test_chosen_icon_is_rendered_on_the_toggle(self):
        html = self._titlebar({'collapse_mode': 'icons', 'toggle_icon': 'bi-menu-app'})

        self.assertIn('bi bi-menu-app', html)
        self.assertNotIn('bi bi-list"', html)

    def test_missing_icon_falls_back_to_the_default(self):
        html = self._titlebar({'collapse_mode': 'icons'})

        self.assertIn('bi bi-list', html)

    def test_directional_icons_are_marked_for_rtl_mirroring(self):
        directional = self._titlebar({
            'collapse_mode': 'icons',
            'toggle_icon': 'bi-arrow-bar-left',
            'toggle_icon_directional': True,
        })
        symmetric = self._titlebar({
            'collapse_mode': 'icons',
            'toggle_icon': 'bi-list',
            'toggle_icon_directional': False,
        })

        self.assertIn('dlux-icon-directional', directional)
        self.assertNotIn('dlux-icon-directional', symmetric)

    def test_context_processor_flags_only_directional_glyphs(self):
        self.assertIn('bi-arrow-bar-left', SIDEBAR_TOGGLE_DIRECTIONAL_ICONS)
        self.assertIn('bi-chevron-left', SIDEBAR_TOGGLE_DIRECTIONAL_ICONS)
        self.assertNotIn('bi-list', SIDEBAR_TOGGLE_DIRECTIONAL_ICONS)
        self.assertNotIn('bi-menu-app', SIDEBAR_TOGGLE_DIRECTIONAL_ICONS)


class _AuthedUser:
    is_authenticated = True
    is_staff = True
    is_superuser = True
    scope = None

    def has_perm(self, _permission):
        return True


class SidebarToggleIconAssetTests(SimpleTestCase):
    @property
    def _static(self):
        return Path(__file__).resolve().parents[1] / 'static' / 'dlux' / 'main'

    def test_rtl_and_state_flips_compose_into_one_transform(self):
        # Two separate `transform` rules would let the later one win, silently
        # dropping either the RTL mirror or the collapsed-state facing.
        css = (self._static / 'css' / 'main.css').read_text(encoding='utf-8')

        self.assertIn('.dlux-icon-directional', css)
        self.assertIn('transform: scaleX(calc(var(--dlux-icon-rtl) * var(--dlux-icon-state)));', css)
        self.assertIn('[dir="rtl"] .dlux-icon-directional', css)
        self.assertIn('--dlux-icon-rtl: -1;', css)

    def test_picker_offers_the_default_and_the_sidebar_cluster(self):
        js = (self._static / 'js' / 'system_setup.js').read_text(encoding='utf-8')
        block = js[js.index('const ICON_SUGGESTIONS = ['):]
        block = block[:block.index('\n    ];')]

        # Without the default in the grid an admin cannot click back to it.
        self.assertIn("'bi-list',", block)
        for icon in (
            'bi-arrow-bar-left',
            'bi-arrow-bar-right',
            'bi-layout-sidebar-inset-reverse',
            'bi-text-indent-left',
            'bi-menu-app',
        ):
            with self.subTest(icon=icon):
                self.assertIn(f"'{icon}',", block)

    def test_picker_is_initialized_and_writes_to_the_posted_field(self):
        js = (self._static / 'js' / 'system_setup.js').read_text(encoding='utf-8')

        self.assertIn('function initIconPickers(root)', js)
        self.assertIn('initIconPickers(root);', js)
        self.assertIn('setNamedFieldValue(form, fieldName, value);', js)
        # The icon must round-trip into the serialized sidebar config.
        self.assertIn("nextConfig.toggle_icon = getNamedFieldValue(form, 'sidebar_toggle_icon')", js)
        self.assertIn("setNamedFieldValue(form, 'sidebar_toggle_icon', sidebar.toggle_icon", js)

    def test_picker_template_binds_to_the_field(self):
        html = _render_picker()

        self.assertIn('data-dlux-icon-picker', html)
        self.assertIn('data-icon-field="sidebar_toggle_icon"', html)
        self.assertIn('data-icon-default="bi-list"', html)
        self.assertIn('value="bi-menu-app"', html)
        self.assertIn('data-icon-search', html)


def _render_picker():
    return render_to_string('dlux/includes/icon_picker.html', {
        'field_name': 'sidebar_toggle_icon',
        'label': 'Sidebar toggle icon',
        'help_text': 'Pick one.',
        'current_icon': 'bi-menu-app',
        'default_icon': 'bi-list',
        'mode': 'setup',
        'DLUX_STRINGS': {},
    })


class IconPickerDisclosureTests(SimpleTestCase):
    """The grid is ~600 buttons, so it must not exist until it is asked for."""

    @property
    def _setup_js(self):
        script = Path(__file__).resolve().parents[1] / 'static' / 'dlux' / 'main' / 'js' / 'system_setup.js'
        return script.read_text(encoding='utf-8')

    def test_grid_starts_collapsed(self):
        html = _render_picker()

        self.assertIn('data-icon-picker-body', html)
        self.assertIn('class="dlux-builder-icon-picker p-2 rounded-4 border d-none"', html)
        self.assertIn('aria-expanded="false"', html)

    def test_current_icon_is_the_disclosure_trigger(self):
        html = _render_picker()

        self.assertIn('data-icon-toggle', html)
        self.assertIn('aria-controls="dlux-icon-picker-body-sidebar_toggle_icon-setup"', html)
        self.assertIn('id="dlux-icon-picker-body-sidebar_toggle_icon-setup"', html)
        # The trigger wraps the live preview, so the thing you click is the icon.
        self.assertIn('data-icon-preview', html)

    def test_reset_is_an_icon_with_an_accessible_name(self):
        html = _render_picker()

        self.assertIn('bi-arrow-counterclockwise', html)
        self.assertIn('aria-label="Reset"', html)
        self.assertNotIn('>Reset<', html)

    def test_grid_is_built_on_open_and_dropped_on_close(self):
        js = self._setup_js
        block = js[js.index('function initIconPickers(root)'):]
        block = block[:block.index('\n    function scan(root)')]

        self.assertIn('function open()', block)
        self.assertIn('function close(', block)
        # Init must not touch the grid.
        self.assertIn("apply(currentValue(), { rerender: false });", block)
        self.assertNotIn('apply(currentValue());', block)
        # Opening builds it, closing frees it.
        self.assertIn("body.classList.remove('d-none');", block)
        self.assertIn("body.classList.add('d-none');", block)
        self.assertIn("suggestions.innerHTML = '';\n                if (search) {", block)

    def test_picking_an_icon_collapses_the_grid(self):
        js = self._setup_js
        block = js[js.index('function initIconPickers(root)'):]
        block = block[:block.index('\n    function scan(root)')]

        self.assertIn("apply(icon, { rerender: false });\n                        close({ focusTrigger: true });", block)

    def test_escape_closes_and_returns_focus(self):
        js = self._setup_js
        block = js[js.index('function initIconPickers(root)'):]
        block = block[:block.index('\n    function scan(root)')]

        self.assertIn("event.key === 'Escape'", block)
        self.assertIn('toggle.focus();', block)

    def test_rerender_is_skipped_while_collapsed(self):
        # Typing in the text field must not rebuild a grid nobody is looking at.
        js = self._setup_js
        block = js[js.index('function initIconPickers(root)'):]
        block = block[:block.index('\n    function scan(root)')]

        self.assertIn('if (rerender && isOpen()) {', block)

    def test_trigger_has_pressable_styling(self):
        css = (
            Path(__file__).resolve().parents[1]
            / 'static' / 'dlux' / 'main' / 'css' / 'system_setup.css'
        ).read_text(encoding='utf-8')

        self.assertIn('.dlux-icon-picker-trigger', css)
        self.assertIn('cursor: pointer;', css)
        self.assertIn('.dlux-icon-picker-trigger[aria-expanded="true"] .dlux-icon-picker-caret', css)


class SidebarToggleInteractionTests(SimpleTestCase):
    """The toggle has to behave like a control, not a printed glyph."""

    @property
    def _root(self):
        return Path(__file__).resolve().parents[1] / 'static' / 'dlux'

    @property
    def _sidebar_css(self):
        return (self._root / 'sidebar' / 'css' / 'main.css').read_text(encoding='utf-8')

    @property
    def _sidebar_js(self):
        return (self._root / 'sidebar' / 'js' / 'main.js').read_text(encoding='utf-8')

    def test_toggle_reports_sidebar_state_to_assistive_tech(self):
        js = self._sidebar_js

        self.assertIn('function syncToggleState()', js)
        self.assertIn("sidebarToggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');", js)
        self.assertIn("sidebarToggle.classList.toggle('is-collapsed', collapsed);", js)

    def test_state_is_read_back_from_the_sidebar_not_the_request(self):
        # Mobile and locked_expanded override the requested value, so trusting the
        # argument would leave the button claiming a state the sidebar never took.
        js = self._sidebar_js

        self.assertIn("const collapsed = sidebar.classList.contains('collapsed');", js)

    def test_every_collapse_path_syncs_the_toggle(self):
        js = self._sidebar_js
        body = js[js.index('document.addEventListener("DOMContentLoaded", function () {\n    const sidebar'):]

        # Direct class writes bypass applyCollapsedState, so each one must sync.
        mutations = body.count('classList.toggle("collapsed")') + body.count('classList.add("collapsed")')
        self.assertEqual(mutations, 2, 'a new direct collapse path needs a syncToggleState() call')
        self.assertEqual(body.count('syncToggleState();'), 3)

    def test_toggle_has_hover_press_and_state_affordances(self):
        css = self._sidebar_css

        self.assertIn('.sidebar-toggle:hover', css)
        self.assertIn('.sidebar-toggle:active', css)
        self.assertIn('.sidebar-toggle[aria-expanded="true"]', css)
        self.assertIn('.sidebar-toggle.is-collapsed .dlux-icon-directional', css)
        self.assertIn('--dlux-icon-state: -1;', css)

    def test_keyboard_focus_is_visible(self):
        css = self._sidebar_css

        self.assertIn('.sidebar-toggle:focus-visible', css)
        self.assertIn('outline: 2px solid rgba(var(--primal-rgb), 0.55);', css)
        # The released rule suppressed the ring outright; it must not come back.
        self.assertNotIn('box-shadow: none !important;\n    color: var(--primal) !important;', css)

    def test_icon_only_animates_once_state_is_synced(self):
        css = self._sidebar_css

        self.assertIn('.sidebar-toggle.is-ready .dlux-icon-directional', css)
        self.assertIn("sidebarToggle.classList.add('is-ready');", self._sidebar_js)

    def test_motion_is_reducible(self):
        css = self._sidebar_css
        block = css[css.index('.sidebar-toggle {'):]

        self.assertIn('@media (prefers-reduced-motion: reduce)', block)

    def test_toggle_follows_the_titlebar_button_shape(self):
        css = (self._root / 'main' / 'css' / 'titlebar.css').read_text(encoding='utf-8')

        self.assertIn('.titlebar[data-titlebar-buttons-shape="square"] .sidebar-toggle', css)
        self.assertIn('.titlebar[data-titlebar-buttons-shape="squircle"] .sidebar-toggle', css)


class SidebarToggleMarkupTests(TestCase):
    def test_button_exposes_expanded_state_and_target(self):
        request = RequestFactory().get('/')
        request.user = _AuthedUser()
        html = render_to_string('dlux/includes/titlebar.html', {
            'request': request,
            'user': request.user,
            'sidebar_enabled': True,
            'sidebar': {'collapse_mode': 'icons', 'toggle_icon': 'bi-list'},
            'titlebar': default_titlebar_config(),
            'DLUX_STRINGS': {},
            'APP_CONFIG': {},
        })

        self.assertIn('aria-controls="sidebar"', html)
        self.assertIn('aria-expanded="true"', html)


class SidebarToggleInitialStateTests(TestCase):
    """The server already resolves the collapse preference, so the button must
    render in the right state instead of popping when JS catches up."""

    def _render(self, *, collapsed):
        request = RequestFactory().get('/')
        request.user = _AuthedUser()
        return render_to_string('dlux/includes/titlebar.html', {
            'request': request,
            'user': request.user,
            'sidebar_enabled': True,
            'sidebar_collapsed': collapsed,
            'sidebar': {'collapse_mode': 'icons', 'toggle_icon': 'bi-arrow-bar-left'},
            'titlebar': default_titlebar_config(),
            'DLUX_STRINGS': {},
            'APP_CONFIG': {},
        })

    def test_collapsed_sidebar_renders_a_collapsed_toggle(self):
        html = self._render(collapsed=True)

        self.assertIn('aria-expanded="false"', html)
        self.assertIn('is-collapsed', html)

    def test_expanded_sidebar_renders_an_expanded_toggle(self):
        html = self._render(collapsed=False)

        self.assertIn('aria-expanded="true"', html)
        self.assertNotIn('is-collapsed', html)


class IconPickerLivePreviewTests(TestCase):
    """Picking an icon must show up on the real toggle immediately, like every
    other Sidebar-step control."""

    @property
    def _setup_js(self):
        script = Path(__file__).resolve().parents[1] / 'static' / 'dlux' / 'main' / 'js' / 'system_setup.js'
        return script.read_text(encoding='utf-8')

    def test_sidebar_preview_applies_the_chosen_glyph(self):
        js = self._setup_js
        block = js[js.index('function applySidebarPreview(form)'):]
        block = block[:block.index('\n    function ', 10)]

        self.assertIn("getNamedFieldValue(form, 'sidebar_toggle_icon')", block)
        self.assertIn('toggleGlyph.className = `bi ${icon}', block)
        self.assertIn("directional.includes(icon) ? ' dlux-icon-directional' : ''", block)

    def test_writing_the_field_reaches_the_preview(self):
        # setNamedFieldValue dispatches input/change, which is what the immediate
        # preview binding listens for — a silent assignment would not preview.
        js = self._setup_js
        block = js[js.index('function setNamedFieldValue(form, name, value)'):]
        block = block[:block.index('\n    function ', 10)]

        self.assertIn("dispatchEvent(new Event('input', { bubbles: true }));", block)
        self.assertIn("dispatchEvent(new Event('change', { bubbles: true }));", block)

    def test_preview_is_skipped_when_the_picker_is_not_rendered(self):
        js = self._setup_js
        block = js[js.index('function applySidebarPreview(form)'):]
        block = block[:block.index('\n    function ', 10)]

        self.assertIn("form.querySelector('[data-dlux-icon-picker][data-icon-field=\"sidebar_toggle_icon\"]')", block)
        self.assertIn('if (toggleIconPicker && toggleGlyph) {', block)

    def test_directional_list_is_served_from_python_not_duplicated_in_js(self):
        html = render_to_string('dlux/includes/icon_picker.html', {
            'field_name': 'sidebar_toggle_icon',
            'label': 'Sidebar toggle icon',
            'help_text': '',
            'current_icon': 'bi-list',
            'default_icon': 'bi-list',
            'directional_icons': ' '.join(SIDEBAR_TOGGLE_DIRECTIONAL_ICONS),
            'mode': 'setup',
            'DLUX_STRINGS': {},
        })

        self.assertIn('data-icon-directional="', html)
        self.assertIn('bi-arrow-bar-left', html)
        # A second hardcoded copy in JS would drift from the Python constant.
        js = self._setup_js
        self.assertNotIn("'bi-chevron-double-left',\n        'bi-chevron-double-right',\n        'bi-caret-left'", js)

    def test_form_supplies_the_directional_list_to_the_picker(self):
        form = SystemSettingsForm(
            instance=SystemSettings(
                is_configured=True,
                sidebar_config={'enabled': True, 'entries': [], 'toggle_icon': 'bi-arrow-bar-left'},
            ),
        )

        self.assertIn('data-icon-directional="', form.sidebar_toggle_icon_html)
        self.assertIn('bi-arrow-bar-left', form.sidebar_toggle_icon_html)


class ToggleIconLockedExpandedTests(TestCase):
    """`locked_expanded` hides the toggle on desktop, so its icon picker follows
    the collapse mode as well as the sidebar's own enable switch."""

    def _picker_html(self, collapse_mode, enabled=True):
        form = SystemSettingsForm(
            instance=SystemSettings(
                is_configured=True,
                sidebar_config={
                    'enabled': enabled,
                    'entries': [],
                    'collapse_mode': collapse_mode,
                    'toggle_icon': 'bi-list',
                },
            ),
        )
        return form.sidebar_toggle_icon_html

    def test_picker_is_disabled_when_the_sidebar_is_always_expanded(self):
        html = self._picker_html('locked_expanded')

        self.assertIn('dlux-dependent-settings is-disabled', html)
        self.assertIn('aria-disabled="true"', html)

    def test_picker_is_live_for_the_collapse_modes_that_show_the_toggle(self):
        for mode in ('icons', 'hidden'):
            with self.subTest(collapse_mode=mode):
                html = self._picker_html(mode)

                self.assertNotIn('is-disabled', html)
                self.assertIn('aria-disabled="false"', html)

    def test_picker_is_disabled_when_the_sidebar_itself_is_off(self):
        html = self._picker_html('icons', enabled=False)

        self.assertIn('is-disabled', html)


class ToggleIconLockedExpandedAssetTests(SimpleTestCase):
    @property
    def _js(self):
        script = Path(__file__).resolve().parents[1] / 'static' / 'dlux' / 'main' / 'js' / 'system_setup.js'
        return script.read_text(encoding='utf-8')

    def test_availability_follows_both_the_switch_and_the_collapse_mode(self):
        js = self._js

        self.assertIn('function syncSidebarToggleIconAvailability(form)', js)
        self.assertIn("const lockedExpanded = collapseMode === 'locked_expanded';", js)
        self.assertIn('const available = sidebarEnabled && !lockedExpanded;', js)

    def test_collapse_mode_changes_resync_the_picker(self):
        # Switching to "always expanded" has to disable it without a reload.
        js = self._js
        block = js[js.index('function syncCollapseMode()'):]
        block = block[:block.index('\n            }', 10)]

        self.assertIn('syncSidebarToggleIconAvailability(form);', block)

    def test_locked_reason_explains_why_rather_than_naming_the_switch(self):
        js = self._js

        self.assertIn("t('sidebar_toggle_icon_locked_reason'", js)
