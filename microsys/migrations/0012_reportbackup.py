import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import microsys.models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("microsys", "0011_useractivitylog_model_key"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReportBackup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "token",
                    models.CharField(
                        default=microsys.models.generate_report_backup_token,
                        editable=False,
                        max_length=64,
                        unique=True,
                        verbose_name="Token",
                    ),
                ),
                ("window", models.CharField(default="all", max_length=10, verbose_name="Window")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("running", "Running"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=12,
                        verbose_name="Status",
                    ),
                ),
                ("file_path", models.CharField(blank=True, max_length=512, verbose_name="File Path")),
                ("file_size", models.BigIntegerField(default=0, verbose_name="File Size")),
                ("model_count", models.PositiveIntegerField(default=0, verbose_name="Model Count")),
                ("file_count", models.PositiveIntegerField(default=0, verbose_name="File Count")),
                ("missing_file_count", models.PositiveIntegerField(default=0, verbose_name="Missing File Count")),
                ("error", models.TextField(blank=True, verbose_name="Error")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Created At")),
                ("started_at", models.DateTimeField(blank=True, null=True, verbose_name="Started At")),
                ("completed_at", models.DateTimeField(blank=True, null=True, verbose_name="Completed At")),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="microsys_report_backups",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="User",
                    ),
                ),
            ],
            options={
                "verbose_name": "Report Backup",
                "verbose_name_plural": "Report Backups",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="SystemBackup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "token",
                    models.CharField(
                        default=microsys.models.generate_report_backup_token,
                        editable=False,
                        max_length=64,
                        unique=True,
                        verbose_name="Token",
                    ),
                ),
                ("requested_by_username", models.CharField(blank=True, max_length=150, verbose_name="Requested By")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("running", "Running"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=12,
                        verbose_name="Status",
                    ),
                ),
                ("file_path", models.CharField(blank=True, max_length=512, verbose_name="File Path")),
                ("file_size", models.BigIntegerField(default=0, verbose_name="File Size")),
                ("model_count", models.PositiveIntegerField(default=0, verbose_name="Model Count")),
                ("row_count", models.PositiveIntegerField(default=0, verbose_name="Row Count")),
                ("file_count", models.PositiveIntegerField(default=0, verbose_name="File Count")),
                ("missing_file_count", models.PositiveIntegerField(default=0, verbose_name="Missing File Count")),
                ("passphrase_required", models.BooleanField(default=False, verbose_name="Passphrase Required")),
                ("error", models.TextField(blank=True, verbose_name="Error")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Created At")),
                ("started_at", models.DateTimeField(blank=True, null=True, verbose_name="Started At")),
                ("completed_at", models.DateTimeField(blank=True, null=True, verbose_name="Completed At")),
            ],
            options={
                "verbose_name": "System Backup",
                "verbose_name_plural": "System Backups",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="SystemRestore",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "token",
                    models.CharField(
                        default=microsys.models.generate_report_backup_token,
                        editable=False,
                        max_length=64,
                        unique=True,
                        verbose_name="Token",
                    ),
                ),
                ("requested_by_username", models.CharField(blank=True, max_length=150, verbose_name="Requested By")),
                ("backup_file_path", models.CharField(max_length=512, verbose_name="Backup File Path")),
                ("ignore_version_mismatch", models.BooleanField(default=False, verbose_name="Ignore Version Mismatch")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("running", "Running"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=12,
                        verbose_name="Status",
                    ),
                ),
                ("report", models.JSONField(blank=True, default=dict, verbose_name="Report")),
                ("error", models.TextField(blank=True, verbose_name="Error")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Created At")),
                ("started_at", models.DateTimeField(blank=True, null=True, verbose_name="Started At")),
                ("completed_at", models.DateTimeField(blank=True, null=True, verbose_name="Completed At")),
            ],
            options={
                "verbose_name": "System Restore",
                "verbose_name_plural": "System Restores",
                "ordering": ["-created_at"],
            },
        ),
    ]
