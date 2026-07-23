from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("dlux", "0010_dluxupdatestate_skipped_versions"),
    ]

    operations = [
        migrations.AddField(
            model_name="dluximageupdate",
            name="control_operation_id",
            field=models.UUIDField(blank=True, null=True, unique=True, verbose_name="Control Operation ID"),
        ),
        migrations.AddField(
            model_name="dluximageupdate",
            name="request_source",
            field=models.CharField(
                choices=[("local", "Local"), ("control", "Control Plane")],
                db_default="local",
                default="local",
                max_length=16,
                verbose_name="Request Source",
            ),
        ),
    ]
