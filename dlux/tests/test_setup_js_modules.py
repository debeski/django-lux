"""Static contract for the setup wizard's JavaScript modules.

`setup/js/main.js` is being split into feature modules that share state through
namespaces on `window` (`DluxSetup`, `DluxSetupDom`, `DluxSetupModel`). Two
mistakes are easy to make and neither shows up in `node --check`:

* a module calls a function another module owns without destructuring it, which
  throws a `ReferenceError` the first time that code path runs — often deep in a
  wizard step nobody opens during a smoke test;
* a module is listed in `base.html` before the module it imports from, so the
  destructure at the top of its IIFE reads `undefined` and the page dies on
  load while still rendering plausibly.

Both have happened during this split. These tests make them fail here instead.
"""
import re
from pathlib import Path

from django.test import SimpleTestCase

JS_DIR = Path(__file__).resolve().parents[1] / 'static' / 'dlux' / 'setup' / 'js'
BASE_HTML = Path(__file__).resolve().parents[1] / 'templates' / 'dlux' / 'base.html'

NAMESPACES = ('DluxSetup', 'DluxSetupDom', 'DluxSetupModel')

# main.js is the orchestrator: it loads last and destructures every namespace,
# so it is checked for load order but not for ownership.
ORCHESTRATOR = 'main.js'


def _modules():
    return sorted(p for p in JS_DIR.glob('*.js'))


def _export_block(source):
    """The names a module publishes onto a namespace."""
    names = set()
    for match in re.finditer(
        r'root\.(?:' + '|'.join(NAMESPACES) + r')\s*=\s*'
        r'(?:Object\.assign\([^,]*,\s*)?\{(.*?)\n    \}',
        source, re.S,
    ):
        names |= set(re.findall(r'^\s+([A-Za-z_$][\w$]*),?\s*$', match.group(1), re.M))
    return names


def _body(source):
    """Everything before the trailing export assignment."""
    cut = source.rfind('root.DluxSetup')
    return source[:cut] if cut != -1 else source


def _declared(body):
    own = set(re.findall(r'\n    function ([A-Za-z_$][\w$]*)\(', body))
    imported = set()
    for match in re.finditer(r'const \{(.*?)\} = root\.\w+;', body, re.S):
        imported |= {
            part.strip() for part in match.group(1).replace('\n', ' ').split(',')
            if part.strip()
        }
    for match in re.finditer(r'const \{ ([^}]*) \} = root\.\w+;', body):
        imported |= {part.strip() for part in match.group(1).split(',') if part.strip()}
    return own, imported


def _script_order():
    html = BASE_HTML.read_text(encoding='utf-8')
    return [
        m.group(1) for m in
        re.finditer(r"dlux_static 'dlux/setup/js/([\w.]+\.js)'", html)
    ]


class SetupJsModuleContractTests(SimpleTestCase):
    def test_every_module_is_loaded_by_base_html(self):
        """A module nobody loads is dead weight; one loaded twice runs twice."""
        on_disk = {p.name for p in _modules()}
        listed = _script_order()
        self.assertEqual(
            sorted(listed), sorted(set(listed)),
            f'a setup module is listed more than once in base.html: {listed}',
        )
        self.assertEqual(
            on_disk, set(listed),
            f'on disk but not loaded: {sorted(on_disk - set(listed))}; '
            f'loaded but missing: {sorted(set(listed) - on_disk)}',
        )

    def test_main_js_loads_last(self):
        order = _script_order()
        self.assertEqual(
            order[-1], ORCHESTRATOR,
            f'{ORCHESTRATOR} destructures every namespace at the top of its IIFE, '
            f'so it must load after all of them; order is {order}',
        )

    def test_cross_module_calls_are_imported(self):
        """Calling another module's export without destructuring it throws.

        `shell.js` shipped briefly calling `rememberSetupWizardStep` from
        `state.js` with no import. `node --check` passed; the wizard threw a
        ReferenceError on load.
        """
        owner = {}
        for path in _modules():
            if path.name == ORCHESTRATOR:
                continue
            for name in _export_block(path.read_text(encoding='utf-8')):
                owner.setdefault(name, path.name)

        gaps = {}
        for path in _modules():
            if path.name == ORCHESTRATOR:
                continue
            body = _body(path.read_text(encoding='utf-8'))
            own, imported = _declared(body)
            called = set(re.findall(r'\b([A-Za-z_$][\w$]*)\s*\(', body))
            missing = sorted(
                name for name in called
                if name in owner
                and owner[name] != path.name
                and name not in own
                and name not in imported
            )
            if missing:
                gaps[path.name] = [(n, owner[n]) for n in missing]

        self.assertEqual(
            gaps, {},
            'these modules call functions they never imported:\n'
            + '\n'.join(
                f'  {mod}: ' + ', '.join(f'{n} (from {src})' for n, src in items)
                for mod, items in sorted(gaps.items())
            ),
        )

    def test_a_module_loads_after_everything_it_imports_from(self):
        """Destructuring happens at IIFE evaluation, so order is not cosmetic."""
        order = _script_order()
        position = {name: i for i, name in enumerate(order)}

        owner = {}
        for path in _modules():
            if path.name == ORCHESTRATOR:
                continue
            for name in _export_block(path.read_text(encoding='utf-8')):
                owner.setdefault(name, path.name)

        problems = []
        for path in _modules():
            if path.name == ORCHESTRATOR:
                continue
            body = _body(path.read_text(encoding='utf-8'))
            _, imported = _declared(body)
            for name in imported:
                source = owner.get(name)
                if not source or source == path.name:
                    continue
                if position.get(source, -1) > position.get(path.name, -1):
                    problems.append(
                        f'{path.name} imports {name} from {source}, '
                        f'which base.html loads later'
                    )

        self.assertEqual(problems, [], '\n'.join(problems))
