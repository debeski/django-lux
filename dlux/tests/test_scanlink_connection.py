import json
from pathlib import Path
import shutil
import subprocess

from django.test import SimpleTestCase


class ScanLinkConnectionTests(SimpleTestCase):
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
        self.assertEqual(json.loads(result.stdout)["passed"], 12)
