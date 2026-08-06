from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dlux', '0013_alter_profile_options'),
    ]

    operations = [
        migrations.AddField(
            model_name='systembackup',
            name='heartbeat_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Heartbeat At'),
        ),
        migrations.AddField(
            model_name='systembackup',
            name='stage',
            field=models.CharField(blank=True, db_default='', default='', max_length=20, verbose_name='Stage'),
        ),
        migrations.AddField(
            model_name='systembackup',
            name='attempt_count',
            field=models.PositiveSmallIntegerField(db_default=0, default=0, verbose_name='Attempts'),
        ),
        migrations.AddField(
            model_name='systembackup',
            name='next_attempt_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Next Attempt At'),
        ),
        migrations.AddField(
            model_name='reportbackup',
            name='criteria',
            field=models.JSONField(blank=True, db_default={}, default=dict, verbose_name='Report Criteria'),
        ),
    ]
