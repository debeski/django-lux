"""Move a project's own file-history rows into DjangoLux's `FileVersion` table.

Projects that kept PDF history before DjangoLux had it (a `DocumentFileVersion`
model with a generic document link) run this once when they switch to
`register_document_file`. Only rows move; archived files stay exactly where they
are on disk and the new rows point at the same storage names.

* **Dry run by default.** `--apply` writes, inside one transaction.
* **Idempotent.** A row is identified by document, field and version number; a
  row already adopted with identical values is skipped, a different one with the
  same identity is a conflict and stops the run before anything is written.
* **Every value is kept**: link, field, version, action, archived file name,
  before/after names, page count, metadata, scope, created/updated/deleted
  times and users.
* `--verify` re-reads every source row and checks its copy and that the
  archived file exists and can be read.
* The source table is never modified.
"""

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

COPIED_FIELDS = (
    'content_type_id', 'object_id', 'document_model', 'field_name', 'version_number', 'action_type',
    'active_name_before', 'active_name_after', 'page_count', 'metadata', 'scope_id',
    'created_at', 'updated_at', 'created_by_id', 'updated_by_id', 'deleted_at', 'deleted_by_id',
)
REQUIRED_FIELDS = (
    'content_type', 'object_id', 'field_name', 'version_number', 'action_type', 'archived_file',
    'active_name_before', 'active_name_after', 'page_count', 'metadata',
)


def _values(row):
    values = {name: getattr(row, name, None) for name in COPIED_FIELDS}
    values['document_model'] = values['document_model'] or ''
    values['archived_file'] = row.archived_file.name
    return values


class Command(BaseCommand):
    help = "Copy a project's file-history rows (app_label.Model) into dlux FileVersion; archived files stay in place."

    def add_arguments(self, parser):
        parser.add_argument('model', help='Source history model, e.g. documents.DocumentFileVersion')
        parser.add_argument('--apply', action='store_true', help='Write the copies. Without it nothing is written.')
        parser.add_argument('--verify', action='store_true', help='Check every source row against its copy and its archived file.')

    def handle(self, *args, model, apply=False, verify=False, **options):
        from dlux.models import FileVersion

        try:
            source = apps.get_model(model)
        except (LookupError, ValueError) as exc:
            raise CommandError(f'Unknown model {model!r}.') from exc
        missing = [name for name in REQUIRED_FIELDS if not any(f.name == name for f in source._meta.get_fields())]
        if missing:
            raise CommandError(f'{model} lacks the history fields: {", ".join(missing)}.')
        manager = getattr(source, 'all_objects', source._default_manager)
        rows = list(manager.all().order_by('pk'))

        plan, skipped, conflicts = [], 0, []
        for row in rows:
            values = _values(row)
            existing = FileVersion.all_objects.filter(
                content_type_id=values['content_type_id'], object_id=values['object_id'],
                field_name=values['field_name'], version_number=values['version_number'],
            ).first()
            if existing is None:
                plan.append(values)
            elif _values(existing) == values:
                skipped += 1
            else:
                conflicts.append(row.pk)

        self.stdout.write(f'{len(rows)} source rows: {len(plan)} to copy, {skipped} already adopted, {len(conflicts)} conflicts.')
        if conflicts:
            raise CommandError(f'Conflicting FileVersion rows for source ids {conflicts[:20]}; nothing was written.')

        if apply and plan:
            with transaction.atomic():
                for values in plan:
                    copy = FileVersion(**{name: values[name] for name in COPIED_FIELDS if name not in ('created_at', 'updated_at')})
                    copy.archived_file.name = values['archived_file']
                    # Bypass ScopedModel.save(): the copy keeps its original actors and scope, not the operator's.
                    FileVersion.all_objects.bulk_create([copy])
                    FileVersion.all_objects.filter(
                        content_type_id=values['content_type_id'], object_id=values['object_id'],
                        field_name=values['field_name'], version_number=values['version_number'],
                    ).update(created_at=values['created_at'], updated_at=values['updated_at'])
            self.stdout.write(self.style.SUCCESS(f'Copied {len(plan)} rows.'))
        elif plan:
            self.stdout.write('Dry run: re-run with --apply to copy.')

        if verify:
            self._verify(rows)

    def _verify(self, rows):
        from dlux.models import FileVersion

        problems = []
        for row in rows:
            values = _values(row)
            copy = FileVersion.all_objects.filter(
                content_type_id=values['content_type_id'], object_id=values['object_id'],
                field_name=values['field_name'], version_number=values['version_number'],
            ).first()
            if copy is None or _values(copy) != values:
                problems.append(f'source {row.pk}: copy missing or different')
                continue
            storage = copy.archived_file.storage
            if not storage.exists(copy.archived_file.name):
                problems.append(f'source {row.pk}: archived file {copy.archived_file.name} is missing')
                continue
            try:
                with storage.open(copy.archived_file.name, 'rb') as stream:
                    stream.read(1)
            except OSError:
                problems.append(f'source {row.pk}: archived file {copy.archived_file.name} cannot be read')
        if problems:
            for problem in problems[:50]:
                self.stdout.write(self.style.ERROR(problem))
            raise CommandError(f'Verification failed for {len(problems)} of {len(rows)} rows.')
        self.stdout.write(self.style.SUCCESS(f'Verified {len(rows)} rows and their archived files.'))
