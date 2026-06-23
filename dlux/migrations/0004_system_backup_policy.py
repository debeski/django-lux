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
                db_index=True,
                default='manual',
                max_length=12,
                verbose_name='Trigger',
            ),
        ),
    ]
