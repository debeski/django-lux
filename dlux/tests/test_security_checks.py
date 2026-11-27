"""The generated CSP is nonce-only, and older projects are told to follow.

New projects send ``script-src 'self' 'nonce-…'``. A project generated before
keeps its own settings, so system check ``dlux.W201`` warns while its policy
still allows ``'unsafe-inline'`` or ``'unsafe-eval'``.
"""
import re

from django.core import checks
from django.test import SimpleTestCase, override_settings

import dlux
from dlux.scaffold._shared import TEMPLATES_ROOT
from dlux.security_checks import check_script_src_nonce_only

# csp.constants values; django-csp is a project dependency, not one of DjangoLux's.
SELF = "'self'"
UNSAFE_INLINE = "'unsafe-inline'"
UNSAFE_EVAL = "'unsafe-eval'"
NONCE = type("Nonce", (), {"__repr__": lambda self: "csp.constants.NONCE"})()


def policy(**directives):
    return {"DIRECTIVES": {"default-src": [SELF], **directives}}


class ScriptSrcCheckTests(SimpleTestCase):
    def ids(self):
        return [message.id for message in check_script_src_nonce_only()]

    @override_settings(CONTENT_SECURITY_POLICY=policy(**{"script-src": [SELF, UNSAFE_INLINE, UNSAFE_EVAL]}))
    def test_the_old_generated_policy_warns(self):
        [warning] = check_script_src_nonce_only()
        self.assertEqual(warning.id, "dlux.W201")
        self.assertIsInstance(warning, checks.Warning)
        self.assertIn('CONTENT_SECURITY_POLICY["DIRECTIVES"]["script-src"]', warning.msg)
        self.assertIn("'unsafe-inline', 'unsafe-eval'", warning.msg)
        self.assertIn("[SELF, NONCE]", warning.hint)

    @override_settings(CONTENT_SECURITY_POLICY=policy(**{"script-src": [SELF, NONCE]}))
    def test_a_nonce_only_policy_passes(self):
        self.assertEqual(self.ids(), [])

    @override_settings(CONTENT_SECURITY_POLICY=policy(**{"script-src": f"{SELF} {UNSAFE_EVAL}"}))
    def test_a_string_value_is_read_too(self):
        [warning] = check_script_src_nonce_only()
        self.assertIn("'unsafe-eval'", warning.msg)
        self.assertNotIn("'unsafe-inline'", warning.msg)

    @override_settings(CONTENT_SECURITY_POLICY={"DIRECTIVES": {"default-src": [SELF, UNSAFE_INLINE]}})
    def test_default_src_counts_when_script_src_is_missing(self):
        [warning] = check_script_src_nonce_only()
        self.assertIn('["default-src"]', warning.msg)

    @override_settings(CONTENT_SECURITY_POLICY=None, CSP_SCRIPT_SRC=(SELF, UNSAFE_INLINE))
    def test_django_csp_3_settings_are_read(self):
        [warning] = check_script_src_nonce_only()
        self.assertIn("CSP_SCRIPT_SRC", warning.msg)

    def test_no_policy_no_warning(self):
        self.assertEqual(self.ids(), [])

    @override_settings(CONTENT_SECURITY_POLICY=policy(**{"script-src": [SELF, UNSAFE_INLINE]}))
    def test_runs_with_the_security_checks(self):
        ids = [message.id for message in checks.run_checks(tags=[checks.Tags.security])]
        self.assertIn("dlux.W201", ids)


class CountdownTests(SimpleTestCase):
    """docs/deprecation-countdown.md: W201 becomes an error in 1.20.0."""

    def test_w201_is_a_warning_before_1_20_0(self):
        version = tuple(int(part) for part in re.match(r"(\d+)\.(\d+)", dlux.__version__).groups())
        if version >= (1, 20):
            self.fail("1.20.0: turn dlux.W201 into an error and update the deprecation countdown")
        with override_settings(CONTENT_SECURITY_POLICY=policy(**{"script-src": [SELF, UNSAFE_INLINE]})):
            [message] = check_script_src_nonce_only()
        self.assertIsInstance(message, checks.Warning)
        self.assertIn("becomes an error in DjangoLux 1.20.0", message.hint)


class GeneratedPolicyTests(SimpleTestCase):
    def setUp(self):
        self.settings_source = (TEMPLATES_ROOT / "project" / "package" / "settings.py.tmpl").read_text(
            encoding="utf-8"
        )

    def test_script_src_is_self_and_nonce(self):
        script_src = re.search(r'^\s*"script-src": (\[.*\]),$', self.settings_source, re.MULTILINE)
        self.assertIsNotNone(script_src)
        self.assertEqual(script_src.group(1), "[SELF, NONCE]")
        self.assertIn("from csp.constants import NONCE, SELF\n", self.settings_source)
        self.assertNotIn("UNSAFE_EVAL", self.settings_source)

    def test_style_src_allows_no_inline_style(self):
        style_src = re.search(r'^\s*"style-src": (\[.*\]),$', self.settings_source, re.MULTILINE)
        self.assertIsNotNone(style_src)
        self.assertEqual(style_src.group(1), "[SELF]")
        self.assertNotIn("UNSAFE_INLINE", self.settings_source)

    def test_the_generated_policy_passes_the_check(self):
        block = re.search(r'"DIRECTIVES": \{\n(.*?)\n    \}', self.settings_source, re.S).group(1)
        script_src = [line for line in block.splitlines() if '"script-src"' in line][0]
        constants = {"SELF": SELF, "NONCE": NONCE, "UNSAFE_INLINE": UNSAFE_INLINE, "UNSAFE_EVAL": UNSAFE_EVAL}
        sources = [constants[name] for name in re.findall(r"[A-Z_]+", script_src.split(":", 1)[1])]
        with override_settings(CONTENT_SECURITY_POLICY=policy(**{"script-src": sources})):
            self.assertEqual(check_script_src_nonce_only(), [])
