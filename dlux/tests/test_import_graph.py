"""Import-graph invariants.

Phase 0 of the Python restructure: before any module moves, lock down what makes
the current layout safe, so a later refactor cannot quietly undo it.

Three invariants, in order of severity:

1. No module-scope import cycle. This is the one that breaks deployments — a
   partner module observes a half-built module object, which is how a project's
   urls-reachable ``from dlux.utils import X`` fails, or how a ROOT_URLCONF ends
   up with no ``urlpatterns``.
2. The deferred-coupling clusters do not grow. 421 function-scope imports are
   what keep invariant 1 true; they are load-bearing, not incidental. A module
   joining one of those clusters is one promoted import away from a real cycle.
3. No import-time side effects. Module scope (including class bodies) must not
   call into settings/translations, which need the app registry and a request.
"""
from dlux.tests.harness import setup_test_environment

setup_test_environment()

import ast
import pathlib
import sys

from django.test import SimpleTestCase

_SCRIPTS = pathlib.Path(__file__).resolve().parents[2] / 'scripts'
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from import_cycles import analyse, build_graphs  # noqa: E402

# The coupling clusters as they stand. Shrinking them is progress and should be
# reflected here; growing them means a new module joined a cluster that is one
# promoted import away from a genuine cycle.
BASELINE_DEFERRED_CLUSTERS = {
    frozenset({
        'dlux', 'dlux.assets', 'dlux.context_processors', 'dlux.discovery',
        'dlux.managers', 'dlux.middleware', 'dlux.models', 'dlux.navbar',
        'dlux.notifications', 'dlux.auth.session_history', 'dlux.tables',
        'dlux.translations', 'dlux.updater', 'dlux.utils',
        'dlux.utils.activity_log', 'dlux.utils.authorization', 'dlux.utils.common',
        'dlux.utils.config', 'dlux.utils.crud', 'dlux.utils.discovery',
        'dlux.utils.import_export', 'dlux.utils.localization', 'dlux.utils.mail',
        'dlux.utils.navigation', 'dlux.utils.sections', 'dlux.utils.settings',
        'dlux.utils.twofactor', 'dlux.utils.users',
        # discovery sub-modules inherit dlux.discovery's deferred edges into
        # utils/translations (config reads and label lookups at call time).
        'dlux.discovery.catalog', 'dlux.discovery.inference', 'dlux.discovery.merge',
        'dlux.discovery.render', 'dlux.discovery.routes', 'dlux.discovery.sanitize',
        # translations.runtime holds the deferred config read that put
        # dlux.translations in this cluster; the string tables stay outside it.
        'dlux.translations.runtime',
        # models sub-modules inherit dlux.models' deferred edges (config reads,
        # sidebar cache invalidation, activity logging at call time). The leaf
        # data modules — scopes, assets, backup — stay outside.
        'dlux.models.activity', 'dlux.models.base', 'dlux.models.notifications',
        'dlux.models.settings', 'dlux.models.updater', 'dlux.models.users',
    }),
    frozenset({
        # The backup/reports/updater/tasks knot. Splitting `backup.py` and
        # `reports.py` into packages did not add coupling — it attributes the
        # existing deferred edges to the sub-modules that actually own them
        # (`.tasks` dispatch in archive/dispatch, progress reporting in create).
        'dlux.backup', 'dlux.backup._shared', 'dlux.backup.create',
        'dlux.backup.dispatch', 'dlux.backup.restore', 'dlux.backup.retry',
        'dlux.reports', 'dlux.reports.archive', 'dlux.tasks',
        'dlux.updater.agent_bridge', 'dlux.updater.control_link',
        'dlux.updater.image_update', 'dlux.updater.service',
        # The 1.8.0 hand-off writer: service.py imports it inside the apply and
        # rollback paths, and it reads image_update's state-dir helpers.
        'dlux.updater.package_request',
    }),
}

# Helpers that need the app registry, a configured system, or a request language.
# Calling them while a module is still importing either crashes or — worse —
# silently freezes an English default into a class attribute for the process.
IMPORT_TIME_UNSAFE_CALLS = {
    'get_strings', 'get_system_config', 'reverse', 'gettext', 'ugettext',
}


class ModuleScopeCycleTests(SimpleTestCase):
    def test_no_module_scope_import_cycles(self):
        cycles = analyse()['module_scope_cycles']

        self.assertEqual(
            cycles, [],
            'Module-scope import cycle(s) introduced: '
            + '; '.join(', '.join(group) for group in cycles)
            + '. Move one edge of the cycle into the function that needs it.',
        )

    def test_deferred_imports_are_still_doing_the_work(self):
        # If this drops sharply, the deferred edges were inlined — check that the
        # cycle test above still passes rather than assuming it is an improvement.
        self.assertGreater(analyse()['deferred_imports'], 300)


class DeferredCouplingBaselineTests(SimpleTestCase):
    def test_no_module_joins_a_coupling_cluster(self):
        clusters = {frozenset(group) for group in analyse()['deferred_cycles']}
        known = set().union(*BASELINE_DEFERRED_CLUSTERS)

        for cluster in clusters:
            new_members = cluster - known
            self.assertEqual(
                new_members, set(),
                f'{sorted(new_members)} joined a deferred-import cluster. Depend on '
                'a leaf module instead, or the next refactor turns this into a cycle.',
            )

    def test_cluster_count_does_not_grow(self):
        clusters = {frozenset(group) for group in analyse()['deferred_cycles']}

        self.assertLessEqual(len(clusters), len(BASELINE_DEFERRED_CLUSTERS))


class ImportTimeSideEffectTests(SimpleTestCase):
    """Module scope includes class bodies — both run while the module imports."""

    @staticmethod
    def _module_scope_calls(tree):
        found = []

        def walk(node, in_function):
            for child in ast.iter_child_nodes(node):
                entering = isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))
                if not in_function and isinstance(child, ast.Call):
                    name = getattr(child.func, 'id', None) or getattr(child.func, 'attr', None)
                    if name in IMPORT_TIME_UNSAFE_CALLS:
                        found.append((name, child.lineno))
                walk(child, in_function or entering)

        walk(tree, False)
        return found

    def test_no_settings_or_translation_lookups_run_at_import(self):
        files, _, _, _ = build_graphs()
        offenders = []
        for module, path in sorted(files.items()):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for name, lineno in self._module_scope_calls(tree):
                offenders.append(f'{module}:{lineno} calls {name}()')

        self.assertEqual(
            offenders, [],
            'Import-time side effect(s): ' + '; '.join(offenders)
            + '. Wrap the value with django.utils.functional.lazy, or move the '
            'call into the function/method that needs it.',
        )
