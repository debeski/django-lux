from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dlux', '0018_managed_asset_namespace'),
    ]

    operations = [
        migrations.AddField(
            model_name='dluxupdatestate',
            name='worker_seen_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Update Worker Seen At'),
        ),
        migrations.AddField(
            model_name='dluxupdatestate',
            name='worker_volume_problem',
            field=models.TextField(blank=True, db_default='', default='', verbose_name='Update Worker Volume Problem'),
        ),
    ]
