import random
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.validators import FileExtensionValidator
from django.db import connection, models
from django.test import TransactionTestCase, override_settings

from dlux.management.commands.dlux_seed import (
    MetadataSeeder,
    MissingRelatedRows,
    build_seed_pdf,
    is_seedable_project_model,
)
from dlux.models import ActivityLog, Scope, ScopedModel
from dlux.reports import build_reports_overview


User = get_user_model()


class SeedLookup(models.Model):
    dlux_seed = True

    name = models.CharField(max_length=80, unique=True)

    class Meta:
        app_label = "seed_tests"


class SeedRecord(models.Model):
    dlux_seed = True

    lookup = models.ForeignKey(SeedLookup, on_delete=models.CASCADE)
    title = models.CharField(max_length=120, unique=True)
    status = models.CharField(
        max_length=12,
        choices=(("new", "New"), ("ready", "Ready")),
    )
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    occurred_on = models.DateField()
    active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict)
    notes = models.TextField(blank=True)

    class Meta:
        app_label = "seed_tests"


class SeedScopedRecord(ScopedModel):
    dlux_seed = True

    title = models.CharField(max_length=120, unique=True)

    class Meta:
        app_label = "seed_tests"


class DluxSeedTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with connection.schema_editor() as editor:
            editor.create_model(SeedLookup)
            editor.create_model(SeedRecord)
            editor.create_model(SeedScopedRecord)

    @classmethod
    def tearDownClass(cls):
        with connection.schema_editor() as editor:
            editor.delete_model(SeedScopedRecord)
            editor.delete_model(SeedRecord)
            editor.delete_model(SeedLookup)
        super().tearDownClass()

    def tearDown(self):
        SeedScopedRecord.all_objects.all().delete()
        SeedRecord.objects.all().delete()
        SeedLookup.objects.all().delete()
        super().tearDown()

    @staticmethod
    def _command_patches(discovered):
        return (
            mock.patch(
                "dlux.management.commands.dlux_seed.discover_seed_models",
                return_value=discovered,
            ),
            mock.patch(
                "dlux.management.commands.dlux_seed.get_populate_command",
                return_value=None,
            ),
        )

    def test_metadata_seeder_generates_typed_values_and_relations(self):
        seeder = MetadataSeeder(database="default", rng=random.Random(7), batch_label="unit")
        seeder.seed_model(SeedLookup, 3)
        rows = seeder.seed_model(SeedRecord, 4)

        self.assertEqual(len(rows), 4)
        self.assertEqual(SeedRecord.objects.count(), 4)
        self.assertTrue(all(row.lookup_id for row in rows))
        self.assertTrue(all(row.status in {"new", "ready"} for row in rows))
        self.assertTrue(all(row.occurred_on for row in rows))
        self.assertTrue(all(isinstance(row.metadata, dict) for row in rows))

    def test_required_empty_relation_blocks_model(self):
        seeder = MetadataSeeder(database="default", rng=random.Random(3), batch_label="unit")

        with self.assertRaises(MissingRelatedRows):
            seeder.seed_model(SeedRecord, 1)

    def test_required_pdf_file_is_a_complete_one_page_document(self):
        field = models.FileField(validators=[FileExtensionValidator(["pdf"])])
        field.set_attributes_from_name("document")
        seeder = MetadataSeeder(database="default", rng=random.Random(3), batch_label="unit")

        seeded_file = seeder._field_value(SeedRecord, field, 1, 1)
        pdf_bytes = seeded_file.read()
        startxref = int(pdf_bytes.rsplit(b"startxref\n", 1)[1].splitlines()[0])

        self.assertEqual(seeded_file.name.rsplit(".", 1)[1], "pdf")
        self.assertEqual(pdf_bytes, build_seed_pdf(seeded_file.name[:-4]))
        self.assertTrue(pdf_bytes.startswith(b"%PDF-1.4\n"))
        self.assertTrue(pdf_bytes.endswith(b"%%EOF\n"))
        self.assertEqual(pdf_bytes[startxref : startxref + 4], b"xref")
        self.assertIn(b"/Type /Page ", pdf_bytes)
        self.assertIn(b"/Count 1", pdf_bytes)

    def test_command_is_dry_run_then_applies_discovered_models(self):
        discovered = [SeedLookup, SeedRecord]
        self.assertTrue(all(is_seedable_project_model(model) for model in discovered))

        discovery_patch, populate_patch = self._command_patches(discovered)
        with discovery_patch, populate_patch:
            output = StringIO()
            call_command(
                "dlux_seed",
                "seed_tests.SeedLookup",
                "seed_tests.SeedRecord",
                "--count",
                "2",
                stdout=output,
            )
            self.assertEqual(SeedLookup.objects.count(), 0)
            self.assertIn("Dry run only", output.getvalue())

            call_command(
                "dlux_seed",
                "seed_tests.SeedLookup",
                "seed_tests.SeedRecord",
                "--count",
                "2",
                "--seed",
                "11",
                "--apply",
                stdout=StringIO(),
            )

        self.assertEqual(SeedLookup.objects.count(), 2)
        self.assertEqual(SeedRecord.objects.count(), 2)
        self.assertFalse(
            ActivityLog.all_objects.filter(model_key__startswith="seed_tests.").exists()
        )

    @override_settings(DLUX_CONFIG={"reports": {"overview_cache_seconds": 0}})
    def test_fixed_user_and_scope_are_applied_and_reported(self):
        user = User.objects.create_superuser(
            username="seed-owner",
            email="seed-owner@example.com",
            password="test-pass-123",
        )
        scope = Scope.objects.create(name="Seed scope")
        ActivityLog.all_objects.all().delete()

        discovery_patch, populate_patch = self._command_patches([SeedScopedRecord])
        output = StringIO()
        with discovery_patch, populate_patch:
            call_command(
                "dlux_seed",
                "seed_tests.SeedScopedRecord",
                "--count",
                "3",
                "--seed",
                "17",
                "--user-id",
                str(user.pk),
                "--scope-id",
                str(scope.pk),
                "--apply",
                stdout=output,
            )

        rows = list(SeedScopedRecord.all_objects.order_by("pk"))
        logs = ActivityLog.all_objects.filter(model_key="seed_tests.seedscopedrecord")
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(row.created_by_id == user.pk for row in rows))
        self.assertTrue(all(row.updated_by_id == user.pk for row in rows))
        self.assertTrue(all(row.scope_id == scope.pk for row in rows))
        self.assertEqual(logs.count(), 3)
        self.assertFalse(logs.exclude(created_by=user, scope=scope).exists())
        self.assertFalse(logs.exclude(action="CREATE", category="user").exists())
        self.assertEqual(build_reports_overview(user, window="all")["current_total"], 3)
        self.assertIn("Logged 3 activity row(s)", output.getvalue())

    def test_log_uses_random_active_users_and_their_scopes(self):
        first_scope = Scope.objects.create(name="First scope")
        second_scope = Scope.objects.create(name="Second scope")
        first_user = User.objects.create_user(username="seed-first", is_active=True)
        second_user = User.objects.create_user(username="seed-second", is_active=True)
        inactive_user = User.objects.create_user(username="seed-inactive", is_active=False)
        first_user.profile.scope = first_scope
        first_user.profile.save(update_fields=["scope"])
        second_user.profile.scope = second_scope
        second_user.profile.save(update_fields=["scope"])
        inactive_user.profile.scope = first_scope
        inactive_user.profile.save(update_fields=["scope"])
        ActivityLog.all_objects.all().delete()

        discovery_patch, populate_patch = self._command_patches([SeedLookup])
        with discovery_patch, populate_patch:
            call_command(
                "dlux_seed",
                "seed_tests.SeedLookup",
                "--count",
                "12",
                "--seed",
                "23",
                "--log",
                "--apply",
                stdout=StringIO(),
            )

        logs = ActivityLog.all_objects.filter(model_key="seed_tests.seedlookup")
        actor_ids = set(logs.values_list("created_by_id", flat=True))
        self.assertEqual(logs.count(), 12)
        self.assertEqual(actor_ids, {first_user.pk, second_user.pk})
        self.assertFalse(logs.filter(created_by=inactive_user).exists())
        self.assertFalse(
            logs.exclude(
                models.Q(created_by=first_user, scope=first_scope)
                | models.Q(created_by=second_user, scope=second_scope)
            ).exists()
        )

    def test_scope_id_implies_logging_with_a_fixed_scope(self):
        user = User.objects.create_user(username="seed-random-scope", is_active=True)
        scope = Scope.objects.create(name="Forced scope")
        ActivityLog.all_objects.all().delete()

        discovery_patch, populate_patch = self._command_patches([SeedLookup])
        with discovery_patch, populate_patch:
            call_command(
                "dlux_seed",
                "seed_tests.SeedLookup",
                "--count",
                "2",
                "--scope-id",
                str(scope.pk),
                "--apply",
                stdout=StringIO(),
            )

        logs = ActivityLog.all_objects.filter(model_key="seed_tests.seedlookup")
        self.assertEqual(logs.count(), 2)
        self.assertFalse(logs.exclude(created_by=user, scope=scope).exists())

    def test_logging_rejects_missing_actor_or_scope(self):
        user = User.objects.create_user(username="seed-validation", is_active=True)
        discovery_patch, populate_patch = self._command_patches([SeedLookup])
        with discovery_patch, populate_patch:
            with self.assertRaisesMessage(CommandError, "User with ID"):
                call_command(
                    "dlux_seed",
                    "seed_tests.SeedLookup",
                    "--user-id",
                    str(user.pk + 1000),
                    stdout=StringIO(),
                )

        discovery_patch, populate_patch = self._command_patches([SeedLookup])
        with discovery_patch, populate_patch:
            with self.assertRaisesMessage(CommandError, "Scope with ID"):
                call_command(
                    "dlux_seed",
                    "seed_tests.SeedLookup",
                    "--scope-id",
                    "999999",
                    stdout=StringIO(),
                )
