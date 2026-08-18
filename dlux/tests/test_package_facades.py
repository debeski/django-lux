"""Runtime integrity guards for the v1.8 package splits.

The checks inspect the committed split packages, never a local archive. They
protect module imports, declared facade exports, relative imports, Django model
registration, and the System Settings form's mixin composition.
"""
from dlux.tests.harness import setup_test_environment

setup_test_environment()

import ast
import importlib
import pathlib
import pkgutil

from django.apps import apps
from django.db import models as django_models
from django.forms import Field
from django.test import SimpleTestCase

PACKAGE = pathlib.Path(__file__).resolve().parents[1]
SPLITS = ('api', 'backup', 'discovery', 'forms', 'models', 'reports', 'scaffold', 'translations')


def _split_modules(package):
    root = importlib.import_module(f'dlux.{package}')
    names = [root.__name__]
    names.extend(info.name for info in pkgutil.walk_packages(root.__path__, f'{root.__name__}.'))
    return [importlib.import_module(name) for name in names]


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


class SplitPackageImportTests(SimpleTestCase):
    def test_every_committed_split_module_imports(self):
        failures = {}
        for package in SPLITS:
            try:
                _split_modules(package)
            except Exception as error:
                failures[package] = f'{type(error).__name__}: {error}'

        self.assertEqual(failures, {}, f'Split package import failure(s): {failures}')

    def test_declared_facade_exports_are_live(self):
        missing = {}
        for package in SPLITS:
            module = importlib.import_module(f'dlux.{package}')
            exports = getattr(module, '__all__', ())
            absent = sorted(name for name in exports if not hasattr(module, name))
            if absent:
                missing[package] = absent

        self.assertEqual(missing, {}, f'Facade exports that do not resolve: {missing}')


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

        expected = {
            candidate.__name__: candidate
            for module in _split_modules('models')
            for candidate in vars(module).values()
            if isinstance(candidate, type)
            and candidate.__module__ == module.__name__
            and issubclass(candidate, django_models.Model)
            and not candidate._meta.abstract
            and not candidate._meta.proxy
        }
        self.assertTrue(expected, 'no concrete models found in the split package')
        self.assertEqual(
            sorted(name for name, model in expected.items() if getattr(models_package, name, None) is not model),
            [],
            'Model(s) missing from dlux.models.',
        )

        registered = set(apps.get_app_config('dlux').get_models())
        self.assertEqual(
            sorted(name for name, model in expected.items() if model not in registered), [],
            'Model(s) missing from the app registry — import them in dlux/models/__init__.py.',
        )
        self.assertEqual(
            {name: model._meta.app_label for name, model in expected.items()
             if model._meta.app_label != 'dlux'},
            {},
            'Model(s) registered under the wrong app_label.',
        )


class SystemSettingsFormShapeTests(SimpleTestCase):
    def test_main_form_extra_field_order_matches_its_committed_source(self):
        from dlux.forms import SystemSettingsForm

        tree = ast.parse((PACKAGE / 'forms' / 'system_settings.py').read_text(encoding='utf-8'))
        form_class = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == 'SystemSettingsForm'
        )
        source_order = [
            target.id
            for node in form_class.body
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance((target := node.targets[0]), ast.Name)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and isinstance(node.value.func.value, ast.Name)
            and node.value.func.value.id == 'forms'
            and node.value.func.attr.endswith('Field')
        ]
        source_order = [
            name for name in source_order
            if name not in set(SystemSettingsForm._meta.fields or ())
        ]
        current_order = [
            name for name in SystemSettingsForm.base_fields if name in set(source_order)
        ]
        self.assertEqual(
            source_order, current_order,
            'Custom form-field order does not match Django\'s resolved form order.',
        )

    def test_group_cleaners_are_reachable_from_the_main_form(self):
        from dlux.forms import SystemSettingsForm
        from dlux.forms import system_settings_groups as groups

        missing = []
        for name in groups.__all__:
            mixin = getattr(groups, name)
            for cleaner, method in vars(mixin).items():
                if cleaner.startswith('clean_') and callable(method) and not callable(
                        getattr(SystemSettingsForm, cleaner, None)):
                    missing.append(f'{name}.{cleaner}')

        self.assertEqual(
            missing, [],
            f'Group cleaner(s) missing from SystemSettingsForm: {missing}',
        )

    def test_every_group_mixin_is_in_the_form_mro(self):
        from dlux.forms import SystemSettingsForm
        from dlux.forms import system_settings_groups as groups

        missing = [
            name for name in groups.__all__
            if getattr(groups, name) not in SystemSettingsForm.__mro__
        ]
        self.assertEqual(missing, [], f'Mixin(s) not mixed into the form: {missing}')

    def test_group_mixins_do_not_declare_form_fields(self):
        from dlux.forms import system_settings_groups as groups

        fields = [
            f'{name}.{attribute}'
            for name in groups.__all__
            for attribute, value in vars(getattr(groups, name)).items()
            if isinstance(value, Field)
        ]
        self.assertEqual(
            fields, [],
            'Form fields belong on SystemSettingsForm; mixin fields change Django field order.',
        )
