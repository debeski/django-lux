from pathlib import Path

from django.test import SimpleTestCase


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SETUP_JS = PACKAGE_ROOT / 'static' / 'dlux' / 'setup' / 'js'


class SystemSettingsPreviewModuleTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.preview_source = (SETUP_JS / 'previews.js').read_text()
        cls.main_source = (SETUP_JS / 'main.js').read_text()
        cls.appearance_source = (SETUP_JS / 'appearance.js').read_text()

    def test_preview_module_owns_page_mutation_entry_points(self):
        self.assertIn('root.DluxSetupPreview = Object.assign', self.preview_source)
        for name in (
            'applyBrandingPreview',
            'applyFooterPreview',
            'applyLayoutPreview',
            'applySidebarPreview',
            'applySystemSettingsPreview',
            'applyTableDensityPreview',
            'applyThemePreview',
            'applyTitlebarPreview',
            'initSystemSettingsPreview',
        ):
            self.assertIn(f'function {name}(', self.preview_source)

    def test_feature_modules_delegate_preview_mutations(self):
        self.assertNotIn('function applyTitlebarPreview(', self.main_source)
        self.assertNotIn('function applySidebarPreview(', self.main_source)
        self.assertIn('} = window.DluxSetupPreview;', self.main_source)
        self.assertNotIn('window.setTheme(theme, {', self.appearance_source)
        self.assertIn('root.DluxSetupPreview.applyThemePreview(', self.appearance_source)

    def test_persistent_notifications_are_not_live_previewed(self):
        self.assertNotIn('function applyNotificationPreview(', self.preview_source)
        dispatcher = self.preview_source.split('function applySystemSettingsPreview(form)', 1)[1]
        dispatcher = dispatcher.split('function initSystemSettingsPreview', 1)[0]
        self.assertNotIn('notification', dispatcher.lower())

    def test_preview_script_loads_after_its_dependencies_and_before_main(self):
        template = (PACKAGE_ROOT / 'templates' / 'dlux' / 'base.html').read_text()
        language = template.index("dlux/setup/js/language.js")
        shell = template.index("dlux/setup/js/shell.js")
        previews = template.index("dlux/setup/js/previews.js")
        main = template.index("dlux/setup/js/main.js")
        self.assertLess(language, previews)
        self.assertLess(shell, previews)
        self.assertLess(previews, main)
