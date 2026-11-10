"""The test fixture app's migrations must match its models.

`document_files_app` is migrated so PostgreSQL can create its tables after
`dlux_scope`. A field added to its models without a migration leaves the test
tables a column short on every database, and hundreds of document tests then fail
with "column does not exist"; this test names the cause instead.
"""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase


class FixtureMigrationsTests(TestCase):
    def test_document_files_app_models_match_their_migrations(self):
        out = StringIO()
        try:
            call_command(
                'makemigrations', 'document_files_app',
                check=True, dry_run=True, stdout=out, stderr=StringIO(),
            )
        except SystemExit:
            self.fail(
                'document_files_app models changed without a migration; update '
                'dlux/tests/document_files_app/migrations:\n' + out.getvalue()
            )
