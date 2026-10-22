from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('dlux', '0027_opsrun_params')]

    operations = [
        migrations.AddField(
            model_name='systemsettings',
            name='tables_config',
            field=models.JSONField(blank=True, db_default={}, default=dict, verbose_name='Tables Configuration'),
        ),
    ]
