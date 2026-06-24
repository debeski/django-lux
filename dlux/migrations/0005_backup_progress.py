from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dlux', '0004_system_backup_policy'),
    ]

    operations = [
        migrations.AddField(
            model_name='reportbackup',
            name='progress_message',
            field=models.CharField(
                blank=True,
                db_default='',
                default='',
                max_length=255,
                verbose_name='Progress Message',
            ),
        ),
        migrations.AddField(
            model_name='reportbackup',
            name='progress_percent',
            field=models.PositiveSmallIntegerField(
                db_default=0,
                default=0,
                verbose_name='Progress Percent',
            ),
        ),
        migrations.AddField(
            model_name='systembackup',
            name='progress_message',
            field=models.CharField(
                blank=True,
                db_default='',
                default='',
                max_length=255,
                verbose_name='Progress Message',
            ),
        ),
        migrations.AddField(
            model_name='systembackup',
            name='progress_percent',
            field=models.PositiveSmallIntegerField(
                db_default=0,
                default=0,
                verbose_name='Progress Percent',
            ),
        ),
    ]
