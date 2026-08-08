from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dlux', '0015_systemrestore_progress'),
    ]

    operations = [
        migrations.AddField(
            model_name='scope',
            name='default_theme',
            field=models.CharField(blank=True, db_default='', default='', max_length=50, verbose_name='Default Theme'),
        ),
    ]
