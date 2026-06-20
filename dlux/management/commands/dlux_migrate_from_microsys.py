"""In-place database migration from django-microsys to django-lux (dlux).

A fully-migrated ``django-microsys`` 2.4.1 database stores everything under the
``microsys`` app label: tables ``microsys_*``, ``django_content_type`` rows with
``app_label='microsys'`` (which is what permissions resolve through), recorded
migrations under app ``microsys``, and app-label-qualified
``UserActivityLog.model_key`` values like ``microsys.systemsettings``.

The ``dlux`` package is byte-for-byte the same framework with the brand swapped,
so migrating an existing database needs no schema *changes* — only a relabelling:

1. rename every ``microsys_*`` table to ``dlux_*`` (no M2M/through tables exist,
   so a flat prefix swap is complete);
2. create any ``dlux`` tables that did not exist in the source ``microsys``
   schema, for example backup/restore tables added after older Microsys
   releases;
3. repoint ``django_content_type`` ``app_label`` microsys -> dlux (permissions,
   which key off the content type, follow automatically);
4. collapse the recorded migration history to dlux's single ``0001_initial``
   (the renamed tables already carry the final, fully-migrated schema);
5. rewrite ``UserActivityLog.model_key`` values ``microsys.*`` -> ``dlux.*``.

Dry-run by default; pass ``--yes`` to apply. Take a database backup first.
Supported only from a *fully migrated* django-microsys 2.4.1 database.
"""
from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.migrations.recorder import MigrationRecorder

OLD = "microsys"
NEW = "dlux"


class Command(BaseCommand):
    help = "Migrate an existing django-microsys database in place to django-lux (dlux)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Apply the migration. Without this flag the command only prints the plan (dry-run).",
        )
        parser.add_argument(
            "--repair-missing-tables",
            action="store_true",
            help=(
                "Repair an already-relabelled django-lux database by creating "
                "missing concrete dlux tables from the current model state."
            ),
        )

    def handle(self, *args, **options):
        apply = options["yes"]
        repair_missing_tables = options["repair_missing_tables"]

        if not apps.is_installed(NEW):
            raise CommandError(
                f"The '{NEW}' app is not in INSTALLED_APPS. Install django-lux and switch "
                f"your settings from microsys to dlux before running this command."
            )

        existing = set(connection.introspection.table_names())
        old_tables = sorted(t for t in existing if t.startswith(OLD + "_"))
        renames = [(t, NEW + t[len(OLD):]) for t in old_tables]
        collisions = [new for _, new in renames if new in existing]
        missing_models = self._missing_dlux_models(existing, renames)

        if not old_tables:
            if repair_missing_tables and missing_models:
                return self._repair_missing_tables(missing_models, apply)
            raise CommandError(
                f"No '{OLD}_*' tables found in this database — nothing to migrate "
                f"(it may already be on django-lux)."
                + (
                    " Missing dlux table(s) were detected: "
                    + ", ".join(model._meta.db_table for model in missing_models)
                    + ". Re-run with --repair-missing-tables --yes to create them."
                    if missing_models
                    else ""
                )
            )
        if collisions:
            raise CommandError(
                "Target tables already exist, refusing to overwrite: "
                + ", ".join(collisions)
                + ". This database does not look like a clean django-microsys install."
            )

        ct_count = self._content_type_count()

        # ── plan summary ─────────────────────────────────────────────────────
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\nmicrosys → dlux migration plan ({connection.vendor}):"))
        self.stdout.write(f"  • rename {len(renames)} table(s)  {OLD}_*  →  {NEW}_*")
        for old, new in renames:
            self.stdout.write(f"      {old}  →  {new}")
        self.stdout.write(f"  • django_content_type: {ct_count} row(s) app_label '{OLD}' → '{NEW}'")
        if missing_models:
            self.stdout.write(f"  • create {len(missing_models)} missing dlux table(s)")
            for model in missing_models:
                self.stdout.write(f"      {model._meta.label}  →  {model._meta.db_table}")
        self.stdout.write(f"  • django_migrations: drop app '{OLD}' history, record '{NEW}.0001_initial' as applied")
        self.stdout.write(f"  • UserActivityLog.model_key: '{OLD}.*' → '{NEW}.*'")

        if not apply:
            self.stdout.write(self.style.WARNING(
                "\nDRY-RUN — nothing changed. Re-run with --yes to apply "
                "(back up your database first)."))
            return

        if connection.vendor == "mysql":
            self.stdout.write(self.style.WARNING(
                "Note: MySQL auto-commits DDL, so the table renames are not rolled "
                "back together if a later step fails. Ensure you have a backup."))

        with transaction.atomic():
            quote = connection.ops.quote_name
            with connection.cursor() as cursor:
                for old, new in renames:
                    cursor.execute(f"ALTER TABLE {quote(old)} RENAME TO {quote(new)}")

            self._create_missing_tables(missing_models)

            # Content types (permissions follow via content_type_id, unchanged).
            from django.contrib.contenttypes.models import ContentType
            ContentType.objects.filter(app_label=OLD).update(app_label=NEW)
            ContentType.objects.clear_cache()

            # Migration history: the renamed tables already hold the final schema,
            # so record dlux.0001_initial as applied and drop the old app history.
            recorder = MigrationRecorder(connection)
            recorder.ensure_schema()
            recorder.migration_qs.filter(app=OLD).delete()
            if not recorder.migration_qs.filter(app=NEW, name="0001_initial").exists():
                recorder.record_applied(NEW, "0001_initial")

            # App-label-qualified activity-log keys (microsys.x -> dlux.x).
            self._rewrite_model_keys()

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. Database migrated from django-microsys to django-lux. "
            f"Run `python manage.py migrate` to confirm no migrations are pending."))

    # ── helpers ──────────────────────────────────────────────────────────────

    def _missing_dlux_models(self, existing_tables, renames=()):
        """Return concrete managed dlux models whose tables will not exist."""
        renamed_old = {old for old, _ in renames}
        renamed_new = {new for _, new in renames}
        future_tables = (set(existing_tables) - renamed_old) | renamed_new
        missing = []
        for model in apps.get_app_config(NEW).get_models():
            opts = model._meta
            if opts.proxy or not opts.managed:
                continue
            if opts.db_table not in future_tables:
                missing.append(model)
        return missing

    def _create_missing_tables(self, missing_models):
        if not missing_models:
            return
        with connection.schema_editor() as schema_editor:
            for model in missing_models:
                schema_editor.create_model(model)

    def _repair_missing_tables(self, missing_models, apply):
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\ndjango-lux missing-table repair plan ({connection.vendor}):"))
        self.stdout.write(f"  • create {len(missing_models)} missing dlux table(s)")
        for model in missing_models:
            self.stdout.write(f"      {model._meta.label}  →  {model._meta.db_table}")

        if not apply:
            self.stdout.write(self.style.WARNING(
                "\nDRY-RUN — nothing changed. Re-run with --repair-missing-tables "
                "--yes to apply."))
            return

        with transaction.atomic():
            self._create_missing_tables(missing_models)

        self.stdout.write(self.style.SUCCESS(
            "\nDone. Missing django-lux tables were created. Run "
            "`python manage.py migrate` to confirm no migrations are pending."))

    def _content_type_count(self):
        from django.contrib.contenttypes.models import ContentType
        return ContentType.objects.filter(app_label=OLD).count()

    def _rewrite_model_keys(self):
        """UserActivityLog.model_key 'microsys.<model>' -> 'dlux.<model>'."""
        from django.db.models import Value
        from django.db.models.functions import Concat, Substr
        try:
            UAL = apps.get_model(NEW, "ActivityLog")
        except LookupError:
            return
        prefix_len = len(OLD) + 1  # length of "microsys" + the dot
        UAL.objects.filter(model_key__startswith=f"{OLD}.").update(
            model_key=Concat(Value(f"{NEW}."), Substr("model_key", prefix_len + 1))
        )
