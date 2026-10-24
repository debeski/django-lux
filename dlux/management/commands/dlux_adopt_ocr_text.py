"""Move a project's own OCR rows into DjangoLux's `FileText` table.

For projects that ran OCR before DjangoLux had it (Archive's
`documents.DocumentOCR`: a generic document link plus field name and file
SHA-256). Run once when switching to DjangoLux OCR, after
`dlux_adopt_file_history` so the copies can link to adopted file versions.

* **Dry run by default.** `--apply` writes, inside one transaction.
* **Idempotent.** A row is identified by document, field and file SHA-256; one
  already adopted with identical values is skipped, a different one with the
  same identity is a conflict and stops the run before anything is written.
* Text, markdown, per-page JSON, engine/versions, timings, status, scope and
  audit times/users are kept. `file_version` is re-linked to the DjangoLux
  `FileVersion` that produced the same active file name, when there is one.
* The source table is never modified.
"""

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

COPIED_FIELDS = (
    'content_type_id', 'object_id', 'document_model', 'field_name', 'file_name', 'file_sha256', 'is_current',
    'status', 'source', 'requested_by_id', 'engine', 'engine_version', 'model_version', 'markdown', 'text',
    'pages', 'page_count', 'mean_confidence', 'timings', 'duration_ms', 'attempts', 'error', 'started_at',
    'finished_at', 'scope_id', 'created_at', 'updated_at', 'created_by_id', 'updated_by_id', 'deleted_at',
    'deleted_by_id',
)
REQUIRED_FIELDS = ('content_type', 'object_id', 'field_name', 'file_sha256', 'status', 'text')
IDENTITY = ('content_type_id', 'object_id', 'field_name', 'file_sha256')


def _values(row):
    values = {name: getattr(row, name, None) for name in COPIED_FIELDS}
    for name in ('document_model', 'file_name', 'source', 'engine', 'engine_version', 'model_version', 'markdown', 'error'):
        values[name] = values[name] or ''
    values['source'] = values['source'] or 'auto'
    values['pages'] = values['pages'] or []
    values['timings'] = values['timings'] or {}
    values['attempts'] = values['attempts'] or 0
    values['page_count'] = values['page_count'] or 0
    values['is_current'] = bool(values['is_current'])
    return values


class Command(BaseCommand):
    help = "Copy a project's OCR rows (app_label.Model) into dlux FileText."

    def add_arguments(self, parser):
        parser.add_argument('model', help='Source OCR model, e.g. documents.DocumentOCR')
        parser.add_argument('--apply', action='store_true', help='Write the copies. Without it nothing is written.')

    def handle(self, *args, model, apply=False, **options):
        from dlux.models import FileText, FileVersion

        try:
            source = apps.get_model(model)
        except (LookupError, ValueError) as exc:
            raise CommandError(f'Unknown model {model!r}.') from exc
        missing = [name for name in REQUIRED_FIELDS if not any(f.name == name for f in source._meta.get_fields())]
        if missing:
            raise CommandError(f'{model} lacks the OCR fields: {", ".join(missing)}.')
        manager = getattr(source, 'all_objects', source._default_manager)
        rows = list(manager.all().order_by('pk'))

        plan, skipped, conflicts = [], 0, []
        for row in rows:
            values = _values(row)
            existing = FileText.all_objects.filter(**{name: values[name] for name in IDENTITY}).first()
            if existing is None:
                plan.append(values)
            elif _values(existing) == values:
                skipped += 1
            else:
                conflicts.append(row.pk)

        self.stdout.write(f'{len(rows)} source rows: {len(plan)} to copy, {skipped} already adopted, {len(conflicts)} conflicts.')
        if conflicts:
            raise CommandError(f'Conflicting FileText rows for source ids {conflicts[:20]}; nothing was written.')
        if not plan:
            return
        if not apply:
            self.stdout.write('Dry run: re-run with --apply to copy.')
            return
        with transaction.atomic():
            for values in plan:
                version = FileVersion.all_objects.filter(
                    content_type_id=values['content_type_id'], object_id=values['object_id'],
                    field_name=values['field_name'], active_name_after=values['file_name'],
                ).order_by('-version_number').first() if values['file_name'] else None
                copy = FileText(**{name: values[name] for name in COPIED_FIELDS if name not in ('created_at', 'updated_at')})
                copy.file_version = version
                # Bypass ScopedModel.save(): the copy keeps its original actors and scope, not the operator's.
                FileText.all_objects.bulk_create([copy])
                FileText.all_objects.filter(**{name: values[name] for name in IDENTITY}).update(
                    created_at=values['created_at'], updated_at=values['updated_at'],
                )
        self.stdout.write(self.style.SUCCESS(f'Copied {len(plan)} rows.'))
