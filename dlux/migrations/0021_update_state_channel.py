from django.db import migrations, models


class Migration(migrations.Migration):
    """Record the release channel beside the rest of the updater state.

    Additive and inline-safe: one nullable-free CharField with a database
    default, so the column is populated for existing rows by PostgreSQL itself
    rather than by a rewrite, and a deployment running the previous release
    against this schema simply never reads it.
    """

    dependencies = [
        ('dlux', '0020_update_run_applying_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='dluxupdatestate',
            name='update_channel',
            field=models.CharField(
                db_default='stable', default='stable', max_length=16,
                verbose_name='Update Channel',
            ),
        ),
    ]
