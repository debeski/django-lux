import random
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.validators import FileExtensionValidator
from django.db import connection, models
from django.test import TransactionTestCase

from dlux.management.commands.dlux_seed import (
    MetadataSeeder,
    MissingRelatedRows,
    build_seed_pdf,
    is_seedable_project_model,
)


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


class DluxSeedTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with connection.schema_editor() as editor:
            editor.create_model(SeedLookup)
            editor.create_model(SeedRecord)

    @classmethod
    def tearDownClass(cls):
        with connection.schema_editor() as editor:
            editor.delete_model(SeedRecord)
            editor.delete_model(SeedLookup)
        super().tearDownClass()

    def tearDown(self):
        SeedRecord.objects.all().delete()
        SeedLookup.objects.all().delete()
        super().tearDown()

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

        with mock.patch(
            "dlux.management.commands.dlux_seed.discover_seed_models",
            return_value=discovered,
        ), mock.patch(
            "dlux.management.commands.dlux_seed.get_populate_command",
            return_value=None,
        ):
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
