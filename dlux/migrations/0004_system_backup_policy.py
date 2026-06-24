import dlux.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dlux', '0003_dlux_update_runtime'),
    ]

    operations = [
        migrations.AddField(
            model_name='systemsettings',
            name='backup_config',
            field=models.JSONField(blank=True, default=dlux.models.default_backup_config, verbose_name='Backup Configuration'),
        ),
        migrations.AddField(
            model_name='systembackup',
            name='trigger',
            field=models.CharField(
                choices=[('manual', 'Manual'), ('scheduled', 'Scheduled'), ('update', 'DjangoLux update')],
                # db_default keeps a persistent database-level default so the previous
                # release's code (which has no `trigger` field) can still INSERT a
                # SystemBackup row after this migration applies — e.g. the updater's
                # pre-update backup running under the old code after a rollback. A plain
                # Python `default` is dropped from the column and would break those inserts.
                db_default='manual',
                db_index=True,
                default='manual',
                max_length=12,
                verbose_name='Trigger',
            ),
        ),
    ]
