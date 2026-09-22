from django.db import migrations, models


class Migration(migrations.Migration):
    """Record the update check interval beside the release channel.

    Additive and inline-safe, like 0021: one column with a database default, so
    existing rows read 15 minutes without a rewrite and a deployment running the
    previous release against this schema never reads it.
    """

    dependencies = [
        ('dlux', '0021_update_state_channel'),
    ]

    operations = [
        migrations.AddField(
            model_name='dluxupdatestate',
            name='check_interval_minutes',
            field=models.PositiveIntegerField(
                db_default=15, default=15,
                verbose_name='Update Check Interval (minutes)',
            ),
        ),
    ]
