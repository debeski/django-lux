from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.test import SimpleTestCase

from dlux.management.commands.dlux_setup import Command


class EnsureSettingsBlockTests(SimpleTestCase):
    """`dlux_setup` must detect an already-wired settings.py via the AST, not a
    literal import line, so it never appends a duplicate dlux_settings block."""

    present = staticmethod(Command._settings_block_present)

    def test_recognizes_every_valid_import_style(self):
        # The scaffolded project imports them combined — the original literal
        # substring check missed this and would have duplicated the block.
        self.assertTrue(self.present(
            "from dlux.utils import get_secret, dlux_settings\ndlux_settings(globals())\n"
        ))
        self.assertTrue(self.present(
            "from dlux.utils import dlux_settings\ndlux_settings(globals())\n"
        ))
        self.assertTrue(self.present(
            "from dlux.utils import dlux_settings, get_secret\ndlux_settings(globals())\n"
        ))
        self.assertTrue(self.present(
            "from dlux.utils import dlux_settings as ds\nds(globals())\n"
        ))
        self.assertTrue(self.present(
            "from dlux.utils import (\n    get_secret,\n    dlux_settings,\n)\ndlux_settings(globals())\n"
        ))

    def test_absent_when_not_imported_or_not_called(self):
        self.assertFalse(self.present("SECRET_KEY = 'x'\nINSTALLED_APPS = []\n"))
        # Imported but never applied — not considered set up.
        self.assertFalse(self.present("from dlux.utils import dlux_settings\n"))
        # A same-named import from a different module must not count.
        self.assertFalse(self.present(
            "from other.utils import dlux_settings\ndlux_settings(globals())\n"
        ))

    def test_unparseable_settings_fall_back_to_literal_check(self):
        broken_with_block = (
            "def (:\n"
            "from dlux.utils import dlux_settings\n"
            "dlux_settings(globals())\n"
        )
        self.assertTrue(self.present(broken_with_block))
        self.assertFalse(self.present("def (:\nSECRET_KEY = 'x'\n"))

    def test_matches_the_appended_default_block(self):
        from dlux.management.commands.dlux_setup import DLUX_SETTINGS_BLOCK
        self.assertTrue(self.present(DLUX_SETTINGS_BLOCK))
