from pathlib import Path

from django.test import SimpleTestCase

from dlux.tests.harness import setup_test_environment

setup_test_environment()

STATIC = Path(__file__).resolve().parents[1] / 'static' / 'dlux'
JS = STATIC / 'helpers' / 'inspector' / 'js' / 'main.js'
CSS = STATIC / 'helpers' / 'inspector' / 'css' / 'main.css'
BASE_HTML = Path(__file__).resolve().parents[1] / 'templates' / 'dlux' / 'base.html'


class InspectorShellAssetTests(SimpleTestCase):
    def test_inspector_shell_exports_adapter_driven_api(self):
        source = JS.read_text(encoding='utf-8')

        self.assertIn('root.DluxInspectorShell', source)
        self.assertIn('createInspectorShell', source)
        self.assertIn('adapter.getSelection', source)
        self.assertIn('adapter.getFields', source)
        self.assertIn('adapter.getActions', source)
        self.assertIn('adapter.commit', source)
        self.assertIn('clearSelection', source)

    def test_inspector_shell_supports_builder_field_shapes(self):
        source = JS.read_text(encoding='utf-8')

        self.assertIn("'localized-text'", source)
        self.assertIn("'url'", source)
        self.assertIn("'textarea'", source)
        self.assertIn("'select'", source)
        self.assertIn("'toggle'", source)
        self.assertIn("'custom'", source)
        self.assertIn('field.render', source)
        self.assertIn('language:', source)

    def test_popover_anchors_to_the_row_it_edits_and_dismisses_on_outside_click(self):
        source = JS.read_text(encoding='utf-8')

        self.assertIn('adapter.getAnchor', source)
        self.assertIn('dismissOnOutsideClick', source)
        self.assertIn('dismissIgnoreSelector', source)
        # Below the anchor by default, above it only when there is no room below.
        self.assertIn("panel.dataset.inspectorPlacement = above ? 'above' : 'below';", source)
        self.assertIn('anchorRect.bottom + POPOVER_GAP', source)
        self.assertIn('anchorRect.top - height - POPOVER_GAP', source)
        # Room is measured inside whatever clips the panel — a scrollable modal body,
        # not the viewport, which is what put the panel past the modal's edge.
        self.assertIn('function visibleBounds(element) {', source)
        self.assertIn('const bounds = visibleBounds(panel);', source)
        self.assertIn('const anchorBounds = visibleBounds(anchor);', source)
        self.assertNotIn('root.innerHeight', source)
        # Too tall for either side: cap and scroll rather than be clipped away.
        # The panel's own box, and only that. A field's layer — an icon picker's
        # dropdown — is a popover in its own right: it floats outside the panel and is
        # not confined by it, so it is neither measured into placement (which made the
        # panel cap itself, and a capped panel scrolls, which clipped the dropdown to a
        # sliver) nor capped to the panel's bounds. Never `scrollHeight`, which an
        # out-of-flow layer inflates without being part of the box.
        self.assertIn('const naturalHeight = panel.offsetHeight;', source)
        self.assertNotIn('panel.scrollHeight', source)
        self.assertNotIn('clampOpenLayers', source)
        self.assertNotIn('MutationObserver', source)
        # A scroll inside the panel cannot have moved the anchor.
        self.assertIn('if (target && typeof target.nodeType === \'number\' && panel.contains(target)) return;', source)
        # Never a height cap: a capped panel scrolls, and a scrolling panel clips the
        # layers its fields open over it. Too tall for either side, it is nudged inside
        # the visible band whole instead.
        self.assertNotIn('panel.style.maxHeight', source)
        self.assertIn('top = Math.max(bounds.top, Math.min(top, bounds.bottom - height));', source)
        # Capture phase, so a click that moves the selection re-anchors the panel
        # instead of dismissing it.
        self.assertIn("addEventListener('click', handleOutsideClick, true)", source)
        self.assertIn("addEventListener('scroll', handleReflow, true)", source)
        self.assertIn("removeEventListener('click', handleOutsideClick, true)", source)

    def test_inspector_shell_keeps_render_and_commit_separate(self):
        source = JS.read_text(encoding='utf-8')
        render_block = source[source.index('shell.render = function'):source.index('shell.api = {')]

        self.assertIn('shell.dispatch(\'render\'', render_block)
        self.assertNotIn('shell.commit(', render_block)
        self.assertIn('commitForEvent(shell, field', source)
        self.assertIn('result.commit', source)

    def test_inspector_shell_is_not_tied_to_existing_builders(self):
        source = JS.read_text(encoding='utf-8')

        self.assertNotIn('sidebar_config', source)
        self.assertNotIn('navbar_config', source)
        self.assertNotIn('ribbon_config', source)
        self.assertNotIn('data-builder-editor', source)
        self.assertNotIn('data-navbar-inspector', source)
        self.assertNotIn('data-ribbon-inspector', source)

    def test_inspector_shell_css_supports_pinned_clear_and_responsive_fields(self):
        source = CSS.read_text(encoding='utf-8')

        self.assertIn('.dlux-inspector-shell__actions', source)
        self.assertIn('.dlux-inspector-shell__action--end', source)
        self.assertIn('.dlux-inspector-shell--popover', source)
        self.assertIn('position: absolute;', source)
        self.assertIn('margin-inline-start: auto;', source)
        # Fields flex into the row they are given and wrap once each would fall
        # below `--dlux-inspector-field-min`.
        self.assertIn('flex: 1 1 var(--dlux-inspector-field-min, 12rem);', source)
        self.assertIn('flex-wrap: wrap;', source)
        self.assertIn('flex-basis: 100%;', source)
        self.assertIn('inset-inline: 0;', source)
        self.assertIn('.dlux-inspector-shell__panel.is-anchor-offscreen', source)
        # The popover panel never scrolls, so it cannot clip a field's dropdown.
        self.assertNotIn('.dlux-inspector-shell__panel.is-capped', source)
        self.assertIn('.dlux-inspector-shell__field--full', source)

    def test_inspector_shell_loads_before_builder_scripts(self):
        source = BASE_HTML.read_text(encoding='utf-8')

        self.assertIn("dlux/helpers/inspector/css/main.css", source)
        self.assertIn("dlux/helpers/inspector/js/main.js", source)
        self.assertLess(
            source.index("dlux/helpers/inspector/js/main.js"),
            source.index("dlux/setup/js/main.js"),
        )
        self.assertLess(
            source.index("dlux/helpers/inspector/js/main.js"),
            source.index("dlux/ribbon/js/ribbon_builder.js"),
        )
