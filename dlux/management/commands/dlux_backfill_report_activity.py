"""Count records saved before activity logging in reports.

A record created before its deployment logged activity has no CREATE row, so
reports never count it. This writes that row from the record's own creation
time, creator, scope and number, marked ``details.backfilled`` (see
``dlux.reports.backfill``).

* **Dry run by default.** ``--apply`` writes, in batches.
* **Idempotent.** A record that already has a CREATE row is skipped.
* ``--model app_label.Model`` limits the run (repeatable); otherwise every model
  reports may count.
"""

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError

from dlux.reports.backfill import backfill_report_activity


class Command(BaseCommand):
    help = "Write the CREATE activity rows that records saved before activity logging lack, so reports count them."

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Write the rows. Without it nothing is written.')
        parser.add_argument('--model', action='append', default=[], help='Only this model (app_label.Model); repeatable.')
        parser.add_argument('--batch-size', type=int, default=500)

    def handle(self, *args, apply=False, model=None, batch_size=500, **options):
        models = []
        for label in model or []:
            try:
                models.append(apps.get_model(label))
            except (LookupError, ValueError) as exc:
                raise CommandError(f'Unknown model {label!r}.') from exc
        results = backfill_report_activity(models or None, apply=apply, batch_size=batch_size)
        total = 0
        for row in results:
            if row['skipped']:
                self.stdout.write(f"{row['model']}: skipped ({row['skipped']})")
                continue
            count = row['written'] if apply else row['missing']
            total += count
            self.stdout.write(f"{row['model']}: {count} {'written' if apply else 'missing'}")
        if apply:
            self.stdout.write(self.style.SUCCESS(f'Wrote {total} CREATE rows.'))
        else:
            self.stdout.write(f'{total} records have no CREATE row. Run again with --apply to write them.')
