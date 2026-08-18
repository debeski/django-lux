"""Facade and split-integrity guards for the Phase 1 package splits.

Seven modules became packages in v1.8.0 — `forms`, `models`, `reports`, `discovery`,
`backup`, `translations`. Each keeps a `__init__.py` facade so
`from dlux.X import Y` is unchanged for this package and for downstream projects.

These tests pin the properties that a split can silently break, each of which
actually went wrong at least once while doing the work:

* a symbol quietly dropped from the facade,
* a decorator lost because the extractor started at the `def` line rather than
  the first decorator (three `@lru_cache` were lost this way),
* a relative import left pointing at the new sub-package instead of `dlux`
  (`from . import __version__`, and a `from .registration import ...` that
  resolved to the wrong module and only failed on a live request),
* a model class not re-exported, which removes it from Django's app registry.
"""
from dlux.tests.harness import setup_test_environment

setup_test_environment()

import ast
import importlib
import pathlib

from django.apps import apps
from django.db import models as django_models
from django.test import SimpleTestCase

PACKAGE = pathlib.Path(__file__).resolve().parents[1]
ARCHIVE = PACKAGE.parent / '.xpose' / 'dlux'

# package name -> archived single-module source it replaced
SPLITS = {
    'forms': 'forms.py',
    'models': 'models.py',
    'reports': 'reports.py',
    'discovery': 'discovery.py',
    'backup': 'backup.py',
    'translations': 'translations.py',
    'api': 'api.py',
    'scaffold': 'scaffold.py',
}


def _archived_tree(filename):
    return ast.parse((ARCHIVE / filename).read_text(encoding='utf-8'))


def _top_level_symbols(tree):
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names |= {t.id for t in node.targets if isinstance(t, ast.Name)}
    return names


def _sub_packages():
    """Every dlux sub-package, so a new one is guarded the day it is created.

    Iterating a hardcoded list is how `dlux/auth/` and `dlux/contracts/` were
    each created unguarded and each shipped the same relative-import bug.
    """
    skip = {'migrations', 'tests', 'static', 'templates', '__pycache__'}
    return sorted(
        d.name for d in PACKAGE.iterdir()
        if d.is_dir() and d.name not in skip and (d / '__init__.py').exists()
    )


class FacadeParityTests(SimpleTestCase):
    def test_every_original_symbol_is_still_importable(self):
        missing = {}
        for package, filename in SPLITS.items():
            if not (ARCHIVE / filename).exists():
                continue
            module = importlib.import_module(f'dlux.{package}')
            absent = sorted(
                name for name in _top_level_symbols(_archived_tree(filename))
                if not hasattr(module, name)
            )
            if absent:
                missing[package] = absent

        self.assertEqual(
            missing, {},
            'Symbols lost from a package facade: ' + repr(missing)
            + '. Re-export them from the package __init__.py — projects import them.',
        )


class DecoratorPreservationTests(SimpleTestCase):
    """`ast` reports a decorated node's lineno at `def`, not at the decorator."""

    def test_no_decorator_was_dropped_in_a_split(self):
        lost = {}
        for package, filename in SPLITS.items():
            if not (ARCHIVE / filename).exists():
                continue
            expected = {
                node.name: [ast.unparse(d) for d in node.decorator_list]
                for node in _archived_tree(filename).body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and node.decorator_list
            }
            if not expected:
                continue
            actual = {}
            for path in (PACKAGE / package).rglob('*.py'):
                for node in ast.parse(path.read_text(encoding='utf-8')).body:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        actual[node.name] = [ast.unparse(d) for d in node.decorator_list]
            for name, decorators in expected.items():
                if actual.get(name) != decorators:
                    lost.setdefault(package, []).append(
                        f'{name}: expected {decorators}, found {actual.get(name)}')

        self.assertEqual(
            lost, {},
            'Decorator(s) lost in a package split: ' + repr(lost)
            + '. Extract source from min(decorator.lineno), not node.lineno.',
        )


class FreeNameResolutionTests(SimpleTestCase):
    """A split can leave a function referring to a name its new module lacks.

    `dlux/scaffold/legacy.py` used `__version__` without importing it: the body
    was byte-identical to the original and the module imported fine, because the
    name is only read when the function runs. Compiling each module and walking
    its code objects catches that statically.
    """

    def test_no_function_reads_a_name_its_module_cannot_provide(self):
        import builtins

        offenders = []
        for package in _sub_packages():
            root = PACKAGE / package
            if not root.exists():
                continue
            for path in sorted(root.rglob('*.py')):
                source = path.read_text(encoding='utf-8')
                tree = ast.parse(source)
                # Module-level bindings: imports, assignments, defs.
                provided = set(dir(builtins)) | {'__name__', '__file__', '__doc__', '__package__'}
                for node in ast.walk(tree):
                    if isinstance(node, (ast.Import, ast.ImportFrom)):
                        provided |= {a.asname or a.name.split('.')[0] for a in node.names}
                    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        provided.add(node.name)
                    elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                        provided.add(node.id)
                    elif isinstance(node, ast.arg):
                        provided.add(node.arg)
                    elif isinstance(node, ast.ExceptHandler) and node.name:
                        provided.add(node.name)
                    elif isinstance(node, (ast.Global, ast.Nonlocal)):
                        provided |= set(node.names)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                        if node.id not in provided:
                            offenders.append(
                                f'{path.relative_to(PACKAGE)}:{node.lineno} reads '
                                f'undefined name {node.id!r}')

        self.assertEqual(offenders, [], 'Undefined name(s): ' + '; '.join(sorted(set(offenders))))


class RelativeImportDepthTests(SimpleTestCase):
    """A sub-module's `.` is the package, not `dlux`."""

    def test_no_relative_import_resolves_to_a_missing_sibling(self):
        offenders = []
        # Every sub-package, not just the ones that replaced a single module:
        # `dlux/auth/` was assembled from six top-level modules and has exactly
        # the same depth hazard, without ever having had a facade.
        for package in _sub_packages():
            root = PACKAGE / package
            if not root.exists():
                continue
            siblings = {p.stem for p in root.rglob('*.py')} | {
                p.name for p in root.iterdir() if p.is_dir()
            }
            # Names the package's own __init__ defines or re-exports.
            exported = set()
            init = root / '__init__.py'
            if init.exists():
                for node in ast.parse(init.read_text(encoding='utf-8')).body:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        exported.add(node.name)
                    elif isinstance(node, ast.Assign):
                        exported |= {t.id for t in node.targets if isinstance(t, ast.Name)}
                    elif isinstance(node, (ast.Import, ast.ImportFrom)):
                        exported |= {a.asname or a.name.split('.')[0] for a in node.names}
            for path in root.rglob('*.py'):
                tree = ast.parse(path.read_text(encoding='utf-8'))
                for node in ast.walk(tree):
                    if not isinstance(node, ast.ImportFrom) or node.level != 1:
                        continue
                    if node.module is None:
                        # `from . import X` is correct when X is a sibling module
                        # or a name the package's own __init__ defines. It is the
                        # historical bug only when X is neither — then `.` was
                        # meant as dlux (e.g. `from . import __version__`).
                        unresolved = sorted(
                            a.name for a in node.names
                            if a.name not in siblings and a.name not in exported
                        )
                        if unresolved:
                            offenders.append(
                                f'{path.relative_to(PACKAGE)}:{node.lineno} `from . import '
                                f'{", ".join(unresolved)}` — `.` is the sub-package '
                                f'here, not dlux')
                        continue
                    head = node.module.split('.')[0]
                    if head == path.stem:
                        # A module is its own sibling, so the membership check
                        # below cannot see this: `from .notifications import X`
                        # inside `api/notifications.py` used to mean
                        # `dlux.notifications` and now silently means itself.
                        offenders.append(
                            f'{path.relative_to(PACKAGE)}:{node.lineno} `from .{node.module}` '
                            f'resolves to the importing module itself')
                    elif head not in siblings:
                        offenders.append(
                            f'{path.relative_to(PACKAGE)}:{node.lineno} `from .{node.module}` '
                            f'has no sibling named {head!r}')

        self.assertEqual(offenders, [], 'Broken relative import(s): ' + '; '.join(offenders))


class ModelRegistryTests(SimpleTestCase):
    """Django resolves models through `<app>.models` — omissions are invisible."""

    def test_every_concrete_model_is_registered_under_dlux(self):
        import dlux.models as models_package

        registered = {m.__name__: m._meta.app_label for m in apps.get_app_config('dlux').get_models()}
        expected = []
        for node in _archived_tree('models.py').body:
            if not isinstance(node, ast.ClassDef):
                continue
            obj = getattr(models_package, node.name, None)
            if (isinstance(obj, type) and issubclass(obj, django_models.Model)
                    and not obj._meta.abstract and not obj._meta.proxy):
                expected.append(node.name)

        self.assertTrue(expected, 'no concrete models found in the archived module')
        self.assertEqual(
            sorted(name for name in expected if name not in registered), [],
            'Model(s) missing from the app registry — import them in dlux/models/__init__.py.',
        )
        self.assertEqual(
            {n: registered[n] for n in expected if registered.get(n) != 'dlux'}, {},
            'Model(s) registered under the wrong app_label.',
        )

class SystemSettingsFormShapeTests(SimpleTestCase):
    """Phase 1-B moved 84 methods and the 713-line layout into mixins.

    The class shape is the contract: field order drives rendering, and a lost
    `clean_<field>` silently stops validating that field. Both are compared
    against the archived pre-split module rather than against a hand-written list.
    """

    @staticmethod
    def _archived_form_class():
        import importlib.util
        import sys

        # The archive is a frozen pre-split snapshot, so it still imports
        # `dlux.asset_forms` — a module that moved to `dlux.forms.assets`. Alias
        # it rather than editing the archive: the point of this file is to be an
        # untouched reference, and where a dependency lives is not part of the
        # form shape being compared.
        import dlux.forms.assets

        aliased = 'dlux.asset_forms' not in sys.modules
        if aliased:
            sys.modules['dlux.asset_forms'] = dlux.forms.assets

        path = ARCHIVE / 'forms.py'
        spec = importlib.util.spec_from_file_location('dlux._archived_forms', path)
        module = importlib.util.module_from_spec(spec)
        module.__package__ = 'dlux'
        sys.modules['dlux._archived_forms'] = module
        try:
            spec.loader.exec_module(module)
        finally:
            if aliased:
                del sys.modules['dlux.asset_forms']
        return module.SystemSettingsForm

    def test_field_order_and_clean_methods_match_the_pre_split_class(self):
        from dlux.forms import SystemSettingsForm

        archived = self._archived_form_class()

        # Fields added since the split are fine; what must not happen is a
        # pre-split field changing position, which is what moving a declaration
        # into a mixin does (the metaclass orders mixin fields first). So compare
        # the archived order against the current order with new names filtered
        # out — every archived field still has to appear, in the same sequence.
        archived_order = list(archived.base_fields)
        current_order = [
            name for name in SystemSettingsForm.base_fields if name in set(archived_order)
        ]
        self.assertEqual(
            archived_order, current_order,
            'Declared field order changed. Field declarations must stay in the main '
            'class — moving them into mixins reorders them via the metaclass.',
        )
        archived_cleaners = sorted(n for n in dir(archived) if n.startswith('clean'))
        current_cleaners = {n for n in dir(SystemSettingsForm) if n.startswith('clean')}
        self.assertEqual(
            archived_cleaners,
            sorted(n for n in current_cleaners if n in set(archived_cleaners)),
            'A clean_* method was lost or renamed; that field silently stops '
            'being validated.',
        )

    def test_every_group_mixin_is_in_the_form_mro(self):
        from dlux.forms import SystemSettingsForm
        from dlux.forms import system_settings_groups as groups

        missing = [
            name for name in groups.__all__
            if getattr(groups, name) not in SystemSettingsForm.__mro__
        ]
        self.assertEqual(missing, [], f'Mixin(s) not mixed into the form: {missing}')
