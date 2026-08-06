from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dlux', '0014_systembackup_liveness'),
    ]

    operations = [
        migrations.AddField(
            model_name='systemrestore',
            name='progress_percent',
            field=models.PositiveSmallIntegerField(db_default=0, default=0, verbose_name='Progress Percent'),
        ),
        migrations.AddField(
            model_name='systemrestore',
            name='progress_message',
            field=models.CharField(blank=True, db_default='', default='', max_length=255, verbose_name='Progress Message'),
        ),
        migrations.AddField(
            model_name='systemrestore',
            name='stage',
            field=models.CharField(blank=True, db_default='', default='', max_length=20, verbose_name='Stage'),
        ),
        migrations.AddField(
            model_name='systemrestore',
            name='heartbeat_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Heartbeat At'),
        ),
    ]
