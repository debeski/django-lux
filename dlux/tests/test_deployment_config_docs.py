import re
from pathlib import Path

from django.test import SimpleTestCase


class DeploymentConfigurationDocsTests(SimpleTestCase):
    def test_every_consumed_dlux_deployment_key_is_documented(self):
        package_root = Path(__file__).resolve().parents[1]
        docs_path = package_root.parent / 'docs' / 'deployment-configuration.md'
        if not docs_path.exists():
            self.skipTest('source documentation is not installed')

        patterns = (
            re.compile(r"""getattr\(settings,\s*['"](DLUX_[A-Z0-9_]+)['"]"""),
            re.compile(r"""settings\.(DLUX_[A-Z0-9_]+)"""),
            re.compile(r"""scope\.(?:get|setdefault)\(\s*['"](DLUX_[A-Z0-9_]+)['"]"""),
            re.compile(r"""scope\[\s*['"](DLUX_[A-Z0-9_]+)['"]\s*\]"""),
            re.compile(r"""os\.(?:getenv|environ\.get)\(\s*['"](DLUX_[A-Z0-9_]+)['"]"""),
        )
        discovered = set()
        for path in package_root.rglob('*.py'):
            if 'tests' in path.parts or 'migrations' in path.parts:
                continue
            source = path.read_text(encoding='utf-8')
            for pattern in patterns:
                discovered.update(pattern.findall(source))

        documentation = docs_path.read_text(encoding='utf-8')
        missing = sorted(key for key in discovered if f'`{key}`' not in documentation)
        self.assertEqual(missing, [])
