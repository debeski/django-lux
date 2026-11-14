import json
from pathlib import Path
import shutil
import subprocess

from django.test import SimpleTestCase
from django.template.loader import render_to_string

from dlux.translations.strings.ar import STRINGS as AR_STRINGS
from dlux.translations.strings.en import STRINGS as EN_STRINGS


class ScanLinkConnectionTests(SimpleTestCase):
    def test_uncertain_scan_guidance_is_rendered_in_both_languages(self):
        for strings in (EN_STRINGS, AR_STRINGS):
            with self.subTest(message=strings["scan_request_uncertain_message"]):
                rendered = render_to_string(
                    "dlux/helpers/scanlink/scan_messages.html",
                    {"DLUX_STRINGS": strings},
                )
                self.assertIn(
                    f'data-scan-request-uncertain="{strings["scan_request_uncertain_message"]}"',
                    rendered,
                )

    def test_scanlink_error_guidance_is_rendered_in_both_languages(self):
        from django.utils.html import escape

        attributes = {
            "data-scan-no-pages": "scan_no_pages_message",
            "data-scan-acquire-failed": "scan_acquire_failed_message",
            "data-scan-worker-crashed": "scan_worker_crashed_message",
            "data-scan-origin-not-allowed": "scan_origin_not_allowed_message",
        }
        for strings in (EN_STRINGS, AR_STRINGS):
            rendered = render_to_string("dlux/helpers/scanlink/scan_messages.html", {"DLUX_STRINGS": strings})
            for attribute, key in attributes.items():
                with self.subTest(attribute=attribute, language=strings is AR_STRINGS):
                    self.assertIn(f'{attribute}="{escape(strings[key])}"', rendered)

    def test_browser_transport_and_guidance(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        root = Path(__file__).resolve().parents[2]
        script = root / "dlux/tests/fixtures/scanlink/scenarios.mjs"
        result = subprocess.run(
            [node, str(script), str(root)],
            capture_output=True, text=True, timeout=30, cwd=root,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["passed"], 23)
