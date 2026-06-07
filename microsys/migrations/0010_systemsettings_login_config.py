from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('microsys', '0009_report_permissions'),
    ]

    operations = [
        migrations.AddField(
            model_name='systemsettings',
            name='login_config',
            field=models.JSONField(blank=True, default=dict, verbose_name='Login Page Configuration'),
        ),
    ]
