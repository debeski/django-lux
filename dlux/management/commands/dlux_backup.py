"""
Take a system backup in the foreground and report it as one JSON line.

Composer execs this before an operator's `composer dlux update` or `dlux
rollback`, which swap DjangoLux without passing through DjangoLux's own update
path and so would otherwise run with no safety snapshot. It runs the same
backup the Backup page and the pre-update step use (server-key encryption),
so the result is restorable from the Backup page.

Exit status is 0 only when the backup completed; the last line of stdout is
always the JSON result, so a caller can parse it without reading the logs.
"""
import json

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError

from dlux.backup import run_system_backup


class Command(BaseCommand):
    help = "Take a system backup now and print the result as JSON"

    def add_arguments(self, parser):
        parser.add_argument(
            "--scope", choices=("data", "full"), default="data",
            help="data = database only (default); full = database and media",
        )
        parser.add_argument(
            "--trigger", choices=("update", "manual", "scheduled"), default="manual",
            help="Recorded on the backup row; Composer passes 'update'",
        )
        parser.add_argument(
            "--requested-by", default="composer",
            help="Recorded as the requester",
        )

    def handle(self, *args, **options):
        SystemBackup = apps.get_model("dlux", "SystemBackup")
        backup = SystemBackup.objects.create(
            requested_by_username=str(options["requested_by"] or "composer")[:150],
            trigger=options["trigger"],
            media_included=options["scope"] == "full",
        )
        run_system_backup(backup.pk)
        backup.refresh_from_db()
        if backup.status == SystemBackup.STATUS_PENDING:
            # A retry was armed. The caller is about to decide whether to swap
            # code on this answer, so the failure is final: no stray run later.
            SystemBackup.objects.filter(pk=backup.pk, status=SystemBackup.STATUS_PENDING).update(
                status=SystemBackup.STATUS_FAILED, next_attempt_at=None,
            )
            backup.refresh_from_db()
        result = {
            "ok": backup.status == SystemBackup.STATUS_COMPLETED,
            "token": backup.token,
            "status": backup.status,
            "trigger": backup.trigger,
            "scope": options["scope"],
            "rows": backup.row_count,
            "files": backup.file_count,
            "size": backup.file_size,
            "path": backup.file_path,
            "error": backup.error,
        }
        self.stdout.write(json.dumps(result))
        if not result["ok"]:
            raise CommandError(f"The backup did not complete: {backup.error or backup.status}")
