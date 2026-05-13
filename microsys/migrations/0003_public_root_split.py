from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('microsys', '0002_public_registration'),
    ]

    operations = [
        migrations.AddField(
            model_name='systemsettings',
            name='public_root_split_enabled',
            field=models.BooleanField(default=False, verbose_name='Separate Public Root From Home'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='public_root_url',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Public Root URL'),
        ),
    ]
