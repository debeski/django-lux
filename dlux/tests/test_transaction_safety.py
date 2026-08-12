"""Swallowed database errors must be wrapped in a savepoint.

The failure this guards against is invisible on SQLite and silent on PostgreSQL
until it takes down an unrelated statement:

    with transaction.atomic():          # e.g. a migration, or an atomic request
        ...
        try:
            Thing.objects.filter(...)   # table does not exist yet on a fresh DB
        except ProgrammingError:
            pass                        # Python recovers — the server does not
        ...
        SomeOther.objects.create(...)   # dies: "current transaction is aborted"

Catching the Python exception does not un-abort the PostgreSQL transaction, so
the traceback points at whatever statement ran *next* and says nothing about the
real cause. `with transaction.atomic():` around the risky query issues a
SAVEPOINT, and the rollback on failure returns the transaction to a usable state.

SQLite does not reproduce any of this — a swallowed error there leaves the
connection perfectly usable — so a behavioural test on the default test database
cannot tell the fixed code from the broken code. Hence a static guard.
"""
from dlux.tests.harness import setup_test_environment

setup_test_environment()

import ast
import pathlib

from django.test import SimpleTestCase

DB_ERRORS = {'ProgrammingError', 'OperationalError', 'DatabaseError', 'InternalError'}
# Attribute access that means "this block talks to the database".
QUERY_MARKERS = {'objects', 'filter', 'exists', 'count', 'first', 'last', 'all', 'get',
                 'exclude', 'values', 'values_list', 'cursor', 'execute', 'aggregate'}

PACKAGE = pathlib.Path(__file__).resolve().parents[1]


def _handler_catches_db_error(handler):
    if handler.type is None:
        return True  # bare except swallows database errors too
    return any(
        isinstance(node, ast.Name) and node.id in DB_ERRORS
        for node in ast.walk(handler.type)
    )


def _block_queries(nodes):
    for node in nodes:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Attribute) and sub.attr in QUERY_MARKERS:
                return True
    return False


def _block_has_savepoint(nodes):
    """A `with transaction.atomic():` (or `atomic(...)`) guarding the query."""
    for node in nodes:
        for sub in ast.walk(node):
            if isinstance(sub, (ast.With, ast.AsyncWith)):
                for item in sub.items:
                    call = item.context_expr
                    func = call.func if isinstance(call, ast.Call) else call
                    name = getattr(func, 'attr', None) or getattr(func, 'id', None)
                    if name == 'atomic':
                        return True
    return False


class SwallowedDatabaseErrorTests(SimpleTestCase):
    def test_every_swallowed_query_error_sits_in_a_savepoint(self):
        offenders = []
        for path in sorted(PACKAGE.rglob('*.py')):
            rel = path.relative_to(PACKAGE)
            if rel.parts[0] in {'tests', 'migrations'} or rel.parts[:2] == ('scaffold', 'templates'):
                continue
            try:
                tree = ast.parse(path.read_text(encoding='utf-8'))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Try):
                    continue
                if not any(_handler_catches_db_error(h) for h in node.handlers):
                    continue
                if not _block_queries(node.body):
                    continue
                if not _block_has_savepoint(node.body):
                    offenders.append(f'dlux/{rel}:{node.lineno}')

        self.assertEqual(
            offenders, [],
            'Query in a try/except that swallows a database error, with no '
            'savepoint: ' + ', '.join(offenders)
            + '. Wrap the query in `with transaction.atomic():` — on PostgreSQL '
            'the caught error leaves the outer transaction aborted and the next '
            'statement fails instead, pointing the traceback at the wrong place.',
        )


class BootstrapQueryTests(SimpleTestCase):
    """The three sites that run before their own tables exist."""

    def test_font_asset_and_migrator_lookups_are_savepointed(self):
        sites = {
            'fonts.py': 'ManagedFontFamily',
            'forms/assets.py': 'ManagedAsset',
            'management/commands/migrator.py': 'model.objects.exists()',
        }
        for filename, marker in sites.items():
            with self.subTest(site=filename):
                source = (PACKAGE / filename).read_text(encoding='utf-8')
                self.assertIn(marker, source)
                self.assertIn('transaction.atomic()', source)
