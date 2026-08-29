"""Row-level access hooks: `dlux.access`.

Which rows a user may see is the project's business, not dlux's — but the
dynamic modal's object lookup is dlux's, and it is the one place all of edit,
view and delete resolve an object through. These cover the registry that lets a
project narrow it without reaching into `dlux.views.sections` from outside.
"""
from dlux.tests.harness import setup_test_environment  # noqa: F401

from django.contrib.auth import get_user_model
from django.test import TestCase

from dlux import access
from dlux.models import ActivityLog

User = get_user_model()


class ModalQuerysetFilterTests(TestCase):
    def tearDown(self):
        for registered in access.get_modal_queryset_filters():
            access.unregister_modal_queryset_filter(registered)

    def test_a_registered_filter_narrows_the_lookup(self):
        def only_nothing(queryset, user):
            return queryset.none()

        access.register_modal_queryset_filter(only_nothing)
        narrowed = access.apply_modal_queryset_filters(ActivityLog.objects.all(), None)
        self.assertEqual(narrowed.count(), 0)

    def test_filters_run_in_registration_order_and_compose(self):
        calls = []

        def first(queryset, user):
            calls.append('first')
            return queryset

        def second(queryset, user):
            calls.append('second')
            return queryset.none()

        access.register_modal_queryset_filter(first)
        access.register_modal_queryset_filter(second)
        result = access.apply_modal_queryset_filters(ActivityLog.objects.all(), None)
        self.assertEqual(calls, ['first', 'second'])
        self.assertEqual(result.count(), 0)

    def test_registering_the_same_filter_twice_does_not_stack_it(self):
        """`AppConfig.ready()` may run more than once, and a filter applied
        twice is at best wasted work and at worst a doubled join."""
        def noop(queryset, user):
            return queryset

        access.register_modal_queryset_filter(noop)
        access.register_modal_queryset_filter(noop)
        self.assertEqual(len(access.get_modal_queryset_filters()), 1)

    def test_a_filter_that_raises_is_skipped_closed(self):
        """It must not take the modal down, and it must not widen what is shown:
        the queryset it was handed is kept, which is the narrower answer.
        """
        def narrow(queryset, user):
            return queryset.none()

        def boom(queryset, user):
            raise RuntimeError('bad filter')

        # A row has to exist, or `.none()` and `.all()` both count zero and the
        # assertion passes whatever the code does.
        ActivityLog.objects.create(action='CREATE', model_name='Probe')
        self.assertEqual(ActivityLog.objects.count(), 1)

        access.register_modal_queryset_filter(narrow)
        access.register_modal_queryset_filter(boom)
        with self.assertLogs('dlux', level='ERROR'):
            result = access.apply_modal_queryset_filters(ActivityLog.objects.all(), None)
        self.assertEqual(result.count(), 0, 'a broken filter must not undo an earlier one')

    def test_a_non_callable_is_refused_at_registration(self):
        with self.assertRaises(ValueError):
            access.register_modal_queryset_filter('not callable')

    def test_the_modal_lookup_applies_registered_filters(self):
        """The point of the registry: no wrapping of dlux internals required."""
        from dlux.views import sections

        seen = []

        def watcher(queryset, user):
            seen.append(queryset.model)
            return queryset.none()

        access.register_modal_queryset_filter(watcher)
        user = User.objects.create_superuser('root_access', 'r@x.com', 'pw')
        result = sections._scope_filtered_modal_queryset(ActivityLog, user)
        self.assertEqual(seen, [ActivityLog])
        self.assertEqual(result.count(), 0, 'a superuser is not exempt from a row filter')

    def test_the_module_pulls_in_nothing_from_dlux(self):
        """Why the registry exists at all: a project registers from
        `AppConfig.ready()`, and importing `dlux.views` there triggers section
        discovery — a database query during startup.
        """
        import ast
        from pathlib import Path

        # Parsed, not grepped: the module's own docstring shows a project
        # importing from it, and a line scan reads that example as an import.
        tree = ast.parse((Path(__file__).resolve().parent.parent / 'access.py').read_text())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or '.' * node.level)
        offenders = {name for name in imported if name.startswith(('dlux', '.'))}
        self.assertEqual(offenders, set(), 'dlux.access must stay import-free')
